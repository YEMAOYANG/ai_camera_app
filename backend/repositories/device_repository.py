from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from core.database import SQLiteDatabase


class DeviceRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self.ensure_schema()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.database.transaction() as conn:
            yield conn

    def ensure_schema(self) -> None:
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS devices (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  binding_code TEXT,
                  name TEXT NOT NULL,
                  location TEXT,
                  status TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                );
                """
            )

    def list_devices(self, conn: sqlite3.Connection, *, family_id: str) -> list[sqlite3.Row]:
        return list(
            conn.execute(
                "SELECT * FROM devices WHERE family_id = ? ORDER BY created_at DESC",
                (family_id,),
            ).fetchall()
        )

    def get_device(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        device_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM devices WHERE family_id = ? AND id = ?",
            (family_id, device_id),
        ).fetchone()
