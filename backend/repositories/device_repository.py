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
                CREATE TABLE IF NOT EXISTS family_default_devices (
                  family_id VARCHAR(255) PRIMARY KEY,
                  device_id VARCHAR(255) NOT NULL,
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS device_runtime_configs (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  device_id VARCHAR(255) NOT NULL,
                  provider VARCHAR(64) NOT NULL,
                  config_json TEXT,
                  secret_ref VARCHAR(255),
                  status VARCHAR(64) NOT NULL DEFAULT 'active',
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL,
                  UNIQUE (family_id, device_id)
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
                """
                SELECT d.*,
                  CASE WHEN fdd.device_id = d.id THEN 1 ELSE 0 END AS is_default
                FROM devices d
                LEFT JOIN family_default_devices fdd
                  ON fdd.family_id = d.family_id AND fdd.device_id = d.id
                WHERE d.family_id = ? AND d.status <> 'unbound'
                ORDER BY d.created_at DESC
                """,
                (family_id,),
            ).fetchall()
        )

    def list_active_observation_devices(
        self,
        conn: DatabaseConnection,
        *,
        after_family_id: str | None = None,
        after_device_id: str | None = None,
        limit: int = 8,
    ) -> list[DatabaseRow]:
        """List bound ONVIF devices without exposing runtime config or secrets."""

        clauses = [
            "d.status <> 'unbound'",
            "drc.status = 'active'",
            "drc.provider = 'onvif_rtsp'",
        ]
        values: list[object] = []
        if after_family_id and after_device_id:
            clauses.append(
                "(d.family_id > ? OR (d.family_id = ? AND d.id > ?))"
            )
            values.extend(
                [after_family_id, after_family_id, after_device_id]
            )
        values.append(max(1, min(int(limit), 100)))
        return list(
            conn.execute(
                f"""
                SELECT d.family_id, d.id AS device_id
                FROM devices d
                JOIN device_runtime_configs drc
                  ON drc.family_id = d.family_id AND drc.device_id = d.id
                WHERE {' AND '.join(clauses)}
                ORDER BY d.family_id, d.id
                LIMIT ?
                """,
                values,
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
            """
            SELECT d.*,
              CASE WHEN fdd.device_id = d.id THEN 1 ELSE 0 END AS is_default
            FROM devices d
            LEFT JOIN family_default_devices fdd
              ON fdd.family_id = d.family_id AND fdd.device_id = d.id
            WHERE d.family_id = ? AND d.id = ?
            """,
            (family_id, device_id),
        ).fetchone()

    def get_default_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT d.*, 1 AS is_default
            FROM family_default_devices fdd
            JOIN devices d ON d.id = fdd.device_id
            WHERE fdd.family_id = ? AND d.family_id = ? AND d.status <> 'unbound'
            LIMIT 1
            """,
            (family_id, family_id),
        ).fetchone()

    def get_default_device_ref(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM family_default_devices WHERE family_id = ?",
            (family_id,),
        ).fetchone()

    def set_default_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        now: int,
    ) -> DatabaseRow | None:
        existing = self.get_default_device_ref(conn, family_id=family_id)
        if existing:
            conn.execute(
                """
                UPDATE family_default_devices
                SET device_id = ?, updated_at = ?
                WHERE family_id = ?
                """,
                (device_id, now, family_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO family_default_devices(family_id, device_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_id, device_id, now, now),
            )
        return self.get_device(conn, family_id=family_id, device_id=device_id)

    def clear_default_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> None:
        conn.execute("DELETE FROM family_default_devices WHERE family_id = ?", (family_id,))

    def find_replacement_default_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        exclude_device_id: str | None = None,
    ) -> DatabaseRow | None:
        clauses = ["family_id = ?", "status <> 'unbound'"]
        values: list[str] = [family_id]
        if exclude_device_id:
            clauses.append("id <> ?")
            values.append(exclude_device_id)
        return conn.execute(
            f"""
            SELECT *
            FROM devices
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            values,
        ).fetchone()

    def ensure_default_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        now: int,
    ) -> DatabaseRow | None:
        current = self.get_default_device(conn, family_id=family_id)
        if current:
            return current
        stale_ref = self.get_default_device_ref(conn, family_id=family_id)
        replacement = self.find_replacement_default_device(conn, family_id=family_id)
        if replacement:
            return self.set_default_device(
                conn,
                family_id=family_id,
                device_id=replacement["id"],
                now=now,
            )
        if stale_ref:
            self.clear_default_device(conn, family_id=family_id)
        return None

    def find_active_device_by_binding_code(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        binding_code: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM devices
            WHERE family_id = ? AND binding_code = ? AND status <> 'unbound'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (family_id, binding_code),
        ).fetchone()

    def find_active_device_by_binding_code_global(
        self,
        conn: DatabaseConnection,
        *,
        binding_code: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM devices
            WHERE binding_code = ? AND status <> 'unbound'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (binding_code,),
        ).fetchone()

    def find_unbound_device_by_binding_code(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        binding_code: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM devices
            WHERE family_id = ? AND binding_code = ? AND status = 'unbound'
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (family_id, binding_code),
        ).fetchone()

    def create_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        binding_code: str | None,
        name: str,
        location: str | None,
        now: int,
    ) -> DatabaseRow:
        device_id = f"dev_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO devices(
              id, family_id, binding_code, name, location, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'bound', ?, ?)
            """,
            (device_id, family_id, binding_code, name, location, now, now),
        )
        return self.get_device(conn, family_id=family_id, device_id=device_id)

    def rebind_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        name: str,
        location: str | None,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE devices
            SET name = ?, location = ?, status = 'bound', unbound_at = NULL, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (name, location, now, family_id, device_id),
        )
        return self.get_device(conn, family_id=family_id, device_id=device_id)

    def get_device_runtime_config(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM device_runtime_configs
            WHERE family_id = ? AND device_id = ? AND status = 'active'
            LIMIT 1
            """,
            (family_id, device_id),
        ).fetchone()

    def get_onvif_runtime_recovery_state(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        return conn.execute(
            f"""
            SELECT
              d.binding_code,
              d.status AS device_status,
              drc.id AS runtime_config_id,
              drc.provider,
              drc.config_json,
              drc.secret_ref,
              drc.status AS runtime_status,
              drc.updated_at
            FROM devices d
            JOIN device_runtime_configs drc
              ON drc.family_id = d.family_id AND drc.device_id = d.id
            WHERE d.family_id = ? AND d.id = ?
            LIMIT 1{lock_clause}
            """,
            (family_id, device_id),
        ).fetchone()

    def update_onvif_runtime_config_json(
        self,
        conn: DatabaseConnection,
        *,
        runtime_config_id: str,
        config_json: str,
        now: int,
    ) -> bool:
        updated = conn.execute(
            """
            UPDATE device_runtime_configs
            SET config_json = ?, updated_at = ?
            WHERE id = ? AND provider = 'onvif_rtsp' AND status = 'active'
            """,
            (config_json, now, runtime_config_id),
        )
        return updated.rowcount == 1

    def upsert_device_runtime_config(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        provider: str,
        config_json: str | None,
        secret_ref: str | None,
        status: str,
        now: int,
    ) -> DatabaseRow | None:
        existing = conn.execute(
            """
            SELECT id
            FROM device_runtime_configs
            WHERE family_id = ? AND device_id = ?
            LIMIT 1
            """,
            (family_id, device_id),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE device_runtime_configs
                SET provider = ?, config_json = ?, secret_ref = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (provider, config_json, secret_ref, status, now, existing["id"]),
            )
        else:
            config_id = f"drt_{uuid.uuid4().hex}"
            conn.execute(
                """
                INSERT INTO device_runtime_configs(
                  id, family_id, device_id, provider, config_json, secret_ref,
                  status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config_id,
                    family_id,
                    device_id,
                    provider,
                    config_json,
                    secret_ref,
                    status,
                    now,
                    now,
                ),
            )
        return self.get_device_runtime_config(conn, family_id=family_id, device_id=device_id)

    def create_onvif_discovery_session(
        self,
        conn: DatabaseConnection,
        *,
        token_hash: str,
        family_id: str,
        user_id: str,
        binding_code: str,
        metadata_json: str,
        expires_at: int,
        now: int,
    ) -> DatabaseRow:
        session_id = f"ods_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO onvif_discovery_sessions(
              id, token_hash, family_id, user_id, binding_code, metadata_json,
              expires_at, consumed_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                session_id,
                token_hash,
                family_id,
                user_id,
                binding_code,
                metadata_json,
                expires_at,
                now,
            ),
        )
        return self.get_onvif_discovery_session(
            conn,
            token_hash=token_hash,
            family_id=family_id,
            user_id=user_id,
        )

    def get_onvif_discovery_session(
        self,
        conn: DatabaseConnection,
        *,
        token_hash: str,
        family_id: str,
        user_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM onvif_discovery_sessions
            WHERE token_hash = ? AND family_id = ? AND user_id = ?
            LIMIT 1
            """,
            (token_hash, family_id, user_id),
        ).fetchone()

    def consume_onvif_discovery_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        consumed_at: int,
    ) -> bool:
        result = conn.execute(
            """
            UPDATE onvif_discovery_sessions
            SET consumed_at = ?
            WHERE id = ? AND consumed_at IS NULL AND expires_at >= ?
            """,
            (consumed_at, session_id, consumed_at),
        )
        return result.rowcount == 1

    def delete_expired_onvif_discovery_sessions(
        self,
        conn: DatabaseConnection,
        *,
        before: int,
    ) -> None:
        conn.execute(
            """
            DELETE FROM onvif_discovery_sessions
            WHERE expires_at < ? OR consumed_at IS NOT NULL
            """,
            (before,),
        )

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
