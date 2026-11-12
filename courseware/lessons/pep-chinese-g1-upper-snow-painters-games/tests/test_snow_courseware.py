from collections import Counter
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom


LESSON = Path(__file__).resolve().parent.parent


class SnowCoursewareTests(unittest.TestCase):
    def test_compiled_two_hour_lesson_keeps_distinct_games_and_child_handoff(self):
        with TemporaryDirectory() as work:
            draft = prepare(LESSON, work, stage_id='snow-regression', now_ms=1)
            scenes = draft['body']['scenes']
            notes = json.loads((LESSON / 'official-notes.json').read_text())
            self.assertEqual(notes['binding']['classHours'], ['lesson_1', 'lesson_2'])
            self.assertEqual(notes['textbookRecheck']['printedPages'], [64, 65])
            self.assertEqual(scenes[-1]['title'], '带着四幅图回到书里')
            games = [scene for scene in scenes if scene['type'] == 'interactive']
            for game, mechanic in zip(games, ('bumper', 'ring', 'trace')):
                actions = game['actions']
                self.assertIn('K.game(K.gameTemplates.' + mechanic + '(', game['content']['html'])
                self.assertEqual(actions[0]['state'], {'demo': True, 'level': 1})
                self.assertIn({'demo': False, 'level': 1},
                              [action.get('state') for action in actions])
            self.assertEqual(len(games), 3)
            issues = check_classroom(draft['body'], Path(work) / 'media', notes=notes,
                                     roster=draft['roster'], grade=1, teaching=True)
            self.assertEqual(
                [issue for issue in issues if issue['gate'] not in {'G1', 'G6'}
                 and issue['code'] != 'quiz_questionAudioUrl_missing'], []
            )

    def test_asset_provenance_and_new_quiz_contexts(self):
        data = json.loads((LESSON / 'lesson.json').read_text())
        provenance = json.loads((LESSON / 'asset-sources.json').read_text())['assets']
        self.assertEqual(set(data['images']), {row['key'] for row in provenance})
        for asset in provenance:
            if 'file' not in asset:
                self.assertEqual(data['images'][asset['key']]['glyph'], asset['spec'])
                continue
            self.assertEqual(hashlib.sha256((LESSON / asset['file']).read_bytes()).hexdigest(),
                             asset['sha256'])
        self.assertNotIn('mud-horse', data['images'])  # The prior art shows a split hoof.
        questions = next(scene['questions'] for scene in data['scenes'] if scene['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in questions), {'A': 1, 'B': 1, 'C': 2})
        mud_stems = {q['visual']['image'] for q in questions if 'visual' in q}
        self.assertEqual(mud_stems, {'mud-chick', 'mud-duck'})
        for page in (LESSON / 'pages').glob('*.js'):
            self.assertFalse(any('__IMG:' + key + '__' in page.read_text() for key in mud_stems))
