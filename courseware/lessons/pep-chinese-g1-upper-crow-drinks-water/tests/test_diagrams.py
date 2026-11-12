"""Verify bottle continuity, writing exemplars, and local media provenance."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import ImageColor

LESSON = Path(__file__).resolve().parent.parent
spec = spec_from_file_location('crow_story_diagrams', LESSON / 'diagrams' / 'render.py')
art = module_from_spec(spec)
spec.loader.exec_module(art)


class DiagramsTest(unittest.TestCase):
    def test_three_stages_keep_mouth_and_raise_the_water_line(self):
        drawings = [art.bottle(i, guides=tuple(range(i))) for i in range(3)]
        for a, b in zip(drawings, drawings[1:]):
            self.assertEqual(a.crop((0, 0, 200, 56)).tobytes(),
                             b.crop((0, 0, 200, 56)).tobytes())
        self.assertGreater(art.WATER_ROWS[0], art.WATER_ROWS[1])
        self.assertGreater(art.WATER_ROWS[1], art.WATER_ROWS[2])
        for i, im in enumerate(drawings):
            self.assertEqual(im.getpixel((100, art.WATER_ROWS[i]))[:3],
                             ImageColor.getrgb(art.WATERLINE))
            for previous in art.WATER_ROWS[:i]:
                self.assertEqual(im.getpixel((68, previous))[:3], ImageColor.getrgb('#fff9ec'))

    def test_single_original_pebble_is_repeated_in_the_three_stages(self):
        for count, stage in ((0, 0), (6, 1), (12, 2)):
            with patch.object(art, 'stamp') as stamp:
                art.bottle(stage)
            calls = stamp.call_args_list
            self.assertEqual(len(calls), count)
            self.assertTrue(all(call.args[1] == 'stone-one' for call in calls))
            self.assertEqual(len({call.args[2] for call in calls}), count)

    def test_writing_cards_contain_only_the_five_assigned_forms(self):
        self.assertEqual(list(art.STROKES), list('只石多出个'))
        self.assertEqual([len(rows) for rows in art.STROKES.values()], [5, 5, 6, 5, 3])
        self.assertEqual(art.STROKES['个'][-1], [(50, 43), (50, 86)])
        self.assertEqual(art.STROKES['出'][0], [(29, 23), (29, 46), (72, 46)])
        self.assertTrue(all(0 < n < 100 for rows in art.STROKES.values()
                            for path in rows for point in path for n in point))

    def test_boat_frames_share_an_orientation_and_identical_stern_position(self):
        idle, blow = [art.aligned_boat(k) for k in ('boat-idle', 'boat-blow')]
        self.assertEqual(idle.size, blow.size)
        idle_box, blow_box = [im.getchannel('A').point(lambda v: 255 if v >= 16 else 0).getbbox()
                              for im in (idle, blow)]
        self.assertEqual(idle_box[0], blow_box[0])
        self.assertGreater(blow_box[2], idle_box[2])

    def test_provenance_and_quiz_registration(self):
        manifest = json.loads((LESSON / 'asset-sources.json').read_text())['assets']
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        for key, row in manifest.items():
            with self.subTest(asset=key):
                self.assertEqual(sha256((LESSON / row['file']).read_bytes()).hexdigest(), row['sha256'])
        self.assertTrue(set(lesson['images']) <= manifest.keys())
        quiz = next(s for s in lesson['scenes'] if s['type'] == 'quiz')
        self.assertEqual([row['answer'][0] for row in quiz['questions']], list('ABCBAC'))
        for row in quiz['questions']:
            self.assertTrue(all(op['visual']['image'] in lesson['images'] for op in row['options'].values()))
