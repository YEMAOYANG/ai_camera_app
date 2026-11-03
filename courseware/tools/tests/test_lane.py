import base64
import io
import json
import shutil
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from courseware.tools import lane
from courseware.tools.check import body_hash


FIXTURE = Path(__file__).parent / 'fixtures' / 'build_lesson'


def wav(seed):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(bytes([seed % 250]) * 8000)
    return buffer.getvalue()


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (640, 360), color).save(buffer, format='PNG')
    return buffer.getvalue()


class FakeService:
    def __init__(self):
        self.calls = []

    def post(self, url, payload):
        self.calls.append(url.rsplit('/api/', 1)[1])
        if url.endswith('/tts'):
            return 200, json.dumps({'data': {'base64': base64.b64encode(wav(len(payload['text']))).decode()}}).encode()
        return 200, json.dumps({'success': True, 'result': {'url': 'https://example.test/a.png', 'width': 640, 'height': 360}}).encode()

    def fetch(self, url):
        return 200, png('orange')


def fake_audit(body, media_dir):
    return {'schemaVersion': 'mira.courseware.audit-receipt.v1', 'bodySha256': body_hash(body), 'ok': True,
            'viewports': ['1280x720', '1000x563', '640x360'], 'pages': [{'scene': 2, 'viewport': '1280x720', 'ok': True}]}


def fake_play(body, media_dir):
    return {'schemaVersion': 'mira.courseware.autoplay-receipt.v1', 'bodySha256': body_hash(body), 'ok': True,
            'pages': [{'scene': 2, 'finished': True, 'stepsToFinish': 9, 'finishedAgain': True, 'errors': [], 'stuck': None, 'ok': True}]}


class LaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lesson = Path(self.tmp.name) / 'lesson'
        shutil.copytree(FIXTURE, self.lesson)
        self.work = Path(self.tmp.name) / 'work'
        self.service = FakeService()
        self.play = fake_play

    def run_lane(self, **kw):
        return lane.run_lesson(self.lesson, self.work, stage_id='stage-lane', post=self.service.post, fetch=self.service.fetch,
                               run_audit=fake_audit, run_play=lambda body, media: self.play(body, media), now_ms=1793700000000, sleep=lambda s: None,
                               **{'teaching': False, **kw})

    def test_full_run_writes_the_package_and_reports_gate_issues(self):
        result = self.run_lane()
        for name in ('body.json', 'draft.json', 'roster.json', 'check.json', 'audit-receipt.json'):
            self.assertTrue((self.work / name).is_file(), name)
        self.assertEqual(result['steps']['build']['scenes'], 3)
        self.assertEqual(result['steps']['build']['voiced'], result['steps']['build']['lines'])
        self.assertTrue(result['steps']['audit']['ok'])
        codes = {issue['code'] for issue in result['issues']}
        self.assertEqual(codes, {'notes_missing'})
        self.assertEqual(result['steps']['check']['errors'], 1)

    def test_traditional_characters_in_the_brief_are_a_gate_error(self):
        (self.lesson / 'brief.json').write_text(json.dumps({'play': '看、听、闻、嘗、摸'}, ensure_ascii=False), encoding='utf-8')
        result = self.run_lane()
        found = [issue for issue in result['issues'] if issue['code'] == 'traditional_chinese']
        self.assertEqual([(issue['gate'], issue['severity']) for issue in found], [('G0', 'error')])
        self.assertIn('嘗', found[0]['detail'])

    def test_random_play_failures_are_gate_issues_and_the_receipt_is_kept(self):
        def stuck(body, media_dir):
            receipt = fake_play(body, media_dir)
            receipt['pages'][0].update(ok=False, finished=False, stuck='never finished in 400 steps')
            receipt['ok'] = False
            return receipt
        self.play = stuck
        result = self.run_lane()
        self.assertEqual(result['steps']['play'], {'ok': False, 'pages': 1, 'failed': 1})
        self.assertIn(('play_unfinished', 2), {(i['code'], i['scene']) for i in result['issues']})
        self.assertTrue((self.work / 'play-receipt.json').is_file())
        self.play = fake_play
        again = self.run_lane(steps=['check'])
        self.assertIn('play_unfinished', {i['code'] for i in again['issues']})

    def test_a_lesson_is_checked_for_enough_spoken_explanation_unless_told_otherwise(self):
        result = self.run_lane(teaching=True)
        thin = [i for i in result['issues'] if i['code'] == 'narration_thin']
        self.assertEqual({(i['gate'], i['severity']) for i in thin}, {('G3', 'error')})
        self.assertTrue(thin)

    def test_second_run_reuses_voices_and_pictures(self):
        (self.lesson / 'pictures.json').write_text(json.dumps([{'key': 'cover', 'prompt': 'a pond'}]))
        first = self.run_lane()
        self.assertEqual(first['steps']['pictures'], {'made': 1, 'reused': 0})
        calls = len(self.service.calls)
        second = self.run_lane()
        self.assertEqual(second['steps']['pictures'], {'made': 0, 'reused': 1})
        self.assertEqual(second['steps']['build']['voiced'], 0)
        self.assertEqual(len(self.service.calls), calls)
        self.assertTrue((self.lesson / 'assets' / 'cover.png').is_file())

    def test_steps_can_be_rerun_alone_from_the_work_folder(self):
        self.run_lane()
        (self.work / 'check.json').unlink()
        result = self.run_lane(steps=['check'])
        self.assertEqual(set(result['steps']), {'check'})
        self.assertTrue((self.work / 'check.json').is_file())
        self.assertNotIn('receipt_missing', {issue['code'] for issue in result['issues']})

    def test_missing_receipt_and_bad_step_names(self):
        result = self.run_lane(steps=['pictures', 'build', 'check'])
        self.assertIn('receipt_missing', {issue['code'] for issue in result['issues']})
        with self.assertRaises(lane.LaneError) as caught:
            self.run_lane(steps=['sing'])
        self.assertEqual(caught.exception.args[0], 'steps_invalid')

    def test_main_exit_code_follows_the_errors(self):
        with patch.object(lane, 'run_lesson', return_value={'steps': {'check': {'errors': 0}}, 'issues': []}), redirect_stdout(io.StringIO()):
            self.assertEqual(lane.main(['--lesson', 'a', '--work', 'b', '--stage-id', 'c']), 0)
        issue = dict(gate='G0', code='notes_missing', scene=None, detail='x', severity='error')
        with patch.object(lane, 'run_lesson', return_value={'steps': {}, 'issues': [issue]}), redirect_stdout(io.StringIO()):
            self.assertEqual(lane.main(['--lesson', 'a', '--work', 'b', '--stage-id', 'c']), 1)
        with patch.object(lane, 'run_lesson', side_effect=lane.LaneError('source_invalid', 'x')), redirect_stderr(io.StringIO()):
            self.assertEqual(lane.main(['--lesson', 'a', '--work', 'b', '--stage-id', 'c']), 1)


if __name__ == '__main__':
    unittest.main()
