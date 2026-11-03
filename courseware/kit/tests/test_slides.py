import json
import unittest

from courseware.kit import slides
from courseware.tools import check


IMAGES = {'pic': '/api/classroom-media/stage/media/pic.png'}
CASES = {
    'title-picture': {'title': '认识事物', 'picture': 'pic', 'caption': '仔细观察图片'},
    'picture-points': {'title': '一起观察', 'picture': 'pic', 'points': ['看一看', '说一说']},
    'two-columns': {'title': '比较', 'left': {'heading': '左边', 'body': '认真看看左边'},
                    'right': {'heading': '右边', 'body': '认真看看右边'},
                    'left_picture': 'pic', 'right_picture': 'pic'},
    'big-word': {'title': '认识字', 'word': '山', 'pinyin': 'shān', 'hint': '跟着老师说', 'picture': 'pic'},
    'steps': {'title': '动手做', 'steps': ['先看一看', '再摆一摆', '最后说一说']},
    'summary': {'title': '回顾', 'items': ['观察图片', '说出发现', '再试一次']},
}


class SlideTests(unittest.TestCase):
    def test_templates_and_invariants(self):
        self.assertEqual(set(slides.template_names()), set(CASES))
        for template, data in CASES.items():
            with self.subTest(template=template):
                result = slides.render(template, data, image_urls=IMAGES)
                again = slides.render(template, data, image_urls=IMAGES)
                self.assertEqual(json.dumps(result, ensure_ascii=False), json.dumps(again, ensure_ascii=False))
                elements = result['elements']
                ids = [element['id'] for element in elements]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(set(result['names'].values()) <= set(ids))
                for element in elements:
                    self.assertGreaterEqual(element['left'], 0)
                    self.assertGreaterEqual(element['top'], 0)
                    self.assertLessEqual(element['left'] + element['width'], 1000)
                    self.assertLessEqual(element['top'] + element['height'], 562.5)
                    if element['type'] == 'text':
                        self.assertEqual(slides.text_box(element), check.text_box(element))
                        self.assertLessEqual(check.text_box(element)[3], element['top'] + element['height'])
                self.assertEqual(slides.canvas(elements), slides.canvas(again['elements']))

    def test_each_template_rejects_bad_data(self):
        errors = {
            'title-picture': ({'title': '标题'}, 'bad_data'),
            'picture-points': ({'title': '标题', 'picture': 'pic', 'points': ['一'] * 5}, 'bad_data'),
            'two-columns': ({'title': '标题', 'left': {'heading': '', 'body': '字'}, 'right': {}}, 'bad_data'),
            'big-word': ({'word': '山', 'hint': '提示', 'picture': 'absent'}, 'image_missing'),
            'steps': ({'title': '标题', 'steps': ['字' * 60, '字', '字', '字', '字']}, 'text_too_long'),
            'summary': ({'title': '标题', 'items': ['字', '']}, 'bad_data'),
        }
        for template, (data, code) in errors.items():
            with self.subTest(template=template):
                with self.assertRaises(slides.LayoutError) as caught:
                    slides.render(template, data, image_urls=IMAGES)
                self.assertEqual(caught.exception.args[0], code)
        with self.assertRaises(slides.LayoutError) as caught:
            slides.render('missing', {}, image_urls=IMAGES)
        self.assertEqual(caught.exception.args, ('unknown_template', 'missing'))

    def test_long_chinese_text_passes_g2(self):
        text = '看一看图片里的事物并说出你的发现'
        cases = {
            'title-picture': {'title': text, 'picture': 'pic', 'caption': text},
            'picture-points': {'title': text, 'picture': 'pic', 'points': [text] * 4},
            'two-columns': {'title': text, 'left': {'heading': '左边的发现', 'body': text * 2},
                            'right': {'heading': '右边的发现', 'body': text * 2}},
            'big-word': {'word': '大山', 'hint': text, 'pinyin': 'dà shān'},
            'steps': {'title': text, 'steps': [text] * 5},
            'summary': {'title': text, 'items': [text] * 5},
        }
        for template, data in cases.items():
            with self.subTest(template=template):
                result = slides.render(template, data, image_urls=IMAGES)
                body = {'stage': {}, 'scenes': [{'type': 'slide', 'content': {
                    'canvas': slides.canvas(result['elements'], result['background'])}}]}
                self.assertEqual([issue for issue in check.check_classroom(body) if issue['gate'] == 'G2'], [])
                for element in result['elements']:
                    if element['type'] == 'text':
                        self.assertEqual(slides.text_box(element), check.text_box(element))
                        self.assertLessEqual(check.text_box(element)[3], element['top'] + element['height'])

    def test_escape_aspect_and_font_fitting(self):
        result = slides.render('title-picture', {'title': '甲 & <乙>', 'picture': 'pic'},
                               image_urls=IMAGES, aspects={'pic': 1})
        title, picture = result['elements']
        self.assertIn('甲 &amp; &lt;乙&gt;', title['content'])
        self.assertIn('font-size:36px', title['content'])
        self.assertEqual(picture['width'], picture['height'])
        self.assertEqual(picture['height'], 332)
        with self.assertRaises(slides.LayoutError) as caught:
            slides.render('title-picture', {'title': '字', 'picture': 'pic'}, image_urls=IMAGES,
                          aspects={'pic': 0})
        self.assertEqual(caught.exception.args[0], 'bad_data')


if __name__ == '__main__':
    unittest.main()
