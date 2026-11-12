from collections import deque
from pathlib import Path
import json
import runpy
import unittest

from PIL import Image

SOURCE = Path(__file__).resolve().parents[1]
ART = runpy.run_path(str(SOURCE/'art-source/diagrams.py'))
LESSON = json.loads((SOURCE/'lesson.json').read_text())
QUIZ = next(scene['questions'] for scene in LESSON['scenes'] if scene['type']=='quiz')
RED = (163, 64, 61)
BAG = (232, 185, 103)


def components(image, color, *, min_area=1):
    rgb=image.convert('RGB')
    pixel_bytes=iter(rgb.tobytes())
    pixels=zip(pixel_bytes,pixel_bytes,pixel_bytes)
    points={(i%rgb.width,i//rgb.width) for i,value in enumerate(pixels) if value==color}
    count=0
    while points:
        todo=deque([points.pop()])
        area=0
        while todo:
            x,y=todo.popleft()
            area+=1
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in points:
                    points.remove(point)
                    todo.append(point)
        if area>=min_area:
            count+=1
    return count


def picture(name):
    return Image.open(SOURCE/'assets'/(name+'.png'))


class ExactQuantityPictures(unittest.TestCase):
    def test_options_follow_exact_repeated_subtraction(self):
        expected={'fixed-group':5,'second-remainder':29-7-7,'stop-short':[5,1],
                  'stop-zero':[3,0],'compare-packs':[4,3]}
        self.assertEqual([q['answer'][0] for q in QUIZ],['b','a','c','b','a'])
        for item in QUIZ:
            key=item['id']
            truth=ART['QUIZ'][key]
            value=truth['options']['abc'.index(item['answer'][0])]
            self.assertEqual(value,expected[key])
            if key in ('stop-short','stop-zero'):
                self.assertEqual(value,list(divmod(truth['total'],truth['size'])))
        self.assertEqual(expected['compare-packs'],[24//6,24//8])

    def test_badges_bags_and_remainders_are_visible_in_the_actual_pngs(self):
        self.assertEqual(components(picture('quiz-fixed-prompt'),RED),23)
        for name,count in ART['QUIZ'].items():
            for key,value in zip('abc',count['options']):
                img=picture('quiz-'+name+'-'+key)
                if name in ('fixed-group','second-remainder'):
                    self.assertEqual(components(img,RED),value)
                elif name in ('stop-short','stop-zero'):
                    self.assertEqual(components(img,BAG,min_area=130),value[0])
                    self.assertEqual(components(img,RED),value[1])
                else:
                    for index,full in enumerate(value):
                        crop=img.crop((0,index*168,500,index*168+168))
                        self.assertEqual(components(crop,BAG,min_area=130),full)
                        self.assertEqual(components(crop,RED),count['sizes'][index])
        for amount in ART['ROUTE_VALUES']:
            self.assertEqual(components(picture('station-'+str(amount)),RED),amount)
