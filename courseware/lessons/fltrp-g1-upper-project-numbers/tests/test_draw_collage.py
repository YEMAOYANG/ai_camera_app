"""Keep every number and count marking tied to an exact picture."""
import importlib.util
import json
from pathlib import Path
import unittest

LESSON = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('draw_collage', LESSON/'art-source/draw_collage.py')
draw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draw)


class CollagePictureTest(unittest.TestCase):
    def test_positions_keep_each_cutout_separate_in_both_arrangements(self):
        for scattered in (False,True):
            points=draw.positions(10,scattered)
            self.assertEqual(len(set(points)),10)
            for i,(x,y) in enumerate(points):
                for a,b in points[i+1:]:
                    self.assertGreaterEqual((x-a)**2+(y-b)**2,69**2)

    def test_source_has_all_ten_spoken_card_positions(self):
        definitions=json.loads((LESSON/'art-source/project-math.json').read_text())
        first=definitions['strip-one-five'][1][0]
        second=definitions['strip-six-ten'][1][0]
        self.assertEqual(first+second,list(range(1,11)))
        self.assertEqual(definitions['collage-four-half'][1],['star',4,2])
        self.assertEqual(definitions['collage-four-full'][1],['star',4,4])

    def test_delivery_card_category_is_separate_from_exact_dots(self):
        for count in range(1,11):
            card = draw.game_group('book',count)
            self.assertEqual(card.size,(240,158))
            dots = [card.getpixel((133+21*(i%5),106+22*(i//5)))[:3] for i in range(10)]
            self.assertEqual(dots.count((33,77,60)),count)
        with self.assertRaises(ValueError):
            draw.game_group('book',11)

    def test_quiz_option_images_match_counts_and_tracking(self):
        lesson=json.loads((LESSON/'lesson.json').read_text())
        diagrams=json.loads((LESSON/'art-source/project-math.json').read_text())
        quiz=next(s['questions'] for s in lesson['scenes'] if s['type']=='quiz')
        expected=[
            ('B','collage',['leaf',8,False]),('A','collage',['ruler',10,False]),('C','collage',['leaf',6,True]),
            ('B','group_mix',['ruler',4,'book',2]),('A','group_mix',['book',9,'ruler',1]),
            ('C','tracked',['leaf',7,list(range(7))]),
        ]
        for q,(letter,kind,params) in zip(quiz,expected,strict=True):
            with self.subTest(id=q['id']):
                self.assertEqual(q['answer'],[letter])
                key=q['options'][letter]['visual']['image']
                self.assertEqual(diagrams[key][:2],[kind,params])
