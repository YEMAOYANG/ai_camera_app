from __future__ import annotations

from services.learning_curriculum_preparation_contract import (canonical_preparation_target_for, formal_target_course_count, preparation_authority_grade)
from core.security import now_ms as current_time_ms

import json
import hashlib
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from core.database import Database, DatabaseConnection, DatabaseRow
from integrations.openmaic_formal_media import compatible_preparation_target
from repositories.formal_student_runtime_gate import (
    current_formal_runtime_sql,
    current_formal_validation_authority_sql,
)
from services.lesson_package_validator import (
    FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
    FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
)


class LessonPackageRepository:
    CANDIDATE_BINDING_CONTRACT_VERSION = (
        "mira.learning.candidate-runtime-binding.v1"
    )

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
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        job_id = f"classroom_job_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_classroom_generation_jobs(
              id, request_id, course_id, course_version, generator, status,
              created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'openmaic', 'pending', ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (job_id, request_id, course_id, course_version, now, now),
        )
        row = self.get_job_by_request(conn, request_id=request_id)
        return row, bool(row and row["id"] == job_id)

    def get_job_by_request(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_classroom_generation_jobs
            WHERE request_id = ?
            LIMIT 1
            """
            + lock,
            (request_id,),
        ).fetchone()

    def get_next_pending_job(
        self,
        conn: DatabaseConnection,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_classroom_generation_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """
        ).fetchone()

    def get_next_formal_candidate_authority(
        self, conn: DatabaseConnection, *, preparation_plan: Mapping[str, Any] | None = None
    ) -> DatabaseRow | None:
        """Return one exact V2 content-ready item safe to issue.

        Before the three content canaries pass, only a canary item may enter
        Runtime.  Afterwards, the remaining items may progress independently
        while content generation continues. Pending/generating/ready/
        quarantined histories are deliberately not selected. A retry is
        eligible only after one explicit, known formal rejection.
        """

        from services.learning_curriculum_preparation_contract import (
            build_preparation_target,
            compatible_preparation_scope_sql,
        )

        # The no-plan path is the existing bounded Grade-1 operator entry.
        # Every automatic scheduler call supplies its exact leased plan.
        current_target = (canonical_preparation_target_for(preparation_plan)
                          if preparation_plan is not None else build_preparation_target("primary_1"))
        grade_code = preparation_authority_grade(current_target)
        target_count = formal_target_course_count(current_target)
        target_scope, target_params = compatible_preparation_scope_sql(
            current_target, target_column="plan.target_spec_json", fingerprint_column="plan.target_fingerprint",
            automatic_only=True,
        )
        plan_scope = ""
        plan_params = ()
        if preparation_plan is not None:
            if any(not preparation_plan.get(field) for field in ("id", "lease_token", "catalog_build_id", "catalog_release_id", "target_fingerprint")):
                raise ValueError("automatic Runtime candidate scope is incomplete")
            plan_scope = " AND plan.id = ? AND plan.lease_token = ? AND plan.lease_expires_at > ? AND plan.target_fingerprint = ? AND build.id = ? AND release_row.id = ?"
            plan_params = (preparation_plan["id"], preparation_plan["lease_token"], current_time_ms(),
                           preparation_plan["target_fingerprint"], preparation_plan["catalog_build_id"], preparation_plan["catalog_release_id"])
        candidates = list(conn.execute(
            f"""
            SELECT item.id AS build_item_id, item.course_id, item.course_version,
              item.skill_id, item.variant_ordinal,
              build.target_spec_json, release_row.id AS release_id,
              plan.id AS preparation_plan_id,
              plan.target_fingerprint,
              course.grade_code, course.subject, course.node_code,
              course.title, course.objective, course.content_json,
              (
                SELECT COUNT(*) + 1
                FROM learning_openmaic_runtime_classrooms AS attempt_count
                WHERE attempt_count.candidate_build_item_id = item.id
              ) AS attempt_ordinal
            FROM learning_catalog_build_items AS item
            JOIN learning_catalog_build_jobs AS build
              ON build.id = item.build_job_id
             AND build.release_id = item.release_id
             AND build.execution_mode = 'content_only'
             AND build.stage_ceiling = 'content_ready'
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = item.release_id
             AND release_row.status = 'draft'
             AND release_row.quality_status = 'building'
             AND release_row.activated_at IS NULL
             AND release_row.retired_at IS NULL
             AND release_row.ready_item_count BETWEEN 0 AND {target_count - 1}
            JOIN learning_curriculum_preparation_plans AS plan
              ON plan.catalog_build_id = build.id
             AND plan.catalog_release_id = release_row.id
             AND plan.shared_build_request_id = build.request_id
             AND plan.target_spec_json = build.target_spec_json
             AND plan.curriculum_version = build.curriculum_version
             AND plan.status = 'running'
             AND plan.stage IN (
               'generating_content', 'building_classrooms',
               'generating_speech', 'validating', 'publishing'
             )
             AND plan.content_target_count = {target_count}
             AND plan.content_candidate_count BETWEEN 1 AND {target_count}
             AND (plan.content_failed_count = 0 OR plan.library_target_fingerprint IS NOT NULL)
             AND plan.content_canary_target_count = 3
             AND plan.content_canary_candidate_count BETWEEN 0 AND 3
             AND (plan.content_canary_failed_count = 0 OR plan.library_target_fingerprint IS NOT NULL)
             AND plan.ready_course_count = 0
             AND plan.failed_course_count = 0
             AND plan.completed_at IS NULL
             AND plan.superseded_at IS NULL
              AND plan.error_code IS NULL
              AND plan.error_message_safe IS NULL
            JOIN learning_openmaic_provider_circuits AS provider_circuit
              ON provider_circuit.circuit_key =
                'formal-generation:deepseek:deepseek-v4-pro'
             AND provider_circuit.provider_id = 'deepseek'
             AND provider_circuit.model_id = 'deepseek-v4-pro'
             AND provider_circuit.status = 'closed'
             AND provider_circuit.probe_succeeded_at IS NOT NULL
            JOIN learning_courses AS course
              ON course.id = item.course_id
             AND course.version = item.course_version
             AND course.retired_at IS NULL
            WHERE item.content_phase = 'course_ready'
              AND item.status = 'course_ready'
              AND item.content_gate_status = 'passed'
              AND item.content_receipt_hash IS NOT NULL
              AND item.execution_mode_snapshot = 'content_only'
              AND item.content_manifest_version_snapshot = build.content_manifest_version
              AND build.status IN ('queued', 'running')
              AND build.total_item_count = {target_count}
              AND build.ready_item_count = 0
              AND build.failed_item_count = 0
              AND build.error_code IS NULL
              AND build.error_message_safe IS NULL
              AND build.completed_at IS NULL
              AND JSON_UNQUOTE(JSON_EXTRACT(
                    plan.target_spec_json, '$.schemaVersion'
                  )) = 'mira.learning.preparation-target.v2'
              AND JSON_UNQUOTE(JSON_EXTRACT(
                    plan.target_spec_json, '$.gradeCode'
                  )) = item.grade_code
              AND item.grade_code = ?
              AND course.grade_code = item.grade_code AND plan.grade_code = item.grade_code
              AND {target_scope}
              {plan_scope}
              AND (plan.library_target_fingerprint IS NOT NULL OR NOT EXISTS (
                SELECT 1 FROM learning_curriculum_preparation_plans AS library_owner
                WHERE library_owner.library_target_fingerprint = plan.target_fingerprint
              ))
              AND (plan.library_target_fingerprint IS NULL OR NOT EXISTS (
                SELECT 1 FROM learning_course_supply_incidents AS incident
                WHERE incident.build_item_id = item.id AND incident.resolved_at IS NULL
              ))
              AND (plan.library_target_fingerprint IS NULL OR EXISTS (
                SELECT 1 FROM learning_course_supply_requests AS request
                WHERE request.target_fingerprint = plan.target_fingerprint
                  AND request.subject = item.subject AND request.skill_id = item.skill_id
                  AND request.variant_ordinal = item.variant_ordinal AND request.enabled = TRUE
              ))
              AND (
                plan.content_canary_passed_at IS NOT NULL
                OR JSON_CONTAINS(
                  build.canary_manifest_json,
                  JSON_OBJECT(
                    'subject', item.subject,
                    'skillId', item.skill_id,
                    'variantOrdinal', item.variant_ordinal
                  ),
                  '$.targets'
                ) = 1
              )
              AND NOT EXISTS (
                SELECT 1
                FROM learning_curriculum_grade_release_pointers AS pointer
                WHERE pointer.release_id = item.release_id
                  AND pointer.pointer_revision >= 1
              )
              AND NOT EXISTS (
                SELECT 1
                FROM learning_openmaic_runtime_classrooms AS blocked
                WHERE blocked.candidate_build_item_id = item.id
                  AND (
                    blocked.status IN ('pending', 'generating', 'ready', 'recovering')
                    OR blocked.quality_status = 'quarantined'
                    OR blocked.status <> 'failed'
                    OR blocked.quality_status <> 'rejected'
                    OR blocked.error_code NOT LIKE 'openmaic_formal_%%'
                    OR blocked.error_code LIKE '%%ambiguous%%'
                    OR blocked.upstream_job_id IS NULL
                    OR blocked.retired_at IS NOT NULL
                  )
              )
              AND NOT EXISTS (
                SELECT 1
                FROM learning_openmaic_formal_citation_recoveries AS recovery
                WHERE recovery.build_item_id = item.id
                  AND recovery.status IN ('reserving', 'running', 'succeeded')
              )
              AND (
                SELECT COUNT(*)
                FROM learning_openmaic_runtime_classrooms AS attempts
                WHERE attempts.candidate_build_item_id = item.id
                  AND attempts.provider_attempt_ordinal IS NOT NULL
              ) < 3
            ORDER BY plan.created_at, plan.id,
              CASE item.subject
                WHEN 'chinese' THEN 1 WHEN 'math' THEN 2
                WHEN 'english' THEN 3 ELSE 4
              END,
              item.subject_ordinal, item.boundary_ordinal,
              item.variant_ordinal, item.id
            LIMIT {target_count}
            """,
            (grade_code, *target_params, *plan_params),
        ).fetchall())
        from repositories.course_supply_inventory import published_supply
        playable = published_supply(conn, current_target)
        for candidate in candidates:
            key = (str(candidate["subject"]), str(candidate["skill_id"]), int(candidate["variant_ordinal"]))
            if key in playable:
                continue
            if preparation_plan is not None:
                candidate = dict(candidate)
                candidate["scheduler_lease_token"] = preparation_plan["lease_token"]
                candidate["scheduler_build_id"] = preparation_plan["catalog_build_id"]
            return candidate
        return None

    def reserve_formal_runtime_package(
        self,
        conn: DatabaseConnection,
        *,
        authority: Mapping[str, Any],
        package_id: str,
        target_fingerprint: str,
        public_payload: Mapping[str, Any],
        private_payload: Mapping[str, Any],
        public_hash: str,
        private_hash: str,
        validation_report: Mapping[str, Any],
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        item_id = str(authority.get("build_item_id") or "")
        plan_id = str(authority.get("preparation_plan_id") or "")
        course_id = str(authority.get("course_id") or "")
        course_version = str(authority.get("course_version") or "")
        if not item_id or not plan_id or not course_id or not course_version:
            raise ValueError("formal package authority is incomplete")
        if len(package_id) > 128 or not package_id:
            raise ValueError("formal package id is invalid")
        for digest in (target_fingerprint, public_hash, private_hash):
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("formal package digest is invalid")
        from services.learning_curriculum_preparation_contract import (
            build_preparation_target,
            preparation_target_fingerprint,
        )

        current_target = canonical_preparation_target_for(authority)
        target_count = formal_target_course_count(current_target)
        try:
            persisted_target = json.loads(str(authority.get("target_spec_json") or ""))
            valid_target = (compatible_preparation_target(persisted_target, current_target)
                            and target_fingerprint == preparation_target_fingerprint(persisted_target))
        except (TypeError, ValueError):
            valid_target = False
        if not valid_target:
            raise ValueError("formal package target contract is stale")
        persisted_target_json = self.encode_json(persisted_target)
        scheduler_scope = ""
        scheduler_params = ()
        if authority.get("scheduler_lease_token") is not None:
            scheduler_scope = " AND plan.lease_token = ? AND plan.lease_expires_at > ? AND build.id = ?"
            scheduler_params = (authority["scheduler_lease_token"], int(now), authority["scheduler_build_id"])
        locked = conn.execute(
            f"""
            SELECT item.id AS build_item_id, item.course_id, item.course_version,
              build.execution_mode, build.stage_ceiling, build.status AS build_status,
              release_row.status AS release_status,
              release_row.quality_status AS release_quality_status,
              release_row.retired_at AS release_retired_at,
              plan.target_fingerprint, course.content_json
            FROM learning_catalog_build_items AS item
            JOIN learning_catalog_build_jobs AS build
              ON build.id = item.build_job_id
             AND build.release_id = item.release_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = item.release_id
            JOIN learning_curriculum_preparation_plans AS plan
              ON plan.id = ?
             AND plan.catalog_build_id = build.id
             AND plan.catalog_release_id = release_row.id
             AND plan.shared_build_request_id = build.request_id
             AND plan.target_spec_json = build.target_spec_json
             AND plan.curriculum_version = build.curriculum_version
             AND plan.status = 'running'
             AND plan.stage IN (
               'generating_content', 'building_classrooms',
               'generating_speech', 'validating', 'publishing'
             )
             AND plan.content_target_count = {target_count}
             AND plan.content_candidate_count BETWEEN 1 AND {target_count}
             AND plan.content_failed_count = 0
             AND plan.content_canary_target_count = 3
             AND plan.content_canary_candidate_count BETWEEN 0 AND 3
             AND plan.content_canary_failed_count = 0
             AND plan.ready_course_count = 0
             AND plan.failed_course_count = 0
             AND plan.completed_at IS NULL
             AND plan.superseded_at IS NULL
             AND plan.error_code IS NULL
             AND plan.error_message_safe IS NULL
            JOIN learning_courses AS course
              ON course.id = item.course_id
             AND course.version = item.course_version
            WHERE item.id = ? AND item.course_id = ? AND item.course_version = ?
              AND item.content_phase = 'course_ready'
              AND item.status = 'course_ready'
              AND item.content_gate_status = 'passed'
              AND item.content_receipt_hash IS NOT NULL
              AND item.execution_mode_snapshot = 'content_only'
              AND item.content_manifest_version_snapshot = build.content_manifest_version
              AND build.status IN ('queued', 'running')
              AND build.total_item_count = {target_count}
              AND build.ready_item_count = 0
              AND build.failed_item_count = 0
              AND build.error_code IS NULL
              AND build.error_message_safe IS NULL
              AND build.completed_at IS NULL
              AND release_row.status = 'draft'
              AND release_row.quality_status = 'building'
              AND release_row.activated_at IS NULL
              AND release_row.retired_at IS NULL
              AND release_row.ready_item_count BETWEEN 0 AND {target_count - 1}
              AND item.grade_code = course.grade_code
              AND item.grade_code = plan.grade_code
              AND item.grade_code = ?
              {scheduler_scope}
              AND plan.target_fingerprint = ?
              AND plan.target_spec_json = ?
              AND (plan.library_target_fingerprint IS NULL OR EXISTS (
                SELECT 1 FROM learning_course_supply_requests AS request
                WHERE request.target_fingerprint = plan.target_fingerprint
                  AND request.subject = item.subject AND request.skill_id = item.skill_id
                  AND request.variant_ordinal = item.variant_ordinal AND request.enabled = TRUE
              ))
              AND JSON_UNQUOTE(JSON_EXTRACT(
                    plan.target_spec_json, '$.schemaVersion'
                  )) = 'mira.learning.preparation-target.v2'
              AND (
                plan.content_canary_passed_at IS NOT NULL
                OR JSON_CONTAINS(
                  build.canary_manifest_json,
                  JSON_OBJECT(
                    'subject', item.subject,
                    'skillId', item.skill_id,
                    'variantOrdinal', item.variant_ordinal
                  ),
                  '$.targets'
                ) = 1
              )
            LIMIT 1 FOR UPDATE
            """,
            (
                plan_id,
                item_id,
                course_id,
                course_version,
                preparation_authority_grade(authority),
                *scheduler_params,
                target_fingerprint,
                persisted_target_json,
            ),
        ).fetchone()
        if locked is None or not (
            str(locked.get("execution_mode") or "") == "content_only"
            and str(locked.get("stage_ceiling") or "") == "content_ready"
            and str(locked.get("build_status") or "") in {"queued", "running"}
            and str(locked.get("release_status") or "") == "draft"
            and str(locked.get("release_quality_status") or "") == "building"
            and locked.get("release_retired_at") is None
            and str(locked.get("target_fingerprint") or "")
            == target_fingerprint
        ):
            raise ValueError("formal package authority is not content-ready")
        course_hash = hashlib.sha256(
            str(locked.get("content_json") or "").encode("utf-8")
        ).hexdigest()
        existing = self.get_package_any_status(
            conn, package_id=package_id, package_version=1
        )
        if existing is not None:
            exact = (
                str(existing.get("course_id") or "") == course_id
                and str(existing.get("course_version") or "") == course_version
                and str(existing.get("status") or "") == "candidate"
                and str(existing.get("schema_version") or "")
                == str(public_payload.get("schemaVersion") or "")
                and str(existing.get("public_content_hash") or "") == public_hash
                and str(existing.get("private_content_hash") or "") == private_hash
                and str(existing.get("source_course_content_hash") or "")
                == course_hash
                and self.decode_json(existing.get("public_payload_json"))
                == dict(public_payload)
                and existing.get("published_at") is None
                and existing.get("retired_at") is None
            )
            if not exact:
                raise ValueError("formal package identity conflict")
            return existing, False

        seed = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:48]
        job_id = f"formal_runtime_job_{seed}"
        request_id = f"formal-package-{seed}"
        artifact_id = f"formal_runtime_source_{seed}"
        source_payload = {
            "schemaVersion": FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
            "buildItemId": item_id,
            "targetFingerprint": target_fingerprint,
            "sourceCourseContentSha256": str(
                public_payload.get("sourceCourseContentSha256") or ""
            ),
            "teachingBriefSha256": str(
                public_payload.get("teachingBriefSha256") or ""
            ),
            "publicationEligible": False,
        }
        source_json = self.encode_json(source_payload)
        conn.execute(
            """
            INSERT INTO learning_classroom_generation_jobs(
              id, request_id, course_id, course_version, generator, status,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'formal_package_authority', 'staged', ?, ?)
            """,
            (
                job_id,
                request_id,
                course_id,
                course_version,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_classroom_source_artifacts(
              id, job_id, request_id, source_format, source_package_version,
              dsl_version, status, source_hash, payload_json,
              validation_report_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'mira.openmaic.formal-runtime-package-source.v1',
              '1', 'formal-runtime-v1', 'compiled', ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                job_id,
                request_id,
                hashlib.sha256(source_json.encode("utf-8")).hexdigest(),
                source_json,
                self.encode_json(validation_report),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_lesson_packages(
              id, version, course_id, course_version,
              source_course_content_hash, schema_version, status,
              source_artifact_id, compiler_version, public_content_hash,
              private_content_hash, public_payload_json,
              validation_report_json, created_at, published_at, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, 'candidate', ?,
              ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                package_id,
                course_id,
                course_version,
                course_hash,
                public_payload["schemaVersion"],
                artifact_id,
                FORMAL_RUNTIME_PACKAGE_COMPILER_VERSION,
                public_hash,
                private_hash,
                self.encode_json(public_payload),
                self.encode_json(validation_report),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_lesson_package_private(
              package_id, package_version, schema_version, payload_json,
              content_hash, created_at, updated_at
            ) VALUES (?, 1, ?, ?, ?, ?, ?)
            """,
            (
                package_id,
                private_payload["schemaVersion"],
                self.encode_json(private_payload),
                private_hash,
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET source_artifact_id = ?, package_id = ?, package_version = 1,
              updated_at = ? WHERE id = ?
            """,
            (artifact_id, package_id, now, job_id),
        )
        package = self.get_package_any_status(
            conn, package_id=package_id, package_version=1
        )
        if package is None:
            raise RuntimeError("formal package disappeared after reservation")
        return package, True

    def claim_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        now: int,
        stale_before: int | None = None,
    ) -> bool:
        stale_before = int(stale_before if stale_before is not None else -1)
        cursor = conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET status = 'generating', started_at = COALESCE(started_at, ?),
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND (
              status = 'pending'
              OR (status = 'generating' AND updated_at < ?)
            )
            """,
            (now, now, job_id, stale_before),
        )
        return cursor.rowcount == 1

    def create_source_artifact(
        self,
        conn: DatabaseConnection,
        *,
        job: Mapping[str, Any],
        source_format: str,
        source_package_version: str,
        dsl_version: str,
        source_hash: str,
        payload_json: str,
        now: int,
    ) -> DatabaseRow:
        artifact_id = f"classroom_source_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_classroom_source_artifacts(
              id, job_id, request_id, source_format,
              source_package_version, dsl_version, status, source_hash,
              payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'quarantined', ?, ?, ?, ?)
            """,
            (
                artifact_id,
                job["id"],
                job["request_id"],
                source_format,
                source_package_version or None,
                dsl_version,
                source_hash,
                payload_json,
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET source_artifact_id = ?, updated_at = ? WHERE id = ?
            """,
            (artifact_id, now, job["id"]),
        )
        return self.get_source_artifact(conn, artifact_id=artifact_id)

    def get_source_artifact(
        self,
        conn: DatabaseConnection,
        *,
        artifact_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_classroom_source_artifacts
            WHERE id = ? LIMIT 1
            """,
            (artifact_id,),
        ).fetchone()

    def update_source_status(
        self,
        conn: DatabaseConnection,
        *,
        artifact_id: str,
        status: str,
        validation_report: Mapping[str, Any],
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_classroom_source_artifacts
            SET status = ?, validation_report_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, self.encode_json(validation_report), now, artifact_id),
        )

    def publish_package(
        self,
        conn: DatabaseConnection,
        *,
        job: Mapping[str, Any],
        artifact_id: str,
        package_id: str,
        course_content_hash: str,
        public_payload: Mapping[str, Any],
        private_payload: Mapping[str, Any],
        public_hash: str,
        private_hash: str,
        compiler_version: str,
        validation_report: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        current = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0) AS maximum
            FROM learning_lesson_packages
            WHERE id = ? FOR UPDATE
            """,
            (package_id,),
        ).fetchone()
        version = int((current or {}).get("maximum") or 0) + 1
        public_json = self.encode_json(public_payload)
        private_json = self.encode_json(private_payload)
        conn.execute(
            """
            INSERT INTO learning_lesson_packages(
              id, version, course_id, course_version,
              source_course_content_hash, schema_version, status,
              source_artifact_id, compiler_version, public_content_hash,
              private_content_hash, public_payload_json,
              validation_report_json, created_at, published_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package_id,
                version,
                job["course_id"],
                job["course_version"],
                course_content_hash,
                public_payload["schemaVersion"],
                artifact_id,
                compiler_version,
                public_hash,
                private_hash,
                public_json,
                self.encode_json(validation_report),
                now,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_lesson_package_private(
              package_id, package_version, schema_version, payload_json,
              content_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package_id,
                version,
                private_payload["schemaVersion"],
                private_json,
                private_hash,
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_course_lesson_package_bindings(
              course_id, course_version, package_id, package_version, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              package_id = VALUES(package_id),
              package_version = VALUES(package_version),
              updated_at = VALUES(updated_at)
            """,
            (
                job["course_id"],
                job["course_version"],
                package_id,
                version,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE learning_classroom_source_artifacts
            SET status = 'compiled', validation_report_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (self.encode_json(validation_report), now, artifact_id),
        )
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET status = 'published', package_id = ?, package_version = ?,
              completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (package_id, version, now, now, job["id"]),
        )
        return self.get_package(
            conn,
            package_id=package_id,
            package_version=version,
        )

    def stage_package_for_media(
        self,
        conn: DatabaseConnection,
        *,
        job: Mapping[str, Any],
        artifact_id: str,
        package_id: str,
        course_content_hash: str,
        public_payload: Mapping[str, Any],
        private_payload: Mapping[str, Any],
        public_hash: str,
        private_hash: str,
        compiler_version: str,
        validation_report: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        """Persist a validated package privately without making it student-visible."""

        current = conn.execute(
            """
            SELECT COALESCE(MAX(version), 0) AS maximum
            FROM learning_lesson_packages
            WHERE id = ? FOR UPDATE
            """,
            (package_id,),
        ).fetchone()
        version = int((current or {}).get("maximum") or 0) + 1
        conn.execute(
            """
            INSERT INTO learning_lesson_packages(
              id, version, course_id, course_version,
              source_course_content_hash, schema_version, status,
              source_artifact_id, compiler_version, public_content_hash,
              private_content_hash, public_payload_json,
              validation_report_json, created_at, published_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'media_pending', ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                package_id,
                version,
                job["course_id"],
                job["course_version"],
                course_content_hash,
                public_payload["schemaVersion"],
                artifact_id,
                compiler_version,
                public_hash,
                private_hash,
                self.encode_json(public_payload),
                self.encode_json(validation_report),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_lesson_package_private(
              package_id, package_version, schema_version, payload_json,
              content_hash, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package_id,
                version,
                private_payload["schemaVersion"],
                self.encode_json(private_payload),
                private_hash,
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE learning_classroom_source_artifacts
            SET status = 'media_pending', validation_report_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (self.encode_json(validation_report), now, artifact_id),
        )
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET status = 'media_pending', package_id = ?, package_version = ?,
              completed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (package_id, version, now, job["id"]),
        )
        row = self.get_package_any_status(
            conn,
            package_id=package_id,
            package_version=version,
        )
        if row is None:
            raise RuntimeError("staged lesson package could not be read")
        return row

    def get_package_media_status(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
    ) -> dict[str, Any]:
        package = self.get_package_any_status(
            conn,
            package_id=package_id,
            package_version=package_version,
        )
        if package is None:
            return {"status": "not_found", "reason": "package_not_found"}
        if str(package["status"]) == "published":
            return {
                "status": "published",
                "reason": None,
                "jobCount": 0,
                "expectedSegmentCount": 0,
                "readySegmentCount": 0,
            }
        jobs = list(
            conn.execute(
                """
                SELECT * FROM learning_media_generation_jobs
                WHERE package_id = ? AND package_version = ?
                ORDER BY created_at ASC, id ASC
                """,
                (package_id, package_version),
            ).fetchall()
        )
        if not jobs:
            return {
                "status": "media_pending",
                "reason": "media_job_missing",
                "jobCount": 0,
                "expectedSegmentCount": 0,
                "readySegmentCount": 0,
            }
        job_statuses = {str(job["status"]) for job in jobs}
        if "rejected" in job_statuses:
            state = "rejected"
            reason = "media_review_rejected"
        elif "failed" in job_statuses:
            state = "failed"
            reason = "media_generation_failed"
        else:
            state = "media_pending"
            reason = "media_not_ready"
        expected = sum(int(job.get("segment_count") or 0) for job in jobs)
        segments = list(
            conn.execute(
                """
                SELECT segment.*, job.status AS job_status,
                  asset.status AS asset_status,
                  asset.scan_status, asset.moderation_status,
                  asset.transcode_status,
                  package_asset.asset_id AS bound_asset_id
                FROM learning_media_generation_jobs AS job
                JOIN learning_narration_segments AS segment ON segment.job_id = job.id
                LEFT JOIN learning_media_assets AS asset ON asset.id = segment.asset_id
                LEFT JOIN learning_lesson_package_assets AS package_asset
                  ON package_asset.package_id = job.package_id
                 AND package_asset.package_version = job.package_version
                 AND package_asset.asset_id = segment.asset_id
                 AND package_asset.scene_id = segment.scene_id
                 AND package_asset.usage_kind = 'narration'
                 AND package_asset.required_asset = 1
                WHERE job.package_id = ? AND job.package_version = ?
                ORDER BY job.created_at ASC, segment.segment_index ASC
                """,
                (package_id, package_version),
            ).fetchall()
        )
        ready = 0
        for segment in segments:
            if str(segment.get("status")) != "ready":
                continue
            if str(segment.get("job_status")) != "ready":
                continue
            if str(segment.get("asset_status")) != "ready":
                continue
            if str(segment.get("scan_status")) != "passed":
                continue
            if str(segment.get("moderation_status")) != "passed":
                continue
            if str(segment.get("transcode_status")) not in {"passed", "not_required"}:
                continue
            if not segment.get("bound_asset_id"):
                continue
            unapproved = conn.execute(
                """
                SELECT 1 FROM learning_media_quality_reviews
                WHERE asset_id = ? AND required_review = 1
                  AND status <> 'approved'
                LIMIT 1
                """,
                (segment["asset_id"],),
            ).fetchone()
            if unapproved is None:
                ready += 1
        if (
            expected > 0
            and len(segments) == expected
            and ready == expected
            and job_statuses == {"ready"}
        ):
            state = "ready"
            reason = None
        return {
            "status": state,
            "reason": reason,
            "jobCount": len(jobs),
            "expectedSegmentCount": expected,
            "readySegmentCount": ready,
            "jobs": [
                {
                    "id": str(job["id"]),
                    "status": str(job["status"]),
                    "error": (
                        {
                            "code": str(job["error_code"]),
                            "message": str(job.get("error_message_safe") or ""),
                        }
                        if job.get("error_code")
                        else None
                    ),
                }
                for job in jobs
            ],
        }

    def publish_staged_package(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
        now: int,
    ) -> DatabaseRow | None:
        package = self.get_package_any_status(
            conn,
            package_id=package_id,
            package_version=package_version,
            for_update=True,
        )
        if package is None:
            return None
        if str(package["status"]) == "published":
            return package
        if str(package["status"]) != "media_pending":
            return package
        media = self.get_package_media_status(
            conn,
            package_id=package_id,
            package_version=package_version,
        )
        if media["status"] != "ready":
            return package
        public_payload = self.decode_json(package["public_payload_json"])
        if public_payload is None:
            raise RuntimeError("staged lesson package public payload is invalid")
        narration_rows = conn.execute(
            """
            SELECT segment.action_id, segment.asset_id
            FROM learning_media_generation_jobs AS job
            JOIN learning_narration_segments AS segment ON segment.job_id = job.id
            JOIN learning_lesson_package_assets AS package_asset
              ON package_asset.package_id = job.package_id
             AND package_asset.package_version = job.package_version
             AND package_asset.asset_id = segment.asset_id
             AND package_asset.scene_id = segment.scene_id
             AND package_asset.usage_kind = 'narration'
             AND package_asset.required_asset = 1
            WHERE job.package_id = ? AND job.package_version = ?
              AND job.status = 'ready' AND segment.status = 'ready'
            ORDER BY segment.segment_index ASC
            """,
            (package_id, package_version),
        ).fetchall()
        narration_refs = {
            str(row["action_id"]): f"asset:{row['asset_id']}"
            for row in narration_rows
        }
        attached: set[str] = set()
        for scene in public_payload.get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for action in scene.get("actions") or []:
                if not isinstance(action, dict) or action.get("type") != "narrate":
                    continue
                asset_ref = narration_refs.get(str(action.get("id") or ""))
                if asset_ref:
                    action["audioAssetRef"] = asset_ref
                    attached.add(asset_ref)
        if len(attached) != len(narration_refs) or not attached:
            raise RuntimeError("not every narration asset is bound to a package action")
        existing_refs = {
            str(value)
            for value in public_payload.get("assetRefs") or []
            if str(value).strip()
        }
        public_payload["assetRefs"] = sorted(existing_refs | attached)
        public_json = self.encode_json(public_payload)
        public_hash = hashlib.sha256(public_json.encode("utf-8")).hexdigest()
        conn.execute(
            """
            UPDATE learning_lesson_packages
            SET status = 'published', public_payload_json = ?,
              public_content_hash = ?, published_at = ?, updated_at = ?
            WHERE id = ? AND version = ? AND status = 'media_pending'
            """,
            (public_json, public_hash, now, now, package_id, package_version),
        )
        conn.execute(
            """
            INSERT INTO learning_course_lesson_package_bindings(
              course_id, course_version, package_id, package_version, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              package_id = VALUES(package_id),
              package_version = VALUES(package_version),
              updated_at = VALUES(updated_at)
            """,
            (
                package["course_id"],
                package["course_version"],
                package_id,
                package_version,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE learning_classroom_source_artifacts
            SET status = 'compiled', updated_at = ?
            WHERE id = ?
            """,
            (now, package["source_artifact_id"]),
        )
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET status = 'published', completed_at = ?, updated_at = ?
            WHERE package_id = ? AND package_version = ?
            """,
            (now, now, package_id, package_version),
        )
        return self.get_package_any_status(
            conn,
            package_id=package_id,
            package_version=package_version,
        )

    def mark_staged_package_media_failed(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
        error_code: str,
        error_message_safe: str,
        rejected: bool,
        now: int,
    ) -> DatabaseRow | None:
        package_status = "rejected" if rejected else "media_failed"
        conn.execute(
            """
            UPDATE learning_lesson_packages
            SET status = ?, updated_at = ?
            WHERE id = ? AND version = ? AND status = 'media_pending'
            """,
            (package_status, now, package_id, package_version),
        )
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              completed_at = ?, updated_at = ?
            WHERE package_id = ? AND package_version = ?
              AND status <> 'published'
            """,
            (
                error_code[:128],
                error_message_safe[:512],
                now,
                now,
                package_id,
                package_version,
            ),
        )
        return self.get_package_any_status(
            conn,
            package_id=package_id,
            package_version=package_version,
        )

    def mark_job_failed(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_classroom_generation_jobs
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              completed_at = ?, updated_at = ?
            WHERE id = ? AND status <> 'published'
            """,
            (error_code, error_message_safe, now, now, job_id),
        )

    def get_package(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_lesson_packages
            WHERE id = ? AND version = ? AND status = 'published'
            LIMIT 1
            """,
            (package_id, package_version),
        ).fetchone()

    def get_package_any_status(
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
            SELECT * FROM learning_lesson_packages
            WHERE id = ? AND version = ?
            LIMIT 1
            """
            + lock,
            (package_id, package_version),
        ).fetchone()

    def list_ready_assets(
        self,
        conn: DatabaseConnection,
        *,
        asset_ids: list[str],
    ) -> set[str]:
        if not asset_ids:
            return set()
        placeholders = ", ".join("?" for _ in asset_ids)
        rows = conn.execute(
            f"""
            SELECT id FROM learning_media_assets
            WHERE id IN ({placeholders})
              AND status = 'ready'
              AND scan_status = 'passed'
              AND moderation_status = 'passed'
              AND transcode_status IN ('passed', 'not_required')
            """,
            asset_ids,
        ).fetchall()
        return {str(row["id"]) for row in rows}

    def get_active_formal_package(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
        family_id: str | None = None,
        child_id: str | None = None,
    ) -> DatabaseRow | None:
        """Resolve an exact progressive item, then the shared active fallback."""

        if family_id and child_id:
            progressive = conn.execute(
                f"""
                SELECT package.*
                FROM children AS child
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
                 AND release_item.status = 'published'
                 AND release_item.quality_status = 'ready'
                 AND release_item.retired_at IS NULL
                JOIN learning_courses AS course
                  ON course.id = release_item.course_id
                 AND course.version = release_item.course_version
                 AND course.grade_code = release_item.grade_code
                 AND course.curriculum_version = release_item.curriculum_version
                 AND course.boundary_version = release_item.boundary_version
                 AND course.status = 'published'
                 AND course.quality_status = 'released'
                 AND course.content_origin = 'openmaic_generated'
                 AND course.retired_at IS NULL
                JOIN learning_course_lesson_package_bindings AS binding
                  ON binding.course_id = release_item.course_id
                 AND binding.course_version = release_item.course_version
                 AND binding.package_id = release_item.package_id
                 AND binding.package_version = release_item.package_version
                JOIN learning_lesson_packages AS package
                  ON package.id = binding.package_id
                 AND package.version = binding.package_version
                 AND package.course_id = course.id
                 AND package.course_version = course.version
                 AND package.status = 'published'
                 AND package.retired_at IS NULL
                JOIN learning_catalog_build_items AS build_item
                  ON build_item.build_job_id = plan.catalog_build_id
                 AND build_item.release_id = plan.catalog_release_id
                 AND build_item.grade_code = child.grade_code
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
                     AND build_item.content_validation_contract_version
                       IS NOT NULL
                     AND build_item.content_validation_contract_version <> ''
                     AND build_item.content_receipt_hash
                       REGEXP '^[0-9a-f]{{64}}$'
                   )
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
                  ON audio.build_item_id = build_item.id
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
                WHERE child.family_id = ? AND child.id = ?
                  AND child.grade_selection_revision >= 1
                  AND course.id = ? AND course.version = ?
                  {current_formal_validation_authority_sql(
                      receipt_alias="receipt",
                      provider_alias="provider",
                  )}
                LIMIT 1 FOR UPDATE
                """,
                (
                    self.CANDIDATE_BINDING_CONTRACT_VERSION,
                    self.CANDIDATE_BINDING_CONTRACT_VERSION,
                    family_id,
                    child_id,
                    course_id,
                    course_version,
                ),
            ).fetchone()
            if progressive is not None:
                return progressive

        return conn.execute(
            f"""
            SELECT package.*
            FROM learning_courses AS course
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
             AND history.activation_source = 'formal_publication'
             AND history.superseded_at IS NULL
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = pointer.release_id
             AND release_item.course_id = course.id
             AND release_item.course_version = course.version
             AND release_item.grade_code = course.grade_code
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_course_lesson_package_bindings AS binding
              ON binding.course_id = release_item.course_id
             AND binding.course_version = release_item.course_version
             AND binding.package_id = release_item.package_id
             AND binding.package_version = release_item.package_version
            JOIN learning_lesson_packages AS package
              ON package.id = binding.package_id
             AND package.version = binding.package_version
             AND package.course_id = course.id
             AND package.course_version = course.version
             AND package.status = 'published'
             AND package.retired_at IS NULL
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
              ON receipt.build_item_id = build_item.id
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
            WHERE course.id = ? AND course.version = ?
              AND course.status = 'published'
              AND course.quality_status = 'released'
              AND course.content_origin = 'openmaic_generated'
              AND course.retired_at IS NULL
              {current_formal_validation_authority_sql(
                  receipt_alias="receipt",
                  provider_alias="provider",
              )}
            LIMIT 1 FOR UPDATE
            """,
            (
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                self.CANDIDATE_BINDING_CONTRACT_VERSION,
                course_id,
                course_version,
            ),
        ).fetchone()

    def has_formal_grade_pointer_for_course(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
    ) -> bool:
        """Return whether this course's grade is governed by formal releases.

        Once a grade has a formal pointer, a missing exact release item is a
        release transition/error, never permission to fall back to a legacy
        package.  Locking the pointer keeps that decision stable until the
        caller either binds the session or rolls the transaction back.
        """

        row = conn.execute(
            """
            SELECT pointer.grade_code
            FROM learning_courses AS course
            JOIN learning_curriculum_grade_release_pointers AS pointer
              ON pointer.grade_code = course.grade_code
             AND pointer.pointer_revision >= 1
             AND pointer.contract_version =
               'mira.learning.formal-publication.v1'
            WHERE course.id = ? AND course.version = ?
            LIMIT 1
            FOR UPDATE
            """,
            (course_id, course_version),
        ).fetchone()
        return row is not None

    def get_active_package(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT package.*
            FROM learning_course_lesson_package_bindings AS binding
            JOIN learning_lesson_packages AS package
              ON package.id = binding.package_id
             AND package.version = binding.package_version
            WHERE binding.course_id = ? AND binding.course_version = ?
              AND package.status = 'published'
            LIMIT 1
            """,
            (course_id, course_version),
        ).fetchone()

    def get_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        session_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_sessions
            WHERE id = ? AND family_id = ? AND child_id = ?
            LIMIT 1
            """
            + lock,
            (session_id, family_id, child_id),
        ).fetchone()

    def bind_session_package(
        self,
        conn: DatabaseConnection,
        *,
        session: Mapping[str, Any],
        package: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        if session.get("lesson_package_id") is None:
            conn.execute(
                """
                UPDATE learning_sessions
                SET lesson_package_id = ?, lesson_package_version = ?,
                  lesson_package_content_hash = ?, current_scene_index = 0,
                  current_action_index = 0, cursor_revision = 0,
                  runtime_state_json = ?, updated_at = ?
                WHERE id = ? AND lesson_package_id IS NULL
                """,
                (
                    package["id"],
                    package["version"],
                    package["public_content_hash"],
                    self.encode_json({"runtimeSchemaVersion": 1}),
                    now,
                    session["id"],
                ),
            )
        return self.get_session(
            conn,
            family_id=session["family_id"],
            child_id=session["child_id"],
            session_id=session["id"],
            for_update=True,
        )

    def update_session_cursor(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        scene_index: int,
        action_index: int,
        cursor_revision: int,
        classroom_completed_at: int | None,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_sessions
            SET current_scene_index = ?, current_action_index = ?,
              cursor_revision = ?, classroom_completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                scene_index,
                action_index,
                cursor_revision,
                classroom_completed_at,
                now,
                session_id,
            ),
        )

    def get_runtime_record_by_idempotency(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        idempotency_key: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_session_runtime_records
            WHERE session_id = ? AND idempotency_key = ?
            LIMIT 1
            """,
            (session_id, idempotency_key),
        ).fetchone()

    def append_runtime_record(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        idempotency_key: str,
        scene_id: str,
        action_id: str,
        record_type: str,
        payload: Mapping[str, Any],
        response: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(seq), 0) AS maximum
            FROM learning_session_runtime_records
            WHERE session_id = ? FOR UPDATE
            """,
            (session_id,),
        ).fetchone()
        sequence = int((row or {}).get("maximum") or 0) + 1
        record_id = f"lesson_runtime_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_session_runtime_records(
              id, session_id, seq, idempotency_key, scene_id, action_id,
              record_type, payload_json, response_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                session_id,
                sequence,
                idempotency_key,
                scene_id,
                action_id,
                record_type,
                self.encode_json(payload),
                self.encode_json(response),
                now,
            ),
        )
        return conn.execute(
            """
            SELECT * FROM learning_session_runtime_records WHERE id = ?
            """,
            (record_id,),
        ).fetchone()

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
