import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from courseware.tools import build, check


FIXTURE = Path(__file__).parent / 'fixtures' / 'build_lesson'


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lesson = self.root / 'lesson'
        shutil.copytree(FIXTURE, self.lesson)
        self.out = self.root / 'out'

    def prepare(self):
        return build.prepare(self.lesson, self.out, stage_id='stage-test', now_ms=123)

    def change(self, edit):
        path = self.lesson / 'lesson.json'
        lesson = json.loads(path.read_text(encoding='utf-8'))
        edit(lesson)
        path.write_text(json.dumps(lesson), encoding='utf-8')

    def clips(self, draft):
        files = {}
        for line in draft['lines']:
            data = line['id'].encode()
            name = 'tts-' + line['id'] + '-' + hashlib.sha256(data).hexdigest() + '.wav'
            (self.out / 'media' / name).write_bytes(data)
            files[line['id']] = name
        return files

    def test_prepare_finish_and_determinism(self):
        draft = self.prepare()
        scenes = draft['body']['scenes']
        self.assertEqual([s['type'] for s in scenes], ['slide', 'interactive', 'quiz'])
        self.assertEqual([s['order'] for s in scenes], [1, 2, 3])
        self.assertEqual([s['id'] for s in scenes], ['scene-intro', 'scene-play', 'scene-quiz'])
        self.assertEqual(draft['body']['stage']['agentIds'], ['gen-teacher', 'gen-student'])
        self.assertEqual([line['id'] for line in draft['lines']], ['intro-1', 'play-1', 'play-3', 'play-5', 'quiz_speech_1', 'quiz_speech_2', 'quiz_speech_3'])
        self.assertTrue(all(line['voice'] == 'Ethan' for line in draft['lines']))
        digest = hashlib.sha256((self.lesson / 'assets/picture.png').read_bytes()).hexdigest()
        url = '/api/classroom-media/stage-test/media/pic-' + digest + '.png'
        self.assertTrue((self.out / 'media' / ('pic-' + digest + '.png')).is_file())
        html = scenes[1]['content']['html']
        self.assertIn("K.ready({img:'" + url + "',", html)
        self.assertIn(url, html)
        self.assertNotIn('__IMG:', html)
        files = self.clips(draft)
        (self.out / 'media' / 'pic-unused.png').write_bytes(b'unused')
        (self.out / 'media' / 'keep.txt').write_text('keep')
        body = build.finish(draft, self.out, files)
        self.assertFalse((self.out / 'media' / 'pic-unused.png').exists())
        self.assertTrue((self.out / 'media' / 'keep.txt').exists())
        self.assertEqual([i for i in check.check_classroom(body, self.out / 'media', roster=draft['roster'], grade=1) if i['severity'] == 'error'], [])
        first = (self.out / 'body.json').read_bytes()
        build.finish(self.prepare(), self.out, files)
        self.assertEqual(first, (self.out / 'body.json').read_bytes())

    def test_error_codes(self):
        cases = [
            ('lesson_invalid', lambda x: x.update(grade=0)),
            ('roster_invalid', lambda x: x['roster']['teacher'].update(voice='Cherry')),
            ('image_missing', lambda x: x['images']['picture'].update(file='assets/missing.png')),
            ('page_missing', lambda x: x['scenes'][1].update(page='missing')),
            ('template_failed', lambda x: x['scenes'][0].update(template='missing')),
            ('target_missing', lambda x: x['scenes'][0]['script'].append({'laser':'missing'})),
            ('quiz_invalid', lambda x: x['scenes'][2]['questions'][0].update(skill='')),
        ]
        original = (self.lesson / 'lesson.json').read_text()
        for code, edit in cases:
            with self.subTest(code=code):
                (self.lesson / 'lesson.json').write_text(original)
                self.change(edit)
                with self.assertRaises(build.BuildError) as caught:
                    self.prepare()
                self.assertEqual(caught.exception.args[0], code)
        (self.lesson / 'lesson.json').write_text(original)
        (self.lesson / 'pages/play.js').write_text('var step = 1;')
        with self.assertRaises(build.BuildError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.args[0], 'start_overlay_missing')
        (self.lesson / 'pages/play.js').write_text((FIXTURE / 'pages/play.js').read_text())
        draft = self.prepare()
        with self.assertRaises(build.BuildError) as caught:
            build.finish(draft, self.out, {})
        self.assertEqual(caught.exception.args[0], 'audio_missing')

    def test_quiz_script_order_and_invalid_beats(self):
        self.change(lambda lesson: lesson['scenes'][2].update(script=[{'say': '先看一看'}, {'discuss': {'by': 'student', 'topic': '数量', 'prompt': '说一说'}}]))
        draft = self.prepare()
        actions = draft['body']['scenes'][2]['actions']
        self.assertEqual([a['id'] for a in actions[:3]], ['quiz-1', 'quiz-2', 'quiz_speech_1'])
        self.assertIn('quiz-1', [line['id'] for line in draft['lines']])
        self.change(lambda lesson: lesson['scenes'][2].update(script=[{'say': '看', 'laser': 'x'}]))
        with self.assertRaises(build.BuildError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.args[0], 'lesson_invalid')
        self.change(lambda lesson: lesson['scenes'][2].update(script=[{'discuss': {'by': 'teacher', 'topic': '数量', 'prompt': '说'}}]))
        with self.assertRaises(build.BuildError) as caught:
            self.prepare()
        self.assertEqual(caught.exception.args[0], 'roster_invalid')

    def test_cli_round_trip(self):
        self.assertEqual(build.main(['prepare', '--lesson', str(self.lesson), '--out', str(self.out), '--stage-id', 'stage-test', '--now-ms', '123']), 0)
        draft = json.loads((self.out / 'draft.json').read_text())
        audio = self.root / 'audio.json'
        audio.write_text(json.dumps({'files': self.clips(draft)}))
        self.assertEqual(build.main(['finish', '--out', str(self.out), '--audio', str(audio)]), 0)
        self.assertTrue((self.out / 'body.json').is_file())

    def test_build_lesson_injects_voice(self):
        def voice(lines):
            return {'files': self.clips({'lines': lines})}
        body = build.build_lesson(self.lesson, self.out, stage_id='stage-test', voice=voice, now_ms=123)
        self.assertTrue(body['scenes'][0]['actions'][0]['audioUrl'])


if __name__ == '__main__':
    unittest.main()
