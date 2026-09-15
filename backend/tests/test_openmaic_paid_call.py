from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from content.learning_budget_policy import LearningBudgetPolicy, UNITS
from core.errors import ApiError
from services.learning_budget_service import LearningBudgetService
from services.learning_paid_authority import scope_digest, teaching_budget_scope
from services.openmaic_paid_call_service import OpenMaicPaidCallService, canonical_scripted_guidance
from tests.test_learning_budget import IsolatedDatabase, test_policy
from tests.test_openmaic_formal_interaction import interaction_fixture
from tests.test_openmaic_runtime_event_bridge import _Repository


class PaidCallContextTest(unittest.TestCase):
    def test_required_context_comes_from_frozen_action_and_excludes_independent_assessment(self):
        manifest, classroom = interaction_fixture(discussion=True)
        marker = {'sceneId': classroom['scenes'][0]['id'], 'actionId': 'discussion-guidance'}
        request = canonical_scripted_guidance(manifest, classroom, marker)
        self.assertEqual(request['messages'], [])
        self.assertEqual(request['config']['discussionTopic'], '十个一怎样合成一个十？')
        self.assertEqual(request['storeState']['currentSceneId'], marker['sceneId'])
        self.assertEqual(request['config']['agentIds'], [manifest['formalEvidence']['teacher']['agentId']])
        self.assertTrue(all(scene['type'] != 'quiz' for scene in request['storeState']['scenes']))
        self.assertEqual(request, canonical_scripted_guidance(manifest, classroom, marker))
        self.assertNotIn('model', request)

    def test_changed_script_cannot_borrow_required_teaching_allowance(self):
        manifest, classroom = interaction_fixture(discussion=True)
        marker = {'sceneId': classroom['scenes'][0]['id'], 'actionId': 'discussion-guidance'}
        changed = deepcopy(classroom)
        changed['scenes'][0]['actions'][-1]['topic'] = '替换成另一门课'
        with self.assertRaises(ValueError): canonical_scripted_guidance(manifest, changed, marker)
        for corrupt in ({**marker, 'prompt': 'replace'}, {**marker, 'actionId': 'forged'}):
            with self.assertRaises(ValueError): canonical_scripted_guidance(manifest, classroom, corrupt)


