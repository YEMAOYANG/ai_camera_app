"""Guard this lesson's registered art and narrated demo-to-play contract."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom


LESSON = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((LESSON / name).read_text(encoding='utf-8'))


class LessonContractTest(unittest.TestCase):
    def test_art_and_quiz_contexts(self):
        lesson = load('lesson.json')
        assets = load('asset-provenance.json')['assets']
        self.assertEqual(set(lesson['images']), set(assets))
        for key, spec in lesson['images'].items():
            with self.subTest(key=key):
                image = (LESSON / spec['file']).read_bytes()
                self.assertEqual(hashlib.sha256(image).hexdigest(), assets[key]['sha256'])
                for source in assets[key].get('ingredients', []):
                    self.assertEqual(assets[source['key']]['sha256'], source['sha256'])

        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in quiz['questions']), {'a': 2, 'b': 2, 'c': 2})
        for question in quiz['questions']:
            for option in question['options'].values():
                self.assertTrue(option['visual']['image'].startswith('quiz-'))

    def test_built_game_handoff_and_static_teaching_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            draft = prepare(LESSON, directory, stage_id='dog-contract', now_ms=1)
            body = draft['body']
            self.assertEqual(body['scenes'][-1]['outlineId'], 'recap-the-exhibit')
            games = [scene for scene in body['scenes'] if scene['type'] == 'interactive']
            self.assertEqual(len(games), 2)
            for scene, mechanic in zip(games, ('parachute', 'bumper')):
                with self.subTest(scene=scene['outlineId']):
                    actions = scene['actions']
                    self.assertEqual(actions[0]['state'], {'demo': True, 'level': 1})
                    self.assertEqual(actions[-1]['state'], {'demo': False, 'level': 1})
                    self.assertEqual(sum(a['type'] == 'widget_highlight' for a in actions), 3)
                    self.assertIn(f'K.gameTemplates.{mechanic}(', scene['content']['html'])

            issues = check_classroom(
                body, Path(directory) / 'media', notes=load('official-notes.json'),
                roster=draft['roster'], grade=draft['grade'], teaching=True,
            )
            static_errors = [
                issue for issue in issues
                if issue['severity'] == 'error' and (
                    issue['gate'] in {'G0', 'G2', 'G3', 'G5'} or
                    (issue['gate'] == 'G4' and issue['code'] != 'quiz_questionAudioUrl_missing')
                )
            ]
            self.assertEqual(static_errors, [])
