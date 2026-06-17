from __future__ import annotations

import json
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.care import CARE_SCENARIOS, DAY_TYPES, REVIEW_DOMAIN_CARE
from repositories.care_repository import CareRepository
from repositories.device_repository import DeviceRepository
from schemas.care import observation_event_payload, parent_review_event_payload, reminder_decision_payload
from services.care_defaults import ensure_default_capability_configs, ensure_default_routine_windows
from services.care_policy_engine import CarePolicyEngine, REVIEW_ITEM_TYPE_PARENT_NOTIFY


class CameraAiObservationService:
    def __init__(self, database_url: str | Path):
        database = Database(database_url)
        self.repository = CareRepository(database)
        self.device_repository = DeviceRepository(database)
        self.policy_engine = CarePolicyEngine()

    def record_observation(self, data: dict) -> dict:
        family_id = _required_text(data, "familyId")
        child_id = _required_text(data, "childId")
        device_id = _optional_text(data.get("deviceId"))
        scenario = _scenario(data.get("scenario"))
        now = now_ms()
        observed_at = _int_or(data.get("observedAt"), now)
        observation_score = _score(data.get("confidence", data.get("observationScore", 0)))
        source = str(data.get("source") or "camera_adapter")[:128]
        source_event_id = _optional_text(data.get("sourceEventId"))
        day_type = _optional_day_type(data.get("dayType"))
        with self.repository.transaction() as conn:
            if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
                raise ApiError("child_not_found", "孩子资料不存在。", 404)
            if not device_id:
                raise ApiError("device_required", "缺少摄像头设备。", 400)
            device = self.device_repository.get_device(
                conn,
                family_id=family_id,
                device_id=device_id,
            )
            if device is None:
                raise ApiError("device_not_found", "设备不存在", 404)
            if device["status"] == "unbound":
                raise ApiError("device_unbound", "设备已解绑", 409)
            ensure_default_capability_configs(
                self.repository,
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=None,
            )
            ensure_default_routine_windows(
                self.repository,
                conn,
                family_id=family_id,
                child_id=child_id,
            )
            if source_event_id:
                existing = self.repository.get_observation_by_source_event(
                    conn,
                    family_id=family_id,
                    source=source,
                    source_event_id=source_event_id,
                )
                if existing:
                    decision = self.repository.latest_decision_for_observation(
                        conn,
                        observation_event_id=existing["id"],
                    )
                    return {
                        "ok": True,
                        "duplicate": True,
                        "observation": observation_event_payload(existing),
                        "decision": reminder_decision_payload(decision) if decision else None,
                    }
            event = self.repository.create_observation_event(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                observed_at=observed_at,
                confidence=observation_score,
                evidence_type=str(data.get("evidenceType") or "none")[:128],
                parent_summary=_optional_text(data.get("parentSummary")),
                raw_detail_json=_json_or_none(data.get("rawDetail")),
                source=source,
                source_event_id=source_event_id,
                source_type=_optional_text(data.get("sourceType")),
                source_id=_optional_text(data.get("sourceId")),
                task_id=_optional_text(data.get("taskId")),
                now=now,
            )
            capability = self.repository.get_capability_config_with_fallback(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
                device_id=device_id,
            )
            min_observation_seconds = int(capability.get("min_observation_seconds") or 20) if capability else 20
            confidence_threshold = float(capability.get("confidence_threshold") or 0.72) if capability else 0.72
            continuous_window_seconds = max(30, min_observation_seconds)
            capability_enabled = capability is not None and bool(capability.get("enabled"))
            signal_rows = []
            state_rows = []
            policy_signal_rows = []
            for signal in _signals(data.get("signals")):
                signal_row = self.repository.create_behavior_signal(
                    conn,
                    observation_event_id=event["id"],
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                    scenario=scenario,
                    signal_type=signal["signalType"],
                    signal_value=signal["signalValue"],
                    confidence=signal["confidence"],
                    duration_seconds=signal["durationSeconds"],
                    metadata_json=_json_or_none(signal.get("metadata")),
                    now=now,
                )
                signal_rows.append(signal_row)
                if not capability_enabled:
                    continue
                if float(signal_row.get("confidence") or 0) < confidence_threshold:
                    continue
                existing_state = self.repository.get_current_behavior_state(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                    scenario=scenario,
                    state=signal_row["signal_type"],
                )
                state_values = _next_state_values(
                    existing_state,
                    signal_row=signal_row,
                    observed_at=observed_at,
                    continuous_window_seconds=continuous_window_seconds,
                )
                policy_signal_rows.append(signal_row)
                state_rows.append(
                    self.repository.upsert_behavior_state(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                        device_id=device_id,
                        scenario=scenario,
                        state=signal_row["signal_type"],
                        status=state_values["status"],
                        started_at=state_values["started_at"],
                        last_observed_at=observed_at,
                        confidence=float(signal_row.get("confidence") or 0),
                        consecutive_seconds=state_values["consecutive_seconds"],
                        parent_summary=_optional_text(data.get("parentSummary")),
                        raw_detail_json=_json_or_none(data.get("rawDetail")),
                        now=now,
                    )
                )
            cooldown_seconds = int(capability.get("cooldown_seconds") or 900) if capability else 900
            history_since = now - max(48 * 60 * 60 * 1000, cooldown_seconds * 1000)
            decision_since = now - max(cooldown_seconds * 1000, 0)
            recent_events = self.repository.list_recent_real_reminder_events(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
                since=history_since,
                limit=100,
            )
            recent_allowed = self.repository.list_recent_allowed_decisions(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
                since=decision_since,
                limit=50,
            )
            current_state = _primary_state(state_rows)
            routine_windows = self.repository.list_routine_windows(
                conn,
                family_id=family_id,
                child_id=child_id,
            )
            policy = self.policy_engine.decide(
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                observation_event=event,
                behavior_signals=policy_signal_rows,
                capability_config=capability,
                current_behavior_state=current_state,
                recent_reminder_events=recent_events,
                recent_allowed_decisions=recent_allowed,
                routine_windows=routine_windows,
                day_type=day_type,
                now=now,
            )
            decision_row = self.repository.create_reminder_decision(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                observation_event_id=event["id"],
                behavior_state_id=current_state["id"] if current_state else None,
                source_type="camera_observation",
                source_id=event["id"],
                task_id=_optional_text(data.get("taskId")),
                decision=policy.decision,
                reason=policy.reason,
                reminder_level=policy.reminder_level,
                cooldown_until=policy.cooldown_until,
                should_speak=policy.should_speak,
                should_notify_parent=policy.should_notify_parent,
                policy_snapshot_json=policy.policy_snapshot_json,
                now=now,
            )
            review_item = None
            if policy.review_item:
                review_item = self._create_or_reuse_review_item(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                    scenario=scenario,
                    decision_id=decision_row["id"],
                    observation_id=event["id"],
                    cooldown_seconds=cooldown_seconds,
                    review=policy.review_item,
                    now=now,
                )
        return {
            "ok": True,
            "observation": observation_event_payload(event),
            "decision": reminder_decision_payload(decision_row),
            "reviewItem": parent_review_event_payload(review_item) if review_item else None,
        }

    def _create_or_reuse_review_item(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        decision_id: str,
        observation_id: str,
        cooldown_seconds: int,
        review: dict,
        now: int,
    ):
        since = now - max(cooldown_seconds * 1000, 30 * 60 * 1000)
        existing = self.repository.find_recent_pending_review_item(
            conn,
            family_id=family_id,
            child_id=child_id,
            domain=REVIEW_DOMAIN_CARE,
            scenario=scenario,
            item_type=REVIEW_ITEM_TYPE_PARENT_NOTIFY,
            since=since,
        )
        if existing:
            return existing
        return self.repository.create_parent_review_event(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            domain=REVIEW_DOMAIN_CARE,
            scenario=scenario,
            item_type=REVIEW_ITEM_TYPE_PARENT_NOTIFY,
            source_type="reminder_decision",
            source_id=decision_id,
            priority=str(review.get("priority") or "normal")[:32],
            status="pending",
            summary=str(review.get("summary") or "有一项看护情况需要家长查看。"),
            related_observation_id=observation_id,
            related_reminder_id=None,
            task_id=_optional_text(review.get("taskId")),
            due_at=review.get("dueAt") if isinstance(review.get("dueAt"), int) else None,
            now=now,
        )


