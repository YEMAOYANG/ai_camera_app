from __future__ import annotations

import unittest

from services.observation_cloud_gate import (
    CloudGateConfig,
    CloudGateDecision,
    GATE_EMPTY_STABLE,
    GATE_MOTION_ACTIVE,
    GATE_PERSON_STABLE,
    default_cloud_gate_state,
    default_care_behavior_state,
    evaluate_care_critical_lane,
    evaluate_cloud_gate,
    evaluate_general_lane,
    has_screen_use_monitor_context,
    has_structured_toy_context,
    sync_care_behavior_from_analysis,
)
from services.vision_prefilter_service import PrefilterResult, prefilter_runtime_from_result


def _prefilter(
    *,
    person: bool | None = False,
    motion: float = 0.0,
    motion_available: bool = True,
    person_available: bool = True,
    confidence: float = 0.9,
    now_ms: int = 0,
    thumb: str = "thumb-a",
) -> PrefilterResult:
    return PrefilterResult(
        motion_score=motion,
        motion_pixels=int(motion * 1000),
        person_detected=person,
        person_confidence=confidence if person else 0.0,
        person_count=1 if person else 0,
        person_available=person_available,
        motion_available=motion_available,
        checked_at=now_ms,
        frame_thumb_b64=thumb,
    )


def _fast_config(**overrides) -> CloudGateConfig:
    base = dict(
        tick_interval_seconds=10.0,
        empty_heartbeat_seconds=1800,
        person_heartbeat_seconds=900,
        motion_cooldown_seconds=300,
        motion_threshold=0.02,
        person_enter_debounce_ticks=2,
        person_leave_debounce_ticks=2,
        motion_exit_debounce_ticks=2,
        confirm_person_leave=False,
    )
    base.update(overrides)
    return CloudGateConfig(**base)


