"""One immutable Grade 6 draft's completion grant; never an Agent/retry grant.

The operator plans against live read-only state, then applies the exact reviewed
plan under the normal budget lock. The parent authorization and reservations
are never updated. An explicit audio-tail renewal extends only this completion
grant's expiry, with an append-only audit. Native validates budget/context before
entering its private saved-stage completion path.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

from content.learning_budget_policy import UNITS, canonical, digest
from integrations.openmaic_formal_quality import quality_sha, quality_snapshot
from services.learning_transport_terminal_reconciliation import (
    EVENT as TRANSPORT_EVENT, validated_terminal_ids,
)

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / 'backend/data/learning-provider-replies'
EVENT = 'saved_stage_tail_authorized'
PLAN_SCHEMA = 'mira.learning.saved-stage-tail-plan.v1'
GRANT_SCHEMA = 'mira.learning.saved-stage-tail-grant.v1'
AUTH_SCHEMA = 'mira.learning.saved-stage-tail-authorization.v1'
RENEWAL_EVENT = 'saved_stage_tail_window_renewed'
RENEWAL_SCHEMA = 'mira.learning.saved-stage-tail-renewal-plan.v1'
RENEWAL_SCOPE = {
    'mode': 'complete-reviewed-audio-tail', 'newAgentSessions': 0, 'newSearches': 0,
    'newQualityReviews': 0, 'preserveCompletedAudio': True,
    'preserveUnknownReservations': True, 'sameFrozenCourseOnly': True,
}
TRANSPORT_PLAN_SHA = 'ea65c1f5acacc86c22f65997d751ea4e80c005383a426140e8589abf2646cfbf'
SCOPE_SHA = '7ce76c22a224ffe9a8318c3d1d5d8d4dd9d639e2469dd094120ed5389f0a6f3c'
PARENT_EXPIRES = 1789135918576
PRICE_CALLS = {'deepseek-flash-peak': 1, 'deepseek-vision-peak': 1,
               'qwen-tts-beijing': 36, 'qwen-asr-beijing': 36}
PRICE_MODELS = {'deepseek-flash-peak': ('deepseek', 'deepseek-v4-flash'),
                'deepseek-vision-peak': ('deepseek', 'deepseek-v4-flash-vision-exp'),
                'qwen-tts-beijing': ('qwen-tts', 'qwen3-tts-flash'),
                'qwen-asr-beijing': ('qwen-asr', 'qwen3-asr-flash')}
IDENTITY = {
    'parentAuthorizationId': '719d46ef248b2a56b5402db3ed2d36cc8e6d614ac1ce22e0635271b57d3a92d4',
    'buildItemId': 'catalog_build_item_ea873d206248a13de584960e',
    'runtimeId': 'omfc_23GS7TPaFEM03Q4eUBDo7UXQyRqVhfUeyynpmTtr56o',
    'jobId': 'omformal_3b6ae9c7b6e8f13472a10d04',
    'runtimeRequestId': 'mira-formal-runtime-catalog_build_item_ea873d206248a13de584960e-attempt-1',
    'sourceJobSha256': 'ca347d0b717d4179b23ed97a1ee941ab6bf651a8a0a35f2daae128dde7f1c284',
    'sourceSnapshotSha256': 'af28bf80539851ab7ae41982fc23834cde976ba758ca204620423ac4dbb4f8a2',
    'repairSnapshotSha256': 'efce9328097b203ec4669e43d03fd18402418f3ca63df1b834760458aac6ee13',
    'formalInputSha256': '6b200140d0be9222d1ee9fe178617e8c45bad4bd27a2322a12223ad2fef0debc',
    'sessionId': 'miraformal_295056404ed5ebf561df5eddf1fcbc57c63c984ea3282a0400c7dc1123409e73',
    'ownerId': 'mira-formal-professional:295056404ed5ebf561df5eddf1fcbc57c63c984ea3282a0400c7dc1123409e73',
    'stageId': 'stage-WmNYqudzYa', 'speechActionCount': 36,
    'sceneIds': ['scene-p1', 'scene-p2', 'scene-p4', 'scene-p3', 'scene-p5', 'scene-p6', 'scene-p7', 'scene-p8'],
    'lockedQuestionIds': ['catalog_gen_ea873d206248a13de584960e263a14d02c8f8c5c12629634_q' + str(n)
                          for n in range(2, 6)],
}


def _require(ok, message='saved-stage completion authorization evidence changed'):
    if not ok:
        raise ValueError(message)


def authorization_id():
    # No timestamp/window in the identity: another plan cannot create a second
    # spending package for this same draft, even after this grant expires.
    return digest({'schema': AUTH_SCHEMA, 'identity': IDENTITY})


def _binding(identity):
    return {'schemaVersion': 'mira.learning.paid-budget-binding.v1',
            'authorizationId': identity, 'required': True}


def _validate_policy(policy):
    _require(policy.raw['enabled'] is True and not policy.aggregate_limits_enabled
             and policy.raw['authorizationTemplates']['production'] is None
             and policy.raw.get('authorizationWindow') is None
             and policy.raw.get('productionInflightOverride') is None
             and policy.raw['limits']['global']['maxInflightCalls'] == 4,
             'completion requires normal classroom policy with automatic production disabled')


def _prices_and_limits(parent, policy):
    frozen = json.loads(parent['price_keys_json'])
    _require(isinstance(frozen, dict) and set(PRICE_CALLS) <= set(frozen['prices']))
    prices = {key: deepcopy(frozen['prices'][key]) for key in sorted(PRICE_CALLS)}
    for key, price in prices.items():
        _require((price['provider'], price['model']) == PRICE_MODELS[key])
        # The original paid vision price is already frozen in the parent. The
        # classroom policy need not add a generation/vision template to use it.
        if key in policy.raw['prices']:
            _require(policy.price(key) == price, 'parent and current registered price differ')
        policy.measure(price['perCallMax'], price, reservation=True)
    # These are the parent's historical observation fields, not newly imposed
    # cumulative quotas. Scope is enforced by proof, operation and namespace.
    return {'keys': sorted(prices), 'prices': prices}, json.loads(parent['limits_json'])


def _file(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}, json.loads(raw)


def source_evidence(*, source_job_path, source_snapshot_path, prepared_snapshot_path):
    job_file, job = _file(source_job_path)
    source_file, source = _file(source_snapshot_path)
    prepared_file, prepared = _file(prepared_snapshot_path)
    live_job = ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/classroom-jobs' / (IDENTITY['jobId'] + '.json')
    _require(hashlib.sha256(live_job.read_bytes()).hexdigest() == IDENTITY['sourceJobSha256'],
             'the current Native failed job must still be the original immutable source')
    _require(job_file['sha256'] == IDENTITY['sourceJobSha256']
             and job['id'] == IDENTITY['jobId'] and job['status'] == 'failed'
             and job.get('completedAt') and job.get('error')
             and job['runtimeRequestId'] == IDENTITY['runtimeRequestId']
             and job['formalInputSha256'] == IDENTITY['formalInputSha256']
             and quality_sha(job['formalInput']) == IDENTITY['formalInputSha256']
             and job['formalInput']['paidBudget'] == _binding(IDENTITY['parentAuthorizationId']))
    _require(quality_sha(quality_snapshot(source)) == IDENTITY['sourceSnapshotSha256']
             and quality_sha(prepared) == IDENTITY['repairSnapshotSha256'])
    _require(prepared['stage']['id'] == source['stage']['id'] == IDENTITY['stageId'])
    scenes = prepared['scenes']
    _require([scene['id'] for scene in scenes] == IDENTITY['sceneIds'])
    questions = [q['id'] for scene in scenes if scene['type'] == 'quiz' for q in scene['content']['questions']]
    speeches = [{'sceneId': scene['id'], 'actionId': action['id'],
                 'textSha256': hashlib.sha256(action['text'].encode()).hexdigest()}
                for scene in scenes for action in scene['actions'] if action.get('type') == 'speech']
    _require(questions == IDENTITY['lockedQuestionIds'] and len(speeches) == 36
             and len({speech['actionId'] for speech in speeches}) == 36)
    return {'sourceJob': job_file, 'sourceSnapshot': source_file, 'preparedSnapshot': prepared_file,
            'speechManifest': speeches, 'speechManifestSha256': digest(speeches)}


def _verify_files(files):
    actual = source_evidence(source_job_path=files['sourceJob']['path'],
        source_snapshot_path=files['sourceSnapshot']['path'],
        prepared_snapshot_path=files['preparedSnapshot']['path'])
    _require(actual == files)


def _snapshot(conn, budget):
    _validate_policy(budget.policy)
    budget._enabled(conn)
    parent = budget.repository.authorization(conn, IDENTITY['parentAuthorizationId'])
    _require(parent is not None and parent['revoked_at'] is None
             and parent['expires_at'] == PARENT_EXPIRES)
    scope = json.loads(parent['scope_json'])
    _require(digest(scope) == SCOPE_SHA)
    current, _ = budget._catalog_production_scope(conn, IDENTITY['buildItemId'])
    _require(current == scope)
    runtime = conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?',
                           (IDENTITY['runtimeId'],)).fetchone()
    item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=?',
                        (IDENTITY['buildItemId'],)).fetchone()
    _require(runtime is not None and item is not None
             and runtime['candidate_build_item_id'] == IDENTITY['buildItemId']
             and runtime['upstream_job_id'] == IDENTITY['jobId']
             and runtime['request_id'] == IDENTITY['runtimeRequestId']
             and runtime['retired_at'] is None and runtime['status'] in {'failed', 'generating'}
             and item['content_phase'] == 'course_ready' and item['content_gate_status'] == 'passed')
    manifest = json.loads(runtime['feature_manifest_json'])
    _require(manifest['paidBudget'] == _binding(IDENTITY['parentAuthorizationId']))
    pending = [dict(row) for row in conn.execute(
        "SELECT * FROM learning_budget_reservations WHERE state IN ('reserved','dispatched','unknown') ORDER BY id").fetchall()]
    _require(len(pending) == 4 and all(row['state'] == 'unknown' for row in pending),
             'the four original unknowns must remain; no active transport may race grant issuance')
    events = [dict(row) for row in conn.execute(
        'SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id', (TRANSPORT_EVENT,)).fetchall()]
    auth_ids = sorted({row['authorization_id'] for row in pending})
    authorities = [dict(budget.repository.authorization(conn, identity)) for identity in auth_ids]
    _require(validated_terminal_ids(pending, events, authorities) == {row['id'] for row in pending})
    _require(events and {json.loads(row['evidence_json'])['planSha256'] for row in events} == {TRANSPORT_PLAN_SHA})
    ledger = [dict(row) for row in conn.execute(
        'SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id',
        (IDENTITY['parentAuthorizationId'],)).fetchall()]
    anchors = [row for row in ledger if row['state'] == 'settled']
    _require(anchors, 'a real settled parent reservation must anchor the grant event')
    return {'parentAuthorization': dict(parent), 'parentLedgerSha256': digest(ledger),
            'parentLedgerRows': len(ledger), 'runtime': dict(runtime), 'item': dict(item),
            'terminalReservations': pending, 'terminalAuthorities': authorities, 'terminalEvents': events,
            'anchorReservationId': anchors[0]['id']}


def _sidecar(plan):
    return {'schemaVersion': GRANT_SCHEMA, 'planSha256': digest(plan),
            'authorizationId': authorization_id(), 'paidBudget': _binding(authorization_id()),
            'identity': deepcopy(IDENTITY),
            'parentAuthorizationSha256': digest(plan['snapshot']['parentAuthorization']),
            'scopeSha256': SCOPE_SHA, 'scope': json.loads(plan['snapshot']['parentAuthorization']['scope_json']),
            'startsAt': plan['startsAt'], 'expiresAt': plan['expiresAt'],
            'priceKeys': sorted(PRICE_CALLS), 'limits': plan['limits'],
            'transportTerminalPlanSha256': TRANSPORT_PLAN_SHA}


def plan_tail_authorization(*, budget, source_job_path, source_snapshot_path, prepared_snapshot_path,
                            starts_at, expires_at):
    now = budget.clock()
    _require(type(starts_at) is int and type(expires_at) is int
             and PARENT_EXPIRES <= starts_at <= now < expires_at <= starts_at + 2 * 3600000,
             'completion needs one explicit bounded technical window of at most two hours')
    files = source_evidence(source_job_path=source_job_path, source_snapshot_path=source_snapshot_path,
                            prepared_snapshot_path=prepared_snapshot_path)
    # Do not acquire repository.locked() for a plan: that increments DB revision.
    with budget.repository.database.transaction() as conn:
        snapshot = _snapshot(conn, budget)
        _require(budget.repository.authorization(conn, authorization_id()) is None,
                 'this draft already has its one completion grant')
        _require(not conn.execute('SELECT id FROM learning_budget_events WHERE event_type=?', (EVENT,)).fetchall())
    prices, maximum = _prices_and_limits(snapshot['parentAuthorization'], budget.policy)
    plan = {'schemaVersion': PLAN_SCHEMA, 'identity': deepcopy(IDENTITY), 'files': files,
            'snapshot': snapshot, 'policySha256': budget.policy.sha256,
            'startsAt': starts_at, 'expiresAt': expires_at, 'priceScope': prices,
            'expectedOperationCalls': dict(PRICE_CALLS), 'limits': maximum,
            'allowedMode': 'complete', 'newAgentSessions': 0, 'newSearches': 0,
            'oldAuthorizationMutations': 0, 'oldReservationMutations': 0}
    return {'plan': plan, 'planSha256': digest(plan), 'sidecar': _sidecar(plan), 'applied': False}


def _validate_plan(plan, policy):
    _require(set(plan) == {'schemaVersion', 'identity', 'files', 'snapshot', 'policySha256',
        'startsAt', 'expiresAt', 'priceScope', 'expectedOperationCalls', 'limits', 'allowedMode',
        'newAgentSessions', 'newSearches', 'oldAuthorizationMutations', 'oldReservationMutations'})
    _require(plan['schemaVersion'] == PLAN_SCHEMA and plan['identity'] == IDENTITY
             and plan['allowedMode'] == 'complete' and plan['expectedOperationCalls'] == PRICE_CALLS
             and all(type(plan[key]) is int and plan[key] == 0 for key in
                     ('newAgentSessions', 'newSearches', 'oldAuthorizationMutations', 'oldReservationMutations')))
    _require(type(plan['startsAt']) is int and type(plan['expiresAt']) is int
             and PARENT_EXPIRES <= plan['startsAt'] < plan['expiresAt'] <= plan['startsAt'] + 2 * 3600000)
    prices, maximum = _prices_and_limits(plan['snapshot']['parentAuthorization'], policy)
    _require(plan['priceScope'] == prices and plan['limits'] == maximum)


def _archive(path, value):
    raw = canonical(value).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        _require(path.read_bytes() == raw, 'content-addressed audit file differs')
        return
    with os.fdopen(fd, 'wb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def apply_tail_authorization(*, budget, plan, expected_plan_sha, archives=ARCHIVES):
    _require(digest(plan) == expected_plan_sha, 'apply requires the exact reviewed plan SHA')
    _validate_plan(plan, budget.policy)
    _verify_files(plan['files'])
    sidecar = _sidecar(plan)
    with budget.repository.locked() as conn:
        existing = budget.repository.authorization(conn, authorization_id())
        if existing is not None:
            _require(verified_tail_grant(conn, existing, budget.policy) == sidecar,
                     'this draft already has a different completion grant')
            return {'applied': False, 'reused': True, 'planSha256': expected_plan_sha, 'sidecar': sidecar}
        now = budget.clock()
        _require(plan['startsAt'] <= now < plan['expiresAt'])
        _require(budget.policy.sha256 == plan['policySha256'] and _snapshot(conn, budget) == plan['snapshot'])
        _require(not conn.execute('SELECT id FROM learning_budget_events WHERE event_type=?', (EVENT,)).fetchall())
        # Archive complete pre-state before either INSERT. A failed transaction
        # may leave only this harmless immutable file, never an unaudited grant.
        _archive(Path(archives) / (expected_plan_sha + '.saved-stage-tail-plan.json'), plan)
        prices = {**plan['priceScope'], 'completionTailGrantSha256': digest(sidecar)}
        expected_authority = {'id': authorization_id(), 'scope_json': canonical(sidecar['scope']),
            'limits_json': canonical(plan['limits']), 'price_keys_json': canonical(prices),
            'policy_sha256': budget.policy.sha256, 'expires_at': plan['expiresAt'],
            'created_at': now, 'revoked_at': None}
        envelope = {'schemaVersion': 'mira.learning.saved-stage-tail-authority-evidence.v1',
                    'plan': plan, 'planSha256': expected_plan_sha, 'sidecar': sidecar,
                    'authority': expected_authority}
        budget.repository.event(conn, plan['snapshot']['anchorReservationId'], EVENT, envelope, now)
        budget.repository.insert_authorization(conn, authorization_id(), sidecar['scope'], plan['limits'],
            prices, budget.policy.sha256, plan['expiresAt'], now)
        _require(verified_tail_grant(conn, budget.repository.authorization(conn, authorization_id()), budget.policy) == sidecar)
    return {'applied': True, 'reused': False, 'planSha256': expected_plan_sha, 'sidecar': sidecar}


def verified_tail_grant(conn, authority, policy):
    """DB-backed proof, also required before every reserve/dispatch of this ID."""
    frozen = json.loads(authority['price_keys_json'])
    marker = frozen.get('completionTailGrantSha256') if isinstance(frozen, dict) else None
    if authority['id'] != authorization_id() and marker is None:
        return None
    _validate_policy(policy)
    _require(authority['id'] == authorization_id() and isinstance(marker, str))
    rows = conn.execute('SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id', (EVENT,)).fetchall()
    _require(len(rows) == 1, 'completion grant requires exactly one committed audit event')
    event = rows[0]
    envelope = json.loads(event['evidence_json'])
    _require(set(envelope) == {'schemaVersion', 'plan', 'planSha256', 'sidecar', 'authority'}
             and envelope['schemaVersion'] == 'mira.learning.saved-stage-tail-authority-evidence.v1')
    plan = envelope['plan']
    _validate_plan(plan, policy)
    sidecar = _sidecar(plan)
    _require(envelope['planSha256'] == digest(plan) and envelope['sidecar'] == sidecar
             and digest(sidecar) == marker
             and event['reservation_id'] == plan['snapshot']['anchorReservationId'])
    parent = conn.execute('SELECT * FROM learning_budget_authorizations WHERE id=?',
                          (IDENTITY['parentAuthorizationId'],)).fetchone()
    _require(parent is not None and dict(parent) == plan['snapshot']['parentAuthorization'],
             'original expired authorization must stay byte-for-byte unchanged')
    _require(envelope['authority'] == {'id': authorization_id(), 'scope_json': canonical(sidecar['scope']),
        'limits_json': canonical(plan['limits']),
        'price_keys_json': canonical({**plan['priceScope'], 'completionTailGrantSha256': marker}),
        'policy_sha256': plan['policySha256'], 'expires_at': plan['expiresAt'],
        'created_at': event['created_at'], 'revoked_at': None}
        and plan['startsAt'] <= event['created_at'] < plan['expiresAt'])
    renewals = conn.execute('SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id',
                            (RENEWAL_EVENT,)).fetchall()
    _require(len(renewals) <= 1, 'completion window can have only one explicit renewal')
    if not renewals:
        _require(dict(authority) == envelope['authority'])
        return sidecar
    renewal_event = renewals[0]
    renewal = json.loads(renewal_event['evidence_json'])
    _require(set(renewal) == {'schemaVersion', 'plan', 'planSha256', 'sidecar'})
    renewal_plan = renewal['plan']
    _validate_renewal_plan(renewal_plan, envelope, policy)
    renewed = {**sidecar, 'expiresAt': renewal_plan['expiresAt']}
    _require(renewal['schemaVersion'] == 'mira.learning.saved-stage-tail-renewal-evidence.v1'
             and renewal['planSha256'] == digest(renewal_plan) and renewal['sidecar'] == renewed
             and renewal_event['reservation_id'] == event['reservation_id']
             and renewal_plan['plannedAt'] <= renewal_event['created_at'] < renewal_plan['expiresAt']
             and dict(authority) == {**envelope['authority'], 'expires_at': renewal_plan['expiresAt']})
    # Newly reserved audio work is not part of this old terminal snapshot.
    for old in renewal_plan['snapshot']['tailLedger']:
        current = conn.execute('SELECT * FROM learning_budget_reservations WHERE id=?', (old['id'],)).fetchone()
        _require(current is not None and dict(current) == old,
                 'renewal must preserve every original terminal reservation')
    return renewed


def _original_envelope(conn):
    rows = conn.execute('SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id', (EVENT,)).fetchall()
    _require(len(rows) == 1, 'completion grant requires exactly one original audit')
    return json.loads(rows[0]['evidence_json'])


def _renewal_snapshot(conn, budget):
    _validate_policy(budget.policy)
    budget._enabled(conn)
    authority = budget.repository.authorization(conn, authorization_id())
    _require(authority is not None and authority['revoked_at'] is None)
    original = _original_envelope(conn)
    sidecar = verified_tail_grant(conn, authority, budget.policy)
    _require(sidecar == original['sidecar'], 'completion window was already renewed')
    current, _ = budget._catalog_production_scope(conn, IDENTITY['buildItemId'])
    _require(current == sidecar['scope'])
    runtime = conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?',
                           (IDENTITY['runtimeId'],)).fetchone()
    item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=?',
                        (IDENTITY['buildItemId'],)).fetchone()
    _require(runtime is not None and item is not None
             and runtime['candidate_build_item_id'] == IDENTITY['buildItemId']
             and runtime['upstream_job_id'] == IDENTITY['jobId']
             and runtime['request_id'] == IDENTITY['runtimeRequestId']
             and runtime['retired_at'] is None and runtime['status'] in {'failed', 'generating'}
             and item['content_phase'] == 'course_ready' and item['content_gate_status'] == 'passed')
    ledger = [dict(row) for row in conn.execute(
        'SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id',
        (authorization_id(),)).fetchall()]
    _require(ledger and all(row['state'] in {'settled', 'unknown', 'released'} for row in ledger),
             'stop active completion dispatches before renewing its window')
    return {'authority': dict(authority), 'tailLedger': ledger,
            'runtime': dict(runtime), 'item': dict(item)}


def _validate_renewal_plan(plan, original, policy):
    _require(set(plan) == {'schemaVersion', 'authorizationId', 'identity', 'originalEnvelopeSha256',
        'originalGrantSha256', 'originalAuthoritySha256', 'policySha256', 'previousExpiresAt',
        'expiresAt', 'plannedAt', 'approvalReference', 'approvalText', 'scope', 'snapshot'})
    _require(plan['schemaVersion'] == RENEWAL_SCHEMA and plan['authorizationId'] == authorization_id()
             and plan['identity'] == IDENTITY and plan['scope'] == RENEWAL_SCOPE
             and plan['originalEnvelopeSha256'] == digest(original)
             and plan['originalGrantSha256'] == digest(original['sidecar'])
             and plan['originalAuthoritySha256'] == digest(original['authority'])
             and plan['policySha256'] == policy.sha256 == original['authority']['policy_sha256']
             and plan['snapshot']['authority'] == original['authority']
             and plan['previousExpiresAt'] == original['sidecar']['expiresAt'])
    _require(all(type(plan[key]) is int for key in ('previousExpiresAt', 'expiresAt', 'plannedAt'))
             and plan['plannedAt'] >= original['authority']['created_at']
             and max(plan['previousExpiresAt'], plan['plannedAt']) < plan['expiresAt']
             <= plan['plannedAt'] + 2 * 3600000,
             'renewal needs one explicit window of at most two hours from the reviewed plan')
    _require(isinstance(plan['approvalReference'], str) and 1 <= len(plan['approvalReference']) <= 256
             and isinstance(plan['approvalText'], str) and 1 <= len(plan['approvalText']) <= 4000,
             'renewal requires the current explicit user approval and its source')
    ledger = plan['snapshot']['tailLedger']
    _require(isinstance(ledger, list) and ledger
             and len({row['id'] for row in ledger}) == len(ledger)
             and all(row['authorization_id'] == authorization_id()
                     and row['state'] in {'settled', 'unknown', 'released'} for row in ledger))


def plan_tail_renewal(*, budget, expires_at, approval_reference, approval_text):
    """Read-only operator plan; no new grant, limit, price, or Provider request."""
    with budget.repository.database.transaction() as conn:
        snapshot = _renewal_snapshot(conn, budget)
        original = _original_envelope(conn)
    _verify_files(original['plan']['files'])
    plan = {'schemaVersion': RENEWAL_SCHEMA, 'authorizationId': authorization_id(),
        'identity': deepcopy(IDENTITY), 'originalEnvelopeSha256': digest(original),
        'originalGrantSha256': digest(original['sidecar']),
        'originalAuthoritySha256': digest(original['authority']),
        'policySha256': budget.policy.sha256, 'previousExpiresAt': original['sidecar']['expiresAt'],
        'expiresAt': expires_at, 'plannedAt': budget.clock(), 'approvalReference': approval_reference,
        'approvalText': approval_text, 'scope': deepcopy(RENEWAL_SCOPE), 'snapshot': snapshot}
    _validate_renewal_plan(plan, original, budget.policy)
    return {'plan': plan, 'planSha256': digest(plan), 'applied': False,
            'sidecar': {**original['sidecar'], 'expiresAt': expires_at}}


def apply_tail_renewal(*, budget, plan, expected_plan_sha, archives=ARCHIVES):
    """Update only the existing completion expiry; preserve its frozen marker."""
    _require(digest(plan) == expected_plan_sha, 'renewal requires the exact reviewed plan SHA')
    with budget.repository.locked() as conn:
        original = _original_envelope(conn)
        _validate_renewal_plan(plan, original, budget.policy)
        existing_events = conn.execute('SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id',
                                       (RENEWAL_EVENT,)).fetchall()
        authority = budget.repository.authorization(conn, authorization_id())
        if existing_events:
            _require(len(existing_events) == 1 and
                     json.loads(existing_events[0]['evidence_json'])['planSha256'] == expected_plan_sha,
                     'this completion already has a different renewal')
            sidecar = verified_tail_grant(conn, authority, budget.policy)
            return {'applied': False, 'reused': True, 'planSha256': expected_plan_sha, 'sidecar': sidecar}
        now = budget.clock()
        _require(plan['plannedAt'] <= now < plan['expiresAt'])
        _require(_renewal_snapshot(conn, budget) == plan['snapshot'], 'renewal pre-state changed; inspect again')
        _verify_files(original['plan']['files'])
        _archive(Path(archives) / (expected_plan_sha + '.saved-stage-tail-renewal.json'), plan)
        sidecar = {**original['sidecar'], 'expiresAt': plan['expiresAt']}
        envelope = {'schemaVersion': 'mira.learning.saved-stage-tail-renewal-evidence.v1',
                    'plan': plan, 'planSha256': expected_plan_sha, 'sidecar': sidecar}
        budget.repository.event(conn, original['plan']['snapshot']['anchorReservationId'], RENEWAL_EVENT, envelope, now)
        cursor = conn.execute('UPDATE learning_budget_authorizations SET expires_at=? WHERE id=? AND expires_at=?',
                              (plan['expiresAt'], authorization_id(), plan['previousExpiresAt']))
        _require(cursor.rowcount == 1)
        _require(verified_tail_grant(conn, budget.repository.authorization(conn, authorization_id()), budget.policy) == sidecar)
    return {'applied': True, 'reused': False, 'planSha256': expected_plan_sha, 'sidecar': sidecar}


def validate_tail_dispatch(authority, *, dispatch_id, request_sha256, price_key):
    """Admit the normal completion lane, never Agent/search/repair namespaces.

    The body contains an opaque request hash; content and the exact 36 narration
    identities are checked by Native's source-bound completion context. This
    function does not pretend to reconstruct those bodies or impose a quota.
    """
    if authority['id'] != authorization_id():
        return
    expected = 'runtime:' + digest([authorization_id(), IDENTITY['sessionId'] + ':completion', request_sha256])
    _require(dispatch_id == expected and price_key in PRICE_CALLS,
             'completion grant requires its exact original completion dispatch namespace')
