from __future__ import annotations

import re
from typing import Mapping

from services.observation_semantic_dedupe import semantic_dedupe_key
from services.observation_session_state import session_snapshot_from_observation
from services.vision_observation_enrich import (
    enrich_observation,
    has_toys_on_table,
    is_cleanup_activity,
    is_homework_like,
    is_meal_scene,
    is_remindable_screen_device,
    is_toy_play_scene,
    meal_standing_detected,
    play_safety_reason,
    screen_use_sustained,
    structured_screen_active,
)


POSTURE_RISK_VALUES = {"bad_posture", "leaning_too_close", "low_head", "slouching"}
TOY_CLEANUP_RE = re.compile(r"(收玩具|整理玩具|收拾玩具|玩具盒|放回|归位)")
TOY_CLEANUP_DONE_RE = re.compile(r"(玩具已收好|已经收好|收纳完成|玩具归位|整理好了|整齐)")
TOY_LEFT_RE = re.compile(r"(离开[^，。,.]{0,12}(玩具|玩具区)|玩具[^，。,.]{0,18}(还在|散落|没收|未收))")
PLAYING_TOYS_RE = re.compile(r"(玩玩具|玩积木|搭积木|摆弄玩具|操作玩具|playing with toys)")
TOY_NEGATION_RE = re.compile(r"(没有|没|未|未见|看不到|没有看到)[^，。,.]{0,18}(玩具|积木|toy|toys)")
POSTURE_RE = re.compile(r"(低头|头低|趴桌|身体前倾|弯腰|离[^，。,.]{0,8}(桌|书|纸)[^，。,.]{0,8}(近|太近|过近))")
MEAL_DISTRACTION_RE = re.compile(r"(玩玩具|玩耍|玩食物|分心|离开餐桌|走开|跑开)")

SIGNAL_PRIORITY = {
    "meal_toys_on_table": 1,
    "meal_standing_on_chair": 2,
    "meal_attention_shifted": 3,
    "meal_eating_observed": 3,
    "toy_play_unsafe_climbing": 4,
    "toy_play_unsafe_elevated": 5,
    "toy_play_unsafe_throwing": 6,
    "toy_play_unsafe_mouth": 7,
    "bad_posture": 8,
    "leaning_too_close": 8,
    "low_head": 8,
    "slouching": 8,
    "posture_risk": 8,
    "child_left_toys_uncollected": 9,
    "cleanup_started": 10,
    "cleanup_done": 11,
    "toy_playing_observed": 12,
    "screen_use_observed": 12,
    "screen_use_sustained": 8,
    "screen_distance_risk": 7,
    "child_not_visible": 13,
}


def build_source_event_id(
    *,
    device_id: str,
    scenario: str,
    window_start_ms: int,
    window_end_ms: int,
    signal_type: str,
    source: str = "ai_camera_test",
) -> str:
    return f"{source}:{device_id}:{scenario}:{window_start_ms}:{window_end_ms}:{signal_type}"


def build_primary_payload(
    analysis: Mapping[str, object],
    *,
    family_id: str,
    child_id: str,
    device_id: str,
    source: str,
    window_start_ms: int,
    window_end_ms: int,
    observed_at: int,
) -> dict | None:
    enriched = enrich_observation(dict(analysis))
    candidates = scenario_signals(enriched)
    if not candidates:
        return None
    scenario, signal_type, signal_value, summary = min(
        candidates,
        key=lambda item: SIGNAL_PRIORITY.get(item[1], 99),
    )
    duration_seconds = max(1, int((window_end_ms - window_start_ms) / 1000))
    confidence = _score(enriched.get("confidence"))
    session = session_snapshot_from_observation(enriched)
    raw_detail = raw_detail_from_analysis(enriched)
    raw_detail["session_bucket"] = session["bucket"]
    raw_detail["session_risk"] = session["risk"]
    payload_without_key = {
        "scenario": scenario,
        "signals": [{"signalType": signal_type}],
        "rawDetail": raw_detail,
    }
    raw_detail["semantic_dedupe_key"] = semantic_dedupe_key(payload_without_key)
    record_care_event = signal_type not in {
        "meal_started",
        "cleanup_started",
        "cleanup_done",
    }
    return {
        "familyId": family_id,
        "childId": child_id,
        "deviceId": device_id,
        "scenario": scenario,
        "observedAt": observed_at,
        "confidence": confidence,
        "evidenceType": "snapshot",
        "parentSummary": summary,
        "source": source,
        "sourceEventId": build_source_event_id(
            device_id=device_id,
            scenario=scenario,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            signal_type=signal_type,
            source=source,
        ),
        "recordCareEvent": record_care_event,
        "signals": [
            {
                "signalType": signal_type,
                "signalValue": signal_value,
                "confidence": confidence,
                "durationSeconds": duration_seconds,
                "metadata": signal_metadata(enriched),
            }
        ],
        "rawDetail": raw_detail,
    }


