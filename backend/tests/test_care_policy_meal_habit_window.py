from __future__ import annotations

import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from models.care import (
    REMINDER_DECISION_ALLOWED,
    REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
)
from services.care_policy_engine import CarePolicyEngine


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000)


def _capability(**overrides) -> dict:
    base = {
        "enabled": True,
        "cooldown_seconds": 0,
        "daily_limit": 10,
        "parent_notify_threshold": 9,
        "confidence_threshold": 0.72,
        "min_observation_seconds": 1,
        "allow_speaker": True,
        "record_only": False,
        "time_windows": "[]",
    }
    base.update(overrides)
    return base


def _lunch_routine_window() -> dict:
    return {
        "id": "lunch",
        "day_type": "school_day",
        "window_type": "lunch",
        "start_time": "11:30",
        "end_time": "12:30",
        "timezone": "Asia/Shanghai",
        "enabled": True,
    }


class CarePolicyMealHabitWindowTest(unittest.TestCase):
    def setUp(self):
        self.engine = CarePolicyEngine()

    def _decide(self, *, scenario: str, observed_at: int, routine_windows: list[dict]):
        return self.engine.decide(
            family_id="fam",
            child_id="child",
            device_id="dev",
            scenario=scenario,
            observation_event={
                "confidence": 0.9,
                "observed_at": observed_at,
                "evidence_type": "snapshot",
                "parent_summary": "test",
            },
            behavior_signals=[
                {
                    "signal_type": "meal_standing_on_chair",
                    "signal_value": "active",
                    "confidence": 0.9,
                    "duration_seconds": 10,
                }
            ],
            capability_config=_capability(),
            current_behavior_state=None,
            recent_reminder_events=[],
            recent_allowed_decisions=[],
            routine_windows=routine_windows,
            day_type="school_day",
            now=observed_at,
        )

    def test_meal_habit_outside_meal_window_is_skipped(self):
        decision = self._decide(
            scenario="meal_habit",
            observed_at=_ms("2026-06-17 10:30:00"),
            routine_windows=[_lunch_routine_window()],
        )
        self.assertEqual(decision.decision, REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW)
        snapshot = json.loads(decision.policy_snapshot_json)
        self.assertNotEqual(snapshot["routineGate"]["reason"], "behavior_only_scenario")

    def test_meal_habit_inside_meal_window_is_allowed(self):
        decision = self._decide(
            scenario="meal_habit",
            observed_at=_ms("2026-06-17 12:00:00"),
            routine_windows=[_lunch_routine_window()],
        )
        self.assertEqual(decision.decision, REMINDER_DECISION_ALLOWED)
        snapshot = json.loads(decision.policy_snapshot_json)
        self.assertEqual(snapshot["routineGate"]["reason"], "within_routine_window")

    def test_posture_remains_behavior_only_outside_meal_window(self):
        decision = self._decide(
            scenario="posture",
            observed_at=_ms("2026-06-17 10:30:00"),
            routine_windows=[_lunch_routine_window()],
        )
        self.assertEqual(decision.decision, REMINDER_DECISION_ALLOWED)
        snapshot = json.loads(decision.policy_snapshot_json)
        self.assertEqual(snapshot["routineGate"]["reason"], "behavior_only_scenario")

    def test_toy_cleanup_remains_behavior_only_outside_meal_window(self):
        decision = self.engine.decide(
            family_id="fam",
            child_id="child",
            device_id="dev",
            scenario="toy_cleanup",
            observation_event={
                "confidence": 0.9,
                "observed_at": _ms("2026-06-17 10:30:00"),
                "evidence_type": "snapshot",
                "parent_summary": "test",
            },
            behavior_signals=[
                {
                    "signal_type": "toys_scattered",
                    "signal_value": "active",
                    "confidence": 0.9,
                    "duration_seconds": 10,
                }
            ],
            capability_config=_capability(),
            current_behavior_state=None,
            recent_reminder_events=[],
            recent_allowed_decisions=[],
            routine_windows=[_lunch_routine_window()],
            day_type="school_day",
            now=_ms("2026-06-17 10:30:00"),
        )
        self.assertEqual(decision.decision, REMINDER_DECISION_ALLOWED)
        snapshot = json.loads(decision.policy_snapshot_json)
        self.assertEqual(snapshot["routineGate"]["reason"], "behavior_only_scenario")


if __name__ == "__main__":
    unittest.main()
