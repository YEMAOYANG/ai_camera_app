"""Check the exact arithmetic behind the newly drawn lantern cards."""
import importlib.util
import json
from pathlib import Path
import unittest

LESSON = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('draw_lanterns', LESSON / 'art-source/draw_lanterns.py')
draw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw)


class LanternPictureTest(unittest.TestCase):
    def test_make_ten_fills_only_the_intended_group(self):
        left = draw.make_ten(9, 6, 1)
        right = draw.make_ten(9, 6, 4, right=True)
        self.assertGreater(left.getpixel((201, 92))[1], left.getpixel((201, 92))[0])
        self.assertGreater(right.getpixel((470, 92))[0], right.getpixel((470, 92))[1])
        with self.assertRaises(ValueError):
            draw.make_ten(9, 6, 2)

    def test_grid_rows_preserve_sum_and_columns_preserve_first_addend(self):
        table = draw.table([10,11,12,13,14], 'directions')
        self.assertEqual(table.size, (610,315))
        # Upper right and lower left both have second addend four.
        self.assertEqual(table.getpixel((500,22))[:3], (39,132,101))
        self.assertEqual(table.getpixel((100,196))[:3], (39,132,101))
        self.assertNotEqual(table.getpixel((100,22))[:3], (39,132,101))

    def test_quiz_expected_answers_use_new_quantity_pictures(self):
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        diagrams = json.loads((LESSON / 'art-source/lantern-math.json').read_text())
        quiz = next(s['questions'] for s in lesson['scenes'] if s['type'] == 'quiz')
        expected = [
            ('A','make_ten',[9,6,1]),('C','pair',[7,8]),('B','total',[11]),
            ('A','one_group',[6]),('B','total',[16]),('C','pair',[6,7]),
        ]
        self.assertEqual(len(quiz), len(expected))
        for question, (key, kind, params) in zip(quiz, expected):
            with self.subTest(id=question['id']):
                self.assertEqual(question['answer'], [key])
                visual = question['options'][key]['visual']['image']
                self.assertEqual(diagrams[visual][:2], [kind,params])
