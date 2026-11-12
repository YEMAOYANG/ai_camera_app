from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

from PIL import ImageColor


LESSON = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("lesson_diagrams", LESSON / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


def color_runs(image, y, color):
    rgb = ImageColor.getrgb(color)
    active = False
    runs = 0
    for x in range(image.width):
        matches = image.getpixel((x, y)) == rgb
        if matches and not active:
            runs += 1
        active = matches
    return runs


class QuantityPicturesTest(unittest.TestCase):
    def test_swapping_group_order_preserves_counts(self):
        for image in (diagrams.paired(2, 4), diagrams.paired(2, 4, reverse=True)):
            self.assertEqual(color_runs(image, 169, diagrams.ORANGE), 2)
            self.assertEqual(color_runs(image, 169, diagrams.BLUE), 4)

    def test_a_removed_group_moves_without_changing_either_count(self):
        left = diagrams.removed(take_orange=True)
        right = diagrams.removed(take_orange=False)
        self.assertEqual(color_runs(left, 96, diagrams.BLUE), 4)
        self.assertEqual(color_runs(left, 255, diagrams.ORANGE), 3)
        self.assertEqual(color_runs(right, 96, diagrams.ORANGE), 3)
        self.assertEqual(color_runs(right, 255, diagrams.BLUE), 4)

    def test_equal_and_unequal_groups_are_distinct(self):
        equal = diagrams.paired(3, 3, shared=False)
        unequal = diagrams.paired(3, 4, shared=False)
        self.assertEqual(color_runs(equal, 169, diagrams.ORANGE), 3)
        self.assertEqual(color_runs(equal, 169, diagrams.BLUE), 3)
        self.assertEqual(color_runs(unequal, 169, diagrams.ORANGE), 3)
        self.assertEqual(color_runs(unequal, 169, diagrams.BLUE), 4)

    def test_three_quiz_pictures_match_spoken_counts(self):
        tickets = diagrams.tickets()
        self.assertEqual(color_runs(tickets, 157, diagrams.BLUE), 1)
        self.assertEqual(color_runs(tickets, 104, diagrams.ORANGE) + color_runs(tickets, 204, diagrams.ORANGE), 5)
        socks = diagrams.socks()
        self.assertEqual(color_runs(socks, 115, diagrams.BLUE), 1)
        self.assertEqual(color_runs(socks, 205, diagrams.ORANGE) + color_runs(socks, 270, diagrams.ORANGE), 6)
        tags = diagrams.tags()
        self.assertEqual(color_runs(tags, 100, diagrams.BLUE), 2)
        self.assertEqual(color_runs(tags, 210, diagrams.BLUE), 0)
        self.assertEqual(color_runs(tags, 100, diagrams.ORANGE) + color_runs(tags, 210, diagrams.ORANGE), 5)
