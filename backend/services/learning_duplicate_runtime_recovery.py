"""Audited selection of an original draft after one unused automatic successor.

This exception authorizes only saved-stage completion/publication. Historical
attempts and paid holds remain visible; no generation or budget grant is issued.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from content.learning_budget_policy import canonical, digest
from integrations.openmaic_formal_quality import quality_canonical_json, quality_sha, quality_snapshot

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / 'openmaic-runtime/.runtime/OpenMAIC'
ARCHIVES = ROOT / 'backend/data/learning-provider-replies'
EVENT = 'single_course_duplicate_runtime_selection'
SCHEMA = 'mira.single-course.duplicate-runtime-selection.v1'
USAGE_TABLES = ('learning_student_formal_session_bindings', 'student_openmaic_launch_tickets',
               'student_openmaic_runtime_sessions', 'learning_formal_qwen_audio_jobs',
               'learning_openmaic_provider_readiness_jobs', 'learning_openmaic_conversation_probes')


def _fail():
    raise ValueError('duplicate Runtime recovery evidence or authority changed')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _session(job):
    return 'miraformal_' + _sha((job['runtimeRequestId'] + '\n' +
        quality_canonical_json(job['formalInput'])).encode())


def _file(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': _sha(raw), 'raw': raw.decode('utf-8')}


def _decoded(file):
    if _sha(file['raw'].encode()) != file['sha256']:
        _fail()
    return json.loads(file['raw'])


def _unchanged_files(files):
    if any(_sha(Path(file['path']).read_bytes()) != file['sha256'] for file in files.values()):
        _fail()


def _native_evidence(jobs):
    node = shutil.which('node')
    if not node or not os.environ.get('MIRA_OPENMAIC_AGENT_DATABASE_URL'):
        raise ValueError('Native read-only session inspection is not configured')
    result = subprocess.run([node, '--require', str(NATIVE / 'node_modules/tsx/dist/cjs/index.cjs'),
        str(ROOT / 'backend/scripts/inspect_duplicate_runtime_sessions.mjs'), *map(_session, jobs)],
        cwd=NATIVE, env=os.environ.copy(), capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError('Native read-only session inspection failed')
    return json.loads(result.stdout)


def _usage(conn, runtimes):
    return {runtime['id']: {table: int(conn.execute(
        f'SELECT COUNT(*) AS count FROM {table} WHERE runtime_classroom_id=?',
        (runtime['id'],)).fetchone()['count']) for table in USAGE_TABLES} for runtime in runtimes}


def _ledger(conn, authorization_id):
    return [dict(row) for row in conn.execute('SELECT * FROM learning_budget_reservations '
        'WHERE authorization_id=? ORDER BY id', (authorization_id,)).fetchall()]


def _events(conn, owner_id):
    return [dict(row) for row in conn.execute('SELECT * FROM learning_curriculum_preparation_events '
        'WHERE plan_id=? ORDER BY created_at,id', (owner_id,)).fetchall()]


def validate_plan(proof):
    """Pure fail-closed checks, also used when reopening the immutable archive."""
    state, identity, files = proof['state'], proof['identity'], proof['files']
    rows = state['runtimes']
    if (proof.get('schemaVersion') != SCHEMA or len(rows) != 2
            or [r.get('attempt_ordinal') for r in rows] != [1, 2]
            or [r.get('provider_attempt_ordinal') for r in rows] != [1, 2]
            or rows[0]['id'] != proof['selectedRuntimeId'] or rows[1]['id'] != proof['duplicateRuntimeId']
            or state['otherTouchedItems'] or state['receipt'] is not None
            or state['requests'] != [{'subject': 'math', 'skill_id': 'fraction_ratio_percentage', 'variant_ordinal': 1}]
            or (state['item'] or {}).get('content_gate_status') != 'passed'
            or state['item'].get('content_phase') != 'course_ready'
            or state['owner'].get('status') != 'running' or state['owner'].get('superseded_at') is not None
            or state['owner'].get('lease_token') is not None
            or state['owner'].get('catalog_build_id') != identity['buildId']
            or state['owner'].get('library_target_fingerprint') != identity['targetFingerprint']):
        _fail()
    original, duplicate = rows
    same = ('course_id', 'course_version', 'package_id', 'package_version', 'candidate_build_item_id',
            'candidate_release_id', 'candidate_grade_code', 'candidate_target_fingerprint', 'candidate_binding_contract_version')
    if (any(original.get(k) != duplicate.get(k) for k in same)
            or original.get('candidate_build_item_id') != identity['buildItemId']
            or original.get('candidate_target_fingerprint') != identity['targetFingerprint']
            or original.get('candidate_grade_code') != 'primary_6'
            or (original['course_id'], original['course_version']) != (state['item']['course_id'], state['item']['course_version'])
            or original.get('retry_of_runtime_id') is not None
            or duplicate.get('retry_of_runtime_id') != original['id']
            or duplicate.get('expected_previous_job_id') != original['upstream_job_id']
            or duplicate.get('retry_reason') != 'formal_candidate_retry_2'
            or not 0 <= duplicate['created_at'] - original['updated_at'] <= 1000
            or any(r.get('status') != 'failed' or r.get('quality_status') != 'rejected'
                   or r.get('error_code') != 'openmaic_formal_generation_failed'
                   or r.get('retired_at') is not None or r.get('upstream_classroom_id')
                   or r.get('ready_at') for r in rows)
            or any(count for usage in proof['usage'].values() for count in usage.values())):
        _fail()
    jobs = [_decoded(files[key]) for key in ('selectedJob', 'duplicateJob')]
    for runtime, job in zip(rows, jobs):
        if (job.get('id') != runtime['upstream_job_id'] or job.get('status') != 'failed'
                or not job.get('completedAt') or job.get('result')
                or job.get('runtimeRequestId') != runtime['request_id']
                or job.get('formalInputSha256') != quality_sha(job['formalInput'])
                or job['formalInput'].get('runtimeRequestId') != runtime['request_id']):
            _fail()
        requirement = json.loads(job['formalInput']['requirement'])
        manifest = json.loads(runtime['feature_manifest_json'])
        if (requirement.get('buildItemId') != identity['buildItemId']
                or requirement.get('targetFingerprint') != identity['targetFingerprint']
                or requirement.get('runtimeRequestId') != runtime['request_id']
                or manifest.get('paidBudget') != job['formalInput'].get('paidBudget')):
            _fail()
    normalized = []
    for job in jobs:
        value = dict(job['formalInput']); value.pop('runtimeRequestId')
        requirement = json.loads(value['requirement']); requirement.pop('runtimeRequestId')
        value['requirement'] = requirement; normalized.append(value)
    if (normalized[0] != normalized[1] or jobs[0].get('error') != 'FORMAL_PROFESSIONAL_SESSION_TIMEOUT'
            or not str(jobs[1].get('error', '')).startswith('FORMAL_PROFESSIONAL_SESSION_CANCELLED:')
            or jobs[1].get('scenesGenerated', 0) != 0 or jobs[1].get('totalScenes', 0) != 0):
        _fail()
    before, after, cancel = [_decoded(files[k]) for k in ('cancelBefore', 'cancelAfter', 'cancelReceipt')]
    expected_session = _session(jobs[1])
    if (cancel.get('officialMethod') != 'PgAgentSessionStore.requestCancel'
            or cancel.get('beforeSha256') != files['cancelBefore']['sha256']
            or cancel.get('jobId') != duplicate['upstream_job_id']
            or cancel.get('runtimeInstanceId') != duplicate['id'] or cancel.get('sessionId') != expected_session
            or cancel.get('buildItemId') != identity['buildItemId']
            or before.get('originalFailedJobSha256') != files['selectedJob']['sha256']
            or after.get('originalFailedJobSha256') != files['selectedJob']['sha256']
            or before.get('stages') != [] or before.get('scenes') != []
            or after.get('session', {}).get('status') != 'cancelled'
            or after.get('terminalEvent', {}).get('data', {}).get('status') != 'cancelled'):
        _fail()
    live = proof['nativeSessions']
    if len(live) != 2:
        _fail()
    for job, current in zip(jobs, live):
        session = current['session']
        if (session.get('id') != _session(job) or session.get('owner_id') != 'mira-formal-professional:' + _session(job)[11:]
                or session.get('status') != 'cancelled' or session.get('deleted_at')
                or session.get('lease_worker_id') is not None):
            _fail()
    if (live[1]['stageCount'] != 0 or live[1]['sceneCount'] != 0 or live[1]['snapshot'] is not None
            or live[1]['session'].get('stage_id') not in (None, 'stage-miraform')
            or live[1]['session'].get('active_stage_id')
            or not any(event.get('seq') == after['terminalEvent']['seq'] and event.get('type') == 'session_end'
                and event.get('data') == after['terminalEvent']['data'] for event in live[1]['events'])
            or not any(str(event.get('id')) == str(cancel.get('ownerEventId'))
                and event.get('type') == 'session_cancel_requested' and event.get('session_id') == expected_session
                for event in live[1]['ownerEvents'])
            or any(event.get('type') in {'stage_link', 'course_link'} for event in live[1]['events'])):
        _fail()
    snapshot = quality_snapshot(_decoded(files['sourceSnapshot']))
    # Project the exported document with the normal quality contract, then compare PostgreSQL.
    if (live[0]['stageCount'] != 1 or live[0]['sceneCount'] != 8 or live[0]['snapshot'] != snapshot
            or len(snapshot.get('scenes', [])) != 8):
        _fail()
    quizzes = [s for s in snapshot['scenes'] if s['type'] == 'quiz']
    ids = [q['id'] for scene in quizzes for q in scene['content']['questions']]
    if len(quizzes) != 2 or len(ids) != 4 or ids != before.get('identity', {}).get('questionIds'):
        _fail()
    return original, duplicate


def _archive_path(sha):
    if not re.fullmatch('[a-f0-9]{64}', str(sha or '')):
        _fail()
    return ARCHIVES / ('duplicate-runtime-selection-' + sha + '.json')


def _write_archive(proof):
    sha = digest(proof); path = _archive_path(sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
            output.write(canonical(proof)); output.flush(); os.fsync(output.fileno())
    except FileExistsError:
        if path.read_text() != canonical(proof):
            _fail()
    return sha


def load_archive(sha):
    proof = json.loads(_archive_path(sha).read_text())
    if digest(proof) != sha:
        _fail()
    validate_plan(proof)
    return proof


def plan_or_apply(*, runtime_service, preparation_repository, identity, state, runtime_id,
                  duplicate_runtime_id, evidence_dir, source_snapshot, expected_sha=None, apply=False, now):
    rows = state['runtimes']
    if len(rows) != 2 or rows[0]['id'] != runtime_id or rows[1]['id'] != duplicate_runtime_id:
        _fail()
    if apply and expected_sha and rows[1].get('retired_at') is not None:
        with runtime_service.repository.transaction() as conn:
            authorized_selection(conn, identity=identity, state=state,
                runtime_id=runtime_id, audit_sha=expected_sha)
        return {'applied': True, 'reused': True, 'expectedHistorySha256': expected_sha,
            'selectedRuntimeId': runtime_id, 'duplicateRuntimeId': duplicate_runtime_id,
            'historicalRuntimeCount': 2, 'newInstances': 0, 'paidLedgerChanged': False}
    directory = Path(evidence_dir).resolve()
    files = {key: _file(path) for key, path in {
        'selectedJob': NATIVE / 'data/classroom-jobs' / (rows[0]['upstream_job_id'] + '.json'),
        'duplicateJob': NATIVE / 'data/classroom-jobs' / (rows[1]['upstream_job_id'] + '.json'),
        'cancelBefore': directory / 'before.json', 'cancelAfter': directory / 'after.json',
        'cancelReceipt': directory / 'cancel-receipt.json', 'sourceSnapshot': source_snapshot}.items()}
    jobs = [_decoded(files[key]) for key in ('selectedJob', 'duplicateJob')]
    native = _native_evidence(jobs)
    with runtime_service.repository.transaction() as conn:
        current = [dict(r) for r in conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms '
            'WHERE candidate_build_item_id=? ORDER BY created_at,id FOR UPDATE', (identity['buildItemId'],)).fetchall()]
        owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=? FOR UPDATE', (state['owner']['id'],)).fetchone()
        item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE', (identity['buildItemId'],)).fetchone()
        receipt = conn.execute('SELECT * FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=? FOR UPDATE', (identity['buildItemId'],)).fetchone()
        requests = [dict(r) for r in conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE', (identity['targetFingerprint'],)).fetchall()]
        if (current != rows or dict(owner or {}) != state['owner'] or dict(item or {}) != state['item']
                or receipt or requests != state['requests']):
            _fail()
        proof = {'schemaVersion': SCHEMA, 'identity': identity, 'state': state,
            'selectedRuntimeId': runtime_id, 'duplicateRuntimeId': duplicate_runtime_id,
            'files': files, 'nativeSessions': native, 'usage': _usage(conn, rows),
            'paidLedger': _ledger(conn, jobs[0]['formalInput']['paidBudget']['authorizationId']),
            'ownerEvents': _events(conn, state['owner']['id'])}
        validate_plan(proof); sha = digest(proof)
        if expected_sha is not None and sha != expected_sha:
            _fail()
        if apply and not expected_sha:
            _fail()
        _unchanged_files(files)
        if apply:
            if load_archive(expected_sha) != proof or _native_evidence(jobs) != native:
                _fail()
            if not runtime_service.repository.retire_runtime_for_retry(conn, runtime_id=duplicate_runtime_id,
                    source_attempt_ordinal=2, now=now):
                _fail()
            preparation_repository.append_event(conn, plan_id=state['owner']['id'], event_type=EVENT,
                stage=state['owner']['stage'], payload={'recoveryReceiptId': sha,
                    'selectedRuntimeId': runtime_id, 'duplicateRuntimeId': duplicate_runtime_id,
                    'historicalRuntimeCount': 2, 'newInstanceCount': 0,
                    'code': 'saved_stage_completion_and_publication_only'}, now=now)
        else:
            _write_archive(proof)
    return {'applied': apply, 'expectedHistorySha256': sha, 'selectedRuntimeId': runtime_id,
        'duplicateRuntimeId': duplicate_runtime_id, 'historicalRuntimeCount': 2,
        'newInstances': 0, 'paidLedgerChanged': False}


def authorized_selection(conn, *, identity, state, runtime_id, audit_sha):
    """Retain both rows in inventory; return only the separately authorized tail target."""
    proof = load_archive(audit_sha)
    original, duplicate = proof['state']['runtimes']
    if identity != proof['identity'] or runtime_id != original['id'] or len(state['runtimes']) != 2:
        _fail()
    history = [dict(row) for row in conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms '
        'WHERE candidate_build_item_id=? ORDER BY created_at,id FOR UPDATE', (identity['buildItemId'],)).fetchall()]
    current_owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=? FOR UPDATE', (state['owner']['id'],)).fetchone()
    current_item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE', (identity['buildItemId'],)).fetchone()
    current_receipt = conn.execute('SELECT * FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=? FOR UPDATE', (identity['buildItemId'],)).fetchone()
    if (history != state['runtimes'] or dict(current_owner or {}) != state['owner']
            or dict(current_item or {}) != state['item'] or (dict(current_receipt) if current_receipt else None) != state['receipt']):
        _fail()
    rows = {row['id']: row for row in state['runtimes']}
    current, retired = rows.get(original['id']), rows.get(duplicate['id'])
    events = conn.execute('SELECT payload_json,created_at FROM learning_curriculum_preparation_events '
        'WHERE plan_id=? AND event_type=? ORDER BY created_at,id', (state['owner']['id'], EVENT)).fetchall()
    matching = [e for e in events if json.loads(e['payload_json']).get('recoveryReceiptId') == audit_sha]
    if len(matching) != 1:
        _fail()
    event = json.loads(matching[0]['payload_json'])
    retired_at = matching[0].get('created_at')
    if (not current or not retired or current.get('retired_at') is not None
            or event.get('selectedRuntimeId') != runtime_id or event.get('duplicateRuntimeId') != duplicate['id']
            or event.get('code') != 'saved_stage_completion_and_publication_only'
            or event.get('historicalRuntimeCount') != 2 or event.get('newInstanceCount') != 0
            or retired != {**duplicate, 'retired_at': retired_at}
            or type(retired_at) is not int or retired_at <= 0 or state['otherTouchedItems']
            or state['requests'] != proof['state']['requests']):
        _fail()
    stable = ('id','request_id','attempt_ordinal','provider_attempt_ordinal','upstream_job_id',
        'candidate_build_item_id','candidate_release_id','candidate_grade_code','candidate_target_fingerprint',
        'candidate_binding_contract_version','course_id','course_version','package_id','package_version','created_at')
    if (any(current.get(k) != original.get(k) for k in stable)
            or state['item']['id'] != proof['state']['item']['id']
            or state['owner']['id'] != proof['state']['owner']['id']
            or state['owner'].get('catalog_build_id') != identity['buildId']
            or state['owner'].get('library_target_fingerprint') != identity['targetFingerprint']
            or state['owner'].get('superseded_at') is not None
            or any(_usage(conn, [retired])[retired['id']].values())
            or (state['receipt'] and state['receipt'].get('runtime_classroom_id') != runtime_id)):
        _fail()
    duplicate_file = proof['files']['duplicateJob']
    _unchanged_files({'duplicateJob': duplicate_file})
    # No future requeue or authored draft can be hidden behind the old cancel receipt.
    jobs = [_decoded(proof['files'][key]) for key in ('selectedJob','duplicateJob')]
    if _native_evidence(jobs)[1] != proof['nativeSessions'][1]:
        _fail()
    return current, proof
