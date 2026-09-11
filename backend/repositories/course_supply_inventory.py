"""Read reusable, currently playable supply without changing frozen builds."""
from __future__ import annotations

from typing import Mapping

from repositories.formal_student_runtime_gate import (
    current_formal_runtime_sql,
    current_formal_validation_authority_sql,
)
from repositories.learning_repository import _student_required_package_assets_sql
from services.learning_curriculum_preparation_contract import (
    compatible_preparation_scope_sql,
    preparation_target_fingerprint,
)


def inherited_scope_requests(conn, target: Mapping) -> list[dict]:
    """Read the newest compatible owner's explicit scope after an upgrade.

    This is display-only: it neither creates a new owner nor enables requests.
    It avoids replacing an existing ready library with an empty preparation
    screen merely because the new creation policy has a new fingerprint.
    """
    return inherited_scope_request_state(conn, target) or []


def inherited_scope_request_state(conn, target: Mapping) -> list[dict] | None:
    """None means no historical owner; [] means its scope was explicitly empty.

    Select the newest owner before filtering enabled requests. Otherwise an
    empty/newly disabled scope could accidentally reveal an older wider one.
    """
    scope_sql, params = compatible_preparation_scope_sql(
        target, target_column='owner.target_spec_json',
        fingerprint_column='owner.target_fingerprint',
    )
    rows = conn.execute(
        f"""SELECT owner.id AS source_plan_id, request.subject, request.skill_id,
          request.variant_ordinal, request.priority, request.purpose, request.enabled,
          NULL AS build_item_id, NULL AS publication_status,
          NULL AS reason_code, NULL AS runtime_status, FALSE AS ready
        FROM learning_curriculum_preparation_plans AS owner
        LEFT JOIN learning_course_supply_requests AS request
          ON request.target_fingerprint = owner.library_target_fingerprint
        WHERE owner.grade_code = ? AND {scope_sql}
          AND owner.target_fingerprint <> ?
        ORDER BY owner.created_at DESC, owner.id DESC, request.priority,
          request.subject, request.skill_id, request.variant_ordinal""",
        (target['gradeCode'], *params, preparation_target_fingerprint(target)),
    ).fetchall()
    if not rows:
        return None
    source = rows[0]['source_plan_id']
    desired = {(item['subject'], item['skillId'], int(item['variantOrdinal']))
               for item in target['courseTargets']}
    return [dict(row) for row in rows if row['source_plan_id'] == source and row.get('enabled', True)
            and row['subject'] is not None
            and (row['subject'], row['skill_id'], int(row['variant_ordinal'])) in desired]


