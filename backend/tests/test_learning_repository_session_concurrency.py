from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from core.database import Database
from repositories.learning_repository import LearningRepository
from tests.support import fresh_test_config


class _Cursor:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _RecordingConnection:
    def __init__(self, select_rows):
        self.select_rows = iter(select_rows)
        self.statements: list[str] = []

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.statements.append(normalized)
        if normalized.startswith("SELECT * FROM learning_sessions"):
            return _Cursor(next(self.select_rows))
        return _Cursor()


class _BarrierLearningRepository(LearningRepository):
    def __init__(self, database: Database, initial_read_barrier: Barrier):
        super().__init__(database)
        self._initial_read_barrier = initial_read_barrier
        self._initial_read_seen = False

    def get_session_for_task(
        self,
        conn,
        *,
        family_id: str,
        task_id: str,
        **kwargs,
    ):
        row = super().get_session_for_task(
            conn,
            family_id=family_id,
            task_id=task_id,
            **kwargs,
        )
        if (
            not kwargs.get("for_update", False)
            and not self._initial_read_seen
            and row is None
        ):
            self._initial_read_seen = True
            self._initial_read_barrier.wait(timeout=10)
        return row


class LearningRepositorySessionConcurrencyTest(unittest.TestCase):
    def setUp(self):
        self.database_url = fresh_test_config()["DATABASE_URL"]

    def test_concurrent_create_or_get_session_returns_one_shared_session(self):
        barrier = Barrier(2)

        def create_once():
            repository = _BarrierLearningRepository(
                Database(self.database_url),
                barrier,
            )
            with repository.transaction() as conn:
                row, created = repository.create_or_get_session(
                    conn,
                    family_id="family_concurrent_session",
                    child_id="child_concurrent_session",
                    task_id="task_concurrent_session",
                    course_id="course_concurrent_session",
                    course_version="1",
                    now=1_777_777_777_000,
                )
                return str(row["id"]), created

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: create_once(), range(2)))

        self.assertEqual(len({session_id for session_id, _ in results}), 1, results)
        self.assertEqual(sorted(created for _, created in results), [False, True])
        with Database(self.database_url).transaction() as conn:
            rows = conn.execute(
                """
                SELECT id FROM learning_sessions
                WHERE family_id = ? AND task_id = ?
                """,
                ("family_concurrent_session", "task_concurrent_session"),
            ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_create_or_get_session_locks_only_post_upsert_read(self):
        stored = {"id": "learn_session_stored"}
        conn = _RecordingConnection([None, stored])
        repository = LearningRepository(Database(self.database_url))

        row, created = repository.create_or_get_session(
            conn,
            family_id="family_lock_contract",
            child_id="child_lock_contract",
            task_id="task_lock_contract",
            course_id="course_lock_contract",
            course_version="1",
            now=1_777_777_777_001,
        )

        selects = [
            statement
            for statement in conn.statements
            if statement.startswith("SELECT * FROM learning_sessions")
        ]
        self.assertEqual(len(selects), 2)
        self.assertNotIn("FOR UPDATE", selects[0])
        self.assertTrue(selects[1].endswith("FOR UPDATE"), selects[1])
        self.assertEqual(row, stored)
        self.assertFalse(created)

    def test_create_or_get_session_raises_runtime_error_if_locked_read_is_missing(self):
        conn = _RecordingConnection([None, None])
        repository = LearningRepository(Database(self.database_url))

        with self.assertRaisesRegex(
            RuntimeError,
            "learning session missing after upsert",
        ):
            repository.create_or_get_session(
                conn,
                family_id="family_missing_session",
                child_id="child_missing_session",
                task_id="task_missing_session",
                course_id="course_missing_session",
                course_version="1",
                now=1_777_777_777_002,
            )


if __name__ == "__main__":
    unittest.main()
