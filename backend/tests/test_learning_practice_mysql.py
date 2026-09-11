"""Bounded MySQL regression for the practice migration and frozen ledger.

Uses only the exact local test database guarded by tests.support. No providers,
workers, production courses, or external calls are involved.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from core.database import Database
from repositories.learning_practice_repository import LearningPracticeRepository
from services.learning_practice_service import LearningPracticeService
from tests.support import fresh_test_config
from tests.test_learning_practice import source


class PracticeMysqlTest(unittest.TestCase):
    def test_migrations_source_query_and_frozen_question_session_roundtrip(self):
        database = Database(fresh_test_config()["DATABASE_URL"])
        repository = LearningPracticeRepository(database)
        scope = {"family_id": "practice-test-family", "child_id": "practice-test-child"}
        with repository.transaction() as conn:
            self.assertFalse(repository.eligible_sources(conn, **scope, grade_code="primary_1", subject="math", skill_id=None))
            self.assertIsNone(repository.lock_child(conn, {"id": "missing", **scope}))
            checks = conn.execute("SHOW CREATE TABLE learning_openmaic_runtime_events").fetchone()
            self.assertIn("interaction_completed", str(checks))

        # Keep publication provenance in the pure Host tests; here exercise the
        # real SQL repository and immutable session/answer transaction boundary.
        repository.lock_child = lambda conn, principal: {"grade_code": "primary_1", "education_stage_code": "primary", "grade_selection_revision": 1}
        repository.eligible_sources = lambda conn, **kwargs: [source()]
        auth = Mock()
        auth.authenticate.return_value = {"principal": {"id": "test-principal", **scope}}
        service = LearningPracticeService(repository=repository, student_auth_service=auth, host_validator=Mock(), clock=lambda: 100)
        started = service.start("test-token", {"requestId": "mysql-1", "subject": "math", "count": 5})
        session_id = started["session"]["id"]
        self.assertEqual(started["session"]["totalQuestions"], 2)
        self.assertEqual(service.start("test-token", {"requestId": "mysql-retry", "subject": "math"})["session"]["id"], session_id)
        for _ in range(2):
            current = service.get("test-token", session_id)
            question_id = current["session"]["currentQuestion"]["id"]
            with repository.transaction() as conn:
                item = next(row for row in repository.items(conn, session_id) if row["question_id"] == question_id)
                answer = json.loads(item["snapshot_json"])["answer"]
            body = {"questionId": question_id, "response": answer}
            saved = service.answer("test-token", session_id, body)
            self.assertEqual(saved, service.answer("test-token", session_id, body))
        self.assertEqual(saved["session"]["status"], "completed")
        self.assertEqual(saved["session"]["correctCount"], 2)
        self.assertIsNone(service.start("test-token", {"requestId": "mysql-2", "subject": "math"})["session"])
        with repository.transaction() as conn:
            self.assertEqual(len(repository.seen(conn, **scope)), 2)
            self.assertIsNone(repository.get_session(conn, family_id="another-family", child_id=scope["child_id"], session_id=session_id))


if __name__ == "__main__":
    unittest.main()
