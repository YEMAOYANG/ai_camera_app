import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw


LESSON = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_diagrams", LESSON / "diagrams.py")
diagrams = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagrams)


class ReviewDiagramsTest(unittest.TestCase):
    def test_frozen_quiz_has_one_mathematically_valid_picture_per_item(self):
        available = [
            [a % 10 + b % 10 >= 10 for a, _, b in diagrams.CHECK_CARRY],
            [n == 47 + 20 for n in diagrams.CHECK_TENS],
            [n == 53 - 8 for n in diagrams.CHECK_BORROW],
            [n == 46 - 20 for n in diagrams.CHECK_TICKETS],
            [n * 7 == 28 for n in diagrams.CHECK_TRIPS],
            [a + b <= 50 for a, b in diagrams.CHECK_CAPACITY],
        ]
        lesson = json.loads((LESSON / "lesson.json").read_text())
        questions = next(scene["questions"] for scene in lesson["scenes"] if scene["type"] == "quiz")
        self.assertEqual(len(questions), len(available))
        for i, (question, valid) in enumerate(zip(questions, available), 1):
            keys = [letter for letter, ok in zip("ABC", valid) if ok]
            self.assertEqual(question["answer"], keys)
            self.assertEqual(len(keys), 1)
            self.assertEqual([option["visual"]["image"] for option in question["options"].values()],
                             [f"q{i}-{letter}" for letter in "abc"])

    def test_exchange_keeps_exact_units_and_marks_ten_only(self):
        image = Image.new("RGBA", (400, 280))
        draw = ImageDraw.Draw(image)
        with patch.object(diagrams, "rod", wraps=diagrams.rod) as rods, \
                patch.object(diagrams, "square", wraps=diagrams.square) as squares, \
                patch.object(draw, "rounded_rectangle", wraps=draw.rounded_rectangle) as outlines:
            diagrams.stock(draw, (0, 0, 390, 260), 4, 13, mark="ten")
        self.assertEqual((rods.call_count, squares.call_count), (4, 13))
        top, bottom = outlines.call_args_list[-1].args[0][1::2]
        rows = [call.args[2] for call in squares.call_args_list]
        self.assertEqual(sum(top < row < bottom for row in rows), 10)
        with patch.object(diagrams, "rod", wraps=diagrams.rod) as rods, \
                patch.object(diagrams, "square", wraps=diagrams.square) as squares, \
                patch.object(draw, "line", wraps=draw.line) as strokes:
            diagrams.stock(draw, (0, 0, 390, 260), 5, 14, remove=7)
        self.assertEqual((rods.call_count, squares.call_count), (5, 14))
        self.assertEqual(sum(call.kwargs.get("fill") == "#9d372b" for call in strokes.call_args_list), 7)

    def test_pictures_match_registered_hash_and_dimensions(self):
        manifest = json.loads((LESSON / "asset-sources.json").read_text())
        for asset in [*manifest["plates"].values(), *manifest["assets"].values()]:
            is_source = "sourceSha256" in asset
            path = LESSON / (asset["source"] if is_source else asset["path"])
            digest = asset["sourceSha256"] if is_source else asset["sha256"]
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), digest)
            with Image.open(path) as picture:
                self.assertEqual(picture.size, (asset["width"], asset["height"]))
                picture.verify()


if __name__ == "__main__":
    unittest.main()
