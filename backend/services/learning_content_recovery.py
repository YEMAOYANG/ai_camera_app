"""One audited content retry, preserving the original failed dispatch history.

The receipt lives in existing preparation events. It authorizes no money and
never replaces Host acceptance, independent verification or publication gates.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from content.learning_budget_policy import canonical, digest

KIND = 'mira.single-course.content-recovery.v1'
EVENT = 'single_course_content_recovery'
BILLED_EVENT = 'single_course_billed_reply_recovery'
BILLED_KIND = 'mira.single-course.billed-reply-recovery.v1'
ARCHIVE_ROOT = Path(__file__).resolve().parents[1] / 'data/learning-provider-replies'
PHASES = (('outline', 1, 'succeeded'), ('raw_candidate', 2, 'succeeded'),
          ('candidate_repair', 3, 'succeeded'), ('lesson_text', 5, 'succeeded'),
          ('reconciliation', 6, 'succeeded'), ('independent_verification', 11, 'failed_safe'))


def _original_history(item, dispatches):
    if (item.get('grade_code') not in {f'primary_{n}' for n in range(2, 7)}
            or not isinstance(dispatches, list) or len(dispatches) != len(PHASES)):
        raise ValueError('recovery requires one returned high-grade content verification failure')
    for row, (phase, ordinal, status) in zip(dispatches, PHASES):
        if (row.get('build_item_id') != item['id'] or row.get('generation_request_id') != item['generation_request_id']
                or row.get('logical_attempt') != 1 or (row.get('phase'), row.get('phase_ordinal'), row.get('status')) != (phase, ordinal, status)):
            raise ValueError('original content history identity changed')
        if status == 'succeeded' and digest(json.loads(row['checkpoint_json'])) != row.get('output_sha256'):
            raise ValueError('original content checkpoint hash changed')
    failed = dispatches[-1]
    if (failed.get('safe_error_code') != 'question_phase_verification_checkpoint_rejected'
            or failed.get('checkpoint_json') is not None or failed.get('output_sha256') is not None
            or failed.get('completed_at') is None or failed.get('billing_evidence') != 'reported'):
        raise ValueError('failed verification is not an auditable returned response')


def recovery_receipt(item, dispatches, *, approval_reference):
    _original_history(item, dispatches)
    receipt = {'recoveryKindId': KIND, 'buildItemId': item['id'],
        'failedDispatchId': dispatches[-1]['id'], 'failedInputShaId': dispatches[-1]['input_sha256'],
        'sourceOutlineDispatchId': dispatches[0]['id'], 'sourceOutlineShaId': dispatches[0]['output_sha256'],
        'historyShaId': digest(dispatches), 'approvalReferenceId': approval_reference,
        'maximumDispatchCount': 14}
    return {**receipt, 'recoveryId': digest(receipt)}


def candidate_less_evidence(*, item, histories):
    """Recognize only a server-persisted receipt with the unchanged original rows."""
    history = histories.get(1) or {}
    receipt = history.get('recoveryReceipt')
    if not isinstance(receipt, dict):
        return None
    try:
        if (int(item.get('attempt_count') or 0) != 2
                or item.get('active_generation_request_id') != item['generation_request_id'] + '.attempt2'
                or any(history.get(key) for key in ('jobs', 'candidates', 'courses'))
                or receipt != recovery_receipt(item, history.get('dispatches'), approval_reference=receipt['approvalReferenceId'])):
            return None
        current = (histories.get(2) or {}).get('dispatches') or []
        if len(current) + len(history['dispatches']) > receipt['maximumDispatchCount']:
            return None
        if current:
            outline = current[0]
            if (outline.get('phase') != 'outline' or outline.get('status') != 'succeeded'
                    or outline.get('output_sha256') != receipt['sourceOutlineShaId']
                    or outline.get('provider_request_id_hash') is not None
                    or outline.get('input_tokens') is not None or outline.get('output_tokens') is not None
                    or outline.get('billing_evidence') != 'unknown'):
                return None
        return {'item': dict(item), 'dispatches': history['dispatches'],
                'recoveryKind': KIND, 'recoveryReceipt': receipt}
    except (KeyError, TypeError, ValueError):
        return None


def recovery_dispatches(*, item, evidence):
    histories = evidence.get('attemptHistories')
    if histories is None:
        histories = {1: {'dispatches': evidence.get('dispatches'), 'recoveryReceipt': evidence.get('recoveryReceipt')}}
    normalized = candidate_less_evidence(item=item, histories=histories)
    return normalized['dispatches'] if normalized else None


def load_recovery_receipt(conn, *, build_id, item_id):
    rows = conn.execute('SELECT event.payload_json,plan.target_fingerprint FROM learning_curriculum_preparation_events event '
        'JOIN learning_curriculum_preparation_plans plan ON plan.id=event.plan_id '
        'WHERE plan.catalog_build_id=? AND event.event_type=? '
        "AND JSON_UNQUOTE(JSON_EXTRACT(event.payload_json, '$.buildItemId'))=? ORDER BY event.created_at,event.id",
        (build_id, EVENT, item_id)).fetchall()
    if not rows:
        return None
    receipts = [json.loads(row['payload_json']) for row in rows]
    if any(receipt.get('approvalReferenceId') != 'grade-build:' + str(row['target_fingerprint'])
           for row, receipt in zip(rows, receipts)):
        raise ValueError('recovery approval does not match the frozen shared owner')
    if any(receipt != receipts[0] for receipt in receipts):
        raise ValueError('conflicting single-course recovery receipts')
    return receipts[0]


def require_billed_recovery_audit(conn, *, build_id, item, histories, audit_sha256, checkpoint):
    """A Host-only replay must retain its complete former failed row first."""
    path = ARCHIVE_ROOT / ('recovery-' + audit_sha256 + '.json')
    audit = json.loads(path.read_text())
    if (digest(audit) != audit_sha256 or audit.get('schemaVersion') != BILLED_KIND
            or audit.get('buildId') != build_id or audit.get('buildItemId') != item['id']
            or audit.get('originalAttemptDispatches') != histories[2]['dispatches']
            or audit.get('checkpoint') != checkpoint):
        raise ValueError('billed reply recovery audit does not match the locked original history')
    event = conn.execute('SELECT event.payload_json FROM learning_curriculum_preparation_events event '
        'JOIN learning_curriculum_preparation_plans plan ON plan.id=event.plan_id '
        'WHERE plan.catalog_build_id=? AND event.event_type=? '
        "AND JSON_UNQUOTE(JSON_EXTRACT(event.payload_json, '$.auditShaId'))=?",
        (build_id, BILLED_EVENT, audit_sha256)).fetchall()
    if len(event) != 1 or json.loads(event[0]['payload_json']).get('buildItemId') != item['id']:
        raise ValueError('billed reply recovery has no exact immutable preparation event')


def replay_billed_reply(*, catalog, item, histories, archive):
    """Recompile the actual saved response locally; never execute a Provider."""
    from integrations.openmaic_question_adapter import _normalize_phase_output_checkpoint
    from services.learning_formal_question_preflight import validate_formal_phase_question_checkpoint
    current = histories[2]['dispatches']
    if (len(current) != 4 or candidate_less_evidence(item=item, histories=histories) is None
            or [(d['phase'], d['status']) for d in current] != [
                ('outline','succeeded'),('raw_candidate','succeeded'),
                ('candidate_repair','succeeded'),('candidate_repair_retry','failed_safe')]):
        raise ValueError('billed reply recovery requires the exact failed attempt-two phase-four history')
    failed = current[-1]
    rebuilt = {**item, 'status':'processing', 'content_phase':'candidate_repair_retry',
        'content_attempt_started_at':failed['attempt_started_at'],
        'content_provider_attempt_hard_deadline_at':failed['attempt_hard_deadline_at']}
    plan = {'priorEvidence':[], 'historicalQuestionFingerprints':[],
            'attemptOneEvidence':candidate_less_evidence(item=item,histories=histories)}
    command, _ = catalog._content_phase_command(item=rebuilt,dispatches=current[:-1],plan=plan)
    prepared = catalog._content_provider_preflight(command)
    if prepared.input_sha256 != failed['input_sha256'] or prepared.profile_sha256 != failed['profile']:
        raise ValueError('billed request/profile cannot be reproduced exactly')
    expected_receipt = {'providerRequestIdHash':failed['provider_request_id_hash'],
        'inputTokens':failed['input_tokens'],'outputTokens':failed['output_tokens'],'billingEvidence':'reported'}
    if (archive.get('schemaVersion') != 'mira.openmaic.question-phase-reply-archive.v1'
            or archive.get('requestId') != item['active_generation_request_id']
            or archive.get('phase') != 'candidate_repair_retry' or archive.get('phaseOrdinal') != 4
            or archive.get('gradeCode') != item['grade_code'] or archive.get('subject') != item['subject']
            or archive.get('skillId') != item['skill_id'] or archive.get('receipt') != expected_receipt
            or hashlib.sha256(archive['content'].encode()).hexdigest() != archive.get('contentSha256')):
        raise ValueError('saved reply is not the exact billed Provider evidence')
    phase_adapter = catalog.staged_content_candidate_generator._adapter
    environment = {'PATH':os.environ.get('PATH',''), 'OPENMAIC_HOST_VALIDATOR_PYTHON':sys.executable,
                   'PYTHONDONTWRITEBYTECODE':'1'}
    result = subprocess.run([phase_adapter.node_binary, str(phase_adapter.sidecar_root/'src/replay-question-phase-reply.mjs')],
        input=json.dumps({'request':prepared.request,'archive':archive},ensure_ascii=False),
        capture_output=True,text=True,timeout=30,check=False,env=environment)
    if result.returncode != 0:
        raise ValueError('saved reply failed pure Host replay: ' + result.stderr[-1200:])
    replay = json.loads(result.stdout)
    if (replay.get('inputSha256') != archive['inputSha256']
            or replay.get('providerProfileSha256') != archive['providerProfileSha256']):
        raise ValueError('saved reply input/profile archive identity drift')
    checkpoint = _normalize_phase_output_checkpoint(prepared, replay['checkpoint'])
    # The next paid phase is forbidden until the exact deterministic Host rules
    # accept all five questions. No independent LLM review is synthesized here.
    accepted = {**failed,'status':'succeeded','checkpoint_json':canonical(checkpoint),
                'output_sha256':digest(checkpoint),'safe_error_code':None}
    lesson, _ = catalog._content_phase_command(item={**rebuilt,'content_phase':'lesson_text'},
        dispatches=[*current[:-1],accepted],plan=plan)
    validate_formal_phase_question_checkpoint(lesson)
    return checkpoint, replay


def recover_billed_single_content_reply(*, adapter, identity, expected_history_sha, now, apply=False):
    catalog, preparations = adapter.catalog_service, adapter.repository
    repository = catalog.repository
    with repository.transaction() as conn:
        release, build = repository.lock_build_authority(conn,build_id=identity['buildId'])
        rows = repository.list_build_items(conn,build_id=identity['buildId'],for_update=True)
        item = next((row for row in rows if row['id']==identity['buildItemId']),None)
        if (not item or not repository._content_authority_is_exact(conn,release=release,build=build,rows=rows,allow_terminal=True)
                or item['status']!='failed' or item['attempt_count']!=2 or item['variant_ordinal']!=1
                or item.get('course_id') is not None or item.get('content_lease_token') is not None
                or item['error_code']!='preparation_content_validation_failed'
                or any(row['status']!='pending' for row in rows if row['id']!=item['id'])):
            raise ValueError('billed reply recovery authority changed')
        requested = conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE',(identity['targetFingerprint'],)).fetchall()
        if list(requested)!=[{'subject':item['subject'],'skill_id':item['skill_id'],'variant_ordinal':1}]:
            raise ValueError('billed reply recovery requires unchanged single-slot scope')
        histories = repository._load_content_attempt_histories_locked(conn,rows=[item])[item['id']]
        if any(histories[2].get(key) for key in ('jobs','candidates','courses')):
            raise ValueError('billed reply recovery cannot replace a persisted candidate')
        current=histories[2]['dispatches']; history_sha=digest(current)
        if expected_history_sha is not None and expected_history_sha!=history_sha:
            raise ValueError('billed reply history differs from the reviewed failure')
        failed=current[-1]
        if now>=failed['attempt_hard_deadline_at']:
            raise ValueError('original attempt deadline expired; recovery cannot renew it')
        archive_path=ARCHIVE_ROOT / ('candidate_repair_retry.'+failed['input_sha256']+'.json')
        archive=json.loads(archive_path.read_text())
        checkpoint,replay=replay_billed_reply(catalog=catalog,item=item,histories=histories,archive=archive)
        audit={'schemaVersion':BILLED_KIND,'buildId':build['id'],'buildItemId':item['id'],
            'approvalReference':identity['scope']['approvalReference'],'originalItem':dict(item),
            'originalAttemptDispatches':current,'sourceArchive':archive,'sourceArchiveSha256':digest(archive),
            'checkpoint':checkpoint,'checkpointSha256':digest(checkpoint),'replay':replay}
        audit_sha=digest(audit)
        plans=conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? '
            'AND target_fingerprint=? ORDER BY id FOR UPDATE',(build['id'],identity['targetFingerprint'])).fetchall()
        owner=next((p for p in plans if p.get('library_target_fingerprint')==identity['targetFingerprint']),None)
        if owner is None or any(p.get('lease_token') is not None or p.get('superseded_at') is not None for p in plans):
            raise ValueError('billed reply recovery owner has changed')
        preview={'historySha256':history_sha,'auditSha256':audit_sha,'checkpointSha256':digest(checkpoint),
            'sourceArchiveSha256':digest(archive),'sourceReplyContentSha256':archive['contentSha256'],
            'dispatchCount':sum(len(h['dispatches']) for h in histories.values()),'nextPhase':'lesson_text',
            'providerCalls':0,'hardDeadlineAt':failed['attempt_hard_deadline_at']}
        if not apply: return preview
        if expected_history_sha is None: raise ValueError('apply requires the reviewed history SHA')
        # Immutable content-addressed evidence is durable before its event and
        # phase recovery commit. A rolled-back transaction may leave only an
        # unreferenced audit file, never a falsely successful dispatch.
        audit_path=ARCHIVE_ROOT/('recovery-'+audit_sha+'.json')
        try:
            fd=os.open(audit_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            if digest(json.loads(audit_path.read_text()))!=audit_sha: raise ValueError('audit archive conflict')
        else:
            with os.fdopen(fd,'w') as output:
                json.dump(audit,output,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                output.flush(); os.fsync(output.fileno())
        preparations.append_event(conn,plan_id=owner['id'],event_type=BILLED_EVENT,stage='generating_content',
            payload={'recoveryKindId':BILLED_KIND,'buildItemId':item['id'],'auditShaId':audit_sha,
                     'sourceDispatchId':failed['id'],'originalHistoryShaId':history_sha,
                     'sourceArchiveShaId':digest(archive),'checkpointShaId':digest(checkpoint)},now=now)
        updated=repository.recover_billed_candidate_retry_host_checkpoint(conn,build_id=build['id'],item_id=item['id'],
            expected_subject=item['subject'],expected_skill_id=item['skill_id'],expected_grade=item['grade_code'],
            failed_dispatch_id=failed['id'],expected_input_sha256=failed['input_sha256'],checkpoint=checkpoint,
            now=now,recovery_audit_sha256=audit_sha)
        if updated is None: raise ValueError('billed reply Host recovery CAS rejected')
        if all(plan['status']=='failed' for plan in plans):
            if preparations.recover_shared_content_validation_plans(conn,build_id=build['id'],
                    target_fingerprint=identity['targetFingerprint'],now=now)!=len(plans):
                raise ValueError('billed reply shared-owner recovery failed')
        elif len(plans)==1 and owner['status'] in {'running','queued'} and owner['stage']=='generating_content':
            cursor=conn.execute("UPDATE learning_curriculum_preparation_plans SET status='running',next_run_at=?,"
                'error_code=NULL,error_message_safe=NULL,completed_at=NULL,last_progress_at=?,updated_at=? '
                'WHERE id=? AND status=? AND lease_token IS NULL AND superseded_at IS NULL',
                (now,now,now,owner['id'],owner['status']))
            if cursor.rowcount!=1: raise ValueError('billed reply owner CAS rejected')
        else: raise ValueError('billed reply owner state requires diagnosis')
        return {**preview,'applied':True,'auditArchive':str(audit_path)}


def recover_single_runtime_preflight(*, adapter, identity, expected_history_sha, now, readiness, apply=False):
    """Reopen only the reviewed owner after a zero-dispatch readiness failure."""
    catalog, preparations = adapter.catalog_service, adapter.repository
    repository = catalog.repository
    with repository.transaction() as conn:
        release, build=repository.lock_build_authority(conn,build_id=identity['buildId'])
        rows=repository.list_build_items(conn,build_id=identity['buildId'],for_update=True)
        item=next((row for row in rows if row['id']==identity['buildItemId']),None)
        if (not item or not build or not repository._content_authority_is_exact(conn,release=release,build=build,rows=rows,allow_terminal=True)
                or build['status']!='running' or build.get('error_code') is not None
                or item['status']!='course_ready' or item['content_phase']!='course_ready'
                or item['content_gate_status']!='passed' or item.get('error_code') is not None
                or not item.get('content_receipt_hash') or item.get('content_lease_token') is not None
                or any(row['status']!='pending' for row in rows if row['id']!=item['id'])):
            raise ValueError('Runtime preflight recovery requires unchanged passed single-course content')
        requested=conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE',(identity['targetFingerprint'],)).fetchall()
        if list(requested)!=[{'subject':item['subject'],'skill_id':item['skill_id'],'variant_ordinal':item['variant_ordinal']}]:
            raise ValueError('Runtime preflight recovery scope changed')
        proof=catalog.audit_locked_content_proofs(conn,build_id=build['id'])
        if tuple(proof.passed_item_ids)!=(item['id'],):
            raise ValueError('Runtime preflight recovery requires exact independently audited Host proof')
        runtimes=conn.execute('SELECT id FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=? FOR UPDATE',
            (item['id'],)).fetchall()
        if runtimes: raise ValueError('Runtime preflight recovery cannot replay an issued classroom')
        plans=conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? '
            'AND target_fingerprint=? ORDER BY id FOR UPDATE',(build['id'],identity['targetFingerprint'])).fetchall()
        if len(plans)!=1: raise ValueError('Runtime preflight recovery requires one exact shared owner')
        owner=plans[0]
        if (owner['status']!='failed' or owner['stage']!='completed'
                or owner['error_code']!='preparation_generation_failed' or owner.get('completed_at') is None
                or owner.get('library_target_fingerprint')!=identity['targetFingerprint']
                or owner.get('lease_token') is not None or owner.get('superseded_at') is not None):
            raise ValueError('Runtime preflight failed owner changed')
        failure=conn.execute("SELECT * FROM learning_curriculum_preparation_events WHERE plan_id=? "
            "AND event_type='claim_failed' ORDER BY created_at DESC,id DESC LIMIT 1",(owner['id'],)).fetchone()
        if (failure is None or failure['created_at']!=owner['completed_at']
                or json.loads(failure['payload_json'])!={'fromStage':'generating_content','errorCode':'preparation_generation_failed'}):
            raise ValueError('Runtime preflight requires the exact reviewed zero-dispatch failure event')
        dispatches=conn.execute('SELECT * FROM learning_course_provider_dispatches WHERE build_item_id=? '
            'ORDER BY logical_attempt,phase_ordinal,id FOR UPDATE',(item['id'],)).fetchall()
        if len(dispatches)>14 or any(row['status'] in {'reserved','dispatched','ambiguous'} for row in dispatches):
            raise ValueError('Runtime preflight recovery has unresolved Provider work')
        audit={'schemaVersion':'mira.single-course.runtime-preflight-recovery.v1','originalOwner':dict(owner),
            'originalFailureEvent':dict(failure),'buildItemId':item['id'],'courseId':item['course_id'],
            'courseVersion':item['course_version'],'contentReceiptSha256':item['content_receipt_hash'],
            'providerDispatchesSha256':digest(list(dispatches)),'providerDispatchCount':len(dispatches)}
        history_sha=digest(audit)
        if expected_history_sha is not None and history_sha!=expected_history_sha:
            raise ValueError('Runtime preflight recovery history differs from the reviewed failure')
        preview={'historySha256':history_sha,'ownerId':owner['id'],'courseId':item['course_id'],
            'contentReceiptSha256':item['content_receipt_hash'],'dispatchCount':len(dispatches),
            'instances':0,'providerCalls':0,'runtimeReady':readiness.get('ready') is True,
            'nextStage':'generating_content'}
        if not apply: return preview
        if expected_history_sha is None or readiness.get('ready') is not True:
            raise ValueError('Runtime preflight apply requires reviewed SHA and current exact native readiness')
        audit_path=ARCHIVE_ROOT/('preflight-recovery-'+history_sha+'.json')
        try: fd=os.open(audit_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError:
            if digest(json.loads(audit_path.read_text()))!=history_sha: raise ValueError('preflight audit archive conflict')
        else:
            with os.fdopen(fd,'w') as output:
                output.write(canonical(audit)); output.flush(); os.fsync(output.fileno())
        cursor=conn.execute("UPDATE learning_curriculum_preparation_plans SET status='running',stage='generating_content',"
            'next_run_at=?,error_code=NULL,error_message_safe=NULL,completed_at=NULL,last_progress_at=?,updated_at=? '
            "WHERE id=? AND status='failed' AND stage='completed' AND error_code='preparation_generation_failed' "
            'AND completed_at=? AND lease_token IS NULL AND superseded_at IS NULL',
            (now,now,now,owner['id'],owner['completed_at']))
        if cursor.rowcount!=1: raise ValueError('Runtime preflight recovery CAS rejected')
        preparations.append_event(conn,plan_id=owner['id'],event_type='single_course_preflight_recovery',stage='generating_content',
            payload={'buildItemId':item['id'],'auditShaId':history_sha,'originalFailureEventId':failure['id'],
                     'contentReceiptShaId':item['content_receipt_hash'],'providerDispatchCount':len(dispatches)},now=now)
        return {**preview,'applied':True,'auditArchive':str(audit_path)}


def recover_single_content_item(*, adapter, identity, expected_history_sha, now, apply=False):
    """Plan or atomically stage attempt two; never executes a Provider call."""
    from integrations.openmaic_question_adapter import _normalize_phase_output_checkpoint
    catalog, preparations = adapter.catalog_service, adapter.repository
    repository = catalog.repository
    with repository.transaction() as conn:
        release, build = repository.lock_build_authority(conn, build_id=identity['buildId'])
        rows = repository.list_build_items(conn, build_id=identity['buildId'], for_update=True)
        item = next((row for row in rows if row['id'] == identity['buildItemId']), None)
        if (item is None or build is None or release is None
                or not repository._content_authority_is_exact(conn, release=release, build=build, rows=rows, allow_terminal=True)
                or item['status'] != 'failed' or item['attempt_count'] != 1 or item['variant_ordinal'] != 1
                or item['error_code'] != 'preparation_content_validation_failed'
                or item.get('course_id') is not None or item.get('content_lease_token') is not None
                or item['content_gate_status'] != 'not_started'
                or any(row['status'] != 'pending' for row in rows if row['id'] != item['id'])):
            raise ValueError('single content recovery authority changed')
        requested = conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE', (identity['targetFingerprint'],)).fetchall()
        if list(requested) != [{'subject': item['subject'], 'skill_id': item['skill_id'], 'variant_ordinal': 1}]:
            raise ValueError('recovery requires the unchanged exact single-slot supply request')
        histories = repository._load_content_attempt_histories_locked(conn, rows=[item])[item['id']]
        if (any(histories[1].get(key) for key in ('jobs', 'candidates', 'courses'))
                or any(histories[2].get(key) for key in ('dispatches', 'jobs', 'candidates', 'courses'))):
            raise ValueError('recovery cannot overwrite a candidate or an existing second attempt')
        dispatches = histories[1]['dispatches']
        receipt = recovery_receipt(item, dispatches, approval_reference=identity['scope']['approvalReference'])
        if expected_history_sha is not None and receipt['historyShaId'] != expected_history_sha:
            raise ValueError('recovery history differs from the reviewed failure')
        source = dispatches[0]
        original = {**item, 'content_phase': 'outline', 'content_attempt_started_at': source['attempt_started_at'],
                    'content_provider_attempt_hard_deadline_at': source['attempt_hard_deadline_at']}
        historical = repository._historical_question_fingerprints(conn, item=original,
            attempt_started_at=source['attempt_started_at'])
        command, initial = catalog._content_phase_command(item=original, dispatches=[],
            plan={'priorEvidence': [], 'historicalQuestionFingerprints': historical, 'attemptOneEvidence': None})
        prepared = catalog._content_provider_preflight(command)
        if prepared.input_sha256 != source['input_sha256'] or prepared.profile_sha256 != source['profile']:
            raise ValueError('stored outline no longer matches the frozen request/profile')
        outline = _normalize_phase_output_checkpoint(prepared, json.loads(source['checkpoint_json']))
        if digest(outline) != source['output_sha256']:
            raise ValueError('stored outline cannot be reused canonically')
        plans = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? '
            'AND target_fingerprint=? ORDER BY id FOR UPDATE', (identity['buildId'], identity['targetFingerprint'])).fetchall()
        owner = next((p for p in plans if p.get('library_target_fingerprint') == identity['targetFingerprint']), None)
        if owner is None or any(p.get('lease_token') is not None or p.get('superseded_at') is not None for p in plans):
            raise ValueError('preparation has another active worker or no current shared owner')
        preview = {'receipt': receipt, 'preservedDispatchCount': 6, 'reusedOutlineCount': 1,
            'remainingDispatchCount': 8, 'nextPhases': ['raw_candidate', 'candidate_repair', 'lesson_text', 'reconciliation', 'independent_verification'],
            'zeroProviderCalls': True, 'buildStatus': build['status'], 'ownerStatus': owner['status']}
        if not apply:
            return preview
        if expected_history_sha is None:
            raise ValueError('apply requires the exact reviewed history SHA')
        if build['status'] == 'failed':
            updated = conn.execute("UPDATE learning_catalog_build_jobs SET status='running',error_code=NULL,"
                "error_message_safe=NULL,completed_at=NULL,updated_at=? WHERE id=? AND status='failed' "
                "AND error_code='preparation_content_validation_failed'", (now, build['id']))
            if updated.rowcount != 1:
                raise ValueError('failed build recovery CAS conflict')
        elif build['status'] != 'running' or build.get('error_code') is not None:
            raise ValueError('build is not recoverable')
        claimed = repository._claim_content_attempt(conn, build={**build, 'status': 'running'}, row=item, attempt=2, now=now)
        if claimed is None:
            raise ValueError('content attempt recovery CAS conflict')
        preparations.append_event(conn, plan_id=owner['id'], event_type=EVENT, stage='generating_content', payload=receipt, now=now)
        evidence = {'item': claimed, 'dispatches': dispatches, 'recoveryReceipt': receipt}
        historical = repository._historical_question_fingerprints(conn, item=claimed, attempt_started_at=now)
        command, initial = catalog._content_phase_command(item=claimed, dispatches=[],
            plan={'priorEvidence': [], 'historicalQuestionFingerprints': historical, 'attemptOneEvidence': evidence})
        prepared = catalog._content_provider_preflight(command)
        outline = _normalize_phase_output_checkpoint(prepared, outline)
        staged = catalog.staged_content_candidate_generator
        # A local checkpoint-copy record is auditable separately from Provider
        # billing. Never copy the old Provider request id or charge its tokens twice.
        reservation = staged._repository.reserve_provider_dispatch(conn, build_item_id=item['id'], logical_attempt=2,
            phase='outline', phase_ordinal=1, generation_request_id=claimed['active_generation_request_id'],
            item_lease_token=claimed['content_lease_token'], provider=prepared.provider['name'], model=prepared.provider['model'],
            profile=prepared.profile_sha256, input_sha256=prepared.input_sha256, attempt_started_at=now,
            attempt_hard_deadline_at=claimed['content_provider_attempt_hard_deadline_at'],
            work_unit_deadline_at=claimed['content_work_unit_deadline_at'], lease_expires_at=claimed['content_lease_expires_at'],
            attempt_initial_checkpoint=initial, command_checkpoint=prepared.request['checkpoint'], prepared_request=prepared.request,
            required_budget_ms=staged.required_phase_budget_ms, clock_ms=lambda: now)
        if not reservation.created or not staged._repository.complete_provider_dispatch(conn,
                dispatch_id=reservation.dispatch['id'], build_item_id=item['id'], generation_request_id=claimed['active_generation_request_id'],
                item_lease_token=claimed['content_lease_token'], outcome='succeeded', checkpoint=outline, output_sha256=digest(outline),
                provider_request_id_hash=None, input_tokens=None, output_tokens=None, billing_evidence='unknown', safe_error_code=None, completed_at=now):
            raise ValueError('outline reuse could not be recorded atomically')
        current_rows = [claimed if row['id'] == item['id'] else row for row in rows]
        advanced = repository._complete_content_provider_phase_locked(conn, locked_item=claimed,
            locked_build={**build, 'status': 'running'}, locked_items=current_rows, persisted_dispatch_id=reservation.dispatch['id'],
            expected_next_phase='raw_candidate', expected_next_phase_ordinal=2, candidate_course=None,
            generator_profile=catalog._content_profile_payload('generator'), now=now)
        if advanced is None:
            raise ValueError('outline handoff CAS conflict')
        if all(plan['status'] == 'failed' for plan in plans):
            if preparations.recover_shared_content_validation_plans(conn, build_id=build['id'],
                    target_fingerprint=identity['targetFingerprint'], now=now) != len(plans):
                raise ValueError('shared preparation recovery did not reopen the exact owners')
        elif len(plans) == 1 and owner['status'] in {'queued', 'running'} and owner['stage'] in {'generating_content', 'completed'}:
            updated = conn.execute("UPDATE learning_curriculum_preparation_plans SET status='running',stage='generating_content',"
                "next_run_at=?,error_code=NULL,error_message_safe=NULL,completed_at=NULL,last_progress_at=?,updated_at=? "
                "WHERE id=? AND status=? AND stage=? AND lease_token IS NULL AND superseded_at IS NULL",
                (now,now,now,owner['id'],owner['status'],owner['stage']))
            if updated.rowcount != 1:
                raise ValueError('shared owner recovery CAS conflict')
        else:
            raise ValueError('mixed preparation states require diagnosis')
        return {**preview, 'applied': True, 'nextPhase': advanced['content_phase'], 'logicalAttempt': 2,
                'reusedOutlineDispatchId': reservation.dispatch['id']}
