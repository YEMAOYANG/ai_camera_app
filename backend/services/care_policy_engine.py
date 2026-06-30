from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
import json
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from core.database import DatabaseRow
from models.care import (
    CARE_SCENARIO_BEDTIME,
    CARE_SCENARIO_LABELS,
    CARE_SCENARIO_MEAL_HABIT,
    CARE_SCENARIO_MEAL_START,
    CARE_SCENARIO_NAP_TIME,
    CARE_SCENARIO_POSTURE,
    CARE_SCENARIO_SCREEN_USE,
    CARE_SCENARIO_TOY_CLEANUP,
    CARE_SCENARIO_TRANSITION,
    CARE_SCENARIO_WAKE_UP,
    DAY_TYPES,
    REMINDER_DECISION_ALLOWED,
    REMINDER_DECISION_PARENT_NOTIFY,
    REMINDER_DECISION_RECORD_ONLY,
    REMINDER_DECISION_SKIPPED_CONTINUITY,
    REMINDER_DECISION_SKIPPED_COOLDOWN,
    REMINDER_DECISION_SKIPPED_DAILY_LIMIT,
    REMINDER_DECISION_SKIPPED_DISABLED,
    REMINDER_DECISION_SKIPPED_LOW_CONFIDENCE,
    REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
    REMINDER_EVENT_SOURCE_DRY_RUN,
    REMINDER_EVENT_SOURCE_TEST,
    REMINDER_STATUS_COMMAND_SENT,
    REMINDER_STATUS_DELIVERED,
    REMINDER_STATUS_FAILED,
    REVIEW_DOMAIN_CARE,
)
from services.care_day_type import effective_day_type
from services.care_routine_window_resolver import (
    DEFAULT_TIMEZONE,
    routine_window_gate,
    window_types_for_scenario,
)
REVIEW_ITEM_TYPE_PARENT_NOTIFY = "care_parent_notify"

RESET_SIGNAL_VALUES = {"recovered", "cleared", "inactive"}
NON_ACTIONABLE_SIGNAL_TYPES = {
    "toy_playing_observed",
    "cleanup_started",
    "cleanup_done",
    "toys_put_away",
    "meal_started",
    "child_at_table",
    "meal_finished",
    "child_not_visible",
    "child_visible",
    "meal_eating_observed",
    "screen_use_observed",
    "ok",
    "unknown",
    "seated",
    "posture_recovered",
    "in_bed",
    "lights_out_or_quiet",
    "wake_up_detected",
}


@dataclass(frozen=True)
class CarePolicyDecision:
    decision: str
    reason: str
    should_speak: bool
    should_notify_parent: bool
    cooldown_until: int | None
    reminder_level: str
    policy_snapshot_json: str
    review_item: dict[str, Any] | None = None


