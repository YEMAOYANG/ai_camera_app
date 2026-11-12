from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from backend.content.textbook_interactive_narration import interactive_cues
from courseware.tools import build, check, preview, verify


class GameAudioTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.lesson = root / 'lesson'
        self.out = root / 'out'
        shutil.copytree(Path(__file__).parent / 'fixtures' / 'build_lesson', self.lesson)
        page = self.lesson / 'pages' / 'play.js'
        page.write_text(page.read_text() + '\nK.game({});\n')
        self.spec = json.loads((self.lesson / 'lesson.json').read_text())
        self.spec['scenes'][1]['gameAudio'] = {'listen': 'intro-1'}

    def prepare(self):
        (self.lesson / 'lesson.json').write_text(json.dumps(self.spec))
        return build.prepare(self.lesson, self.out, stage_id='stage-test', now_ms=123)

    def finish(self, draft):
        clips = {}
        for line in draft['lines']:
            raw = line['id'].encode()
            name = f"tts-{line['id']}-{hashlib.sha256(raw).hexdigest()}.wav"
            (self.out / 'media' / name).write_bytes(raw)
            clips[line['id']] = name
        return build.finish(draft, self.out, clips)

    def test_game_reuses_an_existing_line_and_preserves_prevoice_review(self):
        self.spec['scenes'][0]['script'][0]['say'] = 'Look <here>!'
        draft = self.prepare()
        source = draft['body']['scenes'][1]['content']['html']
        self.assertIn(r'Look \u003chere>!', source)
        self.assertEqual(interactive_cues(source), [{'id': 'listen', 'text': 'Look <here>!'}])
        self.assertEqual(len(draft['lines']), 7)
        before = verify.evidence_input_hash(draft['body'], [])
        final = self.finish(draft)
        action = final['scenes'][0]['actions'][0]
        html = final['scenes'][1]['content']['html']
        self.assertIn(f'const clips={{"listen":"{action["audioUrl"]}"}};let active=null;', html)
        self.assertEqual(verify.evidence_input_hash(final, []), before)
        self.assertFalse(any(i['code'] == 'game_audio_invalid' for i in check.check_classroom(final)))

    def test_wrong_recording_or_unbound_finished_body_is_rejected(self):
        draft = self.prepare()
        final = self.finish(draft)
        for wrong in ('/api/classroom-media/another/media/tts.wav',
                      final['scenes'][1]['actions'][0]['audioUrl'], None):
            with self.subTest(wrong=wrong):
                changed = deepcopy(final)
                html = changed['scenes'][1]['content']['html']
                correct = final['scenes'][0]['actions'][0]['audioUrl']
                changed['scenes'][1]['content']['html'] = (
                    html.replace(correct, wrong) if wrong else draft['body']['scenes'][1]['content']['html'])
                self.assertTrue(any(i['code'] == 'game_audio_invalid' for i in check.check_classroom(changed)))
                with self.assertRaises(ValueError):
                    verify.evidence_input_hash(changed, [])

    def test_private_preview_retargets_both_uses_of_the_same_recording(self):
        self.finish(self.prepare())
        classrooms = self.out.parent / 'classrooms'
        saved = []

        def save(_url, payload):
            saved.append(payload)
            return 200, b'{}'

        preview.stage_preview(self.out, classrooms, stage_id='private-preview', post=save)
        teacher, game, _ = saved[0]['scenes']
        clip = teacher['actions'][0]['audioUrl']
        self.assertTrue(clip.startswith('/api/classroom-media/private-preview/media/'))
        self.assertIn(f'const clips={{"listen":"{clip}"}};let active=null;', game['content']['html'])
        self.assertEqual((classrooms / 'private-preview' / 'media' / clip.rsplit('/', 1)[1]).read_bytes(),
                         b'intro-1')

    def test_author_cannot_reference_missing_same_scene_or_duplicate_speech(self):
        for action in ('absent-1', 'play-1', 'intro-2', 'quiz_speech_1'):
            with self.subTest(action=action):
                self.spec['scenes'][1]['gameAudio']['listen'] = action
                with self.assertRaisesRegex(build.BuildError, 'game_audio_invalid'):
                    self.prepare()
        self.spec['scenes'][1]['gameAudio']['listen'] = 'intro-1'
        self.spec['scenes'][1]['script'][0]['say'] = self.spec['scenes'][0]['script'][0]['say']
        with self.assertRaisesRegex(build.BuildError, 'game_audio_invalid'):
            self.prepare()
