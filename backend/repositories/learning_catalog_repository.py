from __future__ import annotations

from content.formal_curriculum_registry import formal_content_validation_identity

from services.learning_curriculum_preparation_contract import (canonical_preparation_target_for, formal_target_course_count, preparation_authority_grade)

from repositories.course_supply_repository import requested_supply, filter_requested_supply, record_supply_incident

from integrations.openmaic_formal_media import validate_media_manifest, compatible_preparation_target

import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_ONE_CONTENT_DATASET_SHA256,
    SUBJECT_LANGUAGE_POLICY_VERSION,
)
from core.database import Database, DatabaseConnection, DatabaseRow
from integrations.openmaic_question_adapter import (
    QUESTION_PHASE_IO,
    question_phase_execution_authority,
)
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from repositories.learning_question_fingerprint_inventory import (
    HISTORICAL_QUESTION_FINGERPRINT_LIMIT,
    historical_question_fingerprint_snapshots,
    historical_question_fingerprints,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_provider_deadline_contract import (
    FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS as DEFAULT_PROVIDER_ATTEMPT_HARD_DEADLINE_MS,
    provider_attempt_deadline_is_valid,
)


class LearningCatalogBuildConflict(ValueError):
    pass


class LearningCatalogActivationError(ValueError):
    pass


class LearningCatalogRepository:
    # A completed phase hands the next phase a fresh, bounded work unit. Keep
    # this wider than the Provider phase budget so a supervised worker can
    # restart or ride out a short dependency outage without stranding the
    # entire build between two already-persisted phases.
    FORMAL_CONTENT_WORK_UNIT_MS = 10 * 60 * 1000
    FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS = (
        DEFAULT_PROVIDER_ATTEMPT_HARD_DEADLINE_MS
    )
    FORMAL_HISTORICAL_QUESTION_FINGERPRINT_LIMIT = (
        HISTORICAL_QUESTION_FINGERPRINT_LIMIT
    )
    FORMAL_PUBLICATION_CONTRACT_VERSION = (
        "mira.learning.formal-publication.v1"
    )
    FORMAL_PROVIDER_REQUEST_POLICY_VERSION = (
        "mira.openmaic.formal-provider-deepseek-v4-pro-request.v3"
    )
    FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION = (
        "mira.learning.formal-artifact-publication.v1"
    )
    CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION = (
        "mira.learning.candidate-runtime-binding.v1"
    )

    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def sync_boundaries(
        self,
        conn: DatabaseConnection,
        *,
        boundaries: Sequence[Mapping[str, Any]],
        curriculum_version: str,
        now: int,
    ) -> None:
        active_versions: list[str] = []
        for boundary in boundaries:
            boundary_version = str(boundary["boundaryVersion"])
            active_versions.append(boundary_version)
            conn.execute(
                """
                INSERT INTO learning_skill_boundaries(
                  grade_code, subject, skill_id, curriculum_version,
                  boundary_version, title, payload_json, quality_status,
                  status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', 'active', ?, ?)
                ON DUPLICATE KEY UPDATE
                  title = VALUES(title), payload_json = VALUES(payload_json),
                  quality_status = 'ready', status = 'active', retired_at = NULL,
                  updated_at = VALUES(updated_at)
                """,
                (
                    boundary["gradeCode"],
                    boundary["subject"],
                    boundary["skillId"],
                    curriculum_version,
                    boundary_version,
                    boundary["skillTitle"],
                    self.encode_json(boundary),
                    now,
                    now,
                ),
            )
        if active_versions:
            placeholders = ", ".join("?" for _ in active_versions)
            conn.execute(
                f"""
                UPDATE learning_skill_boundaries
                SET status = 'retired', quality_status = 'superseded',
                  retired_at = COALESCE(retired_at, ?), updated_at = ?
                WHERE curriculum_version = ? AND status = 'active'
                  AND boundary_version NOT IN ({placeholders})
                """,
                (now, now, curriculum_version, *active_versions),
            )

    def create_or_get_build(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        curriculum_version: str,
        title: str,
        target_spec: Mapping[str, Any],
        targets: Sequence[Mapping[str, Any]],
        variants_per_boundary: int,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        target_spec_json = self.encode_json(target_spec)
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
        release_id = f"catalog_release_{digest}"
        build_id = f"catalog_build_{digest}"
        boundary_count = len(targets)
        total_count = boundary_count * max(1, int(variants_per_boundary))
        hint = self.get_build_by_request(conn, request_id=request_id)
        authority_release_id = (
            str(hint["release_id"]) if hint is not None else release_id
        )
        if hint is None:
            conn.execute(
                """
                INSERT INTO learning_catalog_releases(
                  id, curriculum_version, title, status, quality_status,
                  required_boundary_count, ready_item_count, created_at, updated_at
                )
                VALUES (?, ?, ?, 'draft', 'building', ?, 0, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (release_id, curriculum_version, title, boundary_count, now, now),
            )
        release = self.get_release(
            conn,
            release_id=authority_release_id,
            for_update=True,
        )
        if release is None:
            raise LearningCatalogBuildConflict(
                "request_id is bound to a missing catalog release"
            )
        locked = self.get_build_by_request(
            conn,
            request_id=request_id,
            for_update=True,
        )
        created = False
        if locked is None:
            build_cursor = conn.execute(
                """
                INSERT INTO learning_catalog_build_jobs(
                  id, request_id, release_id, curriculum_version, status,
                  target_spec_json, total_item_count, ready_item_count,
                  failed_item_count, execution_mode, content_manifest_version,
                  canary_manifest_json, stage_ceiling, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'queued', ?, ?, 0, 0, 'full_pipeline',
                  NULL, NULL, 'active_release', ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (
                    build_id,
                    request_id,
                    release_id,
                    curriculum_version,
                    target_spec_json,
                    total_count,
                    now,
                    now,
                ),
            )
            created = build_cursor.rowcount == 1
            locked = self.get_build_by_request(
                conn,
                request_id=request_id,
                for_update=True,
            )
        if locked is None:
            raise RuntimeError("catalog build identity was not persisted")
        if (
            str(locked["id"]) != build_id
            or str(locked["release_id"]) != release_id
            or str(locked["curriculum_version"]) != curriculum_version
            or str(locked["target_spec_json"]) != target_spec_json
            or int(locked["total_item_count"]) != total_count
            or str(locked.get("execution_mode") or "") != "full_pipeline"
            or str(locked.get("stage_ceiling") or "") != "active_release"
            or locked.get("content_manifest_version") is not None
            or locked.get("canary_manifest_json") is not None
        ):
            raise LearningCatalogBuildConflict(
                "request_id is already bound to another catalog target"
            )
        if (
            str(release["id"]) != release_id
            or str(release["curriculum_version"]) != curriculum_version
            or int(release["required_boundary_count"]) != boundary_count
        ):
            raise LearningCatalogBuildConflict(
                "request_id is already bound to another catalog release"
            )

        if created:
            for target in targets:
                for ordinal in range(1, max(1, int(variants_per_boundary)) + 1):
                    identity = (
                        f"{build_id}:{target['gradeCode']}:{target['subject']}:"
                        f"{target['skillId']}:{ordinal}"
                    )
                    item_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                    conn.execute(
                        """
                        INSERT INTO learning_catalog_build_items(
                          id, build_job_id, release_id, grade_code, subject,
                          skill_id, curriculum_version, boundary_version,
                          variant_ordinal, status, attempt_count,
                          generation_request_id, execution_mode_snapshot,
                          content_manifest_version_snapshot, content_phase,
                          content_gate_status, content_gate_attempt_count,
                          created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?,
                          'full_pipeline', NULL, 'legacy_full_pipeline',
                          'not_applicable', 0, ?, ?)
                        """,
                        (
                            f"catalog_build_item_{item_digest[:24]}",
                            build_id,
                            release_id,
                            target["gradeCode"],
                            target["subject"],
                            target["skillId"],
                            curriculum_version,
                            target["boundaryVersion"],
                            ordinal,
                            f"catalog_gen_{item_digest[:48]}",
                            now,
                            now,
                        ),
                    )
        rows = self.list_build_items(
            conn,
            build_id=build_id,
            for_update=True,
        )
        expected_items = self._expected_full_item_immutables(
            build_id=build_id,
            release_id=release_id,
            curriculum_version=curriculum_version,
            targets=targets,
            variants_per_boundary=variants_per_boundary,
        )
        if len(rows) != total_count or {
            self._full_item_immutable_tuple(row) for row in rows
        } != expected_items:
            raise LearningCatalogBuildConflict(
                "catalog build items do not match the immutable target"
            )
        return locked, created

    def create_or_get_content_build(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        curriculum_version: str,
        title: str,
        target_spec: Mapping[str, Any],
        target_fingerprint: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        target_spec_json = self.encode_json(target_spec)
        canonical_target = canonical_preparation_target_for(target_spec)
        grade_code = preparation_authority_grade(target_spec)
        target_count = formal_target_course_count(target_spec)
        canonical_target_json = self.encode_json(canonical_target)
        canonical_fingerprint = preparation_target_fingerprint(canonical_target)
        canonical_curriculum_version = str(canonical_target["curriculumVersion"])
        computed_fingerprint = hashlib.sha256(
            target_spec_json.encode("utf-8")
        ).hexdigest()
        if (
            not compatible_preparation_target(target_spec, canonical_target)
            or computed_fingerprint != str(target_fingerprint or "")
            or str(curriculum_version) != canonical_curriculum_version
        ):
            raise LearningCatalogBuildConflict(
                "target_fingerprint does not match the immutable content target"
            )
        if "allowPartial" in target_spec:
            raise LearningCatalogBuildConflict(
                "content-only preparation targets cannot declare allowPartial"
            )
        course_targets = target_spec.get("courseTargets")
        canary_manifest = target_spec.get("canaryManifest")
        if (
            str(target_spec.get("schemaVersion") or "")
            != "mira.learning.preparation-target.v2"
            or str(target_spec.get("gradeCode") or "") != grade_code
            or int(target_spec.get("variantsPerBoundary") or 0) != 3
            or int(target_spec.get("totalCourseCount") or 0) != target_count
            or not isinstance(course_targets, list)
            or len(course_targets) != target_count
            or not isinstance(canary_manifest, Mapping)
            or not isinstance(canary_manifest.get("targets"), list)
            or len(canary_manifest["targets"]) != 3
        ):
            raise LearningCatalogBuildConflict(
                "content-only preparation target is not the exact registered grade shape"
            )
        content_manifest_version = str(target_spec["schemaVersion"])
        canary_manifest_json = self.encode_json(canary_manifest)
        boundary_count = len(
            {
                (
                    str(target.get("subject") or ""),
                    str(target.get("skillId") or ""),
                    str(target.get("boundaryVersion") or ""),
                )
                for target in course_targets
            }
        )
        if boundary_count != int(canonical_target["boundaryCount"]):
            raise LearningCatalogBuildConflict(
                "content-only preparation target must match the registered boundary count"
            )

        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
        release_id = f"catalog_release_{digest}"
        build_id = f"catalog_build_{digest}"
        hint = self.get_build_by_request(
            conn,
            request_id=request_id,
        )
        authority_release_id = (
            str(hint["release_id"]) if hint is not None else release_id
        )
        if hint is None:
            conn.execute(
                """
                INSERT INTO learning_catalog_releases(
                  id, curriculum_version, title, status, quality_status,
                  required_boundary_count, ready_item_count, created_at, updated_at
                )
                VALUES (?, ?, ?, 'draft', 'building', ?, 0, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (release_id, curriculum_version, title, boundary_count, now, now),
            )
        release = self.get_release(
            conn,
            release_id=authority_release_id,
            for_update=True,
        )
        if release is None:
            raise LearningCatalogBuildConflict(
                "request_id is bound to a missing catalog release"
            )
        locked = self.get_build_by_request(
            conn,
            request_id=request_id,
            for_update=True,
        )
        created = False
        if locked is None:
            build_cursor = conn.execute(
                """
                INSERT INTO learning_catalog_build_jobs(
                  id, request_id, release_id, curriculum_version, status,
                  target_spec_json, total_item_count, ready_item_count,
                  failed_item_count, execution_mode, content_manifest_version,
                  canary_manifest_json, stage_ceiling, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'queued', ?, ?, 0, 0, 'content_only',
                  ?, ?, 'content_ready', ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (
                    build_id,
                    request_id,
                    release_id,
                    curriculum_version,
                    target_spec_json,
                    target_count,
                    content_manifest_version,
                    canary_manifest_json,
                    now,
                    now,
                ),
            )
            created = build_cursor.rowcount == 1
            locked = self.get_build_by_request(
                conn,
                request_id=request_id,
                for_update=True,
            )
        if locked is None:
            raise RuntimeError("content-only catalog build identity was not persisted")
        if (
            str(locked["id"]) != build_id
            or str(locked["release_id"]) != release_id
            or str(locked["curriculum_version"]) != curriculum_version
            or str(locked["target_spec_json"]) != target_spec_json
            or int(locked["total_item_count"]) != target_count
            or str(locked.get("execution_mode") or "") != "content_only"
            or str(locked.get("stage_ceiling") or "") != "content_ready"
            or str(locked.get("content_manifest_version") or "")
            != content_manifest_version
            or str(locked.get("canary_manifest_json") or "")
            != canary_manifest_json
        ):
            raise LearningCatalogBuildConflict(
                "request_id is already bound to another catalog target"
            )
        if (
            str(release["id"]) != release_id
            or str(release["curriculum_version"]) != curriculum_version
            or str(release["title"]) != title
            or int(release["required_boundary_count"]) != boundary_count
        ):
            raise LearningCatalogBuildConflict(
                "request_id is already bound to another catalog release"
            )

        if created:
            for target in course_targets:
                subject = str(target["subject"])
                skill_id = str(target["skillId"])
                variant_ordinal = int(target["variantOrdinal"])
                identity = (
                    f"{build_id}:{grade_code}:{subject}:{skill_id}:{variant_ordinal}"
                )
                item_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                conn.execute(
                    """
                    INSERT INTO learning_catalog_build_items(
                      id, build_job_id, release_id, grade_code, subject,
                      skill_id, curriculum_version, boundary_version,
                      variant_ordinal, status, attempt_count,
                      generation_request_id, execution_mode_snapshot,
                      content_manifest_version_snapshot, subject_ordinal,
                      boundary_ordinal, content_phase, content_gate_status,
                      content_gate_attempt_count, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0,
                      ?, 'content_only', ?, ?, ?, 'not_started', 'not_started',
                      0, ?, ?)
                    """,
                    (
                        f"catalog_build_item_{item_digest[:24]}",
                        build_id,
                        release_id,
                        grade_code,
                        subject,
                        skill_id,
                        curriculum_version,
                        target["boundaryVersion"],
                        variant_ordinal,
                        f"catalog_gen_{item_digest[:48]}",
                        content_manifest_version,
                        int(target["subjectOrdinal"]),
                        int(target["boundaryOrdinal"]),
                        now,
                        now,
                    ),
                )
        rows = self.list_build_items(
            conn,
            build_id=build_id,
            for_update=True,
        )
        expected_items = self._expected_content_item_immutables(
            build_id=build_id,
            release_id=release_id,
            curriculum_version=canonical_curriculum_version,
            content_manifest_version=content_manifest_version,
            course_targets=course_targets,
            grade_code=grade_code,
        )
        if len(rows) != target_count or any(
            not self._content_item_immutables_match(row, expected)
            for row, expected in zip(rows, expected_items)
        ):
            raise LearningCatalogBuildConflict(
                "content-only catalog build items do not match the immutable target"
            )
        if not self._progressive_release_items_are_exact(
            conn,
            release=release,
            build=locked,
            rows=rows,
            target_fingerprint=target_fingerprint,
        ):
            raise LearningCatalogBuildConflict(
                "content-only catalog release has invalid published items"
            )
        return locked, created

    def get_build_by_request(
        self,
        conn: DatabaseConnection,
        *,
        request_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_catalog_build_jobs
            WHERE request_id = ? LIMIT 1
            """ + lock,
            (request_id,),
        ).fetchone()

    def get_build(
        self, conn: DatabaseConnection, *, build_id: str, for_update: bool = False
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_catalog_build_jobs WHERE id = ? LIMIT 1
            """
            + lock,
            (build_id,),
        ).fetchone()

    def get_release(
        self, conn: DatabaseConnection, *, release_id: str, for_update: bool = False
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_catalog_releases WHERE id = ? LIMIT 1
            """
            + lock,
            (release_id,),
        ).fetchone()

    def get_build_by_release(
        self,
        conn: DatabaseConnection,
        *,
        release_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_catalog_build_jobs
            WHERE release_id = ? LIMIT 1
            """ + lock,
            (release_id,),
        ).fetchone()

    def lock_build_authority(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
    ) -> tuple[DatabaseRow | None, DatabaseRow | None]:
        hint = self.get_build(conn, build_id=build_id)
        if hint is None:
            return None, None
        release = self.get_release(
            conn,
            release_id=str(hint["release_id"]),
            for_update=True,
        )
        if release is None:
            return None, None
        build = self.get_build(conn, build_id=build_id, for_update=True)
        if build is None or str(build.get("release_id") or "") != str(release["id"]):
            return release, None
        return release, build

    def list_build_items(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        for_update: bool = False,
    ) -> list[DatabaseRow]:
        lock = " FOR UPDATE" if for_update else ""
        return list(
            conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE build_job_id = ?
                ORDER BY
                  CASE WHEN subject_ordinal IS NULL THEN 1 ELSE 0 END,
                  subject_ordinal, boundary_ordinal, variant_ordinal,
                  grade_code, subject, skill_id
                """ + lock,
                (build_id,),
            ).fetchall()
        )

    def claim_next_content_item(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        now: int,
        lease_ms: int,
    ) -> Mapping[str, object] | None:
        if int(lease_ms) <= 0:
            raise ValueError("content lease must be positive")
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        if (
            build is None
            or str(build.get("execution_mode") or "") != "content_only"
            or str(build.get("stage_ceiling") or "") != "content_ready"
            or not str(build.get("content_manifest_version") or "")
            or not str(build.get("canary_manifest_json") or "")
        ):
            return None
        if release is None:
            return None
        target_spec = self.decode_json(build.get("target_spec_json"))
        canonical_target = canonical_preparation_target_for(target_spec)
        canonical_curriculum_version = str(canonical_target["curriculumVersion"])
        if (
            not compatible_preparation_target(target_spec, canonical_target)
            or str(build.get("curriculum_version") or "")
            != canonical_curriculum_version
            or str(release.get("curriculum_version") or "")
            != canonical_curriculum_version
        ):
            return None
        course_targets = target_spec.get("courseTargets")
        canary_manifest = target_spec.get("canaryManifest")
        canary_targets = (
            canary_manifest.get("targets")
            if isinstance(canary_manifest, Mapping)
            else None
        )
        if (
            str(target_spec.get("schemaVersion") or "")
            != str(build.get("content_manifest_version") or "")
            or not isinstance(course_targets, list)
            or len(course_targets) != formal_target_course_count(target_spec)
            or not isinstance(canary_targets, list)
            or len(canary_targets) != 3
            or self.encode_json(canary_manifest)
            != str(build.get("canary_manifest_json") or "")
        ):
            return None

        expected_items = self._expected_content_item_immutables(
            build_id=build_id,
            release_id=str(build["release_id"]),
            curriculum_version=canonical_curriculum_version,
            content_manifest_version=str(build["content_manifest_version"]),
            course_targets=course_targets,
            grade_code=preparation_authority_grade(target_spec),
        )
        if len(rows) != formal_target_course_count(target_spec) or any(
            not self._content_item_immutables_match(row, expected)
            for row, expected in zip(rows, expected_items)
        ):
            return None
        if not self._progressive_release_items_are_exact(
            conn,
            release=release,
            build=build,
            rows=rows,
            target_fingerprint=preparation_target_fingerprint(target_spec),
        ):
            return None
        for row in rows:
            if (
                int(row.get("package_attempt_count") or 0) != 0
                or row.get("active_package_request_id") is not None
                or row.get("package_id") is not None
                or row.get("package_version") is not None
            ):
                return None

        processing = [row for row in rows if str(row.get("status") or "") == "processing"]
        if processing:
            if len(processing) != 1:
                return None
            row = processing[0]
            lease_expires_at = int(row.get("content_lease_expires_at") or 0)
            if lease_expires_at >= int(now):
                return None
            attempt = int(row.get("attempt_count") or 0)
            attempt_start = int(row.get("content_attempt_started_at") or 0)
            outer_deadline = int(
                row.get("content_provider_attempt_hard_deadline_at") or 0
            )
            work_deadline = int(row.get("content_work_unit_deadline_at") or 0)
            if (
                attempt not in {1, 2}
                or int(row.get("content_claim_attempt_ordinal") or 0) != attempt
                or str(row.get("content_phase") or "") == "not_started"
                or not str(row.get("active_generation_request_id") or "")
                or attempt_start <= 0
                or work_deadline <= int(now)
                or outer_deadline <= int(now)
            ):
                return None
            dispatch_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = ?
                """,
                (row["id"], attempt),
            ).fetchone()["count"]
            if int(dispatch_count) != 0:
                return None
            lease_token = f"catalog_content_lease_{uuid.uuid4().hex}"
            lease_expires_at = min(
                int(now) + int(lease_ms),
                work_deadline,
                outer_deadline,
            )
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET content_lease_token = ?, content_lease_expires_at = ?,
                  content_heartbeat_at = ?, updated_at = ?
                WHERE id = ? AND status = 'processing'
                  AND attempt_count = ?
                  AND active_generation_request_id = ?
                  AND content_attempt_started_at = ?
                  AND content_provider_attempt_hard_deadline_at = ?
                  AND content_work_unit_deadline_at = ?
                  AND (content_lease_expires_at IS NULL
                    OR content_lease_expires_at < ?)
                """,
                (
                    lease_token,
                    lease_expires_at,
                    now,
                    now,
                    row["id"],
                    attempt,
                    row["active_generation_request_id"],
                    attempt_start,
                    outer_deadline,
                    work_deadline,
                    now,
                ),
            )
            if cursor.rowcount != 1:
                return None
            return self.get_item(conn, item_id=str(row["id"]))

        if any(str(row.get("status") or "") == "failed" for row in rows) and requested_supply(conn, build) is None:
            return None
        rows_by_identity = {
            (
                str(row["subject"]),
                str(row["skill_id"]),
                int(row["variant_ordinal"]),
            ): row
            for row in rows
        }
        canary_keys = {
            (
                str(target.get("subject") or ""),
                str(target.get("skillId") or ""),
                int(target.get("variantOrdinal") or 0),
            )
            for target in canary_targets
        }
        if len(canary_keys) != 3 or any(key not in rows_by_identity for key in canary_keys):
            return None
        canaries_passed = all(
            str(rows_by_identity[key].get("status") or "") == "course_ready"
            and str(rows_by_identity[key].get("content_gate_status") or "") == "passed"
            and bool(rows_by_identity[key].get("content_gate_passed_at"))
            and bool(rows_by_identity[key].get("content_receipt_hash"))
            for key in canary_keys
        )
        eligible_keys = set(rows_by_identity) if canaries_passed else canary_keys
        candidates = [
            row
            for key, row in rows_by_identity.items()
            if key in eligible_keys
            and str(row.get("status") or "") == "pending"
            and int(row.get("attempt_count") or 0) == 0
            and str(row.get("content_phase") or "") == "not_started"
            and str(row.get("content_gate_status") or "") == "not_started"
        ]
        candidates = filter_requested_supply(candidates, requested_supply(conn, build))
        if not candidates:
            return None
        passed_by_subject: dict[int, int] = {}
        for row in rows:
            subject_ordinal = int(row.get("subject_ordinal") or 0)
            if (
                str(row.get("status") or "") == "course_ready"
                and str(row.get("content_gate_status") or "") == "passed"
            ):
                passed_by_subject[subject_ordinal] = (
                    passed_by_subject.get(subject_ordinal, 0) + 1
                )
        row = min(
            candidates,
            key=lambda item: (
                int(item.get('_supply_priority', 0)),
                passed_by_subject.get(int(item["subject_ordinal"]), 0),
                int(item["subject_ordinal"]),
                int(item["boundary_ordinal"]),
                int(item["variant_ordinal"]),
            ),
        )
        attempt_start = int(now)
        outer_deadline = (
            attempt_start + self.FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS
        )
        work_deadline = self._formal_content_work_deadline(
            now=attempt_start,
            outer_deadline=outer_deadline,
        )
        lease_expires_at = min(
            attempt_start + int(lease_ms),
            work_deadline,
            outer_deadline,
        )
        lease_token = f"catalog_content_lease_{uuid.uuid4().hex}"
        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', attempt_count = 1,
              claim_origin_status = 'pending',
              active_generation_request_id = generation_request_id,
              content_phase = 'outline',
              content_lease_token = ?, content_lease_expires_at = ?,
              content_heartbeat_at = ?, content_attempt_started_at = ?,
              content_provider_attempt_hard_deadline_at = ?,
              content_work_unit_deadline_at = ?,
              content_claim_attempt_ordinal = 1,
              started_at = COALESCE(started_at, ?), updated_at = ?
            WHERE id = ? AND status = 'pending' AND attempt_count = 0
              AND active_generation_request_id IS NULL
              AND execution_mode_snapshot = 'content_only'
              AND content_phase = 'not_started'
              AND content_gate_status = 'not_started'
            """,
            (
                lease_token,
                lease_expires_at,
                now,
                attempt_start,
                outer_deadline,
                work_deadline,
                now,
                now,
                row["id"],
            ),
        )
        if cursor.rowcount != 1:
            return None
        self._mark_build_running(conn, build_id=build_id, now=now)
        return self.get_item(conn, item_id=str(row["id"]))

    # Task-7 content advancement deliberately has its own transaction surface.
    # The older claim_next_content_item() above is a frozen Task-3 scaffold; it
    # cannot authenticate the persisted provider graph or Host evidence and is
    # therefore never used by LearningCatalogReleaseService.advance_content().
    def inspect_content_profile_preflight(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
    ) -> str:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        if release is None or build is None:
            return "new"
        return (
            "persisted"
            if any(
                int(row.get("attempt_count") or 0) > 0
                or str(row.get("status") or "")
                in {"processing", "course_ready", "failed"}
                or str(row.get("content_phase") or "") != "not_started"
                for row in rows
            )
            else "new"
        )

    def prepare_content_advance(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        now: int,
        passed_item_ids: frozenset[str],
        repairable_item_ids: frozenset[str],
        locked_attempt_histories_by_item: Mapping[
            str, Mapping[int, Mapping[str, object]]
        ] | None = None,
    ) -> Mapping[str, object]:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        if release is None or build is None:
            return {"action": "stale", "items": rows}
        if str(build.get("status") or "") in {"failed", "completed"}:
            return {"action": "failed", "build": build, "items": rows}
        if not self._content_authority_is_exact(
            conn, release=release, build=build, rows=rows
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
            )
            return {"action": "failed", "build": build, "items": rows}
        item_ids = {str(row.get("id") or "") for row in rows}
        if not passed_item_ids.issubset(item_ids) or not repairable_item_ids.issubset(
            item_ids
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
            )
            return {"action": "failed", "build": build, "items": rows}
        proof_shape_drift = any(
            (
                str(row.get("status") or "") == "course_ready"
                and str(row.get("id") or "") not in passed_item_ids
            )
            or (
                str(row.get("id") or "") in passed_item_ids
                and str(row.get("status") or "") != "course_ready"
            )
            or (
                str(row.get("status") or "") == "failed"
                and int(row.get("attempt_count") or 0) == 1
                and str(row.get("content_gate_status") or "")
                == "failed_deterministic"
                and str(row.get("id") or "") not in repairable_item_ids
            )
            or (
                str(row.get("id") or "") in repairable_item_ids
                and not (
                    str(row.get("status") or "") == "failed"
                    and int(row.get("attempt_count") or 0) == 1
                    and str(row.get("content_gate_status") or "")
                    == "failed_deterministic"
                )
            )
            for row in rows
        )
        if proof_shape_drift:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
            )
            return {"action": "failed", "build": build, "items": rows}

        inflight = [
            row
            for row in rows
            if str(row.get("status") or "") == "processing"
        ]
        if len(inflight) > 1:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
            )
            return {"action": "failed", "build": build, "items": rows}
        if inflight:
            row = inflight[0]
            phase = str(row.get("content_phase") or "")
            if phase in {"host_gate_pending", "host_gate_running"}:
                return self._prepare_host_action(
                    conn,
                    build=build,
                    row=row,
                    rows=rows,
                    now=now,
                    passed_item_ids=passed_item_ids,
                    locked_attempt_histories_by_item=(
                        locked_attempt_histories_by_item or {}
                    ),
                )
            if phase not in self._content_provider_phases():
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_contract_drift",
                    now=now,
                )
                return {"action": "failed", "build": build, "items": rows}
            locked_histories = (
                locked_attempt_histories_by_item.get(str(row["id"]))
                if isinstance(locked_attempt_histories_by_item, Mapping)
                else None
            )
            if not isinstance(locked_histories, Mapping):
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_contract_drift",
                    now=now,
                    item_id=str(row["id"]),
                )
                return {"action": "failed", "build": build, "items": rows}
            current_history = locked_histories.get(int(row["attempt_count"]))
            if not isinstance(current_history, Mapping):
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_contract_drift",
                    now=now,
                    item_id=str(row["id"]),
                )
                return {"action": "failed", "build": build, "items": rows}
            locked_dispatches = list(current_history.get("dispatches") or ())
            prepared = self._claim_existing_provider_phase(
                conn,
                build=build,
                row=row,
                now=now,
                locked_dispatches=locked_dispatches,
            )
            if prepared is None:
                current_build = self.get_build(conn, build_id=str(build["id"]))
                if (
                    current_build is not None
                    and str(current_build.get("status") or "") == "failed"
                ):
                    return {
                        "action": "failed",
                        "build": current_build,
                        "items": rows,
                    }
                return {"action": "busy", "build": build, "items": rows}
            return {
                "action": "provider",
                "build": build,
                "item": prepared,
                "items": rows,
                "dispatches": locked_dispatches,
                "historicalQuestionFingerprints": (
                    self._historical_question_fingerprints(
                        conn,
                        item=prepared,
                    )
                ),
                "priorEvidence": self._prior_content_evidence_from_histories(
                    row=row,
                    rows=rows,
                    passed_item_ids=passed_item_ids,
                    locked_attempt_histories_by_item=(
                        locked_attempt_histories_by_item or {}
                    ),
                ),
                "attemptOneEvidence": (
                    self._attempt_one_evidence_for_active_retry(
                        item=row,
                        histories=locked_histories,
                    )
                    if int(row["attempt_count"]) == 2
                    else None
                ),
            }

        terminal_failures = [
            row
            for row in rows
            if str(row.get("status") or "") == "failed"
            and not (
                int(row.get("attempt_count") or 0) == 1
                and str(row.get("content_gate_status") or "")
                == "failed_deterministic"
            )
        ]
        library_owned = requested_supply(conn, build) is not None
        if terminal_failures and library_owned:
            for failed_item in terminal_failures:
                record_supply_incident(conn, item_id=failed_item['id'], stage='content',
                    reason=failed_item.get('error_code') or 'content_validation_failed', now=now)
        if terminal_failures and not library_owned:
            code = (
                "preparation_content_canary_failed"
                if any(self._is_content_canary(build, row) for row in terminal_failures)
                else "preparation_content_validation_failed"
            )
            self._fence_content_build_locked(
                conn, build=build, rows=rows, error_code=code, now=now
            )
            return {"action": "failed", "build": build, "items": rows}

        repairable = [
            row
            for row in rows
            if str(row.get("id") or "") in repairable_item_ids
        ]
        if repairable:
            row = min(
                repairable,
                key=lambda value: (
                    int(value["subject_ordinal"]),
                    int(value["boundary_ordinal"]),
                    int(value["variant_ordinal"]),
                ),
            )
            histories = (
                locked_attempt_histories_by_item.get(str(row["id"]))
                if isinstance(locked_attempt_histories_by_item, Mapping)
                else None
            )
            if not isinstance(histories, Mapping):
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_contract_drift",
                    now=now,
                    item_id=str(row["id"]),
                )
                return {"action": "failed", "build": build, "items": rows}
            evidence = self._content_attempt_evidence_from_histories(
                item=row,
                histories=histories,
                attempt=1,
            )
            return {
                "action": "attempt2",
                "build": build,
                "item": row,
                "items": rows,
                "historicalQuestionFingerprints": (
                    self._historical_question_fingerprints(
                        conn,
                        item=row,
                    )
                ),
                "priorEvidence": self._prior_content_evidence_from_histories(
                    row=row,
                    rows=rows,
                    passed_item_ids=passed_item_ids,
                    locked_attempt_histories_by_item=(
                        locked_attempt_histories_by_item or {}
                    ),
                ),
                "attemptOneEvidence": evidence,
            }

        passed_canaries = sum(
            1
            for row in rows
            if self._is_content_canary(build, row)
            and str(row.get("id") or "") in passed_item_ids
        )
        if passed_canaries == 3 and len(passed_item_ids) == len(rows):
            return {
                "action": "handoff",
                "build": build,
                "items": rows,
                "allPassedEvidence": [],
            }
        eligible = self._eligible_content_rows(
            conn=conn,
            build=build,
            rows=rows,
            canaries_passed=passed_canaries == 3,
            passed_item_ids=passed_item_ids,
        )
        if not eligible:
            return {"action": "busy", "build": build, "items": rows}
        passed_by_subject = {
            ordinal: sum(
                1
                for item in rows
                if int(item.get("subject_ordinal") or 0) == ordinal
                and str(item.get("id") or "") in passed_item_ids
            )
            for ordinal in (1, 2, 3)
        }
        row = self._select_fair_content_row(
            eligible=eligible,
            passed_by_subject=passed_by_subject,
        )
        claimed = self._claim_content_attempt(
            conn, build=build, row=row, attempt=1, now=now
        )
        if claimed is None:
            return {"action": "busy", "build": build, "items": rows}
        return {
            "action": "provider",
            "build": build,
            "item": claimed,
            "items": rows,
            "dispatches": [],
            "historicalQuestionFingerprints": (
                self._historical_question_fingerprints(
                    conn,
                    item=claimed,
                )
            ),
            "priorEvidence": self._prior_content_evidence_from_histories(
                row=row,
                rows=rows,
                passed_item_ids=passed_item_ids,
                locked_attempt_histories_by_item=(
                    locked_attempt_histories_by_item or {}
                ),
            ),
            "attemptOneEvidence": None,
        }

    def _claim_content_attempt_two_locked(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        attempt_one_request_id: str,
        attempt_one_course_id: str,
        attempt_one_course_version: str,
        now: int,
    ) -> DatabaseRow | None:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        row = next((value for value in rows if str(value["id"]) == item_id), None)
        if (
            release is None
            or build is None
            or row is None
            or str(build.get("status") or "") in {"failed", "completed"}
            or not self._content_authority_is_exact(
                conn, release=release, build=build, rows=rows
            )
            or str(row.get("status") or "") != "failed"
            or str(row.get("content_phase") or "") != "failed"
            or str(row.get("content_gate_status") or "")
            != "failed_deterministic"
            or int(row.get("attempt_count") or 0) != 1
            or int(row.get("content_claim_attempt_ordinal") or 0) != 1
            or str(row.get("generation_request_id") or "")
            != attempt_one_request_id
            or str(row.get("active_generation_request_id") or "")
            != attempt_one_request_id
            or str(row.get("course_id") or "") != attempt_one_course_id
            or str(row.get("course_version") or "")
            != attempt_one_course_version
        ):
            return None
        return self._claim_content_attempt(
            conn, build=build, row=row, attempt=2, now=now
        )

    def recover_zero_call_number_sense_preflight_attempt(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        failed_dispatch_id: str,
        expected_input_sha256: str,
        now: int,
    ) -> DatabaseRow | None:
        """Start attempt two only for one proven pre-billing Host failure.

        The failed dispatch remains immutable. Recovery is allowed only when
        the exact number-sense phase-3 request reached no Provider, every
        predecessor is terminal and authenticated, and no attempt-two residue
        exists. The surrounding transaction can then create one preparation
        retry successor without discarding already-ready courses.
        """

        for value, field in (
            (build_id, "build_id"),
            (item_id, "item_id"),
            (failed_dispatch_id, "failed_dispatch_id"),
        ):
            if not isinstance(value, str) or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value
            ) is None:
                raise ValueError(f"{field} is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", expected_input_sha256) is None:
            raise ValueError("expected_input_sha256 must be canonical SHA-256")
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_provider_unavailable"
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or not any(
                str(row.get("status") or "") == "course_ready" for row in rows
            )
            or str(item.get("grade_code") or "") != "primary_1"
            or (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
            )
            not in {("math", "number_sense_20"), ("english", "letters_sounds")}
            or str(item.get("status") or "") != "failed"
            or int(item.get("attempt_count") or 0) != 1
            or int(item.get("content_claim_attempt_ordinal") or 0) != 1
            or str(item.get("claim_origin_status") or "") != "pending"
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "")
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "") != "not_started"
            or int(item.get("content_gate_attempt_count") or 0) != 0
            or item.get("course_id") is not None
            or item.get("course_version") is not None
            or str(item.get("error_code") or "")
            != "preparation_content_provider_unavailable"
        ):
            return None

        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        attempt_one = histories.get(1)
        attempt_two = histories.get(2)
        if not isinstance(attempt_one, Mapping) or not isinstance(
            attempt_two, Mapping
        ):
            return None
        if any(
            attempt_two.get(key)
            for key in ("dispatches", "jobs", "candidates", "courses")
        ) or any(
            attempt_one.get(key) for key in ("jobs", "candidates", "courses")
        ):
            return None
        dispatches = attempt_one.get("dispatches")
        if not isinstance(dispatches, Sequence) or len(dispatches) != 3:
            return None
        expected_phases = (
            ("outline", 1, "succeeded"),
            ("raw_candidate", 2, "succeeded"),
            ("candidate_repair", 3, "failed_safe"),
        )
        if any(
            not isinstance(dispatch, Mapping)
            or str(dispatch.get("phase") or "") != phase
            or int(dispatch.get("phase_ordinal") or 0) != ordinal
            or str(dispatch.get("status") or "") != status
            or int(dispatch.get("logical_attempt") or 0) != 1
            or str(dispatch.get("generation_request_id") or "")
            != str(item.get("generation_request_id") or "")
            for dispatch, (phase, ordinal, status) in zip(
                dispatches, expected_phases
            )
        ):
            return None
        failed = dispatches[-1]
        if not (
            str(failed.get("id") or "") == failed_dispatch_id
            and str(failed.get("input_sha256") or "")
            == expected_input_sha256
            and str(failed.get("safe_error_code") or "")
            == "question_phase_preflight_rejected"
            and failed.get("provider_request_id_hash") is None
            and failed.get("input_tokens") is None
            and failed.get("output_tokens") is None
            and str(failed.get("billing_evidence") or "") == "unknown"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
        ):
            return None

        reopened = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND execution_mode = 'content_only'
              AND status = 'failed'
              AND error_code = 'preparation_content_provider_unavailable'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if reopened.rowcount != 1:
            return None
        return self._claim_content_attempt(
            conn,
            build={**dict(build), "status": "running"},
            row=item,
            attempt=2,
            now=int(now),
        )

    def recover_provider_rejected_addition_subtraction_attempt(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        failed_dispatch_id: str,
        expected_input_sha256: str,
        now: int,
    ) -> DatabaseRow | None:
        """Retry one fully returned response now accepted by canonical Host rules."""

        for value, field in (
            (build_id, "build_id"),
            (item_id, "item_id"),
            (failed_dispatch_id, "failed_dispatch_id"),
        ):
            if not isinstance(value, str) or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value
            ) is None:
                raise ValueError(f"{field} is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", expected_input_sha256) is None:
            raise ValueError("expected_input_sha256 must be canonical SHA-256")
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_validation_failed"
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or not any(
                str(row.get("status") or "") == "course_ready" for row in rows
            )
            or str(item.get("grade_code") or "") != "primary_1"
            or (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
            )
            not in {
                ("math", "addition_subtraction_20"),
                ("english", "greetings"),
            }
            or str(item.get("status") or "") != "failed"
            or int(item.get("attempt_count") or 0) != 1
            or int(item.get("content_claim_attempt_ordinal") or 0) != 1
            or str(item.get("claim_origin_status") or "") != "pending"
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "")
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "") != "not_started"
            or int(item.get("content_gate_attempt_count") or 0) != 0
            or item.get("course_id") is not None
            or item.get("course_version") is not None
            or str(item.get("error_code") or "")
            != "preparation_content_validation_failed"
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        attempt_two = histories.get(2)
        if not isinstance(attempt_two, Mapping) or any(
            attempt_two.get(key)
            for key in ("dispatches", "jobs", "candidates", "courses")
        ):
            return None
        projected_item = {
            **dict(item),
            "attempt_count": 2,
            "active_generation_request_id": (
                str(item.get("generation_request_id") or "") + ".attempt2"
            ),
        }
        evidence = (
            self._provider_rejected_addition_subtraction_attempt_one_evidence_from_histories(
                item=projected_item,
                histories=histories,
            )
        )
        if evidence is None:
            return None
        dispatches = evidence.get("dispatches")
        failed = dispatches[-1] if isinstance(dispatches, Sequence) else None
        if not isinstance(failed, Mapping) or not (
            str(failed.get("id") or "") == failed_dispatch_id
            and str(failed.get("input_sha256") or "") == expected_input_sha256
        ):
            return None
        reopened = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND execution_mode = 'content_only'
              AND status = 'failed'
              AND error_code = 'preparation_content_validation_failed'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if reopened.rowcount != 1:
            return None
        return self._claim_content_attempt(
            conn,
            build={**dict(build), "status": "running"},
            row=item,
            attempt=2,
            now=int(now),
        )

    def recover_sealed_outline_host_checkpoint(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        failed_dispatch_id: str,
        expected_input_sha256: str,
        checkpoint: Mapping[str, object],
        now: int,
    ) -> DatabaseRow | None:
        """Replace one fully returned, unusable outline with a sealed Host outline."""

        sealed_targets = {
            ("chinese", "pinyin_syllables"),
            ("chinese", "pinyin_initials_syllables"),
            ("chinese", "characters_words"),
            ("chinese", "simple_sentences"),
            ("math", "number_sense_20"),
            ("math", "addition_subtraction_20"),
            ("math", "shapes_position"),
            ("english", "letters_sounds"),
            ("english", "greetings"),
            ("english", "numbers_colors"),
        }
        if (
            re.fullmatch(r"[0-9a-f]{64}", expected_input_sha256) is None
            or set(checkpoint) != {"phaseStatus", "outlinePlan"}
            or checkpoint.get("phaseStatus") != "accepted"
            or not isinstance(checkpoint.get("outlinePlan"), Mapping)
        ):
            raise ValueError("sealed outline Host checkpoint is invalid")
        checkpoint_json = self.encode_json(checkpoint)
        output_sha256 = hashlib.sha256(
            checkpoint_json.encode("utf-8")
        ).hexdigest()
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_provider_unavailable"
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or not any(
                str(row.get("status") or "") == "course_ready" for row in rows
            )
            or str(item.get("grade_code") or "") != "primary_1"
            or (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
            )
            not in sealed_targets
            or str(item.get("status") or "") != "failed"
            or int(item.get("attempt_count") or 0) != 1
            or int(item.get("content_claim_attempt_ordinal") or 0) != 1
            or str(item.get("claim_origin_status") or "") != "pending"
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "")
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "") != "not_started"
            or int(item.get("content_gate_attempt_count") or 0) != 0
            or item.get("course_id") is not None
            or item.get("course_version") is not None
            or str(item.get("error_code") or "")
            != "preparation_content_provider_unavailable"
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        current = histories.get(1)
        future = histories.get(2)
        if (
            not isinstance(current, Mapping)
            or not isinstance(future, Mapping)
            or any(
                current.get(key) for key in ("jobs", "candidates", "courses")
            )
            or any(
                future.get(key)
                for key in ("dispatches", "jobs", "candidates", "courses")
            )
        ):
            return None
        dispatches = current.get("dispatches")
        if not isinstance(dispatches, Sequence) or len(dispatches) != 1:
            return None
        failed = dispatches[0]
        if not isinstance(failed, Mapping):
            return None
        attempt_started_at = failed.get("attempt_started_at")
        hard_deadline_at = failed.get("attempt_hard_deadline_at")
        if not (
            str(failed.get("id") or "") == failed_dispatch_id
            and int(failed.get("logical_attempt") or 0) == 1
            and str(failed.get("generation_request_id") or "")
            == str(item.get("generation_request_id") or "")
            and str(failed.get("phase") or "") == "outline"
            and int(failed.get("phase_ordinal") or 0) == 1
            and str(failed.get("status") or "") == "failed_safe"
            and str(failed.get("input_sha256") or "")
            == expected_input_sha256
            and str(failed.get("safe_error_code") or "")
            == "provider_no_candidate"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(failed.get("provider_request_id_hash") or ""),
            )
            is not None
            and type(failed.get("input_tokens")) is int
            and type(failed.get("output_tokens")) is int
            and str(failed.get("billing_evidence") or "") == "reported"
            and type(attempt_started_at) is int
            and type(hard_deadline_at) is int
            and provider_attempt_deadline_is_valid(
                attempt_started_at, hard_deadline_at
            )
            and int(now) < hard_deadline_at
        ):
            return None
        dispatch_cursor = conn.execute(
            """
            UPDATE learning_course_provider_dispatches
            SET status = 'succeeded', checkpoint_json = ?, output_sha256 = ?,
              safe_error_code = NULL
            WHERE id = ? AND build_item_id = ? AND logical_attempt = 1
              AND phase = 'outline' AND phase_ordinal = 1
              AND status = 'failed_safe' AND input_sha256 = ?
              AND safe_error_code = 'provider_no_candidate'
              AND checkpoint_json IS NULL AND output_sha256 IS NULL
              AND provider_request_id_hash IS NOT NULL
              AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
              AND billing_evidence = 'reported' AND completed_at IS NOT NULL
            """,
            (
                checkpoint_json,
                output_sha256,
                failed_dispatch_id,
                item_id,
                expected_input_sha256,
            ),
        )
        work_deadline_at = self._formal_content_work_deadline(
            now=int(now),
            outer_deadline=int(hard_deadline_at),
        )
        item_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', content_phase = 'raw_candidate',
              error_code = NULL, error_message_safe = NULL, completed_at = NULL,
              content_lease_token = NULL, content_lease_expires_at = NULL,
              content_heartbeat_at = NULL,
              content_provider_attempt_hard_deadline_at = ?,
              content_work_unit_deadline_at = ?, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'failed'
              AND attempt_count = 1 AND content_phase = 'failed'
              AND content_gate_status = 'not_started'
              AND content_gate_attempt_count = 0
              AND error_code = 'preparation_content_provider_unavailable'
              AND course_id IS NULL AND course_version IS NULL
            """,
            (
                int(hard_deadline_at),
                int(work_deadline_at),
                int(now),
                item_id,
                build_id,
            ),
        )
        build_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
              AND error_code = 'preparation_content_provider_unavailable'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if any(
            cursor.rowcount != 1
            for cursor in (dispatch_cursor, item_cursor, build_cursor)
        ):
            raise LearningCatalogBuildConflict("sealed outline Host replay CAS drift")
        return self.get_item(conn, item_id=item_id)

    def recover_billed_candidate_retry_host_checkpoint(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        expected_subject: str,
        expected_skill_id: str,
        failed_dispatch_id: str,
        expected_input_sha256: str,
        checkpoint: Mapping[str, object],
        now: int,
        expected_grade: str = "primary_1",
        recovery_audit_sha256: str | None = None,
    ) -> DatabaseRow | None:
        """Seal one billed retry from its immutable Host-compilable candidate."""

        sealed_targets = {
            ("chinese", "pinyin_syllables"),
            ("chinese", "pinyin_initials_syllables"),
            ("chinese", "characters_words"),
            ("chinese", "simple_sentences"),
            ("math", "number_sense_20"),
            ("math", "addition_subtraction_20"),
            ("math", "shapes_position"),
            ("english", "letters_sounds"),
            ("english", "greetings"),
            ("english", "numbers_colors"),
        }
        audited_high_grade = expected_grade in {f"primary_{n}" for n in range(2, 7)}
        if (
            ((expected_subject, expected_skill_id) not in sealed_targets and not audited_high_grade)
            or (audited_high_grade and re.fullmatch(r"[0-9a-f]{64}", recovery_audit_sha256 or "") is None)
            or
            re.fullmatch(r"[0-9a-f]{64}", expected_input_sha256) is None
            or set(checkpoint) != {"phaseStatus", "candidate"}
            or checkpoint.get("phaseStatus") != "accepted"
            or not isinstance(checkpoint.get("candidate"), Mapping)
        ):
            raise ValueError("Host checkpoint recovery input is invalid")
        checkpoint_json = self.encode_json(checkpoint)
        output_sha256 = hashlib.sha256(
            checkpoint_json.encode("utf-8")
        ).hexdigest()
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        logical_attempt = int((item or {}).get("attempt_count") or 0)
        expected_request_id = str((item or {}).get("generation_request_id") or "")
        if logical_attempt == 2:
            expected_request_id += ".attempt2"
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or not (
                (str(build.get("status") or "") == "failed"
                 and str(build.get("error_code") or "") == "preparation_content_validation_failed")
                or (audited_high_grade and build.get("status") == "running" and build.get("error_code") is None)
            )
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or str(item.get("grade_code") or "") != expected_grade
            or str(item.get("subject") or "") != expected_subject
            or str(item.get("skill_id") or "") != expected_skill_id
            or int(item.get("variant_ordinal") or 0) not in {1, 2, 3}
            or str(item.get("status") or "") != "failed"
            or logical_attempt not in {1, 2}
            or int(item.get("content_claim_attempt_ordinal") or 0)
            != logical_attempt
            or str(item.get("active_generation_request_id") or "")
            != expected_request_id
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "") != "not_started"
            or int(item.get("content_gate_attempt_count") or 0) != 0
            or (
                logical_attempt == 1
                and (
                    item.get("course_id") is not None
                    or item.get("course_version") is not None
                )
            )
            or str(item.get("error_code") or "")
            != "preparation_content_validation_failed"
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        if audited_high_grade:
            from services.learning_content_recovery import candidate_less_evidence, require_billed_recovery_audit
            if (logical_attempt != 2 or candidate_less_evidence(item=item, histories=histories) is None
                    or item.get("course_id") is not None or item.get("course_version") is not None):
                return None
            require_billed_recovery_audit(conn, build_id=build_id, item=item, histories=histories,
                                         audit_sha256=recovery_audit_sha256, checkpoint=checkpoint)
        if logical_attempt == 2:
            try:
                attempt_one = self._attempt_one_evidence_for_active_retry(
                    item=item,
                    histories=histories,
                )
            except LearningCatalogBuildConflict:
                return None
            if "recoveryKind" in attempt_one:
                if (
                    item.get("course_id") is not None
                    or item.get("course_version") is not None
                ):
                    return None
            else:
                attempt_one_job = attempt_one.get("job")
                attempt_one_candidate = attempt_one.get("candidate")
                attempt_one_course = attempt_one.get("course")
                attempt_one_dispatches = attempt_one.get("dispatches")
                try:
                    attempt_one_validation = json.loads(
                        str((attempt_one_candidate or {}).get("validation_json") or "")
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    return None
                attempt_one_receipt = attempt_one_validation.get(
                    "hostGateReceipt"
                )
                attempt_one_issues = (
                    attempt_one_receipt.get("issues")
                    if isinstance(attempt_one_receipt, Mapping)
                    else None
                )
                if not (
                    isinstance(attempt_one_job, Mapping)
                    and isinstance(attempt_one_candidate, Mapping)
                    and isinstance(attempt_one_course, Mapping)
                    and isinstance(attempt_one_dispatches, Sequence)
                    and bool(attempt_one_dispatches)
                    and all(
                        isinstance(dispatch, Mapping)
                        and str(dispatch.get("status") or "") == "succeeded"
                        for dispatch in attempt_one_dispatches
                    )
                    and str(attempt_one_job.get("status") or "") == "failed"
                    and str(attempt_one_job.get("error_code") or "")
                    == "preparation_content_validation_failed"
                    and str(attempt_one_candidate.get("status") or "")
                    == "rejected"
                    and str(attempt_one_candidate.get("error_code") or "")
                    == "preparation_content_validation_failed"
                    and isinstance(attempt_one_receipt, Mapping)
                    and str(attempt_one_receipt.get("outcome") or "")
                    == "rejected"
                    and int(attempt_one_receipt.get("logicalAttempt") or 0) == 1
                    and isinstance(attempt_one_issues, list)
                    and len(attempt_one_issues) == 1
                    and isinstance(attempt_one_issues[0], Mapping)
                    and str(attempt_one_issues[0].get("code") or "")
                    in {
                        "primary_one_content_rejected",
                        "primary_one_independent_solution_disagreement",
                        "primary_one_independent_solution_rejected",
                        "primary_one_duplicate_content_rejected",
                    }
                    and str(attempt_one_course.get("status") or "")
                    == "unverified"
                    and attempt_one_course.get("published_at") is None
                    and str(item.get("course_id") or "")
                    == str(attempt_one_course.get("id") or "")
                    and str(item.get("course_version") or "")
                    == str(attempt_one_course.get("version") or "")
                ):
                    return None
        if logical_attempt == 1 and any(
            (histories.get(2) or {}).get(key)
            for key in ("dispatches", "jobs", "candidates", "courses")
        ):
            return None
        current = histories.get(logical_attempt)
        if not isinstance(current, Mapping) or any(
            current.get(key) for key in ("jobs", "candidates", "courses")
        ):
            return None
        dispatches = current.get("dispatches")
        expected = (
            ("outline", 1, "succeeded"),
            ("raw_candidate", 2, "succeeded"),
            ("candidate_repair", 3, "succeeded"),
            ("candidate_repair_retry", 4, "failed_safe"),
        )
        if not isinstance(dispatches, Sequence) or len(dispatches) != len(expected):
            return None
        if any(
            not isinstance(dispatch, Mapping)
            or str(dispatch.get("phase") or "") != phase
            or int(dispatch.get("phase_ordinal") or 0) != ordinal
            or str(dispatch.get("status") or "") != status
            or int(dispatch.get("logical_attempt") or 0) != logical_attempt
            or str(dispatch.get("generation_request_id") or "")
            != str(item.get("active_generation_request_id") or "")
            for dispatch, (phase, ordinal, status) in zip(dispatches, expected)
        ):
            return None
        attempt_times = {
            (
                dispatch.get("attempt_started_at"),
                dispatch.get("attempt_hard_deadline_at"),
            )
            for dispatch in dispatches
        }
        if len(attempt_times) != 1:
            return None
        attempt_started_at, hard_deadline_at = next(iter(attempt_times))
        if not (
            type(attempt_started_at) is int
            and type(hard_deadline_at) is int
            and provider_attempt_deadline_is_valid(
                attempt_started_at, hard_deadline_at
            )
            and int(now) < hard_deadline_at
        ):
            return None
        try:
            repair_checkpoint = json.loads(str(dispatches[2]["checkpoint_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        failed = dispatches[-1]
        if not (
            repair_checkpoint.get("phaseStatus") == "rejected"
            and repair_checkpoint.get("rejectionCode")
            in {
                "candidate_repair_schema_rejected",
                "candidate_repair_originality_rejected",
            }
            and set(repair_checkpoint) == {"phaseStatus", "rejectionCode"}
            and str(failed.get("id") or "") == failed_dispatch_id
            and str(failed.get("input_sha256") or "")
            == expected_input_sha256
            and str(failed.get("safe_error_code") or "")
            == "question_phase_output_rejected"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(failed.get("provider_request_id_hash") or ""),
            )
            is not None
            and type(failed.get("input_tokens")) is int
            and type(failed.get("output_tokens")) is int
            and str(failed.get("billing_evidence") or "") == "reported"
        ):
            return None
        dispatch_cursor = conn.execute(
            """
            UPDATE learning_course_provider_dispatches
            SET status = 'succeeded', checkpoint_json = ?, output_sha256 = ?,
              safe_error_code = NULL
            WHERE id = ? AND build_item_id = ? AND logical_attempt = ?
              AND phase = 'candidate_repair_retry' AND phase_ordinal = 4
              AND status = 'failed_safe'
              AND input_sha256 = ?
              AND safe_error_code = 'question_phase_output_rejected'
              AND checkpoint_json IS NULL AND output_sha256 IS NULL
              AND provider_request_id_hash IS NOT NULL
              AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
              AND billing_evidence = 'reported' AND completed_at IS NOT NULL
            """,
            (
                checkpoint_json,
                output_sha256,
                failed_dispatch_id,
                item_id,
                logical_attempt,
                expected_input_sha256,
            ),
        )
        work_deadline_at = self._formal_content_work_deadline(
            now=int(now),
            outer_deadline=int(hard_deadline_at),
        )
        item_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', content_phase = 'lesson_text',
              error_code = NULL, error_message_safe = NULL, completed_at = NULL,
              content_lease_token = NULL, content_lease_expires_at = NULL,
              content_heartbeat_at = NULL,
              content_provider_attempt_hard_deadline_at = ?,
              content_work_unit_deadline_at = ?, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'failed'
              AND attempt_count = ? AND content_phase = 'failed'
              AND content_gate_status = 'not_started'
              AND content_gate_attempt_count = 0
              AND error_code = 'preparation_content_validation_failed'
              AND (
                (? = 1 AND course_id IS NULL AND course_version IS NULL)
                OR
                (? = 2 AND course_id <=> ? AND course_version <=> ?)
              )
            """,
            (
                int(hard_deadline_at),
                int(work_deadline_at),
                int(now),
                item_id,
                build_id,
                logical_attempt,
                logical_attempt,
                logical_attempt,
                item.get("course_id"),
                item.get("course_version"),
            ),
        )
        build_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND (
                (status = 'failed' AND error_code = 'preparation_content_validation_failed' AND completed_at IS NOT NULL)
                OR (? = 1 AND status = 'running' AND error_code IS NULL)
            )
            """,
            (int(now), build_id, int(audited_high_grade)),
        )
        if any(
            cursor.rowcount != 1
            for cursor in (dispatch_cursor, item_cursor, build_cursor)
        ):
            raise LearningCatalogBuildConflict("Host checkpoint replay CAS drift")
        return self.get_item(conn, item_id=item_id)

    def recover_greetings_attempt_two_host_checkpoint(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        failed_dispatch_id: str,
        expected_input_sha256: str,
        checkpoint: Mapping[str, object],
        now: int,
    ) -> DatabaseRow | None:
        """Backward-compatible greeting Host-checkpoint recovery."""

        return self.recover_billed_candidate_retry_host_checkpoint(
            conn,
            build_id=build_id,
            item_id=item_id,
            expected_subject="english",
            expected_skill_id="greetings",
            failed_dispatch_id=failed_dispatch_id,
            expected_input_sha256=expected_input_sha256,
            checkpoint=checkpoint,
            now=now,
        )

    def recover_shapes_position_attempt_two_host_checkpoint(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        failed_dispatch_id: str,
        expected_input_sha256: str,
        checkpoint: Mapping[str, object],
        now: int,
    ) -> DatabaseRow | None:
        """Seal attempt two after a rejected shape course and billed phase retry."""

        if (
            re.fullmatch(r"[0-9a-f]{64}", expected_input_sha256) is None
            or set(checkpoint) != {"phaseStatus", "candidate"}
            or checkpoint.get("phaseStatus") != "accepted"
            or not isinstance(checkpoint.get("candidate"), Mapping)
        ):
            raise ValueError("shape Host checkpoint recovery input is invalid")
        checkpoint_json = self.encode_json(checkpoint)
        output_sha256 = hashlib.sha256(
            checkpoint_json.encode("utf-8")
        ).hexdigest()
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_validation_failed"
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or str(item.get("grade_code") or "") != "primary_1"
            or str(item.get("subject") or "") != "math"
            or str(item.get("skill_id") or "") != "shapes_position"
            or int(item.get("variant_ordinal") or 0) != 1
            or str(item.get("status") or "") != "failed"
            or int(item.get("attempt_count") or 0) != 2
            or int(item.get("content_claim_attempt_ordinal") or 0) != 2
            or str(item.get("claim_origin_status") or "") != "failed"
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "") + ".attempt2"
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "") != "not_started"
            or int(item.get("content_gate_attempt_count") or 0) != 0
            or not str(item.get("course_id") or "")
            or str(item.get("course_version") or "") != "0.0.0-candidate"
            or str(item.get("error_code") or "")
            != "preparation_content_validation_failed"
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        try:
            attempt_one = self._content_attempt_evidence_from_histories(
                item=item,
                histories=histories,
                attempt=1,
            )
        except LearningCatalogBuildConflict:
            return None
        prior_candidate = attempt_one.get("candidate")
        prior_course = attempt_one.get("course")
        prior_job = attempt_one.get("job")
        if not all(
            isinstance(value, Mapping)
            for value in (prior_candidate, prior_course, prior_job)
        ):
            return None
        try:
            prior_validation = json.loads(
                str(prior_candidate.get("validation_json") or "")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        prior_receipt = (
            prior_validation.get("hostGateReceipt")
            if isinstance(prior_validation, Mapping)
            else None
        )
        prior_receipt_hash = (
            prior_validation.get("hostGateReceiptHash")
            if isinstance(prior_validation, Mapping)
            else None
        )
        prior_issues = (
            prior_receipt.get("issues")
            if isinstance(prior_receipt, Mapping)
            else None
        )
        if not (
            str(prior_job.get("request_id") or "")
            == str(item.get("generation_request_id") or "")
            and str(prior_job.get("status") or "") == "failed"
            and str(prior_job.get("error_code") or "")
            == "preparation_content_validation_failed"
            and str(prior_candidate.get("status") or "") == "rejected"
            and str(prior_candidate.get("error_code") or "")
            == "preparation_content_validation_failed"
            and str(prior_candidate.get("course_id") or "")
            == str(item.get("course_id") or "")
            and str(prior_candidate.get("course_version") or "")
            == str(item.get("course_version") or "")
            and str(prior_course.get("id") or "")
            == str(item.get("course_id") or "")
            and str(prior_course.get("version") or "")
            == str(item.get("course_version") or "")
            and str(prior_course.get("status") or "") == "unverified"
            and str(prior_course.get("quality_status") or "")
            == "legacy_unreviewed"
            and str(prior_receipt.get("outcome") or "") == "rejected"
            and str(prior_receipt.get("catalogItemId") or "") == item_id
            and str(prior_receipt.get("skillId") or "") == "shapes_position"
            and int(prior_receipt.get("logicalAttempt") or 0) == 1
            and int(prior_receipt.get("variantOrdinal") or 0) == 1
            and isinstance(prior_issues, list)
            and len(prior_issues) == 1
            and str((prior_issues[0] or {}).get("code") or "")
            == "primary_one_content_rejected"
            and re.fullmatch(r"[0-9a-f]{64}", str(prior_receipt_hash or ""))
            is not None
            and hashlib.sha256(
                self.encode_json(prior_receipt).encode("utf-8")
            ).hexdigest()
            == prior_receipt_hash
        ):
            return None
        current = histories.get(2)
        if not isinstance(current, Mapping) or any(
            current.get(key) for key in ("jobs", "candidates", "courses")
        ):
            return None
        dispatches = current.get("dispatches")
        expected = (
            ("outline", 1, "succeeded"),
            ("raw_candidate", 2, "succeeded"),
            ("candidate_repair", 3, "succeeded"),
            ("candidate_repair_retry", 4, "failed_safe"),
        )
        if not isinstance(dispatches, Sequence) or len(dispatches) != len(expected):
            return None
        if any(
            not isinstance(dispatch, Mapping)
            or str(dispatch.get("phase") or "") != phase
            or int(dispatch.get("phase_ordinal") or 0) != ordinal
            or str(dispatch.get("status") or "") != status
            or int(dispatch.get("logical_attempt") or 0) != 2
            or str(dispatch.get("generation_request_id") or "")
            != str(item.get("active_generation_request_id") or "")
            for dispatch, (phase, ordinal, status) in zip(dispatches, expected)
        ):
            return None
        attempt_times = {
            (
                dispatch.get("attempt_started_at"),
                dispatch.get("attempt_hard_deadline_at"),
            )
            for dispatch in dispatches
        }
        if len(attempt_times) != 1:
            return None
        attempt_started_at, hard_deadline_at = next(iter(attempt_times))
        if not (
            type(attempt_started_at) is int
            and type(hard_deadline_at) is int
            and provider_attempt_deadline_is_valid(
                attempt_started_at, hard_deadline_at
            )
            and int(now) < hard_deadline_at
        ):
            return None
        try:
            repair_checkpoint = json.loads(str(dispatches[2]["checkpoint_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        failed = dispatches[-1]
        if not (
            repair_checkpoint
            == {
                "phaseStatus": "rejected",
                "rejectionCode": "candidate_repair_schema_rejected",
            }
            and str(failed.get("id") or "") == failed_dispatch_id
            and str(failed.get("input_sha256") or "")
            == expected_input_sha256
            and str(failed.get("safe_error_code") or "")
            == "question_phase_output_rejected"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(failed.get("provider_request_id_hash") or ""),
            )
            is not None
            and type(failed.get("input_tokens")) is int
            and type(failed.get("output_tokens")) is int
            and str(failed.get("billing_evidence") or "") == "reported"
        ):
            return None
        dispatch_cursor = conn.execute(
            """
            UPDATE learning_course_provider_dispatches
            SET status = 'succeeded', checkpoint_json = ?, output_sha256 = ?,
              safe_error_code = NULL
            WHERE id = ? AND build_item_id = ? AND logical_attempt = 2
              AND phase = 'candidate_repair_retry' AND phase_ordinal = 4
              AND status = 'failed_safe' AND input_sha256 = ?
              AND safe_error_code = 'question_phase_output_rejected'
              AND checkpoint_json IS NULL AND output_sha256 IS NULL
              AND provider_request_id_hash IS NOT NULL
              AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
              AND billing_evidence = 'reported' AND completed_at IS NOT NULL
            """,
            (
                checkpoint_json,
                output_sha256,
                failed_dispatch_id,
                item_id,
                expected_input_sha256,
            ),
        )
        work_deadline_at = self._formal_content_work_deadline(
            now=int(now),
            outer_deadline=int(hard_deadline_at),
        )
        item_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', content_phase = 'lesson_text',
              error_code = NULL, error_message_safe = NULL, completed_at = NULL,
              content_lease_token = NULL, content_lease_expires_at = NULL,
              content_heartbeat_at = NULL,
              content_provider_attempt_hard_deadline_at = ?,
              content_work_unit_deadline_at = ?, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'failed'
              AND attempt_count = 2 AND claim_origin_status = 'failed'
              AND content_phase = 'failed'
              AND content_gate_status = 'not_started'
              AND content_gate_attempt_count = 0
              AND error_code = 'preparation_content_validation_failed'
              AND course_id = ? AND course_version = '0.0.0-candidate'
            """,
            (
                int(hard_deadline_at),
                int(work_deadline_at),
                int(now),
                item_id,
                build_id,
                str(item.get("course_id") or ""),
            ),
        )
        build_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
              AND error_code = 'preparation_content_validation_failed'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if any(
            cursor.rowcount != 1
            for cursor in (dispatch_cursor, item_cursor, build_cursor)
        ):
            raise LearningCatalogBuildConflict("shape Host checkpoint replay CAS drift")
        return self.get_item(conn, item_id=item_id)

    def recover_addition_subtraction_host_rule_replay(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        expected_receipt_hash: str,
        now: int,
    ) -> DatabaseRow | None:
        return self._recover_primary_one_host_rule_replay(
            conn,
            build_id=build_id,
            item_id=item_id,
            expected_receipt_hash=expected_receipt_hash,
            expected_skill_id="addition_subtraction_20",
            now=now,
        )

    def recover_shapes_position_host_rule_replay(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        expected_receipt_hash: str,
        now: int,
    ) -> DatabaseRow | None:
        return self._recover_primary_one_host_rule_replay(
            conn,
            build_id=build_id,
            item_id=item_id,
            expected_receipt_hash=expected_receipt_hash,
            expected_skill_id="shapes_position",
            now=now,
        )

    def recover_characters_words_host_rule_replay(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        expected_receipt_hash: str,
        now: int,
    ) -> DatabaseRow | None:
        return self._recover_primary_one_host_rule_replay(
            conn,
            build_id=build_id,
            item_id=item_id,
            expected_receipt_hash=expected_receipt_hash,
            expected_skill_id="characters_words",
            now=now,
        )

    def recover_completed_host_gate_audit_replay(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        expected_receipt_hash: str,
        now: int,
    ) -> DatabaseRow | None:
        """Reopen a build fenced only after its latest Host pass was persisted."""

        if re.fullmatch(r"[0-9a-f]{64}", expected_receipt_hash) is None:
            raise ValueError("Host audit replay receipt is invalid")
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_contract_drift"
            or len(rows) != formal_target_course_count(build)
            or any(
                str(row.get("status") or "") not in {"pending", "course_ready"}
                for row in rows
            )
            or str(item.get("status") or "") != "course_ready"
            or str(item.get("content_phase") or "") != "course_ready"
            or str(item.get("content_gate_status") or "") != "passed"
            or int(item.get("attempt_count") or 0) != 2
            or int(item.get("content_claim_attempt_ordinal") or 0) != 2
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "") + ".attempt2"
            or str(item.get("content_receipt_hash") or "")
            != expected_receipt_hash
            or str(item.get("content_validation_contract_version") or "")
            != formal_content_validation_identity(preparation_authority_grade(build))["contentValidationContractVersion"]
            or not str(item.get("course_id") or "")
            or not str(item.get("course_version") or "")
            or item.get("content_lease_token") is not None
            or item.get("content_lease_expires_at") is not None
            or item.get("content_work_unit_deadline_at") is not None
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        current = self._content_attempt_evidence_from_histories(
            item=item,
            histories=histories,
            attempt=2,
        )
        job = current.get("job")
        candidate = current.get("candidate")
        course = current.get("course")
        if not all(isinstance(value, Mapping) for value in (job, candidate, course)):
            return None
        try:
            validation = json.loads(str(candidate.get("validation_json") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        receipt = validation.get("hostGateReceipt")
        if not (
            str(job.get("status") or "") == "validated"
            and str(candidate.get("status") or "") == "course_validated"
            and str(validation.get("hostGateReceiptHash") or "")
            == expected_receipt_hash
            and isinstance(receipt, Mapping)
            and str(receipt.get("outcome") or "") == "passed"
            and str(course.get("status") or "") == "validated"
            and str(course.get("id") or "") == str(item.get("course_id") or "")
            and str(course.get("version") or "")
            == str(item.get("course_version") or "")
            and course.get("published_at") is None
            and course.get("retired_at") is None
        ):
            return None
        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
              AND error_code = 'preparation_content_contract_drift'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if cursor.rowcount != 1:
            raise LearningCatalogBuildConflict("Host audit replay CAS drift")
        return self.get_item(conn, item_id=item_id)

    def _recover_primary_one_host_rule_replay(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        expected_receipt_hash: str,
        expected_skill_id: str,
        now: int,
    ) -> DatabaseRow | None:
        """Reopen one rejected attempt-two candidate for local Host replay."""

        if (
            re.fullmatch(r"[0-9a-f]{64}", expected_receipt_hash) is None
            or expected_skill_id
            not in {
                "addition_subtraction_20",
                "shapes_position",
                "characters_words",
            }
        ):
            raise ValueError("Host replay authority is invalid")
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_validation_failed"
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or str(item.get("grade_code") or "") != "primary_1"
            or str(item.get("subject") or "")
            != ("chinese" if expected_skill_id == "characters_words" else "math")
            or str(item.get("skill_id") or "") != expected_skill_id
            or str(item.get("status") or "") != "failed"
            or int(item.get("attempt_count") or 0) != 2
            or int(item.get("content_claim_attempt_ordinal") or 0) != 2
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "") + ".attempt2"
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "")
            != "failed_deterministic"
            or int(item.get("content_gate_attempt_count") or 0) != 1
            or not str(item.get("course_id") or "")
            or not str(item.get("course_version") or "")
            or str(item.get("error_code") or "")
            != "preparation_content_validation_failed"
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if not isinstance(histories, Mapping):
            return None
        current = self._content_attempt_evidence_from_histories(
            item=item,
            histories=histories,
            attempt=2,
        )
        job = current.get("job")
        candidate = current.get("candidate")
        course = current.get("course")
        if not all(isinstance(value, Mapping) for value in (job, candidate, course)):
            return None
        raw_validation = candidate.get("validation_json")
        if not isinstance(raw_validation, str):
            return None
        try:
            validation = json.loads(raw_validation)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        receipt = validation.get("hostGateReceipt")
        issues = receipt.get("issues") if isinstance(receipt, Mapping) else None
        if not (
            str(job.get("status") or "") == "failed"
            and str(job.get("error_code") or "")
            == "preparation_content_validation_failed"
            and job.get("completed_at") is not None
            and str(candidate.get("status") or "") == "rejected"
            and str(candidate.get("error_code") or "")
            == "preparation_content_validation_failed"
            and str(validation.get("schemaVersion") or "")
            == "mira.learning.primary-1-host-gate-evidence.v1"
            and str(validation.get("hostGateReceiptHash") or "")
            == expected_receipt_hash
            and isinstance(receipt, Mapping)
            and str(receipt.get("outcome") or "") == "rejected"
            and int(receipt.get("logicalAttempt") or 0) == 2
            and isinstance(issues, list)
            and len(issues) == 1
            and isinstance(issues[0], Mapping)
            and str(issues[0].get("code") or "")
            == (
                "primary_one_independent_solution_disagreement"
                if expected_skill_id == "characters_words"
                else "primary_one_content_rejected"
            )
            and str(course.get("status") or "") == "unverified"
            and str(course.get("id") or "") == str(candidate.get("course_id") or "")
            and str(course.get("version") or "")
            == str(candidate.get("course_version") or "")
            and course.get("published_at") is None
            and course.get("retired_at") is None
        ):
            return None
        candidate_cursor = conn.execute(
            """
            UPDATE learning_course_generation_candidates
            SET status = 'generated', validation_json = NULL,
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'rejected'
              AND error_code = 'preparation_content_validation_failed'
              AND validation_json = ?
            """,
            (int(now), candidate["id"], raw_validation),
        )
        job_cursor = conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET status = 'generating', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
              AND error_code = 'preparation_content_validation_failed'
              AND completed_at IS NOT NULL
            """,
            (int(now), job["id"]),
        )
        item_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', content_phase = 'host_gate_pending',
              content_gate_status = 'retry_wait', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'failed'
              AND attempt_count = 2 AND content_phase = 'failed'
              AND content_gate_status = 'failed_deterministic'
              AND content_gate_attempt_count = 1
              AND error_code = 'preparation_content_validation_failed'
            """,
            (int(now), item_id, build_id),
        )
        build_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
              AND error_code = 'preparation_content_validation_failed'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if any(
            cursor.rowcount != 1
            for cursor in (
                candidate_cursor,
                job_cursor,
                item_cursor,
                build_cursor,
            )
        ):
            raise LearningCatalogBuildConflict("Host rule replay CAS drift")
        return self.get_item(conn, item_id=item_id)

    def recover_addition_subtraction_host_promotion_replay(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        now: int,
    ) -> DatabaseRow | None:
        """Resume the exact unpublished course blocked during Host promotion."""

        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        item = next(
            (row for row in rows if str(row.get("id") or "") == item_id),
            None,
        )
        if (
            release is None
            or build is None
            or item is None
            or not self._content_authority_is_exact(
                conn,
                release=release,
                build=build,
                rows=rows,
                allow_terminal=True,
            )
            or str(build.get("status") or "") != "failed"
            or str(build.get("error_code") or "")
            != "preparation_content_contract_drift"
            or sum(str(row.get("status") or "") == "failed" for row in rows)
            != 1
            or any(
                str(row.get("status") or "")
                not in {"pending", "course_ready", "failed"}
                for row in rows
            )
            or str(item.get("grade_code") or "") != "primary_1"
            or str(item.get("subject") or "") != "math"
            or str(item.get("skill_id") or "") != "addition_subtraction_20"
            or str(item.get("status") or "") != "failed"
            or int(item.get("attempt_count") or 0) != 2
            or int(item.get("content_claim_attempt_ordinal") or 0) != 2
            or str(item.get("active_generation_request_id") or "")
            != str(item.get("generation_request_id") or "") + ".attempt2"
            or str(item.get("content_phase") or "") != "failed"
            or str(item.get("content_gate_status") or "")
            != "failed_deterministic"
            or int(item.get("content_gate_attempt_count") or 0) != 2
            or str(item.get("error_code") or "")
            != "preparation_content_contract_drift"
            or not str(item.get("course_id") or "")
            or not str(item.get("course_version") or "")
        ):
            return None
        histories = self._load_content_attempt_histories_locked(
            conn, rows=[item]
        ).get(item_id)
        if (
            not isinstance(histories, Mapping)
            or self._provider_rejected_addition_subtraction_attempt_one_evidence_from_histories(
                item=item,
                histories=histories,
            )
            is None
        ):
            return None
        current = self._content_attempt_evidence_from_histories(
            item=item,
            histories=histories,
            attempt=2,
        )
        job = current.get("job")
        candidate = current.get("candidate")
        course = current.get("course")
        dispatches = current.get("dispatches")
        if not (
            isinstance(job, Mapping)
            and isinstance(candidate, Mapping)
            and isinstance(course, Mapping)
            and isinstance(dispatches, Sequence)
            and bool(dispatches)
            and all(
                isinstance(dispatch, Mapping)
                and str(dispatch.get("status") or "") == "succeeded"
                for dispatch in dispatches
            )
            and str(job.get("status") or "") == "generating"
            and job.get("error_code") is None
            and job.get("completed_at") is None
            and str(candidate.get("status") or "") == "generated"
            and candidate.get("validation_json") is None
            and candidate.get("error_code") is None
            and candidate.get("published_at") is None
            and str(candidate.get("course_id") or "")
            == str(item.get("course_id") or "")
            and str(candidate.get("course_version") or "")
            == str(item.get("course_version") or "")
            and str(course.get("id") or "")
            == str(candidate.get("course_id") or "")
            and str(course.get("version") or "")
            == str(candidate.get("course_version") or "")
            and str(course.get("grade_code") or "")
            == str(candidate.get("grade_code") or "")
            and str(course.get("subject") or "")
            == str(candidate.get("subject") or "")
            and str(course.get("node_code") or "")
            == str(candidate.get("node_code") or "")
            and str(course.get("curriculum_version") or "")
            == str(candidate.get("curriculum_version") or "")
            and str(course.get("boundary_version") or "")
            == str(candidate.get("boundary_version") or "")
            and str(course.get("title") or "")
            == str(candidate.get("title") or "")
            and str(course.get("objective") or "")
            == str(candidate.get("objective") or "")
            and str(course.get("generation_request_id") or "")
            == str(item.get("active_generation_request_id") or "")
            and str(course.get("generation_content_hash") or "")
            == str(candidate.get("content_hash") or "")
            and str(course.get("content_json") or "")
            == str(candidate.get("content_json") or "")
            and str(course.get("status") or "") == "unverified"
            and str(course.get("quality_status") or "")
            == "legacy_unreviewed"
            and str(course.get("content_origin") or "")
            == "openmaic_generated"
            and str(course.get("generator") or "")
            == str(job.get("generator") or "")
            and course.get("published_at") is None
            and course.get("retired_at") is None
        ):
            return None
        item_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', content_phase = 'host_gate_pending',
              content_gate_status = 'retry_wait', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL,
              content_lease_token = NULL, content_lease_expires_at = NULL,
              content_heartbeat_at = NULL,
              content_work_unit_deadline_at = NULL, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'failed'
              AND attempt_count = 2 AND content_phase = 'failed'
              AND content_gate_status = 'failed_deterministic'
              AND content_gate_attempt_count = 2
              AND error_code = 'preparation_content_contract_drift'
            """,
            (int(now), item_id, build_id),
        )
        build_cursor = conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'failed'
              AND error_code = 'preparation_content_contract_drift'
              AND completed_at IS NOT NULL
            """,
            (int(now), build_id),
        )
        if item_cursor.rowcount != 1 or build_cursor.rowcount != 1:
            raise LearningCatalogBuildConflict("Host promotion replay CAS drift")
        return self.get_item(conn, item_id=item_id)

    def load_content_proof_inventory(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
    ) -> Mapping[str, object]:
        """Load raw proof authority in the formal Task-7 lock order.

        This method deliberately returns rows, not a trusted Boolean.  The
        release service replays the pure Task-5/6 graph and Host validators
        while these locks remain held.
        """
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        if release is None or build is None:
            return {
                "release": release,
                "build": build,
                "items": rows,
                "evidence": [],
                "attemptHistoriesByItem": {},
                "historicalQuestionFingerprintsByItem": {},
            }
        proof_rows = [
            row
            for row in rows
            if str(row.get("status") or "") in {"course_ready", "failed"}
            and int(row.get("attempt_count") or 0) in {1, 2}
        ]
        proof_rows.sort(
            key=lambda row: (
                int(row.get("subject_ordinal") or 0),
                int(row.get("boundary_ordinal") or 0),
                int(row.get("variant_ordinal") or 0),
                str(row.get("id") or ""),
            )
        )

        history_rows = [
            row
            for row in rows
            if int(row.get("attempt_count") or 0) in {1, 2}
            and str(row.get("status") or "")
            in {"processing", "course_ready", "failed"}
        ]
        history_rows.sort(
            key=lambda row: (
                int(row.get("subject_ordinal") or 0),
                int(row.get("boundary_ordinal") or 0),
                int(row.get("variant_ordinal") or 0),
                str(row.get("id") or ""),
            )
        )
        histories = self._load_content_attempt_histories_locked(
            conn, rows=history_rows
        )
        historical_fingerprints_by_item = {
            str(row["id"]): self._historical_question_fingerprint_snapshots(
                conn,
                item=row,
                histories=histories[str(row["id"])],
            )
            for row in history_rows
        }
        evidence = [
            {
                "item": dict(row),
                "attemptHistories": histories[str(row["id"])],
                "historicalQuestionFingerprintsByAttempt": (
                    historical_fingerprints_by_item[str(row["id"])]
                ),
            }
            for row in proof_rows
        ]
        return {
            "release": dict(release),
            "build": dict(build),
            "items": [dict(row) for row in rows],
            "evidence": evidence,
            "attemptHistoriesByItem": histories,
            "historicalQuestionFingerprintsByItem": (
                historical_fingerprints_by_item
            ),
        }

    def _historical_question_fingerprint_snapshots(
        self,
        conn: DatabaseConnection,
        *,
        item: Mapping[str, object],
        histories: Mapping[int, Mapping[str, object]],
    ) -> dict[int, list[str]]:
        try:
            return historical_question_fingerprint_snapshots(
                conn,
                item=item,
                histories=histories,
            )
        except ValueError as exc:
            raise LearningCatalogBuildConflict(str(exc)) from exc

    def _historical_question_fingerprints(
        self,
        conn: DatabaseConnection,
        *,
        item: Mapping[str, object],
        attempt_started_at: int | None = None,
    ) -> list[str]:
        """Rebuild the immutable pre-attempt question inventory.

        The global semantic course fingerprint is intentionally unique.  A
        formal build must therefore avoid questions from every earlier course
        for the same target, including retired and unverified rows.  The
        attempt start is a stable cutoff, so later audit/replay cannot absorb
        courses written after Provider work began.
        """

        try:
            return historical_question_fingerprints(
                conn,
                item=item,
                attempt_started_at=attempt_started_at,
            )
        except ValueError as exc:
            raise LearningCatalogBuildConflict(str(exc)) from exc

    def _load_content_attempt_histories_locked(
        self,
        conn: DatabaseConnection,
        *,
        rows: Sequence[Mapping[str, object]],
    ) -> dict[str, dict[int, Mapping[str, object]]]:
        if not rows:
            return {}

        item_ids = sorted({str(row["id"]) for row in rows})
        item_placeholders = ", ".join("?" for _ in item_ids)
        dispatches = list(
            conn.execute(
                f"""
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id IN ({item_placeholders})
                  AND logical_attempt IN (1, 2)
                ORDER BY build_item_id, logical_attempt, phase_ordinal, id
                FOR UPDATE
                """,
                tuple(item_ids),
            ).fetchall()
        )

        requests_by_item = {
            str(row["id"]): {
                1: str(row.get("generation_request_id") or ""),
                2: str(row.get("generation_request_id") or "") + ".attempt2",
            }
            for row in rows
        }
        request_ids = sorted(
            {
                request_id
                for attempts in requests_by_item.values()
                for request_id in attempts.values()
            }
        )
        request_placeholders = ", ".join("?" for _ in request_ids)
        jobs = list(
            conn.execute(
                f"""
                SELECT * FROM learning_course_generation_jobs
                WHERE request_id IN ({request_placeholders})
                ORDER BY request_id, id
                FOR UPDATE
                """,
                tuple(request_ids),
            ).fetchall()
        )

        job_ids = sorted({str(job["id"]) for job in jobs})
        candidates: list[DatabaseRow] = []
        if job_ids:
            job_placeholders = ", ".join("?" for _ in job_ids)
            candidates = list(
                conn.execute(
                    f"""
                    SELECT * FROM learning_course_generation_candidates
                    WHERE job_id IN ({job_placeholders})
                    ORDER BY job_id, ordinal, id
                    FOR UPDATE
                    """,
                    tuple(job_ids),
                ).fetchall()
            )

        candidate_pairs = sorted(
            {
                (str(candidate["course_id"]), str(candidate["course_version"]))
                for candidate in candidates
            }
        )
        course_clauses = [
            f"generation_request_id IN ({request_placeholders})"
        ]
        course_params: list[object] = list(request_ids)
        if candidate_pairs:
            pair_placeholders = ", ".join("(?, ?)" for _ in candidate_pairs)
            course_clauses.append(
                f"(id, version) IN ({pair_placeholders})"
            )
            for course_id, course_version in candidate_pairs:
                course_params.extend((course_id, course_version))
        courses = list(
            conn.execute(
                f"""
                SELECT * FROM learning_courses
                WHERE {' OR '.join(course_clauses)}
                ORDER BY id, version
                FOR UPDATE
                """,
                tuple(course_params),
            ).fetchall()
        )

        result: dict[str, dict[int, Mapping[str, object]]] = {}
        for row in rows:
            item_id = str(row["id"])
            attempts: dict[int, Mapping[str, object]] = {}
            for attempt in (1, 2):
                request_id = requests_by_item[item_id][attempt]
                attempt_jobs = [
                    dict(job)
                    for job in jobs
                    if str(job.get("request_id") or "") == request_id
                ]
                attempt_job_ids = {str(job["id"]) for job in attempt_jobs}
                attempt_candidates = [
                    dict(candidate)
                    for candidate in candidates
                    if str(candidate.get("job_id") or "") in attempt_job_ids
                ]
                attempt_pairs = {
                    (
                        str(candidate.get("course_id") or ""),
                        str(candidate.get("course_version") or ""),
                    )
                    for candidate in attempt_candidates
                }
                attempts[attempt] = {
                    "requestId": request_id,
                    "dispatches": [
                        dict(dispatch)
                        for dispatch in dispatches
                        if str(dispatch.get("build_item_id") or "") == item_id
                        and int(dispatch.get("logical_attempt") or 0) == attempt
                    ],
                    "jobs": attempt_jobs,
                    "candidates": attempt_candidates,
                    "courses": [
                        dict(course)
                        for course in courses
                        if str(course.get("generation_request_id") or "")
                        == request_id
                        or (
                            str(course.get("id") or ""),
                            str(course.get("version") or ""),
                        )
                        in attempt_pairs
                    ],
                }
            if int(row.get('attempt_count') or 0) == 2 and row.get('grade_code') != 'primary_1':
                from services.learning_content_recovery import load_recovery_receipt
                receipt = load_recovery_receipt(conn, build_id=str(row['build_job_id']), item_id=item_id)
                if receipt is not None:
                    attempts[1]['recoveryReceipt'] = receipt
            result[item_id] = attempts
        return result

    @staticmethod
    def _content_attempt_evidence_from_histories(
        *,
        item: Mapping[str, object],
        histories: Mapping[int, Mapping[str, object]],
        attempt: int,
        require_course: bool = True,
    ) -> Mapping[str, object]:
        history = histories.get(int(attempt))
        if not isinstance(history, Mapping):
            raise LearningCatalogBuildConflict("content attempt history is missing")
        jobs = history.get("jobs")
        candidates = history.get("candidates")
        courses = history.get("courses")
        if (
            not isinstance(jobs, Sequence)
            or not isinstance(candidates, Sequence)
            or not isinstance(courses, Sequence)
            or len(jobs) != 1
            or len(candidates) != 1
            or (
                len(courses) != 1
                if require_course
                else len(courses) not in {0, 1}
            )
        ):
            raise LearningCatalogBuildConflict(
                "content attempt persistence cardinality drift"
            )
        return {
            "item": dict(item),
            "dispatches": history.get("dispatches"),
            "job": jobs[0],
            "candidate": candidates[0],
            "course": courses[0] if courses else None,
        }

    @staticmethod
    def _zero_call_number_sense_attempt_one_evidence_from_histories(
        *,
        item: Mapping[str, object],
        histories: Mapping[int, Mapping[str, object]],
    ) -> Mapping[str, object] | None:
        """Recognize the one attempt-one history that produced no candidate."""

        request_id = str(item.get("generation_request_id") or "")
        host_target = (
            str(item.get("subject") or ""),
            str(item.get("skill_id") or ""),
        )
        if (
            str(item.get("grade_code") or "") != "primary_1"
            or host_target
            not in {("math", "number_sense_20"), ("english", "letters_sounds")}
            or int(item.get("attempt_count") or 0) != 2
            or str(item.get("active_generation_request_id") or "")
            != request_id + ".attempt2"
        ):
            return None
        history = histories.get(1)
        if not isinstance(history, Mapping):
            return None
        if (
            str(history.get("requestId") or "") != request_id
            or any(history.get(key) for key in ("jobs", "candidates", "courses"))
        ):
            return None
        dispatches = history.get("dispatches")
        if not isinstance(dispatches, Sequence) or len(dispatches) != 3:
            return None
        expected = (
            ("outline", 1, "succeeded"),
            ("raw_candidate", 2, "succeeded"),
            ("candidate_repair", 3, "failed_safe"),
        )
        if any(
            not isinstance(dispatch, Mapping)
            or str(dispatch.get("phase") or "") != phase
            or int(dispatch.get("phase_ordinal") or 0) != ordinal
            or str(dispatch.get("status") or "") != status
            or int(dispatch.get("logical_attempt") or 0) != 1
            or str(dispatch.get("generation_request_id") or "") != request_id
            or re.fullmatch(
                r"[0-9a-f]{64}", str(dispatch.get("input_sha256") or "")
            )
            is None
            for dispatch, (phase, ordinal, status) in zip(dispatches, expected)
        ):
            return None
        if any(
            dispatch.get("checkpoint_json") is None
            or re.fullmatch(
                r"[0-9a-f]{64}", str(dispatch.get("output_sha256") or "")
            )
            is None
            for dispatch in dispatches[:2]
        ):
            return None
        failed = dispatches[-1]
        if not (
            str(failed.get("safe_error_code") or "")
            == "question_phase_preflight_rejected"
            and failed.get("provider_request_id_hash") is None
            and failed.get("input_tokens") is None
            and failed.get("output_tokens") is None
            and str(failed.get("billing_evidence") or "") == "unknown"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
        ):
            return None
        return {
            "recoveryKind": "zero_call_canonical_host_preflight.v1",
            "item": dict(item),
            "dispatches": list(dispatches),
            "failedDispatchId": str(failed.get("id") or ""),
            "failedInputSha256": str(failed.get("input_sha256") or ""),
        }

    @staticmethod
    def _provider_rejected_addition_subtraction_attempt_one_evidence_from_histories(
        *,
        item: Mapping[str, object],
        histories: Mapping[int, Mapping[str, object]],
    ) -> Mapping[str, object] | None:
        request_id = str(item.get("generation_request_id") or "")
        if (
            str(item.get("grade_code") or "") != "primary_1"
            or (
                str(item.get("subject") or ""),
                str(item.get("skill_id") or ""),
            )
            not in {
                ("math", "addition_subtraction_20"),
                ("english", "greetings"),
            }
            or int(item.get("attempt_count") or 0) != 2
            or str(item.get("active_generation_request_id") or "")
            != request_id + ".attempt2"
        ):
            return None
        history = histories.get(1)
        if not isinstance(history, Mapping) or (
            str(history.get("requestId") or "") != request_id
            or any(history.get(key) for key in ("jobs", "candidates", "courses"))
        ):
            return None
        dispatches = history.get("dispatches")
        expected = (
            ("outline", 1, "succeeded"),
            ("raw_candidate", 2, "succeeded"),
            ("candidate_repair", 3, "succeeded"),
            ("candidate_repair_retry", 4, "failed_safe"),
        )
        if not isinstance(dispatches, Sequence) or len(dispatches) != len(expected):
            return None
        if any(
            not isinstance(dispatch, Mapping)
            or str(dispatch.get("phase") or "") != phase
            or int(dispatch.get("phase_ordinal") or 0) != ordinal
            or str(dispatch.get("status") or "") != status
            or int(dispatch.get("logical_attempt") or 0) != 1
            or str(dispatch.get("generation_request_id") or "") != request_id
            or re.fullmatch(
                r"[0-9a-f]{64}", str(dispatch.get("input_sha256") or "")
            )
            is None
            for dispatch, (phase, ordinal, status) in zip(dispatches, expected)
        ):
            return None
        if any(
            dispatch.get("checkpoint_json") is None
            or re.fullmatch(
                r"[0-9a-f]{64}", str(dispatch.get("output_sha256") or "")
            )
            is None
            for dispatch in dispatches[:3]
        ):
            return None
        try:
            repair_checkpoint = json.loads(str(dispatches[2]["checkpoint_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if repair_checkpoint != {
            "phaseStatus": "rejected",
            "rejectionCode": "candidate_repair_schema_rejected",
        }:
            return None
        failed = dispatches[-1]
        if not (
            str(failed.get("safe_error_code") or "")
            == "question_phase_output_rejected"
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(failed.get("provider_request_id_hash") or ""),
            )
            is not None
            and type(failed.get("input_tokens")) is int
            and int(failed["input_tokens"]) >= 0
            and type(failed.get("output_tokens")) is int
            and int(failed["output_tokens"]) >= 0
            and str(failed.get("billing_evidence") or "") == "reported"
            and failed.get("checkpoint_json") is None
            and failed.get("output_sha256") is None
        ):
            return None
        return {
            "recoveryKind": "provider_rejected_addition_subtraction_retry.v1",
            "item": dict(item),
            "dispatches": list(dispatches),
            "failedDispatchId": str(failed.get("id") or ""),
            "failedInputSha256": str(failed.get("input_sha256") or ""),
        }

    @classmethod
    def _attempt_one_evidence_for_active_retry(
        cls,
        *,
        item: Mapping[str, object],
        histories: Mapping[int, Mapping[str, object]],
    ) -> Mapping[str, object]:
        from services.learning_content_recovery import candidate_less_evidence
        audited_recovery = candidate_less_evidence(item=item, histories=histories)
        if audited_recovery is not None:
            return audited_recovery
        zero_call = cls._zero_call_number_sense_attempt_one_evidence_from_histories(
            item=item,
            histories=histories,
        )
        if zero_call is not None:
            return zero_call
        provider_rejected = (
            cls._provider_rejected_addition_subtraction_attempt_one_evidence_from_histories(
                item=item,
                histories=histories,
            )
        )
        if provider_rejected is not None:
            return provider_rejected
        return cls._content_attempt_evidence_from_histories(
            item=item,
            histories=histories,
            attempt=1,
        )

    def list_content_dispatches(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        logical_attempt: int,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = ?
                ORDER BY phase_ordinal, id
                FOR UPDATE
                """,
                (item_id, int(logical_attempt)),
            ).fetchall()
        )

    def load_content_provider_finalize_authority(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        logical_attempt: int,
        generation_request_id: str,
        phase: str,
        phase_ordinal: int,
        lease_token: str,
        attempt_started_at: int,
        outer_deadline_at: int,
        work_deadline_at: int,
        now: int,
    ) -> Mapping[str, object]:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        row = next((value for value in rows if str(value["id"]) == item_id), None)
        if release is None or build is None or row is None:
            return {
                "release": release,
                "build": build,
                "items": [dict(value) for value in rows],
                "item": None,
                "dispatches": [],
                "persistedDispatch": None,
                "priorEvidence": [],
                "attemptOneEvidence": None,
            }
        prior_rows = [
            value
            for value in rows
            if str(value.get("subject") or "")
            == str(row.get("subject") or "")
            and str(value.get("skill_id") or "")
            == str(row.get("skill_id") or "")
            and str(value.get("boundary_version") or "")
            == str(row.get("boundary_version") or "")
            and int(value.get("variant_ordinal") or 0)
            < int(row.get("variant_ordinal") or 0)
        ]
        authority_rows = [*prior_rows, row]
        histories = self._load_content_attempt_histories_locked(
            conn, rows=authority_rows
        )
        historical_snapshots = {
            str(value["id"]): self._historical_question_fingerprint_snapshots(
                conn,
                item=value,
                histories=histories[str(value["id"])],
            )
            for value in authority_rows
        }
        item_histories = histories[str(row["id"])]
        current_history = item_histories.get(int(logical_attempt), {})
        dispatches = current_history.get("dispatches", [])
        target = [
            dispatch
            for dispatch in dispatches
            if str(dispatch.get("phase") or "") == phase
            and int(dispatch.get("phase_ordinal") or 0) == int(phase_ordinal)
        ]
        prior_evidence = [
            {
                "item": dict(prior),
                "attemptHistories": histories[str(prior["id"])],
                "historicalQuestionFingerprintsByAttempt": (
                    historical_snapshots[str(prior["id"])]
                ),
            }
            for prior in prior_rows
        ]
        return {
            "release": dict(release),
            "build": dict(build),
            "items": [dict(value) for value in rows],
            "item": dict(row),
            "dispatches": dispatches,
            "persistedDispatch": target[0] if len(target) == 1 else None,
            "historicalQuestionFingerprints": self._historical_question_fingerprints(
                conn,
                item=row,
                attempt_started_at=attempt_started_at,
            ),
            "priorEvidence": prior_evidence,
            "attemptOneEvidence": (
                {
                    "item": dict(row),
                    "attemptHistories": item_histories,
                    "historicalQuestionFingerprintsByAttempt": (
                        historical_snapshots[str(row["id"])]
                    ),
                }
                if int(logical_attempt) == 2
                else None
            ),
            "requestedIdentity": {
                "generationRequestId": generation_request_id,
                "leaseToken": lease_token,
                "attemptStartedAt": attempt_started_at,
                "outerDeadlineAt": outer_deadline_at,
                "workDeadlineAt": work_deadline_at,
                "now": now,
            },
        }

    def _complete_content_provider_phase_locked(
        self,
        conn: DatabaseConnection,
        *,
        locked_item: Mapping[str, object],
        locked_build: Mapping[str, object],
        locked_items: Sequence[Mapping[str, object]],
        persisted_dispatch_id: str,
        expected_next_phase: str | None,
        expected_next_phase_ordinal: int | None,
        candidate_course: Mapping[str, object] | None,
        generator_profile: Mapping[str, object],
        now: int,
    ) -> DatabaseRow | None:
        locked_item_ids = {
            str(value.get("id") or "")
            for value in locked_items
            if isinstance(value, Mapping)
        }
        if (
            not isinstance(locked_build, Mapping)
            or not isinstance(locked_items, Sequence)
            or len(locked_items) != formal_target_course_count(locked_build)
            or len(locked_item_ids) != formal_target_course_count(locked_build)
            or str(locked_build.get("id") or "")
            != str(locked_item.get("build_job_id") or "")
            or str(locked_item.get("id") or "") not in locked_item_ids
        ):
            raise ValueError("locked content finalize authority is incomplete")
        item_id = str(locked_item["id"])
        build_id = str(locked_item["build_job_id"])
        logical_attempt = int(locked_item["attempt_count"])
        generation_request_id = str(
            locked_item["active_generation_request_id"]
        )
        phase = str(locked_item["content_phase"])
        phase_ordinal = int(
            next(
                authority["phaseOrdinal"]
                for authority in QUESTION_PHASE_IO
                if authority["phase"] == phase
            )
        )
        lease_token = str(locked_item["content_lease_token"])
        attempt_started_at = int(locked_item["content_attempt_started_at"])
        outer_deadline_at = int(
            locked_item["content_provider_attempt_hard_deadline_at"]
        )
        work_deadline_at = int(locked_item["content_work_unit_deadline_at"])
        if expected_next_phase is None:
            if expected_next_phase_ordinal is not None:
                return None
        else:
            expected_ordinal = next(
                (
                    int(authority["phaseOrdinal"])
                    for authority in QUESTION_PHASE_IO
                    if authority["phase"] == expected_next_phase
                ),
                None,
            )
            if expected_ordinal != expected_next_phase_ordinal:
                return None
        if expected_next_phase is not None:
            next_deadline = self._formal_content_work_deadline(
                now=now,
                outer_deadline=outer_deadline_at,
            )
            if next_deadline <= int(now):
                self._fence_content_build_locked(
                    conn,
                    build=locked_build,
                    rows=locked_items,
                    error_code="preparation_content_stage_deadline_exceeded",
                    now=now,
                )
                return None
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET content_phase = ?, content_lease_token = NULL,
                  content_lease_expires_at = NULL, content_heartbeat_at = NULL,
                  content_work_unit_deadline_at = ?, updated_at = ?
                WHERE id = ? AND build_job_id = ?
                  AND status = 'processing' AND attempt_count = ?
                  AND active_generation_request_id = ? AND content_phase = ?
                  AND content_lease_token = ? AND content_attempt_started_at = ?
                  AND content_provider_attempt_hard_deadline_at = ?
                  AND content_work_unit_deadline_at = ?
                  AND EXISTS (
                    SELECT 1 FROM learning_course_provider_dispatches d
                    WHERE d.id = ? AND d.build_item_id = ?
                      AND d.logical_attempt = ?
                      AND d.generation_request_id = ?
                      AND d.phase = ? AND d.phase_ordinal = ?
                      AND d.status = 'succeeded'
                  )
                """,
                (
                    expected_next_phase,
                    next_deadline,
                    now,
                    item_id,
                    build_id,
                    logical_attempt,
                    generation_request_id,
                    phase,
                    lease_token,
                    attempt_started_at,
                    outer_deadline_at,
                    work_deadline_at,
                    persisted_dispatch_id,
                    item_id,
                    logical_attempt,
                    generation_request_id,
                    phase,
                    phase_ordinal,
                ),
            )
            return self.get_item(conn, item_id=item_id) if cursor.rowcount == 1 else None
        if candidate_course is None:
            return None
        course = self._normalize_content_candidate(candidate_course)
        job, candidate = self._create_or_replay_content_candidate(
            conn,
            row=locked_item,
            course=course,
            generator_profile=generator_profile,
            now=now,
        )
        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET course_id = ?, course_version = ?,
              content_phase = 'host_gate_pending', content_gate_status = 'pending',
              content_gate_attempt_count = 0, content_lease_token = NULL,
              content_lease_expires_at = NULL, content_heartbeat_at = NULL,
              content_provider_attempt_hard_deadline_at = NULL,
              content_work_unit_deadline_at = NULL, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'processing'
              AND attempt_count = ? AND active_generation_request_id = ?
              AND content_phase = ? AND content_lease_token = ?
              AND content_attempt_started_at = ?
              AND content_provider_attempt_hard_deadline_at = ?
              AND content_work_unit_deadline_at = ?
              AND EXISTS (
                SELECT 1 FROM learning_course_provider_dispatches d
                WHERE d.id = ? AND d.build_item_id = ?
                  AND d.logical_attempt = ?
                  AND d.generation_request_id = ?
                  AND d.phase = ? AND d.phase_ordinal = ?
                  AND d.status = 'succeeded'
              )
            """,
            (
                candidate["course_id"],
                candidate["course_version"],
                now,
                item_id,
                build_id,
                logical_attempt,
                generation_request_id,
                phase,
                lease_token,
                attempt_started_at,
                outer_deadline_at,
                work_deadline_at,
                persisted_dispatch_id,
                item_id,
                logical_attempt,
                generation_request_id,
                phase,
                phase_ordinal,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return {
            **dict(self.get_item(conn, item_id=item_id)),
            "generation_job_id": job["id"],
            "candidate_id": candidate["id"],
        }

    def complete_content_host_gate(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        logical_attempt: int,
        generation_request_id: str,
        course: Mapping[str, object] | None,
        receipt: Mapping[str, object],
        receipt_hash: str,
        outcome: str,
        lease_token: str,
        gate_ordinal: int,
        now: int,
    ) -> DatabaseRow | None:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        row = next((value for value in rows if str(value["id"]) == item_id), None)
        if release is None or build is None or row is None:
            return None
        if str(build.get("status") or "") not in {"queued", "running"}:
            return None
        if not self._content_authority_is_exact(
            conn, release=release, build=build, rows=rows
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return None
        if (
            str(row.get("status") or "") != "processing"
            or str(row.get("content_phase") or "") != "host_gate_running"
            or int(row.get("attempt_count") or 0) != int(logical_attempt)
            or str(row.get("active_generation_request_id") or "")
            != generation_request_id
            or int(row.get("content_gate_attempt_count") or 0) != int(gate_ordinal)
            or str(row.get("content_lease_token") or "") != lease_token
            or int(row.get("content_lease_expires_at") or 0)
            != int(row.get("content_work_unit_deadline_at") or 0)
            or int(row.get("content_work_unit_deadline_at") or 0) < int(now)
        ):
            return None
        dispatches = self.list_content_dispatches(
            conn,
            item_id=item_id,
            logical_attempt=logical_attempt,
        )
        final_candidate_key = None
        if dispatches:
            try:
                final_candidate_key = question_phase_execution_authority(
                    str(dispatches[-1].get("phase") or ""),
                    int(dispatches[-1].get("phase_ordinal") or 0),
                )["finalCandidateKey"]
            except ValueError:
                final_candidate_key = None
        if (
            not dispatches
            or any(str(dispatch.get("status") or "") != "succeeded" for dispatch in dispatches)
            or final_candidate_key is None
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return None
        evidence_json = self._content_gate_envelope(
            receipt=receipt, receipt_hash=receipt_hash
        )
        job, candidate = self._lock_content_candidate_for_item(conn, row=row)
        if job is None or candidate is None:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
            )
            return None
        existing_validation = candidate.get("validation_json")
        if existing_validation is not None and str(existing_validation) != evidence_json:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
            )
            return None
        if outcome == "passed":
            if course is None or str(receipt.get("outcome") or "") != "passed":
                return None
            normalized = self._normalize_content_candidate(course)
            content_json = self.encode_json(normalized["content"])
            fingerprint = str(receipt.get("hostContentFingerprint") or "")
            if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                return None
            conn.execute(
                """
                INSERT INTO learning_courses(
                  id, version, grade_code, subject, node_code,
                  curriculum_version, boundary_version, title, objective,
                  status, quality_status, content_origin, generator,
                  generation_request_id, generation_content_hash,
                  content_json, published_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'validated',
                  'auto_validated', 'openmaic_generated', ?, ?, ?, ?,
                  NULL, ?, ?)
                ON DUPLICATE KEY UPDATE id = id
                """,
                (
                    normalized["id"],
                    normalized["version"],
                    normalized["gradeCode"],
                    normalized["subject"],
                    normalized["nodeCode"],
                    row["curriculum_version"],
                    row["boundary_version"],
                    normalized["title"],
                    normalized["objective"],
                    job["generator"],
                    generation_request_id,
                    fingerprint,
                    content_json,
                    now,
                    now,
                ),
            )
            persisted = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE id = ? AND version = ? LIMIT 1 FOR UPDATE
                """,
                (normalized["id"], normalized["version"]),
            ).fetchone()
            if (
                persisted is not None
                and str(persisted.get("grade_code") or "")
                == normalized["gradeCode"]
                and str(persisted.get("subject") or "")
                == normalized["subject"]
                and str(persisted.get("node_code") or "")
                == normalized["nodeCode"]
                and str(persisted.get("curriculum_version") or "")
                == str(row["curriculum_version"])
                and str(persisted.get("boundary_version") or "")
                == str(row["boundary_version"])
                and str(persisted.get("title") or "") == normalized["title"]
                and str(persisted.get("objective") or "")
                == normalized["objective"]
                and str(persisted.get("content_json") or "")
                == str(candidate.get("content_json") or "")
                and str(persisted.get("generation_content_hash") or "")
                == str(candidate.get("content_hash") or "")
                and str(persisted.get("generation_request_id") or "")
                == generation_request_id
                and str(persisted.get("generator") or "")
                == str(job["generator"])
                and str(persisted.get("content_origin") or "")
                == "openmaic_generated"
                and str(persisted.get("status") or "") == "unverified"
                and str(persisted.get("quality_status") or "")
                == "legacy_unreviewed"
                and persisted.get("published_at") is None
                and persisted.get("retired_at") is None
                and str(job.get("status") or "")
                in {"queued", "generating"}
                and str(candidate.get("status") or "") == "generated"
                and candidate.get("validation_json") is None
            ):
                promoted = conn.execute(
                    """
                    UPDATE learning_courses
                    SET status = 'validated', quality_status = 'auto_validated',
                      generation_content_hash = ?, content_json = ?, updated_at = ?
                    WHERE id = ? AND version = ? AND status = 'unverified'
                      AND quality_status = 'legacy_unreviewed'
                      AND generation_request_id = ?
                      AND generation_content_hash = ?
                      AND content_json = ?
                      AND published_at IS NULL AND retired_at IS NULL
                    """,
                    (
                        fingerprint,
                        content_json,
                        now,
                        normalized["id"],
                        normalized["version"],
                        generation_request_id,
                        candidate["content_hash"],
                        candidate["content_json"],
                    ),
                )
                if promoted.rowcount != 1:
                    self._fence_content_build_locked(
                        conn,
                        build=build,
                        rows=rows,
                        error_code="preparation_content_contract_drift",
                        now=now,
                        item_id=item_id,
                    )
                    return None
                persisted = conn.execute(
                    """
                    SELECT * FROM learning_courses
                    WHERE id = ? AND version = ? LIMIT 1 FOR UPDATE
                    """,
                    (normalized["id"], normalized["version"]),
                ).fetchone()
            if (
                persisted is None
                or str(persisted.get("grade_code") or "") != normalized["gradeCode"]
                or str(persisted.get("subject") or "") != normalized["subject"]
                or str(persisted.get("node_code") or "") != normalized["nodeCode"]
                or str(persisted.get("curriculum_version") or "")
                != str(row["curriculum_version"])
                or str(persisted.get("boundary_version") or "")
                != str(row["boundary_version"])
                or str(persisted.get("title") or "") != normalized["title"]
                or str(persisted.get("objective") or "") != normalized["objective"]
                or str(persisted.get("content_json") or "") != content_json
                or str(persisted.get("generation_content_hash") or "") != fingerprint
                or str(persisted.get("generation_request_id") or "")
                != generation_request_id
                or str(persisted.get("generator") or "") != str(job["generator"])
                or str(persisted.get("content_origin") or "")
                != "openmaic_generated"
                or str(persisted.get("status") or "") != "validated"
                or str(persisted.get("quality_status") or "")
                != "auto_validated"
                or persisted.get("published_at") is not None
                or persisted.get("retired_at") is not None
            ):
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_contract_drift",
                    now=now,
                )
                return None
            conn.execute(
                """
                UPDATE learning_course_generation_candidates
                SET status = 'course_validated', validation_json = ?,
                  error_code = NULL, error_message_safe = NULL,
                  published_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'generated'
                  AND validation_json IS NULL
                """,
                (evidence_json, now, candidate["id"]),
            )
            conn.execute(
                """
                UPDATE learning_course_generation_jobs
                SET status = 'validated', completed_at = COALESCE(completed_at, ?),
                  error_code = NULL, error_message_safe = NULL, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'generating')
                """,
                (now, now, job["id"]),
            )
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET status = 'course_ready', content_phase = 'course_ready',
                  content_gate_status = 'passed', content_gate_passed_at = ?,
                  content_validation_contract_version = ?,
                  content_receipt_hash = ?, content_lease_token = NULL,
                  content_lease_expires_at = NULL, content_heartbeat_at = NULL,
                  content_work_unit_deadline_at = NULL, updated_at = ?
                WHERE id = ? AND status = 'processing'
                  AND content_phase = 'host_gate_running'
                  AND attempt_count = ? AND active_generation_request_id = ?
                  AND content_gate_attempt_count = ? AND content_lease_token = ?
                """,
                (
                    now,
                    receipt["contentValidationContractVersion"],
                    receipt_hash,
                    now,
                    item_id,
                    logical_attempt,
                    generation_request_id,
                    gate_ordinal,
                    lease_token,
                ),
            )
            return self.get_item(conn, item_id=item_id) if cursor.rowcount == 1 else None

        if outcome != "rejected" or str(receipt.get("outcome") or "") != "rejected":
            return None
        # A deterministic rejection has no accepted course authority, but the
        # exact candidate course remains a write-once, unverified replay
        # artifact.  Attempt 2 is authorized only after re-locking this row
        # together with the dispatch/job/candidate proof.
        conn.execute(
            """
            INSERT INTO learning_courses(
              id, version, grade_code, subject, node_code,
              curriculum_version, boundary_version, title, objective,
              status, quality_status, content_origin, generator,
              generation_request_id, generation_content_hash,
              content_json, published_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'unverified',
              'legacy_unreviewed', 'openmaic_generated', ?, ?, ?, ?,
              NULL, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                candidate["course_id"],
                candidate["course_version"],
                candidate["grade_code"],
                candidate["subject"],
                candidate["node_code"],
                candidate["curriculum_version"],
                candidate["boundary_version"],
                candidate["title"],
                candidate["objective"],
                job["generator"],
                generation_request_id,
                candidate["content_hash"],
                candidate["content_json"],
                now,
                now,
            ),
        )
        rejected_course = conn.execute(
            """
            SELECT * FROM learning_courses
            WHERE id = ? AND version = ? LIMIT 1 FOR UPDATE
            """,
            (candidate["course_id"], candidate["course_version"]),
        ).fetchone()
        if (
            rejected_course is None
            or str(rejected_course.get("grade_code") or "")
            != str(candidate["grade_code"])
            or str(rejected_course.get("subject") or "")
            != str(candidate["subject"])
            or str(rejected_course.get("node_code") or "")
            != str(candidate["node_code"])
            or str(rejected_course.get("curriculum_version") or "")
            != str(candidate["curriculum_version"])
            or str(rejected_course.get("boundary_version") or "")
            != str(candidate["boundary_version"])
            or str(rejected_course.get("title") or "")
            != str(candidate["title"])
            or str(rejected_course.get("objective") or "")
            != str(candidate["objective"])
            or str(rejected_course.get("status") or "") != "unverified"
            or str(rejected_course.get("quality_status") or "")
            != "legacy_unreviewed"
            or str(rejected_course.get("content_origin") or "")
            != "openmaic_generated"
            or str(rejected_course.get("generator") or "")
            != str(job["generator"])
            or str(rejected_course.get("generation_request_id") or "")
            != generation_request_id
            or str(rejected_course.get("generation_content_hash") or "")
            != str(candidate["content_hash"])
            or str(rejected_course.get("content_json") or "")
            != str(candidate["content_json"])
            or rejected_course.get("published_at") is not None
            or rejected_course.get("retired_at") is not None
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return None
        safe_code = (
            "preparation_content_canary_failed"
            if int(logical_attempt) == 2 and self._is_content_canary(build, row)
            else "preparation_content_validation_failed"
        )
        conn.execute(
            """
            UPDATE learning_course_generation_candidates
            SET status = 'rejected', validation_json = ?, error_code = ?,
              error_message_safe = '内容未通过本地确定性门禁。', updated_at = ?
            WHERE id = ? AND status = 'generated' AND validation_json IS NULL
            """,
            (evidence_json, safe_code, now, candidate["id"]),
        )
        conn.execute(
            """
            UPDATE learning_course_generation_jobs
            SET status = 'failed', error_code = ?,
              error_message_safe = '内容未通过本地确定性门禁。',
              completed_at = ?, updated_at = ?
            WHERE id = ? AND status IN ('queued', 'generating')
            """,
            (safe_code, now, now, job["id"]),
        )
        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'failed', content_phase = 'failed',
              content_gate_status = 'failed_deterministic',
              error_code = ?, error_message_safe = '内容未通过本地确定性门禁。',
              completed_at = ?, content_lease_token = NULL,
              content_lease_expires_at = NULL, content_heartbeat_at = NULL,
              content_work_unit_deadline_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'processing'
              AND content_phase = 'host_gate_running'
              AND attempt_count = ? AND active_generation_request_id = ?
              AND content_gate_attempt_count = ? AND content_lease_token = ?
            """,
            (
                safe_code,
                now,
                now,
                item_id,
                logical_attempt,
                generation_request_id,
                gate_ordinal,
                lease_token,
            ),
        )
        if cursor.rowcount != 1:
            return None
        if int(logical_attempt) == 2:
            self._fence_content_build_locked(
                conn, build=build, rows=rows, error_code=safe_code, now=now
            )
        return self.get_item(conn, item_id=item_id)

    def load_content_host_finalize_authority(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        logical_attempt: int,
        generation_request_id: str,
        gate_ordinal: int,
        lease_token: str,
        work_deadline_at: int,
        now: int,
    ) -> Mapping[str, object]:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        row = next((value for value in rows if str(value["id"]) == item_id), None)
        if release is None or build is None or row is None:
            raise LearningCatalogBuildConflict("Host finalize authority is missing")
        if (
            str(build.get("status") or "") not in {"queued", "running"}
            or not self._content_authority_is_exact(
                conn, release=release, build=build, rows=rows
            )
            or str(row.get("status") or "") != "processing"
            or str(row.get("content_phase") or "") != "host_gate_running"
            or int(row.get("attempt_count") or 0) != int(logical_attempt)
            or str(row.get("active_generation_request_id") or "")
            != generation_request_id
            or int(row.get("content_gate_attempt_count") or 0)
            != int(gate_ordinal)
            or str(row.get("content_lease_token") or "") != lease_token
            or int(row.get("content_lease_expires_at") or 0)
            != int(work_deadline_at)
            or int(row.get("content_work_unit_deadline_at") or 0)
            != int(work_deadline_at)
            or int(work_deadline_at) < int(now)
        ):
            raise LearningCatalogBuildConflict("Host finalize authority drift")
        priors = [
            value
            for value in rows
            if str(value.get("subject") or "") == str(row.get("subject") or "")
            and str(value.get("skill_id") or "") == str(row.get("skill_id") or "")
            and str(value.get("boundary_version") or "")
            == str(row.get("boundary_version") or "")
            and int(value.get("variant_ordinal") or 0)
            in range(1, int(row.get("variant_ordinal") or 0))
        ]
        priors.sort(key=lambda value: int(value["variant_ordinal"]))
        if [int(value["variant_ordinal"]) for value in priors] != list(
            range(1, int(row.get("variant_ordinal") or 0))
        ):
            raise LearningCatalogBuildConflict("Host prior authority drift")
        evidence_rows = [*priors, row]
        histories = self._load_content_attempt_histories_locked(
            conn, rows=evidence_rows
        )
        historical_snapshots = {
            str(value["id"]): self._historical_question_fingerprint_snapshots(
                conn,
                item=value,
                histories=histories[str(value["id"])],
            )
            for value in evidence_rows
        }
        current = self._content_attempt_evidence_from_histories(
            item=row,
            histories=histories[str(row["id"])],
            attempt=int(row["attempt_count"]),
            require_course=False,
        )
        return {
            **current,
            "historicalQuestionFingerprints": self._historical_question_fingerprints(
                conn,
                item=row,
            ),
            "priorEvidence": [
                {
                    "item": dict(value),
                    "attemptHistories": histories[str(value["id"])],
                    "historicalQuestionFingerprintsByAttempt": (
                        historical_snapshots[str(value["id"])]
                    ),
                }
                for value in priors
            ],
            "attemptOneEvidence": (
                {
                    "item": dict(row),
                    "attemptHistories": histories[str(row["id"])],
                    "historicalQuestionFingerprintsByAttempt": (
                        historical_snapshots[str(row["id"])]
                    ),
                }
                if int(row["attempt_count"]) == 2
                else None
            ),
        }

    def release_content_provider_dependency(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        lease_token: str,
        now: int,
    ) -> bool:
        phases = tuple(str(authority["phase"]) for authority in QUESTION_PHASE_IO)
        placeholders = ", ".join("?" for _ in phases)
        cursor = conn.execute(
            f"""
            UPDATE learning_catalog_build_items
            SET content_lease_token = NULL, content_lease_expires_at = NULL,
              content_heartbeat_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'processing'
              AND content_phase IN ({placeholders})
              AND content_lease_token = ?
              AND NOT EXISTS (
                SELECT 1 FROM learning_course_provider_dispatches AS dispatch
                WHERE dispatch.build_item_id = learning_catalog_build_items.id
                  AND dispatch.logical_attempt = learning_catalog_build_items.attempt_count
                  AND dispatch.phase = learning_catalog_build_items.content_phase
              )
            """,
            (now, item_id, *phases, lease_token),
        )
        return cursor.rowcount == 1

    def reconcile_content_provider_stale(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        logical_attempt: int,
        generation_request_id: str,
        phase: str,
        phase_ordinal: int,
        lease_token: str,
        now: int,
    ) -> Mapping[str, object]:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        row = next((value for value in rows if str(value["id"]) == item_id), None)
        if release is None or build is None or row is None:
            return {"action": "stale", "items": rows}
        if str(build.get("status") or "") == "failed":
            return {"action": "failed", "item": row, "items": rows}
        if str(build.get("status") or "") not in {"queued", "running"}:
            return {"action": "stale", "item": row, "items": rows}
        if not self._content_authority_is_exact(
            conn, release=release, build=build, rows=rows
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return {"action": "failed", "item": row, "items": rows}
        if (
            str(row.get("status") or "") != "processing"
            or int(row.get("attempt_count") or 0) != int(logical_attempt)
            or str(row.get("active_generation_request_id") or "")
            != generation_request_id
            or str(row.get("content_phase") or "") != phase
            or str(row.get("content_lease_token") or "") != lease_token
        ):
            return {"action": "stale", "item": row, "items": rows}
        dispatches = self.list_content_dispatches(
            conn,
            item_id=item_id,
            logical_attempt=logical_attempt,
        )
        target = [
            dispatch
            for dispatch in dispatches
            if str(dispatch.get("phase") or "") == phase
            and int(dispatch.get("phase_ordinal") or 0) == int(phase_ordinal)
        ]
        if not target:
            return {
                "action": "stale",
                "item": row,
                "items": rows,
                "dispatches": dispatches,
            }
        if len(target) != 1:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return {"action": "failed", "item": row, "items": rows}
        dispatch = target[0]
        if (
            str(dispatch.get("build_item_id") or "") != item_id
            or int(dispatch.get("logical_attempt") or 0) != int(logical_attempt)
            or str(dispatch.get("generation_request_id") or "")
            != generation_request_id
            or str(dispatch.get("item_lease_token") or "") != lease_token
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return {"action": "failed", "item": row, "items": rows}
        status = str(dispatch.get("status") or "")
        if status == "succeeded":
            return {
                "action": "succeeded",
                "item": row,
                "items": rows,
                "dispatches": dispatches,
                "dispatch": dispatch,
            }
        if status == "dispatched" and (
            int(row.get("content_lease_expires_at") or 0) >= int(now)
            and int(row.get("content_work_unit_deadline_at") or 0) >= int(now)
        ):
            return {
                "action": "busy",
                "item": row,
                "items": rows,
                "dispatches": dispatches,
            }
        error_code = {
            "dispatched": "preparation_provider_dispatch_outcome_unknown",
            "ambiguous": "preparation_provider_dispatch_outcome_unknown",
            "failed_safe": "preparation_content_provider_unavailable",
        }.get(status, "preparation_content_contract_drift")
        self._fence_content_build_locked(
            conn,
            build=build,
            rows=rows,
            error_code=error_code,
            now=now,
            item_id=item_id,
        )
        return {"action": "failed", "item": row, "items": rows}

    def fence_content_failure(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str | None,
        error_code: str,
        now: int,
    ) -> None:
        _, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        if build is None:
            return
        self._fence_content_build_locked(
            conn,
            build=build,
            rows=rows,
            error_code=error_code,
            now=now,
            item_id=item_id,
        )

    def is_content_build_failed(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
    ) -> bool:
        _, build = self.lock_build_authority(conn, build_id=build_id)
        if build is None:
            return False
        self.list_build_items(conn, build_id=build_id, for_update=True)
        return str(build.get("status") or "") == "failed"

    def _content_authority_is_exact(
        self,
        conn: DatabaseConnection,
        *,
        release: Mapping[str, Any],
        build: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        allow_terminal: bool = False,
    ) -> bool:
        try:
            current_target = canonical_preparation_target_for(build)
        except (ValueError, TypeError, KeyError):
            return False
        target = self.decode_json(build.get("target_spec_json"))
        if not compatible_preparation_target(target, current_target):
            return False
        target_json = self.encode_json(target)
        course_targets = target["courseTargets"]
        request_id = str(build.get("request_id") or "")
        request_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
        expected_build_id = f"catalog_build_{request_digest}"
        expected_release_id = f"catalog_release_{request_digest}"
        if (
            not request_id
            or str(build.get("id") or "") != expected_build_id
            or str(build.get("release_id") or "") != expected_release_id
            or str(release.get("id") or "") != expected_release_id
            or str(build.get("execution_mode") or "") != "content_only"
            or str(build.get("stage_ceiling") or "") != "content_ready"
            or str(build.get("status") or "")
            not in (
                {"queued", "running", "failed"}
                if allow_terminal
                else {"queued", "running"}
            )
            or str(build.get("curriculum_version") or "")
            != str(target["curriculumVersion"])
            or str(build.get("target_spec_json") or "") != target_json
            or str(build.get("content_manifest_version") or "")
            != str(target["schemaVersion"])
            or str(build.get("canary_manifest_json") or "")
            != self.encode_json(target["canaryManifest"])
            or int(build.get("total_item_count") or 0) != formal_target_course_count(build)
            or int(build.get("ready_item_count") or 0) != 0
            or int(build.get("failed_item_count") or 0) != 0
            or (
                not allow_terminal
                and (
                    build.get("error_code") is not None
                    or build.get("error_message_safe") is not None
                    or build.get("completed_at") is not None
                )
            )
            or (
                allow_terminal
                and str(build.get("status") or "") == "failed"
                and (
                    not str(build.get("error_code") or "")
                    or int(build.get("completed_at") or 0) <= 0
                )
            )
            or str(release.get("status") or "") != "draft"
            or str(release.get("quality_status") or "") != "building"
            or str(release.get("curriculum_version") or "")
            != str(target["curriculumVersion"])
            or int(release.get("required_boundary_count") or 0) != int(current_target["boundaryCount"])
            or release.get("activated_at") is not None
            or release.get("retired_at") is not None
        ):
            return False
        expected = self._expected_content_item_immutables(
            build_id=str(build["id"]),
            release_id=str(release["id"]),
            curriculum_version=str(target["curriculumVersion"]),
            content_manifest_version=str(target["schemaVersion"]),
            course_targets=course_targets,
            grade_code=preparation_authority_grade(build),
        )
        if len(rows) != formal_target_course_count(build) or any(
            not self._content_item_immutables_match(row, immutable)
            for row, immutable in zip(rows, expected)
        ):
            return False
        if not self._progressive_release_items_are_exact(
            conn,
            release=release,
            build=build,
            rows=rows,
            target_fingerprint=preparation_target_fingerprint(target),
        ):
            return False
        return all(
            int(row.get("package_attempt_count") or 0) == 0
            and row.get("active_package_request_id") is None
            and row.get("package_id") is None
            and row.get("package_version") is None
            for row in rows
        )

    @staticmethod
    def _content_provider_phases() -> frozenset[str]:
        return frozenset(str(authority["phase"]) for authority in QUESTION_PHASE_IO)

    @classmethod
    def _formal_content_work_deadline(
        cls,
        *,
        now: int,
        outer_deadline: int,
    ) -> int:
        return min(
            int(now) + cls.FORMAL_CONTENT_WORK_UNIT_MS,
            int(outer_deadline),
        )

    def _claim_content_attempt(
        self,
        conn: DatabaseConnection,
        *,
        build: Mapping[str, Any],
        row: Mapping[str, Any],
        attempt: int,
        now: int,
    ) -> DatabaseRow | None:
        request_id = str(row["generation_request_id"])
        if int(attempt) == 2:
            request_id += ".attempt2"
        attempt_start = int(now)
        outer = attempt_start + self.FORMAL_PROVIDER_ATTEMPT_HARD_DEADLINE_MS
        work = self._formal_content_work_deadline(
            now=attempt_start,
            outer_deadline=outer,
        )
        lease = f"catalog_content_lease_{uuid.uuid4().hex}"
        if int(attempt) == 1:
            where = "status = 'pending' AND attempt_count = 0 AND content_phase = 'not_started'"
        else:
            where = (
                "status = 'failed' AND attempt_count = 1 "
                "AND content_phase = 'failed' "
                "AND (content_gate_status = 'failed_deterministic' OR ("
                "content_gate_status = 'not_started' AND course_id IS NULL "
                "AND course_version IS NULL))"
            )
        cursor = conn.execute(
            f"""
            UPDATE learning_catalog_build_items
            SET status = 'processing', attempt_count = ?,
              claim_origin_status = ?, active_generation_request_id = ?,
              content_phase = 'outline', content_gate_status = 'not_started',
              content_gate_attempt_count = 0, content_gate_passed_at = NULL,
              content_validation_contract_version = NULL,
              content_receipt_hash = NULL, content_lease_token = ?,
              content_lease_expires_at = ?, content_heartbeat_at = ?,
              content_attempt_started_at = ?,
              content_provider_attempt_hard_deadline_at = ?,
              content_work_unit_deadline_at = ?,
              content_claim_attempt_ordinal = ?, error_code = NULL,
              error_message_safe = NULL, completed_at = NULL,
              started_at = COALESCE(started_at, ?), updated_at = ?
            WHERE id = ? AND build_job_id = ?
              AND execution_mode_snapshot = 'content_only' AND {where}
            """,
            (
                attempt,
                "pending" if attempt == 1 else "failed",
                request_id,
                lease,
                work,
                now,
                attempt_start,
                outer,
                work,
                attempt,
                now,
                now,
                row["id"],
                build["id"],
            ),
        )
        if cursor.rowcount != 1:
            return None
        self._mark_build_running(conn, build_id=str(build["id"]), now=now)
        return self.get_item(conn, item_id=str(row["id"]))

    def _claim_existing_provider_phase(
        self,
        conn: DatabaseConnection,
        *,
        build: Mapping[str, Any],
        row: Mapping[str, Any],
        now: int,
        locked_dispatches: Sequence[Mapping[str, object]],
    ) -> DatabaseRow | None:
        outer = int(row.get("content_provider_attempt_hard_deadline_at") or 0)
        work = int(row.get("content_work_unit_deadline_at") or 0)
        target_dispatches = [
            dispatch
            for dispatch in locked_dispatches
            if str(dispatch.get("phase") or "")
            == str(row.get("content_phase") or "")
            and int(dispatch.get("logical_attempt") or 0)
            == int(row.get("attempt_count") or 0)
        ]
        if len(target_dispatches) > 1:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=[row],
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=str(row["id"]),
            )
            return None
        dispatch = target_dispatches[0] if target_dispatches else None
        if outer < int(now) or work < int(now):
            error_code = (
                "preparation_provider_dispatch_outcome_unknown"
                if dispatch is not None
                and str(dispatch.get("status") or "") == "dispatched"
                else "preparation_content_stage_deadline_exceeded"
            )
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=[row],
                error_code=error_code,
                now=now,
                item_id=str(row["id"]),
            )
            return None
        if row.get("content_lease_token") is not None:
            if int(row.get("content_lease_expires_at") or 0) != work:
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=[row],
                    error_code="preparation_content_contract_drift",
                    now=now,
                    item_id=str(row["id"]),
                )
                return None
            if dispatch is None:
                return row
            if str(dispatch.get("item_lease_token") or "") != str(
                row.get("content_lease_token") or ""
            ):
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=[row],
                    error_code="preparation_content_contract_drift",
                    now=now,
                    item_id=str(row["id"]),
                )
                return None
            if str(dispatch.get("status") or "") == "dispatched":
                return None
            return row
        lease = f"catalog_content_lease_{uuid.uuid4().hex}"
        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET content_lease_token = ?, content_lease_expires_at = ?,
              content_heartbeat_at = ?, updated_at = ?
            WHERE id = ? AND build_job_id = ? AND status = 'processing'
              AND content_phase = ? AND attempt_count = ?
              AND active_generation_request_id = ?
              AND content_lease_token IS NULL
              AND content_work_unit_deadline_at = ?
              AND content_provider_attempt_hard_deadline_at = ?
            """,
            (
                lease,
                work,
                now,
                now,
                row["id"],
                build["id"],
                row["content_phase"],
                row["attempt_count"],
                row["active_generation_request_id"],
                work,
                outer,
            ),
        )
        if cursor.rowcount != 1:
            return None
        return conn.execute(
            """
            SELECT * FROM learning_catalog_build_items
            WHERE id = ? LIMIT 1 FOR UPDATE
            """,
            (row["id"],),
        ).fetchone()

    def _prepare_host_action(
        self,
        conn: DatabaseConnection,
        *,
        build: Mapping[str, Any],
        row: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        now: int,
        passed_item_ids: frozenset[str],
        locked_attempt_histories_by_item: Mapping[
            str, Mapping[int, Mapping[str, object]]
        ],
    ) -> Mapping[str, object]:
        phase = str(row.get("content_phase") or "")
        gate_count = int(row.get("content_gate_attempt_count") or 0)
        deadline = int(row.get("content_work_unit_deadline_at") or 0)
        claimed = None
        if phase == "host_gate_running":
            if (
                row.get("content_lease_token") is not None
                and int(row.get("content_lease_expires_at") or 0) != deadline
            ):
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_contract_drift",
                    now=now,
                    item_id=str(row["id"]),
                )
                return {"action": "failed", "build": build, "items": rows}
            if deadline >= int(now) and row.get("content_lease_token") is not None:
                if str(row.get("content_gate_status") or "") == "retry_wait":
                    claimed = row
                else:
                    return {"action": "busy", "build": build, "items": rows}
            if deadline < int(now):
                conn.execute(
                    """
                    UPDATE learning_catalog_build_items
                    SET content_phase = 'host_gate_pending',
                      content_gate_status = 'retry_wait',
                      content_lease_token = NULL,
                      content_lease_expires_at = NULL,
                      content_heartbeat_at = NULL,
                      content_work_unit_deadline_at = NULL, updated_at = ?
                    WHERE id = ? AND content_phase = 'host_gate_running'
                      AND content_gate_attempt_count = ?
                      AND content_work_unit_deadline_at = ?
                    """,
                    (now, row["id"], gate_count, deadline),
                )
                row = self.get_item(conn, item_id=str(row["id"]))
                phase = "host_gate_pending"
        if claimed is None and phase != "host_gate_pending":
            return {"action": "busy", "build": build, "items": rows}
        if claimed is None:
            next_ordinal = gate_count + 1
            if next_ordinal > 3:
                self._fence_content_build_locked(
                    conn,
                    build=build,
                    rows=rows,
                    error_code="preparation_content_gate_attempts_exhausted",
                    now=now,
                    item_id=str(row["id"]),
                )
                return {"action": "failed", "build": build, "items": rows}
            work = int(now) + self.FORMAL_CONTENT_WORK_UNIT_MS
            lease = f"catalog_host_lease_{uuid.uuid4().hex}"
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET content_phase = 'host_gate_running',
                  content_gate_status = 'pending',
                  content_gate_attempt_count = ?, content_lease_token = ?,
                  content_lease_expires_at = ?, content_heartbeat_at = ?,
                  content_work_unit_deadline_at = ?, updated_at = ?
                WHERE id = ? AND status = 'processing'
                  AND content_phase = 'host_gate_pending'
                  AND content_gate_attempt_count = ?
                  AND content_lease_token IS NULL
                """,
                (
                    next_ordinal,
                    lease,
                    work,
                    now,
                    work,
                    now,
                    row["id"],
                    gate_count,
                ),
            )
            if cursor.rowcount != 1:
                return {"action": "busy", "build": build, "items": rows}
            claimed = self.get_item(conn, item_id=str(row["id"]))
        priors = [
            value
            for value in rows
            if str(value.get("subject") or "")
            == str(claimed.get("subject") or "")
            and str(value.get("skill_id") or "")
            == str(claimed.get("skill_id") or "")
            and str(value.get("boundary_version") or "")
            == str(claimed.get("boundary_version") or "")
            and int(value.get("variant_ordinal") or 0)
            < int(claimed.get("variant_ordinal") or 0)
            and str(value.get("id") or "") in passed_item_ids
        ]
        priors.sort(key=lambda value: int(value["variant_ordinal"]))
        authority_rows = [*priors, claimed]
        histories = {
            str(value["id"]): locked_attempt_histories_by_item.get(
                str(value["id"])
            )
            for value in authority_rows
        }
        if any(
            not isinstance(value, Mapping) for value in histories.values()
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=str(row["id"]),
            )
            return {"action": "failed", "build": build, "items": rows}
        try:
            historical_snapshots = {
                str(value["id"]): self._historical_question_fingerprint_snapshots(
                    conn,
                    item=value,
                    histories=histories[str(value["id"])],
                )
                for value in authority_rows
            }
            current = self._content_attempt_evidence_from_histories(
                item=claimed,
                histories=histories[str(claimed["id"])],
                attempt=int(claimed["attempt_count"]),
                require_course=False,
            )
        except LearningCatalogBuildConflict:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=str(row["id"]),
            )
            return {"action": "failed", "build": build, "items": rows}
        return {
            "action": "host",
            "build": build,
            "item": claimed,
            "items": rows,
            "job": current["job"],
            "candidate": current["candidate"],
            "course": current["course"],
            "dispatches": current["dispatches"],
            "historicalQuestionFingerprints": (
                self._historical_question_fingerprints(
                    conn,
                    item=claimed,
                )
            ),
            "priorEvidence": [
                {
                    "item": dict(value),
                    "attemptHistories": histories[str(value["id"])],
                    "historicalQuestionFingerprintsByAttempt": (
                        historical_snapshots[str(value["id"])]
                    ),
                }
                for value in priors
            ],
            "attemptOneEvidence": (
                {
                    "item": dict(claimed),
                    "attemptHistories": histories[str(claimed["id"])],
                    "historicalQuestionFingerprintsByAttempt": (
                        historical_snapshots[str(claimed["id"])]
                    ),
                }
                if int(claimed["attempt_count"]) == 2
                else None
            ),
        }

    def release_content_host_dependency(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        item_id: str,
        logical_attempt: int,
        generation_request_id: str,
        gate_ordinal: int,
        lease_token: str,
        work_deadline_at: int,
        now: int,
    ) -> str:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        rows = (
            self.list_build_items(conn, build_id=build_id, for_update=True)
            if build is not None
            else []
        )
        row = next((value for value in rows if str(value["id"]) == item_id), None)
        if release is None or build is None or row is None:
            return "stale"
        if str(build.get("status") or "") not in {"queued", "running"}:
            return "stale"
        if not self._content_authority_is_exact(
            conn, release=release, build=build, rows=rows
        ):
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_contract_drift",
                now=now,
                item_id=item_id,
            )
            return "failed"
        if (
            str(row.get("status") or "") != "processing"
            or str(row.get("content_phase") or "") != "host_gate_running"
            or int(row.get("attempt_count") or 0) != int(logical_attempt)
            or str(row.get("active_generation_request_id") or "")
            != generation_request_id
            or int(row.get("content_gate_attempt_count") or 0)
            != int(gate_ordinal)
            or str(row.get("content_lease_token") or "") != lease_token
            or int(row.get("content_lease_expires_at") or 0)
            != int(work_deadline_at)
            or int(row.get("content_work_unit_deadline_at") or 0)
            != int(work_deadline_at)
        ):
            return "stale"
        if int(now) > int(work_deadline_at) and int(gate_ordinal) >= 3:
            self._fence_content_build_locked(
                conn,
                build=build,
                rows=rows,
                error_code="preparation_content_gate_attempts_exhausted",
                now=now,
                item_id=item_id,
            )
            return "failed"
        keep_deadline = int(now) <= int(work_deadline_at)
        if (
            keep_deadline
            and str(row.get("content_gate_status") or "") == "retry_wait"
        ):
            return "dependency_retry"
        if keep_deadline:
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET content_gate_status = 'retry_wait', updated_at = ?
                WHERE id = ? AND build_job_id = ? AND status = 'processing'
                  AND content_phase = 'host_gate_running'
                  AND attempt_count = ? AND active_generation_request_id = ?
                  AND content_gate_attempt_count = ?
                  AND content_lease_token = ?
                  AND content_work_unit_deadline_at = ?
                """,
                (
                    now,
                    item_id,
                    build_id,
                    logical_attempt,
                    generation_request_id,
                    gate_ordinal,
                    lease_token,
                    work_deadline_at,
                ),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET content_phase = 'host_gate_pending',
                  content_gate_status = 'retry_wait',
                  content_lease_token = NULL, content_lease_expires_at = NULL,
                  content_heartbeat_at = NULL,
                  content_work_unit_deadline_at = NULL, updated_at = ?
                WHERE id = ? AND build_job_id = ? AND status = 'processing'
                  AND content_phase = 'host_gate_running'
                  AND attempt_count = ? AND active_generation_request_id = ?
                  AND content_gate_attempt_count = ?
                  AND content_lease_token = ?
                  AND content_work_unit_deadline_at = ?
                """,
                (
                    now,
                    item_id,
                    build_id,
                    logical_attempt,
                    generation_request_id,
                    gate_ordinal,
                    lease_token,
                    work_deadline_at,
                ),
            )
        return "dependency_retry" if cursor.rowcount == 1 else "stale"

    def _eligible_content_rows(
        self,
        *,
        conn: DatabaseConnection,
        build: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        canaries_passed: bool,
        passed_item_ids: frozenset[str],
    ) -> list[Mapping[str, Any]]:
        canary_keys = self._content_canary_keys(build)
        by_boundary: dict[tuple[str, str, str], dict[int, Mapping[str, Any]]] = {}
        for row in rows:
            key = (
                str(row["subject"]),
                str(row["skill_id"]),
                str(row["boundary_version"]),
            )
            by_boundary.setdefault(key, {})[int(row["variant_ordinal"])] = row
        eligible: list[Mapping[str, Any]] = []
        for row in rows:
            identity = (
                str(row["subject"]),
                str(row["skill_id"]),
                int(row["variant_ordinal"]),
            )
            if not canaries_passed and identity not in canary_keys:
                continue
            if (
                str(row.get("status") or "") != "pending"
                or int(row.get("attempt_count") or 0) != 0
                or str(row.get("content_phase") or "") != "not_started"
                or str(row.get("content_gate_status") or "") != "not_started"
            ):
                continue
            boundary = by_boundary[
                (
                    str(row["subject"]),
                    str(row["skill_id"]),
                    str(row["boundary_version"]),
                )
            ]
            ordinal = int(row["variant_ordinal"])
            if all(
                prior in boundary
                and str(boundary[prior].get("id") or "") in passed_item_ids
                for prior in range(1, ordinal)
            ):
                eligible.append(row)
        return filter_requested_supply(eligible, requested_supply(conn, build))

    @staticmethod
    def _select_fair_content_row(
        *,
        eligible: Sequence[Mapping[str, Any]],
        passed_by_subject: Mapping[int, int],
    ) -> Mapping[str, Any]:
        if not eligible:
            raise ValueError("no eligible content row")
        return min(
            eligible,
            key=lambda value: (
                int(value.get('_supply_priority', 0)),
                int(passed_by_subject.get(int(value["subject_ordinal"]), 0)),
                int(value["subject_ordinal"]),
                int(value["boundary_ordinal"]),
                int(value["variant_ordinal"]),
            ),
        )

    def _content_canary_keys(
        self, build: Mapping[str, Any]
    ) -> set[tuple[str, str, int]]:
        raw = self.decode_json(build.get("canary_manifest_json"))
        targets = raw.get("targets") if isinstance(raw, Mapping) else None
        if not isinstance(targets, list):
            return set()
        return {
            (
                str(target.get("subject") or ""),
                str(target.get("skillId") or ""),
                int(target.get("variantOrdinal") or 0),
            )
            for target in targets
            if isinstance(target, Mapping)
        }

    def _is_content_canary(
        self, build: Mapping[str, Any], row: Mapping[str, Any]
    ) -> bool:
        return (
            str(row.get("subject") or ""),
            str(row.get("skill_id") or ""),
            int(row.get("variant_ordinal") or 0),
        ) in self._content_canary_keys(build)

    def _prior_content_evidence_from_histories(
        self,
        *,
        row: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        passed_item_ids: frozenset[str],
        locked_attempt_histories_by_item: Mapping[
            str, Mapping[int, Mapping[str, object]]
        ],
    ) -> list[Mapping[str, object]]:
        ordinal = int(row.get("variant_ordinal") or 0)
        priors = [
            value
            for value in rows
            if str(value.get("subject") or "") == str(row.get("subject") or "")
            and str(value.get("skill_id") or "") == str(row.get("skill_id") or "")
            and str(value.get("boundary_version") or "")
            == str(row.get("boundary_version") or "")
            and int(value.get("variant_ordinal") or 0) in range(1, ordinal)
        ]
        priors.sort(key=lambda value: int(value["variant_ordinal"]))
        if [int(value["variant_ordinal"]) for value in priors] != list(
            range(1, ordinal)
        ):
            raise LearningCatalogBuildConflict("prior content variant set drift")
        result: list[Mapping[str, object]] = []
        for prior in priors:
            if str(prior.get("id") or "") not in passed_item_ids:
                raise LearningCatalogBuildConflict("prior content proof drift")
            histories = locked_attempt_histories_by_item.get(
                str(prior["id"])
            )
            if not isinstance(histories, Mapping):
                raise LearningCatalogBuildConflict("prior content evidence is missing")
            evidence = self._content_attempt_evidence_from_histories(
                item=prior,
                histories=histories,
                attempt=int(prior["attempt_count"]),
            )
            result.append(evidence)
        return result

    @staticmethod
    def _provider_cas_matches(
        row: Mapping[str, Any],
        *,
        logical_attempt: int,
        generation_request_id: str,
        phase: str,
        phase_ordinal: int,
        lease_token: str,
        attempt_started_at: int,
        outer_deadline_at: int,
        work_deadline_at: int,
        now: int,
    ) -> bool:
        phases = {
            str(authority["phase"]): int(authority["phaseOrdinal"])
            for authority in QUESTION_PHASE_IO
        }
        return (
            phases.get(phase) == int(phase_ordinal)
            and str(row.get("status") or "") == "processing"
            and int(row.get("attempt_count") or 0) == int(logical_attempt)
            and int(row.get("content_claim_attempt_ordinal") or 0)
            == int(logical_attempt)
            and str(row.get("active_generation_request_id") or "")
            == generation_request_id
            and str(row.get("content_phase") or "") == phase
            and str(row.get("content_lease_token") or "") == lease_token
            and int(row.get("content_attempt_started_at") or 0)
            == int(attempt_started_at)
            and int(row.get("content_provider_attempt_hard_deadline_at") or 0)
            == int(outer_deadline_at)
            and int(row.get("content_work_unit_deadline_at") or 0)
            == int(work_deadline_at)
            and int(row.get("content_lease_expires_at") or 0)
            == int(work_deadline_at)
            and int(work_deadline_at) >= int(now)
            and int(outer_deadline_at) >= int(now)
        )

    @staticmethod
    def _normalize_content_candidate(
        course: Mapping[str, object],
    ) -> dict[str, Any]:
        required = {
            "id",
            "version",
            "gradeCode",
            "subject",
            "nodeCode",
            "title",
            "objective",
            "status",
            "content",
        }
        if not isinstance(course, Mapping) or set(course) != required:
            raise LearningCatalogBuildConflict("content candidate shape drift")
        normalized = json.loads(
            json.dumps(course, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        if normalized.get("status") not in {"unverified", "published"}:
            raise LearningCatalogBuildConflict("content candidate status drift")
        return normalized

    def _create_or_replay_content_candidate(
        self,
        conn: DatabaseConnection,
        *,
        row: Mapping[str, Any],
        course: Mapping[str, Any],
        generator_profile: Mapping[str, object],
        now: int,
    ) -> tuple[DatabaseRow, DatabaseRow]:
        request_id = str(row["active_generation_request_id"])
        if course.get("status") != "unverified":
            raise LearningCatalogBuildConflict("persisted candidate must be unverified")
        profile_json = self.encode_json(generator_profile)
        fingerprint = hashlib.sha256(
            self.encode_json(
                {
                    "gradeCode": row["grade_code"],
                    "subject": row["subject"],
                    "nodeCode": row["skill_id"],
                    "curriculumVersion": row["curriculum_version"],
                    "boundaryVersion": row["boundary_version"],
                    "generator": "openmaic_question_phase_v2",
                    "providerProfile": generator_profile,
                    "requestedCandidateCount": 1,
                }
            ).encode("utf-8")
        ).hexdigest()
        job_id = "learning_course_job_" + hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest()[:32]
        conn.execute(
            """
            INSERT INTO learning_course_generation_jobs(
              id, request_id, request_fingerprint, grade_code, subject,
              node_code, curriculum_version, boundary_version, generator,
              provider, model, prompt_version, requested_candidate_count,
              status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'openmaic_question_phase_v2',
              ?, ?, 'mira.learning.question-contract.v2', 1, 'generating', ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                job_id,
                request_id,
                fingerprint,
                row["grade_code"],
                row["subject"],
                row["skill_id"],
                row["curriculum_version"],
                row["boundary_version"],
                generator_profile["name"],
                generator_profile["model"],
                now,
                now,
            ),
        )
        job = conn.execute(
            """
            SELECT * FROM learning_course_generation_jobs
            WHERE request_id = ? LIMIT 1 FOR UPDATE
            """,
            (request_id,),
        ).fetchone()
        if (
            job is None
            or str(job.get("request_fingerprint") or "") != fingerprint
            or str(job.get("grade_code") or "") != str(row["grade_code"])
            or str(job.get("subject") or "") != str(row["subject"])
            or str(job.get("node_code") or "") != str(row["skill_id"])
            or str(job.get("curriculum_version") or "")
            != str(row["curriculum_version"])
            or str(job.get("boundary_version") or "")
            != str(row["boundary_version"])
            or str(job.get("generator") or "") != "openmaic_question_phase_v2"
            or str(job.get("provider") or "") != str(generator_profile["name"])
            or str(job.get("model") or "") != str(generator_profile["model"])
            or str(job.get("prompt_version") or "")
            != "mira.learning.question-contract.v2"
            or int(job.get("requested_candidate_count") or 0) != 1
        ):
            raise LearningCatalogBuildConflict("content generation job drift")
        content_json = self.encode_json(course["content"])
        content_hash = hashlib.sha256(
            self.encode_json(
                {
                    "gradeCode": course["gradeCode"],
                    "subject": course["subject"],
                    "nodeCode": course["nodeCode"],
                    "title": course["title"],
                    "objective": course["objective"],
                    "content": course["content"],
                }
            ).encode("utf-8")
        ).hexdigest()
        candidate_id = "learning_course_candidate_" + hashlib.sha256(
            f"{job['id']}:1".encode("utf-8")
        ).hexdigest()[:32]
        conn.execute(
            """
            INSERT INTO learning_course_generation_candidates(
              id, job_id, ordinal, course_id, course_version, grade_code,
              subject, node_code, curriculum_version, boundary_version,
              title, objective, status, content_hash, content_json,
              created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'generated', ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                candidate_id,
                job["id"],
                course["id"],
                course["version"],
                course["gradeCode"],
                course["subject"],
                course["nodeCode"],
                row["curriculum_version"],
                row["boundary_version"],
                course["title"],
                course["objective"],
                content_hash,
                content_json,
                now,
                now,
            ),
        )
        candidate = conn.execute(
            """
            SELECT * FROM learning_course_generation_candidates
            WHERE job_id = ? AND ordinal = 1 LIMIT 1 FOR UPDATE
            """,
            (job["id"],),
        ).fetchone()
        if (
            candidate is None
            or str(candidate.get("course_id") or "") != str(course["id"])
            or str(candidate.get("course_version") or "") != str(course["version"])
            or str(candidate.get("content_hash") or "") != content_hash
            or str(candidate.get("content_json") or "") != content_json
            or str(candidate.get("grade_code") or "") != str(course["gradeCode"])
            or str(candidate.get("subject") or "") != str(course["subject"])
            or str(candidate.get("node_code") or "") != str(course["nodeCode"])
            or str(candidate.get("curriculum_version") or "")
            != str(row["curriculum_version"])
            or str(candidate.get("boundary_version") or "")
            != str(row["boundary_version"])
            or str(candidate.get("title") or "") != str(course["title"])
            or str(candidate.get("objective") or "") != str(course["objective"])
            or str(candidate.get("status") or "") != "generated"
            or candidate.get("validation_json") is not None
        ):
            raise LearningCatalogBuildConflict("content candidate drift")
        return job, candidate

    def _lock_content_candidate_for_item(
        self,
        conn: DatabaseConnection,
        *,
        row: Mapping[str, Any],
    ) -> tuple[DatabaseRow | None, DatabaseRow | None]:
        job = conn.execute(
            """
            SELECT * FROM learning_course_generation_jobs
            WHERE request_id = ? LIMIT 1 FOR UPDATE
            """,
            (row.get("active_generation_request_id"),),
        ).fetchone()
        if job is None:
            return None, None
        candidate = conn.execute(
            """
            SELECT * FROM learning_course_generation_candidates
            WHERE job_id = ? AND ordinal = 1 LIMIT 1 FOR UPDATE
            """,
            (job["id"],),
        ).fetchone()
        if (
            candidate is None
            or str(candidate.get("course_id") or "") != str(row.get("course_id") or "")
            or str(candidate.get("course_version") or "")
            != str(row.get("course_version") or "")
        ):
            return job, None
        return job, candidate

    def _content_gate_envelope(
        self,
        *,
        receipt: Mapping[str, object],
        receipt_hash: str,
    ) -> str:
        exact_hash = hashlib.sha256(self.encode_json(receipt).encode("utf-8")).hexdigest()
        if exact_hash != receipt_hash or not re.fullmatch(r"[0-9a-f]{64}", receipt_hash):
            raise LearningCatalogBuildConflict("Host receipt hash drift")
        return self.encode_json(
            {
                "schemaVersion": formal_content_validation_identity(preparation_authority_grade(receipt))["hostGateEvidenceSchemaVersion"],
                "contentFingerprint": str(receipt.get("hostContentFingerprint") or ""),
                "hostGateReceipt": receipt,
                "hostGateReceiptHash": receipt_hash,
            }
        )

    def _fence_content_build_locked(
        self,
        conn: DatabaseConnection,
        *,
        build: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        error_code: str,
        now: int,
        item_id: str | None = None,
    ) -> None:
        if str(build.get("status") or "") not in {"queued", "running"}:
            return
        safe_code = self.safe_code(error_code)
        safe_message = "正式备课内容阶段已安全终止。"
        isolate = bool(item_id and safe_code in {
            "preparation_content_canary_failed", "preparation_content_validation_failed",
        } and requested_supply(conn, build) is not None)
        if isolate:
            record_supply_incident(conn, item_id=item_id, stage="content", reason=safe_code, now=now)
        else:
            build_cursor = conn.execute(
                """
                UPDATE learning_catalog_build_jobs
                SET status = 'failed', error_code = ?, error_message_safe = ?,
                  completed_at = ?, updated_at = ?
                WHERE id = ? AND execution_mode = 'content_only'
                  AND status IN ('queued', 'running')
                """,
                (safe_code, safe_message, now, now, build["id"]),
            )
            if build_cursor.rowcount != 1:
                return
        target_item_id = item_id
        if target_item_id is None:
            processing = [
                row
                for row in rows
                if str(row.get("status") or "") == "processing"
            ]
            if len(processing) == 1:
                target_item_id = str(processing[0]["id"])
        if target_item_id:
            conn.execute(
                """
                UPDATE learning_catalog_build_items
                SET status = 'failed', content_phase = 'failed',
                  content_gate_status = CASE
                    WHEN content_gate_status IN ('pending','retry_wait')
                      OR content_phase IN ('host_gate_pending','host_gate_running')
                    THEN 'failed_deterministic' ELSE 'not_started' END,
                  error_code = ?, error_message_safe = ?, completed_at = ?,
                  content_lease_token = NULL, content_lease_expires_at = NULL,
                  content_heartbeat_at = NULL,
                  content_provider_attempt_hard_deadline_at = NULL,
                  content_work_unit_deadline_at = NULL, updated_at = ?
                WHERE id = ? AND build_job_id = ? AND status = 'processing'
                """,
                (
                    safe_code,
                    safe_message,
                    now,
                    now,
                    target_item_id,
                    build["id"],
                ),
            )

    def get_build_release_readiness(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        for_update: bool = False,
    ) -> dict[str, int]:
        lock = " FOR UPDATE" if for_update else ""
        rows = conn.execute(
            """
            SELECT item.id, item.status,
              CASE WHEN item.status = 'ready' AND EXISTS (
                SELECT 1
                FROM learning_courses AS course
                JOIN learning_course_lesson_package_bindings AS binding
                  ON binding.course_id = course.id
                 AND binding.course_version = course.version
                JOIN learning_lesson_packages AS package
                  ON package.id = binding.package_id
                 AND package.version = binding.package_version
                WHERE course.id = item.course_id
                  AND course.version = item.course_version
                  AND (
                    (course.status = 'validated'
                      AND course.quality_status = 'auto_validated')
                    OR (course.status = 'published'
                      AND course.quality_status = 'released')
                  )
                  AND course.retired_at IS NULL
                  AND course.curriculum_version = item.curriculum_version
                  AND course.boundary_version = item.boundary_version
                  AND binding.package_id = item.package_id
                  AND binding.package_version = item.package_version
                  AND package.status = 'published'
                  AND package.retired_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM learning_lesson_package_assets AS package_asset
                    LEFT JOIN learning_media_assets AS asset
                      ON asset.id = package_asset.asset_id
                    WHERE package_asset.package_id = package.id
                      AND package_asset.package_version = package.version
                      AND package_asset.required_asset = 1
                      AND (
                        asset.id IS NULL OR asset.status IS NULL
                        OR asset.status <> 'ready'
                        OR asset.scan_status IS NULL
                        OR asset.scan_status <> 'passed'
                        OR asset.moderation_status IS NULL
                        OR asset.moderation_status <> 'passed'
                        OR asset.transcode_status IS NULL
                        OR asset.transcode_status NOT IN ('passed', 'not_required')
                        OR NOT EXISTS (
                          SELECT 1
                          FROM learning_media_asset_variants AS asset_variant
                          WHERE asset_variant.asset_id = asset.id
                            AND asset_variant.status = 'ready'
                        )
                        OR NOT EXISTS (
                          SELECT 1
                          FROM learning_media_quality_reviews AS asset_review
                          WHERE asset_review.asset_id = asset.id
                            AND asset_review.required_review = 1
                            AND asset_review.status = 'approved'
                        )
                        OR EXISTS (
                          SELECT 1
                          FROM learning_media_quality_reviews AS asset_review
                          WHERE asset_review.asset_id = asset.id
                            AND asset_review.required_review = 1
                            AND asset_review.status <> 'approved'
                        )
                      )
                  )
              ) THEN 1 ELSE 0 END AS release_ready
            FROM learning_catalog_build_items AS item
            WHERE item.build_job_id = ?
            """ + lock,
            (build_id,),
        ).fetchall()
        item_ready = sum(1 for row in rows if str(row["status"]) == "ready")
        release_ready = sum(int(row.get("release_ready") or 0) for row in rows)
        media_pending = sum(
            1 for row in rows if str(row["status"]) == "course_ready"
        ) + max(0, item_ready - release_ready)
        return {
            "itemReadyCount": item_ready,
            "releaseReadyItemCount": release_ready,
            "mediaPendingItemCount": media_pending,
        }

    def claim_next_item(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        now: int,
        retry_failed: bool,
        stale_before: int,
        retry_external: bool = False,
        excluding_item_ids: Sequence[str] = (),
    ) -> DatabaseRow | None:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        if build is not None:
            self.list_build_items(conn, build_id=build_id, for_update=True)
        if (
            build is None
            or str(build.get("execution_mode") or "") != "full_pipeline"
            or str(build.get("stage_ceiling") or "") != "active_release"
        ):
            return None
        if release is None:
            return None
        excluded = tuple(str(item_id) for item_id in excluding_item_ids if item_id)
        exclusion_clause = ""
        if excluded:
            exclusion_placeholders = ", ".join("?" for _ in excluded)
            exclusion_clause = f" AND id NOT IN ({exclusion_placeholders})"
        row = conn.execute(
            f"""
            SELECT * FROM learning_catalog_build_items
            WHERE build_job_id = ? AND (
              (
                course_id IS NOT NULL AND (
                  (
                    status = 'course_ready'
                    AND (
                      (
                        active_package_request_id IS NOT NULL
                        AND package_attempt_count BETWEEN 1 AND 2
                      )
                      OR (
                        active_package_request_id IS NULL
                        AND package_attempt_count < 2
                      )
                    )
                  )
                  OR (
                    status = 'processing'
                    AND (
                      (
                        active_package_request_id IS NOT NULL
                        AND package_attempt_count BETWEEN 1 AND 2
                      )
                      OR (
                        active_package_request_id IS NULL
                        AND package_attempt_count < 2
                      )
                    )
                    AND updated_at < ?
                  )
                )
              )
              OR (
                course_id IS NULL AND (
                  (status = 'pending' AND attempt_count = 0)
                  OR (
                    status = 'failed' AND ? = 1 AND attempt_count < 2
                  )
                  OR (
                    status = 'external_failed' AND ? = 1
                    AND attempt_count BETWEEN 1 AND 2
                    AND active_generation_request_id IS NOT NULL
                  )
                  OR (
                    status = 'processing' AND attempt_count BETWEEN 1 AND 2
                    AND active_generation_request_id IS NOT NULL
                    AND updated_at < ?
                  )
                )
              )
            )
              {exclusion_clause}
            ORDER BY
              CASE
                WHEN course_id IS NOT NULL
                  AND active_package_request_id IS NOT NULL THEN 0
                WHEN course_id IS NOT NULL THEN 1
                WHEN status = 'external_failed' THEN 2
                WHEN status = 'failed' THEN 3
                WHEN status = 'pending' THEN 4
                ELSE 5
              END,
              grade_code, subject, skill_id, variant_ordinal
            LIMIT 1 FOR UPDATE
            """,
            (
                build_id,
                stale_before,
                1 if retry_failed else 0,
                1 if retry_external else 0,
                stale_before,
                *excluded,
            ),
        ).fetchone()
        if row is None:
            return None
        claimed_from_status = str(row["status"])
        prior_error_code = str(row.get("error_code") or "")
        prior_error_message = str(row.get("error_message_safe") or "")
        if row.get("course_id") is not None:
            claimed = self._claim_package_row(
                conn,
                row=row,
                now=now,
                claimed_from_status=claimed_from_status,
            )
            if claimed is None:
                return None
            self._mark_build_running(conn, build_id=build_id, now=now)
            return claimed

        current_attempt = int(row.get("attempt_count") or 0)
        starts_new_attempt = claimed_from_status in {"pending", "failed"}
        attempt_count = current_attempt + 1 if starts_new_attempt else current_attempt
        if attempt_count < 1 or attempt_count > 2:
            # The SELECT above should make this unreachable.  Keep the write
            # path fail-closed if a future status transition violates it.
            return None
        generation_request_id = str(row["generation_request_id"])
        active_request_id = str(row.get("active_generation_request_id") or "")
        claim_origin_status = str(row.get("claim_origin_status") or "")
        if starts_new_attempt:
            active_request_id = (
                generation_request_id
                if attempt_count == 1
                else f"{generation_request_id}.retry{attempt_count}"
            )
            claim_origin_status = claimed_from_status
        if not active_request_id or claim_origin_status not in {
            "pending",
            "failed",
            "external_failed",
        }:
            # Stale and media-pending continuations must have a durable logical
            # attempt written by their original pending/failed claim.
            return None
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', attempt_count = ?,
              claim_origin_status = ?, active_generation_request_id = ?,
              started_at = COALESCE(started_at, ?), updated_at = ?
            WHERE id = ?
            """,
            (
                attempt_count,
                claim_origin_status,
                active_request_id,
                now,
                now,
                row["id"],
            ),
        )
        self._mark_build_running(conn, build_id=build_id, now=now)
        claimed = conn.execute(
            "SELECT * FROM learning_catalog_build_items WHERE id = ?",
            (row["id"],),
        ).fetchone()
        return {
            **dict(claimed),
            "claimed_from_status": claimed_from_status,
            "claimed_stage": "course",
            **(
                {
                    "prior_error_code": prior_error_code,
                    "prior_error_message_safe": prior_error_message,
                }
                if claim_origin_status == "failed"
                and prior_error_code
                and prior_error_message
                else {}
            ),
        }

    def claim_package_for_item(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        now: int,
    ) -> DatabaseRow | None:
        """Start or resume the bounded package stage for one persisted course."""

        identity = conn.execute(
            """
            SELECT build_job_id, release_id FROM learning_catalog_build_items
            WHERE id = ? LIMIT 1
            """,
            (item_id,),
        ).fetchone()
        if identity is None:
            return None
        release = self.get_release(
            conn,
            release_id=str(identity["release_id"]),
            for_update=True,
        )
        if release is None:
            return None
        build = self.get_build(
            conn,
            build_id=str(identity["build_job_id"]),
            for_update=True,
        )
        row = conn.execute(
            """
            SELECT * FROM learning_catalog_build_items
            WHERE id = ? LIMIT 1 FOR UPDATE
            """,
            (item_id,),
        ).fetchone()
        if (
            build is None
            or str(build.get("release_id") or "") != str(release["id"])
            or str(build.get("execution_mode") or "") != "full_pipeline"
            or str(build.get("stage_ceiling") or "") != "active_release"
        ):
            return None
        if (
            row is None
            or str(row.get("build_job_id") or "") != str(build["id"])
            or str(row.get("release_id") or "") != str(release["id"])
            or str(row.get("execution_mode_snapshot") or "") != "full_pipeline"
            or row.get("course_id") is None
        ):
            return None
        if str(row.get("status") or "") != "processing":
            return None
        if str(row.get("active_package_request_id") or ""):
            # An already-active processing lease belongs to another worker.
            # Stale recovery must enter through claim_next_item's lease check.
            return None
        current_attempt = int(row.get("package_attempt_count") or 0)
        if current_attempt >= 2:
            return None
        package_attempt_count = current_attempt + 1
        active_request_id = self.package_request_id(
            item_id=str(row["id"]),
            course_id=str(row["course_id"]),
            course_version=str(row["course_version"]),
            attempt=package_attempt_count,
        )
        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET package_attempt_count = ?, active_package_request_id = ?,
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'processing'
              AND active_package_request_id IS NULL
              AND package_attempt_count = ?
            """,
            (
                package_attempt_count,
                active_request_id,
                now,
                item_id,
                current_attempt,
            ),
        )
        if cursor.rowcount != 1:
            return None
        claimed = self.get_item(conn, item_id=item_id)
        return {
            **dict(claimed),
            "claimed_from_status": "processing",
            "claimed_stage": "package",
            "package_claim_kind": "new",
        }

    def _claim_package_row(
        self,
        conn: DatabaseConnection,
        *,
        row: Mapping[str, Any],
        now: int,
        claimed_from_status: str,
    ) -> DatabaseRow | None:
        current_attempt = int(row.get("package_attempt_count") or 0)
        active_request_id = str(row.get("active_package_request_id") or "")
        if active_request_id:
            if current_attempt < 1 or current_attempt > 2:
                return None
            claim_kind = (
                "stale"
                if claimed_from_status == "processing"
                else "media_replay"
            )
            package_attempt_count = current_attempt
        else:
            if claimed_from_status not in {"course_ready", "processing"}:
                return None
            if current_attempt >= 2:
                return None
            # Content validation runs while this lightweight lease is held.
            # Only claim_package_for_item may spend a package attempt after the
            # deterministic gate passes.
            package_attempt_count = current_attempt
            claim_kind = (
                "content_gate_stale"
                if claimed_from_status == "processing"
                else "content_gate"
            )
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', package_attempt_count = ?,
              active_package_request_id = ?, error_code = NULL,
              error_message_safe = NULL, completed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                package_attempt_count,
                active_request_id or None,
                now,
                row["id"],
            ),
        )
        claimed = self.get_item(conn, item_id=str(row["id"]))
        if claimed is None:
            return None
        return {
            **dict(claimed),
            "claimed_from_status": claimed_from_status,
            "claimed_stage": "package",
            "package_claim_kind": claim_kind,
        }

    def mark_course_ready_for_content_gate(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        course_id: str,
        course_version: str,
        expected_generation_request_id: str,
        now: int,
    ) -> DatabaseRow | None:
        """Atomically persist a new course and hold its content-gate lease."""

        cursor = conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'processing', course_id = ?, course_version = ?,
              package_id = NULL, package_version = NULL,
              package_attempt_count = 0, active_package_request_id = NULL,
              error_code = NULL, error_message_safe = NULL,
              completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'processing' AND course_id IS NULL
              AND active_generation_request_id = ?
            """,
            (
                course_id,
                course_version,
                now,
                item_id,
                expected_generation_request_id,
            ),
        )
        if cursor.rowcount != 1:
            return None
        row = self.get_item(conn, item_id=item_id)
        return {
            **dict(row),
            "claimed_from_status": "processing",
            "claimed_stage": "package",
            "package_claim_kind": "content_gate",
        }

    @staticmethod
    def package_request_id(
        *, item_id: str, course_id: str, course_version: str, attempt: int
    ) -> str:
        digest = hashlib.sha256(
            f"{item_id}:{course_id}@{course_version}".encode("utf-8")
        ).hexdigest()[:48]
        base = f"catalog_pkg_v2_{digest}"
        return base if int(attempt) == 1 else f"{base}.retry{int(attempt)}"

    @staticmethod
    def _mark_build_running(
        conn: DatabaseConnection, *, build_id: str, now: int
    ) -> None:
        conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET status = 'running', started_at = COALESCE(started_at, ?),
              error_code = NULL, error_message_safe = NULL,
              completed_at = NULL, updated_at = ?
            WHERE id = ? AND status <> 'completed'
            """,
            (now, now, build_id),
        )

    def mark_course_ready(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        course_id: str,
        course_version: str,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'course_ready', course_id = ?, course_version = ?,
              package_id = NULL, package_version = NULL,
              active_package_request_id = NULL,
              error_code = NULL, error_message_safe = NULL,
              completed_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (course_id, course_version, now, item_id),
        )
        return self.get_item(conn, item_id=item_id)

    def mark_package_media_pending(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        package_id: str | None,
        package_version: int | None,
        expected_request_id: str,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'course_ready', package_id = ?, package_version = ?,
              error_code = NULL, error_message_safe = NULL,
              completed_at = NULL, updated_at = ?
            WHERE id = ? AND course_id IS NOT NULL
              AND status = 'processing'
              AND active_package_request_id = ?
            """,
            (
                package_id or None,
                int(package_version) if package_version is not None else None,
                now,
                item_id,
                expected_request_id,
            ),
        )
        return self.get_item(conn, item_id=item_id)

    def mark_package_failed(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        error_code: str,
        error_message: str,
        expected_request_id: str,
        now: int,
    ) -> DatabaseRow:
        row = self.get_item(conn, item_id=item_id)
        if row is None:
            raise ValueError("catalog build item was not found")
        attempts = int(row.get("package_attempt_count") or 0)
        terminal = attempts >= 2
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = ?, active_package_request_id = NULL,
              package_id = NULL, package_version = NULL,
              error_code = ?, error_message_safe = ?,
              completed_at = ?, updated_at = ?
            WHERE id = ? AND course_id IS NOT NULL
              AND status = 'processing'
              AND active_package_request_id = ?
            """,
            (
                "failed" if terminal else "course_ready",
                self.safe_code(error_code),
                self.safe_message(error_message),
                now if terminal else None,
                now,
                item_id,
                expected_request_id,
            ),
        )
        return self.get_item(conn, item_id=item_id)

    def mark_content_gate_deferred(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        error_code: str,
        error_message: str,
        expected_course_id: str,
        expected_course_version: str,
        expected_generation_request_id: str,
        expected_updated_at: int,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'course_ready', error_code = ?,
              error_message_safe = ?, completed_at = NULL, updated_at = ?
            WHERE id = ? AND course_id IS NOT NULL
              AND status = 'processing'
              AND course_id = ? AND course_version = ?
              AND active_generation_request_id = ?
              AND active_package_request_id IS NULL
              AND updated_at = ?
            """,
            (
                self.safe_code(error_code),
                self.safe_message(error_message),
                now,
                item_id,
                expected_course_id,
                expected_course_version,
                expected_generation_request_id,
                int(expected_updated_at),
            ),
        )
        return self.get_item(conn, item_id=item_id)

    def reject_course_for_item(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        error_code: str,
        error_message: str,
        expected_course_id: str,
        expected_course_version: str,
        expected_active_package_request_id: str,
        expected_updated_at: int,
        now: int,
    ) -> DatabaseRow:
        """Retire a bad immutable course and return its item to course retry."""

        row = conn.execute(
            """
            SELECT * FROM learning_catalog_build_items
            WHERE id = ? LIMIT 1 FOR UPDATE
            """,
            (item_id,),
        ).fetchone()
        if row is None or row.get("course_id") is None:
            raise ValueError("catalog item does not reference a course")
        if (
            str(row.get("status") or "") != "processing"
            or str(row.get("course_id") or "") != expected_course_id
            or str(row.get("course_version") or "") != expected_course_version
            or str(row.get("active_package_request_id") or "")
            != expected_active_package_request_id
            or int(row.get("updated_at") or 0) != int(expected_updated_at)
        ):
            # A newer lease/result owns this item.  The late validator must not
            # retire or clear its course.
            return row
        safe_code = self.safe_code(error_code)
        safe_message = self.safe_message(error_message)
        conn.execute(
            """
            UPDATE learning_courses
            SET status = 'retired', quality_status = 'rejected_content_gate',
              retired_at = COALESCE(retired_at, ?), updated_at = ?
            WHERE id = ? AND version = ?
            """,
            (now, now, row["course_id"], row["course_version"]),
        )
        conn.execute(
            """
            UPDATE learning_course_generation_candidates
            SET status = 'rejected', error_code = ?, error_message_safe = ?,
              updated_at = ?
            WHERE course_id = ? AND course_version = ?
            """,
            (
                safe_code,
                safe_message,
                now,
                row["course_id"],
                row["course_version"],
            ),
        )
        conn.execute(
            """
            UPDATE learning_course_generation_jobs AS job
            JOIN learning_course_generation_candidates AS candidate
              ON candidate.job_id = job.id
            SET job.status = 'failed', job.error_code = ?,
              job.error_message_safe = ?, job.completed_at = ?,
              job.updated_at = ?
            WHERE candidate.course_id = ? AND candidate.course_version = ?
            """,
            (
                safe_code,
                safe_message,
                now,
                now,
                row["course_id"],
                row["course_version"],
            ),
        )
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'failed', course_id = NULL, course_version = NULL,
              package_id = NULL, package_version = NULL,
              package_attempt_count = 0, active_package_request_id = NULL,
              error_code = ?, error_message_safe = ?, completed_at = ?,
              updated_at = ?
            WHERE id = ?
            """,
            (safe_code, safe_message, now, now, item_id),
        )
        return self.get_item(conn, item_id=item_id)

    def get_course_for_release_gate(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_courses
            WHERE id = ? AND version = ? LIMIT 1
            """,
            (course_id, course_version),
        ).fetchone()

    def get_item_release_integrity(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT course.*,
              item.package_id AS item_package_id,
              item.package_version AS item_package_version,
              binding.package_id AS binding_package_id,
              binding.package_version AS binding_package_version,
              package.status AS package_status,
              package.source_course_content_hash AS source_course_content_hash
            FROM learning_catalog_build_items AS item
            JOIN learning_courses AS course
              ON course.id = item.course_id
             AND course.version = item.course_version
            LEFT JOIN learning_course_lesson_package_bindings AS binding
              ON binding.course_id = course.id
             AND binding.course_version = course.version
            LEFT JOIN learning_lesson_packages AS package
              ON package.id = binding.package_id
             AND package.version = binding.package_version
            WHERE item.id = ? LIMIT 1
            """,
            (item_id,),
        ).fetchone()

    def mark_item_ready(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        package_id: str,
        package_version: int,
        expected_request_id: str,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'ready', package_id = ?, package_version = ?,
              error_code = NULL, error_message_safe = NULL,
              completed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'processing'
              AND active_package_request_id = ?
            """,
            (
                package_id,
                int(package_version),
                now,
                now,
                item_id,
                expected_request_id,
            ),
        )
        return self.get_item(conn, item_id=item_id)

    def mark_item_failed(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        error_code: str,
        error_message: str,
        expected_generation_request_id: str,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              completed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'processing' AND course_id IS NULL
              AND active_generation_request_id = ?
            """,
            (
                self.safe_code(error_code),
                self.safe_message(error_message),
                now,
                now,
                item_id,
                expected_generation_request_id,
            ),
        )
        return self.get_item(conn, item_id=item_id)

    def mark_item_external_failed(
        self,
        conn: DatabaseConnection,
        *,
        item_id: str,
        error_code: str,
        error_message: str,
        expected_generation_request_id: str,
        now: int,
    ) -> DatabaseRow:
        """Persist a recoverable provider/transport outage without spending an attempt."""

        conn.execute(
            """
            UPDATE learning_catalog_build_items
            SET status = 'external_failed', error_code = ?,
              error_message_safe = ?, claim_origin_status = 'external_failed',
              completed_at = NULL, updated_at = ?
            WHERE id = ? AND status = 'processing' AND course_id IS NULL
              AND active_generation_request_id = ?
            """,
            (
                self.safe_code(error_code),
                self.safe_message(error_message),
                now,
                item_id,
                expected_generation_request_id,
            ),
        )
        return self.get_item(conn, item_id=item_id)

    def get_item(
        self, conn: DatabaseConnection, *, item_id: str
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
            (item_id,),
        ).fetchone()

    def refresh_build_counts(
        self, conn: DatabaseConnection, *, build_id: str, now: int
    ) -> DatabaseRow:
        release, build = self.lock_build_authority(conn, build_id=build_id)
        if release is None or build is None:
            raise RuntimeError("catalog build authority was not found")
        items = self.list_build_items(
            conn,
            build_id=build_id,
            for_update=True,
        )
        statuses = [str(item.get("status") or "") for item in items]
        total = len(items)
        ready = sum(status == "ready" for status in statuses)
        failed = sum(status == "failed" for status in statuses)
        remaining = sum(
            status in {"pending", "processing", "course_ready", "external_failed"}
            for status in statuses
        )
        status = (
            "completed"
            if total > 0 and ready == total
            else "failed"
            if failed > 0 and remaining == 0
            else "running"
        )
        conn.execute(
            """
            UPDATE learning_catalog_build_jobs
            SET total_item_count = ?, ready_item_count = ?, failed_item_count = ?,
              status = ?, completed_at = CASE WHEN ? = 'completed' THEN ? ELSE NULL END,
              updated_at = ? WHERE id = ?
            """,
            (total, ready, failed, status, status, now, now, build_id),
        )
        conn.execute(
            """
            UPDATE learning_catalog_releases
            SET ready_item_count = ?, quality_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                ready,
                "candidate_ready" if status == "completed" else "building",
                now,
                release["id"],
            ),
        )
        return self.get_build(conn, build_id=build_id)

    def activate_release(
        self,
        conn: DatabaseConnection,
        *,
        release_id: str,
        expected_boundary_versions: set[str],
        allow_partial: bool,
        now: int,
    ) -> DatabaseRow:
        release = self.get_release(conn, release_id=release_id, for_update=True)
        if release is None:
            raise LearningCatalogActivationError("catalog release was not found")
        build = self.get_build_by_release(
            conn,
            release_id=release_id,
            for_update=True,
        )
        if build is None:
            raise LearningCatalogActivationError("catalog build was not found")
        items = self.list_build_items(
            conn,
            build_id=str(build["id"]),
            for_update=True,
        )
        if (
            str(build.get("execution_mode") or "") != "full_pipeline"
            or str(build.get("stage_ceiling") or "") != "active_release"
        ):
            raise LearningCatalogActivationError(
                "content-only catalog builds cannot be activated"
            )
        if str(release.get("status") or "") == "active":
            return release
        conn.execute(
            """
            SELECT id FROM learning_catalog_releases
            WHERE curriculum_version = ? FOR UPDATE
            """,
            (release["curriculum_version"],),
        ).fetchall()
        if build is None or str(build["status"]) != "completed":
            raise LearningCatalogActivationError("catalog build is not complete")
        if not items or any(str(item["status"]) != "ready" for item in items):
            raise LearningCatalogActivationError("catalog contains unfinished items")
        item_boundaries = {str(item["boundary_version"]) for item in items}
        if not item_boundaries.issubset(expected_boundary_versions):
            raise LearningCatalogActivationError(
                "catalog release contains a superseded skill boundary"
            )
        if not allow_partial and item_boundaries != expected_boundary_versions:
            raise LearningCatalogActivationError(
                "catalog release does not cover every current skill boundary"
            )

        for item in items:
            ready = conn.execute(
                """
                SELECT course.id
                FROM learning_courses AS course
                JOIN learning_course_lesson_package_bindings AS binding
                  ON binding.course_id = course.id
                 AND binding.course_version = course.version
                JOIN learning_lesson_packages AS package
                  ON package.id = binding.package_id
                 AND package.version = binding.package_version
                WHERE course.id = ? AND course.version = ?
                  AND course.status = 'validated'
                  AND course.quality_status = 'auto_validated'
                  AND course.retired_at IS NULL
                  AND course.curriculum_version = ?
                  AND course.boundary_version = ?
                  AND binding.package_id = ? AND binding.package_version = ?
                  AND package.status = 'published' AND package.retired_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1
                    FROM learning_lesson_package_assets AS package_asset
                    LEFT JOIN learning_media_assets AS asset
                      ON asset.id = package_asset.asset_id
                    WHERE package_asset.package_id = package.id
                      AND package_asset.package_version = package.version
                      AND package_asset.required_asset = 1
                      AND (
                        asset.id IS NULL OR asset.status IS NULL
                        OR asset.status <> 'ready'
                        OR asset.scan_status IS NULL
                        OR asset.scan_status <> 'passed'
                        OR asset.moderation_status IS NULL
                        OR asset.moderation_status <> 'passed'
                        OR asset.transcode_status IS NULL
                        OR asset.transcode_status NOT IN ('passed', 'not_required')
                        OR NOT EXISTS (
                          SELECT 1
                          FROM learning_media_asset_variants AS asset_variant
                          WHERE asset_variant.asset_id = asset.id
                            AND asset_variant.status = 'ready'
                        )
                        OR NOT EXISTS (
                          SELECT 1
                          FROM learning_media_quality_reviews AS asset_review
                          WHERE asset_review.asset_id = asset.id
                            AND asset_review.required_review = 1
                            AND asset_review.status = 'approved'
                        )
                        OR EXISTS (
                          SELECT 1
                          FROM learning_media_quality_reviews AS asset_review
                          WHERE asset_review.asset_id = asset.id
                            AND asset_review.required_review = 1
                            AND asset_review.status <> 'approved'
                        )
                      )
                  )
                LIMIT 1
                """,
                (
                    item["course_id"],
                    item["course_version"],
                    item["curriculum_version"],
                    item["boundary_version"],
                    item["package_id"],
                    item["package_version"],
                ),
            ).fetchone()
            if ready is None:
                raise LearningCatalogActivationError(
                    f"catalog item is not release-ready: {item['id']}"
                )

        old_items = conn.execute(
            """
            SELECT item.course_id, item.course_version
            FROM learning_catalog_releases AS old_release
            JOIN learning_catalog_release_items AS item
              ON item.release_id = old_release.id
            WHERE old_release.curriculum_version = ?
              AND old_release.status = 'active'
              AND old_release.id <> ?
            FOR UPDATE
            """,
            (release["curriculum_version"], release_id),
        ).fetchall()
        conn.execute(
            """
            UPDATE learning_catalog_releases
            SET status = 'retired', quality_status = 'superseded',
              retired_at = COALESCE(retired_at, ?), updated_at = ?
            WHERE curriculum_version = ? AND status = 'active' AND id <> ?
            """,
            (now, now, release["curriculum_version"], release_id),
        )
        conn.execute(
            """
            UPDATE learning_catalog_release_items AS item
            JOIN learning_catalog_releases AS old_release
              ON old_release.id = item.release_id
            SET item.status = 'retired', item.quality_status = 'superseded',
              item.retired_at = COALESCE(item.retired_at, ?), item.updated_at = ?
            WHERE old_release.curriculum_version = ?
              AND old_release.status = 'retired' AND old_release.id <> ?
            """,
            (now, now, release["curriculum_version"], release_id),
        )

        for item in items:
            conn.execute(
                """
                INSERT INTO learning_catalog_release_items(
                  release_id, course_id, course_version, grade_code, subject,
                  skill_id, curriculum_version, boundary_version,
                  variant_ordinal, package_id, package_version, status,
                  quality_status, published_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published',
                  'ready', ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  package_id = VALUES(package_id),
                  package_version = VALUES(package_version),
                  status = 'published', quality_status = 'ready',
                  published_at = COALESCE(published_at, VALUES(published_at)),
                  retired_at = NULL, updated_at = VALUES(updated_at)
                """,
                (
                    release_id,
                    item["course_id"],
                    item["course_version"],
                    item["grade_code"],
                    item["subject"],
                    item["skill_id"],
                    item["curriculum_version"],
                    item["boundary_version"],
                    item["variant_ordinal"],
                    item["package_id"],
                    item["package_version"],
                    now,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE learning_courses
                SET status = 'published', quality_status = 'released',
                  published_at = COALESCE(published_at, ?), retired_at = NULL,
                  updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (now, now, item["course_id"], item["course_version"]),
            )

        current_course_keys = {
            (str(item["course_id"]), str(item["course_version"])) for item in items
        }
        for old in old_items:
            key = (str(old["course_id"]), str(old["course_version"]))
            if key in current_course_keys:
                continue
            conn.execute(
                """
                UPDATE learning_courses
                SET status = 'retired', quality_status = 'superseded',
                  retired_at = COALESCE(retired_at, ?), updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (now, now, *key),
            )
        conn.execute(
            """
            UPDATE learning_catalog_releases
            SET status = 'active', quality_status = 'ready',
              ready_item_count = ?, activated_at = COALESCE(activated_at, ?),
              retired_at = NULL, updated_at = ? WHERE id = ?
            """,
            (len(items), now, now, release_id),
        )
        return self.get_release(conn, release_id=release_id)

    def get_classroom_item_receipt(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_curriculum_classroom_item_receipts
            WHERE build_item_id = ? LIMIT 1
            """
            + lock,
            (build_item_id,),
        ).fetchone()

    def list_classroom_item_receipts(
        self,
        conn: DatabaseConnection,
        *,
        release_id: str,
        for_update: bool = False,
    ) -> list[DatabaseRow]:
        lock = " FOR UPDATE" if for_update else ""
        return list(
            conn.execute(
                """
                SELECT receipt.*,
                  runtime.candidate_build_item_id AS runtime_build_item_id,
                  runtime.candidate_release_id AS runtime_release_id,
                  runtime.candidate_grade_code AS runtime_grade_code,
                  runtime.candidate_target_fingerprint AS runtime_target_fingerprint,
                  runtime.candidate_binding_contract_version AS runtime_contract_version,
                  runtime.course_id AS runtime_course_id,
                  runtime.course_version AS runtime_course_version,
                  runtime.package_id AS runtime_package_id,
                  runtime.package_version AS runtime_package_version,
                  runtime.status AS runtime_status
                FROM learning_curriculum_classroom_item_receipts AS receipt
                JOIN learning_openmaic_runtime_classrooms AS runtime
                  ON runtime.id = receipt.runtime_classroom_id
                WHERE receipt.release_id = ?
                ORDER BY receipt.build_item_id
                """
                + lock,
                (release_id,),
            ).fetchall()
        )

    def reserve_classroom_item_receipt(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        runtime_classroom_id: str,
        target_fingerprint: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        if re.fullmatch(r"[0-9a-f]{64}", str(target_fingerprint or "")) is None:
            raise ValueError("classroom target fingerprint is invalid")
        if int(now) <= 0:
            raise ValueError("classroom receipt timestamp is invalid")
        authority = conn.execute(
            """
            SELECT item.id AS build_item_id, item.release_id, item.grade_code,
              item.course_id AS item_course_id,
              item.course_version AS item_course_version,
              item.curriculum_version AS item_curriculum_version,
              item.content_phase, item.content_gate_status,
              item.content_receipt_hash,
              build.id AS build_id, build.execution_mode, build.stage_ceiling,
              build.curriculum_version AS build_curriculum_version,
              release_row.curriculum_version AS release_curriculum_version,
              release_row.status AS release_status,
              runtime.id AS runtime_classroom_id,
              runtime.course_id AS runtime_course_id,
              runtime.course_version AS runtime_course_version,
              runtime.package_id AS runtime_package_id,
              runtime.package_version AS runtime_package_version,
              runtime.status AS runtime_status,
              runtime.candidate_build_item_id,
              runtime.candidate_release_id,
              runtime.candidate_grade_code,
              runtime.candidate_target_fingerprint,
              runtime.candidate_binding_contract_version,
              runtime.candidate_bound_at
            FROM learning_catalog_build_items AS item
            JOIN learning_catalog_build_jobs AS build
              ON build.id = item.build_job_id
             AND build.release_id = item.release_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = item.release_id
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = ?
            WHERE item.id = ?
            LIMIT 1 FOR UPDATE
            """,
            (runtime_classroom_id, build_item_id),
        ).fetchone()
        if authority is None:
            raise ValueError("classroom receipt authority was not found")
        exact_runtime_binding = (
            str(authority.get("candidate_build_item_id") or "") == build_item_id
            and str(authority.get("candidate_release_id") or "")
            == str(authority.get("release_id") or "")
            and str(authority.get("candidate_grade_code") or "")
            == str(authority.get("grade_code") or "")
            and str(authority.get("candidate_target_fingerprint") or "")
            == target_fingerprint
            and str(authority.get("candidate_binding_contract_version") or "")
            == self.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION
            and type(authority.get("candidate_bound_at")) is int
        )
        exact_artifact_identity = (
            str(authority.get("item_course_id") or "")
            == str(authority.get("runtime_course_id") or "")
            and str(authority.get("item_course_version") or "")
            == str(authority.get("runtime_course_version") or "")
            and str(authority.get("item_curriculum_version") or "")
            == str(authority.get("build_curriculum_version") or "")
            == str(authority.get("release_curriculum_version") or "")
            and bool(str(authority.get("runtime_package_id") or ""))
            and type(authority.get("runtime_package_version")) is int
            and int(authority["runtime_package_version"]) > 0
        )
        if not (
            exact_runtime_binding
            and exact_artifact_identity
            and str(authority.get("execution_mode") or "") == "content_only"
            and str(authority.get("stage_ceiling") or "") == "content_ready"
            and str(authority.get("content_phase") or "") == "course_ready"
            and str(authority.get("content_gate_status") or "") == "passed"
            and bool(str(authority.get("content_receipt_hash") or ""))
            and str(authority.get("runtime_status") or "") == "ready"
            and str(authority.get("release_status") or "") != "active"
        ):
            raise ValueError("classroom receipt authority is not exact")
        existing = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        immutable = (
            str(authority["release_id"]),
            str(authority["grade_code"]),
            target_fingerprint,
            self.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION,
            runtime_classroom_id,
            str(authority["runtime_course_id"]),
            str(authority["runtime_course_version"]),
            str(authority["runtime_package_id"]),
            int(authority["runtime_package_version"]),
        )
        if existing is not None:
            persisted = (
                str(existing["release_id"]),
                str(existing["grade_code"]),
                str(existing["target_fingerprint"]),
                str(existing["binding_contract_version"]),
                str(existing["runtime_classroom_id"]),
                str(existing["course_id"]),
                str(existing["course_version"]),
                str(existing["package_id"]),
                int(existing["package_version"]),
            )
            if persisted != immutable:
                raise LearningCatalogActivationError(
                    "classroom receipt is already bound differently"
                )
            return existing, False
        conn.execute(
            """
            INSERT INTO learning_curriculum_classroom_item_receipts(
              build_item_id, release_id, grade_code, target_fingerprint,
              binding_contract_version, runtime_classroom_id,
              course_id, course_version, package_id, package_version,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (build_item_id, *immutable, int(now), int(now)),
        )
        created = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if created is None:
            raise RuntimeError("classroom receipt disappeared after reservation")
        return created, True

    def record_classroom_item_evidence(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        evidence_kind: str,
        outcome: str,
        receipt_hash: str,
        completed_at: int,
        now: int,
    ) -> DatabaseRow:
        columns = {
            "classroom": (
                "classroom_status",
                "classroom_receipt_hash",
                "classroom_completed_at",
            ),
            "tts": ("tts_status", "tts_receipt_hash", "tts_completed_at"),
            "asr_roundtrip": (
                "asr_roundtrip_status",
                "asr_roundtrip_receipt_hash",
                "asr_roundtrip_completed_at",
            ),
            "conversation_provider": (
                "conversation_provider_status",
                "conversation_provider_receipt_hash",
                "conversation_provider_completed_at",
            ),
        }
        if evidence_kind not in columns:
            raise ValueError("unsupported classroom evidence kind")
        if outcome not in {"passed", "failed"}:
            raise ValueError("unsupported classroom evidence outcome")
        if re.fullmatch(r"[0-9a-f]{64}", str(receipt_hash or "")) is None:
            raise ValueError("classroom evidence hash is invalid")
        if int(completed_at) <= 0 or int(now) < int(completed_at):
            raise ValueError("classroom evidence timestamp is invalid")
        status_column, hash_column, timestamp_column = columns[evidence_kind]
        existing = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if existing is None:
            raise ValueError("classroom receipt was not reserved")
        if int(completed_at) < int(existing["created_at"]):
            raise ValueError("classroom evidence predates its receipt")
        if str(existing[status_column]) != "pending":
            if (
                str(existing[status_column]) == outcome
                and str(existing[hash_column]) == receipt_hash
                and int(existing[timestamp_column]) == int(completed_at)
            ):
                return existing
            raise LearningCatalogActivationError(
                "classroom evidence is already terminal"
            )
        conn.execute(
            f"""
            UPDATE learning_curriculum_classroom_item_receipts
            SET {status_column} = ?, {hash_column} = ?,
              {timestamp_column} = ?, updated_at = ?
            WHERE build_item_id = ? AND {status_column} = 'pending'
            """,
            (outcome, receipt_hash, int(completed_at), int(now), build_item_id),
        )
        row = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if row is None:
            raise RuntimeError("classroom receipt disappeared after evidence")
        return row

    def mark_classroom_auto_validated(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        validation_contract_version: str,
        receipt_hash: str,
        validated_at: int,
        now: int,
    ) -> DatabaseRow:
        if not validation_contract_version or len(validation_contract_version) > 128:
            raise ValueError("auto-validation contract version is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", str(receipt_hash or "")) is None:
            raise ValueError("auto-validation receipt hash is invalid")
        if int(validated_at) <= 0 or int(now) < int(validated_at):
            raise ValueError("auto-validation timestamp is invalid")
        row = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if row is None or any(
            str(row[field]) != "passed"
            for field in (
                "classroom_status",
                "tts_status",
                "asr_roundtrip_status",
                "conversation_provider_status",
            )
        ):
            raise ValueError("all machine evidence must pass before validation")
        if int(validated_at) < max(
            int(row[field])
            for field in (
                "classroom_completed_at",
                "tts_completed_at",
                "asr_roundtrip_completed_at",
                "conversation_provider_completed_at",
            )
        ):
            raise ValueError("auto-validation predates machine evidence")
        if int(row["auto_validated"]) == 1:
            if (
                str(row["auto_validation_contract_version"])
                == validation_contract_version
                and str(row["auto_validation_receipt_hash"]) == receipt_hash
                and int(row["auto_validated_at"]) == int(validated_at)
            ):
                return row
            raise LearningCatalogActivationError(
                "auto-validation evidence is already terminal"
            )
        conn.execute(
            """
            UPDATE learning_curriculum_classroom_item_receipts
            SET auto_validated = 1, auto_validation_contract_version = ?,
              auto_validation_receipt_hash = ?, auto_validated_at = ?,
              updated_at = ?
            WHERE build_item_id = ? AND auto_validated = 0
            """,
            (
                validation_contract_version,
                receipt_hash,
                int(validated_at),
                int(now),
                build_item_id,
            ),
        )
        result = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if result is None:
            raise RuntimeError("classroom receipt disappeared after validation")
        return result

    def mark_classroom_human_approved(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        approved_by: str,
        receipt_hash: str,
        approved_at: int,
        now: int,
    ) -> DatabaseRow:
        if not approved_by or len(approved_by) > 128:
            raise ValueError("classroom approver is invalid")
        if re.fullmatch(r"[0-9a-f]{64}", str(receipt_hash or "")) is None:
            raise ValueError("classroom approval receipt hash is invalid")
        if int(approved_at) <= 0 or int(now) < int(approved_at):
            raise ValueError("classroom approval timestamp is invalid")
        row = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if row is None:
            raise ValueError("classroom receipt was not reserved")
        if int(row["approved"]) == 1:
            if (
                str(row["approved_by"]) == approved_by
                and str(row["approval_receipt_hash"]) == receipt_hash
                and int(row["approved_at"]) == int(approved_at)
            ):
                return row
            raise LearningCatalogActivationError(
                "human approval evidence is already terminal"
            )
        conn.execute(
            """
            UPDATE learning_curriculum_classroom_item_receipts
            SET approved = 1, approved_by = ?, approval_receipt_hash = ?,
              approved_at = ?, updated_at = ?
            WHERE build_item_id = ? AND approved = 0
            """,
            (approved_by, receipt_hash, int(approved_at), int(now), build_item_id),
        )
        result = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if result is None:
            raise RuntimeError("classroom receipt disappeared after approval")
        return result

    def record_classroom_publication_evidence(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        outcome: str,
        receipt_hash: str,
        completed_at: int,
        now: int,
    ) -> DatabaseRow:
        if outcome not in {"published", "failed"}:
            raise ValueError("unsupported classroom publication outcome")
        if re.fullmatch(r"[0-9a-f]{64}", str(receipt_hash or "")) is None:
            raise ValueError("publication receipt hash is invalid")
        if int(completed_at) <= 0 or int(now) < int(completed_at):
            raise ValueError("publication timestamp is invalid")
        row = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if row is None:
            raise ValueError("classroom receipt was not reserved")
        if int(completed_at) < int(row["created_at"]):
            raise ValueError("publication predates its receipt")
        if outcome == "published" and (
            int(row.get("auto_validated") or 0) != 1
            or int(completed_at) < int(row.get("auto_validated_at") or 0)
        ):
            raise ValueError("publication requires prior auto-validation")
        if str(row["publication_status"]) != "pending":
            if (
                str(row["publication_status"]) == outcome
                and str(row["publication_receipt_hash"]) == receipt_hash
                and int(row["published_at"]) == int(completed_at)
            ):
                return row
            raise LearningCatalogActivationError(
                "publication evidence is already terminal"
            )
        conn.execute(
            """
            UPDATE learning_curriculum_classroom_item_receipts
            SET publication_status = ?, publication_receipt_hash = ?,
              published_at = ?, updated_at = ?
            WHERE build_item_id = ? AND publication_status = 'pending'
            """,
            (outcome, receipt_hash, int(completed_at), int(now), build_item_id),
        )
        result = self.get_classroom_item_receipt(
            conn, build_item_id=build_item_id, for_update=True
        )
        if result is None:
            raise RuntimeError("classroom receipt disappeared after publication")
        return result

    def prepare_formal_validation_step(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        now: int,
        expected_stage: str = "validating",
        allow_partial: bool = False,
    ) -> dict[str, object]:
        """Reserve one release-scoped 059 canary before POST.

        Provider availability is a release property, not course content.  A
        canonical witness classroom binds the five-call canary to the exact
        release while preventing the same DeepSeek/Qwen checks from running once
        per each of the thirty immutable courses.
        """

        rows = self._lock_formal_validation_rows(
            conn,
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=publisher_plan_id,
            publisher_lease_token=publisher_lease_token,
            expected_stage=expected_stage,
            now=now,
            allow_partial=allow_partial,
        )
        if not rows:
            return {"action": "idle"}
        candidate = rows[0]
        provider_ids = {
            str(row.get("provider_readiness_id") or "")
            for row in rows
            if str(row.get("provider_readiness_id") or "")
        }
        if len(provider_ids) > 1:
            raise LearningCatalogActivationError(
                "formal release has duplicate Provider readiness jobs"
            )
        candidate_manifest = self.decode_json(candidate.get("feature_manifest_json"))
        if not provider_ids and isinstance(candidate_manifest, Mapping) and (
            "professionalCreation" in candidate_manifest
            or "research" in candidate_manifest
        ):
            self._bind_formal_artifact_validation_rows(
                conn,
                rows=rows,
                now=int(now),
            )
            return {"action": "complete"}
        existing_state = str(candidate.get("provider_state") or "")
        if provider_ids and (
            str(candidate.get("provider_build_item_id") or "")
            != str(candidate["build_item_id"])
            or any(
                str(row.get("provider_readiness_id") or "")
                != next(iter(provider_ids))
                for row in rows
            )
        ):
            raise LearningCatalogActivationError(
                "formal Provider readiness witness is not canonical"
            )
        if existing_state in {"failed", "ambiguous"}:
            return {"action": "idle"}
        if existing_state == "auto_validated":
            self._bind_formal_provider_readiness_rows(
                conn,
                rows=rows,
                witness=candidate,
                provider_receipt_hash=str(
                    candidate.get("provider_receipt_hash") or ""
                ),
                validated_at=int(
                    candidate.get("provider_terminal_at") or now
                ),
                now=int(now),
            )
            return {"action": "complete"}
        if existing_state == "processing":
            request_id = str(candidate.get("provider_request_id") or "")
            if not request_id:
                raise LearningCatalogActivationError(
                    "formal Provider observation identity is incomplete"
                )
            return {"action": "observe", "requestId": request_id}
        if existing_state or provider_ids:
            raise LearningCatalogActivationError(
                "formal Provider readiness state is unsupported"
            )
        if candidate.get("probe_finalized_at") is None:
            return {
                "action": "route_probe",
                "runtimeClassroomId": str(candidate["runtime_classroom_id"]),
            }
        evidence = self._formal_provider_evidence(candidate)
        request_sha256 = hashlib.sha256(
            self.encode_json(evidence).encode("utf-8")
        ).hexdigest()
        digest = hashlib.sha256(
            (
                self.FORMAL_PROVIDER_REQUEST_POLICY_VERSION
                + "|"
                + str(candidate["build_item_id"])
                + "|"
                + str(candidate["audio_terminal_receipt_hash"])
                + "|"
                + str(evidence["routeSession"]["receiptSha256"])
            ).encode("utf-8")
        ).hexdigest()
        request_id = f"formal-provider-ready:{digest[:48]}"
        evidence["requestId"] = request_id
        request_sha256 = hashlib.sha256(
            self.encode_json(evidence).encode("utf-8")
        ).hexdigest()
        readiness_id = f"formal_provider_readiness_{digest[:40]}"
        claim_token = f"formal-provider-claim:{digest[:48]}"
        conn.execute(
            """
            INSERT INTO learning_openmaic_provider_readiness_jobs(
              id, request_id, request_sha256, build_item_id, release_id,
              grade_code, target_fingerprint, runtime_classroom_id,
              runtime_request_id, upstream_classroom_id,
              classroom_content_sha256, audio_job_terminal_receipt_hash,
              validation_scene_order, validation_tts_request_id,
              validation_audio_sha256,
              validation_audio_machine_receipt_hash,
              conversation_probe_id, route_session_contract_version,
              route_session_receipt_hash, route_session_provider_call,
              route_session_status, route_session_completed_at,
              provider_contract_version, expected_provider_call_count,
              provider_attempted_count, provider_passed_count, state,
              claim_token, claim_deadline_at, heartbeat_at, started_at,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, 0, 'passed', ?, ?, 5, 0, 0, 'processing', ?, ?, ?, ?, ?, ?)
            """,
            (
                readiness_id,
                request_id,
                request_sha256,
                candidate["build_item_id"],
                release_id,
                grade_code,
                target_fingerprint,
                candidate["runtime_classroom_id"],
                candidate["runtime_request_id"],
                candidate["upstream_classroom_id"],
                candidate["classroom_content_sha256"],
                candidate["audio_terminal_receipt_hash"],
                int(candidate["validation_scene_order"]),
                candidate["validation_tts_request_id"],
                candidate["validation_audio_sha256"],
                candidate["validation_machine_receipt_hash"],
                candidate["conversation_probe_id"],
                "mira.openmaic.conversation-proof.v1",
                evidence["routeSession"]["receiptSha256"],
                int(candidate["probe_finalized_at"]),
                "mira.openmaic.formal-provider-readiness.v2",
                claim_token,
                int(now) + 180_000,
                int(now),
                int(now),
                int(now),
                int(now),
            ),
        )
        return {"action": "start", "evidence": evidence}

    def persist_formal_provider_readiness(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        response: Mapping[str, object],
        now: int,
        expected_stage: str = "validating",
        allow_partial: bool = False,
    ) -> None:
        """Persist one sanitized release canary and bind it to all 30 items."""

        rows = self._lock_formal_validation_rows(
            conn,
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=publisher_plan_id,
            publisher_lease_token=publisher_lease_token,
            expected_stage=expected_stage,
            now=now,
            allow_partial=allow_partial,
        )
        if not rows:
            raise LearningCatalogActivationError(
                "formal Provider readiness witness is not ready"
            )

        request_id = str(response.get("requestId") or "")
        job = conn.execute(
            "SELECT provider.*, item.build_job_id AS authority_build_id "
            "FROM learning_openmaic_provider_readiness_jobs AS provider "
            "JOIN learning_catalog_build_items AS item "
            "ON item.id = provider.build_item_id "
            "WHERE provider.request_id = ? LIMIT 1 FOR UPDATE",
            (request_id,),
        ).fetchone()
        if job is None:
            raise LearningCatalogActivationError(
                "formal Provider readiness reservation is missing"
            )
        witness = rows[0]
        immutable_exact = bool(
            str(job.get("authority_build_id") or "") == build_id
            and str(job.get("release_id") or "") == release_id
            and str(job.get("grade_code") or "") == grade_code
            and str(job.get("target_fingerprint") or "") == target_fingerprint
            and str(response.get("releaseId") or "") == release_id
            and str(response.get("gradeCode") or "") == grade_code
            and str(response.get("targetFingerprint") or "")
            == target_fingerprint
            and str(job.get("build_item_id") or "")
            == str(response.get("buildItemId") or "")
            and str(job.get("runtime_classroom_id") or "")
            == str(response.get("runtimeClassroomId") or "")
            and str(job.get("runtime_request_id") or "")
            == str(response.get("runtimeRequestId") or "")
            and str(job.get("upstream_classroom_id") or "")
            == str(response.get("upstreamClassroomId") or "")
            and str(job.get("request_sha256") or "")
            == str(response.get("requestSha256") or "")
            and str(job.get("classroom_content_sha256") or "")
            == str(response.get("classroomContentSha256") or "")
            and str(job.get("audio_job_terminal_receipt_hash") or "")
            == str(response.get("audioJobTerminalReceiptSha256") or "")
            and str(job.get("build_item_id") or "")
            == str(witness.get("build_item_id") or "")
            and str(job.get("runtime_classroom_id") or "")
            == str(witness.get("runtime_classroom_id") or "")
            and str(job.get("classroom_content_sha256") or "")
            == str(witness.get("classroom_content_sha256") or "")
            and str(job.get("audio_job_terminal_receipt_hash") or "")
            == str(witness.get("audio_terminal_receipt_hash") or "")
        )
        validation = response.get("validation")
        route = response.get("routeSessionProof")
        if not (
            immutable_exact
            and isinstance(validation, Mapping)
            and isinstance(route, Mapping)
            and int(validation.get("sceneOrder") or 0)
            == int(job["validation_scene_order"])
            and str(validation.get("ttsRequestId") or "")
            == str(job["validation_tts_request_id"])
            and str(validation.get("audioSha256") or "")
            == str(job["validation_audio_sha256"])
            and str(validation.get("machineReceiptSha256") or "")
            == str(job["validation_audio_machine_receipt_hash"])
            and str(route.get("conversationProbeId") or "")
            == str(job["conversation_probe_id"])
            and str(route.get("receiptSha256") or "")
            == str(job["route_session_receipt_hash"])
            and route.get("providerCall") is False
        ):
            raise LearningCatalogActivationError(
                "formal Provider readiness response identity drifted"
            )
        state = str(response.get("status") or "")
        if state not in {"running", "auto_validated", "failed", "ambiguous"}:
            raise LearningCatalogActivationError(
                "formal Provider readiness response state is invalid"
            )
        calls = response.get("calls")
        attempted = int(response.get("providerAttemptedCount") or 0)
        passed = int(response.get("providerPassedCount") or 0)
        if (
            not isinstance(calls, list)
            or len(calls) != attempted
            or attempted < int(job.get("provider_attempted_count") or 0)
            or passed < int(job.get("provider_passed_count") or 0)
        ):
            raise LearningCatalogActivationError(
                "formal Provider readiness call ledger is incomplete"
            )
        for raw_call in calls:
            if not isinstance(raw_call, Mapping):
                raise LearningCatalogActivationError(
                    "formal Provider readiness call receipt is invalid"
                )
            ordinal = int(raw_call.get("callOrdinal") or 0)
            existing = conn.execute(
                "SELECT * FROM learning_openmaic_provider_readiness_call_receipts "
                "WHERE readiness_id = ? AND call_ordinal = ? LIMIT 1 FOR UPDATE",
                (job["id"], ordinal),
            ).fetchone()
            attempted_at = (
                int(existing["attempted_at"])
                if existing is not None
                else int(now)
            )
            completed_at = (
                int(existing["completed_at"])
                if existing is not None
                and existing.get("completed_at") is not None
                and str(existing.get("state") or "")
                == str(raw_call.get("state") or "")
                else int(now)
                if raw_call.get("completedAt") is not None
                else None
            )
            values = (
                job["id"],
                job["provider_contract_version"],
                ordinal,
                raw_call.get("kind"),
                raw_call.get("subject"),
                raw_call.get("providerId"),
                raw_call.get("modelId"),
                raw_call.get("voiceId"),
                raw_call.get("languageCode"),
                0,
                1,
                raw_call.get("requestSha256"),
                raw_call.get("responseSha256"),
                raw_call.get("state"),
                attempted_at,
                completed_at,
                raw_call.get("safeErrorCode"),
                int(job["created_at"]),
                int(now),
            )
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO learning_openmaic_provider_readiness_call_receipts(
                      readiness_id, provider_contract_version, call_ordinal,
                      kind, subject, provider_id, model_id, voice_id,
                      language_code, fallback_used, provider_call,
                      request_sha256, response_sha256, state, attempted_at,
                      completed_at, safe_error_code, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
            else:
                expected_identity = tuple(values[index] for index in range(1, 12))
                actual_identity = (
                    existing["provider_contract_version"],
                    int(existing["call_ordinal"]),
                    existing["kind"],
                    existing.get("subject"),
                    existing["provider_id"],
                    existing["model_id"],
                    existing.get("voice_id"),
                    existing.get("language_code"),
                    int(existing["fallback_used"]),
                    int(existing["provider_call"]),
                    existing["request_sha256"],
                )
                old_state = str(existing.get("state") or "")
                new_state = str(raw_call.get("state") or "")
                if actual_identity != expected_identity or not (
                    old_state == new_state
                    or old_state == "attempted"
                    and new_state in {"passed", "failed", "ambiguous"}
                ):
                    raise LearningCatalogActivationError(
                        "formal Provider call receipt replay conflict"
                    )
                if old_state == new_state:
                    terminal_exact = bool(
                        old_state == "attempted"
                        or (
                            str(existing.get("response_sha256") or "")
                            == str(raw_call.get("responseSha256") or "")
                            and str(existing.get("safe_error_code") or "")
                            == str(raw_call.get("safeErrorCode") or "")
                        )
                    )
                    if not terminal_exact:
                        raise LearningCatalogActivationError(
                            "formal Provider call receipt replay conflict"
                        )
                else:
                    conn.execute(
                        """
                        UPDATE learning_openmaic_provider_readiness_call_receipts
                        SET response_sha256 = ?, state = ?, completed_at = ?,
                          safe_error_code = ?, updated_at = ?
                        WHERE readiness_id = ? AND call_ordinal = ?
                          AND state = 'attempted'
                        """,
                        (
                            raw_call.get("responseSha256"),
                            new_state,
                            int(now),
                            raw_call.get("safeErrorCode"),
                            int(now),
                            job["id"],
                            ordinal,
                        ),
                    )
        terminal = state != "running"
        provider_hash = response.get("providerReceiptSha256") if terminal else None
        safe_error = (
            str(response.get("safeErrorCode") or "formal_provider_readiness_failed")
            if state in {"failed", "ambiguous"}
            else None
        )
        db_state = "processing" if state == "running" else state
        if str(job.get("state") or "") in {"auto_validated", "failed", "ambiguous"}:
            if not (
                str(job["state"]) == db_state
                and int(job["provider_attempted_count"]) == attempted
                and int(job["provider_passed_count"]) == passed
                and str(job.get("provider_receipt_hash") or "")
                == str(provider_hash or "")
            ):
                raise LearningCatalogActivationError(
                    "formal Provider terminal receipt replay conflict"
                )
        else:
            conn.execute(
                """
                UPDATE learning_openmaic_provider_readiness_jobs
                SET provider_attempted_count = ?, provider_passed_count = ?,
                  provider_receipt_hash = ?, state = ?,
                  claim_token = ?, claim_deadline_at = ?, heartbeat_at = ?,
                  safe_error_code = ?, terminal_at = ?, updated_at = ?
                WHERE id = ? AND state = 'processing'
                """,
                (
                    attempted,
                    passed,
                    provider_hash,
                    db_state,
                    None if terminal else job.get("claim_token"),
                    None if terminal else job.get("claim_deadline_at"),
                    None if terminal else int(now),
                    safe_error,
                    int(now) if terminal else None,
                    int(now),
                    job["id"],
                ),
            )
        if state == "auto_validated":
            self._bind_formal_provider_readiness_rows(
                conn,
                rows=rows,
                witness=witness,
                provider_receipt_hash=str(provider_hash),
                validated_at=int(job.get("terminal_at") or now),
                now=int(now),
            )

    def _bind_formal_provider_readiness_rows(
        self,
        conn: DatabaseConnection,
        *,
        rows: Sequence[Mapping[str, object]],
        witness: Mapping[str, object],
        provider_receipt_hash: str,
        validated_at: int,
        now: int,
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", provider_receipt_hash) is None:
            raise LearningCatalogActivationError(
                "formal Provider receipt is incomplete"
            )
        for row in rows:
            provider_binding_hash = self.formal_provider_item_binding_sha256(
                row,
                witness=witness,
                provider_receipt_hash=provider_receipt_hash,
            )
            receipt = self.record_classroom_item_evidence(
                conn,
                build_item_id=str(row["build_item_id"]),
                evidence_kind="conversation_provider",
                outcome="passed",
                receipt_hash=provider_binding_hash,
                completed_at=int(validated_at),
                now=int(now),
            )
            self.mark_classroom_auto_validated(
                conn,
                build_item_id=str(row["build_item_id"]),
                validation_contract_version=self.FORMAL_PUBLICATION_CONTRACT_VERSION,
                receipt_hash=self.formal_item_auto_validation_sha256(
                    receipt,
                    provider_receipt_hash=provider_receipt_hash,
                    provider_binding_hash=provider_binding_hash,
                ),
                validated_at=int(validated_at),
                now=int(now),
            )

    def _bind_formal_artifact_validation_rows(
        self,
        conn: DatabaseConnection,
        *,
        rows: Sequence[Mapping[str, object]],
        now: int,
    ) -> None:
        """Publish from exact generation/audio receipts with zero extra calls."""

        for row in rows:
            manifest = self.decode_json(row.get("feature_manifest_json"))
            if not isinstance(manifest, Mapping):
                raise LearningCatalogActivationError(
                    "formal artifact manifest is incomplete"
                )
            receipt_hash = self.formal_artifact_execution_sha256(row, manifest)
            evidence_status = str(row.get("conversation_provider_status") or "")
            if evidence_status == "pending":
                receipt = self.record_classroom_item_evidence(
                    conn,
                    build_item_id=str(row["build_item_id"]),
                    evidence_kind="conversation_provider",
                    outcome="passed",
                    receipt_hash=receipt_hash,
                    completed_at=int(now),
                    now=int(now),
                )
                validated_at = int(now)
            elif (
                evidence_status == "passed"
                and str(row.get("conversation_provider_receipt_hash") or "")
                == receipt_hash
            ):
                receipt = row
                validated_at = int(
                    row.get("conversation_provider_completed_at") or now
                )
            else:
                raise LearningCatalogActivationError(
                    "formal artifact evidence is already terminal"
                )
            if int(receipt.get("auto_validated") or 0) == 1:
                if not (
                    str(receipt.get("auto_validation_contract_version") or "")
                    == self.FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION
                    and str(receipt.get("auto_validation_receipt_hash") or "")
                    == receipt_hash
                ):
                    raise LearningCatalogActivationError(
                        "formal artifact validation is already terminal"
                    )
                continue
            self.mark_classroom_auto_validated(
                conn,
                build_item_id=str(row["build_item_id"]),
                validation_contract_version=(
                    self.FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION
                ),
                receipt_hash=receipt_hash,
                validated_at=validated_at,
                now=int(now),
            )

    def formal_validation_counts(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
    ) -> dict[str, int]:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
              SUM(CASE WHEN receipt.conversation_provider_status = 'passed'
                AND receipt.auto_validated = 1
                AND (
                  receipt.auto_validation_contract_version = ?
                  OR (
                    provider.state = 'auto_validated'
                    AND provider.provider_attempted_count = 5
                    AND provider.provider_passed_count = 5
                    AND provider.provider_receipt_hash IS NOT NULL
                    AND provider.route_session_provider_call = 0
                    AND provider.route_session_status = 'passed'
                  )
                ) THEN 1 ELSE 0 END) AS ready,
              SUM(CASE WHEN provider.state = 'failed'
                OR receipt.conversation_provider_status = 'failed'
                THEN 1 ELSE 0 END) AS failed,
              SUM(CASE WHEN provider.state = 'ambiguous'
                THEN 1 ELSE 0 END) AS ambiguous
            FROM learning_catalog_build_items AS item
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id
             AND receipt.release_id = item.release_id
             AND receipt.grade_code = item.grade_code
             AND receipt.target_fingerprint = ?
            JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = item.id
             AND audio.release_id = item.release_id
             AND audio.target_fingerprint = ?
             AND audio.state = 'auto_validated'
            LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
              ON provider.release_id = item.release_id
             AND provider.grade_code = item.grade_code
             AND provider.target_fingerprint = ?
            WHERE item.build_job_id = ? AND item.release_id = ?
              AND item.grade_code = ?
            """,
            (
                self.FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION,
                target_fingerprint,
                target_fingerprint,
                target_fingerprint,
                build_id,
                release_id,
                grade_code,
            ),
        ).fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "ready": int(row.get("ready") or 0),
            "failed": int(row.get("failed") or 0),
            "ambiguous": int(row.get("ambiguous") or 0),
        }

    def _lock_formal_validation_rows(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        expected_stage: str,
        now: int,
        allow_partial: bool = False,
    ) -> list[DatabaseRow]:
        plan = conn.execute(
            "SELECT * FROM learning_curriculum_preparation_plans "
            "WHERE id = ? LIMIT 1 FOR UPDATE",
            (publisher_plan_id,),
        ).fetchone()
        if not (
            plan is not None
            and str(plan.get("status") or "") == "running"
            and str(plan.get("stage") or "") == expected_stage
            and str(plan.get("lease_token") or "") == publisher_lease_token
            and int(plan.get("lease_expires_at") or 0) > int(now)
            and str(plan.get("grade_code") or "") == grade_code
            and str(plan.get("catalog_build_id") or "") == build_id
            and str(plan.get("catalog_release_id") or "") == release_id
            and str(plan.get("target_fingerprint") or "") == target_fingerprint
        ):
            raise LearningCatalogActivationError(
                "formal validation publisher lease is stale"
            )
        build_hint = self.get_build(conn, build_id=build_id)
        if (
            build_hint is None
            or str(build_hint.get("release_id") or "") != release_id
        ):
            raise LearningCatalogActivationError(
                "formal validation build authority is incomplete"
            )
        release = self.get_release(conn, release_id=release_id, for_update=True)
        build = self.get_build(conn, build_id=build_id, for_update=True)
        items = self.list_build_items(conn, build_id=build_id, for_update=True)
        items_complete = all(
            str(item.get("release_id") or "") == release_id
            and str(item.get("grade_code") or "") == grade_code
            and str(item.get("content_phase") or "") == "course_ready"
            and str(item.get("content_gate_status") or "") == "passed"
            and bool(str(item.get("course_id") or ""))
            and bool(str(item.get("course_version") or ""))
            for item in items
        )
        items_progressive = all(
            str(item.get("release_id") or "") == release_id
            and str(item.get("grade_code") or "") == grade_code
            and str(item.get("status") or "")
            in ({"pending", "processing", "course_ready", "failed"}
                if plan.get("library_target_fingerprint") else {"pending", "processing", "course_ready"})
            for item in items
        )
        if not (
            build is not None
            and release is not None
            and str(build.get("release_id") or "") == release_id
            and str(build.get("execution_mode") or "") == "content_only"
            and str(build.get("stage_ceiling") or "") == "content_ready"
            and preparation_target_fingerprint(
                self.decode_json(build.get("target_spec_json"))
            )
            == target_fingerprint
            and len(items) == formal_target_course_count(grade_code)
            and (items_progressive if allow_partial else items_complete)
        ):
            raise LearningCatalogActivationError(
                "formal validation build authority is incomplete"
            )
        item_ids = [str(item["id"]) for item in items]
        markers = ", ".join("?" for _ in item_ids)
        rows = list(
            conn.execute(
                f"""
                SELECT item.id AS build_item_id, item.release_id,
                  item.grade_code, item.subject, item.skill_id,
                  item.curriculum_version, item.boundary_version,
                  item.variant_ordinal, item.course_id, item.course_version,
                  course.status AS course_status,
                  course.quality_status AS course_quality_status,
                  course.retired_at AS course_retired_at,
                  runtime.id AS runtime_classroom_id,
                  runtime.request_id AS runtime_request_id,
                  runtime.upstream_job_id,
                  runtime.upstream_classroom_id,
                  runtime.feature_manifest_json,
                  runtime.status AS runtime_status,
                  runtime.course_id AS runtime_course_id,
                  runtime.course_version AS runtime_course_version,
                  runtime.package_id AS runtime_package_id,
                  runtime.package_version AS runtime_package_version,
                  package.status AS package_status,
                  package.retired_at AS package_retired_at,
                  runtime.candidate_build_item_id,
                  runtime.candidate_release_id,
                  runtime.candidate_grade_code,
                  runtime.candidate_target_fingerprint,
                  runtime.candidate_binding_contract_version,
                  receipt.target_fingerprint AS receipt_target_fingerprint,
                  receipt.binding_contract_version,
                  receipt.runtime_classroom_id AS receipt_runtime_classroom_id,
                  receipt.course_id AS receipt_course_id,
                  receipt.course_version AS receipt_course_version,
                  receipt.package_id AS receipt_package_id,
                  receipt.package_version AS receipt_package_version,
                  receipt.classroom_status, receipt.tts_status,
                  receipt.classroom_receipt_hash,
                  receipt.tts_receipt_hash,
                  receipt.asr_roundtrip_status,
                  receipt.asr_roundtrip_receipt_hash,
                  receipt.conversation_provider_status,
                  receipt.conversation_provider_receipt_hash,
                  receipt.auto_validated, receipt.approved,
                  receipt.auto_validation_contract_version,
                  receipt.auto_validation_receipt_hash,
                  receipt.publication_status,
                  receipt.publication_receipt_hash,
                  receipt.published_at AS receipt_published_at,
                  audio.state AS audio_state,
                  audio.release_id AS audio_release_id,
                  audio.grade_code AS audio_grade_code,
                  audio.target_fingerprint AS audio_target_fingerprint,
                  audio.runtime_classroom_id AS audio_runtime_classroom_id,
                  audio.course_id AS audio_course_id,
                  audio.course_version AS audio_course_version,
                  audio.package_id AS audio_package_id,
                  audio.package_version AS audio_package_version,
                  audio.classroom_content_sha256,
                  audio.terminal_receipt_hash AS audio_terminal_receipt_hash,
                  audio.expected_segment_count,
                  audio.tts_attempted_count, audio.tts_completed_count,
                  audio.audio_validated_count, audio.asr_attempted_count,
                  audio.asr_passed_count,
                  segment.scene_order AS validation_scene_order,
                  segment.tts_request_id AS validation_tts_request_id,
                  segment.runtime_audio_sha256 AS validation_audio_sha256,
                  segment.machine_receipt_hash AS validation_machine_receipt_hash,
                  segment.state AS validation_segment_state,
                  probe.id AS conversation_probe_id,
                  probe.runtime_classroom_id AS probe_runtime_classroom_id,
                  probe.upstream_classroom_id AS probe_upstream_classroom_id,
                  probe.candidate_kind AS probe_candidate_kind,
                  probe.chat_receipt_json AS probe_chat_receipt_json,
                  probe.transcription_receipt_json AS probe_transcription_receipt_json,
                  probe.finalized_at AS probe_finalized_at,
                  provider.id AS provider_readiness_id,
                  provider.request_id AS provider_request_id,
                  provider.build_item_id AS provider_build_item_id,
                  provider.state AS provider_state,
                  provider.release_id AS provider_release_id,
                  provider.grade_code AS provider_grade_code,
                  provider.target_fingerprint AS provider_target_fingerprint,
                  provider.runtime_classroom_id AS provider_runtime_classroom_id,
                  provider.classroom_content_sha256 AS provider_classroom_sha256,
                  provider.audio_job_terminal_receipt_hash
                    AS provider_audio_receipt_hash,
                  provider.expected_provider_call_count,
                  provider.provider_attempted_count,
                  provider.provider_passed_count,
                  provider.provider_receipt_hash,
                  provider.terminal_at AS provider_terminal_at,
                  provider.route_session_provider_call,
                  provider.route_session_status,
                  (SELECT COUNT(*)
                     FROM learning_openmaic_provider_readiness_call_receipts
                       AS provider_call
                    WHERE provider_call.readiness_id = provider.id
                      AND provider_call.state = 'passed'
                      AND provider_call.provider_call = 1)
                    AS provider_passed_call_count
                FROM learning_catalog_build_items AS item
                JOIN learning_courses AS course
                  ON course.id = item.course_id
                 AND course.version = item.course_version
                JOIN learning_curriculum_classroom_item_receipts AS receipt
                  ON receipt.build_item_id = item.id
                JOIN learning_openmaic_runtime_classrooms AS runtime
                  ON runtime.id = receipt.runtime_classroom_id
                JOIN learning_lesson_packages AS package
                  ON package.id = runtime.package_id
                 AND package.version = runtime.package_version
                JOIN learning_formal_qwen_audio_jobs AS audio
                  ON audio.build_item_id = item.id
                JOIN learning_formal_qwen_audio_segment_receipts AS segment
                  ON segment.build_item_id = item.id AND segment.scene_order = 0
                LEFT JOIN learning_openmaic_conversation_probes AS probe
                  ON probe.runtime_classroom_id = runtime.id
                LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
                  ON provider.release_id = item.release_id
                 AND provider.grade_code = item.grade_code
                 AND provider.target_fingerprint = receipt.target_fingerprint
                WHERE item.id IN ({markers})
                ORDER BY item.subject_ordinal, item.boundary_ordinal,
                  item.variant_ordinal, item.id
                FOR UPDATE
                """,
                item_ids,
            ).fetchall()
        )
        if allow_partial and plan.get("library_target_fingerprint"):
            # Each independent item still passes every identity/hash check below.
            # Incomplete or rejected siblings are not publication candidates.
            rows = [row for row in rows if row.get("audio_state") == "auto_validated"
                    and row.get("runtime_status") == "ready"]
        if not allow_partial and len(rows) != formal_target_course_count(grade_code):
            raise LearningCatalogActivationError(
                "formal validation evidence does not cover thirty items"
            )
        if allow_partial and len(rows) > formal_target_course_count(grade_code):
            raise LearningCatalogActivationError(
                "formal validation evidence cardinality is invalid"
            )
        if (
            allow_partial
            and not plan.get("library_target_fingerprint")
            and rows
            and str(rows[0].get("build_item_id") or "")
            != str(items[0].get("id") or "")
        ):
            return []
        for row in rows:
            manifest = self.decode_json(row.get("feature_manifest_json"))
            expected_segment_count = int(
                row.get("expected_segment_count") or 0
            )
            formal_evidence = (
                manifest.get("formalEvidence")
                if isinstance(manifest, Mapping)
                else None
            )
            scene_count = (
                manifest.get("sceneCount")
                if isinstance(manifest, Mapping)
                else None
            )
            speech_action_count = (
                formal_evidence.get("speechActionCount")
                if isinstance(formal_evidence, Mapping)
                else None
            )
            exact = bool(
                str(row.get("runtime_status") or "") == "ready"
                and str(row.get("candidate_build_item_id") or "")
                == str(row["build_item_id"])
                and str(row.get("candidate_release_id") or "") == release_id
                and str(row.get("candidate_grade_code") or "") == grade_code
                and str(row.get("candidate_target_fingerprint") or "")
                == target_fingerprint
                and str(row.get("candidate_binding_contract_version") or "")
                == self.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION
                and str(row.get("receipt_target_fingerprint") or "")
                == target_fingerprint
                and str(row.get("binding_contract_version") or "")
                == self.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION
                and str(row.get("receipt_runtime_classroom_id") or "")
                == str(row["runtime_classroom_id"])
                and str(row.get("runtime_course_id") or "")
                == str(row.get("receipt_course_id") or "")
                == str(row.get("course_id") or "")
                and str(row.get("runtime_course_version") or "")
                == str(row.get("receipt_course_version") or "")
                == str(row.get("course_version") or "")
                and str(row.get("runtime_package_id") or "")
                == str(row.get("receipt_package_id") or "")
                and int(row.get("runtime_package_version") or 0)
                == int(row.get("receipt_package_version") or 0) > 0
                and str(row.get("course_status") or "")
                in {"validated", "published"}
                and str(row.get("course_quality_status") or "")
                in {"auto_validated", "released"}
                and row.get("course_retired_at") is None
                and str(row.get("package_status") or "")
                in {"candidate", "published"}
                and row.get("package_retired_at") is None
                and str(row.get("classroom_status") or "") == "passed"
                and str(row.get("classroom_receipt_hash") or "")
                == self.formal_classroom_receipt_sha256(row, manifest)
                and str(row.get("tts_status") or "") == "passed"
                and str(row.get("asr_roundtrip_status") or "") == "passed"
                and str(row.get("audio_state") or "") == "auto_validated"
                and str(row.get("audio_release_id") or "") == release_id
                and str(row.get("audio_grade_code") or "") == grade_code
                and str(row.get("audio_target_fingerprint") or "")
                == target_fingerprint
                and str(row.get("audio_runtime_classroom_id") or "")
                == str(row["runtime_classroom_id"])
                and str(row.get("audio_course_id") or "")
                == str(row.get("course_id") or "")
                and str(row.get("audio_course_version") or "")
                == str(row.get("course_version") or "")
                and str(row.get("audio_package_id") or "")
                == str(row.get("runtime_package_id") or "")
                and int(row.get("audio_package_version") or 0)
                == int(row.get("runtime_package_version") or 0)
                and 1 <= expected_segment_count <= 240
                and type(scene_count) is int
                and 1 <= scene_count <= 60
                and type(speech_action_count) is int
                and scene_count
                <= speech_action_count
                <= min(240, scene_count * 20)
                and expected_segment_count == speech_action_count
                and all(
                    int(row.get(field) or 0) == expected_segment_count
                    for field in (
                        "tts_attempted_count",
                        "tts_completed_count",
                        "audio_validated_count",
                        "asr_attempted_count",
                        "asr_passed_count",
                    )
                )
                and int(row.get("validation_scene_order") or 0) == 0
                and str(row.get("validation_segment_state") or "")
                == "auto_validated"
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(row.get("classroom_content_sha256") or ""),
                )
                is not None
                and str(manifest.get("classroomContentSha256") or "")
                == str(row.get("classroom_content_sha256") or "")
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(row.get("audio_terminal_receipt_hash") or ""),
                )
                is not None
            )
            if not exact:
                raise LearningCatalogActivationError(
                    "formal validation evidence identity is not exact"
                )
        return rows

    @staticmethod
    def formal_classroom_receipt_sha256(
        row: Mapping[str, object], manifest: Mapping[str, object]
    ) -> str:
        """Rebuild Task13's 057 classroom receipt, including teacher evidence."""

        generation_contract = manifest.get("generationContract")
        generation_contract = (
            generation_contract
            if isinstance(generation_contract, Mapping)
            else {}
        )
        source_hash = (
            manifest.get("sourceCourseContentSha256")
            if "sourceCourseContentSha256" in manifest
            else generation_contract.get("sourceCourseContentSha256")
        )
        brief_hash = (
            manifest.get("teachingBriefSha256")
            if "teachingBriefSha256" in manifest
            else generation_contract.get("teachingBriefSha256")
        )
        professional_creation = manifest.get("professionalCreation")
        professional_creation = (
            professional_creation
            if isinstance(professional_creation, Mapping)
            else {}
        )
        research = manifest.get("research")
        research = research if isinstance(research, Mapping) else {}
        payload = {
            "schemaVersion": (
                "mira.learning.formal-classroom-evidence.v2-professional"
            ),
            "buildItemId": str(row.get("build_item_id") or ""),
            "runtimeClassroomId": str(row.get("runtime_classroom_id") or ""),
            "runtimeRequestId": str(row.get("runtime_request_id") or ""),
            "upstreamJobId": str(row.get("upstream_job_id") or ""),
            "upstreamClassroomId": str(
                row.get("upstream_classroom_id") or ""
            ),
            "targetFingerprint": str(
                row.get("audio_target_fingerprint") or ""
            ),
            "sourceCourseContentSha256": source_hash,
            "teachingBriefSha256": brief_hash,
            "classroomContentSha256": manifest.get(
                "classroomContentSha256"
            ),
            "formalRuntimeContract": manifest.get("formalRuntimeContract"),
            "professionalCreationReceiptSha256": (
                professional_creation.get("receiptSha256")
            ),
            "researchReceiptSha256": research.get("receiptSha256"),
            "evidence": manifest.get("formalEvidence"),
        }
        return hashlib.sha256(
            LearningCatalogRepository.encode_json(payload).encode("utf-8")
        ).hexdigest()

    @classmethod
    def formal_artifact_execution_sha256(
        cls,
        row: Mapping[str, object],
        manifest: Mapping[str, object],
    ) -> str:
        """Bind publication to providers already used for the real artifact."""

        professional = manifest.get("professionalCreation")
        research = manifest.get("research")
        formal_evidence = manifest.get("formalEvidence")
        generation_contract = manifest.get("generationContract")
        if not all(
            isinstance(value, Mapping)
            for value in (
                professional,
                research,
                formal_evidence,
                generation_contract,
            )
        ):
            raise LearningCatalogActivationError(
                "formal artifact generation evidence is incomplete"
            )
        assert isinstance(professional, Mapping)
        assert isinstance(research, Mapping)
        assert isinstance(formal_evidence, Mapping)
        assert isinstance(generation_contract, Mapping)
        try:
            validate_media_manifest(manifest)
        except (ValueError, KeyError, TypeError) as exc:
            raise LearningCatalogActivationError("formal artifact media evidence is invalid") from exc
        professional_hash = str(professional.get("receiptSha256") or "")
        research_hash = str(research.get("receiptSha256") or "")
        source_hash = str(manifest.get("sourceCourseContentSha256") or "")
        brief_hash = str(manifest.get("teachingBriefSha256") or "")
        scene_count = manifest.get("sceneCount")
        speech_count = formal_evidence.get("speechActionCount")
        expected_segments = int(row.get("expected_segment_count") or 0)
        identity_exact = bool(
            professional.get("status") == "succeeded"
            and research.get("status") == "succeeded"
            and professional.get("webSearchEnabled") is True
            and int(research.get("searchCount") or 0) >= 1
            and int(research.get("citationCount") or 0) >= 1
            and bool(str(research.get("providerId") or ""))
            and str(professional.get("buildItemId") or "")
            == str(row.get("build_item_id") or "")
            and str(research.get("buildItemId") or "")
            == str(row.get("build_item_id") or "")
            and str(professional.get("classroomId") or "")
            == str(row.get("upstream_classroom_id") or "")
            and str(research.get("classroomId") or "")
            == str(row.get("upstream_classroom_id") or "")
            and str(professional.get("runtimeRequestId") or "")
            == str(row.get("runtime_request_id") or "")
            and str(research.get("runtimeRequestId") or "")
            == str(row.get("runtime_request_id") or "")
            and str(professional.get("sessionId") or "")
            == str(research.get("sessionId") or "")
            and re.fullmatch(r"[0-9a-f]{64}", professional_hash) is not None
            and re.fullmatch(r"[0-9a-f]{64}", research_hash) is not None
            and re.fullmatch(r"[0-9a-f]{64}", source_hash) is not None
            and re.fullmatch(r"[0-9a-f]{64}", brief_hash) is not None
            and type(scene_count) is int
            and 1 <= int(scene_count) <= 60
            and type(speech_count) is int
            and int(scene_count) <= int(speech_count) <= int(scene_count) * 20
            and expected_segments == int(speech_count)
            and all(
                int(row.get(field) or 0) == expected_segments
                for field in (
                    "tts_attempted_count",
                    "tts_completed_count",
                    "audio_validated_count",
                    "asr_attempted_count",
                    "asr_passed_count",
                )
            )
            and str(row.get("audio_state") or "") == "auto_validated"
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(row.get("audio_terminal_receipt_hash") or ""),
            )
            is not None
        )
        if not identity_exact:
            raise LearningCatalogActivationError(
                "formal artifact generation evidence identity is not exact"
            )
        payload = {
            "schemaVersion": cls.FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION,
            "buildItemId": str(row.get("build_item_id") or ""),
            "releaseId": str(row.get("release_id") or ""),
            "gradeCode": str(row.get("grade_code") or ""),
            "targetFingerprint": str(row.get("receipt_target_fingerprint") or ""),
            "runtimeClassroomId": str(row.get("runtime_classroom_id") or ""),
            "runtimeRequestId": str(row.get("runtime_request_id") or ""),
            "upstreamClassroomId": str(row.get("upstream_classroom_id") or ""),
            "classroomReceiptSha256": str(row.get("classroom_receipt_hash") or ""),
            "classroomContentSha256": str(row.get("classroom_content_sha256") or ""),
            "professionalCreationReceiptSha256": professional_hash,
            "researchReceiptSha256": research_hash,
            "audioJobTerminalReceiptSha256": str(
                row.get("audio_terminal_receipt_hash") or ""
            ),
            "sceneCount": int(scene_count),
            "speechActionCount": int(speech_count),
            "sourceCourseContentSha256": source_hash,
            "teachingBriefSha256": brief_hash,
            "additionalProviderCalls": 0,
        }
        return hashlib.sha256(cls.encode_json(payload).encode("utf-8")).hexdigest()

    @staticmethod
    def formal_provider_item_binding_sha256(
        row: Mapping[str, object],
        *,
        witness: Mapping[str, object],
        provider_receipt_hash: str,
    ) -> str:
        """Bind one release canary to one immutable classroom item."""

        payload = {
            "schemaVersion": "mira.learning.formal-provider-release-binding.v1",
            "releaseId": str(row.get("release_id") or ""),
            "gradeCode": str(row.get("grade_code") or ""),
            "targetFingerprint": str(
                row.get("receipt_target_fingerprint")
                or row.get("target_fingerprint")
                or ""
            ),
            "providerWitness": {
                "buildItemId": str(witness.get("build_item_id") or ""),
                "runtimeClassroomId": str(
                    witness.get("runtime_classroom_id") or ""
                ),
                "classroomContentSha256": str(
                    witness.get("classroom_content_sha256") or ""
                ),
                "audioReceiptSha256": str(
                    witness.get("audio_terminal_receipt_hash") or ""
                ),
                "providerReceiptSha256": str(provider_receipt_hash or ""),
            },
            "item": {
                "buildItemId": str(row.get("build_item_id") or ""),
                "runtimeClassroomId": str(
                    row.get("runtime_classroom_id") or ""
                ),
                "classroomReceiptSha256": str(
                    row.get("classroom_receipt_hash") or ""
                ),
                "ttsReceiptSha256": str(row.get("tts_receipt_hash") or ""),
                "asrReceiptSha256": str(
                    row.get("asr_roundtrip_receipt_hash") or ""
                ),
                "audioReceiptSha256": str(
                    row.get("audio_terminal_receipt_hash") or ""
                ),
            },
        }
        return hashlib.sha256(
            LearningCatalogRepository.encode_json(payload).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def formal_item_auto_validation_sha256(
        row: Mapping[str, object],
        *,
        provider_receipt_hash: str,
        provider_binding_hash: str,
    ) -> str:
        payload = {
            "schemaVersion": (
                LearningCatalogRepository.FORMAL_PUBLICATION_CONTRACT_VERSION
            ),
            "buildItemId": str(row.get("build_item_id") or ""),
            "classroomReceiptSha256": str(
                row.get("classroom_receipt_hash") or ""
            ),
            "ttsReceiptSha256": str(row.get("tts_receipt_hash") or ""),
            "asrReceiptSha256": str(
                row.get("asr_roundtrip_receipt_hash") or ""
            ),
            "providerReceiptSha256": str(provider_receipt_hash or ""),
            "providerBindingReceiptSha256": str(provider_binding_hash or ""),
        }
        return hashlib.sha256(
            LearningCatalogRepository.encode_json(payload).encode("utf-8")
        ).hexdigest()

    def _formal_provider_evidence(
        self, row: Mapping[str, object]
    ) -> dict[str, object]:
        chat = self.decode_json(row.get("probe_chat_receipt_json"))
        transcription = self.decode_json(
            row.get("probe_transcription_receipt_json")
        )
        proofs = (chat.get("proof"), transcription.get("proof"))
        if not (
            str(row.get("conversation_probe_id") or "")
            and str(row.get("probe_runtime_classroom_id") or "")
            == str(row.get("runtime_classroom_id") or "")
            and str(row.get("probe_upstream_classroom_id") or "")
            == str(row.get("upstream_classroom_id") or "")
            and str(row.get("probe_candidate_kind") or "") == "release"
            and row.get("probe_finalized_at") is not None
            and chat.get("verified") is True
            and transcription.get("verified") is True
            and all(
                isinstance(proof, Mapping)
                and proof.get("schemaVersion")
                == "mira.openmaic.conversation-proof.v1"
                and proof.get("classroomId")
                == row.get("upstream_classroom_id")
                and proof.get("providerCall") is False
                for proof in proofs
            )
        ):
            raise LearningCatalogActivationError(
                "formal route/session proof is not exact"
            )
        route_payload = {
            "schemaVersion": "mira.openmaic.conversation-proof.v1",
            "conversationProbeId": str(row["conversation_probe_id"]),
            "runtimeClassroomId": str(row["runtime_classroom_id"]),
            "upstreamClassroomId": str(row["upstream_classroom_id"]),
            "chat": chat,
            "transcription": transcription,
            "providerCall": False,
            "completedAt": int(row["probe_finalized_at"]),
        }
        route_hash = hashlib.sha256(
            self.encode_json(route_payload).encode("utf-8")
        ).hexdigest()
        return {
            "schemaVersion": "mira.openmaic.formal-provider-readiness.v2",
            "requestId": "",
            "buildItemId": str(row["build_item_id"]),
            "releaseId": str(row["release_id"]),
            "gradeCode": str(row["grade_code"]),
            "targetFingerprint": str(row["audio_target_fingerprint"]),
            "runtimeClassroomId": str(row["runtime_classroom_id"]),
            "runtimeRequestId": str(row["runtime_request_id"]),
            "upstreamClassroomId": str(row["upstream_classroom_id"]),
            "classroomContentSha256": str(row["classroom_content_sha256"]),
            "audioJobTerminalReceiptSha256": str(
                row["audio_terminal_receipt_hash"]
            ),
            "validation": {
                "subject": str(row["subject"]),
                "sceneOrder": int(row["validation_scene_order"]),
                "ttsRequestId": str(row["validation_tts_request_id"]),
                "audioSha256": str(row["validation_audio_sha256"]),
                "machineReceiptSha256": str(
                    row["validation_machine_receipt_hash"]
                ),
            },
            "routeSession": {
                "schemaVersion": "mira.openmaic.conversation-proof.v1",
                "conversationProbeId": str(row["conversation_probe_id"]),
                "receiptSha256": route_hash,
                "providerCall": False,
            },
        }

    def lock_formal_publication_authority(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        publication_request_id: str,
        now: int,
    ) -> dict[str, object]:
        """Lock pointer then every immutable item/evidence row for publication."""

        conn.execute(
            """
            INSERT IGNORE INTO learning_curriculum_grade_release_pointers(
              grade_code, pointer_revision, updated_at
            ) VALUES (?, 0, ?)
            """,
            (grade_code, int(now)),
        )
        pointer_slot = conn.execute(
            "SELECT * FROM learning_curriculum_grade_release_pointers "
            "WHERE grade_code = ? LIMIT 1 FOR UPDATE",
            (grade_code,),
        ).fetchone()
        if pointer_slot is None:
            raise LearningCatalogActivationError(
                "formal grade publication slot is unavailable"
            )
        published_at = int(now)
        current_history = None
        if int(pointer_slot.get("pointer_revision") or 0) >= 1:
            current_history = conn.execute(
                "SELECT * FROM learning_curriculum_grade_release_history "
                "WHERE id = ? LIMIT 1 FOR UPDATE",
                (pointer_slot.get("history_id"),),
            ).fetchone()
            if current_history is None:
                raise LearningCatalogActivationError(
                    "formal grade publication history is missing"
                )
        plan_hint = conn.execute(
            "SELECT catalog_release_id FROM learning_curriculum_preparation_plans "
            "WHERE id = ? LIMIT 1",
            (publisher_plan_id,),
        ).fetchone()
        release_id = str((plan_hint or {}).get("catalog_release_id") or "")
        if not release_id:
            raise LearningCatalogActivationError(
                "formal publication release identity is missing"
            )
        same_candidate = bool(
            current_history is not None
            and str(pointer_slot.get("release_id") or "") == release_id
            and str(current_history.get("release_id") or "") == release_id
            and str(pointer_slot.get("target_fingerprint") or "")
            == target_fingerprint
        )
        if same_candidate:
            if str(current_history.get("publication_request_id") or "") != str(
                publication_request_id
            ):
                raise LearningCatalogActivationError(
                    "formal publication candidate already has another request"
                )
            published_at = int(current_history["activated_at"])
        rows = self._lock_formal_validation_rows(
            conn,
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=publisher_plan_id,
            publisher_lease_token=publisher_lease_token,
            expected_stage="publishing",
            now=now,
        )
        return self._formal_publication_authority_from_rows(
            rows,
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            published_at=published_at,
        )

    def lock_progressive_formal_publication_authority(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        publisher_plan_id: str,
        publisher_lease_token: str,
        publisher_stage: str,
        now: int,
    ) -> dict[str, object]:
        """Lock all currently auto-validated candidate items without a pointer."""

        rows = self._lock_formal_validation_rows(
            conn,
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            publisher_plan_id=publisher_plan_id,
            publisher_lease_token=publisher_lease_token,
            expected_stage=publisher_stage,
            now=now,
            allow_partial=True,
        )
        if not rows:
            return {
                "gradeCode": grade_code,
                "buildId": build_id,
                "releaseId": release_id,
                "targetFingerprint": target_fingerprint,
                "itemCount": 0,
                "readyItemCount": 0,
                "publishedAt": int(now),
                "items": [],
            }
        return self._formal_publication_authority_from_rows(
            rows,
            grade_code=grade_code,
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            published_at=int(now),
        )

    def _formal_publication_authority_from_rows(
        self,
        rows: Sequence[Mapping[str, object]],
        *,
        grade_code: str,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
        published_at: int,
    ) -> dict[str, object]:
        if not rows:
            raise LearningCatalogActivationError(
                "formal publication contains no validated item"
            )
        item_receipts: list[dict[str, object]] = []
        witness = rows[0]
        provider_ids = {
            str(row.get("provider_readiness_id") or "")
            for row in rows
            if str(row.get("provider_readiness_id") or "")
        }
        artifact_mode = not provider_ids and all(
            str(row.get("auto_validation_contract_version") or "")
            == self.FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION
            for row in rows
        )
        if not artifact_mode and len(provider_ids) != 1:
            raise LearningCatalogActivationError(
                "formal publication requires one release Provider receipt"
            )
        for row in rows:
            if artifact_mode:
                manifest = self.decode_json(row.get("feature_manifest_json"))
                if not isinstance(manifest, Mapping):
                    raise LearningCatalogActivationError(
                        "formal artifact publication manifest is incomplete"
                    )
                evidence_hash = self.formal_artifact_execution_sha256(row, manifest)
                evidence_exact = bool(
                    str(row.get("conversation_provider_status") or "") == "passed"
                    and str(row.get("conversation_provider_receipt_hash") or "")
                    == evidence_hash
                    and int(row.get("auto_validated") or 0) == 1
                    and str(row.get("auto_validation_contract_version") or "")
                    == self.FORMAL_ARTIFACT_PUBLICATION_CONTRACT_VERSION
                    and str(row.get("auto_validation_receipt_hash") or "")
                    == evidence_hash
                    and int(row.get("approved") or 0) == 0
                    and str(row.get("publication_status") or "")
                    in {"pending", "published"}
                )
            else:
                provider_hash = str(row.get("provider_receipt_hash") or "")
                provider_binding_hash = self.formal_provider_item_binding_sha256(
                    row,
                    witness=witness,
                    provider_receipt_hash=provider_hash,
                )
                evidence_hash = provider_binding_hash
                evidence_exact = bool(
                    str(row.get("provider_state") or "") == "auto_validated"
                    and str(row.get("provider_readiness_id") or "")
                    == next(iter(provider_ids))
                    and str(row.get("provider_build_item_id") or "")
                    == str(witness.get("build_item_id") or "")
                    and str(row.get("provider_release_id") or "") == release_id
                    and str(row.get("provider_grade_code") or "") == grade_code
                    and str(row.get("provider_target_fingerprint") or "")
                    == target_fingerprint
                    and str(row.get("provider_runtime_classroom_id") or "")
                    == str(witness.get("runtime_classroom_id") or "")
                    and str(row.get("provider_classroom_sha256") or "")
                    == str(witness.get("classroom_content_sha256") or "")
                    and str(row.get("provider_audio_receipt_hash") or "")
                    == str(witness.get("audio_terminal_receipt_hash") or "")
                    and int(row.get("expected_provider_call_count") or 0) == 5
                    and int(row.get("provider_attempted_count") or 0) == 5
                    and int(row.get("provider_passed_count") or 0) == 5
                    and int(row.get("provider_passed_call_count") or 0) == 5
                    and row.get("route_session_provider_call") is not None
                    and int(row.get("route_session_provider_call") or 0) == 0
                    and str(row.get("route_session_status") or "") == "passed"
                    and re.fullmatch(r"[0-9a-f]{64}", provider_hash) is not None
                    and str(row.get("conversation_provider_status") or "")
                    == "passed"
                    and str(row.get("conversation_provider_receipt_hash") or "")
                    == provider_binding_hash
                    and int(row.get("auto_validated") or 0) == 1
                    and str(row.get("auto_validation_contract_version") or "")
                    == self.FORMAL_PUBLICATION_CONTRACT_VERSION
                    and str(row.get("auto_validation_receipt_hash") or "")
                    == self.formal_item_auto_validation_sha256(
                        row,
                        provider_receipt_hash=provider_hash,
                        provider_binding_hash=provider_binding_hash,
                    )
                    and int(row.get("approved") or 0) == 0
                    and str(row.get("publication_status") or "")
                    in {"pending", "published"}
                )
            if not evidence_exact:
                raise LearningCatalogActivationError(
                    "formal publication evidence authority is incomplete"
                )
            item_payload = {
                "schemaVersion": self.FORMAL_PUBLICATION_CONTRACT_VERSION,
                "gradeCode": grade_code,
                "buildId": build_id,
                "releaseId": release_id,
                "targetFingerprint": target_fingerprint,
                "buildItemId": str(row["build_item_id"]),
                "runtimeClassroomId": str(row["runtime_classroom_id"]),
                "course": {
                    "id": str(row["course_id"]),
                    "version": str(row["course_version"]),
                },
                "package": {
                    "id": str(row["runtime_package_id"]),
                    "version": int(row["runtime_package_version"]),
                },
                "classroomContentSha256": str(
                    row["classroom_content_sha256"]
                ),
                "audioReceiptSha256": str(
                    row["audio_terminal_receipt_hash"]
                ),
                **(
                    {"generationEvidenceReceiptSha256": evidence_hash}
                    if artifact_mode
                    else {
                        "providerReceiptSha256": provider_hash,
                        "providerBindingReceiptSha256": evidence_hash,
                    }
                ),
            }
            item_receipts.append(
                {
                    **dict(row),
                    "publicationReceiptSha256": hashlib.sha256(
                        self.encode_json(item_payload).encode("utf-8")
                    ).hexdigest(),
                }
            )
        aggregate = {
            "schemaVersion": self.FORMAL_PUBLICATION_CONTRACT_VERSION,
            "gradeCode": grade_code,
            "buildId": build_id,
            "releaseId": release_id,
            "targetFingerprint": target_fingerprint,
            "items": [
                {
                    "buildItemId": str(item["build_item_id"]),
                    "receiptSha256": str(item["publicationReceiptSha256"]),
                }
                for item in item_receipts
            ],
        }
        return {
            "gradeCode": grade_code,
            "buildId": build_id,
            "releaseId": release_id,
            "targetFingerprint": target_fingerprint,
            "itemCount": len(item_receipts),
            "readyItemCount": len(item_receipts),
            "publicationReceiptSha256": hashlib.sha256(
                self.encode_json(aggregate).encode("utf-8")
            ).hexdigest(),
            "publishedAt": published_at,
            "items": item_receipts,
        }

    def publish_formal_grade_release(
        self,
        conn: DatabaseConnection,
        *,
        authority: Mapping[str, object],
        publication_request_id: str,
        published_at: int,
        finalize_release: bool = True,
    ) -> None:
        """Publish exact items and optionally finalize the aggregate release."""

        items = authority.get("items")
        release_id = str(authority.get("releaseId") or "")
        if not (
            isinstance(items, list)
            and (
                len(items) == formal_target_course_count(authority)
                if finalize_release
                else 1 <= len(items) <= formal_target_course_count(authority)
            )
            and release_id
            and publication_request_id
            and int(published_at) > 0
        ):
            raise LearningCatalogActivationError(
                "formal publication authority is incomplete"
            )
        for item in items:
            if not isinstance(item, Mapping):
                raise LearningCatalogActivationError(
                    "formal publication item authority is invalid"
                )
            self.record_classroom_publication_evidence(
                conn,
                build_item_id=str(item["build_item_id"]),
                outcome="published",
                receipt_hash=str(item["publicationReceiptSha256"]),
                completed_at=int(
                    item.get("receipt_published_at") or published_at
                ),
                now=int(published_at),
            )
            conn.execute(
                """
                UPDATE learning_lesson_packages
                SET status = 'published',
                  published_at = COALESCE(published_at, ?), updated_at = ?
                WHERE id = ? AND version = ? AND retired_at IS NULL
                  AND status IN ('candidate', 'published')
                """,
                (
                    int(published_at),
                    int(published_at),
                    item["runtime_package_id"],
                    int(item["runtime_package_version"]),
                ),
            )
            package = conn.execute(
                "SELECT course_id, course_version, status, published_at, "
                "retired_at FROM learning_lesson_packages "
                "WHERE id = ? AND version = ? LIMIT 1 FOR UPDATE",
                (
                    item["runtime_package_id"],
                    int(item["runtime_package_version"]),
                ),
            ).fetchone()
            if not (
                package is not None
                and str(package.get("course_id") or "")
                == str(item["course_id"])
                and str(package.get("course_version") or "")
                == str(item["course_version"])
                and str(package.get("status") or "") == "published"
                and package.get("published_at") is not None
                and package.get("retired_at") is None
            ):
                raise LearningCatalogActivationError(
                    "formal lesson package could not be published"
                )
            binding = conn.execute(
                "SELECT * FROM learning_course_lesson_package_bindings "
                "WHERE course_id = ? AND course_version = ? "
                "LIMIT 1 FOR UPDATE",
                (item["course_id"], item["course_version"]),
            ).fetchone()
            if binding is None:
                conn.execute(
                    "INSERT INTO learning_course_lesson_package_bindings("
                    "course_id, course_version, package_id, package_version, "
                    "updated_at) VALUES (?, ?, ?, ?, ?)",
                    (
                        item["course_id"],
                        item["course_version"],
                        item["runtime_package_id"],
                        int(item["runtime_package_version"]),
                        int(published_at),
                    ),
                )
            elif not (
                str(binding.get("package_id") or "")
                == str(item["runtime_package_id"])
                and int(binding.get("package_version") or 0)
                == int(item["runtime_package_version"])
            ):
                raise LearningCatalogActivationError(
                    "formal lesson package binding conflicts"
                )
            conn.execute(
                """
                UPDATE learning_classroom_generation_jobs
                SET status = 'published',
                  started_at = COALESCE(started_at, ?),
                  completed_at = COALESCE(completed_at, ?), updated_at = ?
                WHERE package_id = ? AND package_version = ?
                  AND generator = 'formal_package_authority'
                  AND status IN ('staged', 'published')
                """,
                (
                    int(published_at),
                    int(published_at),
                    int(published_at),
                    item["runtime_package_id"],
                    int(item["runtime_package_version"]),
                ),
            )
            source_job = conn.execute(
                "SELECT status, completed_at FROM "
                "learning_classroom_generation_jobs WHERE package_id = ? "
                "AND package_version = ? AND generator = "
                "'formal_package_authority' LIMIT 1 FOR UPDATE",
                (
                    item["runtime_package_id"],
                    int(item["runtime_package_version"]),
                ),
            ).fetchone()
            if not (
                source_job is not None
                and str(source_job.get("status") or "") == "published"
                and source_job.get("completed_at") is not None
            ):
                raise LearningCatalogActivationError(
                    "formal package generation receipt could not be published"
                )
            existing = conn.execute(
                """
                SELECT * FROM learning_catalog_release_items
                WHERE release_id = ? AND course_id = ? AND course_version = ?
                  AND variant_ordinal = ? LIMIT 1 FOR UPDATE
                """,
                (
                    release_id,
                    item["course_id"],
                    item["course_version"],
                    int(item["variant_ordinal"]),
                ),
            ).fetchone()
            exact_release_item = bool(
                existing is not None
                and str(existing.get("grade_code") or "")
                == str(item["grade_code"])
                and str(existing.get("subject") or "") == str(item["subject"])
                and str(existing.get("skill_id") or "") == str(item["skill_id"])
                and str(existing.get("curriculum_version") or "")
                == str(item["curriculum_version"])
                and str(existing.get("boundary_version") or "")
                == str(item["boundary_version"])
                and str(existing.get("package_id") or "")
                == str(item["runtime_package_id"])
                and int(existing.get("package_version") or 0)
                == int(item["runtime_package_version"])
                and str(existing.get("status") or "") == "published"
                and str(existing.get("quality_status") or "") == "ready"
                and existing.get("retired_at") is None
            )
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO learning_catalog_release_items(
                      release_id, course_id, course_version, grade_code,
                      subject, skill_id, curriculum_version, boundary_version,
                      variant_ordinal, package_id, package_version, status,
                      quality_status, published_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'published',
                      'ready', ?, ?, ?)
                    """,
                    (
                        release_id,
                        item["course_id"],
                        item["course_version"],
                        item["grade_code"],
                        item["subject"],
                        item["skill_id"],
                        item["curriculum_version"],
                        item["boundary_version"],
                        int(item["variant_ordinal"]),
                        item["runtime_package_id"],
                        int(item["runtime_package_version"]),
                        int(published_at),
                        int(published_at),
                        int(published_at),
                    ),
                )
            elif not exact_release_item:
                raise LearningCatalogActivationError(
                    "formal release item replay conflict"
                )
            conn.execute(
                """
                UPDATE learning_courses
                SET status = 'published', quality_status = 'released',
                  published_at = COALESCE(published_at, ?), updated_at = ?
                WHERE id = ? AND version = ? AND retired_at IS NULL
                  AND ((status = 'validated' AND quality_status = 'auto_validated')
                    OR (status = 'published' AND quality_status = 'released'))
                """,
                (
                    int(published_at),
                    int(published_at),
                    item["course_id"],
                    item["course_version"],
                ),
            )
            course = conn.execute(
                "SELECT status, quality_status, retired_at "
                "FROM learning_courses WHERE id = ? AND version = ? "
                "LIMIT 1 FOR UPDATE",
                (item["course_id"], item["course_version"]),
            ).fetchone()
            if not (
                course is not None
                and str(course.get("status") or "") == "published"
                and str(course.get("quality_status") or "") == "released"
                and course.get("retired_at") is None
            ):
                raise LearningCatalogActivationError(
                    "formal course could not be published"
                )
        if not finalize_release:
            counted = conn.execute(
                "SELECT COUNT(*) AS value FROM learning_catalog_release_items "
                "WHERE release_id = ? AND status = 'published' "
                "AND quality_status = 'ready' AND retired_at IS NULL",
                (release_id,),
            ).fetchone()
            ready_item_count = int((counted or {}).get("value") or 0)
            if not 1 <= ready_item_count <= formal_target_course_count(authority):
                raise LearningCatalogActivationError(
                    "progressive formal publication count is invalid"
                )
            updated = conn.execute(
                "UPDATE learning_catalog_releases SET ready_item_count = ?, "
                "updated_at = ? WHERE id = ? AND status = 'draft' "
                "AND quality_status = 'building' AND activated_at IS NULL "
                "AND retired_at IS NULL AND ready_item_count <= ?",
                (
                    ready_item_count,
                    int(published_at),
                    release_id,
                    ready_item_count,
                ),
            )
            if updated.rowcount != 1:
                raise LearningCatalogActivationError(
                    "progressive formal release count could not be advanced"
                )
            return
        conn.execute(
            """
            UPDATE learning_catalog_releases
            SET status = 'published', quality_status = 'ready',
              ready_item_count = ?,
              activated_at = COALESCE(activated_at, ?),
              retired_at = NULL, updated_at = ?
            WHERE id = ? AND status IN ('draft', 'published')
              AND quality_status IN ('building', 'ready')
            """,
            (formal_target_course_count(authority), int(published_at), int(published_at), release_id),
        )
        release = self.get_release(conn, release_id=release_id, for_update=True)
        if not (
            release is not None
            and str(release.get("status") or "") == "published"
            and str(release.get("quality_status") or "") == "ready"
            and int(release.get("ready_item_count") or 0) == formal_target_course_count(authority)
            and release.get("retired_at") is None
        ):
            raise LearningCatalogActivationError(
                "formal grade release could not be published"
            )

    def get_active_grade_release_pointer(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT pointer.*, history.activation_source,
              history.publication_request_id,
              history.publication_receipt_hash
            FROM learning_curriculum_grade_release_pointers AS pointer
            LEFT JOIN learning_curriculum_grade_release_history AS history
              ON history.id = pointer.history_id
            WHERE pointer.grade_code = ? AND pointer.pointer_revision >= 1
            LIMIT 1
            """
            + lock,
            (grade_code,),
        ).fetchone()

    def list_grade_release_history(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        for_update: bool = False,
    ) -> list[DatabaseRow]:
        lock = " FOR UPDATE" if for_update else ""
        return list(
            conn.execute(
                """
                SELECT * FROM learning_curriculum_grade_release_history
                WHERE grade_code = ?
                ORDER BY pointer_revision, activated_at, id
                """
                + lock,
                (grade_code,),
            ).fetchall()
        )

    def activate_grade_release_pointer(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        build_id: str,
        target_fingerprint: str,
        contract_version: str,
        publication_request_id: str,
        publication_receipt_hash: str,
        activated_at: int,
    ) -> DatabaseRow:
        """Atomically append history and CAS one grade pointer only.

        This method intentionally does not call the legacy curriculum-wide
        ``activate_release`` path and does not retire another grade.
        """

        if contract_version != self.FORMAL_PUBLICATION_CONTRACT_VERSION:
            raise ValueError("formal publication contract is unsupported")
        for value, label in (
            (target_fingerprint, "target fingerprint"),
            (publication_receipt_hash, "publication receipt hash"),
        ):
            if re.fullmatch(r"[0-9a-f]{64}", str(value or "")) is None:
                raise ValueError(f"{label} is invalid")
        if not publication_request_id or len(publication_request_id) > 128:
            raise ValueError("publication request id is invalid")
        if int(activated_at) <= 0:
            raise ValueError("publication timestamp is invalid")
        conn.execute(
            """
            INSERT IGNORE INTO learning_curriculum_grade_release_pointers(
              grade_code, pointer_revision, updated_at
            ) VALUES (?, 0, ?)
            """,
            (grade_code, int(activated_at)),
        )
        slot = conn.execute(
            """
            SELECT * FROM learning_curriculum_grade_release_pointers
            WHERE grade_code = ? LIMIT 1 FOR UPDATE
            """,
            (grade_code,),
        ).fetchone()
        if slot is None:
            raise RuntimeError("grade publication slot was not created")
        current_history = None
        if int(slot["pointer_revision"]) >= 1:
            current_history = conn.execute(
                """
                SELECT * FROM learning_curriculum_grade_release_history
                WHERE id = ? AND grade_code = ? AND pointer_revision = ?
                  AND release_id = ? AND target_fingerprint = ?
                  AND contract_version = ? AND activated_at = ?
                  AND superseded_at IS NULL
                LIMIT 1 FOR UPDATE
                """,
                (
                    slot.get("history_id"),
                    grade_code,
                    int(slot["pointer_revision"]),
                    slot.get("release_id"),
                    slot.get("target_fingerprint"),
                    slot.get("contract_version"),
                    slot.get("activated_at"),
                ),
            ).fetchone()
            if current_history is None:
                raise LearningCatalogActivationError(
                    "the current grade publication history is not exact"
                )
        build = self.get_build(conn, build_id=build_id, for_update=True)
        if build is None:
            raise LearningCatalogActivationError("catalog build was not found")
        release = self.get_release(
            conn, release_id=str(build["release_id"]), for_update=True
        )
        items = self.list_build_items(conn, build_id=build_id, for_update=True)
        if release is None or not items:
            raise LearningCatalogActivationError("grade candidate is incomplete")
        if (
            str(build.get("execution_mode") or "") != "content_only"
            or str(build.get("stage_ceiling") or "") != "content_ready"
            or any(str(item.get("grade_code") or "") != grade_code for item in items)
            or any(str(item.get("release_id") or "") != str(release["id"]) for item in items)
        ):
            raise LearningCatalogActivationError(
                "catalog build is outside the grade publication authority"
            )
        receipts = self.list_classroom_item_receipts(
            conn, release_id=str(release["id"]), for_update=True
        )
        if len(receipts) != len(items):
            raise LearningCatalogActivationError(
                "formal publication does not cover every build item"
            )
        item_ids = {str(item["id"]) for item in items}
        for receipt in receipts:
            exact = (
                str(receipt.get("build_item_id") or "") in item_ids
                and str(receipt.get("grade_code") or "") == grade_code
                and str(receipt.get("release_id") or "") == str(release["id"])
                and str(receipt.get("binding_contract_version") or "")
                == self.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION
                and str(receipt.get("target_fingerprint") or "")
                == target_fingerprint
                and str(receipt.get("publication_status") or "") == "published"
                and int(receipt.get("auto_validated") or 0) == 1
                and str(receipt.get("runtime_build_item_id") or "")
                == str(receipt.get("build_item_id") or "")
                and str(receipt.get("runtime_release_id") or "")
                == str(release["id"])
                and str(receipt.get("runtime_grade_code") or "") == grade_code
                and str(receipt.get("runtime_target_fingerprint") or "")
                == target_fingerprint
                and str(receipt.get("runtime_contract_version") or "")
                == self.CLASSROOM_RECEIPT_BINDING_CONTRACT_VERSION
                and str(receipt.get("runtime_course_id") or "")
                == str(receipt.get("course_id") or "")
                and str(receipt.get("runtime_course_version") or "")
                == str(receipt.get("course_version") or "")
                and str(receipt.get("runtime_package_id") or "")
                == str(receipt.get("package_id") or "")
                and int(receipt.get("runtime_package_version") or 0)
                == int(receipt.get("package_version") or 0)
                and str(receipt.get("runtime_status") or "") == "ready"
            )
            if not exact:
                raise LearningCatalogActivationError(
                    "formal publication receipt identity is not exact"
                )
        existing_request = conn.execute(
            """
            SELECT * FROM learning_curriculum_grade_release_history
            WHERE publication_request_id = ? LIMIT 1 FOR UPDATE
            """,
            (publication_request_id,),
        ).fetchone()
        if existing_request is not None:
            expected = (
                grade_code,
                str(release["id"]),
                target_fingerprint,
                contract_version,
                publication_receipt_hash,
            )
            actual = (
                str(existing_request["grade_code"]),
                str(existing_request["release_id"]),
                str(existing_request["target_fingerprint"]),
                str(existing_request["contract_version"]),
                str(existing_request["publication_receipt_hash"]),
            )
            pointer = self.get_active_grade_release_pointer(
                conn, grade_code=grade_code, for_update=True
            )
            if actual == expected and pointer is not None and str(
                pointer["history_id"]
            ) == str(existing_request["id"]):
                return pointer
            raise LearningCatalogActivationError(
                "publication request was reused for different authority"
            )
        if int(slot["pointer_revision"]) >= 1 and (
            str(slot.get("release_id") or "") == str(release["id"])
        ):
            raise LearningCatalogActivationError(
                "the grade pointer already represents this candidate"
            )
        revision = int(slot["pointer_revision"]) + 1
        history_digest = hashlib.sha256(
            f"mira.learning.grade-publication:{publication_request_id}".encode(
                "utf-8"
            )
        ).hexdigest()[:40]
        history_id = f"grade_release_history_{history_digest}"
        previous_history_id = slot.get("history_id") if revision > 1 else None
        previous_release_id = slot.get("release_id") if revision > 1 else None
        if previous_history_id is not None:
            superseded = conn.execute(
                """
                UPDATE learning_curriculum_grade_release_history
                SET superseded_at = ?
                WHERE id = ? AND grade_code = ? AND pointer_revision = ?
                  AND release_id = ? AND target_fingerprint = ?
                  AND contract_version = ? AND activated_at = ?
                  AND superseded_at IS NULL
                """,
                (
                    int(activated_at),
                    previous_history_id,
                    grade_code,
                    int(slot["pointer_revision"]),
                    previous_release_id,
                    slot.get("target_fingerprint"),
                    slot.get("contract_version"),
                    slot.get("activated_at"),
                ),
            )
            if superseded.rowcount != 1:
                raise LearningCatalogActivationError(
                    "the current grade history could not be superseded"
                )
        conn.execute(
            """
            INSERT INTO learning_curriculum_grade_release_history(
              id, grade_code, pointer_revision, target_fingerprint,
              contract_version, release_id, previous_history_id,
              previous_release_id, activation_source, publication_request_id,
              publication_receipt_hash, activated_at, superseded_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'formal_publication', ?, ?, ?, NULL, ?)
            """,
            (
                history_id,
                grade_code,
                revision,
                target_fingerprint,
                contract_version,
                release["id"],
                previous_history_id,
                previous_release_id,
                publication_request_id,
                publication_receipt_hash,
                int(activated_at),
                int(activated_at),
            ),
        )
        updated = conn.execute(
            """
            UPDATE learning_curriculum_grade_release_pointers
            SET pointer_revision = ?, target_fingerprint = ?,
              contract_version = ?, release_id = ?, history_id = ?,
              activated_at = ?, updated_at = ?
            WHERE grade_code = ? AND pointer_revision = ?
              AND history_id <=> ? AND release_id <=> ?
            """,
            (
                revision,
                target_fingerprint,
                contract_version,
                release["id"],
                history_id,
                int(activated_at),
                int(activated_at),
                grade_code,
                int(slot["pointer_revision"]),
                slot.get("history_id"),
                slot.get("release_id"),
            ),
        )
        if updated.rowcount != 1:
            raise LearningCatalogActivationError("grade pointer CAS was lost")
        pointer = self.get_active_grade_release_pointer(
            conn, grade_code=grade_code, for_update=True
        )
        if pointer is None:
            raise RuntimeError("grade pointer disappeared after publication")
        return pointer

    @staticmethod
    def _expected_full_item_immutables(
        *,
        build_id: str,
        release_id: str,
        curriculum_version: str,
        targets: Sequence[Mapping[str, Any]],
        variants_per_boundary: int,
    ) -> set[tuple[object, ...]]:
        expected: set[tuple[object, ...]] = set()
        for target in targets:
            for ordinal in range(1, max(1, int(variants_per_boundary)) + 1):
                identity = (
                    f"{build_id}:{target['gradeCode']}:{target['subject']}:"
                    f"{target['skillId']}:{ordinal}"
                )
                item_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                expected.add(
                    (
                        f"catalog_build_item_{item_digest[:24]}",
                        f"catalog_gen_{item_digest[:48]}",
                        build_id,
                        release_id,
                        str(target["gradeCode"]),
                        str(target["subject"]),
                        str(target["skillId"]),
                        curriculum_version,
                        str(target["boundaryVersion"]),
                        ordinal,
                        "full_pipeline",
                        "",
                    )
                )
        return expected

    @staticmethod
    def _full_item_immutable_tuple(row: Mapping[str, Any]) -> tuple[object, ...]:
        return (
            str(row.get("id") or ""),
            str(row.get("generation_request_id") or ""),
            str(row.get("build_job_id") or ""),
            str(row.get("release_id") or ""),
            str(row.get("grade_code") or ""),
            str(row.get("subject") or ""),
            str(row.get("skill_id") or ""),
            str(row.get("curriculum_version") or ""),
            str(row.get("boundary_version") or ""),
            int(row.get("variant_ordinal") or 0),
            str(row.get("execution_mode_snapshot") or ""),
            str(row.get("content_manifest_version_snapshot") or ""),
        )

    @staticmethod
    def _expected_content_item_immutables(
        *,
        build_id: str,
        release_id: str,
        curriculum_version: str,
        content_manifest_version: str,
        course_targets: Sequence[Mapping[str, Any]],
        grade_code: str,
    ) -> list[dict[str, object]]:
        expected: list[dict[str, object]] = []
        for target in course_targets:
            subject = str(target["subject"])
            skill_id = str(target["skillId"])
            variant_ordinal = int(target["variantOrdinal"])
            identity = (
                f"{build_id}:{grade_code}:{subject}:{skill_id}:{variant_ordinal}"
            )
            item_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            expected.append(
                {
                    "id": f"catalog_build_item_{item_digest[:24]}",
                    "generation_request_id": f"catalog_gen_{item_digest[:48]}",
                    "build_job_id": build_id,
                    "release_id": release_id,
                    "grade_code": grade_code,
                    "subject": subject,
                    "skill_id": skill_id,
                    "curriculum_version": curriculum_version,
                    "boundary_version": str(target["boundaryVersion"]),
                    "variant_ordinal": variant_ordinal,
                    "execution_mode_snapshot": "content_only",
                    "content_manifest_version_snapshot": content_manifest_version,
                    "subject_ordinal": int(target["subjectOrdinal"]),
                    "boundary_ordinal": int(target["boundaryOrdinal"]),
                }
            )
        return expected

    @staticmethod
    def _content_item_immutables_match(
        row: Mapping[str, Any],
        expected: Mapping[str, object],
    ) -> bool:
        integer_fields = {
            "variant_ordinal",
            "subject_ordinal",
            "boundary_ordinal",
        }
        for key, value in expected.items():
            actual = row.get(key)
            if key in integer_fields:
                if int(actual or 0) != int(value):
                    return False
            elif str(actual or "") != str(value):
                return False
        return True

    def _progressive_release_items_are_exact(
        self,
        conn: DatabaseConnection,
        *,
        release: Mapping[str, Any],
        build: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        target_fingerprint: str,
    ) -> bool:
        """Authenticate already-published candidate items during content work."""

        release_id = str(release.get("id") or "")
        build_id = str(build.get("id") or "")
        ready_item_count = int(release.get("ready_item_count") or 0)
        if ready_item_count == 0:
            return not self._release_has_catalog_items(
                conn, release_id=release_id
            )
        if (
            not hasattr(conn, "execute")
            or not release_id
            or not build_id
            or not 1 <= ready_item_count <= formal_target_course_count(build)
            or re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is None
        ):
            return False
        build_item_ids = {str(row.get("id") or "") for row in rows}
        published = list(
            conn.execute(
                """
                SELECT release_item.*,
                  item.id AS exact_build_item_id,
                  item.build_job_id AS exact_build_id,
                  item.status AS exact_build_item_status,
                  item.content_phase AS exact_content_phase,
                  item.content_gate_status AS exact_content_gate_status,
                  receipt.release_id AS exact_receipt_release_id,
                  receipt.grade_code AS exact_receipt_grade_code,
                  receipt.target_fingerprint AS exact_receipt_fingerprint,
                  receipt.runtime_classroom_id,
                  receipt.package_id AS exact_receipt_package_id,
                  receipt.package_version AS exact_receipt_package_version,
                  receipt.classroom_status, receipt.tts_status,
                  receipt.asr_roundtrip_status,
                  receipt.conversation_provider_status,
                  receipt.auto_validated,
                  receipt.publication_status AS exact_publication_status,
                  receipt.publication_receipt_hash AS exact_publication_hash,
                  receipt.published_at AS exact_receipt_published_at,
                  runtime.status AS exact_runtime_status,
                  runtime.candidate_build_item_id,
                  runtime.candidate_release_id,
                  runtime.candidate_grade_code,
                  runtime.candidate_target_fingerprint,
                  package.status AS exact_package_status,
                  package.retired_at AS exact_package_retired_at,
                  course.status AS exact_course_status,
                  course.quality_status AS exact_course_quality_status,
                  course.retired_at AS exact_course_retired_at,
                  source_job.status AS exact_source_job_status,
                  source_job.completed_at AS exact_source_job_completed_at
                FROM learning_catalog_release_items AS release_item
                LEFT JOIN learning_catalog_build_items AS item
                  ON item.build_job_id = ?
                 AND item.release_id = release_item.release_id
                 AND item.course_id = release_item.course_id
                 AND item.course_version = release_item.course_version
                 AND item.grade_code = release_item.grade_code
                 AND item.subject = release_item.subject
                 AND item.skill_id = release_item.skill_id
                 AND item.curriculum_version = release_item.curriculum_version
                 AND item.boundary_version = release_item.boundary_version
                 AND item.variant_ordinal = release_item.variant_ordinal
                LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt
                  ON receipt.build_item_id = item.id
                LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
                  ON runtime.id = receipt.runtime_classroom_id
                LEFT JOIN learning_lesson_packages AS package
                  ON package.id = release_item.package_id
                 AND package.version = release_item.package_version
                LEFT JOIN learning_courses AS course
                  ON course.id = release_item.course_id
                 AND course.version = release_item.course_version
                LEFT JOIN learning_classroom_generation_jobs AS source_job
                  ON source_job.package_id = release_item.package_id
                 AND source_job.package_version = release_item.package_version
                 AND source_job.generator = 'formal_package_authority'
                WHERE release_item.release_id = ?
                ORDER BY release_item.subject, release_item.skill_id,
                  release_item.variant_ordinal, release_item.course_id
                """,
                (build_id, release_id),
            ).fetchall()
        )
        return bool(
            len(published) == ready_item_count
            and all(
                str(item.get("exact_build_item_id") or "") in build_item_ids
                and str(item.get("exact_build_id") or "") == build_id
                and str(item.get("exact_build_item_status") or "")
                == "course_ready"
                and str(item.get("exact_content_phase") or "")
                == "course_ready"
                and str(item.get("exact_content_gate_status") or "") == "passed"
                and str(item.get("status") or "") == "published"
                and str(item.get("quality_status") or "") == "ready"
                and item.get("published_at") is not None
                and item.get("retired_at") is None
                and str(item.get("exact_receipt_release_id") or "") == release_id
                and str(item.get("exact_receipt_grade_code") or "")
                == str(item.get("grade_code") or "")
                and str(item.get("exact_receipt_fingerprint") or "")
                == target_fingerprint
                and str(item.get("runtime_classroom_id") or "")
                and str(item.get("candidate_build_item_id") or "")
                == str(item.get("exact_build_item_id") or "")
                and str(item.get("candidate_release_id") or "") == release_id
                and str(item.get("candidate_grade_code") or "")
                == str(item.get("grade_code") or "")
                and str(item.get("candidate_target_fingerprint") or "")
                == target_fingerprint
                and str(item.get("exact_runtime_status") or "") == "ready"
                and str(item.get("exact_receipt_package_id") or "")
                == str(item.get("package_id") or "")
                and int(item.get("exact_receipt_package_version") or 0)
                == int(item.get("package_version") or 0) > 0
                and str(item.get("classroom_status") or "") == "passed"
                and str(item.get("tts_status") or "") == "passed"
                and str(item.get("asr_roundtrip_status") or "") == "passed"
                and str(item.get("conversation_provider_status") or "")
                == "passed"
                and int(item.get("auto_validated") or 0) == 1
                and str(item.get("exact_publication_status") or "")
                == "published"
                and re.fullmatch(
                    r"[0-9a-f]{64}",
                    str(item.get("exact_publication_hash") or ""),
                )
                is not None
                and item.get("exact_receipt_published_at") is not None
                and str(item.get("exact_package_status") or "") == "published"
                and item.get("exact_package_retired_at") is None
                and str(item.get("exact_course_status") or "") == "published"
                and str(item.get("exact_course_quality_status") or "")
                == "released"
                and item.get("exact_course_retired_at") is None
                and str(item.get("exact_source_job_status") or "")
                == "published"
                and item.get("exact_source_job_completed_at") is not None
                for item in published
            )
        )

    @staticmethod
    def _release_has_catalog_items(
        conn: DatabaseConnection,
        *,
        release_id: str,
    ) -> bool:
        return (
            conn.execute(
                """
                SELECT release_id FROM learning_catalog_release_items
                WHERE release_id = ? LIMIT 1 FOR UPDATE
                """,
                (release_id,),
            ).fetchone()
            is not None
        )

    @staticmethod
    def encode_json(payload: Mapping[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def decode_json(value: object) -> dict[str, Any]:
        try:
            decoded = json.loads(str(value or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}

    @staticmethod
    def safe_code(value: object) -> str:
        return re.sub(r"[^a-z0-9_.-]", "_", str(value or "catalog_build_failed").lower())[:128]

    @staticmethod
    def safe_message(value: object) -> str:
        return DynamicLearningCourseRepository.sanitize_error(value)
