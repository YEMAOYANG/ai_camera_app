from __future__ import annotations

import unittest
from contextlib import contextmanager

from core.errors import ApiError
from repositories.learning_repository import LearningRepository
from services.learning_service import LearningService


def _report(report_id: str, *, child_id: str, created_at: int) -> dict:
    return {
        "id": report_id,
        "family_id": "family_1",
        "child_id": child_id,
        "task_id": f"task_{report_id}",
        "session_id": f"session_{report_id}",
        "course_id": f"course_{report_id}",
        "course_version": "1.0.0",
        "course_title": "20 以内加减法",
        "learning_date": "2026-08-25",
        "grade_code": "primary_1",
        "subject": "math",
        "score": 100,
        "correct_count": 4,
        "independent_correct_count": 2,
        "hint_count": 0,
        "total_questions": 4,
        "mastery_level": "mastered",
        "summary": "独立检查全部正确。",
        "strengths_json": '["计算准确"]',
        "next_step": "继续下一能力点。",
        "created_at": created_at,
    }


class _ParentAuth:
    def authenticate(self, access_token: str) -> dict:
        if access_token != "parent_token":
            raise AssertionError("unexpected parent token")
        return {
            "family": {"id": "family_1"},
            "user": {"id": "user_1"},
        }


class _ProfileRepository:
    def get_child(self, conn, *, family_id: str, child_id: str):
        if family_id == "family_1" and child_id in {"child_1", "child_2"}:
            return {"id": child_id, "family_id": family_id}
        return None


class _ReportRepository:
    def __init__(self):
        self.rows = [
            _report("report_3", child_id="child_1", created_at=300),
            _report("report_2", child_id="child_1", created_at=200),
            _report("report_1", child_id="child_1", created_at=100),
        ]
        self.last_list_scope = None

    @contextmanager
    def transaction(self):
        yield object()

    def list_reports(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        subject: str | None,
        cursor: tuple[int, str] | None,
        limit: int,
    ):
        self.last_list_scope = (family_id, child_id, subject, cursor, limit)
        rows = [row for row in self.rows if row["child_id"] == child_id]
        if subject:
            rows = [row for row in rows if row["subject"] == subject]
        if cursor is not None:
            rows = [
                row
                for row in rows
                if row["created_at"] < cursor[0]
                or (
                    row["created_at"] == cursor[0]
                    and row["id"] < cursor[1]
                )
            ]
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more:
            last = page[-1]
            next_cursor = LearningRepository.encode_report_cursor(
                last["created_at"],
                last["id"],
            )
        return page, next_cursor

    def get_report_detail(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        report_id: str,
    ):
        return next(
            (
                row
                for row in self.rows
                if row["family_id"] == family_id
                and row["child_id"] == child_id
                and row["id"] == report_id
            ),
            None,
        )


def _service(repository: _ReportRepository | None = None) -> LearningService:
    service = object.__new__(LearningService)
    service.auth_service = _ParentAuth()
    service.profile_repository = _ProfileRepository()
    service.repository = repository or _ReportRepository()
    return service


class ParentLearningReportsServiceTest(unittest.TestCase):
    def test_report_cursor_round_trip_is_opaque_and_rejects_malformed_values(self):
        self.assertTrue(
            hasattr(LearningRepository, "encode_report_cursor"),
            "report cursor encoding is not implemented",
        )
        cursor = LearningRepository.encode_report_cursor(200, "report_2")
        self.assertNotIn("report_2", cursor)
        self.assertEqual(
            LearningRepository.decode_report_cursor(cursor),
            (200, "report_2"),
        )
        for malformed in ("!", "a", "W10", "bnVsbA"):
            with self.assertRaises(ValueError):
                LearningRepository.decode_report_cursor(malformed)

    def test_parent_lists_reports_with_owned_child_subject_and_cursor_pagination(self):
        repository = _ReportRepository()
        service = _service(repository)
        self.assertTrue(
            hasattr(service, "list_reports"),
            "parent report listing is not implemented",
        )

        first = service.list_reports(
            "parent_token",
            {"childId": "child_1", "subject": "math", "limit": "2"},
        )
        second = service.list_reports(
            "parent_token",
            {
                "childId": "child_1",
                "subject": "math",
                "limit": "2",
                "cursor": first["nextCursor"],
            },
        )

        self.assertEqual([item["id"] for item in first["items"]], ["report_3", "report_2"])
        self.assertEqual([item["id"] for item in second["items"]], ["report_1"])
        self.assertIsNone(second["nextCursor"])
        self.assertEqual(first["items"][0]["courseTitle"], "20 以内加减法")
        self.assertEqual(first["items"][0]["sessionId"], "session_report_3")
        self.assertEqual(repository.last_list_scope[:3], ("family_1", "child_1", "math"))

    def test_parent_report_detail_is_fail_closed_to_requested_child(self):
        service = _service()
        self.assertTrue(
            hasattr(service, "report_detail"),
            "parent report detail is not implemented",
        )

        payload = service.report_detail(
            "parent_token",
            "report_3",
            {"childId": "child_1"},
        )
        self.assertEqual(payload["report"]["id"], "report_3")
        self.assertEqual(payload["report"]["childId"], "child_1")

        with self.assertRaises(ApiError) as caught:
            service.report_detail(
                "parent_token",
                "report_3",
                {"childId": "child_2"},
            )
        self.assertEqual(caught.exception.code, "learning_report_not_found")


if __name__ == "__main__":
    unittest.main()
