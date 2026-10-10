"""Source authority and diagram reasoning counterexamples, without providers."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from services.homework_answer_quality import (SCHEMA, digest, reversal_answer,
    reviewed_result, reviewed_lesson, student_grading, teaching_quality, _arithmetic_claims_consistent)


def facts(**changes):
    return {'total': 5, 'targetLabel': '雪雪', 'originalOrdinal': 2, 'originalFront': 'left',
        'transform': 'turn_around', 'printedTargetConfirmed': True,
        'handwrittenAnnotationsExcluded': True, **changes}


def source():
    result = {'method': 'tencent_question.v1', 'studentAnswer': '4', 'status': 'pending',
        'sourceAnswerOrdinal': 1, 'sourceAnswerCount': 1, 'prompt': '请看原图。',
        'sourceValidation': {'trusted': False, 'angleVerified': True},
        'tencentRaw': {'answer': {'HandwriteInfo': '4', 'IsCorrect': False,
            'RightAnswer': '2', 'AnswerAnalysis': '原来第2，向后转还是第2。', 'KnowledgePoints': ['位置与顺序']}}}
    return {'id': 'homework-a', 'revision': 3}, {'id': 'item-a', 'revision': 1,
        'result_json': json.dumps(result, ensure_ascii=False)}, {'id': 'page-a', 'content_sha256': 'a'*64}


def record(row, item, page):
    value = {'scope': {'submissionId': row['id'], 'submissionRevision': row['revision'],
        'itemId': item['id'], 'itemRevision': item['revision'], 'pageId': page['id'],
        'sourceImageSha256': page['content_sha256'], 'resultSha256': digest(json.loads(item['result_json']))},
        'expectedAnswer': '4', 'teacherFacts': facts(), 'method': 'operator_reviewed_order_reversal.v1',
        'reviewBasis': 'human_confirmed_original', 'approvalReference': 'explicit-test-review'}
    value['reviewId'] = digest(value)
    return value


class DiagramReasoningTest(TestCase):
    def test_reversal_all_positions_both_directions_and_twice_is_identity(self):
        for total in range(1, 20):
            for original in range(1, total+1):
                for direction in ('left', 'right'):
                    moved = int(reversal_answer(facts(total=total, originalOrdinal=original, originalFront=direction)))
                    self.assertEqual(int(reversal_answer(facts(total=total, originalOrdinal=moved))), original)
                    self.assertEqual(moved, total+1-original)

    def test_unconfirmed_target_handwritten_ordinals_and_invalid_facts_are_rejected(self):
        for updates in ({'printedTargetConfirmed': False}, {'handwrittenAnnotationsExcluded': False},
            {'total': True}, {'originalOrdinal': 0}, {'originalOrdinal': 6},
            {'originalFront': 'unknown'}, {'transform': 'move_position'}):
            with self.subTest(updates=updates), self.assertRaises(ValueError): reversal_answer(facts(**updates))

    def test_correct_json_answer_cannot_hide_detectable_wrong_narration(self):
        for text in ('3加2等于6。', '三加二等于六。', '正确答案是6。', '3 + 2 = 6'):
            with self.subTest(text=text): self.assertFalse(_arithmetic_claims_consistent(text, '5'))
        self.assertTrue(_arithmetic_claims_consistent('3加2等于5。正确答案是5。', '5'))


class SourceBoundAuthorityTest(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'reviews.json'
        env = patch.dict(os.environ, {'HOMEWORK_ANSWER_REVIEW_PATH': str(self.path)})
        env.start(); self.addCleanup(env.stop)
        self.row, self.item, self.page = source()
        self.review = record(self.row, self.item, self.page)
        self.save([self.review])

    def save(self, records):
        self.path.write_text(json.dumps({'schemaVersion': SCHEMA, 'reviews': records}, ensure_ascii=False))

    def test_review_corrects_projection_without_rewriting_receipt_or_ability(self):
        before = deepcopy(self.item); result = reviewed_result(self.row, self.item, self.page)
        grading = student_grading(result)
        self.assertEqual(grading['status'], 'correct'); self.assertEqual(grading['referenceAnswer'], '4')
        self.assertNotIn('providerVerdict', grading)
        self.assertNotIn('providerIsCorrect', grading); self.assertFalse(grading['countsForAbility'])
        self.assertEqual(self.item, before); self.assertEqual(result['tencentRaw']['answer']['RightAnswer'], '2')
        lesson = reviewed_lesson(result)
        self.assertEqual(teaching_quality(lesson, result)['status'], 'verified')
        lesson['steps'][2]['text'] = '答案是2。'
        self.assertEqual(teaching_quality(lesson, result)['status'], 'needs_review')

    def test_review_is_bound_to_source_and_revision_not_question_name(self):
        for case in ('image', 'item', 'submission', 'revision', 'result', 'missing_page'):
            row, item, page = deepcopy((self.row, self.item, self.page))
            if case == 'image': page['content_sha256'] = 'b'*64
            if case == 'item': item['id'] = 'item-b'
            if case == 'submission': row['id'] = 'homework-b'
            if case == 'revision': row['revision'] += 1
            if case == 'result': item['result_json'] = item['result_json'].replace('第2', '第3')
            if case == 'missing_page': page = None
            with self.subTest(case=case): self.assertNotIn('_confirmedAnswerReview', reviewed_result(row, item, page))

    def test_duplicate_reviews_and_wrong_computation_fail_closed(self):
        self.save([self.review, deepcopy(self.review)])
        self.assertNotIn('_confirmedAnswerReview', reviewed_result(self.row, self.item, self.page))
        changed = deepcopy(self.review); changed['expectedAnswer'] = '2'; self.save([changed])
        self.assertNotIn('_confirmedAnswerReview', reviewed_result(self.row, self.item, self.page))

    def test_two_models_agreeing_on_wrong_answer_are_not_authority(self):
        result = json.loads(self.item['result_json'])
        unsafe = {'teacherText': '雪雪是第2。', 'steps': [{'text': '答案2'}],
            'assessment': {'expectedAnswer': '2'}, 'audio': {'status': 'ready'},
            'sourceCheck': {'basis': 'original_image', 'questionLocated': True,
                'questionReadable': True, 'answerLocated': True},
            'gradingReferenceComparison': {'status': 'consistent'}}
        grading = student_grading(result)
        self.assertEqual(grading['status'], 'unknown'); self.assertNotIn('referenceAnswer', grading)
        self.assertNotIn('analysis', grading)
        self.assertEqual(teaching_quality(unsafe, result)['status'], 'needs_review')

    def test_supported_reviewed_followup_varies_without_new_model_and_free_question_is_not_certified(self):
        result = reviewed_result(self.row, self.item, self.page)
        message = '为什么要这样做？请看着原题再解释一下。'
        lesson = reviewed_lesson(result, 'followup', message)
        self.assertNotEqual(lesson['teacherText'], reviewed_lesson(result)['teacherText'])
        self.assertEqual(teaching_quality({**lesson, 'mode': 'followup', 'message': message}, result)['status'], 'verified')
        self.assertIsNone(reviewed_lesson(result, 'followup', '随意造一个新题吧'))


def provisional_source(*, correct=False, answer='4', right='5'):
    region = {'x': .1, 'y': .1, 'width': .8, 'height': .3}
    answer_region = {'x': .5, 'y': .15, 'width': .1, 'height': .1}
    return {'method': 'tencent_question.v1', 'status': 'pending', 'type': 'word_problem',
        'prompt': '请看原图中的这道题。', 'studentAnswer': answer, 'expectedAnswer': right,
        'region': region, 'answerRegions': [answer_region], 'annotationAmbiguous': False,
        'sourceAnswerOrdinal': 2, 'sourceAnswerCount': 6,
        'sourceHierarchy': {'sourcePath': ['一、看图填空'], 'scope': 'answer_blank', 'answerIndex': 2, 'answerCount': 6},
        'providerAssessment': {'isCorrect': correct, 'answerRegion': answer_region},
        'sourceValidation': {'trusted': False, 'angleVerified': True, 'geometryVerified': True,
            'issues': ['question_text_missing', 'multiple_answer_alignment_unverified']},
        'tencentRaw': {'angle': 0, 'answer': {'HandwriteInfo': answer, 'IsCorrect': correct,
            'RightAnswer': right, 'AnswerAnalysis': '请结合原图分析。', 'KnowledgePoints': ['看图计数']}}}


class ProvisionalProviderVerdictTests(TestCase):
    def test_shared_missing_stem_can_show_initial_verdict_without_answer_or_authority(self):
        for correct, answer in ((True, '5'), (False, '4')):
            result = provisional_source(correct=correct, answer=answer); before = deepcopy(result)
            grading = student_grading(result)
            self.assertEqual(grading['status'], 'unknown')
            self.assertEqual(grading['studentQuality']['status'], 'needs_review')
            self.assertEqual(grading['providerVerdict'], {'status': 'correct' if correct else 'incorrect',
                'source': 'tencent', 'provisional': True, 'countsForAbility': False})
            self.assertNotIn('referenceAnswer', grading); self.assertNotIn('analysis', grading)
            self.assertNotIn('providerIsCorrect', grading); self.assertEqual(result, before)
            lesson = {'teacherText': '答案是5。', 'steps': [], 'assessment': {'expectedAnswer': '5'}}
            self.assertEqual(teaching_quality(lesson, result)['status'], 'needs_review')
            from services.homework_tutor_context import grading_context
            context = grading_context(result)
            self.assertEqual(context['paperJudgment'], 'unknown')
            self.assertEqual(context['referenceAnswer'], ''); self.assertEqual(context['analysis'], '')
            self.assertNotIn('providerVerdict', context)

    def test_initial_verdict_needs_no_reference_answer_to_display(self):
        result = provisional_source(right='')
        result['sourceValidation']['issues'].append('reference_answer_missing')
        grading = student_grading(result)
        self.assertEqual(grading['providerVerdict']['status'], 'incorrect')
        self.assertNotIn('referenceAnswer', grading)

    def test_strict_raw_verdict_handwriting_and_geometry_are_required(self):
        updates = [
            ('verdict', value) for value in (None, 0, 1, 'false')
        ] + [('handwriting', value) for value in (None, 4, '', '  ')] + [
            ('angle', value) for value in (None, True, '0', 90, float('nan'))
        ] + [('geometry', field) for field in ('question', 'answer', 'angle', 'validation')]
        for kind, value in updates:
            result = provisional_source()
            if kind == 'verdict': result['tencentRaw']['answer']['IsCorrect'] = value
            elif kind == 'handwriting': result['tencentRaw']['answer']['HandwriteInfo'] = value
            elif kind == 'angle': result['tencentRaw']['angle'] = value
            elif value == 'question': result['region']['width'] = 2
            elif value == 'answer':
                result['providerAssessment']['answerRegion'] = None; result['answerRegions'] = []
            elif value == 'angle': result['sourceValidation']['angleVerified'] = False
            else: result['sourceValidation']['geometryVerified'] = False
            with self.subTest(kind=kind, value=value):
                grading = student_grading(result)
                self.assertNotIn('providerVerdict', grading)
                self.assertTrue(grading['providerVerdictBlockedReason'])

    def test_explicit_arithmetic_and_scalar_verdict_contradictions_are_withheld(self):
        for issue in ('provider_arithmetic_contradiction', 'reference_arithmetic_contradiction'):
            result = provisional_source(); result['sourceValidation']['issues'].append(issue)
            self.assertEqual(student_grading(result)['providerVerdictBlockedReason'], 'provider_source_contradiction')
        for correct, answer, right in ((False, '5', '5'), (True, '4', '5'),
                (False, '５', '5.0'), (False, '第４位。', '四'), (False, '1/2', '0.5')):
            result = provisional_source(correct=correct, answer=answer, right=right)
            with self.subTest(correct=correct, answer=answer, right=right):
                self.assertEqual(student_grading(result)['providerVerdictBlockedReason'], 'numeric_verdict_contradiction')

    def test_direction_reversal_is_withheld_at_every_source_level(self):
        for key in ('prompt', 'sourcePath', 'ancestorContext', 'sourceHierarchy', 'answerAnalysis'):
            result = provisional_source()
            if key == 'sourceHierarchy': result[key]['sourcePath'] = ['训练', '向后转']
            elif key == 'answerAnalysis': result['tencentRaw']['answer']['AnswerAnalysis'] = '转身后方向反转。'
            elif key in {'sourcePath', 'ancestorContext'}: result[key] = ['训练', '向后转']
            else: result[key] = '同学们向后转，谁排在前面？'
            with self.subTest(key=key):
                grading = student_grading(result)
                self.assertNotIn('providerVerdict', grading)
                self.assertEqual(grading['providerVerdictBlockedReason'], 'direction_reversal_requires_review')

    def test_ambiguous_handwriting_unknown_validation_and_answer_copy_mismatch_are_withheld(self):
        for updates in ({'annotationAmbiguous': True}, {'studentAnswer': '3'},
                {'sourceValidation': {'angleVerified': True, 'geometryVerified': True, 'issues': ['new_unknown_problem']}}):
            result = {**provisional_source(), **updates}
            with self.subTest(updates=updates): self.assertNotIn('providerVerdict', student_grading(result))
