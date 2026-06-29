from __future__ import annotations

from core.database import DatabaseConnection
from core.security import now_ms


class ConversationRepository:
    def create_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        family_id: str,
        device_id: str,
        session_type: str,
        started_at: int,
        date_key: str,
    ) -> None:
        now = now_ms()
        conn.execute(
            """
            INSERT INTO conversation_sessions(
              id, family_id, device_id, session_type, started_at, ended_at,
              duration_seconds, date_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, NULL, 0, ?, ?, ?)
            """,
            (session_id, family_id, device_id, session_type, started_at, date_key, now, now),
        )

    def end_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        ended_at: int,
        duration_seconds: int,
    ) -> None:
        conn.execute(
            """
            UPDATE conversation_sessions
            SET ended_at = ?, duration_seconds = ?, updated_at = ?
            WHERE id = ?
            """,
            (ended_at, max(0, duration_seconds), now_ms(), session_id),
        )

    def active_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        session_type: str,
    ):
        return conn.execute(
            """
            SELECT *
            FROM conversation_sessions
            WHERE family_id = ? AND session_type = ? AND ended_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (family_id, session_type),
        ).fetchone()

    def daily_free_chat_seconds(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        date_key: str,
    ) -> int:
        row = conn.execute(
            """
            SELECT free_chat_seconds
            FROM conversation_daily_usage
            WHERE family_id = ? AND date_key = ?
            """,
            (family_id, date_key),
        ).fetchone()
        if row is None:
            return 0
        return int(row.get("free_chat_seconds") or 0)

    def add_daily_free_chat_seconds(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        date_key: str,
        seconds: int,
    ) -> int:
        now = now_ms()
        current = self.daily_free_chat_seconds(conn, family_id=family_id, date_key=date_key)
        total = current + max(0, seconds)
        conn.execute(
            """
            INSERT INTO conversation_daily_usage(family_id, date_key, free_chat_seconds, updated_at)
            VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE free_chat_seconds = VALUES(free_chat_seconds), updated_at = VALUES(updated_at)
            """,
            (family_id, date_key, total, now),
        )
        return total
