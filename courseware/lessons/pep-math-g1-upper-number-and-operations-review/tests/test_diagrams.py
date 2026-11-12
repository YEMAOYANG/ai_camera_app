import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PIL import ImageColor


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ops_diagrams", ROOT / "diagrams.py")
DIAGRAMS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGRAMS)


class NumberDiagramsTest(unittest.TestCase):
    def test_large_game_card_has_one_complete_ten_and_exactly_eight_ones(self):
        image = DIAGRAMS.game_count(18)
        pine = ImageColor.getrgb(DIAGRAMS.PINE)
        orange = ImageColor.getrgb(DIAGRAMS.ORANGE)
        for i in range(10):
            self.assertEqual(image.getpixel((36+40*(i%5),36+40*(i//5)))[:3],pine)
        for i in range(10):
            actual = image.getpixel((36+40*(i%5),119+40*(i//5)))[:3]
            self.assertEqual(actual==orange,i<8)

    def test_registered_diagrams_reproduce_from_saved_stamps(self):
        manifest = json.loads((ROOT / "asset-sources.json").read_text())
        with TemporaryDirectory() as folder:
            target = Path(folder)
            (target / "art-source").symlink_to(ROOT / "art-source", target_is_directory=True)
            (target / "assets").mkdir()
            DIAGRAMS.render(target)
            for key, item in manifest["assets"].items():
                if item["kind"] == "semantic-diagram":
                    with self.subTest(key=key):
                        self.assertEqual((target / item["file"]).read_bytes(), (ROOT / item["file"]).read_bytes())
