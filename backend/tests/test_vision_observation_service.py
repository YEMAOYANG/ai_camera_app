from __future__ import annotations

import unittest
from pathlib import Path

from dataclasses import dataclass

from services.vision_observation_service import VisionObservationService
from services.prompt_registry import PromptRegistry
from services.vision_observation_validator import VisionObservationValidator

PROMPT_ROOT = Path(__file__).resolve().parents[1] / "prompts"


@dataclass
class _FakeVisionResponse:
    text: str
    provider: str = "test"
    model: str = "test"


class _FakeVisionProvider:
    provider_name = "test"
    model_name = "test"

    def __init__(self, text: str):
        self.text = text

    def analyze_image(self, **kwargs):
        return _FakeVisionResponse(text=self.text)


class VisionObservationServiceTest(unittest.TestCase):
    def test_analyze_snapshot_enriches_homework_like(self):
        service = VisionObservationService(
            vision_provider=_FakeVisionProvider(
                '{"has_person": true, "activity": "写作业", "raw_activity": "写字", "confidence": 0.9, "description": "孩子在书桌前写作业。", "posture_status": "ok", "bad_posture": false, "toys_visible": false, "toys_scattered": false, "child_message": ""}'
            ),
            prompt_registry=PromptRegistry(PROMPT_ROOT),
            validator=VisionObservationValidator(),
            enabled=True,
            min_interval_seconds=0,
            max_calls_per_hour=100,
        )
        result = service.analyze_snapshot(
            image_bytes=b"\xff\xd8\xff\xd9",
            content_type="image/jpeg",
            device_key="test-device",
            force_analyze=True,
        )
        self.assertEqual(result["activity"], "写作业")
        self.assertTrue(result["homework_like"])
        self.assertEqual(result["method"], "guardian_kimi_k26")


    def test_rendered_prompt_includes_child_reference(self):
        captured = {}

        class _CapturingProvider(_FakeVisionProvider):
            def analyze_image(self, **kwargs):
                captured["user_prompt"] = kwargs.get("user_prompt")
                return super().analyze_image(**kwargs)

        service = VisionObservationService(
            vision_provider=_CapturingProvider(
                '{"has_person": true, "activity": "写作业", "raw_activity": "写字", "confidence": 0.9, "description": "画面中可见一个人的手臂。", "posture_status": "ok", "bad_posture": false, "toys_visible": false, "toys_scattered": false, "child_message": ""}'
            ),
            prompt_registry=PromptRegistry(PROMPT_ROOT),
            validator=VisionObservationValidator(),
            enabled=True,
            min_interval_seconds=0,
            max_calls_per_hour=100,
        )
        result = service.analyze_snapshot(
            image_bytes=b"\xff\xd8\xff\xd9",
            content_type="image/jpeg",
            device_key="test-device",
            context={"child_reference": "小明", "age_stage": "小学低年级"},
            force_analyze=True,
        )
        prompt = str(captured.get("user_prompt") or "")
        self.assertIn("小明", prompt)
        self.assertIn("小学低年级", prompt)
        self.assertNotIn("一个人", result.get("description") or "")


if __name__ == "__main__":
    unittest.main()
