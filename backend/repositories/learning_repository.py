from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from contextlib import contextmanager
from typing import Iterator, Sequence

from content.primary_skill_boundaries import boundaries_for
from core.database import Database, DatabaseConnection, DatabaseRow
from repositories.formal_student_runtime_gate import (
    current_formal_runtime_sql,
    current_formal_validation_authority_sql,
)


_TEACHING_FLOW_SQL = """
  AND JSON_VALID({alias}.content_json)
  AND JSON_UNQUOTE(JSON_EXTRACT(
    {alias}.content_json, '$.teachingFlow.schemaVersion'
  )) = 'mira.learning.teaching-flow.v1'
  AND JSON_TYPE(JSON_EXTRACT(
    {alias}.content_json, '$.teachingFlow.teach'
  )) = 'OBJECT'
  AND JSON_TYPE(JSON_EXTRACT(
    {alias}.content_json, '$.teachingFlow.recap'
  )) = 'OBJECT'
  AND JSON_LENGTH(JSON_EXTRACT(
    {alias}.content_json, '$.teachingFlow.guidedQuestionIds'
  )) = 2
  AND JSON_LENGTH(JSON_EXTRACT(
    {alias}.content_json, '$.teachingFlow.independentQuestionIds'
  )) = 2
"""


def _validated_sql_alias(alias: str) -> str:
    if not isinstance(alias, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*", alias
    ):
        raise ValueError("alias must be a SQL identifier")
    return alias


def _student_scope_sql(child_alias: str | None) -> tuple[str, str, str]:
    if child_alias is None:
        return "?", "?", "?"
    child_alias = _validated_sql_alias(child_alias)
    return (
        f"{child_alias}.family_id",
        f"{child_alias}.id",
        f"{child_alias}.grade_selection_revision",
    )


def _student_required_package_assets_sql(*, package_alias: str) -> str:
    """Check the live required assets of the exact selected lesson package."""

    package = _validated_sql_alias(package_alias)
    return f"""
      NOT EXISTS (
        SELECT 1
        FROM learning_lesson_package_assets AS package_asset
        LEFT JOIN learning_media_assets AS asset
          ON asset.id = package_asset.asset_id
        WHERE package_asset.package_id = {package}.id
          AND package_asset.package_version = {package}.version
          AND package_asset.required_asset = 1
          AND (
            asset.id IS NULL
            OR asset.status IS NULL
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
    """


def _student_progressive_slot_exists_sql(
    *, release_item_alias: str, child_alias: str | None = None
) -> str:
    """Return a full-evidence current-plan overlay check for one catalog slot."""

    item = release_item_alias
    family_id, child_id, grade_revision = _student_scope_sql(child_alias)
    return f"""
      EXISTS (
        SELECT 1
        FROM learning_curriculum_preparation_plans AS overlay_plan
        JOIN learning_catalog_release_items AS overlay_item
          ON overlay_item.release_id = overlay_plan.catalog_release_id
         AND overlay_item.grade_code = overlay_plan.grade_code
         AND overlay_item.boundary_version = {item}.boundary_version
         AND overlay_item.variant_ordinal = {item}.variant_ordinal
         AND overlay_item.status = 'published'
         AND overlay_item.quality_status = 'ready'
         AND overlay_item.retired_at IS NULL
        JOIN learning_courses AS overlay_course
          ON overlay_course.id = overlay_item.course_id
         AND overlay_course.version = overlay_item.course_version
         AND overlay_course.grade_code = overlay_item.grade_code
         AND overlay_course.curriculum_version = overlay_item.curriculum_version
         AND overlay_course.boundary_version = overlay_item.boundary_version
         AND overlay_course.status = 'published'
         AND overlay_course.quality_status = 'released'
         AND overlay_course.content_origin = 'openmaic_generated'
         AND overlay_course.retired_at IS NULL
        JOIN learning_course_lesson_package_bindings AS overlay_binding
          ON overlay_binding.course_id = overlay_item.course_id
         AND overlay_binding.course_version = overlay_item.course_version
         AND overlay_binding.package_id = overlay_item.package_id
         AND overlay_binding.package_version = overlay_item.package_version
        JOIN learning_lesson_packages AS overlay_package
          ON overlay_package.id = overlay_binding.package_id
         AND overlay_package.version = overlay_binding.package_version
         AND overlay_package.course_id = overlay_item.course_id
         AND overlay_package.course_version = overlay_item.course_version
         AND overlay_package.status = 'published'
         AND overlay_package.retired_at IS NULL
        JOIN learning_catalog_build_items AS overlay_build_item
          ON overlay_build_item.build_job_id = overlay_plan.catalog_build_id
         AND overlay_build_item.release_id = overlay_item.release_id
         AND overlay_build_item.grade_code = overlay_item.grade_code
         AND overlay_build_item.course_id = overlay_item.course_id
         AND overlay_build_item.course_version = overlay_item.course_version
         AND (
           overlay_build_item.status = 'ready'
           OR (
             overlay_build_item.status = 'course_ready'
             AND overlay_build_item.execution_mode_snapshot = 'content_only'
             AND overlay_build_item.content_phase = 'course_ready'
             AND overlay_build_item.content_gate_status = 'passed'
             AND overlay_build_item.content_gate_passed_at IS NOT NULL
             AND overlay_build_item.content_validation_contract_version
               IS NOT NULL
             AND overlay_build_item.content_validation_contract_version <> ''
             AND overlay_build_item.content_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
           )
         )
        JOIN learning_curriculum_classroom_item_receipts AS overlay_receipt
          ON overlay_receipt.build_item_id = overlay_build_item.id
         AND overlay_receipt.release_id = overlay_item.release_id
         AND overlay_receipt.grade_code = overlay_item.grade_code
         AND overlay_receipt.course_id = overlay_item.course_id
         AND overlay_receipt.course_version = overlay_item.course_version
         AND overlay_receipt.package_id = overlay_package.id
         AND overlay_receipt.package_version = overlay_package.version
         AND overlay_receipt.classroom_status = 'passed'
         AND overlay_receipt.tts_status = 'passed'
         AND overlay_receipt.asr_roundtrip_status = 'passed'
         AND overlay_receipt.conversation_provider_status = 'passed'
         AND overlay_receipt.auto_validated = 1
         AND overlay_receipt.publication_status = 'published'
        JOIN learning_openmaic_runtime_classrooms AS overlay_runtime
          ON overlay_runtime.id = overlay_receipt.runtime_classroom_id
         AND overlay_runtime.candidate_build_item_id = overlay_build_item.id
         AND overlay_runtime.candidate_release_id = overlay_item.release_id
         AND overlay_runtime.candidate_grade_code = overlay_item.grade_code
         AND overlay_runtime.candidate_target_fingerprint =
           overlay_plan.target_fingerprint
         AND overlay_runtime.course_id = overlay_item.course_id
         AND overlay_runtime.course_version = overlay_item.course_version
         AND overlay_runtime.package_id = overlay_package.id
         AND overlay_runtime.package_version = overlay_package.version
         AND overlay_runtime.status = 'ready'
         AND overlay_runtime.upstream_classroom_id IS NOT NULL
         AND overlay_runtime.retired_at IS NULL
         {current_formal_runtime_sql(runtime_alias="overlay_runtime")}
        JOIN learning_formal_qwen_audio_jobs AS overlay_audio
          ON overlay_audio.build_item_id = overlay_build_item.id
         AND overlay_audio.runtime_classroom_id = overlay_runtime.id
         AND overlay_audio.release_id = overlay_item.release_id
         AND overlay_audio.grade_code = overlay_item.grade_code
         AND overlay_audio.target_fingerprint = overlay_plan.target_fingerprint
         AND overlay_audio.course_id = overlay_item.course_id
         AND overlay_audio.course_version = overlay_item.course_version
         AND overlay_audio.package_id = overlay_package.id
         AND overlay_audio.package_version = overlay_package.version
         AND overlay_audio.state = 'auto_validated'
         AND overlay_audio.expected_segment_count BETWEEN 1 AND 240
         AND overlay_audio.tts_attempted_count = overlay_audio.expected_segment_count
         AND overlay_audio.tts_completed_count = overlay_audio.expected_segment_count
         AND overlay_audio.audio_validated_count = overlay_audio.expected_segment_count
         AND overlay_audio.asr_attempted_count = overlay_audio.expected_segment_count
         AND overlay_audio.asr_passed_count = overlay_audio.expected_segment_count
         AND overlay_audio.terminal_receipt_hash IS NOT NULL
        LEFT JOIN learning_openmaic_provider_readiness_jobs AS overlay_provider
          ON overlay_provider.release_id = overlay_item.release_id
         AND overlay_provider.grade_code = overlay_item.grade_code
         AND overlay_provider.target_fingerprint = overlay_plan.target_fingerprint
        WHERE overlay_plan.family_id = {family_id}
          AND overlay_plan.child_id = {child_id}
          AND overlay_plan.grade_selection_revision = {grade_revision}
          {current_formal_validation_authority_sql(
              receipt_alias="overlay_receipt",
              provider_alias="overlay_provider",
          )}
          AND overlay_plan.grade_code = {item}.grade_code
          AND overlay_plan.target_fingerprint =
            overlay_receipt.target_fingerprint
          AND overlay_plan.superseded_at IS NULL
          AND overlay_plan.status IN ('queued', 'running', 'ready', 'failed')
          AND NOT EXISTS (
            SELECT 1
            FROM learning_curriculum_preparation_plans AS newer_overlay_plan
            WHERE newer_overlay_plan.family_id = overlay_plan.family_id
              AND newer_overlay_plan.child_id = overlay_plan.child_id
              AND newer_overlay_plan.grade_selection_revision =
                overlay_plan.grade_selection_revision
              AND newer_overlay_plan.target_fingerprint =
                overlay_plan.target_fingerprint
              AND (
                newer_overlay_plan.retry_ordinal > overlay_plan.retry_ordinal
                OR (
                  newer_overlay_plan.retry_ordinal = overlay_plan.retry_ordinal
                  AND newer_overlay_plan.created_at > overlay_plan.created_at
                )
                OR (
                  newer_overlay_plan.retry_ordinal = overlay_plan.retry_ordinal
                  AND newer_overlay_plan.created_at = overlay_plan.created_at
                  AND newer_overlay_plan.id > overlay_plan.id
                )
              )
          )
      )
    """