class ObservationCloudGateGeneralLaneTest(unittest.TestCase):
    def _advance_to_empty_stable(self, config: CloudGateConfig) -> dict:
        gate = default_cloud_gate_state()
        previous = None
        t = 0
        for _ in range(4):
            t += 10_000
            pf = _prefilter(person=False, motion=0.0, now_ms=t, thumb="empty")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertEqual(gate["gate_state"], GATE_EMPTY_STABLE)
        return gate

    def _advance_to_person_stable(self, config: CloudGateConfig) -> tuple[dict, dict]:
        gate = self._advance_to_empty_stable(config)
        previous = prefilter_runtime_from_result(
            _prefilter(person=False, motion=0.0, now_ms=40_000, thumb="empty")
        )
        t = 40_000
        kimi_calls = 0
        for i in range(6):
            t += 10_000
            pf = _prefilter(person=True, motion=0.0, now_ms=t, thumb=f"person-{i}")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            if decision.call_kimi:
                kimi_calls += 1
            gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertEqual(gate["gate_state"], GATE_PERSON_STABLE)
        self.assertEqual(kimi_calls, 1)
        return gate, previous

    def test_g1_empty_room_stable_no_kimi_within_heartbeat(self):
        config = _fast_config(empty_heartbeat_seconds=1800)
        gate = self._advance_to_empty_stable(config)
        previous = prefilter_runtime_from_result(
            _prefilter(person=False, motion=0.0, now_ms=50_000, thumb="empty")
        )
        kimi_calls = 0
        t = 50_000
        for _ in range(30):
            t += 10_000
            pf = _prefilter(person=False, motion=0.0, now_ms=t, thumb="empty")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            if decision.call_kimi:
                kimi_calls += 1
            gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertEqual(kimi_calls, 0)

    def test_g2_person_stable_no_kimi_within_person_heartbeat(self):
        config = _fast_config(person_heartbeat_seconds=900)
        gate, previous = self._advance_to_person_stable(config)
        kimi_calls = 0
        t = 100_000
        for _ in range(30):
            t += 10_000
            pf = _prefilter(person=True, motion=0.0, now_ms=t, thumb="still")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            if decision.call_kimi:
                kimi_calls += 1
            gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertEqual(kimi_calls, 0)

    def test_g3_sustained_motion_respects_cooldown(self):
        config = _fast_config(
            motion_cooldown_seconds=300,
            person_heartbeat_seconds=3600,
            motion_active_sample_seconds=3600,
        )
        gate, previous = self._advance_to_person_stable(config)
        kimi_calls = 0
        t = 100_000
        for i in range(30):
            t += 10_000
            motion = 0.05 if i % 2 == 0 else 0.01
            pf = _prefilter(person=True, motion=motion, now_ms=t, thumb=f"m-{i}")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            if decision.call_kimi:
                kimi_calls += 1
            gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertLessEqual(kimi_calls, 2)

    def test_g4_force_analyze_bypasses_gate_with_child_id(self):
        pf = _prefilter(person=True, motion=0.0, now_ms=1_000)
        decision = evaluate_cloud_gate(
            prefilter=pf,
            prefilter_previous=None,
            cloud_gate=None,
            care_behavior=None,
            now_ms=1_000,
            force_analyze=True,
            child_id="child_1",
        )
        self.assertTrue(decision.call_kimi)
        self.assertEqual(decision.reason, "force_analyze")

    def test_missing_child_id_beats_force_analyze(self):
        pf = _prefilter(person=True, motion=0.0, now_ms=1_000)
        decision = evaluate_cloud_gate(
            prefilter=pf,
            prefilter_previous=None,
            cloud_gate=None,
            care_behavior=None,
            now_ms=1_000,
            force_analyze=True,
            child_id="",
        )
        self.assertFalse(decision.call_kimi)
        self.assertEqual(decision.reason, "missing_child_id")
        self.assertTrue(decision.observation_context_invalid)

    def test_missing_child_id_is_observation_context_invalid(self):
        pf = _prefilter(person=True, motion=0.0, now_ms=1_000)
        decision = evaluate_cloud_gate(
            prefilter=pf,
            prefilter_previous=None,
            cloud_gate=None,
            care_behavior=None,
            now_ms=1_000,
            child_id="",
        )
        self.assertFalse(decision.call_kimi)
        self.assertEqual(decision.reason, "missing_child_id")
        self.assertTrue(decision.observation_context_invalid)

    def test_person_enter_debounce_requires_two_ticks(self):
        config = _fast_config()
        gate = self._advance_to_empty_stable(config)
        previous = prefilter_runtime_from_result(
            _prefilter(person=False, motion=0.0, now_ms=50_000, thumb="empty")
        )
        t = 50_000
        calls = []
        for i in range(4):
            t += 10_000
            pf = _prefilter(person=True, motion=0.0, now_ms=t, thumb=f"p{i}")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            calls.append(decision.call_kimi)
            gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertEqual(sum(1 for c in calls if c), 1)

    def test_g5_motion_active_periodic_sample_while_motion_continues(self):
        config = _fast_config(motion_active_sample_seconds=90, person_heartbeat_seconds=3600)
        gate = {"gate_state": GATE_MOTION_ACTIVE, "last_kimi_at_ms": 0}
        previous = prefilter_runtime_from_result(
            _prefilter(person=True, motion=0.05, now_ms=100_000, thumb="m0")
        )
        t = 100_000
        kimi_calls = 0
        for i in range(12):
            t += 10_000
            pf = _prefilter(person=True, motion=0.05, now_ms=t, thumb=f"m{i}")
            decision = evaluate_general_lane(
                prefilter=pf,
                prefilter_previous=previous,
                cloud_gate=gate,
                now_ms=t,
                config=config,
            )
            if decision.call_kimi:
                kimi_calls += 1
                if decision.reason == "motion_active_sample":
                    gate = decision.next_cloud_gate
            else:
                gate = decision.next_cloud_gate
            previous = prefilter_runtime_from_result(pf)
        self.assertGreaterEqual(kimi_calls, 1)
        self.assertLess(kimi_calls, 12)


