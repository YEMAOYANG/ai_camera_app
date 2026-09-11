"""Exact original-instance continuation after the reviewed search/budget failure.

No new Runtime reservation, content generation, paid reserve or worker is started
by plan. Apply may queue the already authorized original Native session.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from content.learning_budget_policy import canonical, digest
from core.errors import ApiError
from integrations.openmaic_formal_citation_recovery_client import OpenMaicFormalCitationRecoveryClient

JOB = 'omformal_d57c133cbf917beb4cb30bb0'
EVENT = 'single_course_native_prestage_recovery'
ARCHIVES = Path(__file__).resolve().parents[1] / 'data/learning-provider-replies'


def _admitted_preview_from_archive(saved, history_sha):
    """Reconstruct internal continuation data from the immutable private audit.

    A public progress event is only a pointer, never the authority for replay.
    The original audit format and digest remain unchanged across this fix.
    """
    if not isinstance(saved, dict) or digest(saved) != history_sha:
        raise ValueError('Native recovery archive fingerprint mismatch')
    native = saved['native']
    return {'historySha256': history_sha, 'nativeHistorySha256': native['historySha256'],
        'jobId': native['jobId'], 'runtimeId': saved['originalRuntime']['id'],
        'ownerId': saved['originalOwner']['id'], 'instances': 1, 'newInstances': 0,
        'remainingSearchAttempts': native['remainingSearchAttempts'],
        'searchApiConfigured': True, 'contentDispatches': 13, 'budgetContextValid': True,
        'applied': False, 'blockers': []}


def _public_recovery_event(preview, *, status):
    """Publish safe progress atoms; full source evidence stays in ARCHIVES."""
    if status not in {'pending', 'applied'}:
        raise ValueError('Invalid Native recovery event status')
    return {'recoveryReceiptId': preview['historySha256'],
        'nativeRecoveryReceiptId': preview['nativeHistorySha256'],
        'jobId': preview['jobId'], 'runtimeId': preview['runtimeId'], 'ownerId': preview['ownerId'],
        'instanceCount': preview['instances'], 'newInstanceCount': preview['newInstances'],
        'remainingSearchAttemptCount': preview['remainingSearchAttempts'],
        'contentDispatchCount': preview['contentDispatches'], 'status': status}


def _native(config, mode, expected=None):
    client = OpenMaicFormalCitationRecoveryClient(config['OPENMAIC_FULL_RUNTIME_INTERNAL_URL'],
        internal_token=config['INTERNAL_API_TOKEN'], timeout_seconds=45)
    body = {'mode': mode}
    if expected: body['expectedHistorySha256'] = expected
    response = client._request_json('POST', '/api/generate-classroom/' + JOB + '/prestage-recovery', body)
    result = response.get('recovery')
    if response.get('ok') is not True or not isinstance(result, dict) or result.get('jobId') != JOB:
        raise ValueError('Native pre-stage recovery response invalid')
    return result


def _prepare_single_native_prestage(*, adapter, budget, config, identity, expected_history_sha, now, apply=False, native=_native):
    if expected_history_sha is not None and not re.fullmatch(r'[a-f0-9]{64}', expected_history_sha):
        raise ValueError('Recovery requires a SHA256 history identity')
    if identity['scope']['gradeCode'] != 'primary_6' or identity['scope']['subject'] != 'math':
        raise ValueError('Only the reviewed grade-six math sample may use this recovery')
    catalog, preparations = adapter.catalog_service, adapter.repository
    repository = catalog.repository
    saved_path = ARCHIVES / ('native-prestage-' + str(expected_history_sha) + '.json')
    saved = json.loads(saved_path.read_text()) if apply and expected_history_sha and saved_path.exists() else None
    if saved and digest(saved) != expected_history_sha:
        raise ValueError('Native recovery archive fingerprint mismatch')
    with repository.transaction() as conn:
        release, build = repository.lock_build_authority(conn, build_id=identity['buildId'])
        rows = repository.list_build_items(conn, build_id=identity['buildId'], for_update=True)
        item = next((r for r in rows if r['id'] == identity['buildItemId']), None)
        if (not item or not repository._content_authority_is_exact(conn, release=release, build=build, rows=rows, allow_terminal=True)
                or (item['subject'], item['skill_id'], item['variant_ordinal']) != ('math','fraction_ratio_percentage',1)
                or build['status'] != 'running' or item['status'] != 'course_ready' or item['content_phase'] != 'course_ready'
                or item['content_gate_status'] != 'passed' or item.get('error_code') or not item.get('content_receipt_hash')
                or any(r['status'] != 'pending' for r in rows if r['id'] != item['id'])):
            raise ValueError('Original accepted sample content has changed')
        requested = list(conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE', (identity['targetFingerprint'],)).fetchall())
        if requested != [{'subject':'math','skill_id':'fraction_ratio_percentage','variant_ordinal':1}]:
            raise ValueError('Native recovery requires the original one-slot scope')
        runtimes = list(conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=? FOR UPDATE',
            (item['id'],)).fetchall())
        owners = list(conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? '
            'AND target_fingerprint=? FOR UPDATE', (build['id'],identity['targetFingerprint'])).fetchall())
        if len(runtimes) != 1 or len(owners) != 1:
            raise ValueError('Native recovery requires one original Runtime and one owner')
        runtime, owner = runtimes[0], owners[0]
        previous = conn.execute('SELECT * FROM learning_curriculum_preparation_events WHERE plan_id=? AND event_type=? '
            'ORDER BY created_at DESC,id DESC LIMIT 1', (owner['id'],EVENT)).fetchone()
        if previous:
            payload = json.loads(previous['payload_json'])
            if (payload.get('recoveryReceiptId') != expected_history_sha or not saved
                    or payload.get('status') != 'applied' or runtime['status'] not in {'generating','ready'}
                    or runtime.get('upstream_job_id') != JOB or runtime['id'] != saved['originalRuntime']['id']):
                raise ValueError('This recovery was already used; a later failure requires a new diagnosis')
            return {**_admitted_preview_from_archive(saved, expected_history_sha),'applied':True,'reused':True}
        pending_event = conn.execute('SELECT * FROM learning_curriculum_preparation_events WHERE plan_id=? AND event_type=? '
            'ORDER BY created_at DESC,id DESC LIMIT 1', (owner['id'],EVENT + '_pending')).fetchone()
        if pending_event:
            pending = json.loads(pending_event['payload_json'])
            if (not apply or pending.get('recoveryReceiptId') != expected_history_sha or not saved
                    or pending.get('status') != 'pending'
                    or runtime['status'] != 'recovering' or runtime['error_code'] != 'openmaic_formal_prestage_recovery_pending'
                    or runtime['id'] != saved['originalRuntime']['id'] or runtime['upstream_job_id'] != JOB
                    or owner['status'] != 'running' or owner.get('superseded_at') is not None):
                raise ValueError('Recovery is pending; continue only with its original history SHA')
            return {**_admitted_preview_from_archive(saved, expected_history_sha),'pending':True}
        receipt = conn.execute('SELECT * FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?', (item['id'],)).fetchone()
        if (runtime['status'] != 'failed' or runtime['quality_status'] != 'rejected' or runtime['error_code'] != 'openmaic_formal_generation_failed'
                or runtime.get('upstream_job_id') != JOB or runtime.get('upstream_classroom_id') is not None or receipt is not None
                or runtime['attempt_ordinal'] != 1 or runtime['provider_attempt_ordinal'] != 1 or runtime.get('retired_at') is not None
                or runtime['course_id'] != item['course_id'] or runtime['course_version'] != item['course_version']
                or runtime['candidate_target_fingerprint'] != identity['targetFingerprint']
                or owner['status'] != 'running' or owner['stage'] != 'generating_content'
                or owner.get('error_code') is not None or owner.get('error_message_safe') is not None
                or owner.get('completed_at') is not None or owner.get('lease_token') is not None
                or owner.get('superseded_at') is not None or owner.get('library_target_fingerprint') != identity['targetFingerprint']
                or int(owner.get('failed_course_count') or 0) != 0 or int(owner.get('ready_course_count') or 0) != 0):
            raise ValueError('Only the original pre-stage failure can be reopened')
        proof = catalog.audit_locked_content_proofs(conn, build_id=build['id'])
        if tuple(proof.passed_item_ids) != (item['id'],): raise ValueError('Original Host acceptance is not current')
        dispatches = list(conn.execute('SELECT * FROM learning_course_provider_dispatches WHERE build_item_id=? '
            'ORDER BY logical_attempt,phase_ordinal,id', (item['id'],)).fetchall())
        if len(dispatches) != 13 or any(d['status'] in {'reserved','dispatched','ambiguous'} for d in dispatches):
            raise ValueError('Original content dispatch history has changed')
        failures = list(conn.execute('SELECT * FROM learning_curriculum_preparation_events WHERE plan_id=? '
            'ORDER BY created_at,id', (owner['id'],)).fetchall())
        manifest = json.loads(runtime['feature_manifest_json'])
        binding = manifest.get('paidBudget') or {}
        budget_valid = True
        try:
            budget._enabled(conn)
            authority = budget._authority(conn, binding.get('authorizationId'), now)
        except ApiError:
            if apply: raise
            budget_valid = False
            authority = budget.repository.authorization(conn, binding.get('authorizationId'))
        if authority is None or json.loads(authority['scope_json']) != identity['scope']:
            raise ValueError('Recovery budget is not the original exact sample authorization')
        for window in ('day','month'):
            if (budget.policy.raw['limits']['global'][window]['money_micros'] > 10000000
                    or budget.policy.raw['limits']['purposes']['production'][window]['money_micros'] > 8000000):
                raise ValueError('Recovery may not expand the original money ceiling')
        native_result = native(config,'plan',saved['native']['historySha256'] if saved else None)
        search_configured = native_result.get('searchApiConfigured') is True
        native_proof = {k:v for k,v in native_result.items() if k not in {'searchApiConfigured','applied','recoveredAt'}}
        if (native_proof.get('runtimeRequestId') != runtime['request_id'] or native_proof.get('buildItemId') != item['id']
                or native_proof.get('courseId') != item['course_id'] or native_proof.get('courseVersion') != item['course_version']
                or native_proof.get('targetFingerprint') != identity['targetFingerprint'] or native_proof.get('stageCount') != 0
                or native_proof.get('qaCount') != 0 or native_proof.get('remainingSearchAttempts') != 1):
            raise ValueError('Native and Backend frozen sample identities do not match')
        audit = {'schemaVersion':'mira.single-course.native-prestage-recovery.v1','originalOwner':dict(owner),
            'originalRuntime':dict(runtime),'itemSha256':digest(item),'eventsSha256':digest(failures),
            'contentDispatchesSha256':digest(dispatches),'contentReceiptSha256':item['content_receipt_hash'],
            'native':native_proof}
        history = digest(audit)
        if expected_history_sha and expected_history_sha != history: raise ValueError('Recovery history SHA no longer matches')
        preview = {'historySha256':history,'nativeHistorySha256':native_proof['historySha256'],'jobId':JOB,
            'runtimeId':runtime['id'],'ownerId':owner['id'],'instances':1,'newInstances':0,
            'remainingSearchAttempts':1,'searchApiConfigured':search_configured,
            'contentDispatches':len(dispatches),'budgetContextValid':budget_valid,'applied':False,
            'blockers':([] if search_configured else ['search_api_key_required']) + ([] if budget_valid else ['original_budget_inactive'])}
        if not apply: return preview
        if not expected_history_sha: raise ValueError('Apply requires the explicitly reviewed history SHA')
        ARCHIVES.mkdir(parents=True,exist_ok=True)
        try: fd = os.open(saved_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            if digest(json.loads(saved_path.read_text())) != history: raise ValueError('Recovery archive conflict')
        else:
            with os.fdopen(fd,'w') as f: f.write(canonical(audit)); f.flush(); os.fsync(f.fileno())
        if not search_configured:
            raise ValueError('A real configured search API is required before any recovery state change')
        changed = conn.execute("UPDATE learning_openmaic_runtime_classrooms SET status='recovering',quality_status='pending_review',"
            "error_code='openmaic_formal_prestage_recovery_pending',error_message_safe=NULL,updated_at=? WHERE id=? AND status='failed' "
            "AND quality_status='rejected' AND updated_at=? AND upstream_job_id=?",
            (now,runtime['id'],runtime['updated_at'],JOB))
        if changed.rowcount != 1: raise ValueError('Original Runtime recovery CAS rejected')
        changed = conn.execute("UPDATE learning_curriculum_preparation_plans SET status='running',stage='generating_content',"
            'next_run_at=?,error_code=NULL,error_message_safe=NULL,completed_at=NULL,last_progress_at=?,updated_at=? '
            "WHERE id=? AND status='running' AND stage='generating_content' AND updated_at=? "
            'AND error_code IS NULL AND error_message_safe IS NULL AND completed_at IS NULL '
            'AND lease_token IS NULL AND superseded_at IS NULL',
            (now,now,now,owner['id'],owner['updated_at']))
        if changed.rowcount != 1: raise ValueError('Original owner recovery CAS rejected')
        preparations.append_event(conn,plan_id=owner['id'],event_type=EVENT + '_pending',stage='generating_content',
            payload=_public_recovery_event(preview,status='pending'),now=now)
        return {**preview,'pending':True}


def recover_single_native_prestage(*, adapter, budget, config, identity, expected_history_sha, now, apply=False, native=_native):
    prepared = _prepare_single_native_prestage(adapter=adapter,budget=budget,config=config,identity=identity,
        expected_history_sha=expected_history_sha,now=now,apply=apply,native=native)
    if not apply or not prepared.get('pending'): return prepared
    # The original Runtime/owner and pending audit have committed before Native
    # can queue paid work. A failed request remains explicit and resumable.
    resumed = native(config,'apply',prepared['nativeHistorySha256'])
    if resumed.get('applied') is not True or resumed.get('historySha256') != prepared['nativeHistorySha256']:
        raise ValueError('Native did not admit the exact original session recovery')
    repo = adapter.catalog_service.repository
    with repo.transaction() as conn:
        row = conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=? FOR UPDATE',
            (prepared['runtimeId'],)).fetchone()
        owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=? FOR UPDATE',
            (prepared['ownerId'],)).fetchone()
        if (not row or not owner or row['status'] != 'recovering' or row['upstream_job_id'] != JOB
                or row['error_code'] != 'openmaic_formal_prestage_recovery_pending' or owner['status'] != 'running'):
            raise ValueError('Pending original-instance recovery changed; no second dispatch is permitted')
        conn.execute("UPDATE learning_openmaic_runtime_classrooms SET status='generating',error_code=NULL,updated_at=? WHERE id=?",
            (now,row['id']))
        receipt = {k:v for k,v in prepared.items() if k != 'pending'}
        receipt['applied'] = True
        adapter.repository.append_event(conn,plan_id=owner['id'],event_type=EVENT,stage='generating_content',
            payload=_public_recovery_event(receipt,status='applied'),now=now)
    return receipt
