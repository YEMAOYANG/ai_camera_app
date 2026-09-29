"""Every early-grade choice is drawable; presentation never consumes the key."""
from copy import deepcopy
import unittest

from content import textbook_journey as journey
from content.textbook_picture_questions import presentation
from content.textbook_pedagogy import teaching_profile
from test_textbook_activity import release_fixture


class PictureQuestionTests(unittest.TestCase):
    def test_all_transfer_and_probe_options_have_distinct_pictures_without_answer_data(self):
        cases = [(q, skill, 'transfer') for skill, bank in journey.FLOW['bank'].items() for q in bank]
        cases += [(q, skill, 'probe') for skill, q in journey.FLOW['probes'].items()]
        for q, skill, phase in cases:
            current = {**q, 'skill': skill}
            value = presentation(current, phase)
            self.assertEqual(len({o['picture'] for o in value['options']}), len(q['options']))
            self.assertEqual([o['value'] for o in value['options']], [o['value'] for o in q['options']])
            self.assertNotIn('targets', value)
            changed = {**current, 'targets': ['different-private-answer']}
            self.assertEqual(value, presentation(changed, phase))
            if skill in ('me', 'you', 'he'):
                self.assertIn(value['visual']['speaker'], value['visual']['cast'])
                self.assertIn(value['visual']['listener'], value['visual']['cast'])
                self.assertNotEqual(value['visual']['speaker'], value['visual']['listener'])

    def test_precheck_picture_choices_preserve_first_answer_and_reload(self):
        release = release_fixture()
        state = journey.initial({}, release)
        view = journey.public_view(state, release)['games']
        self.assertTrue(view['visual'])
        self.assertTrue(all(o['picture'] for o in view['options']))
        journey.advance(state, 'games', {'section': 'games', 'action': 'answer', 'choice': 'B', 'version': state['version']}, release)
        saved = deepcopy(state['baseline'])
        self.assertEqual(journey.public_view(state, release)['games']['selectedChoice'], 'B')
        self.assertEqual(state['baseline'], saved)
        self.assertFalse(saved[0]['correct'])

    def test_missing_option_picture_cannot_fall_back_to_a_text_only_choice(self):
        item = {**journey.FLOW['bank']['sky'][0], 'skill': 'sky', 'options': [{'value': 'A', 'label': '未配图'}]}
        with self.assertRaises(ValueError): presentation(item, 'transfer')

    def test_both_early_grades_embed_the_binding_picture_first_policy(self):
        for grade in ('primary_1', 'primary_2'):
            profile = teaching_profile(grade)
            policy = profile['lowReadingPolicy']
            self.assertFalse(policy['independentReadingRequired'])
            self.assertTrue(policy['teacherNarrationRequired'])
            self.assertFalse(policy['systemSpeechFallbackAllowed'])
            self.assertGreaterEqual(profile['minVisualSceneRatio'], .8)
        self.assertNotIn('lowReadingPolicy', teaching_profile('primary_6'))
        self.assertEqual(teaching_profile('primary_6'), teaching_profile('primary_6', version=1))


if __name__ == '__main__': unittest.main()
