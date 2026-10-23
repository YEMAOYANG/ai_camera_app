"""Server-owned question sampling; no provider, database, or course mutations."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from content.textbook_catalog import validate_manifest
from content.textbook_preview import (UNITS_PATH, blueprint_prompt, blueprint_question_count,
                                     lesson_blueprint, operator_preview_input, preview_checks)
from core.errors import ApiError


class AssessmentMappingTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json'
        self.manifest = validate_manifest(json.loads(path.read_text()))
        self.blueprint = lesson_blueprint(self.manifest, 'u3-l6')
        self.room = {'scenes': [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]}
        self.author = dict(mode='openmaic_pro_workbench', sessionId='fixture-session',
                           stageId='fixture-stage', skillIds=['fixture'], request='制作已审范围。',
                           imageProvenance='synthetic fixture, no generated media')

    def test_three_reviewed_samples_keep_five_goals_and_exact_question_count(self):
        b = self.blueprint
        self.assertEqual(len(b['targets']), 5)
        self.assertEqual(blueprint_question_count(b), 3)
        self.assertEqual(blueprint_prompt(b)['expectedQuestionCount'], 3)
        self.assertIn('取样目标1、2、3', blueprint_prompt(b)['instructions'][2])
        result = operator_preview_input(self.manifest, 'u3-l6', self.room, {}, self.author)
        self.assertEqual(result['previewPrompt']['targets'], b['targets'])
        self.assertEqual(result['previewPrompt']['expectedQuestionCount'], 3)
        room = {'scenes': [{'type': 'quiz', 'content': {'questions': [{}] * 3}}]}
        self.assertNotIn('question_count_mismatch', preview_checks(room, 1, expected_question_count=3)['issues'])
        self.assertIn('question_count_mismatch', preview_checks(room, 1, expected_question_count=5)['issues'])

    def test_five_samples_or_missing_mapping_keep_historical_count(self):
        b = deepcopy(self.blueprint)
        b['assessmentMapping'] = [dict(targetIndex=i, questionId=f'fixture-{i}', page=i+1) for i in range(5)]
        for mapped in (True, False):
            if not mapped:
                b.pop('assessmentMapping')
            self.assertEqual(blueprint_question_count(b), 5)
            self.assertEqual(blueprint_prompt(b)['expectedQuestionCount'], 5)
            with patch('content.textbook_preview.lesson_blueprint', return_value=b):
                self.assertEqual(operator_preview_input(self.manifest, 'u3-l6', self.room, {}, self.author)
                                 ['previewPrompt']['expectedQuestionCount'], 5)
        self.assertIn('每道题按目标列表顺序覆盖一个目标。', blueprint_prompt(b)['instructions'][2])

    def test_repeated_target_samples_do_not_claim_one_question_per_goal(self):
        b = deepcopy(self.blueprint)
        b['assessmentMapping'] = [dict(targetIndex=i, questionId=f'fixture-{n}', page=n+1)
                                  for n, i in enumerate([0, 0, 1, 2, 3])]
        self.assertEqual(blueprint_question_count(b), 5)
        self.assertIn('取样目标1、1、2、3、4', blueprint_prompt(b)['instructions'][2])
        self.assertNotIn('每道题按目标列表顺序覆盖一个目标。', blueprint_prompt(b)['instructions'][2])

    def test_explicit_invalid_mapping_cannot_fall_back_or_reduce_questions(self):
        good = self.blueprint['assessmentMapping']
        bad = [None, [], {}, '3', good * 11, [None], [good[0], good[0]]]
        for key, values in {'targetIndex': [-1, 5, True, '0', [0, 1]],
                            'questionId': ['', ' q', 1], 'page': [0, 61, True, '6']}.items():
            bad.extend([{**good[0], key: value}] for value in values)
        bad.append([{k: v for k, v in good[0].items() if k != 'targetIndex'}])
        for mapping in bad:
            b = {**self.blueprint, 'assessmentMapping': mapping}
            with self.subTest(mapping=mapping), self.assertRaises(ApiError):
                blueprint_prompt(b)
            with patch('content.textbook_preview.lesson_blueprint', return_value=b), self.assertRaises(ApiError):
                operator_preview_input(self.manifest, 'u3-l6', self.room, {}, self.author)

    def test_caller_question_count_is_never_an_operator_override(self):
        with self.assertRaises(ApiError):
            operator_preview_input(self.manifest, 'u3-l6', self.room, {},
                                   {**self.author, 'expectedQuestionCount': 1})
        spoofed = {**self.room, 'assessmentMapping': [], 'expectedQuestionCount': 1}
        result = operator_preview_input(self.manifest, 'u3-l6', spoofed, {}, self.author)
        self.assertEqual(result['previewPrompt']['expectedQuestionCount'], 3)

    def test_all_previous_registered_units_keep_their_counts(self):
        for path in UNITS_PATH.glob('*.json'):
            if path.name == 'primary1-pinyin-garden3.v1.json':
                continue
            for b in json.loads(path.read_text())['lessons']:
                with self.subTest(path=path.name, node=b['nodeId']):
                    self.assertEqual(blueprint_question_count(b), len(b['targets']))


if __name__ == '__main__':
    unittest.main()
