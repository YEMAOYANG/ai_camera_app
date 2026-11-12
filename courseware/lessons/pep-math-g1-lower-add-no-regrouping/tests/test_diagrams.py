import json
from pathlib import Path
import runpy
import unittest


LESSON = Path(__file__).resolve().parents[1]
DIAGRAMS = runpy.run_path(str(LESSON / 'art-source' / 'diagrams.py'))


class ShapeRecorder:
    def __init__(self):
        self.dots = []

    def ellipse(self, bounds, *, fill):
        self.dots.append((bounds, fill))

    def rounded_rectangle(self, *args, **kwargs):
        pass

    def text(self, *args, **kwargs):
        pass


class ExactDiagramsTest(unittest.TestCase):
    def test_strips_each_hold_ten_dots_and_loose_dots_keep_their_own_row(self):
        drawing = ShapeRecorder()
        DIAGRAMS['model'](drawing, (10, 10, 360, 240), {'value': 89, 'tens': 8, 'ones': 9})
        strip = [bounds for bounds, fill in drawing.dots if fill == DIAGRAMS['STRIP_DOT']]
        loose = [bounds for bounds, fill in drawing.dots if fill == DIAGRAMS['LOOSE_DOT']]
        self.assertEqual(len(strip), 80)
        self.assertEqual(len(loose), 9)
        self.assertLess(max(bounds[3] for bounds in strip), min(bounds[1] for bounds in loose))

    def test_registered_exact_assets_reproduce_their_png_bytes(self):
        count = 0
        for row, _, data in DIAGRAMS['registered_diagrams']():
            count += 1
            self.assertEqual((LESSON / 'assets' / (row['key'] + '.png')).read_bytes(), data, row['key'])
        self.assertEqual(count, 71)

    def test_picture_answers_match_the_ordered_sums(self):
        specs = json.loads((LESSON / 'art-source' / 'diagram-specs.json').read_bytes())['assets']
        models = {asset['key']: asset['semantics'] for asset in specs}
        lesson = json.loads((LESSON / 'lesson.json').read_bytes())
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        for question in quiz['questions']:
            groups = models[question['visual']['image']]['groups']
            if not isinstance(groups[0], list):
                groups = [groups]
            expected = [sum(part['value'] for part in pair) for pair in groups]
            matching = []
            for key, option in question['options'].items():
                value = models[option['visual']['image']]['option']
                values = value if isinstance(value, list) else [value]
                if [item['value'] for item in values] == expected:
                    matching.append(key)
            self.assertEqual(matching, question['answer'], question['id'])


if __name__ == '__main__':
    unittest.main()
