import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("garden_diagrams", ROOT / "diagrams.py")
DIAGRAMS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGRAMS)


class GardenDiagramsTest(unittest.TestCase):
    def test_parent_characters_and_stroke_pair(self):
        self.assertEqual(len(DIAGRAMS.STROKES["爸"]), 8)
        self.assertEqual(len(DIAGRAMS.STROKES["妈"]), 6)
        self.assertLess(DIAGRAMS.COMPARE["儿"][-1][1], DIAGRAMS.COMPARE["儿"][-2][1])
        self.assertEqual(DIAGRAMS.COMPARE["四"][-1][1], DIAGRAMS.COMPARE["四"][-2][1])

    def test_registered_diagrams_reproduce_from_saved_atlases(self):
        manifest = json.loads((ROOT / "asset-sources.json").read_text())
        with TemporaryDirectory() as directory:
            candidate = Path(directory)
            (candidate / "art-source").symlink_to(ROOT / "art-source", target_is_directory=True)
            assets = candidate / "assets"
            assets.mkdir()
            for name in ("compass-person.png", "star-pin.png"):
                (assets / name).symlink_to(ROOT / "assets" / name)
            DIAGRAMS.render(candidate)
            for key, entry in manifest["assets"].items():
                if entry["kind"] == "semantic-diagram":
                    with self.subTest(key=key):
                        self.assertEqual((candidate / entry["file"]).read_bytes(),
                                         (ROOT / entry["file"]).read_bytes())
