from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from models.care import (
    CARE_SCENARIO_MEAL_HABIT,
    CARE_SCENARIO_POSTURE,
    CARE_SCENARIO_SCREEN_USE,
    CARE_SCENARIO_TOY_CLEANUP,
)
from services.care_routine_window_resolver import resolve_meal_window_active
from services.vision_observation_enrich import has_structured_screen_fields, structured_screen_active
from services.vision_prefilter_service import PrefilterResult

TOY_SESSION_ACTIVE = {"playing", "toys_visible", "scattered", "play"}

POSTURE_MONITOR_CONTEXTS = frozenset(
    {"desk", "homework", "reading", "study", "screen", "writing", "homework_study"}
)
POSTURE_MONITOR_ACTIVITIES = frozenset({"写作业", "看书", "写作业/看书", "写字"})
POSTURE_MONITOR_RAW_ACTIVITIES = frozenset({"写字", "阅读", "看书", "写作业"})

GATE_UNKNOWN = "unknown"
GATE_EMPTY_CANDIDATE = "empty_candidate"
GATE_EMPTY_STABLE = "empty_stable"
GATE_PERSON_CANDIDATE = "person_candidate"
GATE_PERSON_STABLE = "person_stable"
GATE_MOTION_ACTIVE = "motion_active"
GATE_PERSON_LEFT_CANDIDATE = "person_left_candidate"


@dataclass(frozen=True)
class CloudGateConfig:
    tick_interval_seconds: float = 10.0
    empty_heartbeat_seconds: int = 1800
    person_heartbeat_seconds: int = 900
    motion_cooldown_seconds: int = 300
    motion_threshold: float = 0.02
    person_enter_debounce_ticks: int = 2
    person_leave_debounce_ticks: int = 2
    motion_exit_debounce_ticks: int = 2
    person_enter_confidence: float = 0.45
    person_exit_confidence: float = 0.35
    confirm_person_leave: bool = False
    posture_interval_seconds: int = 60
    toy_cleanup_interval_seconds: int = 60
    meal_habit_interval_seconds: int = 120
    screen_use_interval_seconds: int = 90
    enable_unsafe_toy_critical: bool = True


@dataclass(frozen=True)
class CloudGateDecision:
    call_kimi: bool
    reason: str
    lane: str
    next_cloud_gate: dict[str, Any]
    next_care_behavior: dict[str, Any] | None = None
    observation_context_invalid: bool = False


def cloud_gate_config() -> CloudGateConfig:
    return CloudGateConfig(
        tick_interval_seconds=float(os.getenv("CAMERA_OBSERVATION_INTERVAL_SECONDS", "10")),
        empty_heartbeat_seconds=int(os.getenv("APP_CLOUD_EMPTY_HEARTBEAT_SECONDS", "1800")),
        person_heartbeat_seconds=int(os.getenv("APP_CLOUD_PERSON_HEARTBEAT_SECONDS", "900")),
        motion_cooldown_seconds=int(os.getenv("APP_CLOUD_MOTION_COOLDOWN_SECONDS", "300")),
        motion_threshold=float(os.getenv("APP_CLOUD_MOTION_THRESHOLD", "0.02")),
        person_enter_debounce_ticks=int(os.getenv("APP_CLOUD_PERSON_ENTER_DEBOUNCE_TICKS", "2")),
        person_leave_debounce_ticks=int(os.getenv("APP_CLOUD_PERSON_LEAVE_DEBOUNCE_TICKS", "2")),
        motion_exit_debounce_ticks=int(os.getenv("APP_CLOUD_MOTION_EXIT_DEBOUNCE_TICKS", "2")),
        person_enter_confidence=float(os.getenv("APP_CLOUD_PERSON_ENTER_CONFIDENCE", "0.45")),
        person_exit_confidence=float(os.getenv("APP_CLOUD_PERSON_EXIT_CONFIDENCE", "0.35")),
        confirm_person_leave=str(os.getenv("APP_CLOUD_CONFIRM_PERSON_LEAVE", "0")).strip().lower()
        in {"1", "true", "yes", "on"},
        posture_interval_seconds=int(os.getenv("APP_CLOUD_POSTURE_INTERVAL_SECONDS", "60")),
        toy_cleanup_interval_seconds=int(os.getenv("APP_CLOUD_TOY_CLEANUP_INTERVAL_SECONDS", "60")),
        meal_habit_interval_seconds=int(os.getenv("APP_CLOUD_MEAL_HABIT_INTERVAL_SECONDS", "120")),
        screen_use_interval_seconds=int(os.getenv("APP_CLOUD_SCREEN_USE_INTERVAL_SECONDS", "90")),
        enable_unsafe_toy_critical=str(os.getenv("APP_CLOUD_ENABLE_UNSAFE_TOY_CRITICAL", "1")).strip().lower()
        in {"1", "true", "yes", "on"},
    )


