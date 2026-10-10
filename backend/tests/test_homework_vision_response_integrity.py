"""Counterexamples for corrupt or non-final OCR response envelopes.

Every request is mocked. Camera mode retains its existing decoding contract;
homework capture refuses to grade modified bytes or contradictory metadata.
"""
import io
import json
from unittest import TestCase
from unittest.mock import patch

from integrations.ai.kimi_vision_provider import OpenAICompatibleVisionProvider


class VisionResponseIntegrityTests(TestCase):
    def request(self, raw, *, capture=True):
        provider = OpenAICompatibleVisionProvider(provider_name="qwen", api_key="fake",
            base_url="https://invalid.example/v1", model_name="fixture-vision",
            capture_received_response=capture)
        with patch("integrations.ai.kimi_vision_provider._encode_image", return_value="data:image/jpeg;base64,ZmFrZQ=="), \
             patch("urllib.request.urlopen", return_value=io.BytesIO(raw)) as transport:
            result = provider.analyze_image(system_prompt="fixture", user_prompt="fixture",
                image_bytes=b"fixture", content_type="image/png")
        transport.assert_called_once()
        return result

    def envelope(self, text="{}", reason="stop"):
        return json.dumps({"choices": [{"finish_reason": reason, "message": {"content": text}}]}, ensure_ascii=False).encode()

    def assert_received_error(self, raw, code):
        result = self.request(raw)
        self.assertEqual(result.response_error, code)
        self.assertEqual(result.raw_response, raw)
        self.assertEqual(result.text, "")
        return result

    def test_invalid_utf8_cannot_silently_change_the_photographed_answer(self):
        content = json.dumps({"pageReadable": True, "items": [{"studentAnswer": "34"}]})
        raw = self.envelope(content).replace(b"34", b"3\xff4")
        self.assert_received_error(raw, "response_invalid_encoding")
        # Existing camera behavior is kept, without applying it to homework.
        legacy = self.request(raw, capture=False)
        self.assertEqual(json.loads(legacy.text)["items"][0]["studentAnswer"], "34")

    def test_utf8_bom_is_supported_without_changing_the_saved_envelope(self):
        raw = b"\xef\xbb\xbf" + self.envelope('{"pageReadable":true,"items":[]}')
        result = self.request(raw)
        self.assertIsNone(result.response_error)
        self.assertEqual(result.raw_response, raw)
        self.assertEqual(result.finish_reason, "stop")
        self.assertTrue(json.loads(result.text)["pageReadable"])

    def test_escaped_lone_surrogate_is_preserved_before_utf8_storage_can_fail(self):
        for content in ('\ud800', '\udfff'):
            raw = json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": content}}]}).encode()
            with self.subTest(codepoint=ord(content)):
                self.assert_received_error(raw, "response_invalid_encoding")
                self.assertEqual(self.request(raw, capture=False).text, content)

    def test_duplicate_keys_cannot_overwrite_length_finish_or_actual_content(self):
        cases = [
            b'{"choices":[{"finish_reason":"length","finish_reason":"stop","message":{"content":"{}"}}]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":"first","content":"{}"}}]}',
            b'{"choices":[],"choices":[{"finish_reason":"stop","message":{"content":"{}"}}]}',
            b'{"choices":[{"finish_reason":"stop","message":{"content":"{}"}}],"usage":{"total_tokens":7000,"total_tokens":1}}',
        ]
        for raw in cases:
            with self.subTest(raw=raw):
                self.assert_received_error(raw, "response_invalid_json")
                # Default camera decoding remains last-key-wins as before.
                self.assertEqual(self.request(raw, capture=False).text, "{}")

    def test_nonfinite_http_envelope_number_is_not_valid_provider_json(self):
        for value in (b"NaN", b"Infinity", b"-Infinity"):
            raw = b'{"choices":[{"message":{"content":"{}"}}],"usage":{"total_tokens":' + value + b'}}'
            with self.subTest(value=value):
                self.assert_received_error(raw, "response_invalid_json")
                self.assertEqual(self.request(raw, capture=False).text, "{}")

    def test_explicit_nonfinal_reasons_cannot_grade_parseable_partial_content(self):
        for reason in ("content_filter", "tool_calls", "function_call"):
            raw = self.envelope('{"pageReadable":true,"items":[]}', reason)
            with self.subTest(reason=reason):
                result = self.assert_received_error(raw, "response_incomplete_content")
                self.assertEqual(result.finish_reason, reason)
                self.assertTrue(json.loads(self.request(raw, capture=False).text)["pageReadable"])

    def test_unknown_finish_reason_is_a_known_envelope_error_not_missing_metadata(self):
        for reason in ("max_token_other_format", True, 1, [], {}):
            raw = self.envelope("{}", reason)
            with self.subTest(reason=reason):
                self.assert_received_error(raw, "response_invalid_envelope")
                self.assertEqual(self.request(raw, capture=False).text, "{}")

    def test_absent_finish_reason_remains_supported_for_compatible_providers(self):
        raw = b'{"choices":[{"message":{"content":"{}"}}]}'
        result = self.request(raw)
        self.assertEqual(result.text, "{}")
        self.assertIsNone(result.finish_reason)
        self.assertIsNone(result.response_error)

    def test_decoder_recursion_failure_does_not_lose_already_received_bytes(self):
        raw = self.envelope()
        # JSON nesting limits differ across Python runtimes. Inject the decoder
        # boundary failure without consuming machine stack or making HTTP.
        with patch("integrations.ai.kimi_vision_provider.json.loads", side_effect=RecursionError):
            self.assert_received_error(raw, "response_invalid_json")


if __name__ == "__main__":
    import unittest
    unittest.main()
