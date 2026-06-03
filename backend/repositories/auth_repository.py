from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import SQLiteDatabase


class AuthRepository:
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
                CREATE TABLE IF NOT EXISTS families (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                  id TEXT PRIMARY KEY,
                  phone TEXT NOT NULL UNIQUE,
                  family_id TEXT NOT NULL,
                  display_name TEXT NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sms_codes (
                  phone TEXT PRIMARY KEY,
                  code_hash TEXT NOT NULL,
                  expires_at INTEGER NOT NULL,
                  created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                  id TEXT PRIMARY KEY,
                  user_id TEXT NOT NULL,
                  access_hash TEXT NOT NULL UNIQUE,
                  refresh_hash TEXT NOT NULL UNIQUE,
                  access_expires_at INTEGER NOT NULL,
                  refresh_expires_at INTEGER NOT NULL,
                  created_at INTEGER NOT NULL,
                  rotated_at INTEGER,
                  revoked_at INTEGER
                );
                """
            )

    def upsert_sms_code(
        self,
        conn: sqlite3.Connection,
        *,
        phone: str,
        code_hash: str,
        expires_at: int,
        created_at: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sms_codes(phone, code_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(phone) DO UPDATE SET
              code_hash = excluded.code_hash,
              expires_at = excluded.expires_at,
              created_at = excluded.created_at
            """,
            (phone, code_hash, expires_at, created_at),
        )

    def find_sms_code(self, conn: sqlite3.Connection, phone: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM sms_codes WHERE phone = ?", (phone,)).fetchone()

    def delete_sms_code(self, conn: sqlite3.Connection, phone: str) -> None:
        conn.execute("DELETE FROM sms_codes WHERE phone = ?", (phone,))

    def find_user_by_phone(self, conn: sqlite3.Connection, phone: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()

    def find_user_by_id(self, conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def find_family_by_id(self, conn: sqlite3.Connection, family_id: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()

    def create_parent_user(
        self,
        conn: sqlite3.Connection,
        *,
        phone: str,
        now: int,
    ) -> sqlite3.Row:
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
        conn: sqlite3.Connection,
        *,
        user_id: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        created_at: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sessions(
              id, user_id, access_hash, refresh_hash,
              access_expires_at, refresh_expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"sess_{uuid.uuid4().hex}",
                user_id,
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                created_at,
            ),
        )

    def find_session_by_refresh_hash(
        self,
        conn: sqlite3.Connection,
        refresh_hash: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM sessions
            WHERE refresh_hash = ? AND revoked_at IS NULL
            """,
            (refresh_hash,),
        ).fetchone()

    def find_session_by_access_hash(
        self,
        conn: sqlite3.Connection,
        access_hash: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM sessions
            WHERE access_hash = ? AND revoked_at IS NULL
            """,
            (access_hash,),
        ).fetchone()

    def rotate_session(
        self,
        conn: sqlite3.Connection,
        *,
        session_id: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        rotated_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE sessions SET
              access_hash = ?,
              refresh_hash = ?,
              access_expires_at = ?,
              refresh_expires_at = ?,
              rotated_at = ?
            WHERE id = ?
            """,
            (
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                rotated_at,
                session_id,
            ),
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
