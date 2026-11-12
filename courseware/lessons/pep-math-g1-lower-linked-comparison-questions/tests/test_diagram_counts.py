"""Check the countable pixels of the delivered diagrams after rendering."""

from itertools import groupby
from pathlib import Path
import unittest

from PIL import Image, ImageColor


ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def visible_marks(key, color, *, y, x, width):
    rgb = ImageColor.getrgb(color)
    with Image.open(ASSETS / f'{key}.png') as image:
        countable = [any(image.getpixel((col, row)) == rgb for row in range(y-14,y+15))
                     for col in range(x,x+width)]
    return [len(list(run)) for colored,run in groupby(countable) if colored]


class DiagramCounts(unittest.TestCase):
    def test_known_groups_leave_a_gap_from_the_number_card(self):
        cases = {'story-known':18, 'story-compare':18, 'story-more':21,
                 'hop-1':8, 'hop-2':9, 'hop-3':20, 'delivery-1':12,
                 'q1':11, 'q2':17, 'q3':13, 'q4':22, 'q5':19}
        for key,count in cases.items():
            with self.subTest(key=key):
                # The number card ends at x124. A mark's solid fill must start
                # at x135 or later and fit entirely inside the row.
                self.assertEqual(visible_marks(key,'#357761',y=141,x=125,width=10),[])
                width=510 if key=='story-known' else 600
                self.assertEqual(len(visible_marks(key,'#357761',y=141,x=135,width=width)),count)

    def test_campground_choices_show_nineteen_and_the_five_extra(self):
        self.assertEqual(len(visible_marks('q5-a','#35758b',y=189,x=50,width=430)),10)
        self.assertEqual(len(visible_marks('q5-a','#35758b',y=250,x=50,width=430)),9)
        self.assertEqual(len(visible_marks('q5-b','#cf7940',y=198,x=339,width=143)),5)


if __name__ == '__main__':
    unittest.main()
