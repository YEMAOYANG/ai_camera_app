"""Check the exact illustrated arithmetic and the registered bitmap sources."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

from PIL import Image


LESSON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LESSON))
import diagrams


class FestivalDiagramsTest(unittest.TestCase):
    def test_registered_art_uses_the_exact_drawn_images(self):
        lesson = json.loads((LESSON / "lesson.json").read_bytes())
        manifest = json.loads((LESSON / "asset-sources.json").read_bytes())
        self.assertEqual(set(lesson["images"]), set(manifest["assets"]))
        for key, expected in diagrams.geometry_assets().items():
            file = LESSON / lesson["images"][key]["file"]
            record = manifest["assets"][key]
            self.assertEqual(record["sha256"], sha256(file.read_bytes()).hexdigest())
            self.assertEqual(record["sourceSha256"], sha256((LESSON / "diagrams.py").read_bytes()).hexdigest())
            with Image.open(file) as picture:
                self.assertEqual(picture.tobytes(), expected.tobytes(), key)

    def test_quiz_images_represent_six_unique_answers_in_balanced_positions(self):
        course = json.loads((LESSON / "lesson.json").read_bytes())
        quiz = next(scene for scene in course["scenes"] if scene["type"] == "quiz")
        answers = [question["answer"][0] for question in quiz["questions"]]
        self.assertEqual(Counter(answers), {"A": 2, "B": 2, "C": 2})
        expected = [10 + 1, 19 - 10, 12 + 7, 17 - 6, (15, "−", 2), 2]
        pictures = diagrams.geometry_assets()
        for number, (question, value) in enumerate(zip(quiz["questions"], expected), 1):
            key = f"q{number}"
            options = diagrams.QUIZ_VALUES[key]
            self.assertEqual(options.count(value), 1)
            self.assertEqual(question["answer"], ["ABC"[options.index(value)]])
            self.assertEqual(len({pictures[f"{key}-{letter}"].tobytes() for letter in "abc"}), 3)


if __name__ == "__main__":
    unittest.main()
