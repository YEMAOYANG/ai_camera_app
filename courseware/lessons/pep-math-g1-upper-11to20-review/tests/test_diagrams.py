"""Check the exact displays whose counts or ordering teach the math rule."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image

LESSON = Path(__file__).resolve().parent.parent
spec = spec_from_file_location('math_review_diagrams', LESSON / 'diagrams' / 'render.py')
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class DiagramTests(unittest.TestCase):
    def test_packing_has_exact_groups_and_distinct_slots(self):
        for total in range(10, 21):
            trays, loose = diagrams.split_positions(total // 10, total % 10)
            assert all(len(set(tray)) == 10 for tray in trays)
            all_positions = [point for tray in trays for point in tray] + loose
            assert len(all_positions) == len(set(all_positions)) == total
            with patch.object(diagrams, 'tile') as tile:
                diagrams.compact_groups(total // 10, total % 10)
                assert tile.call_count == total
                assert len({call.args[2] for call in tile.call_args_list}) == total

        with patch.object(diagrams, 'tile') as tile:
            diagrams.scattered()
            assert tile.call_count == 16
            assert len({call.args[2] for call in tile.call_args_list}) == 16


    def test_each_seed_tray_shows_seventeen_and_only_a_groups_ten(self):
        for inside in (9, 10, 11):
            with patch.object(diagrams, 'tile') as tile:
                diagrams.seed_tray(inside)
            points = [call.args[2] for call in tile.call_args_list]
            assert len(points) == len(set(points)) == 17
            assert sum(x < 169 for x, _ in points) == inside


    def test_compact_counter_beads_at_the_expected_rail_heights(self):
        for total in (10, 11, 12, 13, 15, 19, 20):
            im = diagrams.rails(total // 10, total % 10, compact=True)
            for x, count, color in ((46, total // 10, (40, 105, 86)), (113, total % 10, (167, 69, 36))):
                fills = [im.getpixel((x, 120 - 13 * i))[:3] == color for i in range(9)]
                assert fills == [i < count for i in range(9)]


    def test_lit_quiz_interval_marks_four_inner_positions(self):
        im = diagrams.strip(6, 11, flags=(6, 11), highlighted=range(7, 11), marker='light', size=(420, 270))
        centers = [round(420 * .09 + i * 420 * .82 / 5) for i in range(6)]
        orange = (167, 69, 36)
        green = (40, 105, 86)
        assert [im.getpixel((x, 143))[:3] for x in centers] == [orange, green, green, green, green, orange]


    def test_visual_registry_is_complete_and_approved_answers_are_balanced(self):
        manifest = json.loads((LESSON / 'asset-sources.json').read_text())['assets']
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        assert set(lesson['images']) <= manifest.keys()
        for key, row in manifest.items():
            path = LESSON / row['file']
            assert sha256(path.read_bytes()).hexdigest() == row['sha256'], key
            if key in ('depot-room', 'route-room'):
                with Image.open(path) as image:
                    assert image.size == (400, 225)
                    assert image.mode == 'RGB'
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        assert [q['answer'][0] for q in quiz['questions']] == list('ACBBAC')
