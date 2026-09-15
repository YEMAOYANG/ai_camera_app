"""Audited one-time recovery of the English v2 JSON-authority preflight failure.

The original three rows remain unchanged. Attempt two reuses two canonical
checkpoints locally and resumes normal candidate repair, with no Provider call
in this operator. The original production authorization is never changed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from content.learning_budget_policy import canonical, digest

KIND = 'mira.single-course.english-3d-preflight-recovery.v1'
ARCHIVE_ROOT = Path(__file__).resolve().parents[1] / 'data/learning-provider-replies'
BRIDGE = Path(__file__).resolve().parents[1] / 'content/formal_question_preflight_cli.py'
PHASES = (('outline', 1, 'succeeded'), ('raw_candidate', 2, 'succeeded'),
          ('candidate_repair', 3, 'failed_safe'))


def preflight_history(item, dispatches):
    """Validate original rows independently of the current attempt-two state."""
    if ((item.get('grade_code'), item.get('subject'), item.get('skill_id'), item.get('variant_ordinal'))
            != ('primary_6', 'english', 'past_future', 1)
            or not isinstance(dispatches, list) or len(dispatches) != 3):
        raise ValueError('preflight recovery requires the exact English course and three original phases')
    for row, phase in zip(dispatches, PHASES):
        if (row.get('build_item_id') != item['id'] or row.get('logical_attempt') != 1
                or row.get('generation_request_id') != item['generation_request_id']
                or (row.get('phase'), row.get('phase_ordinal'), row.get('status')) != phase
                or row.get('completed_at') is None
                or any(re.fullmatch(r'[a-f0-9]{64}', str(row.get(key) or '')) is None
                       for key in ('input_sha256', 'profile'))
                or any(row.get(key) != dispatches[0].get(key)
                       for key in ('attempt_started_at', 'attempt_hard_deadline_at'))):
            raise ValueError('preflight recovery original dispatch identity changed')
        if phase[2] == 'succeeded' and (
                digest(json.loads(row['checkpoint_json'])) != row.get('output_sha256')
                or row.get('billing_evidence') != 'reported'
                or re.fullmatch(r'[a-f0-9]{64}', str(row.get('provider_request_id_hash') or '')) is None
                or any(type(row.get(key)) is not int or row[key] < 0 for key in ('input_tokens', 'output_tokens'))):
            raise ValueError('preflight recovery successful source checkpoint or billing changed')
    failed = dispatches[-1]
    if (failed.get('safe_error_code') != 'question_phase_preflight_rejected'
            or failed.get('billing_evidence') != 'unknown'
            or any(failed.get(key) is not None for key in (
                'checkpoint_json', 'output_sha256', 'provider_request_id_hash', 'input_tokens', 'output_tokens'))):
        raise ValueError('preflight recovery cannot retry a returned or ambiguous Provider call')
    return dispatches


def preflight_receipt(item, dispatches, *, approval_reference, source_audit_sha):
    preflight_history(item, dispatches)
    if re.fullmatch(r'[a-f0-9]{64}', str(source_audit_sha)) is None:
        raise ValueError('preflight recovery source audit hash is invalid')
    receipt = {'recoveryKindId': KIND, 'buildItemId': item['id'],
        'failedDispatchId': dispatches[2]['id'], 'failedInputShaId': dispatches[2]['input_sha256'],
        'sourceOutlineDispatchId': dispatches[0]['id'], 'sourceOutlineShaId': dispatches[0]['output_sha256'],
        'sourceRawCandidateDispatchId': dispatches[1]['id'], 'sourceRawCandidateShaId': dispatches[1]['output_sha256'],
        'sourceAuditShaId': source_audit_sha, 'historyShaId': digest(dispatches),
        'approvalReferenceId': approval_reference, 'maximumDispatchCount': 17}
    return {**receipt, 'recoveryId': digest(receipt)}


def validate_failure_audit(audit, *, identity, state):
    if (not isinstance(audit, dict)
            or audit.get('schemaVersion') != 'mira.english-3d.preflight-failure-state.v1'
            or audit.get('auditSha256') != digest({k: v for k, v in audit.items() if k != 'auditSha256'})
            or audit.get('dbStateSha256') != digest(state) or audit.get('dbState') != state
            or audit.get('identity') != identity or audit.get('runtimes') != []
            or audit.get('reservationAtOrAfterFailedPhase') != []):
        raise ValueError('preflight recovery audit no longer matches the exact failed state')
    rows = preflight_history(state['item'], state['dispatches'])
    reservations = audit.get('taskReservations')
    if (not isinstance(reservations, list) or len(reservations) != 2
            or any(row.get('state') != 'settled' or row.get('authorization_id') != audit['authorization']['id']
                   or row.get('dispatched_at', rows[-1]['dispatched_at']) >= rows[-1]['dispatched_at']
                   for row in reservations)):
        raise ValueError('preflight recovery requires two settled calls and no failed-phase Provider dispatch')
    return rows


def _check_source_archives(audit, dispatches):
    entries = audit.get('sidecarArchives')
    if not isinstance(entries, list) or len(entries) != 3:
        raise ValueError('preflight recovery archive coverage changed')
    for index, (entry, row) in enumerate(zip(entries, dispatches)):
        if (entry.get('dispatchId') != row['id'] or entry.get('inputSha256') != row['input_sha256']
                or entry.get('phase') != row['phase'] or entry.get('phaseOrdinal') != row['phase_ordinal']):
            raise ValueError('preflight recovery archive identity changed')
        for key, suffix in (('intent', '.intent.json'), ('response', '.json'), ('temporaryResponse', '.reply.tmp')):
            path = ARCHIVE_ROOT / (row['phase'] + '.' + row['input_sha256'] + suffix)
            recorded = entry.get('files', {}).get(key) or {}
            should_exist = index < 2 and key != 'temporaryResponse'
            if (recorded.get('path') != str(path) or recorded.get('exists') is not should_exist
                    or path.exists() != should_exist
                    or should_exist and hashlib.sha256(path.read_bytes()).hexdigest() != recorded.get('sha256')):
                raise ValueError('preflight recovery source archive changed or failed phase has an intent')


def recover_preflight_content(*, adapter, identity, expected_history_sha, now, failure_audit_path, apply=False):
    from integrations.openmaic_formal_media import REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY, policy_from_target
    from integrations.openmaic_question_adapter import _normalize_phase_output_checkpoint
    from services.learning_content_recovery import EVENT
    audit = json.loads(Path(failure_audit_path).read_text())
    catalog, preparations = adapter.catalog_service, adapter.repository
    repository = catalog.repository
    with repository.transaction() as conn:
        release, build = repository.lock_build_authority(conn, build_id=identity['buildId'])
        rows = repository.list_build_items(conn, build_id=identity['buildId'], for_update=True)
        item = next((row for row in rows if row['id'] == identity['buildItemId']), None)
        if (not item or not build or not release
                or not repository._content_authority_is_exact(conn, release=release, build=build, rows=rows, allow_terminal=True)
                or item['attempt_count'] != 1 or item['status'] != 'failed' or item['content_phase'] != 'failed'
                or item['error_code'] != 'preparation_content_provider_unavailable'
                or item['content_gate_status'] != 'not_started' or item.get('content_gate_attempt_count') != 0
                or item.get('content_claim_attempt_ordinal') != 1
                or item.get('active_generation_request_id') != item.get('generation_request_id')
                or any(item.get(key) is not None for key in ('course_id', 'course_version', 'content_lease_token'))
                or any(row['status'] != 'pending' for row in rows if row['id'] != item['id'])
                or build['status'] != 'failed' or build['error_code'] != 'preparation_content_provider_unavailable'
                or policy_from_target(json.loads(build['target_spec_json'])) != REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY):
            raise ValueError('preflight recovery requires the unchanged failed v2 single course')
        requested = conn.execute('SELECT subject,skill_id,variant_ordinal FROM learning_course_supply_requests '
            'WHERE target_fingerprint=? AND enabled=TRUE', (identity['targetFingerprint'],)).fetchall()
        if list(requested) != [{'subject': 'english', 'skill_id': 'past_future', 'variant_ordinal': 1}]:
            raise ValueError('preflight recovery single-slot supply scope changed')
        plans = conn.execute('SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? '
            'AND target_fingerprint=? ORDER BY id FOR UPDATE', (build['id'], identity['targetFingerprint'])).fetchall()
        if len(plans) != 1:
            raise ValueError('preflight recovery requires one exact shared owner')
        owner = plans[0]
        if (owner['status'] != 'failed' or owner.get('error_code') != 'preparation_content_provider_unavailable'
                or owner.get('lease_token') is not None or owner.get('superseded_at') is not None
                or owner.get('library_target_fingerprint') != identity['targetFingerprint']):
            raise ValueError('preflight recovery shared owner changed or has an active worker')
        histories = repository._load_content_attempt_histories_locked(conn, rows=[item])[item['id']]
        if (any(histories[1].get(k) for k in ('jobs', 'candidates', 'courses', 'recoveryReceipt'))
                or any(histories[2].get(k) for k in ('dispatches', 'jobs', 'candidates', 'courses'))):
            raise ValueError('preflight recovery cannot replace a candidate or existing second attempt')
        dispatches = histories[1]['dispatches']
        state = {'build': dict(build), 'item': dict(item), 'owner': dict(owner), 'dispatches': list(dispatches)}
        validate_failure_audit(audit, identity=identity, state=state)
        _check_source_archives(audit, dispatches)
        authorization = audit['authorization']
        current_grant = conn.execute('SELECT * FROM learning_budget_authorizations WHERE id=? FOR UPDATE', (authorization['id'],)).fetchone()
        if (current_grant is None or any(current_grant.get(k) != v for k, v in authorization.items())
                or current_grant['revoked_at'] is not None or current_grant['expires_at'] <= now
                or json.loads(current_grant['scope_json']) != identity['scope']):
            raise ValueError('preflight recovery original production grant changed or expired')
        charges = conn.execute('SELECT id,state,dispatched_at FROM learning_budget_reservations WHERE authorization_id=? '
            'ORDER BY created_at,id FOR UPDATE', (authorization['id'],)).fetchall()
        if ([r['id'] for r in charges] != [r['id'] for r in audit['taskReservations']]
                or any(r['state'] != 'settled' or r['dispatched_at'] >= dispatches[-1]['dispatched_at'] for r in charges)):
            raise ValueError('preflight recovery Provider ledger changed since the zero-dispatch audit')
        if conn.execute('SELECT id FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?', (item['id'],)).fetchall():
            raise ValueError('preflight recovery cannot coexist with a Native classroom')
        # Reproduce every original request and checkpoint against its frozen inventory.
        original = {**item, 'status': 'processing', 'content_attempt_started_at': dispatches[0]['attempt_started_at'],
            'content_provider_attempt_hard_deadline_at': dispatches[0]['attempt_hard_deadline_at']}
        historical = repository._historical_question_fingerprints(conn, item=original,
            attempt_started_at=dispatches[0]['attempt_started_at'])
        original_plan = {'priorEvidence': [], 'historicalQuestionFingerprints': historical, 'attemptOneEvidence': None}
        sources = []
        for index, source in enumerate(dispatches):
            command, _ = catalog._content_phase_command(item={**original, 'content_phase': source['phase']},
                dispatches=dispatches[:index], plan=original_plan)
            prepared = catalog._content_provider_preflight(command)
            if prepared.input_sha256 != source['input_sha256'] or prepared.profile_sha256 != source['profile']:
                raise ValueError('preflight recovery source request or profile hash changed')
            if index < 2:
                checkpoint = _normalize_phase_output_checkpoint(prepared, json.loads(source['checkpoint_json']))
                if digest(checkpoint) != source['output_sha256']:
                    raise ValueError('preflight recovery source checkpoint cannot be reused')
                sources.append(checkpoint)
        request = prepared.request
        objective = {'gradeCode': request['gradeCode'], 'subject': request['subject'],
            'skillId': request['skillBoundary']['skillId'], 'objectivePolicy': request['objectivePolicy'],
            'questions': request['checkpoint']['rawCandidate']['questions']}
        checked = subprocess.run([sys.executable, '-B', str(BRIDGE)], input=canonical(objective),
            capture_output=True, text=True, timeout=10, check=False)
        if checked.returncode != 0:
            raise ValueError('preflight recovery requires the repaired local Host authority bridge')
        issues = json.loads(checked.stdout)
        if issues.get('schemaVersion') != 'mira.formal-objective-preflight.v1' or not isinstance(issues.get('issues'), list):
            raise ValueError('preflight recovery Host result contract changed')
        receipt = preflight_receipt(item, dispatches, approval_reference=identity['scope']['approvalReference'],
            source_audit_sha=audit['auditSha256'])
        plan_sha = digest({'receipt': receipt, 'dbStateSha256': audit['dbStateSha256'],
            'bridgeSourceSha256': hashlib.sha256(BRIDGE.read_bytes()).hexdigest(), 'hostPreflight': issues})
        if expected_history_sha is not None and expected_history_sha != plan_sha:
            raise ValueError('preflight recovery plan differs from the reviewed evidence')
        preview = {'historySha256': plan_sha, 'receipt': receipt, 'preservedDispatchCount': 3,
            'reusedCheckpointCount': 2, 'nextPhase': 'candidate_repair', 'logicalAttempt': 2,
            'providerCalls': 0, 'hostPreflight': issues, 'authorizationExpiresAt': current_grant['expires_at']}
        if not apply:
            return preview
        if expected_history_sha is None:
            raise ValueError('preflight recovery apply requires the exact reviewed plan hash')
        archive_path = ARCHIVE_ROOT / ('content-preflight-recovery-' + audit['auditSha256'] + '.json')
        try:
            fd = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if json.loads(archive_path.read_text()) != audit:
                raise ValueError('preflight recovery immutable archive conflict')
        else:
            with os.fdopen(fd, 'w') as out:
                out.write(canonical(audit)); out.flush(); os.fsync(out.fileno())
        changed = conn.execute("UPDATE learning_catalog_build_jobs SET status='running',error_code=NULL,"
            "error_message_safe=NULL,completed_at=NULL,updated_at=? WHERE id=? AND status='failed' "
            "AND error_code='preparation_content_provider_unavailable'", (now, build['id']))
        if changed.rowcount != 1:
            raise ValueError('preflight recovery build CAS rejected')
        active_build = {**build, 'status': 'running', 'error_code': None}
        active = repository._claim_content_attempt(conn, build=active_build, row=item, attempt=2, now=now)
        if active is None:
            raise ValueError('preflight recovery attempt-two CAS rejected')
        preparations.append_event(conn, plan_id=owner['id'], event_type=EVENT, stage='generating_content', payload=receipt, now=now)
        evidence = {'item': active, 'dispatches': dispatches, 'recoveryReceipt': receipt}
        copied = []
        fresh_history = repository._historical_question_fingerprints(conn, item=active, attempt_started_at=now)
        staged = catalog.staged_content_candidate_generator
        for index, checkpoint in enumerate(sources):
            if index:
                active = repository._claim_existing_provider_phase(conn, build=active_build, row=active,
                    now=now, locked_dispatches=copied)
                if active is None:
                    raise ValueError('preflight recovery local reuse lease CAS rejected')
            command, initial = catalog._content_phase_command(item=active, dispatches=copied,
                plan={'priorEvidence': [], 'historicalQuestionFingerprints': fresh_history, 'attemptOneEvidence': evidence})
            prepared = catalog._content_provider_preflight(command)
            checkpoint = _normalize_phase_output_checkpoint(prepared, checkpoint)
            reservation = staged._repository.reserve_provider_dispatch(conn, build_item_id=item['id'], logical_attempt=2,
                phase=command.phase, phase_ordinal=command.phase_ordinal, generation_request_id=active['active_generation_request_id'],
                item_lease_token=active['content_lease_token'], provider=prepared.provider['name'], model=prepared.provider['model'],
                profile=prepared.profile_sha256, input_sha256=prepared.input_sha256, attempt_started_at=now,
                attempt_hard_deadline_at=active['content_provider_attempt_hard_deadline_at'],
                work_unit_deadline_at=active['content_work_unit_deadline_at'], lease_expires_at=active['content_lease_expires_at'],
                attempt_initial_checkpoint=initial, command_checkpoint=prepared.request['checkpoint'], prepared_request=prepared.request,
                required_budget_ms=staged.required_phase_budget_ms, clock_ms=lambda: now)
            if not reservation.created or not staged._repository.complete_provider_dispatch(conn,
                    dispatch_id=reservation.dispatch['id'], build_item_id=item['id'], generation_request_id=active['active_generation_request_id'],
                    item_lease_token=active['content_lease_token'], outcome='succeeded', checkpoint=checkpoint, output_sha256=digest(checkpoint),
                    provider_request_id_hash=None, input_tokens=None, output_tokens=None, billing_evidence='unknown', safe_error_code=None, completed_at=now):
                raise ValueError('preflight recovery local checkpoint recording failed')
            copied = [dict(r) for r in conn.execute('SELECT * FROM learning_course_provider_dispatches WHERE build_item_id=? '
                'AND logical_attempt=2 ORDER BY phase_ordinal', (item['id'],)).fetchall()]
            advanced = repository._complete_content_provider_phase_locked(conn, locked_item=active,
                locked_build=active_build, locked_items=[active if r['id'] == item['id'] else r for r in rows],
                persisted_dispatch_id=reservation.dispatch['id'], expected_next_phase=('raw_candidate' if index == 0 else 'candidate_repair'),
                expected_next_phase_ordinal=index + 2, candidate_course=None,
                generator_profile=catalog._content_profile_payload('generator'), now=now)
            if advanced is None:
                raise ValueError('preflight recovery local checkpoint handoff rejected')
            active = advanced
        changed = conn.execute("UPDATE learning_curriculum_preparation_plans SET status='running',stage='generating_content',"
            'next_run_at=?,error_code=NULL,error_message_safe=NULL,completed_at=NULL,last_progress_at=?,updated_at=? '
            "WHERE id=? AND status='failed' AND error_code='preparation_content_provider_unavailable' "
            'AND lease_token IS NULL AND superseded_at IS NULL', (now, now, now, owner['id']))
        if changed.rowcount != 1:
            raise ValueError('preflight recovery owner CAS rejected')
        return {**preview, 'applied': True, 'auditArchive': str(archive_path),
            'reusedDispatchIds': [row['id'] for row in copied]}
