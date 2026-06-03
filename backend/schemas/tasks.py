from __future__ import annotations

import sqlite3

from core.errors import ApiError
from models.tasks import TASK_STATUSES, TASK_TYPES


def task_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "title": row["title"],
        "description": row["description"],
        "type": row["type"],
        "status": row["status"],
        "scheduledDate": row["scheduled_date"],
        "scheduledStart": row["scheduled_start"],
        "scheduledEnd": row["scheduled_end"],
        "rewardPoints": row["reward_points"],
        "requiresParentConfirmation": bool(row["requires_parent_confirmation"]),
        "evidenceSummary": row["evidence_summary"],
        "rejectionReason": row["rejection_reason"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "completedAt": row["completed_at"],
        "confirmedAt": row["confirmed_at"],
        "rejectedAt": row["rejected_at"],
        "pointsGrantedAt": row["points_granted_at"],
    }


def validate_task_type(value: str) -> str:
    if value not in TASK_TYPES:
        raise ApiError("invalid_task_type", "任务类型不支持")
    return value


def validate_task_status(value: str) -> str:
    if value not in TASK_STATUSES:
        raise ApiError("invalid_task_status", "任务状态不支持")
    return value
