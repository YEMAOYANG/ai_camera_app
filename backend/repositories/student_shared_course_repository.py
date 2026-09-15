"""Student access to already published shared lessons, without production work."""
from __future__ import annotations

import hashlib
import json

from core.errors import ApiError
from integrations.openmaic_formal_media import compatible_preparation_target
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)


def shared_course_inventory(conn, *, family_id, child_id, grade_code, grade_selection_revision):
    # Authenticate the supplied scope against the current child, even for callers
    # outside StudentLearningService. No child preparation is created by a read.
    child = conn.execute(
        "SELECT id FROM children WHERE family_id = ? AND id = ? AND grade_code = ? "
        "AND grade_selection_revision = ? AND grade_selection_revision >= 1 LIMIT 1",
        (family_id, child_id, grade_code, grade_selection_revision),
    ).fetchone()
    if child is None:
        return {}
    try:
        target = build_preparation_target(grade_code)
    except (KeyError, ValueError):
        return {}
    # Local import avoids the existing inventory -> LearningRepository asset
    # gate dependency. This is the same full published/media gate as supply.
    from repositories.course_supply_inventory import published_supply
    return {
        (str(row['course_id']), str(row['course_version'])): row
        for row in published_supply(conn, target).values()
    }


def shared_course_rows(conn, *, family_id, child_id, grade_code,
                       grade_selection_revision, subject=None, favorite_only=False,
                       course_id=None, course_version=None):
    inventory = shared_course_inventory(
        conn, family_id=family_id, child_id=child_id, grade_code=grade_code,
        grade_selection_revision=grade_selection_revision,
    )
    keys = [key for key in inventory
            if (course_id is None or key[0] == course_id)
            and (course_version is None or key[1] == course_version)]
    if not keys:
        return []
    identities = ' OR '.join('(course.id = ? AND course.version = ?)' for _ in keys)
    params = [family_id, child_id, family_id, child_id, family_id, child_id,
              grade_code, *(value for key in keys for value in key)]
    subject_sql = ''
    if subject is not None:
        subject_sql = ' AND course.subject = ?'
        params.append(subject)
    favorite_sql = ' AND favorite.course_id IS NOT NULL' if favorite_only else ''
    return list(conn.execute(
        f"""SELECT course.*, favorite.course_id AS favorite_course_id,
          (SELECT MAX(task.scheduled_date) FROM tasks AS task
           WHERE task.family_id = ? AND task.child_id = ? AND task.type = 'learning'
             AND task.learning_course_id = course.id
             AND task.learning_course_version = course.version) AS last_learning_date,
          (SELECT MAX(task.updated_at) FROM tasks AS task
           WHERE task.family_id = ? AND task.child_id = ? AND task.type = 'learning'
             AND task.learning_course_id = course.id
             AND task.learning_course_version = course.version) AS last_task_activity_at
        FROM learning_courses AS course
        LEFT JOIN student_learning_course_favorites AS favorite
          ON favorite.family_id = ? AND favorite.child_id = ?
          AND favorite.course_id = course.id AND favorite.course_version = course.version
        WHERE course.grade_code = ? AND ({identities})
          AND course.status = 'published' AND course.quality_status = 'released'
          AND course.content_origin = 'openmaic_generated' AND course.retired_at IS NULL
          {subject_sql} {favorite_sql}
        ORDER BY course.published_at DESC, course.id""", params,
    ).fetchall())


