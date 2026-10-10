"""Received provider replies remain recoverable without another paid request."""
import io
import json
import urllib.error
from unittest import TestCase
from unittest.mock import patch

from integrations.ai.kimi_vision_provider import AiVisionResponse, OpenAICompatibleVisionProvider


class VisionResponseReceiptTests(TestCase):
    def provider(self, *, capture=False):
        return OpenAICompatibleVisionProvider(
            provider_name="qwen", api_key="fake-secret", base_url="https://invalid.example/v1",
            model_name="fixture-vision", capture_received_response=capture,
        )

    def reply(self, provider, body, *, headers=None):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        response = io.BytesIO(raw)
        response.headers = headers or {}
        with patch("integrations.ai.kimi_vision_provider._encode_image", return_value="data:image/jpeg;base64,ZmFrZQ=="), \
             patch("urllib.request.urlopen", return_value=response) as transport:
            result = provider.analyze_image(
                system_prompt="fixture prompt", user_prompt="fixture task",
                image_bytes=b"fixture pixels", content_type="image/png",
            )
        transport.assert_called_once()
        return result, raw

    def test_existing_positional_response_and_care_mode_remain_compatible(self):
        legacy = AiVisionResponse("{}", "fixture", "fixture-vision")
        self.assertIsNone(legacy.finish_reason)
        self.assertIsNone(legacy.raw_response)
        result, _ = self.reply(self.provider(), {"choices": [{"message": {"content": " {} "}}]})
        self.assertEqual(result.text, "{}")
        self.assertIsNone(result.raw_response)
        self.assertIsNone(result.response_error)

    def test_truncated_model_content_has_exact_receipt_and_finish_reason(self):
        # A valid HTTP envelope may contain incomplete OCR JSON. This is a
        # returned result, so it must not be confused with a network timeout.
        body = {
            "id": "chatcmpl.fixture-1", "choices": [{"finish_reason": "length", "message": {"content": '{"items":['}}],
            "usage": {"prompt_tokens": 731, "completion_tokens": 7000, "total_tokens": 7731},
        }
        result, raw = self.reply(self.provider(capture=True), body)
        self.assertEqual(result.text, '{"items":[')
        self.assertEqual(result.finish_reason, "length")
        self.assertEqual(result.raw_response, raw)
        self.assertEqual(result.usage["completion_tokens"], 7000)
        self.assertEqual(result.request_id, "chatcmpl.fixture-1")
        self.assertIsNone(result.response_error)
        self.assertNotIn("raw_response", repr(result))

    def test_empty_received_content_preserves_metadata_and_private_envelope(self):
        body = {"choices": [{"finish_reason": "stop", "message": {"content": None}}],
            "usage": {"completion_tokens": 0, "prompt_tokens": 52}}
        result, raw = self.reply(self.provider(capture=True), body, headers={"x-request-id": "fixture-request:1"})
        self.assertEqual(result.response_error, "response_empty_content")
        self.assertEqual(result.raw_response, raw)
        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(result.request_id, "fixture-request:1")
        legacy, _ = self.reply(self.provider(), body)
        self.assertIsNone(legacy)

    def test_received_invalid_json_or_envelope_is_diagnosable_without_replay(self):
        cases = [(b"<html>fixture error</html>", "response_invalid_json"),
            (b"[]", "response_invalid_envelope"), (b'{"choices":[]}', "response_invalid_envelope"),
            (b'{"choices":[{"message":"invalid"}]}', "response_invalid_envelope")]
        for raw, expected in cases:
            with self.subTest(error=expected, raw=raw):
                result, _ = self.reply(self.provider(capture=True), raw)
                self.assertEqual(result.response_error, expected)
                self.assertEqual(result.raw_response, raw)
                self.assertIsNone(self.reply(self.provider(), raw)[0])

    def test_capture_bounds_response_and_reports_that_saved_prefix_is_incomplete(self):
        raw = b"x" * (2 * 1024 * 1024 + 200)
        result, _ = self.reply(self.provider(capture=True), raw)
        self.assertEqual(result.response_error, "response_too_large")
        self.assertEqual(len(result.raw_response), 2 * 1024 * 1024)
        self.assertEqual(result.text, "")

    def test_early_http_disconnect_is_not_mislabeled_as_complete_model_reply(self):
        with self.assertLogs("integrations.ai.kimi_vision_provider", level="WARNING") as logs:
            result, _ = self.reply(self.provider(capture=True), b'{"choices":', headers={"Content-Length": "200"})
        self.assertIsNone(result)
        self.assertIn("IncompleteRead", " ".join(logs.output))

    def test_metadata_cannot_copy_arbitrary_provider_strings_or_non_token_usage(self):
        body = {"id": "untrusted private text", "choices": [{"finish_reason": "untrusted text", "message": {"content": "{}"}}],
            "usage": {"prompt_tokens": True, "completion_tokens": -1, "total_tokens": 50,
                "input_tokens": "53", "output_tokens": 1_000_000_001, "private_prompt": "fixture"}}
        result, _ = self.reply(self.provider(capture=True), body, headers={"x-request-id": "fixture-header-1"})
        self.assertEqual(result.usage, {"total_tokens": 50})
        self.assertEqual(result.request_id, "fixture-header-1")
        self.assertIsNone(result.finish_reason)

    def test_http_or_transport_error_remains_unknown_without_leaking_error_body(self):
        errors = [TimeoutError("fixture-private-prompt"),
            urllib.error.HTTPError("https://invalid.example/v1", 500, "fixture-private-prompt", {}, io.BytesIO(b"fake-secret fixture-private-prompt"))]
        for capture in (False, True):
            for error in errors:
                with self.subTest(capture=capture, error=type(error).__name__), \
                     patch("integrations.ai.kimi_vision_provider._encode_image", return_value="data:image/jpeg;base64,ZmFrZQ=="), \
                     patch("urllib.request.urlopen", side_effect=error), \
                     self.assertLogs("integrations.ai.kimi_vision_provider", level="WARNING") as logs:
                    result = self.provider(capture=capture).analyze_image(
                        system_prompt="fixture", user_prompt="fixture", image_bytes=b"fixture", content_type="image/png")
                self.assertIsNone(result)
                self.assertNotIn("fake-secret", " ".join(logs.output))
                self.assertNotIn("fixture-private-prompt", " ".join(logs.output))
