"""Exercise the real stdin bridge without a Provider, browser or database."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from content.formal_objective_rules import objective_question_policy


CLI = Path(__file__).resolve().parents[1] / 'content/formal_question_preflight_cli.py'


class FormalQuestionPreflightCliTest(unittest.TestCase):
    def request(self, grade='primary_6', subject='english', skill='past_future', band='standard'):
        return {'gradeCode': grade, 'subject': subject, 'skillId': skill,
            'objectivePolicy': objective_question_policy(grade, subject, skill, band),
            # Invalid empty question shells should become bounded repair issues,
            # after successful authority checking, rather than an unavailable Host.
            'questions': [{} for _ in range(5)]}

    def run_bridge(self, request):
        return subprocess.run([sys.executable, '-B', str(CLI)],
            input=json.dumps(request, ensure_ascii=False), text=True,
            capture_output=True, timeout=10, check=False)

    def test_registered_english_policies_survive_the_json_round_trip(self):
        for grade, skill in (('primary_2', 'actions_abilities'), ('primary_3', 'daily_routines'),
                            ('primary_5', 'present_tenses'), ('primary_6', 'past_future'),
                            ('primary_6', 'grammar_in_context')):
            for band in ('basic', 'standard', 'challenge'):
                with self.subTest(grade=grade, skill=skill, band=band):
                    request = self.request(grade=grade, skill=skill, band=band)
                    result = self.run_bridge(request)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    output = json.loads(result.stdout)
                    self.assertEqual(set(output), {'schemaVersion', 'issues'})
                    self.assertEqual(output['schemaVersion'], 'mira.formal-objective-preflight.v1')
                    self.assertEqual([issue['question'] for issue in output['issues']], [1, 2, 3, 4, 5])

    def test_registered_non_english_authority_is_unchanged(self):
        for subject, skill in (('math', 'fraction_ratio_percentage'), ('chinese', 'language_application')):
            with self.subTest(subject=subject):
                result = self.run_bridge(self.request(subject=subject, skill=skill))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(json.loads(result.stdout)['issues']), 5)

    def test_changed_missing_or_boolean_numeric_policy_fields_are_rejected(self):
        original = json.loads(json.dumps(self.request()))
        mutations = (
            lambda p: p['verbs']['walk'].__setitem__(2, 'walk'),
            lambda p: p.pop('verbs'),
            lambda p: p.update(extra=True),
            lambda p: p.update(difficultyCode='basic'),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                request = deepcopy(original)
                mutate(request['objectivePolicy'])
                result = self.run_bridge(request)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('preflight objective authority mismatch', result.stderr)
                self.assertEqual(result.stdout, '')
        # Python's ordinary equality accepts 1 == True; the transport contract
        # must preserve the registered JSON scalar type as well as its value.
        def numeric_paths(value, path=()):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield from numeric_paths(child, (*path, key))
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    yield from numeric_paths(child, (*path, index))
            elif type(value) is int and value in (0, 1):
                yield path
        numeric_original = json.loads(json.dumps(self.request(band='basic')))
        paths = list(numeric_paths(numeric_original['objectivePolicy']))
        self.assertTrue(paths, 'fixture must cover a registered numeric 0 or 1')
        request = deepcopy(numeric_original)
        target = request['objectivePolicy']
        for key in paths[0][:-1]:
            target = target[key]
        key = paths[0][-1]
        target[key] = bool(target[key])
        result = self.run_bridge(request)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('preflight objective authority mismatch', result.stderr)


if __name__ == '__main__':
    unittest.main()
