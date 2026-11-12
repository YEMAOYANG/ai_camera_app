"""Test the precise observation diagrams and the offline lesson contracts."""
from pathlib import Path
from copy import deepcopy
import json
import sys
import unittest

from PIL import Image, ImageColor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'diagrams'))
from render import (BLUE, FAIR, QUIZ_RISE, UNEQUAL_DIP, UNEQUAL_WIDTH, WATERLINE, basin, tug_result)
from paper_views import MESHES, paper_view, pull_test
from courseware.tools import check,verify
from backend.content.courseware_observation import project_snapshot


class PaperModels(unittest.TestCase):
    def test_equal_size_depth_controls_and_both_foils(self):
        self.assertEqual(FAIR[0],FAIR[1])
        self.assertNotEqual(UNEQUAL_WIDTH[0][0],UNEQUAL_WIDTH[1][0])
        self.assertEqual(UNEQUAL_WIDTH[0][1],UNEQUAL_WIDTH[1][1])
        self.assertNotEqual(UNEQUAL_DIP[0][1],UNEQUAL_DIP[1][1])
        self.assertEqual(UNEQUAL_DIP[0][0],UNEQUAL_DIP[1][0])

    def test_wet_fronts_are_measured_from_the_same_drawn_waterline(self):
        self.assertEqual(tuple(sorted(QUIZ_RISE)),QUIZ_RISE)
        blue=ImageColor.getrgb(BLUE)
        for rise in QUIZ_RISE:
            view=basin((FAIR[0],),(rise,))
            self.assertEqual(view.getpixel((228,WATERLINE)),blue)
            self.assertEqual(view.getpixel((228,WATERLINE-rise)),blue)
            self.assertNotEqual(view.getpixel((228,WATERLINE-rise-5)),blue)

    def test_selected_tug_model_leaves_the_tan_sample_connected(self):
        paired=tug_result((True,False))
        reversed_pair=tug_result((False,True))
        self.assertNotEqual(paired.getpixel((225,90)),reversed_pair.getpixel((225,90)))
        self.assertNotEqual(paired.getpixel((225,196)),reversed_pair.getpixel((225,196)))

    def test_capture_images_reproduce_both_views_of_each_model(self):
        for sample in MESHES:
            for direction in ('top','side'):
                with self.subTest(sample=sample,direction=direction):
                    with Image.open(ROOT/'assets'/f'paper-{direction}-{sample}.png') as saved:
                        self.assertEqual(saved.tobytes(),paper_view(sample,direction=='top').tobytes())
            self.assertNotEqual(paper_view(sample,True).tobytes(),paper_view(sample,False).tobytes())

    def test_pull_choices_hold_width_fixed_and_only_kraft_is_unbroken(self):
        for sample in ('tissue','news','kraft'):
            with self.subTest(sample=sample):
                image=pull_test(sample)
                self.assertEqual(image.getpixel((125,132)),image.getpixel((125,170)))
                self.assertNotEqual(image.getpixel((125,133)),image.getpixel((125,132)))
                self.assertEqual(image.getpixel((208,151))==image.getpixel((208,182)),sample!='kraft')

    def test_observation_card_requires_three_complete_matching_pairs(self):
        lesson=json.loads((ROOT/'lesson.json').read_text())
        scene=next(scene for scene in lesson['scenes'] if scene['key']=='photograph-paper-shapes')
        card=scene['observationCard']
        scene_id='scene-'+scene['key']
        snapshot=dict(schemaVersion='mira.game.observation.v1',sceneId=scene_id,kind='simulation',levels=[])
        for number,sample in enumerate(('kraft','news','print'),1):
            snapshot['levels'].append(dict(level=number,trials=[
                dict(trialId='same-paper-two-views',top='paper-top-'+sample,side='paper-side-'+sample)]))
        result=project_snapshot(card,scene_id,snapshot)
        self.assertEqual(len(result['levels']),3)
        self.assertIn('只记实际看到的',result['familyTask'])
        partial=deepcopy(snapshot)
        partial['levels'].pop()
        with self.assertRaisesRegex(ValueError,'invalid observation snapshot'):
            project_snapshot(card,scene_id,partial)
        mixed=deepcopy(snapshot)
        mixed['levels'][1]['trials'][0]['side']='paper-side-kraft'
        with self.assertRaisesRegex(ValueError,'undeclared observation outcome'):
            project_snapshot(card,scene_id,mixed)

    def test_plans_cover_all_art_and_game_audio_references(self):
        read=lambda name:json.loads((ROOT/name).read_text())
        lesson,plan=read('lesson.json'),read('art-plan.json')
        planned=[a['assetKey'] for atlas in plan['atlases'] for a in atlas['assets']]
        self.assertEqual(len(planned),len(set(planned)))
        self.assertEqual(set(lesson['images']),set(planned)|set(plan['compositions'])|set(plan['finishedSemanticDiagrams']))
        for key in plan['finishedSemanticDiagrams']:
            self.assertTrue((ROOT/lesson['images'][key]['file']).is_file())
        lines={f"{s['key']}-{i}":(s['key'],a['say']) for s in lesson['scenes']
               for i,a in enumerate(s.get('script',[]),1) if 'say' in a}
        games=[s for s in lesson['scenes'] if s['type']=='interactive']
        self.assertEqual(sum(len(s['gameAudio']) for s in games),14)
        for scene in games:
            for key in scene['gameAudio'].values():
                self.assertNotEqual(lines[key][0],scene['key'])

    def test_g0_accepts_string_objectives_with_verbatim_page_references(self):
        notes=json.loads((ROOT/'official-notes.json').read_text())
        evidence=notes['objectiveEvidence']
        self.assertEqual(notes['objectives'],[r['goal'] for r in evidence])
        self.assertEqual(len(evidence),4)
        self.assertTrue(all(r['pageRefs'] for r in evidence))
        self.assertEqual(len(verify._teaching_items(notes)),6)
        self.assertFalse([i for i in check.check_classroom({'scenes':[]},None,notes=notes,teaching=True) if i['gate']=='G0'])


if __name__=='__main__':
    unittest.main()
