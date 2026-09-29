from copy import deepcopy
import json
import unittest

from services.report_growth_assessment import build_growth_maps, growth_for_period
from services.report_learning_summary import journey_snapshot, learning_for_period, save_journey_report_day
import test_report_learning_summary as learning_tests
from test_report_learning_summary import at
from test_textbook_activity import release_fixture
from content import textbook_journey as journey


def records(*, correct=6, hint=False):
    return [{'phase': 'transfer', 'skill': skill, 'correct': i < correct,
             'hintUsed': hint and i == 0, 'adultHelp': i == 5, 'round': 0}
            for i, skill in enumerate(journey.SKILLS)]


class GrowthAssessmentTests(unittest.TestCase):
    def build(self, tasks=(), lessons=(), camera=()):
        maps = build_growth_maps([{'id': 'a', 'nickname': '孩子甲'}, {'id': 'b', 'nickname': '孩子乙'}],
            tasks, lessons, camera, start_date='2026-09-29', end_date='2026-09-29')
        return [{s['key']: s for s in m['skills']} for m in maps]

    def test_no_evidence_is_unknown_instead_of_a_default_score(self):
        for child in self.build():
            self.assertTrue(all(s['score'] is None and s['sampleCount'] == 0 for s in child.values()))

    def test_camera_and_parent_outcome_are_one_sample_and_parent_correction_wins(self):
        camera = {'id': 'obs', 'child_id': 'a', 'task_id': 'task', 'observed_at': at('2026-09-29'),
                  'scenario': 'toy_cleanup', 'signal_type': 'cleanup_done', 'signal_value': 'observed', 'source': 'camera_adapter'}
        parent = {'id': 'task', 'child_id': 'a', 'type': 'housework', 'status': 'rejected',
                  'rejected_at': at('2026-09-29'), 'title': '收纳'}
        first, second = self.build(tasks=[parent], camera=[camera, {**camera, 'id': 'repeat'}])
        self.assertEqual(first['order']['score'], 0)
        self.assertEqual(first['order']['sampleCount'], 1)
        self.assertEqual(first['order']['evidence'][0]['source'], 'camera_parent')
        self.assertIsNone(second['order']['score'])

    def test_timer_completion_pending_tasks_and_title_keywords_do_not_create_ability(self):
        tasks = [{'id': str(i), 'child_id': 'a', 'type': 'learning', 'title': '主动专注运动喝水',
                  'status': status, 'completion_source': 'camera', 'completed_at': at('2026-09-29')}
                 for i, status in enumerate(('completed', 'in_progress', 'missed', 'awaiting_parent_confirmation'))]
        tasks.append({**tasks[0], 'id': 'life-timer', 'type': 'life'})
        self.assertTrue(all(s['score'] is None for s in self.build(tasks=tasks)[0].values()))

    def test_course_scores_are_child_scoped_and_do_not_infer_attention_or_initiative(self):
        lesson = {'childId': 'a', 'courseId': 'course', 'courseVersion': '1', 'courseTitle': '天地人',
                  'assessmentEvidence': {
                      'independence': {'correct': 4, 'total': 6, 'recordDate': '2026-09-29'},
                      'comprehension': {'correct': 5, 'total': 6, 'recordDate': '2026-09-29'},
                      'retention': {'correct': 6, 'total': 6, 'recordDate': '2026-09-30'}}}
        first, second = self.build(lessons=[lesson, lesson])
        self.assertEqual(first['independence']['score'], 67)
        self.assertEqual(first['comprehension']['score'], 83)
        self.assertEqual(first['independence']['sampleCount'], 1)
        self.assertTrue(all(first[k]['score'] is None for k in ('retention', 'focus', 'initiative')))
        self.assertTrue(all(s['score'] is None for s in second.values()))

    def test_review_retention_uses_first_answers_even_after_successful_repair(self):
        state = journey.initial({}, release_fixture())
        first = records(correct=3, hint=True)
        repaired = [{**r, 'round': 1, 'correct': True, 'hintUsed': False, 'adultHelp': False} for r in first]
        state.update(updatedAt=at('2026-09-29'), status='session_passed', verified=journey.SKILLS,
            reviewHistory=[{'level': 0, 'completedAt': at('2026-09-29'), 'records': first + repaired}])
        state['challenge']['records'] = first + repaired
        snapshot = journey_snapshot(state)
        self.assertEqual(snapshot['assessmentEvidence']['comprehension']['correct'], 6)
        self.assertEqual(snapshot['assessmentEvidence']['retention']['correct'], 2)
        self.assertEqual(snapshot['assessmentEvidence']['retention']['total'], 6)

    def test_unanswered_transfer_and_guided_play_are_not_wrong_answers_or_independent_credit(self):
        state = journey.initial({}, release_fixture())
        state['updatedAt'] = at('2026-09-29')
        state['games']['records'] = [{'phase': 'hunt', 'skill': 'sky', 'correct': True}]
        self.assertEqual(journey_snapshot(state)['assessmentEvidence'], {})
        state['challenge']['records'] = records(correct=6)[:1]
        metric = journey_snapshot(state)['assessmentEvidence']['comprehension']
        self.assertEqual((metric['correct'], metric['total']), (1, 1))

    def test_past_daily_assessment_does_not_change_after_new_review(self):
        state = journey.initial({}, release_fixture())
        state.update(updatedAt=at('2026-09-28'), baselineRecordedAt=at('2026-09-28'))
        state['baseline'] = [{**r, 'phase': 'diagnostic'} for r in records(correct=4)]
        state['challenge']['records'] = records(correct=3)
        save_journey_report_day(state, {})
        old = deepcopy(state['reportDays']['2026-09-28'])
        previous = deepcopy(state)
        state.update(updatedAt=at('2026-09-29'), reviewActive=True)
        state['challenge']['records'] = records(correct=6)
        save_journey_report_day(state, previous)
        self.assertEqual(state['reportDays']['2026-09-28'], old)


