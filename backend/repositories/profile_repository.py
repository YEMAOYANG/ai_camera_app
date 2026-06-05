from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class ProfileRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def get_user(self, conn: DatabaseConnection, user_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def get_family(self, conn: DatabaseConnection, family_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()

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

    def update_user_profile(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        display_name: str | None,
    ) -> DatabaseRow:
        if display_name is not None:
            conn.execute("UPDATE users SET display_name = ? WHERE id = ?", (display_name, user_id))
        return self.get_user(conn, user_id)

    def update_family_name(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str | None,
    ) -> DatabaseRow:
        if name is not None:
            conn.execute("UPDATE families SET name = ? WHERE id = ?", (name, family_id))
        return self.get_family(conn, family_id)

    def upsert_parent_identity(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        display_name: str,
        relationship: str,
        now: int,
    ) -> DatabaseRow:
        existing = self.get_parent_identity(conn, family_id=family_id)
        if existing:
            conn.execute(
                """
                UPDATE parent_identities
                SET display_name = ?, relationship = ?, confirmed_at = ?
                WHERE family_id = ?
                """,
                (display_name, relationship, now, family_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO parent_identities(family_id, display_name, relationship, confirmed_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_id, display_name, relationship, now),
            )
        return self.get_parent_identity(conn, family_id=family_id)

    def list_sessions(self, conn: DatabaseConnection, *, user_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ?
                ORDER BY COALESCE(rotated_at, created_at) DESC
                LIMIT 8
                """,
                (user_id,),
            ).fetchall()
        )

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
        row = conn.execute(
            """
            SELECT * FROM family_members
            WHERE family_id = ? AND user_id = ?
            LIMIT 1
            """,
            (family_id, user_id),
        ).fetchone()
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
        return self.get_family_member(conn, family_id=family_id, member_id=member_id)

    def list_family_members(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM family_members
                WHERE family_id = ?
                ORDER BY role = 'admin' DESC, created_at
                """,
                (family_id,),
            ).fetchall()
        )

    def get_family_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        member_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM family_members WHERE family_id = ? AND id = ?",
            (family_id, member_id),
        ).fetchone()

    def create_family_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str,
        phone: str | None,
        role: str,
        status: str,
        notify_enabled: bool,
        now: int,
    ) -> DatabaseRow:
        member_id = f"member_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO family_members(
              id, family_id, user_id, name, phone, role, status,
              notify_enabled, created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            """,
            (member_id, family_id, name, phone, role, status, int(notify_enabled), now, now),
        )
        return self.get_family_member(conn, family_id=family_id, member_id=member_id)

    def update_family_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        member_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, family_id, member_id]
            conn.execute(
                f"""
                UPDATE family_members
                SET {', '.join(assignments)}, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                values,
            )
        return self.get_family_member(conn, family_id=family_id, member_id=member_id)

    def delete_family_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        member_id: str,
    ) -> None:
        conn.execute(
            "DELETE FROM family_members WHERE family_id = ? AND id = ?",
            (family_id, member_id),
        )

    def list_family_invitations(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM family_invitations
                WHERE family_id = ? AND status = 'pending'
                ORDER BY created_at DESC
                """,
                (family_id,),
            ).fetchall()
        )

    def get_family_invitation(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        invitation_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM family_invitations WHERE family_id = ? AND id = ?",
            (family_id, invitation_id),
        ).fetchone()

    def create_family_invitation(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str,
        phone: str,
        role: str,
        created_by: str,
        now: int,
        expires_at: int | None,
    ) -> DatabaseRow:
        invitation_id = f"invite_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO family_invitations(
              id, family_id, name, phone, role, status, created_by,
              created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (invitation_id, family_id, name, phone, role, created_by, now, now, expires_at),
        )
        return self.get_family_invitation(
            conn,
            family_id=family_id,
            invitation_id=invitation_id,
        )

    def update_family_invitation(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        invitation_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, family_id, invitation_id]
            conn.execute(
                f"""
                UPDATE family_invitations
                SET {', '.join(assignments)}, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                values,
            )
        return self.get_family_invitation(
            conn,
            family_id=family_id,
            invitation_id=invitation_id,
        )

    def list_children(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                "SELECT * FROM children WHERE family_id = ? ORDER BY created_at",
                (family_id,),
            ).fetchall()
        )

    def current_child(self, conn: DatabaseConnection, *, family_id: str) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM children WHERE family_id = ? ORDER BY created_at LIMIT 1",
            (family_id,),
        ).fetchone()

    def get_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()

    def update_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, family_id, child_id]
            conn.execute(
                f"""
                UPDATE children
                SET {', '.join(assignments)}, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                values,
            )
        return self.get_child(conn, family_id=family_id, child_id=child_id)

    def list_contacts(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM emergency_contacts
                WHERE family_id = ?
                ORDER BY priority, created_at
                """,
                (family_id,),
            ).fetchall()
        )

    def get_contact(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        contact_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM emergency_contacts WHERE family_id = ? AND id = ?",
            (family_id, contact_id),
        ).fetchone()

    def create_contact(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str,
        phone: str,
        relationship: str | None,
        default_notify: bool,
        now: int,
    ) -> DatabaseRow:
        contact_id = f"contact_{uuid.uuid4().hex}"
        priority_row = conn.execute(
            "SELECT COALESCE(MAX(priority), 0) AS max_priority FROM emergency_contacts WHERE family_id = ?",
            (family_id,),
        ).fetchone()
        priority = int(priority_row["max_priority"] or 0) + 1
        conn.execute(
            """
            INSERT INTO emergency_contacts(
              id, family_id, name, phone, relationship, priority,
              default_notify, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (contact_id, family_id, name, phone, relationship, priority, int(default_notify), now, now),
        )
        return self.get_contact(conn, family_id=family_id, contact_id=contact_id)

    def update_contact(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        contact_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, family_id, contact_id]
            conn.execute(
                f"""
                UPDATE emergency_contacts
                SET {', '.join(assignments)}, updated_at = ?
                WHERE family_id = ? AND id = ?
                """,
                values,
            )
        return self.get_contact(conn, family_id=family_id, contact_id=contact_id)

    def delete_contact(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        contact_id: str,
    ) -> None:
        conn.execute(
            "DELETE FROM emergency_contacts WHERE family_id = ? AND id = ?",
            (family_id, contact_id),
        )

    def get_setting(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        key: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM app_settings WHERE family_id = ? AND setting_key = ?",
            (family_id, key),
        ).fetchone()

    def upsert_setting(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        key: str,
        value: dict,
        now: int,
    ) -> DatabaseRow:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        existing = self.get_setting(conn, family_id=family_id, key=key)
        if existing:
            conn.execute(
                """
                UPDATE app_settings
                SET value = ?, updated_at = ?
                WHERE family_id = ? AND setting_key = ?
                """,
                (encoded, now, family_id, key),
            )
        else:
            conn.execute(
                """
                INSERT INTO app_settings(family_id, setting_key, value, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (family_id, key, encoded, now),
            )
        return self.get_setting(conn, family_id=family_id, key=key)

    def count_devices(self, conn: DatabaseConnection, *, family_id: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM devices WHERE family_id = ? AND status <> 'unbound'",
            (family_id,),
        ).fetchone()
        return int(row["count"] or 0)

    def count_pending_items(self, conn: DatabaseConnection, *, family_id: str) -> int:
        task_row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM tasks
            WHERE family_id = ?
              AND status IN ('awaiting_parent_confirmation', 'delayed', 'missed')
            """,
            (family_id,),
        ).fetchone()
        redemption_row = conn.execute(
            """
            SELECT COUNT(*) AS count FROM reward_redemptions
            WHERE family_id = ? AND status = 'redeemed'
            """,
            (family_id,),
        ).fetchone()
        return int(task_row["count"] or 0) + int(redemption_row["count"] or 0)

    def create_feedback(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
        category: str,
        content: str,
        now: int,
    ) -> DatabaseRow:
        feedback_id = f"feedback_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO feedback_items(id, family_id, user_id, category, content, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'received', ?)
            """,
            (feedback_id, family_id, user_id, category, content, now),
        )
        return conn.execute(
            "SELECT * FROM feedback_items WHERE id = ?",
            (feedback_id,),
        ).fetchone()
