from __future__ import annotations

import copy
import hashlib
import unittest

from content.primary_skill_boundaries import boundary_for
from integrations.openmaic_question_adapter import (
    IndependentSolutionResult,
    OpenMaicQuestionError,
    QuestionCandidateResult,
)
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
    PROMPT_VERSION,
)
from services.learning_generated_course_validator import (
    INDEPENDENT_SOLUTION_SCHEMA_VERSION,
    LearningGeneratedCourseValidator,
)
from tests.support import fresh_test_config
from tests.test_learning_generated_course_validator import math_candidate
from tests.test_learning_generated_course_validator import _formal_course
from tests.test_learning_catalog_validator import _valid_number_sense_course


class _FakeQuestionAdapter:
    provider_name = "kimi"
    model_name = "kimi-test"

    def __init__(self, *, vary_by_request: bool = False):
        self.generate_calls: list[dict] = []
        self.verify_calls: list[dict] = []
        self.vary_by_request = vary_by_request

    def availability(self):
        return {"available": True, "generator": "openmaic"}

    def generate(self, **kwargs):
        self.generate_calls.append(copy.deepcopy(kwargs))
        boundary = kwargs["skill_boundary"]
        course = math_candidate()
        course["gradeCode"] = kwargs["grade_code"]
        course["subject"] = kwargs["subject"]
        course["nodeCode"] = boundary["skillId"]
        course["objective"] = "；".join(boundary["learningObjectives"])
        for question in course["content"]["questions"]:
            question["skill"] = boundary["skillTitle"]
            if self.vary_by_request:
                digest = hashlib.sha256(
                    kwargs["request_id"].encode("utf-8")
                ).hexdigest()[:8]
                letters_only = digest.translate(
                    str.maketrans("0123456789abcdef", "abcdefghijklmnop")
                )
                question["prompt"] += f"（测试变式{letters_only}）"
        return QuestionCandidateResult(
            request_id=kwargs["request_id"],
            candidate_course=course,
            question_fingerprints=tuple(f"{index:064x}" for index in range(1, 6)),
            validation={"schemaValidated": True},
            provider="kimi",
            model="kimi-test",
            elapsed_ms=3,
        )

    def verify(self, **kwargs):
        self.verify_calls.append(copy.deepcopy(kwargs))
        course = kwargs["candidate_course"]
        validator = LearningGeneratedCourseValidator()
        return IndependentSolutionResult(
            request_id=kwargs["request_id"],
            solution={
                "schemaVersion": INDEPENDENT_SOLUTION_SCHEMA_VERSION,
                "solver": "kimi-test:fresh-call",
                "independentFromGeneration": True,
                "verificationRequestId": kwargs["request_id"],
                "publicQuestionHash": validator.public_question_hash(course),
                "gradeCode": kwargs["grade_code"],
                "subject": kwargs["subject"],
                "skillId": kwargs["skill_boundary"]["skillId"],
                "teachingReview": {"passed": True, "issues": []},
                "answers": [
                    {
                        "questionId": question["id"],
                        "answer": question["answer"],
                        **(
                            {
                                "derivedExpression": question[
                                    "verificationExpression"
                                ]
                            }
                            if question["type"] == "numeric"
                            else {}
                        ),
                    }
                    for question in course["content"]["questions"]
                ],
            },
            provider="kimi",
            model="kimi-test",
            elapsed_ms=2,
        )


