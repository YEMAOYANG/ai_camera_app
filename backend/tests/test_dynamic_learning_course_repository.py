from __future__ import annotations

import unittest

from core.database import Database
import repositories.dynamic_learning_course_repository as dynamic_repository_module
from content.primary_skill_boundaries import boundaries_for
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
    LearningCourseCandidateConflict,
    LearningCourseGenerationRequestConflict,
    LearningCoursePublicationConflict,
)
from tests.support import fresh_test_config


class DynamicLearningQuestionFingerprintTest(unittest.TestCase):
    @staticmethod
    def _fingerprint(question: dict[str, object]) -> str:
        return DynamicLearningCourseRepository.question_fingerprint(
            grade_code="primary_1",
            subject="english",
            node_code="letters_sounds",
            question=question,
        )

    def test_question_fingerprint_ignores_punctuation_whitespace_and_formatting(self):
        canonical = {
            "type": "single_choice",
            "prompt": "字母A的首音是什么",
            "choices": [
                {"id": "apple", "label": "apple"},
                {"id": "ant", "label": "ant"},
            ],
        }
        formatting_only_variant = {
            "type": "single_choice",
            "prompt": "\u200b 字 母 Ａ 的 首 音 是 什 么？！\u2060",
            "choices": [
                {"id": "different-id-1", "label": "a p p l e!!!"},
                {"id": "different-id-2", "label": "\u200ca\u00a0n t？"},
            ],
        }

        self.assertEqual(
            self._fingerprint(formatting_only_variant),
            self._fingerprint(canonical),
        )

    def test_question_fingerprint_preserves_substantive_text_changes(self):
        canonical = {
            "type": "single_choice",
            "prompt": "字母A的首音是什么",
            "choices": [
                {"id": "apple", "label": "apple"},
                {"id": "ant", "label": "ant"},
            ],
        }
        substantively_different = {
            "type": "single_choice",
            "prompt": "字母B的首音是什么",
            "choices": [
                {"id": "banana", "label": "banana"},
                {"id": "ball", "label": "ball"},
            ],
        }

        self.assertNotEqual(
            self._fingerprint(substantively_different),
            self._fingerprint(canonical),
        )


class DynamicLearningCourseRepositoryTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database = Database(config["DATABASE_URL"])
        self.repository = DynamicLearningCourseRepository(self.database)

    def test_provider_dispatch_repository_exports_durable_cas_boundaries(self):
        self.assertTrue(
            callable(
                getattr(dynamic_repository_module, "begin_provider_dispatch", None)
            )
        )
        self.assertTrue(
            callable(
                getattr(dynamic_repository_module, "complete_provider_dispatch", None)
            )
        )

    def test_request_id_is_idempotent_and_bound_to_exact_generation_spec(self):
        with self.repository.transaction() as conn:
            first, created = self._create_job(
                conn,
                request_id="openmaic-primary-3-math-001",
                generation_spec={"difficulty": "standard", "questionCount": 5},
            )
            replay, replay_created = self._create_job(
                conn,
                request_id="openmaic-primary-3-math-001",
                generation_spec={"questionCount": 5, "difficulty": "standard"},
            )

        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(first["id"], replay["id"])
        self.assertEqual(first["request_fingerprint"], replay["request_fingerprint"])

        with self.assertRaises(LearningCourseGenerationRequestConflict):
            with self.repository.transaction() as conn:
                self._create_job(
                    conn,
                    request_id="openmaic-primary-3-math-001",
                    generation_spec={"difficulty": "advanced", "questionCount": 5},
                )

        with self.repository.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM learning_course_generation_jobs"
            ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_candidate_identity_target_and_existing_fingerprint_are_guarded(self):
        course = self._course()
        with self.repository.transaction() as conn:
            job, _ = self._create_job(conn)
            self.repository.mark_job_generating(conn, job_id=job["id"], now=101)
            candidate, created = self.repository.create_or_get_candidate(
                conn,
                job_id=job["id"],
                ordinal=1,
                course=course,
                now=102,
            )
            replay, replay_created = self.repository.create_or_get_candidate(
                conn,
                job_id=job["id"],
                ordinal=1,
                course=course,
                now=103,
            )
            validated = self.repository.mark_candidate_validated(
                conn,
                candidate_id=candidate["id"],
                validation={
                    "valid": True,
                    "checks": ["schema", "answers"],
                    "contentFingerprint": "a" * 64,
                },
                now=104,
            )
            fingerprints = self.repository.existing_content_fingerprints(
                conn,
                grade_code="primary_3",
                subject="math",
                node_code="multi_digit_operations",
            )

        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(candidate["id"], replay["id"])
        self.assertEqual(validated["status"], "validated")
        self.assertIn("a" * 64, fingerprints)
        self.assertNotIn(candidate["content_hash"], fingerprints)

        changed = self._course()
        changed["title"] = "不同的课程内容"
        with self.assertRaises(LearningCourseCandidateConflict):
            with self.repository.transaction() as conn:
                self.repository.create_or_get_candidate(
                    conn,
                    job_id=job["id"],
                    ordinal=1,
                    course=changed,
                    now=105,
                )

        wrong_target = self._course()
        wrong_target["gradeCode"] = "primary_6"
        with self.assertRaises(LearningCourseCandidateConflict):
            with self.repository.transaction() as conn:
                self.repository.create_or_get_candidate(
                    conn,
                    job_id=job["id"],
                    ordinal=2,
                    course=wrong_target,
                    now=106,
                )

    def test_validated_candidates_stage_atomically_without_student_publication(self):
        first_course = self._course()
        second_course = self._course(
            course_id="openmaic_primary_math_g3_multi_digit_002",
            version="gen-2026-08-13.2",
            title="三位数加法巩固",
        )
        with self.repository.transaction() as conn:
            job, _ = self._create_job(conn, requested_candidate_count=2)
            first, _ = self.repository.create_or_get_candidate(
                conn,
                job_id=job["id"],
                ordinal=1,
                course=first_course,
                now=201,
            )
            second, _ = self.repository.create_or_get_candidate(
                conn,
                job_id=job["id"],
                ordinal=2,
                course=second_course,
                now=202,
            )
            self.repository.mark_candidate_validated(
                conn,
                candidate_id=first["id"],
                validation={"valid": True, "contentFingerprint": "a" * 64},
                now=203,
            )
            self.repository.mark_candidate_validated(
                conn,
                candidate_id=second["id"],
                validation={"valid": True, "contentFingerprint": "b" * 64},
                now=204,
            )

        published_first, created_first = self.repository.publish_candidate(
            candidate_id=first["id"],
            now=205,
        )
        self.assertTrue(created_first)
        self.assertEqual(published_first["content_origin"], "openmaic_generated")
        self.assertEqual(published_first["generator"], "openmaic")
        self.assertEqual(published_first["generation_request_id"], job["request_id"])
        self.assertEqual(
            published_first["generation_content_hash"], "a" * 64
        )
        self.assertEqual(published_first["status"], "validated")
        self.assertEqual(published_first["quality_status"], "auto_validated")
        self.assertIsNone(published_first["published_at"])

        with self.repository.transaction() as conn:
            partial_job = self.repository.get_job(conn, job_id=job["id"])
        self.assertEqual(partial_job["status"], "partially_validated")

        self.repository.publish_candidate(candidate_id=second["id"], now=206)
        replayed_course, replay_created = self.repository.publish_candidate(
            candidate_id=second["id"],
            now=207,
        )
        self.assertFalse(replay_created)
        self.assertEqual(replayed_course["id"], second_course["id"])

        with self.repository.transaction() as conn:
            published_job = self.repository.get_job(conn, job_id=job["id"])
            rows = self.repository.list_published_dynamic_courses(
                conn,
                grade_code="primary_3",
                subject="math",
                node_code="multi_digit_operations",
            )
            count = self.repository.count_published_dynamic_courses(
                conn,
                grade_code="primary_3",
                subject="math",
                node_code="multi_digit_operations",
            )
        self.assertEqual(published_job["status"], "validated")
        self.assertEqual(len(rows), 2)
        self.assertEqual(count, 2)

    def test_publication_conflict_rolls_back_candidate_and_job_states(self):
        course = self._course()
        with self.repository.transaction() as conn:
            job, _ = self._create_job(conn)
            candidate, _ = self.repository.create_or_get_candidate(
                conn,
                job_id=job["id"],
                ordinal=1,
                course=course,
                now=301,
            )
            self.repository.mark_candidate_validated(
                conn,
                candidate_id=candidate["id"],
                validation={"valid": True, "contentFingerprint": "c" * 64},
                now=302,
            )
            conn.execute(
                """
                INSERT INTO learning_courses(
                  id, version, grade_code, subject, node_code, title,
                  objective, status, content_json, published_at,
                  created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'published', '{}', ?, ?, ?)
                """,
                (
                    course["id"],
                    course["version"],
                    course["gradeCode"],
                    course["subject"],
                    course["nodeCode"],
                    "已有静态课",
                    "不可被 AI 候选覆盖",
                    300,
                    300,
                    300,
                ),
            )

        with self.assertRaises(LearningCoursePublicationConflict):
            self.repository.publish_candidate(candidate_id=candidate["id"], now=303)

        with self.repository.transaction() as conn:
            persisted_candidate = self.repository.get_candidate(
                conn,
                candidate_id=candidate["id"],
            )
            persisted_job = self.repository.get_job(conn, job_id=job["id"])
            persisted_course = conn.execute(
                """
                SELECT * FROM learning_courses WHERE id = ? AND version = ?
                """,
                (course["id"], course["version"]),
            ).fetchone()
        self.assertEqual(persisted_candidate["status"], "validated")
        self.assertEqual(persisted_job["status"], "candidates_ready")
        self.assertEqual(persisted_course["content_origin"], "legacy_seed")
        self.assertEqual(persisted_course["title"], "已有静态课")

    def test_semantic_fingerprint_unique_constraint_blocks_cross_request_duplicate(self):
        first_course = self._course(course_id="dynamic-semantic-first")
        second_course = self._course(
            course_id="dynamic-semantic-second",
            version="1.0.0",
            title="不同标题但相同题目语义",
        )
        fingerprint = "d" * 64
        with self.repository.transaction() as conn:
            first_job, _ = self._create_job(
                conn, request_id="semantic-request-first"
            )
            first, _ = self.repository.create_or_get_candidate(
                conn,
                job_id=first_job["id"],
                ordinal=1,
                course=first_course,
                now=350,
            )
            self.repository.mark_candidate_validated(
                conn,
                candidate_id=first["id"],
                validation={"contentFingerprint": fingerprint},
                now=351,
            )
        self.repository.publish_candidate(candidate_id=first["id"], now=352)

        with self.repository.transaction() as conn:
            second_job, _ = self._create_job(
                conn, request_id="semantic-request-second"
            )
            second, _ = self.repository.create_or_get_candidate(
                conn,
                job_id=second_job["id"],
                ordinal=1,
                course=second_course,
                now=353,
            )
            self.repository.mark_candidate_validated(
                conn,
                candidate_id=second["id"],
                validation={"contentFingerprint": fingerprint},
                now=354,
            )

        with self.assertRaises(LearningCoursePublicationConflict):
            self.repository.publish_candidate(candidate_id=second["id"], now=355)

        with self.repository.transaction() as conn:
            rows = conn.execute(
                """
                SELECT id FROM learning_courses
                WHERE generation_content_hash = ?
                """,
                (fingerprint,),
            ).fetchall()
        self.assertEqual([row["id"] for row in rows], [first_course["id"]])

    def test_job_and_candidate_failures_only_persist_sanitized_errors(self):
        leaked = (
            "provider https://alice:pass123@example.test failed "
            "APP_AI_API_KEY=super-secret Authorization: Bearer token-value-123"
        )
        with self.repository.transaction() as conn:
            job, _ = self._create_job(conn)
            failed = self.repository.mark_job_failed(
                conn,
                job_id=job["id"],
                error_code="Provider Timeout!",
                error_message=leaked,
                now=401,
            )

        safe_message = failed["error_message_safe"]
        self.assertEqual(failed["error_code"], "provider_timeout_")
        self.assertNotIn("super-secret", safe_message)
        self.assertNotIn("pass123", safe_message)
        self.assertNotIn("token-value-123", safe_message)
        self.assertIn("[REDACTED]", safe_message)

    def _create_job(
        self,
        conn,
        *,
        request_id: str = "openmaic-primary-3-math-default",
        requested_candidate_count: int = 1,
        generation_spec: dict | None = None,
    ):
        boundary = next(
            item
            for item in boundaries_for("primary_3", "math")
            if item.skill_id == "multi_digit_operations"
        )
        return self.repository.create_or_get_job(
            conn,
            request_id=request_id,
            grade_code="primary_3",
            subject="math",
            node_code="multi_digit_operations",
            curriculum_version=boundary.curriculum_version,
            boundary_version=boundary.boundary_version,
            generator="openmaic",
            provider="kimi",
            model="kimi-k2.6",
            prompt_version="primary-course-v1",
            requested_candidate_count=requested_candidate_count,
            generation_spec=generation_spec or {"questionCount": 5},
            now=100,
        )

    @staticmethod
    def _course(
        *,
        course_id: str = "openmaic_primary_math_g3_multi_digit_001",
        version: str = "gen-2026-08-13.1",
        title: str = "三位数加法练习",
    ) -> dict:
        return {
            "id": course_id,
            "version": version,
            "gradeCode": "primary_3",
            "subject": "math",
            "nodeCode": "multi_digit_operations",
            "title": title,
            "objective": "准确完成三位数加法并说明进位过程。",
            "content": {
                "outcomeMode": "scored_deterministic",
                "sessionKind": "lesson",
                "estimatedMinutes": 10,
                "questions": [
                    {
                        "id": "q1",
                        "type": "numeric",
                        "prompt": "238 + 157 = ?",
                        "answer": "395",
                        "verificationExpression": "238+157",
                    }
                ],
            },
        }


if __name__ == "__main__":
    unittest.main()
