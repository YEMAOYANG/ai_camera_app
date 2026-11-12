import importlib.util
from pathlib import Path
import unittest


SOURCE=Path(__file__).resolve().parents[1]/"diagrams.py"
SPEC=importlib.util.spec_from_file_location("garden_seven_diagrams",SOURCE)
ART=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class DiagramTests(unittest.TestCase):
    def test_registered_strokes_match_national_standard(self):
        self.assertEqual({
            char:"".join(str(category) for category,_ in strokes)
            for char,strokes in ART.STROKES.items()
        }, {"巾":"252","洗":"441312135","房":"45134153","老":"121335","看":"311325111","包":"35515"})
        self.assertEqual(ART.OUTSIDE_COUNTS,{"房":4,"老":4,"看":4,"包":2})
        for chars in ART.WRITE_BOARDS.values():
            self.assertEqual(ART.teaching_board(chars).width,720)

    def test_only_one_card_shows_the_first_four_strokes(self):
        expected=ART.STROKES["房"][:4]
        self.assertEqual([key for key,part in ART.QUIZ_STROKES.items() if part==expected],["quiz-4-b"])
        rendered={ART.quiz_card(key).tobytes() for key in ART.QUIZ_STROKES}
        self.assertEqual(len(rendered),3)
