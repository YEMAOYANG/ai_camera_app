"""Validate a completed saved classroom and reconcile only its existing Runtime."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from content.learning_budget_policy import canonical, digest
from integrations.openmaic_formal_quality import quality_canonical_json, quality_sha
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient

EVENT = 'single_course_saved_stage_reconciliation'
ARCHIVES = Path(__file__).resolve().parents[1] / 'data/learning-provider-replies'


def validate_saved_stage_completion(completion, source_bytes, promoted, *, runtime, expected_input_sha, upstream):
    """Pure identity check; success never substitutes for normal Runtime QA."""
    if not isinstance(completion, dict):
        raise ValueError('saved-stage completion must be an object')
    unsigned = {key: value for key, value in completion.items() if key != 'receiptSha256'}
    source = json.loads(source_bytes)
    if not isinstance(source, dict) or not isinstance(promoted, dict) or not isinstance(source.get('formalInput'), dict):
        raise ValueError('saved-stage source/promoted job must contain the frozen input')
    formal_input = source.get('formalInput') or {}
    expected_session = 'miraformal_' + hashlib.sha256(
        (runtime['request_id'] + '\n' + quality_canonical_json(formal_input)).encode()).hexdigest()
    identity = {key: completion.get(key) for key in ('sourceJobSha256', 'sourceSnapshotSha256',
        'repairSnapshotSha256', 'sessionId', 'stageId')}
    if (completion.get('kind') != 'operator_saved_stage_repair'
            or quality_sha(unsigned) != completion.get('receiptSha256')
            or any(type(completion.get(key)) is not int or completion[key] != 0
                   for key in ('newAgentSessions', 'newSearches'))
            or any(not isinstance(identity[key], str) or len(identity[key]) != 64
                   or any(char not in '0123456789abcdef' for char in identity[key])
                   for key in ('sourceJobSha256', 'sourceSnapshotSha256', 'repairSnapshotSha256'))
            or hashlib.sha256(source_bytes).hexdigest() != completion['sourceJobSha256']
            or source.get('status') != 'failed' or not source.get('error') or not source.get('completedAt')
            or source.get('id') != runtime['upstream_job_id']
            or source.get('runtimeRequestId') != runtime['request_id']
            or source.get('formalInputSha256') != expected_input_sha
            or formal_input.get('runtimeRequestId') != runtime['request_id']
            or quality_sha(formal_input) != expected_input_sha
            or completion.get('sessionId') != expected_session
            or not isinstance(completion.get('completedAt'), str) or not completion['completedAt']
            or completion.get('originalSessionStatus') not in {'failed', 'cancelled', 'succeeded'}
            or completion.get('recoveryId') != 'omsaved_' + quality_sha(identity)[:24]):
        raise ValueError('saved-stage original job/session or completion SHA mismatch')
    recovery = promoted.get('formalSavedStageRecovery') or {}
    expected_recovery = {'originalStatus': 'failed', 'originalError': source['error'],
        'originalCompletedAt': source['completedAt'], **{key: identity[key] for key in
        ('sourceJobSha256', 'sourceSnapshotSha256', 'repairSnapshotSha256')},
        'recoveryId': completion['recoveryId'], 'receiptSha256': completion['receiptSha256']}
    result = completion.get('result') or {}
    native_result = promoted.get('result') or {}
    if (promoted.get('id') != source['id'] or promoted.get('status') != 'succeeded'
            or promoted.get('step') != 'completed' or promoted.get('error')
            or promoted.get('runtimeRequestId') != source['runtimeRequestId']
            or promoted.get('formalInputSha256') != expected_input_sha
            or promoted.get('formalInput') != formal_input
            or promoted.get('completedAt') != completion.get('completedAt')
            or recovery != expected_recovery or result.get('id') != completion.get('stageId')
            or native_result.get('classroomId') != completion.get('stageId')
            or any(native_result.get(key) != result.get(key) for key in
                   ('scenesCount', 'speechActionCount', 'formalAudio', 'professionalCreation', 'research', 'media', 'video'))
            or upstream is None or upstream.status != 'succeeded' or not upstream.done
            or upstream.job_id != source['id'] or upstream.classroom_id != completion.get('stageId')
            or upstream.scenes_count != result.get('scenesCount')
            or upstream.speech_action_count != result.get('speechActionCount')
            or not OpenMaicFullRuntimeClient.formal_job_identity_matches(upstream,
                runtime_request_id=runtime['request_id'], formal_input_sha256=expected_input_sha)
            or upstream.professional_creation != result.get('professionalCreation')
            or upstream.research != result.get('research')
            or (upstream.professional_creation or {}).get('sessionId') != expected_session
            or (upstream.research or {}).get('sessionId') != expected_session
            or upstream.formal_audio is None
            or upstream.formal_audio.receipt_sha256 != (result.get('formalAudio') or {}).get('receiptSha256')):
        raise ValueError('saved-stage promoted job or authoritative completion evidence mismatch')
    return completion['receiptSha256']


def reconcile_saved_stage(*, runtime_service, preparation_repository, identity, state,
                          runtime_id, completion_path, now):
    if (len(state['runtimes']) != 1 or state['runtimes'][0]['id'] != runtime_id
            or state['otherTouchedItems'] or not state.get('owner') or not state.get('item')):
        raise ValueError('saved-stage reconciliation requires the existing single-slot Runtime')
    runtime, owner, item = state['runtimes'][0], state['owner'], state['item']
    if (runtime.get('retired_at') is not None or runtime['status'] not in {'failed', 'generating', 'ready'}
            or runtime.get('candidate_build_item_id') != identity['buildItemId']
            or runtime.get('candidate_target_fingerprint') != identity['targetFingerprint']
            or (runtime['course_id'], runtime['course_version']) != (item['course_id'], item['course_version'])
            or item.get('content_gate_status') != 'passed' or item.get('content_phase') != 'course_ready'
            or owner.get('status') != 'running' or owner.get('superseded_at') is not None
            or owner.get('catalog_build_id') != identity['buildId']
            or owner.get('library_target_fingerprint') != identity['targetFingerprint']
            or (runtime['status'] == 'failed' and (runtime.get('quality_status') != 'rejected'
                or not runtime.get('error_code') or runtime.get('upstream_classroom_id') is not None))):
        raise ValueError('saved-stage original content, owner or Runtime is no longer eligible')
    path = Path(completion_path).resolve()
    if (path.name != 'completion.json' or path.parent.name != runtime['upstream_job_id']
            or path.parent.parent.name != 'formal-saved-stage-recoveries'):
        raise ValueError('completion must be the original Native saved-stage recovery file')
    completion = json.loads(path.read_bytes())
    source_bytes = (path.parent / 'source-job.json').read_bytes()
    promoted_path = path.parent.parent.parent / 'classroom-jobs' / (runtime['upstream_job_id'] + '.json')
    promoted_bytes = promoted_path.read_bytes()
    promoted = json.loads(promoted_bytes)
    manifest = json.loads(runtime['feature_manifest_json'])
    expected_input_sha = runtime_service._formal_input_sha256(runtime_request_id=runtime['request_id'],
        generation_contract=manifest.get('generationContract'), formal_contract=manifest.get('formalRuntimeContract'),
        paid_budget=manifest.get('paidBudget'))
    upstream = runtime_service.client.get_generation_job_by_request_id(runtime['request_id'])
    receipt_sha = validate_saved_stage_completion(completion, source_bytes, promoted, runtime=runtime,
        expected_input_sha=expected_input_sha, upstream=upstream)
    if quality_sha(json.loads((path.parent / 'prepared-snapshot.json').read_bytes())) != completion['repairSnapshotSha256']:
        raise ValueError('saved-stage repair snapshot no longer matches its completion')
    audit = {'schemaVersion': 'mira.single-course.saved-stage-reconciliation.v1',
        'originalRuntime': runtime, 'originalOwner': owner, 'buildItemId': identity['buildItemId'],
        'completionReceiptSha256': receipt_sha, 'sourceJobSha256': completion['sourceJobSha256'],
        'promotedJobSha256': hashlib.sha256(promoted_bytes).hexdigest(), 'formalInputSha256': expected_input_sha}
    audit_sha = digest(audit)
    with runtime_service.repository.transaction() as conn:
        current = runtime_service.repository.get_runtime_classroom(conn, runtime_id=runtime_id, for_update=True)
        current_owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=? FOR UPDATE', (owner['id'],)).fetchone()
        current_item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE', (item['id'],)).fetchone()
        requests = list(conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE', (identity['targetFingerprint'],)).fetchall())
        if (dict(current or {}) != runtime or dict(current_owner or {}) != owner or dict(current_item or {}) != item
                or requests != state['requests'] or promoted_path.read_bytes() != promoted_bytes):
            raise ValueError('saved-stage reconciliation source changed before compare-and-set')
        previous = conn.execute('SELECT payload_json FROM learning_curriculum_preparation_events WHERE plan_id=? '
            'AND event_type=? ORDER BY created_at DESC,id DESC LIMIT 1', (owner['id'], EVENT)).fetchone()
        if previous:
            if json.loads(previous['payload_json']).get('recoveryReceiptId') != receipt_sha or runtime['status'] == 'failed':
                raise ValueError('saved-stage revalidation was already attempted; diagnose the saved outcome')
        else:
            ARCHIVES.mkdir(parents=True, exist_ok=True)
            audit_path = ARCHIVES / ('saved-stage-reconciliation-' + audit_sha + '.json')
            try:
                fd = os.open(audit_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if digest(json.loads(audit_path.read_text())) != audit_sha:
                    raise ValueError('saved-stage reconciliation audit conflict')
            else:
                with os.fdopen(fd, 'w') as output:
                    output.write(canonical(audit)); output.flush(); os.fsync(output.fileno())
            if runtime['status'] == 'failed' and not runtime_service.repository.resume_formal_candidate_after_validator_fix(
                    conn, runtime_id=runtime_id, expected_upstream_job_id=runtime['upstream_job_id'],
                    expected_error_code=runtime['error_code'], now=now):
                raise ValueError('saved-stage Runtime rejection no longer matches')
            preparation_repository.append_event(conn, plan_id=owner['id'], event_type=EVENT, stage=owner['stage'],
                payload={'code': 'saved_classroom_recovery', 'status': 'pending_review',
                    'recoveryReceiptId': receipt_sha, 'auditReceiptId': audit_sha}, now=now)
    result = runtime_service.generation_status(runtime['upstream_job_id'])
    return {'runtimeId': runtime_id, 'upstreamJobId': runtime['upstream_job_id'],
        'completionReceiptSha256': receipt_sha, 'result': result,
        'newInstances': 0, 'newAgentSessions': 0, 'newSearches': 0, 'publicationRequested': False}
