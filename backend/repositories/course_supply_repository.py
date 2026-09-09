from __future__ import annotations

import json

from services.learning_curriculum_preparation_contract import preparation_target_fingerprint


def requested_supply(conn, build):
    """None means legacy batch; an empty mapping means deliberately no work."""
    raw = build.get('target_spec_json')
    target = json.loads(raw) if isinstance(raw, str) else raw
    fingerprint = preparation_target_fingerprint(target)
    owner = conn.execute(
        'SELECT id FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ?',
        (fingerprint,),
    ).fetchone()
    if owner is None:
        return None
    rows = conn.execute(
        """SELECT subject, skill_id, variant_ordinal, priority
        FROM learning_course_supply_requests WHERE target_fingerprint = ? AND enabled = TRUE""",
        (fingerprint,),
    ).fetchall()
    return {(r['subject'], r['skill_id'], r['variant_ordinal']): r['priority'] for r in rows}


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


def observe_supply_incidents(conn, *, build_id, now):
    """Retain terminal evidence; observing a failure never authorizes a retry."""
    rows = conn.execute(
        """SELECT item.id, item.status AS content_status, item.content_gate_status,
          item.attempt_count, item.error_code AS content_error,
          runtime.id AS runtime_id, runtime.status AS runtime_status, runtime.quality_status,
          runtime.error_code AS runtime_error, audio.state AS audio_state,
          receipt.publication_status
        FROM learning_catalog_build_items AS item
        JOIN learning_curriculum_preparation_plans AS owner
          ON owner.catalog_build_id = item.build_job_id
          AND owner.library_target_fingerprint IS NOT NULL
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
        if row['publication_status'] == 'published':
            conn.execute('UPDATE learning_course_supply_incidents SET resolved_at = ? WHERE build_item_id = ? AND resolved_at IS NULL', (now, row['id']))
            continue
        if row['runtime_status'] == 'failed' or row['quality_status'] == 'quarantined':
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
