from __future__ import annotations

import copy
import hashlib
import tempfile
from types import SimpleNamespace

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from integrations.openmaic_full_runtime_client import (
    OpenMaicFormalAudioAsrReceipt,
    OpenMaicFormalAudioReceipt,
    OpenMaicFormalAudioSegmentReceipt,
    OpenMaicFormalAudioTtsReceipt,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    FormalQwenAudioService,
    build_formal_speech_manifest,
)
from tests.test_formal_qwen_audio_repository import (
    FormalQwenAudioRepositoryTest,
    _classroom,
)
from tests.test_formal_qwen_audio_validation import _wav


class _Clock:
    def __init__(self) -> None:
        self.value = 5_000

    def __call__(self) -> int:
        self.value += 1
        return self.value


class _Runtime:
    def __init__(
        self,
        *,
        build_item_id: str,
        upstream_classroom_id: str,
        missing_receipt: bool = False,
    ) -> None:
        self.audio = _wav()
        self.audio_sha256 = hashlib.sha256(self.audio).hexdigest()
        self.download_calls: list[str] = []
        self.classroom = _classroom()
        self.upstream_classroom_id = upstream_classroom_id
        self.formal_audio = None if missing_receipt else self._receipt(build_item_id)

    def get_classroom(self, _classroom_id: str) -> dict:
        return copy.deepcopy(self.classroom)

    def get_generation_job_by_request_id(self, _request_id: str):
        return SimpleNamespace(
            status="succeeded",
            classroom_id=self.upstream_classroom_id,
            formal_audio=self.formal_audio,
        )

    def download_formal_audio_tts(
        self, request_id: str, *, expected_sha256: str
    ) -> bytes:
        assert expected_sha256 == self.audio_sha256
        self.download_calls.append(request_id)
        return self.audio

    def start_formal_audio_tts(self, **_payload):
        raise AssertionError("backend must not dispatch formal TTS")

    def start_formal_audio_asr(self, **_payload):
        raise AssertionError("backend must not dispatch formal ASR")

    def _receipt(self, build_item_id: str) -> OpenMaicFormalAudioReceipt:
        voice = get_formal_subject_qwen_voice_identity("chinese")
        manifest = build_formal_speech_manifest(
            self.classroom,
            build_item_id=build_item_id,
            voice=voice,
        )
        job = {
            "upstream_classroom_id": self.upstream_classroom_id,
            "classroom_content_sha256": manifest["classroomContentSha256"],
            "subject": "chinese",
            "teacher_profile_id": voice.teacher_profile_id,
            "teacher_profile_version": voice.teacher_profile_version,
            "teacher_profile_hash": voice.teacher_profile_hash,
            "teacher_gender": voice.teacher_gender,
        }
        receipts = []
        for segment in manifest["segments"]:
            tts_payload = FormalQwenAudioService._tts_payload(job, segment)
            asr_payload = FormalQwenAudioService._asr_payload(
                job,
                segment,
                audio_sha256=self.audio_sha256,
            )
            text = str(segment["text"])
            transcript_sha256 = hashlib.sha256(text.encode()).hexdigest()
            receipts.append(OpenMaicFormalAudioSegmentReceipt(
                scene_order=int(segment["sceneOrder"]),
                scene_id=str(segment["sceneId"]),
                action_id=str(segment["actionId"]),
                narration_segment_id=str(segment["narrationSegmentId"]),
                source_text_sha256=str(segment["sourceTextSha256"]),
                text_sha256=str(segment["textSha256"]),
                tts=OpenMaicFormalAudioTtsReceipt(
                    request_id=str(segment["ttsRequestId"]),
                    request_sha256=FormalQwenAudioService._hash_payload(
                        tts_payload
                    ),
                    audio_sha256=self.audio_sha256,
                    size_bytes=len(self.audio),
                    voice_id=voice.voice_id,
                ),
                asr=OpenMaicFormalAudioAsrReceipt(
                    request_id=str(segment["asrRequestId"]),
                    request_sha256=FormalQwenAudioService._hash_payload(
                        asr_payload
                    ),
                    transcript_sha256=transcript_sha256,
                    normalized_transcript_sha256=transcript_sha256,
                    similarity_bps=10_000,
                ),
            ))
        return OpenMaicFormalAudioReceipt(
            schema_version="mira.openmaic.formal-audio-lifecycle.v2",
            build_item_id=build_item_id,
            classroom_id=self.upstream_classroom_id,
            classroom_content_sha256=str(manifest["classroomContentSha256"]),
            subject="chinese",
            speech_text_policy_version="mira.learning.formal-speech-text.v2",
            teacher_profile_id=voice.teacher_profile_id,
            teacher_profile_version=voice.teacher_profile_version,
            teacher_profile_sha256=voice.teacher_profile_hash,
            teacher_gender=voice.teacher_gender,
            expected_segment_count=len(receipts),
            tts_succeeded_count=len(receipts),
            asr_passed_count=len(receipts),
            segments=tuple(receipts),
            receipt_sha256="9" * 64,
        )


