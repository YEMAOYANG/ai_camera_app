from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from core.errors import ApiError
from routes.api.v1.reports import reports_bp
from services.learning_coaching_service import save_coaching
from services.profile_service import ProfileService
import test_report_learning_summary as report_fixture
from test_report_learning_summary import at


class CoachingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = report_fixture.ReportLearningTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.fixture.insert(self.fixture.state(support=True))
        self.clock = patch('services.learning_coaching_service.now_ms', return_value=at('2026-09-29'))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def save(self, **changes):
        data = {'recordDate': '2026-09-29', 'minutes': 2, 'usualMinutes': 10,
                'reason': 'understanding', 'revision': 0, **changes}
        with self.db.transaction():
            return save_coaching(self.db, family_id='family', user_id='parent', session_id='session', data=data)

    def test_missing_is_unknown_zero_is_explicit_and_duplicate_is_idempotent(self):
        self.assertEqual(self.fixture.report()['coachingSummary']['recordedSessions'], 0)
        self.assertIsNone(save_coaching(self.db, family_id='family', user_id='parent', session_id='session', record_date='2026-09-29')['coaching'])
        first = self.save(minutes=0, reason='none')
        self.assertEqual(self.save(minutes=0, reason='none'), first)
        summary = self.fixture.report()['coachingSummary']
        self.assertEqual((summary['recordedSessions'], summary['totalMinutes'], summary['differenceMinutes']), (1, 0, 10))

    def test_conflict_does_not_overwrite_and_negative_difference_is_preserved(self):
        self.save()
        with self.assertRaises(ApiError) as error:
            self.save(minutes=15)
        self.assertEqual(error.exception.code, 'coaching_conflict')
        self.save(minutes=15, revision=1)
        self.assertEqual(self.fixture.report()['coachingSummary']['differenceMinutes'], -5)
        self.assertEqual(self.fixture.report()['lessons'][0]['coaching']['revision'], 2)
        self.assertNotIn('recordedBy', self.fixture.report()['lessons'][0]['coaching'])

    def test_family_date_and_input_boundaries(self):
        with self.assertRaises(ApiError):
            save_coaching(self.db, family_id='stranger', user_id='parent', session_id='session', record_date='2026-09-29')
        for changes in ({'minutes': True}, {'minutes': -1}, {'minutes': 181}, {'usualMinutes': False},
                        {'reason': 'made_up'}, {'recordDate': '2026-09-30'}, {'recordDate': '2026-09-27'},
                        {'recordDate': '2026-9-29'}, {'minutes': 0}, {'reason': 'none'}):
            with self.subTest(changes=changes), self.assertRaises(ApiError):
                self.save(**changes)

    def test_coaching_does_not_rewrite_academic_evidence_or_day_snapshots(self):
        before = json.loads(self.db.execute('SELECT runtime_state_json FROM learning_sessions').fetchone()['runtime_state_json'])
        evidence = deepcopy(self.fixture.report()['lessons'][0]['assessmentEvidence'])
        self.save()
        after = json.loads(self.db.execute('SELECT runtime_state_json FROM learning_sessions').fetchone()['runtime_state_json'])
        self.assertEqual(before['textbookPlay'], after['textbookPlay'])
        self.assertEqual(self.fixture.report()['lessons'][0]['assessmentEvidence'], evidence)
        self.assertIn('parentSupport', self.fixture.report()['lessons'][0])

    def test_routes_enforce_server_capability_and_strip_actor(self):
        service = object.__new__(ProfileService)
        service.repository = SimpleNamespace(transaction=self.db.transaction)
        def auth(token):
            if token != 'test':
                raise ApiError('unauthorized', '请先登录', 401)
            return {'family': {'id': 'family'}, 'user': {'id': 'parent'}}
        service._auth_context = Mock(side_effect=auth)
        app = Flask(__name__)
        app.register_blueprint(reports_bp, url_prefix='/api/reports')
        client = app.test_client()
        url = '/api/reports/learning/session/coaching'
        body = {'recordDate': '2026-09-29', 'minutes': 2, 'usualMinutes': None, 'reason': 'company', 'revision': 0}
        with patch('routes.api.v1.reports.profile_service', return_value=service), patch.object(service, '_assert_capability') as permission:
            self.assertEqual(client.put(url, json=body).status_code, 401)
            response = client.put(url, json=body, headers={'Authorization': 'Bearer test'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(permission.call_args.args[-1], 'manage_tasks')
            self.assertNotIn('recordedBy', response.json['coaching'])
            response = client.get(url+'?recordDate=2026-09-29', headers={'Authorization': 'Bearer test'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(permission.call_args.args[-1], 'view_reports')
            permission.side_effect = ApiError('family_capability_required', '没有权限', 403)
            self.assertEqual(client.put(url, json=body, headers={'Authorization': 'Bearer test'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
