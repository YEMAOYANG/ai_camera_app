"""A separate, explicitly approved recovery for the current two-page failure.

No API route exposes this module. Preflight performs reads only; the caller owns
the transaction. The old unknown call and failed job remain immutable evidence.
Only the granted job gets a new request identity under the durable-response
contract, with at most one new vision reservation for each approved page.
"""
from __future__ import annotations

import hashlib
import json
import re

from core.errors import ApiError


SCHEMA = 'homework.operator-recognition-response-repair.v1'
WIRE_CONTRACT = 'durable-vision-response.v3'
APPROVAL_TEXT = '允许这份两页作业重新分析一次'
ITEM_MARKER = '__operator_recognition_repair__'
JOB_PREFIX = 'hwj_response_repair_'
TTL_MS = 30 * 60 * 1000
MAXIMUM_PAGES = 2
RESPONSE_SCHEMA = 'mira.homework-recognition-response.v1'


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _parsed(value, fallback=None):
    return json.loads(value) if isinstance(value, str) else value if value is not None else fallback


def _error(code='homework_repair_scope_changed'):
    raise ApiError(code, '作业或授权范围已变化，不会发出新的识别请求', 409)


def _scope(scope):
    required = {'phone', 'familyId', 'childId', 'submissionId', 'expectedRevision', 'unknownCallId'}
    if (not isinstance(scope, dict) or set(scope) != required
            or not isinstance(scope['phone'], str) or not re.fullmatch(r'\d{11}', scope['phone'])
            or type(scope['expectedRevision']) is not int or scope['expectedRevision'] < 1):
        _error('homework_repair_scope_invalid')
    for key in required - {'phone', 'expectedRevision'}:
        if not isinstance(scope[key], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', scope[key]):
            _error('homework_repair_scope_invalid')


def _input(service, page):
    binding = service._recognition_repair_input(page)
    provider = service.provider
    if getattr(provider, 'capture_received_response', False) is not True:
        _error('homework_repair_contract_invalid')
    spec = service.policy['recognitionPrompt']
    prompt = service.prompts.get_prompt(spec['id'], spec['version'])
    if prompt is None:
        _error('homework_repair_contract_invalid')
    binding['wire'] = {
        **binding['wire'],
        'contract': WIRE_CONTRACT,
        'captureReceivedResponse': True,
        'responseSchema': RESPONSE_SCHEMA,
        'promptId': spec['id'],
        'promptVersion': spec['version'],
        'promptSha256': _digest({'body': prompt.body, 'systemPrompt': service.policy['systemPrompt']}),
        'maximumOutputTokens': 7000,
        'temperature': 0.6 if getattr(provider, 'disable_thinking', False) else 1.0,
        'disableThinking': bool(getattr(provider, 'disable_thinking', False)),
        'jsonOutput': bool(getattr(provider, 'json_output', False)),
        'timeoutSeconds': provider.timeout_seconds,
    }
    return binding


def _inputs(service, pages):
    if len(pages) != MAXIMUM_PAGES:
        _error()
    return [_input(service, page) for page in pages]


def _snapshots(conn, grant):
    old_call = conn.execute('SELECT * FROM homework_provider_calls WHERE id=?', (grant.get('oldCallId'),)).fetchone()
    old_job = conn.execute('SELECT * FROM homework_jobs WHERE id=?', (grant.get('oldJobId'),)).fetchone()
    if (not old_call or not old_job or _digest(dict(old_call)) != grant.get('oldCallSha256')
            or _digest(dict(old_job)) != grant.get('oldJobSha256')):
        _error('homework_repair_authorization_invalid')


def _validate_grant(service, conn, record, row, *, scope=None):
    try:
        grant = _parsed(record['result_json'], {})
    except (ValueError, TypeError):
        _error('homework_repair_authorization_invalid')
    if (not isinstance(grant, dict) or record['request_sha256'] != _digest(grant)
            or record['submission_id'] != row['id'] or record['item_id'] != ITEM_MARKER
            or grant.get('schema') != SCHEMA or grant.get('authorizationId') != record['id']
            or grant.get('jobId') != JOB_PREFIX + _digest(record['id'])[:48]
            or record['idempotency_key'] != 'response-v3:' + str(grant.get('oldCallId'))
            or grant.get('approvalText') != APPROVAL_TEXT
            or grant.get('maximumNewVisionCalls') != MAXIMUM_PAGES
            or grant.get('wireContract') != WIRE_CONTRACT
            or grant.get('newRevision') != row['revision']
            or grant.get('familyId') != row['family_id'] or grant.get('childId') != row['child_id']
            or grant.get('submissionId') != row['id'] or row['source'] != 'parent_app'
            or type(grant.get('approvedAt')) is not int or type(grant.get('expiresAt')) is not int
            or grant['expiresAt'] != grant['approvedAt'] + TTL_MS
            or (scope is not None and grant.get('scopeSha256') != _digest(scope))):
        _error('homework_repair_authorization_invalid')
    approved_by = conn.execute('SELECT id,phone,family_id FROM users WHERE id=?', (grant.get('approvedByUserId'),)).fetchone()
    if not approved_by or approved_by['family_id'] != row['family_id']:
        _error('homework_repair_authorization_invalid')
    pages = service.repository.pages(conn, row['id'])
    if grant.get('inputs') != _inputs(service, pages):
        _error('homework_repair_scope_changed')
    _snapshots(conn, grant)
    return grant


def _result(grant, *, authorized, already=False, job_status='not_created'):
    return {
        'ok': True, 'authorized': authorized, 'alreadyAuthorized': already,
        'authorizationId': grant['authorizationId'], 'submissionId': grant['submissionId'],
        'revision': grant['newRevision'], 'jobId': grant['jobId'], 'jobStatus': job_status,
        'expiresAt': grant['expiresAt'], 'maximumNewVisionCalls': grant['maximumNewVisionCalls'],
        'pageCount': len(grant['inputs']), 'wireContract': WIRE_CONTRACT,
        'inputSha256': _digest(grant['inputs']),
    }


def authorize_recovery(service, conn, scope, *, execute=False, approval_text=None):
    """Read-only preflight by default; execution consumes this exact new approval."""
    service._enabled()
    _scope(scope)
    if execute and approval_text != APPROVAL_TEXT:
        _error('homework_repair_approval_required')
    user = conn.execute('SELECT id,phone,family_id FROM users WHERE phone=?', (scope['phone'],)).fetchone()
    if not user or user['family_id'] != scope['familyId']:
        _error('homework_repair_scope_invalid')
    service.profile._assert_capability(conn, {'user': dict(user), 'family': {'id': scope['familyId']}}, 'manage_tasks')
    row = service.repository.submission(conn, scope['familyId'], scope['submissionId'], child=scope['childId'], lock=execute)
    audit_id = 'hwresponse_' + _digest([SCHEMA, scope['submissionId'], scope['unknownCallId']])[:56]
    existing = conn.execute('SELECT * FROM homework_actions WHERE id=?', (audit_id,)).fetchone()
    if existing:
        grant = _validate_grant(service, conn, existing, row, scope=scope)
        job = conn.execute('SELECT * FROM homework_jobs WHERE id=?', (grant['jobId'],)).fetchone()
        if not job or job['submission_id'] != row['id'] or job['revision'] != grant['newRevision']:
            _error('homework_repair_authorization_invalid')
        # Repeating approval can inspect the immutable old grant, never renew it.
        return _result(grant, authorized=True, already=True, job_status=job['status'])
    if (row['revision'] != scope['expectedRevision'] or row['source'] != 'parent_app'
            or row['status'] != 'provider_unknown' or row['error_code'] != 'homework_provider_unknown'
            or service.repository.items(conn, row['id'])):
        _error()
    pages = service.repository.pages(conn, row['id'])
    inputs = _inputs(service, pages)
    old_job = conn.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=?',
                           (row['id'], row['revision'])).fetchone()
    old_call = conn.execute('SELECT * FROM homework_provider_calls WHERE id=?', (scope['unknownCallId'],)).fetchone()
    selected = next((value for value in inputs if old_call and value['pageId'] == old_call['page_id']), None)
    if (not old_job or old_job['status'] != 'failed' or old_job['stage'] != 'recognizing'
            or old_job['error_code'] != 'homework_provider_unknown' or not selected or not old_call
            or old_call['status'] != 'unknown' or old_call['error_code'] != 'homework_provider_unknown'
            or old_call['submission_id'] != row['id'] or old_call['child_id'] != row['child_id']
            or old_call['request_sha256'] != selected['baseRequestSha256']
            or old_call['provider'] != service.provider.provider_name or old_call['model'] != service.provider.model_name
            or old_call['prompt_version'] != service.policy['recognitionPrompt']['version']
            or old_call['result_json'] is not None or _parsed(old_call['receipt_json'], {}).get('receivedResponse')):
        _error()
    if conn.execute('SELECT id FROM homework_jobs WHERE submission_id=? AND status IN (?,?)',
                    (row['id'], 'queued', 'working')).fetchone():
        _error()
    count = conn.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=?', (row['id'],)).fetchone()['n']
    if count + len(pages) > service.policy['maxProviderCallsPerSubmission']:
        _error('homework_budget_exceeded')
    now = service.clock()
    grant = {
        'schema': SCHEMA, 'authorizationId': audit_id, 'scopeSha256': _digest(scope),
        'approvedByUserId': user['id'], 'familyId': row['family_id'], 'childId': row['child_id'],
        'submissionId': row['id'], 'oldRevision': row['revision'], 'newRevision': row['revision'] + 1,
        'oldCallId': old_call['id'], 'oldCallSha256': _digest(dict(old_call)),
        'oldJobId': old_job['id'], 'oldJobSha256': _digest(dict(old_job)),
        'jobId': JOB_PREFIX + _digest(audit_id)[:48], 'inputs': inputs,
        'wireContract': WIRE_CONTRACT, 'maximumNewVisionCalls': len(pages),
        'approvedAt': now, 'expiresAt': now + TTL_MS, 'approvalText': APPROVAL_TEXT,
    }
    if execute:
        service._processing_enabled()
        conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                     (audit_id, row['id'], ITEM_MARKER, 'response-v3:' + old_call['id'], _digest(grant), _canonical(grant), now))
        conn.execute('UPDATE homework_submissions SET revision=?,status=?,error_code=NULL,updated_at=? WHERE id=?',
                     (grant['newRevision'], 'queued', now, row['id']))
        conn.execute('INSERT INTO homework_jobs (id,submission_id,revision,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                     (grant['jobId'], row['id'], grant['newRevision'], 'queued', 'quality_check', now, now))
    return _result(grant, authorized=execute, job_status='queued' if execute else 'not_created')


def recognition_recovery_grant(service, conn, job, row, page, image):
    """Validate all page inputs before this page's bounded call reservation.

    Expiry is returned for the service to check immediately before *new* call
    reservation; already received/succeeded calls remain reusable after expiry.
    """
    if not job['id'].startswith(JOB_PREFIX):
        return None
    records = conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=?', (row['id'], ITEM_MARKER)).fetchall()
    for record in records:
        try:
            saved = _parsed(record['result_json'], {})
        except (ValueError, TypeError):
            continue
        if not isinstance(saved, dict) or saved.get('jobId') != job['id']:
            continue
        grant = _validate_grant(service, conn, record, row)
        if job['submission_id'] != row['id'] or job['revision'] != grant['newRevision']:
            _error('homework_repair_authorization_invalid')
        binding = next((value for value in grant['inputs'] if value['pageId'] == page['id']), None)
        if binding is None or binding['imageSha256'] != hashlib.sha256(image).hexdigest():
            _error('homework_repair_authorization_invalid')
        calls = conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=?', (row['id'],)).fetchall()
        approved_calls = [call for call in calls if _parsed(call['receipt_json'], {}).get('operatorRepairAuthorizationId') == record['id']]
        if (len(approved_calls) > grant['maximumNewVisionCalls']
                or len({call['page_id'] for call in approved_calls}) != len(approved_calls)
                or any(call['page_id'] not in {value['pageId'] for value in grant['inputs']} for call in approved_calls)):
            _error('homework_repair_authorization_invalid')
        for call in approved_calls:
            receipt = _parsed(call['receipt_json'], {})
            approved_input = next(value for value in grant['inputs'] if value['pageId'] == call['page_id'])
            request_sha = _digest({'baseRequestSha256': approved_input['baseRequestSha256'],
                                   'operatorRepair': record['id'], 'authorizationSha256': record['request_sha256'],
                                   'wire': approved_input['wire']})
            if (call['request_sha256'] != request_sha or call['child_id'] != row['child_id']
                    or receipt.get('authorizationSha256') != record['request_sha256']
                    or receipt.get('wireContract') != WIRE_CONTRACT
                    or receipt.get('maximumNewVisionCalls') != grant['maximumNewVisionCalls']):
                _error('homework_repair_authorization_invalid')
        return {
            'id': record['id'], 'sha256': record['request_sha256'], 'expiresAt': grant['expiresAt'],
            'wire': binding['wire'], 'maximumNewVisionCalls': grant['maximumNewVisionCalls'],
            'wireContract': WIRE_CONTRACT,
        }
    _error('homework_repair_authorization_invalid')
