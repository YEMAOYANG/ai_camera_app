from __future__ import annotations

import io
import json
import unittest
import wave

from integrations.tts.voxcpm2 import (
    TtsHttpResponse,
    VoxCpm2HttpProvider,
)
from services.tts_provider import TtsProviderError, TtsSynthesisRequest


def test_wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 800)
    return output.getvalue()


class RecordingTransport:
    def __init__(self, *, content_type: str = "audio/wav", body: bytes | None = None):
        self.content_type = content_type
        self.body = test_wav_bytes() if body is None else body
        self.calls: list[dict] = []

    def post(self, *, url, headers, body, timeout_seconds):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout": timeout_seconds,
            }
        )
        return TtsHttpResponse(
            status=200,
            headers={"content-type": self.content_type},
            body=self.body,
        )


class VoxCpm2HttpProviderTest(unittest.TestCase):
    def request(self):
        return TtsSynthesisRequest(
            text="跟我读 a。",
            language_code="zh-CN",
            voice_prompt="温柔清晰的老师声音",
        )

    def test_vllm_omni_contract_uses_official_speech_endpoint_without_credentials(self):
        transport = RecordingTransport()
        provider = VoxCpm2HttpProvider(
            base_url="http://127.0.0.1:8000/v1",
            backend="vllm-omni",
            transport=transport,
        )
        result = provider.synthesize(self.request())
        call = transport.calls[0]
        self.assertEqual(call["url"], "http://127.0.0.1:8000/v1/audio/speech")
        payload = json.loads(call["body"].decode("utf-8"))
        self.assertEqual(payload["model"], "openbmb/VoxCPM2")
        self.assertEqual(payload["voice"], "default")
        self.assertEqual(payload["response_format"], "wav")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["input"], "(温柔清晰的老师声音)跟我读 a。")
        self.assertNotIn("Authorization", call["headers"])
        self.assertNotIn("api_key", payload)
        self.assertEqual(result.mime_type, "audio/wav")
        self.assertEqual(result.duration_ms, 100)

    def test_python_api_contract_uses_official_upload_fields_without_clone_audio(self):
        transport = RecordingTransport()
        provider = VoxCpm2HttpProvider(
            base_url="http://127.0.0.1:8000",
            backend="python-api",
            transport=transport,
        )
        provider.synthesize(self.request())
        call = transport.calls[0]
        body = call["body"].decode("utf-8")
        self.assertEqual(call["url"], "http://127.0.0.1:8000/tts/upload")
        self.assertIn('name="text"', body)
        self.assertIn("(温柔清晰的老师声音)跟我读 a。", body)
        self.assertIn('name="cfg_value"', body)
        self.assertIn('name="inference_timesteps"', body)
        self.assertNotIn("reference_audio", body)
        self.assertNotIn("prompt_audio", body)
        self.assertNotIn("Authorization", call["headers"])

    def test_rejects_browser_style_credentials_in_base_url(self):
        with self.assertRaises(ValueError):
            VoxCpm2HttpProvider(base_url="http://user:key@127.0.0.1:8000")

    def test_rejects_non_audio_response_and_empty_audio(self):
        provider = VoxCpm2HttpProvider(
            base_url="http://127.0.0.1:8000",
            transport=RecordingTransport(content_type="application/json"),
        )
        with self.assertRaises(TtsProviderError) as invalid_type:
            provider.synthesize(self.request())
        self.assertEqual(invalid_type.exception.code, "tts_invalid_content_type")

        empty_provider = VoxCpm2HttpProvider(
            base_url="http://127.0.0.1:8000",
            transport=RecordingTransport(body=b""),
        )
        with self.assertRaises(TtsProviderError) as empty:
            empty_provider.synthesize(self.request())
        self.assertEqual(empty.exception.code, "tts_empty_audio")


if __name__ == "__main__":
    unittest.main()
