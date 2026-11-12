"""Check the view pairs and the distinguishing marks in the flower exercises."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'diagrams'))
from render import PHOTOS, SHAPES, art, neutral, sketch


class FlowerModels(unittest.TestCase):
    def test_pairs_show_one_specimen_from_above_and_side(self):
        for kind,(above,side) in PHOTOS.items():
            a,b=art(above),art(side)
            self.assertNotEqual(a.tobytes(),b.tobytes())
            self.assertLess(abs(a.width/b.width-1),.18,kind)
            self.assertLessEqual(b.height,a.height,kind)

    def test_the_funnel_and_cross_use_the_view_showing_that_shape(self):
        self.assertEqual(SHAPES['trumpet'],PHOTOS['trumpet'][1])
        self.assertEqual(SHAPES['cross'],PHOTOS['cross'][0])

    def test_sort_samples_use_the_same_colors(self):
        colors=lambda im:set(pixel for _,pixel in im.getcolors(32))
        self.assertEqual(len({frozenset(colors(neutral(k,v))) for k,v in SHAPES.items()}),1)

    def test_record_options_do_not_collapse(self):
        self.assertEqual(len({sketch(mode).tobytes() for mode in ('all','center','wrong-shape')}),3)


if __name__=='__main__':
    unittest.main()
