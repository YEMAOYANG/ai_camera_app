"""Guard the photographed profile and the source material for shape samples."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'diagrams'))
from render import EXAMPLES, VIEWS, art, neutral_shape, note_page, picture_options


class LeafModels(unittest.TestCase):
    def test_same_leaf_edge_view_has_similar_length_but_much_less_projected_width(self):
        for above,edge in VIEWS.values():
            with self.subTest(specimen=above):
                broad, thin=art(above),art(edge)
                self.assertLess(abs(thin.width/broad.width-1),.2)
                self.assertLess(thin.height, .55*broad.height)

    def test_top_appearances_distinguish_narrow_from_round(self):
        narrow=art('maize-top'); round_leaf=art('lotus-blade')
        self.assertGreater(narrow.width/narrow.height,3.2)
        self.assertLess(abs(round_leaf.width/round_leaf.height-1),.15)

    def test_dock_samples_share_the_same_neutral_palette(self):
        for key in EXAMPLES.values():
            image=neutral_shape(key)
            colors=image.getcolors(256)
            self.assertIsNotNone(colors)
            self.assertEqual({p for _,p in colors},{p for _,p in neutral_shape('gold-ginkgo').getcolors(256)})

    def test_record_options_distinguish_outline_veins_and_complete_record(self):
        results=[note_page(key=k) for k in ('pale-camphor','camphor-top')]
        self.assertNotEqual(results[0].tobytes(),results[1].tobytes())
        answers={name:im.tobytes() for name,im,_ in picture_options() if name.startswith('q5-')}
        self.assertEqual(len(set(answers.values())),4)


if __name__=='__main__':
    unittest.main()
