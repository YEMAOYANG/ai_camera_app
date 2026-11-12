"""Verify the shown parts, unknown locations, and original media registration."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import unittest
from unittest.mock import patch

LESSON = Path(__file__).resolve().parent.parent
spec = spec_from_file_location('lantern_quantity_diagrams', LESSON / 'diagrams' / 'render.py')
art = module_from_spec(spec)
spec.loader.exec_module(art)


class DiagramsTest(unittest.TestCase):
    def test_different_stories_show_the_same_two_parts(self):
        for a,b,event in ((6,3,'come'),(6,3,'still'),(3,6,'out')):
            with patch.object(art,'stamp') as stamp:
                art.two_groups(a,b,event=event)
            points=[c.args[2] for c in stamp.call_args_list]
            self.assertEqual(len(points),9)
            self.assertEqual(len(set(points)),9)
            self.assertEqual(sum(x<360 for x,_ in points),a)

    def test_the_hidden_problem_renders_visible_lights_and_the_whole_number(self):
        with patch.object(art,'stamp') as stamp, patch.object(art,'mark') as mark:
            art.hidden(9,6)
        self.assertEqual([c.args[1] for c in stamp.call_args_list],['lantern-one']*6+['cloth-cover'])
        self.assertEqual([c.args[1] for c in mark.call_args_list],['?',9])

    def test_math_cards_change_question_location_instead_of_color(self):
        with patch.object(art,'mark') as mark:
            art.relation_icon('add',5,3)
            art.relation_icon('sub',8,3)
        calls=mark.call_args_list
        self.assertEqual([c.args[1] for c in calls],['?',5,3,8,3,'?'])
        self.assertEqual(calls[0].args[2],calls[3].args[2])
        self.assertEqual(calls[2].args[2],calls[5].args[2])

    def test_fact_family_and_stamp_check(self):
        minus=art.answer_icon('sub')
        self.assertEqual(minus.getpixel((66,93))[:3],(35,66,55))
        self.assertNotEqual(minus.getpixel((95,70))[:3],(35,66,55))
        with patch.object(art,'mark') as mark:
            art.family(6,3)
        self.assertEqual([c.args[1] for c in mark.call_args_list],['6+3=9','9-3=6','9-6=3'])
        with patch.object(art,'stamp') as stamp:
            im=art.whole(14,key='stamp-one',crossed=6)
        self.assertEqual(len(stamp.call_args_list),14)
        self.assertEqual(sum(im.getpixel(c.args[2])[:3]==(140,48,36) for c in stamp.call_args_list),6)

    def test_registered_assets_and_six_answer_positions(self):
        lesson=json.loads((LESSON/'lesson.json').read_text())
        manifest=json.loads((LESSON/'asset-sources.json').read_text())['assets']
        self.assertTrue(set(lesson['images'])<=set(manifest))
        for key,row in manifest.items():
            self.assertEqual(sha256((LESSON/row['file']).read_bytes()).hexdigest(),row['sha256'],key)
        quiz=next(s for s in lesson['scenes'] if s['type']=='quiz')
        self.assertEqual([q['answer'][0] for q in quiz['questions']],list('BCABAC'))
