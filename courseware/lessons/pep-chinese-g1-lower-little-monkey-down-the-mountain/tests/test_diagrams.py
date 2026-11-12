import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "diagrams.py"
SPEC = importlib.util.spec_from_file_location("monkey_diagrams", SOURCE)
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class DiagramTests(unittest.TestCase):
    def test_all_seven_shapes_keep_the_official_stroke_order(self):
        expected = {
            "高":"4125125251", "兴":"443134", "着":"43111325111", "往":"33241121",
            "瓜":"33544", "兔":"35251354", "进":"1132454",
        }
        self.assertEqual({
            char:"".join(str(category) for category,_ in strokes)
            for char,strokes in ART.STROKES.items()
        }, expected)
        for characters in ART.BOARDS.values():
            self.assertEqual(ART.stroke_board(characters).size[0],790)

    def test_last_dot_has_distinct_placements_and_base_shape(self):
        keys=("quiz-5-a","quiz-5-b","quiz-5-c")
        dots=[ART.rabbit_choice(key) for key in keys]
        self.assertEqual(len({img.tobytes() for img in dots}),3)
        dark=lambda img: {index for index,pixel in enumerate(img.getdata()) if pixel==(39,71,59)}
        self.assertTrue(dark(dots[0]).issubset(dark(dots[1])))
        self.assertTrue(dark(dots[0]).issubset(dark(dots[2])))
        self.assertEqual(dots[0].getpixel((208,205)),(177,77,41))

    def test_balloon_cards_keep_the_same_right_reference(self):
        keys=("quiz-4-a","quiz-4-b","quiz-4-c")
        boards=[ART.balloon_choice(key) for key in keys]
        self.assertEqual(len({img.crop((166,0,330,230)).tobytes() for img in boards}),1)
        self.assertEqual(len({img.crop((0,0,164,230)).tobytes() for img in boards}),3)
