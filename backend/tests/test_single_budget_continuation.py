from copy import deepcopy
from datetime import datetime
import json
import unittest
from zoneinfo import ZoneInfo

from content.learning_budget_policy import LearningBudgetPolicy, digest
from scripts.generate_one_library_course import write_policy
from services.learning_budget_service import LearningBudgetService
from services.learning_single_budget_continuation import continue_single_budget, EVENT
from services.learning_single_search_transition import BRAVE_KEY, BAIDU_KEY
from tests.test_single_search_transition import SingleSearchTransitionTest


class SingleBudgetContinuationTests(unittest.TestCase):
    transition = SingleSearchTransitionTest.transition

    def setUp(self):
        SingleSearchTransitionTest.setUp(self)
        expiry = self.now + 3 * 3600000
        plan = self.transition(continuation_expires_at=expiry)
        self.transition(apply=True, expected_sha=plan['transitionSha256'], continuation_expires_at=expiry)
        raw = deepcopy(LearningBudgetPolicy.load(self.path).raw)
        raw['aggregateLimitsEnabled'] = False
        self.active = LearningBudgetService(self.database, policy=LearningBudgetPolicy(raw), clock=lambda: self.now)
        raw['enabled'] = False
        write_policy(self.path, LearningBudgetPolicy(raw))
        # SQLite TEXT does not enforce MySQL migration 076's VARCHAR(32).
        # Enforce that real column boundary in this focused compatibility fixture.
        with self.database.transaction() as conn:
            conn.executescript("CREATE TRIGGER budget_event_type_length BEFORE INSERT ON learning_budget_events "
                "WHEN LENGTH(NEW.event_type) > 32 BEGIN SELECT RAISE(ABORT, 'event_type exceeds VARCHAR(32)'); END;")
        self.expiry = int(datetime(2026, 9, 10, 20, 30, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp() * 1000)

    def continue_budget(self, **options):
        return continue_single_budget(database=self.database, policy_path=self.path, identity=self.identity,
            now=self.now, expires_at=self.expiry, write_policy=write_policy, archives=self.folder/'audit', **options)

    def test_continuation_keeps_original_grant_and_all_charges_and_search_audit(self):
        with self.database.transaction() as conn:
            original = dict(self.active.repository.authorization(conn, self.key))
        plan = self.continue_budget()
        self.assertFalse(LearningBudgetPolicy.load(self.path).raw['enabled'])
        result = self.continue_budget(apply=True, expected_sha=plan['continuationSha256'])
        self.assertEqual(result['authorizationIds'], [self.key])
        self.assertEqual(result['expiresAt'], self.expiry)
        self.assertFalse(result['newAuthorizationCreated'])
        with self.database.transaction() as conn:
            self.assertEqual(dict(self.active.repository.authorization(conn, self.key)), {**original, 'expires_at': self.expiry})
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM learning_budget_authorizations').fetchone()['n'], 1)
            self.assertEqual([dict(r) for r in conn.execute('SELECT * FROM learning_budget_reservations ORDER BY id')], self.before)
        resumed = LearningBudgetService(self.database, policy=LearningBudgetPolicy.load(self.path), clock=lambda:self.now)
        prices = resumed.authorization_context(authorization_id=self.key)['prices']
        self.assertIn(BAIDU_KEY, prices)
        self.assertNotIn(BRAVE_KEY, prices)
        self.assertTrue(self.continue_budget(apply=True, expected_sha=plan['continuationSha256'])['applied'])
        with self.database.transaction() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) n FROM learning_budget_events WHERE event_type=?', (EVENT,)).fetchone()['n'], 1)

    def test_changed_ledger_rejects_reviewed_plan_and_preserves_paused_original(self):
        plan = self.continue_budget()
        self.active.reserve(authorization_id=self.key, dispatch_id='continuation-unresolved',
            request_sha256=digest('continuation-unresolved'), price_key=BAIDU_KEY,
            max_units={'calls':1, 'search_requests':1})
        with self.assertRaisesRegex(ValueError, 'pending or unknown'):
            self.continue_budget(apply=True, expected_sha=plan['continuationSha256'])
        self.assertFalse(LearningBudgetPolicy.load(self.path).raw['enabled'])
        with self.database.transaction() as conn:
            self.assertNotEqual(self.active.repository.authorization(conn, self.key)['expires_at'], self.expiry)
