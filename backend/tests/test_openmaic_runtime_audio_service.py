from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from core.errors import ApiError
from core.security import now_ms
from services.openmaic_runtime_audio_service import OpenMaicRuntimeAudioService


class _AudioRepository:
    def __init__(self, rows):
        self.rows = rows

    @contextmanager
    def transaction(self):
        yield object()

    def list_runtime_audio_assets(self, _conn, **_identity):
        return self.rows

    @staticmethod
    def decode_json(value, fallback):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback


class OpenMaicRuntimeAudioServiceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="mira-runtime-audio-"
        )
        self.root = Path(self.temporary.name)
        self.rows = self._rows()
        self.repository = _AudioRepository(self.rows)
        self.service = OpenMaicRuntimeAudioService(
            "unused",
            storage_root=self.root,
            repository=self.repository,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_manifest_and_exact_asset_authorization_verify_real_bytes(self):
        manifest = self.service.manifest(**self._identity())
        self.assertEqual(manifest["speechActionCount"], 10)
        self.assertEqual(manifest["classroomContentSha256"], "c" * 64)
        self.assertEqual(len(manifest["assets"]), 10)
        first = manifest["assets"][0]
        self.assertEqual(first["audioId"], "formal-audio-0")
        self.assertEqual(
            first["deliveryPath"],
            "/mira/runtime-audio/formal-audio-0",
        )
        self.assertEqual(
            first["audioMetadata"],
            {
                "schemaVersion": "mira.openmaic.speech-audio.v1",
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Ethan",
                "fallbackUsed": False,
            },
        )
        serialized = json.dumps(manifest)
        self.assertNotIn("storageKey", serialized)
        self.assertNotIn("internal", serialized)

        asset = self.service.authorize_asset(
            **self._identity(), asset_id="formal-audio-0"
        )
        self.assertTrue(asset.path.is_file())
        self.assertEqual(asset.mime_type, "audio/wav")
        self.assertEqual(asset.byte_size, 64)

    def test_manifest_uses_the_classroom_scene_count(self):
        self.rows = self._rows(count=7)
        self.repository.rows = self.rows

        manifest = self.service.manifest(**self._identity())

        self.assertEqual(manifest["speechActionCount"], 7)
        self.assertEqual(len(manifest["assets"]), 7)

    def test_manifest_allows_multiple_speech_assets_for_one_scene(self):
        self.rows = self._rows(count=12, scene_count=7)
        self.repository.rows = self.rows

        manifest = self.service.manifest(**self._identity())

        self.assertEqual(manifest["speechActionCount"], 12)
        self.assertEqual(len(manifest["assets"]), 12)
        self.assertLess(
            len({asset["sceneId"] for asset in manifest["assets"]}),
            len(manifest["assets"]),
        )

    def test_missing_segment_mime_regression_and_unknown_asset_fail_closed(self):
        self.repository.rows = self.rows[:9]
        with self.assertRaises(ApiError) as missing:
            self.service.manifest(**self._identity())
        self.assertEqual(missing.exception.code, "openmaic_runtime_audio_unavailable")

        self.repository.rows = self.rows
        self.rows[0]["variant_mime_type"] = "text/plain"
        with self.assertRaises(ApiError) as wrong_type:
            self.service.manifest(**self._identity())
        self.assertEqual(
            wrong_type.exception.code,
            "openmaic_runtime_audio_integrity_failed",
        )
        self.rows[0]["variant_mime_type"] = "audio/wav"

        with self.assertRaises(ApiError) as unknown:
            self.service.authorize_asset(
                **self._identity(), asset_id="formal-audio-other"
            )
        self.assertEqual(unknown.exception.status_code, 404)

    def test_hash_tamper_and_storage_escape_fail_closed(self):
        path = self.root / self.rows[0]["storage_key"]
        data = bytearray(path.read_bytes())
        data[-1] ^= 0x01
        path.write_bytes(data)
        with self.assertRaises(ApiError) as tampered:
            self.service.authorize_asset(
                **self._identity(), asset_id="formal-audio-0"
            )
        self.assertEqual(
            tampered.exception.code,
            "openmaic_runtime_audio_integrity_failed",
        )

        self.repository.rows = self._rows()
        self.repository.rows[0]["storage_key"] = "../secret.wav"
        self.repository.rows[0]["asset_storage_key"] = "../secret.wav"
        self.repository.rows[0]["variant_storage_key"] = "../secret.wav"
        with self.assertRaises(ApiError) as escaped:
            self.service.authorize_asset(
                **self._identity(), asset_id="formal-audio-0"
            )
        self.assertIn(
            escaped.exception.code,
            {
                "openmaic_runtime_audio_integrity_failed",
                "openmaic_runtime_audio_storage_missing",
            },
        )

    def test_manifest_never_exports_a_drifted_classroom_content_hash(self):
        self.rows[0]["classroom_content_sha256"] = "f" * 64
        with self.assertRaises(ApiError) as drifted:
            self.service.manifest(**self._identity())
        self.assertEqual(
            drifted.exception.code,
            "openmaic_runtime_audio_unavailable",
        )

    @staticmethod
    def _identity():
        return {
            "runtime_session_id": "runtime-session-a",
            "learning_session_id": "learning-session-a",
            "upstream_classroom_id": "classroom-a",
        }

    def _rows(self, *, count=10, scene_count=None):
        scene_count = count if scene_count is None else scene_count
        classroom_hash = "c" * 64
        rows = []
        for index in range(count):
            audio = bytearray(64)
            audio[0:4] = b"RIFF"
            audio[4:8] = (56).to_bytes(4, "little")
            audio[8:12] = b"WAVE"
            audio[-1] = index
            storage_key = f"narration/formal-audio-{index}.wav"
            path = self.root / storage_key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
            digest = hashlib.sha256(audio).hexdigest()
            rows.append(
                {
                    "runtime_session_id": "runtime-session-a",
                    "learning_session_id": "learning-session-a",
                    "runtime_session_expires_at": now_ms() + 60_000,
                    "runtime_session_revoked_at": None,
                    "runtime_classroom_id": "runtime-classroom-a",
                    "upstream_classroom_id": "classroom-a",
                    "runtime_status": "ready",
                    "runtime_quality_status": "pending_review",
                    "runtime_retired_at": None,
                    "feature_manifest_json": json.dumps(
                        {
                            "classroomContentSha256": classroom_hash,
                            "sceneCount": scene_count,
                            "formalEvidence": {"speechActionCount": count},
                        }
                    ),
                    "candidate_binding_contract_version": (
                        "mira.learning.candidate-runtime-binding.v1"
                    ),
                    "runtime_binding_contract_version": (
                        "mira.learning.candidate-runtime-binding.v1"
                    ),
                    "build_item_id": "build-a",
                    "audio_job_state": "auto_validated",
                    "classroom_content_sha256": classroom_hash,
                    "audio_contract_version": (
                        "mira.learning.formal-qwen-audio.v1"
                    ),
                    "expected_segment_count": count,
                    "tts_attempted_count": count,
                    "tts_completed_count": count,
                    "audio_validated_count": count,
                    "asr_attempted_count": count,
                    "asr_passed_count": count,
                    "tts_provider_id": "qwen-tts",
                    "tts_model_id": "qwen3-tts-flash",
                    "tts_voice_id": "Ethan",
                    "tts_fallback_allowed": 0,
                    "terminal_receipt_hash": "d" * 64,
                    "scene_order": index,
                    "scene_id": f"scene-{index % scene_count}",
                    "action_id": f"speech-{index}",
                    "segment_state": "auto_validated",
                    "runtime_audio_sha256": digest,
                    "download_sha256": digest,
                    "streamed_sha256": digest,
                    "readback_sha256": digest,
                    "storage_key": storage_key,
                    "asset_id": f"formal-audio-{index}",
                    "segment_mime_type": "audio/wav",
                    "segment_byte_size": len(audio),
                    "segment_duration_ms": 1_000,
                    "pcm_format": 1,
                    "channel_count": 1,
                    "bits_per_sample": 16,
                    "sample_rate_hz": 24_000,
                    "block_align": 2,
                    "safe_error_code": None,
                    "machine_receipt_hash": "e" * 64,
                    "asset_kind": "audio",
                    "asset_storage_key": storage_key,
                    "asset_content_hash": digest,
                    "asset_mime_type": "audio/wav",
                    "asset_byte_size": len(audio),
                    "asset_duration_ms": 1_000,
                    "asset_scan_status": "passed",
                    "asset_moderation_status": "passed",
                    "asset_transcode_status": "not_required",
                    "asset_status": "ready",
                    "variant_key": "original",
                    "variant_storage_key": storage_key,
                    "variant_content_hash": digest,
                    "variant_mime_type": "audio/wav",
                    "variant_byte_size": len(audio),
                    "variant_duration_ms": 1_000,
                    "variant_status": "ready",
                }
            )
        return rows


if __name__ == "__main__":
    unittest.main()