def default_cloud_gate_state() -> dict[str, Any]:
    return {
        "gate_state": GATE_UNKNOWN,
        "person_enter_debounce": 0,
        "person_leave_debounce": 0,
        "motion_exit_debounce": 0,
        "motion_active": False,
        "last_motion_active": False,
        "last_person_detected": None,
        "empty_stable_since_ms": 0,
        "person_stable_since_ms": 0,
        "last_kimi_at_ms": 0,
        "last_motion_kimi_at_ms": 0,
        "last_kimi_reason": "",
        "last_empty_heartbeat_at_ms": 0,
        "last_person_heartbeat_at_ms": 0,
    }


def default_care_behavior_state() -> dict[str, Any]:
    return {
        "last_toy_session": "",
        "toys_scattered_last": False,
        "toys_visible_last": False,
        "last_posture_context": "",
        "last_kimi_activity": "",
        "last_kimi_raw_activity": "",
        "cleanup_phase": "none",
        "last_critical_kimi_at_ms": 0,
        "last_critical_reason": "",
        "last_posture_kimi_at_ms": 0,
        "last_meal_habit_kimi_at_ms": 0,
        "last_screen_use_kimi_at_ms": 0,
        "last_screen_use_signature": "",
        "screen_context_changed": False,
    }


def evaluate_cloud_gate(
    *,
    prefilter: PrefilterResult,
    prefilter_previous: Mapping[str, Any] | None,
    cloud_gate: Mapping[str, Any] | None,
    care_behavior: Mapping[str, Any] | None,
    now_ms: int,
    force_analyze: bool = False,
    child_id: str = "",
    family_id: str = "",
    device_id: str = "",
    enabled_capabilities: Sequence[Mapping[str, Any]] | None = None,
    routine_windows: Sequence[Mapping[str, Any]] | None = None,
    meal_capability_config: Mapping[str, Any] | None = None,
    explicit_day_type: str | None = None,
) -> CloudGateDecision:
    del family_id, device_id
    behavior = dict(care_behavior or default_care_behavior_state())
    gate = dict(cloud_gate or default_cloud_gate_state())

    if not str(child_id or "").strip():
        return CloudGateDecision(
            call_kimi=False,
            reason="missing_child_id",
            lane="context",
            next_cloud_gate=gate,
            next_care_behavior=behavior,
            observation_context_invalid=True,
        )

    if force_analyze:
        return CloudGateDecision(
            call_kimi=True,
            reason="force_analyze",
            lane="manual",
            next_cloud_gate=gate,
            next_care_behavior=behavior,
        )

    config = cloud_gate_config()
    general = evaluate_general_lane(
        prefilter=prefilter,
        prefilter_previous=prefilter_previous,
        cloud_gate=cloud_gate,
        now_ms=now_ms,
        config=config,
    )
    if general.call_kimi:
        return CloudGateDecision(
            call_kimi=general.call_kimi,
            reason=general.reason,
            lane=general.lane,
            next_cloud_gate=general.next_cloud_gate,
            next_care_behavior=behavior,
        )

    meal_window_active = resolve_meal_window_active(
        routine_windows=routine_windows or [],
        capability_config=meal_capability_config,
        observed_at=now_ms,
        explicit_day_type=explicit_day_type,
    )
    critical = evaluate_care_critical_lane(
        prefilter=prefilter,
        prefilter_previous=prefilter_previous,
        cloud_gate=general.next_cloud_gate,
        care_behavior=behavior,
        general_decision=general,
        now_ms=now_ms,
        config=config,
        enabled_capabilities=enabled_capabilities,
        meal_window_active=meal_window_active,
    )
    if critical is not None:
        return critical

    return CloudGateDecision(
        call_kimi=general.call_kimi,
        reason=general.reason,
        lane=general.lane,
        next_cloud_gate=general.next_cloud_gate,
        next_care_behavior=behavior,
    )


