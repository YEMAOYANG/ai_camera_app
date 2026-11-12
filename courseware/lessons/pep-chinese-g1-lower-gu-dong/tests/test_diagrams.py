import importlib.util
from pathlib import Path
import unittest


SOURCE=Path(__file__).resolve().parents[1]/"diagrams.py"
SPEC=importlib.util.spec_from_file_location("gudong_diagrams",SOURCE)
ART=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class DiagramTests(unittest.TestCase):
    def test_each_of_seven_textbook_characters_has_the_correct_stroke_sequence(self):
        expected={"为":"4354","吓":"251124","没":"4413554","到":"15412122",
                  "怕":"44232511","家":"4451353334","象":"35251353334"}
        self.assertEqual({ch:"".join(str(kind) for kind,_ in strokes)
                          for ch,strokes in ART.STROKES.items()},expected)
        self.assertEqual({ch for chars in ART.BOARDS.values() for ch in chars},set(expected))
        self.assertTrue(all(ART.writing_board(chars).width==750 for chars in ART.BOARDS.values()))

    def test_only_the_correct_card_uses_the_standard_last_dot(self):
        self.assertEqual([key for key,coords in ART.DOTS.items() if coords==ART.STROKES["为"][-1][1]],["quiz-6-c"])
        self.assertEqual(len({ART.last_dot_card(key).tobytes() for key in ART.DOTS}),3)
