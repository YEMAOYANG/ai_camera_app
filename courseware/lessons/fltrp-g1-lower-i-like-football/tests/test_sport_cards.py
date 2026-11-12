import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image


ART = Path(__file__).resolve().parents[1] / 'art-source'
MODULE_SPEC = importlib.util.spec_from_file_location('sport_cards', ART / 'draw_sport_cards.py')
CARDS = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(CARDS)
RECIPES = json.loads((ART / 'sport-cards.json').read_text(encoding='utf-8'))


class SportCardLayoutTest(unittest.TestCase):
    def test_layouts_leave_room_for_full_size_cutouts(self):
        with patch.object(CARDS, 'cutout', return_value=Image.new('RGBA', (450, 450), 'navy')):
            for name, recipe in RECIPES.items():
                with self.subTest(name=name):
                    rendered = CARDS.card(recipe)
                    self.assertEqual(rendered.size, tuple(recipe['canvas']))

    def test_same_team_and_sport_have_only_the_speaker_moved(self):
        for self_group, other_group in [('we-football', 'they-football'),
                                         ('quiz-we-ping', 'quiz-they-ping')]:
            with self.subTest(pair=(self_group, other_group)):
                own, other = RECIPES[self_group], RECIPES[other_group]
                self.assertEqual(own['groups'], other['groups'])
                own_parts = {part[0]: part[1:] for part in own['pieces']}
                other_parts = {part[0]: part[1:] for part in other['pieces']}
                self.assertNotEqual(own_parts.pop('mic')[0], other_parts.pop('mic')[0])
                self.assertEqual(own_parts, other_parts)


if __name__ == '__main__':
    unittest.main()
