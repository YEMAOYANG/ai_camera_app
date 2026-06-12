from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class CameraCommandRepository:
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
                CREATE TABLE IF NOT EXISTS camera_commands (
                  id VARCHAR(255) PRIMARY KEY,
                  family_id VARCHAR(255) NOT NULL,
                  device_id VARCHAR(255),
                  task_id VARCHAR(255),
                  command_type VARCHAR(255) NOT NULL,
                  status VARCHAR(255) NOT NULL,
                  message TEXT,
                  request_payload TEXT,
                  response_payload TEXT,
                  created_at BIGINT NOT NULL,
                  updated_at BIGINT NOT NULL,
                  completed_at BIGINT
                );
                """
            )

    def create_command(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        command_type: str,
        status: str,
        message: str | None,
        request_payload: str | None,
        device_id: str | None,
        task_id: str | None,
        now: int,
    ) -> DatabaseRow:
        command_id = f"cmd_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO camera_commands(
              id, family_id, device_id, task_id, command_type, status, message,
              request_payload, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                command_id,
                family_id,
                device_id,
                task_id,
                command_type,
                status,
                message,
                request_payload,
                now,
                now,
            ),
        )
        return self.get_command(conn, family_id=family_id, command_id=command_id)

    def update_command(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        command_id: str,
        status: str,
        message: str | None,
        response_payload: str | None,
        now: int,
        completed: bool = False,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE camera_commands
            SET status = ?, message = ?, response_payload = ?, updated_at = ?,
              completed_at = CASE WHEN ? THEN ? ELSE completed_at END
            WHERE family_id = ? AND id = ?
            """,
            (
                status,
                message,
                response_payload,
                now,
                1 if completed else 0,
                now,
                family_id,
                command_id,
            ),
        )
        return self.get_command(conn, family_id=family_id, command_id=command_id)

    def get_command(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        command_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM camera_commands WHERE family_id = ? AND id = ?",
            (family_id, command_id),
        ).fetchone()

    def list_recent_commands(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        limit: int = 30,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM camera_commands
                WHERE family_id = ?
                ORDER BY COALESCE(completed_at, updated_at, created_at) DESC, id DESC
                LIMIT ?
                """,
                (family_id, limit),
            ).fetchall()
        )

    def list_recent_task_events(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        limit: int = 30,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM task_events
                WHERE family_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (family_id, limit),
            ).fetchall()
        )
