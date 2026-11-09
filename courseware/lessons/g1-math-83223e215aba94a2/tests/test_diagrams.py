import importlib.util
from pathlib import Path
import unittest
from PIL import Image

MODULE = Path(__file__).resolve().parents[1] / 'diagrams.py'
SPEC = importlib.util.spec_from_file_location('kindergarten_diagrams', MODULE)
diagrams = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagrams)


class DiagramSemanticsTests(unittest.TestCase):
    def test_square_and_rectangle_have_distinct_edge_lengths(self):
        square = diagrams.SHAPES['square']
        rectangle = diagrams.SHAPES['rectangle']
        self.assertEqual(square[1][0] - square[0][0], square[2][1] - square[1][1])
        self.assertGreater(rectangle[1][0] - rectangle[0][0], rectangle[2][1] - rectangle[1][1])

    def test_arrowheads_agree_with_spoken_directions(self):
        self.assertEqual(min(diagrams.ARROWS['left'], key=lambda p: p[0]), (72, 256))
        self.assertEqual(max(diagrams.ARROWS['right'], key=lambda p: p[0]), (440, 256))
        self.assertEqual(min(diagrams.ARROWS['up'], key=lambda p: p[1]), (256, 72))

    def test_route_destination_is_left_and_start_faces_up(self):
        image = diagrams.render('left-route')
        self.assertEqual(image.getpixel((100, 256)), (255, 250, 240))
        self.assertEqual(image.getpixel((405, 270)), (223, 168, 94))
        self.assertEqual(image.getpixel((405, 175)), (130, 90, 50))

    def test_unknown_diagram_cannot_silently_draw_a_placeholder(self):
        with self.assertRaises(ValueError):
            diagrams.render('unknown')

    def test_scoring_picture_encodes_one_and_two_points(self):
        image = diagrams.render('score-demo', {key: Image.new('RGB', (172,172), 'white') for key in ('leaf','flower')})
        for y, expected in [(158, 1), (378, 2)]:
            pixels = [image.getpixel((x,y)) == (193,123,72) for x in range(300,500)]
            runs = sum(value and (index == 0 or not pixels[index-1]) for index,value in enumerate(pixels))
            self.assertEqual(runs, expected)

    def test_quiz_records_show_the_expected_number_of_separate_dots(self):
        for count in range(6, 11):
            with self.subTest(count=count):
                image = diagrams.render(f'record-{count}')
                row_counts = []
                for y in (172, 332):
                    colored = [image.getpixel((x, y)) == (193, 123, 72) for x in range(512)]
                    row_counts.append(sum(value and (index == 0 or not colored[index - 1])
                                          for index, value in enumerate(colored)))
                self.assertEqual(row_counts, [5, count - 5])


if __name__ == '__main__':
    unittest.main()
