from copy import deepcopy
import unittest
from unittest.mock import patch

from content import textbook_journey as journey
from content.textbook_journey_registry import definitions, validate_definition
from core.errors import ApiError
from services.report_learning_summary import journey_snapshot, save_journey_report_day
from test_textbook_activity import release_fixture


class JourneyRegistryTests(unittest.TestCase):
    def setUp(self):
        existing = definitions()[0]
        plan, flow = deepcopy(existing.plan), deepcopy(existing.flow)
        plan.update(id='isolated-two-target-test', releaseSha256='b' * 64, quizSkills=['sky', 'earth'])
        plan['skills'] = {k: v for k, v in plan['skills'].items() if k in ('sky', 'earth')}
        flow['skills'] = ['sky', 'earth']
        self.spec = validate_definition(plan, flow, renderer='tiandiren', audio_pack='audio-v2')
        self.release = deepcopy(release_fixture())
        self.release['sha256'] = plan['releaseSha256']
        for scene in self.release['classroom']['scenes']:
            if scene.get('type') == 'quiz':
                scene['content']['questions'] = scene['content']['questions'][:2]
        self.patch = patch('content.textbook_journey_registry.definitions', return_value=(existing, self.spec))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def finish(self, state, section, timestamp):
        for _ in range(100):
            if state[section]['phase'] == 'done':
                return
            current = journey.item(state[section], self.release, state)
            journey.advance(state, section, {'version': state['version'], 'action': 'answer', 'choice': current['targets'][0]}, self.release, timestamp=timestamp)
            journey.advance(state, section, {'version': state['version'], 'action': 'next'}, self.release, timestamp=timestamp)
        self.fail('lesson did not finish')

    def test_two_target_lesson_and_its_two_reviews_keep_their_own_denominator(self):
        state = journey.initial({}, self.release)
        self.finish(state, 'games', 1800000000000)
        self.finish(state, 'challenge', 1800000000000)
        self.assertTrue(journey.complete({'textbookPlay': state}))
        self.assertEqual(journey.public_view(state, self.release)['evidence']['total'], 2)
        self.assertEqual(journey.quiz_result(state, self.release)['independentCorrectCount'], 2)
        save_journey_report_day(state, {})
        self.assertEqual(journey_snapshot(state)['verification'], {'correct': 2, 'total': 2})
        original = deepcopy(state['baseline'])
        for _ in range(2):
            now = state['reviewDueAt']
            journey.advance(state, 'challenge', {'version': state['version'], 'action': 'review'}, self.release, timestamp=now)
            self.finish(state, 'challenge', now)
        self.assertEqual(journey.summary(state)['status'], 'retained')
        self.assertIsNone(state['reviewDueAt'])
        self.assertEqual(state['baseline'], original)
        self.assertEqual(len(journey.initial({}, release_fixture())['games']['queue']), 6)

    def test_cross_lesson_state_and_mismatched_question_count_fail_closed(self):
        state = journey.initial({}, release_fixture())
        with self.assertRaises(ApiError):
            journey.initial({'textbookPlay': state}, self.release)
        changed = deepcopy(self.release)
        for scene in changed['classroom']['scenes']:
            if scene.get('type') == 'quiz':
                scene['content']['questions'].pop()
        with self.assertRaises(ApiError):
            journey.initial({}, changed)

    def test_picture_lesson_cannot_be_enabled_without_scene_and_choice_art(self):
        with self.assertRaises(ValueError):
            validate_definition(self.spec.plan, self.spec.flow, renderer='picture_choices', audio_pack='audio-v2')
        with self.assertRaises(ValueError):
            validate_definition(self.spec.plan, self.spec.flow, renderer='tiandiren', audio_pack='../private')


if __name__ == '__main__':
    unittest.main()
