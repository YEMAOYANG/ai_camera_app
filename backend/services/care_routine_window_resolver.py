from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from core.database import DatabaseRow
from models.care import (
    CARE_SCENARIO_BEDTIME,
    CARE_SCENARIO_MEAL_HABIT,
    CARE_SCENARIO_MEAL_START,
    CARE_SCENARIO_NAP_TIME,
    CARE_SCENARIO_POSTURE,
    CARE_SCENARIO_TRANSITION,
    CARE_SCENARIO_WAKE_UP,
    DAY_TYPES,
)
from services.care_day_type import effective_day_type

DEFAULT_TIMEZONE = "Asia/Shanghai"

SCENARIO_ROUTINE_WINDOW_TYPES: dict[str, set[str]] = {
    CARE_SCENARIO_WAKE_UP: {"wake_up"},
    CARE_SCENARIO_MEAL_START: {"breakfast", "lunch", "dinner", "meal"},
    CARE_SCENARIO_MEAL_HABIT: {"breakfast", "lunch", "dinner", "meal"},
    CARE_SCENARIO_NAP_TIME: {"nap"},
    CARE_SCENARIO_BEDTIME: {"bedtime"},
    CARE_SCENARIO_POSTURE: {"posture", "study", "reading", "meal", "breakfast", "lunch", "dinner"},
    CARE_SCENARIO_TRANSITION: {"transition"},
}

MEAL_WINDOW_TYPES = {"breakfast", "lunch", "dinner", "meal"}


def routine_window_gate(
    *,
    scenario: str,
    capability_config: Mapping[str, Any],
    routine_windows: Sequence[Mapping[str, Any]],
    explicit_day_type: str | None,
    observed_at: int,
) -> dict[str, Any]:
    window_types = window_types_for_scenario(scenario, capability_config)
    gate: dict[str, Any] = {
        "allowed": False,
        "reason": "out_of_routine_window",
        "dayType": "",
        "windowTypes": sorted(window_types),
        "matchedWindowId": "",
    }
    if not window_types:
        gate["reason"] = "routine_window_not_configured"
        return gate

    matched_day_rows: list[Mapping[str, Any]] = []
    disabled_rows = 0
    resolved_day_type = ""
    for row in routine_windows:
        timezone = str(row.get("timezone") or DEFAULT_TIMEZONE)
        row_day_type = str(row.get("day_type") or row.get("dayType") or "")
        window_type = str(row.get("window_type") or row.get("windowType") or "")
        if window_type not in window_types:
            continue
        current_day_type = effective_day_type(
            observed_at,
            timezone=timezone,
            explicit_day_type=explicit_day_type,
        )
        resolved_day_type = resolved_day_type or current_day_type
        if row_day_type != current_day_type:
            continue
        matched_day_rows.append(row)
        enabled = row.get("enabled")
        if enabled is not None and not bool(enabled):
            disabled_rows += 1
            continue
        if time_in_window(observed_at, row):
            gate.update(
                {
                    "allowed": True,
                    "reason": "within_routine_window",
                    "dayType": current_day_type,
                    "matchedWindowId": str(row.get("id") or ""),
                    "matchedWindowType": window_type,
                }
            )
            return gate

    gate["dayType"] = explicit_day_type if explicit_day_type in DAY_TYPES else resolved_day_type
    if matched_day_rows and disabled_rows == len(matched_day_rows):
        gate["reason"] = "routine_window_disabled"
    elif not matched_day_rows:
        gate["reason"] = "routine_window_missing"
    return gate


def resolve_meal_window_active(
    *,
    routine_windows: Sequence[Mapping[str, Any]],
    capability_config: Mapping[str, Any] | None = None,
    observed_at: int,
    explicit_day_type: str | None = None,
) -> bool:
    """Return True when meal_habit critical window is active.

    Routine windows are the sole primary source for meal timing.
    Capability ``timeWindows`` only narrows which routine window types are
    considered; it does not provide a second independent schedule fallback.
    """
    gate = routine_window_gate(
        scenario=CARE_SCENARIO_MEAL_HABIT,
        capability_config=capability_config or {},
        routine_windows=routine_windows,
        explicit_day_type=explicit_day_type,
        observed_at=observed_at,
    )
    return bool(gate.get("allowed"))


def window_types_for_scenario(scenario: str, capability_config: Mapping[str, Any]) -> set[str]:
    allowed = set(SCENARIO_ROUTINE_WINDOW_TYPES.get(scenario, set()))
    configured = set(json_list(capability_config.get("time_windows") or capability_config.get("timeWindows")))
    if configured:
        return allowed & configured
    return allowed


def time_in_window(observed_at: int, row: Mapping[str, Any]) -> bool:
    zone = zone_info(str(row.get("timezone") or DEFAULT_TIMEZONE))
    local_time = datetime.fromtimestamp(observed_at / 1000, tz=zone).time()
    start_time = parse_clock(str(row.get("start_time") or row.get("startTime") or ""))
    end_time = parse_clock(str(row.get("end_time") or row.get("endTime") or ""))
    if start_time is None or end_time is None:
        return False
    if start_time <= end_time:
        return start_time <= local_time <= end_time
    return local_time >= start_time or local_time <= end_time


def parse_clock(value: str) -> time | None:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(int(hour_text), int(minute_text))
    except (TypeError, ValueError):
        return None


def zone_info(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone or DEFAULT_TIMEZONE)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item)]


def routine_rows_to_mappings(rows: Sequence[DatabaseRow]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]
