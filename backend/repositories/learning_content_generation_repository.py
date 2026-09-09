from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from core.database import Database, DatabaseConnection, DatabaseRow


class LearningContentGenerationRepository:
    """Persistence boundary for unverified learning-content enrichments."""

    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def get_course(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_courses
            WHERE id = ? AND version = ?
            LIMIT 1
            """,
            (course_id, course_version),
        ).fetchone()

    def create_or_get_job(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        course_id: str,
        course_version: str,
        generator: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        job_id = f"learning_content_job_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_content_generation_jobs(
              id, request_id, course_id, course_version, generator, status,
              started_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'generating', ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                job_id,
                request_id,
                course_id,
                course_version,
                generator,
                now,
                now,
                now,
            ),
        )
        row = self.get_job_by_request(conn, request_id=request_id)
        return row, bool(row and row["id"] == job_id)

    def get_job_by_request(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_content_generation_jobs
            WHERE request_id = ?
            LIMIT 1
            """,
            (request_id,),
        ).fetchone()

    def restart_stale_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        request_id: str,
        stale_before: int,
        now: int,
    ) -> DatabaseRow | None:
        """Atomically claim a generation job abandoned by a dead worker."""

        cursor = conn.execute(
            """
            UPDATE learning_content_generation_jobs
            SET started_at = ?, completed_at = NULL, error_code = NULL,
              error_message = NULL, updated_at = ?
            WHERE id = ? AND request_id = ? AND status = 'generating'
              AND updated_at <= ?
            """,
            (now, now, job_id, request_id, stale_before),
        )
        if cursor.rowcount != 1:
            return None
        return self.get_job_by_request(conn, request_id=request_id)

    def get_draft_for_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_content_enrichment_drafts
            WHERE job_id = ?
            LIMIT 1
            """,
            (job_id,),
        ).fetchone()

    def complete_with_draft(
        self,
        conn: DatabaseConnection,
        *,
        job: Mapping[str, Any],
        enrichment: Mapping[str, Any],
        payload_json: str,
        content_hash: str,
        now: int,
    ) -> tuple[DatabaseRow, DatabaseRow]:
        draft_id = f"learning_content_draft_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_content_enrichment_drafts(
              id, job_id, request_id, course_id, course_version,
              schema_version, generator, provider, model, status,
              content_hash, payload_json, elapsed_ms, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'validated_draft', ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                draft_id,
                job["id"],
                job["request_id"],
                job["course_id"],
                job["course_version"],
                str(enrichment.get("schemaVersion") or ""),
                str(enrichment.get("generator") or "openmaic"),
                str(enrichment.get("provider") or ""),
                str(enrichment.get("model") or ""),
                content_hash,
                payload_json,
                max(0, int(enrichment.get("elapsedMs") or 0)),
                now,
                now,
            ),
        )
        draft = self.get_draft_for_job(conn, job_id=str(job["id"]))
        conn.execute(
            """
            UPDATE learning_content_generation_jobs
            SET status = 'validated_draft', draft_id = ?, error_code = NULL,
              error_message = NULL, completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (draft["id"], now, now, job["id"]),
        )
        persisted_job = self.get_job_by_request(
            conn, request_id=str(job["request_id"])
        )
        return persisted_job, draft

    def complete_with_error(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        request_id: str,
        error_code: str,
        error_message: str,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_content_generation_jobs
            SET status = 'failed', error_code = ?, error_message = ?,
              completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (error_code, error_message, now, now, job_id),
        )
        return self.get_job_by_request(conn, request_id=request_id)

    @staticmethod
    def encode_json(payload: Mapping[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def decode_json(value: Any) -> dict[str, Any] | None:
        try:
            payload = json.loads(str(value or ""))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        return payload if isinstance(payload, dict) else None
