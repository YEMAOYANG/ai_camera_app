from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.database import Database
from repositories.care_repository import CareRepository
from services.camera_observe_service import CameraObserveService
from services.observation_runtime_state import ObservationRuntimeStateStore
from tests.support import TEST_DATABASE_URL, reset_mysql_test_database


class _AbsentVision:
    def analyze_snapshot(self, **kwargs):
        return {
            "has_person": False,
            "activity": "离开",
            "confidence": 0.92,
            "description": "客厅暂时没有看到孩子。",
            "method": "guardian_test",
        }


class CameraObserveRuntimePersistenceTest(unittest.TestCase):
    def setUp(self):
        reset_mysql_test_database()
        self.database_url = TEST_DATABASE_URL
        self.repository = CareRepository(Database(self.database_url))
        self.runtime_store = ObservationRuntimeStateStore(self.repository)
        self.service = CameraObserveService(
            self.database_url,
            vision_service=_AbsentVision(),
        )
        self.family_id = "fam_runtime_test"
        self.child_id = "child_runtime_test"
        self.device_id = "dev_runtime_test"
        self.image_bytes = _tiny_png()

    def _load_absence(self) -> dict:
        with self.repository.transaction() as conn:
            runtime = self.runtime_store.load(
                conn,
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=self.device_id,
            )
        return dict(runtime.get("absence") or {})

    def test_absence_runtime_persisted_after_first_record(self):
        posts: list[dict] = []

        def post(payload: dict) -> dict:
            posts.append(payload)
            return {"ok": True}

        env = {
            "APP_ABSENCE_CONFIRM_TICKS": "1",
            "APP_ABSENCE_CHECK_INTERVAL_SECONDS": "300",
        }
        with patch.dict(os.environ, env, clear=False):
            first = self.service.run_tick(
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=self.device_id,
                image_bytes=self.image_bytes,
                post_observation=post,
            )
            second = self.service.run_tick(
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=self.device_id,
                image_bytes=self.image_bytes,
                post_observation=post,
            )

        self.assertTrue(first.posted)
        self.assertFalse(second.posted)
        self.assertIn(
            second.skip_reason,
            {"absent_already_recorded", "absence_stable_skip"},
        )
        self.assertEqual(len(posts), 1)

        absence = self._load_absence()
        self.assertEqual(absence.get("mode"), "absence")
        self.assertTrue(absence.get("recorded_absent"))

    def test_absence_stable_skip_after_recorded(self):
        posts: list[dict] = []

        def post(payload: dict) -> dict:
            posts.append(payload)
            return {"ok": True}

        env = {
            "APP_ABSENCE_CONFIRM_TICKS": "1",
            "APP_ABSENCE_CHECK_INTERVAL_SECONDS": "300",
        }
        with patch.dict(os.environ, env, clear=False):
            self.service.run_tick(
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=self.device_id,
                image_bytes=self.image_bytes,
                post_observation=post,
            )
            skipped = self.service.run_tick(
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=self.device_id,
                image_bytes=self.image_bytes,
                post_observation=post,
            )

        self.assertTrue(skipped.skipped)
        self.assertIn(skipped.skip_reason, {"absent_already_recorded", "absence_stable_skip"})
        self.assertEqual(len(posts), 1)


def _tiny_png() -> bytes:
    from PIL import Image
    import io

    image = Image.new("RGB", (32, 32), color=(120, 140, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