def claim_published_shared_course(conn, *, database, child, course, now):
    """Attach only this child's follower to a verified, immutable shared build.

    The existing progressive-plan package and Runtime binders remain the launch
    authority. This does not advance a production owner, create a Provider job,
    supersede another plan or change the grade pointer.
    """
    inventory = shared_course_inventory(
        conn, family_id=child['family_id'], child_id=child['id'],
        grade_code=child['grade_code'],
        grade_selection_revision=int(child['grade_selection_revision']),
    )
    available = inventory.get((str(course['id']), str(course['version'])))
    if available is None:
        return None  # An ordinary child-plan/active-pointer lesson needs no claim.
    source = conn.execute(
        """SELECT owner.id, owner.catalog_build_id, owner.catalog_release_id,
          owner.target_fingerprint, owner.target_spec_json
        FROM learning_curriculum_preparation_plans AS owner
        JOIN learning_catalog_build_items AS item
          ON item.build_job_id = owner.catalog_build_id
          AND item.release_id = owner.catalog_release_id AND item.grade_code = owner.grade_code
        JOIN learning_catalog_build_jobs AS build ON build.id = item.build_job_id
          AND build.release_id = item.release_id AND build.target_spec_json = owner.target_spec_json
        WHERE item.id = ? AND owner.library_target_fingerprint = ?
          AND owner.target_fingerprint = owner.library_target_fingerprint
          AND owner.family_id IS NULL AND owner.child_id IS NULL
          AND owner.grade_selection_revision = 0 AND owner.grade_code = ?
        LIMIT 1 FOR UPDATE""",
        (available['build_item_id'], available['target_fingerprint'], child['grade_code']),
    ).fetchone()
    try:
        target = json.loads(source['target_spec_json']) if source else None
        fingerprint = preparation_target_fingerprint(target) if target else None
        if (source is None or fingerprint != source['target_fingerprint']
                or not compatible_preparation_target(target, build_preparation_target(child['grade_code']))):
            raise ValueError('shared publication authority changed')
        digest = hashlib.sha256(f"grade-build:{fingerprint}".encode()).hexdigest()[:24]
        if (source['catalog_build_id'] != f'catalog_build_{digest}'
                or source['catalog_release_id'] != f'catalog_release_{digest}'):
            raise ValueError('shared build identity changed')
        revision = int(child['grade_selection_revision'])
        request_digest = hashlib.sha256(f"{child['id']}|{revision}|{fingerprint}".encode()).hexdigest()
        repository = LearningCurriculumPreparationRepository(database)
        plan, _ = repository.reserve_plan(
            conn, family_id=child['family_id'], child_id=child['id'],
            grade_code=child['grade_code'],
            school_year_start_year=int(child['grade_school_year_start']),
            grade_selection_revision=revision, target=target, target_fingerprint=fingerprint,
            request_id=f'grade-prep:{request_digest}',
            shared_build_request_id=f'grade-build:{fingerprint}', now=now,
        )
        if plan.get('superseded_at') is not None or plan['status'] not in {'queued', 'running', 'ready', 'failed'}:
            raise ValueError('child publication claim is no longer current')
        if (plan.get('catalog_build_id') not in (None, source['catalog_build_id'])
                or plan.get('catalog_release_id') not in (None, source['catalog_release_id'])):
            raise ValueError('child publication claim identity changed')
        if plan.get('catalog_build_id') is None or plan.get('catalog_release_id') is None:
            # No content or publication counters are synthesized. Keep queued
            # state schema-valid; claim_next excludes child followers whenever
            # this exact library production owner exists, even after they are due.
            conn.execute(
                "UPDATE learning_curriculum_preparation_plans SET catalog_build_id = ?, "
                "catalog_release_id = ?, updated_at = ? "
                "WHERE id = ? AND status = 'queued' AND stage = 'queued' "
                "AND lease_token IS NULL AND superseded_at IS NULL "
                "AND catalog_build_id IS NULL AND catalog_release_id IS NULL",
                (source['catalog_build_id'], source['catalog_release_id'], now, plan['id']),
            )
            plan = repository.get_plan(conn, plan['id'], for_update=True)
        if (plan is None or plan.get('catalog_build_id') != source['catalog_build_id']
                or plan.get('catalog_release_id') != source['catalog_release_id']):
            raise ValueError('child publication claim could not be attached')
        return plan
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError('learning_classroom_release_changed', '正式课程刚刚更新，请重新打开这节课', 409) from exc