class GrowthSqlTests(unittest.TestCase):
    def setUp(self):
        self.fixture = learning_tests.ReportLearningTests()
        self.fixture.setUp()
        self.db = self.fixture.db

    def tearDown(self):
        self.fixture.tearDown()

    def camera(self, identity, *, family='family', child='session-child', confidence=.9, task=None):
        self.db.execute('INSERT INTO camera_observation_events VALUES (?,?,?,?,?,?,?,?,?)',
            (identity, family, child, 'device', task, at('2026-09-29'), 'toy_cleanup', 'camera_adapter', confidence))
        self.db.execute('INSERT INTO behavior_signals VALUES (?,?,?,?,?,?,?,?,?)',
            ('s-'+identity, identity, family, child, 'device', 'toy_cleanup', 'cleanup_done', 'observed', confidence))

    def test_camera_confidence_is_a_filter_not_an_ability_score_and_sql_is_family_bound(self):
        state = self.fixture.state()
        self.fixture.insert(state, report_day='2026-09-29')
        self.fixture.insert(state, family='foreign', session='foreign', name='不可泄露')
        self.db.execute("INSERT INTO children VALUES ('other','family','另一位孩子')")
        self.camera('real')
        self.camera('duplicate')
        self.camera('unreliable', child='other', confidence=.4)
        self.camera('foreign', family='foreign', child='foreign-child')
        learning = learning_for_period(self.db, family_id='family', start_date='2026-09-29', end_date='2026-09-29')
        maps = growth_for_period(self.db, family_id='family', start_date='2026-09-29', end_date='2026-09-29', tasks=[], learning=learning)
        self.assertNotIn('不可泄露', json.dumps(maps, ensure_ascii=False))
        result = {m['childId']: {s['key']: s for s in m['skills']} for m in maps}
        self.assertEqual(result['session-child']['order']['score'], 100)
        self.assertEqual(result['session-child']['order']['sampleCount'], 1)
        self.assertEqual(result['session-child']['independence']['score'], 67)
        self.assertIsNone(result['other']['order']['score'])
