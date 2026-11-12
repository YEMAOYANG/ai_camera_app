"""Check the experimental setup and visible changes encoded in the diagrams."""
from pathlib import Path
import json
import sys
import unittest

from PIL import ImageChops, ImageColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'diagrams'))
from compositions import (COPPER_POLISH_START, PAPER, WIRE_REGIONS, WIRE_RING_RADIUS,
                          asset, copper_before_polishing, wire_choice)
from render import (EDGE, FAIR, SIGNAL, TEACHING_SETUP, UNEQUAL_LENGTH, UNEQUAL_PRESS,
                    bend_result, quiz_tip_view, setup_pair)


class MetalModels(unittest.TestCase):
    def test_fair_setup_keeps_length_thickness_and_pressure_position(self):
        self.assertEqual(FAIR[0],FAIR[1])
        self.assertEqual(TEACHING_SETUP,(FAIR[0],)*3)
        self.assertNotEqual(UNEQUAL_LENGTH[0][0],UNEQUAL_LENGTH[1][0])
        self.assertNotEqual(UNEQUAL_PRESS[0][2],UNEQUAL_PRESS[1][2])
        mark=ImageColor.getrgb(SIGNAL)
        for rows in (FAIR, UNEQUAL_LENGTH, UNEQUAL_PRESS):
            img=setup_pair(rows)
            for index, (_,_,offset) in enumerate(rows):
                self.assertEqual(img.getpixel((56+offset,80+149*index)),mark)

    def test_side_view_exposes_the_thinner_tip_and_foils_do_not(self):
        color=ImageColor.getrgb(EDGE)
        image=quiz_tip_view('side')
        self.assertEqual(image.getpixel((275,108)),color)
        self.assertEqual(image.getpixel((275,124)),color)
        self.assertNotEqual(image.getpixel((275,91)),color)
        self.assertEqual(quiz_tip_view('straight').getpixel((275,88)),color)
        self.assertEqual(quiz_tip_view('top').getpixel((275,79)),color)

    def test_bends_in_opposite_directions_keep_the_same_start(self):
        a,b=bend_result(-1),bend_result(1)
        self.assertEqual(a.crop((35,114,100,137)).tobytes(),b.crop((35,114,100,137)).tobytes())
        self.assertNotEqual(a.crop((221,64,273,196)).tobytes(),b.crop((221,64,273,196)).tobytes())

    def test_polishing_changes_only_the_marked_end_of_the_same_copper_shape(self):
        after=asset('metal-top-copper')
        before=copper_before_polishing(after)
        untouched=(0,0,COPPER_POLISH_START,after.height)
        self.assertEqual(before.crop(untouched).tobytes(),after.crop(untouched).tobytes())
        self.assertEqual(before.getchannel('A').tobytes(),after.getchannel('A').tobytes())
        self.assertLess(sum(before.getpixel((312,50))[:3]),sum(after.getpixel((312,50))[:3]))

    def test_copper_question_circles_move_without_changing_the_cable(self):
        original=wire_choice()
        for region,(x,y) in WIRE_REGIONS.items():
            with self.subTest(region=region):
                rgb=original.getpixel((x,y))
                if region=='gap':
                    self.assertEqual(rgb,ImageColor.getrgb(PAPER))
                elif region=='coating':
                    self.assertGreater(rgb[1],rgb[0])
                else:
                    self.assertGreater(rgb[0],rgb[1])
                marker=ImageChops.difference(original,wire_choice(region)).getbbox()
                r=WIRE_RING_RADIUS
                self.assertEqual(marker,(x-r,y-r,x+r+1,y+r+1))

    def test_art_plan_covers_every_picture_and_the_two_views(self):
        read=lambda name:json.loads((ROOT/name).read_text())
        lesson,plan=read('lesson.json'),read('art-plan.json')
        generated=[a['assetKey'] for atlas in plan['atlases'] for a in atlas['assets']]
        self.assertEqual(len(generated),len(set(generated)))
        self.assertEqual(set(lesson['images']),set(plan['compositions'])|set(generated)|set(plan['finishedSemanticDiagrams']))
        for key in plan['finishedSemanticDiagrams']:
            self.assertTrue((ROOT/lesson['images'][key]['file']).is_file())

    def test_game_cues_reuse_teacher_lines_from_other_scenes(self):
        lesson=json.loads((ROOT/'lesson.json').read_text())
        speeches={f"{s['key']}-{i}":(s['key'],a['say']) for s in lesson['scenes']
                  for i,a in enumerate(s.get('script',[]),1) if 'say' in a}
        for game in [s for s in lesson['scenes'] if s['type']=='interactive']:
            self.assertEqual(len(game['gameAudio']),6)
            spoken={a['say'] for a in game['script'] if 'say' in a}
            for ref in game['gameAudio'].values():
                page,text=speeches[ref]
                self.assertNotEqual(page,game['key'])
                self.assertNotIn(text,spoken)


if __name__=='__main__':
    unittest.main()
