from __future__ import annotations

import sqlite3


def firmware_package_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "version": row["version"],
        "channel": row["channel"],
        "status": row["status"],
        "notes": row["notes"],
        "createdAt": row["created_at"],
    }


def firmware_job_payload(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "deviceId": row["device_id"],
        "packageId": row["package_id"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
