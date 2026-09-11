"""Teaching expiry: isolated SQLite, no provider or business DB calls."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from content.learning_budget_policy import LearningBudgetPolicy, UNITS, digest
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService
from services.learning_paid_authority import teaching_budget_bindings, teaching_budget_scope, scope_digest
from tests.test_learning_budget import IsolatedDatabase, test_policy


class TeachingAuthorizationTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = IsolatedDatabase(Path(directory.name) / 'budget.db')
        self.now = 1789055940000
        self.raw = test_policy()
        self.raw.update(aggregateLimitsEnabled=False, renewTeachingAuthorizations=True)
        self.raw['authorizationTemplates']['required_teaching'] = {
            'maxUnits': dict.fromkeys(UNITS, 1000000), 'priceKeys': ['fake-text-v1'], 'ttlMs': 60000}
        self.row = {'course_id': 'course-six', 'course_version': 'v4', 'child_id': 'child-six',
            'learning_session_id': 'session-six', 'learning_session_status': 'in_progress',
            'learning_session_completed_at': None}
        self.manifest = {'generationContract': {'professionalCreationPolicy': {'interactionDesignPolicy': {}},
            'teachingBrief': {'course': {'gradeCode': 'primary_6', 'subject': 'math'}},
            'targetFingerprint': 'target-v4'}, 'formalEvidence': {'discussionActionCount': 3}}
        self.scope = teaching_budget_scope(self.row, self.manifest, 'required_teaching')
        self.identity = scope_digest(self.scope)
        self.service = self.make_service()

    def make_service(self, raw=None):
        return LearningBudgetService(self.db, policy=LearningBudgetPolicy(raw or self.raw), clock=lambda: self.now)

    def bind(self, admit=True, row=None):
        return teaching_budget_bindings(self.service, row or self.row, self.manifest, admit=admit)

    def snapshot(self):
        with self.db.transaction() as conn:
            return (self.service.repository.authorization(conn, self.identity),
                conn.execute('SELECT * FROM learning_budget_reservations ORDER BY id').fetchall(),
                conn.execute('SELECT * FROM learning_budget_events ORDER BY id').fetchall())

    def assert_code(self, code, fn):
        with self.assertRaises(ApiError) as caught:
            fn()
        self.assertEqual(caught.exception.code, 'learning_budget_' + code)

    def test_cross_day_reentry_keeps_grant_cost_unknown_hold_and_one_audit(self):
        binding = self.bind()['required_teaching']
        for name in ('known', 'unknown'):
            reservation = self.service.reserve(authorization_id=self.identity, dispatch_id=name,
                request_sha256=digest(name), price_key='fake-text-v1',
                max_units={'calls': 1, 'input_tokens': 100, 'output_tokens': 50})
            self.service.dispatch(reservation_id=reservation['reservationId'], authorization_id=self.identity,
                                  request_sha256=digest(name))
            if name == 'known':
                self.service.settle(reservation_id=reservation['reservationId'], authorization_id=self.identity,
                    actual_units={'calls': 1, 'input_tokens': 10, 'output_tokens': 5},
                    provider_request_id='fixture-id', evidence_sha256=digest('fixture-result'))
            else:
                self.service.unknown(reservation_id=reservation['reservationId'], authorization_id=self.identity,
                                     reason_code='provider_outcome_unknown')
        before, ledger, events = self.snapshot()
        self.now += 2 * 86400000
        self.assert_code('authorization_expired', lambda: self.service.authorization_context(authorization_id=self.identity))
        self.assertEqual(self.bind(admit=False)['required_teaching'], binding)
        after, ledger_after, events_after = self.snapshot()
        self.assertEqual({**before, 'expires_at': self.now + 60000}, after)
        self.assertEqual(ledger_after, ledger)
        self.assertEqual(events_after[:-1], events)
        audit = json.loads(events_after[-1]['evidence_json'])
        self.assertEqual(audit['renewalSha256'], digest(audit['audit']))
        self.assertEqual(audit['audit']['previousExpiresAt'], before['expires_at'])
        self.assertFalse(audit['audit']['providerDispatch'])
        self.assertEqual(self.service.authorization_context(authorization_id=self.identity)['unsettledReservationCount'], 1)
        for _ in range(3):
            self.assertEqual(self.bind(admit=False)['required_teaching'], binding)
        self.assertEqual(self.snapshot(), (after, ledger_after, events_after))

    def test_validate_never_mints_and_unused_expiry_is_only_released_audit(self):
        self.assertIsNone(self.bind(admit=False)['required_teaching'])
        self.assertIsNone(self.snapshot()[0])
        self.now += 86400000
        binding = self.bind()['required_teaching']
        self.assertEqual(self.snapshot()[1:], ([], []))
        self.now += 60001
        self.assertEqual(self.bind()['required_teaching'], binding)
        _, ledger, events = self.snapshot()
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger[0]['state'], 'released')
        self.assertEqual(json.loads(ledger[0]['max_units_json']), dict.fromkeys(UNITS, 0))
        self.assertIsNone(ledger[0]['dispatched_at'])
        self.assertIsNone(ledger[0]['provider_request_id'])
        self.assertEqual(events[0]['event_type'], 'teaching_authorization_renewed')
        self.assertIsNone(self.service.authorization_context(authorization_id=self.identity)['latestProviderDispatchAt'])

    def test_revoked_completed_or_changed_scope_never_reopens(self):
        self.bind()
        self.now += 60001
        before = self.snapshot()
        for field in ('courseId', 'courseVersion', 'userId', 'sessionId', 'approvalReference'):
            scope = {**self.scope, field: self.scope[field] + '-different'}
            self.assert_code('authorization_conflict', lambda: self.service.issue_course_authorization(
                authorization_id=self.identity, scope=scope, existing_only=True))
        for changed in ('price', 'limits'):
            raw = deepcopy(self.raw)
            if changed == 'price':
                raw['prices']['fake-text-v1']['version'] = 'changed'
            else:
                raw['authorizationTemplates']['required_teaching']['maxUnits']['calls'] += 1
            service = self.make_service(raw)
            self.assert_code('authorization_conflict', lambda: service.issue_course_authorization(
                authorization_id=self.identity, scope=self.scope, existing_only=True))
        self.assertEqual(self.snapshot(), before)
        complete = {**self.row, 'learning_session_status': 'completed', 'learning_session_completed_at': self.now}
        self.assert_code('learning_session_inactive', lambda: self.bind(row=complete))
        self.assertIsNone(self.bind(admit=False, row=complete)['required_teaching'])
        self.assertEqual(self.snapshot(), before)
        self.service.close_authorization(authorization_id=self.identity)
        before = self.snapshot()
        self.assert_code('authorization_expired', self.bind)
        self.assertIsNone(self.bind(admit=False)['required_teaching'])
        self.assertEqual(self.snapshot(), before)

    def test_legacy_fixed_window_and_other_purposes_never_renew(self):
        for purpose in ('production', 'optional_interaction'):
            raw = deepcopy(self.raw)
            raw['authorizationTemplates'][purpose] = raw['authorizationTemplates']['required_teaching']
            service = self.make_service(raw)
            scope = {**self.scope, 'purpose': purpose}
            if purpose == 'production':
                scope.update(userId=None, sessionId=None, productionJobId='job-one')
            identity = digest(scope)
            service.issue_course_authorization(authorization_id=identity, scope=scope)
            self.now += 60001
            self.assert_code('authorization_expired', lambda: service.issue_course_authorization(
                authorization_id=identity, scope=scope))
        raw = deepcopy(self.raw)
        raw.pop('renewTeachingAuthorizations')
        service = self.make_service(raw)
        service.issue_course_authorization(authorization_id=self.identity, scope=self.scope)
        self.now += 60001
        self.assert_code('authorization_expired', lambda: service.issue_course_authorization(
            authorization_id=self.identity, scope=self.scope))
        raw['authorizationWindow'] = {'startsAt': self.now-60001, 'expiresAt': self.now-1, 'scopes': [self.scope]}
        service = self.make_service(raw)
        self.assert_code('authorization_window_closed', lambda: service.issue_course_authorization(
            authorization_id=self.identity, scope=self.scope))

    def test_policy_is_opt_in_and_fixed_window_is_incompatible(self):
        legacy = test_policy()
        parsed = LearningBudgetPolicy(legacy)
        self.assertFalse(parsed.renew_teaching_authorizations)
        self.assertEqual(parsed.sha256, digest(legacy))
        for value in (1, 'true', None):
            with self.assertRaises(ValueError):
                LearningBudgetPolicy({**legacy, 'renewTeachingAuthorizations': value})
        with self.assertRaises(ValueError):
            LearningBudgetPolicy({**self.raw, 'authorizationWindow': {
                'startsAt': self.now, 'expiresAt': self.now+60000, 'scopes': [self.scope]}})
        stable = LearningBudgetPolicy.load(Path(__file__).parents[1] / 'content/learning_classroom_policy.json')
        self.assertTrue(stable.renew_teaching_authorizations)
        self.assertIsNone(stable.raw['authorizationTemplates']['production'])
        self.assertNotIn('authorizationWindow', stable.raw)


if __name__ == '__main__':
    unittest.main()
