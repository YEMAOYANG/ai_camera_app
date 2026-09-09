from __future__ import annotations

import unittest
from unittest.mock import patch

from app import create_app
from tests.fixtures.primary_math_courses import PRIMARY_MATH_COURSES
from core.database import Database
from core.security import now_ms
from repositories.learning_content_generation_repository import (
    LearningContentGenerationRepository,
)
from repositories.learning_repository import LearningRepository
from services.learning_content_generation_service import LearningContentGenerationError
from tests.support import fresh_test_config


class FakeLearningContentGenerationService:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []
        self.failure: tuple[str, str] | None = None

    def status(self):
        return {
            "schemaVersion": "mira.learning.enrichment.v1",
            "generator": "openmaic",
            "available": True,
            "adapter": {
                "available": True,
                "provider": "fake-kimi",
                "model": "fake-model",
            },
            "policy": {
                "sourceOfTruth": "published_deterministic_course",
                "answerSource": "mira_deterministic_validation_only",
                "actionsEnabled": False,
                "mediaEnabled": False,
            },
        }

    def generate(self, course, request_id):
        self.calls.append((course["id"], course["version"], request_id))
        if self.failure:
            raise LearningContentGenerationError(*self.failure)
        return {
            "schemaVersion": "mira.learning.enrichment.v1",
            "requestId": request_id,
            "status": "validated_draft",
            "generator": "openmaic",
            "provider": "fake-kimi",
            "model": "fake-model",
            "elapsedMs": 17,
            "sourceCourse": {
                "id": course["id"],
                "version": course["version"],
                "gradeCode": course["grade_code"],
                "subject": course["subject"],
                "skillId": course["node_code"],
            },
            "authority": {
                "curriculum": "published_deterministic_course",
                "questions": "published_deterministic_course",
                "answers": "mira_deterministic_validation_only",
                "openMaicRole": "presentation_and_interaction_draft_only",
                "authoritativeAnswersProvided": False,
            },
            "draft": {
                "status": "unverified",
                "authoritativeAnswersProvided": False,
                "scenes": [
                    {
                        "id": "explain",
                        "type": "slide",
                        "title": "先理解方法",
                        "description": "这是非权威讲解草稿。",
                    }
                ],
            },
        }


