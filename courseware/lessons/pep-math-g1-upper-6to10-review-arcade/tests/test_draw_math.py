import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import ImageColor


LESSON = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('draw_math', LESSON/'art-source'/'draw_math.py')
DRAW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRAW)


class DiagramsTest(unittest.TestCase):
    def test_render_is_deterministic_and_covers_registered_diagrams(self):
        lesson = json.loads((LESSON/'lesson.json').read_text())
        proof = json.loads((LESSON/'asset-provenance.json').read_text())
        registered = {key for key, record in proof['assets'].items()
                      if record['kind'] == 'deterministic_semantic_diagram'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            one = DRAW.write_assets(path/'one')
            two = DRAW.write_assets(path/'two')
            self.assertEqual(one, two)
            self.assertEqual(set(one), registered)
            for key, record in one.items():
                self.assertEqual(record['file'], lesson['images'][key]['file'])
                self.assertEqual((path/'one'/(key+'.png')).read_bytes(),
                                 (LESSON/record['file']).read_bytes())

    def test_nine_slots_show_four_filled_and_five_empty(self):
        stem = DRAW.quiz_nine().image
        centers = [(204+i%3*63, 117+i//3*63) for i in range(9)]
        colors = [stem.getpixel(xy) for xy in centers]
        self.assertEqual(colors, [ImageColor.getrgb(DRAW.GREEN)]*4+[ImageColor.getrgb(DRAW.CREAM)]*5)

    def test_only_the_third_chip_from_left_is_the_seventh_from_right(self):
        orange = ImageColor.getrgb(DRAW.ORANGE)
        for circled in (6, 2, 3):
            im = DRAW.pegs(circled).image
            marks = [i for i in range(9) if im.getpixel((70+i*72, 223-28)) == orange]
            self.assertEqual(marks, [circled])
        self.assertEqual(9-2, 7)

    def test_only_the_last_two_triangles_are_crossed_out(self):
        im = DRAW.quiz_tool_bag().image
        orange = ImageColor.getrgb(DRAW.ORANGE)
        centers = [(145+i%3*64, 126+i//3*64) for i in range(9)]
        self.assertEqual([i for i, xy in enumerate(centers) if im.getpixel(xy) == orange], [7, 8])

    def test_writing_ten_keeps_the_one_and_adds_zero_to_the_right_half(self):
        first = DRAW.writing_ten(False).image
        complete = DRAW.writing_ten(True).image
        left, right = (214, 34, 360, 327), (362, 34, 507, 327)
        ink = ImageColor.getrgb(DRAW.INK)
        orange = ImageColor.getrgb(DRAW.ORANGE)
        self.assertEqual(first.crop(left).tobytes(), complete.crop(left).tobytes())
        self.assertEqual(first.getpixel((330, 58)), orange)
        self.assertNotIn(ink, list(first.crop(right).getdata()))
        self.assertIn(ink, list(complete.crop(right).getdata()))
        self.assertEqual(complete.getpixel((472, 62)), orange)


if __name__ == '__main__':
    unittest.main()
