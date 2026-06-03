from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import SQLiteDatabase
from models.firmware import FIRMWARE_PACKAGE_ACTIVE, FIRMWARE_SCHEDULED


class FirmwareRepository:
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
                CREATE TABLE IF NOT EXISTS firmware_packages (
                  id TEXT PRIMARY KEY,
                  version TEXT NOT NULL,
                  channel TEXT NOT NULL,
                  status TEXT NOT NULL,
                  notes TEXT,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS firmware_jobs (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  device_id TEXT NOT NULL,
                  package_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                );
                """
            )

    def list_packages(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        rows = list(
            conn.execute(
                "SELECT * FROM firmware_packages WHERE status = ? ORDER BY created_at DESC",
                (FIRMWARE_PACKAGE_ACTIVE,),
            ).fetchall()
        )
        if rows:
            return rows
        conn.execute(
            """
            INSERT INTO firmware_packages(id, version, channel, status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "fw_dev_0_1_0",
                "0.1.0-dev",
                "dev",
                FIRMWARE_PACKAGE_ACTIVE,
                "V1 boundary package for mock OTA status only.",
                0,
            ),
        )
        return list(
            conn.execute(
                "SELECT * FROM firmware_packages WHERE status = ? ORDER BY created_at DESC",
                (FIRMWARE_PACKAGE_ACTIVE,),
            ).fetchall()
        )

    def get_package(self, conn: sqlite3.Connection, package_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM firmware_packages WHERE id = ?",
            (package_id,),
        ).fetchone()

    def latest_job_for_device(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        device_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM firmware_jobs
            WHERE family_id = ? AND device_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (family_id, device_id),
        ).fetchone()

    def create_job(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        device_id: str,
        package_id: str,
        now: int,
    ) -> sqlite3.Row:
        job_id = f"fwjob_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO firmware_jobs(
              id, family_id, device_id, package_id, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, family_id, device_id, package_id, FIRMWARE_SCHEDULED, now, now),
        )
        return conn.execute("SELECT * FROM firmware_jobs WHERE id = ?", (job_id,)).fetchone()
