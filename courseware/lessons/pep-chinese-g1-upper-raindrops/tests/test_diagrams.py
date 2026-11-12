import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rain_diagrams", ROOT / "diagrams.py")
DIAGRAMS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGRAMS)


class RainDiagramsTest(unittest.TestCase):
    def test_stroke_counts_and_hook(self):
        self.assertEqual({key: len(value) for key, value in DIAGRAMS.STROKES.items()},
                         {"来": 7, "半": 5, "你": 7, "有": 6})
        start, bend, hook = DIAGRAMS.STROKES["你"][3]
        self.assertEqual(start[1], bend[1])
        self.assertLess(hook[0], bend[0])
        self.assertGreater(hook[1], bend[1])

    def test_registered_diagrams_reproduce_from_illustration_sources(self):
        manifest = json.loads((ROOT / "asset-sources.json").read_text())
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "art-source").symlink_to(ROOT / "art-source", target_is_directory=True)
            assets = root / "assets"
            assets.mkdir()
            for item in manifest["assets"].values():
                if item["kind"] == "codex-builtin-imagegen":
                    (root / item["file"]).symlink_to(ROOT / item["file"])
            DIAGRAMS.render(root)
            for key, item in manifest["assets"].items():
                if item["kind"] == "semantic-diagram":
                    with self.subTest(key=key):
                        self.assertEqual((root / item["file"]).read_bytes(), (ROOT / item["file"]).read_bytes())
