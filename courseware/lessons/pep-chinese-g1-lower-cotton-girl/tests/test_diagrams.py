import importlib.util
from pathlib import Path
import unittest


SOURCE=Path(__file__).resolve().parents[1]/"diagrams.py"
SPEC=importlib.util.spec_from_file_location("cotton_diagrams",SOURCE)
ART=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class DiagramTests(unittest.TestCase):
    def test_seven_characters_match_standard_stroke_sequences(self):
        expected={"干":"112","久":"354","她":"531525","还":"1324454",
                  "身":"3251113","空":"44534121","星":"251131121"}
        self.assertEqual({ch:"".join(str(kind) for kind,_ in strokes)
                          for ch,strokes in ART.STROKES.items()},expected)
        self.assertEqual(ART.QUIZ_STROKES["quiz-6-c"],ART.STROKES["还"][:4])
        self.assertTrue(all(ART.writing_board(chars).width==750 for chars in ART.BOARDS.values()))

    def test_six_seven_and_eight_spots_stay_separate(self):
        for count in (6,7,8):
            points=ART.spot_locations(count)
            self.assertEqual(len(set(points)),count)
            self.assertTrue(all((x-u)**2+(y-v)**2>(.064)**2
                                for i,(x,y) in enumerate(points) for u,v in points[:i]))
            img=ART.paper_beetle(count)
            self.assertTrue(all(img.getpixel((round(300*x),round(300*y)))==(38,71,61) for x,y in points))
        self.assertIn((.50,.34),ART.spot_locations(7))
        self.assertEqual(len({ART.paper_beetle(n).tobytes() for n in (6,7,8)}),3)
