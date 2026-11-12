from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("summer_diagrams", ROOT / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class SummerDiagramTests(unittest.TestCase):
    def test_both_written_characters_keep_stroke_order_and_direction(self):
        bean, dipper = (diagrams.STROKES[char] for char in "豆斗")
        self.assertEqual((len(bean), len(dipper)), (7, 4))
        self.assertEqual(len(bean[2]), 3)
        self.assertGreater(bean[4][-1][0], bean[4][0][0])
        self.assertLess(bean[5][-1][0], bean[5][0][0])
        self.assertGreater(bean[-1][-1][0] - bean[-1][0][0], bean[0][-1][0] - bean[0][0][0])
        self.assertEqual(dipper[-1][0][0], dipper[-1][-1][0])
        self.assertLess(dipper[-1][0][1], dipper[2][0][1])
        self.assertGreater(dipper[-1][-1][1], dipper[2][0][1])

    def test_comma_and_period_are_inside_separate_lower_left_corners(self):
        sheet = diagrams.copy_board().convert("RGB")
        color = (189, 87, 44)
        for top in (13, 186):
            pixels = [(x, y) for x in range(525, 681) for y in range(top, top + 156)
                      if sheet.getpixel((x, y)) == color]
            self.assertTrue(pixels)
            self.assertLess(max(x for x, _ in pixels), 603)
            self.assertGreater(min(y for _, y in pixels), top + 78)
        self.assertEqual(len(set(diagrams.DIPPER)), 7)
