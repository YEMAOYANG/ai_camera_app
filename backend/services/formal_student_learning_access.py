from __future__ import annotations

import re
from typing import Mapping

from core.errors import ApiError
from repositories.formal_student_runtime_gate import current_formal_runtime_sql
from schemas.education import grade_definition_from_row


FORMAL_STUDENT_GRADE_CODES = frozenset({"primary_1"})
FORMAL_PUBLICATION_CONTRACT_VERSION = "mira.learning.formal-publication.v1"
FORMAL_COURSE_COUNT = 30


def assert_formal_student_grade_open(child: Mapping[str, object]) -> str:
    grade = grade_definition_from_row(child)
    if grade is None or grade.education_stage_code != "primary":
        raise ApiError(
            "student_learning_primary_only",
            "学生学习空间仅面向已开放的小学年级",
            409,
        )
    if grade.code not in FORMAL_STUDENT_GRADE_CODES:
        raise ApiError(
            "student_learning_grade_not_open",
            "该年级正式课程尚未开放",
            409,
        )
    return grade.code


def assert_formal_student_workspace_open(child: Mapping[str, object]) -> str:
    """Allow the student shell before a whole catalog release is complete.

    Grade selection revision is the child-scoped authority for every rolling
    catalog query.  A zero revision predates an explicit saved grade selection
    and must not be allowed to see either a candidate or shared active release.
    """

    grade_code = assert_formal_student_grade_open(child)
    if int(child.get("grade_selection_revision") or 0) < 1:
        raise _release_not_ready()
    return grade_code


def assert_formal_student_release_ready(
    conn,
    child: Mapping[str, object],
    *,
    for_update: bool = False,
) -> None:
    grade_code = assert_formal_student_workspace_open(child)
    if not _formal_student_release_is_ready(
        _load_active_formal_student_release(
            conn,
            grade_code=grade_code,
            for_update=for_update,
        ),
        grade_code=grade_code,
    ):
        raise _release_not_ready()


def formal_student_release_available(
    conn,
    child: Mapping[str, object],
) -> bool:
    """Return whether this child can use the currently active formal release."""
    try:
        grade_code = assert_formal_student_workspace_open(child)
    except ApiError:
        return False
    return _formal_student_release_is_ready(
        _load_active_formal_student_release(
            conn,
            grade_code=grade_code,
            for_update=False,
        ),
        grade_code=grade_code,
    )


def _load_active_formal_student_release(
    conn,
    *,
    grade_code: str,
    for_update: bool,
):
    lock_clause = " FOR UPDATE" if for_update else ""
    return conn.execute(
        f"""
        SELECT plan.*
        FROM learning_curriculum_preparation_plans AS plan
        JOIN learning_curriculum_grade_release_pointers AS pointer
          ON pointer.grade_code = plan.grade_code
          AND pointer.pointer_revision >= 1
          AND pointer.target_fingerprint = plan.target_fingerprint
          AND pointer.contract_version = plan.formal_contract_version
          AND pointer.release_id = plan.catalog_release_id
          AND pointer.history_id = plan.formal_publication_history_id
        JOIN learning_curriculum_grade_release_history AS history
          ON history.id = pointer.history_id
          AND history.grade_code = pointer.grade_code
          AND history.pointer_revision = pointer.pointer_revision
          AND history.target_fingerprint = pointer.target_fingerprint
          AND history.contract_version = pointer.contract_version
          AND history.release_id = pointer.release_id
          AND history.activation_source = 'formal_publication'
          AND history.publication_receipt_hash =
            plan.formal_publication_receipt_hash
          AND history.superseded_at IS NULL
        WHERE plan.grade_code = ?
          AND plan.status = 'ready' AND plan.stage = 'completed'
          AND plan.superseded_at IS NULL
          AND (
            SELECT COUNT(*)
            FROM learning_catalog_release_items AS current_release_item
            WHERE current_release_item.release_id = plan.catalog_release_id
              AND current_release_item.grade_code = plan.grade_code
              AND current_release_item.status = 'published'
              AND current_release_item.quality_status = 'ready'
              AND current_release_item.retired_at IS NULL
          ) = plan.total_course_count
          AND NOT EXISTS (
            SELECT 1
            FROM learning_catalog_release_items AS current_release_item
            WHERE current_release_item.release_id = plan.catalog_release_id
              AND current_release_item.grade_code = plan.grade_code
              AND current_release_item.status = 'published'
              AND current_release_item.quality_status = 'ready'
              AND current_release_item.retired_at IS NULL
              AND NOT EXISTS (
                SELECT 1
                FROM learning_openmaic_runtime_classrooms AS current_runtime
                WHERE current_runtime.candidate_release_id =
                        current_release_item.release_id
                  AND current_runtime.candidate_grade_code =
                        current_release_item.grade_code
                  AND current_runtime.candidate_target_fingerprint =
                        plan.target_fingerprint
                  AND current_runtime.course_id = current_release_item.course_id
                  AND current_runtime.course_version =
                        current_release_item.course_version
                  AND current_runtime.package_id = current_release_item.package_id
                  AND current_runtime.package_version =
                        current_release_item.package_version
                  AND current_runtime.status = 'ready'
                  AND current_runtime.upstream_classroom_id IS NOT NULL
                  AND current_runtime.retired_at IS NULL
                  {current_formal_runtime_sql(runtime_alias="current_runtime")}
              )
          )
        ORDER BY plan.retry_ordinal DESC, plan.created_at DESC
        LIMIT 1
        """ + lock_clause,
        (grade_code,),
    ).fetchone()


def _formal_student_release_is_ready(
    plan: Mapping[str, object] | None,
    *,
    grade_code: str,
) -> bool:
    receipt = str((plan or {}).get("formal_publication_receipt_hash") or "")
    target_fingerprint = str((plan or {}).get("target_fingerprint") or "")
    total_count = int((plan or {}).get("total_course_count") or 0)
    return bool(
        plan is not None
        and str(plan.get("grade_code") or "") == grade_code
        and str(plan.get("status") or "") == "ready"
        and str(plan.get("stage") or "") == "completed"
        and int(plan.get("progress_percent") or 0) == 100
        and total_count == FORMAL_COURSE_COUNT
        and int(plan.get("ready_course_count") or 0) == total_count
        and int(plan.get("failed_course_count") or 0) == 0
        and int(plan.get("content_target_count") or 0) == total_count
        and int(plan.get("content_candidate_count") or 0) == total_count
        and int(plan.get("content_failed_count") or 0) == 0
        and int(plan.get("classroom_ready_count") or 0) == total_count
        and int(plan.get("speech_ready_count") or 0) == total_count
        and int(plan.get("validation_ready_count") or 0) == total_count
        and int(plan.get("published_course_count") or 0) == total_count
        and int(plan.get("formal_ready_at") or 0) > 0
        and int(plan.get("completed_at") or 0) > 0
        and bool(str(plan.get("catalog_release_id") or ""))
        and re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is not None
        and str(plan.get("formal_contract_version") or "")
        == FORMAL_PUBLICATION_CONTRACT_VERSION
        and bool(str(plan.get("formal_publication_history_id") or ""))
        and re.fullmatch(r"[0-9a-f]{64}", receipt) is not None
    )


def _release_not_ready() -> ApiError:
    return ApiError(
        "student_learning_release_not_ready",
        "该年级正式课程尚未准备完成",
        409,
    )
