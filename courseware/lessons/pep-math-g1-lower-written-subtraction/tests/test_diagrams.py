"""Check the quantities and position conventions used by the lesson art."""

import importlib.util
import json
from pathlib import Path
import unittest


LESSON = Path(__file__).resolve().parents[1]
ART = LESSON / "art-source"
spec = importlib.util.spec_from_file_location("draw_diagrams", ART / "draw_diagrams.py")
draw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw)


class SubtractionPicturesTest(unittest.TestCase):
    def test_packet_coordinates_stay_distinct_in_the_thirteen_loose_group(self):
        points = draw.packet_tiles(13, 351, 112, 58)
        self.assertEqual(len(set(points)), 13)
        self.assertEqual([sum(y == row for _, y in points) for row in (112, 170, 228)], [5, 5, 3])

    def test_retreat_conserves_the_stock_and_selects_a_digit_column(self):
        for value, remove in ((63, 27), (80, 26)):
            tens, ones = divmod(value, 10)
            self.assertEqual((tens - 1) * 10 + ones + 10, value)
            self.assertEqual(draw.exchange(value, remove).size, (680, 330))
        right = draw.vertical(72, 6)
        wrong = draw.vertical(72, 6, alignment="tens")
        self.assertNotEqual(right.crop((357, 137, 456, 192)).tobytes(),
                            wrong.crop((357, 137, 456, 192)).tobytes())

    def test_each_quiz_uses_one_precise_and_distinct_option(self):
        course = json.loads((LESSON / "lesson.json").read_bytes())
        diagrams = json.loads((ART / "diagram-data.json").read_bytes())
        quiz = next(scene["questions"] for scene in course["scenes"] if scene["type"] == "quiz")
        expected = [
            ("B", ["stock", 4, 3]),
            ("C", ["stock", 2, 7]),
            ("A", ["stock", 8, 10]),
            ("B", ["vertical", 72, 6, {}]),
            ("C", ["vertical", 58, 54, {"answer": "4"}]),
            ("A", ["stock", 4, 7]),
        ]
        self.assertEqual(len(quiz), len(expected))
        for question, (correct, drawing) in zip(quiz, expected):
            with self.subTest(question=question["id"]):
                self.assertEqual(question["answer"], [correct])
                options = {key: diagrams[option["visual"]["image"]]
                           for key, option in question["options"].items()}
                self.assertEqual([key for key, value in options.items() if value == drawing], [correct])
                self.assertEqual(len({json.dumps(value, sort_keys=True) for value in options.values()}), 3)
