from __future__ import annotations

from typing import Any, Mapping

from services.observation_runtime_state import runtime_config


def should_skip_vision_before_analyze(
    absence: Mapping[str, Any],
    *,
    now_ms: int,
    force_analyze: bool,
    prefilter_activity: bool = False,
    prefilter_person: bool | None = None,
    prefilter_blocks_skip: bool = False,
) -> tuple[bool, str]:
    if force_analyze:
        return False, ""
    if prefilter_blocks_skip:
        return False, ""
    if prefilter_person is True:
        return False, ""
    if prefilter_activity:
        return False, ""
    mode = str(absence.get("mode") or "active")
    if mode != "absence":
        return False, ""
    if not bool(absence.get("recorded_absent")):
        return False, ""
    next_check_at = int(absence.get("next_check_at") or 0)
    if next_check_at > now_ms:
        return True, "absence_prefilter_skip"
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


def update_absence_after_prefilter(
    absence: dict[str, Any],
    *,
    person_detected: bool | None,
    now_ms: int,
    frame_stable: bool,
) -> dict[str, Any]:
    if person_detected is True:
        return update_absence_after_analysis(
            absence,
            has_person=True,
            now_ms=now_ms,
            frame_stable=frame_stable,
        )
    if person_detected is False:
        return update_absence_after_analysis(
            absence,
            has_person=False,
            now_ms=now_ms,
            frame_stable=frame_stable,
        )
    return dict(absence)


def absence_needs_kimi(
    absence: Mapping[str, Any],
    *,
    person_detected: bool | None,
    now_ms: int,
) -> bool:
    if person_detected is True:
        return False
    if person_detected is not False:
        return False
    config = runtime_config()
    mode = str(absence.get("mode") or "active")
    if mode != "absence":
        consecutive = int(absence.get("consecutive_no_person") or 0) + 1
        return consecutive >= config["absence_confirm_ticks"]
    if not bool(absence.get("recorded_absent")):
        return True
    return int(absence.get("next_check_at") or 0) <= now_ms


def absence_prefilter_skip(
    absence: Mapping[str, Any],
    *,
    now_ms: int,
    person_detected: bool | None,
) -> tuple[bool, str]:
    if person_detected is True:
        return False, ""
    mode = str(absence.get("mode") or "active")
    if mode != "absence":
        return False, ""
    if not bool(absence.get("recorded_absent")):
        return False, ""
    next_check_at = int(absence.get("next_check_at") or 0)
    if next_check_at > now_ms:
        return True, "absence_prefilter_skip"
    return False, ""
