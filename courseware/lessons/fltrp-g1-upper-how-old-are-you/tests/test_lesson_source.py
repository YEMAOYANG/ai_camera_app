from collections import Counter
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest

from PIL import Image

from courseware.kit import page
from courseware.tools.check import check_classroom


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT.parents[1] / 'kit/game_templates/catalog.json'
SPEC = importlib.util.spec_from_file_location('age_badge_art', ROOT / 'badge_art.py')
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


class AgeLessonSourceTests(unittest.TestCase):
    def test_exact_textbook_boundary_and_independent_quiz_answers(self):
        notes = load(ROOT / 'official-notes.json')
        identity = load(ROOT / 'identity.json')
        self.assertEqual(identity['nodeId'], notes['binding']['nodeId'])
        self.assertEqual(identity['revisionId'], '20260928-metadata-1')
        self.assertEqual(notes['textbookReview']['printedPages'], [50, 51, 52])
        self.assertEqual(notes['textbookReview']['boundaryAfter'], 53)
        self.assertEqual(notes['resources']['learningTaskSheet']['status'], 'not_provided')
        self.assertFalse([v for v in check_classroom({'scenes': []}, notes=notes, grade=1) if v['gate'] == 'G0'])
        quiz = next(scene for scene in load(ROOT / 'lesson.json')['scenes'] if scene['type'] == 'quiz')
        self.assertEqual(len(quiz['questions']), 6)
        self.assertEqual(Counter(q['answer'][0] for q in quiz['questions']), {'a': 2, 'b': 2, 'c': 2})
        self.assertEqual(len({q['id'] for q in quiz['questions']}), 6)

    def test_approved_entries_and_fixed_teaching_anchors(self):
        lesson = load(ROOT / 'lesson.json')
        catalog = load(CATALOG)
        versions = {v['entryPoint']: v for item in catalog['templates'] for v in item['versions']}
        games = [s for s in lesson['scenes'] if s['type'] == 'interactive']
        self.assertEqual(len(games), 2)
        entries = set()
        for scene in games:
            with self.subTest(scene=scene['key']):
                base = ROOT / 'pages' / scene['page']
                markup = base.with_suffix('.html').read_text()
                script = base.with_suffix('.js').read_text()
                entry = re.search(r'K\.game\((K\.gameTemplates\.\w+)\(', script)[1]
                entries.add(entry)
                self.assertEqual(versions[entry]['status'], '可用')
                self.assertTrue(versions[entry]['ownerApprovedOn'])
                self.assertEqual(scene['script'][0]['setState'], {'demo': True, 'level': 1, 'pause': True})
                self.assertEqual(scene['script'][-1]['setState'], {'demo': False, 'level': 1, 'pause': False})
                anchors = {beat['highlight'][1:] for beat in scene['script'] if 'highlight' in beat}
                self.assertTrue(anchors <= page.defined_ids(markup))
                self.assertTrue(all(anchor.startswith('demo-') for anchor in anchors))
                self.assertTrue(set(re.findall(r'__IMG:([^_]+)__', script)) <= set(lesson['images']))
        self.assertEqual(len(entries), 2)

    def test_planned_art_and_deterministic_badge_outputs(self):
        plan = load(ROOT / 'art-plan.json')
        keys = {key for record in plan['prompts'] for key in record['outputs']}
        keys.update(plan['localCandidateAndDerivedArt'])
        keys.update(plan['badgeDiagrams']['outputs'])
        provenance = load(ROOT / 'asset-provenance.json')
        source_only = set(plan['sourceOnlyOutputs'])
        self.assertEqual(source_only, set(provenance['sourceOnlyAssets']))
        self.assertLessEqual(source_only, keys)
        self.assertEqual(keys - source_only, set(load(ROOT / 'lesson.json')['images']))
        manifest = provenance['assets']
        for key in ART.BADGE_LAYOUTS:
            with self.subTest(key=key):
                with io.BytesIO() as stream:
                    ART.render_badge_art(key).save(stream, format='PNG', optimize=True)
                    data = stream.getvalue()
                self.assertEqual(sha256(data).hexdigest(), manifest[key]['sha256'])
                self.assertEqual(data, (ROOT / manifest[key]['path']).read_bytes())

    def test_six_turns_with_its_orientation_marker(self):
        upright = ART.render_badge_art('badge-six')
        upside_down = ART.render_badge_art('badge-six-inverted')
        self.assertEqual(upright.transpose(Image.Transpose.ROTATE_180).tobytes(), upside_down.tobytes())
        self.assertEqual(upright.getpixel((128, 207)), (174, 96, 51, 255))
        self.assertEqual(upside_down.getpixel((127, 48)), (174, 96, 51, 255))
