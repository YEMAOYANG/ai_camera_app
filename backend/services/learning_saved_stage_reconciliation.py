"""Validate a completed saved classroom and reconcile only its existing Runtime."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from content.learning_budget_policy import canonical, digest
from integrations.openmaic_formal_playful import playful_generation_kwargs
from integrations.openmaic_formal_quality import quality_canonical_json, quality_sha, quality_snapshot
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient

EVENT = 'single_course_saved_stage_reconciliation'
ARCHIVES = Path(__file__).resolve().parents[1] / 'data/learning-provider-replies'
_DISCUSSION_REPAIR_FIELDS = {'schemaVersion', 'promptVersion', 'sessionId', 'stageId',
    'sourceSnapshotSha256', 'inputSnapshotSha256', 'outputSnapshotSha256', 'frozenContextSha256',
    'rejectedReviewSha256', 'requestSha256', 'providerResponseSha256', 'providerRequestIdHash',
    'providerId', 'modelId', 'authorizationId', 'namespace', 'repairReference', 'insertions', 'receiptSha256'}
_DISCUSSION_REPAIR_IDENTITY = ('sessionId', 'stageId', 'sourceSnapshotSha256', 'inputSnapshotSha256',
                              'frozenContextSha256', 'rejectedReviewSha256')


def _validate_learner_discussion_audit(receipt, prepared_snapshot, result, audit):
    """Check immutable Native source/request/response artifacts without any Provider call."""
    names = {'input', 'request', 'provider-response', 'rejected-review', 'completion', 'dispatch.claim'}
    if not isinstance(audit, dict) or set(audit) != names or any(not isinstance(audit[key], dict) for key in names):
        raise ValueError('saved-stage learner discussion repair audit is incomplete')
    identity = {key: receipt[key] for key in _DISCUSSION_REPAIR_IDENTITY}
    archived_input, request, response = audit['input'], audit['request'], audit['provider-response']
    rejected, derived, claim = audit['rejected-review'], audit['completion'], audit['dispatch.claim']
    context = archived_input.get('frozenContext')
    quality = (result.get('professionalCreation') or {}).get('teachingQuality')
    if (set(archived_input) != set(identity) | {'frozenContext', 'snapshot', 'sourceScenes'}
            or any(archived_input[key] != value for key, value in identity.items())
            or not isinstance(context, dict) or set(context) != {'gradeBoundary', 'selectionPlan', 'teachingBrief'}
            or quality_sha(context) != receipt['frozenContextSha256']
            or quality_sha(archived_input.get('snapshot')) != quality_sha(prepared_snapshot)
            or quality_sha(quality_snapshot({'stage': result['stage'], 'scenes': archived_input.get('sourceScenes')}))
               != receipt['inputSnapshotSha256']
            or not isinstance(quality, dict) or quality.get('status') != 'passed'
            or quality.get('snapshotSha256') != receipt['outputSnapshotSha256']
            or not isinstance(context['selectionPlan'], dict)
            or not isinstance(context['selectionPlan'].get('planSha256'), str)
            or re.fullmatch(r'[0-9a-f]{64}', context['selectionPlan']['planSha256']) is None
            or quality.get('selectionPlanSha256') != context['selectionPlan']['planSha256']
            or any(quality.get(key + 'Sha256') != quality_sha(context[key])
                   for key in ('gradeBoundary', 'teachingBrief'))
            or set(rejected) != {'status', 'snapshotSha256', 'issues'}
            or rejected['status'] != 'needs_revision' or rejected['snapshotSha256'] != receipt['inputSnapshotSha256']
            or not isinstance(rejected['issues'], list) or not rejected['issues']
            or quality_sha(rejected) != receipt['rejectedReviewSha256']
            or quality_sha(request) != receipt['requestSha256']
            or quality_sha(response) != receipt['providerResponseSha256']
            or response.get('providerRequestIdHash') != receipt['providerRequestIdHash']
            or any(request.get(key) != value or response.get(key) != value for key, value in {
                'schemaVersion': 'mira.openmaic.courseware-provider-call.v1',
                'phase': 'learner_discussion_repair', 'requestId': 'learner-repair-' + quality_sha(identity)}.items())
            or any(claim.get(key) != value for key, value in {**identity,
                **{key: receipt[key] for key in ('authorizationId', 'namespace', 'repairReference', 'requestSha256')}}.items())
            or set(derived) != {'scenes', 'receipt'}
            or quality_canonical_json(derived['receipt']) != quality_canonical_json(receipt)
            or quality_sha(quality_snapshot({'stage': result['stage'], 'scenes': derived['scenes']}))
               != receipt['outputSnapshotSha256']):
        raise ValueError('saved-stage learner discussion repair audit provenance mismatch')
    try:
        provider_output = json.loads(response['content'])
        user_prompt = json.loads(request['userPrompt'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('saved-stage learner discussion repair audit payload is invalid') from exc
    if (not isinstance(provider_output, dict) or set(provider_output) != {'insertions'}
            or quality_canonical_json(provider_output['insertions']) != quality_canonical_json(receipt['insertions'])
            or not isinstance(user_prompt, dict)
            or any(quality_sha(user_prompt.get(key)) != quality_sha(value) for key, value in {
                **context, 'snapshot': prepared_snapshot, 'rejectedReview': rejected,
                'promptVersion': receipt['promptVersion']}.items())):
        raise ValueError('saved-stage learner discussion repair Provider payload changed')


def validate_learner_discussion_repair(completion, prepared_snapshot, *, repair_audit=None):
    """Verify the two AI discussion additions against the frozen quality projection."""
    receipt = completion.get('learnerDiscussionRepair')
    if (not isinstance(receipt, dict) or set(receipt) != _DISCUSSION_REPAIR_FIELDS
            or not isinstance(prepared_snapshot, dict)):
        raise ValueError('saved-stage learner discussion repair evidence is incomplete')
    hashes = ('sourceSnapshotSha256', 'inputSnapshotSha256', 'outputSnapshotSha256',
        'frozenContextSha256', 'rejectedReviewSha256', 'requestSha256', 'providerResponseSha256',
        'providerRequestIdHash', 'authorizationId', 'repairReference', 'receiptSha256')
    unsigned = {key: value for key, value in receipt.items() if key != 'receiptSha256'}
    if (any(not isinstance(receipt[key], str) or re.fullmatch(r'[0-9a-f]{64}', receipt[key]) is None
            for key in hashes)
            or receipt['schemaVersion'] != 'mira.openmaic.learner-discussion-repair.v1'
            or receipt['promptVersion'] != 'mira.formal-learner-discussion-repair.v1'
            or receipt['providerId'] != 'deepseek' or receipt['modelId'] != 'deepseek-v4-flash'
            or receipt['sessionId'] != completion['sessionId']
            or receipt['stageId'] != completion['stageId']
            or receipt['sourceSnapshotSha256'] != completion['sourceSnapshotSha256']
            or receipt['inputSnapshotSha256'] != completion['repairSnapshotSha256']
            or receipt['namespace'] != completion['sessionId'] + ':completion'
            or quality_sha(unsigned) != receipt['receiptSha256']
            or quality_sha(prepared_snapshot) != receipt['inputSnapshotSha256']):
        raise ValueError('saved-stage learner discussion repair identity or provenance mismatch')
    original = quality_snapshot(prepared_snapshot)
    result = completion.get('result')
    if not isinstance(result, dict):
        raise ValueError('saved-stage learner discussion repair result is missing')
    output = quality_snapshot(result)
    if (quality_sha(original) != receipt['inputSnapshotSha256']
            or quality_sha(output) != receipt['outputSnapshotSha256']
            or original['stage']['id'] != completion['stageId']
            or len(original['scenes']) < 2 or len(output['scenes']) != len(original['scenes'])
            or original['scenes'][0]['id'] != 'scene-p1' or original['scenes'][-1]['id'] != 'scene-p8'):
        raise ValueError('saved-stage learner discussion repair snapshots changed')
    roster = result['stage'].get('generatedAgentConfigs')
    teacher_ids = ([agent.get('id') for agent in roster
                    if isinstance(agent, dict) and agent.get('role') == 'teacher']
                   if isinstance(roster, list) else [])
    if (len(teacher_ids) != 1 or not isinstance(teacher_ids[0], str) or not teacher_ids[0]
            or not isinstance(result['stage'].get('agentIds'), list)
            or result['stage']['agentIds'].count(teacher_ids[0]) != 1):
        raise ValueError('saved-stage learner discussion repair teacher roster is invalid')
    insertions = receipt['insertions']
    if not isinstance(insertions, list) or len(insertions) != 2:
        raise ValueError('saved-stage learner discussion repair must contain two insertions')
    previous_ids = {action.get('id') for scene in original['scenes'] for action in scene['actions']
                    if isinstance(action, dict) and isinstance(action.get('id'), str)}
    new_ids = set()
    for insertion, index in zip(insertions, (0, len(original['scenes']) - 1)):
        before, after = original['scenes'][index], output['scenes'][index]
        if (not isinstance(insertion, dict) or set(insertion) != {'sceneId', 'afterActionCount', 'action'}
                or insertion['sceneId'] != before['id'] or after['id'] != before['id']
                or type(insertion['afterActionCount']) is not int
                or insertion['afterActionCount'] != len(before['actions'])
                or any(isinstance(action, dict) and action.get('type') == 'discussion'
                       for action in before['actions'])
                or len(after['actions']) != len(before['actions']) + 1):
            raise ValueError('saved-stage learner discussion repair insertion location changed')
        action = insertion['action']
        if (not isinstance(action, dict) or set(action) != {'id', 'type', 'topic', 'prompt', 'agentId'}
                or action['type'] != 'discussion'
                or any(not isinstance(action[key], str) or not action[key].strip()
                       for key in ('id', 'topic', 'prompt', 'agentId'))
                or action['agentId'] != teacher_ids[0]
                or action['id'] in previous_ids or action['id'] in new_ids
                or quality_canonical_json(after['actions'][-1]) != quality_canonical_json(action)):
            raise ValueError('saved-stage learner discussion repair action is invalid')
        new_ids.add(action['id'])
        after['actions'].pop()
    if quality_canonical_json(output) != quality_canonical_json(original):
        raise ValueError('saved-stage learner discussion repair modified frozen classroom content')
    if repair_audit is not None:
        _validate_learner_discussion_audit(receipt, prepared_snapshot, result, repair_audit)
    return receipt['receiptSha256']


def validate_saved_stage_completion(completion, source_bytes, promoted, *, runtime, expected_input_sha, upstream,
                                    prepared_snapshot=None, learner_discussion_audit=None):
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
    if 'learnerDiscussionRepair' in completion:
        validate_learner_discussion_repair(completion, prepared_snapshot, repair_audit=learner_discussion_audit)
    return completion['receiptSha256']


def reconcile_saved_stage(*, runtime_service, preparation_repository, identity, state,
                          runtime_id, completion_path, now, duplicate_recovery_sha=None):
    selection_proof = None
    if duplicate_recovery_sha:
        from services.learning_duplicate_runtime_recovery import authorized_selection
        with runtime_service.repository.transaction() as conn:
            runtime, selection_proof = authorized_selection(conn, identity=identity, state=state,
                runtime_id=runtime_id, audit_sha=duplicate_recovery_sha)
    elif len(state['runtimes']) == 1:
        runtime = state['runtimes'][0]
    else:
        raise ValueError('saved-stage reconciliation requires the existing single-slot Runtime')
    if (runtime['id'] != runtime_id
            or state['otherTouchedItems'] or not state.get('owner') or not state.get('item')):
        raise ValueError('saved-stage reconciliation requires the existing single-slot Runtime')
    owner, item = state['owner'], state['item']
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
    if selection_proof and hashlib.sha256(source_bytes).hexdigest() != selection_proof['files']['selectedJob']['sha256']:
        raise ValueError('saved-stage source differs from the selected original timeout')
    promoted_path = path.parent.parent.parent / 'classroom-jobs' / (runtime['upstream_job_id'] + '.json')
    promoted_bytes = promoted_path.read_bytes()
    promoted = json.loads(promoted_bytes)
    manifest = json.loads(runtime['feature_manifest_json'])
    expected_input_sha = runtime_service._formal_input_sha256(runtime_request_id=runtime['request_id'],
        generation_contract=manifest.get('generationContract'), formal_contract=manifest.get('formalRuntimeContract'),
        paid_budget=manifest.get('paidBudget'))
    upstream = runtime_service.client.get_generation_job_by_request_id(runtime['request_id'],
        **playful_generation_kwargs(manifest.get('generationContract')))
    prepared_snapshot = json.loads((path.parent / 'prepared-snapshot.json').read_bytes())
    learner_discussion_audit = None
    if 'learnerDiscussionRepair' in completion:
        # Validate the identity before using its digest in a fixed Native audit path.
        validate_learner_discussion_repair(completion, prepared_snapshot)
        repair_identity = {key: completion['learnerDiscussionRepair'][key] for key in _DISCUSSION_REPAIR_IDENTITY}
        repair_folder = path.parent.parent.parent / 'formal-learner-discussion-repairs' / quality_sha(repair_identity)
        learner_discussion_audit = {name: json.loads((repair_folder / (name if name == 'dispatch.claim' else name + '.json')).read_bytes())
            for name in ('input', 'request', 'provider-response', 'rejected-review', 'completion', 'dispatch.claim')}
    receipt_sha = validate_saved_stage_completion(completion, source_bytes, promoted, runtime=runtime,
        expected_input_sha=expected_input_sha, upstream=upstream, prepared_snapshot=prepared_snapshot,
        learner_discussion_audit=learner_discussion_audit)
    if quality_sha(prepared_snapshot) != completion['repairSnapshotSha256']:
        raise ValueError('saved-stage repair snapshot no longer matches its completion')
    audit = {'schemaVersion': 'mira.single-course.saved-stage-reconciliation.v1',
        'originalRuntime': runtime, 'originalOwner': owner, 'buildItemId': identity['buildItemId'],
        'completionReceiptSha256': receipt_sha, 'sourceJobSha256': completion['sourceJobSha256'],
        'promotedJobSha256': hashlib.sha256(promoted_bytes).hexdigest(), 'formalInputSha256': expected_input_sha,
        **({'duplicateRecoverySha256': duplicate_recovery_sha, 'historicalRuntimeCount': 2} if duplicate_recovery_sha else {})}
    audit_sha = digest(audit)
    with runtime_service.repository.transaction() as conn:
        current = runtime_service.repository.get_runtime_classroom(conn, runtime_id=runtime_id, for_update=True)
        current_owner = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE id=? FOR UPDATE', (owner['id'],)).fetchone()
        current_item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE', (item['id'],)).fetchone()
        if duplicate_recovery_sha:
            current_history = [dict(row) for row in conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms '
                'WHERE candidate_build_item_id=? ORDER BY created_at,id FOR UPDATE', (identity['buildItemId'],)).fetchall()]
            authorized_selection(conn, identity=identity, state={**state, 'runtimes': current_history},
                runtime_id=runtime_id, audit_sha=duplicate_recovery_sha)
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
