from __future__ import annotations

import sqlite3


def point_account_payload(row: sqlite3.Row) -> dict:
    return {
        "familyId": row["family_id"],
        "childId": row["child_id"],
        "balance": row["balance"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def point_ledger_payload(row: sqlite3.Row) -> dict:
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