def scenario_signals(analysis: Mapping[str, object]) -> list[tuple[str, str, str, str]]:
    result: list[tuple[str, str, str, str]] = []
    text = analysis_text(analysis)
    has_person = analysis.get("has_person")
    toys_scattered = bool(analysis.get("toys_scattered"))
    playing_toys = (
        str(analysis.get("activity") or "") == "玩玩具" or PLAYING_TOYS_RE.search(text)
    ) and not TOY_NEGATION_RE.search(text)

    if has_person is False:
        result.append(("transition", "child_not_visible", "active", "暂未看到孩子。"))
        return result

    if is_cleanup_activity(analysis):
        result.append(("toy_cleanup", "cleanup_started", "active", "观察到孩子正在收纳玩具。"))
        return result

    if is_toy_play_scene(analysis):
        unsafe = play_safety_reason(analysis)
        if unsafe == "climbing_furniture":
            result.append(("toy_cleanup", "toy_play_unsafe_climbing", "active", "玩玩具时有不安全动作。"))
        elif unsafe == "standing_on_furniture":
            result.append(("toy_cleanup", "toy_play_unsafe_elevated", "active", "玩玩具时有不安全动作。"))
        elif unsafe == "throwing":
            result.append(("toy_cleanup", "toy_play_unsafe_throwing", "active", "玩玩具时有不安全动作。"))
        elif unsafe == "small_parts_mouth":
            result.append(("toy_cleanup", "toy_play_unsafe_mouth", "active", "玩玩具时有不安全动作。"))
        elif playing_toys:
            result.append(("toy_cleanup", "toy_playing_observed", "active", "观察到孩子正在玩玩具。"))
        return result

    if is_meal_scene(analysis):
        if has_toys_on_table(analysis):
            result.append(("meal_habit", "meal_toys_on_table", "active", "餐桌上有玩具，需要先收好。"))
        elif meal_standing_detected(analysis):
            result.append(("meal_habit", "meal_standing_on_chair", "active", "用餐时未坐好。"))
        elif structured_screen_active(analysis):
            result.append(("meal_habit", "meal_attention_shifted", "active", "观察到用餐时分心看屏幕。"))
        elif MEAL_DISTRACTION_RE.search(text):
            result.append(("meal_habit", "meal_attention_shifted", "active", "观察到用餐时注意力离开餐桌。"))
        else:
            result.append(("meal_habit", "meal_eating_observed", "active", "观察到孩子正在用餐。"))
        return result

    structured_phone_active = structured_screen_active(analysis) and is_remindable_screen_device(analysis)
    screen_candidates = _screen_use_candidates(analysis)
    if screen_candidates:
        result.extend(screen_candidates)
        return result

    posture_status = str(analysis.get("posture_status") or "").strip()
    posture_signal = ""
    if posture_status in POSTURE_RISK_VALUES:
        posture_signal = posture_status
    elif bool(analysis.get("bad_posture")):
        posture_signal = "bad_posture"
    elif has_person is True and POSTURE_RE.search(text):
        posture_signal = "posture_risk"
    if has_person is True and posture_signal and is_homework_like(analysis) and not playing_toys and not structured_phone_active:
        result.append(("posture", posture_signal, "active", "观察到坐姿需要留意。"))

    if TOY_CLEANUP_DONE_RE.search(text):
        result.append(("toy_cleanup", "cleanup_done", "recovered", "观察到玩具已经收好。"))
    elif TOY_CLEANUP_RE.search(text):
        result.append(("toy_cleanup", "cleanup_started", "active", "观察到孩子正在收纳玩具。"))
    elif TOY_LEFT_RE.search(text) or (has_person is False and toys_scattered):
        result.append(("toy_cleanup", "child_left_toys_uncollected", "active", "孩子离开后，玩具还没有收好。"))
    elif toys_scattered and not playing_toys:
        result.append(("toy_cleanup", "child_left_toys_uncollected", "active", "观察到玩具还没有收好。"))

    return result


def _screen_use_candidates(analysis: Mapping[str, object]) -> list[tuple[str, str, str, str]]:
    if not structured_screen_active(analysis):
        return []
    if is_remindable_screen_device(analysis):
        if screen_use_sustained(analysis):
            distance_risk = str(analysis.get("screen_distance_risk") or "").strip().lower()
            if distance_risk == "too_close":
                return [
                    (
                        "screen_use",
                        "screen_distance_risk",
                        "active",
                        "观察到孩子长时间近距离看屏幕。",
                    )
                ]
            return [
                (
                    "screen_use",
                    "screen_use_sustained",
                    "active",
                    "观察到孩子持续使用手机或平板。",
                )
            ]
        return [
            (
                "screen_use",
                "screen_use_observed",
                "active",
                "观察到孩子正在看手机或平板。",
            )
        ]
    return [
        (
            "screen_use",
            "screen_use_observed",
            "active",
            "观察到孩子正在看屏幕。",
        )
    ]


def analysis_text(analysis: Mapping[str, object]) -> str:
    return "".join(
        str(analysis.get(key) or "")
        for key in (
            "activity",
            "raw_activity",
            "posture_status",
            "description",
            "decision_reason",
        )
    )


def signal_metadata(analysis: Mapping[str, object]) -> dict:
    return {
        "activity": str(analysis.get("activity") or analysis.get("raw_activity") or "")[:80],
        "method": str(analysis.get("method") or "")[:80],
        "activityStability": _score(analysis.get("activity_stability")),
    }


def raw_detail_from_analysis(analysis: Mapping[str, object]) -> dict:
    allowed_keys = {
        "has_person",
        "activity",
        "raw_activity",
        "bad_posture",
        "posture_status",
        "toys_visible",
        "toys_scattered",
        "toys_on_table",
        "meal_standing",
        "is_meal_scene",
        "meal_etiquette_issue",
        "play_safety_status",
        "play_safety_reason",
        "confidence",
        "description",
        "child_message",
        "decision_reason",
        "activity_history",
        "events",
        "summary",
        "method",
        "activity_stability",
        "vision_cadence",
        "vision_backoff",
        "session_bucket",
        "session_risk",
        "screen_device_visible",
        "screen_device_type",
        "screen_use_active",
        "screen_distance_risk",
        "screen_use_context",
        "screen_use_duration_hint",
        "observation_resample",
    }
    return {
        key: analysis.get(key)
        for key in allowed_keys
        if key in analysis
    }


def _score(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))
