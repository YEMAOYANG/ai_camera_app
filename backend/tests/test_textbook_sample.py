"""Pedagogical evidence and recovery invariants for the isolated sample."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from services.textbook_sample_service import (
    LESSON, PHASES, QUESTIONS, ROLES, SampleError, activity, apply, new_state, report, view,
)
from scripts.serve_textbook_sample import Store


NOW = 1_800_000_000


def do(state, action, choice=None, now=NOW):
    return apply(state, {'action': action, **({'choice': choice} if choice is not None else {})}, now)


def finish_quiz(state, wrong=None, hinted=None):
    phase = state['phase']
    while state['phase'] == phase:
        item = activity(state)
        if item['skill'] == hinted:
            state = do(state, 'hint')
        answer = item['answer']
        if item['skill'] == wrong:
            answer = next(o['value'] for o in item['options'] if o['value'] != answer)
        state = do(state, 'choose', answer)
        state = do(state, 'next')
    return state


def finish_game(state):
    phase = state['phase']
    while state['phase'] == phase:
        state = do(state, 'choose', activity(state)['answerZones'][0])
        state = do(state, 'next')
    return state


def completed():
    state = do(new_state(NOW), 'start', 'check')
    return finish_quiz(finish_quiz(state))


class LessonEvidenceTests(unittest.TestCase):
    def test_full_play_route_covers_all_six_objectives_and_finishes(self):
        state = do(new_state(NOW), 'start', 'play')
        for choice in ['sky', 'earth', 'teal']:
            state = do(state, 'explore', choice)
        state = finish_game(do(state, 'next'))
        self.assertEqual(state['phase'], 'role-demo')
        state = finish_game(do(state, 'next'))
        state = finish_quiz(finish_quiz(state))
        self.assertEqual(state['phase'], 'complete')
        self.assertEqual(report(state, NOW)['practiceRounds'], 9)
        self.assertEqual(report(state, NOW)['transfer']['independent'], 6)

    def test_no_skip_with_navigation_or_wrong_choice(self):
        state = do(new_state(NOW), 'start', 'play')
        with self.assertRaises(SampleError):
            do(state, 'next')
        for choice in ['sky', 'earth', 'teal']:
            state = do(state, 'explore', choice)
        state = do(state, 'next')
        state = do(state, 'choose', 'earth')
        self.assertFalse(view(state, NOW)['canContinue'])
        self.assertEqual(len(state['practice']), 0)
        with self.assertRaises(SampleError):
            do(state, 'next')
        state = do(state, 'choose', 'sky')
        self.assertEqual(state['practice'][0]['attempts'], 2)

    def test_all_three_children_are_valid_people(self):
        for person in ('coral', 'teal', 'yellow'):
            state = new_state(NOW)
            state.update(phase='hunt', index=2)
            self.assertTrue(do(state, 'choose', person)['current']['solved'])

    def test_speaker_change_changes_me_and_you(self):
        for index, (skill, speaker) in enumerate(ROLES):
            state = new_state(NOW)
            state.update(phase='roles', index=index)
            answer = activity(state)['answerZones'][0]
            self.assertEqual(answer, speaker if skill == 'me' else ('teal' if speaker == 'coral' else 'coral') if skill == 'you' else 'yellow')
        state.update(phase='role-demo')
        state = do(state, 'demo', 'coral')
        self.assertEqual(view(state, NOW)['highlight'], ['coral'])
        state = do(state, 'demo', 'you')
        self.assertEqual(view(state, NOW)['highlight'], ['teal'])

    def test_hint_levels_do_not_expose_game_answer_until_demonstration(self):
        state = new_state(NOW)
        state.update(phase='hunt')
        self.assertNotIn('highlight', view(state, NOW))
        state = do(state, 'hint')
        self.assertNotIn('highlight', view(state, NOW))
        state = do(state, 'hint')
        self.assertEqual(view(state, NOW)['highlight'], ['sky'])
        self.assertEqual(do(state, 'hint')['current']['hintLevel'], 2)

    def test_independent_is_false_after_hint_or_adult_help(self):
        for action in ('hint', 'adult'):
            state = do(new_state(NOW), 'start', 'check')
            state = do(state, action)
            state = do(state, 'choose', activity(state)['answer'])
            self.assertTrue(state['check'][0]['correct'])
            self.assertFalse(state['check'][0]['independent'])

    def test_quiz_hint_uses_story_semantics_not_unrelated_garden_mic(self):
        state = new_state(NOW)
        state.update(phase='transfer', index=1)
        state = do(do(state, 'hint'), 'hint')
        self.assertNotIn('话筒', state['current']['feedback'])
        self.assertEqual(state['current']['feedbackAudio'], ['explain-me'])

    def test_first_attempt_cannot_be_replaced(self):
        state = do(new_state(NOW), 'start', 'check')
        state = do(state, 'choose', 'B')
        with self.assertRaises(SampleError):
            do(state, 'choose', 'A')
        with self.assertRaises(SampleError):
            do(state, 'hint')
        self.assertFalse(state['check'][0]['correct'])

    def test_only_weak_or_helped_objectives_receive_repair(self):
        state = do(new_state(NOW), 'start', 'check')
        state = finish_quiz(state, wrong='you', hinted='earth')
        self.assertEqual(state['phase'], 'repair')
        self.assertEqual(state['repairSkills'], ['earth', 'you'])
        before = deepcopy(state['check'])
        state = finish_game(state)
        self.assertEqual(state['check'], before)
        self.assertEqual(state['phase'], 'transfer')

    def test_fast_path_still_requires_fresh_contexts(self):
        state = finish_quiz(do(new_state(NOW), 'start', 'check'))
        self.assertEqual(state['phase'], 'transfer')
        self.assertFalse(report(state, NOW)['completed'])
        self.assertEqual(report(finish_quiz(state), NOW)['practiceRounds'], 0)

    def test_no_delayed_review_before_server_due_time(self):
        state = completed()
        self.assertEqual(state['reviewDueAt'], NOW + 86400)
        with self.assertRaises(SampleError):
            do(state, 'review', 'due', NOW + 86399)
        self.assertEqual(do(state, 'review', 'due', NOW + 86400)['phase'], 'review')

    def test_preview_never_produces_delayed_evidence_or_resets_due_time(self):
        state = completed()
        state = do(state, 'review', 'preview')
        self.assertTrue(view(state, NOW)['question']['id'].startswith('transfer-'))
        state = finish_quiz(state)
        self.assertEqual(state['phase'], 'complete')
        self.assertEqual(state['review'], [])
        self.assertEqual(state['reviewDueAt'], NOW + 86400)
        self.assertEqual(report(state, NOW)['review']['answered'], 0)

    def test_replay_preserves_original_evidence_and_review_date(self):
        original = completed()
        state = do(original, 'replay')
        for choice in ['sky', 'earth', 'teal']:
            state = do(state, 'explore', choice)
        state = finish_game(do(state, 'next'))
        state = finish_game(do(state, 'next'))
        self.assertEqual(state['phase'], 'complete')
        self.assertFalse(state['replaying'])
        self.assertEqual(state['check'], original['check'])
        self.assertEqual(state['transfer'], original['transfer'])
        self.assertEqual(state['reviewDueAt'], original['reviewDueAt'])
        self.assertEqual(len(state['replayPractice']), 9)
        self.assertEqual(report(state, NOW)['practiceRounds'], 0)

    def test_actual_review_is_separate_and_not_repeatable_as_new_evidence(self):
        state = do(completed(), 'review', 'due', NOW + 86400)
        while state['phase'] == 'review':
            state = do(state, 'choose', activity(state)['answer'], NOW + 86401)
            state = do(state, 'next', now=NOW + 86401)
        self.assertEqual(state['phase'], 'review-complete')
        self.assertEqual(report(state, NOW + 86402)['review']['independent'], 6)
        with self.assertRaises(SampleError):
            do(state, 'review', 'due', NOW + 86402)

    def test_no_private_answers_or_future_items_in_unanswered_view(self):
        for phase in ('check', 'transfer', 'review', 'review-preview'):
            state = new_state(NOW)
            state.update(phase=phase)
            public = view(state, NOW)
            encoded = json.dumps(public)
            self.assertNotIn('"answer"', encoded)
            self.assertNotIn('"explanation"', encoded)
            self.assertNotIn('"skills"', encoded)
            self.assertNotIn('"spoken"', encoded)
            self.assertEqual(len(public['question']['options']), 3)

    def test_invalid_choices_and_client_scores_are_rejected(self):
        state = do(new_state(NOW), 'start', 'check')
        for data in ({'action': 'choose', 'choice': 'D'}, {'action': 'choose', 'choice': 'A', 'score': 100}, {'action': 'complete'}):
            with self.assertRaises(SampleError):
                apply(state, data, NOW)

    def test_report_never_claims_reading_writing_or_saved_parent_minutes(self):
        result = report(completed(), NOW)
        self.assertTrue(result['sampleOnly'])
        self.assertIn('口头朗读准确性', result['notAssessed'])
        self.assertFalse(result['interventionSuggested'])
        self.assertNotIn('mastery', result)

    def test_content_allows_only_declared_learning_scope(self):
        self.assertEqual(set(LESSON['skills']), {'sky', 'earth', 'person', 'me', 'you', 'he'})
        for group in ('check', 'transfer', 'review'):
            questions = [q for q in QUESTIONS.values() if q['id'].startswith(group + '-')]
            self.assertEqual({q['skill'] for q in questions}, set(LESSON['skills']))
            for q in questions:
                self.assertEqual(sum(o['value'] == q['answer'] for o in q['options']), 1)
                self.assertEqual(len({o['label'] for o in q['options']}), 3)
                target = LESSON['skills'][q['skill']]['word']
                self.assertNotIn(target, q.get('displayPrompt', q['prompt']), 'Avoid visual copying of the target character from the question.')
        self.assertFalse(LESSON['publicationAllowed'])


class SamplePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'isolated.sqlite3'
        self.store = Store(self.path)
        self.sid, _, _ = self.store.session(None, NOW)

    def tearDown(self):
        self.temp.cleanup()

    def test_lost_response_retry_is_idempotent_and_restart_restores_state(self):
        request = {'requestId': str(uuid4()), 'revision': 0, 'action': 'start', 'choice': 'check'}
        first = self.store.act(self.sid, request, NOW)
        self.assertEqual(self.store.act(self.sid, request, NOW + 1), first)
        restored = Store(self.path).session(self.sid, NOW + 2)[1]
        self.assertEqual(restored['phase'], 'check')
        self.assertEqual(restored['revision'], 1)

    def test_conflicting_duplicate_and_stale_revision_cannot_write(self):
        request = {'requestId': str(uuid4()), 'revision': 0, 'action': 'start', 'choice': 'check'}
        self.store.act(self.sid, request, NOW)
        with self.assertRaises(SampleError):
            self.store.act(self.sid, {**request, 'choice': 'play'}, NOW)
        with self.assertRaises(SampleError):
            self.store.act(self.sid, {**request, 'requestId': str(uuid4())}, NOW)
        self.assertEqual(self.store.session(self.sid, NOW)[1]['revision'], 1)

    def test_another_session_cannot_inherit_results(self):
        other, _, _ = self.store.session(None, NOW)
        self.store.act(self.sid, {'requestId': str(uuid4()), 'revision': 0, 'action': 'start', 'choice': 'check'}, NOW)
        self.assertEqual(self.store.session(other, NOW)[1]['phase'], 'welcome')


if __name__ == '__main__':
    unittest.main()