class PaidCallTeachingAuthorizationTest(unittest.TestCase):
    """Exercise runtime row aliases against the real ledger without provider calls."""

    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = IsolatedDatabase(Path(directory.name) / 'budget.db')
        self.now = 1789055940000
        raw = test_policy()
        raw.update(aggregateLimitsEnabled=False, renewTeachingAuthorizations=True)
        raw['authorizationTemplates']['required_teaching'] = {
            'maxUnits': dict.fromkeys(UNITS, 1000000),
            'priceKeys': ['fake-text-v1'], 'ttlMs': 60000}
        self.budget = LearningBudgetService(
            self.db, policy=LearningBudgetPolicy(raw), clock=lambda: self.now)

        self.manifest, self.classroom = interaction_fixture(discussion=True)
        self.row = deepcopy(_Repository().authority)
        self.manifest['formalEvidence']['runtimeEventAuthority'] = deepcopy(
            self.row['feature_manifest_json']['formalEvidence']['runtimeEventAuthority'])
        # These names are the SELECT aliases of get_runtime_authority, not the
        # learning_session_* names used by the authorization service.
        self.row.update(
            feature_manifest_json=self.manifest,
            upstream_classroom_id=self.classroom['stage']['id'],
            session_status='in_progress', session_completed_at=None,
            runtime_expires_at=self.now + 86400000)
        self.marker = {'sceneId': self.classroom['scenes'][0]['id'],
                       'actionId': 'discussion-guidance'}
        self.repository = Mock()
        self.repository.transaction.side_effect = lambda: nullcontext(object())
        self.repository.get_runtime_authority.side_effect = lambda *args, **kwargs: dict(self.row)
        self.repository.get_scene_identity.return_value = {'scene_id': self.marker['sceneId']}
        self.runtime = Mock()
        self.runtime.client.get_classroom.return_value = self.classroom
        self.runtime.client.read_teaching_conversation.return_value = None
        self.service = OpenMaicPaidCallService(
            repository=self.repository, runtime_service=self.runtime, budget_service=self.budget)
        scope_row = {**self.row, 'course_id': self.row['session_course_id'],
                     'course_version': self.row['session_course_version']}
        self.scope = teaching_budget_scope(scope_row, self.manifest, 'required_teaching')
        self.identity = scope_digest(self.scope)
        clock = patch('services.openmaic_paid_call_service.now_ms', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def authorize(self):
        return self.budget.issue_course_authorization(
            authorization_id=self.identity, scope=self.scope)

    def admit(self):
        return self.service.admit(
            runtime_session_id=self.row['runtime_session_id'],
            learning_session_id=self.row['learning_session_id'],
            upstream_classroom_id=self.row['upstream_classroom_id'],
            data={'path': '/api/chat/pi',
                  'request': {'messages': [], 'miraScriptedAction': self.marker}})

    def snapshot(self):
        with self.db.transaction() as conn:
            return tuple(conn.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                         for table in ('learning_budget_authorizations',
                                       'learning_budget_reservations', 'learning_budget_events'))

    def assert_rejected(self, code):
        with self.assertRaises(ApiError) as caught:
            self.admit()
        self.assertEqual(caught.exception.code, code)

    def test_active_runtime_aliases_reuse_existing_authorization_without_ledger_writes(self):
        binding = self.authorize()
        before = self.snapshot()
        self.assertNotIn('learning_session_status', self.row)
        self.assertNotIn('learning_session_completed_at', self.row)
        result = self.admit()
        self.assertEqual(result['paidBudget'], binding)
        self.assertEqual(result['purpose'], 'required_teaching')
        self.assertEqual(result['upstreamPath'], '/api/chat/pi')
        self.assertEqual(result['request']['miraTeachingContext']['authorizationId'], self.identity)
        self.assertEqual(result['request']['miraTeachingContext']['expectedRevision'], 0)
        self.assertEqual(result, self.admit())
        self.assertEqual(self.snapshot(), before)

    def test_expired_active_authorization_renews_same_identity_only_once(self):
        binding = self.authorize()
        self.now += 60001
        result = self.admit()
        self.assertEqual(result['paidBudget'], binding)
        authorizations, reservations, events = self.snapshot()
        self.assertEqual(len(authorizations), 1)
        self.assertEqual(authorizations[0]['id'], self.identity)
        self.assertEqual(authorizations[0]['expires_at'], self.now + 60000)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['event_type'], 'teaching_authorization_renewed')
        self.assertTrue(all(row['dispatched_at'] is None for row in reservations))
        before = self.snapshot()
        self.admit()
        self.assertEqual(self.snapshot(), before)

    def test_admission_does_not_mint_a_missing_authorization(self):
        before = self.snapshot()
        self.assert_rejected('learning_budget_unavailable')
        self.assertEqual(self.snapshot(), before)

    def test_completed_or_revoked_runtime_cannot_start_or_renew_teaching(self):
        self.authorize()
        self.now += 60001
        before = self.snapshot()
        for changes, code in (
            ({'session_status': 'completed', 'session_completed_at': self.now},
             'learning_session_completed'),
            ({'session_status': 'in_progress', 'session_completed_at': self.now},
             'learning_budget_unavailable'),
            ({'runtime_revoked_at': self.now}, 'runtime_event_session_not_found'),
        ):
            with self.subTest(changes=changes):
                original = dict(self.row)
                self.row.update(changes)
                self.assert_rejected(code)
                self.assertEqual(self.snapshot(), before)
                self.row = original

    def test_revoked_budget_cannot_be_recreated_or_renewed(self):
        self.authorize()
        self.budget.close_authorization(authorization_id=self.identity)
        self.now += 60001
        before = self.snapshot()
        self.assert_rejected('learning_budget_unavailable')
        self.assertEqual(self.snapshot(), before)
