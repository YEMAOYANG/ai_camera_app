from __future__ import annotations

import sqlite3


def device_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "familyId": row["family_id"],
        "bindingCode": row["binding_code"],
        "name": row["name"],
        "location": row["location"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