def _student_visible_course_sql(
    *,
    course_alias: str = "course",
    child_alias: str | None = None,
    require_available_package_assets: bool = False,
) -> str:
    """Return the exact per-course rolling/active formal visibility gate.

    Each of the two groups of three placeholders binds family id, child id and
    the child's current grade-selection revision. A progressively published
    item is visible only through that exact child plan. The shared grade pointer
    remains a safe fallback for slots not yet replaced by that plan. With a
    child alias, both scopes instead correlate to that current child row.
    Classroom entry flags additionally check this exact package's live assets.
    """

    course = course_alias
    family_id, child_id, grade_revision = _student_scope_sql(child_alias)
    asset_gate = (
        "AND " + _student_required_package_assets_sql(package_alias="student_package")
        if require_available_package_assets
        else ""
    )
    return f"""
      EXISTS (
        SELECT 1
        FROM learning_catalog_release_items AS student_release_item
        JOIN learning_catalog_releases AS student_release
          ON student_release.id = student_release_item.release_id
         AND student_release.retired_at IS NULL
        JOIN learning_course_lesson_package_bindings AS student_binding
          ON student_binding.course_id = student_release_item.course_id
         AND student_binding.course_version = student_release_item.course_version
         AND student_binding.package_id = student_release_item.package_id
         AND student_binding.package_version = student_release_item.package_version
        JOIN learning_lesson_packages AS student_package
          ON student_package.id = student_binding.package_id
         AND student_package.version = student_binding.package_version
         AND student_package.course_id = student_release_item.course_id
         AND student_package.course_version = student_release_item.course_version
         AND student_package.status = 'published'
         AND student_package.retired_at IS NULL
        JOIN learning_catalog_build_items AS student_build_item
          ON student_build_item.release_id = student_release_item.release_id
         AND student_build_item.grade_code = student_release_item.grade_code
         AND student_build_item.course_id = student_release_item.course_id
         AND student_build_item.course_version = student_release_item.course_version
         AND (
           student_build_item.status = 'ready'
           OR (
             student_build_item.status = 'course_ready'
             AND student_build_item.execution_mode_snapshot = 'content_only'
             AND student_build_item.content_phase = 'course_ready'
             AND student_build_item.content_gate_status = 'passed'
             AND student_build_item.content_gate_passed_at IS NOT NULL
             AND student_build_item.content_validation_contract_version
               IS NOT NULL
             AND student_build_item.content_validation_contract_version <> ''
             AND student_build_item.content_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
           )
         )
        JOIN learning_curriculum_classroom_item_receipts AS student_receipt
          ON student_receipt.build_item_id = student_build_item.id
         AND student_receipt.release_id = student_release_item.release_id
         AND student_receipt.grade_code = student_release_item.grade_code
         AND student_receipt.course_id = student_release_item.course_id
         AND student_receipt.course_version = student_release_item.course_version
         AND student_receipt.package_id = student_package.id
         AND student_receipt.package_version = student_package.version
         AND student_receipt.classroom_status = 'passed'
         AND student_receipt.tts_status = 'passed'
         AND student_receipt.asr_roundtrip_status = 'passed'
         AND student_receipt.conversation_provider_status = 'passed'
         AND student_receipt.auto_validated = 1
         AND student_receipt.publication_status = 'published'
        JOIN learning_openmaic_runtime_classrooms AS student_runtime
          ON student_runtime.id = student_receipt.runtime_classroom_id
         AND student_runtime.candidate_build_item_id = student_build_item.id
         AND student_runtime.candidate_release_id = student_release_item.release_id
         AND student_runtime.candidate_grade_code = student_release_item.grade_code
         AND student_runtime.candidate_target_fingerprint =
           student_receipt.target_fingerprint
         AND student_runtime.course_id = student_release_item.course_id
         AND student_runtime.course_version = student_release_item.course_version
         AND student_runtime.package_id = student_package.id
         AND student_runtime.package_version = student_package.version
         AND student_runtime.status = 'ready'
         AND student_runtime.upstream_classroom_id IS NOT NULL
         AND student_runtime.retired_at IS NULL
         {current_formal_runtime_sql(runtime_alias="student_runtime")}
        JOIN learning_formal_qwen_audio_jobs AS student_audio
          ON student_audio.build_item_id = student_receipt.build_item_id
         AND student_audio.runtime_classroom_id = student_runtime.id
         AND student_audio.release_id = student_release_item.release_id
         AND student_audio.grade_code = student_release_item.grade_code
         AND student_audio.target_fingerprint = student_receipt.target_fingerprint
         AND student_audio.course_id = student_release_item.course_id
         AND student_audio.course_version = student_release_item.course_version
         AND student_audio.package_id = student_package.id
         AND student_audio.package_version = student_package.version
         AND student_audio.state = 'auto_validated'
         AND student_audio.expected_segment_count BETWEEN 1 AND 240
         AND student_audio.tts_attempted_count = student_audio.expected_segment_count
         AND student_audio.tts_completed_count = student_audio.expected_segment_count
         AND student_audio.audio_validated_count = student_audio.expected_segment_count
         AND student_audio.asr_attempted_count = student_audio.expected_segment_count
         AND student_audio.asr_passed_count = student_audio.expected_segment_count
         AND student_audio.terminal_receipt_hash IS NOT NULL
        LEFT JOIN learning_openmaic_provider_readiness_jobs AS student_provider
          ON student_provider.release_id = student_release_item.release_id
         AND student_provider.grade_code = student_release_item.grade_code
         AND student_provider.target_fingerprint = student_receipt.target_fingerprint
        LEFT JOIN learning_curriculum_grade_release_pointers AS student_pointer
          ON student_pointer.grade_code = student_release_item.grade_code
         AND student_pointer.release_id = student_release_item.release_id
         AND student_pointer.target_fingerprint = student_receipt.target_fingerprint
         AND student_pointer.pointer_revision >= 1
         AND student_pointer.contract_version =
           'mira.learning.formal-publication.v1'
        LEFT JOIN learning_curriculum_grade_release_history AS student_history
          ON student_history.id = student_pointer.history_id
         AND student_history.grade_code = student_pointer.grade_code
         AND student_history.pointer_revision = student_pointer.pointer_revision
         AND student_history.target_fingerprint = student_pointer.target_fingerprint
         AND student_history.contract_version = student_pointer.contract_version
         AND student_history.release_id = student_pointer.release_id
         AND student_history.activated_at = student_pointer.activated_at
         AND student_history.activation_source = 'formal_publication'
         AND student_history.superseded_at IS NULL
        WHERE student_release_item.course_id = {course}.id
          AND student_release_item.course_version = {course}.version
          AND student_release_item.grade_code = {course}.grade_code
          {current_formal_validation_authority_sql(
              receipt_alias="student_receipt",
              provider_alias="student_provider",
          )}
          AND student_release_item.status = 'published'
          AND student_release_item.quality_status = 'ready'
          AND student_release_item.retired_at IS NULL
          AND student_release_item.curriculum_version = {course}.curriculum_version
          AND student_release_item.boundary_version = {course}.boundary_version
          AND student_release.curriculum_version = {course}.curriculum_version
          {asset_gate}
          AND (
            EXISTS (
              SELECT 1
              FROM learning_curriculum_preparation_plans AS student_plan
              WHERE student_plan.family_id = {family_id}
                AND student_plan.child_id = {child_id}
                AND student_plan.grade_selection_revision = {grade_revision}
                AND student_plan.grade_code = {course}.grade_code
                AND student_plan.catalog_build_id = student_build_item.build_job_id
                AND student_plan.catalog_release_id = student_release_item.release_id
                AND student_plan.target_fingerprint =
                  student_receipt.target_fingerprint
                AND student_plan.superseded_at IS NULL
                AND student_plan.status IN ('queued', 'running', 'ready', 'failed')
                AND NOT EXISTS (
                  SELECT 1
                  FROM learning_curriculum_preparation_plans AS newer_plan
                  WHERE newer_plan.family_id = student_plan.family_id
                    AND newer_plan.child_id = student_plan.child_id
                    AND newer_plan.grade_selection_revision =
                      student_plan.grade_selection_revision
                    AND newer_plan.target_fingerprint = student_plan.target_fingerprint
                    AND (
                      newer_plan.retry_ordinal > student_plan.retry_ordinal
                      OR (
                        newer_plan.retry_ordinal = student_plan.retry_ordinal
                        AND newer_plan.created_at > student_plan.created_at
                      )
                      OR (
                        newer_plan.retry_ordinal = student_plan.retry_ordinal
                        AND newer_plan.created_at = student_plan.created_at
                        AND newer_plan.id > student_plan.id
                      )
                    )
                )
            )
            OR (
              student_history.id IS NOT NULL
              AND NOT {_student_progressive_slot_exists_sql(
                  release_item_alias="student_release_item", child_alias=child_alias
              )}
            )
          )
      )
    """


class LearningRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def ensure_published_courses(self, courses: tuple[dict, ...], *, now: int) -> None:
        with self.transaction() as conn:
            for course in courses:
                boundary = next(
                    (
                        item
                        for item in boundaries_for(
                            str(course["gradeCode"]), str(course["subject"])
                        )
                        if item.skill_id == str(course["nodeCode"])
                    ),
                    None,
                )
                conn.execute(
                    """
                    INSERT INTO learning_courses(
                      id, version, grade_code, subject, node_code, title,
                      objective, status, quality_status, curriculum_version,
                      boundary_version, content_json, published_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'legacy_seed', ?, ?, ?, ?, ?, ?)
                    ON DUPLICATE KEY UPDATE
                      grade_code = VALUES(grade_code),
                      subject = VALUES(subject),
                      node_code = VALUES(node_code),
                      title = VALUES(title),
                      objective = VALUES(objective),
                      status = VALUES(status),
                      quality_status = VALUES(quality_status),
                      curriculum_version = VALUES(curriculum_version),
                      boundary_version = VALUES(boundary_version),
                      content_json = VALUES(content_json),
                      published_at = COALESCE(published_at, VALUES(published_at)),
                      updated_at = VALUES(updated_at)
                    """,
                    (
                        course["id"],
                        course["version"],
                        course["gradeCode"],
                        course["subject"],
                        course["nodeCode"],
                        course["title"],
                        course["objective"],
                        course["status"],
                        boundary.curriculum_version if boundary else None,
                        boundary.boundary_version if boundary else None,
                        self._json(course["content"]),
                        now,
                        now,
                        now,
                    ),
                )

    def get_recommended_course(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        learning_date: str,
        subject: str,
        required_node_code: str | None = None,
        excluding_course_ids: Sequence[str] = (),
        content_origins: Sequence[str] = (),
        require_teaching_flow: bool = False,
        require_catalog_release: bool = False,
        require_formal_pointer: bool = False,
        student_grade_selection_revision: int | None = None,
        curriculum_version: str | None = None,
        boundary_version: str | None = None,
    ) -> DatabaseRow | None:
        exclusions = tuple(
            str(course_id).strip()
            for course_id in excluding_course_ids
            if str(course_id).strip()
        )
        exclusion_sql = ""
        params: list[object] = [
            family_id,
            child_id,
            grade_code,
            subject,
        ]
        required_node = str(required_node_code or "").strip()
        required_node_sql = ""
        if required_node:
            required_node_sql = " AND course.node_code = ?"
            params.append(required_node)
        if exclusions:
            exclusion_sql = (
                f" AND course.id NOT IN ({', '.join('?' for _ in exclusions)})"
            )
            params.extend(exclusions)
        origins = tuple(
            str(origin).strip()
            for origin in content_origins
            if str(origin).strip()
        )
        origin_sql = ""
        if origins:
            origin_sql = (
                f" AND course.content_origin IN ({', '.join('?' for _ in origins)})"
            )
            params.extend(origins)
        teaching_flow_sql = (
            _TEACHING_FLOW_SQL.format(alias="course")
            if require_teaching_flow
            else ""
        )
        student_scoped = student_grade_selection_revision is not None
        catalog_join_sql = (
            self._catalog_release_joins()
            if require_catalog_release and not student_scoped
            else ""
        )
        catalog_filter_sql = (
            self._catalog_release_filters()
            if require_catalog_release and not student_scoped
            else ""
        )
        if require_formal_pointer and not require_catalog_release:
            raise ValueError("formal pointer requires a catalog release")
        if require_catalog_release:
            if not curriculum_version or (not boundary_version and not student_scoped):
                raise ValueError(
                    "catalog recommendation requires curriculum and boundary versions"
                )
            if student_scoped:
                catalog_filter_sql += (
                    f" AND {_student_visible_course_sql()}"
                    " AND course.curriculum_version = ?"
                )
                params.extend(
                    (
                        family_id,
                        child_id,
                        int(student_grade_selection_revision),
                        family_id,
                        child_id,
                        int(student_grade_selection_revision),
                        curriculum_version,
                    )
                )
                if boundary_version:
                    catalog_filter_sql += " AND course.boundary_version = ?"
                    params.append(boundary_version)
            else:
                catalog_filter_sql += (
                    " AND course.curriculum_version = ?"
                    " AND course.boundary_version = ?"
                    " AND catalog_release.curriculum_version = ?"
                )
                params.extend(
                    (curriculum_version, boundary_version, curriculum_version)
                )
                if require_formal_pointer:
                    catalog_filter_sql += (
                        " AND grade_pointer.target_fingerprint IS NOT NULL"
                        " AND grade_pointer.contract_version = "
                        "'mira.learning.formal-publication.v1'"
                    )
        params.extend(
            (
                family_id,
                child_id,
                learning_date,
                family_id,
                child_id,
                learning_date,
            )
        )
        return conn.execute(
            f"""
            SELECT course.*
            FROM learning_courses AS course
            {catalog_join_sql}
            LEFT JOIN learning_mastery_states AS mastery
              ON mastery.family_id = ?
             AND mastery.child_id = ?
             AND mastery.node_code = course.node_code
             AND mastery.subject = course.subject
            WHERE course.grade_code = ?
              AND course.subject = ?
              AND course.status = 'published'
              {required_node_sql}
              {exclusion_sql}
              {origin_sql}
              {teaching_flow_sql}
              {catalog_filter_sql}
            ORDER BY
              CASE WHEN EXISTS (
                SELECT 1
                FROM tasks AS prior_learning_task
                WHERE prior_learning_task.family_id = ?
                  AND prior_learning_task.child_id = ?
                  AND prior_learning_task.type = 'learning'
                  AND prior_learning_task.learning_course_id = course.id
                  AND prior_learning_task.learning_course_version = course.version
              ) THEN 1 ELSE 0 END,
              CASE WHEN mastery.node_code IS NULL THEN 0 ELSE 1 END,
              CASE
                WHEN mastery.node_code IS NOT NULL
                 AND mastery.next_review_date <= ? THEN 0
                ELSE 1
              END,
              mastery.next_review_date ASC,
              mastery.last_practiced_at ASC,
              COALESCE((
                SELECT MAX(prior_lru_task.scheduled_date)
                FROM tasks AS prior_lru_task
                WHERE prior_lru_task.family_id = ?
                  AND prior_lru_task.child_id = ?
                  AND prior_lru_task.type = 'learning'
                  AND prior_lru_task.learning_course_id = course.id
                  AND prior_lru_task.learning_course_version = course.version
              ), '0000-00-00') ASC,
              SHA2(CONCAT(?, ':', course.id, ':', course.version), 256) ASC,
              course.published_at ASC,
              course.id ASC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def list_published_subjects(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        content_origins: Sequence[str] = (),
        require_teaching_flow: bool = False,
        require_catalog_release: bool = False,
        family_id: str | None = None,
        child_id: str | None = None,
        student_grade_selection_revision: int | None = None,
        curriculum_version: str | None = None,
    ) -> list[str]:
        origins = tuple(
            str(origin).strip()
            for origin in content_origins
            if str(origin).strip()
        )
        origin_sql = ""
        params: list[object] = [grade_code]
        if origins:
            origin_sql = (
                f" AND course.content_origin IN ({', '.join('?' for _ in origins)})"
            )
            params.extend(origins)
        teaching_flow_sql = (
            _TEACHING_FLOW_SQL.format(alias="course")
            if require_teaching_flow
            else ""
        )
        student_scoped = student_grade_selection_revision is not None
        if student_scoped and (not family_id or not child_id):
            raise ValueError("student catalog subject query requires child authority")
        catalog_join_sql = (
            self._catalog_release_joins()
            if require_catalog_release and not student_scoped
            else ""
        )
        catalog_filter_sql = (
            self._catalog_release_filters()
            if require_catalog_release and not student_scoped
            else ""
        )
        if require_catalog_release:
            if not curriculum_version:
                raise ValueError("catalog subject query requires curriculum version")
            if student_scoped:
                catalog_filter_sql += (
                    f" AND {_student_visible_course_sql()}"
                    " AND course.curriculum_version = ?"
                )
                params.extend(
                    (
                        family_id,
                        child_id,
                        int(student_grade_selection_revision),
                        family_id,
                        child_id,
                        int(student_grade_selection_revision),
                        curriculum_version,
                    )
                )
            else:
                catalog_filter_sql += (
                    " AND course.curriculum_version = ?"
                    " AND catalog_release.curriculum_version = ?"
                )
                params.extend((curriculum_version, curriculum_version))
        rows = conn.execute(
            f"""
            SELECT course.subject, MIN(course.published_at) AS first_published_at
            FROM learning_courses AS course
            {catalog_join_sql}
            WHERE course.grade_code = ? AND course.status = 'published'
              {origin_sql}
              {teaching_flow_sql}
              {catalog_filter_sql}
            GROUP BY course.subject
            ORDER BY first_published_at, course.subject
            """,
            params,
        ).fetchall()
        return [str(row["subject"]) for row in rows]

    def list_primary_children_pending_daily_preparation(
        self,
        conn: DatabaseConnection,
        *,
        learning_date: str,
    ) -> list[DatabaseRow]:
        """Return only primary children whose three daily slots are incomplete."""

        return list(
            conn.execute(
                """
                SELECT child.*
                FROM children AS child
                WHERE child.grade_code IN (
                  'primary_1', 'primary_2', 'primary_3',
                  'primary_4', 'primary_5', 'primary_6'
                )
                  AND (
                    (
                      SELECT COUNT(DISTINCT COALESCE(task.learning_slot, 'core'))
                      FROM tasks AS task
                      WHERE task.family_id = child.family_id
                        AND task.child_id = child.id
                        AND task.scheduled_date = ?
                        AND task.type = 'learning'
                        AND COALESCE(task.learning_slot, 'core') IN (
                          'core', 'rotation', 'extension'
                        )
                    ) < 3
                    OR EXISTS (
                    SELECT 1
                    FROM tasks AS task
                    WHERE task.family_id = child.family_id
                      AND task.child_id = child.id
                      AND task.scheduled_date = ?
                      AND task.type = 'learning'
                      AND COALESCE(task.learning_slot, 'core') IN (
                        'core', 'rotation', 'extension'
                      )
                      AND NOT EXISTS (
                        SELECT 1
                        FROM learning_sessions AS session
                        WHERE session.task_id = task.id
                      )
                      AND NOT EXISTS (
                        SELECT 1
                        FROM learning_curriculum_grade_release_pointers AS pointer
                        JOIN learning_curriculum_grade_release_history AS history
                          ON history.id = pointer.history_id
                         AND history.grade_code = pointer.grade_code
                         AND history.pointer_revision = pointer.pointer_revision
                         AND history.target_fingerprint = pointer.target_fingerprint
                         AND history.contract_version = pointer.contract_version
                         AND history.release_id = pointer.release_id
                         AND history.activation_source = 'formal_publication'
                         AND history.superseded_at IS NULL
                        JOIN learning_catalog_releases AS release_row
                          ON release_row.id = pointer.release_id
                         AND release_row.status = 'published'
                         AND release_row.quality_status = 'ready'
                         AND release_row.retired_at IS NULL
                        JOIN learning_catalog_release_items AS release_item
                          ON release_item.release_id = pointer.release_id
                         AND release_item.course_id = task.learning_course_id
                         AND release_item.course_version = task.learning_course_version
                         AND release_item.status = 'published'
                         AND release_item.quality_status = 'ready'
                         AND release_item.retired_at IS NULL
                         AND release_item.package_id IS NOT NULL
                         AND release_item.package_id <> ''
                         AND release_item.package_version > 0
                        WHERE pointer.grade_code = child.grade_code
                          AND pointer.pointer_revision >= 1
                          AND pointer.contract_version =
                            'mira.learning.formal-publication.v1'
                      )
                    )
                  )
                ORDER BY child.family_id, child.created_at, child.id
                """,
                (learning_date, learning_date),
            ).fetchall()
        )

    def has_unpracticed_course(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        subject: str,
        excluding_node_code: str,
        content_origins: Sequence[str] = (),
        require_teaching_flow: bool = False,
        require_catalog_release: bool = False,
        curriculum_version: str | None = None,
    ) -> bool:
        origins = tuple(
            str(origin).strip()
            for origin in content_origins
            if str(origin).strip()
        )
        origin_sql = ""
        params: list[object] = [
            family_id,
            child_id,
            grade_code,
            subject,
            excluding_node_code,
        ]
        if origins:
            origin_sql = (
                f" AND course.content_origin IN ({', '.join('?' for _ in origins)})"
            )
            params.extend(origins)
        teaching_flow_sql = (
            _TEACHING_FLOW_SQL.format(alias="course")
            if require_teaching_flow
            else ""
        )
        catalog_join_sql = self._catalog_release_joins() if require_catalog_release else ""
        catalog_filter_sql = self._catalog_release_filters() if require_catalog_release else ""
        if require_catalog_release:
            if not curriculum_version:
                raise ValueError("catalog course query requires curriculum version")
            catalog_filter_sql += (
                " AND course.curriculum_version = ?"
                " AND catalog_release.curriculum_version = ?"
            )
            params.extend((curriculum_version, curriculum_version))
        row = conn.execute(
            f"""
            SELECT course.id
            FROM learning_courses AS course
            {catalog_join_sql}
            LEFT JOIN learning_mastery_states AS mastery
              ON mastery.family_id = ?
             AND mastery.child_id = ?
             AND mastery.node_code = course.node_code
             AND mastery.subject = course.subject
            WHERE course.grade_code = ?
              AND course.subject = ?
              AND course.status = 'published'
              AND course.node_code <> ?
              {origin_sql}
              {teaching_flow_sql}
              {catalog_filter_sql}
              AND mastery.node_code IS NULL
            LIMIT 1
            """,
            params,
        ).fetchone()
        return row is not None

    def count_unassigned_published_courses(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        subject: str,
        node_code: str | None = None,
        content_origins: Sequence[str] = (),
        require_teaching_flow: bool = False,
        require_catalog_release: bool = False,
        curriculum_version: str | None = None,
        boundary_version: str | None = None,
    ) -> int:
        origins = tuple(
            str(origin).strip()
            for origin in content_origins
            if str(origin).strip()
        )
        origin_sql = ""
        params: list[object] = [grade_code, subject]
        node = str(node_code or "").strip()
        node_sql = ""
        if node:
            node_sql = " AND course.node_code = ?"
            params.append(node)
        if origins:
            origin_sql = (
                f" AND course.content_origin IN ({', '.join('?' for _ in origins)})"
            )
            params.extend(origins)
        teaching_flow_sql = (
            _TEACHING_FLOW_SQL.format(alias="course")
            if require_teaching_flow
            else ""
        )
        catalog_join_sql = self._catalog_release_joins() if require_catalog_release else ""
        catalog_filter_sql = self._catalog_release_filters() if require_catalog_release else ""
        if require_catalog_release:
            if not curriculum_version or (node and not boundary_version):
                raise ValueError(
                    "catalog supply query requires current curriculum and boundary versions"
                )
            catalog_filter_sql += (
                " AND course.curriculum_version = ?"
                " AND catalog_release.curriculum_version = ?"
            )
            params.extend((curriculum_version, curriculum_version))
            if node:
                catalog_filter_sql += " AND course.boundary_version = ?"
                params.append(boundary_version)
        params.extend((family_id, child_id))
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS value
            FROM learning_courses AS course
            {catalog_join_sql}
            WHERE course.grade_code = ?
              AND course.subject = ?
              AND course.status = 'published'
              {node_sql}
              {origin_sql}
              {teaching_flow_sql}
              {catalog_filter_sql}
              AND NOT EXISTS (
                SELECT 1
                FROM tasks AS prior_learning_task
                WHERE prior_learning_task.family_id = ?
                  AND prior_learning_task.child_id = ?
                  AND prior_learning_task.type = 'learning'
                  AND prior_learning_task.learning_course_id = course.id
                  AND prior_learning_task.learning_course_version = course.version
              )
            """,
            params,
        ).fetchone()
        return int((row or {}).get("value") or 0)

    def get_student_visible_course(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        grade_selection_revision: int,
        course_id: str,
        course_version: str,
    ) -> DatabaseRow | None:
        """Return one exact rolling item or a shared active-pointer fallback."""

        return conn.execute(
            f"""
            SELECT course.*
            FROM learning_courses AS course
            WHERE course.id = ? AND course.version = ?
              AND course.grade_code = ?
              AND course.status = 'published'
              AND course.quality_status = 'released'
              AND course.content_origin = 'openmaic_generated'
              AND course.retired_at IS NULL
              AND {_student_visible_course_sql()}
            LIMIT 1
            """,
            (
                course_id,
                course_version,
                grade_code,
                family_id,
                child_id,
                int(grade_selection_revision),
                family_id,
                child_id,
                int(grade_selection_revision),
            ),
        ).fetchone()

    def list_student_visible_courses(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        grade_selection_revision: int,
        subject: str | None = None,
        favorite_only: bool = False,
        limit: int = 50,
    ) -> list[DatabaseRow]:
        """List currently usable catalog rows, including taskless new items."""

        params: list[object] = [
            family_id,
            child_id,
            family_id,
            child_id,
            family_id,
            child_id,
            grade_code,
        ]
        subject_sql = ""
        if subject:
            subject_sql = " AND course.subject = ?"
            params.append(subject)
        params.extend(
            (
                family_id,
                child_id,
                int(grade_selection_revision),
                family_id,
                child_id,
                int(grade_selection_revision),
            )
        )
        favorite_sql = " AND favorite.course_id IS NOT NULL" if favorite_only else ""
        params.append(int(limit))
        return list(
            conn.execute(
                f"""
                SELECT course.*,
                  favorite.course_id AS favorite_course_id,
                  (
                    SELECT MAX(history_task.scheduled_date)
                    FROM tasks AS history_task
                    WHERE history_task.family_id = ?
                      AND history_task.child_id = ?
                      AND history_task.type = 'learning'
                      AND history_task.learning_course_id = course.id
                      AND history_task.learning_course_version = course.version
                  ) AS last_learning_date,
                  (
                    SELECT MAX(history_task.updated_at)
                    FROM tasks AS history_task
                    WHERE history_task.family_id = ?
                      AND history_task.child_id = ?
                      AND history_task.type = 'learning'
                      AND history_task.learning_course_id = course.id
                      AND history_task.learning_course_version = course.version
                  ) AS last_task_activity_at
                FROM learning_courses AS course
                LEFT JOIN student_learning_course_favorites AS favorite
                  ON favorite.family_id = ?
                 AND favorite.child_id = ?
                 AND favorite.course_id = course.id
                 AND favorite.course_version = course.version
                WHERE course.grade_code = ?
                  AND course.status = 'published'
                  AND course.quality_status = 'released'
                  AND course.content_origin = 'openmaic_generated'
                  AND course.retired_at IS NULL
                  {subject_sql}
                  AND {_student_visible_course_sql()}
                  {favorite_sql}
                ORDER BY
                  CASE WHEN last_learning_date IS NULL THEN 0 ELSE 1 END,
                  COALESCE(last_learning_date, '0000-00-00') ASC,
                  SHA2(CONCAT(CURRENT_DATE(), ':', course.id, ':', course.version), 256),
                  course.published_at DESC,
                  course.id
                LIMIT ?
                """,
                params,
            ).fetchall()
        )

    def student_catalog_summary(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        grade_code: str,
        grade_selection_revision: int,
        target_course_count: int = 30,
    ) -> dict[str, object]:
        """Describe rolling generation without treating a failed refresh as no access."""

        plan = conn.execute(
            """
            SELECT status, stage, total_course_count, progress_percent
            FROM learning_curriculum_preparation_plans
            WHERE family_id = ? AND child_id = ? AND grade_code = ?
              AND grade_selection_revision = ? AND superseded_at IS NULL
            ORDER BY retry_ordinal DESC, created_at DESC, id DESC
            LIMIT 1
            """,
            (family_id, child_id, grade_code, int(grade_selection_revision)),
        ).fetchone()
        available = conn.execute(
            f"""
            SELECT COUNT(*) AS value
            FROM learning_courses AS course
            WHERE course.grade_code = ?
              AND course.status = 'published'
              AND course.quality_status = 'released'
              AND course.content_origin = 'openmaic_generated'
              AND course.retired_at IS NULL
              AND {_student_visible_course_sql()}
            """,
            (
                grade_code,
                family_id,
                child_id,
                int(grade_selection_revision),
                family_id,
                child_id,
                int(grade_selection_revision),
            ),
        ).fetchone()
        available_count = int((available or {}).get("value") or 0)
        resolved_target = int(
            (plan or {}).get("total_course_count") or target_course_count
        )
        if plan is None:
            status = "complete" if available_count >= resolved_target else "preparing"
        elif str(plan.get("status") or "") == "failed":
            status = "failed"
        elif (
            str(plan.get("status") or "") == "ready"
            and str(plan.get("stage") or "") == "completed"
        ):
            status = "complete"
        else:
            status = "preparing"
        progress = (plan or {}).get("progress_percent")
        progress_percent = (
            min(100 if status == "complete" else 99, max(0, int(progress)))
            if progress is not None else None
        )
        return {
            "preparationProgressPercent": progress_percent,
            "catalogStatus": status,
            "availableCourseCount": available_count,
            "targetCourseCount": resolved_target,
        }

    def count_published_grade_courses(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
    ) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) AS value
            FROM learning_courses
            WHERE grade_code = ? AND status = 'published' AND retired_at IS NULL
            """,
            (grade_code,),
        ).fetchone()
        return int((row or {}).get("value") or 0)

    def get_course(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        version: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            "SELECT * FROM learning_courses WHERE id = ? AND version = ?" + lock,
            (course_id, version),
        ).fetchone()

    def get_course_in_active_formal_release(
        self,
        conn: DatabaseConnection,
        *,
        grade_code: str,
        course_id: str,
        course_version: str,
    ) -> DatabaseRow | None:
        """Return a current-read course from the exact active formal pointer."""

        return conn.execute(
            """
            SELECT course.*
            FROM learning_curriculum_grade_release_pointers AS pointer
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
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = pointer.release_id
             AND release_row.status = 'published'
             AND release_row.quality_status = 'ready'
             AND release_row.retired_at IS NULL
            JOIN learning_catalog_release_items AS release_item
              ON release_item.release_id = pointer.release_id
             AND release_item.grade_code = pointer.grade_code
             AND release_item.course_id = ?
             AND release_item.course_version = ?
             AND release_item.status = 'published'
             AND release_item.quality_status = 'ready'
             AND release_item.retired_at IS NULL
            JOIN learning_courses AS course
              ON course.id = release_item.course_id
             AND course.version = release_item.course_version
             AND course.grade_code = pointer.grade_code
             AND course.status = 'published'
             AND course.quality_status = 'released'
             AND course.content_origin = 'openmaic_generated'
             AND course.retired_at IS NULL
            WHERE pointer.grade_code = ?
              AND pointer.pointer_revision >= 1
              AND pointer.contract_version =
                'mira.learning.formal-publication.v1'
            LIMIT 1 FOR UPDATE
            """,
            (course_id, course_version, grade_code),
        ).fetchone()

    def is_course_in_active_catalog(
        self,
        conn: DatabaseConnection,
        *,
        course_id: str,
        course_version: str,
        curriculum_version: str,
        boundary_version: str,
    ) -> bool:
        row = conn.execute(
            f"""
            SELECT course.id
            FROM learning_courses AS course
            {self._catalog_release_joins()}
            WHERE course.id = ? AND course.version = ?
              AND course.status = 'published'
              AND course.curriculum_version = ?
              AND course.boundary_version = ?
              AND catalog_release.curriculum_version = ?
              {self._catalog_release_filters()}
            LIMIT 1
            """,
            (
                course_id,
                course_version,
                curriculum_version,
                boundary_version,
                curriculum_version,
            ),
        ).fetchone()
        return row is not None

    def get_today_task(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_date: str,
        slot: str | None = None,
    ) -> DatabaseRow | None:
        slot_sql = " AND learning_slot = ?" if slot else ""
        params: list[object] = [family_id, child_id, learning_date]
        if slot:
            params.append(slot)
        return conn.execute(
            f"""
            SELECT * FROM tasks
            WHERE family_id = ? AND child_id = ? AND scheduled_date = ?
              AND type = 'learning' AND learning_course_id IS NOT NULL
              AND status <> 'cancelled'
              {slot_sql}
            ORDER BY
              CASE learning_slot WHEN 'core' THEN 0 WHEN 'rotation' THEN 1 ELSE 2 END,
              created_at, id
            LIMIT 1
            """,
            params,
        ).fetchone()

    def get_today_tasks(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_date: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM tasks
                WHERE family_id = ? AND child_id = ? AND scheduled_date = ?
                  AND type = 'learning' AND learning_course_id IS NOT NULL
                  AND status <> 'cancelled'
                ORDER BY
                  CASE learning_slot WHEN 'core' THEN 0 WHEN 'rotation' THEN 1 ELSE 2 END,
                  created_at, id
                """,
                (family_id, child_id, learning_date),
            ).fetchall()
        )

    def list_daily_carryovers(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        target_date: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT task.*,
                  carryover.id AS carryover_id,
                  carryover.origin_date AS carryover_origin_date,
                  carryover.target_date AS carryover_target_date,
                  carryover.target_slot AS carryover_target_slot,
                  carryover.reason AS carryover_reason
                FROM learning_task_carryovers AS carryover
                JOIN tasks AS task
                  ON task.id = carryover.source_task_id
                 AND task.family_id = carryover.family_id
                 AND task.child_id = carryover.child_id
                WHERE carryover.family_id = ? AND carryover.child_id = ?
                  AND carryover.target_date = ?
                ORDER BY
                  CASE carryover.target_slot
                    WHEN 'core' THEN 0 WHEN 'rotation' THEN 1 ELSE 2
                  END,
                  carryover.created_at,
                  carryover.id
                """,
                (family_id, child_id, target_date),
            ).fetchall()
        )

    def list_carryover_candidates(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        earliest_date: str,
        target_date: str,
        limit: int = 12,
    ) -> list[DatabaseRow]:
        """Return recent unfinished tasks without mutating their history."""

        return list(
            conn.execute(
                """
                SELECT task.*,
                  session.id AS carryover_session_id,
                  session.status AS carryover_session_status,
                  session.updated_at AS carryover_session_updated_at
                FROM tasks AS task
                JOIN learning_courses AS course
                  ON course.id = task.learning_course_id
                 AND course.version = task.learning_course_version
                LEFT JOIN learning_sessions AS session
                  ON session.family_id = task.family_id
                 AND session.task_id = task.id
                WHERE task.family_id = ? AND task.child_id = ?
                  AND task.type = 'learning'
                  AND task.learning_course_id IS NOT NULL
                  AND task.scheduled_date >= ? AND task.scheduled_date < ?
                  AND task.status NOT IN (
                    'completed', 'confirmed', 'awaiting_parent_confirmation',
                    'rejected', 'expired', 'cancelled'
                  )
                  AND (session.id IS NULL OR session.status <> 'completed')
                  AND NOT EXISTS (
                    SELECT 1 FROM task_events AS acknowledged
                    WHERE acknowledged.task_id = task.id
                      AND acknowledged.event_type = 'missed_acknowledged'
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM learning_reports AS report
                    WHERE report.family_id = task.family_id
                      AND report.task_id = task.id
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM tasks AS newer_task
                    JOIN learning_courses AS newer_course
                      ON newer_course.id = newer_task.learning_course_id
                     AND newer_course.version =
                       newer_task.learning_course_version
                    WHERE newer_task.family_id = task.family_id
                      AND newer_task.child_id = task.child_id
                      AND newer_task.type = 'learning'
                      AND newer_task.learning_course_id IS NOT NULL
                      AND newer_task.status NOT IN (
                        'cancelled', 'rejected', 'expired'
                      )
                      AND newer_course.grade_code = course.grade_code
                      AND newer_course.subject = course.subject
                      AND newer_course.node_code = course.node_code
                      AND COALESCE(newer_course.curriculum_version, '') =
                        COALESCE(course.curriculum_version, '')
                      AND (
                        newer_task.scheduled_date > task.scheduled_date
                        OR (
                          newer_task.scheduled_date = task.scheduled_date
                          AND newer_task.created_at > task.created_at
                        )
                        OR (
                          newer_task.scheduled_date = task.scheduled_date
                          AND newer_task.created_at = task.created_at
                          AND newer_task.id > task.id
                        )
                      )
                  )
                ORDER BY
                  CASE
                    WHEN session.id IS NOT NULL AND session.status <> 'completed' THEN 0
                    ELSE 1
                  END,
                  COALESCE(session.updated_at, task.updated_at) DESC,
                  task.scheduled_date DESC,
                  CASE task.learning_slot
                    WHEN 'core' THEN 0 WHEN 'rotation' THEN 1 ELSE 2
                  END,
                  task.id
                LIMIT ?
                """,
                (family_id, child_id, earliest_date, target_date, limit),
            ).fetchall()
        )

    def create_daily_carryover(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        source_task: DatabaseRow,
        target_date: str,
        target_slot: str,
        reason: str,
        now: int,
    ) -> DatabaseRow:
        carryover_id = "carry_" + hashlib.sha256(
            f"{family_id}\n{child_id}\n{target_date}\n{target_slot}".encode(
                "utf-8"
            )
        ).hexdigest()
        conn.execute(
            """
            INSERT INTO learning_task_carryovers(
              id, family_id, child_id, source_task_id, origin_date,
              target_date, target_slot, reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                carryover_id,
                family_id,
                child_id,
                source_task["id"],
                source_task["scheduled_date"],
                target_date,
                target_slot,
                reason,
                now,
                now,
            ),
        )
        return conn.execute(
            """
            SELECT * FROM learning_task_carryovers
            WHERE id = ? AND family_id = ? AND child_id = ?
            LIMIT 1
            """,
            (carryover_id, family_id, child_id),
        ).fetchone()

    def reactivate_task_for_carryover(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> DatabaseRow | None:
        """Make an unfinished historical task schedulable on its carryover day.

        ``missed_at`` and all task events stay intact as the audit record.  The
        carryover row supplies the effective date to the scheduler, while the
        original ``scheduled_date`` continues to identify when the lesson was
        first assigned.
        """

        conn.execute(
            """
            UPDATE tasks
            SET status = 'scheduled', reminder_status = 'pending',
              camera_observation_status = 'unknown',
              delay_reminder_count = 0, next_reminder_at = NULL,
              delayed_at = NULL, ended_at = NULL, updated_at = ?
            WHERE family_id = ? AND id = ? AND type = 'learning'
              AND status NOT IN (
                'completed', 'confirmed', 'awaiting_parent_confirmation',
                'rejected', 'expired', 'cancelled'
              )
            """,
            (now, family_id, task_id),
        )
        return self.get_task(
            conn,
            family_id=family_id,
            task_id=task_id,
        )

    def cancel_unstarted_task_for_carryover(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE tasks AS task
            SET status = 'cancelled',
              evidence_summary = '由昨日未完成课程替换',
              ended_at = COALESCE(ended_at, ?), updated_at = ?
            WHERE task.family_id = ? AND task.id = ?
              AND task.type = 'learning'
              AND task.status IN ('scheduled', 'pending', 'reminder_sent', 'delayed')
              AND NOT EXISTS (
                SELECT 1 FROM learning_sessions AS session
                WHERE session.family_id = task.family_id
                  AND session.task_id = task.id
              )
            """,
            (now, now, family_id, task_id),
        )
        row = conn.execute(
            "SELECT * FROM tasks WHERE family_id = ? AND id = ? LIMIT 1",
            (family_id, task_id),
        ).fetchone()
        return row if row is not None and row.get("status") == "cancelled" else None

    def count_learning_backlog(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        before_date: str,
    ) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM tasks AS task
            JOIN learning_courses AS course
              ON course.id = task.learning_course_id
             AND course.version = task.learning_course_version
            LEFT JOIN learning_sessions AS session
              ON session.family_id = task.family_id
             AND session.task_id = task.id
            WHERE task.family_id = ? AND task.child_id = ?
              AND task.type = 'learning'
              AND task.learning_course_id IS NOT NULL
              AND task.scheduled_date < ?
              AND task.status NOT IN (
                'completed', 'confirmed', 'awaiting_parent_confirmation',
                'rejected', 'expired', 'cancelled'
              )
              AND (session.id IS NULL OR session.status <> 'completed')
              AND NOT EXISTS (
                SELECT 1 FROM task_events AS acknowledged
                WHERE acknowledged.task_id = task.id
                  AND acknowledged.event_type = 'missed_acknowledged'
              )
              AND NOT EXISTS (
                SELECT 1 FROM learning_task_carryovers AS current_carryover
                WHERE current_carryover.source_task_id = task.id
                  AND current_carryover.target_date = ?
              )
              AND NOT EXISTS (
                SELECT 1
                FROM tasks AS newer_task
                JOIN learning_courses AS newer_course
                  ON newer_course.id = newer_task.learning_course_id
                 AND newer_course.version = newer_task.learning_course_version
                WHERE newer_task.family_id = task.family_id
                  AND newer_task.child_id = task.child_id
                  AND newer_task.type = 'learning'
                  AND newer_task.learning_course_id IS NOT NULL
                  AND newer_task.status NOT IN (
                    'cancelled', 'rejected', 'expired'
                  )
                  AND newer_course.grade_code = course.grade_code
                  AND newer_course.subject = course.subject
                  AND newer_course.node_code = course.node_code
                  AND COALESCE(newer_course.curriculum_version, '') =
                    COALESCE(course.curriculum_version, '')
                  AND (
                    newer_task.scheduled_date > task.scheduled_date
                    OR (
                      newer_task.scheduled_date = task.scheduled_date
                      AND newer_task.created_at > task.created_at
                    )
                    OR (
                      newer_task.scheduled_date = task.scheduled_date
                      AND newer_task.created_at = task.created_at
                      AND newer_task.id > task.id
                    )
                  )
              )
            """,
            (family_id, child_id, before_date, before_date),
        ).fetchone()
        return int((row or {}).get("count") or 0)

    def assign_today_task(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        learning_date: str,
        slot: str,
        scheduled_start: str | None,
        course: DatabaseRow,
        created_by: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        assignment_key = hashlib.sha256(
            f"{family_id}\n{child_id}\n{learning_date}\n{slot}".encode("utf-8")
        ).hexdigest()
        existing = self.get_today_task(
            conn,
            family_id=family_id,
            child_id=child_id,
            learning_date=learning_date,
            slot=slot,
        )
        if existing is not None:
            return existing, False
        existing = conn.execute(
            "SELECT * FROM tasks WHERE learning_assignment_key = ? LIMIT 1",
            (assignment_key,),
        ).fetchone()
        if existing is not None:
            return existing, False

        task_id = f"task_{uuid.uuid4().hex}"
        start_at = (
            f"{learning_date}T{scheduled_start}:00" if scheduled_start else None
        )
        conn.execute(
            """
            INSERT INTO tasks(
              id, family_id, child_id, title, description, type, status,
              scheduled_date, scheduled_start, scheduled_end, schedule_type,
              start_at, due_at, repeat_rule, priority, reward_points,
              requires_parent_confirmation, created_by, reminder_minutes_before,
              reminder_status, timezone, learning_course_id,
              learning_course_version, learning_assignment_key, learning_slot,
              created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'learning', 'scheduled', ?, ?, NULL, 'one_time',
              ?, NULL, NULL, 3, 0, 0, ?, 5, 'pending', 'Asia/Shanghai', ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                task_id,
                family_id,
                child_id,
                course["title"],
                course["objective"],
                learning_date,
                scheduled_start,
                start_at,
                created_by,
                course["id"],
                course["version"],
                assignment_key,
                slot,
                now,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM tasks WHERE learning_assignment_key = ? LIMIT 1",
            (assignment_key,),
        ).fetchone()
        return row, row["id"] == task_id

    def replace_unstarted_task_course(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        course: DatabaseRow,
        now: int,
    ) -> DatabaseRow | None:
        """Move an unstarted daily slot to a different published course.

        This is intentionally guarded in SQL: once a learning session exists,
        or the task has left a pre-start state, its course/version is immutable.
        The guard lets daily preparation repair old duplicate-subject pairs
        without rewriting any learning history.
        """

        conn.execute(
            """
            UPDATE tasks AS task
            SET title = ?, description = ?,
              learning_course_id = ?, learning_course_version = ?,
              updated_at = ?
            WHERE task.family_id = ? AND task.id = ?
              AND task.type = 'learning'
              AND task.status IN ('scheduled', 'pending', 'reminder_sent', 'delayed')
              AND NOT EXISTS (
                SELECT 1 FROM learning_sessions AS session
                WHERE session.family_id = task.family_id
                  AND session.task_id = task.id
              )
            """,
            (
                course["title"],
                course["objective"],
                course["id"],
                course["version"],
                now,
                family_id,
                task_id,
            ),
        )
        return self.get_task(conn, family_id=family_id, task_id=task_id)

    def get_task(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            "SELECT * FROM tasks WHERE family_id = ? AND id = ?" + lock,
            (family_id, task_id),
        ).fetchone()

    def get_session_for_task(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_sessions
            WHERE family_id = ? AND task_id = ?
            LIMIT 1
            """
            + (" FOR UPDATE" if for_update else ""),
            (family_id, task_id),
        ).fetchone()

    def get_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        session_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_sessions
            WHERE family_id = ? AND id = ?
            LIMIT 1
            """
            + lock,
            (family_id, session_id),
        ).fetchone()

    def create_or_get_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        task_id: str,
        course_id: str,
        course_version: str,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        existing = self.get_session_for_task(
            conn,
            family_id=family_id,
            task_id=task_id,
        )
        if existing is not None:
            return existing, False
        session_id = f"learn_session_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_sessions(
              id, family_id, child_id, task_id, course_id, course_version,
              status, current_question_index, correct_count, attempted_count,
              answers_json, started_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'in_progress', 0, 0, 0, '[]', ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                session_id,
                family_id,
                child_id,
                task_id,
                course_id,
                course_version,
                now,
                now,
                now,
            ),
        )
        row = self.get_session_for_task(
            conn,
            family_id=family_id,
            task_id=task_id,
            for_update=True,
        )
        if row is None:
            raise RuntimeError(
                "learning session missing after upsert: "
                f"family_id={family_id}, task_id={task_id}"
            )
        return row, row["id"] == session_id

    def update_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        session_id: str,
        status: str,
        current_question_index: int,
        correct_count: int,
        attempted_count: int,
        answers: list[dict],
        completed_at: int | None,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE learning_sessions
            SET status = ?, current_question_index = ?, correct_count = ?,
              attempted_count = ?, answers_json = ?, completed_at = ?, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (
                status,
                current_question_index,
                correct_count,
                attempted_count,
                self._json(answers),
                completed_at,
                now,
                family_id,
                session_id,
            ),
        )
        return self.get_session(
            conn,
            family_id=family_id,
            session_id=session_id,
            for_update=True,
        )

    def mark_task_in_progress(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE tasks
            SET status = CASE
                WHEN status IN (
                  'scheduled', 'pending', 'reminder_sent', 'delayed', 'missed'
                )
                  THEN 'in_progress'
                ELSE status
              END,
              started_at = COALESCE(started_at, ?),
              reminder_status = 'runtime_active',
              camera_observation_status = 'runtime_active',
              next_reminder_at = NULL, updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (now, now, family_id, task_id),
        )

    def mark_task_completed(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        summary: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'completed', completion_source = 'learning_session',
              evidence_summary = ?, completed_at = COALESCE(completed_at, ?),
              ended_at = COALESCE(ended_at, ?), updated_at = ?
            WHERE family_id = ? AND id = ?
            """,
            (summary, now, now, now, family_id, task_id),
        )

    def create_or_get_report(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        task_id: str,
        session_id: str,
        course_id: str,
        course_version: str,
        learning_date: str,
        grade_code: str,
        subject: str,
        score: int,
        correct_count: int,
        independent_correct_count: int,
        hint_count: int,
        total_questions: int,
        mastery_level: str,
        summary: str,
        strengths: list[str],
        next_step: str,
        now: int,
    ) -> DatabaseRow:
        report_id = f"learn_report_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_reports(
              id, family_id, child_id, task_id, session_id, course_id,
              course_version, learning_date, grade_code, subject, score,
              correct_count, independent_correct_count, hint_count,
              total_questions, mastery_level, summary,
              strengths_json, next_step, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                report_id,
                family_id,
                child_id,
                task_id,
                session_id,
                course_id,
                course_version,
                learning_date,
                grade_code,
                subject,
                score,
                correct_count,
                independent_correct_count,
                hint_count,
                total_questions,
                mastery_level,
                summary,
                self._json(strengths),
                next_step,
                now,
            ),
        )
        return self.get_report_for_session(
            conn,
            family_id=family_id,
            session_id=session_id,
        )

    def get_report_for_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        session_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_reports
            WHERE family_id = ? AND session_id = ?
            LIMIT 1
            """
            + lock,
            (family_id, session_id),
        ).fetchone()

    def latest_report(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        subject: str | None = None,
    ) -> DatabaseRow | None:
        subject_sql = " AND subject = ?" if subject else ""
        params: list[object] = [family_id, child_id]
        if subject:
            params.append(subject)
        return conn.execute(
            f"""
            SELECT * FROM learning_reports
            WHERE family_id = ? AND child_id = ?
              {subject_sql}
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

    def list_reports(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        subject: str | None,
        cursor: tuple[int, str] | None,
        limit: int,
    ) -> tuple[list[DatabaseRow], str | None]:
        conditions = [
            "report.family_id = ?",
            "report.child_id = ?",
        ]
        params: list[object] = [family_id, child_id]
        if subject:
            conditions.append("report.subject = ?")
            params.append(subject)
        if cursor is not None:
            conditions.append(
                "(report.created_at < ? OR "
                "(report.created_at = ? AND report.id < ?))"
            )
            params.extend((cursor[0], cursor[0], cursor[1]))
        params.append(limit + 1)
        rows = conn.execute(
            f"""
            SELECT report.*, course.title AS course_title
            FROM learning_reports AS report
            JOIN learning_sessions AS session
              ON session.id = report.session_id
             AND session.family_id = report.family_id
             AND session.child_id = report.child_id
             AND session.task_id = report.task_id
             AND session.course_id = report.course_id
             AND session.course_version = report.course_version
            LEFT JOIN learning_courses AS course
              ON course.id = report.course_id
             AND course.version = report.course_version
            WHERE {' AND '.join(conditions)}
            ORDER BY report.created_at DESC, report.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = self.encode_report_cursor(
                int(last["created_at"]),
                str(last["id"]),
            )
        return page, next_cursor

    def get_report_detail(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        report_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT report.*, course.title AS course_title
            FROM learning_reports AS report
            JOIN learning_sessions AS session
              ON session.id = report.session_id
             AND session.family_id = report.family_id
             AND session.child_id = report.child_id
             AND session.task_id = report.task_id
             AND session.course_id = report.course_id
             AND session.course_version = report.course_version
            LEFT JOIN learning_courses AS course
              ON course.id = report.course_id
             AND course.version = report.course_version
            WHERE report.id = ? AND report.family_id = ?
              AND report.child_id = ?
            LIMIT 1
            """,
            (report_id, family_id, child_id),
        ).fetchone()

    def upsert_mastery_state(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        node_code: str,
        subject: str,
        grade_code: str,
        attempts: int,
        correct_count: int,
        independent_correct_count: int,
        hint_count: int,
        latest_score: int,
        mastery_level: str,
        last_practiced_at: int,
        next_review_date: str,
        course_id: str,
        course_version: str,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_mastery_states(
              family_id, child_id, node_code, subject, grade_code, attempts,
              correct_count, independent_correct_count, hint_count,
              latest_score, mastery_level, last_practiced_at,
              next_review_date, course_id, course_version, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              grade_code = VALUES(grade_code),
              attempts = attempts + VALUES(attempts),
              correct_count = correct_count + VALUES(correct_count),
              independent_correct_count = independent_correct_count + VALUES(independent_correct_count),
              hint_count = hint_count + VALUES(hint_count),
              latest_score = VALUES(latest_score),
              mastery_level = VALUES(mastery_level),
              last_practiced_at = VALUES(last_practiced_at),
              next_review_date = VALUES(next_review_date),
              course_id = VALUES(course_id),
              course_version = VALUES(course_version),
              updated_at = VALUES(updated_at)
            """,
            (
                family_id,
                child_id,
                node_code,
                subject,
                grade_code,
                attempts,
                correct_count,
                independent_correct_count,
                hint_count,
                latest_score,
                mastery_level,
                last_practiced_at,
                next_review_date,
                course_id,
                course_version,
                now,
            ),
        )
        return self.get_mastery_state(
            conn,
            family_id=family_id,
            child_id=child_id,
            node_code=node_code,
            subject=subject,
        )

    def get_mastery_state(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        node_code: str,
        subject: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_mastery_states
            WHERE family_id = ? AND child_id = ? AND node_code = ? AND subject = ?
            LIMIT 1
            """,
            (family_id, child_id, node_code, subject),
        ).fetchone()

    def add_task_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        task_id: str,
        event_type: str,
        message: str,
        payload: dict,
        now: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO task_events(
              id, family_id, task_id, event_type, message, payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"evt_{uuid.uuid4().hex}",
                family_id,
                task_id,
                event_type,
                message,
                self._json(payload),
                now,
            ),
        )

    @staticmethod
    def _catalog_release_joins() -> str:
        return """
          JOIN learning_catalog_release_items AS catalog_item
            ON catalog_item.course_id = course.id
           AND catalog_item.course_version = course.version
          JOIN learning_catalog_releases AS catalog_release
            ON catalog_release.id = catalog_item.release_id
          LEFT JOIN learning_curriculum_grade_release_pointers AS grade_pointer
            ON grade_pointer.grade_code = course.grade_code
           AND grade_pointer.release_id = catalog_release.id
           AND grade_pointer.pointer_revision >= 1
          JOIN learning_course_lesson_package_bindings AS package_binding
            ON package_binding.course_id = course.id
           AND package_binding.course_version = course.version
           AND package_binding.package_id = catalog_item.package_id
           AND package_binding.package_version = catalog_item.package_version
          JOIN learning_lesson_packages AS lesson_package
            ON lesson_package.id = package_binding.package_id
           AND lesson_package.version = package_binding.package_version
        """

    @staticmethod
    def _catalog_release_filters() -> str:
        return f"""
          AND course.quality_status = 'released'
          AND course.retired_at IS NULL
          AND catalog_item.status = 'published'
          AND catalog_item.quality_status = 'ready'
          AND catalog_item.retired_at IS NULL
          AND catalog_item.curriculum_version = course.curriculum_version
          AND catalog_item.boundary_version = course.boundary_version
          AND catalog_release.retired_at IS NULL
          AND (
            (
              catalog_release.status = 'active'
              AND catalog_release.quality_status = 'ready'
            )
            OR (
              grade_pointer.target_fingerprint IS NOT NULL
              AND grade_pointer.contract_version =
                'mira.learning.formal-publication.v1'
              AND EXISTS (
                SELECT 1
                FROM learning_curriculum_classroom_item_receipts AS formal_receipt
                JOIN learning_openmaic_runtime_classrooms AS formal_runtime
                  ON formal_runtime.id = formal_receipt.runtime_classroom_id
                 AND formal_runtime.candidate_build_item_id =
                   formal_receipt.build_item_id
                 AND formal_runtime.candidate_release_id = catalog_release.id
                 AND formal_runtime.candidate_grade_code = course.grade_code
                 AND formal_runtime.candidate_target_fingerprint =
                   grade_pointer.target_fingerprint
                 AND formal_runtime.course_id = course.id
                 AND formal_runtime.course_version = course.version
                 AND formal_runtime.package_id = lesson_package.id
                 AND formal_runtime.package_version = lesson_package.version
                 AND formal_runtime.status = 'ready'
                 AND formal_runtime.upstream_classroom_id IS NOT NULL
                 AND formal_runtime.retired_at IS NULL
                JOIN learning_formal_qwen_audio_jobs AS formal_audio
                  ON formal_audio.build_item_id = formal_receipt.build_item_id
                 AND formal_audio.runtime_classroom_id = formal_runtime.id
                 AND formal_audio.release_id = catalog_release.id
                 AND formal_audio.grade_code = course.grade_code
                 AND formal_audio.target_fingerprint =
                   grade_pointer.target_fingerprint
                 AND formal_audio.course_id = course.id
                 AND formal_audio.course_version = course.version
                 AND formal_audio.package_id = lesson_package.id
                 AND formal_audio.package_version = lesson_package.version
                 AND formal_audio.state = 'auto_validated'
                 AND formal_audio.expected_segment_count BETWEEN 1 AND 240
                 AND formal_audio.tts_attempted_count = formal_audio.expected_segment_count
                 AND formal_audio.tts_completed_count = formal_audio.expected_segment_count
                 AND formal_audio.audio_validated_count = formal_audio.expected_segment_count
                 AND formal_audio.asr_attempted_count = formal_audio.expected_segment_count
                 AND formal_audio.asr_passed_count = formal_audio.expected_segment_count
                 AND formal_audio.terminal_receipt_hash IS NOT NULL
                LEFT JOIN learning_openmaic_provider_readiness_jobs AS formal_provider
                  ON formal_provider.release_id = catalog_release.id
                 AND formal_provider.grade_code = course.grade_code
                 AND formal_provider.target_fingerprint =
                   grade_pointer.target_fingerprint
                WHERE formal_receipt.release_id = catalog_release.id
                  AND formal_receipt.grade_code = course.grade_code
                  AND formal_receipt.target_fingerprint =
                    grade_pointer.target_fingerprint
                  AND formal_receipt.course_id = course.id
                  AND formal_receipt.course_version = course.version
                  AND formal_receipt.package_id = lesson_package.id
                  AND formal_receipt.package_version = lesson_package.version
                  AND formal_receipt.classroom_status = 'passed'
                  AND formal_receipt.tts_status = 'passed'
                  AND formal_receipt.asr_roundtrip_status = 'passed'
                  AND formal_receipt.conversation_provider_status = 'passed'
                  AND formal_receipt.auto_validated = 1
                  AND formal_receipt.publication_status = 'published'
                  {current_formal_validation_authority_sql(
                      receipt_alias="formal_receipt",
                      provider_alias="formal_provider",
                  )}
              )
            )
          )
          AND lesson_package.status = 'published'
          AND lesson_package.retired_at IS NULL
          AND NOT EXISTS (
            SELECT 1
            FROM learning_lesson_package_assets AS required_package_asset
            LEFT JOIN learning_media_assets AS required_asset
              ON required_asset.id = required_package_asset.asset_id
            WHERE required_package_asset.package_id = lesson_package.id
              AND required_package_asset.package_version = lesson_package.version
              AND required_package_asset.required_asset = 1
              AND (
                required_asset.id IS NULL
                OR required_asset.status IS NULL
                OR required_asset.status <> 'ready'
                OR required_asset.scan_status IS NULL
                OR required_asset.scan_status <> 'passed'
                OR required_asset.moderation_status IS NULL
                OR required_asset.moderation_status <> 'passed'
                OR required_asset.transcode_status IS NULL
                OR required_asset.transcode_status NOT IN ('passed', 'not_required')
                OR NOT EXISTS (
                  SELECT 1
                  FROM learning_media_asset_variants AS required_variant
                  WHERE required_variant.asset_id = required_asset.id
                    AND required_variant.status = 'ready'
                )
                OR NOT EXISTS (
                  SELECT 1
                  FROM learning_media_quality_reviews AS required_review
                  WHERE required_review.asset_id = required_asset.id
                    AND required_review.required_review = 1
                    AND required_review.status = 'approved'
                )
                OR EXISTS (
                  SELECT 1
                  FROM learning_media_quality_reviews AS required_review
                  WHERE required_review.asset_id = required_asset.id
                    AND required_review.required_review = 1
                    AND required_review.status <> 'approved'
                )
              )
          )
        """

    @staticmethod
    def parse_json(value: object, fallback):
        if isinstance(value, (dict, list)):
            return value
        if not isinstance(value, str) or not value.strip():
            return fallback
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return fallback

    @staticmethod
    def encode_report_cursor(created_at: int, report_id: str) -> str:
        raw = json.dumps([created_at, report_id], separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def decode_report_cursor(value: str | None) -> tuple[int, str] | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            padding = "=" * (-len(text) % 4)
            decoded = json.loads(
                base64.urlsafe_b64decode(text + padding).decode("utf-8")
            )
            if (
                not isinstance(decoded, list)
                or len(decoded) != 2
                or not isinstance(decoded[0], int)
                or decoded[0] < 0
                or not isinstance(decoded[1], str)
                or not decoded[1]
            ):
                raise ValueError
            return decoded[0], decoded[1]
        except (
            ValueError,
            TypeError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            raise ValueError("invalid report cursor") from exc

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
