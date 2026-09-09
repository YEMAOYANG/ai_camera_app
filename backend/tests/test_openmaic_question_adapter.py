from __future__ import annotations

import copy
import json
import unittest

from content.primary_skill_boundaries import boundary_for
from integrations.openmaic_question_adapter import OpenMaicQuestionAdapter
from tests.test_learning_generated_course_validator import math_candidate


class OpenMaicQuestionAdapterTest(unittest.TestCase):
    def test_question_sidecar_process_timeout_is_configurable(self):
        captured = {}

        def fake_runner(*args, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            return type(
                "Completed",
                (),
                {
                    "stdout": json.dumps(
                        {"available": True, "supportedContracts": []}
                    ),
                    "returncode": 0,
                },
            )()

        adapter = OpenMaicQuestionAdapter(
            fake_mode=True,
            timeout_seconds=420,
            process_runner=fake_runner,
        )
        adapter.availability()
        self.assertEqual(captured["timeout"], 420.0)

    def test_generation_feedback_is_forwarded_as_a_bounded_separate_field(self):
        boundary = boundary_for("primary_3", "math")
        captured = {}
        adapter = OpenMaicQuestionAdapter(fake_mode=True)

        def fake_call(payload):
            captured["payload"] = payload
            raise RuntimeError("payload captured")

        adapter._call = fake_call
        with self.assertRaisesRegex(RuntimeError, "payload captured"):
            adapter.generate(
                request_id="adapter-feedback",
                grade_code="primary_3",
                subject="math",
                skill_boundary=boundary.to_openmaic_payload(),
                generation_feedback={
                    "code": "invalid_generated_course",
                    "message": "q4 缺少比较证据",
                },
            )
        self.assertEqual(
            captured["payload"]["generationFeedback"],
            {
                "code": "invalid_generated_course",
                "message": "q4 缺少比较证据",
            },
        )
        self.assertNotIn("studentId", captured["payload"])

    def test_verification_payload_includes_q1_explanation_without_answer(self):
        boundary = boundary_for("primary_3", "math")
        candidate = math_candidate()
        captured = {}
        adapter = OpenMaicQuestionAdapter(fake_mode=True)

        def fake_call(payload):
            captured["payload"] = payload
            return (
                {
                    "schemaVersion": "mira.openmaic.question_verification_result.v1",
                    "requestId": "adapter-public-worked-example",
                    "generator": "openmaic",
                    "solution": {
                        "teachingReview": {"passed": True, "issues": []}
                    },
                },
                1,
            )

        adapter._call = fake_call
        adapter.verify(
            request_id="adapter-public-worked-example",
            grade_code="primary_3",
            subject="math",
            skill_boundary=boundary.to_openmaic_payload(),
            candidate_course=candidate,
        )

        worked_example = captured["payload"]["publicTeachingFlow"][
            "workedExample"
        ]
        first_question = candidate["content"]["questions"][0]
        self.assertEqual(
            worked_example,
            {
                "questionId": first_question["id"],
                "explanation": first_question["explanation"],
            },
        )
        self.assertNotIn("answer", worked_example)
        self.assertNotIn("evaluation", worked_example)

    def test_consistency_repair_sends_only_public_copy_and_freezes_authority(self):
        boundary = boundary_for("primary_3", "math")
        candidate = math_candidate()
        original = copy.deepcopy(candidate)
        question_ids = [
            str(question["id"])
            for question in candidate["content"]["questions"]
        ]
        captured = {}
        adapter = OpenMaicQuestionAdapter(fake_mode=True)

        def fake_call(payload):
            captured["payload"] = payload
            return (
                {
                    "schemaVersion": (
                        "mira.openmaic.question_consistency_repair_result.v1"
                    ),
                    "requestId": "adapter-consistency-repair",
                    "generator": "openmaic",
                    "repair": {
                        "title": "统一术语后的课程",
                        "intro": "先听清楚统一的比较说法。",
                        "teach": {
                            "title": "统一说“更大”",
                            "sayText": "比较时，我们说一个数比另一个数更大。",
                            "keyPoints": ["先比较", "统一用更大"],
                        },
                        "recap": {"sayText": "今天统一用“更大”比较。"},
                        "questionGuidance": [
                            {
                                "questionId": question_id,
                                "hint": f"第{index}题先自己想。",
                                "explanation": f"第{index}题使用统一术语解释。",
                            }
                            for index, question_id in enumerate(question_ids, start=1)
                        ],
                    },
                },
                1,
            )

        adapter._call = fake_call
        repaired = adapter.repair_consistency(
            request_id="adapter-consistency-repair",
            grade_code="primary_3",
            subject="math",
            skill_boundary=boundary.to_openmaic_payload(),
            candidate_course=candidate,
            review_issues=["示范解析和选项使用了不一致的比较术语"],
        )

        serialized_payload = json.dumps(captured["payload"], ensure_ascii=False)
        self.assertNotIn('"answer"', serialized_payload)
        self.assertNotIn("acceptedAnswers", serialized_payload)
        self.assertNotIn("verificationExpression", serialized_payload)
        self.assertNotIn('"evaluation"', serialized_payload)
        self.assertEqual(repaired.candidate_course["title"], "统一术语后的课程")
        self.assertEqual(
            repaired.candidate_course["content"]["questions"][0]["explanation"],
            "第1题使用统一术语解释。",
        )
        for before, after in zip(
            original["content"]["questions"],
            repaired.candidate_course["content"]["questions"],
        ):
            for key in (
                "id",
                "type",
                "prompt",
                "choices",
                "answer",
                "acceptedAnswers",
                "verificationExpression",
                "evaluation",
            ):
                self.assertEqual(after.get(key), before.get(key), key)

    def test_real_sidecar_generates_then_freshly_solves_public_questions(self):
        boundary = boundary_for("primary_3", "math")
        seed = math_candidate()
        generated = {
            "title": "三年级多位数计算",
            "intro": "先读题，再独立完成五道计算题。",
            "estimatedMinutes": 10,
            "teachingFlow": {
                "teach": {
                    "title": "先理解计算方法",
                    "sayText": "先看清运算符号，再按步骤完成计算。",
                    "keyPoints": ["看清符号", "分步计算", "完成后检查"],
                },
                "recap": {"sayText": "计算时先看清符号，再分步完成并检查。"},
            },
            "questions": [
                self._sidecar_question(question, index=index)
                for index, question in enumerate(
                    seed["content"]["questions"], start=1
                )
            ],
        }
        outline = {
            "courseTitle": "三年级多位数计算",
            "languageDirective": "Use Simplified Chinese.",
            "outlines": [
                {
                    "id": "practice",
                    "type": "quiz",
                    "title": "五题练习",
                    "description": "在固定能力边界内练习",
                    "keyPoints": ["独立计算"],
                    "quizConfig": {
                        "questionCount": 5,
                        "difficulty": "medium",
                        "questionTypes": ["numeric"],
                    },
                }
            ],
        }
        verification = {
            "answers": [
                {
                    "questionId": f"adapter_generation_q{index}",
                    "answer": question["answer"],
                    **(
                        {"derivedExpression": question["verificationExpression"]}
                        if question["type"] == "numeric"
                        else {}
                    ),
                }
                for index, question in enumerate(generated["questions"], start=1)
            ],
            "teachingReview": {"passed": True, "issues": []},
        }
        adapter = OpenMaicQuestionAdapter(
            fake_mode=True,
            provider_name="kimi",
            model_name="kimi-test",
            base_url="https://example.invalid/v1",
            generation_fake_responses=(
                json.dumps(outline, ensure_ascii=False),
                json.dumps(generated, ensure_ascii=False),
                json.dumps(generated, ensure_ascii=False),
                json.dumps(
                    {
                        "title": generated["title"],
                        "intro": generated["intro"],
                        "teachingFlow": generated["teachingFlow"],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "estimatedMinutes": generated["estimatedMinutes"],
                        "questions": generated["questions"],
                    },
                    ensure_ascii=False,
                ),
            ),
            verification_fake_responses=(
                json.dumps(verification, ensure_ascii=False),
            ),
        )

        generated_result = adapter.generate(
            request_id="adapter-generation",
            grade_code="primary_3",
            subject="math",
            skill_boundary=boundary.to_openmaic_payload(),
        )
        solved_result = adapter.verify(
            request_id="adapter-verification",
            grade_code="primary_3",
            subject="math",
            skill_boundary=boundary.to_openmaic_payload(),
            candidate_course=generated_result.candidate_course,
        )

        self.assertEqual(len(generated_result.question_fingerprints), 5)
        self.assertEqual(
            solved_result.solution["verificationRequestId"],
            "adapter-verification",
        )
        self.assertRegex(
            solved_result.solution["publicQuestionHash"], r"^[0-9a-f]{64}$"
        )
        self.assertEqual(
            [
                question["type"]
                for question in generated_result.candidate_course["content"][
                    "questions"
                ][1:3]
            ],
            ["single_choice", "single_choice"],
        )
        for question, answer in zip(
            generated_result.candidate_course["content"]["questions"],
            solved_result.solution["answers"],
        ):
            self.assertEqual(
                "derivedExpression" in answer,
                question["type"] == "numeric",
            )
        self.assertEqual(
            solved_result.solution["teachingReview"],
            {"passed": True, "issues": []},
        )

    def test_verify_rejects_candidate_without_public_teaching_flow(self):
        boundary = boundary_for("primary_3", "math")
        candidate = math_candidate()
        candidate["content"].pop("teachingFlow")
        adapter = OpenMaicQuestionAdapter(fake_mode=True)

        with self.assertRaisesRegex(Exception, "teaching flow"):
            adapter.verify(
                request_id="adapter-missing-flow",
                grade_code="primary_3",
                subject="math",
                skill_boundary=boundary.to_openmaic_payload(),
                candidate_course=candidate,
            )

    @staticmethod
    def _sidecar_question(question: dict, *, index: int) -> dict:
        common = {
            key: question[key]
            for key in ("prompt", "skill", "hint", "explanation")
        }
        if index in {2, 3}:
            answer = int(question["answer"])
            return {
                **common,
                "type": "single_choice",
                "answer": "B",
                "choices": [
                    {"id": "A", "label": str(answer - 1)},
                    {"id": "B", "label": str(answer)},
                    {"id": "C", "label": str(answer + 1)},
                ],
            }
        return {
            **common,
            "type": "numeric",
            "answer": question["answer"],
            "verificationExpression": question["verificationExpression"],
        }


if __name__ == "__main__":
    unittest.main()
