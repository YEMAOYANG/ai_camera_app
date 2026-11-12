"""Check the positional claims encoded in the lesson's picture models."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'diagrams'))
from render import PROPS, relation, side_ground


class DirectionPictures(unittest.TestCase):
    def test_turning_changes_labels_on_both_axes_without_moving_the_props(self):
        north = {'purple-drum': (1, 0), 'orange-crate': (-1, 0),
                 'green-flag': (0, -1), 'blue-lantern': (0, 1)}
        for key, direction in north.items():
            with self.subTest(prop=key):
                self.assertEqual(relation((0, 0), PROPS[key], 'north'), direction)
                self.assertEqual(relation((0, 0), PROPS[key], 'south'),
                                 tuple(-component for component in direction))

    def test_person_facing_blue_lamp_sees_crate_to_their_right(self):
        self.assertEqual(relation((0, 0), PROPS['blue-lantern'], 'east'), (1, 0))
        self.assertEqual(relation((0, 0), PROPS['orange-crate'], 'east'), (0, 1))
        self.assertEqual(relation((0, 0), PROPS['purple-drum'], 'east'), (0, -1))
        self.assertEqual(relation((0, 0), PROPS['green-flag'], 'east'), (-1, 0))

    def test_changing_reference_does_not_change_object_coordinates(self):
        self.assertEqual(relation((-1.12, 0), (0, 0), 'north'), (0, 1.12))
        self.assertEqual(relation((1.12, 0), (0, 0), 'north'), (0, -1.12))
        self.assertEqual(relation((0, 0), (0, 1), 'west'), (0, -1))

    def test_side_camera_places_near_object_lower_and_keeps_both_props_visible(self):
        drum, crate = (side_ground(PROPS[prop]) for prop in ('purple-drum', 'orange-crate'))
        flag, lantern = (side_ground(PROPS[prop]) for prop in ('green-flag', 'blue-lantern'))
        actor_x, actor_y = side_ground((0, 0))
        self.assertLess(crate[0], actor_x)
        self.assertGreater(drum[0], actor_x)
        self.assertLess(flag[1], actor_y)
        self.assertGreater(lantern[1], actor_y)
        self.assertGreater(actor_x - flag[0], 45)
        self.assertGreater(lantern[0] - actor_x, 45)


if __name__ == '__main__':
    unittest.main()
