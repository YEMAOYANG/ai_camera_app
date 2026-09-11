from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from content.primary_skill_boundaries import boundaries_for
from repositories.learning_repository import LearningRepository
from services.learning_difficulty import available_skill_order, preferred_difficulty, selection_payload
from services.learning_service import LearningService
from services.learning_practice_service import canonical, digest
from tests.test_learning_practice import PracticeTest, source


class DifficultySelectionTest(unittest.TestCase):
    def test_only_independent_evidence_promotes_and_prerequisites_remain_ordered(self):
        self.assertEqual(preferred_difficulty(None), 'standard')
        self.assertEqual(preferred_difficulty({'mastery_level': 'mastered', 'correct_count': 20}), 'standard')
        self.assertEqual(preferred_difficulty({'mastery_level': 'mastered', 'independent_correct_count': 2, 'hint_count': 0}), 'challenge')
        self.assertEqual(preferred_difficulty({'mastery_level': 'mastered', 'independent_correct_count': 20, 'hint_count': 2}), 'basic')
        self.assertEqual(preferred_difficulty({'mastery_level': 'needs_practice'}), 'basic')
        bounds = boundaries_for('primary_6', 'math')
        self.assertEqual(available_skill_order(bounds, {}), [bounds[0].skill_id])
        states = {bounds[0].skill_id: {'mastery_level': 'mastered'}}
        self.assertEqual(available_skill_order(bounds, states), [bounds[1].skill_id, bounds[0].skill_id])

    def test_missing_tier_selects_only_completed_formal_review_without_future_skill(self):
        service = object.__new__(LearningService)
        service.static_catalog_enabled = False
        service.repository = Mock()
        service.repository.list_published_subjects.return_value = ['math']
        service.repository.get_mastery_state.return_value = {'mastery_level': 'needs_practice'}
        skill = boundaries_for('primary_6', 'math')[0].skill_id
        review = {'id': 'review', 'version': '1', 'content_json': json.dumps({'difficultyCode': 'standard'})}
        service.repository.get_recommended_course.side_effect = lambda conn, **kw: deepcopy(review) if kw.get('require_completed') else None
        chosen = service._course_for_child(None, family_id='family', child={'family_id': 'family', 'id': 'child', 'grade_code': 'primary_6'},
            learning_date='2026-09-10', subject='math', allow_missing=True)
        self.assertTrue(chosen['_difficulty_review_fallback'])
        calls = [call.kwargs for call in service.repository.get_recommended_course.call_args_list]
        self.assertEqual([c['required_node_code'] for c in calls], [skill, skill])
        self.assertEqual(calls[0]['difficulty_code'], 'basic')
        self.assertTrue(calls[1]['require_completed'])
        self.assertTrue(all(c['require_formal_pointer'] for c in calls))
        self.assertEqual(selection_payload(chosen, {'mastery_level': 'needs_practice'})['mode'], 'review')

    def test_query_binds_difficulty_and_exact_child_completed_version(self):
        conn = Mock()
        LearningRepository(Mock()).get_recommended_course(conn, family_id='f', child_id='c', grade_code='primary_6',
            learning_date='2026-09-10', subject='math', required_node_code='skill', difficulty_code='basic', require_completed=True)
        sql, params = conn.execute.call_args.args
        self.assertIn('difficulty_review.course_version = course.version', sql)
        self.assertIn("difficulty_review.status = 'completed'", sql)
        self.assertEqual(params[:8], ['f', 'c', 'primary_6', 'math', 'skill', 'basic', 'f', 'c'])

    def test_practice_missing_tier_preserves_pool_and_returns_review_path(self):
        fixture = PracticeTest()
        fixture.setUp()
        fixture.repo.child.update(grade_code='primary_6')
        skill = boundaries_for('primary_6', 'math')[0].skill_id
        row = source()
        content = json.loads(row['content_json'])
        content['difficultyCode'] = 'standard'
        row.update(grade_code='primary_6', node_code=skill, content_json=canonical(content),
            feature_manifest_json=canonical({'sourceCourseContentSha256': digest(content)}))
        fixture.repo.sources = [row]
        fixture.repo.difficulty_mastery = lambda conn, **scope: {skill: {'mastery_level': 'needs_practice'}}
        response = fixture.start()
        self.assertIsNone(response['session'])
        self.assertEqual(response['fallbackPath'], '/learning')
        self.assertIn('当前难度', response['message'])
        self.assertFalse(fixture.repo.questions)
        fixture.repo.difficulty_mastery = lambda conn, **scope: {}
        self.assertEqual(fixture.start()['session']['totalQuestions'], 2)
