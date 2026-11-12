"""Check the geometry shown to children in the courtyard illustrations."""
from math import hypot
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'diagrams'))
from render import CLOCKWISE, DIRECTIONS, LIGHTS, PEG_HEIGHT, relative, shadow_end, side_pos


class CardinalModels(unittest.TestCase):
    def test_shadow_points_away_from_model_light(self):
        for time, expected_signs in [
            ('morning', (-1, 0)), ('noon-model', (0, -1)), ('evening', (1, 0)),
        ]:
            with self.subTest(phase=time):
                lamp = LIGHTS[time]
                shadow = shadow_end(lamp)
                self.assertEqual(tuple((v > 0) - (v < 0) for v in shadow), expected_signs)
                # Intersect the ray from the model ball to the shadow tip at peg height.
                ratio = PEG_HEIGHT / lamp[2]
                for i in range(2):
                    self.assertAlmostEqual(shadow[i] + ratio * (lamp[i] - shadow[i]), 0)

    def test_model_noon_shadow_is_shorter(self):
        afternoon = hypot(*shadow_end(LIGHTS['evening']))
        morning = hypot(*shadow_end(LIGHTS['morning']))
        noon = hypot(*shadow_end(LIGHTS['noon-model']))
        self.assertGreater(morning, noon)
        self.assertEqual(morning, afternoon)

    def test_side_projection_keeps_light_and_shadow_on_opposite_sides(self):
        pivot = side_pos((0, 0))
        for lamp in LIGHTS.values():
            l = side_pos(lamp[:2])
            s = side_pos(shadow_end(lamp))
            dot = sum((a-c)*(b-c) for a,b,c in zip(l,s,pivot))
            self.assertLess(dot, 0)

    def test_compass_order_and_body_facing_are_independent(self):
        self.assertEqual(CLOCKWISE, ('东','南','西','北'))
        for first, opposite in [('东','西'),('南','北')]:
            self.assertEqual(DIRECTIONS[first], tuple(-x for x in DIRECTIONS[opposite]))
        self.assertEqual(relative('东','北'),(0,-1))
        self.assertEqual(relative('南','北'),(-1,0))
        self.assertEqual(relative('西','北'),(0,1))


if __name__ == '__main__':
    unittest.main()
