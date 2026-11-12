import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from PIL import ImageColor


SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('draw_place_value', SOURCE/'art-source'/'draw_place_value.py')
DRAW = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRAW)


class PlaceValueDiagramsTest(unittest.TestCase):
    def test_deterministic_art_matches_registered_playback(self):
        lesson = json.loads((SOURCE/'lesson.json').read_text())
        proof = json.loads((SOURCE/'asset-provenance.json').read_text())
        registered = {key for key, row in proof['assets'].items() if row['kind']=='deterministic_semantic_diagram'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = DRAW.write_assets(root/'first')
            self.assertEqual(first, DRAW.write_assets(root/'second'))
            self.assertEqual(set(first), registered)
            for key, record in first.items():
                self.assertEqual(record['file'], lesson['images'][key]['file'])
                self.assertEqual(record['sha256'], proof['assets'][key]['sha256'])
                self.assertEqual((root/'first'/(key+'.png')).read_bytes(),(SOURCE/record['file']).read_bytes())

    def test_stamp_options_show_nine_ten_and_eleven_pieces(self):
        green = ImageColor.getrgb(DRAW.GREEN)
        for count in (9,10,11):
            image = DRAW.tray(count).image
            centers = [(126+i%5*57,74+i//5*57) for i in range(15)]
            self.assertEqual(sum(image.getpixel(xy)==green for xy in centers),count)

    def test_group_of_ten_and_seven_outside_do_not_overlap(self):
        image = DRAW.count_board(True,7).image
        green = ImageColor.getrgb(DRAW.GREEN)
        inside = [(100+i%5*71,134+i//5*71) for i in range(10)]
        outside = [(505+i%3*55,134+i//3*55) for i in range(9)]
        self.assertTrue(all(image.getpixel(xy)==green for xy in inside))
        self.assertEqual(sum(image.getpixel(xy)==green for xy in outside),7)
        self.assertLess(max(x for x,y in inside)+21,min(x for x,y in outside)-19)

    def test_place_value_diagram_moves_ten_unit_beads_to_one_tens_bead(self):
        orange = ImageColor.getrgb(DRAW.ORANGE)
        def bead_count(image,x):
            pixels = [image.getpixel((x,y))==orange for y in range(190)]
            return sum(val and not prev for prev,val in zip([False]+pixels,pixels))
        before = DRAW.abacus_card(0,10).image
        after = DRAW.abacus_card(1,0).image
        left,right = (round(220*(.12+.76*part)) for part in (.27,.73))
        self.assertEqual((bead_count(before,left),bead_count(before,right)),(0,10))
        self.assertEqual((bead_count(after,left),bead_count(after,right)),(1,0))


if __name__=='__main__':
    unittest.main()
