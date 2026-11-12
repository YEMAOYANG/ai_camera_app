from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("minute_diagrams", ROOT / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class MinuteDiagramTests(unittest.TestCase):
    def test_exact_book_stroke_counts_and_highlighted_turn(self):
        paths = diagrams.STROKES
        self.assertEqual([len(paths[c]) for c in "元灯车站坐老师"], [4, 6, 4, 10, 7, 6, 6])
        yuan_hook = paths["元"][-1]
        self.assertGreater(yuan_hook[-1][0], yuan_hook[0][0])
        self.assertLess(yuan_hook[-1][1], yuan_hook[-2][1])
        self.assertEqual(paths["车"][-1][0][0], paths["车"][-1][-1][0])
        self.assertEqual(paths["师"][0][0][0], paths["师"][0][-1][0])
        self.assertLess(paths["老"][4][-1][0], paths["老"][4][0][0])

    def test_open_middle_closed_recognition_shapes_have_distinct_join_heights(self):
        ji, yi, si = (diagrams.yi_paths(height) for height in (.49, .35, .24))
        self.assertEqual(ji[:2], yi[:2])
        self.assertEqual(yi[:2], si[:2])
        self.assertGreater(ji[2][0][1], yi[2][0][1])
        self.assertGreater(yi[2][0][1], si[2][0][1])
