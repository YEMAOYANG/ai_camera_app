from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("stationery_diagrams", ROOT / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class StationeryDiagramTests(unittest.TestCase):
    def test_mainland_stroke_order_has_six_book_counts_and_three_walking_strokes(self):
        paths = diagrams.STROKES
        self.assertEqual([len(paths[c]) for c in "笔知道放平安"], [10, 8, 12, 8, 5, 6])
        dot, turn, sweep = paths["道"][-3:]
        self.assertEqual((len(dot), len(turn), len(sweep)), (2, 5, 5))
        self.assertLess(turn[-1][0], turn[-2][0])
        self.assertGreater(sweep[-1][0], sweep[0][0])
        self.assertLess(paths["笔"][-1][-1][1], paths["笔"][-1][-2][1])
        self.assertGreater(paths["平"][-1][0][1], paths["平"][0][0][1])

    def test_bottom_component_is_marked_low_on_the_correct_quiz_card(self):
        bitmap = diagrams.box_glyph(range(6, 11)).convert("RGB")
        mark = (189, 87, 44)
        rows = [y for y in range(bitmap.height) for x in range(bitmap.width) if bitmap.getpixel((x, y)) == mark]
        self.assertTrue(rows)
        self.assertGreater(min(rows), 190)
