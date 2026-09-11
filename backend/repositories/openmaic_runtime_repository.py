from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from core.database import Database, DatabaseConnection, DatabaseRow
from integrations.openmaic_formal_media import (
    compatible_preparation_target, policy_from_target, generation_options,
)
from integrations.openmaic_formal_pedagogy import (
    adaptive_policy, grade_boundary_fields, validate_generation_grade_boundary,
)
from repositories.formal_student_runtime_gate import (
    current_formal_runtime_sql,
    current_formal_validation_authority_sql,
)


class OpenMaicRuntimeRepository:
    """Persistence boundary for the isolated full OpenMAIC runtime."""

    CANDIDATE_BINDING_CONTRACT_VERSION = (
        "mira.learning.candidate-runtime-binding.v1"
    )
    FORMAL_PROVIDER_CIRCUIT_KEY = (
        "formal-generation:deepseek:deepseek-v4-pro"
    )
    FORMAL_PROVIDER_ID = "deepseek"
    FORMAL_PROVIDER_MODEL_ID = "deepseek-v4-pro"

    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    @staticmethod
    def encode_json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def decode_json(value: object, fallback: Any) -> Any:
        if not isinstance(value, str) or not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    @classmethod
    def _candidate_item_is_in_canary_manifest(
        cls,
        *,
        build: Mapping[str, Any],
        item: Mapping[str, Any],
    ) -> bool:
        manifest = cls.decode_json(build.get("canary_manifest_json"), {})
        targets = manifest.get("targets") if isinstance(manifest, Mapping) else None
        if not isinstance(targets, list):
            return False
        identity = (
            str(item.get("subject") or ""),
            str(item.get("skill_id") or ""),
            int(item.get("variant_ordinal") or 0),
        )
        return any(
            isinstance(target, Mapping)
            and identity
            == (
                str(target.get("subject") or ""),
                str(target.get("skillId") or ""),
                int(target.get("variantOrdinal") or 0),
            )
            for target in targets
        )

    @classmethod
    def _candidate_content_handoff_is_current(
        cls,
        *,
        release: Mapping[str, Any],
        build: Mapping[str, Any],
        item: Mapping[str, Any],
        plan: Mapping[str, Any],
        complete_item_count: int,
    ) -> bool:
        from services.learning_curriculum_preparation_contract import (
            canonical_preparation_target_for, formal_target_course_count,
            preparation_authority_grade,
        )

        try:
            target = cls.decode_json(build.get("target_spec_json"), {})
            current_target = canonical_preparation_target_for(target)
            grade = preparation_authority_grade(target)
            if (
                not compatible_preparation_target(target, current_target)
                or preparation_authority_grade(item) != grade
                or preparation_authority_grade(plan) != grade
            ):
                return False
            course_count = formal_target_course_count(target)
        except (KeyError, TypeError, ValueError):
            return False
        candidate_count = int(plan.get("content_candidate_count") or 0)
        canary_passed = plan.get("content_canary_passed_at") is not None
        canary_candidate_count = int(
            plan.get("content_canary_candidate_count") or 0
        )
        published_count = int(plan.get("published_course_count") or 0)
        return bool(
            str(release.get("status") or "") == "draft"
            and str(release.get("quality_status") or "") == "building"
            and release.get("activated_at") is None
            and release.get("retired_at") is None
            and 0 <= published_count <= candidate_count <= course_count
            and int(release.get("ready_item_count") or 0) == published_count
            and str(build.get("execution_mode") or "") == "content_only"
            and str(build.get("stage_ceiling") or "") == "content_ready"
            and str(build.get("status") or "") in {"queued", "running"}
            and int(build.get("total_item_count") or 0) == course_count
            and int(build.get("ready_item_count") or 0) == 0
            and int(build.get("failed_item_count") or 0) == 0
            and build.get("error_code") is None
            and build.get("error_message_safe") is None
            and build.get("completed_at") is None
            and str(item.get("content_phase") or "") == "course_ready"
            and str(item.get("status") or "") == "course_ready"
            and str(item.get("content_gate_status") or "") == "passed"
            and bool(str(item.get("content_receipt_hash") or ""))
            and str(item.get("execution_mode_snapshot") or "") == "content_only"
            and str(item.get("content_manifest_version_snapshot") or "")
            == str(build.get("content_manifest_version") or "")
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "")
            in {
                "generating_content",
                "building_classrooms",
                "generating_speech",
                "validating",
                "publishing",
            }
            and int(plan.get("content_target_count") or 0) == course_count
            and 1 <= candidate_count
            and (int(plan.get("content_failed_count") or 0) == 0 or plan.get("library_target_fingerprint") is not None)
            and int(plan.get("content_canary_target_count") or 0) == 3
            and 1 <= canary_candidate_count <= 3
            and (int(plan.get("content_canary_failed_count") or 0) == 0 or plan.get("library_target_fingerprint") is not None)
            and (not canary_passed or canary_candidate_count == 3)
            and (
                canary_passed
                or cls._candidate_item_is_in_canary_manifest(
                    build=build,
                    item=item,
                )
            )
            and (
                (candidate_count == course_count)
                == (plan.get("content_generation_completed_at") is not None)
            )
            and int(plan.get("ready_course_count") or 0) == 0
            and int(plan.get("failed_course_count") or 0) == 0
            and plan.get("completed_at") is None
            and plan.get("superseded_at") is None
            and plan.get("error_code") is None
            and plan.get("error_message_safe") is None
            and complete_item_count == candidate_count
        )

    def get_formal_provider_circuit(
        self,
        conn: DatabaseConnection,
        *,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_provider_circuits
            WHERE circuit_key = ?
            LIMIT 1
            """
            + lock,
            (self.FORMAL_PROVIDER_CIRCUIT_KEY,),
        ).fetchone()

    def claim_initial_formal_provider_probe(
        self, conn: DatabaseConnection, *, now: int
    ) -> bool:
        """Reserve the first probe durably; an existing fuse is never reopened."""
        cursor = conn.execute(
            """
            INSERT INTO learning_openmaic_provider_circuits(
              circuit_key, provider_id, model_id, status, reason_code,
              opened_at, last_probe_at, revision, created_at, updated_at
            ) VALUES (?, ?, ?, 'open', 'initial_probe_pending', ?, ?, 1, ?, ?)
            ON DUPLICATE KEY UPDATE circuit_key = circuit_key
            """,
            (self.FORMAL_PROVIDER_CIRCUIT_KEY, self.FORMAL_PROVIDER_ID,
             self.FORMAL_PROVIDER_MODEL_ID, now, now, now, now),
        )
        return cursor.rowcount == 1

    def complete_initial_formal_provider_probe(
        self, conn: DatabaseConnection, *, claimed_at: int,
        ready: bool, now: int,
    ) -> bool:
        # A newer operator probe or runtime failure always wins over this result.
        cursor = conn.execute(
            """
            UPDATE learning_openmaic_provider_circuits
            SET status = ?, reason_code = ?, probe_succeeded_at = ?,
              closed_at = ?, revision = revision + 1, updated_at = ?
            WHERE circuit_key = ? AND revision = 1 AND status = 'open'
              AND reason_code = 'initial_probe_pending' AND last_probe_at = ?
            """,
            ('closed' if ready else 'open',
             None if ready else 'openmaic_formal_provider_canary_failed',
             now if ready else None, now if ready else None, now,
             self.FORMAL_PROVIDER_CIRCUIT_KEY, claimed_at),
        )
        return cursor.rowcount == 1

    def open_formal_provider_circuit(
        self,
        conn: DatabaseConnection,
        *,
        reason_code: str,
        runtime_id: str | None,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_openmaic_provider_circuits(
              circuit_key, provider_id, model_id, status, reason_code,
              opened_by_runtime_id, opened_at, last_probe_at,
              probe_succeeded_at, closed_at, revision, created_at, updated_at
            ) VALUES (?, ?, ?, 'open', ?, ?, ?, NULL, NULL, NULL, 1, ?, ?)
            ON DUPLICATE KEY UPDATE
              status = 'open', reason_code = VALUES(reason_code),
              opened_by_runtime_id = VALUES(opened_by_runtime_id),
              opened_at = VALUES(opened_at), last_probe_at = NULL,
              probe_succeeded_at = NULL, closed_at = NULL,
              revision = revision + 1, updated_at = VALUES(updated_at)
            """,
            (
                self.FORMAL_PROVIDER_CIRCUIT_KEY,
                self.FORMAL_PROVIDER_ID,
                self.FORMAL_PROVIDER_MODEL_ID,
                reason_code,
                runtime_id,
                now,
                now,
                now,
            ),
        )
        return self.get_formal_provider_circuit(conn, for_update=True)

    def close_formal_provider_circuit_after_probe(
        self,
        conn: DatabaseConnection,
        *,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_openmaic_provider_circuits(
              circuit_key, provider_id, model_id, status, reason_code,
              opened_by_runtime_id, opened_at, last_probe_at,
              probe_succeeded_at, closed_at, revision, created_at, updated_at
            ) VALUES (?, ?, ?, 'closed', NULL, NULL, NULL, ?, ?, ?, 1, ?, ?)
            ON DUPLICATE KEY UPDATE
              status = 'closed', reason_code = NULL,
              opened_by_runtime_id = NULL, last_probe_at = VALUES(last_probe_at),
              probe_succeeded_at = VALUES(probe_succeeded_at),
              closed_at = VALUES(closed_at), revision = revision + 1,
              updated_at = VALUES(updated_at)
            """,
            (
                self.FORMAL_PROVIDER_CIRCUIT_KEY,
                self.FORMAL_PROVIDER_ID,
                self.FORMAL_PROVIDER_MODEL_ID,
                now,
                now,
                now,
                now,
                now,
            ),
        )
        return self.get_formal_provider_circuit(conn, for_update=True)

    def record_formal_provider_probe_failure(
        self,
        conn: DatabaseConnection,
        *,
        reason_code: str,
        now: int,
    ) -> DatabaseRow:
        circuit = self.open_formal_provider_circuit(
            conn,
            reason_code=reason_code,
            runtime_id=None,
            now=now,
        )
        conn.execute(
            """
            UPDATE learning_openmaic_provider_circuits
            SET last_probe_at = ?, updated_at = ?
            WHERE circuit_key = ?
            """,
            (now, now, self.FORMAL_PROVIDER_CIRCUIT_KEY),
        )
        return self.get_formal_provider_circuit(conn, for_update=True)

    def get_release_course_package(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT course.id AS course_id, course.version AS course_version,
              course.grade_code, course.subject, course.node_code,
              course.title, course.objective,
              package.id AS package_id, package.version AS package_version,
              package.public_content_hash,
              release_row.id AS release_id
            FROM learning_catalog_releases AS release_row
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = release_row.id
             AND release_item.course_id = ?
             AND release_item.course_version = ?
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_courses AS course
              ON course.id = release_item.course_id
             AND course.version = release_item.course_version
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.retired_at IS NULL
            JOIN learning_lesson_packages AS package
              ON package.id = release_item.package_id
             AND package.version = release_item.package_version
             AND package.status = 'published'
             AND package.retired_at IS NULL
            WHERE release_row.status = 'active'
              AND release_row.quality_status = 'ready'
              AND release_row.curriculum_version = release_item.curriculum_version
            LIMIT 1
            """,
            (course_id, course_version),
        ).fetchone()

    def get_active_release_course_for_boundary(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        subject: str,
        skill_id: str,
        curriculum_version: str,
        boundary_version: str,
    ) -> DatabaseRow | None:
        """Resolve one server-owned sample course from the active release.

        Callers provide the fixed backend policy constants, never browser
        fields.  Matching both course and release-item identity prevents a
        stale or mislabeled course from supplying the grade in a generation
        requirement.
        """

        return conn.execute(
            """
            SELECT course.id AS course_id, course.version AS course_version,
              course.grade_code, course.subject, course.node_code,
              course.curriculum_version, course.boundary_version,
              course.title, course.objective,
              package.id AS package_id, package.version AS package_version,
              package.public_content_hash,
              release_row.id AS release_id
            FROM learning_catalog_releases AS release_row
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = release_row.id
             AND release_item.grade_code = ?
             AND release_item.subject = ?
             AND release_item.skill_id = ?
             AND release_item.curriculum_version = ?
             AND release_item.boundary_version = ?
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_courses AS course
              ON course.id = release_item.course_id
             AND course.version = release_item.course_version
             AND course.grade_code = release_item.grade_code
             AND course.subject = release_item.subject
             AND course.node_code = release_item.skill_id
             AND course.curriculum_version = release_item.curriculum_version
             AND course.boundary_version = release_item.boundary_version
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.content_origin = 'openmaic_generated'
             AND course.retired_at IS NULL
            JOIN learning_lesson_packages AS package
              ON package.id = release_item.package_id
             AND package.version = release_item.package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
             AND package.status = 'published'
             AND package.retired_at IS NULL
            WHERE release_row.status = 'active'
              AND release_row.quality_status = 'ready'
              AND release_row.curriculum_version = release_item.curriculum_version
            ORDER BY release_item.variant_ordinal ASC, course.id ASC
            LIMIT 1
            """,
            (
                grade_code,
                subject,
                skill_id,
                curriculum_version,
                boundary_version,
            ),
        ).fetchone()

    def get_by_request_id(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_classrooms
            WHERE request_id = ? LIMIT 1
            """
            + lock,
            (request_id,),
        ).fetchone()

    def get_runtime_classroom(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_classrooms
            WHERE id = ? LIMIT 1
            """
            + lock,
            (runtime_id,),
        ).fetchone()

    def bind_candidate_runtime(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        build_item_id: str,
        target_fingerprint: str,
        binding_contract_version: str = CANDIDATE_BINDING_CONTRACT_VERSION,
        now: int,
    ) -> DatabaseRow:
        """Bind one Runtime attempt to an inactive formal build item.

        The Runtime row already owns the exact course/package identity.  This
        method locks and cross-checks that identity against the content item
        and package before persisting the candidate ownership snapshot.
        """

        import re
        from services.learning_curriculum_preparation_contract import (
            build_preparation_target,
            preparation_target_fingerprint,
        )

        if re.fullmatch(r"[0-9a-f]{64}", str(target_fingerprint or "")) is None:
            raise ValueError("candidate target fingerprint is invalid")
        if binding_contract_version != self.CANDIDATE_BINDING_CONTRACT_VERSION:
            raise ValueError("candidate binding contract is unsupported")
        if int(now) <= 0:
            raise ValueError("candidate binding timestamp is invalid")
        authority = conn.execute(
            """
            SELECT runtime.*, item.build_job_id, item.release_id AS item_release_id,
              item.grade_code AS item_grade_code,
              item.course_id AS item_course_id,
              item.course_version AS item_course_version,
              item.curriculum_version AS item_curriculum_version,
              item.content_phase, item.content_gate_status,
              item.content_receipt_hash, build.execution_mode,
              build.stage_ceiling, build.target_spec_json,
              build.curriculum_version AS build_curriculum_version,
              release_row.curriculum_version AS release_curriculum_version,
              release_row.status AS release_status,
              package.course_id AS package_course_id,
              package.course_version AS package_course_version
            FROM learning_openmaic_runtime_classrooms AS runtime
            JOIN learning_catalog_build_items AS item ON item.id = ?
            JOIN learning_catalog_build_jobs AS build
              ON build.id = item.build_job_id
             AND build.release_id = item.release_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = item.release_id
            JOIN learning_lesson_packages AS package
              ON package.id = runtime.package_id
             AND package.version = runtime.package_version
            WHERE runtime.id = ?
            LIMIT 1 FOR UPDATE
            """,
            (build_item_id, runtime_id),
        ).fetchone()
        if authority is None:
            raise ValueError("candidate runtime authority was not found")
        persisted = (
            authority.get("candidate_build_item_id"),
            authority.get("candidate_release_id"),
            authority.get("candidate_grade_code"),
            authority.get("candidate_target_fingerprint"),
            authority.get("candidate_binding_contract_version"),
            authority.get("candidate_bound_at"),
        )
        expected = (
            build_item_id,
            authority["item_release_id"],
            authority["item_grade_code"],
            target_fingerprint,
            binding_contract_version,
            int(now),
        )
        if any(value is not None for value in persisted):
            if persisted[:5] != expected[:5]:
                raise ValueError("candidate runtime is already bound differently")
            return authority
        if (
            str(authority.get("release_status") or "") == "active"
            or conn.execute(
                """
                SELECT grade_code
                FROM learning_curriculum_grade_release_pointers
                WHERE release_id = ? AND pointer_revision >= 1
                LIMIT 1 FOR UPDATE
                """,
                (authority["item_release_id"],),
            ).fetchone()
            is not None
        ):
            raise ValueError("active releases cannot acquire candidate runtimes")
        if (
            str(authority.get("execution_mode") or "") != "content_only"
            or str(authority.get("stage_ceiling") or "") != "content_ready"
            or str(authority.get("content_phase") or "") != "course_ready"
            or str(authority.get("content_gate_status") or "") != "passed"
            or not str(authority.get("content_receipt_hash") or "")
        ):
            raise ValueError("candidate build item is not content-ready")
        target_spec = self.decode_json(authority.get("target_spec_json"), {})
        try:
            canonical_fingerprint = preparation_target_fingerprint(target_spec)
        except (KeyError, TypeError, ValueError):
            raise ValueError("candidate build target contract is invalid") from None
        if (
            canonical_fingerprint != target_fingerprint
            or str(authority.get("item_curriculum_version") or "")
            != str(authority.get("build_curriculum_version") or "")
            or str(authority.get("item_curriculum_version") or "")
            != str(authority.get("release_curriculum_version") or "")
        ):
            raise ValueError("candidate build target identity mismatch")
        exact_identity = (
            str(authority.get("course_id") or ""),
            str(authority.get("course_version") or ""),
        )
        if (
            exact_identity
            != (
                str(authority.get("item_course_id") or ""),
                str(authority.get("item_course_version") or ""),
            )
            or exact_identity
            != (
                str(authority.get("package_course_id") or ""),
                str(authority.get("package_course_version") or ""),
            )
        ):
            raise ValueError("candidate runtime course/package identity mismatch")
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET candidate_build_item_id = ?, candidate_release_id = ?,
              candidate_grade_code = ?, candidate_target_fingerprint = ?,
              candidate_binding_contract_version = ?, candidate_bound_at = ?,
              updated_at = GREATEST(updated_at, ?)
            WHERE id = ? AND candidate_build_item_id IS NULL
              AND candidate_release_id IS NULL AND candidate_grade_code IS NULL
              AND candidate_target_fingerprint IS NULL
              AND candidate_binding_contract_version IS NULL
              AND candidate_bound_at IS NULL
            """,
            (*expected, int(now), runtime_id),
        )
        if updated.rowcount != 1:
            raise ValueError("candidate runtime binding lost its authority")
        bound = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if bound is None:
            raise RuntimeError("candidate runtime disappeared after binding")
        return bound

    def get_candidate_runtime_for_item(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        attempt_ordinal: int | None = None,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        attempt_clause = " AND attempt_ordinal = ?" if attempt_ordinal else ""
        params: tuple[object, ...] = (
            (build_item_id, int(attempt_ordinal))
            if attempt_ordinal
            else (build_item_id,)
        )
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_classrooms
            WHERE candidate_build_item_id = ?
            """
            + attempt_clause
            + " ORDER BY attempt_ordinal DESC LIMIT 1"
            + lock,
            params,
        ).fetchone()

    def get_by_upstream_job(
        self,
        conn: DatabaseConnection,
        *,
        upstream_job_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_classrooms
            WHERE upstream_job_id = ? LIMIT 1
            """
            + lock,
            (upstream_job_id,),
        ).fetchone()

    def get_for_package(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_classrooms
            WHERE package_id = ? AND package_version = ?
              AND retired_at IS NULL
            LIMIT 1
            """
            + lock,
            (package_id, package_version),
        ).fetchone()

    def get_package_runtime_attempts(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
        for_update: bool = False,
    ) -> list[DatabaseRow]:
        lock = " FOR UPDATE" if for_update else ""
        return list(
            conn.execute(
                """
                SELECT * FROM learning_openmaic_runtime_classrooms
                WHERE package_id = ? AND package_version = ?
                ORDER BY attempt_ordinal ASC, created_at ASC, id ASC
                """
                + lock,
                (package_id, package_version),
            ).fetchall()
        )

    def get_next_generating_runtime(
        self, conn: DatabaseConnection
    ) -> DatabaseRow | None:
        """Return one non-terminal task for bounded polling/stale cleanup.

        Pending rows are included so a process interruption between the local
        insert and the upstream start call cannot block this package forever.
        The service never starts or retries such a row; it only terminally
        fails it after the fixed stale deadline.
        """

        return conn.execute(
            """
            SELECT * FROM learning_openmaic_runtime_classrooms
            WHERE status IN ('pending', 'generating')
              AND retired_at IS NULL
            ORDER BY updated_at ASC, id ASC
            LIMIT 1
            """
        ).fetchone()

    def list_nonterminal_runtimes(
        self,
        conn: DatabaseConnection,
        *,
        limit: int = 100,
    ) -> list[DatabaseRow]:
        """Snapshot persisted Runtime work for independent reconciliation.

        A single oldest-row poll can block every completed job behind one
        slow upstream generation.  The worker uses this bounded snapshot so
        each already-persisted job is reconciled once per pass without
        creating or blindly redispatching any new upstream work.
        """

        bounded_limit = max(1, min(int(limit), 100))
        return list(
            conn.execute(
                """
                SELECT * FROM learning_openmaic_runtime_classrooms
                WHERE (status IN ('pending', 'generating') OR (
                    status = 'failed' AND quality_status = 'quarantined'
                    AND error_code = 'openmaic_formal_generation_ambiguous'
                    AND candidate_build_item_id IS NOT NULL
                    AND upstream_job_id IS NOT NULL
                    AND upstream_classroom_id IS NULL
                  ))
                  AND retired_at IS NULL
                ORDER BY updated_at ASC, id ASC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        )

    def get_next_release_without_runtime(
        self, conn: DatabaseConnection
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT course.id AS course_id, course.version AS course_version,
              course.grade_code, course.subject, course.node_code,
              course.title, course.objective,
              package.id AS package_id, package.version AS package_version,
              package.public_content_hash,
              release_row.id AS release_id
            FROM learning_catalog_releases AS release_row
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = release_row.id
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_courses AS course
              ON course.id = release_item.course_id
             AND course.version = release_item.course_version
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.retired_at IS NULL
            JOIN learning_lesson_packages AS package
              ON package.id = release_item.package_id
             AND package.version = release_item.package_version
             AND package.status = 'published'
             AND package.retired_at IS NULL
            LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.package_id = package.id
             AND runtime.package_version = package.version
             AND runtime.retired_at IS NULL
            WHERE release_row.status = 'active'
              AND release_row.quality_status = 'ready'
              AND runtime.id IS NULL
            ORDER BY release_item.variant_ordinal ASC, course.id ASC
            LIMIT 1
            """
        ).fetchone()

    def create_runtime_classroom(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        request_id: str,
        course: Mapping[str, Any],
        feature_manifest: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_openmaic_runtime_classrooms(
              id, request_id, course_id, course_version,
              package_id, package_version, status,
              feature_manifest_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                runtime_id,
                request_id,
                course["course_id"],
                course["course_version"],
                course["package_id"],
                int(course["package_version"]),
                self.encode_json(feature_manifest),
                now,
                now,
            ),
        )
        return self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )

    def get_formal_candidate_generation_authority(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
        target_fingerprint: str,
    ) -> dict[str, Any]:
        """Load the answer-blind brief from the exact locked package/course.

        This read and ``reserve_candidate_runtime`` are intentionally called in
        one database transaction.  The latter repeats the full release/build/
        package authority checks before any runtime row can commit.
        """

        from services.lesson_package_validator import (
            FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
            FORMAL_RUNTIME_PACKAGE_SCHEMA,
            LessonPackageValidationError,
            LessonPackageValidator,
            formal_runtime_teaching_brief,
        )

        row = conn.execute(
            """
            SELECT course.*, package.status AS package_status,
              package.schema_version AS package_schema_version,
              package.compiler_version AS package_compiler_version,
              package.public_payload_json, package.public_content_hash,
              package.source_course_content_hash, package.published_at,
              package.retired_at AS package_retired_at,
              item.course_id AS item_course_id,
              item.course_version AS item_course_version, build.target_spec_json
            FROM learning_catalog_build_items AS item
            JOIN learning_catalog_build_jobs AS build ON build.id = item.build_job_id
             AND build.release_id = item.release_id
            JOIN learning_courses AS course
              ON course.id = item.course_id AND course.version = item.course_version
            JOIN learning_lesson_packages AS package
              ON package.id = ? AND package.version = ?
             AND package.course_id = course.id
             AND package.course_version = course.version
            WHERE item.id = ? AND item.course_id = ? AND item.course_version = ?
            LIMIT 1 FOR UPDATE
            """,
            (
                package_id,
                package_version,
                build_item_id,
                course_id,
                course_version,
            ),
        ).fetchone()
        if row is None:
            raise ValueError("formal candidate generation authority was not found")
        try:
            teaching_brief, brief_hash, content_hash = (
                formal_runtime_teaching_brief(row)
            )
            public_payload = json.loads(str(row.get("public_payload_json") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("formal candidate course content drifted") from None
        expected_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "authority": "mira_backend_candidate_only",
            "buildItemId": build_item_id,
            "courseId": course_id,
            "courseVersion": course_version,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": content_hash,
            "teachingBriefSha256": brief_hash,
            "teachingBrief": teaching_brief,
            "studentLaunchEligible": False,
        }
        try:
            expected_report = LessonPackageValidator().validate_formal_runtime_package(
                payload=expected_payload,
                build_item_id=build_item_id,
                course_id=course_id,
                course_version=course_version,
                target_fingerprint=target_fingerprint,
                teaching_brief=teaching_brief,
                teaching_brief_sha256=brief_hash,
                source_course_content_sha256=content_hash,
            )
        except LessonPackageValidationError:
            raise ValueError("formal candidate package contract is invalid") from None
        public_json = self.encode_json(public_payload)
        if not (
            str(row.get("package_status") or "") == "candidate"
            and str(row.get("package_schema_version") or "")
            == FORMAL_RUNTIME_PACKAGE_SCHEMA
            and str(row.get("package_compiler_version") or "")
            == FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION
            and row.get("published_at") is None
            and row.get("package_retired_at") is None
            and public_payload == expected_payload
            and str(row.get("public_content_hash") or "")
            == hashlib.sha256(public_json.encode("utf-8")).hexdigest()
            and str(row.get("source_course_content_hash") or "") == content_hash
            and expected_report.get("valid") is True
        ):
            raise ValueError("formal candidate package/course authority drifted")
        selected_policy = policy_from_target(self.decode_json(row.get("target_spec_json"), {}))
        return {
            "teachingBrief": teaching_brief,
            "teachingBriefSha256": brief_hash,
            "sourceCourseContentSha256": content_hash,
            "professionalCreationPolicy": selected_policy,
            **grade_boundary_fields(row, selected_policy),
        }

    def reserve_candidate_runtime(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        runtime_request_id: str,
        build_item_id: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
        target_fingerprint: str,
        feature_manifest: Mapping[str, Any],
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        """Atomically reserve a fully bound 057 formal Runtime attempt.

        The candidate columns and attempt/retry columns are written in the
        same INSERT.  This is required by migration 057; creating a legacy
        NULL-bound retry row and binding it later is intentionally impossible.
        """

        import re
        from services.learning_curriculum_preparation_contract import (
            canonical_preparation_target_for,
            preparation_target_fingerprint,
        )

        if re.fullmatch(r"[0-9a-f]{64}", str(target_fingerprint or "")) is None:
            raise ValueError("candidate target fingerprint is invalid")
        if type(package_version) is not int or package_version < 1:
            raise ValueError("candidate package version is invalid")
        if int(now) <= 0:
            raise ValueError("candidate reservation timestamp is invalid")

        def exact_replay(existing: Mapping[str, Any]) -> tuple[DatabaseRow, bool]:
            expected = (
                build_item_id,
                course_id,
                course_version,
                package_id,
                package_version,
                target_fingerprint,
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
            )
            actual = (
                existing.get("candidate_build_item_id"),
                existing.get("course_id"),
                existing.get("course_version"),
                existing.get("package_id"),
                existing.get("package_version"),
                existing.get("candidate_target_fingerprint"),
                existing.get("candidate_binding_contract_version"),
            )
            if actual != expected:
                raise ValueError("candidate runtime request conflict")
            return existing, False

        # Do not gap-lock the absent request row before acquiring the stable
        # release mutex. Two same-key creators would otherwise both retain a
        # shared gap lock and deadlock while upgrading to INSERT.
        existing_hint = self.get_by_request_id(
            conn, request_id=runtime_request_id, for_update=False
        )
        if existing_hint is not None:
            exact_replay(existing_hint)

        seed = conn.execute(
            """
            SELECT id, build_job_id, release_id
            FROM learning_catalog_build_items
            WHERE id = ? LIMIT 1
            """,
            (build_item_id,),
        ).fetchone()
        if seed is None:
            raise ValueError("candidate build item was not found")
        release = conn.execute(
            """SELECT * FROM learning_catalog_releases
            WHERE id = ? LIMIT 1 FOR UPDATE""",
            (seed["release_id"],),
        ).fetchone()
        existing = self.get_by_request_id(
            conn, request_id=runtime_request_id, for_update=True
        )
        build = conn.execute(
            """SELECT * FROM learning_catalog_build_jobs
            WHERE id = ? AND release_id = ? LIMIT 1 FOR UPDATE""",
            (seed["build_job_id"], seed["release_id"]),
        ).fetchone()
        item = conn.execute(
            """SELECT * FROM learning_catalog_build_items
            WHERE id = ? AND build_job_id = ? AND release_id = ?
            LIMIT 1 FOR UPDATE""",
            (build_item_id, seed["build_job_id"], seed["release_id"]),
        ).fetchone()
        course = conn.execute(
            """SELECT * FROM learning_courses
            WHERE id = ? AND version = ? LIMIT 1 FOR UPDATE""",
            (course_id, course_version),
        ).fetchone()
        package = conn.execute(
            """SELECT * FROM learning_lesson_packages
            WHERE id = ? AND version = ? LIMIT 1 FOR UPDATE""",
            (package_id, package_version),
        ).fetchone()
        package_private = conn.execute(
            """SELECT * FROM learning_lesson_package_private
            WHERE package_id = ? AND package_version = ?
            LIMIT 1 FOR UPDATE""",
            (package_id, package_version),
        ).fetchone()
        source_artifact = (
            conn.execute(
                """SELECT * FROM learning_classroom_source_artifacts
                WHERE id = ? LIMIT 1 FOR UPDATE""",
                (package["source_artifact_id"],),
            ).fetchone()
            if package is not None
            else None
        )
        source_job = (
            conn.execute(
                """SELECT * FROM learning_classroom_generation_jobs
                WHERE id = ? LIMIT 1 FOR UPDATE""",
                (source_artifact["job_id"],),
            ).fetchone()
            if source_artifact is not None
            else None
        )
        plan = (
            conn.execute(
                """SELECT * FROM learning_curriculum_preparation_plans
                WHERE catalog_build_id = ? AND catalog_release_id = ?
                  AND shared_build_request_id = ?
                  AND target_spec_json = ? AND curriculum_version = ?
                  AND target_fingerprint = ?
                  AND status = 'running'
                  AND stage IN (
                    'generating_content', 'building_classrooms',
                    'generating_speech', 'validating', 'publishing'
                  )
                  AND superseded_at IS NULL
                  AND completed_at IS NULL
                  AND error_code IS NULL
                  AND error_message_safe IS NULL
                LIMIT 1 FOR UPDATE""",
                (
                    seed["build_job_id"],
                    seed["release_id"],
                    build["request_id"],
                    build["target_spec_json"],
                    build["curriculum_version"],
                    target_fingerprint,
                ),
            ).fetchone()
            if build is not None
            else None
        )
        complete_item_count = (
            conn.execute(
                """SELECT COUNT(*) AS count_value
                FROM learning_catalog_build_items
                WHERE build_job_id = ? AND release_id = ?
                  AND status = 'course_ready'
                  AND content_phase = 'course_ready'
                  AND content_gate_status = 'passed'
                  AND content_receipt_hash IS NOT NULL
                  AND course_id IS NOT NULL AND course_version IS NOT NULL
                  AND execution_mode_snapshot = 'content_only'
                  AND content_manifest_version_snapshot = ?""",
                (
                    seed["build_job_id"],
                    seed["release_id"],
                    build["content_manifest_version"],
                ),
            ).fetchone()
            if build is not None
            else None
        )
        if any(
            value is None
            for value in (release, build, item, course, package, plan)
        ):
            raise ValueError("candidate runtime authority was not found")
        if any(
            value is None
            for value in (package_private, source_artifact, source_job)
        ):
            raise ValueError("formal candidate package authority mismatch")
        active_pointer = conn.execute(
            """SELECT grade_code
            FROM learning_curriculum_grade_release_pointers
            WHERE release_id = ? AND pointer_revision >= 1
            LIMIT 1 FOR UPDATE""",
            (seed["release_id"],),
        ).fetchone()
        if active_pointer is not None:
            raise ValueError("active releases cannot acquire candidate runtimes")
        if course.get("retired_at") is not None or not self._candidate_content_handoff_is_current(
            release=release,
            build=build,
            item=item,
            plan=plan,
            complete_item_count=int(
                (complete_item_count or {}).get("count_value") or 0
            ),
        ):
            raise ValueError("candidate runtime handoff authority is not current")
        target_spec = self.decode_json(build.get("target_spec_json"), {})
        try:
            current_target = canonical_preparation_target_for(target_spec)
            canonical_fingerprint = preparation_target_fingerprint(target_spec)
            current_fingerprint = preparation_target_fingerprint(current_target)
        except (KeyError, TypeError, ValueError):
            raise ValueError("candidate build target contract is invalid") from None
        if (
            not compatible_preparation_target(target_spec, current_target)
            or canonical_fingerprint != target_fingerprint
        ):
            raise ValueError("candidate build target identity mismatch")

        from services.lesson_package_validator import (
            FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
            FORMAL_RUNTIME_PACKAGE_SCHEMA,
            FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
            LessonPackageValidationError,
            LessonPackageValidator,
            formal_runtime_teaching_brief,
        )

        try:
            teaching_brief, teaching_brief_hash, course_content_hash = (
                formal_runtime_teaching_brief(course)
            )
        except ValueError:
            raise ValueError("formal candidate course content is invalid") from None

        expected_package_id = "formal_runtime_package_" + hashlib.sha256(
            build_item_id.encode("utf-8")
        ).hexdigest()[:48]
        expected_public_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "authority": "mira_backend_candidate_only",
            "buildItemId": build_item_id,
            "courseId": course_id,
            "courseVersion": course_version,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": course_content_hash,
            "teachingBriefSha256": teaching_brief_hash,
            "teachingBrief": teaching_brief,
            "studentLaunchEligible": False,
        }
        expected_private_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "buildItemId": build_item_id,
            "targetFingerprint": target_fingerprint,
        }
        expected_source_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
            "buildItemId": build_item_id,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": course_content_hash,
            "teachingBriefSha256": teaching_brief_hash,
            "publicationEligible": False,
        }
        try:
            expected_validation_report = (
                LessonPackageValidator().validate_formal_runtime_package(
                    payload=expected_public_payload,
                    build_item_id=build_item_id,
                    course_id=course_id,
                    course_version=course_version,
                    target_fingerprint=target_fingerprint,
                    teaching_brief=teaching_brief,
                    teaching_brief_sha256=teaching_brief_hash,
                    source_course_content_sha256=course_content_hash,
                )
            )
        except LessonPackageValidationError:
            raise ValueError("formal candidate package contract is invalid") from None
        public_json = str(package.get("public_payload_json") or "")
        private_json = str(package_private.get("payload_json") or "")
        source_json = str(source_artifact.get("payload_json") or "")
        report_json = str(package.get("validation_report_json") or "")
        source_report_json = str(
            source_artifact.get("validation_report_json") or ""
        )
        try:
            public_payload = json.loads(public_json)
            private_payload = json.loads(private_json)
            source_payload = json.loads(source_json)
            validation_report = json.loads(report_json)
            source_validation_report = json.loads(source_report_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("formal candidate package payload is invalid") from None
        seed_digest = hashlib.sha256(build_item_id.encode("utf-8")).hexdigest()[:48]
        package_contract_matches = bool(
            package_id == expected_package_id
            and int(package_version) == 1
            and str(package.get("status") or "") == "candidate"
            and str(package.get("schema_version") or "")
            == FORMAL_RUNTIME_PACKAGE_SCHEMA
            and str(package.get("compiler_version") or "")
            == FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION
            and package.get("published_at") is None
            and package.get("retired_at") is None
            and public_payload == expected_public_payload
            and private_payload == expected_private_payload
            and source_payload == expected_source_payload
            and validation_report == expected_validation_report
            and source_validation_report == expected_validation_report
            and str(package_private.get("schema_version") or "")
            == FORMAL_RUNTIME_PACKAGE_SCHEMA
            and str(source_artifact.get("source_format") or "")
            == FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA
            and str(source_artifact.get("dsl_version") or "")
            == "formal-runtime-v1"
            and str(source_artifact.get("status") or "") == "compiled"
            and str(source_artifact.get("id") or "")
            == f"formal_runtime_source_{seed_digest}"
            and str(source_job.get("id") or "")
            == f"formal_runtime_job_{seed_digest}"
            and str(source_job.get("generator") or "")
            == "formal_package_authority"
            and str(source_job.get("status") or "") == "staged"
            and source_job.get("started_at") is None
            and source_job.get("completed_at") is None
            and str(source_job.get("course_id") or "") == course_id
            and str(source_job.get("course_version") or "") == course_version
            and str(source_job.get("package_id") or "") == package_id
            and int(source_job.get("package_version") or 0) == package_version
            and str(package.get("source_course_content_hash") or "")
            == course_content_hash
            and str(package.get("public_content_hash") or "")
            == hashlib.sha256(public_json.encode("utf-8")).hexdigest()
            and str(package.get("private_content_hash") or "")
            == hashlib.sha256(private_json.encode("utf-8")).hexdigest()
            and str(package_private.get("content_hash") or "")
            == hashlib.sha256(private_json.encode("utf-8")).hexdigest()
            and str(source_artifact.get("source_hash") or "")
            == hashlib.sha256(source_json.encode("utf-8")).hexdigest()
        )
        if not package_contract_matches:
            raise ValueError("formal candidate package authority mismatch")
        item_identity = (
            str(item.get("course_id") or ""),
            str(item.get("course_version") or ""),
        )
        requested_identity = (str(course_id), str(course_version))
        if (
            item_identity != requested_identity
            or (str(course.get("id") or ""), str(course.get("version") or ""))
            != requested_identity
            or (
                str(package.get("course_id") or ""),
                str(package.get("course_version") or ""),
            )
            != requested_identity
            or str(item.get("grade_code") or "")
            != str(course.get("grade_code") or "")
            or str(item.get("curriculum_version") or "")
            != str(build.get("curriculum_version") or "")
            or str(item.get("curriculum_version") or "")
            != str(release.get("curriculum_version") or "")
        ):
            raise ValueError("candidate runtime course/package identity mismatch")

        selected_policy = policy_from_target(target_spec)
        if adaptive_policy(selected_policy):
            generation = feature_manifest.get("generationContract")
            if (not isinstance(generation, Mapping)
                    or generation.get("professionalCreationPolicy") != selected_policy):
                raise ValueError("candidate grade boundary policy mismatch")
            validate_generation_grade_boundary(generation, course)
        if existing is not None:
            return exact_replay(existing)

        attempts = list(
            conn.execute(
                """SELECT * FROM learning_openmaic_runtime_classrooms
                WHERE candidate_build_item_id = ?
                ORDER BY attempt_ordinal ASC, created_at ASC, id ASC
                FOR UPDATE""",
                (build_item_id,),
            ).fetchall()
        )
        if [int(row["attempt_ordinal"]) for row in attempts] != list(
            range(1, len(attempts) + 1)
        ):
            raise ValueError("candidate runtime attempt history is invalid")
        provider_attempts = [
            int(row["provider_attempt_ordinal"])
            for row in attempts
            if row.get("provider_attempt_ordinal") is not None
        ]
        if provider_attempts != list(range(1, len(provider_attempts) + 1)):
            raise ValueError("candidate Provider attempt history is invalid")
        if any(
            (
                str(row.get("course_id") or ""),
                str(row.get("course_version") or ""),
                str(row.get("package_id") or ""),
                int(row.get("package_version") or 0),
                str(row.get("candidate_target_fingerprint") or ""),
            )
            != (
                course_id,
                course_version,
                package_id,
                package_version,
                target_fingerprint,
            )
            for row in attempts
        ):
            raise ValueError("candidate runtime attempt history drifted")
        attempt_ordinal = len(attempts) + 1
        provider_attempt_ordinal = len(provider_attempts) + 1
        if attempt_ordinal > 16 or provider_attempt_ordinal > 3:
            raise ValueError("candidate Provider attempt limit reached")
        previous = attempts[-1] if attempts else None
        if previous is not None:
            previous_error = str(previous.get("error_code") or "")
            if (
                str(previous.get("status") or "") != "failed"
                or str(previous.get("quality_status") or "") != "rejected"
                or not previous_error.startswith("openmaic_formal_")
                or "ambiguous" in previous_error
                or not str(previous.get("upstream_job_id") or "")
                or previous.get("retired_at") is not None
            ):
                raise ValueError("candidate runtime is not safely retryable")

        retry_of_runtime_id = str(previous["id"]) if previous is not None else None
        retry_reason = (
            f"formal_candidate_retry_{attempt_ordinal}"
            if previous is not None
            else None
        )
        expected_previous_job_id = (
            str(previous["upstream_job_id"]) if previous is not None else None
        )
        conn.execute(
            """
            INSERT INTO learning_openmaic_runtime_classrooms(
              id, request_id, attempt_ordinal, provider_attempt_ordinal,
              retry_of_runtime_id,
              retry_reason, expected_previous_job_id,
              course_id, course_version, package_id, package_version,
              status, quality_status, feature_manifest_json,
              candidate_build_item_id, candidate_release_id,
              candidate_grade_code, candidate_target_fingerprint,
              candidate_binding_contract_version, candidate_bound_at,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              'pending', 'pending_review', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                runtime_id,
                runtime_request_id,
                attempt_ordinal,
                provider_attempt_ordinal,
                retry_of_runtime_id,
                retry_reason,
                expected_previous_job_id,
                course_id,
                course_version,
                package_id,
                package_version,
                self.encode_json(feature_manifest),
                build_item_id,
                seed["release_id"],
                item["grade_code"],
                target_fingerprint,
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                now,
                now,
                now,
            ),
        )
        row = self.get_by_request_id(
            conn, request_id=runtime_request_id, for_update=True
        )
        if row is None:
            raise RuntimeError("candidate runtime reservation disappeared")
        return row, True

    def quarantine_candidate_dispatch(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> DatabaseRow:
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', quality_status = 'quarantined',
              error_code = ?, error_message_safe = ?, updated_at = ?
            WHERE id = ? AND candidate_build_item_id IS NOT NULL
              AND status = 'pending' AND upstream_job_id IS NULL
              AND quality_status = 'pending_review' AND retired_at IS NULL
            """,
            (error_code[:128], error_message_safe[:512], now, runtime_id),
        )
        row = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if row is None or (
            updated.rowcount != 1
            and not (
                str(row.get("status") or "") == "failed"
                and str(row.get("quality_status") or "") == "quarantined"
                and str(row.get("error_code") or "") == error_code[:128]
            )
        ):
            raise RuntimeError("candidate dispatch quarantine conflict")
        return row

    def assert_candidate_completion_authority(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        build_item_id: str,
        target_fingerprint: str,
        expected_upstream_job_id: str,
    ) -> DatabaseRow:
        """Lock and revalidate the exact progressive handoff before passed evidence."""

        authority = conn.execute(
            """
            SELECT runtime.*, item.build_job_id, item.release_id,
              item.course_id AS item_course_id,
              item.course_version AS item_course_version,
              item.grade_code AS item_grade_code,
              item.subject AS item_subject, item.skill_id,
              item.variant_ordinal,
              item.curriculum_version AS item_curriculum_version,
              item.status AS item_status, item.content_phase,
              item.content_gate_status, item.content_receipt_hash,
              item.execution_mode_snapshot,
              item.content_manifest_version_snapshot,
              build.status AS build_status, build.execution_mode,
              build.curriculum_version AS build_curriculum_version,
              build.stage_ceiling, build.total_item_count,
              build.ready_item_count AS build_ready_item_count,
              build.failed_item_count AS build_failed_item_count,
              build.content_manifest_version, build.canary_manifest_json,
              build.completed_at AS build_completed_at,
              build.error_code AS build_error_code,
              build.error_message_safe AS build_error_message_safe,
              release_row.status AS release_status,
              release_row.curriculum_version AS release_curriculum_version,
              release_row.quality_status AS release_quality_status,
              release_row.activated_at AS release_activated_at,
              release_row.retired_at AS release_retired_at,
              release_row.ready_item_count AS release_ready_item_count,
              plan.id AS preparation_plan_id, plan.status AS plan_status,
              plan.grade_code AS plan_grade_code,
              plan.curriculum_version AS plan_curriculum_version,
              plan.stage AS plan_stage, plan.content_target_count, plan.library_target_fingerprint,
              plan.content_candidate_count, plan.content_failed_count,
              plan.content_canary_target_count,
              plan.content_canary_candidate_count,
              plan.content_canary_failed_count,
              plan.content_canary_passed_at,
              plan.content_generation_completed_at,
              plan.ready_course_count AS plan_ready_course_count,
              plan.failed_course_count AS plan_failed_course_count,
              plan.published_course_count,
              plan.completed_at AS plan_completed_at,
              plan.superseded_at AS plan_superseded_at,
              plan.error_code AS plan_error_code,
              plan.error_message_safe AS plan_error_message_safe,
              plan.target_spec_json AS plan_target_spec_json,
              course.id AS locked_course_id,
              course.version AS locked_course_version,
              course.grade_code AS locked_course_grade_code,
              course.subject AS locked_course_subject,
              course.node_code AS locked_course_node_code,
              course.curriculum_version AS locked_course_curriculum_version,
              course.boundary_version AS locked_course_boundary_version,
              course.title AS locked_course_title,
              course.objective AS locked_course_objective,
              course.content_json AS locked_course_content_json,
              course.retired_at AS locked_course_retired_at,
              package.status AS locked_package_status,
              package.schema_version AS locked_package_schema_version,
              package.compiler_version AS locked_package_compiler_version,
              package.public_payload_json AS locked_public_payload_json,
              package.public_content_hash AS locked_public_content_hash,
              package.private_content_hash AS locked_private_content_hash,
              package.validation_report_json AS locked_package_validation_json,
              package.source_course_content_hash AS locked_source_course_hash,
              package.source_artifact_id AS locked_source_artifact_id,
              package.published_at AS locked_package_published_at,
              package.retired_at AS locked_package_retired_at,
              package_private.schema_version AS locked_private_schema_version,
              package_private.payload_json AS locked_private_payload_json,
              package_private.content_hash AS locked_private_row_hash,
              source.id AS locked_source_id,
              source.job_id AS locked_source_job_id,
              source.source_format AS locked_source_format,
              source.dsl_version AS locked_source_dsl_version,
              source.status AS locked_source_status,
              source.source_hash AS locked_source_hash,
              source.payload_json AS locked_source_payload_json,
              source.validation_report_json AS locked_source_validation_json,
              source_job.generator AS locked_source_job_generator,
              source_job.status AS locked_source_job_status,
              source_job.course_id AS locked_source_job_course_id,
              source_job.course_version AS locked_source_job_course_version,
              source_job.package_id AS locked_source_job_package_id,
              source_job.package_version AS locked_source_job_package_version,
              source_job.started_at AS locked_source_job_started_at,
              source_job.completed_at AS locked_source_job_completed_at,
              (
                SELECT COUNT(*)
                FROM learning_catalog_build_items AS complete_item
                WHERE complete_item.build_job_id = build.id
                  AND complete_item.release_id = release_row.id
                  AND complete_item.status = 'course_ready'
                  AND complete_item.content_phase = 'course_ready'
                  AND complete_item.content_gate_status = 'passed'
                  AND complete_item.content_receipt_hash IS NOT NULL
                  AND complete_item.course_id IS NOT NULL
                  AND complete_item.course_version IS NOT NULL
                  AND complete_item.execution_mode_snapshot = 'content_only'
                  AND complete_item.content_manifest_version_snapshot =
                    build.content_manifest_version
              ) AS complete_item_count
            FROM learning_openmaic_runtime_classrooms AS runtime
            JOIN learning_catalog_build_items AS item
              ON item.id = runtime.candidate_build_item_id
             AND item.release_id = runtime.candidate_release_id
            JOIN learning_catalog_build_jobs AS build
              ON build.id = item.build_job_id AND build.release_id = item.release_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = item.release_id
            JOIN learning_curriculum_preparation_plans AS plan
              ON plan.catalog_build_id = build.id
             AND plan.catalog_release_id = release_row.id
             AND plan.shared_build_request_id = build.request_id
             AND plan.target_spec_json = build.target_spec_json
             AND plan.curriculum_version = build.curriculum_version
             AND plan.target_fingerprint = runtime.candidate_target_fingerprint
             AND (
               plan.library_target_fingerprint = runtime.candidate_target_fingerprint
               OR (plan.library_target_fingerprint IS NULL AND NOT EXISTS (
                 SELECT 1 FROM learning_curriculum_preparation_plans AS production_owner
                 WHERE production_owner.catalog_build_id = build.id
                   AND production_owner.library_target_fingerprint = runtime.candidate_target_fingerprint
               ))
             )
             AND plan.status = 'running'
             AND plan.stage IN (
               'generating_content', 'building_classrooms',
               'generating_speech', 'validating', 'publishing'
             )
             AND plan.superseded_at IS NULL
             AND plan.completed_at IS NULL
             AND plan.error_code IS NULL
             AND plan.error_message_safe IS NULL
            JOIN learning_courses AS course
              ON course.id = runtime.course_id
             AND course.version = runtime.course_version
             AND course.id = item.course_id
             AND course.version = item.course_version
            JOIN learning_lesson_packages AS package
              ON package.id = runtime.package_id
             AND package.version = runtime.package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
            JOIN learning_lesson_package_private AS package_private
              ON package_private.package_id = package.id
             AND package_private.package_version = package.version
            JOIN learning_classroom_source_artifacts AS source
              ON source.id = package.source_artifact_id
            JOIN learning_classroom_generation_jobs AS source_job
              ON source_job.id = source.job_id
            WHERE runtime.id = ? AND runtime.candidate_build_item_id = ?
              AND runtime.candidate_target_fingerprint = ?
            LIMIT 1 FOR UPDATE
            """,
            (runtime_id, build_item_id, target_fingerprint),
        ).fetchone()
        if authority is None:
            raise ValueError("candidate completion authority was not found")
        active_pointer = conn.execute(
            """SELECT grade_code
            FROM learning_curriculum_grade_release_pointers
            WHERE release_id = ? AND pointer_revision >= 1
            LIMIT 1 FOR UPDATE""",
            (authority["release_id"],),
        ).fetchone()
        from services.learning_curriculum_preparation_contract import (
            canonical_preparation_target_for,
            preparation_authority_grade,
            preparation_target_fingerprint,
        )
        from services.lesson_package_validator import (
            FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
            FORMAL_RUNTIME_PACKAGE_SCHEMA,
            FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
            LessonPackageValidationError,
            LessonPackageValidator,
            formal_runtime_request_id,
            formal_runtime_teaching_brief,
        )
        from integrations.openmaic_full_runtime_client import (
            OpenMaicFullRuntimeClient,
        )
        from content.teacher_profiles import (
            get_formal_runtime_teacher_contract,
        )

        persisted_target = self.decode_json(
            authority.get("plan_target_spec_json"), {}
        )
        current_target = canonical_preparation_target_for(persisted_target)
        expected_grade = preparation_authority_grade(persisted_target)
        current_target_matches = bool(
            compatible_preparation_target(persisted_target, current_target)
            and preparation_target_fingerprint(persisted_target) == target_fingerprint
        )
        locked_course = {
            "id": authority.get("locked_course_id"),
            "version": authority.get("locked_course_version"),
            "grade_code": authority.get("locked_course_grade_code"),
            "subject": authority.get("locked_course_subject"),
            "node_code": authority.get("locked_course_node_code"),
            "curriculum_version": authority.get("locked_course_curriculum_version"),
            "boundary_version": authority.get("locked_course_boundary_version"),
            "title": authority.get("locked_course_title"),
            "objective": authority.get("locked_course_objective"),
            "content_json": authority.get("locked_course_content_json"),
        }
        try:
            brief, brief_hash, course_content_hash = formal_runtime_teaching_brief(
                locked_course
            )
            public_payload = json.loads(
                str(authority.get("locked_public_payload_json") or "")
            )
            private_payload = json.loads(
                str(authority.get("locked_private_payload_json") or "")
            )
            source_payload = json.loads(
                str(authority.get("locked_source_payload_json") or "")
            )
            package_report = json.loads(
                str(authority.get("locked_package_validation_json") or "")
            )
            source_report = json.loads(
                str(authority.get("locked_source_validation_json") or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            raise ValueError("candidate completion package authority drifted") from None
        expected_public = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "authority": "mira_backend_candidate_only",
            "buildItemId": build_item_id,
            "courseId": str(authority.get("course_id") or ""),
            "courseVersion": str(authority.get("course_version") or ""),
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": course_content_hash,
            "teachingBriefSha256": brief_hash,
            "teachingBrief": brief,
            "studentLaunchEligible": False,
        }
        expected_private = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA,
            "buildItemId": build_item_id,
            "targetFingerprint": target_fingerprint,
        }
        expected_source = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
            "buildItemId": build_item_id,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": course_content_hash,
            "teachingBriefSha256": brief_hash,
            "publicationEligible": False,
        }
        try:
            expected_report = LessonPackageValidator().validate_formal_runtime_package(
                payload=expected_public,
                build_item_id=build_item_id,
                course_id=str(authority.get("course_id") or ""),
                course_version=str(authority.get("course_version") or ""),
                target_fingerprint=target_fingerprint,
                teaching_brief=brief,
                teaching_brief_sha256=brief_hash,
                source_course_content_sha256=course_content_hash,
            )
        except LessonPackageValidationError:
            raise ValueError("candidate completion package authority drifted") from None
        public_json = str(authority.get("locked_public_payload_json") or "")
        private_json = str(authority.get("locked_private_payload_json") or "")
        source_json = str(authority.get("locked_source_payload_json") or "")
        seed_digest = hashlib.sha256(build_item_id.encode("utf-8")).hexdigest()[:48]
        package_authority_matches = bool(
            str(authority.get("locked_course_id") or "")
            == str(authority.get("course_id") or "")
            and str(authority.get("locked_course_version") or "")
            == str(authority.get("course_version") or "")
            and authority.get("locked_course_retired_at") is None
            and str(authority.get("package_id") or "")
            == f"formal_runtime_package_{seed_digest}"
            and int(authority.get("package_version") or 0) == 1
            and str(authority.get("locked_package_status") or "") == "candidate"
            and str(authority.get("locked_package_schema_version") or "")
            == FORMAL_RUNTIME_PACKAGE_SCHEMA
            and str(authority.get("locked_package_compiler_version") or "")
            == FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION
            and authority.get("locked_package_published_at") is None
            and authority.get("locked_package_retired_at") is None
            and public_payload == expected_public
            and private_payload == expected_private
            and source_payload == expected_source
            and package_report == expected_report
            and source_report == expected_report
            and str(authority.get("locked_source_course_hash") or "")
            == course_content_hash
            and str(authority.get("locked_public_content_hash") or "")
            == hashlib.sha256(public_json.encode("utf-8")).hexdigest()
            and str(authority.get("locked_private_content_hash") or "")
            == hashlib.sha256(private_json.encode("utf-8")).hexdigest()
            and str(authority.get("locked_private_row_hash") or "")
            == hashlib.sha256(private_json.encode("utf-8")).hexdigest()
            and str(authority.get("locked_source_hash") or "")
            == hashlib.sha256(source_json.encode("utf-8")).hexdigest()
            and str(authority.get("locked_private_schema_version") or "")
            == FORMAL_RUNTIME_PACKAGE_SCHEMA
            and str(authority.get("locked_source_id") or "")
            == f"formal_runtime_source_{seed_digest}"
            and str(authority.get("locked_source_job_id") or "")
            == f"formal_runtime_job_{seed_digest}"
            and str(authority.get("locked_source_format") or "")
            == FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA
            and str(authority.get("locked_source_dsl_version") or "")
            == "formal-runtime-v1"
            and str(authority.get("locked_source_status") or "") == "compiled"
            and str(authority.get("locked_source_job_generator") or "")
            == "formal_package_authority"
            and str(authority.get("locked_source_job_status") or "") == "staged"
            and authority.get("locked_source_job_started_at") is None
            and authority.get("locked_source_job_completed_at") is None
            and str(authority.get("locked_source_job_course_id") or "")
            == str(authority.get("course_id") or "")
            and str(authority.get("locked_source_job_course_version") or "")
            == str(authority.get("course_version") or "")
            and str(authority.get("locked_source_job_package_id") or "")
            == str(authority.get("package_id") or "")
            and int(authority.get("locked_source_job_package_version") or 0) == 1
        )
        expected_request_id = formal_runtime_request_id(
            build_item_id, int(authority.get("attempt_ordinal") or 0)
        )
        expected_generation_contract = {
            "schemaVersion": OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION,
            "authority": "mira_backend_formal_candidate",
            "buildItemId": build_item_id,
            "course": {
                "id": str(authority.get("course_id") or ""),
                "version": str(authority.get("course_version") or ""),
                "packageId": str(authority.get("package_id") or ""),
                "packageVersion": int(authority.get("package_version") or 0),
            },
            "targetFingerprint": target_fingerprint,
            "runtimeRequestId": expected_request_id,
            "coursewareAuthority": dict(
                OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
            ),
            "professionalCreationPolicy": json.loads(
                json.dumps(
                    policy_from_target(persisted_target),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
            "sourceCourseContentSha256": course_content_hash,
            "teachingBriefSha256": brief_hash,
            "teachingBrief": brief,
            "teacher": get_formal_runtime_teacher_contract(
                str(authority.get("locked_course_subject") or "")
            ),
            "requiredClassroom": (
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT
            ),
            "generation": json.loads(
                json.dumps(
                    generation_options(policy_from_target(persisted_target)),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
        }
        if isinstance(brief.get("difficultyPolicy"), Mapping):
            from content.formal_difficulty_policy import formal_difficulty_policy
            brief_course = brief["course"]
            difficulty = formal_difficulty_policy(
                str(brief_course.get("gradeCode")), str(brief_course.get("subject")),
                str(brief_course.get("skillId")), str(brief_course.get("difficultyCode")),
            )
            if difficulty != brief["difficultyPolicy"]:
                raise ValueError("candidate completion difficulty authority mismatch")
            expected_generation_contract["difficultyPolicy"] = difficulty
            expected_generation_contract["course"]["difficultyCode"] = difficulty["difficultyCode"]
        expected_generation_contract.update(
            grade_boundary_fields(locked_course, policy_from_target(persisted_target))
        )
        runtime_manifest = self.decode_json(
            authority.get("feature_manifest_json"), {}
        )
        runtime_binding_matches = bool(
            str(authority.get("request_id") or "") == expected_request_id
            and str(authority.get("candidate_release_id") or "")
            == str(authority.get("release_id") or "")
            and str(authority.get("candidate_grade_code") or "")
            == str(authority.get("item_grade_code") or "")
            and str(authority.get("candidate_binding_contract_version") or "")
            == self.CANDIDATE_BINDING_CONTRACT_VERSION
            and authority.get("candidate_bound_at") is not None
            and isinstance(runtime_manifest, Mapping)
            and runtime_manifest.get("generationContract")
            == expected_generation_contract
            and runtime_manifest.get("formalRuntimeContract")
            == OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT
            and str(runtime_manifest.get("sourceCourseContentSha256") or "")
            == course_content_hash
            and str(runtime_manifest.get("teachingBriefSha256") or "")
            == brief_hash
        )
        progressive_handoff_matches = self._candidate_content_handoff_is_current(
            release={
                "status": authority.get("release_status"),
                "quality_status": authority.get("release_quality_status"),
                "activated_at": authority.get("release_activated_at"),
                "retired_at": authority.get("release_retired_at"),
                "ready_item_count": authority.get("release_ready_item_count"),
            },
            build={
                "target_spec_json": authority.get("plan_target_spec_json"),
                "execution_mode": authority.get("execution_mode"),
                "stage_ceiling": authority.get("stage_ceiling"),
                "status": authority.get("build_status"),
                "total_item_count": authority.get("total_item_count"),
                "ready_item_count": authority.get("build_ready_item_count"),
                "failed_item_count": authority.get("build_failed_item_count"),
                "content_manifest_version": authority.get(
                    "content_manifest_version"
                ),
                "canary_manifest_json": authority.get("canary_manifest_json"),
                "completed_at": authority.get("build_completed_at"),
                "error_code": authority.get("build_error_code"),
                "error_message_safe": authority.get(
                    "build_error_message_safe"
                ),
            },
            item={
                "grade_code": authority.get("item_grade_code"),
                "subject": authority.get("item_subject"),
                "skill_id": authority.get("skill_id"),
                "variant_ordinal": authority.get("variant_ordinal"),
                "content_phase": authority.get("content_phase"),
                "status": authority.get("item_status"),
                "content_gate_status": authority.get("content_gate_status"),
                "content_receipt_hash": authority.get("content_receipt_hash"),
                "execution_mode_snapshot": authority.get(
                    "execution_mode_snapshot"
                ),
                "content_manifest_version_snapshot": authority.get(
                    "content_manifest_version_snapshot"
                ),
            },
            plan={
                "grade_code": authority.get("plan_grade_code"),
                "target_spec_json": authority.get("plan_target_spec_json"),
                "status": authority.get("plan_status"),
                "stage": authority.get("plan_stage"),
                "content_target_count": authority.get("content_target_count"),
                "content_candidate_count": authority.get(
                    "content_candidate_count"
                ),
                "content_failed_count": authority.get("content_failed_count"),
                "library_target_fingerprint": authority.get("library_target_fingerprint"),
                "content_canary_target_count": authority.get(
                    "content_canary_target_count"
                ),
                "content_canary_candidate_count": authority.get(
                    "content_canary_candidate_count"
                ),
                "content_canary_failed_count": authority.get(
                    "content_canary_failed_count"
                ),
                "content_canary_passed_at": authority.get(
                    "content_canary_passed_at"
                ),
                "content_generation_completed_at": authority.get(
                    "content_generation_completed_at"
                ),
                "ready_course_count": authority.get("plan_ready_course_count"),
                "failed_course_count": authority.get(
                    "plan_failed_course_count"
                ),
                "published_course_count": authority.get(
                    "published_course_count"
                ),
                "completed_at": authority.get("plan_completed_at"),
                "superseded_at": authority.get("plan_superseded_at"),
                "error_code": authority.get("plan_error_code"),
                "error_message_safe": authority.get(
                    "plan_error_message_safe"
                ),
            },
            complete_item_count=int(authority.get("complete_item_count") or 0),
        )
        if not (
            current_target_matches
            and package_authority_matches
            and runtime_binding_matches
            and str(authority.get("status") or "") in {"generating", "ready"}
            and str(authority.get("quality_status") or "")
            in {"pending_review", "candidate"}
            and str(authority.get("upstream_job_id") or "")
            == str(expected_upstream_job_id or "")
            and str(authority.get("item_course_id") or "")
            == str(authority.get("course_id") or "")
            and str(authority.get("item_course_version") or "")
            == str(authority.get("course_version") or "")
            and str(authority.get("item_grade_code") or "")
            == str(authority.get("candidate_grade_code") or "")
            == str(authority.get("plan_grade_code") or "")
            == str(authority.get("locked_course_grade_code") or "")
            == expected_grade
            and str(authority.get("item_curriculum_version") or "")
            == str(authority.get("build_curriculum_version") or "")
            == str(authority.get("release_curriculum_version") or "")
            == str(authority.get("plan_curriculum_version") or "")
            and str(authority.get("item_status") or "") == "course_ready"
            and str(authority.get("content_phase") or "") == "course_ready"
            and str(authority.get("content_gate_status") or "") == "passed"
            and bool(str(authority.get("content_receipt_hash") or ""))
            and str(authority.get("execution_mode_snapshot") or "")
            == "content_only"
            and str(authority.get("content_manifest_version_snapshot") or "")
            == str(authority.get("content_manifest_version") or "")
            and progressive_handoff_matches
            and active_pointer is None
        ):
            raise ValueError("candidate completion authority is no longer current")
        return authority

    def quarantine_candidate_generation(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> DatabaseRow:
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', quality_status = 'quarantined',
              error_code = ?, error_message_safe = ?, updated_at = ?
            WHERE id = ? AND candidate_build_item_id IS NOT NULL
              AND status IN ('pending', 'generating')
              AND quality_status = 'pending_review' AND retired_at IS NULL
            """,
            (error_code[:128], error_message_safe[:512], now, runtime_id),
        )
        row = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if row is None or (
            updated.rowcount != 1
            and not (
                str(row.get("status") or "") == "failed"
                and str(row.get("quality_status") or "") == "quarantined"
                and str(row.get("error_code") or "") == error_code[:128]
            )
        ):
            raise RuntimeError("candidate generation quarantine conflict")
        return row

    def reject_candidate_generation(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        error_code: str,
        error_message_safe: str,
        now: int,
        provider_attempt_consumed: bool = True,
    ) -> DatabaseRow:
        if not str(error_code).startswith("openmaic_formal_"):
            raise ValueError("candidate rejection error code is invalid")
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', quality_status = 'rejected',
              error_code = ?, error_message_safe = ?,
              provider_attempt_ordinal = CASE
                WHEN ? THEN provider_attempt_ordinal ELSE NULL END,
              updated_at = ?
            WHERE id = ? AND candidate_build_item_id IS NOT NULL
              AND status IN ('pending', 'generating')
              AND quality_status = 'pending_review' AND retired_at IS NULL
            """,
            (
                error_code[:128],
                error_message_safe[:512],
                bool(provider_attempt_consumed),
                now,
                runtime_id,
            ),
        )
        row = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if row is None or (
            updated.rowcount != 1
            and not (
                str(row.get("status") or "") == "failed"
                and str(row.get("quality_status") or "") == "rejected"
                and str(row.get("error_code") or "") == error_code[:128]
                and (
                    provider_attempt_consumed
                    or row.get("provider_attempt_ordinal") is None
                )
            )
        ):
            raise RuntimeError("candidate generation rejection conflict")
        return row

    def reclassify_candidate_provider_billing_failure(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        expected_upstream_job_id: str,
        now: int,
    ) -> DatabaseRow:
        """Exclude a proven pre-generation billing rejection from the limit."""

        row = self.get_runtime_classroom(
            conn,
            runtime_id=runtime_id,
            for_update=True,
        )
        if not (
            row is not None
            and row.get("candidate_build_item_id") is not None
            and str(row.get("status") or "") == "failed"
            and str(row.get("quality_status") or "") == "rejected"
            and str(row.get("error_code") or "")
            == "openmaic_formal_generation_failed"
            and str(row.get("upstream_job_id") or "")
            == expected_upstream_job_id
            and row.get("retired_at") is None
        ):
            raise ValueError("candidate billing reclassification authority is invalid")
        conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET error_code = 'openmaic_formal_provider_billing_blocked',
              error_message_safe =
                '正式课堂生成 Provider 在生成前拒绝了请求，未占内容尝试',
              provider_attempt_ordinal = NULL, updated_at = ?
            WHERE id = ? AND upstream_job_id = ?
            """,
            (now, runtime_id, expected_upstream_job_id),
        )
        build_item_id = str(row["candidate_build_item_id"])
        remaining = conn.execute(
            """
            SELECT id, provider_attempt_ordinal
            FROM learning_openmaic_runtime_classrooms
            WHERE candidate_build_item_id = ?
              AND provider_attempt_ordinal IS NOT NULL
            ORDER BY attempt_ordinal ASC, id ASC
            FOR UPDATE
            """,
            (build_item_id,),
        ).fetchall()
        for ordinal, attempt in enumerate(remaining, start=1):
            if int(attempt["provider_attempt_ordinal"]) == ordinal:
                continue
            conn.execute(
                """
                UPDATE learning_openmaic_runtime_classrooms
                SET provider_attempt_ordinal = ?, updated_at = ?
                WHERE id = ?
                """,
                (ordinal, now, attempt["id"]),
            )
        reclassified = self.get_runtime_classroom(
            conn,
            runtime_id=runtime_id,
            for_update=True,
        )
        if (
            reclassified is None
            or reclassified.get("provider_attempt_ordinal") is not None
            or str(reclassified.get("error_code") or "")
            != "openmaic_formal_provider_billing_blocked"
        ):
            raise RuntimeError("candidate billing reclassification did not persist")
        return reclassified

    def create_retry_runtime_classroom(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        request_id: str,
        retry_of_runtime_id: str,
        retry_reason: str,
        expected_previous_job_id: str,
        attempt_ordinal: int,
        source_runtime: Mapping[str, Any],
        feature_manifest: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_openmaic_runtime_classrooms(
              id, request_id, attempt_ordinal, retry_of_runtime_id,
              retry_reason, expected_previous_job_id,
              course_id, course_version, package_id, package_version,
              status, quality_status, feature_manifest_json,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              'pending', 'pending_review', ?, ?, ?)
            """,
            (
                runtime_id,
                request_id,
                attempt_ordinal,
                retry_of_runtime_id,
                retry_reason,
                expected_previous_job_id,
                source_runtime["course_id"],
                source_runtime["course_version"],
                source_runtime["package_id"],
                int(source_runtime["package_version"]),
                self.encode_json(feature_manifest),
                now,
                now,
            ),
        )
        return self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )

    def retire_runtime_for_retry(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        source_attempt_ordinal: int,
        now: int,
    ) -> bool:
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET retired_at = ?
            WHERE id = ? AND attempt_ordinal = ? AND status = 'failed'
              AND retired_at IS NULL
            """,
            (now, runtime_id, source_attempt_ordinal),
        )
        return updated.rowcount == 1

    def mark_generating(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        upstream_job_id: str,
        now: int,
    ) -> bool:
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET upstream_job_id = ?, status = 'generating',
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'pending' AND upstream_job_id IS NULL
              AND retired_at IS NULL
            """,
            (upstream_job_id, now, runtime_id),
        )
        return updated.rowcount == 1

    def resume_formal_candidate_after_authoritative_completion(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        expected_upstream_job_id: str,
        expected_request_id: str,
        expected_feature_manifest_json: str,
        now: int,
    ) -> bool:
        """Reopen a transport quarantine only for the identical completed job.

        The caller must verify the upstream request, input hash, contract, and
        succeeded result. This CAS changes no dispatch or published receipt;
        the ordinary formal completion validator remains the release authority.
        """
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'generating', quality_status = 'pending_review',
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND upstream_job_id = ? AND request_id = ?
              AND feature_manifest_json = ?
              AND candidate_build_item_id IS NOT NULL
              AND status = 'failed' AND quality_status = 'quarantined'
              AND error_code = 'openmaic_formal_generation_ambiguous'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL
            """,
            (now, runtime_id, expected_upstream_job_id, expected_request_id,
             expected_feature_manifest_json),
        )
        return updated.rowcount == 1

    def resume_formal_candidate_after_validator_fix(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        expected_upstream_job_id: str,
        expected_error_code: str,
        now: int,
    ) -> bool:
        """Re-run validation for the same completed Provider artifact.

        This transition cannot create or attach another upstream job. It only
        reopens a locally rejected formal row when its immutable job identity
        and exact validator error still match the repair request.
        """

        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'generating', quality_status = 'pending_review',
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND upstream_job_id = ?
              AND candidate_build_item_id IS NOT NULL
              AND status = 'failed' AND quality_status = 'rejected'
              AND error_code = ? AND upstream_classroom_id IS NULL
              AND retired_at IS NULL
            """,
            (
                now,
                runtime_id,
                expected_upstream_job_id,
                expected_error_code,
            ),
        )
        return updated.rowcount == 1

    def mark_ready(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        upstream_classroom_id: str,
        feature_manifest: Mapping[str, Any],
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET upstream_classroom_id = ?, status = 'ready',
              feature_manifest_json = ?, error_code = NULL,
              error_message_safe = NULL, ready_at = ?, updated_at = ?
            WHERE id = ? AND status IN ('pending', 'generating')
            """,
            (
                upstream_classroom_id,
                self.encode_json(feature_manifest),
                now,
                now,
                runtime_id,
            ),
        )

    def mark_failed(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              updated_at = ?
            WHERE id = ? AND status <> 'ready'
            """,
            (error_code[:128], error_message_safe[:512], now, runtime_id),
        )

    def get_formal_citation_recovery_by_runtime(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_openmaic_formal_citation_recoveries
            WHERE runtime_classroom_id = ? LIMIT 1
            """
            + lock,
            (runtime_id,),
        ).fetchone()

    def reserve_formal_citation_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        recovery_request_id: str,
        runtime_id: str,
        expected_upstream_job_id: str,
        formal_input_sha256: str,
        now: int,
    ) -> DatabaseRow:
        """Reserve the exact second attempt and atomically block attempt three."""

        existing = self.get_formal_citation_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if existing is not None:
            if (
                str(existing.get("id") or "") != recovery_id
                or str(existing.get("recovery_request_id") or "")
                != recovery_request_id
                or str(existing.get("source_upstream_job_id") or "")
                != expected_upstream_job_id
                or str(existing.get("source_formal_input_sha256") or "")
                != formal_input_sha256
            ):
                raise ValueError("formal citation recovery replay conflict")
            return existing

        runtime = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if runtime is None or runtime.get("candidate_build_item_id") is None:
            raise ValueError("formal citation recovery runtime was not found")
        build_item_id = str(runtime["candidate_build_item_id"])
        attempts = list(
            conn.execute(
                """
                SELECT id, attempt_ordinal, provider_attempt_ordinal, status,
                  quality_status, error_code, upstream_job_id, retired_at
                FROM learning_openmaic_runtime_classrooms
                WHERE candidate_build_item_id = ?
                ORDER BY attempt_ordinal, id
                FOR UPDATE
                """,
                (build_item_id,),
            ).fetchall()
        )
        exact_two_attempts = bool(
            len(attempts) == 2
            and str(attempts[1].get("id") or "") == runtime_id
            and [int(row.get("attempt_ordinal") or 0) for row in attempts]
            == [1, 2]
            and [
                int(row.get("provider_attempt_ordinal") or 0)
                for row in attempts
            ]
            == [1, 2]
            and all(row.get("retired_at") is None for row in attempts)
            and all(
                str(row.get("status") or "") == "failed"
                and str(row.get("quality_status") or "") == "rejected"
                and str(row.get("error_code") or "")
                == "openmaic_formal_generation_failed"
                and bool(str(row.get("upstream_job_id") or ""))
                for row in attempts
            )
        )
        if not exact_two_attempts or not (
            str(runtime.get("status") or "") == "failed"
            and str(runtime.get("quality_status") or "") == "rejected"
            and str(runtime.get("error_code") or "")
            == "openmaic_formal_generation_failed"
            and int(runtime.get("attempt_ordinal") or 0) == 2
            and int(runtime.get("provider_attempt_ordinal") or 0) == 2
            and str(runtime.get("upstream_job_id") or "")
            == expected_upstream_job_id
            and runtime.get("retired_at") is None
        ):
            raise ValueError("formal citation recovery source is not exact attempt two")
        conn.execute(
            """
            INSERT INTO learning_openmaic_formal_citation_recoveries(
              id, recovery_request_id, runtime_classroom_id, build_item_id,
              status, recovery_policy_version, source_runtime_status,
              source_quality_status,
              source_runtime_error_code, source_runtime_error_message_safe,
              source_attempt_ordinal, source_provider_attempt_ordinal,
              source_runtime_request_id, source_upstream_job_id,
              source_formal_input_sha256, source_job_status, source_job_error,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'reserving',
              'mira-formal-citation-recovery.v1', 'failed', 'rejected',
              'openmaic_formal_generation_failed', ?, 2, 2, ?, ?, ?, 'failed',
              'FORMAL_PROFESSIONAL_RESEARCH_CITATION_MISSING', ?, ?)
            """,
            (
                recovery_id,
                recovery_request_id,
                runtime_id,
                build_item_id,
                runtime.get("error_message_safe"),
                runtime["request_id"],
                expected_upstream_job_id,
                formal_input_sha256,
                now,
                now,
            ),
        )
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'recovering', quality_status = 'pending_review',
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND attempt_ordinal = 2
              AND provider_attempt_ordinal = 2
              AND status = 'failed' AND quality_status = 'rejected'
              AND error_code = 'openmaic_formal_generation_failed'
              AND upstream_job_id = ? AND retired_at IS NULL
            """,
            (now, runtime_id, expected_upstream_job_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("formal citation recovery runtime reservation lost")
        reserved = self.get_formal_citation_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if reserved is None:
            raise RuntimeError("formal citation recovery reservation disappeared")
        return reserved

    def attach_formal_citation_recovery_receipt(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        upstream_recovery_id: str,
        status: str,
        source_job_completed_at: str,
        source_job_snapshot_sha256: str,
        calls: Mapping[str, int],
        repair: Mapping[str, Any] | None,
        result: Mapping[str, Any] | None,
        receipt: Mapping[str, Any],
        receipt_sha256: str,
        error: Mapping[str, str] | None,
        now: int,
    ) -> DatabaseRow:
        mapped_status = "running" if status in {"queued", "running"} else status
        if mapped_status not in {"running", "succeeded", "failed"}:
            raise ValueError("formal citation recovery status is invalid")
        current = self.get_formal_citation_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if current is None:
            raise ValueError("formal citation recovery was not reserved")
        if str(current.get("status") or "") in {"succeeded", "failed"}:
            if (
                str(current.get("status") or "") != mapped_status
                or str(current.get("upstream_recovery_id") or "")
                != upstream_recovery_id
                or str(current.get("response_receipt_sha256") or "")
                != receipt_sha256
            ):
                raise ValueError("formal citation recovery terminal replay conflict")
            return current
        repair_payload = dict(repair) if isinstance(repair, Mapping) else None
        result_payload = dict(result) if isinstance(result, Mapping) else None
        formal_audio = (
            result_payload.get("formalAudio")
            if isinstance(result_payload, Mapping)
            else None
        )
        professional = (
            result_payload.get("professionalCreation")
            if isinstance(result_payload, Mapping)
            else None
        )
        research = (
            result_payload.get("research")
            if isinstance(result_payload, Mapping)
            else None
        )
        terminal_at = now if mapped_status in {"succeeded", "failed"} else None
        updated = conn.execute(
            """
            UPDATE learning_openmaic_formal_citation_recoveries
            SET status = ?, upstream_recovery_id = ?,
              response_schema_version = ?, response_kind = ?,
              source_job_completed_at = ?, source_job_snapshot_sha256 = ?,
              llm_call_count = ?, web_search_call_count = ?,
              fetch_url_call_count = ?, image_generation_call_count = ?,
              video_generation_call_count = ?, repair_policy_version = ?,
              repair_before_scenes_sha256 = ?,
              repair_after_scenes_sha256 = ?, repair_sha256 = ?,
              repair_json = ?, upstream_classroom_id = ?,
              result_scene_count = ?, result_speech_action_count = ?,
              formal_audio_receipt_sha256 = ?,
              professional_creation_receipt_sha256 = ?,
              research_receipt_sha256 = ?, result_json = ?,
              response_receipt_json = ?, response_receipt_sha256 = ?,
              error_code = ?, error_message_safe = ?, updated_at = ?,
              terminal_at = ?
            WHERE id = ? AND status IN ('reserving', 'running')
              AND (upstream_recovery_id IS NULL OR upstream_recovery_id = ?)
            """,
            (
                mapped_status,
                upstream_recovery_id,
                receipt.get("schemaVersion"),
                receipt.get("kind"),
                source_job_completed_at,
                source_job_snapshot_sha256,
                int(calls["llm"]),
                int(calls["webSearch"]),
                int(calls["fetchUrl"]),
                int(calls["imageGeneration"]),
                int(calls["videoGeneration"]),
                repair_payload.get("policyVersion") if repair_payload else None,
                repair_payload.get("beforeScenesSha256") if repair_payload else None,
                repair_payload.get("afterScenesSha256") if repair_payload else None,
                repair_payload.get("repairSha256") if repair_payload else None,
                self.encode_json(repair_payload) if repair_payload else None,
                result_payload.get("classroomId") if result_payload else None,
                result_payload.get("scenesCount") if result_payload else None,
                result_payload.get("speechActionCount") if result_payload else None,
                formal_audio.get("receiptSha256")
                if isinstance(formal_audio, Mapping)
                else None,
                professional.get("receiptSha256")
                if isinstance(professional, Mapping)
                else None,
                research.get("receiptSha256")
                if isinstance(research, Mapping)
                else None,
                self.encode_json(result_payload) if result_payload else None,
                self.encode_json(receipt),
                receipt_sha256,
                error.get("code")[:128] if error else None,
                error.get("message")[:512] if error else None,
                now,
                terminal_at,
                current["id"],
                upstream_recovery_id,
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("formal citation recovery receipt attach conflict")
        attached = self.get_formal_citation_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if attached is None:
            raise RuntimeError("formal citation recovery disappeared")
        return attached

    def resume_formal_candidate_from_citation_recovery(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        expected_recovery_id: str,
        expected_receipt_sha256: str,
        now: int,
    ) -> DatabaseRow:
        recovery = self.get_formal_citation_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        runtime = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if not (
            recovery is not None
            and runtime is not None
            and str(recovery.get("status") or "") == "succeeded"
            and str(recovery.get("upstream_recovery_id") or "")
            == expected_recovery_id
            and str(recovery.get("response_receipt_sha256") or "")
            == expected_receipt_sha256
            and str(recovery.get("source_upstream_job_id") or "")
            == str(runtime.get("upstream_job_id") or "")
            and str(recovery.get("source_runtime_request_id") or "")
            == str(runtime.get("request_id") or "")
            and str(recovery.get("build_item_id") or "")
            == str(runtime.get("candidate_build_item_id") or "")
            and int(runtime.get("attempt_ordinal") or 0) == 2
            and int(runtime.get("provider_attempt_ordinal") or 0) == 2
            and runtime.get("retired_at") is None
        ):
            raise ValueError("formal citation recovery resume authority is invalid")
        if str(runtime.get("status") or "") in {"generating", "ready"}:
            return runtime
        updated = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'generating', quality_status = 'pending_review',
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'recovering'
              AND quality_status = 'pending_review'
              AND attempt_ordinal = 2 AND provider_attempt_ordinal = 2
              AND upstream_job_id = ? AND retired_at IS NULL
            """,
            (now, runtime_id, recovery["source_upstream_job_id"]),
        )
        if updated.rowcount != 1:
            raise RuntimeError("formal citation recovery resume CAS conflict")
        resumed = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if resumed is None or str(resumed.get("status") or "") != "generating":
            raise RuntimeError("formal citation recovery did not resume generation")
        return resumed

    def quarantine_failed_formal_citation_recovery(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        now: int,
    ) -> DatabaseRow:
        recovery = self.get_formal_citation_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if recovery is None or str(recovery.get("status") or "") != "failed":
            raise ValueError("formal citation recovery has no failed receipt")
        conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', quality_status = 'quarantined',
              error_code = 'openmaic_formal_citation_recovery_failed',
              error_message_safe = '正式课堂引用恢复失败，已隔离且不会创建第三次尝试',
              updated_at = ?
            WHERE id = ? AND status = 'recovering'
              AND quality_status = 'pending_review'
            """,
            (now, runtime_id),
        )
        runtime = self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )
        if runtime is None or not (
            str(runtime.get("status") or "") == "failed"
            and str(runtime.get("quality_status") or "") == "quarantined"
        ):
            raise RuntimeError("failed formal citation recovery was not quarantined")
        return runtime

    def get_deterministic_recovery_by_request(
        self,
        conn: DatabaseConnection,
        *,
        recovery_request_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """SELECT * FROM learning_openmaic_deterministic_recoveries
            WHERE recovery_request_id = ? LIMIT 1""" + lock,
            (recovery_request_id,),
        ).fetchone()

    def get_deterministic_recovery_by_runtime(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """SELECT * FROM learning_openmaic_deterministic_recoveries
            WHERE runtime_classroom_id = ? LIMIT 1""" + lock,
            (runtime_id,),
        ).fetchone()

    def get_tts_credential_recovery_by_request(
        self,
        conn: DatabaseConnection,
        *,
        recovery_request_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """SELECT * FROM learning_openmaic_tts_credential_recoveries
            WHERE recovery_request_id = ? LIMIT 1""" + lock,
            (recovery_request_id,),
        ).fetchone()

    def get_tts_credential_recovery_by_runtime(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """SELECT * FROM learning_openmaic_tts_credential_recoveries
            WHERE runtime_classroom_id = ? LIMIT 1""" + lock,
            (runtime_id,),
        ).fetchone()

    def get_tts_credential_recovery_by_parent(
        self,
        conn: DatabaseConnection,
        *,
        parent_recovery_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """SELECT * FROM learning_openmaic_tts_credential_recoveries
            WHERE parent_recovery_id = ? LIMIT 1""" + lock,
            (parent_recovery_id,),
        ).fetchone()

    def reserve_tts_credential_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        recovery_request_id: str,
        runtime_id: str,
        parent_recovery_id: str,
        expected_source_job_id: str,
        parent_db_snapshot_sha256: str,
        parent_receipt_sha256: str,
        parent_runtime_snapshot_sha256: str,
        expected_upstream_child_id: str,
        expected_upstream_classroom_id: str,
        mode: str,
        kind: str,
        tts_provider_id: str,
        tts_model_id: str,
        tts_voice_id: str,
        now: int,
    ) -> DatabaseRow:
        """Claim attempt three and append the unique child without parent writes."""

        claimed = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'recovering', updated_at = ?
            WHERE id = ? AND attempt_ordinal = 3 AND status = 'failed'
              AND error_code = 'openmaic_generation_failed'
              AND upstream_job_id = ? AND upstream_classroom_id IS NULL
              AND retired_at IS NULL""",
            (now, runtime_id, expected_source_job_id),
        )
        if claimed.rowcount != 1:
            raise RuntimeError("openmaic TTS credential runtime claim conflict")
        inserted = conn.execute(
            """INSERT INTO learning_openmaic_tts_credential_recoveries(
              id, recovery_request_id, runtime_classroom_id,
              parent_recovery_id, mode, kind, status,
              parent_status, parent_dispatch_count, parent_error_code,
              parent_error_message_safe, parent_terminal_at,
              parent_expected_upstream_recovery_id,
              parent_upstream_recovery_id,
              parent_db_snapshot_sha256, parent_receipt_sha256,
              parent_runtime_snapshot_sha256,
              source_upstream_job_id, source_job_snapshot_sha256,
              source_generation_contract_sha256,
              parent_policy_id, parent_policy_version,
              parent_canonical_spec_sha256, parent_code_patch_sha256,
              parent_tts_expected_call_count,
              parent_tts_attempted_call_count,
              parent_tts_completed_call_count,
              expected_upstream_child_id, expected_upstream_classroom_id,
              llm_call_count, web_search_call_count,
              image_generation_call_count, video_generation_call_count,
              tts_expected_call_count, tts_attempted_call_count,
              tts_completed_call_count, tts_provider_id, tts_model_id,
              tts_voice_id, tts_fallback_used, created_at, updated_at
            )
            SELECT ?, ?, ?, parent.id, ?, ?, 'recovering',
              parent.status, parent.dispatch_count, parent.error_code,
              parent.error_message_safe, parent.terminal_at,
              parent.expected_upstream_recovery_id,
              parent.upstream_recovery_id, ?, ?, ?,
              parent.source_upstream_job_id,
              parent.source_job_snapshot_sha256,
              parent.source_generation_contract_sha256,
              parent.policy_id, parent.policy_version,
              parent.canonical_spec_sha256, parent.code_patch_sha256,
              parent.tts_expected_call_count,
              parent.tts_attempted_call_count,
              parent.tts_completed_call_count,
              ?, ?, 0, 0, 0, 0, 10, 0, 0, ?, ?, ?, FALSE, ?, ?
            FROM learning_openmaic_deterministic_recoveries AS parent
            WHERE parent.id = ? AND parent.runtime_classroom_id = ?
              AND parent.status = 'failed' AND parent.dispatch_count = 2
              AND parent.error_code = 'openmaic_deterministic_recovery_failed'
              AND parent.error_message_safe IS NOT NULL
              AND parent.terminal_at IS NOT NULL
              AND parent.expected_upstream_recovery_id =
                parent.upstream_recovery_id
              AND parent.upstream_recovery_id IS NOT NULL
              AND parent.source_upstream_job_id = ?
              AND parent.source_job_status = 'failed'
              AND parent.source_job_error = 'structured_output_exhausted'
              AND parent.source_scenes_generated = 4
              AND parent.source_total_scenes = 10
              AND parent.policy_id IS NOT NULL
              AND parent.policy_version IS NOT NULL
              AND parent.canonical_spec_sha256 IS NOT NULL
              AND parent.code_patch_sha256 IS NOT NULL
              AND parent.llm_call_count = 0
              AND parent.web_search_call_count = 0
              AND parent.image_generation_call_count = 0
              AND parent.video_generation_call_count = 0
              AND parent.tts_expected_call_count = 10
              AND parent.tts_attempted_call_count = 1
              AND parent.tts_completed_call_count = 0
              AND parent.tts_provider_id = 'qwen-tts'
              AND parent.tts_model_id = 'qwen3-tts-flash'
              AND parent.tts_voice_id = 'Serena'
              AND parent.tts_fallback_used = FALSE
              AND parent.tts_verified_asset_count IS NULL
              AND parent.upstream_classroom_id IS NULL
              AND parent.scene_count IS NULL
              AND parent.content_sha256 IS NULL
              AND parent.final_artifact_sha256 IS NULL
              AND parent.artifact_created_at IS NULL
              AND parent.static_contract_verified = FALSE
              AND parent.conversation_probe_verified = FALSE
              AND parent.verified_at IS NULL
              AND parent.receipt_json IS NOT NULL""",
            (
                recovery_id,
                recovery_request_id,
                runtime_id,
                mode,
                kind,
                parent_db_snapshot_sha256,
                parent_receipt_sha256,
                parent_runtime_snapshot_sha256,
                expected_upstream_child_id,
                expected_upstream_classroom_id,
                tts_provider_id,
                tts_model_id,
                tts_voice_id,
                now,
                now,
                parent_recovery_id,
                runtime_id,
                expected_source_job_id,
            ),
        )
        if inserted.rowcount != 1:
            raise RuntimeError("openmaic TTS credential child claim conflict")
        row = self.get_tts_credential_recovery_by_request(
            conn,
            recovery_request_id=recovery_request_id,
            for_update=True,
        )
        if row is None:
            raise RuntimeError("openmaic TTS credential child missing")
        return row

    def reserve_deterministic_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        recovery_request_id: str,
        runtime: Mapping[str, Any],
        expected_source_job_id: str,
        expected_upstream_recovery_id: str,
        source_job_snapshot: Mapping[str, Any],
        source_generation_contract_sha256: str,
        mode: str,
        kind: str,
        source_scenes_generated: int,
        source_total_scenes: int,
        tts_provider_id: str,
        tts_model_id: str,
        tts_voice_id: str,
        now: int,
    ) -> DatabaseRow:
        """Atomically claim the failed attempt-three row and append its audit row.

        The runtime's upstream job id and source error columns are deliberately
        left untouched.  A process interruption after commit is observed only;
        replaying the request never dispatches the external recovery again.
        """

        claimed = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'recovering', updated_at = ?
            WHERE id = ? AND attempt_ordinal = 3 AND status = 'failed'
              AND error_code = 'openmaic_generation_failed'
              AND upstream_job_id = ? AND upstream_classroom_id IS NULL
              AND retired_at IS NULL""",
            (now, runtime["id"], expected_source_job_id),
        )
        if claimed.rowcount != 1:
            raise RuntimeError("openmaic deterministic recovery claim conflict")
        conn.execute(
            """INSERT INTO learning_openmaic_deterministic_recoveries(
              id, recovery_request_id, runtime_classroom_id, mode, kind, status,
              source_runtime_status, source_runtime_error_code,
              source_runtime_error_message_safe, source_upstream_job_id,
              source_job_status, source_job_error, source_scenes_generated,
              source_total_scenes, source_completed_at,
              source_job_snapshot_sha256, source_generation_contract_sha256,
              expected_upstream_recovery_id,
              llm_call_count, web_search_call_count,
              image_generation_call_count, video_generation_call_count,
              tts_expected_call_count, tts_attempted_call_count,
              tts_completed_call_count,
              tts_provider_id, tts_model_id, tts_voice_id,
              tts_fallback_used, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'recovering', ?, ?, ?, ?,
              'failed', 'structured_output_exhausted', ?, ?, ?, ?, ?, ?,
              0, 0, 0, 0, 10, 0, 0, ?, ?, ?, FALSE, ?, ?)""",
            (
                recovery_id,
                recovery_request_id,
                runtime["id"],
                mode,
                kind,
                runtime["status"],
                runtime["error_code"],
                runtime.get("error_message_safe"),
                expected_source_job_id,
                source_scenes_generated,
                source_total_scenes,
                source_job_snapshot.get("completedAt"),
                source_job_snapshot["jobSnapshotSha256"],
                source_generation_contract_sha256,
                expected_upstream_recovery_id,
                tts_provider_id,
                tts_model_id,
                tts_voice_id,
                now,
                now,
            ),
        )
        row = self.get_deterministic_recovery_by_request(
            conn,
            recovery_request_id=recovery_request_id,
            for_update=True,
        )
        if row is None:
            raise RuntimeError("openmaic deterministic recovery reservation missing")
        return row

    def reserve_deterministic_recovery_redispatch(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        recovery_request_id: str,
        source_upstream_job_id: str,
        expected_upstream_recovery_id: str,
        source_job_snapshot_sha256: str,
        source_generation_contract_sha256: str,
        now: int,
    ) -> DatabaseRow:
        """CAS the sole pre-provider 403 into its second and final dispatch."""

        runtime = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'recovering', updated_at = ?
            WHERE id = ? AND attempt_ordinal = 3 AND status = 'failed'
              AND error_code = 'openmaic_generation_failed'
              AND upstream_job_id = ? AND upstream_classroom_id IS NULL
              AND retired_at IS NULL""",
            (now, runtime_id, source_upstream_job_id),
        )
        if runtime.rowcount != 1:
            raise RuntimeError("openmaic recovery redispatch runtime CAS conflict")

        recovery = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET dispatch_count = 2,
              first_dispatch_error_code = error_code,
              first_dispatch_error_message_safe = error_message_safe,
              first_dispatch_rejected_at = terminal_at,
              status = 'recovering', error_code = NULL,
              error_message_safe = NULL, terminal_at = NULL, updated_at = ?
            WHERE id = ? AND runtime_classroom_id = ?
              AND recovery_request_id = ?
              AND mode = 'deterministic_no_llm'
              AND kind = 'mira_sample_deterministic_no_llm_v1'
              AND status = 'failed' AND dispatch_count = 1
              AND first_dispatch_error_code IS NULL
              AND first_dispatch_error_message_safe IS NULL
              AND first_dispatch_rejected_at IS NULL
              AND error_code = 'openmaic_recovery_upstream_rejected'
              AND error_message_safe IS NOT NULL AND terminal_at IS NOT NULL
              AND source_runtime_status = 'failed'
              AND source_runtime_error_code = 'openmaic_generation_failed'
              AND source_upstream_job_id = ?
              AND source_job_status = 'failed'
              AND source_job_error = 'structured_output_exhausted'
              AND source_scenes_generated = 4 AND source_total_scenes = 10
              AND source_job_snapshot_sha256 = ?
              AND source_generation_contract_sha256 = ?
              AND expected_upstream_recovery_id = ?
              AND upstream_recovery_id IS NULL
              AND policy_id IS NULL AND policy_version IS NULL
              AND canonical_spec_sha256 IS NULL AND code_patch_sha256 IS NULL
              AND llm_call_count = 0 AND web_search_call_count = 0
              AND image_generation_call_count = 0
              AND video_generation_call_count = 0
              AND tts_expected_call_count = 10
              AND tts_attempted_call_count = 0
              AND tts_completed_call_count = 0
              AND tts_provider_id = 'qwen-tts'
              AND tts_model_id = 'qwen3-tts-flash'
              AND tts_voice_id = 'Serena' AND tts_fallback_used = FALSE
              AND tts_verified_asset_count IS NULL
              AND upstream_classroom_id IS NULL AND scene_count IS NULL
              AND content_sha256 IS NULL AND final_artifact_sha256 IS NULL
              AND artifact_created_at IS NULL
              AND static_contract_verified = FALSE
              AND conversation_probe_verified = FALSE
              AND verified_at IS NULL AND receipt_json IS NULL""",
            (
                now,
                recovery_id,
                runtime_id,
                recovery_request_id,
                source_upstream_job_id,
                source_job_snapshot_sha256,
                source_generation_contract_sha256,
                expected_upstream_recovery_id,
            ),
        )
        if recovery.rowcount != 1:
            raise RuntimeError("openmaic recovery redispatch audit CAS conflict")
        row = self.get_deterministic_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if row is None:
            raise RuntimeError("openmaic recovery redispatch row missing")
        return row

    def attach_deterministic_recovery_receipt(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        upstream_recovery_id: str,
        source: Mapping[str, Any],
        policy: Mapping[str, Any],
        calls: Mapping[str, Any],
        receipt: Mapping[str, Any],
        now: int,
    ) -> bool:
        tts = calls["tts"]
        updated = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET upstream_recovery_id = ?, source_completed_at = ?,
              policy_id = ?, policy_version = ?,
              canonical_spec_sha256 = ?, code_patch_sha256 = ?,
              llm_call_count = ?, web_search_call_count = ?,
              image_generation_call_count = ?, video_generation_call_count = ?,
              tts_expected_call_count = ?, tts_attempted_call_count = ?,
              tts_completed_call_count = ?,
              receipt_json = ?, updated_at = ?
            WHERE id = ? AND status = 'recovering'
              AND upstream_recovery_id IS NULL
              AND expected_upstream_recovery_id = ?
              AND source_upstream_job_id = ?
              AND source_job_snapshot_sha256 = ?""",
            (
                upstream_recovery_id,
                source.get("completedAt"),
                policy["marker"],
                policy["version"],
                policy["canonicalSpecSha256"],
                policy["patchSha256"],
                int(calls["llm"]),
                int(calls["webSearch"]),
                int(calls["imageGeneration"]),
                int(calls["videoGeneration"]),
                int(tts["expected"]),
                int(tts["attempted"]),
                int(tts["completed"]),
                self.encode_json(receipt),
                now,
                recovery_id,
                upstream_recovery_id,
                source["jobId"],
                source["jobSnapshotSha256"],
            ),
        )
        return updated.rowcount == 1

    def attach_tts_credential_recovery_receipt(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        upstream_child_id: str,
        parent_runtime_snapshot_sha256: str,
        policy: Mapping[str, Any],
        calls: Mapping[str, Any],
        receipt: Mapping[str, Any],
        now: int,
    ) -> bool:
        tts = calls["tts"]
        updated = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET upstream_child_id = ?, policy_version = ?,
              classroom_policy_version = ?, canonical_spec_sha256 = ?,
              parent_patch_sha256 = ?, code_patch_sha256 = ?,
              llm_call_count = ?, web_search_call_count = ?,
              image_generation_call_count = ?, video_generation_call_count = ?,
              tts_expected_call_count = ?, tts_attempted_call_count = ?,
              tts_completed_call_count = ?, receipt_json = ?, updated_at = ?
            WHERE id = ? AND status = 'recovering'
              AND upstream_child_id IS NULL
              AND expected_upstream_child_id = ?
              AND parent_runtime_snapshot_sha256 = ?""",
            (
                upstream_child_id,
                policy["version"],
                policy["classroomPolicyVersion"],
                policy["canonicalSpecSha256"],
                policy["parentPatchSha256"],
                policy["patchSha256"],
                int(calls["llm"]),
                int(calls["webSearch"]),
                int(calls["imageGeneration"]),
                int(calls["videoGeneration"]),
                int(tts["expected"]),
                int(tts["attempted"]),
                int(tts["completed"]),
                self.encode_json(receipt),
                now,
                recovery_id,
                upstream_child_id,
                parent_runtime_snapshot_sha256,
            ),
        )
        return updated.rowcount == 1

    def update_tts_credential_recovery_observation(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        receipt: Mapping[str, Any],
        tts_attempted_count: int,
        tts_completed_count: int,
        progressed: bool,
        now: int,
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET receipt_json = ?, tts_attempted_call_count = ?,
              tts_completed_call_count = ?,
              updated_at = CASE WHEN ? THEN ? ELSE updated_at END
            WHERE id = ? AND status = 'recovering'
              AND upstream_child_id IS NOT NULL
              AND tts_attempted_call_count <= ?
              AND tts_completed_call_count <= ?""",
            (
                self.encode_json(receipt),
                tts_attempted_count,
                tts_completed_count,
                bool(progressed),
                now,
                recovery_id,
                tts_attempted_count,
                tts_completed_count,
            ),
        )
        return updated.rowcount == 1

    def claim_tts_credential_recovery_validation(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        receipt: Mapping[str, Any],
        now: int,
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET status = 'validating',
              tts_attempted_call_count = 10,
              tts_completed_call_count = 10,
              static_contract_verified = FALSE,
              conversation_probe_verified = FALSE,
              receipt_json = ?, updated_at = ?
            WHERE id = ? AND status = 'recovering'
              AND upstream_child_id = expected_upstream_child_id
              AND policy_version IS NOT NULL
              AND classroom_policy_version IS NOT NULL
              AND canonical_spec_sha256 IS NOT NULL
              AND parent_patch_sha256 IS NOT NULL
              AND code_patch_sha256 IS NOT NULL
              AND receipt_json IS NOT NULL
              AND llm_call_count = 0 AND web_search_call_count = 0
              AND image_generation_call_count = 0
              AND video_generation_call_count = 0
              AND tts_expected_call_count = 10
              AND tts_attempted_call_count <= 10
              AND tts_completed_call_count <= 10""",
            (
                self.encode_json(receipt),
                now,
                recovery_id,
            ),
        )
        return updated.rowcount == 1

    def complete_tts_credential_static_validation(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        artifact: Mapping[str, Any],
        receipt: Mapping[str, Any],
        now: int,
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET upstream_classroom_id = ?, scene_count = ?, audio_count = ?,
              content_sha256 = ?, final_artifact_sha256 = ?,
              artifact_created_at = ?, tts_verified_asset_count = 10,
              static_contract_verified = TRUE, receipt_json = ?,
              updated_at = ?
            WHERE id = ? AND status = 'validating'
              AND static_contract_verified = FALSE
              AND upstream_classroom_id IS NULL
              AND upstream_child_id = expected_upstream_child_id
              AND ? = expected_upstream_classroom_id
              AND tts_expected_call_count = 10
              AND tts_attempted_call_count = 10
              AND tts_completed_call_count = 10
              AND conversation_probe_id IS NULL
              AND conversation_probe_verified = FALSE
              AND error_code IS NULL AND terminal_at IS NULL""",
            (
                artifact["classroomId"],
                int(artifact["sceneCount"]),
                int(artifact["audioCount"]),
                artifact["contentSha256"],
                artifact["artifactSha256"],
                receipt.get("completedAt"),
                self.encode_json(receipt),
                now,
                recovery_id,
                artifact["classroomId"],
            ),
        )
        return updated.rowcount == 1

    def claim_tts_credential_recovery_publication(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        conversation_probe_id: str,
        now: int,
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries AS child
            SET status = 'publishing', updated_at = ?
            WHERE child.id = ? AND child.runtime_classroom_id = ?
              AND child.status = 'validating'
              AND child.static_contract_verified = TRUE
              AND child.upstream_child_id = child.expected_upstream_child_id
              AND child.upstream_classroom_id =
                child.expected_upstream_classroom_id
              AND child.policy_version IS NOT NULL
              AND child.classroom_policy_version IS NOT NULL
              AND child.canonical_spec_sha256 IS NOT NULL
              AND child.parent_patch_sha256 IS NOT NULL
              AND child.code_patch_sha256 IS NOT NULL
              AND child.llm_call_count = 0
              AND child.web_search_call_count = 0
              AND child.image_generation_call_count = 0
              AND child.video_generation_call_count = 0
              AND child.scene_count = 10 AND child.audio_count = 10
              AND child.tts_verified_asset_count = 10
              AND child.tts_expected_call_count = 10
              AND child.tts_attempted_call_count = 10
              AND child.tts_completed_call_count = 10
              AND child.content_sha256 IS NOT NULL
              AND child.final_artifact_sha256 IS NOT NULL
              AND child.artifact_created_at IS NOT NULL
              AND child.receipt_json IS NOT NULL
              AND child.conversation_probe_verified = FALSE
              AND child.conversation_probe_id IS NULL
              AND child.verified_at IS NULL
              AND child.error_code IS NULL AND child.terminal_at IS NULL
              AND EXISTS (
                SELECT 1 FROM learning_openmaic_conversation_probes AS probe
                WHERE probe.id = ?
                  AND probe.runtime_classroom_id = child.runtime_classroom_id
                  AND probe.upstream_classroom_id = child.upstream_classroom_id
                  AND probe.candidate_kind = 'tts_credential_recovery'
                  AND probe.deterministic_recovery_id =
                    child.parent_recovery_id
                  AND probe.tts_credential_recovery_id = child.id
                  AND probe.finalized_at IS NOT NULL
              )""",
            (now, recovery_id, runtime_id, conversation_probe_id),
        )
        return updated.rowcount == 1

    def fail_tts_credential_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        source_upstream_job_id: str,
        expected_status: str,
        error_code: str,
        error_message_safe: str,
        receipt: Mapping[str, Any] | None,
        tts_attempted_count: int | None,
        tts_completed_count: int | None,
        now: int,
    ) -> bool:
        encoded_receipt = (
            self.encode_json(receipt) if receipt is not None else None
        )
        if expected_status == "validating":
            child = conn.execute(
                """SELECT status, parent_recovery_id, upstream_classroom_id
                FROM learning_openmaic_tts_credential_recoveries
                WHERE id = ? AND runtime_classroom_id = ?
                LIMIT 1 FOR UPDATE""",
                (recovery_id, runtime_id),
            ).fetchone()
            if child is None or str(child.get("status") or "") != "validating":
                return False
            probe = conn.execute(
                """SELECT id, runtime_classroom_id, upstream_classroom_id,
                  candidate_kind, deterministic_recovery_id,
                  tts_credential_recovery_id, finalized_at
                FROM learning_openmaic_conversation_probes
                WHERE tts_credential_recovery_id = ?
                LIMIT 1 FOR UPDATE""",
                (recovery_id,),
            ).fetchone()
            if probe is not None and (
                probe.get("finalized_at") is not None
                and str(probe.get("runtime_classroom_id") or "") == runtime_id
                and str(probe.get("upstream_classroom_id") or "")
                == str(child.get("upstream_classroom_id") or "")
                and str(probe.get("candidate_kind") or "")
                == "tts_credential_recovery"
                and str(probe.get("deterministic_recovery_id") or "")
                == str(child.get("parent_recovery_id") or "")
                and str(probe.get("tts_credential_recovery_id") or "")
                == recovery_id
            ):
                return False
        failed = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET status = 'failed',
              error_code = CASE
                WHEN (? IS NOT NULL AND ? < tts_attempted_call_count)
                  OR (? IS NOT NULL AND ? < tts_completed_call_count)
                THEN 'openmaic_tts_credential_counter_regression'
                ELSE ?
              END,
              error_message_safe = CASE
                WHEN (? IS NOT NULL AND ? < tts_attempted_call_count)
                  OR (? IS NOT NULL AND ? < tts_completed_call_count)
                THEN 'TTS 凭证恢复终态计数与已持久化进度不一致'
                ELSE ?
              END,
              receipt_json = CASE
                WHEN ? IS NOT NULL
                  AND (? IS NULL OR ? >= tts_attempted_call_count)
                  AND (? IS NULL OR ? >= tts_completed_call_count)
                THEN ? ELSE receipt_json
              END,
              tts_attempted_call_count = GREATEST(
                tts_attempted_call_count,
                COALESCE(?, tts_attempted_call_count)
              ),
              tts_completed_call_count = GREATEST(
                tts_completed_call_count,
                COALESCE(?, tts_completed_call_count)
              ),
              conversation_probe_verified = FALSE, verified_at = NULL,
              updated_at = ?, terminal_at = ?
            WHERE id = ? AND runtime_classroom_id = ?
              AND status = ?""",
            (
                tts_attempted_count,
                tts_attempted_count,
                tts_completed_count,
                tts_completed_count,
                error_code[:128],
                tts_attempted_count,
                tts_attempted_count,
                tts_completed_count,
                tts_completed_count,
                error_message_safe[:512],
                encoded_receipt,
                tts_attempted_count,
                tts_attempted_count,
                tts_completed_count,
                tts_completed_count,
                encoded_receipt,
                tts_attempted_count,
                tts_completed_count,
                now,
                now,
                recovery_id,
                runtime_id,
                expected_status,
            ),
        )
        if failed.rowcount != 1:
            return False
        restored = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', updated_at = ?
            WHERE id = ? AND status = 'recovering' AND attempt_ordinal = 3
              AND upstream_job_id = ?
              AND error_code = 'openmaic_generation_failed'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL""",
            (now, runtime_id, source_upstream_job_id),
        )
        if restored.rowcount != 1:
            raise RuntimeError("openmaic TTS credential failure CAS conflict")
        return True

    def fail_stale_tts_credential_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        source_upstream_job_id: str,
        expected_status: str,
        expected_updated_at: int,
        expected_tts_attempted_count: int,
        expected_tts_completed_count: int,
        stale_cutoff: int,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> bool:
        child = conn.execute(
            """SELECT status, updated_at, tts_attempted_call_count,
              tts_completed_call_count
            FROM learning_openmaic_tts_credential_recoveries
            WHERE id = ? AND runtime_classroom_id = ?
            LIMIT 1 FOR UPDATE""",
            (recovery_id, runtime_id),
        ).fetchone()
        if child is None or not (
            str(child.get("status") or "") == expected_status
            and int(child.get("updated_at") or 0) == expected_updated_at
            and int(child.get("updated_at") or 0) <= stale_cutoff
            and int(child.get("tts_attempted_call_count") or 0)
            == expected_tts_attempted_count
            and int(child.get("tts_completed_call_count") or 0)
            == expected_tts_completed_count
        ):
            return False
        if expected_status in {"validating", "publishing"}:
            probe = conn.execute(
                """SELECT finalized_at
                FROM learning_openmaic_conversation_probes
                WHERE tts_credential_recovery_id = ?
                LIMIT 1 FOR UPDATE""",
                (recovery_id,),
            ).fetchone()
            finalized = (
                probe is not None and probe.get("finalized_at") is not None
            )
            if expected_status == "validating" and finalized:
                return False
            if expected_status == "publishing" and not finalized:
                return False
        elif expected_status != "recovering":
            return False
        failed = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              conversation_probe_verified = FALSE, verified_at = NULL,
              updated_at = ?, terminal_at = ?
            WHERE id = ? AND runtime_classroom_id = ? AND status = ?
              AND updated_at = ? AND updated_at <= ?
              AND tts_attempted_call_count = ?
              AND tts_completed_call_count = ?""",
            (
                error_code[:128],
                error_message_safe[:512],
                now,
                now,
                recovery_id,
                runtime_id,
                expected_status,
                expected_updated_at,
                stale_cutoff,
                expected_tts_attempted_count,
                expected_tts_completed_count,
            ),
        )
        if failed.rowcount != 1:
            return False
        restored = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', updated_at = ?
            WHERE id = ? AND status = 'recovering' AND attempt_ordinal = 3
              AND upstream_job_id = ?
              AND error_code = 'openmaic_generation_failed'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL""",
            (now, runtime_id, source_upstream_job_id),
        )
        if restored.rowcount != 1:
            raise RuntimeError("openmaic stale TTS child runtime CAS conflict")
        return True

    def mark_ready_from_tts_credential_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        parent_recovery_id: str,
        parent_db_snapshot_sha256: str,
        parent_receipt_sha256: str,
        parent_runtime_snapshot_sha256: str,
        source_upstream_job_id: str,
        upstream_child_id: str,
        upstream_classroom_id: str,
        conversation_probe_id: str,
        feature_manifest: Mapping[str, Any],
        receipt: Mapping[str, Any],
        now: int,
    ) -> None:
        parent = self.get_deterministic_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=True
        )
        if parent is None or str(parent.get("id") or "") != parent_recovery_id:
            raise RuntimeError("openmaic TTS credential parent missing")
        child = conn.execute(
            """UPDATE learning_openmaic_tts_credential_recoveries
            SET status = 'succeeded', conversation_probe_verified = TRUE,
              conversation_probe_id = ?, verified_at = ?, receipt_json = ?,
              error_code = NULL, error_message_safe = NULL,
              updated_at = ?, terminal_at = ?
            WHERE id = ? AND runtime_classroom_id = ? AND status = 'publishing'
              AND parent_recovery_id = ?
              AND parent_db_snapshot_sha256 = ?
              AND parent_receipt_sha256 = ?
              AND parent_runtime_snapshot_sha256 = ?
              AND upstream_child_id = expected_upstream_child_id
              AND upstream_child_id = ?
              AND upstream_classroom_id = expected_upstream_classroom_id
              AND upstream_classroom_id = ?
              AND scene_count = 10 AND audio_count = 10
              AND tts_verified_asset_count = 10
              AND static_contract_verified = TRUE
              AND conversation_probe_verified = FALSE
              AND llm_call_count = 0 AND web_search_call_count = 0
              AND image_generation_call_count = 0
              AND video_generation_call_count = 0
              AND tts_expected_call_count = 10
              AND tts_attempted_call_count = 10
              AND tts_completed_call_count = 10
              AND content_sha256 IS NOT NULL
              AND final_artifact_sha256 IS NOT NULL
              AND receipt_json IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM learning_openmaic_conversation_probes AS probe
                WHERE probe.id = ?
                  AND probe.runtime_classroom_id = ?
                  AND probe.upstream_classroom_id = ?
                  AND probe.candidate_kind = 'tts_credential_recovery'
                  AND probe.deterministic_recovery_id = ?
                  AND probe.tts_credential_recovery_id = ?
                  AND probe.finalized_at IS NOT NULL
              )""",
            (
                conversation_probe_id,
                now,
                self.encode_json(receipt),
                now,
                now,
                recovery_id,
                runtime_id,
                parent_recovery_id,
                parent_db_snapshot_sha256,
                parent_receipt_sha256,
                parent_runtime_snapshot_sha256,
                upstream_child_id,
                upstream_classroom_id,
                conversation_probe_id,
                runtime_id,
                upstream_classroom_id,
                parent_recovery_id,
                recovery_id,
            ),
        )
        if child.rowcount != 1:
            raise RuntimeError("openmaic TTS credential finalization conflict")
        runtime = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET upstream_classroom_id = ?, status = 'ready',
              quality_status = 'pending_review', feature_manifest_json = ?,
              error_code = NULL, error_message_safe = NULL,
              ready_at = ?, updated_at = ?
            WHERE id = ? AND attempt_ordinal = 3 AND status = 'recovering'
              AND upstream_job_id = ?
              AND error_code = 'openmaic_generation_failed'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL""",
            (
                upstream_classroom_id,
                self.encode_json(feature_manifest),
                now,
                now,
                runtime_id,
                source_upstream_job_id,
            ),
        )
        if runtime.rowcount != 1:
            raise RuntimeError("openmaic TTS credential runtime ready conflict")

    def update_deterministic_recovery_observation(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        receipt: Mapping[str, Any],
        tts_attempted_count: int,
        tts_completed_count: int,
        progressed: bool,
        now: int,
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET receipt_json = ?, tts_attempted_call_count = ?,
              tts_completed_call_count = ?,
              updated_at = CASE WHEN ? THEN ? ELSE updated_at END
            WHERE id = ? AND status = 'recovering'
              AND upstream_recovery_id IS NOT NULL
              AND tts_attempted_call_count <= ?
              AND tts_completed_call_count <= ?""",
            (
                self.encode_json(receipt),
                tts_attempted_count,
                tts_completed_count,
                bool(progressed),
                now,
                recovery_id,
                tts_attempted_count,
                tts_completed_count,
            ),
        )
        return updated.rowcount == 1

    def fail_stale_deterministic_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        expected_status: str,
        expected_updated_at: int,
        expected_tts_attempted_count: int,
        expected_tts_completed_count: int,
        error_code: str,
        error_message_safe: str,
        receipt: Mapping[str, Any] | None,
        now: int,
    ) -> bool:
        """Terminalize only the exact stale observation read by this poller."""

        failed = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              receipt_json = COALESCE(?, receipt_json),
              updated_at = ?, terminal_at = ?
            WHERE id = ? AND runtime_classroom_id = ? AND status = ?
              AND updated_at = ? AND tts_attempted_call_count = ?
              AND tts_completed_call_count = ?""",
            (
                error_code[:128],
                error_message_safe[:512],
                self.encode_json(receipt) if receipt is not None else None,
                now,
                now,
                recovery_id,
                runtime_id,
                expected_status,
                expected_updated_at,
                expected_tts_attempted_count,
                expected_tts_completed_count,
            ),
        )
        if failed.rowcount != 1:
            return False
        restored = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', updated_at = ?
            WHERE id = ? AND status = 'recovering' AND attempt_ordinal = 3
              AND error_code = 'openmaic_generation_failed'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL""",
            (now, runtime_id),
        )
        if restored.rowcount != 1:
            raise RuntimeError("openmaic deterministic recovery stale CAS conflict")
        return True

    def claim_deterministic_recovery_validation(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        artifact: Mapping[str, Any],
        tts_attempted_count: int,
        tts_completed_count: int,
        receipt: Mapping[str, Any],
        now: int,
    ) -> bool:
        tts = artifact["tts"]
        updated = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET status = 'validating', upstream_classroom_id = ?, scene_count = ?,
              content_sha256 = ?, final_artifact_sha256 = ?,
              artifact_created_at = ?, tts_verified_asset_count = ?,
              tts_attempted_call_count = ?, tts_completed_call_count = ?,
              receipt_json = ?, updated_at = ?
            WHERE id = ? AND status = 'recovering'
              AND upstream_recovery_id IS NOT NULL
              AND source_job_snapshot_sha256 IS NOT NULL
              AND upstream_recovery_id = expected_upstream_recovery_id
              AND llm_call_count = 0 AND web_search_call_count = 0
              AND image_generation_call_count = 0
              AND video_generation_call_count = 0
              AND tts_expected_call_count = 10
              AND ? = 10 AND ? = 10""",
            (
                artifact["classroomId"],
                int(artifact["sceneCount"]),
                artifact["contentSha256"],
                artifact["artifactSha256"],
                receipt.get("completedAt"),
                int(tts["speechCount"]),
                tts_attempted_count,
                tts_completed_count,
                self.encode_json(receipt),
                now,
                recovery_id,
                tts_attempted_count,
                tts_completed_count,
            ),
        )
        return updated.rowcount == 1

    def fail_deterministic_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        error_code: str,
        error_message_safe: str,
        receipt: Mapping[str, Any] | None,
        tts_attempted_count: int | None,
        tts_completed_count: int | None,
        now: int,
    ) -> bool:
        failed = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              receipt_json = COALESCE(?, receipt_json),
              tts_attempted_call_count = COALESCE(?, tts_attempted_call_count),
              tts_completed_call_count = COALESCE(?, tts_completed_call_count),
              updated_at = ?, terminal_at = ?
            WHERE id = ? AND runtime_classroom_id = ?
              AND status IN ('recovering', 'validating')""",
            (
                error_code[:128],
                error_message_safe[:512],
                self.encode_json(receipt) if receipt is not None else None,
                tts_attempted_count,
                tts_completed_count,
                now,
                now,
                recovery_id,
                runtime_id,
            ),
        )
        if failed.rowcount != 1:
            return False
        restored = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET status = 'failed', updated_at = ?
            WHERE id = ? AND status = 'recovering' AND attempt_ordinal = 3
              AND error_code = 'openmaic_generation_failed'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL""",
            (now, runtime_id),
        )
        if restored.rowcount != 1:
            raise RuntimeError("openmaic deterministic recovery failure CAS conflict")
        return True

    def mark_ready_from_deterministic_recovery(
        self,
        conn: DatabaseConnection,
        *,
        recovery_id: str,
        runtime_id: str,
        source_upstream_job_id: str,
        upstream_classroom_id: str,
        feature_manifest: Mapping[str, Any],
        receipt: Mapping[str, Any],
        now: int,
    ) -> None:
        recovery = conn.execute(
            """UPDATE learning_openmaic_deterministic_recoveries
            SET status = 'succeeded', static_contract_verified = TRUE,
              conversation_probe_verified = TRUE, verified_at = ?,
              receipt_json = ?, updated_at = ?, terminal_at = ?
            WHERE id = ? AND runtime_classroom_id = ? AND status = 'validating'
              AND source_runtime_status = 'failed'
              AND source_runtime_error_code = 'openmaic_generation_failed'
              AND source_upstream_job_id = ?
              AND source_job_status = 'failed'
              AND source_job_error = 'structured_output_exhausted'
              AND source_job_snapshot_sha256 IS NOT NULL
              AND upstream_recovery_id = expected_upstream_recovery_id
              AND upstream_classroom_id = ?
              AND scene_count = 10 AND tts_verified_asset_count = 10
              AND llm_call_count = 0 AND web_search_call_count = 0
              AND image_generation_call_count = 0
              AND video_generation_call_count = 0
              AND tts_expected_call_count = 10
              AND tts_attempted_call_count = 10
              AND tts_completed_call_count = 10""",
            (
                now,
                self.encode_json(receipt),
                now,
                now,
                recovery_id,
                runtime_id,
                source_upstream_job_id,
                upstream_classroom_id,
            ),
        )
        if recovery.rowcount != 1:
            raise RuntimeError("openmaic deterministic recovery finalization conflict")
        runtime = conn.execute(
            """UPDATE learning_openmaic_runtime_classrooms
            SET upstream_classroom_id = ?, status = 'ready',
              feature_manifest_json = ?, error_code = NULL,
              error_message_safe = NULL, ready_at = ?, updated_at = ?
            WHERE id = ? AND attempt_ordinal = 3 AND status = 'recovering'
              AND upstream_job_id = ? AND error_code = 'openmaic_generation_failed'
              AND upstream_classroom_id IS NULL AND retired_at IS NULL""",
            (
                upstream_classroom_id,
                self.encode_json(feature_manifest),
                now,
                now,
                runtime_id,
                source_upstream_job_id,
            ),
        )
        if runtime.rowcount != 1:
            raise RuntimeError("openmaic deterministic recovery runtime ready CAS conflict")

    def get_formal_session_binding_for_update(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_session_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM learning_student_formal_session_bindings
            WHERE learning_session_id = ? AND family_id = ? AND child_id = ?
            LIMIT 1 FOR UPDATE
            """,
            (learning_session_id, family_id, child_id),
        ).fetchone()

    def bind_formal_session_to_active_release(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_session_id: str,
        now: int,
    ) -> DatabaseRow | None:
        """Pin a session to an exact active pointer or current child plan item."""

        existing = self.get_formal_session_binding_for_update(
            conn,
            family_id=family_id,
            child_id=child_id,
            learning_session_id=learning_session_id,
        )
        if existing is not None:
            return existing
        child = conn.execute(
            """
            SELECT grade_code, grade_selection_revision
            FROM children
            WHERE family_id = ? AND id = ?
            LIMIT 1 FOR UPDATE
            """,
            (family_id, child_id),
        ).fetchone()
        if child is None or int(child.get("grade_selection_revision") or 0) < 1:
            return None

        candidate = conn.execute(
            f"""
            SELECT 'progressive_plan' AS authority_kind,
              NULL AS pointer_history_id, NULL AS pointer_revision,
              plan.id AS preparation_plan_id,
              child.grade_selection_revision,
              plan.catalog_release_id AS release_id,
              plan.target_fingerprint,
              'mira.learning.formal-publication.v1'
                AS publication_contract_version,
              runtime.candidate_binding_contract_version
                AS runtime_binding_contract_version,
              build_item.id AS build_item_id,
              course.id AS course_id, course.version AS course_version,
              package.id AS package_id, package.version AS package_version,
              package.public_content_hash AS package_content_hash,
              runtime.id AS runtime_classroom_id,
              runtime.upstream_classroom_id
            FROM learning_sessions AS session
            JOIN children AS child
              ON child.id = session.child_id
             AND child.family_id = session.family_id
            JOIN learning_courses AS course
              ON course.id = session.course_id
             AND course.version = session.course_version
             AND course.grade_code = child.grade_code
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.content_origin = 'openmaic_generated'
             AND course.retired_at IS NULL
            JOIN learning_lesson_packages AS package
              ON package.id = session.lesson_package_id
             AND package.version = session.lesson_package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
             AND package.public_content_hash = session.lesson_package_content_hash
             AND package.status = 'published'
             AND package.retired_at IS NULL
            JOIN learning_curriculum_preparation_plans AS plan
              ON plan.family_id = child.family_id
             AND plan.child_id = child.id
             AND plan.grade_code = child.grade_code
             AND plan.grade_selection_revision = child.grade_selection_revision
             AND plan.superseded_at IS NULL
             AND plan.status IN ('queued', 'running', 'ready', 'failed')
             AND NOT EXISTS (
               SELECT 1
               FROM learning_curriculum_preparation_plans AS newer_plan
               WHERE newer_plan.family_id = plan.family_id
                 AND newer_plan.child_id = plan.child_id
                 AND newer_plan.grade_selection_revision =
                   plan.grade_selection_revision
                 AND newer_plan.target_fingerprint = plan.target_fingerprint
                 AND (
                   newer_plan.retry_ordinal > plan.retry_ordinal
                   OR (
                     newer_plan.retry_ordinal = plan.retry_ordinal
                     AND newer_plan.created_at > plan.created_at
                   )
                   OR (
                     newer_plan.retry_ordinal = plan.retry_ordinal
                     AND newer_plan.created_at = plan.created_at
                     AND newer_plan.id > plan.id
                   )
                 )
             )
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = plan.catalog_release_id
             AND release_row.retired_at IS NULL
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = plan.catalog_release_id
             AND release_item.grade_code = child.grade_code
             AND release_item.course_id = course.id
             AND release_item.course_version = course.version
             AND release_item.package_id = package.id
             AND release_item.package_version = package.version
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_catalog_build_items AS build_item
              ON build_item.id = (
                SELECT exact_item.id
                FROM learning_catalog_build_items AS exact_item
                WHERE exact_item.build_job_id = plan.catalog_build_id
                  AND exact_item.release_id = plan.catalog_release_id
                  AND exact_item.grade_code = child.grade_code
                  AND exact_item.course_id = course.id
                  AND exact_item.course_version = course.version
                  AND (
                    exact_item.status = 'ready'
                    OR (
                      exact_item.status = 'course_ready'
                      AND exact_item.execution_mode_snapshot = 'content_only'
                      AND exact_item.content_phase = 'course_ready'
                      AND exact_item.content_gate_status = 'passed'
                      AND exact_item.content_gate_passed_at IS NOT NULL
                      AND exact_item.content_validation_contract_version
                        IS NOT NULL
                      AND exact_item.content_validation_contract_version <> ''
                      AND exact_item.content_receipt_hash
                        REGEXP '^[0-9a-f]{{64}}$'
                    )
                  )
                LIMIT 1
              )
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.candidate_build_item_id = build_item.id
             AND runtime.candidate_release_id = plan.catalog_release_id
             AND runtime.candidate_grade_code = child.grade_code
             AND runtime.candidate_target_fingerprint = plan.target_fingerprint
             AND runtime.candidate_binding_contract_version = ?
             AND runtime.course_id = course.id
             AND runtime.course_version = course.version
             AND runtime.package_id = package.id
             AND runtime.package_version = package.version
             AND runtime.status = 'ready'
             AND runtime.upstream_classroom_id IS NOT NULL
             AND runtime.retired_at IS NULL
             {current_formal_runtime_sql(runtime_alias="runtime")}
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = build_item.id
             AND receipt.runtime_classroom_id = runtime.id
             AND receipt.release_id = plan.catalog_release_id
             AND receipt.grade_code = child.grade_code
             AND receipt.target_fingerprint = plan.target_fingerprint
             AND receipt.binding_contract_version = ?
             AND receipt.course_id = course.id
             AND receipt.course_version = course.version
             AND receipt.package_id = package.id
             AND receipt.package_version = package.version
             AND receipt.classroom_status = 'passed'
             AND receipt.tts_status = 'passed'
             AND receipt.asr_roundtrip_status = 'passed'
             AND receipt.conversation_provider_status = 'passed'
             AND receipt.auto_validated = 1
             AND receipt.publication_status = 'published'
            JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = receipt.build_item_id
             AND audio.runtime_classroom_id = runtime.id
             AND audio.release_id = plan.catalog_release_id
             AND audio.grade_code = child.grade_code
             AND audio.target_fingerprint = plan.target_fingerprint
             AND audio.course_id = course.id
             AND audio.course_version = course.version
             AND audio.package_id = package.id
             AND audio.package_version = package.version
             AND audio.state = 'auto_validated'
             AND audio.expected_segment_count BETWEEN 1 AND 240
             AND audio.tts_attempted_count = audio.expected_segment_count
             AND audio.tts_completed_count = audio.expected_segment_count
             AND audio.audio_validated_count = audio.expected_segment_count
             AND audio.asr_attempted_count = audio.expected_segment_count
             AND audio.asr_passed_count = audio.expected_segment_count
             AND audio.terminal_receipt_hash IS NOT NULL
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
              ON provider.release_id = plan.catalog_release_id
             AND provider.grade_code = child.grade_code
             AND provider.target_fingerprint = plan.target_fingerprint
            WHERE session.id = ? AND session.family_id = ?
              AND session.child_id = ? AND course.grade_code = child.grade_code
              {current_formal_validation_authority_sql(
                  receipt_alias="receipt",
                  provider_alias="provider",
              )}
            LIMIT 1 FOR UPDATE
            """,
            (
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                learning_session_id,
                family_id,
                child_id,
            ),
        ).fetchone()
        authority = candidate
        if authority is None:
            authority = conn.execute(
                f"""
                SELECT 'active_pointer' AS authority_kind,
                  pointer.history_id AS pointer_history_id,
                  pointer.pointer_revision,
                  NULL AS preparation_plan_id,
                  NULL AS grade_selection_revision,
                  pointer.release_id, pointer.target_fingerprint,
                  pointer.contract_version AS publication_contract_version,
                  runtime.candidate_binding_contract_version
                    AS runtime_binding_contract_version,
                  build_item.id AS build_item_id,
                  course.id AS course_id, course.version AS course_version,
                  package.id AS package_id, package.version AS package_version,
                  package.public_content_hash AS package_content_hash,
                  runtime.id AS runtime_classroom_id,
                  runtime.upstream_classroom_id
            FROM learning_sessions AS session
            JOIN children AS child
              ON child.id = session.child_id
             AND child.family_id = session.family_id
            JOIN learning_courses AS course
              ON course.id = session.course_id
             AND course.version = session.course_version
             AND course.grade_code = child.grade_code
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.content_origin = 'openmaic_generated'
             AND course.retired_at IS NULL
            JOIN learning_lesson_packages AS package
              ON package.id = session.lesson_package_id
             AND package.version = session.lesson_package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
             AND package.public_content_hash = session.lesson_package_content_hash
             AND package.status = 'published'
             AND package.retired_at IS NULL
            JOIN learning_curriculum_grade_release_pointers AS pointer
              ON pointer.grade_code = course.grade_code
             AND pointer.pointer_revision >= 1
             AND pointer.contract_version =
               'mira.learning.formal-publication.v1'
            JOIN learning_curriculum_grade_release_history AS history
              ON history.id = pointer.history_id
             AND history.grade_code = pointer.grade_code
             AND history.pointer_revision = pointer.pointer_revision
             AND history.target_fingerprint = pointer.target_fingerprint
             AND history.contract_version = pointer.contract_version
             AND history.release_id = pointer.release_id
             AND history.activated_at = pointer.activated_at
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = pointer.release_id
             AND release_row.retired_at IS NULL
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = pointer.release_id
             AND release_item.course_id = course.id
             AND release_item.course_version = course.version
             AND release_item.grade_code = course.grade_code
             AND release_item.package_id = package.id
             AND release_item.package_version = package.version
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.candidate_release_id = pointer.release_id
             AND runtime.candidate_grade_code = pointer.grade_code
             AND runtime.candidate_target_fingerprint =
               pointer.target_fingerprint
             AND runtime.candidate_binding_contract_version =
               ?
             AND runtime.course_id = course.id
             AND runtime.course_version = course.version
             AND runtime.package_id = package.id
             AND runtime.package_version = package.version
             AND runtime.status = 'ready'
             AND runtime.upstream_classroom_id IS NOT NULL
             AND runtime.retired_at IS NULL
             {current_formal_runtime_sql(runtime_alias="runtime")}
            JOIN learning_catalog_build_items AS build_item
              ON build_item.id = runtime.candidate_build_item_id
             AND build_item.release_id = pointer.release_id
             AND build_item.grade_code = pointer.grade_code
             AND build_item.course_id = course.id
             AND build_item.course_version = course.version
             AND (
               build_item.status = 'ready'
               OR (
                 build_item.status = 'course_ready'
                 AND build_item.execution_mode_snapshot = 'content_only'
                 AND build_item.content_phase = 'course_ready'
                 AND build_item.content_gate_status = 'passed'
                 AND build_item.content_gate_passed_at IS NOT NULL
                 AND build_item.content_validation_contract_version IS NOT NULL
                 AND build_item.content_validation_contract_version <> ''
                 AND build_item.content_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
               )
             )
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = runtime.candidate_build_item_id
             AND receipt.runtime_classroom_id = runtime.id
             AND receipt.release_id = pointer.release_id
             AND receipt.grade_code = pointer.grade_code
             AND receipt.target_fingerprint = pointer.target_fingerprint
             AND receipt.binding_contract_version = ?
             AND receipt.course_id = course.id
             AND receipt.course_version = course.version
             AND receipt.package_id = package.id
             AND receipt.package_version = package.version
             AND receipt.classroom_status = 'passed'
             AND receipt.tts_status = 'passed'
             AND receipt.asr_roundtrip_status = 'passed'
             AND receipt.conversation_provider_status = 'passed'
             AND receipt.auto_validated = 1
             AND receipt.publication_status = 'published'
            JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = receipt.build_item_id
             AND audio.runtime_classroom_id = runtime.id
             AND audio.release_id = pointer.release_id
             AND audio.grade_code = pointer.grade_code
             AND audio.target_fingerprint = pointer.target_fingerprint
             AND audio.course_id = course.id
             AND audio.course_version = course.version
             AND audio.package_id = package.id
             AND audio.package_version = package.version
             AND audio.state = 'auto_validated'
             AND audio.expected_segment_count BETWEEN 1 AND 240
             AND audio.tts_attempted_count = audio.expected_segment_count
             AND audio.tts_completed_count = audio.expected_segment_count
             AND audio.audio_validated_count = audio.expected_segment_count
             AND audio.asr_attempted_count = audio.expected_segment_count
             AND audio.asr_passed_count = audio.expected_segment_count
             AND audio.terminal_receipt_hash IS NOT NULL
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
              ON provider.release_id = pointer.release_id
             AND provider.grade_code = pointer.grade_code
             AND provider.target_fingerprint = pointer.target_fingerprint
            WHERE session.id = ? AND session.family_id = ?
              AND session.child_id = ?
              {current_formal_validation_authority_sql(
                  receipt_alias="receipt",
                  provider_alias="provider",
              )}
            LIMIT 1
                FOR UPDATE
                """,
                (
                    self.CANDIDATE_BINDING_CONTRACT_VERSION,
                    self.CANDIDATE_BINDING_CONTRACT_VERSION,
                    learning_session_id,
                    family_id,
                    child_id,
                ),
            ).fetchone()
        if authority is None:
            return None
        conn.execute(
            """
            INSERT INTO learning_student_formal_session_bindings(
              learning_session_id, family_id, child_id, grade_code,
              authority_kind, pointer_history_id, pointer_revision,
              preparation_plan_id, grade_selection_revision, release_id,
              target_fingerprint, publication_contract_version,
              runtime_binding_contract_version, build_item_id,
              course_id, course_version, package_id, package_version,
              package_content_hash, runtime_classroom_id,
              upstream_classroom_id, bound_at, created_at
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON DUPLICATE KEY UPDATE
              learning_session_id = VALUES(learning_session_id)
            """,
            (
                learning_session_id,
                family_id,
                child_id,
                str(child["grade_code"]),
                authority["authority_kind"],
                authority.get("pointer_history_id"),
                authority.get("pointer_revision"),
                authority.get("preparation_plan_id"),
                authority.get("grade_selection_revision"),
                authority["release_id"],
                authority["target_fingerprint"],
                authority["publication_contract_version"],
                authority["runtime_binding_contract_version"],
                authority["build_item_id"],
                authority["course_id"],
                authority["course_version"],
                authority["package_id"],
                int(authority["package_version"]),
                authority["package_content_hash"],
                authority["runtime_classroom_id"],
                authority["upstream_classroom_id"],
                int(now),
                int(now),
            ),
        )
        return self.get_formal_session_binding_for_update(
            conn,
            family_id=family_id,
            child_id=child_id,
            learning_session_id=learning_session_id,
        )

    def get_owned_session_runtime(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_session_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT session.id AS learning_session_id, session.status AS session_status,
              session.course_id, session.course_version,
              session.lesson_package_id, session.lesson_package_version,
              session.lesson_package_content_hash,
              formal_binding.learning_session_id
                AS formal_binding_learning_session_id,
              formal_binding.family_id AS formal_binding_family_id,
              formal_binding.child_id AS formal_binding_child_id,
              formal_binding.grade_code AS formal_binding_grade_code,
              formal_binding.authority_kind AS formal_binding_authority_kind,
              formal_binding.pointer_history_id
                AS formal_binding_pointer_history_id,
              formal_binding.pointer_revision
                AS formal_binding_pointer_revision,
              formal_binding.preparation_plan_id
                AS formal_binding_preparation_plan_id,
              formal_binding.grade_selection_revision
                AS formal_binding_grade_selection_revision,
              formal_binding.release_id AS formal_binding_release_id,
              formal_binding.target_fingerprint
                AS formal_binding_target_fingerprint,
              formal_binding.publication_contract_version
                AS formal_binding_contract_version,
              formal_binding.runtime_binding_contract_version
                AS formal_binding_runtime_contract_version,
              formal_binding.build_item_id AS formal_binding_build_item_id,
              formal_binding.course_id AS formal_binding_course_id,
              formal_binding.course_version AS formal_binding_course_version,
              formal_binding.package_id AS formal_binding_package_id,
              formal_binding.package_version AS formal_binding_package_version,
              formal_binding.package_content_hash
                AS formal_binding_package_content_hash,
              formal_binding.runtime_classroom_id
                AS formal_binding_runtime_classroom_id,
              formal_binding.upstream_classroom_id
                AS formal_binding_upstream_classroom_id,
              child.grade_code AS child_grade_code,
              child.grade_selection_revision AS child_grade_selection_revision,
              course.grade_code AS course_grade_code,
              course.subject AS course_subject,
              course.node_code AS course_node_code,
              course.curriculum_version AS course_curriculum_version,
              course.boundary_version AS course_boundary_version,
              runtime.id AS runtime_classroom_id, runtime.status AS runtime_status,
              runtime.quality_status AS runtime_quality_status,
              runtime.request_id AS runtime_request_id,
              runtime.upstream_classroom_id, runtime.feature_manifest_json,
              runtime.ready_at, runtime.candidate_build_item_id,
              runtime.candidate_release_id,
              runtime.candidate_grade_code,
              runtime.candidate_target_fingerprint,
              runtime.candidate_binding_contract_version,
              candidate_release.status AS candidate_release_status,
              candidate_pointer.release_id AS active_candidate_release_id,
              candidate_pointer.target_fingerprint AS active_candidate_fingerprint,
              candidate_pointer.contract_version AS active_candidate_contract_version,
              candidate_receipt.publication_status AS candidate_publication_status,
              candidate_receipt.auto_validated AS candidate_auto_validated,
              candidate_receipt.tts_status AS candidate_tts_status,
              candidate_receipt.asr_roundtrip_status AS candidate_asr_status,
              candidate_receipt.conversation_provider_status
                AS candidate_conversation_status,
              candidate_receipt.conversation_provider_receipt_hash
                AS candidate_generation_evidence_receipt_hash,
              candidate_receipt.auto_validation_contract_version
                AS candidate_auto_validation_contract_version,
              candidate_receipt.auto_validation_receipt_hash
                AS candidate_auto_validation_receipt_hash,
              formal_audio.state AS formal_audio_state,
              formal_audio.release_id AS formal_audio_release_id,
              formal_audio.grade_code AS formal_audio_grade_code,
              formal_audio.target_fingerprint AS formal_audio_target_fingerprint,
              formal_audio.runtime_classroom_id
                AS formal_audio_runtime_classroom_id,
              formal_audio.course_id AS formal_audio_course_id,
              formal_audio.course_version AS formal_audio_course_version,
              formal_audio.package_id AS formal_audio_package_id,
              formal_audio.package_version AS formal_audio_package_version,
              formal_audio.classroom_content_sha256
                AS formal_audio_classroom_sha256,
              formal_audio.subject AS formal_audio_subject,
              formal_audio.teacher_profile_id
                AS formal_audio_teacher_profile_id,
              formal_audio.teacher_profile_version
                AS formal_audio_teacher_profile_version,
              formal_audio.teacher_profile_hash
                AS formal_audio_teacher_profile_hash,
              formal_audio.teacher_name AS formal_audio_teacher_name,
              formal_audio.teacher_gender AS formal_audio_teacher_gender,
              formal_audio.voice_gender AS formal_audio_voice_gender,
              formal_audio.tts_voice_id AS formal_audio_voice_id,
              formal_audio.language_code AS formal_audio_language_code,
              formal_audio.expected_segment_count
                AS formal_audio_expected_segment_count,
              formal_audio.tts_attempted_count
                AS formal_audio_tts_attempted_count,
              formal_audio.tts_completed_count
                AS formal_audio_tts_completed_count,
              formal_audio.audio_validated_count
                AS formal_audio_validated_count,
              formal_audio.asr_attempted_count
                AS formal_audio_asr_attempted_count,
              formal_audio.asr_passed_count
                AS formal_audio_asr_passed_count,
              formal_audio.terminal_receipt_hash AS formal_audio_receipt_hash,
              formal_provider.state AS formal_provider_state,
              formal_provider.build_item_id AS formal_provider_build_item_id,
              formal_provider.release_id AS formal_provider_release_id,
              formal_provider.grade_code AS formal_provider_grade_code,
              formal_provider.target_fingerprint
                AS formal_provider_target_fingerprint,
              formal_provider.runtime_classroom_id
                AS formal_provider_runtime_classroom_id,
              formal_provider.classroom_content_sha256
                AS formal_provider_classroom_sha256,
              formal_provider.audio_job_terminal_receipt_hash
                AS formal_provider_audio_receipt_hash,
              formal_provider.expected_provider_call_count
                AS formal_provider_expected_count,
              formal_provider.provider_attempted_count
                AS formal_provider_attempted_count,
              formal_provider.provider_passed_count
                AS formal_provider_passed_count,
              formal_provider.provider_receipt_hash
                AS formal_provider_receipt_hash,
              formal_provider.route_session_provider_call
                AS formal_route_provider_call,
              formal_provider.route_session_status AS formal_route_status
            FROM learning_sessions AS session
            JOIN children AS child
              ON child.id = session.child_id
             AND child.family_id = session.family_id
            JOIN learning_courses AS course
              ON course.id = session.course_id
             AND course.version = session.course_version
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.content_origin = 'openmaic_generated'
             AND course.retired_at IS NULL
            JOIN learning_lesson_packages AS package
              ON package.id = session.lesson_package_id
             AND package.version = session.lesson_package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
             AND package.public_content_hash = session.lesson_package_content_hash
             AND package.status = 'published'
             AND package.retired_at IS NULL
            LEFT JOIN learning_student_formal_session_bindings AS formal_binding
              ON formal_binding.learning_session_id = session.id
             AND formal_binding.family_id = session.family_id
             AND formal_binding.child_id = session.child_id
             AND formal_binding.course_id = session.course_id
             AND formal_binding.course_version = session.course_version
             AND formal_binding.package_id = session.lesson_package_id
             AND formal_binding.package_version = session.lesson_package_version
             AND formal_binding.package_content_hash =
               session.lesson_package_content_hash
            LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.package_id = package.id
             AND runtime.package_version = package.version
             AND (
               formal_binding.learning_session_id IS NULL
               OR runtime.id = formal_binding.runtime_classroom_id
             )
             AND runtime.retired_at IS NULL
            LEFT JOIN learning_catalog_releases AS candidate_release
              ON candidate_release.id = runtime.candidate_release_id
            LEFT JOIN learning_curriculum_grade_release_pointers AS candidate_pointer
              ON candidate_pointer.grade_code = runtime.candidate_grade_code
             AND candidate_pointer.release_id = runtime.candidate_release_id
             AND candidate_pointer.target_fingerprint =
               runtime.candidate_target_fingerprint
             AND candidate_pointer.pointer_revision >= 1
            LEFT JOIN learning_curriculum_classroom_item_receipts AS candidate_receipt
              ON candidate_receipt.build_item_id = runtime.candidate_build_item_id
             AND candidate_receipt.runtime_classroom_id = runtime.id
            LEFT JOIN learning_formal_qwen_audio_jobs AS formal_audio
              ON formal_audio.build_item_id = runtime.candidate_build_item_id
             AND formal_audio.runtime_classroom_id = runtime.id
             AND formal_audio.release_id = runtime.candidate_release_id
             AND formal_audio.target_fingerprint =
               runtime.candidate_target_fingerprint
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS formal_provider
              ON formal_provider.release_id = runtime.candidate_release_id
             AND formal_provider.grade_code = runtime.candidate_grade_code
             AND formal_provider.target_fingerprint =
               runtime.candidate_target_fingerprint
            WHERE session.id = ? AND session.family_id = ? AND session.child_id = ?
            LIMIT 1
            """,
            (learning_session_id, family_id, child_id),
        ).fetchone()

    def replace_formal_feature_evidence(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        expected_manifest: Mapping[str, Any],
        updated_manifest: Mapping[str, Any],
        now: int,
    ) -> None:
        if (
            {key: value for key, value in expected_manifest.items() if key != "evidence"}
            != {key: value for key, value in updated_manifest.items() if key != "evidence"}
        ):
            raise ValueError("only derived feature evidence may be replaced")
        changed = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET feature_manifest_json = ?, updated_at = ?
            WHERE id = ? AND status = 'ready' AND retired_at IS NULL
              AND BINARY feature_manifest_json = BINARY ?
            """,
            (
                self.encode_json(updated_manifest), now, runtime_id,
                self.encode_json(expected_manifest),
            ),
        )
        if changed.rowcount != 1:
            raise RuntimeError("formal feature evidence compare-and-swap conflict")

    def review_runtime_classroom(
        self,
        conn: DatabaseConnection,
        *,
        runtime_id: str,
        decision: str,
        reviewer_id: str,
        notes: str,
        now: int,
    ) -> DatabaseRow | None:
        quality_status = "approved" if decision == "approve" else "rejected"
        cursor = conn.execute(
            """
            UPDATE learning_openmaic_runtime_classrooms
            SET quality_status = ?, reviewed_by = ?, reviewed_at = ?,
              review_notes = ?, updated_at = ?
            WHERE id = ? AND status = 'ready' AND retired_at IS NULL
              AND quality_status IN ('pending_review', 'approved', 'rejected')
            """,
            (
                quality_status,
                reviewer_id,
                now,
                notes or None,
                now,
                runtime_id,
            ),
        )
        if not cursor.rowcount:
            return None
        return self.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=True
        )

    def revoke_active_launch_tickets(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        learning_session_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_openmaic_launch_tickets
            SET revoked_at = ?
            WHERE principal_id = ? AND learning_session_id = ?
              AND consumed_at IS NULL AND revoked_at IS NULL
            """,
            (now, principal_id, learning_session_id),
        )

    def revoke_runtime_student_access(
        self,
        conn: DatabaseConnection,
        *,
        runtime_classroom_id: str,
        now: int,
    ) -> None:
        """Revoke live student credentials when a ready classroom is rejected."""

        conn.execute(
            """
            UPDATE student_openmaic_launch_tickets
            SET revoked_at = ?
            WHERE runtime_classroom_id = ?
              AND expires_at >= ?
              AND consumed_at IS NULL
              AND revoked_at IS NULL
            """,
            (now, runtime_classroom_id, now),
        )
        conn.execute(
            """
            UPDATE student_openmaic_runtime_sessions
            SET revoked_at = ?
            WHERE runtime_classroom_id = ?
              AND expires_at >= ?
              AND revoked_at IS NULL
            """,
            (now, runtime_classroom_id, now),
        )

    def create_launch_ticket(
        self,
        conn: DatabaseConnection,
        *,
        ticket_id: str,
        token_hash: str,
        principal: Mapping[str, Any],
        learning_session_id: str,
        runtime_classroom_id: str,
        expires_at: int,
        now: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO student_openmaic_launch_tickets(
              id, token_hash, principal_id, family_id, child_id,
              learning_session_id, runtime_classroom_id,
              expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id,
                token_hash,
                principal["id"],
                principal["family_id"],
                principal["child_id"],
                learning_session_id,
                runtime_classroom_id,
                expires_at,
                now,
            ),
        )

    def get_launch_ticket_for_update(
        self,
        conn: DatabaseConnection,
        *,
        token_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT ticket.*, runtime.status AS runtime_status,
              runtime.quality_status AS runtime_quality_status,
              runtime.request_id AS runtime_request_id,
              runtime.upstream_classroom_id, runtime.feature_manifest_json,
              runtime.candidate_build_item_id,
              runtime.candidate_release_id, runtime.candidate_grade_code,
              runtime.candidate_target_fingerprint,
              runtime.candidate_binding_contract_version,
              session.course_id, session.course_version,
              session.status AS learning_session_status,
              session.completed_at AS learning_session_completed_at,
              session.lesson_package_id, session.lesson_package_version,
              session.lesson_package_content_hash,
              formal_binding.learning_session_id
                AS formal_binding_learning_session_id,
              formal_binding.family_id AS formal_binding_family_id,
              formal_binding.child_id AS formal_binding_child_id,
              formal_binding.grade_code AS formal_binding_grade_code,
              formal_binding.authority_kind AS formal_binding_authority_kind,
              formal_binding.pointer_history_id
                AS formal_binding_pointer_history_id,
              formal_binding.pointer_revision
                AS formal_binding_pointer_revision,
              formal_binding.preparation_plan_id
                AS formal_binding_preparation_plan_id,
              formal_binding.grade_selection_revision
                AS formal_binding_grade_selection_revision,
              formal_binding.release_id AS formal_binding_release_id,
              formal_binding.target_fingerprint
                AS formal_binding_target_fingerprint,
              formal_binding.publication_contract_version
                AS formal_binding_contract_version,
              formal_binding.runtime_binding_contract_version
                AS formal_binding_runtime_contract_version,
              formal_binding.build_item_id AS formal_binding_build_item_id,
              formal_binding.course_id AS formal_binding_course_id,
              formal_binding.course_version AS formal_binding_course_version,
              formal_binding.package_id AS formal_binding_package_id,
              formal_binding.package_version AS formal_binding_package_version,
              formal_binding.package_content_hash
                AS formal_binding_package_content_hash,
              formal_binding.runtime_classroom_id
                AS formal_binding_runtime_classroom_id,
              formal_binding.upstream_classroom_id
                AS formal_binding_upstream_classroom_id,
              child.grade_code AS child_grade_code,
              child.grade_selection_revision AS child_grade_selection_revision,
              course.grade_code AS course_grade_code,
              course.subject AS course_subject,
              course.node_code AS course_node_code,
              course.curriculum_version AS course_curriculum_version,
              course.boundary_version AS course_boundary_version,
              candidate_release.status AS candidate_release_status,
              candidate_pointer.release_id AS active_candidate_release_id,
              candidate_pointer.target_fingerprint AS active_candidate_fingerprint,
              candidate_pointer.contract_version AS active_candidate_contract_version,
              candidate_receipt.publication_status AS candidate_publication_status,
              candidate_receipt.auto_validated AS candidate_auto_validated,
              candidate_receipt.tts_status AS candidate_tts_status,
              candidate_receipt.asr_roundtrip_status AS candidate_asr_status,
              candidate_receipt.conversation_provider_status
                AS candidate_conversation_status,
              candidate_receipt.conversation_provider_receipt_hash
                AS candidate_generation_evidence_receipt_hash,
              candidate_receipt.auto_validation_contract_version
                AS candidate_auto_validation_contract_version,
              candidate_receipt.auto_validation_receipt_hash
                AS candidate_auto_validation_receipt_hash,
              formal_audio.state AS formal_audio_state,
              formal_audio.release_id AS formal_audio_release_id,
              formal_audio.grade_code AS formal_audio_grade_code,
              formal_audio.target_fingerprint AS formal_audio_target_fingerprint,
              formal_audio.runtime_classroom_id
                AS formal_audio_runtime_classroom_id,
              formal_audio.course_id AS formal_audio_course_id,
              formal_audio.course_version AS formal_audio_course_version,
              formal_audio.package_id AS formal_audio_package_id,
              formal_audio.package_version AS formal_audio_package_version,
              formal_audio.classroom_content_sha256
                AS formal_audio_classroom_sha256,
              formal_audio.subject AS formal_audio_subject,
              formal_audio.teacher_profile_id
                AS formal_audio_teacher_profile_id,
              formal_audio.teacher_profile_version
                AS formal_audio_teacher_profile_version,
              formal_audio.teacher_profile_hash
                AS formal_audio_teacher_profile_hash,
              formal_audio.teacher_name AS formal_audio_teacher_name,
              formal_audio.teacher_gender AS formal_audio_teacher_gender,
              formal_audio.voice_gender AS formal_audio_voice_gender,
              formal_audio.tts_voice_id AS formal_audio_voice_id,
              formal_audio.language_code AS formal_audio_language_code,
              formal_audio.expected_segment_count
                AS formal_audio_expected_segment_count,
              formal_audio.tts_attempted_count
                AS formal_audio_tts_attempted_count,
              formal_audio.tts_completed_count
                AS formal_audio_tts_completed_count,
              formal_audio.audio_validated_count
                AS formal_audio_validated_count,
              formal_audio.asr_attempted_count
                AS formal_audio_asr_attempted_count,
              formal_audio.asr_passed_count
                AS formal_audio_asr_passed_count,
              formal_audio.terminal_receipt_hash AS formal_audio_receipt_hash,
              formal_provider.state AS formal_provider_state,
              formal_provider.build_item_id AS formal_provider_build_item_id,
              formal_provider.release_id AS formal_provider_release_id,
              formal_provider.grade_code AS formal_provider_grade_code,
              formal_provider.target_fingerprint
                AS formal_provider_target_fingerprint,
              formal_provider.runtime_classroom_id
                AS formal_provider_runtime_classroom_id,
              formal_provider.classroom_content_sha256
                AS formal_provider_classroom_sha256,
              formal_provider.audio_job_terminal_receipt_hash
                AS formal_provider_audio_receipt_hash,
              formal_provider.expected_provider_call_count
                AS formal_provider_expected_count,
              formal_provider.provider_attempted_count
                AS formal_provider_attempted_count,
              formal_provider.provider_passed_count
                AS formal_provider_passed_count,
              formal_provider.provider_receipt_hash
                AS formal_provider_receipt_hash,
              formal_provider.route_session_provider_call
                AS formal_route_provider_call,
              formal_provider.route_session_status AS formal_route_status
            FROM student_openmaic_launch_tickets AS ticket
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = ticket.runtime_classroom_id
            JOIN learning_sessions AS session
              ON session.id = ticket.learning_session_id
             AND session.family_id = ticket.family_id
             AND session.child_id = ticket.child_id
            LEFT JOIN learning_student_formal_session_bindings AS formal_binding
              ON formal_binding.learning_session_id = session.id
             AND formal_binding.family_id = ticket.family_id
             AND formal_binding.child_id = ticket.child_id
             AND formal_binding.runtime_classroom_id =
               ticket.runtime_classroom_id
            JOIN children AS child
              ON child.id = session.child_id
             AND child.family_id = session.family_id
            JOIN learning_courses AS course
              ON course.id = session.course_id
             AND course.version = session.course_version
            LEFT JOIN learning_catalog_releases AS candidate_release
              ON candidate_release.id = runtime.candidate_release_id
            LEFT JOIN learning_curriculum_grade_release_pointers AS candidate_pointer
              ON candidate_pointer.grade_code = runtime.candidate_grade_code
             AND candidate_pointer.release_id = runtime.candidate_release_id
             AND candidate_pointer.target_fingerprint =
               runtime.candidate_target_fingerprint
             AND candidate_pointer.pointer_revision >= 1
            LEFT JOIN learning_curriculum_classroom_item_receipts AS candidate_receipt
              ON candidate_receipt.build_item_id = runtime.candidate_build_item_id
             AND candidate_receipt.runtime_classroom_id = runtime.id
            LEFT JOIN learning_formal_qwen_audio_jobs AS formal_audio
              ON formal_audio.build_item_id = runtime.candidate_build_item_id
             AND formal_audio.runtime_classroom_id = runtime.id
             AND formal_audio.release_id = runtime.candidate_release_id
             AND formal_audio.target_fingerprint =
               runtime.candidate_target_fingerprint
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS formal_provider
              ON formal_provider.release_id = runtime.candidate_release_id
             AND formal_provider.grade_code = runtime.candidate_grade_code
             AND formal_provider.target_fingerprint =
               runtime.candidate_target_fingerprint
            WHERE ticket.token_hash = ?
            LIMIT 1 FOR UPDATE
            """,
            (token_hash,),
        ).fetchone()

    def consume_launch_ticket(
        self,
        conn: DatabaseConnection,
        *,
        ticket_id: str,
        runtime_session_id: str,
        runtime_token_hash: str,
        expires_at: int,
        now: int,
    ) -> None:
        updated = conn.execute(
            """
            UPDATE student_openmaic_launch_tickets
            SET consumed_at = ?
            WHERE id = ? AND consumed_at IS NULL AND revoked_at IS NULL
            """,
            (now, ticket_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("openmaic launch ticket was already consumed")
        ticket = conn.execute(
            "SELECT * FROM student_openmaic_launch_tickets WHERE id = ?",
            (ticket_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO student_openmaic_runtime_sessions(
              id, token_hash, launch_ticket_id, principal_id,
              family_id, child_id, learning_session_id,
              runtime_classroom_id, expires_at, last_active_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                runtime_session_id,
                runtime_token_hash,
                ticket_id,
                ticket["principal_id"],
                ticket["family_id"],
                ticket["child_id"],
                ticket["learning_session_id"],
                ticket["runtime_classroom_id"],
                expires_at,
                now,
                now,
            ),
        )

    def get_runtime_session_for_update(
        self,
        conn: DatabaseConnection,
        *,
        token_hash: str,
    ) -> DatabaseRow | None:
        # Serialize revocation and last-seen writes on this one session only.
        # Locking the whole authority join also locked learning_sessions and
        # children in optimizer order, opposite to progress-event ingestion.
        # That made an audio GET sporadically fail with MySQL deadlock 1213.
        locked = conn.execute(
            "SELECT id FROM student_openmaic_runtime_sessions "
            "WHERE token_hash = ? LIMIT 1 FOR UPDATE",
            (token_hash,),
        ).fetchone()
        if locked is None:
            return None
        return conn.execute(
            """
            SELECT runtime_session.*, runtime.status AS runtime_status,
              runtime.quality_status AS runtime_quality_status,
              runtime.request_id AS runtime_request_id,
              runtime.upstream_classroom_id, runtime.feature_manifest_json,
              runtime.candidate_build_item_id,
              runtime.candidate_release_id, runtime.candidate_grade_code,
              runtime.candidate_target_fingerprint,
              runtime.candidate_binding_contract_version,
              session.course_id, session.course_version,
              session.status AS learning_session_status,
              session.completed_at AS learning_session_completed_at,
              session.lesson_package_id, session.lesson_package_version,
              session.lesson_package_content_hash,
              formal_binding.learning_session_id
                AS formal_binding_learning_session_id,
              formal_binding.family_id AS formal_binding_family_id,
              formal_binding.child_id AS formal_binding_child_id,
              formal_binding.grade_code AS formal_binding_grade_code,
              formal_binding.authority_kind AS formal_binding_authority_kind,
              formal_binding.pointer_history_id
                AS formal_binding_pointer_history_id,
              formal_binding.pointer_revision
                AS formal_binding_pointer_revision,
              formal_binding.preparation_plan_id
                AS formal_binding_preparation_plan_id,
              formal_binding.grade_selection_revision
                AS formal_binding_grade_selection_revision,
              formal_binding.release_id AS formal_binding_release_id,
              formal_binding.target_fingerprint
                AS formal_binding_target_fingerprint,
              formal_binding.publication_contract_version
                AS formal_binding_contract_version,
              formal_binding.runtime_binding_contract_version
                AS formal_binding_runtime_contract_version,
              formal_binding.build_item_id AS formal_binding_build_item_id,
              formal_binding.course_id AS formal_binding_course_id,
              formal_binding.course_version AS formal_binding_course_version,
              formal_binding.package_id AS formal_binding_package_id,
              formal_binding.package_version AS formal_binding_package_version,
              formal_binding.package_content_hash
                AS formal_binding_package_content_hash,
              formal_binding.runtime_classroom_id
                AS formal_binding_runtime_classroom_id,
              formal_binding.upstream_classroom_id
                AS formal_binding_upstream_classroom_id,
              child.grade_code AS child_grade_code,
              child.grade_selection_revision AS child_grade_selection_revision,
              course.grade_code AS course_grade_code,
              course.subject AS course_subject,
              course.node_code AS course_node_code,
              course.curriculum_version AS course_curriculum_version,
              course.boundary_version AS course_boundary_version,
              candidate_release.status AS candidate_release_status,
              candidate_pointer.release_id AS active_candidate_release_id,
              candidate_pointer.target_fingerprint AS active_candidate_fingerprint,
              candidate_pointer.contract_version AS active_candidate_contract_version,
              candidate_receipt.publication_status AS candidate_publication_status,
              candidate_receipt.auto_validated AS candidate_auto_validated,
              candidate_receipt.tts_status AS candidate_tts_status,
              candidate_receipt.asr_roundtrip_status AS candidate_asr_status,
              candidate_receipt.conversation_provider_status
                AS candidate_conversation_status,
              candidate_receipt.conversation_provider_receipt_hash
                AS candidate_generation_evidence_receipt_hash,
              candidate_receipt.auto_validation_contract_version
                AS candidate_auto_validation_contract_version,
              candidate_receipt.auto_validation_receipt_hash
                AS candidate_auto_validation_receipt_hash,
              formal_audio.state AS formal_audio_state,
              formal_audio.release_id AS formal_audio_release_id,
              formal_audio.grade_code AS formal_audio_grade_code,
              formal_audio.target_fingerprint AS formal_audio_target_fingerprint,
              formal_audio.runtime_classroom_id
                AS formal_audio_runtime_classroom_id,
              formal_audio.course_id AS formal_audio_course_id,
              formal_audio.course_version AS formal_audio_course_version,
              formal_audio.package_id AS formal_audio_package_id,
              formal_audio.package_version AS formal_audio_package_version,
              formal_audio.classroom_content_sha256
                AS formal_audio_classroom_sha256,
              formal_audio.subject AS formal_audio_subject,
              formal_audio.teacher_profile_id
                AS formal_audio_teacher_profile_id,
              formal_audio.teacher_profile_version
                AS formal_audio_teacher_profile_version,
              formal_audio.teacher_profile_hash
                AS formal_audio_teacher_profile_hash,
              formal_audio.teacher_name AS formal_audio_teacher_name,
              formal_audio.teacher_gender AS formal_audio_teacher_gender,
              formal_audio.voice_gender AS formal_audio_voice_gender,
              formal_audio.tts_voice_id AS formal_audio_voice_id,
              formal_audio.language_code AS formal_audio_language_code,
              formal_audio.expected_segment_count
                AS formal_audio_expected_segment_count,
              formal_audio.tts_attempted_count
                AS formal_audio_tts_attempted_count,
              formal_audio.tts_completed_count
                AS formal_audio_tts_completed_count,
              formal_audio.audio_validated_count
                AS formal_audio_validated_count,
              formal_audio.asr_attempted_count
                AS formal_audio_asr_attempted_count,
              formal_audio.asr_passed_count
                AS formal_audio_asr_passed_count,
              formal_audio.terminal_receipt_hash AS formal_audio_receipt_hash,
              formal_provider.state AS formal_provider_state,
              formal_provider.build_item_id AS formal_provider_build_item_id,
              formal_provider.release_id AS formal_provider_release_id,
              formal_provider.grade_code AS formal_provider_grade_code,
              formal_provider.target_fingerprint
                AS formal_provider_target_fingerprint,
              formal_provider.runtime_classroom_id
                AS formal_provider_runtime_classroom_id,
              formal_provider.classroom_content_sha256
                AS formal_provider_classroom_sha256,
              formal_provider.audio_job_terminal_receipt_hash
                AS formal_provider_audio_receipt_hash,
              formal_provider.expected_provider_call_count
                AS formal_provider_expected_count,
              formal_provider.provider_attempted_count
                AS formal_provider_attempted_count,
              formal_provider.provider_passed_count
                AS formal_provider_passed_count,
              formal_provider.provider_receipt_hash
                AS formal_provider_receipt_hash,
              formal_provider.route_session_provider_call
                AS formal_route_provider_call,
              formal_provider.route_session_status AS formal_route_status
            FROM student_openmaic_runtime_sessions AS runtime_session
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = runtime_session.runtime_classroom_id
            JOIN learning_sessions AS session
              ON session.id = runtime_session.learning_session_id
             AND session.family_id = runtime_session.family_id
             AND session.child_id = runtime_session.child_id
            LEFT JOIN learning_student_formal_session_bindings AS formal_binding
              ON formal_binding.learning_session_id = session.id
             AND formal_binding.family_id = runtime_session.family_id
             AND formal_binding.child_id = runtime_session.child_id
             AND formal_binding.runtime_classroom_id =
               runtime_session.runtime_classroom_id
            JOIN children AS child
              ON child.id = session.child_id
             AND child.family_id = session.family_id
            JOIN learning_courses AS course
              ON course.id = session.course_id
             AND course.version = session.course_version
            LEFT JOIN learning_catalog_releases AS candidate_release
              ON candidate_release.id = runtime.candidate_release_id
            LEFT JOIN learning_curriculum_grade_release_pointers AS candidate_pointer
              ON candidate_pointer.grade_code = runtime.candidate_grade_code
             AND candidate_pointer.release_id = runtime.candidate_release_id
             AND candidate_pointer.target_fingerprint =
               runtime.candidate_target_fingerprint
             AND candidate_pointer.pointer_revision >= 1
            LEFT JOIN learning_curriculum_classroom_item_receipts AS candidate_receipt
              ON candidate_receipt.build_item_id = runtime.candidate_build_item_id
             AND candidate_receipt.runtime_classroom_id = runtime.id
            LEFT JOIN learning_formal_qwen_audio_jobs AS formal_audio
              ON formal_audio.build_item_id = runtime.candidate_build_item_id
             AND formal_audio.runtime_classroom_id = runtime.id
             AND formal_audio.release_id = runtime.candidate_release_id
             AND formal_audio.target_fingerprint =
               runtime.candidate_target_fingerprint
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS formal_provider
              ON formal_provider.release_id = runtime.candidate_release_id
             AND formal_provider.grade_code = runtime.candidate_grade_code
             AND formal_provider.target_fingerprint =
               runtime.candidate_target_fingerprint
            WHERE runtime_session.token_hash = ?
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()

    def list_runtime_audio_assets(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        learning_session_id: str,
        upstream_classroom_id: str,
        now: int,
    ) -> list[DatabaseRow]:
        """Resolve the immutable formal-audio sidecar for one live session.

        This is deliberately a read-only, exact-identity join.  The caller
        still verifies every contract field and the bytes on disk before an
        asset can be exposed through the student runtime gateway.
        """

        return list(
            conn.execute(
                """
                SELECT runtime_session.id AS runtime_session_id,
                  runtime_session.learning_session_id,
                  runtime_session.expires_at AS runtime_session_expires_at,
                  runtime_session.revoked_at AS runtime_session_revoked_at,
                  runtime.id AS runtime_classroom_id,
                  runtime.upstream_classroom_id,
                  runtime.status AS runtime_status,
                  runtime.quality_status AS runtime_quality_status,
                  runtime.retired_at AS runtime_retired_at,
                  runtime.feature_manifest_json,
                  runtime.candidate_binding_contract_version,
                  formal_binding.runtime_binding_contract_version,
                  audio.build_item_id, audio.state AS audio_job_state,
                  audio.classroom_content_sha256,
                  audio.audio_contract_version,
                  audio.expected_segment_count,
                  audio.tts_attempted_count, audio.tts_completed_count,
                  audio.audio_validated_count, audio.asr_attempted_count,
                  audio.asr_passed_count,
                  audio.tts_provider_id, audio.tts_model_id,
                  audio.tts_voice_id, audio.tts_fallback_allowed,
                  audio.terminal_receipt_hash,
                  segment.scene_order, segment.scene_id, segment.action_id,
                  segment.state AS segment_state,
                  segment.runtime_audio_sha256,
                  segment.download_sha256, segment.streamed_sha256,
                  segment.readback_sha256, segment.storage_key,
                  segment.asset_id, segment.mime_type AS segment_mime_type,
                  segment.byte_size AS segment_byte_size,
                  segment.duration_ms AS segment_duration_ms,
                  segment.pcm_format, segment.channel_count,
                  segment.bits_per_sample, segment.sample_rate_hz,
                  segment.block_align, segment.safe_error_code,
                  segment.machine_receipt_hash,
                  asset.kind AS asset_kind,
                  asset.storage_key AS asset_storage_key,
                  asset.content_hash AS asset_content_hash,
                  asset.mime_type AS asset_mime_type,
                  asset.byte_size AS asset_byte_size,
                  asset.duration_ms AS asset_duration_ms,
                  asset.scan_status AS asset_scan_status,
                  asset.moderation_status AS asset_moderation_status,
                  asset.transcode_status AS asset_transcode_status,
                  asset.status AS asset_status,
                  variant.variant_key,
                  variant.storage_key AS variant_storage_key,
                  variant.content_hash AS variant_content_hash,
                  variant.mime_type AS variant_mime_type,
                  variant.byte_size AS variant_byte_size,
                  variant.duration_ms AS variant_duration_ms,
                  variant.status AS variant_status
                FROM student_openmaic_runtime_sessions AS runtime_session
                JOIN learning_sessions AS session
                  ON session.id = runtime_session.learning_session_id
                 AND session.family_id = runtime_session.family_id
                 AND session.child_id = runtime_session.child_id
                JOIN learning_openmaic_runtime_classrooms AS runtime
                  ON runtime.id = runtime_session.runtime_classroom_id
                JOIN learning_student_formal_session_bindings AS formal_binding
                  ON formal_binding.learning_session_id = session.id
                 AND formal_binding.family_id = runtime_session.family_id
                 AND formal_binding.child_id = runtime_session.child_id
                 AND formal_binding.runtime_classroom_id = runtime.id
                 AND formal_binding.upstream_classroom_id =
                   runtime.upstream_classroom_id
                 AND formal_binding.build_item_id =
                   runtime.candidate_build_item_id
                 AND formal_binding.release_id = runtime.candidate_release_id
                 AND formal_binding.grade_code = runtime.candidate_grade_code
                 AND formal_binding.target_fingerprint =
                   runtime.candidate_target_fingerprint
                 AND formal_binding.runtime_binding_contract_version =
                   runtime.candidate_binding_contract_version
                 AND formal_binding.course_id = session.course_id
                 AND formal_binding.course_version = session.course_version
                 AND formal_binding.package_id = session.lesson_package_id
                 AND formal_binding.package_version =
                   session.lesson_package_version
                 AND formal_binding.package_content_hash =
                   session.lesson_package_content_hash
                JOIN learning_formal_qwen_audio_jobs AS audio
                  ON audio.build_item_id = formal_binding.build_item_id
                 AND audio.release_id = formal_binding.release_id
                 AND audio.grade_code = formal_binding.grade_code
                 AND audio.target_fingerprint =
                   formal_binding.target_fingerprint
                 AND audio.runtime_classroom_id = runtime.id
                 AND audio.upstream_classroom_id =
                   runtime.upstream_classroom_id
                 AND audio.course_id = formal_binding.course_id
                 AND audio.course_version = formal_binding.course_version
                 AND audio.package_id = formal_binding.package_id
                 AND audio.package_version = formal_binding.package_version
                JOIN learning_formal_qwen_audio_segment_receipts AS segment
                  ON segment.build_item_id = audio.build_item_id
                JOIN learning_media_assets AS asset
                  ON asset.id = segment.asset_id
                JOIN learning_media_asset_variants AS variant
                  ON variant.asset_id = asset.id
                 AND variant.variant_key = 'original'
                WHERE runtime_session.id = ?
                  AND runtime_session.learning_session_id = ?
                  AND runtime.upstream_classroom_id = ?
                  AND runtime_session.revoked_at IS NULL
                  AND runtime_session.expires_at >= ?
                ORDER BY segment.scene_order ASC
                """,
                (
                    runtime_session_id,
                    learning_session_id,
                    upstream_classroom_id,
                    int(now),
                ),
            ).fetchall()
        )

    def touch_runtime_session(
        self,
        conn: DatabaseConnection,
        *,
        runtime_session_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_openmaic_runtime_sessions
            SET last_active_at = ? WHERE id = ?
            """,
            (now, runtime_session_id),
        )

    def create_conversation_probe(
        self, conn: DatabaseConnection, *, probe_id: str, ticket_hash: str,
        runtime_classroom_id: str, upstream_classroom_id: str, challenge: str,
        expires_at: int, now: int, candidate_kind: str = "release",
        deterministic_recovery_id: str | None = None,
        tts_credential_recovery_id: str | None = None,
    ) -> None:
        conn.execute(
            """INSERT INTO learning_openmaic_conversation_probes(
              id,ticket_hash,runtime_classroom_id,upstream_classroom_id,
              candidate_kind,deterministic_recovery_id,
              tts_credential_recovery_id,challenge,
              expires_at,created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (probe_id, ticket_hash, runtime_classroom_id, upstream_classroom_id,
             candidate_kind, deterministic_recovery_id,
             tts_credential_recovery_id, challenge, expires_at, now),
        )

    def get_conversation_probe_by_ticket_for_update(
        self, conn: DatabaseConnection, *, ticket_hash: str
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM learning_openmaic_conversation_probes WHERE ticket_hash = ? LIMIT 1 FOR UPDATE",
            (ticket_hash,),
        ).fetchone()

    def get_conversation_probe_by_runtime_token_for_update(
        self, conn: DatabaseConnection, *, runtime_token_hash: str
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM learning_openmaic_conversation_probes WHERE runtime_token_hash = ? LIMIT 1 FOR UPDATE",
            (runtime_token_hash,),
        ).fetchone()

    def get_conversation_probe_by_id_for_update(
        self, conn: DatabaseConnection, *, probe_id: str
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM learning_openmaic_conversation_probes WHERE id = ? LIMIT 1 FOR UPDATE",
            (probe_id,),
        ).fetchone()

    def get_conversation_probe_by_runtime_classroom_for_update(
        self, conn: DatabaseConnection, *, runtime_classroom_id: str
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM learning_openmaic_conversation_probes "
            "WHERE runtime_classroom_id = ? LIMIT 1 FOR UPDATE",
            (runtime_classroom_id,),
        ).fetchone()

    def consume_conversation_probe_ticket(
        self, conn: DatabaseConnection, *, probe_id: str, runtime_token_hash: str,
        runtime_session_id: str, now: int
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_conversation_probes
            SET consumed_at = ?, runtime_token_hash = ?, runtime_session_id = ?
            WHERE id = ? AND consumed_at IS NULL AND revoked_at IS NULL""",
            (now, runtime_token_hash, runtime_session_id, probe_id),
        )
        return updated.rowcount == 1

    def finalize_conversation_probe(
        self, conn: DatabaseConnection, *, probe_id: str,
        chat_receipt: Mapping[str, Any], transcription_receipt: Mapping[str, Any], now: int
    ) -> bool:
        updated = conn.execute(
            """UPDATE learning_openmaic_conversation_probes
            SET chat_receipt_json = ?, transcription_receipt_json = ?,
                finalized_at = ?, revoked_at = ?
            WHERE id = ? AND consumed_at IS NOT NULL AND revoked_at IS NULL
              AND finalized_at IS NULL""",
            (self.encode_json(chat_receipt), self.encode_json(transcription_receipt), now, now, probe_id),
        )
        return updated.rowcount == 1
