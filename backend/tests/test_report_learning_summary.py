"""Family isolation and dated learning evidence, using real SQL in memory."""
from copy import deepcopy
from datetime import datetime
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from content import textbook_journey as journey
from routes.api.v1.reports import reports_bp
from services.profile_service import ProfileService
from services.report_learning_summary import ZONE, learning_for_period, save_journey_report_day
from test_textbook_activity import release_fixture
from test_textbook_journey_persistence import Connection


def at(day, hour=12):
    return int(datetime.fromisoformat(f'{day}T{hour:02d}:00:00').replace(tzinfo=ZONE).timestamp() * 1000)


class ReportLearningTests(unittest.TestCase):
    def setUp(self):
        self.db = Connection()
        schemas = {
            'children': 'id TEXT,family_id TEXT,nickname TEXT',
            'learning_courses': 'id TEXT,version TEXT,title TEXT,subject TEXT',
            'learning_sessions': 'id TEXT,family_id TEXT,child_id TEXT,course_id TEXT,course_version TEXT,task_id TEXT,started_at INTEGER,updated_at INTEGER,runtime_state_json TEXT',
            'learning_reports': 'id TEXT,family_id TEXT,child_id TEXT,session_id TEXT,course_id TEXT,course_version TEXT,task_id TEXT,learning_date TEXT,created_at INTEGER,independent_correct_count INTEGER,total_questions INTEGER,hint_count INTEGER,mastery_level TEXT,next_step TEXT',
            'tasks': 'id TEXT,family_id TEXT,scheduled_date TEXT,scheduled_start TEXT,created_at INTEGER',
            'camera_observation_events': 'id TEXT,family_id TEXT,child_id TEXT,device_id TEXT,task_id TEXT,observed_at INTEGER,scenario TEXT,source TEXT,confidence REAL',
            'behavior_signals': 'id TEXT,observation_event_id TEXT,family_id TEXT,child_id TEXT,device_id TEXT,scenario TEXT,signal_type TEXT,signal_value TEXT,confidence REAL',
        }
        for table, columns in schemas.items():
            self.db.execute(f'CREATE TABLE {table} ({columns})')
        self.db.execute("INSERT INTO learning_courses VALUES ('course','1','天地人','chinese')")

    def tearDown(self):
        self.db.raw.close()

    def state(self, day='2026-09-29', *, support=False):
        state = journey.initial({}, release_fixture())
        state.update(updatedAt=at(day), verified=journey.SKILLS[:5 if support else 6],
                     status='needs_support' if support else 'session_passed', parentNeeded=support,
                     reviewDueAt=None if support else at('2026-09-30'))
        state['baseline'] = [{'skill': s, 'correct': i < 4, 'hintUsed': i == 4, 'adultHelp': i == 5}
                             for i, s in enumerate(journey.SKILLS)]
        return state

    def insert(self, state, *, family='family', name='孩子', session='session', report_day='2026-09-28'):
        self.db.execute('INSERT INTO children VALUES (?,?,?)', (session+'-child', family, name))
        self.db.execute('INSERT INTO learning_sessions VALUES (?,?,?,?,?,?,?,?,?)',
            (session, family, session+'-child', 'course', '1', session+'-task', at('2026-09-28'),
             state.get('updatedAt', at('2026-09-29')), json.dumps({'textbookPlay': state})))
        self.db.execute('INSERT INTO learning_reports VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (session+'-report', family, session+'-child', session, 'course', '1', session+'-task',
             report_day, at(report_day), 4, 6, 1, 'developing', '继续练习'))

    def report(self, start='2026-09-29', end=None):
        return learning_for_period(self.db, family_id='family', start_date=start, end_date=end or start)

    def test_day_snapshot_preserves_past_support_after_later_success(self):
        old = self.state('2026-09-28', support=True)
        state = self.state()
        save_journey_report_day(state, old)
        before = deepcopy(state['reportDays']['2026-09-28'])
        self.insert(state)
        self.assertEqual(self.report('2026-09-28')['needsSupportCount'], 1)
        self.assertEqual(self.report()['needsSupportCount'], 0)
        self.assertEqual(self.report('2026-09-28')['lessons'][0]['verification']['correct'], 5)
        self.assertEqual(self.report()['lessons'][0]['verification']['correct'], 6)
        self.assertEqual(self.report('2026-09-28', '2026-09-29')['lessonCount'], 1)
        self.assertEqual(state['reportDays']['2026-09-28'], before)

    def test_live_legacy_evidence_and_family_isolation_without_writing(self):
        state = self.state()
        self.insert(state)
        self.insert(state, family='other-family', name='不可泄露', session='other')
        result = self.report()
        self.assertEqual(result['lessonCount'], 1)
        self.assertNotIn('不可泄露', json.dumps(result, ensure_ascii=False))
        lesson = result['lessons'][0]
        self.assertEqual(lesson['baseline'], {'correct': 4, 'total': 6, 'hints': 1, 'adultHelp': 1})
        self.assertEqual(lesson['reviewDueAt'], at('2026-09-30'))
        saved = json.loads(self.db.execute("SELECT runtime_state_json FROM learning_sessions WHERE id='session'").fetchone()['runtime_state_json'])
        self.assertNotIn('reportDays', saved['textbookPlay'])
        historical = self.report('2026-09-28')['lessons'][0]
        self.assertIsNone(historical['verification'])
        self.assertEqual(historical['statusLabel'], '首次练习记录')

    def test_review_day_included_without_changing_precheck_or_double_counting_course(self):
        state = self.state()
        save_journey_report_day(state, {})
        original_baseline = deepcopy(state['baseline'])
        previous = deepcopy(state)
        state.update(updatedAt=at('2026-09-30'), reviewLevel=1, reviewDueAt=at('2026-10-07'))
        state['reviewHistory'] = [{'level': 0, 'completedAt': at('2026-09-30'), 'independentSkills': journey.SKILLS}]
        save_journey_report_day(state, previous)
        self.insert(state)
        week = self.report('2026-09-28', '2026-10-04')
        self.assertEqual((week['lessonCount'], week['reviewCount']), (1, 1))
        self.assertEqual(self.report('2026-09-30')['reviewCount'], 1)
        self.assertEqual(self.report('2026-09-29')['reviewCount'], 0)
        self.assertEqual(self.report('2026-09-29')['lessons'][0]['reviewDueAt'], at('2026-09-30'))
        self.assertEqual(state['baseline'], original_baseline)

    def test_midnight_and_empty_period(self):
        state = self.state()
        state['updatedAt'] = at('2026-09-30', 0)
        save_journey_report_day(state, {})
        self.insert(state)
        self.assertEqual(self.report('2026-09-29')['lessonCount'], 0)
        self.assertEqual(self.report('2026-09-30')['lessonCount'], 1)
        self.assertEqual(self.report('2026-10-01')['lessons'], [])

    def test_generic_course_uses_its_real_report_without_six_skill_assumption(self):
        self.insert({}, report_day='2026-09-29')
        result = self.report()['lessons'][0]
        self.assertEqual(result['kind'], 'course')
        self.assertIsNone(result['verification'])
        self.assertIsNone(result['baseline']['adultHelp'])

    def test_actual_answer_day_takes_precedence_over_the_scheduled_learning_date(self):
        self.insert({}, report_day='2026-09-29')
        self.db.execute("UPDATE learning_reports SET learning_date='2026-09-28'")
        lesson = self.report()['lessons'][0]
        self.assertEqual(lesson['assessmentEvidence']['independence']['recordDate'], '2026-09-29')
        self.assertEqual(self.report('2026-09-28')['lessonCount'], 0)

    def test_real_daily_and_weekly_routes_include_learning_when_no_daily_tasks(self):
        self.insert(self.state(support=True))
        service = object.__new__(ProfileService)
        service.repository = SimpleNamespace(transaction=self.db.transaction)
        service._auth_context = Mock(return_value={'family': {'id': 'family'}})
        app = Flask(__name__)
        app.register_blueprint(reports_bp, url_prefix='/api/reports')
        with patch('routes.api.v1.reports.profile_service', return_value=service), patch('services.profile_service._report_events', return_value=[]):
            for url in ('/api/reports/daily?date=2026-09-29', '/api/reports/weekly?startDate=2026-09-28&endDate=2026-09-29'):
                response = app.test_client().get(url, headers={'Authorization': 'Bearer local-test'})
                self.assertEqual(response.status_code, 200)
                maps = response.json['report']['skillMaps']
                self.assertEqual(len(maps), 1)
                self.assertEqual(maps[0]['childId'], 'session-child')
                scores = {s['key']: s['score'] for s in maps[0]['skills']}
                self.assertEqual(scores['comprehension'], 83)
                self.assertIsNone(scores['focus'])
                report = response.json['report']
                self.assertEqual(report['taskTotal'], 0)
                self.assertEqual(report['learning']['lessonCount'], 1)
                self.assertIn('需要您留意', report['headline'])
                self.assertIn('实际作答', report['body'])


if __name__ == '__main__':
    unittest.main()
