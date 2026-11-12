"""Keep the curriculum's steps, picture answers, and camera anchors consistent."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'diagrams'))
from render import QUIZ_ROUTE, QUIZ_SPOTS, ROOMS, TEACH_ROUTE, TEACH_SPOTS, difference


class CampusModel(unittest.TestCase):
    def test_demonstration_route_counts_steps_from_each_new_start(self):
        self.assertEqual(TEACH_ROUTE,[(TEACH_SPOTS['pot-plant'],TEACH_SPOTS['ochre-bench']),
                                     (TEACH_SPOTS['ochre-bench'],TEACH_SPOTS['blue-book'])])
        self.assertEqual([(b[0]-a[0],b[1]-a[1]) for a,b in TEACH_ROUTE],[(3,0),(0,-2)])

    def test_quiz_route_starts_at_a_different_landmark_and_turns_north_then_east(self):
        self.assertEqual(QUIZ_ROUTE,[(QUIZ_SPOTS['campus-flag'],QUIZ_SPOTS['wind-chime']),
                                    (QUIZ_SPOTS['wind-chime'],QUIZ_SPOTS['notice-board'])])
        self.assertEqual([(b[0]-a[0],b[1]-a[1]) for a,b in QUIZ_ROUTE],[(0,-2),(2,0)])

    def test_west_facing_right_points_north(self):
        self.assertEqual(difference('西',(0,-1)),(0,1))

    def test_both_cameras_share_order_and_distinct_matching_landmarks(self):
        rooms=list(ROOMS.values())
        self.assertEqual([r['symbol'] for r in rooms],['blue-book','plum-drum','wood-palette'])
        self.assertEqual([r['neighbor'] for r in rooms],['ochre-bench','pot-plant','notice-board'])
        self.assertEqual([r['x'] for r in rooms],sorted(r['x'] for r in rooms))
        self.assertTrue(all(abs(r['offset'])<75 for r in rooms))


if __name__=='__main__':
    unittest.main()
