"""Exact published fine-course authority, retained across supplementary batches.

A new batch never invalidates another registered lesson. Each lesson still needs
its own immutable binding, formal publication, live Runtime, audio/ASR and media.
Retired content stays unavailable. New study stays within the child's grade;
an exact already-started lower-grade session can still resume its classroom.
"""
from core.errors import ApiError
from content.progressive_curriculum import CURRICULUM_VERSION


def progressive_formal_authority(conn, *, database, child, course, runtime_classroom_id=None):
    if course.get('curriculum_version') != CURRICULUM_VERSION:
        return None
    from repositories.learning_repository import _student_visible_course_sql
    from repositories.progressive_learning_repository import ProgressiveLearningRepository
    from services.progressive_learning_service import ProgressiveLearningService
    try:
        binding = ProgressiveLearningService(ProgressiveLearningRepository(database)).binding_for_course(conn, course=course)
    except (ApiError, ValueError, KeyError):
        return None
    if binding is None:
        return None
    grade = str(child.get('grade_code') or '')
    if grade not in {f'primary_{number}' for number in range(1, 7)} or course['grade_code'] > grade:
        return None
    resume_only = course['grade_code'] != grade
    # A prerequisite declaration no longer grants cross-grade study. Preserve
    # only an existing session's exact child/course/package/runtime identity.
    resume_gate = """AND EXISTS (
        SELECT 1 FROM learning_sessions AS prior_session
        JOIN tasks AS prior_task ON prior_task.id = prior_session.task_id
          AND prior_task.family_id = prior_session.family_id
          AND prior_task.child_id = prior_session.child_id
          AND prior_task.learning_course_id = prior_session.course_id
          AND prior_task.learning_course_version = prior_session.course_version
        LEFT JOIN learning_student_formal_session_bindings AS prior_authority
          ON prior_authority.learning_session_id = prior_session.id
        WHERE prior_session.family_id = fine_child.family_id
          AND prior_session.child_id = fine_child.id
          AND prior_session.course_id = course.id AND prior_session.course_version = course.version
          AND prior_session.status = 'in_progress' AND prior_session.completed_at IS NULL
          AND prior_task.status NOT IN ('completed', 'confirmed', 'awaiting_parent_confirmation',
                                        'rejected', 'expired', 'cancelled')
          AND (prior_session.lesson_package_id IS NULL OR (
            prior_session.lesson_package_id = fine_package.id
            AND prior_session.lesson_package_version = fine_package.version
            AND prior_session.lesson_package_content_hash = fine_package.public_content_hash))
          AND (prior_authority.learning_session_id IS NULL OR (
            prior_authority.family_id = fine_child.family_id AND prior_authority.child_id = fine_child.id
            AND prior_authority.course_id = course.id AND prior_authority.course_version = course.version
            AND prior_authority.package_id = fine_package.id AND prior_authority.package_version = fine_package.version
            AND prior_authority.package_content_hash = fine_package.public_content_hash
            AND prior_authority.runtime_classroom_id = fine_runtime.id
            AND prior_authority.release_id = fine_runtime.candidate_release_id
            AND prior_authority.target_fingerprint = fine_runtime.candidate_target_fingerprint))
    )""" if resume_only else ""
    gate = _student_visible_course_sql(child_alias='fine_child', require_available_package_assets=True,
                                      allow_progressive_publication=True, exact_runtime_alias='fine_runtime')
    runtime_filter = "AND fine_runtime.id = ?" if runtime_classroom_id is not None else ""
    return conn.execute(f"""
        SELECT 'progressive_course' AS authority_kind, {int(resume_only)} AS resume_only,
          NULL AS pointer_history_id, NULL AS pointer_revision,
          NULL AS preparation_plan_id, fine_child.grade_selection_revision,
          fine_runtime.candidate_release_id AS release_id,
          fine_runtime.candidate_target_fingerprint AS target_fingerprint,
          'mira.learning.formal-publication.v1' AS publication_contract_version,
          fine_runtime.candidate_binding_contract_version AS runtime_binding_contract_version,
          fine_runtime.candidate_build_item_id AS build_item_id,
          course.id AS course_id, course.version AS course_version,
          course.grade_code AS binding_grade_code,
          fine_package.id AS package_id, fine_package.version AS package_version,
          fine_package.public_content_hash AS package_content_hash,
          fine_runtime.id AS runtime_classroom_id, fine_runtime.upstream_classroom_id
        FROM learning_courses AS course
        JOIN children AS fine_child ON fine_child.id = ? AND fine_child.family_id = ?
          AND fine_child.grade_code = ? AND fine_child.grade_selection_revision = ?
          AND fine_child.grade_selection_revision >= 1
        JOIN learning_openmaic_runtime_classrooms AS fine_runtime
          ON fine_runtime.course_id = course.id AND fine_runtime.course_version = course.version
        JOIN learning_lesson_packages AS fine_package
          ON fine_package.id = fine_runtime.package_id AND fine_package.version = fine_runtime.package_version
          AND fine_package.course_id = course.id AND fine_package.course_version = course.version
        WHERE course.id = ? AND course.version = ? AND course.status = 'published'
          AND course.quality_status = 'released' AND course.content_origin = 'openmaic_generated'
          AND course.retired_at IS NULL AND {gate} {resume_gate} {runtime_filter}
        ORDER BY fine_runtime.created_at DESC LIMIT 1
    """, (child['id'], child['family_id'], grade, int(child.get('grade_selection_revision') or 0),
          course['id'], course['version'],
          *((runtime_classroom_id,) if runtime_classroom_id is not None else ()))).fetchone()
