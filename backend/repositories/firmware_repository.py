from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow
from models.firmware import FIRMWARE_PACKAGE_ACTIVE, FIRMWARE_SCHEDULED


class FirmwareRepository:
    def __init__(self, database: Database):
        self.database = database
        self.ensure_schema()

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def ensure_schema(self) -> None:
        if not self.database.allow_runtime_schema_creation:
            return
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS firmware_packages (
                  id VARCHAR(255) PRIMARY KEY,
                  version VARCHAR(255) NOT NULL,
                  channel VARCHAR(255) NOT NULL,
                  status VARCHAR(255) NOT NULL,
                  notes TEXT,
                  created_at BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS firmware_jobs (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  device_id VARCHAR(255) NOT NULL,
                  package_id VARCHAR(255) NOT NULL,
                  status VARCHAR(255) NOT NULL,
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL
                );
                """
            )

    def list_packages(self, conn: DatabaseConnection) -> list[DatabaseRow]:
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

    def get_package(self, conn: DatabaseConnection, package_id: str) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM firmware_packages WHERE id = ?",
            (package_id,),
        ).fetchone()

    def latest_job_for_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
    ) -> DatabaseRow | None:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        package_id: str,
        now: int,
    ) -> DatabaseRow:
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
