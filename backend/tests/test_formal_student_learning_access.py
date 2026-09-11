from __future__ import annotations

import unittest

from core.errors import ApiError
from services.formal_student_learning_access import (
    assert_formal_student_release_ready,
    assert_formal_student_workspace_open,
    formal_student_release_available,
)


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.row = row
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...]):
        self.calls.append((query, params))
        return _Result(self.row)


def _child(grade_code: str = "primary_1") -> dict[str, object]:
    return {
        "id": "child-1",
        "family_id": "family-1",
        "grade_code": grade_code,
        "grade_selection_revision": 2,
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


class FormalStudentLearningAccessTest(unittest.TestCase):
    def test_availability_reuses_the_active_formal_release_gate(self) -> None:
        ready = _Connection(_formal_ready_plan())
        incomplete_plan = _formal_ready_plan()
        incomplete_plan["published_course_count"] = 29

        self.assertTrue(formal_student_release_available(ready, _child()))
        self.assertFalse(
            formal_student_release_available(
                _Connection(incomplete_plan),
                _child(),
            )
        )
        unopened = _Connection(_formal_ready_plan())
        self.assertFalse(
            formal_student_release_available(unopened, _child("primary_2"))
        )
        self.assertEqual(unopened.calls[0][1], ("primary_2",))

    def test_exact_current_formal_release_is_allowed(self) -> None:
        conn = _Connection(_formal_ready_plan())

        assert_formal_student_release_ready(conn, _child())

        self.assertEqual(len(conn.calls), 1)
        query, params = conn.calls[0]
        self.assertIn("learning_curriculum_grade_release_pointers", query)
        self.assertIn("learning_curriculum_grade_release_history", query)
        self.assertEqual(params, ("primary_1",))
        self.assertNotIn("plan.family_id = ?", query)
        self.assertNotIn("plan.child_id = ?", query)

    def test_write_gate_locks_matching_plan_pointer_and_history(self) -> None:
        conn = _Connection(_formal_ready_plan())

        try:
            assert_formal_student_release_ready(
                conn,
                _child(),
                for_update=True,
            )
        except TypeError as exc:
            self.fail(f"formal write gate does not support row locking: {exc}")

        query, _ = conn.calls[0]
        self.assertRegex(query.strip(), r"LIMIT 1\s+FOR UPDATE$")

    def test_incomplete_formal_course_evidence_fails_closed(self) -> None:
        plan = _formal_ready_plan()
        plan["published_course_count"] = 29

        with self.assertRaises(ApiError) as raised:
            assert_formal_student_release_ready(_Connection(plan), _child())

        self.assertEqual(raised.exception.code, "student_learning_release_not_ready")

    def test_registered_grade_without_its_own_release_stays_closed(self) -> None:
        conn = _Connection(_formal_ready_plan())

        with self.assertRaises(ApiError) as raised:
            assert_formal_student_release_ready(conn, _child("primary_2"))

        self.assertEqual(raised.exception.code, "student_learning_release_not_ready")
        self.assertEqual(conn.calls[0][1], ("primary_2",))

    def test_each_registered_grade_requires_its_exact_published_capacity(self):
        for number in range(2, 7):
            grade = f"primary_{number}"
            plan = {key: 27 if value == 30 else value for key, value in _formal_ready_plan().items()}
            plan["grade_code"] = grade
            self.assertTrue(formal_student_release_available(_Connection(plan), _child(grade)))
            plan["published_course_count"] = 26
            self.assertFalse(formal_student_release_available(_Connection(plan), _child(grade)))

    def test_saved_grade_revision_opens_workspace_before_catalog_is_ready(self) -> None:
        self.assertEqual(
            assert_formal_student_workspace_open(_child()),
            "primary_1",
        )
        unsaved = _child()
        unsaved["grade_selection_revision"] = 0
        with self.assertRaises(ApiError) as raised:
            assert_formal_student_workspace_open(unsaved)
        self.assertEqual(
            raised.exception.code,
            "student_learning_release_not_ready",
        )


if __name__ == "__main__":
    unittest.main()
