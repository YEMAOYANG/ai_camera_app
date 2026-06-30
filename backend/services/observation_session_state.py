from __future__ import annotations

from typing import Any, Mapping

from services.vision_observation_enrich import (
    is_cleanup_activity,
    is_meal_scene,
    is_remindable_screen_device,
    is_toy_play_scene,
    meal_standing_detected,
    has_toys_on_table,
    play_safety_reason,
    screen_use_sustained,
    structured_screen_active,
)


def session_snapshot_from_observation(obs: Mapping[str, object]) -> dict[str, str]:
    has_person = obs.get("has_person")
    if has_person is False:
        return {"bucket": "absent", "risk": "absent"}

    if is_cleanup_activity(obs):
        return {"bucket": "toy_play", "risk": "cleanup_started"}

    if is_meal_scene(obs):
        if has_toys_on_table(obs):
            return {"bucket": "meal", "risk": "meal_toys_on_table"}
        if meal_standing_detected(obs) or bool(obs.get("meal_standing")):
            return {"bucket": "meal", "risk": "meal_standing"}
        if str(obs.get("meal_etiquette_issue") or "") == "distracted":
            return {"bucket": "meal", "risk": "meal_distracted"}
        return {"bucket": "meal", "risk": "meal_seated"}

    if is_toy_play_scene(obs):
        unsafe = play_safety_reason(obs)
        if unsafe:
            return {"bucket": "toy_play", "risk": f"toy_unsafe_{unsafe}"}
        return {"bucket": "toy_play", "risk": "toy_playing_safe"}

    if structured_screen_active(obs):
        device_type = str(obs.get("screen_device_type") or "unknown").strip().lower()
        if is_remindable_screen_device(obs):
            if screen_use_sustained(obs):
                distance_risk = str(obs.get("screen_distance_risk") or "").strip().lower()
                if distance_risk == "too_close":
                    return {"bucket": "screen_use", "risk": "screen_distance_risk"}
                return {"bucket": "screen_use", "risk": "screen_use_sustained"}
            return {"bucket": "screen_use", "risk": "screen_use_brief"}
        return {"bucket": "screen_use", "risk": f"screen_{device_type}"}

    activity = str(obs.get("activity") or obs.get("raw_activity") or "").strip()
    if activity in {"写作业/看书", "看书", "写作业"}:
        return {"bucket": "homework", "risk": str(obs.get("posture_status") or "none")}
    if activity in {"走动", "离开"}:
        return {"bucket": "walk", "risk": activity}
    return {"bucket": "other", "risk": activity or "none"}


def risk_escalated(previous: Mapping[str, str], current: Mapping[str, str]) -> bool:
    priority = {
        "meal_seated": 1,
        "meal_distracted": 2,
        "meal_standing": 3,
        "meal_toys_on_table": 4,
        "toy_playing_safe": 1,
    }
    if previous.get("bucket") != current.get("bucket"):
        return True
    previous_risk = str(previous.get("risk") or "none")
    current_risk = str(current.get("risk") or "none")
    if previous_risk == current_risk:
        return False
    if previous.get("bucket") == "meal":
        return priority.get(current_risk, 0) > priority.get(previous_risk, 0)
    return previous_risk != current_risk


def should_invoke_vision(
    *,
    previous_session: Mapping[str, str],
    current_session: Mapping[str, str],
    frame_stable: bool,
    force_analyze: bool,
) -> bool:
    if force_analyze:
        return True
    if risk_escalated(previous_session, current_session):
        return True
    return not frame_stable


def should_post_observation(
    *,
    previous_session: Mapping[str, Any],
    current_session: Mapping[str, str],
    has_person: object,
    absence_mode: str,
    recorded_absent: bool,
) -> tuple[bool, str]:
    if has_person is False:
        if absence_mode == "absence" and recorded_absent:
            return False, "absent_already_recorded"
        if absence_mode == "absence":
            return True, "absent_first_record"
        return False, "absent_not_confirmed"

    previous_bucket = str(previous_session.get("bucket") or "other")
    if has_person is True and previous_bucket == "absent":
        return True, "absence_recovery"

    previous_risk = str(previous_session.get("risk") or "none")
    current_bucket = str(current_session.get("bucket") or "other")
    current_risk = str(current_session.get("risk") or "none")
    if previous_bucket != current_bucket or previous_risk != current_risk:
        return True, "session_changed"
    return False, "session_stable"


def should_force_screen_use_resample(
    *,
    previous_session: Mapping[str, Any],
    current_session: Mapping[str, str],
    now_ms: int,
    interval_seconds: int = 90,
) -> bool:
    if str(current_session.get("bucket") or "") != "screen_use":
        return False
    last_record = int(previous_session.get("last_record_at") or 0)
    if last_record <= 0:
        return False
    return (now_ms - last_record) >= max(30, interval_seconds) * 1000


def update_session_after_post(session: dict[str, Any], current: Mapping[str, str], *, now_ms: int) -> dict[str, Any]:
    next_session = dict(session)
    next_session.update(current)
    next_session["last_record_at"] = now_ms
    next_session["last_cloud_at"] = now_ms
    return next_session
