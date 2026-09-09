from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest
import wave

from core.database import Database
from repositories.learning_teacher_media_repository import LearningTeacherMediaRepository
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    LearningMediaMaterializationError,
    LearningMediaMaterializationService,
    NarrationSegmentSpec,
)
from services.learning_teacher_library_service import LearningTeacherLibraryService
from services.tts_provider import TtsSynthesisResult
from tests.support import fresh_test_config


def fixture_wav() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x01\x00" * 800)
    return output.getvalue()


class ContractFakeVoxCpmProvider:
    """Test-only contract double. It is never wired into application code."""

    provider_id = "voxcpm2"
    model_name = "openbmb/VoxCPM2"

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.requests = []

    def synthesize(self, request):
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("test provider unavailable")
        return TtsSynthesisResult(
            audio=fixture_wav(),
            mime_type="audio/wav",
            provider_id=self.provider_id,
            model=self.model_name,
            duration_ms=100,
        )


class ContractFakeMacOsSayProvider(ContractFakeVoxCpmProvider):
    provider_id = "macos-say"
    model_name = "apple/macos-system-speech"


class LearningTeacherMediaAssetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = fresh_test_config()
        cls.database = Database(config["DATABASE_URL"])
        cls.repository = LearningTeacherMediaRepository(cls.database)
        cls.temporary = tempfile.TemporaryDirectory(prefix="mira-media-test-")
        cls.store = FilesystemLearningMediaAssetStore(Path(cls.temporary.name))
        with cls.database.transaction() as conn:
            conn.execute(
                "INSERT INTO families(id, name, created_at) VALUES ('family_media', 'Media', 1)"
            )
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, created_at, updated_at
                ) VALUES ('child_media', 'family_media', '乐乐', 1, 1)
                """
            )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def service(self, *, fail: bool = False):
        provider = ContractFakeVoxCpmProvider(fail=fail)
        return (
            LearningMediaMaterializationService(
                self.repository,
                tts_provider=provider,
                asset_store=self.store,
            ),
            provider,
        )

    def test_teacher_preference_is_versioned_and_public_profile_is_safe(self):
        library = LearningTeacherLibraryService(self.repository)
        catalog = library.list_teachers(
            subject="chinese",
            family_id="family_media",
            child_id="child_media",
        )
        self.assertEqual(len(catalog["items"]), 1)
        self.assertIsNone(catalog["selected"])
        selected = library.set_teacher_preference(
            family_id="family_media",
            child_id="child_media",
            subject="chinese",
            teacher_profile_id="mira_chinese_gentle",
            updated_by_user_id="user_content_ops",
        )
        self.assertEqual(selected["teacher"]["version"], 2)
        self.assertNotIn("voicePrompt", selected["teacher"])
        refreshed = library.list_teachers(
            subject="chinese",
            family_id="family_media",
            child_id="child_media",
        )
        self.assertEqual(refreshed["selected"], {"id": "mira_chinese_gentle", "version": 2})

    def test_idempotency_replays_identical_job_and_rejects_changed_request(self):
        service, _ = self.service()
        kwargs = {
            "idempotency_key": "media-idempotency-1",
            "teacher_profile_id": "mira_math_clear",
            "teacher_profile_version": 1,
            "subject": "math",
            "segments": [NarrationSegmentSpec(text="先看十位，再看个位。")],
        }
        first = service.enqueue_narration(**kwargs)
        second = service.enqueue_narration(**kwargs)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertEqual(first["id"], second["id"])
        with self.assertRaises(LearningMediaMaterializationError) as conflict:
            service.enqueue_narration(
                **{**kwargs, "segments": [NarrationSegmentSpec(text="请求内容发生改变。")]}
            )
        self.assertEqual(conflict.exception.code, "idempotency_conflict")

    def test_english_audio_is_hidden_until_manual_pronunciation_review(self):
        service, provider = self.service()
        job = service.enqueue_narration(
            idempotency_key="media-english-gate",
            teacher_profile_id="mira_english_standard",
            teacher_profile_version=1,
            subject="english",
            pronunciation_kind="english",
            package_id="package_media_english",
            package_version=1,
            segments=[
                NarrationSegmentSpec(
                    text="Listen and repeat: apple.",
                    subtitle="Listen and repeat: apple.",
                    scene_id="scene_intro",
                    action_id="narrate_intro",
                )
            ],
        )
        materialized = service.materialize_job(job_id=job["id"])
        self.assertEqual(materialized["status"], "awaiting_review")
        self.assertEqual(materialized["segments"][0]["status"], "awaiting_review")
        self.assertEqual(len(provider.requests), 1)
        library = LearningTeacherLibraryService(self.repository)
        hidden = library.list_ready_assets(
            package_id="package_media_english",
            package_version=1,
        )
        self.assertEqual(hidden["items"], [])

        reviewed = service.review_pronunciation_asset(
            asset_id=materialized["segments"][0]["assetId"],
            approved=True,
            reviewer_type="content_reviewer",
            reviewer_id="reviewer_1",
            findings={"word": "apple", "pronunciationAccurate": True},
        )
        self.assertEqual(reviewed["status"], "ready")
        with self.database.transaction() as conn:
            review = conn.execute(
                """
                SELECT findings_json FROM learning_media_quality_reviews
                WHERE asset_id = ? AND review_kind = 'manual_pronunciation'
                LIMIT 1
                """,
                (materialized["segments"][0]["assetId"],),
            ).fetchone()
        findings = self.repository.decode_json(review["findings_json"], {})
        self.assertTrue(findings["checksumVerified"])
        self.assertTrue(findings["manualPronunciationApproved"])
        visible = library.list_ready_assets(
            package_id="package_media_english",
            package_version=1,
        )
        self.assertEqual(len(visible["items"]), 1)
        self.assertIsNone(visible["items"][0]["variants"][0]["deliveryUrl"])
        self.assertEqual(len(visible["items"][0]["checksum"]), 64)

    def test_pinyin_forces_manual_review_and_failed_provider_never_creates_asset(self):
        pinyin_service, _ = self.service()
        pinyin = pinyin_service.enqueue_narration(
            idempotency_key="media-pinyin-gate",
            teacher_profile_id="mira_chinese_gentle",
            teacher_profile_version=1,
            subject="chinese",
            pronunciation_kind="pinyin",
            segments=[NarrationSegmentSpec(text="看口形，跟我读：a。")],
        )
        result = pinyin_service.materialize_job(job_id=pinyin["id"])
        self.assertTrue(result["requiresManualReview"])
        self.assertEqual(result["segments"][0]["status"], "awaiting_review")

        failing_service, _ = self.service(fail=True)
        failed = failing_service.enqueue_narration(
            idempotency_key="media-provider-failure",
            teacher_profile_id="mira_math_clear",
            teacher_profile_version=1,
            subject="math",
            segments=[NarrationSegmentSpec(text="从十位开始比较。")],
        )
        with self.assertRaises(LearningMediaMaterializationError):
            failing_service.materialize_job(job_id=failed["id"])
        persisted = failing_service.get_job(job_id=failed["id"])
        self.assertEqual(persisted["status"], "failed")
        self.assertIsNone(persisted["segments"][0]["assetId"])

    def test_macos_provider_is_honestly_bound_and_math_uses_integrity_review(self):
        provider = ContractFakeMacOsSayProvider()
        service = LearningMediaMaterializationService(
            self.repository,
            tts_provider=provider,
            asset_store=self.store,
        )
        job = service.enqueue_narration(
            idempotency_key="media-macos-math-binding",
            teacher_profile_id="mira_math_clear",
            teacher_profile_version=1,
            subject="math",
            pronunciation_kind="general",
            segments=[NarrationSegmentSpec(text="一加一等于二。")],
        )
        self.assertEqual(job["teacherProfile"], {"id": "mira_math_clear", "version": 1})
        with self.database.transaction() as conn:
            stored = conn.execute(
                """
                SELECT provider_id, provider_model
                FROM learning_media_generation_jobs WHERE id = ?
                """,
                (job["id"],),
            ).fetchone()
        self.assertEqual(stored["provider_id"], "macos-say")
        self.assertEqual(stored["provider_model"], "apple/macos-system-speech")

        materialized = service.materialize_job(job_id=job["id"])
        self.assertEqual(materialized["status"], "ready")
        self.assertFalse(materialized["requiresManualReview"])
        with self.database.transaction() as conn:
            review = conn.execute(
                """
                SELECT review_kind, status, reviewer_type
                FROM learning_media_quality_reviews
                WHERE asset_id = ? LIMIT 1
                """,
                (materialized["segments"][0]["assetId"],),
            ).fetchone()
        self.assertEqual(review["review_kind"], "automated_integrity")
        self.assertEqual(review["status"], "approved")
        self.assertEqual(review["reviewer_type"], "system")


if __name__ == "__main__":
    unittest.main()
