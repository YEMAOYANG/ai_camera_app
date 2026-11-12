import importlib.util
from pathlib import Path
import unittest


SOURCE=Path(__file__).resolve().parents[1]/"diagrams.py"
SPEC=importlib.util.spec_from_file_location("gecko_diagrams",SOURCE)
ART=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class DiagramTests(unittest.TestCase):
    def test_seven_writing_targets_follow_the_confirmed_stroke_orders(self):
        expected={"边":"53454","过":"124454","向":"325251","行":"332112",
                  "找":"1211534","草":"122251112","赶":"1212134112"}
        self.assertEqual({ch:"".join(str(kind) for kind,_ in strokes)
                          for ch,strokes in ART.STROKES.items()},expected)
        self.assertEqual({ch for chars in ART.BOARDS.values() for ch in chars},set(expected))
        self.assertTrue(all(ART.writing_board(chars).width==750 for chars in ART.BOARDS.values()))

    def test_radical_question_has_only_the_correct_seven_stroke_outline(self):
        self.assertEqual(ART.CHOICES["quiz-6-c"],ART.STROKES["赶"][:7])
        self.assertEqual(ART.CHOICES["quiz-6-b"],ART.STROKES["边"][-3:])
        self.assertEqual(len({ART.radical_choice(key).tobytes() for key in ART.CHOICES}),3)