class ObservationCloudGateCareCriticalLaneTest(unittest.TestCase):
    def _caps(self, *scenarios: str) -> list[dict]:
        return [{"scenario": scenario, "enabled": True} for scenario in scenarios]

    def test_s1_posture_interval_triggers_critical(self):
        config = CloudGateConfig(posture_interval_seconds=60)
        gate = {"gate_state": GATE_PERSON_STABLE}
        behavior = default_care_behavior_state()
        behavior["last_posture_context"] = "homework"
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        previous = prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000))
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=previous,
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        self.assertFalse(general.call_kimi)
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(
                _prefilter(person=True, now_ms=110_000)
            ),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("posture"),
            meal_window_active=False,
        )
        self.assertIsNotNone(critical)
        assert critical is not None
        self.assertTrue(critical.call_kimi)
        self.assertEqual(critical.reason, "posture_interval")
        self.assertEqual(critical.lane, "care_critical")

    def test_s1_posture_interval_skips_without_monitor_context(self):
        config = CloudGateConfig(posture_interval_seconds=60)
        gate = {"gate_state": GATE_PERSON_STABLE}
        behavior = default_care_behavior_state()
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("posture"),
            meal_window_active=False,
        )
        self.assertIsNone(critical)

    def test_s2_toy_cleanup_leave_forces_kimi(self):
        config = CloudGateConfig()
        behavior = default_care_behavior_state()
        behavior["toys_scattered_last"] = True
        gate = {"gate_state": GATE_EMPTY_STABLE}
        pf = _prefilter(person=False, motion=0.0, now_ms=200_000)
        general = CloudGateDecision(
            call_kimi=False,
            reason="cloud_gate_person_leave_lightweight",
            lane="general",
            next_cloud_gate=gate,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=None,
            cloud_gate=gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=200_000,
            config=config,
            enabled_capabilities=self._caps("toy_cleanup"),
            meal_window_active=False,
        )
        self.assertIsNotNone(critical)
        assert critical is not None
        self.assertEqual(critical.reason, "toy_cleanup_leave")

    def test_s3_meal_habit_only_inside_meal_window(self):
        config = CloudGateConfig(meal_habit_interval_seconds=120)
        behavior = default_care_behavior_state()
        gate = {"gate_state": GATE_PERSON_STABLE}
        pf = _prefilter(person=True, motion=0.0, now_ms=300_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(
                _prefilter(person=True, now_ms=290_000)
            ),
            cloud_gate=gate,
            now_ms=300_000,
            config=config,
        )
        outside = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(
                _prefilter(person=True, now_ms=290_000)
            ),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=300_000,
            config=config,
            enabled_capabilities=self._caps("meal_habit"),
            meal_window_active=False,
        )
        self.assertIsNone(outside)
        inside = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(
                _prefilter(person=True, now_ms=290_000)
            ),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=300_000,
            config=config,
            enabled_capabilities=self._caps("meal_habit"),
            meal_window_active=True,
        )
        self.assertIsNotNone(inside)
        assert inside is not None
        self.assertEqual(inside.reason, "meal_habit_interval")

    def test_c12_meal_window_via_cloud_gate_routine_windows(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        noon = datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        now = int(noon.timestamp() * 1000)
        pf = _prefilter(person=True, motion=0.0, now_ms=now)
        decision = evaluate_cloud_gate(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(
                _prefilter(person=True, now_ms=now - 10_000)
            ),
            cloud_gate={"gate_state": GATE_PERSON_STABLE, "person_stable_since_ms": now - 600_000},
            care_behavior=default_care_behavior_state(),
            now_ms=now,
            child_id="child_1",
            enabled_capabilities=self._caps("meal_habit"),
            routine_windows=[
                {
                    "id": "lunch",
                    "day_type": "school_day",
                    "window_type": "lunch",
                    "start_time": "11:30",
                    "end_time": "13:00",
                    "timezone": "Asia/Shanghai",
                    "enabled": True,
                }
            ],
            explicit_day_type="school_day",
        )
        self.assertTrue(decision.call_kimi)
        self.assertEqual(decision.reason, "meal_habit_interval")

    def test_c13_toy_unsafe_requires_structured_toy_context(self):
        config = CloudGateConfig(motion_cooldown_seconds=300)
        gate = {"gate_state": GATE_PERSON_STABLE, "last_motion_kimi_at_ms": 0}
        behavior = default_care_behavior_state()
        pf = _prefilter(person=True, motion=0.05, now_ms=400_000)
        previous = prefilter_runtime_from_result(_prefilter(person=True, motion=0.0, now_ms=390_000))
        general = CloudGateDecision(
            call_kimi=False,
            reason="cloud_gate_person_stable",
            lane="general",
            next_cloud_gate=dict(gate),
        )
        without_context = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=previous,
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=400_000,
            config=config,
            enabled_capabilities=self._caps("toy_cleanup"),
            meal_window_active=False,
        )
        self.assertIsNone(without_context)
        behavior["last_toy_session"] = "playing"
        with_context = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=previous,
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=400_000,
            config=config,
            enabled_capabilities=self._caps("toy_cleanup"),
            meal_window_active=False,
        )
        self.assertIsNotNone(with_context)
        assert with_context is not None
        self.assertEqual(with_context.reason, "toy_unsafe_motion")

    def test_has_structured_toy_context_rejects_description_only(self):
        behavior = default_care_behavior_state()
        behavior["last_critical_reason"] = "unsafe climbing on sofa"
        self.assertFalse(has_structured_toy_context(behavior))

    def test_s4_screen_use_interval_triggers_with_structured_context(self):
        config = CloudGateConfig(screen_use_interval_seconds=90)
        gate = {"gate_state": GATE_PERSON_STABLE}
        behavior = default_care_behavior_state()
        behavior["last_screen_use_signature"] = "phone:active"
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("screen_use"),
            meal_window_active=False,
        )
        self.assertIsNotNone(critical)
        assert critical is not None
        self.assertTrue(critical.call_kimi)
        self.assertEqual(critical.reason, "screen_use_interval")

    def test_s4_screen_use_interval_skips_without_structured_context(self):
        config = CloudGateConfig(screen_use_interval_seconds=90)
        behavior = default_care_behavior_state()
        gate = {"gate_state": GATE_PERSON_STABLE}
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("screen_use"),
            meal_window_active=False,
        )
        self.assertIsNone(critical)

    def test_s4_screen_use_stable_respects_interval(self):
        config = CloudGateConfig(screen_use_interval_seconds=90)
        behavior = default_care_behavior_state()
        behavior["last_screen_use_signature"] = "phone:active"
        behavior["last_screen_use_kimi_at_ms"] = 50_000
        gate = {"gate_state": GATE_PERSON_STABLE}
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("screen_use"),
            meal_window_active=False,
        )
        self.assertIsNone(critical)

    def test_s4_screen_use_context_change_triggers_critical(self):
        config = CloudGateConfig(screen_use_interval_seconds=90)
        behavior = default_care_behavior_state()
        behavior["last_screen_use_signature"] = "phone:active"
        behavior["screen_context_changed"] = True
        behavior["last_screen_use_kimi_at_ms"] = 119_000
        gate = {"gate_state": GATE_PERSON_STABLE}
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("screen_use"),
            meal_window_active=False,
        )
        self.assertIsNotNone(critical)
        assert critical is not None
        self.assertEqual(critical.reason, "screen_use_context_change")
        assert critical.next_care_behavior is not None
        self.assertFalse(critical.next_care_behavior.get("screen_context_changed"))

    def test_s4_screen_use_skips_posture_interval_when_screen_monitor_active(self):
        config = CloudGateConfig(posture_interval_seconds=60, screen_use_interval_seconds=90)
        behavior = default_care_behavior_state()
        behavior["last_posture_context"] = "screen"
        behavior["last_screen_use_signature"] = "phone:active"
        behavior["last_posture_kimi_at_ms"] = 0
        behavior["last_screen_use_kimi_at_ms"] = 50_000
        gate = {"gate_state": GATE_PERSON_STABLE}
        pf = _prefilter(person=True, motion=0.0, now_ms=120_000)
        general = evaluate_general_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=gate,
            now_ms=120_000,
            config=config,
        )
        critical = evaluate_care_critical_lane(
            prefilter=pf,
            prefilter_previous=prefilter_runtime_from_result(_prefilter(person=True, now_ms=110_000)),
            cloud_gate=general.next_cloud_gate,
            care_behavior=behavior,
            general_decision=general,
            now_ms=120_000,
            config=config,
            enabled_capabilities=self._caps("posture", "screen_use"),
            meal_window_active=False,
        )
        self.assertIsNone(critical)

    def test_sync_screen_signature_marks_context_change(self):
        behavior = default_care_behavior_state()
        updated = sync_care_behavior_from_analysis(
            behavior,
            {
                "activity": "玩手机",
                "raw_activity": "看手机",
                "screen_device_visible": True,
                "screen_device_type": "phone",
                "screen_use_active": True,
            },
        )
        self.assertEqual(updated["last_screen_use_signature"], "phone:active")
        self.assertFalse(updated.get("screen_context_changed"))
        changed = sync_care_behavior_from_analysis(
            updated,
            {
                "activity": "看电视",
                "raw_activity": "看电视",
                "screen_device_visible": True,
                "screen_device_type": "tv",
                "screen_use_active": True,
            },
        )
        self.assertTrue(changed.get("screen_context_changed"))
        self.assertEqual(changed["last_screen_use_signature"], "tv:active")

    def test_has_screen_use_monitor_context_requires_active_signature(self):
        behavior = default_care_behavior_state()
        self.assertFalse(has_screen_use_monitor_context(behavior))
        behavior["last_screen_use_signature"] = "tv:inactive"
        self.assertFalse(has_screen_use_monitor_context(behavior))
        behavior["last_screen_use_signature"] = "phone:active"
        self.assertTrue(has_screen_use_monitor_context(behavior))


if __name__ == "__main__":
    unittest.main()
