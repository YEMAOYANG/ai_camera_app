from __future__ import annotations

import json

from core.database import DatabaseRow


def camera_command_payload(row: DatabaseRow | None) -> dict:
    if row is None:
        return {}
    return {
        "commandId": row["id"],
        "commandType": row["command_type"],
        "status": row["status"],
        "taskId": row.get("task_id"),
        "deviceId": row.get("device_id"),
        "message": row.get("message") or "",
        "request": _json_value(row.get("request_payload")),
        "response": _json_value(row.get("response_payload")),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "completedAt": row.get("completed_at"),
    }


def camera_status_payload(
    *,
    connection_status: str,
    stream_available: bool,
    snapshot_available: bool,
    speaker_available: bool,
    monitor_available: bool,
    last_seen_at: int | None,
    runtime_provider: str,
    current_task: dict | None,
    message: str,
) -> dict:
    return {
        "connectionStatus": connection_status,
        "streamAvailable": stream_available,
        "snapshotAvailable": snapshot_available,
        "speakerAvailable": speaker_available,
        "monitorAvailable": monitor_available,
        "lastSeenAt": last_seen_at,
        "runtimeProvider": runtime_provider,
        "currentTask": current_task,
        "message": message,
    }


def _json_value(value: object) -> object:
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