class CarePolicyEngine:
    def decide(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        observation_event: DatabaseRow,
        behavior_signals: list[DatabaseRow],
        capability_config: DatabaseRow | None,
        current_behavior_state: DatabaseRow | None,
        recent_reminder_events: list[DatabaseRow],
        recent_allowed_decisions: list[DatabaseRow],
        routine_windows: list[DatabaseRow] | None = None,
        day_type: str | None = None,
        now: int,
    ) -> CarePolicyDecision:
        del family_id, child_id, device_id

        observation_score = _float_value(observation_event.get("confidence"))
        consecutive_seconds = _consecutive_seconds(behavior_signals, current_behavior_state)
        real_reminder_events = _real_reminder_events(recent_reminder_events)
        day_start = _start_of_local_day_ms(now)
        daily_real_count = sum(
            1
            for row in real_reminder_events
            if _event_time(row) >= day_start and _reminder_counts_toward_limits(row)
        )

        snapshot: dict[str, Any] = {
            "stage": "stage_2c_policy_engine",
            "scenario": scenario,
            "observationScore": observation_score,
            "consecutiveSeconds": consecutive_seconds,
            "dailyRealReminderCount": daily_real_count,
            "recentAllowedDecisionCount": len(recent_allowed_decisions),
        }

        if capability_config is None or not bool(capability_config.get("enabled")):
            return _decision(
                REMINDER_DECISION_SKIPPED_DISABLED,
                "capability_disabled",
                snapshot,
            )

        cooldown_seconds = _int_value(capability_config.get("cooldown_seconds"), 900)
        daily_limit = _int_value(capability_config.get("daily_limit"), 4)
        parent_notify_threshold = _int_value(
            capability_config.get("parent_notify_threshold"),
            3,
        )
        confidence_threshold = _float_value(
            capability_config.get("confidence_threshold"),
            0.72,
        )
        confidence_threshold = _effective_confidence_threshold(
            scenario=scenario,
            configured_threshold=confidence_threshold,
        )
        min_observation_seconds = _int_value(
            capability_config.get("min_observation_seconds"),
            20,
        )
        primary_signal_type = _primary_signal_type(behavior_signals)
        min_observation_seconds = _effective_min_observation_seconds(
            scenario=scenario,
            signal_type=primary_signal_type,
            configured_seconds=min_observation_seconds,
        )
        cooldown_seconds = _effective_cooldown_seconds(
            scenario=scenario,
            signal_type=primary_signal_type,
            configured_seconds=cooldown_seconds,
        )
        snapshot.update(
            {
                "cooldownSeconds": cooldown_seconds,
                "dailyLimit": daily_limit,
                "parentNotifyThreshold": parent_notify_threshold,
                "confidenceThreshold": confidence_threshold,
                "minObservationSeconds": min_observation_seconds,
                "primarySignalType": primary_signal_type,
                "allowSpeaker": bool(capability_config.get("allow_speaker")),
                "recordOnly": bool(capability_config.get("record_only")),
            }
        )

        if bool(capability_config.get("record_only")):
            return _decision(REMINDER_DECISION_RECORD_ONLY, "capability_record_only", snapshot)

        if observation_score < confidence_threshold:
            return _decision(
                REMINDER_DECISION_SKIPPED_LOW_CONFIDENCE,
                "low_observation_score",
                snapshot,
            )

        signal_reason = _signal_semantic_reason(behavior_signals, current_behavior_state)
        if signal_reason:
            snapshot["signalGateReason"] = signal_reason
            return _decision(
                REMINDER_DECISION_RECORD_ONLY,
                signal_reason,
                snapshot,
            )

        if consecutive_seconds < min_observation_seconds:
            return _decision(
                REMINDER_DECISION_SKIPPED_CONTINUITY,
                "continuous_observation_too_short",
                snapshot,
            )

        delivered_reminder_events = [
            row for row in real_reminder_events if _reminder_counts_toward_limits(row)
        ]
        cooldown_until = _cooldown_until(
            now=now,
            cooldown_seconds=cooldown_seconds,
            recent_reminder_events=delivered_reminder_events,
            recent_allowed_decisions=recent_allowed_decisions,
        )
        if cooldown_until is not None and cooldown_until > now:
            snapshot["cooldownUntil"] = cooldown_until
            return _decision(
                REMINDER_DECISION_SKIPPED_COOLDOWN,
                "cooldown_active",
                snapshot,
                cooldown_until=cooldown_until,
            )

        is_routine = str(observation_event.get("evidence_type") or "") == "routine_window"
        if (
            not is_routine
            and parent_notify_threshold > 0
            and daily_real_count >= parent_notify_threshold
        ):
            review = _review_item(scenario=scenario, observation_event=observation_event)
            return _decision(
                REMINDER_DECISION_PARENT_NOTIFY,
                "parent_notify_threshold_reached",
                snapshot,
                should_notify_parent=True,
                review_item=review,
            )

        if (
            not is_routine
            and (daily_limit <= 0 or daily_real_count >= daily_limit)
        ):
            return _decision(
                REMINDER_DECISION_SKIPPED_DAILY_LIMIT,
                "daily_limit_reached",
                snapshot,
            )

        if not bool(capability_config.get("allow_speaker")):
            return _decision(
                REMINDER_DECISION_RECORD_ONLY,
                "speaker_not_allowed",
                snapshot,
            )

        if scenario in {CARE_SCENARIO_TOY_CLEANUP, CARE_SCENARIO_POSTURE, CARE_SCENARIO_SCREEN_USE}:
            snapshot["routineGate"] = {
                "allowed": True,
                "reason": "behavior_only_scenario",
                "dayType": day_type or "",
                "windowTypes": [],
                "matchedWindowId": "",
            }
            return _decision(
                REMINDER_DECISION_ALLOWED,
                "behavior_policy_allowed",
                snapshot,
                should_speak=_should_speak_for_behavior_signal(primary_signal_type),
            )

        if scenario == CARE_SCENARIO_MEAL_HABIT:
            routine_gate = routine_window_gate(
                scenario=scenario,
                capability_config=capability_config,
                routine_windows=routine_windows or [],
                explicit_day_type=day_type,
                observed_at=_int_value(observation_event.get("observed_at"), now),
            )
            snapshot["routineGate"] = routine_gate
            if not routine_gate["allowed"]:
                return _decision(
                    REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
                    str(routine_gate["reason"]),
                    snapshot,
                )
            return _decision(
                REMINDER_DECISION_ALLOWED,
                "behavior_policy_allowed",
                snapshot,
                should_speak=_should_speak_for_behavior_signal(primary_signal_type),
            )

        routine_gate = routine_window_gate(
            scenario=scenario,
            capability_config=capability_config,
            routine_windows=routine_windows or [],
            explicit_day_type=day_type,
            observed_at=_int_value(observation_event.get("observed_at"), now),
        )
        snapshot["routineGate"] = routine_gate
        if not routine_gate["allowed"]:
            return _decision(
                REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
                str(routine_gate["reason"]),
                snapshot,
            )

        return _decision(
            REMINDER_DECISION_ALLOWED,
            "policy_allowed",
            snapshot,
            should_speak=True,
        )


