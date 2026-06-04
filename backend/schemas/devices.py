from __future__ import annotations

from core.database import DatabaseRow


def device_payload(row: DatabaseRow) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "bindingCode": row["binding_code"],
        "name": row["name"],
        "location": row["location"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "unboundAt": row.get("unbound_at"),
    }
