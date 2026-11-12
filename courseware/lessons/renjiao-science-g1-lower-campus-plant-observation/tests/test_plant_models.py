"""Check deterministic details in the plant observation and quiz pictures."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'diagrams'))
from render import BRANCHES, PETAL_COUNTS, art, petal_positions, visuals


class CampusPlantModels(unittest.TestCase):
    def test_the_two_yellow_flower_models_have_exact_distinct_counts(self):
        self.assertEqual(PETAL_COUNTS,{'jasmine':6,'forsythia':4})
        for count in PETAL_COUNTS.values():
            points=petal_positions(count,(90,90),30)
            self.assertEqual(len({(x,y) for x,y,_ in points}),count)
            self.assertEqual(points[0],(90,60,0))

    def test_the_observation_view_pairs_have_different_source_pixels(self):
        for species,(top,side) in BRANCHES.items():
            with self.subTest(species=species):
                self.assertNotEqual(art(top).tobytes(),art(side).tobytes())
                self.assertGreater(art(top).width,art(top).height)
                self.assertGreater(art(side).width,art(side).height)

    def test_teaching_and_correct_quiz_show_the_same_rubbing_order(self):
        sources={key:parents for key,_,_,parents in visuals()}
        steps=['paper-on-bark','crayon-side','bark-print']
        self.assertEqual(sources['bark-steps'],steps)
        self.assertEqual(sources['q3-c'],steps)
        self.assertNotEqual(sources['q3-a'],steps)
        self.assertNotEqual(sources['q3-b'],steps)

    def test_the_pine_record_needs_both_images_and_the_sign_rejects_the_leaf_foil(self):
        sources={key:parents for key,_,_,parents in visuals()}
        self.assertEqual(sources['q5-c'],['whole-pine','pine-bark'])
        self.assertEqual(sources['q6-a'],['plant-sign','whole-pine','pine-bark'])
        self.assertEqual(sources['q6-c'],['plant-sign','whole-pine','oval-sprig'])


if __name__=='__main__':
    unittest.main()
