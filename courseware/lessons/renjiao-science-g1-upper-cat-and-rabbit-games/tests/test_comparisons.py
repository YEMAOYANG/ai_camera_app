from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

from PIL import Image


LESSON = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("lesson_compare_pictures", LESSON / "compose_pictures.py")
pictures = module_from_spec(spec)
spec.loader.exec_module(pictures)


class ComparisonPicturesTest(unittest.TestCase):
    def test_composed_images_preserve_order_and_each_unobscured_center(self):
        assets = LESSON / "assets"
        for name, parts in pictures.COMPARISONS.items():
            with self.subTest(name=name):
                result = pictures.comparison(assets, parts)
                self.assertEqual(result.size, (320 * len(parts) + 18 * (len(parts) + 1), 356))
                for i, key in enumerate(parts):
                    with Image.open(assets / (key + ".png")) as image:
                        expected = image.convert("RGB").resize((320, 320), Image.Resampling.LANCZOS)
                        self.assertEqual(result.getpixel((178 + i * 338, 178)), expected.getpixel((160, 160)))
                with Image.open(assets / (name + ".png")) as generated:
                    self.assertEqual(generated.tobytes(), result.tobytes())
