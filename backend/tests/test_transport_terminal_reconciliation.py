"""Plan/apply against a temporary SQL database, never a running deployment."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from content.learning_budget_policy import LearningBudgetPolicy, UNITS, canonical, digest
from services.learning_budget_service import LearningBudgetService
from services import learning_transport_terminal_reconciliation as recovery
from tests.test_learning_budget import IsolatedDatabase, test_policy


class ReadConnection:
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = lambda cur, row: {desc[0]: value for desc, value in zip(cur.description, row)}
    def execute(self, sql, args=()):
        return self.conn.execute('BEGIN' if sql == 'START TRANSACTION READ ONLY' else sql, args)
    def rollback(self):
        self.conn.rollback()
    def close(self):
        self.conn.close()


class TransportTerminalReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = IsolatedDatabase(self.directory / 'isolated.db')
        self.database.connect = lambda: ReadConnection(self.database.path)
        raw = test_policy()
        raw['prices']['fake-text-v1']['provider'] = 'deepseek'
        raw['prices']['fake-tts-v1'] = {**raw['prices']['fake-text-v1'], 'provider': 'qwen-tts'}
        self.service = LearningBudgetService(self.database, policy=LearningBudgetPolicy(raw), clock=lambda: 100000)
        self.auth = digest('existing-production-authority')
        scope = {'purpose': 'production', 'gradeCode': 'primary_6', 'subject': 'math', 'courseId': 'original-course',
                 'courseVersion': 'v1', 'productionJobId': 'original-job', 'userId': None, 'sessionId': None,
                 'approvalReference': 'original-approval'}
        self.service.create_authorization(authorization_id=self.auth, scope=scope,
            max_units=dict.fromkeys(UNITS, 1000000), price_keys=['fake-text-v1', 'fake-tts-v1'], expires_at=200000)
        attributions = []
        for index in range(4):
            namespace = 'miraformal_' + digest(index)
            source = {'id': namespace}
            attribution = {'namespace': namespace, 'kind': 'native_session'}
            if index == 0:
                source = {'tts': {'requestId': 'formal_tts_original', 'state': 'ambiguous'}}
                attribution.update(kind='original_tts_request', physicalRequestId='formal_tts_original',
                                   sourceRecordSha256=digest(source['tts']))
            source_path = self.write(f'source-{index}.json', source)
            request_sha = digest('request-' + str(index))
            dispatch = 'runtime:' + recovery._sha(json.dumps([self.auth, namespace, request_sha], separators=(',', ':')).encode())
            row = self.service.reserve(authorization_id=self.auth, dispatch_id=dispatch, request_sha256=request_sha,
                price_key='fake-tts-v1' if index == 0 else 'fake-text-v1',
                max_units={'calls': 1, 'input_tokens': 100, 'output_tokens': 50})
            self.service.dispatch(authorization_id=self.auth, reservation_id=row['reservationId'], request_sha256=request_sha)
            self.service.unknown(authorization_id=self.auth, reservation_id=row['reservationId'], reason_code='provider_result_unknown')
            attribution.update(reservationId=row['reservationId'], sourcePath=str(source_path), sourceSha256=recovery._sha(source_path.read_bytes()))
            attributions.append(attribution)
        self.original_rows, self.original_auth, self.original_events = self.snapshot()
        audit_rows = []
        for row in self.original_rows:
            item = {key: value for key, value in row.items() if key not in {'max_units_json', 'actual_units_json', 'price_json'}}
            item.update(maxUnits=json.loads(row['max_units_json']), actualUnits=None,
                        priceIdentity={key: json.loads(row['price_json'])[key] for key in ('key', 'provider', 'model', 'version')})
            audit_rows.append(item)
        self.audit = {'readOnly': True, 'globalPendingStateCounts': {'reserved': 0, 'dispatched': 0, 'unknown': 4}, 'globalPendingRows': audit_rows}
        self.patch = patch.object(recovery, 'SOURCE_AUDIT_SHA', digest(self.audit))
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.source_path = self.write('audit.json', self.audit)
        self.stop = {'stoppedAt': 100100, 'sourceAttribution': attributions}
        self.stop_path = self.write('stop.json', self.stop)
        self.verifier = Mock()

    def write(self, name, value):
        path = self.directory / name
        path.write_text(canonical(value))
        return path

    def snapshot(self):
        with self.database.transaction() as conn:
            return tuple(conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall() for table in
                         ('learning_budget_reservations', 'learning_budget_authorizations', 'learning_budget_events'))

    def plan(self):
        return recovery.plan_reconciliation(database=self.database, source_audit=self.source_path,
            stop_evidence=self.stop_path, approval_reference='reviewed-four-original-transports',
            verifier=self.verifier, archives=self.directory / 'archives')

    def apply(self, plan):
        return recovery.apply_reconciliation(database=self.database, plan_path=plan['planPath'],
            expected_plan_sha=plan['planSha256'], now=100200, verifier=self.verifier)

    def test_plan_is_read_only_apply_only_appends_four_complete_events_and_is_idempotent(self):
        before = self.snapshot()
        plan = self.plan()
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(plan['applied'])
        result = self.apply(plan)
        rows, authorities, events = self.snapshot()
        self.assertEqual(rows, self.original_rows)
        self.assertEqual(authorities, self.original_auth)
        self.assertEqual(events[:len(self.original_events)], self.original_events)
        self.assertEqual(len(events) - len(self.original_events), 4)
        self.assertEqual(recovery.validated_terminal_ids(rows, events, authorities), {row['id'] for row in rows})
        self.assertFalse(result['reused'])
        self.assertTrue(self.apply(plan)['reused'])
        self.assertEqual(self.snapshot(), (rows, authorities, events))

    def test_second_live_verification_failure_rolls_back_all_events(self):
        plan = self.plan()
        self.verifier.side_effect = [None, ValueError('process restarted')]
        with self.assertRaisesRegex(ValueError, 'restarted'):
            self.apply(plan)
        self.assertEqual(self.snapshot(), (self.original_rows, self.original_auth, self.original_events))

    def test_source_stop_file_and_archive_tampering_are_rejected(self):
        plan = self.plan()
        original = self.stop_path.read_text()
        self.stop_path.write_text(original + ' ')
        with self.assertRaises(ValueError): self.apply(plan)
        self.stop_path.write_text(original)
        path = Path(plan['planPath'])
        archive = json.loads(path.read_text())
        archive['plan']['localTransportEndedAt'] += 1
        path.write_text(canonical(archive))
        with self.assertRaises(ValueError): self.apply(plan)
        self.assertEqual(self.snapshot(), (self.original_rows, self.original_auth, self.original_events))

    def test_changed_original_ledger_or_authority_is_rejected(self):
        plan = self.plan()
        with self.database.transaction() as conn:
            conn.execute('UPDATE learning_budget_authorizations SET expires_at=expires_at+1 WHERE id=?', (self.auth,))
        with self.assertRaises(ValueError): self.apply(plan)
        self.assertEqual(self.snapshot()[2], self.original_events)

    def test_wrong_namespace_or_repair_request_cannot_attribute_original_cost(self):
        original = deepcopy(self.stop)
        self.stop['sourceAttribution'][0]['namespace'] += ':other'
        self.write('stop.json', self.stop)
        with self.assertRaises(ValueError): self.plan()
        self.stop = original
        self.stop['sourceAttribution'][0]['physicalRequestId'] += '.repair1'
        self.write('stop.json', self.stop)
        with self.assertRaises(ValueError): self.plan()

    def test_different_four_or_three_rows_cannot_reuse_original_audit(self):
        wrong = deepcopy(self.audit)
        wrong['globalPendingRows'].pop()
        self.write('audit.json', wrong)
        with self.assertRaises(ValueError): self.plan()
        self.write('audit.json', self.audit)
        with self.database.transaction() as conn:
            conn.execute("UPDATE learning_budget_reservations SET request_identity_sha256=? WHERE id=?",
                         (digest('changed'), self.original_rows[0]['id']))
        with self.assertRaises(ValueError): self.plan()

    def test_partial_receipt_batch_is_never_completed_by_apply(self):
        plan = self.plan()
        archive = json.loads(Path(plan['planPath']).read_text())
        with self.database.transaction() as conn:
            self.service.repository.event(conn, self.original_rows[0]['id'], recovery.EVENT,
                recovery.receipt(archive['plan'], self.original_rows[0]['id']), 100200)
        with self.assertRaises(ValueError): self.apply(plan)
        self.assertEqual(len(self.snapshot()[2]) - len(self.original_events), 1)

    def test_future_unknown_is_not_auto_included_or_changed(self):
        plan = self.plan()
        future = self.service.reserve(authorization_id=self.auth, dispatch_id='future', request_sha256=digest('future'),
            price_key='fake-text-v1', max_units={'calls': 1, 'input_tokens': 100, 'output_tokens': 50})
        self.service.dispatch(authorization_id=self.auth, reservation_id=future['reservationId'], request_sha256=future['requestSha256'])
        self.service.unknown(authorization_id=self.auth, reservation_id=future['reservationId'], reason_code='new_unknown')
        self.apply(plan)
        rows, authorities, events = self.snapshot()
        confirmed = recovery.validated_terminal_ids(rows, events, authorities)
        self.assertEqual(len(confirmed), 4)
        self.assertNotIn(future['reservationId'], confirmed)

    def test_default_verifier_rechecks_processes_ports_and_managed_stop_log(self):
        log = self.directory / 'managed-stop.log'
        log.write_text('synthetic managed stop fixture\n')
        ports = [{'port': port, 'pids': []} for port in (3000, 3100, 3101, 8000)]
        processes = [{'pid': 999991, 'ppid': 1, 'startIdentity': 'known-start', 'cwd': str(recovery.ROOT / 'backend'),
                      'commandSha256': digest('python app.py'), 'role': 'backend'},
                     {'pid': 999992, 'ppid': 1, 'startIdentity': 'known-start', 'cwd': str(recovery.ROOT / 'openmaic-runtime'),
                      'commandSha256': digest('node server'), 'role': 'native_or_gateway'}]
        evidence = {'schemaVersion': recovery.STOP_SCHEMA, 'sourceAuditSha256': recovery.SOURCE_AUDIT_SHA,
            'deploymentRoot': str(recovery.ROOT), 'capturedAt': 100000, 'stoppedAt': 100100, 'verifiedAt': 100101,
            'before': {'processes': processes, 'ports': ports}, 'after': {'processes': [], 'ports': ports},
            'managedStop': {'command': ['/bin/bash', str(recovery.ROOT / 'openmaic-runtime/scripts/local-test-stack.sh'), 'stop'],
                            'exitCode': 0, 'startedAt': 100000, 'completedAt': 100100,
                            'logPath': str(log), 'logSha256': recovery._sha(log.read_bytes())}}
        with patch.object(recovery.os, 'kill', side_effect=ProcessLookupError), \
             patch.object(recovery.socket, 'socket') as sockets, \
             patch('scripts.collect_learning_transport_stop.probe', return_value={'processes': [], 'ports': ports}) as probe:
            sockets.return_value.__enter__.return_value.connect_ex.return_value = 61
            recovery.verify_stopped(evidence)
            probe.return_value = {'processes': [processes[0]], 'ports': ports}
            with self.assertRaises(ValueError): recovery.verify_stopped(evidence)
            probe.return_value = {'processes': [], 'ports': ports}
            sockets.return_value.__enter__.return_value.connect_ex.return_value = 0
            with self.assertRaises(ValueError): recovery.verify_stopped(evidence)
            sockets.return_value.__enter__.return_value.connect_ex.return_value = 61
            log.write_text('changed log')
            with self.assertRaises(ValueError): recovery.verify_stopped(evidence)
        with patch.object(recovery.os, 'kill', return_value=None):
            log.write_text('synthetic managed stop fixture\n')
            with self.assertRaisesRegex(ValueError, 'still present'): recovery.verify_stopped(evidence)