def _effective_confidence_threshold(
    *,
    scenario: str,
    configured_threshold: float,
) -> float:
    if scenario == CARE_SCENARIO_POSTURE:
        return min(configured_threshold, 0.68)
    return configured_threshold


def _effective_min_observation_seconds(
    *,
    scenario: str,
    signal_type: str,
    configured_seconds: int,
) -> int:
    signal = signal_type.strip().lower()
    if signal == "meal_standing_on_chair":
        return min(configured_seconds, 5)
    if signal == "meal_toys_on_table":
        return min(configured_seconds, 10)
    if signal.startswith("toy_play_unsafe_"):
        return min(configured_seconds, 15)
    if scenario == CARE_SCENARIO_POSTURE:
        return min(configured_seconds, 3)
    if signal == "meal_attention_shifted":
        return min(configured_seconds, 20)
    return configured_seconds


def _effective_cooldown_seconds(
    *,
    scenario: str,
    signal_type: str,
    configured_seconds: int,
) -> int:
    signal = signal_type.strip().lower()
    if signal == "meal_standing_on_chair":
        return min(configured_seconds, 180)
    if signal == "meal_toys_on_table":
        return min(configured_seconds, 600)
    if signal.startswith("toy_play_unsafe_"):
        return min(configured_seconds, 600)
    return configured_seconds


def _primary_signal_type(behavior_signals: list[DatabaseRow]) -> str:
    if not behavior_signals:
        return ""
    return str(behavior_signals[0].get("signal_type") or "").strip()


def _should_speak_for_behavior_signal(signal_type: str) -> bool:
    signal = signal_type.strip().lower()
    if signal in NON_ACTIONABLE_SIGNAL_TYPES:
        return False
    return True


def _decision(
    decision: str,
    reason: str,
    snapshot: Mapping[str, Any],
    *,
    should_speak: bool = False,
    should_notify_parent: bool = False,
    cooldown_until: int | None = None,
    review_item: dict[str, Any] | None = None,
) -> CarePolicyDecision:
    payload = dict(snapshot)
    payload.update(
        {
            "decision": decision,
            "reason": reason,
            "shouldSpeak": should_speak,
            "shouldNotifyParent": should_notify_parent,
        }
    )
    return CarePolicyDecision(
        decision=decision,
        reason=reason,
        should_speak=should_speak,
        should_notify_parent=should_notify_parent,
        cooldown_until=cooldown_until,
        reminder_level="repeat" if should_notify_parent else "gentle",
        policy_snapshot_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        review_item=review_item,
    )


