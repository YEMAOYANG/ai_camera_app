"""Bounded database regression for the practice schema and frozen ledger.

Uses only the exact local test database guarded by tests.support. No providers,
workers, production courses, or external calls are involved.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
import unittest
from unittest.mock import Mock

from core.database import Database
from repositories.learning_practice_repository import LearningPracticeRepository
from services.learning_practice_service import LearningPracticeService
from tests.support import fresh_test_config
from tests.test_learning_practice import Repository as PublicationFixture, _Rows


class PracticeDatabaseTest(unittest.TestCase):
    def test_migrations_source_query_and_frozen_question_session_roundtrip(self):
        database = Database(fresh_test_config()["DATABASE_URL"])
        repository = LearningPracticeRepository(database)
        scope = {"family_id": "practice-test-family", "child_id": "practice-test-child"}
        with repository.transaction() as conn:
            self.assertFalse(repository.eligible_sources(conn, **scope, grade_code="primary_1", subject="math", skill_id=None))
            self.assertIsNone(repository.lock_child(conn, {"id": "missing", **scope}))
            checks = conn.execute(
                "SELECT string_agg(pg_get_constraintdef(oid), ' ') AS checks FROM pg_constraint "
                "WHERE conrelid = 'learning_openmaic_runtime_events'::regclass AND contype = 'c'"
            ).fetchone()
            self.assertIn("interaction_completed", str(checks))

        # Freeze only the upstream completed-publication fixture. Every practice
        # ledger query still executes against the database, and the service rechecks the
        # real fine binding, prerequisites and original Host validation receipt.
        publication = PublicationFixture()
        publication.child.update(id=scope['child_id'], family_id=scope['family_id'])
        real_transaction = repository.transaction

        class PublicationConnection:
            def __init__(self, conn): self.conn = conn
            def execute(self, sql, params=()):
                if any(marker in sql for marker in (
                    'FROM learning_progressive_course_bindings',
                    "SELECT 'progressive_course' AS authority_kind",
                    'FROM learning_progressive_lesson_progress',
                    'SELECT candidate.validation_json',
                )):
                    return publication.execute(sql, params)
                if 'SELECT course.* FROM learning_courses AS course' in sql and 'AND EXISTS' in sql:
                    row = publication.completed_progressive_course(None,
                        course_id=params[0], course_version=params[1], family_id=params[2], child_id=params[3])
                    return _Rows([row] if row else [])
                return self.conn.execute(sql, params)

        @contextmanager
        def transaction():
            with real_transaction() as conn:
                yield PublicationConnection(conn)

        repository.transaction = transaction
        repository.lock_child = lambda conn, principal: publication.child
        repository.eligible_sources = lambda conn, **kwargs: publication.sources
        auth = Mock()
        auth.authenticate.return_value = {"principal": {"id": "test-principal", **scope}}
        service = LearningPracticeService(repository=repository, student_auth_service=auth, host_validator=Mock(), clock=lambda: 100)
        started = service.start("test-token", {"requestId": "mysql-1", "subject": "math", "count": 5})
        session_id = started["session"]["id"]
        self.assertEqual(started["session"]["totalQuestions"], 5)
        self.assertEqual(service.start("test-token", {"requestId": "mysql-retry", "subject": "math"})["session"]["id"], session_id)
        for _ in range(5):
            current = service.get("test-token", session_id)
            question_id = current["session"]["currentQuestion"]["id"]
            with repository.transaction() as conn:
                item = next(row for row in repository.items(conn, session_id) if row["question_id"] == question_id)
                answer = json.loads(item["snapshot_json"])["answer"]
            body = {"questionId": question_id, "response": answer}
            saved = service.answer("test-token", session_id, body)
            self.assertEqual(saved, service.answer("test-token", session_id, body))
        self.assertEqual(saved["session"]["status"], "completed")
        self.assertEqual(saved["session"]["correctCount"], 5)
        self.assertIsNone(service.start("test-token", {"requestId": "mysql-2", "subject": "math"})["session"])
        with repository.transaction() as conn:
            self.assertEqual(len(repository.seen(conn, **scope)), 5)
            self.assertIsNone(repository.get_session(conn, family_id="another-family", child_id=scope["child_id"], session_id=session_id))


if __name__ == "__main__":
    unittest.main()