class InternalLearningContentApiTest(unittest.TestCase):
    def setUp(self):
        self.internal_token = "learning-content-token"
        self.app = create_app(
            fresh_test_config(INTERNAL_API_TOKEN=self.internal_token)
        )
        self.client = self.app.test_client()
        self.headers = {
            "Content-Type": "application/json",
            "X-Mira-Internal-Token": self.internal_token,
            "X-Mira-Internal-Source": "content-worker",
        }
        self.generator = FakeLearningContentGenerationService()
        self.generator_patch = patch(
            "services.service_factory.learning_content_generation_service",
            return_value=self.generator,
        )
        self.generator_patch.start()
        self.addCleanup(self.generator_patch.stop)
        self.database = Database(self.app.config["DATABASE_URL"])
        LearningRepository(self.database).ensure_published_courses(
            PRIMARY_MATH_COURSES,
            now=now_ms(),
        )
        self.course = PRIMARY_MATH_COURSES[2]

    def test_status_requires_internal_guard_and_exposes_non_authority_policy(self):
        unauthorized = self.client.get("/internal/learning/content/status")
        self.assertEqual(unauthorized.status_code, 401, unauthorized.json)

        response = self.client.get(
            "/internal/learning/content/status",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["generation"]["available"])
        policy = response.json["generation"]["policy"]
        self.assertEqual(
            policy["sourceOfTruth"], "published_deterministic_course"
        )
        self.assertEqual(
            policy["answerSource"], "mira_deterministic_validation_only"
        )
        self.assertFalse(policy["actionsEnabled"])
        self.assertIn("auditId", response.json["internal"])

    def test_generate_persists_validated_draft_and_replays_idempotently(self):
        payload = {
            "courseId": self.course["id"],
            "courseVersion": self.course["version"],
            "requestId": "content-run-20260812-001",
        }
        first = self.client.post(
            "/internal/learning/content/generate",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200, first.json)
        self.assertTrue(first.json["ok"])
        self.assertFalse(first.json["replayed"])
        self.assertEqual(first.json["job"]["status"], "validated_draft")
        self.assertEqual(
            first.json["enrichment"]["status"], "validated_draft"
        )
        self.assertFalse(
            first.json["enrichment"]["payload"]["authority"]
            ["authoritativeAnswersProvided"]
        )

        replay = self.client.post(
            "/internal/learning/content/generate",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertTrue(replay.json["replayed"])
        self.assertEqual(replay.json["job"]["id"], first.json["job"]["id"])
        self.assertEqual(
            replay.json["enrichment"]["contentHash"],
            first.json["enrichment"]["contentHash"],
        )
        self.assertEqual(len(self.generator.calls), 1)

        with self.database.transaction() as conn:
            jobs = conn.execute(
                "SELECT * FROM learning_content_generation_jobs"
            ).fetchall()
            drafts = conn.execute(
                "SELECT * FROM learning_content_enrichment_drafts"
            ).fetchall()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(jobs[0]["draft_id"], drafts[0]["id"])
        self.assertEqual(drafts[0]["status"], "validated_draft")

    def test_request_id_is_bound_to_exact_course_version(self):
        first = self._generate("fixed-request")
        self.assertEqual(first.status_code, 200, first.json)

        conflict = self.client.post(
            "/internal/learning/content/generate",
            json={
                "courseId": "another-course",
                "courseVersion": "9.9.9",
                "requestId": "fixed-request",
            },
            headers=self.headers,
        )
        self.assertEqual(conflict.status_code, 409, conflict.json)
        self.assertEqual(
            conflict.json["error"], "learning_content_request_conflict"
        )
        self.assertEqual(len(self.generator.calls), 1)

    def test_generation_failure_is_sanitized_persisted_and_replayed(self):
        leaked = "provider failed with APP_AI_API_KEY=super-secret"
        self.generator.failure = ("openmaic_timeout", leaked)

        first = self._generate("timeout-request")
        self.assertEqual(first.status_code, 504, first.json)
        self.assertFalse(first.json["ok"])
        self.assertFalse(first.json["replayed"])
        self.assertEqual(first.json["job"]["status"], "failed")
        self.assertEqual(first.json["error"]["code"], "openmaic_timeout")
        self.assertNotIn("super-secret", str(first.json))

        replay = self._generate("timeout-request")
        self.assertEqual(replay.status_code, 504, replay.json)
        self.assertTrue(replay.json["replayed"])
        self.assertEqual(len(self.generator.calls), 1)
        self.assertNotIn("super-secret", str(replay.json))

        with self.database.transaction() as conn:
            job = conn.execute(
                """
                SELECT * FROM learning_content_generation_jobs
                WHERE request_id = ?
                """,
                ("timeout-request",),
            ).fetchone()
            draft_count = conn.execute(
                "SELECT COUNT(*) AS value FROM learning_content_enrichment_drafts"
            ).fetchone()["value"]
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_code"], "openmaic_timeout")
        self.assertNotIn("super-secret", job["error_message"])
        self.assertEqual(draft_count, 0)

    def test_abandoned_generating_job_is_reclaimed_but_fresh_job_is_not(self):
        stale_request = "stale-generation-request"
        fresh_request = "fresh-generation-request"
        with self.database.transaction() as conn:
            repository = LearningContentGenerationRepository(self.database)
            repository.create_or_get_job(
                conn,
                request_id=stale_request,
                course_id=self.course["id"],
                course_version=self.course["version"],
                generator="openmaic",
                now=1,
            )
            repository.create_or_get_job(
                conn,
                request_id=fresh_request,
                course_id=self.course["id"],
                course_version=self.course["version"],
                generator="openmaic",
                now=now_ms(),
            )

        stale = self._generate(stale_request)
        self.assertEqual(stale.status_code, 200, stale.json)
        self.assertEqual(stale.json["job"]["status"], "validated_draft")
        self.assertEqual(len(self.generator.calls), 1)

        fresh = self._generate(fresh_request)
        self.assertEqual(fresh.status_code, 202, fresh.json)
        self.assertEqual(fresh.json["job"]["status"], "generating")
        self.assertEqual(len(self.generator.calls), 1)

    def test_unpublished_or_missing_course_never_calls_generator(self):
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_courses SET status = 'draft'
                WHERE id = ? AND version = ?
                """,
                (self.course["id"], self.course["version"]),
            )
        unpublished = self._generate("draft-course-request")
        self.assertEqual(unpublished.status_code, 409, unpublished.json)
        self.assertEqual(unpublished.json["error"], "learning_course_not_published")

        missing = self.client.post(
            "/internal/learning/content/generate",
            json={
                "courseId": "missing-course",
                "courseVersion": "1.0.0",
            },
            headers=self.headers,
        )
        self.assertEqual(missing.status_code, 404, missing.json)
        self.assertEqual(missing.json["error"], "learning_course_not_found")
        self.assertEqual(self.generator.calls, [])

    def _generate(self, request_id: str):
        return self.client.post(
            "/internal/learning/content/generate",
            json={
                "courseId": self.course["id"],
                "courseVersion": self.course["version"],
                "requestId": request_id,
            },
            headers=self.headers,
        )


if __name__ == "__main__":
    unittest.main()