def _review_item(*, scenario: str, observation_event: DatabaseRow) -> dict[str, Any]:
    label = CARE_SCENARIO_LABELS.get(scenario, "看护")
    summary = f"今天已经多次提醒，建议家长看一下{label}情况。"
    return {
        "domain": REVIEW_DOMAIN_CARE,
        "scenario": scenario,
        "itemType": REVIEW_ITEM_TYPE_PARENT_NOTIFY,
        "sourceType": "camera_observation",
        "sourceId": observation_event["id"],
        "priority": "normal",
        "summary": summary,
        "relatedObservationId": observation_event["id"],
        "relatedReminderId": None,
        "taskId": observation_event.get("task_id"),
        "dueAt": None,
    }


def _cooldown_until(
    *,
    now: int,
    cooldown_seconds: int,
    recent_reminder_events: list[DatabaseRow],
    recent_allowed_decisions: list[DatabaseRow],
) -> int | None:
    if cooldown_seconds <= 0:
        return None
    latest = 0
    for row in recent_reminder_events:
        latest = max(latest, _event_time(row))
    for row in recent_allowed_decisions:
        latest = max(latest, _int_value(row.get("created_at"), 0))
    if latest <= 0:
        return None
    until = latest + cooldown_seconds * 1000
    return until if until > now else None


def _real_reminder_events(rows: list[DatabaseRow]) -> list[DatabaseRow]:
    result = []
    for row in rows:
        if bool(row.get("is_test")):
            continue
        if str(row.get("event_source") or "") in {
            REMINDER_EVENT_SOURCE_TEST,
            REMINDER_EVENT_SOURCE_DRY_RUN,
        }:
            continue
        result.append(row)
    return result


def _signal_semantic_reason(
    behavior_signals: list[DatabaseRow],
    current_behavior_state: DatabaseRow | None,
) -> str:
    signals = behavior_signals or []
    if not signals and current_behavior_state is not None:
        status = str(current_behavior_state.get("status") or "").strip().lower()
        if status in RESET_SIGNAL_VALUES:
            return "signal_recovered_or_inactive"
        return ""

    has_actionable_signal = False
    for row in signals:
        signal_type = str(row.get("signal_type") or "").strip().lower()
        signal_value = str(row.get("signal_value") or "").strip().lower()
        if signal_type in RESET_SIGNAL_VALUES or signal_value in RESET_SIGNAL_VALUES:
            return "signal_recovered_or_inactive"
        if signal_type in NON_ACTIONABLE_SIGNAL_TYPES or signal_value in NON_ACTIONABLE_SIGNAL_TYPES:
            continue
        has_actionable_signal = True
    if signals and not has_actionable_signal:
        return "signal_positive_or_in_progress"
    return ""


def _reminder_counts_toward_limits(row: DatabaseRow) -> bool:
    status = str(row.get("delivery_status") or "")
    if status == REMINDER_STATUS_FAILED:
        return False
    return status in {REMINDER_STATUS_COMMAND_SENT, REMINDER_STATUS_DELIVERED}


def _json_list(value: object) -> list[str]:
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


def _consecutive_seconds(
    behavior_signals: list[DatabaseRow],
    current_behavior_state: DatabaseRow | None,
) -> int:
    signal_seconds = [
        _int_value(row.get("duration_seconds"), 0)
        for row in behavior_signals
    ]
    state_seconds = (
        _int_value(current_behavior_state.get("consecutive_seconds"), 0)
        if current_behavior_state is not None
        else 0
    )
    return max(signal_seconds + [state_seconds, 0])


def _event_time(row: DatabaseRow) -> int:
    return _int_value(row.get("generated_at"), _int_value(row.get("created_at"), 0))


def _start_of_local_day_ms(now: int, timezone: str = DEFAULT_TIMEZONE) -> int:
    zone = ZoneInfo(timezone)
    dt = datetime.fromtimestamp(now / 1000, tz=zone)
    start = datetime.combine(dt.date(), time.min, tzinfo=zone)
    return int(start.timestamp() * 1000)


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_value(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
