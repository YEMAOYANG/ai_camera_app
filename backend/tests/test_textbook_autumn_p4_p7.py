import unittest

from content.textbook_autumn_p4_p7 import VALIDATORS, apply_page, initial_page
from core.errors import ApiError


class AutumnPageOperationTests(unittest.TestCase):
    def setUp(self):
        self.ids = {n: VALIDATORS['scene-p' + str(n)] for n in range(4, 8)}

    def apply(self, n, state, name, **values):
        apply_page(self.ids[n], state, {'name': name, **values})

    def test_paragraphs_recompute_placements_and_support_revision(self):
        s = initial_page(self.ids[4])
        with self.assertRaises(ApiError): self.apply(4, s, 'place', token='token1', slot='slot1')
        self.apply(4, s, 'start')
        self.apply(4, s, 'place', token='token1', slot='slot2')
        self.apply(4, s, 'place', token='token2', slot='slot1')
        self.apply(4, s, 'place', token='token3', slot='slot3')
        self.assertFalse(s['completed'])
        self.assertEqual(s['attempts'][-1]['helpCount'], 0)
        self.assertEqual(s['helpCount'], 1)
        self.apply(4, s, 'place', token='token1', slot='slot1')
        self.apply(4, s, 'place', token='token2', slot='slot2')
        self.assertTrue(s['completed'])
        self.assertEqual(s['attempts'][-1]['helpCount'], 1)
        self.apply(4, s, 'reset'); self.assertFalse(s['completed'])
        with self.assertRaises(ApiError): apply_page(self.ids[4], s, {'name': 'place', 'token': 'token1', 'slot': 'slot1', 'completed': True})

    def test_ten_picture_words_require_requests_and_first_comparison(self):
        s = initial_page(self.ids[5]); self.apply(5, s, 'start')
        with self.assertRaises(ApiError): self.apply(5, s, 'choose', object='autumn')
        self.apply(5, s, 'listen'); self.apply(5, s, 'choose', object='winter')
        self.assertFalse(s['attempts'][-1]['passed'])
        self.assertEqual(s['attempts'][-1]['helpCount'], 0)
        self.assertEqual(s['attempts'][-1]['support'], 'picture_and_teacher_audio')
        self.assertEqual(s['helpCount'], 1)
        self.apply(5, s, 'choose', object='autumn'); self.apply(5, s, 'next')
        self.assertEqual(s['attempts'][-1]['helpCount'], 1)
        with self.assertRaises(ApiError): self.apply(5, s, 'compareDone')
        self.apply(5, s, 'compareListen', value='qiu'); self.apply(5, s, 'compareListen', value='hui')
        self.apply(5, s, 'compareDone')
        for i, value in enumerate(('weather', 'change', 'tree', 'leaf', 'yellow', 'single', 'from-tree', 'toward', 'flying'), 1):
            self.assertEqual(s['index'], i); self.apply(5, s, 'listen'); self.apply(5, s, 'choose', object=value)
            if i < 9: self.apply(5, s, 'next')
        self.assertTrue(s['completed']); self.assertEqual(len(s['placed']), 10)

    def test_return_token_and_single_point_failed_stroke(self):
        s = initial_page(self.ids[4]); self.apply(4, s, 'start'); self.apply(4, s, 'place', token='token1', slot='slot1')
        self.apply(4, s, 'return', token='token1'); self.assertIsNone(s['slots']['slot1'])
        s = initial_page(self.ids[6]); self.apply(6, s, 'start')
        self.apply(6, s, 'stroke', character='了', points=[{'x': 10, 'y': 10}])
        self.assertFalse(s['attempts'][-1]['passed'])
        self.assertEqual(s['attempts'][-1]['helpCount'], 0)
        self.assertEqual(s['helpCount'], 1)
        self.apply(6, s, 'stroke', character='了', points=[{'x': 500, 'y': 900}])
        self.assertFalse(s['attempts'][-1]['passed'])
        self.assertEqual(s['attempts'][-1]['helpCount'], 1)

    def test_strokes_are_recomputed_from_bounded_points_not_result_flags(self):
        s = initial_page(self.ids[6]); self.apply(6, s, 'start')
        with self.assertRaises(ApiError): self.apply(6, s, 'stroke', character='了', points=[])
        self.apply(6, s, 'stroke', character='了', points=[{'x': 0, 'y': 0}, {'x': 1, 'y': 1}, {'x': 2, 'y': 2}])
        self.assertFalse(s['attempts'][-1]['passed'])
        paths = {
            '了': [[(48,38),(88,38),(128,38),(109,58),(90,78)], [(90,78),(104,104),(110,130),(106,149),(94,158),(82,146)]],
            '子': [[(48,36),(87,36),(126,36),(107,54),(88,72)], [(88,72),(102,100),(108,128),(104,148),(92,158),(80,146)],
                  [(32,100),(90,100),(148,100)]]}
        for char, strokes in paths.items():
            for stroke in strokes:
                self.apply(6, s, 'stroke', character=char, points=[{'x': x, 'y': y} for x,y in stroke])
        self.assertTrue(s['completed']); self.assertEqual(len(s['strokes']['了']), 2)
        self.apply(6, s, 'undo', character='子'); self.assertFalse(s['completed'])
        with self.assertRaises(ApiError): apply_page(self.ids[6], s, {'name': 'stroke', 'character': '子', 'points': [], 'valid': True})

    def test_writing_try_redo_remain_separate_when_switching(self):
        s=initial_page(self.ids[6]);self.apply(6,s,'start')
        points=[{'x': 48,'y': 38},{'x':128,'y':38},{'x':90,'y':78}]
        self.apply(6,s,'stroke',character='了',points=points);self.assertEqual(len(s['strokes']['了']),1)
        self.apply(6,s,'retry');self.assertEqual(s['versionMode'],'redo');self.assertEqual(s['strokes']['了'],[])
        self.apply(6,s,'stroke',character='子',points=[{'x':5,'y':5}])
        self.apply(6,s,'version',mode='try');self.assertEqual(len(s['strokes']['了']),1);self.assertEqual(s['strokes']['子'],[])
        self.apply(6,s,'version',mode='redo');self.assertEqual(len(s['strokes']['子']),1);self.assertFalse(s['completed'])

    def test_sky_requires_both_variables_and_a_second_scene(self):
        s = initial_page(self.ids[7]); self.apply(7, s, 'start')
        with self.assertRaises(ApiError): self.apply(7, s, 'choose', value='both')
        for _ in range(6): self.apply(7, s, 'blue')
        for _ in range(3): self.apply(7, s, 'height')
        self.apply(7, s, 'choose', value='so'); self.assertFalse(s['completed'])
        self.apply(7, s, 'nextSky')
        for _ in range(5): self.apply(7, s, 'blue')
        for _ in range(4): self.apply(7, s, 'height')
        self.apply(7, s, 'choose', value='both'); self.assertTrue(s['completed'])
        self.apply(7, s, 'reset'); self.assertFalse(s['completed'])


if __name__ == '__main__': unittest.main()
