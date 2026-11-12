import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("lesson_diagrams", ROOT / "diagrams.py")
DIAGRAMS = module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGRAMS)


class DiagramTests(unittest.TestCase):
    def test_written_columns_and_carry_have_separate_positions(self):
        seen = []

        def record(_, xy, value, size, color=DIAGRAMS.PINE):
            seen.append((xy, str(value), color))

        with patch.object(DIAGRAMS, "label", record):
            DIAGRAMS.vertical(7, 65, 72, carry=True)

        numbers = [row for row in seen if row[1].isdigit()]
        assert numbers[0][0][0] == numbers[1][0][0]  # 7 and 5 are ones
        assert numbers[2][0][0] < numbers[1][0][0]   # 6 is a ten
        assert numbers[3][0][0] == numbers[0][0][0]  # result ones
        mark = numbers[-1]
        assert mark[1:] == ("1", DIAGRAMS.ORANGE)
        assert numbers[2][0][0] < mark[0][0] < numbers[1][0][0]


    def test_quiz_result_pictures_have_unique_arithmetic_answers(self):
        assert DIAGRAMS.place(70) == (7, 0)
        assert DIAGRAMS.place(6) == (0, 6)
        for question, answers in DIAGRAMS.RESULT_CHOICES.items():
            target = sum(DIAGRAMS.QUIZ_PROBLEMS[question-1])
            assert len(answers) == len(set(answers)) == 3
            assert answers.count(target) == 1
        assert [sum(pair) for pair in DIAGRAMS.QUIZ_PROBLEMS] == [56, 65, 70, 63, 54]


    def test_all_game_and_quiz_diagrams_reproduce_registered_png_pixels(self):
        from PIL import Image, ImageChops

        for name, regenerated in DIAGRAMS.figures():
            saved = Image.open(ROOT / "assets" / f"{name}.png")
            assert saved.size == regenerated.size
            assert ImageChops.difference(saved.convert("RGB"), regenerated).getbbox() is None
