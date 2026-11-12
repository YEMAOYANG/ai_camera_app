import importlib.util
from pathlib import Path
import unittest

from PIL import ImageColor


MODULE = Path(__file__).resolve().parents[1] / "draw_quiz_diagrams.py"
SPEC = importlib.util.spec_from_file_location("draw_quiz_diagrams", MODULE)
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class QuizDiagramTests(unittest.TestCase):
    def test_options_all_start_with_ten_and_cross_exactly_the_labelled_quantity(self):
        center = "#e0f5fd"
        for crossed in (0, 1, 8, 9):
            with self.subTest(crossed=crossed):
                image = ART.ten_grid(crossed)
                for index in range(10):
                    x, y = 174 + 112 * (index % 5), 78 + 94 * (index // 5)
                    self.assertEqual(image.getpixel((x + 12, y + 4)), ImageColor.getrgb(ART.BLUE))
                    color = ART.CROSS if index < crossed else center
                    self.assertEqual(image.getpixel((x, y)), ImageColor.getrgb(color))

    def test_each_bag_shows_five_visible_counters(self):
        image = ART.equal_bags()
        for center_x, center_y in ((290, 198), (610, 141)):
            for dx, dy in ((-48, -22), (0, -22), (48, -22), (-24, 23), (24, 23)):
                self.assertEqual(image.getpixel((center_x + dx, center_y + dy)),
                                 ImageColor.getrgb("#e0f5fd"))

    def test_cakes_are_ten_at_the_start_and_two_visible_in_the_bag_afterward(self):
        image = ART.round_cakes()
        self.assertEqual((len(ART.CAKES_BEFORE), len(ART.CAKES_IN_BAG)), (10, 2))
        for x, y in (*ART.CAKES_BEFORE, *ART.CAKES_IN_BAG):
            self.assertEqual(image.getpixel((x, y)), ImageColor.getrgb("#edb162"))
        covered_plate = image.crop((530, 111, 690, 229))
        self.assertNotIn(ImageColor.getrgb("#edb162"), covered_plate.getdata())
