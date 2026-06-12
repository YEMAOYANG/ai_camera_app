from __future__ import annotations

import json

from core.database import DatabaseRow


def point_account_payload(row: DatabaseRow) -> dict:
    return {
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "balance": row["balance"],
        "stageNoticeHandledBalance": row.get("stage_notice_handled_balance") or 0,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def point_ledger_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "delta": row["delta"],
        "balanceAfter": row["balance_after"],
        "type": row["type"],
        "sourceType": row["source_type"],
        "sourceId": row["source_id"],
        "note": row["note"],
        "createdAt": row["created_at"],
    }


def point_reward_unit_payload(row: DatabaseRow) -> dict:
    metadata = _json_dict(row.get("metadata_json"))
    suffix = str(metadata.get("suffix") or row.get("label") or "").strip()
    return {
        "key": row["item_key"],
        "label": row["label"],
        "description": row.get("description") or "",
        "suffix": suffix or row["label"],
        "imageAsset": row.get("image_asset") or "",
    }


def point_settings_payload(
    value: dict,
    unit_options: list[dict],
    *,
    updated_at: int | None = None,
) -> dict:
    unit_key = str(value.get("unit") or "").strip()
    selected = next((item for item in unit_options if item["key"] == unit_key), None)
    if selected is None and unit_options:
        selected = unit_options[0]
        unit_key = selected["key"]
    return {
        "stageThreshold": value["stageThreshold"],
        "unit": unit_key,
        "unitOption": selected,
        "unitOptions": unit_options,
        "updatedAt": updated_at,
    }


def _json_dict(value: object) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}
