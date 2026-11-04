import unittest

from courseware.tools.check import check_classroom


def speech(text):
    return {'type': 'speech', 'text': text, 'audioUrl': '/a.wav'}


def slide(lit, spoken=('先看这一点。',)):
    elements = [{'id': 'text_point-%d' % n, 'type': 'text', 'left': 20, 'top': 20 + 60 * n, 'width': 300, 'content': '<p style="font-size:20px">点</p>'} for n in (1, 2, 3)]
    actions = [{'type': 'spotlight', 'elementId': 'text_point-%d' % n} for n in lit] + [speech(text) for text in spoken]
    return {'type': 'slide', 'actions': actions, 'content': {'canvas': {'elements': elements}}}


def issues_of(scene, code):
    return [i for i in check_classroom({'scenes': [scene]}, teaching=True) if i['code'] == code]


class TeachingScriptTests(unittest.TestCase):
    def test_tone_marked_pinyin_is_refused_in_a_spoken_line_only_for_a_teaching_lesson(self):
        scene = slide([1, 2, 3], ['江读 jiāng，第一声。'])
        found = issues_of(scene, 'speech_pinyin')
        self.assertEqual([(i['gate'], i['scene'], i['severity']) for i in found], [('G3', 1, 'error')])
        self.assertEqual([i for i in check_classroom({'scenes': [scene]}) if i['code'] == 'speech_pinyin'], [])
        self.assertEqual(issues_of(slide([1, 2, 3], ['江，第一声，声音平平的。']), 'speech_pinyin'), [])

    def test_every_numbered_text_of_a_slide_is_lit_in_order(self):
        self.assertEqual(issues_of(slide([1, 2, 3]), 'spotlight_gap'), [])
        self.assertEqual(issues_of(slide([1, 1, 2, 3]), 'spotlight_gap'), [])
        for lit in ([1, 2], [1, 3, 2], [3, 2, 1], []):
            found = issues_of(slide(lit), 'spotlight_gap')
            self.assertEqual([(i['gate'], i['severity']) for i in found], [('G3', 'error')], lit)

    def test_a_slide_without_numbered_texts_needs_no_ordered_spotlights(self):
        scene = {'type': 'slide', 'actions': [speech('看图。')], 'content': {'canvas': {'elements': [
            {'id': 'image_picture', 'type': 'image', 'left': 0, 'top': 0, 'width': 100, 'height': 100}]}}}
        self.assertEqual(issues_of(scene, 'spotlight_gap'), [])


if __name__ == '__main__':
    unittest.main()
