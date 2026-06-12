from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import uuid

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
                  wake_name VARCHAR(255),
                  location VARCHAR(255),
                  status VARCHAR(255) NOT NULL,
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL
                );
                """
            )
            self._ensure_column(
                conn,
                table="devices",
                column="wake_name",
                definition="VARCHAR(255)",
            )

    def _ensure_column(
        self,
        conn: DatabaseConnection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in columns):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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

    def get_family_member_by_user(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM family_members
            WHERE family_id = ? AND user_id = ?
            LIMIT 1
            """,
            (family_id, user_id),
        ).fetchone()

    def get_app_option_item(
        self,
        conn: DatabaseConnection,
        *,
        catalog_key: str,
        item_key: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM app_option_items
            WHERE catalog_key = ? AND item_key = ? AND enabled = 1
            LIMIT 1
            """,
            (catalog_key, item_key),
        ).fetchone()

    def ensure_owner_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
        name: str,
        phone: str,
        now: int,
    ) -> DatabaseRow:
        row = self.get_family_member_by_user(
            conn,
            family_id=family_id,
            user_id=user_id,
        )
        if row:
            return row
        member_id = f"member_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO family_members(
              id, family_id, user_id, name, phone, role, status,
              notify_enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'admin', 'active', 1, ?, ?)
            """,
            (member_id, family_id, user_id, name or "家长", phone, now, now),
        )
        return self.get_family_member_by_user(
            conn,
            family_id=family_id,
            user_id=user_id,
        )

    def update_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, family_id, device_id]
            conn.execute(
                f"""
                UPDATE devices
                SET {', '.join(assignments)}, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                values,
            )
        return self.get_device(conn, family_id=family_id, device_id=device_id)

    def unbind_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE devices
            SET status = 'unbound', updated_at = ?, unbound_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (now, now, family_id, device_id),
        )
        return self.get_device(conn, family_id=family_id, device_id=device_id)
