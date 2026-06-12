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

    def get_user_by_phone(self, conn: DatabaseConnection, phone: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM users WHERE phone = ?", (phone,)).fetchone()

    def get_family(self, conn: DatabaseConnection, family_id: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM families WHERE id = ?", (family_id,)).fetchone()

    def get_family_by_code(self, conn: DatabaseConnection, family_code: str) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM families WHERE family_code = ?",
            (family_code,),
        ).fetchone()

    def update_family_code(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        family_code: str,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            "UPDATE families SET family_code = ?, family_code_updated_at = ? WHERE id = ?",
            (family_code, now, family_id),
        )
        return self.get_family(conn, family_id)

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

    def update_user_family(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        family_id: str,
    ) -> DatabaseRow:
        conn.execute("UPDATE users SET family_id = ? WHERE id = ?", (family_id, user_id))
        return self.get_user(conn, user_id)

    def update_user_phone(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        phone: str,
    ) -> DatabaseRow:
        conn.execute("UPDATE users SET phone = ? WHERE id = ?", (phone, user_id))
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
        relationship_key: str,
        now: int,
    ) -> DatabaseRow:
        existing = self.get_parent_identity(conn, family_id=family_id)
        if existing:
            conn.execute(
                """
                UPDATE parent_identities
                SET display_name = ?, relationship = ?, relationship_key = ?, confirmed_at = ?
                WHERE family_id = ?
                """,
                (display_name, relationship, relationship_key, now, family_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO parent_identities(
                  family_id, display_name, relationship, relationship_key, confirmed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (family_id, display_name, relationship, relationship_key, now),
            )
        return self.get_parent_identity(conn, family_id=family_id)

    def list_sessions(self, conn: DatabaseConnection, *, user_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND revoked_at IS NULL
                ORDER BY COALESCE(last_active_at, rotated_at, created_at) DESC
                LIMIT 30
                """,
                (user_id,),
            ).fetchall()
        )

    def get_session(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        session_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM sessions
            WHERE user_id = ? AND id = ?
            LIMIT 1
            """,
            (user_id, session_id),
        ).fetchone()

    def revoke_session(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        session_id: str,
        revoked_at: int,
    ) -> DatabaseRow | None:
        row = self.get_session(conn, user_id=user_id, session_id=session_id)
        if row is None:
            return None
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE user_id = ? AND id = ? AND revoked_at IS NULL
            """,
            (revoked_at, user_id, session_id),
        )
        return self.get_session(conn, user_id=user_id, session_id=session_id)

    def mark_user_deletion_requested(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        requested_at: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE users
            SET account_status = 'deletion_requested', deletion_requested_at = ?
            WHERE id = ?
            """,
            (requested_at, user_id),
        )
        return self.get_user(conn, user_id)

    def revoke_user_sessions(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        revoked_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE sessions
            SET revoked_at = ?
            WHERE user_id = ? AND revoked_at IS NULL
            """,
            (revoked_at, user_id),
        )

    def create_account_deletion_request(
        self,
        conn: DatabaseConnection,
        *,
        user_id: str,
        family_id: str,
        reason: str | None,
        requested_at: int,
    ) -> DatabaseRow:
        request_id = f"acct_del_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO account_deletion_requests(
              id, user_id, family_id, status, reason, requested_at
            )
            VALUES (?, ?, ?, 'requested', ?, ?)
            """,
            (request_id, user_id, family_id, reason, requested_at),
        )
        return conn.execute(
            "SELECT * FROM account_deletion_requests WHERE id = ?",
            (request_id,),
        ).fetchone()

    def ensure_owner_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
        name: str,
        relationship_key: str | None = None,
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
            conn.execute(
                """
                UPDATE family_members
                SET name = ?, relationship_key = COALESCE(?, relationship_key),
                    phone = ?, updated_at = ?
                WHERE id = ?
                """,
                (name or row["name"], relationship_key, phone, now, row["id"]),
            )
            return self.get_family_member(conn, family_id=family_id, member_id=row["id"])
        member_id = f"member_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO family_members(
              id, family_id, user_id, name, relationship_key, phone, role, status,
              notify_enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'admin', 'active', 1, ?, ?)
            """,
            (
                member_id,
                family_id,
                user_id,
                name or "家长",
                relationship_key,
                phone,
                now,
                now,
            ),
        )
        return self.get_family_member(conn, family_id=family_id, member_id=member_id)

    def find_sms_code(self, conn: DatabaseConnection, phone: str) -> DatabaseRow | None:
        return conn.execute("SELECT * FROM sms_codes WHERE phone = ?", (phone,)).fetchone()

    def increment_sms_attempts(self, conn: DatabaseConnection, phone: str) -> None:
        conn.execute(
            "UPDATE sms_codes SET attempt_count = attempt_count + 1 WHERE phone = ?",
            (phone,),
        )

    def delete_sms_code(self, conn: DatabaseConnection, phone: str) -> None:
        conn.execute("DELETE FROM sms_codes WHERE phone = ?", (phone,))

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

    def get_family_member_by_phone(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        phone: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM family_members
            WHERE family_id = ? AND phone = ?
            LIMIT 1
            """,
            (family_id, phone),
        ).fetchone()

    def upsert_joined_family_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
        name: str,
        relationship_key: str | None,
        phone: str,
        role: str,
        now: int,
    ) -> DatabaseRow:
        member = self.get_family_member_by_user(conn, family_id=family_id, user_id=user_id)
        if member is None and phone:
            member = self.get_family_member_by_phone(conn, family_id=family_id, phone=phone)
        if member:
            conn.execute(
                """
                UPDATE family_members
                SET user_id = ?, name = ?, relationship_key = ?, phone = ?, role = ?, status = 'active',
                    notify_enabled = 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    user_id,
                    name or member["name"],
                    relationship_key or member.get("relationship_key"),
                    phone,
                    role,
                    now,
                    member["id"],
                ),
            )
            return self.get_family_member(conn, family_id=family_id, member_id=member["id"])
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
                name or "家庭成员",
                relationship_key,
                phone,
                role,
                now,
                now,
            ),
        )
        return self.get_family_member(conn, family_id=family_id, member_id=member_id)

    def create_family_member(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str,
        relationship_key: str | None,
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
              id, family_id, user_id, name, relationship_key, phone, role, status,
              notify_enabled, created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                member_id,
                family_id,
                name,
                relationship_key,
                phone,
                role,
                status,
                int(notify_enabled),
                now,
                now,
            ),
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
                  AND NOT EXISTS (
                    SELECT 1
                    FROM family_members fm
                    WHERE fm.family_id = family_invitations.family_id
                      AND fm.phone = family_invitations.phone
                      AND fm.status = 'active'
                      AND fm.user_id IS NOT NULL
                  )
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

    def get_family_invitation_for_phone(
        self,
        conn: DatabaseConnection,
        *,
        invitation_id: str,
        phone: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT fi.*, f.name AS family_name, role_item.label AS role_label
            FROM family_invitations fi
            JOIN families f ON f.id = fi.family_id
            LEFT JOIN app_option_items role_item
              ON role_item.catalog_key = 'family_role'
             AND role_item.item_key = fi.role
             AND role_item.enabled = 1
            WHERE fi.id = ? AND fi.phone = ?
            LIMIT 1
            """,
            (invitation_id, phone),
        ).fetchone()

    def get_accepted_family_invitation_by_user(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        user_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM family_invitations
            WHERE family_id = ?
              AND accepted_by = ?
              AND status = 'accepted'
            ORDER BY COALESCE(accepted_at, updated_at, created_at) DESC
            LIMIT 1
            """,
            (family_id, user_id),
        ).fetchone()

    def create_family_invitation(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        name: str,
        relationship_key: str | None,
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
              id, family_id, name, relationship_key, phone, role, status, created_by,
              created_at, updated_at, expires_at, delivery_status, delivery_message
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?)
            """,
            (
                invitation_id,
                family_id,
                name,
                relationship_key,
                phone,
                role,
                created_by,
                now,
                now,
                expires_at,
                "not_configured",
                "邀请已保存。短信邀请暂未接入，请让对方使用该手机号登录后接受邀请。",
            ),
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

    def update_family_invitation_by_id(
        self,
        conn: DatabaseConnection,
        *,
        invitation_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
        if fields:
            assignments = [f"{column} = ?" for column in fields]
            values = list(fields.values()) + [now, invitation_id]
            conn.execute(
                f"""
                UPDATE family_invitations
                SET {', '.join(assignments)}, updated_at = ?
                WHERE id = ?
                """,
                values,
            )
        return conn.execute(
            "SELECT * FROM family_invitations WHERE id = ?",
            (invitation_id,),
        ).fetchone()

    def setup_completed(self, conn: DatabaseConnection, *, family_id: str) -> bool:
        row = conn.execute(
            "SELECT completed FROM setup_progress WHERE family_id = ?",
            (family_id,),
        ).fetchone()
        return bool(row and row["completed"])

    def cleanup_orphan_family(self, conn: DatabaseConnection, *, family_id: str) -> None:
        user_count = conn.execute(
            "SELECT COUNT(*) AS count FROM users WHERE family_id = ?",
            (family_id,),
        ).fetchone()
        if int(user_count["count"] or 0) > 0:
            return
        for table in (
            "setup_progress",
            "parent_identities",
            "family_members",
            "family_invitations",
            "emergency_contacts",
            "wifi_configs",
            "devices",
            "children",
            "app_settings",
            "feedback_items",
            "tasks",
            "task_events",
            "point_accounts",
            "point_ledger",
            "reward_items",
            "reward_redemptions",
            "camera_commands",
            "firmware_jobs",
            "account_deletion_requests",
        ):
            conn.execute(f"DELETE FROM {table} WHERE family_id = ?", (family_id,))
        conn.execute("DELETE FROM families WHERE id = ?", (family_id,))

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

    def update_current_device_wake_name(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        wake_name: str,
        now: int,
    ) -> None:
        row = conn.execute(
            """
            SELECT id
            FROM devices
            WHERE family_id = ? AND status <> 'unbound'
            ORDER BY created_at
            LIMIT 1
            """,
            (family_id,),
        ).fetchone()
        if row is None:
            return
        conn.execute(
            "UPDATE devices SET wake_name = ?, updated_at = ? WHERE family_id = ? AND id = ?",
            (wake_name, now, family_id, row["id"]),
        )

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
        relationship_key: str | None,
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
              id, family_id, name, phone, relationship, relationship_key, priority,
              default_notify, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                family_id,
                name,
                phone,
                relationship,
                relationship_key,
                priority,
                int(default_notify),
                now,
                now,
            ),
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