class _WidgetCompatibleQuestionAdapter(_FakeQuestionAdapter):
    """Catalog fixture whose guided questions fit controlled choice widgets."""

    def generate(self, **kwargs):
        if kwargs["grade_code"] == "primary_1":
            self.generate_calls.append(copy.deepcopy(kwargs))
            course, _target, _boundary, _request_id = _formal_course(
                kwargs["skill_boundary"]["skillId"],
                request_id=kwargs["request_id"],
            )
            skill_id = kwargs["skill_boundary"]["skillId"]
            if skill_id == "pinyin_syllables":
                course["content"]["teachingFlow"]["teach"] = {
                    "title": "单韵母 a、o、e",
                    "sayText": "先看口形，再听读音。",
                    "keyPoints": ["a", "o", "e"],
                }
            if skill_id == "number_sense_20":
                candidate_source_authority = copy.deepcopy(
                    course["content"]["sourceAuthority"]
                )
                course["content"] = copy.deepcopy(
                    _valid_number_sense_course()["content"]
                )
                course["content"]["sourceAuthority"] = candidate_source_authority
            course["objective"] = "；".join(
                kwargs["skill_boundary"]["learningObjectives"]
            )
            return QuestionCandidateResult(
                request_id=kwargs["request_id"],
                candidate_course=course,
                question_fingerprints=tuple(
                    hashlib.sha256(question["id"].encode("utf-8")).hexdigest()
                    for question in course["content"]["questions"]
                ),
                validation={"schemaValidated": True},
                provider="kimi",
                model="kimi-test",
                elapsed_ms=3,
            )
        result = super().generate(**kwargs)
        for question in result.candidate_course["content"]["questions"]:
            if question["type"] == "single_choice":
                continue
            correct_label = str(question["answer"])
            question["type"] = "single_choice"
            question["answer"] = "correct"
            question["choices"] = [
                {"id": "distractor_a", "label": f"{correct_label}A"},
                {"id": "correct", "label": correct_label},
                {"id": "distractor_b", "label": f"{correct_label}B"},
            ]
            question["evaluation"] = {
                "expectedOptionId": "correct",
                "normalization": ["trim", "casefold"],
            }
            question.pop("verificationExpression", None)
            question.pop("acceptedAnswers", None)
        return result


class _RetryOnceQuestionAdapter(_FakeQuestionAdapter):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    def generate(self, **kwargs):
        if not self.failed_once:
            self.failed_once = True
            self.generate_calls.append(copy.deepcopy(kwargs))
            raise OpenMaicQuestionError(
                "invalid_generation",
                "candidate choices were not unique",
            )
        return super().generate(**kwargs)


class _TransientOnceQuestionAdapter(_FakeQuestionAdapter):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    def generate(self, **kwargs):
        if not self.failed_once:
            self.failed_once = True
            self.generate_calls.append(copy.deepcopy(kwargs))
            raise OpenMaicQuestionError(
                "generation_failed",
                "Moonshot returned HTTP 429: token quota exceeded",
            )
        return super().generate(**kwargs)


class _ConsistencyRepairQuestionAdapter(_FakeQuestionAdapter):
    def __init__(self):
        super().__init__(vary_by_request=True)
        self.repair_calls: list[dict] = []

    def verify(self, **kwargs):
        result = super().verify(**kwargs)
        if len(self.verify_calls) == 1:
            result.solution["teachingReview"] = {
                "passed": False,
                "issues": ["示范解析使用“大于”，题目选项使用“更大”"],
            }
        return result

    def repair_consistency(self, **kwargs):
        self.repair_calls.append(copy.deepcopy(kwargs))
        candidate = copy.deepcopy(kwargs["candidate_course"])
        candidate["content"]["questions"][0]["explanation"] = (
            "统一使用“更大”解释这道示范题。"
        )
        return QuestionCandidateResult(
            request_id=kwargs["request_id"],
            candidate_course=candidate,
            question_fingerprints=tuple(
                f"{index:064x}" for index in range(11, 16)
            ),
            validation={
                "schemaValidated": True,
                "consistencyRepairApplied": True,
            },
            provider="kimi",
            model="kimi-test",
            elapsed_ms=4,
        )


class DynamicLearningCourseGenerationServiceTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.adapter = _FakeQuestionAdapter()
        self.service = DynamicLearningCourseGenerationService(
            config["DATABASE_URL"], adapter=self.adapter
        )

    def test_grade_subject_and_skill_are_generated_verified_and_staged(self):
        boundary = boundary_for("primary_3", "math")
        result = self.service.generate(
            {
                "requestId": "dynamic-primary-3-math-1",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": boundary.skill_id,
            }
        )

        self.assertEqual(result.status_code, 200, result.payload)
        self.assertTrue(result.payload["ok"])
        self.assertEqual(result.payload["course"]["contentOrigin"], "openmaic_generated")
        self.assertEqual(len(self.adapter.generate_calls), 1)
        self.assertEqual(len(self.adapter.verify_calls), 1)
        generation = self.adapter.generate_calls[0]
        verification = self.adapter.verify_calls[0]
        self.assertEqual(generation["grade_code"], "primary_3")
        self.assertEqual(generation["subject"], "math")
        self.assertEqual(generation["skill_boundary"]["skillId"], boundary.skill_id)
        self.assertNotIn("questions", generation["skill_boundary"])
        self.assertRegex(verification["request_id"], r"^learning_verify_[0-9a-f]{48}$")
        self.assertEqual(
            verification["candidate_course"]["content"]["teachingFlow"][
                "demoQuestionId"
            ],
            verification["candidate_course"]["content"]["questions"][0]["id"],
        )

        replay = self.service.generate(
            {
                "requestId": "dynamic-primary-3-math-1",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": boundary.skill_id,
            }
        )
        self.assertTrue(replay.payload["replayed"])
        self.assertEqual(len(self.adapter.generate_calls), 1)

    def test_semantically_duplicate_course_from_another_request_is_rejected(self):
        boundary = boundary_for("primary_3", "math")
        first = self.service.generate(
            {
                "requestId": "dynamic-duplicate-1",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": boundary.skill_id,
            }
        )
        second = self.service.generate(
            {
                "requestId": "dynamic-duplicate-2",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": boundary.skill_id,
            }
        )
        self.assertTrue(first.payload["ok"])
        self.assertEqual(second.status_code, 422)
        self.assertEqual(second.payload["status"], "rejected")
        self.assertEqual(second.payload["error"], "duplicate_generated_course")

    def test_generate_next_uses_declared_progression_not_skill_id_sort(self):
        result = self.service.generate_next(
            grade_code="primary_1",
            subject="chinese",
        )

        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(len(self.adapter.generate_calls), 1)
        self.assertEqual(
            self.adapter.generate_calls[0]["skill_boundary"]["skillId"],
            "pinyin_syllables",
        )

    def test_generate_for_skill_retries_model_contract_failure(self):
        adapter = _RetryOnceQuestionAdapter()
        service = DynamicLearningCourseGenerationService(
            fresh_test_config()["DATABASE_URL"],
            adapter=adapter,
        )

        result = service.generate_for_skill(
            grade_code="primary_1",
            subject="chinese",
            skill_id="pinyin_syllables",
        )

        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(len(adapter.generate_calls), 2)

    def test_generate_for_skill_forwards_only_explicit_validation_feedback(self):
        adapter = _FakeQuestionAdapter()
        service = DynamicLearningCourseGenerationService(
            fresh_test_config()["DATABASE_URL"],
            adapter=adapter,
        )
        feedback = {
            "code": "invalid_generated_course",
            "message": "q4 缺少比较证据",
        }

        result = service.generate_for_skill(
            grade_code="primary_3",
            subject="math",
            skill_id="multi_digit_operations",
            attempts=1,
            request_id="dynamic-feedback",
            generation_feedback=feedback,
        )

        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(adapter.generate_calls[0]["generation_feedback"], feedback)

    def test_transient_failed_job_requires_explicit_same_request_replay(self):
        adapter = _TransientOnceQuestionAdapter()
        service = DynamicLearningCourseGenerationService(
            fresh_test_config()["DATABASE_URL"],
            adapter=adapter,
        )
        request = {
            "requestId": "dynamic-provider-quota-replay",
            "gradeCode": "primary_3",
            "subject": "math",
            "skillId": "multi_digit_operations",
        }

        failed = service.generate(request, enqueue_classroom=False)
        self.assertFalse(failed.payload["ok"])
        self.assertEqual(failed.payload["error"], "generation_failed")

        passive_replay = service.generate(request, enqueue_classroom=False)
        self.assertFalse(passive_replay.payload["ok"])
        self.assertTrue(passive_replay.payload["replayed"])
        self.assertEqual(len(adapter.generate_calls), 1)

        recovered = service.generate(
            request,
            enqueue_classroom=False,
            retry_transient_failed=True,
        )
        self.assertTrue(recovered.payload["ok"], recovered.payload)
        self.assertEqual(len(adapter.generate_calls), 2)
        self.assertEqual(
            [call["request_id"] for call in adapter.generate_calls],
            [request["requestId"], request["requestId"]],
        )

    def test_failed_teaching_review_gets_one_text_only_repair_and_fresh_review(self):
        adapter = _ConsistencyRepairQuestionAdapter()
        service = DynamicLearningCourseGenerationService(
            fresh_test_config()["DATABASE_URL"],
            adapter=adapter,
        )

        result = service.generate(
            {
                "requestId": "dynamic-consistency-repair",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": "multi_digit_operations",
            },
            enqueue_classroom=False,
        )

        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(len(adapter.repair_calls), 1)
        self.assertEqual(len(adapter.verify_calls), 2)
        repair = adapter.repair_calls[0]
        self.assertEqual(
            repair["review_issues"],
            ("示范解析使用“大于”，题目选项使用“更大”",),
        )
        self.assertRegex(repair["request_id"], r"^learning_consistency_[0-9a-f]{48}$")
        self.assertNotEqual(
            adapter.verify_calls[0]["request_id"],
            adapter.verify_calls[1]["request_id"],
        )

    def test_catalog_text_fact_can_use_repair_but_structural_failure_cannot(self):
        passed_solution = {
            "teachingReview": {"passed": True, "issues": []},
        }
        self.assertEqual(
            DynamicLearningCourseGenerationService._consistency_repair_issues(
                {
                    "issues": [
                        {
                            "code": "generated_teaching_answer_leak",
                            "message": "Teaching flow directly reveals a guided or independent answer.",
                        }
                    ]
                },
                passed_solution,
            ),
            ("Teaching flow directly reveals a guided or independent answer.",),
        )
        self.assertEqual(
            DynamicLearningCourseGenerationService._consistency_repair_issues(
                {
                    "issues": [
                        {
                            "code": "invalid_generated_course",
                            "message": "图形与位置课程包含错误或排他的图形/左右事实",
                        }
                    ]
                },
                passed_solution,
            ),
            ("图形与位置课程包含错误或排他的图形/左右事实",),
        )
        self.assertEqual(
            DynamicLearningCourseGenerationService._consistency_repair_issues(
                {
                    "issues": [
                        {
                            "code": "invalid_generated_course",
                            "message": "图形与位置的两道独立题必须分别覆盖识图和位置关系",
                        }
                    ]
                },
                passed_solution,
            ),
            (),
        )

    def test_stale_generating_job_reuses_same_request_without_new_attempt_id(self):
        boundary = boundary_for("primary_3", "math")
        request_id = "dynamic-stale-same-request"
        generation_spec = {
            "gradeCode": boundary.grade_code,
            "subject": boundary.subject,
            "skillBoundary": boundary.to_openmaic_payload(),
            "curriculumVersion": boundary.curriculum_version,
            "boundaryVersion": boundary.boundary_version,
            "questionCount": 5,
        }
        with self.service.repository.transaction() as conn:
            job, created = self.service.repository.create_or_get_job(
                conn,
                request_id=request_id,
                grade_code=boundary.grade_code,
                subject=boundary.subject,
                node_code=boundary.skill_id,
                curriculum_version=boundary.curriculum_version,
                boundary_version=boundary.boundary_version,
                generator="openmaic",
                provider=self.adapter.provider_name,
                model=self.adapter.model_name,
                prompt_version=PROMPT_VERSION,
                requested_candidate_count=1,
                generation_spec=generation_spec,
                now=1,
            )
            self.assertTrue(created)
            self.service.repository.mark_job_generating(
                conn,
                job_id=str(job["id"]),
                now=2,
            )
            conn.execute(
                "UPDATE learning_course_generation_jobs SET updated_at = 2 WHERE id = ?",
                (job["id"],),
            )

        recovered = self.service.generate(
            {
                "requestId": request_id,
                "gradeCode": boundary.grade_code,
                "subject": boundary.subject,
                "skillId": boundary.skill_id,
            },
            enqueue_classroom=False,
        )
        self.assertTrue(recovered.payload["ok"], recovered.payload)
        self.assertEqual(len(self.adapter.generate_calls), 1)
        self.assertEqual(self.adapter.generate_calls[0]["request_id"], request_id)

        replay = self.service.generate(
            {
                "requestId": request_id,
                "gradeCode": boundary.grade_code,
                "subject": boundary.subject,
                "skillId": boundary.skill_id,
            },
            enqueue_classroom=False,
        )
        self.assertTrue(replay.payload["replayed"], replay.payload)
        self.assertEqual(len(self.adapter.generate_calls), 1)


if __name__ == "__main__":
    unittest.main()
