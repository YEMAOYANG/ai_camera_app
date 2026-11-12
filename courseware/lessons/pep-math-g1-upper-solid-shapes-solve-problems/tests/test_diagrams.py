"""Check the geometry and the independently derived answer keys."""

from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from math import hypot, sqrt
from pathlib import Path
import re
import sys
import unittest

from PIL import ImageChops


LESSON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LESSON))
import diagrams


def height(model):
    return max(position[2] + size[2] for _, position, size in model)


class SolidShapeDiagramsTest(unittest.TestCase):
    def test_teaching_models_use_the_same_ten_pieces_and_compare_from_the_floor(self):
        flat, thin, capped = diagrams.bases()
        kinds = Counter(piece.kind for piece in diagrams.MATERIALS)
        self.assertEqual(kinds, {"block": 8, "cylinder": 1, "sphere": 1})
        self.assertEqual(sum(len(set(p.size)) == 1 and p.kind == "block"
                             for p in diagrams.MATERIALS), 1)
        identifiers = {piece.key for piece in diagrams.MATERIALS}
        self.assertEqual(len(identifiers), 10)
        for model in (diagrams.full_build(flat), diagrams.full_build(capped)):
            self.assertEqual(len(model), 10)
            self.assertEqual({piece.key for piece, _, _ in model}, identifiers)
            self.assertEqual(min(position[2] for _, position, _ in model), 0)
        self.assertLess(height(flat), height(capped))
        self.assertLess(height(capped), height(thin))

    def test_three_separate_level_pads_touch_the_ball_and_fit_on_the_cylinder(self):
        *pads, sphere = diagrams.cradle(0)
        self.assertEqual(len(pads), 3)
        self.assertEqual(len({position[2] + size[2] for _, position, size in pads}), 1)
        _, (cx, cy, ball_bottom), (_, _, diameter) = sphere
        radius = diameter / 2
        pad_height = pads[0][1][2] + pads[0][2][2]
        cross_section = sqrt(radius**2 - (ball_bottom + radius - pad_height)**2)
        for _, (x, y, _), (width, depth, _) in pads:
            nearest = hypot(max(abs(cx - x) - width / 2, 0),
                            max(abs(cy - y) - depth / 2, 0))
            self.assertAlmostEqual(nearest, cross_section)
            farthest = hypot(abs(x) + width / 2, abs(y) + depth / 2)
            self.assertLess(farthest, diagrams.CYLINDER.size[0] / 2)
        for (_, (x1, y1, _), (w1, d1, _)), (_, (x2, y2, _), (w2, d2, _)) in combinations(pads, 2):
            self.assertTrue(abs(x1 - x2) >= (w1 + w2) / 2 or abs(y1 - y2) >= (d1 + d2) / 2)
        self.assertGreater(ball_bottom, 0)

    def test_quiz_uses_the_widest_face_and_filters_missing_pieces_before_height(self):
        lesson = json.loads((LESSON / "lesson.json").read_text(encoding="utf-8"))
        quizzes = {q["id"]: q for scene in lesson["scenes"] if scene["type"] == "quiz"
                   for q in scene["questions"]}
        self.assertEqual(len(quizzes), 6)
        self.assertEqual(Counter(q["answer"][0] for q in quizzes.values()), {"A": 2, "B": 2, "C": 2})
        sizes = diagrams.QUIZ_BOX.size
        areas = [sizes[axes[0]] * sizes[axes[1]] for axes in diagrams.QUIZ_BOX_ORIENTATIONS]
        self.assertEqual(quizzes["sssp-q1"]["answer"], ["ABC"[areas.index(max(areas))]])
        q5, q6 = diagrams.quiz_towers()
        self.assertEqual(quizzes["sssp-q5"]["answer"], ["ABC"[max(range(3), key=lambda i: height(q5[i]))]])
        tallest = max(range(3), key=lambda i: height(q6[i]))
        self.assertLess(len(q6[tallest]), len(diagrams.QUIZ_Q6))
        complete = [i for i, model in enumerate(q6) if len(model) == len(diagrams.QUIZ_Q6)]
        self.assertEqual(quizzes["sssp-q6"]["answer"], ["ABC"[max(complete, key=lambda i: height(q6[i]))]])

    def test_registered_assets_are_the_exact_generated_geometry(self):
        lesson = json.loads((LESSON / "lesson.json").read_text(encoding="utf-8"))
        assets = diagrams.geometry_assets()
        manifest = json.loads((LESSON / "asset-sources.json").read_text(encoding="utf-8"))
        self.assertEqual(set(lesson["images"]), set(manifest["assets"]))
        self.assertTrue(set(assets) <= set(lesson["images"]))
        for key, image in assets.items():
            source = LESSON / lesson["images"][key]["file"]
            with diagrams.Image.open(source) as saved:
                self.assertEqual(saved.size, image.size, key)
                self.assertEqual(saved.tobytes(), image.tobytes(), key)
        for index in range(1, 7):
            self.assertEqual(len({assets[f"q{index}-{letter}"].tobytes() for letter in "abc"}), 3)

    def test_side_rails_remove_only_the_left_and_right_rolling_arrows(self):
        with (
            diagrams.Image.open(LESSON / "assets/roll-flat.png") as flat,
            diagrams.Image.open(LESSON / "assets/roll-side-rails.png") as rails,
        ):
            x, y = flat.width // 2, flat.height // 2
            for offset in (-110, 110):
                self.assertEqual(flat.getpixel((x, y + offset)), rails.getpixel((x, y + offset)))
                self.assertEqual(flat.getpixel((x + offset, y)), flat.getpixel((x, y + offset)))
                self.assertNotEqual(rails.getpixel((x + offset, y)), rails.getpixel((x, y + offset)))

    def test_roll_quiz_arrows_differ_only_by_direction(self):
        base = diagrams.overhead(diagrams.QUIZ_Q3_WALLS, ())
        center_x, center_y = base.width // 2, base.height // 2
        measurements = []
        for letter in "abc":
            with diagrams.Image.open(LESSON / f"assets/q3-{letter}.png") as option:
                box = ImageChops.difference(base, option).getbbox()
            self.assertIsNotNone(box, letter)
            left, top, right, bottom = box
            width, height = right - left, bottom - top
            length, breadth = max(width, height), min(width, height)
            if letter == "a":
                self.assertLess(right, center_x)
                offset = center_x - right
            elif letter == "b":
                self.assertLess(bottom, center_y)
                offset = center_y - bottom
            else:
                self.assertGreater(left, center_x)
                offset = left - center_x
            measurements.append((length, breadth, offset))
        for values in zip(*measurements):
            self.assertLessEqual(max(values) - min(values), 1, measurements)

    def test_platform_diagrams_match_asset_provenance_and_use_a_common_baseline(self):
        brief = json.loads((LESSON / "brief.json").read_text(encoding="utf-8"))
        plan = next(page["game"]["artPlan"] for page in brief["pageSequence"] if page["key"] == "p03")
        scene = json.loads((LESSON / "pages/face-hop.scene.json").read_text(encoding="utf-8"))
        source = (LESSON / "pages/face-hop.js").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"__IMG:([^_]+)__", source)), set(scene["images"]))
        self.assertEqual(set(scene["images"]), set(plan))

        assets = diagrams.hop_geometry_assets()
        self.assertEqual(set(assets), {key for key, item in plan.items()
                                      if item["kind"] == "deterministic-geometry"})
        self.assertEqual(len(assets), 10)
        provenance = json.loads((LESSON / "asset-sources.json").read_text(encoding="utf-8"))["assets"]
        shape_boxes = {}
        for key, image in assets.items():
            spec = plan[key]
            filename = LESSON / scene["images"][key]["file"]
            self.assertEqual(provenance[key]["sha256"], sha256(filename.read_bytes()).hexdigest())
            self.assertEqual(provenance[key]["spec"], spec["spec"])
            with diagrams.Image.open(filename) as saved:
                self.assertEqual(saved.mode, "RGBA")
                self.assertEqual(saved.size, (120, 96))
                self.assertEqual(saved.tobytes(), image.tobytes())
                alpha = saved.getchannel("A")
                self.assertEqual(alpha.getpixel((0, 0)), 0)
                self.assertEqual(alpha.getpixel((10, diagrams.HOP_FLOOR + 1)), 255)
                self.assertIsNotNone(alpha.crop((22, diagrams.HOP_FLOOR - 3,
                                                  98, diagrams.HOP_FLOOR - 1)).getbbox())
                shape_boxes[key] = alpha.crop((0, 0, 120, diagrams.HOP_FLOOR - 1)).getbbox()

        for material in ("board", "brick", "case"):
            flat, upright = (shape_boxes[f"hop-{pose}-{material}"] for pose in ("wide", "end"))
            self.assertLess(upright[1], flat[1], material)
            self.assertGreater(flat[2] - flat[0], upright[2] - upright[0], material)
        upright = shape_boxes["hop-upright-cylinder"]
        side = shape_boxes["hop-side-cylinder"]
        self.assertLess(upright[1], side[1])
        self.assertGreater(side[2] - side[0], upright[2] - upright[0])

    def test_platform_scene_uses_the_complete_registered_art_in_lesson_order(self):
        lesson = json.loads((LESSON / "lesson.json").read_text(encoding="utf-8"))
        recipe = json.loads((LESSON / "pages/face-hop.scene.json").read_text(encoding="utf-8"))
        manifest = json.loads((LESSON / "asset-sources.json").read_text(encoding="utf-8"))["assets"]
        position = next(i for i, scene in enumerate(lesson["scenes"]) if scene["key"] == "p03")
        self.assertEqual([scene["key"] for scene in lesson["scenes"][position - 1:position + 2]],
                         ["p02", "p03", "p04"])
        self.assertEqual(lesson["scenes"][position], recipe["scene"])
        self.assertEqual(len(recipe["images"]), 15)
        total_bytes = 0
        for key, spec in recipe["images"].items():
            self.assertEqual(lesson["images"][key], spec)
            file = LESSON / spec["file"]
            raw = file.read_bytes()
            total_bytes += len(raw)
            self.assertEqual(sha256(raw).hexdigest(), manifest[key]["sha256"])
            with diagrams.Image.open(file) as image:
                self.assertEqual(image.format, "PNG")
                if key == "hop-workbench":
                    self.assertEqual(image.size, (1280, 720))
                    self.assertEqual(image.mode, "RGB")
                image.verify()
        self.assertLessEqual(total_bytes, 3_000_000)

    def test_platform_teacher_points_at_the_fixed_first_landing_and_only_unpauses(self):
        recipe = json.loads((LESSON / "pages/face-hop.scene.json").read_text(encoding="utf-8"))
        script = recipe["scene"]["script"]
        html = (LESSON / "pages/face-hop.html").read_text(encoding="utf-8")
        self.assertEqual(script[1]["setState"], {"demo": True, "level": 1, "pause": True})
        self.assertEqual(script[4]["highlight"], "#face-hop-demo-wide")
        self.assertIn('id="face-hop-demo-wide" class="g-anchor"', html)
        self.assertEqual(script[6]["setState"], {"pause": False})
        self.assertEqual(script[10]["setState"], {"demo": False, "level": 1, "pause": False})

    def test_depot_uses_exact_registered_diagrams_for_distinct_supports(self):
        assets = diagrams.support_depot_assets()
        self.assertEqual(len(assets), 7)
        self.assertEqual(len({image.tobytes() for image in assets.values()}), 7)
        source = json.loads((LESSON / "lesson.json").read_text(encoding="utf-8"))
        manifest = json.loads((LESSON / "asset-sources.json").read_text(encoding="utf-8"))
        for key, expected in assets.items():
            path = LESSON / source["images"][key]["file"]
            record = manifest["assets"][key]
            self.assertEqual(record["sha256"], sha256(path.read_bytes()).hexdigest())
            self.assertEqual(record["kind"], "deterministic-geometry")
            with diagrams.Image.open(path) as image:
                self.assertEqual((image.mode, image.size), ("RGBA", (144, 144)))
                self.assertEqual(image.tobytes(), expected.tobytes())


if __name__ == "__main__":
    unittest.main()
