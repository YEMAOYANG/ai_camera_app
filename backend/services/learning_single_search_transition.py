"""One audited Brave-to-Baidu transition; no new grant, instance or paid call."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re

from content.learning_budget_policy import LearningBudgetPolicy, canonical, digest
from content.single_course_budget import build_single_course_policy

EVENT = 'search_provider_transition'
BAIDU_KEY = 'baidu-search-standard-2026-09-10'
BRAVE_KEY = 'brave-search-ceiling'
JOB = 'omformal_d57c133cbf917beb4cb30bb0'
ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / 'backend/data/learning-provider-replies'
EXTERNAL_MICROS = 72000


def _transition_event(conn, authorization_id):
    row = conn.execute('SELECT e.evidence_json FROM learning_budget_events e '
        'JOIN learning_budget_reservations r ON r.id=e.reservation_id '
        'WHERE r.authorization_id=? AND e.event_type=? ORDER BY e.id DESC LIMIT 1',
        (authorization_id, EVENT)).fetchone()
    if not row:
        return None
    envelope = json.loads(row['evidence_json'])
    audit = envelope.get('audit')
    if not isinstance(audit, dict) or digest(audit) != envelope.get('transitionSha256'):
        raise ValueError('search transition audit is invalid')
    return audit


def transition_active_prices(conn, authority):
    """Only the audited selected prices are active; historical prices stay stored."""
    frozen = json.loads(authority['price_keys_json'])
    if not {BRAVE_KEY, BAIDU_KEY} <= set(frozen.get('prices', {})):
        return None
    audit = _transition_event(conn, authority['id'])
    if not audit:
        return None
    from services.learning_single_budget_continuation import validate_continued_authority
    validate_continued_authority(conn, authority, original=audit['newAuthorization'])
    raw = audit['newPolicy']
    return {key: raw['prices'][key] for key in raw['authorizationTemplates']['production']['priceKeys']}


def transition_allows_template(conn, authority, requested_prices):
    active = transition_active_prices(conn, authority)
    return active is not None and requested_prices == {'keys': sorted(active), 'prices': active}


def _probe_evidence():
    evidence = []
    for filename in ('baidu-search-probe.json', 'baidu-runtime-search-probe.json'):
        path = ROOT / 'output' / filename
        data = path.read_bytes()
        result = json.loads(data)
        if (result.get('ok') is not True or result.get('httpStatus') != 200
                or not isinstance(result.get('requestId'), str) or not result['requestId']):
            raise ValueError('the two real Baidu diagnostic receipts are required')
        if filename == 'baidu-runtime-search-probe.json' and (
                result.get('actualHttpRequests') != 1 or result.get('edition') != 'standard'
                or result.get('providerId') != 'baidu' or result.get('modelCalls') != 0):
            raise ValueError('Baidu runtime diagnostic identity changed')
        evidence.append({'artifact': filename, 'sha256': hashlib.sha256(data).hexdigest(),
            'requestId': result['requestId'], 'provider': 'baidu', 'model': 'baidu-web-search',
            'edition': 'standard', 'calls': 1, 'estimatedMoneyMicros': 36000})
    if len({row['requestId'] for row in evidence}) != 2:
        raise ValueError('Baidu diagnostics must be two distinct actual requests')
    return evidence


def _snapshot(conn, budget, identity):
    if budget.repository.control(conn)['halted']:
        raise ValueError('global budget is halted')
    scope, _ = budget._catalog_production_scope(conn, identity['buildItemId'])
    if scope != identity['scope']:
        raise ValueError('current enabled catalog scope differs from the frozen sample')
    item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=?',
        (identity['buildItemId'],)).fetchone()
    runtimes = list(conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms '
        'WHERE candidate_build_item_id=? ORDER BY id', (identity['buildItemId'],)).fetchall())
    dispatches = list(conn.execute('SELECT * FROM learning_course_provider_dispatches '
        'WHERE build_item_id=? ORDER BY id', (identity['buildItemId'],)).fetchall())
    if (not item or item['content_phase'] != 'course_ready' or item['content_gate_status'] != 'passed'
            or len(runtimes) != 1 or runtimes[0]['upstream_job_id'] != JOB
            or runtimes[0]['status'] != 'failed' or len(dispatches) != 13):
        raise ValueError('only the accepted original thirteen-phase, one-instance sample may transition')
    ledger = [dict(row) for row in conn.execute('SELECT * FROM learning_budget_reservations ORDER BY id').fetchall()]
    if any(row['state'] not in {'settled', 'released'} for row in ledger):
        raise ValueError('all prior calls must be settled/released; no unknown or in-flight transition')
    amounts = [(row, json.loads(row['actual_units_json'])) for row in ledger if row['state'] == 'settled']
    summary = {'rows': len(ledger), 'settledCalls': sum(v['calls'] for _, v in amounts),
        'totalMoneyMicros': sum(v['money_micros'] for _, v in amounts),
        'productionMoneyMicros': sum(v['money_micros'] for r, v in amounts if r['purpose'] == 'production'),
        'ledgerSha256': digest(ledger), 'catalogSha256': digest({'item': dict(item),
            'runtimes': [dict(r) for r in runtimes], 'dispatches': [dict(r) for r in dispatches]})}
    return ledger, summary


def _audit(conn, budget, policy, identity, now, probes, continuation_expires_at=None):
    window = policy.raw.get('authorizationWindow') or {}
    if (policy.raw['enabled'] is not False or window.get('scopes') != [identity['scope']]
            or not window.get('startsAt', now + 1) <= now < window.get('expiresAt', 0)
            or identity['scope']['gradeCode'] != 'primary_6' or identity['scope']['subject'] != 'math'
            or identity['slot']['skillId'] != 'fraction_ratio_percentage' or identity['slot']['variantOrdinal'] != 1):
        raise ValueError('the original paused, unexpired single-slot policy is required')
    key = digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': identity['scope']})
    authority = budget.repository.authorization(conn, key)
    if (authority is None or authority['revoked_at'] is not None or authority['expires_at'] <= now
            or json.loads(authority['scope_json']) != identity['scope']
            or authority['expires_at'] > window['expiresAt']):
        raise ValueError('the original unrevoked, unexpired authorization is required')
    if _transition_event(conn, key):
        raise ValueError('this authorization already has a search transition; use its original SHA for retry')
    ledger, summary = _snapshot(conn, budget, identity)
    own = [r for r in ledger if r['authorization_id'] == key and r['state'] == 'settled']
    if not own:
        raise ValueError('the original settled authorization history is required')
    template = policy.raw['authorizationTemplates']['production']
    frozen = json.loads(authority['price_keys_json'])
    expected = {'keys': sorted(template['priceKeys']),
        'prices': {k: policy.price(k) for k in sorted(template['priceKeys'])}}
    if (frozen != expected or BRAVE_KEY not in frozen['prices'] or BAIDU_KEY in frozen['prices']
            or json.loads(authority['limits_json']) != template['maxUnits']):
        raise ValueError('original frozen Brave price/template has changed')
    if sum(p['estimatedMoneyMicros'] for p in probes) != EXTERNAL_MICROS:
        raise ValueError('the two independently billed diagnostics must remain in the total ceiling')
    if summary['totalMoneyMicros'] + EXTERNAL_MICROS >= 10000000 or summary['productionMoneyMicros'] + EXTERNAL_MICROS >= 8000000:
        raise ValueError('no remaining original sample production budget')
    generated, _ = build_single_course_policy(grade='primary_6', subject='math', skill='fraction_ratio_percentage',
        ordinal=1, now=window['startsAt'], ttl_ms=window['expiresAt'] - window['startsAt'], search_provider='baidu')
    new_raw = deepcopy(policy.raw)
    new_raw['prices'].pop(BRAVE_KEY)
    new_raw['prices'][BAIDU_KEY] = generated.price(BAIDU_KEY)
    new_raw['authorizationTemplates']['production']['priceKeys'] = [
        BAIDU_KEY if k == BRAVE_KEY else k for k in template['priceKeys']]
    # These real diagnostics are outside this ledger. Deduct them from available
    # ceilings instead of fabricating reservations or wiping historical costs.
    for period in ('day', 'month'):
        new_raw['limits']['global'][period]['money_micros'] = min(new_raw['limits']['global'][period]['money_micros'], 10000000 - EXTERNAL_MICROS)
        new_raw['limits']['purposes']['production'][period]['money_micros'] = min(new_raw['limits']['purposes']['production'][period]['money_micros'], 8000000 - EXTERNAL_MICROS)
    for maximum in (new_raw['limits']['course']['lifetime'], new_raw['limits']['authorization']):
        maximum['money_micros'] = min(maximum['money_micros'], 10000000 - EXTERNAL_MICROS)
    new_raw['authorizationTemplates']['production']['maxUnits']['money_micros'] = min(template['maxUnits']['money_micros'], 8000000 - EXTERNAL_MICROS)
    new_expiry = authority['expires_at']
    if continuation_expires_at is not None:
        today = datetime.fromtimestamp(now / 1000, policy.timezone).date()
        if (str(policy.timezone) != 'Asia/Shanghai' or type(continuation_expires_at) is not int
                or not max(now, window['expiresAt']) < continuation_expires_at <= now + 3 * 3600000
                or datetime.fromtimestamp(continuation_expires_at / 1000, policy.timezone).date() != today
                or datetime.fromtimestamp(window['startsAt'] / 1000, policy.timezone).date() != today):
            raise ValueError('continuation expiry must extend this same-day sample by at most three hours from now')
        new_expiry = continuation_expires_at
        new_raw['authorizationWindow']['expiresAt'] = new_expiry
    new_raw['enabled'] = True
    new_policy = LearningBudgetPolicy(new_raw)
    new_frozen = deepcopy(frozen)
    new_frozen['keys'] = sorted([*frozen['keys'], BAIDU_KEY])
    new_frozen['prices'][BAIDU_KEY] = generated.price(BAIDU_KEY)
    new_authority = {**dict(authority), 'price_keys_json': canonical(new_frozen),
        'limits_json': canonical(new_raw['authorizationTemplates']['production']['maxUnits']),
        'policy_sha256': new_policy.sha256, 'expires_at': new_expiry}
    return {'schemaVersion': 'mira.single-course.search-transition.v1',
        'approvalReference': 'user_continue_same_grade6_math_2026-09-10', 'authorizationId': key,
        'buildItemId': identity['buildItemId'], 'jobId': JOB, 'oldPolicy': policy.raw,
        'oldAuthorization': dict(authority), 'newAuthorization': new_authority, 'newPolicy': new_policy.raw,
        'anchorReservationId': own[-1]['id'], 'snapshot': summary, 'externalDiagnostics': probes,
        'externalEstimatedMoneyMicros': EXTERNAL_MICROS, 'windowExtended': new_expiry != authority['expires_at'],
        'newAuthorizationCreated': False, 'historicalPricesPreserved': True}


def _view(audit, *, applied=False):
    return {'transitionSha256': digest(audit), 'authorizationId': audit['authorizationId'],
        'buildItemId': audit['buildItemId'], 'jobId': JOB, 'searchProvider': 'baidu',
        'snapshot': audit['snapshot'], 'externalEstimatedMoneyMicros': EXTERNAL_MICROS,
        'ledgerGlobalCeilingMicros': audit['newPolicy']['limits']['global']['day']['money_micros'],
        'ledgerProductionCeilingMicros': audit['newPolicy']['limits']['purposes']['production']['day']['money_micros'],
        'expiresAt': audit['newAuthorization']['expires_at'],
        'originalExpiresAt': audit['oldAuthorization']['expires_at'], 'windowExtended': audit['windowExtended'],
        'newAuthorizationCreated': False, 'providerCalls': 0, 'applied': applied}


def transition_single_search(*, database, policy_path, identity, now, expected_sha=None,
                             apply=False, write_policy=None, archives=ARCHIVES, probes=None,
                             continuation_expires_at=None):
    from services.learning_budget_service import LearningBudgetService
    if expected_sha is not None and not re.fullmatch(r'[a-f0-9]{64}', expected_sha):
        raise ValueError('transition SHA must be exact')
    if apply and (expected_sha is None or write_policy is None):
        raise ValueError('apply requires the reviewed transition SHA and atomic policy writer')
    policy_path = Path(policy_path).resolve()
    policy = LearningBudgetPolicy.load(policy_path)
    budget = LearningBudgetService(database, policy=policy)
    key = digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': identity['scope']})
    evidence = _probe_evidence() if probes is None else probes
    manager = budget.repository.locked() if apply else database.transaction()
    with manager as conn:
        previous = _transition_event(conn, key)
        if previous:
            if not apply or digest(previous) != expected_sha:
                raise ValueError('search transition already recorded; retry only its original expected SHA')
            audit = previous
            row = budget.repository.authorization(conn, key)
            _, snapshot = _snapshot(conn, budget, identity)
            if (dict(row) != audit['newAuthorization'] or snapshot != audit['snapshot']
                    or evidence != audit['externalDiagnostics'] or now >= row['expires_at']
                    or continuation_expires_at != (row['expires_at'] if audit['windowExtended'] else None)
                    or policy.sha256 not in {digest(audit['oldPolicy']), digest(audit['newPolicy'])}):
                raise ValueError('partially applied transition no longer matches its immutable audit')
        else:
            audit = _audit(conn, budget, policy, identity, now, evidence, continuation_expires_at)
            if expected_sha is not None and expected_sha != digest(audit):
                raise ValueError('policy, authorization or ledger changed since transition review')
            if not apply:
                return _view(audit)
            folder = Path(archives); folder.mkdir(parents=True, exist_ok=True)
            path = folder / ('search-transition-' + expected_sha + '.json')
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if digest(json.loads(path.read_text())) != expected_sha:
                    raise ValueError('transition archive conflicts with reviewed evidence')
            else:
                with os.fdopen(fd, 'w') as out:
                    out.write(canonical(audit)); out.flush(); os.fsync(out.fileno())
            if LearningBudgetPolicy.load(policy_path).sha256 != policy.sha256:
                raise ValueError('paused policy changed during transition')
            old, new = audit['oldAuthorization'], audit['newAuthorization']
            changed = conn.execute('UPDATE learning_budget_authorizations SET price_keys_json=?, limits_json=?, policy_sha256=?, expires_at=? '
                'WHERE id=? AND scope_json=? AND price_keys_json=? AND limits_json=? AND policy_sha256=? '
                'AND expires_at=? AND revoked_at IS NULL',
                (new['price_keys_json'], new['limits_json'], new['policy_sha256'], new['expires_at'], key, old['scope_json'],
                 old['price_keys_json'], old['limits_json'], old['policy_sha256'], old['expires_at']))
            if changed.rowcount != 1:
                raise ValueError('original authorization transition CAS rejected')
            budget.repository.event(conn, audit['anchorReservationId'], EVENT,
                {'transitionSha256': expected_sha, 'audit': audit}, now)
    # The DB commit precedes enabling. A crash leaves calls paused; replaying this
    # exact event finishes the file install without amending a second grant.
    if LearningBudgetPolicy.load(policy_path).sha256 not in {digest(audit['oldPolicy']), digest(audit['newPolicy'])}:
        raise ValueError('policy changed after transition commit; it remains unmodified')
    write_policy(policy_path, LearningBudgetPolicy(audit['newPolicy']))
    return _view(audit, applied=True)
