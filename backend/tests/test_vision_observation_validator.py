from __future__ import annotations

import unittest

from services.vision_observation_enrich import enrich_observation_risks, is_homework_like
from services.vision_observation_validator import VisionObservationValidator


class VisionObservationValidatorTest(unittest.TestCase):
    def test_parses_json_fence_and_whitelist_activity(self):
        validator = VisionObservationValidator()
        result = validator.validate(
            '```json\n{"has_person": true, "activity": "玩手机", "confidence": 0.82, "description": "孩子低头看手机。"}\n```'
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.observation["activity"], "玩手机")

    def test_invalid_json_returns_fallback(self):
        validator = VisionObservationValidator()
        result = validator.validate("not-json")
        self.assertFalse(result.ok)
        self.assertEqual(result.observation["confidence"], 0.0)


class VisionObservationEnrichTest(unittest.TestCase):
    def test_homework_like_excludes_phone_activity(self):
        obs = enrich_observation_risks(
            {
                "has_person": True,
                "activity": "玩手机",
                "description": "孩子正在玩手机。",
            }
        )
        self.assertFalse(obs["homework_like"])

    def test_homework_like_detects_writing(self):
        obs = {
            "has_person": True,
            "activity": "写作业",
            "description": "孩子在书桌前写字。",
        }
        self.assertTrue(is_homework_like(obs))
        enriched = enrich_observation_risks(obs)
        self.assertTrue(enriched["homework_like"])


if __name__ == "__main__":
    unittest.main()
