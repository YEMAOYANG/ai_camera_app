"""Explicit historical local-transport audit; never settles or releases money."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket

from content.learning_budget_policy import canonical, digest
from repositories.learning_budget_repository import LearningBudgetRepository

ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / 'backend/data/learning-provider-replies'
EVENT = 'transport_terminal_confirmed'
PLAN_SCHEMA = 'mira.learning.transport-terminal-plan.v1'
RECEIPT_SCHEMA = 'mira.learning.transport-terminal-receipt.v1'
STOP_SCHEMA = 'mira.learning.managed-transport-stop.v1'
SOURCE_AUDIT_SHA = 'cebd0b3f1d491452525e4707ff0afccd858955a38af858693b1e370d89d59267'
KIND = 'managed_deployment_processes_exited'
SCOPE = 'local_transport_concurrency_only'
SETTLEMENT_FIELDS = ('actual_units_json', 'settlement_sha256', 'provider_request_id', 'settled_at')
CLAIM_FIELDS = {'reservationId', 'reservationSnapshotSha256', 'authorizationId',
                'authorizationSnapshotSha256', 'requestIdentitySha256', 'dispatchedAt'}
PLAN_FIELDS = {'schemaVersion', 'confirmationKind', 'scope', 'sourceAuditSha256', 'stopEvidenceSha256',
               'reservationClaims', 'localTransportEndedAt', 'approvalReference'}


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _is_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _require(ok):
    if not ok:
        raise ValueError('local transport audit evidence or identity changed')


def validate_plan(plan):
    _require(isinstance(plan, dict) and set(plan) == PLAN_FIELDS)
    _require(plan['schemaVersion'] == PLAN_SCHEMA and plan['confirmationKind'] == KIND and plan['scope'] == SCOPE)
    _require(plan['sourceAuditSha256'] == SOURCE_AUDIT_SHA and _is_sha(plan['stopEvidenceSha256']))
    _require(isinstance(plan['approvalReference'], str) and 1 <= len(plan['approvalReference']) <= 160)
    ended = plan['localTransportEndedAt']
    _require(type(ended) is int and ended > 0)
    claims = plan['reservationClaims']
    _require(isinstance(claims, list) and len(claims) == 4)
    for claim in claims:
        _require(isinstance(claim, dict) and set(claim) == CLAIM_FIELDS)
        _require(all(_is_sha(claim[key]) for key in CLAIM_FIELDS - {'dispatchedAt'}))
        _require(type(claim['dispatchedAt']) is int and 0 < claim['dispatchedAt'] <= ended)
    ids = [claim['reservationId'] for claim in claims]
    _require(ids == sorted(set(ids)))
    return claims


def _original_unknown(row):
    row = dict(row)
    if row.get('state') == 'settled':
        # Only normal settlement fields may change after the transport audit.
        _require(_is_sha(row.get('settlement_sha256')) and type(row.get('settled_at')) is int)
        actual = json.loads(row.get('actual_units_json') or 'null')
        _require(isinstance(actual, dict) and actual.get('calls') == 1
                 and all(type(v) is int and v >= 0 for v in actual.values()))
        row.update(state='unknown', **dict.fromkeys(SETTLEMENT_FIELDS))
    _require(row.get('state') == 'unknown' and all(row.get(key) is None for key in SETTLEMENT_FIELDS))
    return row


def validated_terminal_ids(reservation_rows, event_rows, authorization_rows):
    """Bad, incomplete or conflicting batches remain charged to concurrency."""
    rows = {row['id']: dict(row) for row in reservation_rows}
    authorities = {row['id']: dict(row) for row in authorization_rows}
    candidates = {}
    anchors = {}
    for event in event_rows:
        if event.get('event_type') != EVENT:
            continue
        anchor = event.get('reservation_id')
        anchors.setdefault(anchor, []).append(event)
        try:
            evidence = json.loads(event['evidence_json'])
            _require(set(evidence) == {'schemaVersion', 'planSha256', 'reservationId', 'batchSha256', 'plan'})
            claims = validate_plan(evidence['plan'])
            _require(evidence['schemaVersion'] == RECEIPT_SCHEMA and evidence['reservationId'] == anchor)
            _require(evidence['planSha256'] == digest(evidence['plan']) and evidence['batchSha256'] == digest(claims))
            _require(anchor in {claim['reservationId'] for claim in claims})
            candidates[evidence['planSha256']] = evidence['plan']
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    result = set()
    for plan_sha, plan in candidates.items():
        try:
            claims = validate_plan(plan)
            for claim in claims:
                identity = claim['reservationId']
                _require(len(anchors.get(identity, [])) == 1)
                evidence = json.loads(anchors[identity][0]['evidence_json'])
                _require(evidence == receipt(plan, identity))
                _require(type(anchors[identity][0].get('created_at')) is int
                         and anchors[identity][0]['created_at'] >= plan['localTransportEndedAt'])
                row = rows[identity]
                _require(row['authorization_id'] == claim['authorizationId']
                         and row['request_identity_sha256'] == claim['requestIdentitySha256']
                         and row['dispatched_at'] == claim['dispatchedAt'])
                _require(digest(_original_unknown(row)) == claim['reservationSnapshotSha256'])
                _require(digest(authorities[claim['authorizationId']]) == claim['authorizationSnapshotSha256'])
                if row['state'] == 'settled':
                    settled = [event for event in event_rows if event.get('event_type') == 'settled'
                               and event.get('reservation_id') == identity]
                    _require(len(settled) == 1)
                    evidence = json.loads(settled[0]['evidence_json'])
                    _require(_is_sha(evidence.get('evidenceSha256')))
                    settlement = digest({'actualUnits': json.loads(row['actual_units_json']),
                                         'providerRequestId': row['provider_request_id'],
                                         'evidenceSha256': evidence['evidenceSha256']})
                    _require(settlement == row['settlement_sha256'] == evidence.get('settlementSha256')
                             and settled[0]['created_at'] == row['settled_at'])
            result.update(claim['reservationId'] for claim in claims if rows[claim['reservationId']]['state'] == 'unknown')
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return result


def receipt(plan, reservation_id):
    return {'schemaVersion': RECEIPT_SCHEMA, 'planSha256': digest(plan), 'reservationId': reservation_id,
            'batchSha256': digest(plan['reservationClaims']), 'plan': plan}


def _load_rows(conn, ids):
    marks = ','.join('?' for _ in ids)
    rows = [dict(row) for row in conn.execute(f'SELECT * FROM learning_budget_reservations WHERE id IN ({marks}) ORDER BY id', tuple(ids)).fetchall()]
    auth_ids = sorted({row['authorization_id'] for row in rows})
    auth_marks = ','.join('?' for _ in auth_ids)
    authorities = [dict(row) for row in conn.execute(f'SELECT * FROM learning_budget_authorizations WHERE id IN ({auth_marks}) ORDER BY id', tuple(auth_ids)).fetchall()] if auth_ids else []
    return rows, authorities


def verified_transport_terminal_reservation_ids(conn, *, pending_rows):
    if not any(row.get('state') == 'unknown' for row in pending_rows):
        return set()
    events = [dict(row) for row in conn.execute('SELECT * FROM learning_budget_events WHERE event_type=? ORDER BY id', (EVENT,)).fetchall()]
    ids = sorted({event['reservation_id'] for event in events})
    if not ids:
        return set()
    rows, authorities = _load_rows(conn, ids)
    marks = ','.join('?' for _ in ids)
    events += [dict(row) for row in conn.execute(f"SELECT * FROM learning_budget_events WHERE event_type='settled' AND reservation_id IN ({marks}) ORDER BY id", tuple(ids)).fetchall()]
    return validated_terminal_ids(rows, events, authorities)


def _file(path):
    path = Path(path).resolve()
    _require(path.is_file())
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': _sha(raw), 'raw': raw.decode()}


def _read_file(envelope):
    _require(set(envelope) == {'path', 'sha256', 'raw'} and _sha(envelope['raw'].encode()) == envelope['sha256'])
    _require(_sha(Path(envelope['path']).read_bytes()) == envelope['sha256'])
    return json.loads(envelope['raw'])


def verify_stopped(evidence):
    """Recheck local facts without trusting a captured 'passed' boolean."""
    _require(evidence.get('schemaVersion') == STOP_SCHEMA and evidence.get('sourceAuditSha256') == SOURCE_AUDIT_SHA)
    _require(evidence.get('deploymentRoot') == str(ROOT))
    for key in ('capturedAt', 'stoppedAt', 'verifiedAt'):
        _require(type(evidence.get(key)) is int)
    _require(0 < evidence['capturedAt'] <= evidence['stoppedAt'] <= evidence['verifiedAt'])
    managed = evidence['managedStop']
    command = managed['command']
    _require(len(command) == 3 and command[0] in {'bash', '/bin/bash'}
             and command[1] == str(ROOT / 'openmaic-runtime/scripts/local-test-stack.sh') and command[2] == 'stop')
    _require(type(managed.get('exitCode')) is int and managed['exitCode'] == 0)
    _require(evidence['capturedAt'] <= managed['startedAt'] <= managed['completedAt'] <= evidence['stoppedAt'])
    _require(_sha(Path(managed['logPath']).read_bytes()) == managed['logSha256'])
    before, after = evidence['before'], evidence['after']
    _require(isinstance(before['processes'], list) and before['processes'] and after['processes'] == [])
    _require(any(process.get('role') == 'backend' for process in before['processes'])
             and any(str(process.get('cwd', '')).startswith(str(ROOT / 'openmaic-runtime')) for process in before['processes']))
    for process in before['processes']:
        _require(type(process.get('pid')) is int and process['pid'] > 1 and process.get('startIdentity')
                 and isinstance(process.get('cwd'), str) and _is_sha(process.get('commandSha256')))
        try:
            os.kill(process['pid'], 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError('captured transport process is still present')
    ports = {entry['port'] for entry in before['ports']}
    _require(ports == {3000, 3100, 3101, 8000} and {entry['port'] for entry in after['ports']} == ports)
    for entry in after['ports']:
        _require(entry['pids'] == [] and type(entry['port']) is int and 1 <= entry['port'] <= 65535)
        with socket.socket() as sock:
            sock.settimeout(0.15)
            _require(sock.connect_ex(('127.0.0.1', entry['port'])) != 0)
    # Reuse the managed collector's exact ownership rules; do not classify Codex
    # or IDE infrastructure as a course Provider process merely by its cwd.
    from scripts.collect_learning_transport_stop import probe
    current = probe()
    _require(current['processes'] == [] and all(entry['pids'] == [] for entry in current['ports'])
             and {entry['port'] for entry in current['ports']} == ports)


def _source_rows(audit, rows):
    _require(digest(audit) == SOURCE_AUDIT_SHA and audit.get('readOnly') is True)
    _require(audit.get('globalPendingStateCounts') == {'reserved': 0, 'dispatched': 0, 'unknown': 4})
    expected = {row['id']: row for row in audit['globalPendingRows']}
    _require(len(expected) == 4 and set(expected) == {row['id'] for row in rows})
    for row in rows:
        source = expected[row['id']]
        _require(_original_unknown(row) == row and row['state'] == 'unknown')
        for field in ('id', 'authorization_id', 'dispatch_id', 'request_sha256', 'request_identity_sha256',
                      'purpose', 'course_key', 'policy_sha256', 'state', 'created_at', 'charge_at', 'dispatched_at',
                      'settlement_sha256', 'provider_request_id', 'settled_at'):
            _require(row[field] == source[field])
        _require(json.loads(row['max_units_json']) == source['maxUnits'] and source['actualUnits'] is None)
        price = json.loads(row['price_json'])
        _require(all(price[key] == value for key, value in source['priceIdentity'].items()))


def _attributions(evidence, rows):
    entries = evidence['sourceAttribution']
    _require(isinstance(entries, list) and len(entries) == 4)
    mapped = {entry['reservationId']: entry for entry in entries}
    _require(len(mapped) == 4 and set(mapped) == {row['id'] for row in rows})
    files = []
    for row in rows:
        entry = mapped[row['id']]
        source = _file(entry['sourcePath'])
        _require(source['sha256'] == entry['sourceSha256'])
        namespace = entry['namespace']
        _require(isinstance(namespace, str) and namespace)
        physical = json.dumps([row['authorization_id'], namespace, row['request_sha256']], ensure_ascii=False, separators=(',', ':'))
        _require(row['dispatch_id'] == 'runtime:' + _sha(physical.encode()))
        value = json.loads(source['raw'])
        price = json.loads(row['price_json'])
        if price['provider'] == 'deepseek':
            _require(entry['kind'] == 'native_session' and namespace.startswith('miraformal_'))
            session = value.get('session', value)
            _require(session.get('id') == namespace)
        elif price['provider'] == 'qwen-tts':
            value = value.get('tts', value)
            request_id = entry.get('physicalRequestId')
            _require(entry['kind'] == 'original_tts_request' and isinstance(request_id, str)
                     and '.repair' not in request_id and '.pronunciation' not in request_id)
            _require(value.get('requestId') == request_id and value.get('state') in {'failed', 'ambiguous'}
                     and not value.get('operatorRepair'))
            _require(digest(value) == entry.get('sourceRecordSha256'))
        else:
            raise ValueError('only the explicitly audited original providers are supported')
        files.append(source)
    return files


def _events(conn, ids):
    marks = ','.join('?' for _ in ids)
    return [dict(row) for row in conn.execute(f'SELECT * FROM learning_budget_events WHERE reservation_id IN ({marks}) ORDER BY id', tuple(ids)).fetchall()]


def plan_reconciliation(*, database, source_audit, stop_evidence, approval_reference,
                        verifier=verify_stopped, archives=ARCHIVES):
    source, stop = _file(source_audit), _file(stop_evidence)
    audit, evidence = _read_file(source), _read_file(stop)
    verifier(evidence)
    ids = sorted(row['id'] for row in audit['globalPendingRows'])
    conn = database.connect()
    try:
        conn.execute('START TRANSACTION READ ONLY')
        rows, authorities = _load_rows(conn, ids)
        _source_rows(audit, rows)
        events = _events(conn, ids)
        _require(not any(event['event_type'] == EVENT for event in events))
        files = _attributions(evidence, rows)
        auths = {row['id']: row for row in authorities}
        claims = [{'reservationId': row['id'], 'reservationSnapshotSha256': digest(row),
                   'authorizationId': row['authorization_id'], 'authorizationSnapshotSha256': digest(auths[row['authorization_id']]),
                   'requestIdentitySha256': row['request_identity_sha256'], 'dispatchedAt': row['dispatched_at']} for row in rows]
        plan = {'schemaVersion': PLAN_SCHEMA, 'confirmationKind': KIND, 'scope': SCOPE,
                'sourceAuditSha256': digest(audit), 'stopEvidenceSha256': digest(evidence),
                'reservationClaims': claims, 'localTransportEndedAt': evidence['stoppedAt'], 'approvalReference': approval_reference}
        validate_plan(plan)
        archive = {'plan': plan, 'sourceAudit': source, 'stopEvidence': stop, 'sourceFiles': files,
                   'reservations': rows, 'authorizations': authorities, 'priorEvents': events}
    finally:
        conn.rollback()
        conn.close()
    directory = Path(archives)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('transport-terminal-' + digest(plan) + '.json')
    data = canonical(archive).encode()
    if path.exists():
        _require(path.read_bytes() == data)
    else:
        with open(path, 'xb') as target:
            os.chmod(path, 0o600)
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
    return {'planSha256': digest(plan), 'planPath': str(path), 'reservationCount': 4, 'applied': False}


def apply_reconciliation(*, database, plan_path, expected_plan_sha, now,
                         verifier=verify_stopped):
    archive = json.loads(Path(plan_path).read_text())
    plan = archive['plan']
    claims = validate_plan(plan)
    _require(_is_sha(expected_plan_sha) and digest(plan) == expected_plan_sha)
    evidence = _read_file(archive['stopEvidence'])
    audit = _read_file(archive['sourceAudit'])
    _require(digest(evidence) == plan['stopEvidenceSha256'] and digest(audit) == plan['sourceAuditSha256'])
    _require(type(now) is int and now >= evidence.get('verifiedAt', evidence['stoppedAt']))
    verifier(evidence)
    ids = [claim['reservationId'] for claim in claims]
    repository = LearningBudgetRepository(database)
    with repository.locked() as conn:
        rows, authorities = _load_rows(conn, ids)
        _require(rows == archive['reservations'] and authorities == archive['authorizations'])
        _source_rows(audit, rows)
        _require(_attributions(evidence, rows) == archive['sourceFiles'])
        events = _events(conn, ids)
        prior = [event for event in events if event['event_type'] != EVENT]
        terminal = [event for event in events if event['event_type'] == EVENT]
        _require(prior == archive['priorEvents'])
        for row, claim in zip(rows, claims):
            _require(row['id'] == claim['reservationId'] and digest(row) == claim['reservationSnapshotSha256'])
        _require(all(digest(next(a for a in authorities if a['id'] == c['authorizationId'])) == c['authorizationSnapshotSha256'] for c in claims))
        verifier(evidence)
        if terminal:
            _require(len(terminal) == 4 and validated_terminal_ids(rows, terminal, authorities) == set(ids)
                     and all(json.loads(event['evidence_json'])['planSha256'] == expected_plan_sha for event in terminal))
            reused = True
        else:
            for identity in ids:
                repository.event(conn, identity, EVENT, receipt(plan, identity), now)
            reused = False
    return {'planSha256': expected_plan_sha, 'reservationCount': 4, 'applied': True,
            'reused': reused, 'reservationMutations': 0, 'authorizationMutations': 0, 'providerCalls': 0}
