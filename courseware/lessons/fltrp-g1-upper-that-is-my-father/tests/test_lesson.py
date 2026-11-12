from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from courseware.tools.build import prepare
from courseware.tools.check import check_classroom
from courseware.tools.game_audio import verify_recordings


LESSON = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((LESSON / name).read_text())


def digest(name):
    return sha256((LESSON / name).read_bytes()).hexdigest()


class FamilyIntroductionsTest(unittest.TestCase):
    def test_official_scope_and_registered_picture_choices(self):
        lesson = read('lesson.json')
        notes = read('official-notes.json')
        brief = read('brief.json')
        self.assertEqual(notes['officialTextbook']['printedPages'], [56, 57, 58])
        self.assertEqual(notes['officialTextbook']['assetPages'], [61, 62, 63])
        self.assertEqual(notes['objectives'], brief['goals'])
        self.assertEqual(digest('official-notes.json'), brief['officialNotesSha256'])
        self.assertEqual([item['key'] for item in brief['pageSequence']],
                         [item['key'] for item in lesson['scenes']])

        art = read('asset-provenance.json')['assets']
        self.assertEqual({name for entry in notes['factChecks'] for name in entry['images']}, set(art))
        self.assertEqual({name for name, entry in art.items() if entry['usedBy']}, set(lesson['images']))
        for name, entry in art.items():
            self.assertEqual(digest(entry['path']), entry['sha256'], name)
            if 'generatedSource' in entry:
                self.assertEqual(digest(entry['generatedSource']), entry['generatedSourceSha256'], name)
            else:
                self.assertEqual(digest(entry['renderSource']), entry['renderSourceSha256'], name)
                self.assertEqual(entry['inputs'], {key: art[key]['sha256'] for key in entry['inputs']})

        quiz = next(item for item in lesson['scenes'] if item['type'] == 'quiz')
        self.assertEqual(Counter(item['answer'][0] for item in quiz['questions']), {'a': 2, 'b': 2, 'c': 2})
        for item in quiz['questions']:
            options = {option['visual']['image'] for option in item['options'].values()}
            self.assertEqual(len(options), 3)
            self.assertTrue(options <= set(lesson['images']))
        self.assertEqual(quiz['questions'][4]['options']['c']['visual']['image'], 'quiz-route-correct')

    def test_regular_builder_accepts_every_prevoice_requirement(self):
        with TemporaryDirectory() as workspace:
            draft = prepare(LESSON, workspace, stage_id='family-introductions-test', now_ms=1)
            body = draft['body']
            issues = check_classroom(body, Path(workspace) / 'media', notes=read('official-notes.json'),
                                     roster=draft['roster'], grade=1, teaching=True, require_play=True)
            self.assertEqual({item['code'] for item in issues if item['severity'] == 'error'}, {
                'speech_audio_missing', 'quiz_questionAudioUrl_missing',
                'game_audio_invalid', 'play_receipt_missing',
            })
            self.assertNotIn('media_unreferenced', {item['code'] for item in issues})
            verify_recordings(body, before_voice=True)
