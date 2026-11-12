from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("rain_diagrams", ROOT / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class RainDiagramTests(unittest.TestCase):
    def test_six_shapes_have_book_stroke_counts_and_key_directions(self):
        paths = diagrams.STROKES
        self.assertEqual([len(paths[char]) for char in "这看鱼面问加"], [7, 9, 8, 9, 6, 5])
        self.assertLess(paths["看"][3][-1][0], paths["看"][3][0][0])
        self.assertGreater(paths["鱼"][-1][0][1], max(y for x, y in paths["鱼"][-2]))
        self.assertLess(paths["面"][1][-1][0], paths["面"][1][0][0])

    def test_question_mouth_is_inside_only_for_centered_answer(self):
        positions = {}
        for name in ("left", "outside", "center"):
            bitmap = diagrams.question_mouth(name).convert("RGB")
            orange = (189, 87, 44)
            positions[name] = [x for y in range(bitmap.height) for x in range(bitmap.width) if bitmap.getpixel((x, y)) == orange]
        left_wall, right_wall = 28 + 305 * .25, 28 + 305 * .75
        self.assertLess(min(positions["left"]) - left_wall, 5)
        self.assertGreater(min(positions["center"]), left_wall + 35)
        self.assertLess(max(positions["center"]), right_wall - 25)
        self.assertGreater(min(positions["outside"]), right_wall)
