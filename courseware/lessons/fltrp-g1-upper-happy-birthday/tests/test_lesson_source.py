from collections import Counter
from hashlib import sha256
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest

from courseware.kit import page
from courseware.tools.check import check_classroom


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT.parents[1] / 'kit/game_templates/catalog.json'
SPEC = importlib.util.spec_from_file_location('birthday_age_badges', ROOT / 'age_badges.py')
ART = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ART)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


class BirthdayLessonSourceTests(unittest.TestCase):
    def test_exact_textbook_and_both_indexed_activities_are_reviewed(self):
        identity, notes, brief = [read(ROOT / f'{name}.json') for name in ('identity', 'official-notes', 'brief')]
        self.assertEqual(identity['nodeId'], 'e4a59458-107b-3fc3-b99b-9811315bf782')
        self.assertEqual(notes['binding']['legacyActivityIds'], identity['legacyActivityIds'])
        self.assertEqual(notes['textbookReview']['printedPages'], [53, 54, 55])
        self.assertEqual(notes['textbookReview']['activitiesReviewed'], list(range(1, 7)))
        self.assertEqual(notes['sourceCompleteness']['reviewedSupportingPageCount'], 75)
        self.assertFalse([issue for issue in check_classroom({'scenes': []}, notes=notes, grade=1)
                          if issue['gate'] == 'G0'])
        self.assertEqual(brief['authorModels'], ['gpt-6.1-sol'])
        self.assertEqual(brief['officialNotesSha256'], sha256((ROOT / 'official-notes.json').read_bytes()).hexdigest())

    def test_games_use_different_approved_templates_and_valid_cues(self):
        lesson = read(ROOT / 'lesson.json')
        catalog = {v['entryPoint']: v for item in read(CATALOG)['templates'] for v in item['versions']}
        games = [s for s in lesson['scenes'] if s['type'] == 'interactive']
        self.assertEqual(len(games), 2)
        speech = {f'{s["key"]}-{i}': (s['key'], b['say']) for s in lesson['scenes']
                  for i, b in enumerate(s.get('script', []), 1) if 'say' in b}
        entries = set()
        for scene in games:
            with self.subTest(page=scene['page']):
                path = ROOT / 'pages' / scene['page']
                markup, script = path.with_suffix('.html').read_text(), path.with_suffix('.js').read_text()
                entry = re.search(r'K\.game\((K\.gameTemplates\.\w+)\(', script)[1]
                entries.add(entry)
                self.assertEqual(catalog[entry]['status'], '可用')
                self.assertTrue(catalog[entry]['ownerApprovedOn'])
                self.assertIn('voiceLead:true,stepVoiceLead:true', script)
                self.assertEqual(scene['script'][0]['setState'], {'demo': True, 'level': 1, 'pause': True})
                self.assertEqual(scene['script'][-1]['setState'], {'demo': False, 'level': 1, 'pause': False})
                movement = next(i for i, b in enumerate(scene['script']) if b.get('setState') == {'pause': False})
                anchors = [b['highlight'][1:] for b in scene['script'][:movement] if 'highlight' in b]
                self.assertGreaterEqual(len(anchors), 2)
                self.assertTrue(set(anchors) <= page.defined_ids(markup))
                self.assertTrue(all(anchor.startswith('demo-') for anchor in anchors))
                self.assertTrue(set(re.findall(r'__IMG:([^_]+)__', script)) <= set(lesson['images']))
                self.assertTrue(all(speech[action][0] != scene['key'] for action in scene['gameAudio'].values()))
        self.assertEqual(entries, {'K.gameTemplates.wordBubbles', 'K.gameTemplates.bubbleMaze'})

    def test_picture_check_is_independent_and_numbers_reproduce(self):
        lesson = read(ROOT / 'lesson.json')
        plan = read(ROOT / 'art-plan.json')
        quiz = next(s for s in lesson['scenes'] if s['type'] == 'quiz')['questions']
        self.assertEqual(len(quiz), 6)
        self.assertEqual(Counter(q['answer'][0] for q in quiz), {'a': 2, 'b': 2, 'c': 2})
        self.assertTrue(all(len(q['answer']) == 1 and q['skill'] and q['analysis'] for q in quiz))
        self.assertEqual(quiz[-1]['options']['c']['visual']['image'], 'age-four')
        for question in quiz:
            self.assertEqual(len({option['visual']['image'] for option in question['options'].values()}), 3)
        keys = {key for record in plan['prompts'] for key in record['outputs']}
        keys.update(plan['localCandidateAndDerivedArt'])
        keys.update(plan['badgeDiagrams']['outputs'])
        self.assertEqual(keys, set(lesson['images']))
        provenance = read(ROOT / 'asset-provenance.json')['assets']
        for key, age in ART.AGES.items():
            with self.subTest(age=age):
                with io.BytesIO() as stream:
                    ART.badge(age).save(stream, format='PNG', optimize=True)
                    data = stream.getvalue()
                self.assertEqual(sha256(data).hexdigest(), provenance[key]['sha256'])
                self.assertEqual(data, (ROOT / provenance[key]['path']).read_bytes())
