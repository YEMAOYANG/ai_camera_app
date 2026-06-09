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


def family_invitation_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "name": row["name"],
        "phone": row["phone"] or "",
        "role": row["role"],
        "status": row["status"],
        "createdBy": row["created_by"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "expiresAt": row.get("expires_at"),
    }


def guardian_identity_options_payload(
    groups: list[DatabaseRow],
    labels: list[DatabaseRow],
    roles: list[DatabaseRow],
) -> dict:
    labels_by_group: dict[str, list[dict]] = {}
    for row in labels:
        group_key = row.get("parent_key") or ""
        labels_by_group.setdefault(group_key, []).append(
            {
                "key": row["item_key"],
                "label": row["label"],
                "description": row.get("description") or "",
                "imageAsset": row.get("image_asset") or "",
            }
        )

    identity_groups = []
    for row in groups:
        group_labels = labels_by_group.get(row["item_key"], [])
        default_label = group_labels[0]["label"] if group_labels else ""
        default_key = group_labels[0]["key"] if group_labels else ""
        identity_groups.append(
            {
                "key": row["item_key"],
                "label": row["label"],
                "description": row.get("description") or "",
                "defaultKey": default_key,
                "defaultLabel": default_label,
                "labels": group_labels,
            }
        )

    family_roles = [
        {
            "key": row["item_key"],
            "label": row["label"],
            "description": row.get("description") or "",
        }
        for row in roles
    ]
    return {"identityGroups": identity_groups, "familyRoles": family_roles}


def child_profile_payload(row: DatabaseRow | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "name": row["name"],
        "nickname": row["nickname"] or "",
        "gender": row.get("gender") or "unspecified",
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


def emergency_contact_payload(
    row: DatabaseRow,
    *,
    relationship: str | None = None,
    relationship_key: str | None = None,
) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "name": row["name"],
        "phone": row["phone"],
        "relationship": relationship if relationship is not None else row["relationship"] or "",
        "relationshipKey": (
            relationship_key
            if relationship_key is not None
            else row.get("relationship_key") or ""
        ),
        "defaultNotify": bool(row.get("default_notify", 1)),
        "priority": row["priority"],
        "createdAt": row["created_at"],
        "updatedAt": row.get("updated_at") or row["created_at"],
    }


def setting_payload(key: str, value: dict, updated_at: int | None = None) -> dict:
    return {"key": key, "value": value, "updatedAt": updated_at}


def account_profile_payload(
    user: DatabaseRow,
    family: DatabaseRow,
    parent_identity: DatabaseRow | None,
    *,
    role: str,
    relationship_key: str = "",
) -> dict:
    display_name = (
        parent_identity["display_name"]
        if parent_identity and parent_identity["display_name"]
        else user["display_name"]
    )
    return {
        "userId": user["id"],
        "phone": user["phone"],
        "displayName": display_name,
        "familyId": family["id"],
        "familyName": family["name"],
        "relationship": parent_identity["relationship"] if parent_identity else "",
        "relationshipKey": relationship_key or (
            parent_identity.get("relationship_key") if parent_identity else ""
        )
        or "",
        "role": role,
    }


def account_security_payload(
    user: DatabaseRow,
    sessions: list[DatabaseRow],
    *,
    current_access_hash: str = "",
) -> dict:
    return {
        "phone": user["phone"],
        "loginMethod": "sms",
        "accountStatus": user.get("account_status") or "active",
        "loginDevices": [
            {
                "id": row["id"],
                "label": row.get("device_label") or _session_label(row),
                "deviceType": row.get("device_type") or "unknown",
                "platform": row.get("platform") or "unknown",
                "appVersion": row.get("app_version") or "",
                "active": row.get("revoked_at") is None,
                "current": bool(current_access_hash and row.get("access_hash") == current_access_hash),
                "createdAt": row["created_at"],
                "lastActiveAt": row.get("last_active_at") or row.get("rotated_at") or row["created_at"],
                "rotatedAt": row.get("rotated_at"),
            }
            for row in sessions
        ],
    }


def account_deletion_request_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "requestedAt": row["requested_at"],
        "completedAt": row.get("completed_at"),
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


def _session_label(row: DatabaseRow) -> str:
    platform = str(row.get("platform") or "").lower()
    device_type = str(row.get("device_type") or "").lower()
    combined = f"{platform} {device_type}"
    if "ios" in combined or "iphone" in combined:
        return "本机 iPhone"
    if "android" in combined:
        return "Android 手机"
    if "mac" in combined:
        return "Mac 设备"
    return "已登录设备"
