import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("lotus_diagrams",ROOT/"diagrams.py")
DIAGRAMS=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGRAMS)


class LotusDiagramsTest(unittest.TestCase):
    def test_rounded_stroke_turns_right_without_the_hook(self):
        turn=DIAGRAMS.TURN
        self.assertGreater(turn[-1][0],turn[-2][0])
        self.assertEqual(turn[-1][1],turn[-2][1])
        self.assertLess(DIAGRAMS.HOOK[-1][1],turn[-1][1])

    def test_registered_diagrams_reproduce_from_original_crops(self):
        manifest=json.loads((ROOT/"asset-sources.json").read_text())
        with TemporaryDirectory() as folder:
            work=Path(folder)
            (work/"art-source").symlink_to(ROOT/"art-source",target_is_directory=True)
            (work/"assets").mkdir()
            for asset in manifest["assets"].values():
                if asset["kind"]=="codex-builtin-imagegen":
                    (work/asset["file"]).symlink_to(ROOT/asset["file"])
            DIAGRAMS.render(work)
            for key,asset in manifest["assets"].items():
                if asset["kind"]=="semantic-diagram":
                    with self.subTest(key=key):
                        self.assertEqual((work/asset["file"]).read_bytes(),(ROOT/asset["file"]).read_bytes())
