"""Owned report snapshots over in-memory SQL; no provider or real database."""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime
import json
import os
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from routes.api.v1.reports import reports_bp
from services.homework_answer_quality import attach_reference_answer_layout, reference_for_correction
from services.homework_service import POLICY
from services.homework_tencent_normalizer import normalize_question_page
from services.profile_service import ProfileService
from services.report_homework_progress import homework_progress_for_period
from services.report_learning_summary import ZONE, learning_for_period, review_report_for_period
from tests.test_homework_tencent_grading import marks, source


def at(day, hour=12):
    return int(datetime.fromisoformat(f'{day}T{hour:02d}:00:00').replace(tzinfo=ZONE).timestamp() * 1000)


class MemoryConnection:
    def __init__(self):
        self.raw = sqlite3.connect(':memory:')
        self.raw.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        cursor = self.raw.execute(sql, tuple(params))
        return SimpleNamespace(
            fetchone=lambda: self._row(cursor.fetchone()),
            fetchall=lambda: [dict(row) for row in cursor.fetchall()])

    @staticmethod
    def _row(value):
        return dict(value) if value is not None else None

    @contextmanager
    def transaction(self):
        with self.raw:
            yield self


class ReportHomeworkProgressTest(unittest.TestCase):
    def setUp(self):
        self.db = MemoryConnection()
        self.addCleanup(self.db.raw.close)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {'HOMEWORK_ANSWER_REVIEW_PATH': self.temp.name + '/absent.json'})
        env.start()
        self.addCleanup(env.stop)
        schemas = {
            'children': 'id TEXT,family_id TEXT,nickname TEXT',
            'learning_courses': 'id TEXT,version TEXT,title TEXT,subject TEXT',
            'learning_sessions': 'id TEXT,family_id TEXT,child_id TEXT,course_id TEXT,course_version TEXT,task_id TEXT,started_at INTEGER,updated_at INTEGER,runtime_state_json TEXT',
            'learning_reports': 'id TEXT,family_id TEXT,child_id TEXT,session_id TEXT,course_id TEXT,course_version TEXT,task_id TEXT,learning_date TEXT,created_at INTEGER,independent_correct_count INTEGER,total_questions INTEGER,hint_count INTEGER,mastery_level TEXT,next_step TEXT',
            'tasks': 'id TEXT,family_id TEXT,scheduled_date TEXT,scheduled_start TEXT,created_at INTEGER',
            'camera_observation_events': 'id TEXT,family_id TEXT,child_id TEXT,device_id TEXT,task_id TEXT,observed_at INTEGER,scenario TEXT,source TEXT,confidence REAL',
            'behavior_signals': 'id TEXT,observation_event_id TEXT,family_id TEXT,child_id TEXT,device_id TEXT,scenario TEXT,signal_type TEXT,signal_value TEXT,confidence REAL',
            'homework_submissions': 'id TEXT,family_id TEXT,child_id TEXT,title TEXT,revision INTEGER,source TEXT,created_at INTEGER,deleted_at INTEGER',
            'homework_pages': 'id TEXT,submission_id TEXT,content_sha256 TEXT',
            'homework_items': 'id TEXT,submission_id TEXT,page_id TEXT,revision INTEGER,result_json TEXT,correction_json TEXT',
        }
        for table, columns in schemas.items():
            self.db.execute(f'CREATE TABLE {table} ({columns})')
        self.db.execute("INSERT INTO children VALUES ('child','family','孩子')")
        self.db.execute("INSERT INTO children VALUES ('other-child','other-family','其他家庭')")

    def submission(self, identity='paper', *, family='family', child='child', day='2026-09-29',
                   origin='parent_upload', deleted=None):
        self.db.execute('INSERT INTO homework_submissions VALUES (?,?,?,?,?,?,?,?)',
            (identity, family, child, '数学作业-' + identity, 1, origin, at(day), deleted))
        self.db.execute('INSERT INTO homework_pages VALUES (?,?,?)',
            (identity + '-page', identity, 'a' * 64))

    def item(self, identity, *, paper='paper', answer='1', correction=None, missing_reference=False):
        result = normalize_question_page(
            [marks(prompt='看图填写数量', answer=answer, right='3', correct=answer == '3')],
            page_id=paper + '-page', width=800, height=1000, grade='primary_1', subject='math',
            policy=POLICY, submit_receipts=[source('看图填写数量')])['items'][0]
        # These are distinct one-blank questions, not duplicate siblings in one
        # official Tencent mark. Each source group needs its own path.
        result['sourceHierarchy']['markPath'] = [len(self.db.execute(
            'SELECT id FROM homework_items WHERE submission_id=?', (paper,)).fetchall())]
        reference = reference_for_correction(result)
        self.assertIsNotNone(reference)
        binding_result = deepcopy(result)
        value = deepcopy(correction or {})
        if missing_reference:
            result['tencentRaw']['answer'].pop('RightAnswer')
        self.db.execute('INSERT INTO homework_items VALUES (?,?,?,?,?,?)',
            (identity, paper, paper + '-page', 1, json.dumps(result), json.dumps(value)))
        if value:
            bound = attach_reference_answer_layout(self.db, {'id': paper},
                {'page_id': paper + '-page'}, binding_result)
            value.setdefault('referenceDigest', reference_for_correction(bound)['digest'])
            self.db.execute('UPDATE homework_items SET correction_json=? WHERE id=?',
                (json.dumps(value), identity))

    def report(self, day='2026-09-29', end=None):
        return homework_progress_for_period(self.db, family_id='family', start=at(day, 0),
            end=at(end or day, 0) + 24 * 60 * 60 * 1000)

    def test_progress_uses_reference_gate_and_never_claims_independent_mastery(self):
        self.submission()
        self.item('corrected', correction={'correct': True, 'attempts': 2, 'lastAnswer': '3',
            'updatedAt': at('2026-09-29'), 'tutorViewed': True})
        self.item('retry', correction={'correct': False, 'attempts': 1,
            'lastAnswer': '2', 'updatedAt': at('2026-09-29')})
        self.item('not-started')
        self.item('unknown', missing_reference=True,
            correction={'correct': True, 'attempts': 8, 'tutorViewed': True})
        self.item('original-correct', answer='3')
        before = list(self.db.execute('SELECT * FROM homework_items ORDER BY id').fetchall())
        changes = self.db.raw.total_changes
        report = self.report()
        self.assertEqual({key: report[key] for key in
            ('submissionCount', 'total', 'corrected', 'inProgress', 'notStarted', 'needsReview', 'assisted')},
            {'submissionCount': 1, 'total': 3, 'corrected': 1, 'inProgress': 1,
             'notStarted': 1, 'needsReview': 1, 'assisted': 1})
        self.assertIsNone(report['independent'])
        self.assertFalse(report['countsForAbility'])
        self.assertEqual(report['scope'], 'current_same_question_correction')
        self.assertEqual(report['entries'][0]['submissionId'], 'paper')
        self.assertEqual(report, self.report())
        self.assertEqual(changes, self.db.raw.total_changes)
        self.assertEqual(before, list(self.db.execute('SELECT * FROM homework_items ORDER BY id').fetchall()))

    def test_deleted_test_other_family_and_mismatched_child_sources_are_excluded(self):
        for identity, kwargs in (
            ('live', {}), ('synthetic', {'origin': 'synthetic_fixture'}),
            ('paid', {'origin': 'paid_validation'}), ('deleted', {'deleted': at('2026-09-29')}),
            ('foreign', {'family': 'other-family', 'child': 'other-child'}),
            ('wrong-child', {'child': 'other-child'}),
        ):
            self.submission(identity, **kwargs)
            self.item(identity + '-item', paper=identity)
        report = self.report()
        self.assertEqual(report['submissionCount'], 1)
        self.assertEqual(report['total'], 1)
        self.assertEqual([entry['submissionId'] for entry in report['entries']], ['live'])
        self.assertNotIn('其他家庭', json.dumps(report, ensure_ascii=False))

    def test_stale_correction_digest_does_not_count_as_corrected(self):
        self.submission()
        self.item('stale', correction={'correct': True, 'attempts': 4,
            'referenceDigest': 'wrong-reference', 'updatedAt': at('2026-09-29')})
        report = self.report()
        self.assertEqual(report['corrected'], 0)
        self.assertEqual(report['notStarted'], 1)

    def test_unprocessed_uploads_and_essay_guidance_are_not_zero_error_papers(self):
        self.submission('unprocessed')
        self.submission('essay')
        self.db.execute('INSERT INTO homework_items VALUES (?,?,?,?,?,?)',
            ('essay-item', 'essay', 'essay-page', 1, '{"method":"tencent_essay.v1"}', '{}'))
        report = self.report()
        self.assertEqual(report['submissionCount'], 0)
        self.assertEqual(report['entries'], [])

    def test_period_selects_upload_or_latest_answer_and_discloses_current_snapshot(self):
        self.submission('old', day='2026-09-28')
        self.item('old-answer', paper='old', correction={'correct': True, 'attempts': 1,
            'updatedAt': at('2026-09-30', 0)})
        self.submission('today')
        self.item('today-answer', paper='today')
        self.submission('future', day='2026-10-01')
        self.item('future-answer', paper='future')
        self.assertEqual([entry['submissionId'] for entry in self.report()['entries']], ['today'])
        next_day = self.report('2026-09-30')
        self.assertEqual([entry['submissionId'] for entry in next_day['entries']], ['old'])
        self.assertEqual(next_day['corrected'], 1)
        self.assertEqual(next_day['periodSelection'], 'uploaded_or_latest_correction_activity_in_period')
        self.assertEqual(self.report('2026-09-29', '2026-09-30')['submissionCount'], 2)

    def test_daily_and_weekly_routes_add_owned_homework_without_course_or_care_scores(self):
        self.submission()
        self.item('corrected', correction={'correct': True, 'attempts': 1,
            'updatedAt': at('2026-09-29'), 'explanationViewed': True})
        service = object.__new__(ProfileService)
        service.repository = SimpleNamespace(transaction=self.db.transaction)
        service._auth_context = Mock(return_value={'family': {'id': 'family'}})
        app = Flask(__name__)
        app.config['HOMEWORK_ANALYSIS_ENABLED'] = True
        app.register_blueprint(reports_bp, url_prefix='/api/reports')
        with patch('routes.api.v1.reports.profile_service', return_value=service), \
                patch('services.profile_service._report_events', return_value=[]):
            for url in ('/api/reports/daily?date=2026-09-29',
                        '/api/reports/weekly?startDate=2026-09-28&endDate=2026-09-29'):
                response = app.test_client().get(url, headers={'Authorization': 'Bearer offline'})
                self.assertEqual(response.status_code, 200)
                report = response.json['report']
                self.assertEqual(report['learning']['homeworkProgress']['corrected'], 1)
                self.assertEqual(report['learning']['lessonCount'], 0)
                self.assertEqual(report['taskTotal'], 0)
                self.assertTrue(all(skill['score'] is None for entry in report['skillMaps'] for skill in entry['skills']))
        with app.app_context():
            app.config['HOMEWORK_ANALYSIS_ENABLED'] = False
            self.assertNotIn('homeworkProgress', learning_for_period(
                self.db, family_id='family', start_date='2026-09-29', end_date='2026-09-29'))

    def test_weekend_report_reprojects_counts_after_current_source_filter(self):
        self.db.execute('CREATE TABLE learning_review_runs (id TEXT,family_id TEXT,child_id TEXT,created_at INTEGER,completed_at INTEGER,coverage_json TEXT)')
        self.db.execute('INSERT INTO learning_review_runs VALUES (?,?,?,?,?,?)',
            ('review', 'family', 'child', at('2026-09-29'), at('2026-09-29'), '{}'))
        filtered = {'sourceReviewCount': 1, 'items': [{'correct': True, 'independent': False}],
            'independentFirstCorrect': 0}
        with patch('services.learning_review_service.LearningReviewService._summary',
                   return_value={'correctCount': 8, 'independentCorrectCount': 6}), \
                patch('services.learning_review_service.LearningReviewService._report', return_value=filtered) as report, \
                patch('repositories.learning_review_repository.LearningReviewRepository.items', return_value=[]), \
                patch('services.learning_evidence_service.weaknesses', return_value=[]):
            result = review_report_for_period(self.db, family_id='family',
                start=at('2026-09-29', 0), end=at('2026-09-30', 0))
        entry = result['weekendReviews'][0]
        self.assertEqual(entry['correctCount'], 1)
        self.assertEqual(entry['independentCorrectCount'], 0)
        self.assertEqual(entry['report'], filtered)
        self.assertIs(report.call_args.kwargs['conn'], self.db)


if __name__ == '__main__':
    unittest.main()
