"""Isolated SQL and fixture files only; never mint real grants or call Providers."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from content.learning_budget_policy import LearningBudgetPolicy, canonical, digest, UNITS
from core.errors import ApiError
from integrations.openmaic_formal_quality import quality_sha, quality_snapshot
from services.learning_budget_service import LearningBudgetService
from services import learning_saved_stage_tail_authorization as tail
from services.learning_transport_terminal_reconciliation import receipt, validated_terminal_ids
from tests.test_learning_budget import IsolatedDatabase


class SavedStageTailAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.db = IsolatedDatabase(self.path / 'budget.db')
        self.now = tail.PARENT_EXPIRES - 1000
        self.raw = LearningBudgetPolicy.load(Path(__file__).parents[1] / 'content/learning_classroom_policy.json').raw
        self.policy = LearningBudgetPolicy(self.raw)
        self.scope = {'purpose': 'production', 'gradeCode': 'primary_6', 'subject': 'math',
            'courseId': 'catalog-item:' + tail.IDENTITY['buildItemId'], 'courseVersion': 'synthetic-version',
            'productionJobId': tail.IDENTITY['buildItemId'], 'userId': None, 'sessionId': None,
            'approvalReference': 'same-original-approved-course'}
        self.addCleanup(patch.stopall)
        patch.object(tail, 'ROOT', self.path).start()
        patch.object(tail, 'SCOPE_SHA', digest(self.scope)).start()
        self.service = LearningBudgetService(self.db, policy=self.policy, clock=lambda: self.now)
        self.service._catalog_production_scope = Mock(return_value=(self.scope, True))
        self.parent = tail.IDENTITY['parentAuthorizationId']
        self.other = digest('fixture-other-original-authorization')
        self.prices = deepcopy(self.raw['prices'])
        self.prices['deepseek-vision-peak'] = {**deepcopy(self.prices['deepseek-flash-peak']),
            'model': 'deepseek-v4-flash-vision-exp',
            'perCallMax': {'calls': 1, 'input_tokens': 65536, 'output_tokens': 8192}}
        with self.db.transaction() as conn:
            for identity in (self.parent, self.other):
                self.service.repository.insert_authorization(conn, identity, self.scope,
                    {**dict.fromkeys(UNITS, 0), 'calls': 1},
                    {'keys': sorted(self.prices), 'prices': self.prices}, self.policy.sha256,
                    tail.PARENT_EXPIRES, self.now - 1000)
        anchor = self.reserve('anchor', self.parent)
        self.dispatch(anchor)
        self.service.settle(reservation_id=anchor['reservationId'], authorization_id=self.parent,
            actual_units={'calls': 1, 'input_tokens': 1, 'output_tokens': 1},
            provider_request_id='fixture-paid-receipt', evidence_sha256=digest('fixture-receipt'))
        self.unknowns = []
        for i in range(4):
            row = self.reserve('old-' + str(i), self.other if i == 3 else self.parent)
            self.dispatch(row)
            self.service.unknown(reservation_id=row['reservationId'], authorization_id=row['authorizationId'],
                                  reason_code='fixture-unknown')
            self.unknowns.append(row['reservationId'])
        self.now += 2000
        self.install_terminal_events()
        self.make_sources()
        with self.db.transaction() as conn:
            conn.execute('CREATE TABLE learning_openmaic_runtime_classrooms (id TEXT, candidate_build_item_id TEXT, upstream_job_id TEXT, request_id TEXT, retired_at INTEGER, status TEXT, feature_manifest_json TEXT)')
            conn.execute('CREATE TABLE learning_catalog_build_items (id TEXT, content_phase TEXT, content_gate_status TEXT)')
            conn.execute('INSERT INTO learning_openmaic_runtime_classrooms VALUES (?,?,?,?,?,?,?)',
                (tail.IDENTITY['runtimeId'], tail.IDENTITY['buildItemId'], tail.IDENTITY['jobId'],
                 tail.IDENTITY['runtimeRequestId'], None, 'failed', canonical({'paidBudget': tail._binding(self.parent)})))
            conn.execute('INSERT INTO learning_catalog_build_items VALUES (?,?,?)',
                (tail.IDENTITY['buildItemId'], 'course_ready', 'passed'))
        self.before = self.read_rows()

    def reserve(self, name, authorization_id=None, *, namespace=None, price_key='deepseek-flash-peak', max_units=None):
        authorization_id = authorization_id or tail.authorization_id()
        request_sha = digest(name)
        dispatch_id = name if authorization_id in (self.parent, self.other) else 'runtime:' + digest([
            authorization_id, namespace or tail.IDENTITY['sessionId'] + ':completion', request_sha])
        return self.service.reserve(authorization_id=authorization_id, dispatch_id=dispatch_id,
            request_sha256=request_sha, price_key=price_key,
            max_units=max_units or {'calls': 1, 'input_tokens': 100, 'output_tokens': 10})

    def dispatch(self, row):
        return self.service.dispatch(reservation_id=row['reservationId'], authorization_id=row['authorizationId'],
                                     request_sha256=row['requestSha256'])

    def read_rows(self):
        with self.db.transaction() as conn:
            return {table: conn.execute('SELECT * FROM ' + table + ' ORDER BY id').fetchall()
                    for table in ('learning_budget_authorizations', 'learning_budget_reservations', 'learning_budget_events')}

    def install_terminal_events(self):
        with self.db.transaction() as conn:
            rows = conn.execute("SELECT * FROM learning_budget_reservations WHERE state='unknown' ORDER BY id").fetchall()
            claims = [{'reservationId': row['id'], 'reservationSnapshotSha256': digest(row),
                'authorizationId': row['authorization_id'],
                'authorizationSnapshotSha256': digest(self.service.repository.authorization(conn, row['authorization_id'])),
                'requestIdentitySha256': row['request_identity_sha256'], 'dispatchedAt': row['dispatched_at']}
                for row in rows]
            plan = {'schemaVersion': 'mira.learning.transport-terminal-plan.v1',
                'confirmationKind': 'managed_deployment_processes_exited', 'scope': 'local_transport_concurrency_only',
                'sourceAuditSha256': 'cebd0b3f1d491452525e4707ff0afccd858955a38af858693b1e370d89d59267',
                'stopEvidenceSha256': digest('fixture-stop'), 'reservationClaims': claims,
                'localTransportEndedAt': self.now - 1, 'approvalReference': 'fixture-existing-approval'}
            for claim in claims:
                self.service.repository.event(conn, claim['reservationId'], 'transport_terminal_confirmed',
                                              receipt(plan, claim['reservationId']), self.now)
        patch.object(tail, 'TRANSPORT_PLAN_SHA', digest(plan)).start()

    def make_sources(self):
        scenes = [{'id': identity, 'type': 'slide', 'title': identity, 'order': index,
            'content': {}, 'actions': []} for index, identity in enumerate(tail.IDENTITY['sceneIds'])]
        for i in range(36):
            scenes[i % 8]['actions'].append({'id': 'speech-' + str(i), 'type': 'speech', 'text': '原稿旁白' + str(i)})
        for i, scene in enumerate(scenes[5:7]):
            scene['type'] = 'quiz'
            scene['content'] = {'questions': [{'id': q, 'question': q, 'answer': []}
                for q in tail.IDENTITY['lockedQuestionIds'][i*2:i*2+2]]}
        source = {'stage': {'id': tail.IDENTITY['stageId'], 'name': '原稿'}, 'scenes': scenes}
        prepared = quality_snapshot(source)
        formal_input = {'runtimeRequestId': tail.IDENTITY['runtimeRequestId'], 'paidBudget': tail._binding(self.parent)}
        job = {'id': tail.IDENTITY['jobId'], 'status': 'failed', 'error': 'original-timeout', 'completedAt': 'original-time',
            'runtimeRequestId': tail.IDENTITY['runtimeRequestId'], 'formalInput': formal_input,
            'formalInputSha256': quality_sha(formal_input)}
        self.paths = {}
        for key, value in [('source_job', job), ('source_snapshot', source), ('prepared_snapshot', prepared)]:
            path = self.path / (key + '.json')
            path.write_text(canonical(value))
            self.paths[key + '_path'] = path
        patch.dict(tail.IDENTITY, {'sourceJobSha256': hashlib.sha256(self.paths['source_job_path'].read_bytes()).hexdigest(),
            'formalInputSha256': quality_sha(formal_input), 'sourceSnapshotSha256': quality_sha(quality_snapshot(source)),
            'repairSnapshotSha256': quality_sha(prepared)}).start()
        live_job = self.path / 'openmaic-runtime/.runtime/OpenMAIC/data/classroom-jobs' / (tail.IDENTITY['jobId'] + '.json')
        live_job.parent.mkdir(parents=True)
        live_job.write_bytes(self.paths['source_job_path'].read_bytes())

    def plan(self):
        return tail.plan_tail_authorization(budget=self.service, **self.paths,
            starts_at=self.now, expires_at=self.now + 3600000)

    def apply(self, document=None):
        document = document or self.plan()
        return tail.apply_tail_authorization(budget=self.service, plan=document['plan'],
            expected_plan_sha=document['planSha256'], archives=self.path / 'archives')

    def test_plan_read_only_apply_exact_scope_prices_context_and_historical_hashes(self):
        with self.db.transaction() as conn:
            control = dict(self.service.repository.control(conn))
        document = self.plan()
        self.assertEqual(self.read_rows(), self.before)
        with self.db.transaction() as conn:
            self.assertEqual(self.service.repository.control(conn), control)
        applied = self.apply(document)
        self.assertTrue(applied['applied'])
        after = self.read_rows()
        self.assertEqual(after['learning_budget_reservations'], self.before['learning_budget_reservations'])
        self.assertEqual([row for row in after['learning_budget_authorizations'] if row['id'] != tail.authorization_id()],
                         self.before['learning_budget_authorizations'])
        self.assertEqual(len(after['learning_budget_events']), len(self.before['learning_budget_events']) + 1)
        self.assertEqual(len(list((self.path / 'archives').glob('*.json'))), 1)
        context = self.service.authorization_context(authorization_id=tail.authorization_id())
        self.assertEqual(context['completionTailGrant'], document['sidecar'])
        self.assertEqual(set(context['prices']), set(tail.PRICE_CALLS))
        self.assertEqual(document['sidecar']['scope'], self.scope)
        self.assertFalse(context['aggregateLimitsEnabled'])
        events = [e for e in after['learning_budget_events'] if e['event_type'] == 'transport_terminal_confirmed']
        self.assertEqual(validated_terminal_ids(after['learning_budget_reservations'], events,
                                                after['learning_budget_authorizations']), set(self.unknowns))

    def test_apply_is_single_idempotent_and_concurrent(self):
        document = self.plan()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.apply(document), range(2)))
        self.assertEqual(sum(result['applied'] for result in results), 1)
        self.assertTrue(self.apply(document)['reused'])
        with self.assertRaisesRegex(ValueError, 'already'):
            self.plan()
        self.assertEqual(len(self.read_rows()['learning_budget_authorizations']), 3)

    def test_wrong_sha_files_catalog_and_history_abort_without_new_grant(self):
        document = self.plan()
        with self.assertRaises(ValueError):
            tail.apply_tail_authorization(budget=self.service, plan=document['plan'],
                expected_plan_sha='0'*64, archives=self.path / 'archive')
        self.paths['source_job_path'].write_text('{}')
        with self.assertRaises(ValueError):
            self.apply(document)
        self.assertEqual(self.read_rows(), self.before)

    def test_plan_mutations_and_policy_enable_production_are_rejected(self):
        document = self.plan()
        for mutation in ('identity', 'prices', 'limits', 'expiry', 'mode', 'fake-call-quota'):
            changed = deepcopy(document)
            plan = changed['plan']
            if mutation == 'identity': plan['identity']['jobId'] = 'another-job'
            if mutation == 'prices': plan['priceScope']['prices']['deepseek-pro-peak'] = self.prices['deepseek-pro-peak']
            if mutation == 'limits': plan['limits']['calls'] += 1
            if mutation == 'expiry': plan['expiresAt'] += 3*3600000
            if mutation == 'mode': plan['allowedMode'] = 'repair'
            if mutation == 'fake-call-quota': plan['newSearches'] = True
            changed['planSha256'] = digest(plan)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.apply(changed)
        self.assertEqual(self.read_rows(), self.before)
        self.service.policy.raw['authorizationTemplates']['production'] = {'enabled': True}
        with self.assertRaises(ValueError): self.plan()

    def test_parent_runtime_or_terminal_event_change_before_apply_rejected(self):
        document = self.plan()
        for table, column, value, where in (
            ('learning_budget_authorizations', 'expires_at', tail.PARENT_EXPIRES + 1, ('id', self.parent)),
            ('learning_openmaic_runtime_classrooms', 'status', 'ready', ('id', tail.IDENTITY['runtimeId'])),
            ('learning_budget_events', 'evidence_json', '{}', ('event_type', 'transport_terminal_confirmed'))):
            with self.db.transaction() as conn:
                rows = conn.execute('SELECT * FROM ' + table + ' WHERE ' + where[0] + '=?', (where[1],)).fetchall()
                conn.execute('UPDATE ' + table + ' SET ' + column + '=? WHERE ' + where[0] + '=?', (value, where[1]))
            with self.assertRaises(ValueError): self.apply(document)
            with self.db.transaction() as conn:
                for row in rows:
                    conn.execute('UPDATE ' + table + ' SET ' + column + '=? WHERE id=?', (row[column], row['id']))
        self.assertEqual(self.read_rows(), self.before)

    def test_missing_or_changed_db_proof_never_becomes_observation_authority(self):
        self.apply()
        with self.db.transaction() as conn:
            event = conn.execute('SELECT * FROM learning_budget_events WHERE event_type=?', (tail.EVENT,)).fetchone()
            conn.execute('DELETE FROM learning_budget_events WHERE event_type=?', (tail.EVENT,))
        with self.assertRaises(ValueError):
            self.service.authorization_context(authorization_id=tail.authorization_id())
        with self.assertRaises(ValueError): self.reserve('missing-proof')
        with self.db.transaction() as conn:
            self.service.repository.event(conn, event['reservation_id'], tail.EVENT, json.loads(event['evidence_json']), event['created_at'])
            conn.execute('UPDATE learning_budget_authorizations SET expires_at=expires_at+1 WHERE id=?', (self.parent,))
        with self.assertRaises(ValueError): self.reserve('changed-parent')

    def test_completion_lane_only_unknown_idempotency_and_no_new_cumulative_quota(self):
        self.apply()
        # Parent observation limits.calls is one. Two real scoped reservations
        # remain valid; 74 is an estimate, never a newly introduced counter gate.
        one = self.reserve('one')
        self.assertTrue(self.dispatch(one)['dispatchAllowed'])
        self.service.settle(reservation_id=one['reservationId'], authorization_id=tail.authorization_id(),
            actual_units={'calls': 1, 'input_tokens': 20, 'output_tokens': 10},
            provider_request_id='fixture-real-receipt', evidence_sha256=digest('actual'))
        two = self.reserve('two')
        self.assertTrue(self.dispatch(two)['dispatchAllowed'])
        self.service.unknown(reservation_id=two['reservationId'], authorization_id=tail.authorization_id(), reason_code='connection_lost')
        self.assertEqual(self.reserve('two')['state'], 'unknown')
        self.assertFalse(self.dispatch(two)['dispatchAllowed'])
        for namespace in (tail.IDENTITY['sessionId'], tail.IDENTITY['sessionId'] + ':repair', 'other:completion'):
            with self.subTest(namespace=namespace), self.assertRaises(ValueError):
                self.reserve('wrong', namespace=namespace)
        with self.assertRaises(ValueError): self.reserve('pro', price_key='deepseek-pro-peak')
        self.assertIsNone(self.service.issue_catalog_production_authorization(build_item_id=tail.IDENTITY['buildItemId']))
        with self.assertRaises(ApiError) as expired:
            self.service.authorization_context(authorization_id=self.parent)
        self.assertEqual(expired.exception.code, 'learning_budget_authorization_expired')

    def test_live_or_new_unknown_transport_cannot_be_hidden_by_old_receipts(self):
        document = self.plan()
        with self.db.transaction() as conn:
            conn.execute("UPDATE learning_budget_reservations SET state='dispatched' WHERE id=?", (self.unknowns[0],))
        with self.assertRaises(ValueError): self.apply(document)

    def renewal_fixture(self):
        original = self.apply()
        row = self.reserve('renewal-known-unknown')
        self.dispatch(row)
        self.service.unknown(reservation_id=row['reservationId'], authorization_id=tail.authorization_id(),
                             reason_code='provider_result_unknown')
        plan = tail.plan_tail_renewal(budget=self.service,
            expires_at=self.now + 2 * 3600000, approval_reference='current-user-message',
            approval_text='继续完成这一个课堂并保留原计费记录')
        return original, row, plan

    def apply_renewal(self, document):
        return tail.apply_tail_renewal(budget=self.service, plan=document['plan'],
            expected_plan_sha=document['planSha256'], archives=self.path / 'archives')

    def test_renewal_changes_only_expiry_and_appends_one_audit_preserving_unknown(self):
        original, unknown, document = self.renewal_fixture()
        before = self.read_rows()
        self.assertEqual(document['sidecar'], {**original['sidecar'], 'expiresAt': self.now + 2 * 3600000})
        result = self.apply_renewal(document)
        self.assertTrue(result['applied'])
        after = self.read_rows()
        self.assertEqual(after['learning_budget_reservations'], before['learning_budget_reservations'])
        for old, current in zip(before['learning_budget_authorizations'], after['learning_budget_authorizations']):
            self.assertEqual(current, {**old, 'expires_at': document['sidecar']['expiresAt']}
                             if old['id'] == tail.authorization_id() else old)
        self.assertEqual(after['learning_budget_events'][:-1], before['learning_budget_events'])
        self.assertEqual(after['learning_budget_events'][-1]['event_type'], tail.RENEWAL_EVENT)
        self.assertTrue(self.apply_renewal(document)['reused'])
        self.assertEqual(self.read_rows(), after)
        self.now += 3600001  # The initial tail expired, the audited extension did not.
        context = self.service.authorization_context(authorization_id=tail.authorization_id())
        self.assertEqual(context['completionTailGrant'], document['sidecar'])
        self.assertFalse(self.dispatch(unknown)['dispatchAllowed'])
        self.reserve('new-audio', price_key='qwen-tts-beijing', max_units={'calls': 1, 'characters': 30})
        with self.assertRaises(ApiError):
            self.service.authorization_context(authorization_id=self.parent)

    def test_renewal_plan_is_read_only_and_apply_is_concurrent_idempotent(self):
        _, _, document = self.renewal_fixture()
        before = self.read_rows()
        with self.db.transaction() as conn:
            revision = self.service.repository.control(conn)['revision']
        tail.plan_tail_renewal(budget=self.service, expires_at=self.now + 2 * 3600000,
                              approval_reference='same', approval_text='继续完成')
        self.assertEqual(self.read_rows(), before)
        with self.db.transaction() as conn:
            self.assertEqual(self.service.repository.control(conn)['revision'], revision)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.apply_renewal(document), range(2)))
        self.assertEqual(sum(result['applied'] for result in results), 1)

    def test_renewal_rejects_scope_price_expiry_and_live_ledger_changes(self):
        _, _, document = self.renewal_fixture()
        before = self.read_rows()
        for key, value in [('scope', {**tail.RENEWAL_SCOPE, 'newQualityReviews': 1}),
                           ('expiresAt', self.now + 3 * 3600000), ('approvalText', ''),
                           ('originalGrantSha256', '0' * 64), ('previousExpiresAt', self.now)]:
            changed = deepcopy(document)
            changed['plan'][key] = value
            changed['planSha256'] = digest(changed['plan'])
            with self.subTest(key=key), self.assertRaises(ValueError): self.apply_renewal(changed)
        self.assertEqual(self.read_rows(), before)
        pending = self.reserve('new-active')
        with self.assertRaises(ValueError): self.apply_renewal(document)
        with self.assertRaises(ValueError):
            tail.plan_tail_renewal(budget=self.service, expires_at=self.now + 2 * 3600000,
                                  approval_reference='same', approval_text='继续完成')

    def test_renewal_forged_expiry_or_missing_audit_and_old_unknown_change_are_rejected(self):
        _, unknown, document = self.renewal_fixture()
        with self.db.transaction() as conn:
            conn.execute('UPDATE learning_budget_authorizations SET expires_at=expires_at+1 WHERE id=?', (tail.authorization_id(),))
        with self.assertRaises(ValueError):
            self.service.authorization_context(authorization_id=tail.authorization_id())
        with self.db.transaction() as conn:
            conn.execute('UPDATE learning_budget_authorizations SET expires_at=expires_at-1 WHERE id=?', (tail.authorization_id(),))
        self.apply_renewal(document)
        with self.db.transaction() as conn:
            conn.execute("UPDATE learning_budget_reservations SET state='released' WHERE id=?", (unknown['reservationId'],))
        with self.assertRaises(ValueError):
            self.service.authorization_context(authorization_id=tail.authorization_id())
        with self.db.transaction() as conn:
            conn.execute("UPDATE learning_budget_reservations SET state='unknown' WHERE id=?", (unknown['reservationId'],))
            conn.execute('DELETE FROM learning_budget_events WHERE event_type=?', (tail.RENEWAL_EVENT,))
        with self.assertRaises(ValueError):
            self.service.authorization_context(authorization_id=tail.authorization_id())


if __name__ == '__main__':
    unittest.main()
