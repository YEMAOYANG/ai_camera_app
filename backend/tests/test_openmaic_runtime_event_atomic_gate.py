from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
import unittest

from core.database import Database
from core.errors import ApiError
from repositories.openmaic_runtime_event_repository import (
    OpenMaicRuntimeEventRepository,
)
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService
from tests.support import fresh_test_config
from tests.test_openmaic_runtime_event_bridge import NOW, _LearningService, _event


class _BarrierChildRepository:
    """Use the real test database for the child lock at the race boundary."""

    def __init__(
        self,
        database: Database,
        *,
        snapshot_barrier: Barrier,
        grade_committed: Event,
    ):
        self.database = database
        self.snapshot_barrier = snapshot_barrier
        self.grade_committed = grade_committed

    def transaction(self):
        return self.database.transaction()

    def get_runtime_subject(self, _conn, **_kwargs):
        self.snapshot_barrier.wait(timeout=10)
        if not self.grade_committed.wait(timeout=10):
            raise AssertionError("grade update did not commit before the child lock")
        return {
            "runtime_session_id": "runtime-session-1",
            "principal_id": "principal-1",
            "family_id": "family-runtime-gate",
            "child_id": "child-runtime-gate",
            "learning_session_id": "learning-session-1",
            "runtime_classroom_id": "runtime-row-1",
            "upstream_classroom_id": "classroom-1",
            "task_id": "task-1",
            "course_id": "course-1",
            "course_version": "1",
            "package_id": "package-1",
            "package_version": 1,
        }

    @staticmethod
    def get_child_for_update(conn, *, family_id: str, child_id: str):
        return conn.execute(
            """
            SELECT * FROM children
            WHERE family_id = ? AND id = ?
            LIMIT 1 FOR UPDATE
            """,
            (family_id, child_id),
        ).fetchone()

    def __getattr__(self, name: str):
        raise AssertionError(f"formal event gate advanced past changed child: {name}")


class OpenMaicRuntimeEventAtomicGateTest(unittest.TestCase):
    def setUp(self):
        self.database_url = fresh_test_config()["DATABASE_URL"]
        self.database = Database(self.database_url)
        with self.database.transaction() as conn:
            conn.execute(
                "INSERT INTO families(id, name, created_at) VALUES (?, ?, ?)",
                ("family-runtime-gate", "Runtime Gate", NOW),
            )
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, grade_code,
                  grade_selection_revision, created_at, updated_at
                ) VALUES (?, ?, ?, 'primary_1', 1, ?, ?)
                """,
                (
                    "child-runtime-gate",
                    "family-runtime-gate",
                    "乐乐",
                    NOW,
                    NOW,
                ),
            )

    def test_committed_grade_switch_wins_barrier_before_answer_child_lock(self):
        self._assert_lock_queries_match_the_real_schema()
        snapshot_barrier = Barrier(2)
        grade_committed = Event()
        learning = _LearningService()
        service = OpenMaicRuntimeEventService(
            repository=_BarrierChildRepository(
                self.database,
                snapshot_barrier=snapshot_barrier,
                grade_committed=grade_committed,
            ),
            learning_service=learning,
            clock=lambda: NOW,
        )
        answer = _event(
            1,
            "answer_submitted",
            {
                "sceneIndex": 0,
                "sceneId": "scene-0",
                "questionId": "q1",
                "response": "12",
                "attemptNumber": 1,
            },
        )

        def record_answer():
            return service.record(
                runtime_session_id="runtime-session-1",
                learning_session_id="learning-session-1",
                upstream_classroom_id="classroom-1",
                data=answer,
            )

        def switch_grade():
            snapshot_barrier.wait(timeout=10)
            with Database(self.database_url).transaction() as conn:
                conn.execute(
                    """
                    UPDATE children
                    SET grade_code = 'primary_2', grade_selection_revision = 2,
                      updated_at = ?
                    WHERE family_id = ? AND id = ?
                    """,
                    (NOW + 1, "family-runtime-gate", "child-runtime-gate"),
                )
            grade_committed.set()

        with ThreadPoolExecutor(max_workers=2) as executor:
            record_future = executor.submit(record_answer)
            switch_future = executor.submit(switch_grade)
            switch_future.result(timeout=15)
            with self.assertRaises(ApiError) as raised:
                record_future.result(timeout=15)

        self.assertEqual(raised.exception.code, "student_learning_grade_not_open")
        self.assertEqual(learning.answer_calls, 0)
        self.assertEqual(learning.complete_calls, 0)
        with self.database.transaction() as conn:
            counts = {
                table: int(
                    conn.execute(f"SELECT COUNT(*) AS count FROM {table}")
                    .fetchone()["count"]
                )
                for table in (
                    "learning_openmaic_runtime_events",
                    "learning_openmaic_runtime_event_streams",
                    "learning_reports",
                    "task_events",
                )
            }
        self.assertEqual(counts, {key: 0 for key in counts})

    def _assert_lock_queries_match_the_real_schema(self):
        repository = OpenMaicRuntimeEventRepository(self.database)
        with repository.transaction() as conn:
            self.assertIsNone(
                repository.get_runtime_subject(
                    conn,
                    runtime_session_id="missing-runtime",
                    learning_session_id="missing-session",
                    upstream_classroom_id="missing-classroom",
                )
            )
            self.assertIsNone(
                repository.get_child_for_update(
                    conn,
                    family_id="missing-family",
                    child_id="missing-child",
                )
            )
            self.assertIsNone(
                repository.get_principal_for_update(
                    conn,
                    principal_id="missing-principal",
                )
            )
            self.assertIsNone(
                repository.get_task_for_update(
                    conn,
                    family_id="missing-family",
                    task_id="missing-task",
                )
            )
            self.assertIsNone(
                repository.get_learning_session_for_update(
                    conn,
                    family_id="missing-family",
                    learning_session_id="missing-session",
                )
            )
            self.assertIsNone(
                repository.get_formal_pointer_for_update(
                    conn,
                    grade_code="primary_1",
                )
            )
            self.assertIsNone(
                repository.get_formal_plan_for_update(
                    conn,
                    family_id="missing-family",
                    child_id="missing-child",
                    grade_code="primary_1",
                    grade_selection_revision=1,
                )
            )
            self.assertIsNone(
                repository.get_formal_history_for_update(
                    conn,
                    history_id="missing-history",
                    grade_code="primary_1",
                )
            )
            self.assertIsNone(
                repository.get_formal_course_ownership_for_update(
                    conn,
                    learning_session_id="missing-session",
                    release_id="missing-release",
                    grade_code="primary_1",
                    course_id="missing-course",
                    course_version="1",
                    package_id="missing-package",
                    package_version=1,
                )
            )
            self.assertIsNone(
                repository.get_runtime_authority(
                    conn,
                    runtime_session_id="missing-runtime",
                    learning_session_id="missing-session",
                    upstream_classroom_id="missing-classroom",
                    for_update=True,
                )
            )


if __name__ == "__main__":
    unittest.main()
