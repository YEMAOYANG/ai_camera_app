from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow
from models.tasks import (
    TASK_ACTIVE_SCHEDULED_STATUSES,
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_COMPLETED,
    TASK_CONFIRMED,
    TASK_DELAYED,
    TASK_IN_PROGRESS,
    TASK_MISSED,
    TASK_PENDING,
    TASK_REMINDER_SENT,
    TASK_REJECTED,
    TASK_SCHEDULED,
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
                  points_granted_at BIGINT,
                  reminder_minutes_before INTEGER NOT NULL DEFAULT 5,
                  reminder_status VARCHAR(255) NOT NULL DEFAULT 'pending',
                  started_at BIGINT,
                  ended_at BIGINT,
                  missed_at BIGINT,
                  delayed_at BIGINT,
                  last_reminder_at BIGINT,
                  next_reminder_at BIGINT,
                  delay_reminder_count INTEGER NOT NULL DEFAULT 0,
                  camera_observation_status VARCHAR(255) NOT NULL DEFAULT 'unknown',
                  device_id VARCHAR(255),
                  timezone VARCHAR(255) NOT NULL DEFAULT 'Asia/Shanghai'
                );
                CREATE TABLE IF NOT EXISTS task_events (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  task_id VARCHAR(255) NOT NULL,
                  event_type VARCHAR(255) NOT NULL,
                  message TEXT,
                  payload TEXT,
                  created_at BIGINT NOT NULL
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
        reminder_minutes_before: int = 5,
        device_id: str | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> DatabaseRow:
        task_id = f"task_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO tasks(
              id, family_id, child_id, title, description, type, status,
              scheduled_date, scheduled_start, scheduled_end, schedule_type,
              start_at, due_at, repeat_rule, priority, reward_points,
              requires_parent_confirmation, ai_observation_summary, created_by,
              reminder_minutes_before, reminder_status, device_id, timezone,
              created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                family_id,
                child_id,
                title,
                description,
                task_type,
                TASK_SCHEDULED,
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
                reminder_minutes_before,
                "pending",
                device_id,
                timezone,
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
                SELECT t.*,
                  EXISTS(
                    SELECT 1 FROM task_events e
                    WHERE e.family_id = t.family_id
                      AND e.task_id = t.id
                      AND e.event_type = 'missed_acknowledged'
                    LIMIT 1
                  ) AS missed_acknowledged
                FROM tasks t
                WHERE {' AND '.join(clauses)}
                ORDER BY scheduled_date, scheduled_start IS NULL, scheduled_start, created_at
                """,
                values,
            ).fetchall()
        )

    def list_scheduler_tasks(
        self,
        conn: DatabaseConnection,
        *,
        end_date: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM tasks
                WHERE scheduled_date <= ?
                  AND status IN (?, ?, ?, ?, ?)
                ORDER BY scheduled_start IS NULL, scheduled_start, created_at
                """,
                (
                    end_date,
                    TASK_SCHEDULED,
                    TASK_PENDING,
                    TASK_REMINDER_SENT,
                    TASK_IN_PROGRESS,
                    TASK_DELAYED,
                ),
            ).fetchall()
        )

    def list_in_progress_tasks(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        scheduled_date: str | None = None,
        device_id: str | None = None,
        include_unassigned: bool = False,
    ) -> list[DatabaseRow]:
        clauses = ["family_id = ?", "status IN (?, ?)"]
        values: list[str] = [family_id, TASK_IN_PROGRESS, TASK_DELAYED]
        if scheduled_date:
            clauses.append("scheduled_date = ?")
            values.append(scheduled_date)
        if device_id:
            if include_unassigned:
                clauses.append("(device_id = ? OR device_id IS NULL OR device_id = '')")
                values.append(device_id)
            else:
                clauses.append("device_id = ?")
                values.append(device_id)
        return list(
            conn.execute(
                f"""
                SELECT * FROM tasks
                WHERE {' AND '.join(clauses)}
                ORDER BY scheduled_start IS NULL, scheduled_start, updated_at DESC
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
            """
            SELECT t.*,
              EXISTS(
                SELECT 1 FROM task_events e
                WHERE e.family_id = t.family_id
                  AND e.task_id = t.id
                  AND e.event_type = 'missed_acknowledged'
                LIMIT 1
              ) AS missed_acknowledged
            FROM tasks t
            WHERE t.family_id = ? AND t.id = ?
            """,
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

    def mark_in_progress(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        observation_status: str = "unknown",
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?,
              started_at = COALESCE(started_at, ?),
              camera_observation_status = ?,
              next_reminder_at = NULL,
              updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (TASK_IN_PROGRESS, now, observation_status, now, family_id, task_id),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_reminder_result(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        sent: bool,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = CASE
                WHEN ? = 1 AND status IN (?, ?) THEN ?
                ELSE status
              END,
              reminder_status = ?,
              last_reminder_at = ?,
              updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (
                1 if sent else 0,
                TASK_SCHEDULED,
                TASK_PENDING,
                TASK_REMINDER_SENT,
                "sent" if sent else "failed",
                now,
                now,
                family_id,
                task_id,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_delayed(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        observation_status: str,
        next_reminder_at: int | None,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?,
              delayed_at = COALESCE(delayed_at, ?),
              camera_observation_status = ?,
              next_reminder_at = ?,
              updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (
                TASK_DELAYED,
                now,
                observation_status,
                next_reminder_at,
                now,
                family_id,
                task_id,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_delay_reminder_result(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        sent: bool,
        next_reminder_at: int | None,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE tasks
            SET delay_reminder_count = delay_reminder_count + 1,
              last_reminder_at = ?,
              next_reminder_at = ?,
              reminder_status = ?,
              updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (
                now,
                next_reminder_at,
                "sent" if sent else "failed",
                now,
                family_id,
                task_id,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def mark_missed(
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
            SET status = ?,
              missed_at = COALESCE(missed_at, ?),
              evidence_summary = COALESCE(?, evidence_summary),
              completion_source = COALESCE(completion_source, 'scheduler'),
              next_reminder_at = NULL,
              updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (TASK_MISSED, now, reason, now, family_id, task_id),
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
              completed_at = ?,
              ended_at = COALESCE(ended_at, ?),
              next_reminder_at = NULL,
              updated_at = ?
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

    def mark_points_granted_once(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET points_granted_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ? AND points_granted_at IS NULL
            """,
            (now, now, family_id, task_id),
        )
        return cursor.rowcount == 1

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

    def add_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        event_type: str,
        message: str | None,
        payload: dict | None,
        now: int,
    ) -> DatabaseRow:
        event_id = f"evt_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO task_events(
              id, family_id, task_id, event_type, message, payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                family_id,
                task_id,
                event_type,
                message,
                json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")),
                now,
            ),
        )
        return conn.execute(
            "SELECT * FROM task_events WHERE id = ?",
            (event_id,),
        ).fetchone()

    def list_events(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        limit: int = 50,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM task_events
                WHERE family_id = ? AND task_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (family_id, task_id, limit),
            ).fetchall()
        )

    def has_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str | None = None,
        task_id: str,
        event_type: str,
    ) -> bool:
        if family_id:
            row = conn.execute(
                """
                SELECT id FROM task_events
                WHERE family_id = ? AND task_id = ? AND event_type = ?
                LIMIT 1
                """,
                (family_id, task_id, event_type),
            ).fetchone()
            return row is not None
        row = conn.execute(
            "SELECT id FROM task_events WHERE task_id = ? AND event_type = ? LIMIT 1",
            (task_id, event_type),
        ).fetchone()
        return row is not None
