from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from core.database import Database, DatabaseRow
from core.errors import ApiError
from core.security import now_ms
from repositories.learning_content_generation_repository import (
    LearningContentGenerationRepository,
)
from services.learning_content_generation_service import (
    LearningContentGenerationError,
    LearningContentGenerationService,
)


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_FAILURES: dict[str, tuple[str, str, int]] = {
    "openmaic_unavailable": (
        "openmaic_unavailable",
        "OpenMAIC content generation is currently unavailable.",
        503,
    ),
    "openmaic_timeout": (
        "openmaic_timeout",
        "OpenMAIC content generation timed out.",
        504,
    ),
    "invalid_openmaic_request": (
        "invalid_openmaic_request",
        "The fixed learning boundary could not be sent to OpenMAIC.",
        422,
    ),
    "invalid_learning_course": (
        "invalid_learning_course",
        "The published deterministic course is not generation-ready.",
        422,
    ),
    "learning_course_not_published": (
        "learning_course_not_published",
        "Only a published deterministic course can be enriched.",
        409,
    ),
    "unsupported_learning_course": (
        "unsupported_learning_course",
        "This course is outside the enabled OpenMAIC enrichment policy.",
        422,
    ),
    "invalid_openmaic_draft": (
        "invalid_openmaic_draft",
        "The OpenMAIC draft failed deterministic validation.",
        422,
    ),
    "openmaic_boundary_mismatch": (
        "openmaic_boundary_mismatch",
        "The OpenMAIC draft changed the fixed learning boundary.",
        422,
    ),
    "openmaic_limit_exceeded": (
        "openmaic_limit_exceeded",
        "The OpenMAIC draft exceeded the configured content limits.",
        422,
    ),
    "openmaic_answer_authority_leak": (
        "openmaic_answer_authority_leak",
        "The OpenMAIC draft attempted to provide answer authority.",
        422,
    ),
    "openmaic_unsafe_scene": (
        "openmaic_unsafe_scene",
        "The OpenMAIC draft contains a disabled scene or media action.",
        422,
    ),
    "openmaic_generation_failed": (
        "openmaic_generation_failed",
        "OpenMAIC content generation failed.",
        502,
    ),
}


@dataclass(frozen=True)
class LearningContentPipelineResult:
    payload: dict[str, Any]
    status_code: int


