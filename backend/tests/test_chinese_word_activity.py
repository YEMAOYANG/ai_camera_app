"""Sequential word observations cannot weaken the picture-answer gate."""
from copy import deepcopy
import unittest

from content.chinese_word_activity import cards_scene, word_picture
from services.textbook_batch_queue_audio_service import _Markup, _reviewed_word_observation


class ReviewedWordObservations(unittest.TestCase):
    def setUp(self):
        self.cards = [{'character': c, 'assetId': 'word'+str(i), 'cueId': 'word'+str(i)}
                      for i, c in enumerate('眼睛晴')]
        self.assets = {card['assetId']: word_picture(key, card['character'])
                       for card, key in zip(self.cards, ['eyes', 'eyes', 'sunny'])}
        self.scene = {'sceneId': 'cards', 'title': '听一听，看一看', 'cards': self.cards,
                      'initialCueId': 'intro', 'resetCueId': 'reset',
                      'completeCueId': 'complete', 'writeCueId': 'write',
                      'finiteCues': [{'cueId': key, 'teacherText': '看图片，听老师说。'}
                                     for key in ['intro', 'reset', 'complete', 'write', 'word0', 'word1', 'word2']]}
        self.frozen = {'binding': {'subject': 'chinese'},
            'reviewedLessonScope': {'recognizedCharacters': list('眼睛晴')},
            'activityDesign': {'lessonFamily': 'chinese_word_contexts_v1', 'scenes': [self.scene],
                'assetPlan': [{'assetId': key, 'svgMarkup': svg} for key, svg in self.assets.items()]}}

    def test_shared_context_is_valid_only_in_exact_sequential_observations(self):
        source = cards_scene(self.scene, self.assets)
        self.assertTrue(_reviewed_word_observation(self.frozen, {'id': 'cards'}, source))
        markup = _Markup(source)
        self.assertEqual(markup.choices, [])
        cards = [a for tag, a in markup.tags if 'data-mira-word-card' in a]
        self.assertEqual([a['data-mira-word-card'] for a in cards], list('眼睛晴'))
        self.assertEqual(sum('hidden' not in a for a in cards), 1)

    def test_answer_choices_changed_behavior_wrong_scope_and_missing_word_rejected(self):
        source = cards_scene(self.scene, self.assets)
        for altered in [source.replace('data-mira-word-card', 'data-mira-picture-choice'),
                        source.replace(' hidden', ''), source.replace('current++;readCard()', 'current+=2;readCard()')]:
            self.assertFalse(_reviewed_word_observation(self.frozen, {'id': 'cards'}, altered))
        self.assertFalse(_reviewed_word_observation(self.frozen, {'id': 'another-scene'}, source))
        changed = deepcopy(self.frozen)
        changed['reviewedLessonScope']['recognizedCharacters'].append('情')
        self.assertFalse(_reviewed_word_observation(changed, {'id': 'cards'}, source))

    def test_target_text_alone_cannot_make_identical_contexts_meaningful(self):
        assets = {card['assetId']: word_picture('eyes', card['character']) for card in self.cards}
        self.frozen['activityDesign']['assetPlan'] = [{'assetId': key, 'svgMarkup': svg} for key, svg in assets.items()]
        self.assertFalse(_reviewed_word_observation(self.frozen, {'id': 'cards'}, cards_scene(self.scene, assets)))


if __name__ == '__main__':
    unittest.main()
