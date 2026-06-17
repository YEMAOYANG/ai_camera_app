from __future__ import annotations

import unittest
from pathlib import Path

from services.ai_care_reminder_service import AiCareReminderService
from services.ai_text_provider import AiTextResponse
from services.reminder_text_validator import ReminderTextValidator
from services.auth_service import AuthService
from services.prompt_registry import PromptRegistry
from tests.support import TEST_DATABASE_URL, reset_mysql_test_database


class FakeAiProvider:
    provider_name = "fake"
    model_name = "fake-care-reminder"

    def __init__(self, text: str | None):
        self.text = text

    def complete(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 96, temperature: float = 0.4):
        if self.text is None:
            return None
        return AiTextResponse(text=self.text, provider=self.provider_name, model=self.model_name)


class AiCareReminderTextValidationTest(unittest.TestCase):
    def test_valid_json_text_passes(self):
        validator = ReminderTextValidator()

        result = validator.validate_json_text(
            '{"text":"玩具玩好啦，把它们送回家吧。","tone":"warm","scenario":"toy_cleanup","safety":"ok"}',
            scenario="toy_cleanup",
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.text, "玩具玩好啦，把它们送回家吧。")

    def test_invalid_json_banned_repeated_and_long_text_fail(self):
        validator = ReminderTextValidator(max_length=20)

        self.assertEqual(
            validator.validate_json_text("请收玩具。", scenario="toy_cleanup").reason,
            "invalid_json",
        )
        self.assertTrue(
            validator.validate_json_text(
                '{"text":"系统检测到你不乖，妈妈会生气。","tone":"warm","scenario":"toy_cleanup","safety":"ok"}',
                scenario="toy_cleanup",
            ).reason.startswith("forbidden:")
        )
        self.assertEqual(
            validator.validate_json_text(
                '{"text":"玩具玩好啦，把它们送回家吧。","tone":"warm","scenario":"toy_cleanup","safety":"ok"}',
                scenario="toy_cleanup",
                last_text="玩具玩好啦，把它们送回家吧。",
            ).reason,
            "repeated",
        )
        self.assertEqual(
            validator.validate_json_text(
                '{"text":"玩具玩好啦，我们现在一起把小积木和小汽车都慢慢送回自己的家里吧。","tone":"warm","scenario":"toy_cleanup","safety":"ok"}',
                scenario="toy_cleanup",
            ).reason,
            "too_long",
        )

    def test_service_uses_fallback_when_ai_is_unavailable_or_invalid(self):
        reset_mysql_test_database()
        service = AiCareReminderService(
            TEST_DATABASE_URL,
            auth_service=AuthService(TEST_DATABASE_URL),
            ai_text_provider=FakeAiProvider("不是 JSON"),
            prompt_registry=PromptRegistry(Path(__file__).resolve().parents[1] / "prompts"),
        )

        result = service.generate_and_record(
            family_id="fam_test",
            child_id="child_test",
            device_id=None,
            scenario="toy_cleanup",
            context={"dayType": "school_day"},
        )

        self.assertEqual(result["event"]["textSource"], "fallback")
        self.assertTrue(result["event"]["fallbackUsed"])
        self.assertNotIn("系统检测到", result["event"]["text"])


if __name__ == "__main__":
    unittest.main()
