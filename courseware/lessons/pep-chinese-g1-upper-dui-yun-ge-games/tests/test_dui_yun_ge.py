from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom
from courseware.tools.game_audio import verify_recordings


LESSON = Path(__file__).resolve().parent.parent


class DuiYunGeTests(unittest.TestCase):
    def test_correct_edition_and_taught_content(self):
        notes = json.loads((LESSON / 'official-notes.json').read_text())
        self.assertEqual(notes['binding'], {
            'editionId': 'pep-chinese-g1-upper-2022-standard',
            'revisionId': '20260924-directory-3',
            'nodeId': 'u6-l1',
        })
        self.assertEqual(notes['resources']['textbook']['printedPages'], [73])
        self.assertEqual([h['id'] for h in notes['officialHours']['hours']], ['lesson_1', 'lesson_2'])
        self.assertEqual(''.join(c[0] for c in notes['characters']['read']), '对歌雨风虫清绿桃红')
        self.assertEqual(''.join(notes['characters']['write']), '云雨虫山水')
        with TemporaryDirectory() as work:
            draft = prepare(LESSON, work, stage_id='dui-yun-regression', now_ms=1)
            body = draft['body']
            games = [s for s in body['scenes'] if s['type'] == 'interactive']
            self.assertEqual(len(games), 2)
            for game, mechanic in zip(games, ('fallingTiles', 'sortingDepot')):
                html = game['content']['html']
                self.assertIn('K.game(K.gameTemplates.' + mechanic + '(', html)
                states = [action['state'] for action in game['actions'] if action['type'] == 'widget_setState']
                self.assertEqual(states, [
                    {'demo': True, 'level': 1, 'pause': True},
                    {'pause': False},
                    {'demo': False, 'level': 1, 'pause': False},
                ])
            verify_recordings(body, before_voice=True)
            issues = check_classroom(body, Path(work) / 'media', notes=notes,
                                     roster=draft['roster'], grade=1, teaching=True)
            self.assertEqual([i for i in issues if i['gate'] not in ('G1', 'G6')
                              and i['code'] not in ('quiz_questionAudioUrl_missing', 'game_audio_invalid')], [])

    def test_textbook_excerpt_is_four_attributed_consecutive_speech_actions(self):
        notes = json.loads((LESSON / 'official-notes.json').read_text())
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        reading = next(scene for scene in lesson['scenes'] if scene['key'] == 'p07')
        excerpt = notes['verifiedText']['lines']
        script = reading['script']
        start = script.index({'say': excerpt[0]})
        self.assertEqual(script[start:start + 4], [{'say': line} for line in excerpt])
        self.assertIn('第73页', reading['data']['points'][0])
        all_speech = [action.get('say') for scene in lesson['scenes'] for action in scene.get('script', [])]
        self.assertTrue(all(all_speech.count(line) == 1 for line in excerpt))

    def test_reused_picture_hashes_and_new_quiz_art(self):
        lesson = json.loads((LESSON / 'lesson.json').read_text())
        source = json.loads((LESSON / 'asset-sources.json').read_text())
        self.assertEqual(set(lesson['images']), {item['key'] for item in source['assets']})
        self.assertEqual({item['key'] for item in source['legacyUnknownImages']}, {'q-peach', 'q-singer'})
        self.assertTrue({item['key'] for item in source['legacyUnknownImages']}.isdisjoint(lesson['images']))
        for item in source['assets']:
            if 'file' in item:
                self.assertEqual(sha256((LESSON / item['file']).read_bytes()).hexdigest(), item['sha256'])
        quiz = next(scene for scene in lesson['scenes'] if scene['type'] == 'quiz')
        self.assertEqual(Counter(q['answer'][0] for q in quiz['questions']), {'A': 1, 'B': 2, 'C': 1})
        q_pictures = {key for key in lesson['images'] if key.startswith('q-')}
        for page in (LESSON / 'pages').glob('*.js'):
            self.assertFalse(any('__IMG:' + key + '__' in page.read_text() for key in q_pictures))
