import importlib.util
from pathlib import Path
import unittest
from PIL import ImageColor


path = Path(__file__).resolve().parents[1] / 'diagrams.py'
spec = importlib.util.spec_from_file_location('chain_book_diagrams', path)
diagrams = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagrams)


class BookCountStatesTest(unittest.TestCase):
    def test_each_worked_example_carries_the_intermediate_count(self):
        expected = {
            'add-add': (3, 4, 6),
            'subtract-subtract': (9, 5, 3),
            'add-subtract': (3, 7, 6),
            'subtract-add': (7, 3, 5),
        }
        self.assertEqual({name: diagrams.count_states(*case) for name, case in diagrams.EXAMPLES.items()}, expected)

    def test_rejects_an_impossible_intermediate_shelf(self):
        with self.assertRaises(ValueError):
            diagrams.count_states(2, -3, 5)
        with self.assertRaises(ValueError):
            diagrams.count_states(8, 3, -2)

    def test_supports_a_truly_empty_shelf(self):
        self.assertEqual(diagrams.count_states(10, -6, -4), (10, 4, 0))

    def test_each_question_visual_has_exactly_the_requested_dots(self):
        dot = ImageColor.getrgb(diagrams.DOT_COLOR)
        for count in range(11):
            with self.subTest(count=count):
                image = diagrams.render_quantity(count)
                self.assertEqual(sum(image.getpixel(pos) == dot for pos in diagrams.DOT_POSITIONS), count)
