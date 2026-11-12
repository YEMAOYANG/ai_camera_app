"""Check the lesson's registered playback pictures and writing diagrams."""

from hashlib import sha256
import json
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree


LESSON = Path(__file__).resolve().parents[1]
DIAGRAMS = LESSON / 'art-source' / 'diagrams'


class IllustrationsTest(unittest.TestCase):
    def test_each_picture_matches_its_registered_asset_and_source(self):
        lesson = json.loads((LESSON / 'lesson.json').read_bytes())
        manifest = json.loads((LESSON / 'asset-sources.json').read_bytes())
        assets = {row['key']: row for row in manifest['assets']}
        self.assertEqual(len(assets), len(manifest['assets']))
        self.assertEqual(assets.keys(), lesson['images'].keys())

        for key, image in lesson['images'].items():
            with self.subTest(image=key):
                asset = assets[key]
                self.assertEqual(image['file'], asset['file'])
                self.assertEqual(sha256((LESSON / asset['file']).read_bytes()).hexdigest(), asset['sha256'])
                self.assertEqual(sha256((LESSON / asset['source']).read_bytes()).hexdigest(), asset['sourceSha256'])

        for scene in ('p06', 'p08'):
            with self.subTest(scene=scene):
                budget = manifest['sceneImageBudgets'][scene]
                self.assertEqual(budget['remainingImageKeys'], [])
                actual = {key: (LESSON / assets[key]['file']).stat().st_size for key in budget['imageBytes']}
                self.assertEqual(budget['imageBytes'], actual)
                self.assertLessEqual(sum(actual.values()), budget['targetMaximumBytes'])

    def test_writing_diagrams_accumulate_the_official_strokes_in_order(self):
        strokes = {
            'moon': ('撇', '横折钩', '横', '横'),
            'child': ('撇', '竖弯钩'),
            'head': ('点', '点', '横', '撇', '点'),
            'inside': ('竖', '横折', '横', '横', '竖', '横', '横'),
            'see': ('竖', '横折', '撇', '竖弯钩'),
        }
        for key, sequence in strokes.items():
            diagram = ElementTree.parse(DIAGRAMS / f'strokes-{key}.svg')
            steps = diagram.findall('./{*}g[@data-step]')
            self.assertEqual(len(steps), len(sequence))
            for index, step in enumerate(steps):
                with self.subTest(character=key, step=index + 1):
                    paths = step.findall('./{*}path[@data-stroke]')
                    self.assertEqual(int(step.get('data-step')), index + 1)
                    self.assertEqual(tuple(path.get('data-stroke') for path in paths), sequence[:index + 1])
                    self.assertEqual([path.get('data-current') for path in paths], ['false'] * index + ['true'])

    def test_game_highlights_use_full_canvas_positions(self):
        for page, count in (('shape-snake', 3), ('phrase-delivery', 4)):
            with self.subTest(page=page):
                css = (LESSON / 'pages' / f'{page}.css').read_text(encoding='utf-8')
                self.assertRegex(css, r'\.boat-teacher-anchor\s*\{[^}]*\bposition:\s*fixed\b')
                html = (LESSON / 'pages' / f'{page}.html').read_text(encoding='utf-8')
                boxes = re.findall(r'left:(\d+)px;top:(\d+)px;width:(\d+)px;height:(\d+)px', html)
                self.assertEqual(len(boxes), count)
                for left, top, width, height in (map(int, box) for box in boxes):
                    self.assertLessEqual(left + width, 1280)
                    self.assertLessEqual(top + height, 720)


if __name__ == '__main__':
    unittest.main()
