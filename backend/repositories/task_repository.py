from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow
from models.tasks import (
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_COMPLETED,
    TASK_CONFIRMED,
    TASK_PENDING,
    TASK_REJECTED,
)


class TaskRepository:
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
                CREATE TABLE IF NOT EXISTS tasks (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  child_id VARCHAR(255) NOT NULL,
                  title VARCHAR(255) NOT NULL,
                  description TEXT,
                  type VARCHAR(255) NOT NULL,
                  status VARCHAR(255) NOT NULL,
                  scheduled_date VARCHAR(255) NOT NULL,
                  scheduled_start VARCHAR(255),
                  scheduled_end VARCHAR(255),
                  schedule_type VARCHAR(255) NOT NULL DEFAULT 'one_time',
                  start_at VARCHAR(255),
                  due_at VARCHAR(255),
                  repeat_rule TEXT,
                  priority INTEGER NOT NULL DEFAULT 3,
                  reward_points INTEGER NOT NULL DEFAULT 0,
                  requires_parent_confirmation INTEGER NOT NULL DEFAULT 1,
                  completion_source VARCHAR(255),
                  evidence TEXT,
                  evidence_summary TEXT,
                  ai_observation_summary TEXT,
                  rejection_reason TEXT,
                  created_by VARCHAR(255),
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL,
                  completed_at BIGINT,
                  confirmed_at BIGINT,
                  rejected_at BIGINT,
                  points_granted_at BIGINT
                );
                """
            )

    def child_exists(self, conn: DatabaseConnection, *, family_id: str, child_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def create_task(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        title: str,
        description: str | None,
        task_type: str,
        scheduled_date: str,
        scheduled_start: str | None,
        scheduled_end: str | None,
        schedule_type: str,
        start_at: str | None,
        due_at: str | None,
        repeat_rule: str | None,
        priority: int,
        reward_points: int,
        requires_parent_confirmation: bool,
        ai_observation_summary: str | None,
        created_by: str | None,
        now: int,
    ) -> DatabaseRow:
        task_id = f"task_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO tasks(
              id, family_id, child_id, title, description, type, status,
              scheduled_date, scheduled_start, scheduled_end, schedule_type,
              start_at, due_at, repeat_rule, priority, reward_points,
              requires_parent_confirmation, ai_observation_summary, created_by,
              created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                schedule_type,
                start_at,
                due_at,
                repeat_rule,
                priority,
                reward_points,
                int(requires_parent_confirmation),
                ai_observation_summary,
                created_by,
                now,
                now,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def list_tasks(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        scheduled_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
    ) -> list[DatabaseRow]:
        clauses = ["family_id = ?"]
        values: list[str] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        if scheduled_date:
            clauses.append("scheduled_date = ?")
            values.append(scheduled_date)
        if start_date:
            clauses.append("scheduled_date >= ?")
            values.append(start_date)
        if end_date:
            clauses.append("scheduled_date <= ?")
            values.append(end_date)
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM tasks WHERE family_id = ? AND id = ?",
            (family_id, task_id),
        ).fetchone()

    def update_task(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        fields: dict,
        now: int,
    ) -> DatabaseRow | None:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        evidence_summary: str | None,
        completion_source: str | None,
        evidence: str | None,
        ai_observation_summary: str | None,
        requires_parent_confirmation: bool,
        now: int,
    ) -> DatabaseRow | None:
        next_status = (
            TASK_AWAITING_PARENT_CONFIRMATION
            if requires_parent_confirmation
            else TASK_COMPLETED
        )
        conn.execute(
            """
            UPDATE tasks
            SET status = ?,
              evidence_summary = COALESCE(?, evidence_summary),
              completion_source = COALESCE(?, completion_source),
              evidence = COALESCE(?, evidence),
              ai_observation_summary = COALESCE(?, ai_observation_summary),
              completed_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (
                next_status,
                evidence_summary,
                completion_source,
                evidence,
                ai_observation_summary,
                now,
                now,
                family_id,
                task_id,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_confirmed(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> DatabaseRow | None:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> DatabaseRow | None:
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
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        reason: str | None,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, rejection_reason = ?, rejected_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (TASK_REJECTED, reason, now, now, family_id, task_id),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)
