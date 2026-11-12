"""Keep the paper, sample position and visibility result consistent."""
from pathlib import Path
import json
import sys
import unittest
from hashlib import sha256
from io import BytesIO

from PIL import ImageColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'diagrams'))
from compose import SIGNAL, compositions
from render import BLUE, ORANGE, SAMPLES, TARGET, TARGET_RADIUS, controlled_view


class MaterialModels(unittest.TestCase):
    def test_every_sample_uses_the_same_reference_shape_and_position(self):
        for symbol in ('ring','triangle'):
            control=[controlled_view(kind,symbol).crop((200,15,310,102)).tobytes() for kind in SAMPLES]
            self.assertEqual(len(set(control)),1)

    def test_only_clear_sample_shows_the_same_teaching_ring(self):
        x,y=TARGET
        test_pixel=(x+TARGET_RADIUS-2,y)
        self.assertEqual(controlled_view('clear').getpixel(test_pixel),ImageColor.getrgb(ORANGE))
        self.assertEqual(controlled_view('clear').getpixel((test_pixel[0],59)),ImageColor.getrgb(ORANGE))
        for kind in ('wood','metal'):
            self.assertNotEqual(controlled_view(kind).getpixel(test_pixel),ImageColor.getrgb(ORANGE))

    def test_quiz_uses_a_different_mark_and_opaque_foils_hide_it(self):
        x,y=TARGET
        clear=controlled_view('clear','triangle')
        self.assertEqual(clear.getpixel((x,y)),ImageColor.getrgb(BLUE))
        for kind in ('wood','metal'):
            self.assertNotEqual(controlled_view(kind,'triangle').getpixel((x,y)),ImageColor.getrgb(BLUE))

    def test_art_plan_covers_each_lesson_image_and_declared_view(self):
        read=lambda name:json.loads((ROOT/name).read_text())
        lesson,plan=read('lesson.json'),read('art-plan.json')
        raw={a['assetKey'] for atlas in plan['atlases'] for a in atlas['assets']}
        planned=set(plan['compositions'])|raw|set(plan['finishedSemanticDiagrams'])
        self.assertLessEqual(set(lesson['images']),planned)
        self.assertEqual(len(raw),sum(len(a['assets']) for a in plan['atlases']))
        for compose in plan['compositions'].values():
            self.assertLessEqual(set(compose['sources']),raw)
        for key in plan['finishedSemanticDiagrams']:
            self.assertTrue((ROOT/lesson['images'][key]['file']).is_file())

    def test_every_game_cue_reuses_a_line_from_another_scene(self):
        lesson=json.loads((ROOT/'lesson.json').read_text())
        narration={f"{s['key']}-{i}":(s['key'],action['say']) for s in lesson['scenes']
                   for i,action in enumerate(s.get('script',[]),1) if 'say' in action}
        games=[s for s in lesson['scenes'] if s['type']=='interactive']
        self.assertEqual(len(games),2)
        for scene in games:
            own={a['say'] for a in scene['script'] if 'say' in a}
            self.assertEqual(len(scene['gameAudio']),6)
            for action_id in scene['gameAudio'].values():
                key,text=narration[action_id]
                self.assertNotEqual(key,scene['key'])
                self.assertNotIn(text,own)

    def test_compositions_rebuild_and_keep_only_the_metal_clasp_circled(self):
        records = json.loads((ROOT / 'asset-sources.json').read_text())['assets']
        rendered = compositions()
        for key, image in rendered.items():
            with self.subTest(key=key):
                output = BytesIO()
                image.save(output, format='PNG', optimize=True)
                self.assertEqual(sha256(output.getvalue()).hexdigest(), records[key]['sha256'])

        marked = rendered['quiz-fabric-snap-stimulus']
        self.assertEqual(marked.getpixel((331, 154)), ImageColor.getrgb(SIGNAL))
        self.assertNotEqual(marked.getpixel((331, 194)), ImageColor.getrgb(SIGNAL))
        self.assertNotEqual(marked.getpixel((185, 194)), ImageColor.getrgb(SIGNAL))


if __name__=='__main__':
    unittest.main()
