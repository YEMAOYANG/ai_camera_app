from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import SQLiteDatabase
from models.tasks import (
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_CONFIRMED,
    TASK_PENDING,
    TASK_REJECTED,
)


class TaskRepository:
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
                CREATE TABLE IF NOT EXISTS tasks (
                  id TEXT PRIMARY KEY,
                  family_id TEXT NOT NULL,
                  child_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  description TEXT,
                  type TEXT NOT NULL,
                  status TEXT NOT NULL,
                  scheduled_date TEXT NOT NULL,
                  scheduled_start TEXT,
                  scheduled_end TEXT,
                  reward_points INTEGER NOT NULL DEFAULT 0,
                  requires_parent_confirmation INTEGER NOT NULL DEFAULT 1,
                  evidence_summary TEXT,
                  rejection_reason TEXT,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL,
                  completed_at INTEGER,
                  confirmed_at INTEGER,
                  rejected_at INTEGER,
                  points_granted_at INTEGER
                );
                """
            )

    def child_exists(self, conn: sqlite3.Connection, *, family_id: str, child_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def create_task(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        child_id: str,
        title: str,
        description: str | None,
        task_type: str,
        scheduled_date: str,
        scheduled_start: str | None,
        scheduled_end: str | None,
        reward_points: int,
        requires_parent_confirmation: bool,
        now: int,
    ) -> sqlite3.Row:
        task_id = f"task_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO tasks(
              id, family_id, child_id, title, description, type, status,
              scheduled_date, scheduled_start, scheduled_end, reward_points,
              requires_parent_confirmation, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                family_id,
                child_id,
                title,
                description,
                task_type,
                TASK_PENDING,
                scheduled_date,
                scheduled_start,
                scheduled_end,
                reward_points,
                int(requires_parent_confirmation),
                now,
                now,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def list_tasks(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        child_id: str | None = None,
        scheduled_date: str | None = None,
        status: str | None = None,
    ) -> list[sqlite3.Row]:
        clauses = ["family_id = ?"]
        values: list[str] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        if scheduled_date:
            clauses.append("scheduled_date = ?")
            values.append(scheduled_date)
        if status:
            clauses.append("status = ?")
            values.append(status)
        return list(
            conn.execute(
                f"""
                SELECT * FROM tasks
                WHERE {' AND '.join(clauses)}
                ORDER BY scheduled_date, scheduled_start IS NULL, scheduled_start, created_at
                """,
                values,
            ).fetchall()
        )

    def get_task(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        task_id: str,
    ) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM tasks WHERE family_id = ? AND id = ?",
            (family_id, task_id),
        ).fetchone()

    def update_task(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        task_id: str,
        fields: dict,
        now: int,
    ) -> sqlite3.Row | None:
        if not fields:
            return self.get_task(conn, family_id=family_id, task_id=task_id)
        assignments = [f"{column} = ?" for column in fields]
        values = list(fields.values()) + [now, family_id, task_id]
        conn.execute(
            f"""
            UPDATE tasks
            SET {', '.join(assignments)}, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            values,
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_completed(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        task_id: str,
        evidence_summary: str | None,
        now: int,
    ) -> sqlite3.Row | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, evidence_summary = COALESCE(?, evidence_summary),
              completed_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (TASK_AWAITING_PARENT_CONFIRMATION, evidence_summary, now, now, family_id, task_id),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_confirmed(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> sqlite3.Row | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, confirmed_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (TASK_CONFIRMED, now, now, family_id, task_id),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_points_granted(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> sqlite3.Row | None:
        conn.execute(
            """
            UPDATE tasks
            SET points_granted_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (now, now, family_id, task_id),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_rejected(
        self,
        conn: sqlite3.Connection,
        *,
        family_id: str,
        task_id: str,
        reason: str | None,
        now: int,
    ) -> sqlite3.Row | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, rejection_reason = ?, rejected_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (TASK_REJECTED, reason, now, now, family_id, task_id),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)
