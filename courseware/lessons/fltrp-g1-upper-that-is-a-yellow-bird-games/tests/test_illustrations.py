import importlib.util
import json
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('yellow_bird_illustrations', ROOT / 'illustrations.py')
ILLUSTRATIONS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ILLUSTRATIONS
SPEC.loader.exec_module(ILLUSTRATIONS)


class IllustrationTests(unittest.TestCase):
    def test_all_derived_images_have_a_recipe_and_an_original_dependency(self):
        plan = json.loads((ROOT / 'art-plan.json').read_text(encoding='utf-8'))
        lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        originals = {record['key'] for record in plan['sourceAssets']}
        self.assertEqual(set(ILLUSTRATIONS.CARDS), set(lesson['images']) - originals)
        for key, card in ILLUSTRATIONS.CARDS.items():
            with self.subTest(key=key):
                self.assertTrue(set(card.inputs) <= originals)
                for item in card.items:
                    self.assertGreaterEqual(item.x - item.width / 2, 0)
                    self.assertLessEqual(item.x + item.width / 2, ILLUSTRATIONS.SIZE[0])
                    self.assertGreaterEqual(item.baseline - item.height, 0)
                    self.assertLessEqual(item.baseline, ILLUSTRATIONS.SIZE[1])

    def test_moving_speaker_changes_distance_to_the_same_desk_and_bird(self):
        layouts = ILLUSTRATIONS.CARDS
        for near_key, far_key in (
            ('near-desk-example', 'far-desk-example'),
            ('quiz-reporter-right-near-black', 'quiz-reporter-left-far-black'),
        ):
            near, far = layouts[near_key], layouts[far_key]
            self.assertEqual(near.items[1], far.items[1])
            self.assertLess(abs(near.items[0].x - near.items[1].x), 170)
            self.assertGreater(abs(far.items[0].x - far.items[1].x), 270)
        self.assertTrue(layouts['quiz-reporter-right-near-black'].items[0].mirror)
        self.assertFalse(layouts['quiz-reporter-left-far-black'].items[0].mirror)
        self.assertEqual(layouts['quiz-reporter-stimulus'].items,
                         layouts['quiz-reporter-right-near-black'].items[:1])

    def test_courtyard_question_cards_follow_the_answer_choices(self):
        lesson = json.loads((ROOT / 'lesson.json').read_text(encoding='utf-8'))
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        expected = {
            'hear-bag-at-fair': ['quiz-fair-cat', 'quiz-fair-schoolbag', 'quiz-fair-blue-bird'],
            'hear-far-blue-bird': ['quiz-courtyard-near-blue', 'quiz-courtyard-far-black', 'quiz-courtyard-far-blue'],
            'hear-near-black-cat': [
                'quiz-courtyard-near-black-cat', 'quiz-courtyard-far-black-cat', 'quiz-courtyard-near-cream-cat',
            ],
            'hear-cap-in-display': [
                'quiz-courtyard-display-cat', 'quiz-courtyard-display-knit-hat', 'quiz-courtyard-display-baseball-cap',
            ],
            'new-speaker-near-black-bird': [
                'quiz-reporter-stimulus', 'quiz-reporter-right-near-black', 'quiz-reporter-left-far-black',
                'quiz-reporter-right-near-blue',
            ],
            'hear-far-my-desk': [
                'quiz-school-near-desk', 'quiz-school-far-desk', 'quiz-school-far-schoolbag',
            ],
        }
        for question in quiz['questions']:
            with self.subTest(question=question['id']):
                keys = [question['visual']['image']] if 'visual' in question else []
                keys.extend(option['visual']['image'] for option in question['options'].values())
                courtyard_keys = [key for key in keys if ILLUSTRATIONS.CARDS[key].background == ILLUSTRATIONS.COURTYARD]
                self.assertEqual(courtyard_keys, expected.get(question['id'], []))
        self.assertEqual(quiz['questions'][0]['options']['a']['visual']['image'], 'quiz-fair-cat')
        self.assertNotEqual(quiz['questions'][3]['options']['a']['visual']['image'], 'quiz-fair-cat')

    def test_black_cat_choices_separate_distance_and_color(self):
        cards = ILLUSTRATIONS.CARDS
        near = cards['quiz-courtyard-near-black-cat']
        far = cards['quiz-courtyard-far-black-cat']
        cream = cards['quiz-courtyard-near-cream-cat']
        self.assertEqual(near.items[0], far.items[0])
        self.assertEqual(near.items[0], cream.items[0])
        self.assertEqual(near.items[1].asset, far.items[1].asset)
        self.assertLess(near.items[1].x, far.items[1].x)
        self.assertEqual(near.items[1].x, cream.items[1].x)
        self.assertNotEqual(near.items[1].asset, cream.items[1].asset)

    def test_opaque_exhibits_and_other_options_share_a_frame(self):
        cards = ILLUSTRATIONS.CARDS
        desk_group = ('quiz-school-near-desk', 'quiz-school-far-desk', 'quiz-school-far-schoolbag')
        for group in (
            ('quiz-fair-cat', 'quiz-fair-schoolbag', 'quiz-fair-blue-bird'),
            desk_group,
        ):
            placements = [cards[key].items[-1] for key in group]
            self.assertTrue(all(item.framed for item in placements))
            self.assertEqual(len({(item.width, item.height, item.baseline) for item in placements}), 1)
        near, far, other = (cards[key].items[-1] for key in desk_group)
        self.assertEqual(near.asset, far.asset)
        self.assertLess(near.x, far.x)
        self.assertEqual(far.x, other.x)
        opaque = Image.new('RGB', (120, 90), '#a15444')
        frame = ILLUSTRATIONS.framed_exhibit(opaque, far)
        self.assertEqual(frame.size, (far.width, far.height))
        self.assertEqual(frame.getpixel((far.width // 2, 1))[:3], (216, 190, 149))
        self.assertEqual(frame.getpixel((far.width // 2, far.height // 2))[:3], (161, 84, 68))

    def test_guide_and_bird_render_in_separate_unclipped_regions(self):
        card = ILLUSTRATIONS.CARDS['quiz-reporter-right-near-black']
        guide = Image.new('RGBA', (160, 240))
        ImageDraw.Draw(guide).rectangle((25, 15, 135, 225), fill=(12, 90, 31, 255))
        bird = Image.new('RGBA', (180, 130))
        ImageDraw.Draw(bird).ellipse((12, 12, 167, 117), fill=(8, 15, 22, 255))
        result = ILLUSTRATIONS.render(card, {
            ILLUSTRATIONS.COURTYARD: Image.new('RGB', (640, 380), '#c8d9af'),
            'lookout-guide': guide,
            'black-bird': bird,
        })
        self.assertEqual(result.size, (640, 380))
        self.assertEqual(result.getpixel((535, 226)), (12, 90, 31))
        self.assertEqual(result.getpixel((382, 270)), (8, 15, 22))
        self.assertNotEqual(result.getpixel((463, 270)), (8, 15, 22))

    def test_playback_copy_keeps_proportions_and_transparent_edges(self):
        source = Image.new('RGBA', (400, 200))
        ImageDraw.Draw(source).rectangle((100, 30, 300, 170), fill=(230, 155, 42, 255))
        preview = ILLUSTRATIONS.playback_image(source, (120, 120))
        self.assertEqual(source.size, (400, 200))
        self.assertEqual(preview.size, (120, 60))
        self.assertEqual(preview.getpixel((0, 0))[3], 0)
        self.assertEqual(preview.getpixel((60, 30)), (230, 155, 42, 255))
