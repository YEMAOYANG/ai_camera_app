import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

from courseware.tools import autoplay, build, check


FIXTURE = Path(__file__).parent / 'fixtures' / 'build_lesson'
PAGE = """
<section data-guided-media-activity data-phase="locked">
  <img src="__IMG:picture__" alt="示例图">
  <button id="go" data-media-trigger disabled>开始</button>
  <audio data-guided-media src="__AUDIO:recording__"></audio>
</section>
"""
SCRIPT = """
const root = document.querySelector('[data-guided-media-activity]');
const button = root.querySelector('button');
const recording = root.querySelector('audio');
K.onState = state => {
  if (!state.activityReady) return;
  root.dataset.phase = 'ready';
  button.disabled = false;
};
button.onclick = async () => {
  await recording.play();
  root.dataset.phase = 'playing';
};
recording.onended = () => { root.dataset.phase = 'done'; };
"""


class GuidedMediaActivityTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        self.source = root / 'lesson'
        self.output = root / 'build'
        shutil.copytree(FIXTURE, self.source)
        wav_path = self.source / 'assets' / 'recording.wav'
        with wave.open(str(wav_path), 'wb') as wav:
            wav.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\x00\x00' * 2400)
        self.sha = hashlib.sha256(wav_path.read_bytes()).hexdigest()
        self.lesson_path = self.source / 'lesson.json'
        self.lesson = json.loads(self.lesson_path.read_text(encoding='utf-8'))
        for scene in self.lesson['scenes']:
            scene.pop('startImage', None)
        self.lesson['audio'] = {'recording': {'file': 'assets/recording.wav', 'sha256': self.sha}}
        self.lesson_path.write_text(json.dumps(self.lesson, ensure_ascii=False), encoding='utf-8')
        self.page_source = self.source / 'pages' / 'play.html'
        self.page_source.write_text(PAGE, encoding='utf-8')
        self.script_path = self.source / 'pages' / 'play.js'
        self.script_path.write_text(SCRIPT, encoding='utf-8')

    def test_exact_recording_becomes_an_archivable_media_reference(self):
        draft = build.prepare(self.source, self.output, stage_id='guided')
        name = f'recording-{self.sha}.wav'
        html = next(s['content']['html'] for s in draft['body']['scenes'] if s['type'] == 'interactive')
        self.assertIn(f'/api/classroom-media/guided/media/{name}', html)
        self.assertNotIn('__AUDIO:', html)
        self.assertEqual(hashlib.sha256((self.output / 'media' / name).read_bytes()).hexdigest(), self.sha)

    def test_changed_or_unused_recording_fails_build(self):
        self.lesson['audio']['recording']['sha256'] = '0' * 64
        self.lesson_path.write_text(json.dumps(self.lesson), encoding='utf-8')
        with self.assertRaisesRegex(build.BuildError, 'source SHA-256 mismatch'):
            build.prepare(self.source, self.output, stage_id='guided')
        self.lesson['audio']['recording']['sha256'] = self.sha
        self.lesson_path.write_text(json.dumps(self.lesson), encoding='utf-8')
        self.page_source.write_text(PAGE.replace('__AUDIO:recording__', ''), encoding='utf-8')
        with self.assertRaisesRegex(build.BuildError, 'audio_asset_unreferenced'):
            build.prepare(self.source, self.output, stage_id='guided')

    def test_generic_random_play_receipt_cannot_approve_guided_media(self):
        draft = build.prepare(self.source, self.output, stage_id='guided')
        body = draft['body']
        index = next(i for i, s in enumerate(body['scenes'], 1) if s['type'] == 'interactive')
        receipt = {
            'schemaVersion': 'mira.courseware.autoplay-receipt.v1', 'ok': True, 'bodySha256': check.body_hash(body),
            'pages': [{'scene': index, 'finished': True, 'finishedAgain': True, 'method': 'random', 'errors': []}],
        }
        issues = check.check_classroom(body, play_receipt=receipt)
        self.assertIn('guided_media_playback_unverified', {issue['code'] for issue in issues})

    def test_autoplay_requires_actual_media_end_on_both_plays(self):
        chrome = Path(os.environ.get('MIRA_CHROME_BIN', autoplay.CHROME))
        try:
            autoplay._playwright_dir()
        except RuntimeError as exc:
            self.skipTest(str(exc))
        if not chrome.is_file() or not shutil.which('node'):
            self.skipTest('Chrome and Node are required')
        draft = build.prepare(self.source, self.output, stage_id='guided')
        receipt = autoplay.play_body(draft['body'], self.output / 'media')
        self.assertTrue(receipt['ok'], receipt)
        self.assertEqual(receipt['pages'][0]['method'], 'guided-media')
        self.assertTrue(receipt['pages'][0]['finishedAgain'])
        self.script_path.write_text(SCRIPT.replace('await recording.play();', '')
                                     .replace("root.dataset.phase = 'playing';", "root.dataset.phase = 'done';"),
                                     encoding='utf-8')
        fake = build.prepare(self.source, self.output, stage_id='guided')
        rejected = autoplay.play_body(fake['body'], self.output / 'media')
        self.assertFalse(rejected['ok'])
        self.assertIn('complete, unaltered media playback', rejected['pages'][0]['stuck'])