class FormalQwenAudioServiceTest(FormalQwenAudioRepositoryTest):
    def test_worker_imports_exact_ten_openmaic_wavs_without_provider_posts(self) -> None:
        fixture, repository, _voice, _manifest = self._prepare_audio_authority(
            "audio-service-success"
        )
        runtime = _Runtime(
            build_item_id=str(fixture["item_id"]),
            upstream_classroom_id="upstream-audio-service-success-1",
        )
        with tempfile.TemporaryDirectory() as root:
            service = FormalQwenAudioService(
                repository,
                runtime_client=runtime,
                asset_store=FilesystemLearningMediaAssetStore(root),
                clock=_Clock(),
            )
            result = service.process_next()

        self.assertEqual(result["state"], "auto_validated", result)
        self.assertEqual(result["ttsCompletedCount"], 10)
        self.assertEqual(result["audioValidatedCount"], 10)
        self.assertEqual(result["asrPassedCount"], 10)
        self.assertEqual(len(runtime.download_calls), 10)
        with self.database.transaction() as conn:
            receipt = self.catalog.get_classroom_item_receipt(
                conn, build_item_id=str(fixture["item_id"])
            )
        self.assertEqual(receipt["tts_status"], "passed")
        self.assertEqual(receipt["asr_roundtrip_status"], "passed")
        self.assertEqual(receipt["conversation_provider_status"], "pending")
        self.assertEqual(receipt["auto_validated"], 0)
        self.assertEqual(receipt["approved"], 0)

    def test_missing_v2_receipt_fails_without_provider_dispatch(self) -> None:
        fixture, repository, _voice, _manifest = self._prepare_audio_authority(
            "audio-service-lost-asr"
        )
        runtime = _Runtime(
            build_item_id=str(fixture["item_id"]),
            upstream_classroom_id="upstream-audio-service-lost-asr-1",
            missing_receipt=True,
        )
        with tempfile.TemporaryDirectory() as root:
            service = FormalQwenAudioService(
                repository,
                runtime_client=runtime,
                asset_store=FilesystemLearningMediaAssetStore(root),
                clock=_Clock(),
            )
            first = service.process_next()
            second = service.process_next()

        self.assertEqual(first["state"], "failed")
        self.assertIsNone(second)
        self.assertEqual(runtime.download_calls, [])
        with self.database.transaction() as conn:
            job = repository.get_formal_audio_job(
                conn, build_item_id=str(fixture["item_id"])
            )
            segment = repository.get_formal_audio_segment(
                conn, build_item_id=str(fixture["item_id"]), scene_order=0
            )
            receipt = self.catalog.get_classroom_item_receipt(
                conn, build_item_id=str(fixture["item_id"])
            )
        self.assertEqual(job["state"], "failed")
        self.assertEqual(segment["state"], "failed")
        self.assertIsNone(segment["asr_result_sha256"])
        self.assertIsNone(segment["normalized_transcript_sha256"])
        self.assertEqual(receipt["tts_status"], "failed")
        self.assertEqual(receipt["asr_roundtrip_status"], "failed")


if __name__ == "__main__":
    import unittest
    unittest.main()
