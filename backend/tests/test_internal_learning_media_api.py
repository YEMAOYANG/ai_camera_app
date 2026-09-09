from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app import create_app
from core.config import ConfigError, validate_flask_config
from core.database import Database
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    LearningMediaMaterializationService,
    NarrationSegmentSpec,
)
from services.learning_media_worker_runner import LearningMediaWorkerRunner
from tests.support import fresh_test_config
from tests.test_learning_teacher_media_assets import ContractFakeVoxCpmProvider


class InternalLearningMediaApiTest(unittest.TestCase):
    def setUp(self):
        self.token = "internal-media-test-token"
        self.temporary = tempfile.TemporaryDirectory(prefix="mira-internal-media-")
        self.app = create_app(
            fresh_test_config(
                INTERNAL_API_TOKEN=self.token,
                LEARNING_MEDIA_STORAGE_ROOT=self.temporary.name,
            )
        )
        self.client = self.app.test_client()
        self.repository = LearningTeacherMediaRepository(
            Database(self.app.config["DATABASE_URL"])
        )
        self.media_service = LearningMediaMaterializationService(
            self.repository,
            tts_provider=ContractFakeVoxCpmProvider(),
            asset_store=FilesystemLearningMediaAssetStore(
                Path(self.temporary.name)
            ),
        )
        self.app.extensions[
            "mira_learning_media_materialization_service"
        ] = self.media_service

    def tearDown(self):
        self.temporary.cleanup()

    def test_status_materialize_and_manual_review_routes(self):
        unauthorized = self.client.get("/internal/learning/media/status")
        self.assertEqual(unauthorized.status_code, 401, unauthorized.json)
        job = self.media_service.enqueue_narration(
            idempotency_key="internal-media-pinyin",
            teacher_profile_id="mira_chinese_gentle",
            teacher_profile_version=1,
            subject="chinese",
            pronunciation_kind="pinyin",
            segments=[
                NarrationSegmentSpec(
                    text="看口形，跟我读 a。",
                    scene_id="scene-teach",
                    action_id="scene-teach:narrate",
                ),
                NarrationSegmentSpec(
                    text="嘴巴圆圆，跟我读 o。",
                    scene_id="scene-demo",
                    action_id="scene-demo:narrate",
                ),
            ],
        )
        status = self.client.get(
            "/internal/learning/media/status",
            query_string={"jobId": job["id"]},
            headers=self._headers(),
        )
        self.assertEqual(status.status_code, 200, status.json)
        self.assertTrue(status.json["availability"]["configured"])
        self.assertEqual(status.json["job"]["status"], "pending")

        materialized = self.client.post(
            "/internal/learning/media/materialize",
            json={"jobId": job["id"]},
            headers=self._headers(),
        )
        self.assertEqual(materialized.status_code, 200, materialized.json)
        self.assertEqual(materialized.json["job"]["status"], "awaiting_review")
        for segment in materialized.json["job"]["segments"]:
            reviewed = self.client.post(
                "/internal/learning/media/review",
                json={
                    "assetId": segment["assetId"],
                    "approved": True,
                    "notes": "本地测试审核",
                    "findings": {"pronunciationAccurate": True},
                },
                headers=self._headers(),
            )
            self.assertEqual(reviewed.status_code, 200, reviewed.json)
        self.assertEqual(reviewed.json["review"]["job"]["status"], "ready")

    def test_unconfigured_provider_stays_pending_and_config_rejects_enabled_worker(self):
        unconfigured = LearningMediaMaterializationService(self.repository)
        job = unconfigured.enqueue_narration(
            idempotency_key="internal-media-unconfigured",
            teacher_profile_id="mira_math_clear",
            teacher_profile_version=1,
            subject="math",
            segments=[NarrationSegmentSpec(text="先看清题目。")],
        )
        self.app.extensions[
            "mira_learning_media_materialization_service"
        ] = unconfigured
        response = self.client.post(
            "/internal/learning/media/materialize",
            json={"jobId": job["id"]},
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 503, response.json)
        self.assertEqual(response.json["error"], "tts_provider_unconfigured")
        self.assertEqual(unconfigured.get_job(job_id=job["id"])["status"], "pending")

        invalid = dict(self.app.config)
        invalid["LEARNING_MEDIA_WORKER_ENABLED"] = True
        invalid["LEARNING_VOXCPM_BASE_URL"] = ""
        with self.assertRaises(ConfigError):
            validate_flask_config(invalid)

    def test_worker_materializes_then_finalizes_package(self):
        runner = LearningMediaWorkerRunner()
        finalized: list[tuple[str, int]] = []
        result = runner.run_once(
            next_pending=lambda: {
                "id": "media_job_worker",
                "package": {"id": "lesson_pkg_worker", "version": 2},
            },
            materialize=lambda job_id: {"id": job_id, "status": "ready"},
            finalize=lambda package_id, version: (
                finalized.append((package_id, version))
                or {"status": "published"}
            ),
            checked_at_ms=1234,
        )
        self.assertEqual(finalized, [("lesson_pkg_worker", 2)])
        self.assertEqual(result["package"]["status"], "published")
        self.assertEqual(runner.status()["lastJobId"], "media_job_worker")
        self.assertEqual(runner.status()["lastCheckedAt"], 1234)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Mira-Internal-Token": self.token,
            "X-Mira-Internal-Source": "content-review-test",
        }


if __name__ == "__main__":
    unittest.main()
