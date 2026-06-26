from __future__ import annotations

import unittest

from services.parent_facing_copy import (
    build_child_vision_context,
    sanitize_parent_facing_observation,
)


class ParentFacingCopyTest(unittest.TestCase):
    def test_build_child_vision_context_uses_nickname(self):
        context = build_child_vision_context(
            {"nickname": "小明", "ageStage": "小学低年级", "grade": "二年级"}
        )
        self.assertEqual(context["child_reference"], "小明")
        self.assertEqual(context["age_stage"], "小学低年级")
        self.assertEqual(context["grade"], "二年级")

    def test_build_child_vision_context_defaults_without_child(self):
        context = build_child_vision_context(None)
        self.assertEqual(context["child_reference"], "孩子")
        self.assertEqual(context["age_stage"], "未知")

    def test_sanitize_mid_sentence_one_person_pattern(self):
        cleaned = sanitize_parent_facing_observation("画面中可见一个人的手臂放在桌面上。")
        self.assertNotIn("一个人", cleaned)
        self.assertIn("孩子", cleaned)


if __name__ == "__main__":
    unittest.main()
