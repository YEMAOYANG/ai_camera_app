from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class AuthRepository:
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
                CREATE TABLE IF NOT EXISTS families (
                  id VARCHAR(255) PRIMARY KEY,
                  name VARCHAR(255) NOT NULL,
                  family_code VARCHAR(32) UNIQUE,
                  family_code_updated_at BIGINT,
                  created_at BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                  id VARCHAR(255) PRIMARY KEY,
                  phone VARCHAR(255) NOT NULL UNIQUE,
                  family_id VARCHAR(255) NOT NULL,
                  display_name VARCHAR(255) NOT NULL,
                  account_status VARCHAR(255) NOT NULL DEFAULT 'active',
                  created_at BIGINT NOT NULL,
                  deletion_requested_at BIGINT,
                  deleted_at BIGINT
                );

                CREATE TABLE IF NOT EXISTS sms_codes (
                  phone VARCHAR(255) NOT NULL,
                  purpose VARCHAR(32) NOT NULL,
                  code_hash VARCHAR(255) NOT NULL,
                  expires_at BIGINT NOT NULL,
                  created_at BIGINT NOT NULL,
                  attempt_count INTEGER NOT NULL DEFAULT 0,
                  last_sent_at BIGINT NOT NULL,
                  PRIMARY KEY (phone, purpose),
                  CHECK (purpose IN ('login', 'phone_change'))
                );

                CREATE TABLE IF NOT EXISTS sms_send_windows (
                  scope_key VARCHAR(128) NOT NULL,
                  window_start BIGINT NOT NULL,
                  reserved_count INTEGER NOT NULL,
                  updated_at BIGINT NOT NULL,
                  PRIMARY KEY (scope_key, window_start),
                  CHECK (reserved_count >= 0)
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  id VARCHAR(255) PRIMARY KEY,
                  user_id VARCHAR(255) NOT NULL,
                  device_label VARCHAR(255),
                  device_type VARCHAR(255),
                  device_model VARCHAR(255),
                  device_hardware VARCHAR(255),
                  platform VARCHAR(255),
                  os_version VARCHAR(255),
                  app_version VARCHAR(255),
                  last_active_at BIGINT,
                  access_hash VARCHAR(255) NOT NULL UNIQUE,
                  refresh_hash VARCHAR(255) NOT NULL UNIQUE,
                  access_expires_at BIGINT NOT NULL,
                  refresh_expires_at BIGINT NOT NULL,
                  created_at BIGINT NOT NULL,
                  rotated_at BIGINT,
                  revoked_at BIGINT
                );
                """
            )

    def reserve_sms_send_budget(
        self,
        conn: DatabaseConnection,
        *,
        now: int,
        scope_key: str,
        window_seconds: int,
        max_sends: int,
    ) -> bool:
        """Atomically reserve one provider submission in a scoped window."""
        if max_sends < 1 or window_seconds < 1:
            return False
        window_ms = window_seconds * 1000
        window_start = now - now % window_ms
        cursor = conn.execute(
            """
            INSERT INTO sms_send_windows(
              scope_key, window_start, reserved_count, updated_at
            ) VALUES (?, ?, 1, ?)
            ON CONFLICT (scope_key, window_start) DO UPDATE SET
              reserved_count = sms_send_windows.reserved_count + 1,
              updated_at = EXCLUDED.updated_at
            WHERE sms_send_windows.reserved_count < ?
            """,
            (scope_key, window_start, now, max_sends),
        )
        conn.execute(
            "DELETE FROM sms_send_windows WHERE window_start < ?",
            (now - 7 * 24 * 60 * 60 * 1000,),
        )
        return cursor.rowcount == 1

    def reserve_sms_code(
        self,
        conn: DatabaseConnection,
        *,
        phone: str,
        purpose: str,
        code_hash: str,
        expires_at: int,
        created_at: int,
        resend_cooldown_seconds: int,
    ) -> bool:
        """Atomically reserve one provider send for a phone and purpose.

        The single INSERT/ON CONFLICT statement closes the first-request race:
        concurrent requests cannot both observe an absent row and send separate
        messages. The reservation intentionally commits before the provider is
        called, so an ambiguous provider timeout still enforces the cooldown.
        """
        cursor = conn.execute(
            """
            INSERT INTO sms_codes(
              phone, purpose, code_hash, expires_at, created_at, attempt_count, last_sent_at
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT (phone, purpose) DO UPDATE SET
              code_hash = EXCLUDED.code_hash,
              expires_at = EXCLUDED.expires_at,
              created_at = EXCLUDED.created_at,
              attempt_count = 0,
              last_sent_at = EXCLUDED.last_sent_at
            WHERE sms_codes.last_sent_at <= ?
            """,
            (
                phone,
                purpose,
                code_hash,
                expires_at,
                created_at,
                created_at,
                created_at - max(0, resend_cooldown_seconds) * 1000,
            ),
        )
        return cursor.rowcount == 1

    def find_sms_code(
        self,
        conn: DatabaseConnection,
        phone: str,
        *,
        purpose: str = "login",
        for_update: bool = False,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM sms_codes WHERE phone = ? AND purpose = ?"
            + (" FOR UPDATE" if for_update else ""),
            (phone, purpose),
        ).fetchone()

    def delete_sms_code(
        self,
        conn: DatabaseConnection,
        phone: str,
        *,
        purpose: str = "login",
    ) -> None:
        conn.execute(
            "DELETE FROM sms_codes WHERE phone = ? AND purpose = ?",
            (phone, purpose),
        )

    def increment_sms_attempts(
        self,
        conn: DatabaseConnection,
        phone: str,
        *,
        purpose: str = "login",
    ) -> None:
        conn.execute(
            """
            UPDATE sms_codes SET attempt_count = attempt_count + 1
            WHERE phone = ? AND purpose = ?
            """,
            (phone, purpose),
        )

    def find_user_by_phone(self, conn: DatabaseConnection, phone: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()

    def find_user_by_id(self, conn: DatabaseConnection, user_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def find_family_by_id(self, conn: DatabaseConnection, family_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()

    def list_pending_family_invitations_by_phone(
        self,
        conn: DatabaseConnection,
        phone: str,
        *,
        now: int,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT fi.*, f.name AS family_name, role_item.label AS role_label
                FROM family_invitations fi
                JOIN families f ON f.id = fi.family_id
                LEFT JOIN app_option_items role_item
                  ON role_item.catalog_key = 'family_role'
                 AND role_item.item_key = fi.role
                 AND role_item.enabled = 1
                WHERE fi.phone = ?
                  AND fi.status = 'pending'
                  AND (fi.expires_at IS NULL OR fi.expires_at >= ?)
                  AND NOT EXISTS (
                    SELECT 1
                    FROM family_members fm
                    WHERE fm.family_id = fi.family_id
                      AND fm.phone = fi.phone
                      AND fm.status = 'active'
                      AND fm.user_id IS NOT NULL
                  )
                ORDER BY fi.created_at DESC
                """,
                (phone, now),
            ).fetchall()
        )

    def create_parent_user(
        self,
        conn: DatabaseConnection,
        *,
        phone: str,
        now: int,
    ) -> DatabaseRow:
        family_id = f"fam_{uuid.uuid4().hex}"
        user_id = f"user_{uuid.uuid4().hex}"
        family_code = _new_family_code()
        conn.execute(
            "INSERT INTO families(id, name, family_code, family_code_updated_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (family_id, "我的家庭", family_code, now, now),
        )
        conn.execute(
            """
            INSERT INTO users(id, phone, family_id, display_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, phone, family_id, "家长", now),
        )
        user = self.find_user_by_id(conn, user_id)
        if user is None:
            raise RuntimeError("created user could not be loaded")
        return user

    def create_session(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        device_label: str,
        device_type: str,
        device_model: str,
        device_hardware: str,
        platform: str,
        os_version: str,
        app_version: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        created_at: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sessions(
              id, user_id, device_label, device_type, device_model, device_hardware,
              platform, os_version, app_version, last_active_at,
              access_hash, refresh_hash,
              access_expires_at, refresh_expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{uuid.uuid4().hex}",
                user_id,
                device_label,
                device_type,
                device_model,
                device_hardware,
                platform,
                os_version,
                app_version,
                created_at,
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                created_at,
            ),
        )

    def revoke_matching_device_sessions(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        device_label: str,
        device_type: str,
        device_model: str,
        device_hardware: str,
        platform: str,
        os_version: str,
        app_version: str,
        revoked_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE user_id = ?
              AND revoked_at IS NULL
              AND COALESCE(device_label, '') = ?
              AND COALESCE(device_type, '') = ?
              AND COALESCE(device_model, '') = ?
              AND COALESCE(device_hardware, '') = ?
              AND COALESCE(platform, '') = ?
              AND COALESCE(os_version, '') = ?
              AND COALESCE(app_version, '') = ?
            """,
            (
                revoked_at,
                user_id,
                device_label,
                device_type,
                device_model,
                device_hardware,
                platform,
                os_version,
                app_version,
            ),
        )

    def find_session_by_refresh_hash(
        self,
        conn: DatabaseConnection,
        refresh_hash: str,
        *,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM sessions
            WHERE refresh_hash = ? AND revoked_at IS NULL
            """ + (" FOR UPDATE" if for_update else ""),
            (refresh_hash,),
        ).fetchone()

    def find_session_by_access_hash(
        self,
        conn: DatabaseConnection,
        access_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM sessions
            WHERE access_hash = ? AND revoked_at IS NULL
            """,
            (access_hash,),
        ).fetchone()

    def rotate_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        device_label: str,
        device_type: str,
        device_model: str,
        device_hardware: str,
        platform: str,
        os_version: str,
        app_version: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        rotated_at: int,
        expected_refresh_hash: str,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE sessions SET
              device_label = ?,
              device_type = ?,
              device_model = ?,
              device_hardware = ?,
              platform = ?,
              os_version = ?,
              app_version = ?,
              last_active_at = ?,
              access_hash = ?,
              refresh_hash = ?,
              access_expires_at = ?,
              refresh_expires_at = ?,
              rotated_at = ?
            WHERE id = ? AND refresh_hash = ? AND revoked_at IS NULL
            """,
            (
                device_label,
                device_type,
                device_model,
                device_hardware,
                platform,
                os_version,
                app_version,
                rotated_at,
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                rotated_at,
                session_id,
                expected_refresh_hash,
            ),
        )
        return cursor.rowcount == 1

    def touch_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        last_active_at: int,
    ) -> None:
        conn.execute(
            "UPDATE sessions SET last_active_at = ? WHERE id = ?",
            (last_active_at, session_id),
        )

    def revoke_sessions(
        self,
        *,
        access_hash: str | None,
        refresh_hash: str | None,
        revoked_at: int,
    ) -> None:
        clauses = []
        values: list[str | int] = [revoked_at]
        if access_hash:
            clauses.append("access_hash = ?")
            values.append(access_hash)
        if refresh_hash:
            clauses.append("refresh_hash = ?")
            values.append(refresh_hash)
        if not clauses:
            return
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL AND ({' OR '.join(clauses)})",
                values,
            )


def _new_family_code() -> str:
    return uuid.uuid4().hex[:8].upper()
