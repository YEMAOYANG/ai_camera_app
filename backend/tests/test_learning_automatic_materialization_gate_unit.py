from __future__ import annotations

import unittest
from contextlib import contextmanager

from services.learning_service import LearningService


def _child(grade_code: str) -> dict[str, object]:
    return {
        "id": f"child-{grade_code}",
        "family_id": "family-1",
        "grade_code": grade_code,
        "grade_selection_revision": 1,
    }


def _formal_ready_plan() -> dict[str, object]:
    return {
        "grade_code": "primary_1",
        "status": "ready",
        "stage": "completed",
        "progress_percent": 100,
        "total_course_count": 30,
        "ready_course_count": 30,
        "failed_course_count": 0,
        "content_target_count": 30,
        "content_candidate_count": 30,
        "content_failed_count": 0,
        "classroom_ready_count": 30,
        "speech_ready_count": 30,
        "validation_ready_count": 30,
        "published_course_count": 30,
        "formal_ready_at": 123,
        "completed_at": 123,
        "catalog_release_id": "release-1",
        "target_fingerprint": "b" * 64,
        "formal_contract_version": "mira.learning.formal-publication.v1",
        "formal_publication_history_id": "history-1",
        "formal_publication_receipt_hash": "a" * 64,
    }


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self, release_row):
        self.release_row = release_row
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]):
        self.calls.append((query, params))
        return _Result(self.release_row)


class _Repository:
    def __init__(self, child: dict[str, object], release_row):
        self.child = child
        self.conn = _Connection(release_row)

    @contextmanager
    def transaction(self):
        yield self.conn

    def list_primary_children_pending_daily_preparation(
        self,
        _conn,
        *,
        learning_date,
    ):
        del learning_date
        return [self.child]


class _ProfileRepository:
    def __init__(self, repository: _Repository):
        self.repository = repository

    def get_child(self, _conn, *, family_id, child_id, for_update=False):
        del for_update
        child = self.repository.child
        if child["family_id"] != family_id or child["id"] != child_id:
            return None
        return dict(child)


def _service(child: dict[str, object], release_row):
    service = object.__new__(LearningService)
    service.repository = _Repository(child, release_row)
    service.profile_repository = _ProfileRepository(service.repository)
    service.formal_learning_access_checker = None
    service._ensure_catalog = lambda: None
    service._learning_date = lambda value: value or "2026-09-10"
    service.dynamic_calls = []
    service.materialization_calls = []

    def ensure_dynamic_supply(*, child, learning_date):
        service.dynamic_calls.append((child["id"], learning_date))

    def ensure_today(_conn, **kwargs):
        service.materialization_calls.append(kwargs)
        return [], 3

    service._ensure_dynamic_supply = ensure_dynamic_supply
    service._ensure_today_for_child = ensure_today
    return service


class LearningAutomaticMaterializationGateUnitTest(unittest.TestCase):
    def test_unopened_grade_is_skipped_before_provider_or_materialization(self):
        service = _service(_child("primary_2"), _formal_ready_plan())

        result = service.ensure_today_for_all_primary_children(
            learning_date="2026-09-10"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["createdCount"], 0)
        self.assertEqual(result["childrenEnsured"], 0)
        self.assertEqual(result.get("childrenSkipped"), 1)
        self.assertEqual(result["failures"], [])
        self.assertEqual(
            (result.get("skipped") or [{}])[0].get("code"),
            "student_learning_grade_not_open",
        )
        self.assertEqual(service.dynamic_calls, [])
        self.assertEqual(service.materialization_calls, [])
        self.assertEqual(service.repository.conn.calls, [])

    def test_unready_formal_release_is_skipped_before_provider_or_materialization(self):
        service = _service(_child("primary_1"), None)

        result = service.ensure_today_for_all_primary_children(
            learning_date="2026-09-10"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["createdCount"], 0)
        self.assertEqual(result["childrenEnsured"], 0)
        self.assertEqual(result.get("childrenSkipped"), 1)
        self.assertEqual(result["failures"], [])
        self.assertEqual(
            (result.get("skipped") or [{}])[0].get("code"),
            "student_learning_release_not_ready",
        )
        self.assertEqual(service.dynamic_calls, [])
        self.assertEqual(service.materialization_calls, [])
        self.assertEqual(len(service.repository.conn.calls), 1)

    def test_ready_formal_release_allows_provider_then_materialization(self):
        service = _service(_child("primary_1"), _formal_ready_plan())

        result = service.ensure_today_for_all_primary_children(
            learning_date="2026-09-10"
        )

        self.assertEqual(result["failures"], [])
        self.assertEqual(result["childrenEnsured"], 1)
        self.assertEqual(result.get("childrenSkipped"), 0)
        self.assertEqual(result.get("skipped"), [])
        self.assertEqual(result["createdCount"], 3)
        self.assertEqual(
            service.dynamic_calls,
            [("child-primary_1", "2026-09-10")],
        )
        self.assertEqual(len(service.materialization_calls), 1)
        self.assertEqual(len(service.repository.conn.calls), 2)

    def test_materialization_rechecks_live_grade_after_initial_gate(self):
        service = _service(_child("primary_1"), _formal_ready_plan())
        original_dynamic_supply = service._ensure_dynamic_supply

        def switch_grade_after_initial_gate(*, child, learning_date):
            original_dynamic_supply(child=child, learning_date=learning_date)
            service.repository.child = {
                **service.repository.child,
                "grade_code": "primary_2",
                "grade_selection_revision": 2,
            }

        service._ensure_dynamic_supply = switch_grade_after_initial_gate

        result = service.ensure_today_for_all_primary_children(
            learning_date="2026-09-11"
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["createdCount"], 0)
        self.assertEqual(result["childrenEnsured"], 0)
        self.assertEqual(result["childrenSkipped"], 1)
        self.assertEqual(result["skipped"][0]["code"], "student_learning_grade_not_open")
        self.assertEqual(
            service.dynamic_calls,
            [("child-primary_1", "2026-09-11")],
        )
        self.assertEqual(service.materialization_calls, [])


if __name__ == "__main__":
    unittest.main()
