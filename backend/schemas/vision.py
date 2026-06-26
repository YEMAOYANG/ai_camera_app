from __future__ import annotations

import time
from typing import Any, Mapping

VISION_METHOD = "guardian_kimi_k26"
VISION_METHOD_CACHED = "guardian_kimi_cached"
VISION_METHOD_DISABLED = "vision_not_configured"

RELIABLE_CONFIDENCE_THRESHOLD = 0.65

ALLOWED_ACTIVITIES = frozenset(
    {
        "写作业/看书",
        "看书",
        "写作业",
        "玩玩具",
        "收玩具",
        "看电视",
        "玩手机",
        "吃饭",
        "走动",
        "离开",
        "发呆",
        "其他",
        "未知",
    }
)

POSTURE_STATUSES = frozenset(
    {"ok", "low_head", "leaning_too_close", "slouching", "unknown", "posture_risk", "bad_posture"}
)


def normalize_vision_observation(
    raw: Mapping[str, Any] | None,
    *,
    observed_at: int | None = None,
    method: str = VISION_METHOD,
) -> dict[str, Any]:
    now = observed_at if observed_at is not None else int(time.time() * 1000)
    if not isinstance(raw, dict):
        return _fallback_observation(observed_at=now, method=method)
    activity = str(raw.get("activity") or "").strip()
    raw_activity = str(raw.get("raw_activity") or activity or "").strip()
    if activity and activity not in ALLOWED_ACTIVITIES:
        activity = "其他"
    has_person = raw.get("has_person")
    if has_person is not None:
        has_person = bool(has_person)
    confidence = _clamp_score(raw.get("confidence"))
    posture_status = str(raw.get("posture_status") or "unknown").strip() or "unknown"
    if posture_status not in POSTURE_STATUSES:
        posture_status = "unknown"
    return {
        "has_person": has_person,
        "activity": activity,
        "raw_activity": raw_activity,
        "description": str(raw.get("description") or "")[:180],
        "confidence": confidence,
        "observed_at": int(raw.get("observed_at") or now),
        "method": str(raw.get("method") or method),
        "posture_status": posture_status,
        "bad_posture": bool(raw.get("bad_posture")),
        "toys_visible": bool(raw.get("toys_visible")),
        "toys_scattered": bool(raw.get("toys_scattered")),
        "homework_like": bool(raw.get("homework_like")),
        "child_message": str(raw.get("child_message") or "")[:120],
        "activity_stability": _clamp_score(raw.get("activity_stability") or 1.0),
    }


def _fallback_observation(*, observed_at: int, method: str, reason: str = "") -> dict[str, Any]:
    payload = normalize_vision_observation(
        {
            "has_person": None,
            "activity": "",
            "raw_activity": "",
            "description": reason or "暂时无法识别画面内容。",
            "confidence": 0.0,
            "posture_status": "unknown",
            "bad_posture": False,
            "toys_visible": False,
            "toys_scattered": False,
            "homework_like": False,
            "child_message": "",
            "activity_stability": 0.0,
        },
        observed_at=observed_at,
        method=method,
    )
    return payload


def insufficient_observation(*, reason: str = "vision_not_configured", observed_at: int | None = None) -> dict[str, Any]:
    now = observed_at if observed_at is not None else int(time.time() * 1000)
    return _fallback_observation(observed_at=now, method=VISION_METHOD_DISABLED, reason=reason)


def observation_is_reliable(*, has_person: object, confidence: object) -> bool:
    if has_person not in (True, False):
        return False
    try:
        score = float(confidence or 0)
    except (TypeError, ValueError):
        return False
    return score >= RELIABLE_CONFIDENCE_THRESHOLD


def with_observation_reliability(observation: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(observation)
    has_person = payload.get("has_person", payload.get("hasPerson"))
    payload["isReliable"] = observation_is_reliable(
        has_person=has_person,
        confidence=payload.get("confidence"),
    )
    return payload


def _clamp_score(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))