def evaluate_care_critical_lane(
    *,
    prefilter: PrefilterResult,
    prefilter_previous: Mapping[str, Any] | None,
    cloud_gate: Mapping[str, Any],
    care_behavior: dict[str, Any],
    general_decision: CloudGateDecision,
    now_ms: int,
    config: CloudGateConfig,
    enabled_capabilities: Sequence[Mapping[str, Any]] | None,
    meal_window_active: bool,
) -> CloudGateDecision | None:
    if not prefilter.prefilter_ready:
        return None

    person_present = _person_present(prefilter, config)
    previous = prefilter_previous or {}
    motion_now = _motion_active(prefilter, config)
    motion_before = _previous_motion_active(previous, config)
    motion_started = motion_now and not motion_before
    gate = dict(cloud_gate)

    if _capability_enabled(enabled_capabilities, CARE_SCENARIO_TOY_CLEANUP):
        if general_decision.reason == "cloud_gate_person_leave_lightweight" and has_structured_toy_context(
            care_behavior
        ):
            return _critical_decision(
                gate=gate,
                behavior=care_behavior,
                now_ms=now_ms,
                reason="toy_cleanup_leave",
            )

        if (
            config.enable_unsafe_toy_critical
            and motion_started
            and person_present
            and has_structured_toy_context(care_behavior)
            and _motion_cooldown_elapsed(gate, now_ms, config)
        ):
            return _critical_decision(
                gate=gate,
                behavior=care_behavior,
                now_ms=now_ms,
                reason="toy_unsafe_motion",
            )

    if _capability_enabled(enabled_capabilities, CARE_SCENARIO_POSTURE) and person_present:
        screen_use_enabled = _capability_enabled(enabled_capabilities, CARE_SCENARIO_SCREEN_USE)
        screen_monitor_active = screen_use_enabled and has_screen_use_monitor_context(care_behavior)
        if not screen_monitor_active and has_posture_monitor_context(care_behavior):
            last_posture = int(care_behavior.get("last_posture_kimi_at_ms") or 0)
            if (now_ms - last_posture) >= config.posture_interval_seconds * 1000:
                return _critical_decision(
                    gate=gate,
                    behavior=care_behavior,
                    now_ms=now_ms,
                    reason="posture_interval",
                    posture=True,
                )

    if (
        _capability_enabled(enabled_capabilities, CARE_SCENARIO_MEAL_HABIT)
        and meal_window_active
        and person_present
    ):
        last_meal = int(care_behavior.get("last_meal_habit_kimi_at_ms") or 0)
        if (now_ms - last_meal) >= config.meal_habit_interval_seconds * 1000:
            return _critical_decision(
                gate=gate,
                behavior=care_behavior,
                now_ms=now_ms,
                reason="meal_habit_interval",
                meal_habit=True,
            )

    if _capability_enabled(enabled_capabilities, CARE_SCENARIO_SCREEN_USE) and person_present:
        if bool(care_behavior.get("screen_context_changed")):
            return _critical_decision(
                gate=gate,
                behavior=care_behavior,
                now_ms=now_ms,
                reason="screen_use_context_change",
                screen_use=True,
                clear_screen_context_change=True,
            )
        if has_screen_use_monitor_context(care_behavior):
            last_screen = int(care_behavior.get("last_screen_use_kimi_at_ms") or 0)
            if (now_ms - last_screen) >= config.screen_use_interval_seconds * 1000:
                return _critical_decision(
                    gate=gate,
                    behavior=care_behavior,
                    now_ms=now_ms,
                    reason="screen_use_interval",
                    screen_use=True,
                )

    return None


