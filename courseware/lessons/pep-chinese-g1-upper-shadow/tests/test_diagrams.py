import importlib.util
from pathlib import Path
import unittest

from PIL import Image


LESSON = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shadow_diagrams", LESSON / "diagrams.py")
diagrams = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagrams)


class ShadowDiagramsTest(unittest.TestCase):
    def test_paper_figure_turn_moves_its_left_side_to_the_top(self):
        self.assertEqual(diagrams.offset("front", "up"), (0, -1))
        self.assertEqual(diagrams.offset("front", "right"), (1, 0))
        self.assertEqual(diagrams.offset("left", "right"), (0, -1))
        self.assertEqual(diagrams.offset("right", "right"), (0, 1))

    def test_written_forms_keep_the_verified_number_of_strokes(self):
        self.assertEqual([len(diagrams.STROKES[glyph]) for glyph in "左右在我"], [5, 5, 6, 7])
        start, *_, hook_base, hook_tip = diagrams.STROKES["我"][4]
        self.assertGreater(hook_base[0], start[0])
        self.assertGreater(hook_base[1], start[1])
        self.assertLess(hook_tip[1], hook_base[1])

    def test_quiz_uses_three_distinct_highlights_on_the_same_character(self):
        for name, stroke in zip("abc", (1, 3, 5)):
            with Image.open(LESSON / "assets" / ("stroke-choice-" + name + ".png")) as saved:
                self.assertEqual(saved.tobytes(), diagrams.write_choice(stroke).tobytes())