def published_supply(conn, target: Mapping) -> dict[tuple[str, str, int], dict]:
    """Resolve exact compatible published slots, preferring this target.

    Compatibility applies to immutable target/hash pairs, not just a matching
    skill name. All readiness checks are live: a withdrawn package, Runtime or
    required media asset stops satisfying supply on the next read. This query
    is also used before content claims, so a policy upgrade can reuse an old
    published lesson without launching its replacement automatically.
    """
    grade = str(target['gradeCode'])
    fingerprint = preparation_target_fingerprint(target)
    scope_sql, scope_params = compatible_preparation_scope_sql(
        target, target_column='build.target_spec_json',
        fingerprint_column='receipt.target_fingerprint',
    )
    rows = conn.execute(
        f"""SELECT item.subject, item.skill_id, item.variant_ordinal,
          item.id AS build_item_id, receipt.course_id, receipt.course_version,
          receipt.target_fingerprint, receipt.published_at,
          runtime.id AS runtime_classroom_id
        FROM learning_catalog_build_items AS item
        JOIN learning_catalog_build_jobs AS build ON build.id = item.build_job_id
        JOIN learning_curriculum_preparation_plans AS owner
          ON owner.catalog_build_id = build.id
          AND owner.library_target_fingerprint IS NOT NULL
          AND owner.grade_code = item.grade_code
          AND owner.target_fingerprint = owner.library_target_fingerprint
        JOIN learning_curriculum_classroom_item_receipts AS receipt
          ON receipt.build_item_id = item.id AND receipt.release_id = item.release_id
          AND receipt.grade_code = item.grade_code
          AND receipt.target_fingerprint = owner.target_fingerprint
          AND receipt.course_id = item.course_id AND receipt.course_version = item.course_version
        JOIN learning_courses AS course
          ON course.id = receipt.course_id AND course.version = receipt.course_version
          AND course.grade_code = receipt.grade_code
          AND course.status = 'published' AND course.quality_status = 'released'
          AND course.retired_at IS NULL
        JOIN learning_catalog_release_items AS release_item
          ON release_item.release_id = receipt.release_id
          AND release_item.grade_code = receipt.grade_code
          AND release_item.course_id = receipt.course_id
          AND release_item.course_version = receipt.course_version
          AND release_item.package_id = receipt.package_id
          AND release_item.package_version = receipt.package_version
          AND release_item.status = 'published' AND release_item.quality_status = 'ready'
          AND release_item.retired_at IS NULL
          AND release_item.curriculum_version = course.curriculum_version
          AND release_item.boundary_version = course.boundary_version
        JOIN learning_catalog_releases AS catalog_release
          ON catalog_release.id = receipt.release_id AND catalog_release.retired_at IS NULL
          AND catalog_release.curriculum_version = course.curriculum_version
        JOIN learning_course_lesson_package_bindings AS binding
          ON binding.course_id = receipt.course_id AND binding.course_version = receipt.course_version
          AND binding.package_id = receipt.package_id AND binding.package_version = receipt.package_version
        JOIN learning_lesson_packages AS package
          ON package.id = receipt.package_id AND package.version = receipt.package_version
          AND package.course_id = receipt.course_id AND package.course_version = receipt.course_version
          AND package.status = 'published' AND package.retired_at IS NULL
        JOIN learning_openmaic_runtime_classrooms AS runtime
          ON runtime.id = receipt.runtime_classroom_id
          AND runtime.candidate_build_item_id = item.id
          AND runtime.candidate_release_id = receipt.release_id
          AND runtime.candidate_grade_code = receipt.grade_code
          AND runtime.candidate_target_fingerprint = receipt.target_fingerprint
          AND runtime.course_id = receipt.course_id AND runtime.course_version = receipt.course_version
          AND runtime.package_id = receipt.package_id AND runtime.package_version = receipt.package_version
          AND runtime.status = 'ready' AND runtime.upstream_classroom_id IS NOT NULL
          AND runtime.retired_at IS NULL
          {current_formal_runtime_sql(runtime_alias='runtime')}
        JOIN learning_formal_qwen_audio_jobs AS audio
          ON audio.build_item_id = item.id AND audio.runtime_classroom_id = runtime.id
          AND audio.release_id = receipt.release_id AND audio.grade_code = receipt.grade_code
          AND audio.target_fingerprint = receipt.target_fingerprint
          AND audio.course_id = receipt.course_id AND audio.course_version = receipt.course_version
          AND audio.package_id = receipt.package_id AND audio.package_version = receipt.package_version
          AND audio.state = 'auto_validated' AND audio.expected_segment_count BETWEEN 1 AND 240
          AND audio.tts_attempted_count = audio.expected_segment_count
          AND audio.tts_completed_count = audio.expected_segment_count
          AND audio.audio_validated_count = audio.expected_segment_count
          AND audio.asr_attempted_count = audio.expected_segment_count
          AND audio.asr_passed_count = audio.expected_segment_count
          AND audio.terminal_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
        LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
          ON provider.release_id = receipt.release_id AND provider.grade_code = receipt.grade_code
          AND provider.target_fingerprint = receipt.target_fingerprint
        WHERE item.grade_code = ? AND {scope_sql}
          AND receipt.classroom_status = 'passed' AND receipt.tts_status = 'passed'
          AND receipt.asr_roundtrip_status = 'passed' AND receipt.auto_validated = 1
          AND receipt.publication_status = 'published'
          AND receipt.publication_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
          {current_formal_validation_authority_sql(receipt_alias='receipt', provider_alias='provider')}
          AND {_student_required_package_assets_sql(package_alias='package')}
        ORDER BY (receipt.target_fingerprint = ?) DESC, receipt.published_at DESC, item.id""",
        (grade, *scope_params, fingerprint),
    ).fetchall()
    desired = {(item['subject'], item['skillId'], int(item['variantOrdinal']))
               for item in target['courseTargets']}
    result = {}
    for row in rows:
        key = (row['subject'], row['skill_id'], int(row['variant_ordinal']))
        if key in desired:
            result.setdefault(key, dict(row))
    return result
