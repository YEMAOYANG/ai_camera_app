from __future__ import annotations

import copy
import hashlib
import json
import unittest

from content.primary_skill_boundaries import boundaries_for
from services.lesson_package_validator import (
    LessonPackageValidationError,
    LessonPackageValidator,
)


class GradeOnePinyinGoldPackageTest(unittest.TestCase):
    def setUp(self):
        self.validator = LessonPackageValidator()
        self.boundary = boundaries_for("primary_1", "chinese")[0]
        self.course = self._course()
        self.source = self._source()

    def test_progression_starts_with_narrow_aoe_before_other_pinyin_and_characters(self):
        boundaries = boundaries_for("primary_1", "chinese")
        self.assertEqual(boundaries[0].skill_id, "pinyin_syllables")
        self.assertEqual(boundaries[0].skill_title, "单韵母 a、o、e")
        self.assertIn("单韵母 a、o、e", boundaries[0].allowed_content)
        self.assertIn("偏旁部首", boundaries[0].excluded_content)
        self.assertEqual(boundaries[1].skill_id, "pinyin_initials_syllables")
        self.assertEqual(boundaries[1].prerequisite_skills, ("pinyin_syllables",))
        self.assertEqual(boundaries[2].skill_id, "characters_words")
        self.assertEqual(
            boundaries[2].prerequisite_skills,
            ("pinyin_initials_syllables",),
        )

    def test_python_compiles_answer_blind_intent_to_controlled_five_phase_package(self):
        compiled = self.validator.compile(
            source=self.source,
            course=self.course,
            source_hash=hashlib.sha256(b"aoe-gold-source").hexdigest(),
        )

        package = compiled.public_payload
        self.assertEqual(
            [scene["phaseRole"] for scene in package["scenes"]],
            ["teach", "demo", "guided", "independent", "recap"],
        )
        self.assertEqual(package["scenes"][0]["layoutTemplate"], "phonics_focus.v1")
        self.assertEqual(
            [item["label"] for item in package["scenes"][0]["templateData"]["focusItems"]],
            ["a", "o", "e"],
        )
        self.assertEqual(
            [
                action["targetId"]
                for action in package["scenes"][0]["actions"]
                if action["type"] == "focus"
            ],
            ["teach-point-1", "teach-point-2", "teach-point-3"],
        )
        self.assertEqual(
            [
                action["targetId"]
                for action in package["scenes"][1]["actions"]
                if action["type"] == "focus"
            ],
            ["demo-prompt", "demo-explanation"],
        )
        guided = package["scenes"][2]
        self.assertEqual(guided["widgetTemplate"], "listen_tap_choice.v1")
        self.assertEqual(guided["questionRefs"], ["q2", "q3"])
        self.assertEqual(
            guided["templateData"]["stateContract"]["completion"],
            "guided_questions_evaluated",
        )
        independent = package["scenes"][3]
        self.assertEqual(independent["mode"], "independent")
        self.assertEqual(independent["questionRefs"], ["q4", "q5"])
        self.assertEqual(
            package["learningMetadata"]["masteryThreshold"],
            {
                "policy": "independent_all_correct_v1",
                "evidenceCount": 2,
                "requiredCorrect": 2,
                "claimScope": "this_lesson_only",
            },
        )
        self.assertEqual(package["assetRefs"], [])
        encoded = json.dumps(package, ensure_ascii=False).casefold()
        for forbidden in ("<script", "javascript", '"html"', '"canvas"', "play_media"):
            self.assertNotIn(forbidden, encoded)
        self.assertNotIn('"answer"', encoded)
        self.assertEqual(compiled.report["sourceMode"], "structured_intent_only")
        self.assertEqual(compiled.report["compilerVersion"], "mira.lesson-package-compiler.v2.3.0")
        self.assertIn("controlled_spotlight_actions", compiled.report["checks"])
        self.assertIn("independent_mastery_evidence_two_of_two", compiled.report["checks"])

    def test_publication_gate_rejects_raw_renderer_fields_role_drift_and_mastery_claim(self):
        raw_html = copy.deepcopy(self.source)
        raw_html["classroom"]["intent"]["html"] = "<button>点一下就完成</button>"
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(source=raw_html, course=self.course, source_hash="a" * 64)
        self.assertEqual(raised.exception.code, "unsafe_classroom_field")

        wrong_roles = copy.deepcopy(self.source)
        wrong_roles["classroom"]["intent"]["guided"]["questionRefs"] = ["q3", "q2"]
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(source=wrong_roles, course=self.course, source_hash="b" * 64)
        self.assertEqual(raised.exception.code, "classroom_question_role_mismatch")

        overclaim = copy.deepcopy(self.source)
        overclaim["classroom"]["intent"]["recap"]["sayText"] = "你已经完全掌握 a、o、e 了。"
        overclaim_course = copy.deepcopy(self.course)
        overclaim_content = json.loads(overclaim_course["content_json"])
        overclaim_content["teachingFlow"]["recap"]["sayText"] = (
            "你已经完全掌握 a、o、e 了。"
        )
        overclaim_course["content_json"] = json.dumps(
            overclaim_content,
            ensure_ascii=False,
        )
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(
                source=overclaim,
                course=overclaim_course,
                source_hash="c" * 64,
            )
        self.assertEqual(raised.exception.code, "classroom_recap_overclaims_mastery")

        unsafe_asset = copy.deepcopy(self.source)
        unsafe_asset["classroom"]["intent"]["assetBrief"][0]["purpose"] = (
            "从 https://example.invalid/aoe.mp3 加载"
        )
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(source=unsafe_asset, course=self.course, source_hash="d" * 64)
        self.assertEqual(raised.exception.code, "unsafe_classroom_asset_brief")

        wrong_template = copy.deepcopy(self.source)
        wrong_template["classroom"]["intent"]["layoutTemplate"] = "concept_focus.v1"
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(source=wrong_template, course=self.course, source_hash="e" * 64)
        self.assertEqual(raised.exception.code, "classroom_gold_template_mismatch")

        failed_review = copy.deepcopy(self.source)
        failed_review["generationMeta"]["teachingReview"] = {
            "passed": False,
            "issues": ["a 的口形说明不准确"],
        }
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(source=failed_review, course=self.course, source_hash="f" * 64)
        self.assertEqual(raised.exception.code, "classroom_teaching_review_failed")

    def test_publication_gate_rejects_widget_and_guided_question_type_mismatch(self):
        wrong_listen_course = copy.deepcopy(self.course)
        content = json.loads(wrong_listen_course["content_json"])
        content["questions"][1]["type"] = "sequence"
        wrong_listen_course["content_json"] = json.dumps(content, ensure_ascii=False)
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(
                source=self.source,
                course=wrong_listen_course,
                source_hash="1" * 64,
            )
        self.assertEqual(
            raised.exception.code,
            "classroom_widget_question_type_mismatch",
        )

        wrong_sort_source = copy.deepcopy(self.source)
        wrong_sort_source["classroom"]["intent"]["widgetTemplate"] = "sort_order.v1"
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(
                source=wrong_sort_source,
                course=self.course,
                source_hash="2" * 64,
            )
        self.assertEqual(
            raised.exception.code,
            "classroom_widget_question_type_mismatch",
        )

    def _course(self):
        questions = [
            self._question("q1", "老师示范：哪一个是 a？", "a", "示范时先看字形 a，再听读音。"),
            self._question("q2", "听辨后选择 a。", "a", "a 的口形是嘴巴张大。"),
            self._question("q3", "听辨后选择 o。", "o", "o 的口形是嘴巴圆圆。"),
            self._question("q4", "听辨后选择 e。", "e", "e 的口形较扁。"),
            self._question("q5", "从 a、o、e 中选择 o。", "o", "o 写作圆圆的 o。"),
        ]
        content = {
            "estimatedMinutes": 10,
            "questions": questions,
            "teachingFlow": {
                "schemaVersion": "mira.learning.teaching-flow.v1",
                "teach": {
                    "title": "单韵母 a、o、e",
                    "sayText": "先看口形，再听读音。",
                    "keyPoints": ["a", "o", "e"],
                },
                "demoQuestionId": "q1",
                "guidedQuestionIds": ["q2", "q3"],
                "independentQuestionIds": ["q4", "q5"],
                "recap": {"sayText": "回顾三个单韵母。"},
            },
        }
        return {
            "id": "gold-aoe-course",
            "version": "1.0.0",
            "grade_code": "primary_1",
            "subject": "chinese",
            "node_code": "pinyin_syllables",
            "title": "单韵母 a、o、e",
            "content_json": json.dumps(content, ensure_ascii=False),
        }

    @staticmethod
    def _question(question_id, prompt, answer_label, explanation):
        choices = [
            {"id": "a", "label": "a"},
            {"id": "o", "label": "o"},
            {"id": "e", "label": "e"},
        ]
        return {
            "id": question_id,
            "type": "single_choice",
            "prompt": prompt,
            "skill": "单韵母听辨",
            "hint": "先看口形，再听读音。",
            "explanation": explanation,
            "answer": answer_label,
            "choices": choices,
        }

    def _source(self):
        boundary = self.boundary.to_openmaic_payload()
        return {
            "schemaVersion": "mira.openmaic.classroom_intent.v2",
            "dslVersion": "0.1.0",
            "generator": "openmaic",
            "requestId": "gold-aoe-intent",
            "provider": "kimi",
            "model": "kimi-test",
            "status": "unverified",
            "publicationEligible": False,
            "authoritativeAnswersProvided": False,
            "sourceAuthority": "openmaic_generation_untrusted",
            "gradeCode": "primary_1",
            "subject": "chinese",
            "skillBoundary": boundary,
            "classroom": {
                "id": "stage-1",
                "title": "单韵母 a、o、e",
                "language": "zh-CN",
                "intent": {
                    "schemaVersion": "mira.learning.classroom-intent.v1",
                    "layoutTemplate": "phonics_focus.v1",
                    "widgetTemplate": "listen_tap_choice.v1",
                    "assetBrief": [
                        {
                            "id": "aoe-pronunciation",
                            "kind": "audio",
                            "purpose": "a、o、e 标准发音，可由受控 TTS 提供",
                            "required": False,
                            "deliveryMode": "tts",
                        }
                    ],
                    "misconceptions": ["把 a、o、e 的口形混在一起", "只看字形不认真听读音"],
                    "teach": {
                        "title": "单韵母 a、o、e",
                        "sayText": "先看口形，再听读音。",
                        "keyPoints": ["a", "o", "e"],
                    },
                    "demo": {
                        "title": "老师示范",
                        "sayText": "示范时先看字形 a，再听读音。",
                        "keyPoints": ["看口形", "听读音"],
                    },
                    "guided": {
                        "title": "听一听，点一点",
                        "sayText": "听完一个读音，再点对应的字母。",
                        "keyPoints": [],
                        "questionRefs": ["q2", "q3"],
                    },
                    "independent": {
                        "title": "我来自己试",
                        "sayText": "独立完成最后两道练习。",
                        "keyPoints": [],
                        "questionRefs": ["q4", "q5"],
                    },
                    "recap": {
                        "title": "回顾一下",
                        "sayText": "回顾三个单韵母。",
                        "keyPoints": ["认清 a、o、e", "先听再读"],
                    },
                    "gameRules": {
                        "goal": "完成两道引导听辨",
                        "instructions": ["先听读音", "再点字母", "听反馈后继续"],
                        "successCriterion": "两道引导练习都经过服务器判定",
                        "maxAttempts": 2,
                        "feedbackMode": "encouraging_retry",
                    },
                },
            },
            "generationMeta": {
                "sourceMode": "structured_intent_only",
                "teachingReview": {
                    "passed": True,
                    "issues": [],
                    "reviewer": "independent_ai_classroom_intent_review_v2",
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
