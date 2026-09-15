"""Registered past markers use the same answer-blind tense rules in every band."""
from copy import deepcopy
import unittest

from content.formal_objective_rules import (
    objective_question_policy, solve_objective_question, validate_objective_question,
)
from content.primary_skill_boundaries import PRIMARY_SKILL_BOUNDARIES


ARGS = ('primary_6', 'english', 'past_future')


class FormalPastFutureMarkersTest(unittest.TestCase):
    def test_registered_last_week_works_in_all_bands_without_changing_questions(self):
        boundary = next(b for b in PRIMARY_SKILL_BOUNDARIES
                        if (b.grade_code, b.subject, b.skill_id) == ARGS)
        self.assertIn('last week', boundary.allowed_content)
        for band in ('basic', 'standard', 'challenge'):
            original = objective_question_policy(*ARGS, band)['publicPromptExample']
            prompt = original.replace('yesterday', 'last week')
            expected = solve_objective_question(*ARGS, original, band)
            self.assertNotEqual(prompt, original)
            self.assertEqual(solve_objective_question(*ARGS, prompt, band), expected)
            for kind in ('exact_text', 'single_choice'):
                with self.subTest(band=band, kind=kind):
                    question = {'type': kind, 'prompt': prompt, 'answer': expected}
                    if kind == 'single_choice':
                        question.update(answer='correct', choices=[
                            {'id': 'correct', 'label': expected},
                            {'id': 'wrong', 'label': 'incorrect answer'},
                        ])
                    before = deepcopy(question)
                    self.assertEqual(validate_objective_question(*ARGS, question, band), expected)
                    self.assertEqual(question, before)
                    question['answer'] = 'incorrect answer' if kind == 'exact_text' else 'wrong'
                    with self.assertRaises(ValueError):
                        validate_objective_question(*ARGS, question, band)

    def test_last_week_keeps_past_and_future_answers_distinct(self):
        for verb, past in (('walk', 'walked'), ('eat', 'ate'), ('sing', 'sang')):
            for marker, expected, wrong in (
                ('last week', past, 'will ' + verb),
                ('yesterday', past, 'will ' + verb),
                ('tomorrow', 'will ' + verb, past),
            ):
                with self.subTest(verb=verb, marker=marker):
                    prompt = f'填空：She ____ ({verb}) {marker}.'
                    self.assertEqual(solve_objective_question(*ARGS, prompt, 'basic'), expected)
                    with self.assertRaises(ValueError):
                        validate_objective_question(*ARGS,
                            {'type': 'exact_text', 'prompt': prompt, 'answer': wrong}, 'basic')
        # A wrong past claim and correct future claim reverse the standard
        # answer. The same evidence still selects the wrong claim in challenge.
        stem = ('辨析任务：A题【填空：He ____ (eat) last week.】说法【will eat】。'
                'B题【填空：I ____ (go) tomorrow.】说法【will go】。')
        suffix = '按ABC顺序用分号列出；没有则回答none。'
        cases = (
            ('standard', stem + '问题：哪些说法正确？' + suffix, 'B', 'A'),
            ('challenge', stem + 'C题【填空：We ____ (sing) yesterday.】说法【sang】。'
             + '问题：哪些说法错误？' + suffix, 'A', 'B'),
        )
        for band, prompt, expected, wrong in cases:
            with self.subTest(band=band):
                self.assertEqual(validate_objective_question(*ARGS,
                    {'type': 'exact_text', 'prompt': prompt, 'answer': expected}, band), expected)
                with self.assertRaises(ValueError):
                    validate_objective_question(*ARGS,
                        {'type': 'exact_text', 'prompt': prompt, 'answer': wrong}, band)

    def test_unregistered_markers_and_other_tense_modes_remain_closed(self):
        for band in ('basic', 'standard', 'challenge'):
            prompt = objective_question_policy(*ARGS, band)['publicPromptExample']
            for marker in ('last month', 'next week', 'last year', 'every day', 'now'):
                with self.subTest(band=band, marker=marker), self.assertRaises(ValueError):
                    solve_objective_question(*ARGS, prompt.replace('yesterday', marker), band)
            for grade, skill in (('primary_3', 'daily_routines'), ('primary_5', 'present_tenses')):
                other = (grade, 'english', skill)
                prompt = objective_question_policy(*other, band)['publicPromptExample']
                changed = prompt.replace('every day', 'last week').replace('now', 'last week')
                self.assertNotEqual(prompt, changed)
                with self.subTest(other=other, band=band), self.assertRaises(ValueError):
                    solve_objective_question(*other, changed, band)


if __name__ == '__main__':
    unittest.main()