class LearningContentPipelineService:
    """Runs and persists internal-only OpenMAIC enrichment jobs.

    The saved artifact remains a ``validated_draft``. It never updates
    ``learning_courses`` and therefore cannot replace deterministic questions,
    answers, or publication state.
    """

    def __init__(
        self,
        database_url: str | Path,
        *,
        generation_service: LearningContentGenerationService,
        stale_after_ms: int = 180_000,
    ):
        self.repository = LearningContentGenerationRepository(Database(database_url))
        self.generation_service = generation_service
        self.stale_after_ms = max(30_000, int(stale_after_ms))

    def status(self) -> dict[str, Any]:
        payload = dict(self.generation_service.status())
        payload["jobPolicy"] = {"staleAfterMs": self.stale_after_ms}
        return payload

    def generate(self, data: Mapping[str, Any]) -> LearningContentPipelineResult:
        course_id = self._required_text(data, "courseId", max_length=255)
        course_version = self._required_text(data, "courseVersion", max_length=64)
        request_id = self._request_id(data.get("requestId"))
        started_at = now_ms()

        with self.repository.transaction() as conn:
            existing_job = self.repository.get_job_by_request(
                conn, request_id=request_id
            )
            if existing_job is not None:
                self._assert_request_target(
                    existing_job,
                    course_id=course_id,
                    course_version=course_version,
                )
                if (
                    str(existing_job.get("status") or "") != "generating"
                    or int(existing_job.get("updated_at") or 0)
                    > started_at - self.stale_after_ms
                ):
                    return self._persisted_result(
                        conn, job=existing_job, replayed=True
                    )
                restarted_job = self.repository.restart_stale_job(
                    conn,
                    job_id=str(existing_job["id"]),
                    request_id=request_id,
                    stale_before=started_at - self.stale_after_ms,
                    now=started_at,
                )
                if restarted_job is None:
                    latest_job = self.repository.get_job_by_request(
                        conn, request_id=request_id
                    )
                    return self._persisted_result(
                        conn, job=latest_job or existing_job, replayed=True
                    )
                existing_job = restarted_job
            course = self.repository.get_course(
                conn,
                course_id=course_id,
                course_version=course_version,
            )
            if course is None:
                raise ApiError(
                    "learning_course_not_found",
                    "The requested learning course version does not exist.",
                    404,
                )
            if str(course.get("status") or "") != "published":
                raise ApiError(
                    "learning_course_not_published",
                    "Only a published deterministic course can be enriched.",
                    409,
                )
            if existing_job is not None:
                job = existing_job
            else:
                job, created = self.repository.create_or_get_job(
                    conn,
                    request_id=request_id,
                    course_id=course_id,
                    course_version=course_version,
                    generator="openmaic",
                    now=started_at,
                )
                if not created:
                    self._assert_request_target(
                        job,
                        course_id=course_id,
                        course_version=course_version,
                    )
                    return self._persisted_result(conn, job=job, replayed=True)

        try:
            enrichment = self.generation_service.generate(course, request_id)
            self._validate_enrichment_identity(
                enrichment,
                request_id=request_id,
                course_id=course_id,
                course_version=course_version,
            )
        except LearningContentGenerationError as exc:
            return self._persist_failure(job=job, code=exc.code)
        except Exception:
            return self._persist_failure(job=job, code="openmaic_generation_failed")

        payload_json = self.repository.encode_json(enrichment)
        content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        completed_at = now_ms()
        with self.repository.transaction() as conn:
            persisted_job, draft = self.repository.complete_with_draft(
                conn,
                job=job,
                enrichment=enrichment,
                payload_json=payload_json,
                content_hash=content_hash,
                now=completed_at,
            )
        return LearningContentPipelineResult(
            payload={
                "ok": True,
                "replayed": False,
                "job": self._job_payload(persisted_job),
                "enrichment": self._draft_payload(draft, enrichment),
            },
            status_code=200,
        )

    def _persist_failure(
        self,
        *,
        job: Mapping[str, Any],
        code: str,
    ) -> LearningContentPipelineResult:
        safe_code, safe_message, status_code = self._safe_failure(code)
        with self.repository.transaction() as conn:
            persisted_job = self.repository.complete_with_error(
                conn,
                job_id=str(job["id"]),
                request_id=str(job["request_id"]),
                error_code=safe_code,
                error_message=safe_message,
                now=now_ms(),
            )
        return LearningContentPipelineResult(
            payload={
                "ok": False,
                "replayed": False,
                "job": self._job_payload(persisted_job),
                "enrichment": None,
                "error": {"code": safe_code, "message": safe_message},
            },
            status_code=status_code,
        )

    def _persisted_result(
        self,
        conn,
        *,
        job: Mapping[str, Any],
        replayed: bool,
    ) -> LearningContentPipelineResult:
        status = str(job.get("status") or "")
        if status == "failed":
            safe_code, safe_message, status_code = self._safe_failure(
                str(job.get("error_code") or "openmaic_generation_failed")
            )
            return LearningContentPipelineResult(
                payload={
                    "ok": False,
                    "replayed": replayed,
                    "job": self._job_payload(job),
                    "enrichment": None,
                    "error": {"code": safe_code, "message": safe_message},
                },
                status_code=status_code,
            )
        if status == "validated_draft":
            draft = self.repository.get_draft_for_job(conn, job_id=str(job["id"]))
            enrichment = self.repository.decode_json(
                draft.get("payload_json") if draft else None
            )
            if draft is None or enrichment is None:
                return LearningContentPipelineResult(
                    payload={
                        "ok": False,
                        "replayed": replayed,
                        "job": self._job_payload(job),
                        "enrichment": None,
                        "error": {
                            "code": "learning_content_draft_unavailable",
                            "message": "The persisted enrichment draft is unavailable.",
                        },
                    },
                    status_code=500,
                )
            return LearningContentPipelineResult(
                payload={
                    "ok": True,
                    "replayed": replayed,
                    "job": self._job_payload(job),
                    "enrichment": self._draft_payload(draft, enrichment),
                },
                status_code=200,
            )
        return LearningContentPipelineResult(
            payload={
                "ok": True,
                "replayed": replayed,
                "job": self._job_payload(job),
                "enrichment": None,
            },
            status_code=202,
        )

    @staticmethod
    def _assert_request_target(
        job: Mapping[str, Any],
        *,
        course_id: str,
        course_version: str,
    ) -> None:
        if (
            str(job.get("course_id") or "") != course_id
            or str(job.get("course_version") or "") != course_version
        ):
            raise ApiError(
                "learning_content_request_conflict",
                "requestId is already bound to another course version.",
                409,
            )

    @staticmethod
    def _validate_enrichment_identity(
        enrichment: Any,
        *,
        request_id: str,
        course_id: str,
        course_version: str,
    ) -> None:
        if not isinstance(enrichment, Mapping):
            raise LearningContentGenerationError(
                "invalid_openmaic_draft", "OpenMAIC enrichment must be an object"
            )
        source = enrichment.get("sourceCourse")
        authority = enrichment.get("authority")
        if (
            enrichment.get("status") != "validated_draft"
            or enrichment.get("requestId") != request_id
            or enrichment.get("generator") != "openmaic"
            or not isinstance(source, Mapping)
            or source.get("id") != course_id
            or source.get("version") != course_version
            or not isinstance(authority, Mapping)
            or authority.get("authoritativeAnswersProvided") is not False
            or not isinstance(enrichment.get("draft"), Mapping)
        ):
            raise LearningContentGenerationError(
                "invalid_openmaic_draft",
                "OpenMAIC enrichment identity or authority is invalid",
            )

    @staticmethod
    def _job_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        error = None
        if row.get("error_code"):
            error = {
                "code": row["error_code"],
                "message": row.get("error_message") or "",
            }
        return {
            "id": row["id"],
            "requestId": row["request_id"],
            "courseId": row["course_id"],
            "courseVersion": row["course_version"],
            "generator": row["generator"],
            "status": row["status"],
            "draftId": row.get("draft_id"),
            "error": error,
            "startedAt": row["started_at"],
            "completedAt": row.get("completed_at"),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _draft_payload(
        row: Mapping[str, Any], enrichment: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "id": row["id"],
            "jobId": row["job_id"],
            "requestId": row["request_id"],
            "courseId": row["course_id"],
            "courseVersion": row["course_version"],
            "schemaVersion": row["schema_version"],
            "generator": row["generator"],
            "provider": row["provider"],
            "model": row["model"],
            "status": row["status"],
            "contentHash": row["content_hash"],
            "elapsedMs": int(row.get("elapsed_ms") or 0),
            "payload": dict(enrichment),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _safe_failure(code: str) -> tuple[str, str, int]:
        return _SAFE_FAILURES.get(
            str(code or ""),
            _SAFE_FAILURES["openmaic_generation_failed"],
        )

    @staticmethod
    def _required_text(
        data: Mapping[str, Any], key: str, *, max_length: int
    ) -> str:
        value = str(data.get(key) or "").strip()
        if not value:
            raise ApiError(f"missing_{key}", f"{key} is required.", 400)
        if len(value) > max_length:
            raise ApiError(f"invalid_{key}", f"{key} is too long.", 400)
        return value

    @staticmethod
    def _request_id(value: Any) -> str:
        if value is None or not str(value).strip():
            return f"learning_content_{uuid.uuid4().hex}"
        request_id = str(value).strip()
        if not _REQUEST_ID_PATTERN.fullmatch(request_id):
            raise ApiError(
                "invalid_requestId",
                "requestId must contain only letters, numbers, '.', '_', ':', or '-'.",
                400,
            )
        return request_id
