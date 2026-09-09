from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)


class _Client(OpenMaicFullRuntimeClient):
    def __init__(self) -> None:
        super().__init__(
            "http://127.0.0.1:3000",
            timeout_seconds=120,
            formal_audio_internal_token="i" * 32,
        )
        self.calls = []

    def _request_json(
        self, method, path, body=None, *, extra_headers=None,
        timeout_seconds=None,
    ):
        self.calls.append(
            (method, path, body, dict(extra_headers or {}), timeout_seconds)
        )
        request_id = str((body or {}).get("requestId") or path.rsplit("=", 1)[-1])
        if path.startswith("/api/mira/formal-audio/asr"):
            transcript = "你好同学"
            return {
                "success": True,
                "requestId": request_id,
                "state": "succeeded",
                "transcript": transcript,
                "transcriptSha256": hashlib.sha256(transcript.encode()).hexdigest(),
            }
        return {
            "success": True,
            "requestId": request_id,
            "state": "succeeded",
            "audioSha256": "2" * 64,
            "mimeType": "audio/wav",
        }


class _AudioResponse:
    def __init__(self, body: bytes, url: str) -> None:
        self.body = body
        self.url = url
        self.headers = {
            "Content-Type": "audio/wav",
            "Content-Length": str(len(body)),
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self, _size=-1):
        return self.body


class FormalQwenAudioClientTest(unittest.TestCase):
    def test_audio_scene_order_uses_the_adaptive_runtime_bound(self) -> None:
        common = {
            "request_id": "tts-239",
            "classroom_id": "classroom-1",
            "classroom_content_sha256": "0" * 64,
            "subject": "math",
            "teacher_profile_id": "mira_math_clear",
            "teacher_profile_version": 2,
            "teacher_profile_sha256": "1" * 64,
            "teacher_gender": "male",
            "scene_id": "scene-59",
            "action_id": "action-239",
            "narration_segment_id": "narration-239",
        }

        payload = OpenMaicFullRuntimeClient._formal_audio_identity_payload(
            **common,
            scene_order=239,
        )

        self.assertEqual(payload["sceneOrder"], 239)
        with self.assertRaises(OpenMaicFullRuntimeError):
            OpenMaicFullRuntimeClient._formal_audio_identity_payload(
                **common,
                scene_order=240,
            )

    def test_tts_and_asr_requests_expose_only_frozen_identity_fields(self) -> None:
        client = _Client()
        tts = client.start_formal_audio_tts(
            request_id="tts-1",
            classroom_id="classroom-1",
            classroom_content_sha256="0" * 64,
            subject="math",
            teacher_profile_id="mira_math_clear",
            teacher_profile_version=2,
            teacher_profile_sha256="1" * 64,
            teacher_gender="male",
            scene_id="scene-1",
            scene_order=0,
            action_id="action-1",
            narration_segment_id="narration-1",
            text="我们一起学数学",
            text_sha256=hashlib.sha256("我们一起学数学".encode()).hexdigest(),
        )
        self.assertEqual(tts["audioSha256"], "2" * 64)
        method, path, payload, headers, timeout_seconds = client.calls[0]
        self.assertEqual((method, path), ("POST", "/api/mira/formal-audio/tts"))
        self.assertEqual(set(payload), {
            "requestId", "classroomId", "classroomContentSha256", "subject",
            "teacherProfileId", "teacherProfileVersion", "teacherProfileSha256",
            "teacherGender", "sceneId", "sceneOrder", "actionId",
            "narrationSegmentId", "text", "textSha256",
        })
        self.assertTrue({"provider", "model", "voice", "fallback", "apiKey", "baseUrl", "audioUrl", "audioBase64"}.isdisjoint(payload))
        self.assertEqual(headers, {
            "X-Mira-Internal-Token": "i" * 32,
            "X-Forwarded-For": "127.0.0.1",
            "X-Forwarded-Host": "127.0.0.1:3000",
            "X-Forwarded-Port": "3000",
            "X-Forwarded-Proto": "http",
        })
        self.assertEqual(
            timeout_seconds,
            OpenMaicFullRuntimeClient.FORMAL_AUDIO_REQUEST_TIMEOUT_SECONDS,
        )

        asr = client.start_formal_audio_asr(
            request_id="asr-1",
            tts_request_id="tts-1",
            classroom_id="classroom-1",
            classroom_content_sha256="0" * 64,
            subject="math",
            teacher_profile_id="mira_math_clear",
            teacher_profile_version=2,
            teacher_profile_sha256="1" * 64,
            teacher_gender="male",
            scene_id="scene-1",
            scene_order=0,
            action_id="action-1",
            narration_segment_id="narration-1",
            audio_sha256="2" * 64,
        )
        self.assertEqual(asr["transcript"], "你好同学")
        self.assertEqual(set(client.calls[1][2]), {
            "requestId", "ttsRequestId", "classroomId", "classroomContentSha256",
            "subject", "teacherProfileId", "teacherProfileVersion",
            "teacherProfileSha256", "teacherGender", "sceneId", "sceneOrder",
            "actionId", "narrationSegmentId", "audioSha256",
        })

    def test_tts_download_is_same_origin_bounded_wav_with_exact_hash(self) -> None:
        audio = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"0" * 32
        digest = hashlib.sha256(audio).hexdigest()
        url = "http://127.0.0.1:3000/api/mira/formal-audio/tts?requestId=tts-1&download=1"
        with patch(
            "integrations.openmaic_full_runtime_client.urlopen",
            return_value=_AudioResponse(audio, url),
        ):
            result = OpenMaicFullRuntimeClient(
                "http://127.0.0.1:3000", timeout_seconds=120,
                formal_audio_internal_token="i" * 32,
            ).download_formal_audio_tts("tts-1", expected_sha256=digest)
        self.assertEqual(result, audio)

    def test_asr_get_observation_never_fabricates_ephemeral_transcript(self) -> None:
        class ObservationClient(_Client):
            def _request_json(
                self, method, path, body=None, *, extra_headers=None,
                timeout_seconds=None,
            ):
                self.calls.append(
                    (method, path, body, dict(extra_headers or {}), timeout_seconds)
                )
                return {
                    "success": True,
                    "requestId": "asr-1",
                    "state": "succeeded",
                    "transcriptSha256": "4" * 64,
                }

        observed = ObservationClient().get_formal_audio_asr("asr-1")
        self.assertEqual(observed["status"], "succeeded")
        self.assertIsNone(observed["transcript"])
        self.assertFalse(observed["completionUsable"])

    def test_formal_audio_private_headers_reject_https_even_with_token(self) -> None:
        client = OpenMaicFullRuntimeClient(
            "https://127.0.0.1:3000",
            formal_audio_internal_token="i" * 32,
        )
        with self.assertRaises(OpenMaicFullRuntimeError) as raised:
            client.get_formal_audio_tts("tts-1")
        self.assertEqual(raised.exception.code, "formal_audio_private_authority_missing")


if __name__ == "__main__":
    unittest.main()
