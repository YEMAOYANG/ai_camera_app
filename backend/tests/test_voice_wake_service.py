from __future__ import annotations

import unittest

from services.voice_wake_service import (
    clean_camera_command_text,
    match_wake_names,
    normalize_wake_text,
    wake_ack_text,
)


class VoiceWakeServiceTest(unittest.TestCase):
    def test_normalize_wake_text_strips_punctuation_and_spaces(self):
        self.assertEqual(normalize_wake_text(" 小暖，你好！ "), "小暖你好")

    def test_custom_wake_name_matches_homophones(self):
        for text in ("小暖你好",):
            with self.subTest(text=text):
                result = match_wake_names(text, "小暖", "小暖")
                self.assertTrue(result["matched"])
                self.assertEqual(result["name"], "小暖")

    def test_confirmed_wake_requires_repeat_or_greeting(self):
        result = match_wake_names("小暖", "小暖", "小暖", require_confirmation=True)
        self.assertFalse(result["matched"])
        self.assertEqual(result["reason"], "wake_phrase_not_confirmed")

        for text in ("小暖小暖", "小暖你好"):
            with self.subTest(text=text):
                result = match_wake_names(text, "小暖", "小暖", require_confirmation=True)
                self.assertTrue(result["matched"])
                self.assertEqual(result["name"], "小暖")

    def test_hello_before_name_is_not_confirmed(self):
        result = match_wake_names("你好小暖", "小暖", "小暖", require_confirmation=True)
        self.assertFalse(result["matched"])

    def test_command_cleaning_removes_wake_name(self):
        command = clean_camera_command_text(
            "小暖你好，讲个故事",
            {"wakeName": "小暖", "fallbackWakeName": "小暖"},
        )
        self.assertEqual(command, "讲个故事")

    def test_wake_ack_text(self):
        self.assertEqual(wake_ack_text("小暖"), "小暖在听，你说吧。")


if __name__ == "__main__":
    unittest.main()
