from __future__ import annotations

import json
import re

from repositories.course_supply_inventory import published_supply
from services.learning_curriculum_preparation_contract import preparation_target_fingerprint


def requested_supply(conn, build):
    """None means legacy batch; an empty mapping means deliberately no work."""
    if not hasattr(conn, 'execute'):
        # Pure inventory/audit callers do not consult the production request table.
        return None
    raw = build.get('target_spec_json')
    target = json.loads(raw) if isinstance(raw, str) else raw
    fingerprint = preparation_target_fingerprint(target)
    owner = conn.execute(
        'SELECT id FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ? AND grade_code = ?',
        (fingerprint, target['gradeCode']),
    ).fetchone()
    if owner is None:
        return None
    rows = conn.execute(
        """SELECT subject, skill_id, variant_ordinal, priority
        FROM learning_course_supply_requests WHERE target_fingerprint = ? AND enabled = TRUE""",
        (fingerprint,),
    ).fetchall()
    ready = published_supply(conn, target)
    return {(r['subject'], r['skill_id'], r['variant_ordinal']): r['priority'] for r in rows
            if (r['subject'], r['skill_id'], int(r['variant_ordinal'])) not in ready}


def filter_requested_supply(rows, requested):
    if requested is None:
        return list(rows)
    result = []
    for row in rows:
        key = (row['subject'], row['skill_id'], row['variant_ordinal'])
        if key in requested:
            result.append({**row, '_supply_priority': requested[key]})
    return result


def record_supply_incident(conn, *, item_id, stage, reason, now, runtime_id=None):
    conn.execute(
        """INSERT INTO learning_course_supply_incidents
        (build_item_id, stage, reason_code, blocked_at, last_observed_at, failure_runtime_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
          resolved_at = IF(failure_runtime_id <=> VALUES(failure_runtime_id), resolved_at, NULL),
          failure_runtime_id = VALUES(failure_runtime_id),
          stage = VALUES(stage), reason_code = VALUES(reason_code),
          last_observed_at = VALUES(last_observed_at)""",
        (item_id, stage, reason, now, now, runtime_id),
    )


def _has_verified_content_recovery(row):
    """A completed Host recovery resolves content blocking before publication."""
    return bool(
        row.get('content_status') == 'course_ready'
        and row.get('content_gate_status') == 'passed'
        and type(row.get('content_gate_passed_at')) is int
        and row['content_gate_passed_at'] > 0
        and re.fullmatch(r'[0-9a-f]{64}', str(row.get('content_receipt_hash') or ''))
        and row.get('verified_course_status') == 'validated'
        and row.get('verified_course_retired_at') is None
    )


def observe_supply_incidents(conn, *, build_id, now):
    """Retain terminal evidence; observing a failure never authorizes a retry."""
    build = conn.execute('SELECT target_spec_json FROM learning_catalog_build_jobs WHERE id = ?', (build_id,)).fetchone()
    target = json.loads(build['target_spec_json']) if build else None
    available = published_supply(conn, target) if target else {}
    rows = conn.execute(
        """SELECT item.id, item.subject, item.skill_id, item.variant_ordinal,
          item.status AS content_status, item.content_gate_status,
          item.content_gate_passed_at, item.content_receipt_hash,
          verified_course.status AS verified_course_status,
          verified_course.retired_at AS verified_course_retired_at,
          item.attempt_count, item.error_code AS content_error,
          runtime.id AS runtime_id, runtime.status AS runtime_status, runtime.quality_status,
          runtime.error_code AS runtime_error, audio.state AS audio_state,
          receipt.publication_status
        FROM learning_catalog_build_items AS item
        JOIN learning_curriculum_preparation_plans AS owner
          ON owner.catalog_build_id = item.build_job_id
          AND owner.library_target_fingerprint IS NOT NULL
        LEFT JOIN learning_courses AS verified_course
          ON verified_course.id = item.course_id AND verified_course.version = item.course_version
          AND verified_course.generation_request_id = item.active_generation_request_id
        LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
          ON runtime.candidate_build_item_id = item.id
          AND NOT EXISTS (SELECT 1 FROM learning_openmaic_runtime_classrooms AS newer
            WHERE newer.candidate_build_item_id = item.id
              AND (newer.created_at > runtime.created_at
                OR (newer.created_at = runtime.created_at AND newer.id > runtime.id)))
        LEFT JOIN learning_formal_qwen_audio_jobs AS audio ON audio.build_item_id = item.id
        LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt ON receipt.build_item_id = item.id
        WHERE item.build_job_id = ?""",
        (build_id,),
    ).fetchall()
    for row in rows:
        key = (row['subject'], row['skill_id'], int(row['variant_ordinal']))
        if key in available:
            conn.execute('UPDATE learning_course_supply_incidents SET resolved_at = ? WHERE build_item_id = ? AND resolved_at IS NULL', (now, row['id']))
            continue
        if _has_verified_content_recovery(row):
            # Requiring publication to clear this particular incident deadlocks
            # Runtime admission, which correctly excludes unresolved incidents.
            # Keep the failed evidence and resolve only its now-passed content
            # validation condition; later classroom/media failures stay fenced.
            conn.execute("UPDATE learning_course_supply_incidents SET resolved_at = ? "
                "WHERE build_item_id = ? AND stage = 'content' "
                "AND reason_code = 'preparation_content_validation_failed' "
                "AND failure_runtime_id IS NULL AND resolved_at IS NULL", (now,row['id']))
        if row['publication_status'] == 'published':
            stage, reason = 'availability', 'published_course_unavailable'
        elif row['runtime_status'] == 'failed' or row['quality_status'] == 'quarantined':
            stage, reason = 'classroom', row['runtime_error'] or 'classroom_failed'
        elif row['audio_state'] in {'failed', 'ambiguous'}:
            stage, reason = 'speech', 'speech_' + row['audio_state']
        elif row['content_status'] == 'failed' and not (
            row['attempt_count'] == 1 and row['content_gate_status'] == 'failed_deterministic'
        ):
            stage, reason = 'content', row['content_error'] or 'content_failed'
        else:
            continue
        record_supply_incident(conn, item_id=row['id'], stage=stage, reason=reason, now=now,
                               runtime_id=row['runtime_id'])
    counts = conn.execute(
        """SELECT COUNT(*) AS blocked,
          SUM(item.content_phase = 'course_ready') AS blocked_ready
        FROM learning_course_supply_incidents AS incident
        JOIN learning_catalog_build_items AS item ON item.id = incident.build_item_id
        WHERE item.build_job_id = ? AND incident.resolved_at IS NULL""", (build_id,),
    ).fetchone()
    return {'blocked': int(counts['blocked'] or 0), 'blockedReady': int(counts['blocked_ready'] or 0)}
