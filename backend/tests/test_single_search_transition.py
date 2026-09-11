from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from content.learning_budget_policy import LearningBudgetPolicy, canonical, digest
from content.single_course_budget import build_single_course_policy
from core.errors import ApiError
from scripts.generate_one_library_course import write_policy
from services.learning_budget_service import LearningBudgetService
from services.learning_single_search_transition import transition_single_search, BRAVE_KEY, BAIDU_KEY, JOB
from tests.test_learning_budget import IsolatedDatabase


class SingleSearchTransitionTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.database = IsolatedDatabase(self.folder / 'budget.sqlite')
        self.now = int(datetime(2026, 9, 10, 14, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp() * 1000)
        policy, self.identity = build_single_course_policy(grade='primary_6', subject='math',
            skill='fraction_ratio_percentage', ordinal=1, now=self.now - 3600000)
        self.scope_patch = patch.object(LearningBudgetService, '_catalog_production_scope',
            return_value=(self.identity['scope'], True))
        self.scope_patch.start(); self.addCleanup(self.scope_patch.stop)
        self.service = LearningBudgetService(self.database, policy=policy, clock=lambda: self.now)
        self.key = digest({'schema': 'mira.catalog-paid-budget.v1', 'scope': self.identity['scope']})
        self.service.issue_course_authorization(authorization_id=self.key, scope=self.identity['scope'])
        reservation = self.service.reserve(authorization_id=self.key, dispatch_id='test-brave-1',
            request_sha256=digest('request'), price_key=BRAVE_KEY, max_units={'calls': 1, 'search_requests': 1})
        self.service.dispatch(reservation_id=reservation['reservationId'], authorization_id=self.key, request_sha256=digest('request'))
        self.service.settle(reservation_id=reservation['reservationId'], authorization_id=self.key,
            actual_units={'calls': 1, 'search_requests': 1}, provider_request_id='fixture-brave', evidence_sha256=digest('receipt'))
        with self.database.transaction() as conn:
            conn.executescript('CREATE TABLE learning_catalog_build_items(id TEXT, content_phase TEXT, content_gate_status TEXT);'
                'CREATE TABLE learning_openmaic_runtime_classrooms(id TEXT, candidate_build_item_id TEXT, upstream_job_id TEXT, status TEXT);'
                'CREATE TABLE learning_course_provider_dispatches(id TEXT, build_item_id TEXT);')
            conn.execute('INSERT INTO learning_catalog_build_items VALUES (?, ?, ?)', (self.identity['buildItemId'], 'course_ready', 'passed'))
            conn.execute('INSERT INTO learning_openmaic_runtime_classrooms VALUES (?, ?, ?, ?)', ('runtime',self.identity['buildItemId'],JOB,'failed'))
            for i in range(13):
                conn.execute('INSERT INTO learning_course_provider_dispatches VALUES (?, ?)', (str(i),self.identity['buildItemId']))
            self.before = [dict(row) for row in conn.execute('SELECT * FROM learning_budget_reservations ORDER BY id').fetchall()]
        raw = deepcopy(policy.raw); raw['enabled'] = False
        self.path = write_policy(self.folder / 'policy.json', LearningBudgetPolicy(raw), create_only=True)
        self.probes = [{'requestId': 'fixture-a', 'estimatedMoneyMicros': 36000},
                       {'requestId': 'fixture-b', 'estimatedMoneyMicros': 36000}]

    def transition(self, **options):
        return transition_single_search(database=self.database, policy_path=self.path, identity=self.identity,
            now=self.now, write_policy=write_policy, archives=self.folder / 'audit', probes=self.probes, **options)

    def test_same_grant_keeps_ledger_and_history_prices_but_only_baidu_can_dispatch(self):
        expiry = self.now + 3 * 3600000
        plan = self.transition(continuation_expires_at=expiry)
        result = self.transition(apply=True, expected_sha=plan['transitionSha256'], continuation_expires_at=expiry)
        self.assertTrue(result['applied']); self.assertTrue(result['windowExtended'])
        self.assertEqual(result['authorizationId'], self.key)
        current = LearningBudgetPolicy.load(self.path)
        self.assertEqual(current.raw['limits']['global']['day']['money_micros'], 9928000)
        self.assertEqual(current.raw['limits']['purposes']['production']['day']['money_micros'], 7928000)
        active = LearningBudgetService(self.database, policy=current, clock=lambda: self.now)
        with self.database.transaction() as conn:
            self.assertEqual([dict(r) for r in conn.execute('SELECT * FROM learning_budget_reservations ORDER BY id')], self.before)
            row = active.repository.authorization(conn,self.key)
            self.assertEqual(row['expires_at'],expiry)
            self.assertEqual(json.loads(row['limits_json'])['money_micros'],7928000)
            self.assertIn(BRAVE_KEY,json.loads(row['price_keys_json'])['prices'])
        self.assertTrue(active.issue_course_authorization(authorization_id=self.key,scope=self.identity['scope']))
        self.assertNotIn(BRAVE_KEY, active.authorization_context(authorization_id=self.key)['prices'])
        with self.assertRaises(ApiError) as error:
            active.reserve(authorization_id=self.key,dispatch_id='old-brave-denied',request_sha256=digest('other'),
                price_key=BRAVE_KEY,max_units={'calls':1,'search_requests':1})
        self.assertEqual(error.exception.code,'learning_budget_price_not_authorized')
        self.assertTrue(self.transition(apply=True,expected_sha=plan['transitionSha256'],continuation_expires_at=expiry)['applied'])
        reservation = active.reserve(authorization_id=self.key,dispatch_id='baidu-fixture',request_sha256=digest('baidu'),
            price_key=BAIDU_KEY,max_units={'calls':1,'search_requests':1})
        self.assertEqual(reservation['maxUnits']['money_micros'],36000)

    def test_wrong_sha_or_changed_ledger_and_cross_day_extension_do_not_activate(self):
        plan = self.transition()
        with self.assertRaises(ValueError):
            self.transition(apply=True,expected_sha='0'*64)
        with self.assertRaises(ValueError):
            self.transition(continuation_expires_at=self.now+24*3600000)
        self.service.reserve(authorization_id=self.key,dispatch_id='pending-fixture',request_sha256=digest('pending'),
            price_key=BRAVE_KEY,max_units={'calls':1,'search_requests':1})
        with self.assertRaisesRegex(ValueError,'unknown or in-flight'):
            self.transition(apply=True,expected_sha=plan['transitionSha256'])
        self.assertFalse(LearningBudgetPolicy.load(self.path).raw['enabled'])

    def test_committed_grant_and_paused_file_resume_by_exact_audit_without_second_transition(self):
        plan = self.transition()
        def failed_write(*_args, **_kwargs): raise OSError('fixture disk failure')
        with self.assertRaises(OSError):
            transition_single_search(database=self.database,policy_path=self.path,identity=self.identity,
                now=self.now,apply=True,expected_sha=plan['transitionSha256'],write_policy=failed_write,
                archives=self.folder/'audit',probes=self.probes)
        self.assertFalse(LearningBudgetPolicy.load(self.path).raw['enabled'])
        self.assertTrue(self.transition(apply=True,expected_sha=plan['transitionSha256'])['applied'])
        with self.database.transaction() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) n FROM learning_budget_events WHERE event_type='search_provider_transition'").fetchone()['n'],1)
