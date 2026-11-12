import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "written_review_diagrams", Path(__file__).resolve().parents[1] / "diagrams.py"
)
diagrams = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagrams)


class RemovalPictureTest(unittest.TestCase):
    def test_stem_shows_original_and_carried_quantities_without_giving_the_operation(self):
        with patch.object(diagrams, "stock", wraps=diagrams.stock) as stock, \
             patch.object(diagrams, "text", wraps=diagrams.text) as labels:
            picture = diagrams.removal_story(58, 24)

        self.assertEqual([call.args[2:] for call in stock.call_args_list], [(5, 8), (2, 4)])
        self.assertEqual([call.args[2] for call in labels.call_args_list], [58, 24])
        self.assertEqual(picture.size, (650, 355))
        self.assertEqual(picture.getpixel((341, 207)), (71, 129, 109, 255))
        self.assertEqual(picture.getpixel((305, 196)), (251, 239, 207, 255))


if __name__ == "__main__":
    unittest.main()