def has_structured_toy_context(behavior: Mapping[str, Any]) -> bool:
    session = str(behavior.get("last_toy_session") or "").strip().lower()
    if session in TOY_SESSION_ACTIVE:
        return True
    if bool(behavior.get("toys_scattered_last")):
        return True
    if bool(behavior.get("toys_visible_last")):
        return True
    return False


def has_posture_monitor_context(behavior: Mapping[str, Any]) -> bool:
    context = str(behavior.get("last_posture_context") or "").strip().lower()
    if context in POSTURE_MONITOR_CONTEXTS:
        return True
    activity = str(behavior.get("last_kimi_activity") or "").strip()
    if activity in POSTURE_MONITOR_ACTIVITIES:
        return True
    raw_activity = str(behavior.get("last_kimi_raw_activity") or "").strip()
    return raw_activity in POSTURE_MONITOR_RAW_ACTIVITIES


def has_screen_use_monitor_context(behavior: Mapping[str, Any]) -> bool:
    signature = str(behavior.get("last_screen_use_signature") or "").strip().lower()
    return signature.endswith(":active")


def screen_use_signature(analysis: Mapping[str, Any]) -> str:
    if not has_structured_screen_fields(analysis):
        return ""
    device_type = str(analysis.get("screen_device_type") or "unknown").strip().lower() or "unknown"
    if not bool(analysis.get("screen_device_visible")) or not bool(analysis.get("screen_use_active")):
        return f"{device_type}:inactive"
    return f"{device_type}:active"


def posture_context_from_analysis(analysis: Mapping[str, Any]) -> str:
    if structured_screen_active(analysis):
        return ""
    activity = str(analysis.get("activity") or "").strip()
    raw_activity = str(analysis.get("raw_activity") or "").strip()
    if activity in {"写作业", "写作业/看书"} or raw_activity in {"写字", "写作业"}:
        return "homework"
    if activity == "看书" or raw_activity in {"阅读", "看书"}:
        return "reading"
    if activity in {"玩手机", "看电视"}:
        return "screen"
    return ""


