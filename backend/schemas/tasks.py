from __future__ import annotations

import json

from core.database import DatabaseRow

from core.errors import ApiError
from models.tasks import TASK_STATUSES, TASK_TYPES


def task_payload(row: DatabaseRow) -> dict:
    start_at = row.get("start_at") or _compose_datetime(
        row["scheduled_date"],
        row.get("scheduled_start"),
    )
    due_at = row.get("due_at") or _compose_datetime(
        row["scheduled_date"],
        row.get("scheduled_end"),
    )
    evidence = _parse_json_object(row.get("evidence"))
    if not evidence and row.get("evidence_summary"):
        evidence = {"summary": row["evidence_summary"]}

    return {
        "id": row["id"],
        "taskId": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "title": row["title"],
        "description": row["description"],
        "type": row["type"],
        "taskType": row["type"],
        "scheduleType": row.get("schedule_type") or "one_time",
        "startAt": start_at,
        "dueAt": due_at,
        "repeatRule": _parse_json_value(row.get("repeat_rule")),
        "status": row["status"],
        "priority": row.get("priority") or 3,
        "scheduledDate": row["scheduled_date"],
        "scheduledStart": row["scheduled_start"],
        "scheduledEnd": row["scheduled_end"],
        "rewardPoints": row["reward_points"],
        "requiresParentConfirmation": bool(row["requires_parent_confirmation"]),
        "reminderMinutesBefore": row.get("reminder_minutes_before") or 5,
        "reminderStatus": row.get("reminder_status") or "pending",
        "completionSource": row.get("completion_source"),
        "evidence": evidence,
        "evidenceSummary": row["evidence_summary"],
        "aiObservationSummary": row.get("ai_observation_summary"),
        "rejectionReason": _normalize_rejection_reason(row["rejection_reason"]),
        "createdBy": row.get("created_by"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "startedAt": row.get("started_at"),
        "endedAt": row.get("ended_at"),
        "missedAt": row.get("missed_at"),
        "delayedAt": row.get("delayed_at"),
        "lastReminderAt": row.get("last_reminder_at"),
        "nextReminderAt": row.get("next_reminder_at"),
        "delayReminderCount": row.get("delay_reminder_count") or 0,
        "cameraObservationStatus": row.get("camera_observation_status") or "unknown",
        "parentActions": _parent_actions(row),
        "deviceId": row.get("device_id"),
        "timezone": row.get("timezone") or "Asia/Shanghai",
        "completedAt": row["completed_at"],
        "confirmedAt": row["confirmed_at"],
        "rejectedAt": row["rejected_at"],
        "pointsGrantedAt": row["points_granted_at"],
    }


def task_event_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "taskId": row["task_id"],
        "eventType": row["event_type"],
        "message": row.get("message") or "",
        "payload": _parse_json_object(row.get("payload")),
        "createdAt": row["created_at"],
    }


def _parent_actions(row: DatabaseRow) -> list[dict]:
    status = str(row.get("status") or "")
    if status == "awaiting_parent_confirmation":
        return [
            {"value": "confirm", "label": "确认完成"},
            {"value": "reject", "label": "驳回"},
        ]
    if status in {"missed", "expired"}:
        if bool(row.get("missed_acknowledged")):
            return []
        return [
            {"value": "reschedule", "label": "重新安排"},
            {"value": "manual_complete", "label": "手动补记完成"},
            {"value": "acknowledge_missed", "label": "不处理"},
        ]
    return []


def validate_task_type(value: str) -> str:
    if value not in TASK_TYPES:
        raise ApiError("invalid_task_type", "任务类型不支持")
    return value


def _normalize_rejection_reason(value: str | None) -> str | None:
    if not value:
        return value
    legacy_phrases = (
        "等待孩子补充完成",
        "等待补充完成",
        "孩子补充",
        "补充完成",
    )
    if any(phrase in value for phrase in legacy_phrases):
        return "证据不足，未通过家长确认。"
    return value


def validate_task_status(value: str) -> str:
    if value not in TASK_STATUSES:
        raise ApiError("invalid_task_status", "任务状态不支持")
    return value


def _compose_datetime(scheduled_date: str, time_text: str | None) -> str | None:
    if not scheduled_date or not time_text:
        return None
    return f"{scheduled_date}T{time_text}:00"


def _parse_json_object(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"summary": value}
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
