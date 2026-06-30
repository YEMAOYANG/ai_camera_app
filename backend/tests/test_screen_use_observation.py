from __future__ import annotations

import unittest

from models.care import (
    REMINDER_DECISION_ALLOWED,
    REMINDER_DECISION_RECORD_ONLY,
)
from services.care_policy_engine import CarePolicyEngine, NON_ACTIONABLE_SIGNAL_TYPES
from services.observation_payload_builder import build_primary_payload, scenario_signals
from services.vision_observation_enrich import enrich_observation


def _screen_analysis(**overrides) -> dict:
    base = {
        "has_person": True,
        "activity": "玩手机",
        "raw_activity": "看手机",
        "confidence": 0.86,
        "description": "小爱低头看手机。",
        "posture_status": "low_head",
        "bad_posture": True,
        "screen_device_visible": True,
        "screen_device_type": "phone",
        "screen_use_active": True,
        "screen_distance_risk": "ok",
        "screen_use_context": "leisure",
        "screen_use_duration_hint": "sustained",
    }
    base.update(overrides)
    return enrich_observation(base)


class ScreenUsePayloadTest(unittest.TestCase):
    def _payload(self, analysis: dict) -> dict | None:
        return build_primary_payload(
            analysis,
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            source="test",
            window_start_ms=1_000,
            window_end_ms=100_000,
            observed_at=100_000,
        )

    def test_brief_phone_only_records(self):
        analysis = _screen_analysis(screen_use_duration_hint="brief")
        payload = self._payload(analysis)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "screen_use")
        self.assertEqual(payload["signals"][0]["signalType"], "screen_use_observed")

    def test_sustained_phone_tablet_can_remind(self):
        for device_type in ("phone", "tablet"):
            with self.subTest(device_type=device_type):
                analysis = _screen_analysis(
                    screen_device_type=device_type,
                    screen_use_duration_hint="sustained",
                )
                payload = self._payload(analysis)
                self.assertIsNotNone(payload)
                assert payload is not None
                self.assertEqual(payload["scenario"], "screen_use")
                self.assertEqual(payload["signals"][0]["signalType"], "screen_use_sustained")

    def test_tv_computer_only_record(self):
        for device_type in ("tv", "computer"):
            with self.subTest(device_type=device_type):
                analysis = _screen_analysis(
                    activity="看电视",
                    screen_device_type=device_type,
                    screen_use_duration_hint="sustained",
                )
                payload = self._payload(analysis)
                self.assertIsNotNone(payload)
                assert payload is not None
                self.assertEqual(payload["scenario"], "screen_use")
                self.assertEqual(payload["signals"][0]["signalType"], "screen_use_observed")

    def test_missing_structured_fields_do_not_trigger_screen_use(self):
        analysis = enrich_observation(
            {
                "has_person": True,
                "activity": "玩手机",
                "confidence": 0.86,
                "description": "小爱低头看手机。",
                "posture_status": "low_head",
                "bad_posture": True,
            }
        )
        payload = self._payload(analysis)
        self.assertIsNone(payload)

    def test_meal_window_phone_goes_to_meal_habit(self):
        analysis = _screen_analysis(
            activity="吃饭",
            description="小爱在餐桌前吃饭，同时低头看手机。",
            screen_use_context="meal",
        )
        payload = self._payload(analysis)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "meal_habit")
        self.assertEqual(payload["signals"][0]["signalType"], "meal_attention_shifted")
        self.assertNotIn("screen_use", {item[0] for item in scenario_signals(analysis)})

    def test_homework_bad_posture_without_phone_stays_posture(self):
        analysis = enrich_observation(
            {
                "has_person": True,
                "activity": "写作业",
                "raw_activity": "在书桌写字",
                "confidence": 0.88,
                "description": "小爱在书桌前写字，明显低头趴桌。",
                "posture_status": "low_head",
                "bad_posture": True,
            }
        )
        payload = self._payload(analysis)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "posture")

    def test_phone_with_posture_only_screen_use(self):
        analysis = _screen_analysis(
            screen_use_duration_hint="sustained",
            screen_distance_risk="too_close",
        )
        payload = self._payload(analysis)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "screen_use")
        self.assertEqual(payload["signals"][0]["signalType"], "screen_distance_risk")
        self.assertFalse(analysis.get("bad_posture"))

    def test_toy_unsafe_still_wins_over_screen(self):
        analysis = _screen_analysis(
            activity="玩玩具",
            description="孩子正在爬茶几，同时拿着手机。",
            screen_use_duration_hint="sustained",
        )
        payload = self._payload(analysis)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "toy_cleanup")
        self.assertTrue(str(payload["signals"][0]["signalType"]).startswith("toy_play_unsafe_"))


class ScreenUsePolicyTest(unittest.TestCase):
    def test_non_actionable_signals_include_screen_observed(self):
        self.assertIn("screen_use_observed", NON_ACTIONABLE_SIGNAL_TYPES)

    def test_screen_use_observed_is_record_only(self):
        engine = CarePolicyEngine()
        decision = engine.decide(
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            scenario="screen_use",
            observation_event={
                "id": "obs_1",
                "confidence": 0.9,
                "observed_at": 1_700_000_000_000,
                "evidence_type": "snapshot",
            },
            behavior_signals=[
                {
                    "signal_type": "screen_use_observed",
                    "signal_value": "active",
                    "duration_seconds": 120,
                    "confidence": 0.9,
                }
            ],
            capability_config={
                "enabled": True,
                "cooldown_seconds": 0,
                "daily_limit": 3,
                "parent_notify_threshold": 3,
                "confidence_threshold": 0.72,
                "min_observation_seconds": 90,
                "allow_speaker": True,
                "record_only": False,
                "time_windows": "[]",
            },
            current_behavior_state=None,
            recent_reminder_events=[],
            recent_allowed_decisions=[],
            now=1_700_000_100_000,
        )
        self.assertEqual(decision.decision, REMINDER_DECISION_RECORD_ONLY)
        self.assertFalse(decision.should_speak)
        self.assertEqual(decision.reason, "signal_positive_or_in_progress")

    def test_screen_use_sustained_can_speak(self):
        engine = CarePolicyEngine()
        decision = engine.decide(
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            scenario="screen_use",
            observation_event={
                "id": "obs_2",
                "confidence": 0.9,
                "observed_at": 1_700_000_000_000,
                "evidence_type": "snapshot",
            },
            behavior_signals=[
                {
                    "signal_type": "screen_use_sustained",
                    "signal_value": "active",
                    "duration_seconds": 120,
                    "confidence": 0.9,
                }
            ],
            capability_config={
                "enabled": True,
                "cooldown_seconds": 0,
                "daily_limit": 3,
                "parent_notify_threshold": 3,
                "confidence_threshold": 0.72,
                "min_observation_seconds": 90,
                "allow_speaker": True,
                "record_only": False,
                "time_windows": "[]",
            },
            current_behavior_state=None,
            recent_reminder_events=[],
            recent_allowed_decisions=[],
            now=1_700_000_100_000,
        )
        self.assertEqual(decision.decision, REMINDER_DECISION_ALLOWED)
        self.assertTrue(decision.should_speak)


if __name__ == "__main__":
    unittest.main()
