from __future__ import annotations

import unittest

from integrations.camera_runtime.ai_camera_test_observation_adapter import (
    AiCameraTestObservationAdapter,
    AiCameraTestObservationConfig,
    ObservationAdapterConfigError,
    build_source_event_id,
)
from workers.camera_observation_worker import CameraObservationWorker, build_worker_from_env


class AiCameraTestObservationAdapterTest(unittest.TestCase):
    def test_payload_mapping_ignores_old_reminder_text(self):
        adapter = AiCameraTestObservationAdapter(_config(), json_request=_unused_request)

        payloads = adapter.payloads_from_analysis(
            {
                "has_person": True,
                "activity": "走动",
                "toys_visible": True,
                "toys_scattered": True,
                "confidence": 0.86,
                "description": "玩具还在地上，孩子已经离开玩具区。",
                "child_message": "旧项目里的播报文案不能迁移。",
                "reminder": "旧项目里的提醒不能迁移。",
                "decision_reason": "旧项目内置提醒原因只作为内部证据。",
                "method": "vision-test",
            },
            window_start_ms=1_000,
            window_end_ms=6_000,
            observed_at=6_000,
        )

        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["scenario"], "toy_cleanup")
        self.assertEqual(payload["source"], "ai_camera_test")
        self.assertEqual(payload["sourceEventId"], "ai_camera_test:dev_1:toy_cleanup:1000:6000:toys_scattered")
        self.assertEqual(payload["signals"][0]["durationSeconds"], 5)
        self.assertEqual(payload["signals"][0]["signalType"], "toys_scattered")
        self.assertNotIn("reminder", payload["rawDetail"])
        self.assertNotIn("child_message", payload["rawDetail"])

    def test_source_event_id_is_stable(self):
        first = build_source_event_id(
            device_id="dev_1",
            scenario="posture",
            window_start_ms=10,
            window_end_ms=20,
            signal_type="leaning_too_close",
        )
        second = build_source_event_id(
            device_id="dev_1",
            scenario="posture",
            window_start_ms=10,
            window_end_ms=20,
            signal_type="leaning_too_close",
        )

        self.assertEqual(first, second)
        self.assertEqual(first, "ai_camera_test:dev_1:posture:10:20:leaning_too_close")

    def test_worker_posts_only_observation_endpoint(self):
        calls = []

        def fake_request(url, payload, headers, timeout):
            calls.append((url, payload, headers, timeout))
            if url.endswith("/api/camera/snapshot?format=data_url"):
                return {"image": "data:image/jpeg;base64,abc"}
            if url.endswith("/api/analyze_frame"):
                self.assertEqual(payload["image"], "data:image/jpeg;base64,abc")
                return {
                    "has_person": True,
                    "activity": "吃饭",
                    "confidence": 0.9,
                    "description": "孩子坐在餐桌前吃饭。",
                    "method": "vision-test",
                }
            self.assertEqual(url, "http://current.local/internal/camera/observations")
            self.assertEqual(headers["X-Mira-Internal-Token"], "token")
            self.assertEqual(headers["X-Mira-Internal-Source"], "ai_camera_test")
            return {"ok": True}

        adapter = AiCameraTestObservationAdapter(_config(), json_request=fake_request)
        result = CameraObservationWorker(adapter).run_once(
            window_start_ms=10_000,
            window_end_ms=15_000,
        )

        self.assertEqual(result.posted_count, 1)
        called_urls = [item[0] for item in calls]
        self.assertTrue(all("/internal/reminders/trigger" not in url for url in called_urls))
        self.assertTrue(all("speaker" not in url for url in called_urls))
        self.assertIn("http://current.local/internal/camera/observations", called_urls)

    def test_missing_required_worker_config_fails_fast(self):
        base_env = {
            "AI_CAMERA_TEST_BASE_URL": "http://old.local",
            "CAMERA_OBSERVATION_INTERNAL_URL": "http://current.local/internal/camera/observations",
            "INTERNAL_API_TOKEN": "token",
            "CAMERA_OBSERVATION_FAMILY_ID": "fam_1",
            "CAMERA_OBSERVATION_CHILD_ID": "child_1",
            "CAMERA_OBSERVATION_DEVICE_ID": "dev_1",
        }
        for key in (
            "INTERNAL_API_TOKEN",
            "CAMERA_OBSERVATION_FAMILY_ID",
            "CAMERA_OBSERVATION_CHILD_ID",
            "CAMERA_OBSERVATION_DEVICE_ID",
        ):
            env = dict(base_env)
            env[key] = ""
            with self.subTest(key=key):
                with self.assertRaises(ObservationAdapterConfigError):
                    build_worker_from_env(env)


def _config() -> AiCameraTestObservationConfig:
    return AiCameraTestObservationConfig(
        base_url="http://old.local",
        internal_url="http://current.local/internal/camera/observations",
        internal_token="token",
        family_id="fam_1",
        child_id="child_1",
        device_id="dev_1",
        interval_seconds=5.0,
    )


def _unused_request(url, payload, headers, timeout):
    raise AssertionError(f"unexpected request to {url}")


if __name__ == "__main__":
    unittest.main()
