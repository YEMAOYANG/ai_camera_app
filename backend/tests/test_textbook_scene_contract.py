"""Portable authoring constraints; isolated and without provider calls."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import digest
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_scene_contract import (PROMPT_END, PROMPT_START, freeze_scene_contract,
                                             render_scene_contract, scene_canonical, scene_digest,
                                             validate_scene_contract)
from tests.test_textbook_workbench_authoring import reviewed_draft


class TextbookSceneContractTest(unittest.TestCase):
    def test_native_scene_integral_float_spelling_preserves_number_and_other_types(self):
        raw = {'range': [[0.0, -0.0], [100.0, 50]], 'fraction': 33.333333333333336,
               'label': '100.0', 'flag': True}
        before = deepcopy(raw)
        expected = {'range': [[0, 0], [100, 50]], 'fraction': 33.333333333333336,
                    'label': '100.0', 'flag': True}
        self.assertEqual(scene_digest(raw), digest(expected))
        self.assertEqual(raw, before)
        self.assertNotEqual(scene_digest(raw), scene_digest({**raw, 'fraction': 33.5}))
        self.assertNotEqual(scene_canonical({'number': True}), scene_canonical({'number': 1}))
        self.assertNotEqual(scene_canonical({'number': '100.0'}), scene_canonical({'number': 100}))
        self.assertNotEqual(scene_canonical({'number': float(2 ** 53)}),
                            scene_canonical({'number': 2 ** 53}))
        for number in (float('nan'), float('inf'), -float('inf')):
            with self.assertRaises(ValueError):
                scene_canonical({'nested': [number]})

    def setUp(self):
        self.draft = reviewed_draft()
        self.draft['pagePlan'] += [
            {'page': 2, 'type': 'interactive', 'title': '观察并修改', 'move': '移动对象并观察改变，可撤销后再试。'},
            {'page': 3, 'type': 'quiz', 'title': '听一听再找图', 'move': '通过语音和图片辨认新情境。',
             'questionIds': ['school-meeting'], 'narrationGuidance': ['先听老师说，再点图片。']}]
        self.draft['lockedAssessments'] = [
            {'id': 'school-meeting', 'page': 3, 'type': 'single', 'points': 10,
             'question': '请找到小朋友见面的图。', 'analysis': '他们走近并向对方挥手。', 'answer': 'B',
             'choices': [{'value': 'A', 'label': '第一幅图', 'asset': 'leaving'},
                         {'value': 'B', 'label': '第二幅图', 'asset': 'meeting'}]}]
        self.catalog = {'manifestSha256': 'a' * 64, 'lessonScopeSha256': 'b' * 64}
        self.policy = freeze_interaction_policy()

    def freeze(self, draft=None):
        return freeze_scene_contract(draft or self.draft, self.catalog, self.policy)

    def test_roundtrip_pins_complete_constraints_without_inventing_scene_or_audio(self):
        snapshot = self.freeze()
        prompt = render_scene_contract(snapshot)
        self.assertTrue(prompt.startswith(PROMPT_START))
        self.assertTrue(prompt.endswith(PROMPT_END))
        self.assertEqual(json.loads(prompt[len(PROMPT_START):-len(PROMPT_END)]), snapshot)
        contract = validate_scene_contract(snapshot, draft=self.draft, catalog_check=self.catalog,
                                           interaction_policy=self.policy)
        self.assertEqual(contract['lockedAssessments'], self.draft['lockedAssessments'])
        self.assertEqual(contract['pagePlan'], self.draft['pagePlan'])
        self.assertNotIn('scenes', contract)
        self.assertNotIn('speech', contract)
        self.draft['pagePlan'][0]['title'] = 'Changed later'
        self.assertNotEqual(snapshot['contract']['pagePlan'], self.draft['pagePlan'])

    def test_missing_or_reordered_pages_and_quiz_coverage_are_rejected(self):
        cases = []
        for mutator in (
            lambda d: d['pagePlan'][1].update(page=3),
            lambda d: d['pagePlan'][1].update(type='video'),
            lambda d: d['pagePlan'][0].update(move=''),
            lambda d: d['pagePlan'][2].update(questionIds=[]),
            lambda d: d['pagePlan'][0].update(questionIds=['school-meeting']),
            lambda d: d['lockedAssessments'].clear(),
            lambda d: d['lockedAssessments'][0].update(page=2),
            lambda d: d['lockedAssessments'].append(deepcopy(d['lockedAssessments'][0])),
            lambda d: d['lockedAssessments'][0].update(answer='C'),
            lambda d: d['lockedAssessments'][0]['choices'][1].update(value='A'),
        ):
            draft = deepcopy(self.draft)
            mutator(draft)
            cases.append(draft)
        for draft in cases:
            with self.subTest(plan=draft['pagePlan'], quizzes=draft['lockedAssessments']):
                with self.assertRaises(ValueError):
                    self.freeze(draft)

    def test_low_reading_requires_real_asset_keys_but_does_not_blanket_high_grades(self):
        draft = deepcopy(self.draft)
        draft['lockedAssessments'][0]['choices'][0].pop('asset')
        with self.assertRaises(ValueError):
            self.freeze(draft)
        draft['binding']['gradeCode'] = 'primary_3'
        self.assertEqual(self.freeze(draft)['contract']['binding']['gradeCode'], 'primary_3')

    def test_teacher_and_grade_cannot_be_downgraded_even_with_recomputed_snapshot_hash(self):
        snapshot = self.freeze()
        snapshot['contract']['binding']['gradeCode'] = 'primary_3'
        snapshot['sha256'] = digest(snapshot['contract'])
        with self.assertRaisesRegex(ValueError, 'original reviewed draft'):
            validate_scene_contract(snapshot, draft=self.draft, catalog_check=self.catalog, interaction_policy=self.policy)
        snapshot['contract']['teacherContract']['subject'] = 'english'
        snapshot['sha256'] = digest(snapshot['contract'])
        with self.assertRaisesRegex(ValueError, 'teacher'):
            validate_scene_contract(snapshot)

    def test_portable_contract_rejects_ambiguous_numeric_values_at_any_depth(self):
        for number in (1.0, 0.0000001, float('nan'), float('inf'), 2 ** 53):
            with self.subTest(number=number):
                draft = deepcopy(self.draft)
                draft['scopeReview']['extra'] = [{'number': number}]
                with self.assertRaisesRegex(ValueError, 'portable JSON'):
                    self.freeze(draft)

    def test_guidance_is_optional_but_cannot_repeat_question_or_reveal_analysis(self):
        draft = deepcopy(self.draft)
        draft['pagePlan'][2].pop('narrationGuidance')
        self.freeze(draft)
        for field in ('analysis', 'question'):
            draft['pagePlan'][2]['narrationGuidance'] = [draft['lockedAssessments'][0][field]]
            with self.assertRaises(ValueError):
                self.freeze(draft)

    def test_changed_catalog_or_policy_is_not_silently_refrozen(self):
        snapshot = self.freeze()
        with self.assertRaises(ValueError):
            validate_scene_contract(snapshot, draft=self.draft,
                                    catalog_check={**self.catalog, 'lessonScopeSha256': 'c' * 64},
                                    interaction_policy=self.policy)
        modified = deepcopy(self.policy)
        modified['policy']['policyId'] += '-future'
        modified['sha256'] = digest(modified['policy'])
        with self.assertRaises(ValueError):
            validate_scene_contract(snapshot, draft=self.draft, catalog_check=self.catalog, interaction_policy=modified)


if __name__ == '__main__':
    unittest.main()
