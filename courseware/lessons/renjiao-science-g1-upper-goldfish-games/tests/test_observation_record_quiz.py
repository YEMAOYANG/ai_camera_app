"""The new observation question uses comparable silhouettes and its archived spoken prompt."""
import json
from pathlib import Path
import unittest

from PIL import Image, ImageChops

LESSON = Path(__file__).resolve().parents[1]


class ObservationRecordQuizTests(unittest.TestCase):
    def test_one_observation_sketch_records_both_visible_features(self):
        lesson = json.loads((LESSON / "lesson.json").read_bytes())
        quiz = next(scene for scene in lesson["scenes"] if scene["key"] == "quiz")
        question = next(q for q in quiz["questions"] if q["id"] == "gf-quiz-record")
        self.assertEqual(question["question"], "三张观察卡里，哪张画对了金鱼的身体形状？")
        self.assertEqual(question["answer"], ["B"])
        self.assertEqual(question["visual"]["image"], "record-window-specimen")

        def picture(option):
            key = question["options"][option]["visual"]["image"]
            with Image.open(LESSON / lesson["images"][key]["file"]) as image:
                return image.convert("RGB")

        match = picture("B")
        tail_difference = ImageChops.difference(picture("A"), match).getbbox()
        dorsal_difference = ImageChops.difference(picture("C"), match).getbbox()
        self.assertIsNotNone(tail_difference)
        self.assertIsNotNone(dorsal_difference)
        self.assertLessEqual(tail_difference[2], 188)
        self.assertGreaterEqual(dorsal_difference[0], 240)
        self.assertLessEqual(dorsal_difference[3], 140)


if __name__ == "__main__":
    unittest.main()