def sync_care_behavior_from_analysis(
    behavior: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    """Update structured toy/screen context from Kimi analysis; never infer from description."""
    next_behavior = dict(behavior)
    toys_visible = bool(analysis.get("toys_visible"))
    toys_scattered = bool(analysis.get("toys_scattered"))
    activity = str(analysis.get("activity") or analysis.get("raw_activity") or "").strip()
    raw_activity = str(analysis.get("raw_activity") or "").strip()
    next_behavior["last_kimi_activity"] = activity
    next_behavior["last_kimi_raw_activity"] = raw_activity
    posture_context = posture_context_from_analysis(analysis)
    if posture_context:
        next_behavior["last_posture_context"] = posture_context
    elif structured_screen_active(analysis):
        next_behavior["last_posture_context"] = ""
    signature = screen_use_signature(analysis)
    previous_signature = str(next_behavior.get("last_screen_use_signature") or "")
    if signature:
        if signature != previous_signature and previous_signature and (
            signature.endswith(":active") or previous_signature.endswith(":active")
        ):
            next_behavior["screen_context_changed"] = True
        next_behavior["last_screen_use_signature"] = signature
    elif previous_signature:
        next_behavior["last_screen_use_signature"] = ""
        if previous_signature.endswith(":active"):
            next_behavior["screen_context_changed"] = True
    next_behavior["toys_visible_last"] = toys_visible
    next_behavior["toys_scattered_last"] = toys_scattered
    if activity == "玩玩具":
        next_behavior["last_toy_session"] = "playing"
    elif toys_scattered:
        next_behavior["last_toy_session"] = "scattered"
    elif toys_visible:
        next_behavior["last_toy_session"] = "toys_visible"
    return next_behavior


def _capability_enabled(
    enabled_capabilities: Sequence[Mapping[str, Any]] | None,
    scenario: str,
) -> bool:
    for row in enabled_capabilities or []:
        if str(row.get("scenario") or "") != scenario:
            continue
        return bool(row.get("enabled"))
    return False


def _critical_decision(
    *,
    gate: dict[str, Any],
    behavior: dict[str, Any],
    now_ms: int,
    reason: str,
    posture: bool = False,
    meal_habit: bool = False,
    screen_use: bool = False,
    clear_screen_context_change: bool = False,
) -> CloudGateDecision:
    behavior["last_critical_kimi_at_ms"] = now_ms
    behavior["last_critical_reason"] = reason
    if posture:
        behavior["last_posture_kimi_at_ms"] = now_ms
    if meal_habit:
        behavior["last_meal_habit_kimi_at_ms"] = now_ms
    if screen_use:
        behavior["last_screen_use_kimi_at_ms"] = now_ms
    if clear_screen_context_change:
        behavior["screen_context_changed"] = False
    gate["last_kimi_at_ms"] = now_ms
    gate["last_kimi_reason"] = reason
    if reason == "toy_unsafe_motion":
        gate["last_motion_kimi_at_ms"] = now_ms
    return CloudGateDecision(
        call_kimi=True,
        reason=reason,
        lane="care_critical",
        next_cloud_gate=gate,
        next_care_behavior=behavior,
    )


def evaluate_general_lane(
    *,
    prefilter: PrefilterResult,
    prefilter_previous: Mapping[str, Any] | None,
    cloud_gate: Mapping[str, Any] | None,
    now_ms: int,
    config: CloudGateConfig | None = None,
) -> CloudGateDecision:
    config = config or cloud_gate_config()
    gate = dict(cloud_gate or default_cloud_gate_state())
    previous = prefilter_previous or {}

    if not prefilter.prefilter_ready:
        gate["gate_state"] = GATE_UNKNOWN
        return CloudGateDecision(
            call_kimi=False,
            reason="prefilter_warming",
            lane="general",
            next_cloud_gate=gate,
        )

    person_present = _person_present(prefilter, config)
    motion_now = _motion_active(prefilter, config)
    motion_before = _previous_motion_active(previous, config)
    motion_started = motion_now and not motion_before
    motion_stopped = (not motion_now) and motion_before

    state = str(gate.get("gate_state") or GATE_UNKNOWN)
    reason = ""
    call_kimi = False

    if state == GATE_UNKNOWN:
        gate, call_kimi, reason = _from_unknown(gate, person_present, now_ms)
    elif state == GATE_EMPTY_CANDIDATE:
        gate, call_kimi, reason = _from_empty_candidate(gate, person_present, now_ms, config)
    elif state == GATE_EMPTY_STABLE:
        gate, call_kimi, reason = _from_empty_stable(
            gate,
            person_present,
            motion_started,
            now_ms,
            config,
        )
    elif state == GATE_PERSON_CANDIDATE:
        gate, call_kimi, reason = _from_person_candidate(gate, person_present, now_ms, config)
    elif state == GATE_PERSON_STABLE:
        gate, call_kimi, reason = _from_person_stable(
            gate,
            person_present,
            motion_started,
            now_ms,
            config,
        )
    elif state == GATE_MOTION_ACTIVE:
        gate, call_kimi, reason = _from_motion_active(
            gate,
            person_present,
            motion_now,
            motion_stopped,
            now_ms,
            config,
        )
    elif state == GATE_PERSON_LEFT_CANDIDATE:
        gate, call_kimi, reason = _from_person_left_candidate(gate, person_present, now_ms, config)
    else:
        gate["gate_state"] = GATE_UNKNOWN

    gate["last_person_detected"] = person_present
    gate["last_motion_active"] = motion_now
    gate["motion_active"] = str(gate.get("gate_state") or "") == GATE_MOTION_ACTIVE

    if call_kimi:
        gate["last_kimi_at_ms"] = now_ms
        gate["last_kimi_reason"] = reason
        if reason in {"person_motion_started", "empty_motion_edge"}:
            gate["last_motion_kimi_at_ms"] = now_ms
        if reason == "empty_heartbeat":
            gate["last_empty_heartbeat_at_ms"] = now_ms
        if reason == "person_heartbeat":
            gate["last_person_heartbeat_at_ms"] = now_ms

    if not call_kimi and not reason:
        reason = f"cloud_gate_{gate.get('gate_state')}"

    return CloudGateDecision(
        call_kimi=call_kimi,
        reason=reason,
        lane="general",
        next_cloud_gate=gate,
    )


def _person_present(prefilter: PrefilterResult, config: CloudGateConfig) -> bool:
    if prefilter.person_detected is False:
        return False
    if prefilter.person_detected is True:
        if prefilter.person_confidence >= config.person_enter_confidence:
            return True
        return prefilter.person_confidence > config.person_exit_confidence
    return False


def _motion_active(prefilter: PrefilterResult, config: CloudGateConfig) -> bool:
    return prefilter.motion_available and prefilter.motion_score >= config.motion_threshold


def _previous_motion_active(previous: Mapping[str, Any], config: CloudGateConfig) -> bool:
    score = float(previous.get("motion_score") or 0.0)
    available = bool(previous.get("motion_available"))
    return available and score >= config.motion_threshold


def _motion_cooldown_elapsed(gate: Mapping[str, Any], now_ms: int, config: CloudGateConfig) -> bool:
    last = int(gate.get("last_motion_kimi_at_ms") or 0)
    if last <= 0:
        return True
    return (now_ms - last) >= config.motion_cooldown_seconds * 1000


def _from_unknown(
    gate: dict[str, Any],
    person_present: bool,
    now_ms: int,
) -> tuple[dict[str, Any], bool, str]:
    if person_present:
        gate["gate_state"] = GATE_PERSON_CANDIDATE
        gate["person_enter_debounce"] = 1
        return gate, False, "prefilter_warming"
    gate["gate_state"] = GATE_EMPTY_CANDIDATE
    gate["person_enter_debounce"] = 1
    return gate, False, "prefilter_warming"


def _from_empty_candidate(
    gate: dict[str, Any],
    person_present: bool,
    now_ms: int,
    config: CloudGateConfig,
) -> tuple[dict[str, Any], bool, str]:
    if person_present:
        debounce = int(gate.get("person_enter_debounce") or 0) + 1
        gate["person_enter_debounce"] = debounce
        if debounce >= config.person_enter_debounce_ticks:
            gate["gate_state"] = GATE_PERSON_CANDIDATE
        return gate, False, "cloud_gate_empty_candidate"
    debounce = int(gate.get("person_enter_debounce") or 0) + 1
    gate["person_enter_debounce"] = debounce
    if debounce >= config.person_enter_debounce_ticks:
        gate["gate_state"] = GATE_EMPTY_STABLE
        gate["empty_stable_since_ms"] = now_ms
    return gate, False, "cloud_gate_empty_candidate"


def _from_empty_stable(
    gate: dict[str, Any],
    person_present: bool,
    motion_started: bool,
    now_ms: int,
    config: CloudGateConfig,
) -> tuple[dict[str, Any], bool, str]:
    if person_present:
        gate["gate_state"] = GATE_PERSON_CANDIDATE
        gate["person_enter_debounce"] = 1
        gate["person_stable_since_ms"] = 0
        return gate, False, "cloud_gate_person_enter_pending"
    if motion_started and _motion_cooldown_elapsed(gate, now_ms, config):
        return gate, True, "empty_motion_edge"
    last_hb = int(gate.get("last_empty_heartbeat_at_ms") or 0)
    stable_since = int(gate.get("empty_stable_since_ms") or now_ms)
    hb_due = (now_ms - max(last_hb, stable_since)) >= config.empty_heartbeat_seconds * 1000
    if hb_due:
        return gate, True, "empty_heartbeat"
    return gate, False, "cloud_gate_empty_stable"


def _from_person_candidate(
    gate: dict[str, Any],
    person_present: bool,
    now_ms: int,
    config: CloudGateConfig,
) -> tuple[dict[str, Any], bool, str]:
    if not person_present:
        gate["gate_state"] = GATE_EMPTY_CANDIDATE
        gate["person_enter_debounce"] = 1
        return gate, False, "cloud_gate_person_enter_aborted"
    debounce = int(gate.get("person_enter_debounce") or 0) + 1
    gate["person_enter_debounce"] = debounce
    if debounce >= config.person_enter_debounce_ticks:
        gate["gate_state"] = GATE_PERSON_STABLE
        gate["person_stable_since_ms"] = now_ms
        gate["person_enter_debounce"] = 0
        return gate, True, "person_enter"
    return gate, False, "cloud_gate_person_candidate"


def _from_person_stable(
    gate: dict[str, Any],
    person_present: bool,
    motion_started: bool,
    now_ms: int,
    config: CloudGateConfig,
) -> tuple[dict[str, Any], bool, str]:
    if not person_present:
        gate["gate_state"] = GATE_PERSON_LEFT_CANDIDATE
        gate["person_leave_debounce"] = 1
        return gate, False, "cloud_gate_person_leave_pending"
    if motion_started and _motion_cooldown_elapsed(gate, now_ms, config):
        gate["gate_state"] = GATE_MOTION_ACTIVE
        gate["motion_exit_debounce"] = 0
        return gate, True, "person_motion_started"
    last_hb = int(gate.get("last_person_heartbeat_at_ms") or 0)
    stable_since = int(gate.get("person_stable_since_ms") or now_ms)
    hb_due = (now_ms - max(last_hb, stable_since)) >= config.person_heartbeat_seconds * 1000
    if hb_due:
        return gate, True, "person_heartbeat"
    return gate, False, "cloud_gate_person_stable"


def _from_motion_active(
    gate: dict[str, Any],
    person_present: bool,
    motion_now: bool,
    motion_stopped: bool,
    now_ms: int,
    config: CloudGateConfig,
) -> tuple[dict[str, Any], bool, str]:
    if not person_present:
        gate["gate_state"] = GATE_PERSON_LEFT_CANDIDATE
        gate["person_leave_debounce"] = 1
        return gate, False, "cloud_gate_person_leave_pending"
    if motion_now:
        gate["motion_exit_debounce"] = 0
        return gate, False, "cloud_gate_motion_active"
    if motion_stopped:
        debounce = int(gate.get("motion_exit_debounce") or 0) + 1
        gate["motion_exit_debounce"] = debounce
        if debounce >= config.motion_exit_debounce_ticks:
            gate["gate_state"] = GATE_PERSON_STABLE
            gate["person_stable_since_ms"] = now_ms
            gate["motion_exit_debounce"] = 0
        return gate, False, "cloud_gate_motion_cooldown"
    return gate, False, "cloud_gate_motion_active"


def _from_person_left_candidate(
    gate: dict[str, Any],
    person_present: bool,
    now_ms: int,
    config: CloudGateConfig,
) -> tuple[dict[str, Any], bool, str]:
    if person_present:
        gate["gate_state"] = GATE_PERSON_STABLE
        gate["person_stable_since_ms"] = now_ms
        gate["person_leave_debounce"] = 0
        return gate, False, "cloud_gate_person_return"
    debounce = int(gate.get("person_leave_debounce") or 0) + 1
    gate["person_leave_debounce"] = debounce
    if debounce < config.person_leave_debounce_ticks:
        return gate, False, "cloud_gate_person_leave_pending"
    gate["gate_state"] = GATE_EMPTY_STABLE
    gate["empty_stable_since_ms"] = now_ms
    gate["person_leave_debounce"] = 0
    gate["person_stable_since_ms"] = 0
    if config.confirm_person_leave:
        return gate, True, "person_leave"
    return gate, False, "cloud_gate_person_leave_lightweight"
