from __future__ import annotations

import json

from core.database import DatabaseRow


def family_member_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "userId": row["user_id"],
        "name": row["name"],
        "phone": row["phone"] or "",
        "role": row["role"],
        "status": row["status"],
        "notifyEnabled": bool(row["notify_enabled"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def child_profile_payload(row: DatabaseRow | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "name": row["name"],
        "nickname": row["nickname"] or "",
        "birthday": row["birthday"] or "",
        "ageStage": row["age_stage"] or "",
        "educationStage": row.get("education_stage") or row["age_stage"] or "",
        "grade": row.get("grade") or "",
        "schoolName": row.get("school_name") or "",
        "interests": _json_list(row.get("interests")),
        "taskPreferences": _json_dict(row.get("task_preferences")),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def emergency_contact_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "name": row["name"],
        "phone": row["phone"],
        "relationship": row["relationship"] or "",
        "defaultNotify": bool(row.get("default_notify", 1)),
        "priority": row["priority"],
        "createdAt": row["created_at"],
        "updatedAt": row.get("updated_at") or row["created_at"],
    }


def setting_payload(key: str, value: dict, updated_at: int | None = None) -> dict:
    return {"key": key, "value": value, "updatedAt": updated_at}


def account_profile_payload(user: DatabaseRow, family: DatabaseRow, parent_identity: DatabaseRow | None) -> dict:
    return {
        "userId": user["id"],
        "phone": user["phone"],
        "displayName": user["display_name"],
        "familyId": family["id"],
        "familyName": family["name"],
        "relationship": parent_identity["relationship"] if parent_identity else "",
        "role": "admin",
    }


def account_security_payload(user: DatabaseRow, sessions: list[DatabaseRow]) -> dict:
    return {
        "phone": user["phone"],
        "loginMethod": "sms",
        "accountStatus": "active",
        "loginDevices": [
            {
                "id": row["id"],
                "label": "已登录设备",
                "active": row.get("revoked_at") is None,
                "createdAt": row["created_at"],
                "rotatedAt": row.get("rotated_at"),
            }
            for row in sessions
        ],
    }


def legal_document_payload(
    *,
    key: str,
    title: str,
    summary: str,
    sections: list[dict],
    version: str,
    effective_date: str,
) -> dict:
    return {
        "key": key,
        "title": title,
        "summary": summary,
        "sections": sections,
        "version": version,
        "effectiveDate": effective_date,
    }


def feedback_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "category": row["category"],
        "content": row["content"],
        "status": row["status"],
        "createdAt": row["created_at"],
    }


def _json_list(value: object) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: object) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
