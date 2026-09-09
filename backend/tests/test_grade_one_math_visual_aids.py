from __future__ import annotations

import hashlib
import json
import re
import unittest

from content.primary_skill_boundaries import boundaries_for
from services.lesson_package_validator import (
    LESSON_PACKAGE_COMPILER_VERSION,
    LessonPackageValidationError,
    LessonPackageValidator,
)
from tests.test_learning_catalog_validator import (
    _valid_add_sub_course,
    _valid_number_sense_course,
    _valid_shapes_position_course,
)


class GradeOneMathVisualAidsTest(unittest.TestCase):
    def setUp(self):
        self.validator = LessonPackageValidator()

    def test_compiles_three_math_boundaries_to_controlled_visual_aids(self):
        cases = (
            (
                _valid_add_sub_course(),
                [
                    self._image_brief("combine-counters", "合起来的圆片演示"),
                    self._image_brief("take-away-counters", "去掉圆片的演示"),
                ],
                ["math_counters.v1", "math_counters.v1"],
            ),
            (
                _valid_number_sense_course(),
                [
                    self._image_brief("compare-numbers", "20以内数的大小比较"),
                    self._image_brief("place-value", "十位和个位的积木演示"),
                ],
                ["number_compare.v1", "place_value.v1"],
            ),
            (
                _valid_shapes_position_course(),
                [
                    self._image_brief("shape-family", "常见平面图形"),
                    self._image_brief("position-map", "上下左右位置图"),
                ],
                ["shape_gallery.v1", "position_compass.v1"],
            ),
        )

        for catalog_course, briefs, expected_kinds in cases:
            with self.subTest(node_code=catalog_course["nodeCode"]):
                course = self._database_course(catalog_course)
                compiled = self.validator.compile(
                    source=self._source(catalog_course, briefs),
                    course=course,
                    source_hash=hashlib.sha256(
                        catalog_course["nodeCode"].encode("utf-8")
                    ).hexdigest(),
                )
                package = compiled.public_payload
                teach = package["scenes"][0]
                aids = teach["templateData"]["visualAids"]
                self.assertEqual([item["kind"] for item in aids], expected_kinds)
                self.assertEqual(package["assetBrief"], [])
                self.assertEqual(
                    compiled.report["fulfilledAssetBriefCount"],
                    len(briefs),
                )
                self.assertEqual(
                    compiled.report["controlledVisualAidCount"],
                    len(aids),
                )
                self.assertEqual(
                    compiled.report["compilerVersion"],
                    LESSON_PACKAGE_COMPILER_VERSION,
                )
                encoded = json.dumps(package, ensure_ascii=False).casefold()
                self.assertNotIn('"html"', encoded)
                self.assertNotIn('"canvas"', encoded)
                self.assertNotIn('"answer"', encoded)
                self.assertNotIn("http://", encoded)
                self.assertNotIn("https://", encoded)

    def test_counter_aids_use_reviewed_teaching_equations(self):
        catalog_course = _valid_add_sub_course()
        compiled = self.validator.compile(
            source=self._source(
                catalog_course,
                [self._image_brief("counter-model", "加减法圆片模型")],
            ),
            course=self._database_course(catalog_course),
            source_hash="a" * 64,
        )
        aids = compiled.public_payload["scenes"][0]["templateData"]["visualAids"]
        self.assertEqual(
            aids,
            [
                {
                    "id": "visual-addition-combine",
                    "kind": "math_counters.v1",
                    "operation": "combine",
                    "left": 8,
                    "right": 4,
                    "result": 12,
                    "caption": "把两部分合起来，就是加法。",
                },
                {
                    "id": "visual-subtraction-take-away",
                    "kind": "math_counters.v1",
                    "operation": "take_away",
                    "left": 13,
                    "right": 4,
                    "result": 9,
                    "caption": "从原来的一组里去掉一部分，就是减法。",
                },
            ],
        )

    def test_number_visuals_do_not_reuse_practice_numbers(self):
        catalog_course = _valid_number_sense_course()
        compiled = self.validator.compile(
            source=self._source(
                catalog_course,
                [self._image_brief("number-tools", "数位和大小比较")],
            ),
            course=self._database_course(catalog_course),
            source_hash="b" * 64,
        )
        aids = compiled.public_payload["scenes"][0]["templateData"]["visualAids"]
        comparison, place_value = aids
        practice_text = json.dumps(
            catalog_course["content"]["questions"][1:],
            ensure_ascii=False,
        )
        practice_numbers = {
            int(value)
            for value in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", practice_text)
        }
        for value in (
            comparison["left"],
            comparison["right"],
            place_value["value"],
        ):
            self.assertNotIn(value, practice_numbers)

    def test_required_non_visual_asset_fails_closed(self):
        catalog_course = _valid_shapes_position_course()
        video = {
            "id": "required-video",
            "kind": "video",
            "purpose": "图形位置演示视频",
            "required": True,
            "deliveryMode": "generated_asset",
        }
        with self.assertRaises(LessonPackageValidationError) as raised:
            self.validator.compile(
                source=self._source(catalog_course, [video]),
                course=self._database_course(catalog_course),
                source_hash="c" * 64,
            )
        self.assertEqual(
            raised.exception.code,
            "required_classroom_asset_unfulfilled",
        )

    def test_answer_disclosure_gate_distinguishes_place_value_teaching_from_answer_claims(self):
        ordinary_teaching = self.validator._canonical_text(
            "比如15就是1个十和5个一，20也是两位数，它是2个十和0个一。"
        )
        self.assertFalse(
            self.validator._explicit_answer_disclosure(ordinary_teaching, "20")
        )
        for leak in (
            "这题正确答案是20。",
            "所以应选20。",
            "正确的数为20。",
            "请直接选择20。",
        ):
            with self.subTest(leak=leak):
                self.assertTrue(
                    self.validator._explicit_answer_disclosure(
                        self.validator._canonical_text(leak),
                        "20",
                    )
                )

    @staticmethod
    def _image_brief(brief_id: str, purpose: str) -> dict:
        return {
            "id": brief_id,
            "kind": "image",
            "purpose": purpose,
            "required": True,
            "deliveryMode": "generated_asset",
        }

    @staticmethod
    def _database_course(catalog_course: dict) -> dict:
        return {
            "id": catalog_course["id"],
            "version": catalog_course["version"],
            "grade_code": catalog_course["gradeCode"],
            "subject": catalog_course["subject"],
            "node_code": catalog_course["nodeCode"],
            "title": catalog_course["title"],
            "content_json": json.dumps(
                catalog_course["content"],
                ensure_ascii=False,
            ),
        }

    @staticmethod
    def _source(catalog_course: dict, briefs: list[dict]) -> dict:
        content = catalog_course["content"]
        flow = content["teachingFlow"]
        by_id = {item["id"]: item for item in content["questions"]}
        demo = by_id[flow["demoQuestionId"]]
        boundary = next(
            item
            for item in boundaries_for(
                catalog_course["gradeCode"],
                catalog_course["subject"],
            )
            if item.skill_id == catalog_course["nodeCode"]
        )
        return {
            "schemaVersion": "mira.openmaic.classroom_intent.v2",
            "dslVersion": "0.1.0",
            "generator": "openmaic",
            "requestId": f"visual-{catalog_course['nodeCode']}",
            "provider": "kimi",
            "model": "kimi-test",
            "status": "unverified",
            "publicationEligible": False,
            "authoritativeAnswersProvided": False,
            "sourceAuthority": "openmaic_generation_untrusted",
            "gradeCode": catalog_course["gradeCode"],
            "subject": catalog_course["subject"],
            "skillBoundary": boundary.to_openmaic_payload(),
            "classroom": {
                "id": f"stage-{catalog_course['nodeCode']}",
                "title": catalog_course["title"],
                "language": "zh-CN",
                "intent": {
                    "schemaVersion": "mira.learning.classroom-intent.v1",
                    "layoutTemplate": "concept_focus.v1",
                    "widgetTemplate": "match_pairs.v1",
                    "assetBrief": briefs,
                    "misconceptions": ["只看一个线索就急着作答"],
                    "teach": {
                        "title": flow["teach"]["title"],
                        "sayText": flow["teach"]["sayText"],
                        "keyPoints": flow["teach"]["keyPoints"],
                    },
                    "demo": {
                        "title": "老师示范",
                        "sayText": demo["explanation"],
                        "keyPoints": ["先看条件", "再用方法"],
                    },
                    "guided": {
                        "title": "跟老师练一练",
                        "sayText": "完成一道后提交，等待反馈再继续。",
                        "keyPoints": [],
                        "questionRefs": flow["guidedQuestionIds"],
                    },
                    "independent": {
                        "title": "我会自己做",
                        "sayText": "独立完成最后两道练习。",
                        "keyPoints": [],
                        "questionRefs": flow["independentQuestionIds"],
                    },
                    "recap": {
                        "title": "一起回顾",
                        "sayText": flow["recap"]["sayText"],
                        "keyPoints": ["说出方法", "检查条件"],
                    },
                    "gameRules": {
                        "goal": "完成两道引导练习",
                        "instructions": ["先看题", "提交后等待反馈"],
                        "successCriterion": "两道题都经过服务器判定",
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
