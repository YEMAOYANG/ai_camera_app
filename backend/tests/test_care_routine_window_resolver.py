from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from services.care_routine_window_resolver import (
    resolve_meal_window_active,
    routine_window_gate,
    time_in_window,
)


def _lunch_window(*, day_type: str = "school_day", enabled: bool = True) -> dict:
    return {
        "id": "win_lunch",
        "day_type": day_type,
        "window_type": "lunch",
        "start_time": "11:30",
        "end_time": "13:00",
        "timezone": "Asia/Shanghai",
        "enabled": enabled,
    }


class CareRoutineWindowResolverTest(unittest.TestCase):
    def test_meal_window_active_within_routine_window(self):
        noon = datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        observed_at = int(noon.timestamp() * 1000)
        active = resolve_meal_window_active(
            routine_windows=[_lunch_window()],
            observed_at=observed_at,
            explicit_day_type="school_day",
        )
        self.assertTrue(active)

    def test_meal_window_inactive_outside_routine_window(self):
        morning = datetime(2026, 6, 29, 8, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        observed_at = int(morning.timestamp() * 1000)
        active = resolve_meal_window_active(
            routine_windows=[_lunch_window()],
            observed_at=observed_at,
            explicit_day_type="school_day",
        )
        self.assertFalse(active)

    def test_meal_window_missing_when_no_routine_rows(self):
        noon = datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        observed_at = int(noon.timestamp() * 1000)
        gate = routine_window_gate(
            scenario="meal_habit",
            capability_config={"time_windows": ["lunch"]},
            routine_windows=[],
            explicit_day_type="school_day",
            observed_at=observed_at,
        )
        self.assertFalse(gate["allowed"])
        self.assertEqual(gate["reason"], "routine_window_missing")

    def test_capability_time_windows_narrow_types(self):
        noon = datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        observed_at = int(noon.timestamp() * 1000)
        gate = routine_window_gate(
            scenario="meal_habit",
            capability_config={"time_windows": ["breakfast"]},
            routine_windows=[_lunch_window()],
            explicit_day_type="school_day",
            observed_at=observed_at,
        )
        self.assertFalse(gate["allowed"])

    def test_time_in_window_supports_camel_case_fields(self):
        noon = datetime(2026, 6, 29, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        observed_at = int(noon.timestamp() * 1000)
        row = {
            "startTime": "11:30",
            "endTime": "13:00",
            "timezone": "Asia/Shanghai",
        }
        self.assertTrue(time_in_window(observed_at, row))


if __name__ == "__main__":
    unittest.main()
