from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy

from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)


def _sha(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _request() -> dict:
    return {
        "schemaVersion": "mira.openmaic.formal-provider-readiness.v2",
        "requestId": "provider-ready-1",
        "buildItemId": "build-item-1",
        "releaseId": "release-1",
        "gradeCode": "primary_2",
        "targetFingerprint": "a" * 64,
        "runtimeClassroomId": "runtime-1",
        "runtimeRequestId": "runtime-request-1",
        "upstreamClassroomId": "classroom-1",
        "classroomContentSha256": "b" * 64,
        "audioJobTerminalReceiptSha256": "c" * 64,
        "validation": {
            "subject": "math",
            "sceneOrder": 0,
            "ttsRequestId": "formal-tts-1",
            "audioSha256": "d" * 64,
            "machineReceiptSha256": "e" * 64,
        },
        "routeSession": {
            "schemaVersion": "mira.openmaic.conversation-proof.v1",
            "conversationProbeId": "probe-1",
            "receiptSha256": "f" * 64,
            "providerCall": False,
        },
    }


def _response(request: dict) -> dict:
    call_specs = [
        (1, "deepseek_text", None, "deepseek", "deepseek-v4-pro", None, None),
        (2, "qwen_asr", "math", "qwen-asr", "qwen3-asr-flash", None, "zh-CN"),
        (3, "qwen_tts", "chinese", "qwen-tts", "qwen3-tts-flash", "Serena", "zh-CN"),
        (4, "qwen_tts", "math", "qwen-tts", "qwen3-tts-flash", "Ethan", "zh-CN"),
        (5, "qwen_tts", "english", "qwen-tts", "qwen3-tts-flash", "Jennifer", "en-US"),
    ]
    calls = [
        {
            "callOrdinal": ordinal,
            "kind": kind,
            **({"subject": subject} if subject else {}),
            "providerId": provider_id,
            "modelId": model_id,
            **({"voiceId": voice_id} if voice_id else {}),
            **({"languageCode": language_code} if language_code else {}),
            "fallbackUsed": False,
            "providerCall": True,
            "requestSha256": str(ordinal) * 64,
            "state": "passed",
            "attemptedAt": f"2026-08-25T00:00:0{ordinal}.000Z",
            "completedAt": f"2026-08-25T00:00:0{ordinal}.100Z",
            "responseSha256": str(ordinal + 4) * 64,
        }
        for ordinal, kind, subject, provider_id, model_id, voice_id, language_code
        in call_specs
    ]
    proof_without_hash = {
        "schemaVersion": "mira.openmaic.formal-provider-readiness.v2",
        "providerCall": True,
        "expectedCallCount": 5,
        "attemptedCallCount": 5,
        "passedCallCount": 5,
        "calls": calls,
    }
    return {
        "success": True,
        "schemaVersion": "mira.openmaic.formal-provider-readiness-job.v2",
        "requestId": request["requestId"],
        "requestSha256": _sha(request),
        "buildItemId": request["buildItemId"],
        "releaseId": request["releaseId"],
        "gradeCode": request["gradeCode"],
        "targetFingerprint": request["targetFingerprint"],
        "runtimeClassroomId": request["runtimeClassroomId"],
        "runtimeRequestId": request["runtimeRequestId"],
        "upstreamClassroomId": request["upstreamClassroomId"],
        "classroomContentSha256": request["classroomContentSha256"],
        "audioJobTerminalReceiptSha256": request[
            "audioJobTerminalReceiptSha256"
        ],
        "validation": request["validation"],
        "routeSessionProof": request["routeSession"],
        "state": "auto_validated",
        "providerAttemptedCount": 5,
        "providerPassedCount": 5,
        "calls": calls,
        "providerProof": {
            **proof_without_hash,
            "receiptSha256": _sha(proof_without_hash),
        },
        "createdAt": "2026-08-25T00:00:00.000Z",
        "updatedAt": "2026-08-25T00:00:06.000Z",
        "completedAt": "2026-08-25T00:00:06.000Z",
        "done": True,
    }


class _Client(OpenMaicFullRuntimeClient):
    def __init__(self, response: dict):
        super().__init__(
            "http://127.0.0.1:3000",
            timeout_seconds=120,
            formal_audio_internal_token="i" * 32,
        )
        self.response = response
        self.calls = []

    def _request_json(
        self, method, path, body=None, *, extra_headers=None,
        timeout_seconds=None,
    ):
        self.calls.append(
            (method, path, body, dict(extra_headers or {}), timeout_seconds)
        )
        return deepcopy(self.response)


class FormalProviderReadinessClientTest(unittest.TestCase):
    def test_validation_scene_order_uses_the_adaptive_runtime_bound(self):
        request = _request()
        request["validation"]["sceneOrder"] = 239
        client = _Client(_response(request))

        result = client.start_formal_provider_readiness(**request)

        self.assertEqual(result["validation"]["sceneOrder"], 239)
        request["validation"]["sceneOrder"] = 240
        with self.assertRaises(OpenMaicFullRuntimeError):
            _Client(_response(request)).start_formal_provider_readiness(**request)

    def test_post_sends_exact_server_owned_evidence_and_validates_five_calls(self):
        request = _request()
        client = _Client(_response(request))

        result = client.start_formal_provider_readiness(**request)

        self.assertEqual(result["status"], "auto_validated")
        self.assertEqual(
            result["calls"][0],
            _response(request)["calls"][0],
        )
        self.assertEqual(result["calls"][0]["kind"], "deepseek_text")
        self.assertEqual(result["calls"][0]["providerId"], "deepseek")
        self.assertEqual(result["calls"][0]["modelId"], "deepseek-v4-pro")
        self.assertEqual(result["providerReceiptSha256"], _response(request)["providerProof"]["receiptSha256"])
        method, path, body, headers, timeout_seconds = client.calls[0]
        self.assertEqual((method, path), ("POST", "/api/mira/formal-provider-readiness"))
        self.assertEqual(body, request)
        self.assertTrue(
            {
                "provider",
                "model",
                "voice",
                "apiKey",
                "baseUrl",
                "fallback",
                "audioUrl",
                "base64",
            }.isdisjoint(body)
        )
        self.assertEqual(headers["X-Mira-Internal-Token"], "i" * 32)
        self.assertEqual(
            timeout_seconds,
            OpenMaicFullRuntimeClient.FORMAL_AUDIO_REQUEST_TIMEOUT_SECONDS,
        )

    def test_auto_validated_rejects_false_provider_call_or_raw_payload(self):
        request = _request()
        wrong_proof = _response(request)
        wrong_proof["providerProof"]["providerCall"] = False
        with self.assertRaises(OpenMaicFullRuntimeError):
            _Client(wrong_proof).start_formal_provider_readiness(**request)

        raw = _response(request)
        raw["transcript"] = "不允许回传原始文本"
        with self.assertRaises(OpenMaicFullRuntimeError):
            _Client(raw).start_formal_provider_readiness(**request)

    def test_get_is_observation_only_and_never_starts_a_second_provider_call(self):
        request = _request()
        client = _Client(_response(request))

        result = client.get_formal_provider_readiness(request["requestId"])

        self.assertEqual(result["status"], "auto_validated")
        self.assertEqual(
            client.calls,
            [
                (
                    "GET",
                    "/api/mira/formal-provider-readiness?requestId=provider-ready-1",
                    None,
                    client._formal_audio_headers(),
                    OpenMaicFullRuntimeClient.FORMAL_AUDIO_REQUEST_TIMEOUT_SECONDS,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
