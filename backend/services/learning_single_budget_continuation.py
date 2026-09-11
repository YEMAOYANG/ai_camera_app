"""Audited time-only continuation of the original single-course authorization."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re

from content.learning_budget_policy import LearningBudgetPolicy, canonical, digest

EVENT = 'single_course_auth_continued'
SCHEMA = 'mira.single-course.authorization-continuation.v1'
ARCHIVES = Path(__file__).resolve().parents[2] / 'backend/data/learning-provider-replies'


def _events(conn):
    result = []
    for row in conn.execute('SELECT evidence_json FROM learning_budget_events WHERE event_type=? ORDER BY id', (EVENT,)).fetchall():
        envelope = json.loads(row['evidence_json'])
        audit = envelope.get('audit')
        if not isinstance(audit, dict) or digest(audit) != envelope.get('continuationSha256'):
            raise ValueError('authorization continuation audit is invalid')
        result.append(audit)
    return result


def _validate_change(old, new):
    if (set(old) != set(new) or {k: v for k, v in old.items() if k != 'expires_at'}
            != {k: v for k, v in new.items() if k != 'expires_at'}
            or type(new['expires_at']) is not int or new['expires_at'] <= old['expires_at']):
        raise ValueError('continuation may change only authorization expiry')


def validate_continued_authority(conn, authority, *, original=None):
    """Verify every expiry-only change; the search-price audit remains immutable."""
    previous = None
    current = original
    found = False
    for audit in _events(conn):
        changes = audit.get('authorizationChanges') or []
        change = next((c for c in changes if c['old']['id'] == authority['id']), None)
        if change is None:
            continue
        if (audit.get('schemaVersion') != SCHEMA
                or audit.get('previousContinuationSha256') != previous and found
                or not found and audit.get('productionAuthorizationId') == authority['id']
                   and audit.get('previousContinuationSha256') is not None):
            raise ValueError('authorization continuation chain is broken')
        _validate_change(change['old'], change['new'])
        if current is not None and current != change['old']:
            raise ValueError('authorization continuation source changed')
        current = change['new']
        previous = digest(audit)
        found = True
    if current is not None and dict(authority) != current:
        raise ValueError('authorization does not match its immutable continuation audit')
    return found


def _snapshot(conn, budget, identity, scopes):
    from services.learning_single_search_transition import JOB
    if budget.repository.control(conn)['halted']:
        raise ValueError('budget accounting is halted; diagnose unresolved usage first')
    actual, _ = budget._catalog_production_scope(conn, identity['buildItemId'])
    if actual != identity['scope']:
        raise ValueError('current enabled catalog scope differs from the frozen sample')
    item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=?', (identity['buildItemId'],)).fetchone()
    runtimes = [dict(r) for r in conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=? ORDER BY id', (identity['buildItemId'],)).fetchall()]
    if (not item or item['content_phase'] != 'course_ready' or item['content_gate_status'] != 'passed'
            or len(runtimes) != 1 or runtimes[0]['upstream_job_id'] != JOB):
        raise ValueError('only the accepted original single classroom may continue')
    production_id = digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': identity['scope']})
    authorities = []
    for scope in scopes:
        if scope['purpose'] == 'production':
            key = production_id
        else:
            from services.learning_paid_authority import scope_digest
            session = conn.execute('SELECT * FROM learning_sessions WHERE id=?', (scope['sessionId'],)).fetchone()
            if (not session or session['child_id'] != scope['userId'] or session['status'] != 'in_progress'
                    or session.get('completed_at') is not None or scope['productionJobId'] is not None
                    or scope['courseId'] != runtimes[0]['course_id'] or scope['courseVersion'] != runtimes[0]['course_version']
                    or session['course_id'] != scope['courseId'] or session['course_version'] != scope['courseVersion']
                    or scope['approvalReference'] != identity['targetFingerprint']):
                raise ValueError('teaching continuation must match this sample and its active student session')
            key = scope_digest(scope)
        row = budget.repository.authorization(conn, key)
        if row is None or row['revoked_at'] is not None or json.loads(row['scope_json']) != scope:
            raise ValueError('each scope must retain its original unrevoked authorization')
        validate_continued_authority(conn, row)
        authorities.append(dict(row))
    marks = ','.join('?' for _ in authorities)
    ledger = [dict(r) for r in conn.execute(f'SELECT * FROM learning_budget_reservations WHERE authorization_id IN ({marks}) ORDER BY id', tuple(r['id'] for r in authorities)).fetchall()]
    if not ledger or any(r['state'] not in {'settled', 'released'} for r in ledger):
        raise ValueError('original calls must be settled/released before continuation; no pending or unknown calls')
    own = [r for r in ledger if r['authorization_id'] == production_id]
    if not own:
        raise ValueError('original production history is required')
    return authorities, {'ledgerSha256': digest(ledger), 'ledgerRows': len(ledger),
        'settledMoneyMicros': sum(json.loads(r['actual_units_json'])['money_micros'] for r in ledger if r['state'] == 'settled'),
        'catalogSha256': digest({'item': dict(item), 'runtimes': runtimes})}, own[-1]['id']


def _view(audit, applied=False):
    return {'continuationSha256': digest(audit), 'applied': applied,
        'authorizationIds': [c['new']['id'] for c in audit['authorizationChanges']],
        'oldExpiresAt': audit['oldPolicy']['authorizationWindow']['expiresAt'],
        'expiresAt': audit['newPolicy']['authorizationWindow']['expiresAt'],
        'aggregateLimitsEnabled': False, 'newAuthorizationCreated': False,
        'scopeChanged': False, 'priorChargesPreserved': True, 'providerCalls': 0,
        'snapshot': audit['snapshot']}


def continue_single_budget(*, database, policy_path, identity, now, expires_at,
                           expected_sha=None, apply=False, write_policy=None, archives=ARCHIVES):
    from services.learning_budget_service import LearningBudgetService
    from services.learning_single_search_transition import transition_active_prices
    if type(expires_at) is not int or (expected_sha is not None and not re.fullmatch(r'[a-f0-9]{64}', expected_sha)):
        raise ValueError('continuation requires fixed expiry and an exact review SHA')
    if apply and (expected_sha is None or write_policy is None):
        raise ValueError('apply requires the reviewed SHA and atomic policy writer')
    path = Path(policy_path).resolve()
    policy = LearningBudgetPolicy.load(path)
    window = policy.raw.get('authorizationWindow') or {}
    scopes = window.get('scopes') or []
    if (policy.aggregate_limits_enabled or not scopes or scopes[0] != identity['scope'] or len(scopes) > 2
            or identity['scope']['gradeCode'] != 'primary_6' or identity['scope']['subject'] != 'math'
            or identity['slot']['skillId'] != 'fraction_ratio_percentage' or identity['slot']['variantOrdinal'] != 1
            or any(s['purpose'] != 'required_teaching' or s['gradeCode'] != 'primary_6' or s['subject'] != 'math'
                   or not s['userId'] or not s['sessionId'] for s in scopes[1:])):
        raise ValueError('continuation is only for the original metering-only Grade 6 sample and its exact teaching session')
    today = datetime.fromtimestamp(now / 1000, policy.timezone).date()
    if (str(policy.timezone) != 'Asia/Shanghai' or expires_at <= now
            or datetime.fromtimestamp(expires_at / 1000, policy.timezone).date() != today
            or datetime.fromtimestamp(window['startsAt'] / 1000, policy.timezone).date() != today):
        raise ValueError('continuation must finish within this same Shanghai day')
    budget = LearningBudgetService(database, policy=policy)
    key = digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': identity['scope']})
    manager = budget.repository.locked() if apply else database.transaction()
    with manager as conn:
        previous = [a for a in _events(conn) if a['productionAuthorizationId'] == key]
        replay = next((a for a in previous if digest(a) == expected_sha), None) if apply else None
        authorities, snapshot, anchor = _snapshot(conn, budget, identity, scopes)
        # This also verifies the frozen Brave/Baidu transition through earlier expiry continuations.
        transition_active_prices(conn, authorities[0])
        if replay:
            audit = replay
            if (previous[-1] != audit or authorities != [c['new'] for c in audit['authorizationChanges']]
                    or snapshot != audit['snapshot'] or expires_at != audit['newPolicy']['authorizationWindow']['expiresAt']
                    or policy.sha256 not in {digest(audit['oldPolicy']), digest(audit['newPolicy'])}):
                raise ValueError('committed continuation no longer matches the original reviewed evidence')
        else:
            if policy.raw['enabled'] or expires_at <= window['expiresAt'] or any(expires_at <= a['expires_at'] for a in authorities):
                raise ValueError('pause the original policy and extend its existing expiry only')
            raw = deepcopy(policy.raw)
            raw['authorizationWindow']['expiresAt'] = expires_at
            raw['enabled'] = True
            new_policy = LearningBudgetPolicy(raw)
            audit = {'schemaVersion': SCHEMA, 'approvalReference': 'user_complete_same_grade6_sample_remove_internal_quotas_2026-09-10',
                'productionAuthorizationId': key, 'buildItemId': identity['buildItemId'],
                'previousContinuationSha256': digest(previous[-1]) if previous else None,
                'oldPolicy': policy.raw, 'newPolicy': new_policy.raw, 'snapshot': snapshot,
                'authorizationChanges': [{'old': a, 'new': {**a, 'expires_at': expires_at}} for a in authorities],
                'anchorReservationId': anchor}
            if expected_sha is not None and expected_sha != digest(audit):
                raise ValueError('policy, original authorization, or ledger changed since review')
            if not apply:
                return _view(audit)
            folder = Path(archives); folder.mkdir(parents=True, exist_ok=True)
            archive = folder / ('authorization-continuation-' + expected_sha + '.json')
            try:
                fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if digest(json.loads(archive.read_text())) != expected_sha:
                    raise ValueError('continuation archive conflicts with the reviewed evidence')
            else:
                with os.fdopen(fd, 'w') as stream:
                    stream.write(canonical(audit)); stream.flush(); os.fsync(stream.fileno())
            if LearningBudgetPolicy.load(path).sha256 != policy.sha256:
                raise ValueError('paused policy changed during continuation')
            for change in audit['authorizationChanges']:
                old, new = change['old'], change['new']
                _validate_change(old, new)
                changed = conn.execute('UPDATE learning_budget_authorizations SET expires_at=? WHERE id=? AND scope_json=? '
                    'AND limits_json=? AND price_keys_json=? AND policy_sha256=? AND expires_at=? AND revoked_at IS NULL',
                    (expires_at, old['id'], old['scope_json'], old['limits_json'], old['price_keys_json'], old['policy_sha256'], old['expires_at']))
                if changed.rowcount != 1:
                    raise ValueError('same-authorization expiry CAS rejected')
            budget.repository.event(conn, anchor, EVENT, {'continuationSha256': expected_sha, 'audit': audit}, now)
    # Commit the audited expiry before re-enabling; exact replay repairs a file-write failure.
    if LearningBudgetPolicy.load(path).sha256 not in {digest(audit['oldPolicy']), digest(audit['newPolicy'])}:
        raise ValueError('policy changed after continuation commit; it remains unmodified')
    write_policy(path, LearningBudgetPolicy(audit['newPolicy']))
    return _view(audit, applied=True)
