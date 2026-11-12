"""Verify the counts behind lesson transfer diagrams and the new picture quiz."""
import importlib.util
import json
from pathlib import Path
import unittest

LESSON = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('draw_math', LESSON / 'art-source/draw_math.py')
draw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw)


class KiteMathPictureTest(unittest.TestCase):
    def test_moving_tabs_preserves_count_and_original_color(self):
        self.assertEqual(draw.transfer(4, 7, 3, 'right'), ('o', 'gggggggooo'))
        self.assertEqual(draw.transfer(3, 8, 1, 'left'), ('ooog', 'ggggggg'))
        self.assertEqual(draw.transfer(4, 8, 2, 'right'), ('oo', 'ggggggggoo'))
        with self.assertRaises(ValueError):
            draw.transfer(5, 9, 2, 'right')

    def test_tabs_fill_only_the_cells_their_count_allows(self):
        picture = draw.pair(4, 8)
        def pixel(x, y):
            return picture.getpixel((x, y))[:3]
        self.assertGreater(pixel(36, 47)[0], pixel(36, 47)[1])
        self.assertEqual(pixel(180, 47), (255, 247, 223))
        self.assertGreater(pixel(327, 83)[1], pixel(327, 83)[0])
        self.assertEqual(pixel(363, 83), (255, 247, 223))

    def test_each_new_answer_points_to_the_expected_quantity_picture(self):
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        diagrams = json.loads((LESSON / 'art-source/math-diagrams.json').read_text())
        quiz = next(scene['questions'] for scene in lesson['scenes'] if scene['type'] == 'quiz')
        expected = [
            ('B', ['regroup', [4, 8, 2, 'right'], {}]),
            ('A', ['pair', [4, 9], {}]),
            ('C', ['pair', [9, 2], {'reverse': True}]),
            ('C', ['total', [3], {}]),
            ('A', ['pair', [5, 7], {'moved': True}]),
            ('B', ['shipment', [1], {}]),
        ]
        self.assertEqual(len(quiz), len(expected))
        for question, (key, drawing) in zip(quiz, expected):
            with self.subTest(id=question['id']):
                self.assertEqual(question['answer'], [key])
                image = question['options'][key]['visual']['image']
                self.assertEqual(diagrams[image], drawing)
                self.assertTrue((LESSON / 'assets' / (image + '.png')).is_file())
