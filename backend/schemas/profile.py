from __future__ import annotations

import json

from core.database import DatabaseRow


def family_member_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "userId": row["user_id"],
        "name": row["name"],
        "relationshipKey": row.get("relationship_key") or "",
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
        "relationshipKey": row.get("relationship_key") or "",
        "phone": row["phone"] or "",
        "role": row["role"],
        "status": row["status"],
        "createdBy": row["created_by"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "expiresAt": row.get("expires_at"),
        "acceptedBy": row.get("accepted_by") or "",
        "acceptedAt": row.get("accepted_at"),
        "declinedAt": row.get("declined_at"),
        "deliveryStatus": row.get("delivery_status") or "",
        "deliveryNotice": row.get("delivery_message") or "",
    }


def pending_join_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "familyName": row.get("family_name") or "家庭空间",
        "name": row["name"],
        "relationshipKey": row.get("relationship_key") or "",
        "phone": row["phone"] or "",
        "role": row["role"],
        "roleLabel": row.get("role_label") or row["role"],
        "status": row["status"],
        "expiresAt": row.get("expires_at"),
        "deliveryStatus": row.get("delivery_status") or "",
        "deliveryNotice": row.get("delivery_message") or "",
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
            "capabilities": role_capabilities_from_option(row),
        }
        for row in roles
    ]
    return {"identityGroups": identity_groups, "familyRoles": family_roles}


def role_capabilities_from_option(row: DatabaseRow | None) -> list[str]:
    if row is None:
        return []
    metadata = _json_dict(row.get("metadata_json"))
    raw = metadata.get("capabilities")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


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
        "sleepTime": row.get("sleep_time") or "",
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
    role_label: str = "",
    capabilities: list[str] | None = None,
    display_name: str | None = None,
    relationship: str | None = None,
    relationship_key: str = "",
) -> dict:
    resolved_display_name = display_name or (
        parent_identity["display_name"]
        if parent_identity and parent_identity["display_name"]
        else user["display_name"]
    )
    resolved_relationship = relationship if relationship is not None else (
        parent_identity["relationship"] if parent_identity else ""
    )
    return {
        "userId": user["id"],
        "phone": user["phone"],
        "displayName": resolved_display_name,
        "familyId": family["id"],
        "familyName": family["name"],
        "relationship": resolved_relationship,
        "relationshipKey": relationship_key or (
            parent_identity.get("relationship_key") if parent_identity else ""
        )
        or "",
        "role": role,
        "roleLabel": role_label or role,
        "capabilities": capabilities or [],
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
                "label": _session_display_label(row),
                "deviceType": row.get("device_type") or "unknown",
                "model": row.get("device_model") or "",
                "hardware": row.get("device_hardware") or "",
                "platform": row.get("platform") or "unknown",
                "osVersion": row.get("os_version") or "",
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


def _session_display_label(row: DatabaseRow) -> str:
    label = str(row.get("device_label") or "").strip()
    if label and label not in {"已登录设备", "unknown", "unknown device"}:
        return label
    return _session_label(row)


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
    return "其他登录设备"
