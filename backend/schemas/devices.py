from __future__ import annotations

import json

from core.database import DatabaseRow


def device_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "bindingCode": row["binding_code"],
        "name": row["name"],
        "wakeName": row.get("wake_name") or "",
        "location": row["location"],
        "status": row["status"],
        "isDefault": bool(row.get("is_default")),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "unboundAt": row.get("unbound_at"),
    }


def device_runtime_config_payload(row: DatabaseRow, *, config: dict, adapter_implemented: bool) -> dict:
    provider = str(row["provider"] or "")
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "deviceId": row["device_id"],
        "provider": provider,
        "config": dict(config),
        "hasSecretRef": bool(row.get("secret_ref")),
        "status": row["status"],
        "adapterImplemented": bool(adapter_implemented),
        "message": _runtime_config_message(provider, adapter_implemented),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def runtime_config_json(row: DatabaseRow | None) -> dict:
    if row is None:
        return {}
    raw = row.get("config_json")
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _runtime_config_message(provider: str, adapter_implemented: bool) -> str:
    if not adapter_implemented:
        return "当前摄像头运行适配器尚未接入。"
    if provider == "disabled":
        return "摄像头运行配置已关闭。"
    return "摄像头运行配置已保存。"
