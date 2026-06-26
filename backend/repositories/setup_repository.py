from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow
from models.setup import SETUP_DONE, SETUP_PENDING, SetupProgress
from schemas.setup import setup_progress_from_row


class SetupRepository:
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
                CREATE TABLE IF NOT EXISTS setup_progress (
                  family_id VARCHAR(255) PRIMARY KEY,
                  completed INTEGER NOT NULL DEFAULT 0,
                  parent_identity_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  device_binding_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  wifi_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  child_profile_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  camera_name_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  camera_name_intro_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  camera_name_intro_at BIGINT,
                  contacts_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL,
                  completed_at BIGINT
                );

                CREATE TABLE IF NOT EXISTS parent_identities (
                  family_id VARCHAR(255) PRIMARY KEY,
                  display_name VARCHAR(255) NOT NULL,
                  relationship VARCHAR(255) NOT NULL,
                  relationship_key VARCHAR(255),
                  confirmed_at BIGINT NOT NULL
                );

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

                CREATE TABLE IF NOT EXISTS wifi_configs (
                  family_id VARCHAR(255) PRIMARY KEY,
                  ssid VARCHAR(255) NOT NULL,
                  auth_type VARCHAR(255) NOT NULL,
                  password_set INTEGER NOT NULL,
                  saved_at BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS children (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  name VARCHAR(255) NOT NULL,
                  nickname VARCHAR(255),
                  gender VARCHAR(255) NOT NULL DEFAULT 'unspecified',
                  age_stage VARCHAR(255),
                  education_stage VARCHAR(255),
                  grade VARCHAR(255),
                  birthday VARCHAR(255),
                  sleep_time VARCHAR(255),
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS emergency_contacts (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  name VARCHAR(255) NOT NULL,
                  phone VARCHAR(255) NOT NULL,
                  relationship VARCHAR(255),
                  relationship_key VARCHAR(255),
                  priority INTEGER NOT NULL,
                  created_at BIGINT NOT NULL
                );
                """
            )
            self._ensure_column(
                conn,
                table="children",
                column="sleep_time",
                definition="VARCHAR(255)",
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

    def get_or_create_progress(
        self,
        conn: DatabaseConnection,
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
                  wifi_status, child_profile_status, camera_name_status,
                  camera_name_intro_status, contacts_status, created_at, updated_at
                )
                VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    family_id,
                    SETUP_PENDING,
                    SETUP_PENDING,
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
        conn: DatabaseConnection,
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
            "camera_name_status",
            "camera_name_intro_status",
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        display_name: str,
        relationship: str,
        relationship_key: str,
        now: int,
    ) -> None:
        existing = conn.execute(
            "SELECT family_id FROM parent_identities WHERE family_id = ?",
            (family_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE parent_identities
                SET display_name = ?, relationship = ?, relationship_key = ?, confirmed_at = ?
                WHERE family_id = ?
                """,
                (display_name, relationship, relationship_key, now, family_id),
            )
            return

        conn.execute(
            """
            INSERT INTO parent_identities(
              family_id, display_name, relationship, relationship_key, confirmed_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (family_id, display_name, relationship, relationship_key, now),
        )

    def list_app_option_items(
        self,
        conn: DatabaseConnection,
        *,
        catalog_key: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT *
                FROM app_option_items
                WHERE catalog_key = ? AND enabled = 1
                ORDER BY COALESCE(parent_key, ''), sort_order, item_key
                """,
                (catalog_key,),
            ).fetchall()
        )

    def get_parent_identity(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM parent_identities WHERE family_id = ?",
            (family_id,),
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
            WHERE family_id = ? AND user_id = ? AND status = 'active'
            LIMIT 1
            """,
            (family_id, user_id),
        ).fetchone()

    def upsert_family_member_role(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
        name: str,
        relationship_key: str,
        phone: str,
        role: str,
        now: int,
    ) -> DatabaseRow:
        existing = self.get_family_member_by_user(
            conn,
            family_id=family_id,
            user_id=user_id,
        )
        if existing:
            conn.execute(
                """
                UPDATE family_members
                SET name = ?, relationship_key = ?, phone = ?, role = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name or existing["name"],
                    relationship_key,
                    phone or existing["phone"],
                    role,
                    now,
                    existing["id"],
                ),
            )
            return self.get_family_member_by_user(
                conn,
                family_id=family_id,
                user_id=user_id,
            )

        member_id = f"member_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO family_members(
              id, family_id, user_id, name, relationship_key, phone, role, status,
              notify_enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)
            """,
            (
                member_id,
                family_id,
                user_id,
                name or "家长",
                relationship_key,
                phone,
                role,
                now,
                now,
            ),
        )
        return self.get_family_member_by_user(
            conn,
            family_id=family_id,
            user_id=user_id,
        )

    def save_device(
        self,
        conn: DatabaseConnection,
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        ssid: str,
        auth_type: str,
        password_set: bool,
        now: int,
    ) -> None:
        existing = conn.execute(
            "SELECT family_id FROM wifi_configs WHERE family_id = ?",
            (family_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE wifi_configs
                SET ssid = ?, auth_type = ?, password_set = ?, saved_at = ?
                WHERE family_id = ?
                """,
                (ssid, auth_type, int(password_set), now, family_id),
            )
            return

        conn.execute(
            """
            INSERT INTO wifi_configs(family_id, ssid, auth_type, password_set, saved_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (family_id, ssid, auth_type, int(password_set), now),
        )

    def current_wifi(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM wifi_configs WHERE family_id = ?",
            (family_id,),
        ).fetchone()

    def save_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str,
        nickname: str | None,
        gender: str,
        age_stage: str | None,
        education_stage: str | None,
        grade: str | None,
        birthday: str | None,
        sleep_time: str | None,
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
                UPDATE children SET name = ?, nickname = ?, gender = ?,
                  age_stage = ?, education_stage = ?, grade = ?,
                  birthday = ?, sleep_time = ?, updated_at = ? WHERE id = ?
                """,
                (
                    name,
                    nickname,
                    gender,
                    age_stage,
                    education_stage,
                    grade,
                    birthday,
                    sleep_time,
                    now,
                    child_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, nickname, gender, age_stage, education_stage,
                  grade, birthday, sleep_time, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    child_id,
                    family_id,
                    name,
                    nickname,
                    gender,
                    age_stage,
                    education_stage,
                    grade,
                    birthday,
                    sleep_time,
                    now,
                    now,
                ),
            )
        return child_id

    def current_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM children WHERE family_id = ? ORDER BY created_at LIMIT 1",
            (family_id,),
        ).fetchone()

    def current_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM devices WHERE family_id = ? ORDER BY created_at LIMIT 1",
            (family_id,),
        ).fetchone()

    def save_camera_name(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
        wake_name: str,
        now: int,
    ) -> str | None:
        conn.execute(
            """
            UPDATE devices SET wake_name = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (wake_name, now, family_id, device_id),
        )
        return device_id

    def mark_camera_name_intro_attempt(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE setup_progress
            SET camera_name_intro_status = ?, camera_name_intro_at = ?, updated_at = ?
            WHERE family_id = ?
            """,
            (SETUP_DONE, now, now, family_id),
        )

    def replace_contacts(
        self,
        conn: DatabaseConnection,
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
                  id, family_id, name, phone, relationship, relationship_key, priority, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contact_id,
                    family_id,
                    contact["name"],
                    contact["phone"],
                    contact.get("relationship"),
                    contact.get("relationship_key"),
                    index + 1,
                    now,
                ),
            )
        return ids

    def complete_setup(
        self,
        conn: DatabaseConnection,
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
