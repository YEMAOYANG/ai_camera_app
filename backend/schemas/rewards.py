from __future__ import annotations

import sqlite3

from core.errors import ApiError
from models.rewards import REWARD_STATUSES


def reward_item_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "title": row["title"],
        "description": row["description"],
        "pointsCost": row["points_cost"],
        "category": row["category"],
        "status": row["status"],
        "icon": row["icon"],
        "createdBy": row["created_by"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def redemption_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "rewardItemId": row["reward_item_id"],
        "rewardTitle": row["reward_title"],
        "pointsCost": row["points_cost"],
        "status": row["status"],
        "requestedBy": row["requested_by"],
        "fulfilledBy": row["fulfilled_by"],
        "cancelledBy": row["cancelled_by"],
        "requestedAt": row["requested_at"],
        "fulfilledAt": row["fulfilled_at"],
        "cancelledAt": row["cancelled_at"],
    }


def validate_reward_status(value: str) -> str:
    if value not in REWARD_STATUSES:
        raise ApiError("invalid_reward_status", "奖励状态不支持")
    return value
