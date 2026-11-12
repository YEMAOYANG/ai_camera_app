"""Verify the authored count layouts and their reproducible playback images."""

from collections import Counter
import json
import math
from pathlib import Path
import re
import runpy
import tempfile
import unittest

from PIL import Image


LESSON = Path(__file__).resolve().parents[1]
LAYOUT = LESSON / "art-source" / "counted-layout.json"
BRIEF = json.loads((LESSON / "brief.json").read_text(encoding="utf-8"))
ATLAS = BRIEF["mediaPlan"]["ballAtlas"]
GROUPS = ATLAS["paintOrderByGroup"]


class CountedArtTest(unittest.TestCase):
    def assert_single_target(self, target, choices, colour, quantity):
        self.assertEqual([key for key in choices if GROUPS[key].count(colour) == quantity], [target])
        self.assertEqual({len(GROUPS[key]) for key in choices}, {len(GROUPS[target])})

    def test_group_names_and_spoken_targets(self):
        self.assertEqual(len(GROUPS), 23)
        for name, colour_order in GROUPS.items():
            with self.subTest(group=name):
                declared = Counter({colour: int(amount) for colour, amount in re.findall(r"([pbu])(\d+)", name)})
                self.assertEqual(Counter(colour_order), declared)
        for level in ATLAS["wordBubbles"]["levels"]:
            for target, choices, colour, quantity in level:
                self.assert_single_target(target, choices, colour, quantity)
        for level in ATLAS["listenDelivery"]["levels"]:
            for target, colour, quantity, _ in level["orders"]:
                self.assert_single_target(target, level["stationGroups"], colour, quantity)

    def test_counting_slots_do_not_overlap_or_clip(self):
        for count, grid in ATLAS["gridsByTotal"].items():
            centres = grid["centres"]
            diameter = grid["diameter"]
            self.assertEqual(len(centres), int(count))
            for index, centre in enumerate(centres):
                self.assertTrue(all(diameter / 2 < axis < 100 - diameter / 2 for axis in centre))
                for other in centres[index + 1:]:
                    self.assertGreater(math.dist(centre, other), diameter)

    def test_quiz_stems_have_the_expected_objects(self):
        layout = json.loads(LAYOUT.read_text(encoding="utf-8"))
        for key, counts in (
            ("q-pink-stem", {"pink-ball": 7, "brown-ball": 2}),
            ("q-pencil-stem", {"green-pencil": 10, "green-pen": 1, "yellow-pencil": 2}),
            ("q-kite-stem", {"purple-kite": 6, "purple-book": 1, "yellow-kite": 1}),
        ):
            self.assertEqual(Counter(layer["asset"] for layer in layout[key]["sprites"]), counts)

    def test_repeat_render_is_identical(self):
        render = runpy.run_path(str(LESSON / "art-source" / "compose.py"))["render_all"]
        with tempfile.TemporaryDirectory(prefix="counted-art-") as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            render(first)
            render(second)
            expected = set(json.loads(LAYOUT.read_text(encoding="utf-8"))) | {f"group-{key}" for key in GROUPS}
            self.assertEqual({p.stem for p in first.glob("*.png")}, expected)
            self.assertEqual({p.stem for p in second.glob("*.png")}, expected)
            for key in sorted(expected):
                filename = f"{key}.png"
                with self.subTest(asset=key):
                    self.assertEqual((first / filename).read_bytes(), (second / filename).read_bytes())
                    if key.startswith("group-"):
                        with Image.open(first / filename) as image:
                            self.assertEqual(image.size, (256, 256))
                            self.assertEqual(image.mode, "RGBA")
                            self.assertEqual(image.getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
