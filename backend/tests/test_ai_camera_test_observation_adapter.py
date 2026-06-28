from __future__ import annotations

import json
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
        self.assertEqual(
            payload["sourceEventId"],
            "ai_camera_test:dev_1:toy_cleanup:1000:6000:child_left_toys_uncollected",
        )
        self.assertEqual(payload["signals"][0]["durationSeconds"], 5)
        self.assertEqual(payload["signals"][0]["signalType"], "child_left_toys_uncollected")
        self.assertNotIn("reminder", payload["rawDetail"])
        self.assertEqual(payload["rawDetail"].get("child_message"), "")

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

    def test_normal_or_unknown_posture_does_not_create_posture_payload(self):
        adapter = AiCameraTestObservationAdapter(_config(), json_request=_unused_request)

        normal_payloads = adapter.payloads_from_analysis(
            {
                "has_person": True,
                "activity": "写作业/看书",
                "posture_status": "ok",
                "bad_posture": False,
                "confidence": 0.78,
                "description": "一个人坐在桌前，纸上有手写文字和一支笔。",
                "summary": {"skills": [{"name": "坐姿", "score": 88}]},
            },
            window_start_ms=1_000,
            window_end_ms=4_000,
            observed_at=4_000,
        )
        unknown_payloads = adapter.payloads_from_analysis(
            {
                "has_person": False,
                "activity": "离开",
                "posture_status": "unknown",
                "bad_posture": False,
                "confidence": 0.9,
                "description": "画面中没有清晰的人出现。",
                "summary": {"skills": [{"name": "坐姿", "score": 60}]},
            },
            window_start_ms=4_000,
            window_end_ms=7_000,
            observed_at=7_000,
        )

        self.assertEqual(normal_payloads, [])
        self.assertEqual(len(unknown_payloads), 1)
        self.assertEqual(unknown_payloads[0]["scenario"], "transition")
        self.assertEqual(unknown_payloads[0]["signals"][0]["signalType"], "child_not_visible")

    def test_negated_toy_description_does_not_create_toy_payload(self):
        adapter = AiCameraTestObservationAdapter(_config(), json_request=_unused_request)

        payloads = adapter.payloads_from_analysis(
            {
                "has_person": True,
                "activity": "玩玩具",
                "confidence": 0.82,
                "description": "一个人趴在桌上，头部埋在双臂之间，没有看到书本、手机或玩具等物品。",
                "decision_reason": "坐姿风险处在冷却期内。",
            },
            window_start_ms=1_000,
            window_end_ms=6_000,
            observed_at=6_000,
        )

        self.assertEqual(payloads, [])

    def test_risky_posture_still_creates_posture_payload(self):
        adapter = AiCameraTestObservationAdapter(_config(), json_request=_unused_request)

        payloads = adapter.payloads_from_analysis(
            {
                "has_person": True,
                "activity": "写作业/看书",
                "posture_status": "leaning_too_close",
                "bad_posture": True,
                "confidence": 0.72,
                "description": "孩子头离纸面太近。",
            },
            window_start_ms=10_000,
            window_end_ms=40_000,
            observed_at=40_000,
        )

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["scenario"], "posture")
        self.assertEqual(payloads[0]["signals"][0]["signalType"], "leaning_too_close")
        self.assertEqual(payloads[0]["signals"][0]["durationSeconds"], 30)

    def test_playing_toys_does_not_create_posture_payload(self):
        adapter = AiCameraTestObservationAdapter(_config(), json_request=_unused_request)

        payloads = adapter.payloads_from_analysis(
            {
                "has_person": True,
                "activity": "玩玩具",
                "posture_status": "leaning_too_close",
                "bad_posture": True,
                "confidence": 0.82,
                "description": "孩子坐在客厅地垫上，周围散落着多个机器人玩具和一个大包装盒。",
                "child_message": "眼睛离桌面远一点，坐舒服些。",
            },
            window_start_ms=1_000,
            window_end_ms=6_000,
            observed_at=6_000,
        )

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["scenario"], "toy_cleanup")
        self.assertEqual(payloads[0]["signals"][0]["signalType"], "toy_playing_observed")

    def test_worker_posts_only_observation_endpoint(self):
        calls = []

        class _FakeVision:
            def analyze_snapshot(self, **kwargs):
                return {
                    "has_person": True,
                    "activity": "写作业/看书",
                    "posture_status": "leaning_too_close",
                    "bad_posture": True,
                    "confidence": 0.9,
                    "description": "孩子低头靠近桌面写字。",
                    "method": "guardian_test",
                    "observed_at": 15_000,
                }

        def fake_request(url, payload, headers, timeout):
            calls.append((url, payload, headers, timeout))
            if url.endswith("/api/camera/snapshot?format=data_url"):
                return {"image": "data:image/jpeg;base64,YWJj"}
            self.assertEqual(url, "http://current.local/internal/camera/observations")
            self.assertEqual(headers["X-Mira-Internal-Token"], "token")
            self.assertEqual(headers["X-Mira-Internal-Source"], "ai_camera_test")
            return {"ok": True}

        class _FakeObserveService:
            vision_service = _FakeVision()

            def run_tick(self, **kwargs):
                from dataclasses import dataclass
                from services.observation_payload_builder import build_primary_payload
                from services.vision_observation_enrich import enrich_observation
                from schemas.vision import with_observation_reliability

                analysis = with_observation_reliability(
                    enrich_observation(
                        self.vision_service.analyze_snapshot(
                            image_bytes=kwargs["image_bytes"],
                            content_type=kwargs.get("content_type") or "image/jpeg",
                            device_key="dev_1",
                            context={},
                            force_analyze=False,
                        )
                    )
                )
                payload = build_primary_payload(
                    analysis,
                    family_id=kwargs["family_id"],
                    child_id=kwargs["child_id"],
                    device_id=kwargs["device_id"],
                    source=kwargs.get("source") or "ai_camera_test",
                    window_start_ms=kwargs.get("window_start_ms") or 10_000,
                    window_end_ms=kwargs.get("window_end_ms") or 15_000,
                    observed_at=kwargs.get("window_end_ms") or 15_000,
                )
                response = None
                posted = False
                if payload is not None:
                    response = kwargs["post_observation"](payload)
                    posted = bool(response.get("ok"))
                from services.camera_observe_service import ObserveTickResult

                return ObserveTickResult(
                    skipped=False,
                    skip_reason="",
                    analysis=analysis,
                    posted=posted,
                    observation_count=1 if payload else 0,
                    response=response,
                )

        adapter = AiCameraTestObservationAdapter(
            _config(),
            json_request=fake_request,
            vision_service=_FakeVision(),
            observe_service=_FakeObserveService(),
        )
        result = CameraObservationWorker(adapter).run_once(
            window_start_ms=10_000,
            window_end_ms=15_000,
        )

        self.assertEqual(result.posted_count, 1)
        called_urls = [item[0] for item in calls]
        self.assertTrue(all("/internal/reminders/trigger" not in url for url in called_urls))
        self.assertTrue(all("speaker" not in url for url in called_urls))
        self.assertTrue(all("/api/analyze_frame" not in url for url in called_urls))
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

    def test_run_observe_tick_skips_when_snapshot_unavailable(self):
        from integrations.camera_runtime.ai_camera_test_observation_adapter import SnapshotUnavailableError

        def failing_snapshot(url, payload, headers, timeout):
            raise SnapshotUnavailableError("摄像头 RTSP 不可达，请检查摄像头是否在线、IP 是否正确。")

        adapter = AiCameraTestObservationAdapter(_config(), json_request=failing_snapshot)
        result = adapter.run_observe_tick(window_start_ms=1_000, window_end_ms=6_000)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["skip_reason"], "snapshot_unavailable")
        self.assertFalse(result["posted"])
        self.assertIn("RTSP", result["message"])


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
