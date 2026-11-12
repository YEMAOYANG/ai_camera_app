import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

from PIL import Image


SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('how_many_game_compositions', SOURCE / 'game_compositions.py')
GAME_ART = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(SOURCE))
try:
    SPEC.loader.exec_module(GAME_ART)
finally:
    sys.path.pop(0)


class ArcadeSourceTests(unittest.TestCase):
    def test_target_icons_preserve_every_boat_without_overlap(self):
        sprite = Image.new('RGBA', (40, 40), (100, 20, 180, 255))
        for count in GAME_ART.BOAT_COUNTS:
            with self.subTest(count=count):
                alpha = GAME_ART.boat_target(sprite, count).getchannel('A')
                # Exact full-area count catches overlaps or clipping at icon edges.
                self.assertEqual(alpha.histogram()[255], 36 * 36 * count)

    def test_step_cues_are_teacher_recordings_and_reveal_only_the_english_word(self):
        lesson = json.loads((SOURCE / 'lesson.json').read_text(encoding='utf-8'))
        lines = {f'{scene["key"]}-{index}': beat['say']
                 for scene in lesson['scenes'] if scene['type'] == 'slide'
                 for index, beat in enumerate(scene['script'], 1)
                 if 'say' in beat and 'by' not in beat}
        for scene in lesson['scenes']:
            if scene['type'] != 'interactive':
                continue
            with self.subTest(scene=scene['key']):
                page = (SOURCE / 'pages' / f'{scene["page"]}.js').read_text(encoding='utf-8')
                step_lists = re.findall(r'steps:\[([^\]]+)\]', page)
                self.assertEqual(len(step_lists), 3)
                for step_list in step_lists:
                    for cue in re.findall(r"'([a-z-]+)'", step_list):
                        self.assertTrue(cue.startswith('word-'))
                        self.assertEqual(lines[scene['gameAudio'][cue]], cue[5:].capitalize() + '.')
                for cue in re.findall(r"(?:goal|hint|hint2|praise):'([a-z-]+)'", page):
                    self.assertIn(scene['gameAudio'][cue], lines)
