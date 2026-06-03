from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class DeviceRepository:
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
                CREATE TABLE IF NOT EXISTS devices (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  binding_code VARCHAR(255),
                  name VARCHAR(255) NOT NULL,
                  location VARCHAR(255),
                  status VARCHAR(255) NOT NULL,
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL
                );
                """
            )

    def list_devices(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                "SELECT * FROM devices WHERE family_id = ? ORDER BY created_at DESC",
                (family_id,),
            ).fetchall()
        )

    def get_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM devices WHERE family_id = ? AND id = ?",
            (family_id, device_id),
        ).fetchone()
