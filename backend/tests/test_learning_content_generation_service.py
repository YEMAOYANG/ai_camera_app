from __future__ import annotations

import copy
import unittest

from integrations.openmaic_draft_adapter import DraftGenerationResult, OpenMaicDraftError
from services.learning_content_generation_service import (
    LEARNING_ENRICHMENT_SCHEMA,
    LearningContentGenerationError,
    LearningContentGenerationService,
)


def published_course() -> dict:
    return {
        "id": "primary_math_g3_multi_digit_operations_v1",
        "version": "1.0.0",
        "gradeCode": "primary_3",
        "subject": "math",
        "nodeCode": "multi_digit_operations",
        "title": "多位数计算与应用",
        "objective": "准确完成三位数加减与两位数乘一位数。",
        "status": "published",
        "content": {
            "outcomeMode": "scored_deterministic",
            "sessionKind": "lesson",
            "intro": "今天练习列式计算。",
            "estimatedMinutes": 10,
            "questions": [
                {
                    "id": "g3q1",
                    "type": "numeric",
                    "prompt": "238 + 157 = ?",
                    "answer": "395",
                    "verificationExpression": "238+157",
                    "skill": "三位数加法",
                    "hint": "从个位开始。",
                    "explanation": "结果是395。",
                }
            ],
        },
    }


class FakeAdapter:
    def __init__(
        self,
        *,
        mutate=None,
        error: OpenMaicDraftError | None = None,
        response_request_id: str | None = None,
    ):
        self.boundary = None
        self.mutate = mutate
        self.error = error
        self.response_request_id = response_request_id

    def availability(self):
        return {"available": True, "generator": "openmaic"}

    def generate(self, skill_boundary, request_id):
        self.boundary = copy.deepcopy(skill_boundary)
        if self.error:
            raise self.error
        draft = {
            "status": "unverified",
            "skillBoundary": copy.deepcopy(skill_boundary),
            "authoritativeAnswersProvided": False,
            "courseTitle": "三位数加法练习",
            "scenes": [
                {
                    "id": "explain",
                    "type": "slide",
                    "order": 1,
                    "title": "从个位开始",
                    "description": "个位满十向十位进一。",
                    "keyPoints": ["相同数位对齐"],
                    "interactionDraft": {
                        "elements": [
                            {"type": "text", "content": "先看个位。"},
                            {"type": "shape", "shape": "rect"},
                        ]
                    },
                },
                {
                    "id": "check",
                    "type": "quiz",
                    "order": 2,
                    "title": "说说第一步",
                    "description": "只生成问题草稿，不给答案。",
                    "keyPoints": ["先判断个位是否满十"],
                    "interactionDraft": {
                        "questions": [
                            {
                                "id": "draft-q1",
                                "type": "single",
                                "question": "计算加法时先看哪一位？",
                                "options": [
                                    {"value": "A", "label": "个位"},
                                    {"value": "B", "label": "百位"},
                                ],
                                "answerAuthority": "mira_validation_required",
                            }
                        ]
                    },
                },
            ],
        }
        if self.mutate:
            self.mutate(draft)
        return DraftGenerationResult(
            schema_version="mira.openmaic.draft.v1",
            request_id=self.response_request_id or request_id,
            generator="openmaic",
            draft=draft,
            provider="kimi",
            model="kimi-k2.6",
            elapsed_ms=42,
        )


