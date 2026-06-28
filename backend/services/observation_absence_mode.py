from __future__ import annotations

from typing import Any, Mapping

from services.observation_runtime_state import runtime_config


def should_skip_vision_before_analyze(
    absence: Mapping[str, Any],
    *,
    now_ms: int,
    frame_stable: bool,
    force_analyze: bool,
) -> tuple[bool, str]:
    if force_analyze:
        return False, ""
    mode = str(absence.get("mode") or "active")
    if mode != "absence":
        return False, ""
    next_check_at = int(absence.get("next_check_at") or 0)
    if next_check_at > now_ms:
        if frame_stable:
            return True, "absence_stable_skip"
        return False, ""
    return False, ""


def update_absence_after_analysis(
    absence: dict[str, Any],
    *,
    has_person: object,
    now_ms: int,
    frame_stable: bool,
) -> dict[str, Any]:
    config = runtime_config()
    next_absence = dict(absence)
    if has_person is True:
        next_absence.update(
            {
                "mode": "active",
                "consecutive_no_person": 0,
                "absence_started_at": 0,
                "next_check_at": 0,
                "recorded_absent": False,
            }
        )
        return next_absence

    if has_person is not False:
        return next_absence

    consecutive = int(next_absence.get("consecutive_no_person") or 0) + 1
    next_absence["consecutive_no_person"] = consecutive
    if consecutive < config["absence_confirm_ticks"]:
        next_absence["mode"] = "active"
        next_absence["next_check_at"] = 0
        return next_absence

    if str(next_absence.get("mode") or "") != "absence":
        next_absence["mode"] = "absence"
        next_absence["absence_started_at"] = now_ms

    absence_started_at = int(next_absence.get("absence_started_at") or now_ms)
    elapsed_seconds = max(0, (now_ms - absence_started_at) // 1000)
    interval = config["absence_check_interval_seconds"]
    if elapsed_seconds >= config["absence_long_after_seconds"]:
        interval = config["absence_long_interval_seconds"]
    if frame_stable and int(next_absence.get("next_check_at") or 0) > now_ms:
        return next_absence
    next_absence["next_check_at"] = now_ms + interval * 1000
    return next_absence


def should_write_absent_record(
    absence: Mapping[str, Any],
    *,
    has_person: object,
) -> bool:
    if has_person is not False:
        return has_person is True
    if str(absence.get("mode") or "") != "absence":
        return False
    return not bool(absence.get("recorded_absent"))


def mark_absent_recorded(absence: dict[str, Any]) -> dict[str, Any]:
    next_absence = dict(absence)
    next_absence["recorded_absent"] = True
    return next_absence
