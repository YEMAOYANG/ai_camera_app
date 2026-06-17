from __future__ import annotations

from decimal import Decimal
import json
from typing import Any

from core.database import DatabaseRow
from models.care import CARE_SCENARIO_LABELS


def capability_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "deviceId": row.get("device_id") or "",
        "scenario": row["scenario"],
        "label": CARE_SCENARIO_LABELS.get(row["scenario"], row["scenario"]),
        "enabled": bool(row["enabled"]),
        "dayTypes": _json_list(row.get("day_types")),
        "timeWindows": _json_list(row.get("time_windows")),
        "minObservationSeconds": int(row.get("min_observation_seconds") or 0),
        "observationThreshold": _as_float(row.get("confidence_threshold")),
        "cooldownSeconds": int(row.get("cooldown_seconds") or 0),
        "dailyLimit": int(row.get("daily_limit") or 0),
        "parentNotifyThreshold": int(row.get("parent_notify_threshold") or 0),
        "allowSpeaker": bool(row.get("allow_speaker")),
        "recordOnly": bool(row.get("record_only")),
        "lastRemindedAt": row.get("last_reminded_at"),
        "dailyReminderCount": int(row.get("daily_reminder_count") or 0),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def routine_window_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "dayType": row["day_type"],
        "windowType": row["window_type"],
        "startTime": row["start_time"],
        "endTime": row["end_time"],
        "enabled": bool(row["enabled"]),
        "timezone": row.get("timezone") or "Asia/Shanghai",
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def observation_event_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "deviceId": row.get("device_id") or "",
        "scenario": row["scenario"],
        "observedAt": row["observed_at"],
        "observationScore": _as_float(row.get("confidence")),
        "evidenceType": row.get("evidence_type") or "none",
        "summary": row.get("parent_summary") or "",
        "source": row.get("source") or "camera_adapter",
        "sourceEventId": row.get("source_event_id") or "",
        "createdAt": row["created_at"],
    }


def reminder_decision_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "deviceId": row.get("device_id") or "",
        "scenario": row["scenario"],
        "observationEventId": row.get("observation_event_id") or "",
        "behaviorStateId": row.get("behavior_state_id") or "",
        "sourceType": row.get("source_type") or "",
        "sourceId": row.get("source_id") or "",
        "taskId": row.get("task_id") or "",
        "decision": row["decision"],
        "reason": row["reason"],
        "reminderLevel": row.get("reminder_level") or "gentle",
        "cooldownUntil": row.get("cooldown_until"),
        "shouldSpeak": bool(row.get("should_speak")),
        "shouldNotifyParent": bool(row.get("should_notify_parent")),
        "createdAt": row["created_at"],
    }


def reminder_event_payload(row: DatabaseRow) -> dict:
    command_status = str(row.get("command_status") or "")
    command_message = str(row.get("command_message") or "")
    delivery_status = row.get("delivery_status") or "generated"
    command_id = row.get("command_id") or ""
    failure_reason = row.get("failure_reason") or ""
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "deviceId": row.get("device_id") or "",
        "scenario": row["scenario"],
        "reminderDecisionId": row.get("reminder_decision_id") or "",
        "eventSource": row.get("event_source") or "care_policy",
        "isTest": bool(row.get("is_test")),
        "sourceType": row.get("source_type") or "",
        "sourceId": row.get("source_id") or "",
        "taskId": row.get("task_id") or "",
        "text": row["text"],
        "tone": row.get("tone") or "warm",
        "textSource": row.get("text_source") or "fallback",
        "deliveryStatus": delivery_status,
        "commandId": command_id,
        "fallbackUsed": bool(row.get("fallback_used")),
        "failureReason": failure_reason,
        "delivery": {
            "status": delivery_status,
            "commandId": command_id,
            "commandStatus": command_status,
            "message": command_message or failure_reason,
            "updatedAt": row.get("command_updated_at"),
            "completedAt": row.get("command_completed_at"),
        },
        "generatedAt": row["generated_at"],
        "deliveredAt": row.get("delivered_at"),
        "createdAt": row["created_at"],
    }


def parent_review_event_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row.get("child_id") or "",
        "deviceId": row.get("device_id") or "",
        "domain": row.get("domain") or "care",
        "scenario": row.get("scenario") or "",
        "reviewType": row.get("item_type") or "",
        "itemType": row.get("item_type") or "",
        "sourceType": row.get("source_type") or "",
        "sourceId": row.get("source_id") or "",
        "priority": row.get("priority") or "normal",
        "status": row["status"],
        "summary": row["summary"],
        "relatedObservationId": row.get("related_observation_id") or "",
        "relatedReminderId": row.get("related_reminder_id") or "",
        "taskId": row.get("task_id") or "",
        "dueAt": row.get("due_at"),
        "createdAt": row["created_at"],
        "resolvedAt": row.get("resolved_at"),
    }


def _json_list(value: object) -> list:
    parsed = _json_value(value)
    return parsed if isinstance(parsed, list) else []


def _json_value(value: object) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _as_float(value: object) -> float:
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
