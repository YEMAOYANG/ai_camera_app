from __future__ import annotations

import hashlib
import inspect
import json
import unittest

from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)
from services.learning_media_materialization_service import FormalQwenAudioService


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _formal_audio(segment_count: int = 7) -> dict:
    segments = []
    for order in range(segment_count):
        segments.append({
            "sceneOrder": order,
            "sceneId": f"scene-{order}",
            "actionId": f"speech-{order}",
            "narrationSegmentId": f"formal-narration-{order}",
            "sourceTextSha256": hashlib.sha256(
                f"source-{order}".encode()
            ).hexdigest(),
            "textSha256": hashlib.sha256(
                f"text-{order}".encode()
            ).hexdigest(),
            "tts": {
                "requestId": f"formal-tts-{order}",
                "requestSha256": hashlib.sha256(
                    f"tts-request-{order}".encode()
                ).hexdigest(),
                "state": "succeeded",
                "audioSha256": hashlib.sha256(
                    f"audio-{order}".encode()
                ).hexdigest(),
                "mimeType": "audio/wav",
                "sizeBytes": 1024 + order,
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Ethan",
                "fallbackUsed": False,
            },
            "asr": {
                "requestId": f"formal-asr-{order}",
                "requestSha256": hashlib.sha256(
                    f"asr-request-{order}".encode()
                ).hexdigest(),
                "state": "succeeded",
                "transcriptSha256": hashlib.sha256(
                    f"transcript-{order}".encode()
                ).hexdigest(),
                "normalizedTranscriptSha256": hashlib.sha256(
                    f"normalized-{order}".encode()
                ).hexdigest(),
                "similarityBps": 9000,
                "providerId": "qwen-asr",
                "modelId": "qwen3-asr-flash",
                "fallbackUsed": False,
            },
        })
    receipt = {
        "schemaVersion": "mira.openmaic.formal-audio-lifecycle.v2",
        "status": "succeeded",
        "buildItemId": "build-item-1",
        "classroomId": "formal-classroom-1",
        "classroomContentSha256": "1" * 64,
        "subject": "math",
        "speechTextPolicyVersion": "mira.learning.formal-speech-text.v2",
        "teacherProfile": {
            "id": "mira-math-clear",
            "version": 2,
            "sha256": "2" * 64,
            "gender": "male",
        },
        "expectedSegmentCount": segment_count,
        "ttsSucceededCount": segment_count,
        "asrPassedCount": segment_count,
        "segments": segments,
    }
    receipt["receiptSha256"] = _canonical_sha256(receipt)
    return receipt


def _job_payload(formal_audio: object = None, *, scenes_count: int = 7) -> dict:
    result = {
        "classroomId": "formal-classroom-1",
        "scenesCount": scenes_count,
        "speechActionCount": (
            int(formal_audio.get("expectedSegmentCount"))
            if isinstance(formal_audio, dict)
            else scenes_count
        ),
    }
    if formal_audio is not None:
        result["formalAudio"] = formal_audio
    return {
        "success": True,
        "jobId": "formal-job-1",
        "status": "succeeded",
        "step": "completed",
        "progress": 100,
        "done": True,
        "runtimeRequestId": "formal-runtime-1",
        "formalContractVersion": "mira.openmaic.formal-runtime.v1",
        "formalInputSha256": "3" * 64,
        "result": result,
    }


class OpenMaicFormalAudioV2ClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100")

    def test_parses_adaptive_segment_lifecycle_receipt(self) -> None:
        receipt = self.client._formal_audio_receipt_from_payload(
            _formal_audio(),
            classroom_id="formal-classroom-1",
            expected_segment_count=7,
        )

        self.assertEqual(receipt.build_item_id, "build-item-1")
        self.assertEqual(receipt.subject, "math")
        self.assertEqual(receipt.expected_segment_count, 7)
        self.assertEqual(len(receipt.segments), 7)
        self.assertEqual(receipt.segments[0].tts.voice_id, "Ethan")
        self.assertEqual(receipt.segments[6].asr.similarity_bps, 9000)

    def test_rejects_extra_fields_even_with_rehashed_receipt(self) -> None:
        receipt = _formal_audio()
        receipt["providerPayload"] = {"secret": "must-not-cross"}
        receipt.pop("receiptSha256")
        receipt["receiptSha256"] = _canonical_sha256(receipt)

        with self.assertRaises(OpenMaicFullRuntimeError) as raised:
            self.client._formal_audio_receipt_from_payload(
                receipt,
                classroom_id="formal-classroom-1",
                expected_segment_count=7,
            )

        self.assertEqual(
            raised.exception.code, "invalid_openmaic_formal_audio_receipt"
        )

    def test_rejects_tampered_receipt_hash_and_weak_asr(self) -> None:
        tampered = _formal_audio()
        tampered["segments"][0]["tts"]["audioSha256"] = "f" * 64
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.client._formal_audio_receipt_from_payload(
                tampered,
                classroom_id="formal-classroom-1",
                expected_segment_count=7,
            )

        weak = _formal_audio()
        weak["segments"][0]["asr"]["similarityBps"] = 8499
        weak.pop("receiptSha256")
        weak["receiptSha256"] = _canonical_sha256(weak)
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.client._formal_audio_receipt_from_payload(
                weak,
                classroom_id="formal-classroom-1",
                expected_segment_count=7,
            )

    def test_rejects_receipt_count_that_differs_from_speech_action_count(self) -> None:
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.client._formal_audio_receipt_from_payload(
                _formal_audio(),
                classroom_id="formal-classroom-1",
                expected_segment_count=8,
            )

    def test_receipt_allows_multiple_segments_for_one_scene(self) -> None:
        raw = _formal_audio()
        raw["segments"][1]["sceneId"] = raw["segments"][0]["sceneId"]
        raw.pop("receiptSha256")
        raw["receiptSha256"] = _canonical_sha256(raw)

        receipt = self.client._formal_audio_receipt_from_payload(
            raw,
            classroom_id="formal-classroom-1",
            expected_segment_count=7,
        )

        self.assertEqual(receipt.segments[0].scene_id, receipt.segments[1].scene_id)

    def test_legacy_succeeded_job_without_v2_receipt_remains_observable(self) -> None:
        job = self.client._job_from_payload(_job_payload())
        self.assertIsNone(job.formal_audio)

    def test_rejects_formal_audio_on_non_terminal_job(self) -> None:
        payload = _job_payload(_formal_audio())
        payload.update(status="running", done=False, progress=90)
        with self.assertRaises(OpenMaicFullRuntimeError):
            self.client._job_from_payload(payload)

    def test_production_importer_has_no_tts_or_asr_post_dispatch(self) -> None:
        source = inspect.getsource(FormalQwenAudioService)
        self.assertNotIn("start_formal_audio_tts", source)
        self.assertNotIn("start_formal_audio_asr", source)
        self.assertIn("get_generation_job_by_request_id", source)
        self.assertIn("download_formal_audio_tts", source)


if __name__ == "__main__":
    unittest.main()
