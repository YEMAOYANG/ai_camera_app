from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from services.camera_observe_service import CameraObserveService
from services.observation_cloud_gate import default_cloud_gate_state
from services.observation_runtime_state import default_runtime_payload
from services.vision_prefilter_service import PrefilterResult
from tests.support import TEST_DATABASE_URL


def _tiny_png() -> bytes:
    from PIL import Image
    import io

    image = Image.new("RGB", (32, 32), color=(120, 140, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@dataclass
class _SequencePrefilter:
    results: list[PrefilterResult]
    index: int = 0

    def analyze_frame(self, image_bytes: bytes, *, previous: dict | None, now_ms: int) -> PrefilterResult:
        del image_bytes, previous, now_ms
        if self.index >= len(self.results):
            return self.results[-1]
        result = self.results[self.index]
        self.index += 1
        return result


def _prefilter(*, person: bool | None, motion: float = 0.0, now_ms: int = 0) -> PrefilterResult:
    return PrefilterResult(
        motion_score=motion,
        motion_pixels=int(motion * 1000),
        person_detected=person,
        person_confidence=0.9 if person else 0.0,
        person_count=1 if person else 0,
        person_available=True,
        motion_available=True,
        checked_at=now_ms,
        frame_thumb_b64="thumb",
    )


class _CountingVision:
    calls = 0

    def analyze_snapshot(self, **kwargs):
        _CountingVision.calls += 1
        return {
            "has_person": True,
            "activity": "发呆",
            "confidence": 0.9,
            "description": "孩子在客厅。",
            "toys_visible": False,
            "toys_scattered": False,
        }


class _AbsentVision:
    calls = 0

    def analyze_snapshot(self, **kwargs):
        _AbsentVision.calls += 1
        return {
            "has_person": False,
            "activity": "离开",
            "confidence": 0.92,
            "description": "客厅暂时没有看到孩子。",
        }


def _default_context(**runtime_overrides) -> Any:
    runtime = default_runtime_payload()
    for key, value in runtime_overrides.items():
        if isinstance(value, dict) and isinstance(runtime.get(key), dict):
            runtime[key] = {**runtime[key], **value}
        else:
            runtime[key] = value
    from services.camera_observe_service import _ObserveContext

    return _ObserveContext(
        runtime=runtime,
        previous_session=dict(runtime.get("session") or {}),
        frame_stable=True,
        prefilter_previous=runtime.get("prefilter"),
        absence_snapshot=dict(runtime.get("absence") or {}),
        enabled_capabilities=[
            {"scenario": "posture", "enabled": True},
            {"scenario": "toy_cleanup", "enabled": True},
            {"scenario": "meal_habit", "enabled": True},
        ],
        routine_windows=[
            {
                "id": "lunch",
                "day_type": "school_day",
                "window_type": "lunch",
                "start_time": "11:30",
                "end_time": "12:30",
                "timezone": "Asia/Shanghai",
                "enabled": True,
            }
        ],
        meal_capability_config={"scenario": "meal_habit", "enabled": True, "time_windows": "[]"},
    )


class CameraObserveCloudGateTickTest(unittest.TestCase):
    def setUp(self):
        _CountingVision.calls = 0
        _AbsentVision.calls = 0
        self.service = CameraObserveService(
            TEST_DATABASE_URL,
            vision_service=_CountingVision(),
            vision_prefilter=_SequencePrefilter([_prefilter(person=True)]),
        )
        self.saved_payloads: list[dict] = []
        self.image_bytes = _tiny_png()

        def save_runtime(**kwargs):
            self.saved_payloads.append(dict(kwargs["payload"]))

        self.service._save_runtime = save_runtime  # type: ignore[method-assign]
        self.service._load_observe_context = lambda **kwargs: _default_context()  # type: ignore[method-assign]

    def test_missing_child_id_skips_before_kimi(self):
        result = self.service.run_tick(
            family_id="fam",
            child_id="",
            device_id="dev",
            image_bytes=self.image_bytes,
        )
        self.assertTrue(result.skipped)
        self.assertEqual(result.skip_reason, "missing_child_id")
        self.assertEqual(_CountingVision.calls, 0)
        self.assertEqual(self.saved_payloads, [])

    def test_gate_skip_persists_prefilter_only_display(self):
        _CountingVision.calls = 0
        from core.security import now_ms

        now = now_ms()
        stable_gate = {
            **default_cloud_gate_state(),
            "gate_state": "person_stable",
            "person_stable_since_ms": now,
            "last_person_heartbeat_at_ms": now,
        }
        behavior = {
            "last_posture_kimi_at_ms": 9_999_999_999,
            "last_meal_habit_kimi_at_ms": 9_999_999_999,
            "last_screen_use_kimi_at_ms": 9_999_999_999,
        }
        enabled = [
            {"scenario": "posture", "enabled": False},
            {"scenario": "toy_cleanup", "enabled": False},
            {"scenario": "meal_habit", "enabled": False},
            {"scenario": "screen_use", "enabled": False},
        ]

        def load_context(**kwargs):
            ctx = _default_context(cloud_gate=stable_gate, care_behavior=behavior)
            return type(ctx)(**{**ctx.__dict__, "enabled_capabilities": enabled})

        self.service._load_observe_context = load_context  # type: ignore[method-assign]
        self.service.vision_prefilter = _SequencePrefilter([_prefilter(person=True, motion=0.0)])
        env = {"APP_CLOUD_PERSON_HEARTBEAT_SECONDS": "900"}
        with patch.dict(os.environ, env, clear=False):
            result = self.service.run_tick(
                family_id="fam",
                child_id="child",
                device_id="dev",
                image_bytes=self.image_bytes,
            )
        self.assertTrue(result.skipped)
        self.assertEqual(_CountingVision.calls, 0)
        self.assertTrue(self.saved_payloads)
        self.assertEqual(self.saved_payloads[-1]["display"].get("freshness"), "prefilter_only")

    def test_empty_room_stable_limits_kimi_calls_with_runtime_roundtrip(self):
        env = {
            "APP_CLOUD_EMPTY_HEARTBEAT_SECONDS": "1800",
            "APP_ABSENCE_CONFIRM_TICKS": "999",
            "APP_CLOUD_PERSON_ENTER_DEBOUNCE_TICKS": "2",
        }
        memory: dict[str, Any] = {}
        disabled = [
            {"scenario": "posture", "enabled": False},
            {"scenario": "toy_cleanup", "enabled": False},
            {"scenario": "meal_habit", "enabled": False},
            {"scenario": "screen_use", "enabled": False},
        ]

        def load_context(**kwargs):
            ctx = _default_context(**memory)
            return type(ctx)(**{**ctx.__dict__, "enabled_capabilities": disabled})

        def save_runtime(**kwargs):
            memory.clear()
            memory.update(dict(kwargs["payload"]))
            self.saved_payloads.append(dict(kwargs["payload"]))

        self.service._load_observe_context = load_context  # type: ignore[method-assign]
        self.service._save_runtime = save_runtime  # type: ignore[method-assign]
        self.service.vision_service = _AbsentVision()
        self.service.vision_prefilter = _SequencePrefilter(
            [_prefilter(person=False, motion=0.0, now_ms=i * 10_000) for i in range(8)]
        )
        _AbsentVision.calls = 0
        with patch.dict(os.environ, env, clear=False):
            for _ in range(6):
                self.service.run_tick(
                    family_id="fam",
                    child_id="child",
                    device_id="dev",
                    image_bytes=self.image_bytes,
                    post_observation=lambda _payload: {"ok": True},
                )
        self.assertLessEqual(_AbsentVision.calls, 1)
        self.assertGreaterEqual(len(self.saved_payloads), 2)
        self.assertIn("cloud_gate", memory)
        self.assertNotEqual(memory["cloud_gate"].get("gate_state"), "unknown")

    def test_empty_room_stable_limits_kimi_calls(self):
        env = {
            "APP_CLOUD_EMPTY_HEARTBEAT_SECONDS": "1800",
            "APP_ABSENCE_CONFIRM_TICKS": "3",
        }
        self.service.vision_service = _AbsentVision()
        self.service.vision_prefilter = _SequencePrefilter(
            [_prefilter(person=False, motion=0.0) for _ in range(8)]
        )
        with patch.dict(os.environ, env, clear=False):
            for _ in range(6):
                self.service.run_tick(
                    family_id="fam",
                    child_id="child",
                    device_id="dev",
                    image_bytes=self.image_bytes,
                )
        self.assertLessEqual(_AbsentVision.calls, 1)

    def test_kimi_runs_between_read_and_write_phases(self):
        order: list[str] = []

        def load_context(**kwargs):
            order.append("read")
            return _default_context()

        def analyze(**kwargs):
            order.append("kimi")
            return _CountingVision().analyze_snapshot(**kwargs)

        def save_runtime(**kwargs):
            order.append("write")
            self.saved_payloads.append(dict(kwargs["payload"]))

        self.service._load_observe_context = load_context  # type: ignore[method-assign]
        self.service._analyze_image = analyze  # type: ignore[method-assign]
        self.service._save_runtime = save_runtime  # type: ignore[method-assign]
        self.service.runtime_store.load = lambda conn, **kwargs: default_runtime_payload()  # type: ignore[method-assign]
        self.service._semantic_duplicate = lambda **kwargs: False  # type: ignore[method-assign]
        self.service.run_tick(
            family_id="fam",
            child_id="child",
            device_id="dev",
            image_bytes=self.image_bytes,
            force_analyze=True,
        )
        self.assertEqual(order, ["read", "kimi", "write"])


if __name__ == "__main__":
    unittest.main()
