from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


spec = spec_from_file_location("unit_review_diagrams", Path(__file__).resolve().parents[1] / "diagrams.py")
diagrams = module_from_spec(spec)
spec.loader.exec_module(diagrams)


class DiagramTest(TestCase):
    def test_sixty_three_has_six_full_ten_frames_and_three_loose_objects(self):
        with patch.object(diagrams, "sprite") as draw:
            diagrams.quantity(63, "garden-sprout")
        cells = [call.args[2:4] for call in draw.call_args_list]
        self.assertEqual(len(cells), 63)
        self.assertEqual(len(set(cells)), 63)
        rows = sorted({y for _, y in cells})
        self.assertEqual([sum(y == row for _, y in cells) for row in rows], [15, 15, 15, 15, 3])

    def test_missing_part_does_not_draw_hidden_objects(self):
        with patch.object(diagrams, "sprite") as draw:
            diagrams.whole(11, 6, unknown="part", asset="garden-pot")
        self.assertEqual(draw.call_count, 11)
        with patch.object(diagrams, "sprite") as draw:
            diagrams.whole(11, 6, unknown="whole", asset="garden-pot")
        self.assertEqual(draw.call_count, 17)