def _signals(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "signalType": str(item.get("signalType") or item.get("type") or "unknown")[:255],
                "signalValue": str(item.get("signalValue") or item.get("value") or "observed")[:255],
                "confidence": _score(item.get("confidence", item.get("observationScore", 0))),
                "durationSeconds": _int_or(item.get("durationSeconds"), 0),
                "metadata": item.get("metadata"),
            }
        )
    return result


def _max_signal_duration(value: object) -> int:
    durations = [item["durationSeconds"] for item in _signals(value)]
    return max(durations) if durations else 0


def _state_status(value: object) -> str:
    text = str(value or "").strip()
    return (text or "active")[:64]


def _next_state_values(
    existing,
    *,
    signal_row,
    observed_at: int,
    continuous_window_seconds: int,
) -> dict:
    status = _state_status(signal_row.get("signal_value"))
    signal_seconds = int(signal_row.get("duration_seconds") or 0)
    if _is_reset_status(status) or existing is None:
        return {
            "status": status,
            "started_at": observed_at,
            "consecutive_seconds": 0 if _is_reset_status(status) else signal_seconds,
        }
    last_observed_at = int(existing.get("last_observed_at") or 0)
    gap_seconds = max(0, int((observed_at - last_observed_at) / 1000))
    if gap_seconds > continuous_window_seconds:
        return {
            "status": status,
            "started_at": observed_at,
            "consecutive_seconds": signal_seconds,
        }
    return {
        "status": status,
        "started_at": int(existing.get("started_at") or observed_at),
        "consecutive_seconds": int(existing.get("consecutive_seconds") or 0) + signal_seconds,
    }


def _is_reset_status(status: str) -> bool:
    return status.strip().lower() in {"recovered", "cleared", "inactive"}


def _primary_state(rows: list[dict]):
    if not rows:
        return None
    return max(
        rows,
        key=lambda row: (
            int(row.get("consecutive_seconds") or 0),
            float(row.get("confidence") or 0),
            int(row.get("updated_at") or 0),
        ),
    )


def _scenario(value: object) -> str:
    scenario = str(value or "").strip()
    if scenario not in CARE_SCENARIOS:
        raise ApiError("invalid_care_scenario", "看护能力暂不支持。")
    return scenario


def _optional_day_type(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text not in DAY_TYPES:
        raise ApiError("invalid_day_type", "作息类型暂不支持。")
    return text


def _required_text(data: dict, key: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ApiError(f"missing_{key}", f"{key} is required")
    return value


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int_or(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _score(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(parsed, 1.0))


def _json_or_none(value: object) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
