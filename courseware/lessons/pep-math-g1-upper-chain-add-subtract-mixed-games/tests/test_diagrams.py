import importlib.util
import json
from pathlib import Path
import unittest


LESSON = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("diagrams", LESSON / "diagrams.py")
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


class LessonDiagrams(unittest.TestCase):
    def test_each_panel_draws_only_the_start_or_the_signed_change(self):
        brief = json.loads((LESSON / "brief.json").read_text(encoding="utf-8"))
        original = ART.draw_object
        try:
            for item, kind in zip(brief["quiz"], ART.QUIZ_OBJECTS):
                drawn = [0, 0, 0]

                def count(draw, object_kind, x, y, color):
                    self.assertEqual(object_kind, kind)
                    drawn[min(2, x // 300)] += 1
                    original(draw, object_kind, x, y, color)

                ART.draw_object = count
                ART.quiz_story(item["calculation"], kind)
                self.assertEqual(drawn, [abs(value) for value in item["calculation"]])
        finally:
            ART.draw_object = original

    def test_questions_have_a_unique_correct_digit_at_balanced_positions(self):
        brief = json.loads((LESSON / "brief.json").read_text(encoding="utf-8"))
        answers = []
        for index, item in enumerate(brief["quiz"]):
            values = item["calculation"]
            target = sum(values if index < 4 else values[:2])
            self.assertEqual(item["options"].count(target), 1)
            self.assertEqual(item["options"]["ABC".index(item["answer"])], target)
            answers.append(item["answer"])
        self.assertEqual(sorted(answers), list("AABBCC"))
