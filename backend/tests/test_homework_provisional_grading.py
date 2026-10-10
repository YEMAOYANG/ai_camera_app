"""Initial Tencent display results never become formal grades or AI context."""
from copy import deepcopy
import json
from unittest import TestCase

from integrations.ai.kimi_vision_provider import AiVisionResponse
from tests import test_homework_analysis as fixtures
from tests.test_homework_answer_quality import provisional_source


class HomeworkProvisionalPaperProjectionTests(TestCase):
    setUp = fixtures.HomeworkTest.setUp
    create = fixtures.HomeworkTest.create
    upload = fixtures.HomeworkTest.upload
    ready = fixtures.HomeworkTest.ready
    events = fixtures.HomeworkTest.events

    def paper(self):
        self.raw.update(prompt='请看图作答。', type='word_problem', confidence=.2)
        self.provider.analyze_image.side_effect = lambda **kw: AiVisionResponse(json.dumps({
            'pageReadable': True, 'items': [deepcopy(self.raw) for _ in range(3)]}), 'fixture', 'fixture-vision')
        submission = self.ready()
        results = []
        for ordinal, (item, correct, answer) in enumerate(zip(submission['items'], (True, False, False), ('5', '4', '')), 1):
            current = self.db.execute('SELECT result_json FROM homework_items WHERE id=?', (item['id'],)).fetchone()
            result = {**json.loads(current['result_json']), **provisional_source(correct=correct, answer=answer)}
            result.update(sourceAnswerOrdinal=ordinal, sourceAnswerCount=3)
            result['sourceHierarchy'].update(answerIndex=ordinal, answerCount=3)
            self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',
                (json.dumps(result, ensure_ascii=False), item['id']))
            results.append((item, result))
        self.db.raw.commit()
        return submission, results

    def test_parent_and_student_display_summary_is_separate_from_formal_results(self):
        submission, results = self.paper()
        model_calls, voice_calls = self.provider.analyze_image.call_count, self.transport.call_count
        events = len(self.events())
        saved = [self.db.execute('SELECT result_json FROM homework_items WHERE id=?', (item['id'],)).fetchone()['result_json']
            for item, _ in results]
        for _ in range(2):
            parent = self.service.get('parent-a', submission['id'])['submission']
            student = self.service.student_detail('student-a', submission['id'])['submission']
            for public in (parent, student):
                self.assertEqual(public['provisionalPaperSummary'], {'correct': 1, 'incorrect': 1,
                    'unknown': 1, 'blank': 1, 'total': 3, 'countsForAbility': False})
                self.assertEqual(public['originalPaperSummary'], {'correct': 0, 'incorrect': 0,
                    'unknown': 3, 'blank': 1, 'total': 3, 'countsForAbility': False})
                self.assertEqual(public['providerVerdictSummary'], {'correct': 0, 'incorrect': 0, 'unknown': 3, 'total': 3})
                self.assertEqual(public['originalSummary']['pending'], 3)
                self.assertEqual(public['studentSummary'], {'ready': 0, 'awaitingMedia': 0,
                    'unsupportedCorrection': 0, 'corrected': 0, 'selfReportedCompleted': 0})
                self.assertFalse(public['readyForStudent'])
                for entry, (_, raw) in zip(public['originalPaperItems'], results):
                    grading = entry['reviewContext']['grading']
                    self.assertEqual(entry['status'], 'pending'); self.assertEqual(grading['status'], 'unknown')
                    self.assertEqual(grading['studentQuality']['status'], 'needs_review')
                    self.assertNotIn('referenceAnswer', grading); self.assertNotIn('analysis', grading)
                    if raw['studentAnswer']:
                        self.assertIn('providerVerdict', grading)
                    else:
                        self.assertNotIn('providerVerdict', grading)
            self.assertEqual(student['items'], [])
            self.assertTrue(all(not entry['readyForStudent'] for entry in parent['items']))
            self.assertTrue(all('expectedAnswer' not in entry and 'explanation' not in entry for entry in parent['items']))
        self.assertEqual([self.db.execute('SELECT result_json FROM homework_items WHERE id=?', (item['id'],)).fetchone()['result_json']
            for item, _ in results], saved)
        self.assertEqual(self.provider.analyze_image.call_count, model_calls)
        self.assertEqual(self.transport.call_count, voice_calls); self.assertEqual(len(self.events()), events)

    def test_blocked_direction_item_does_not_publish_initial_wrong_or_change_formal_summary(self):
        submission, results = self.paper()
        item, result = results[1]
        result['ancestorContext'] = ['正步训练', '同学们向后转']
        result['tencentRaw']['answer']['RightAnswer'] = '2'
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',
            (json.dumps(result, ensure_ascii=False), item['id']))
        self.db.raw.commit()
        for public in (self.service.get('parent-a', submission['id'])['submission'],
                self.service.student_detail('student-a', submission['id'])['submission']):
            self.assertEqual(public['provisionalPaperSummary']['incorrect'], 0)
            self.assertEqual(public['provisionalPaperSummary']['unknown'], 2)
            self.assertEqual(public['originalPaperSummary']['incorrect'], 0)
            grading = public['originalPaperItems'][1]['reviewContext']['grading']
            self.assertNotIn('providerVerdict', grading)
            self.assertEqual(grading['providerVerdictBlockedReason'], 'direction_reversal_requires_review')
            self.assertNotIn('referenceAnswer', grading); self.assertNotIn('analysis', grading)

    def test_non_tencent_submission_has_no_initial_provider_summary(self):
        submission = self.ready()
        self.assertNotIn('provisionalPaperSummary', submission)
        student = self.service.student_detail('student-a', submission['id'])['submission']
        self.assertNotIn('provisionalPaperSummary', student)
