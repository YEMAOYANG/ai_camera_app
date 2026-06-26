from __future__ import annotations

import json
import re
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.care import (
    CARE_SCENARIO_POSTURE,
    CARE_SCENARIOS,
    DAY_TYPES,
    REVIEW_DOMAIN_CARE,
)
from models.care import REMINDER_DECISION_ALLOWED
from repositories.care_repository import CareRepository
from repositories.device_repository import DeviceRepository
from schemas.care import observation_event_payload, parent_review_event_payload, reminder_decision_payload
from services.care_defaults import ensure_default_capability_configs, ensure_default_routine_windows
from services.care_policy_engine import CarePolicyEngine, REVIEW_ITEM_TYPE_PARENT_NOTIFY
from services.task_event_stream import CAMERA_OBSERVATION_UPDATED, REMINDER_DECISION_CREATED, publish_family_event


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
            parsed_signals = _signals(data.get("signals"))
            parent_summary = _optional_text(data.get("parentSummary"))
            raw_detail_json = _json_or_none(data.get("rawDetail"))
            primary_signal_type = parsed_signals[0]["signalType"] if parsed_signals else ""
            duplicate_care_event = self.repository.find_recent_duplicate_observation(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                signal_type=primary_signal_type,
                parent_summary=parent_summary,
                raw_detail_json=raw_detail_json,
                since=now - 120_000,
            )
            event = self.repository.create_observation_event(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                observed_at=observed_at,
                confidence=observation_score,
                evidence_type=str(data.get("evidenceType") or "none")[:128],
                parent_summary=parent_summary,
                raw_detail_json=raw_detail_json,
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
            confidence_threshold = _effective_confidence_threshold(
                scenario=scenario,
                configured_threshold=float(capability.get("confidence_threshold") or 0.72) if capability else 0.72,
            )
            continuous_window_seconds = max(30, min_observation_seconds)
            capability_enabled = capability is not None and bool(capability.get("enabled"))
            signal_rows = []
            state_rows = []
            policy_signal_rows = []
            for signal in parsed_signals:
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
        care_event = None
        duplicate_care_event = bool(duplicate_care_event)
        if data.get("recordCareEvent") is not False and not duplicate_care_event:
            care_event = self._record_parent_care_event(
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                event=event,
                data=data,
                observation_score=observation_score,
            )
        reminder_result = None
        if not duplicate_care_event:
            reminder_result = self._trigger_allowed_reminder(
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                decision=decision_row,
                event=event,
                data=data,
            )
        publish_family_event(
            family_id=family_id,
            event_type=CAMERA_OBSERVATION_UPDATED,
            device_id=device_id,
            observation_id=event["id"],
            is_reliable=observation_score >= 0.65,
            source="camera_observation",
        )
        publish_family_event(
            family_id=family_id,
            event_type=REMINDER_DECISION_CREATED,
            device_id=device_id,
            observation_id=event["id"],
            event_ids=[decision_row["id"]],
            is_reliable=observation_score >= 0.65,
            source="care_policy",
        )
        return {
            "ok": True,
            "observation": observation_event_payload(event),
            "decision": reminder_decision_payload(decision_row),
            "careEvent": care_event,
            "reminder": reminder_result,
            "reviewItem": parent_review_event_payload(review_item) if review_item else None,
            "duplicate": duplicate_care_event,
            "duplicateCareEvent": duplicate_care_event,
        }

    def _record_parent_care_event(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        event,
        data: dict,
        observation_score: float,
    ) -> dict | None:
        if not device_id:
            return None
        try:
            from services.service_factory import camera_command_service

            command = camera_command_service().record_observation_event(
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                observation=_camera_event_observation(
                    event=event,
                    data=data,
                    observation_score=observation_score,
                ),
            )
            return command
        except Exception:
            return None

    def _trigger_allowed_reminder(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        decision,
        event,
        data: dict,
    ) -> dict | None:
        if (
            str(decision.get("decision") or "") != REMINDER_DECISION_ALLOWED
            or not bool(decision.get("should_speak"))
        ):
            return None
        try:
            from services.service_factory import ai_care_reminder_service

            return ai_care_reminder_service().trigger_internal(
                {
                    "familyId": family_id,
                    "childId": child_id,
                    "deviceId": device_id or "",
                    "scenario": scenario,
                    "reminderDecisionId": decision["id"],
                    "context": _reminder_context_from_observation(
                        event=event,
                        data=data,
                        decision=decision,
                    ),
                }
            )
        except Exception as exc:
            return {"ok": False, "error": "reminder_trigger_failed", "message": str(exc)}

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


def _effective_confidence_threshold(
    *,
    scenario: str,
    configured_threshold: float,
) -> float:
    if scenario == CARE_SCENARIO_POSTURE:
        return min(configured_threshold, 0.68)
    return configured_threshold


def _camera_event_observation(*, event, data: dict, observation_score: float) -> dict:
    raw_detail = _dict_or_empty(data.get("rawDetail"))
    has_person_value = _first_present(
        data,
        raw_detail,
        "hasPerson",
        "has_person",
    )
    activity = str(
        data.get("activity")
        or raw_detail.get("activity")
        or raw_detail.get("raw_activity")
        or ""
    ).strip()
    description = _clean_parent_text(
        data.get("description")
        or raw_detail.get("description")
        or raw_detail.get("child_message")
    )
    decision_reason = _clean_parent_text(
        data.get("decisionReason")
        or raw_detail.get("decision_reason")
    )
    summary = _clean_parent_text(data.get("parentSummary") or event.get("parent_summary"))
    if not summary:
        summary = _summary_from_activity(
            has_person=has_person_value,
            activity=activity,
            description=description,
        )
    snapshot_ref = str(
        data.get("snapshotRef")
        or data.get("thumbnailUrl")
        or raw_detail.get("snapshotRef")
        or raw_detail.get("thumbnailUrl")
        or ""
    ).strip()
    return {
        "id": event["id"],
        "hasPerson": has_person_value if isinstance(has_person_value, bool) else None,
        "activity": _activity_label(activity, description),
        "confidence": observation_score,
        "observedAt": event.get("observed_at") or data.get("observedAt"),
        "summary": summary,
        "description": description,
        "decisionReason": decision_reason,
        "isReliable": observation_score >= 0.65,
        "source": data.get("source") or event.get("source") or "camera_adapter",
        "sourceEventId": event.get("source_event_id") or data.get("sourceEventId") or "",
        "scenario": event.get("scenario") or data.get("scenario") or "",
        "evidenceType": event.get("evidence_type") or data.get("evidenceType") or "none",
        "snapshotRef": snapshot_ref,
        "thumbnailUrl": snapshot_ref,
        "rawDetail": raw_detail,
    }


def _reminder_context_from_observation(*, event, data: dict, decision) -> dict:
    raw_detail = _dict_or_empty(data.get("rawDetail"))
    return {
        "reminderLevel": decision.get("reminder_level") or "gentle",
        "scenario": event.get("scenario") or data.get("scenario") or "",
        "activity": raw_detail.get("activity") or raw_detail.get("raw_activity") or data.get("activity") or "",
        "description": raw_detail.get("description") or data.get("description") or "",
        "decisionReason": raw_detail.get("decision_reason") or data.get("decisionReason") or "",
        "cameraObservation": {
            "hasPerson": _first_present(data, raw_detail, "hasPerson", "has_person"),
            "activity": raw_detail.get("activity") or raw_detail.get("raw_activity") or "",
            "confidence": data.get("confidence") or event.get("confidence") or 0,
            "summary": data.get("parentSummary") or event.get("parent_summary") or "",
        },
    }


def _dict_or_empty(value: object) -> dict:
    if isinstance(value, dict):
        return value
    return {}


def _clean_parent_text(value: object, *, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if _looks_like_structured_payload(text):
        return ""
    return text[:limit]


def _looks_like_structured_payload(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    starts_structured = compact.startswith(("{", "["))
    ends_structured = compact.endswith(("}", "]"))
    has_structured_keys = any(
        token in compact
        for token in ("'score'", '"score"', "'skills'", '"skills"', "{'name'", '"name"')
    )
    return has_structured_keys or (starts_structured and ends_structured)


def _first_present(primary: dict, secondary: dict, *keys: str):
    for key in keys:
        if key in primary:
            return primary.get(key)
        if key in secondary:
            return secondary.get(key)
    return None


def _summary_from_activity(*, has_person: object, activity: str, description: str) -> str:
    label = _activity_label(activity, description)
    if label == "玩玩具":
        return "孩子正在玩玩具"
    if label:
        return f"孩子正在{label}"
    if has_person is False:
        return "暂未看到孩子"
    if has_person is True:
        return "画面暂时无法判断"
    return ""


def _activity_label(activity: str, description: str = "") -> str:
    activity_text = activity.strip()
    normalized = activity_text.lower()
    if normalized in {"", "其他", "未知", "无明显活动", "other", "unknown", "normal"}:
        return ""
    text = f"{activity_text} {description}".strip().lower()
    if _positive_toy_activity(activity_text, description):
        return "玩玩具"
    return activity_text[:40]


def _positive_toy_activity(activity: str, description: str) -> bool:
    activity_text = activity.strip().lower()
    if activity_text in {"玩玩具", "玩积木", "toy_play", "playing_toys", "playing with toys"}:
        return True
    text = f"{activity} {description}".strip().lower()
    if _contains_negated_toy(text):
        return False
    return any(token in text for token in ("玩玩具", "玩积木", "搭积木", "摆弄玩具", "操作玩具", "playing with toys"))


def _contains_negated_toy(text: str) -> bool:
    return re.search(r"(没有|没|未|未见|看不到|没有看到)[^，。,.]{0,18}(玩具|积木|toy|toys)", text) is not None


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
