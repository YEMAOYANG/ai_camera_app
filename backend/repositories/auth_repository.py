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
                  phone VARCHAR(255) PRIMARY KEY,
                  code_hash VARCHAR(255) NOT NULL,
                  expires_at BIGINT NOT NULL,
                  created_at BIGINT NOT NULL,
                  attempt_count INTEGER NOT NULL DEFAULT 0,
                  last_sent_at BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  id VARCHAR(255) PRIMARY KEY,
                  user_id VARCHAR(255) NOT NULL,
                  device_label VARCHAR(255),
                  device_type VARCHAR(255),
                  platform VARCHAR(255),
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

    def upsert_sms_code(
        self,
        conn: DatabaseConnection,
        *,
        phone: str,
        code_hash: str,
        expires_at: int,
        created_at: int,
    ) -> None:
        existing = self.find_sms_code(conn, phone)
        if existing:
            conn.execute(
                """
                UPDATE sms_codes
                SET code_hash = ?, expires_at = ?, created_at = ?, attempt_count = 0, last_sent_at = ?
                WHERE phone = ?
                """,
                (code_hash, expires_at, created_at, created_at, phone),
            )
            return

        conn.execute(
            """
            INSERT INTO sms_codes(phone, code_hash, expires_at, created_at, attempt_count, last_sent_at)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (phone, code_hash, expires_at, created_at, created_at),
        )

    def find_sms_code(self, conn: DatabaseConnection, phone: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM sms_codes WHERE phone = ?", (phone,)).fetchone()

    def delete_sms_code(self, conn: DatabaseConnection, phone: str) -> None:
        conn.execute("DELETE FROM sms_codes WHERE phone = ?", (phone,))

    def increment_sms_attempts(self, conn: DatabaseConnection, phone: str) -> None:
        conn.execute(
            "UPDATE sms_codes SET attempt_count = attempt_count + 1 WHERE phone = ?",
            (phone,),
        )

    def find_user_by_phone(self, conn: DatabaseConnection, phone: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()

    def find_user_by_id(self, conn: DatabaseConnection, user_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def find_family_by_id(self, conn: DatabaseConnection, family_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()

    def create_parent_user(
        self,
        conn: DatabaseConnection,
        *,
        phone: str,
        now: int,
    ) -> DatabaseRow:
        family_id = f"fam_{uuid.uuid4().hex}"
        user_id = f"user_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO families(id, name, created_at) VALUES (?, ?, ?)",
            (family_id, "我的家庭", now),
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
        platform: str,
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
              id, user_id, device_label, device_type, platform, app_version, last_active_at,
              access_hash, refresh_hash,
              access_expires_at, refresh_expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{uuid.uuid4().hex}",
                user_id,
                device_label,
                device_type,
                platform,
                app_version,
                created_at,
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                created_at,
            ),
        )

    def find_session_by_refresh_hash(
        self,
        conn: DatabaseConnection,
        refresh_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM sessions
            WHERE refresh_hash = ? AND revoked_at IS NULL
            """,
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
        platform: str,
        app_version: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        rotated_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE sessions SET
              device_label = ?,
              device_type = ?,
              platform = ?,
              app_version = ?,
              last_active_at = ?,
              access_hash = ?,
              refresh_hash = ?,
              access_expires_at = ?,
              refresh_expires_at = ?,
              rotated_at = ?
            WHERE id = ?
            """,
            (
                device_label,
                device_type,
                platform,
                app_version,
                rotated_at,
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                rotated_at,
                session_id,
            ),
        )

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
