from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import SQLiteDatabase
from models.setup import SETUP_DONE, SETUP_PENDING, SetupProgress
from schemas.setup import setup_progress_from_row


class SetupRepository:
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
                CREATE TABLE IF NOT EXISTS setup_progress (
                  family_id TEXT PRIMARY KEY,
                  completed INTEGER NOT NULL DEFAULT 0,
                  parent_identity_status TEXT NOT NULL DEFAULT 'pending',
                  device_binding_status TEXT NOT NULL DEFAULT 'pending',
                  wifi_status TEXT NOT NULL DEFAULT 'pending',
                  child_profile_status TEXT NOT NULL DEFAULT 'pending',
                  contacts_status TEXT NOT NULL DEFAULT 'pending',
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  completed_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS parent_identities (
                  family_id TEXT PRIMARY KEY,
                  display_name TEXT NOT NULL,
                  relationship TEXT NOT NULL,
                  confirmed_at INTEGER NOT NULL
                );

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

                CREATE TABLE IF NOT EXISTS wifi_configs (
                  family_id TEXT PRIMARY KEY,
                  ssid TEXT NOT NULL,
                  auth_type TEXT NOT NULL,
                  password_set INTEGER NOT NULL,
                  saved_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS children (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  nickname TEXT,
                  age_stage TEXT,
                  birthday TEXT,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS emergency_contacts (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  phone TEXT NOT NULL,
                  relationship TEXT,
                  priority INTEGER NOT NULL,
                  created_at INTEGER NOT NULL
                );
                """
            )

    def get_or_create_progress(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        now: int,
    ) -> SetupProgress:
        row = conn.execute(
            "SELECT * FROM setup_progress WHERE family_id = ?",
            (family_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO setup_progress(
                  family_id, completed, parent_identity_status, device_binding_status,
                  wifi_status, child_profile_status, contacts_status, created_at, updated_at
                )
                VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    family_id,
                    SETUP_PENDING,
                    SETUP_PENDING,
                    SETUP_PENDING,
                    SETUP_PENDING,
                    SETUP_PENDING,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM setup_progress WHERE family_id = ?",
                (family_id,),
            ).fetchone()
        return setup_progress_from_row(row)

    def mark_step_done(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        column: str,
        now: int,
    ) -> None:
        allowed = {
            "parent_identity_status",
            "device_binding_status",
            "wifi_status",
            "child_profile_status",
            "contacts_status",
        }
        if column not in allowed:
            raise ValueError(f"unsupported setup status column: {column}")
        conn.execute(
            f"UPDATE setup_progress SET {column} = ?, updated_at = ? WHERE family_id = ?",
            (SETUP_DONE, now, family_id),
        )

    def save_parent_identity(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        display_name: str,
        relationship: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO parent_identities(family_id, display_name, relationship, confirmed_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(family_id) DO UPDATE SET
              display_name = excluded.display_name,
              relationship = excluded.relationship,
              confirmed_at = excluded.confirmed_at
            """,
            (family_id, display_name, relationship, now),
        )

    def save_device(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        binding_code: str | None,
        name: str,
        location: str | None,
        now: int,
    ) -> str:
        row = conn.execute(
            "SELECT id FROM devices WHERE family_id = ? ORDER BY created_at LIMIT 1",
            (family_id,),
        ).fetchone()
        device_id = row["id"] if row else f"dev_{uuid.uuid4().hex}"
        if row:
            conn.execute(
                """
                UPDATE devices SET binding_code = ?, name = ?, location = ?,
                  status = ?, updated_at = ? WHERE id = ?
                """,
                (binding_code, name, location, "bound", now, device_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO devices(
                  id, family_id, binding_code, name, location, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, family_id, binding_code, name, location, "bound", now, now),
            )
        return device_id

    def save_wifi(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        ssid: str,
        auth_type: str,
        password_set: bool,
        now: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO wifi_configs(family_id, ssid, auth_type, password_set, saved_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(family_id) DO UPDATE SET
              ssid = excluded.ssid,
              auth_type = excluded.auth_type,
              password_set = excluded.password_set,
              saved_at = excluded.saved_at
            """,
            (family_id, ssid, auth_type, int(password_set), now),
        )

    def save_child(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        name: str,
        nickname: str | None,
        age_stage: str | None,
        birthday: str | None,
        now: int,
    ) -> str:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? ORDER BY created_at LIMIT 1",
            (family_id,),
        ).fetchone()
        child_id = row["id"] if row else f"child_{uuid.uuid4().hex}"
        if row:
            conn.execute(
                """
                UPDATE children SET name = ?, nickname = ?, age_stage = ?,
                  birthday = ?, updated_at = ? WHERE id = ?
                """,
                (name, nickname, age_stage, birthday, now, child_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, nickname, age_stage, birthday, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (child_id, family_id, name, nickname, age_stage, birthday, now, now),
            )
        return child_id

    def replace_contacts(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        contacts: list[dict],
        now: int,
    ) -> list[str]:
        conn.execute("DELETE FROM emergency_contacts WHERE family_id = ?", (family_id,))
        ids: list[str] = []
        for index, contact in enumerate(contacts):
            contact_id = f"contact_{uuid.uuid4().hex}"
            ids.append(contact_id)
            conn.execute(
                """
                INSERT INTO emergency_contacts(
                  id, family_id, name, phone, relationship, priority, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact_id,
                    family_id,
                    contact["name"],
                    contact["phone"],
                    contact.get("relationship"),
                    index + 1,
                    now,
                ),
            )
        return ids

    def complete_setup(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE setup_progress
            SET completed = 1, updated_at = ?, completed_at = ?
            WHERE family_id = ?
            """,
            (now, now, family_id),
        )