class LearningContentGenerationServiceTest(unittest.TestCase):
    def test_builds_fixed_boundary_and_returns_validated_non_answer_enrichment(self):
        adapter = FakeAdapter()
        service = LearningContentGenerationService(adapter)
        payload = service.generate(published_course(), "req-enrich-1")

        self.assertEqual(payload["schemaVersion"], LEARNING_ENRICHMENT_SCHEMA)
        self.assertEqual(payload["status"], "validated_draft")
        self.assertEqual(payload["generator"], "openmaic")
        self.assertEqual(payload["provider"], "kimi")
        self.assertEqual(payload["model"], "kimi-k2.6")
        self.assertEqual(payload["sourceCourse"]["skillId"], "multi_digit_operations")
        self.assertFalse(payload["authority"]["authoritativeAnswersProvided"])
        self.assertEqual(adapter.boundary["gradeCode"], "primary_3")
        self.assertEqual(adapter.boundary["subject"], "math")
        self.assertEqual(adapter.boundary["skillId"], "multi_digit_operations")
        serialized_boundary = str(adapter.boundary)
        self.assertNotIn("395", serialized_boundary)
        self.assertNotIn("verificationExpression", serialized_boundary)
        self.assertIn("三位数加法", adapter.boundary["allowedContent"])

    def test_accepts_database_row_shape_with_content_json(self):
        course = published_course()
        row = {
            "id": course["id"],
            "version": course["version"],
            "grade_code": course["gradeCode"],
            "subject": course["subject"],
            "node_code": course["nodeCode"],
            "title": course["title"],
            "objective": course["objective"],
            "status": "published",
            "content_json": __import__("json").dumps(course["content"], ensure_ascii=False),
        }
        payload = LearningContentGenerationService(FakeAdapter()).generate(row, "req-row")
        self.assertEqual(payload["sourceCourse"]["gradeCode"], "primary_3")

    def test_safe_deterministic_subjects_are_allowed_without_sharing_answer_contracts(self):
        subject_questions = {
            "math": {
                "type": "numeric",
                "answer": "4",
                "evaluation": {"expected": "4"},
            },
            "chinese": {
                "type": "accepted_text",
                "acceptedAnswers": ["中国", "中华人民共和国"],
                "evaluation": {
                    "acceptedAnswers": ["中国", "中华人民共和国"],
                    "normalization": ["trim"],
                },
            },
            "english": {
                "type": "exact_text",
                "answer": "apple",
                "evaluation": {
                    "expected": "apple",
                    "normalization": ["trim", "casefold"],
                },
            },
        }
        for subject, authority in subject_questions.items():
            with self.subTest(subject=subject):
                course = published_course()
                course["id"] = f"primary_{subject}_g3_safe_v1"
                course["subject"] = subject
                course["content"]["questions"][0].update(authority)
                adapter = FakeAdapter()
                payload = LearningContentGenerationService(adapter).generate(
                    course, f"req-{subject}"
                )
                self.assertEqual(payload["sourceCourse"]["subject"], subject)
                serialized = str(adapter.boundary)
                self.assertNotIn("evaluation", serialized)
                self.assertNotIn("acceptedAnswers", serialized)
                self.assertNotIn("expectedOptionId", serialized)
                self.assertNotIn("expectedSequence", serialized)
                self.assertNotIn("中华人民共和国", serialized)
                self.assertEqual(
                    adapter.boundary["outcomeMode"], "scored_deterministic"
                )
                self.assertEqual(adapter.boundary["sessionKind"], "lesson")

    def test_rejects_non_deterministic_non_lesson_and_non_core_subject_courses(self):
        cases = []

        missing_mode = published_course()
        missing_mode["content"].pop("outcomeMode")
        cases.append(missing_mode)

        missing_kind = published_course()
        missing_kind["content"].pop("sessionKind")
        cases.append(missing_kind)

        activity = published_course()
        activity["content"]["sessionKind"] = "activity"
        cases.append(activity)

        invalid_grade = published_course()
        invalid_grade["gradeCode"] = "primary_7"
        cases.append(invalid_grade)

        participation_question = published_course()
        participation_question["content"]["questions"][0]["type"] = "participation"
        participation_question["content"]["questions"][0].pop("answer")
        cases.append(participation_question)

        for blocked_subject in (
            "science",
            "information_technology",
            "morality_law",
        ):
            blocked = published_course()
            blocked["subject"] = blocked_subject
            cases.append(blocked)

        for index, course in enumerate(cases):
            with self.subTest(index=index):
                adapter = FakeAdapter()
                with self.assertRaises(LearningContentGenerationError) as context:
                    LearningContentGenerationService(adapter).generate(
                        course, f"req-blocked-{index}"
                    )
                self.assertEqual(context.exception.code, "unsupported_learning_course")
                self.assertIsNone(adapter.boundary)

    def test_rejects_unpublished_course_before_calling_openmaic(self):
        course = published_course()
        course["status"] = "draft"
        adapter = FakeAdapter()
        with self.assertRaises(LearningContentGenerationError) as context:
            LearningContentGenerationService(adapter).generate(course, "req-draft")
        self.assertEqual(context.exception.code, "learning_course_not_published")
        self.assertIsNone(adapter.boundary)

    def test_rejects_grade_subject_or_skill_boundary_drift(self):
        def mutate(draft):
            draft["skillBoundary"]["gradeCode"] = "primary_6"

        with self.assertRaises(LearningContentGenerationError) as context:
            LearningContentGenerationService(FakeAdapter(mutate=mutate)).generate(
                published_course(), "req-drift"
            )
        self.assertEqual(context.exception.code, "openmaic_boundary_mismatch")

    def test_rejects_changed_allowed_scope_and_response_identity(self):
        def mutate(draft):
            draft["skillBoundary"]["allowedContent"] = ["六年级分数除法"]

        with self.assertRaises(LearningContentGenerationError) as boundary_context:
            LearningContentGenerationService(FakeAdapter(mutate=mutate)).generate(
                published_course(), "req-scope"
            )
        self.assertEqual(boundary_context.exception.code, "openmaic_boundary_mismatch")

        with self.assertRaises(LearningContentGenerationError) as identity_context:
            LearningContentGenerationService(
                FakeAdapter(response_request_id="req-someone-else")
            ).generate(published_course(), "req-identity")
        self.assertEqual(identity_context.exception.code, "invalid_openmaic_draft")

    def test_rejects_answer_authority_fields_defensively(self):
        mutations = (
            lambda draft: draft["scenes"][1]["interactionDraft"]["questions"][0].update(
                {"answer": ["A"]}
            ),
            lambda draft: draft["scenes"][1]["interactionDraft"]["questions"][0].update(
                {"evaluation": {"expectedOptionId": "A"}}
            ),
            lambda draft: draft["scenes"][1]["interactionDraft"]["questions"][0].update(
                {"EXPECTEDANSWER": "A"}
            ),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(LearningContentGenerationError) as context:
                    LearningContentGenerationService(FakeAdapter(mutate=mutate)).generate(
                        published_course(), f"req-answer-{index}"
                    )
                self.assertEqual(context.exception.code, "openmaic_answer_authority_leak")

    def test_rejects_action_media_and_interactive_scenes(self):
        mutations = (
            lambda draft: draft["scenes"][0].update({"actions": []}),
            lambda draft: draft["scenes"][0]["interactionDraft"]["elements"].append(
                {"type": "image", "src": "https://example.test/image.png"}
            ),
            lambda draft: draft["scenes"][0].update({"type": "interactive"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(LearningContentGenerationError) as context:
                    LearningContentGenerationService(FakeAdapter(mutate=mutate)).generate(
                        published_course(), f"req-unsafe-{index}"
                    )
                self.assertEqual(context.exception.code, "openmaic_unsafe_scene")

    def test_rejects_html_or_encoded_html_that_survives_the_sidecar(self):
        mutations = (
            lambda draft: draft["scenes"][1]["interactionDraft"]["questions"][0].update(
                {"question": "<script>alert(1)</script>请回答"}
            ),
            lambda draft: draft["scenes"][0].update(
                {"description": "&lt;img src=x onerror=unsafe()&gt;"}
            ),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(LearningContentGenerationError) as context:
                    LearningContentGenerationService(FakeAdapter(mutate=mutate)).generate(
                        published_course(), f"req-rich-text-{index}"
                    )
                self.assertEqual(context.exception.code, "openmaic_unsafe_scene")

    def test_status_exposes_runtime_policy(self):
        payload = LearningContentGenerationService(FakeAdapter()).status()
        self.assertTrue(payload["available"])
        self.assertFalse(payload["policy"]["actionsEnabled"])
        self.assertFalse(payload["policy"]["mediaEnabled"])
        self.assertEqual(payload["policy"]["answerSource"], "mira_deterministic_validation_only")
        self.assertEqual(payload["policy"]["requiredOutcomeMode"], "scored_deterministic")
        self.assertEqual(
            set(payload["policy"]["allowedSubjects"]),
            {"chinese", "math", "english"},
        )

    def test_maps_adapter_failure_to_stable_business_error(self):
        adapter = FakeAdapter(error=OpenMaicDraftError("openmaic_timeout", "timed out"))
        with self.assertRaises(LearningContentGenerationError) as context:
            LearningContentGenerationService(adapter).generate(published_course(), "req-timeout")
        self.assertEqual(context.exception.code, "openmaic_timeout")


if __name__ == "__main__":
    unittest.main()
