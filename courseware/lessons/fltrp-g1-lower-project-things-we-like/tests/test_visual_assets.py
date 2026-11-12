"""Check that exact colour and order distinctions survive atlas assembly."""

from pathlib import Path
import unittest

from PIL import Image, ImageChops


ASSETS = Path(__file__).resolve().parents[1] / "assets"


def image(name):
    with Image.open(ASSETS / f"{name}.png") as opened:
        return opened.convert("RGB")


class VisualAssetsTests(unittest.TestCase):
    def test_favourite_uses_three_distinct_colour_samples(self):
        colors = [image(f"quiz-5-{letter}").getpixel((125, 125)) for letter in "abc"]
        self.assertEqual(colors, [(131, 69, 169), (47, 134, 91), (225, 122, 41)])
        self.assertTrue((ASSETS / "quiz-5-hat.png").is_file())

    def test_vote_choices_change_the_mark_and_keep_the_same_doll(self):
        crossed, plain = image("quiz-4-a"), image("quiz-4-b")
        self.assertEqual(crossed.size, plain.size)
        self.assertIsNone(ImageChops.difference(crossed.crop((0, 0, 280, 280)),
                                               plain.crop((0, 0, 280, 280))).getbbox())
        self.assertIsNotNone(ImageChops.difference(crossed, plain).getbbox())

    def test_sequence_uses_the_same_three_drawings_in_three_distinct_orders(self):
        strips = [image(f"quiz-6-{letter}") for letter in "abc"]
        self.assertTrue(all(strip.size == (876, 280) for strip in strips))
        parts = [[strip.crop((292*i, 0, 292*(i+1), 280)).tobytes() for i in range(3)]
                 for strip in strips]
        draw, ask, show = parts[2]
        self.assertEqual(len({draw, ask, show}), 3)
        self.assertEqual(parts[0], [ask, draw, show])
        self.assertEqual(parts[1], [draw, show, ask])
