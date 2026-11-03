import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from courseware.tools import preview


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.build, self.classrooms = root / 'build', root / 'classrooms'
        (self.build / 'media').mkdir(parents=True)
        self.audio = b'wav bytes'
        self.audio_name = 'tts-a-' + hashlib.sha256(self.audio).hexdigest() + '.wav'
        (self.build / 'media' / self.audio_name).write_bytes(self.audio)
        self.picture_name = 'pic-' + hashlib.sha256(b'png').hexdigest() + '.png'
        (self.build / 'media' / self.picture_name).write_bytes(b'png')
        body = {'stage': {'id': 'stage-x', 'name': '本课'}, 'scenes': [{'id': 's', 'actions': [
            {'audioUrl': f'/api/classroom-media/stage-x/media/{self.audio_name}'}],
            'content': {'src': f'/api/classroom-media/stage-x/media/{self.picture_name}'}}]}
        (self.build / 'body.json').write_text(json.dumps(body, ensure_ascii=False))
        self.saved = []

    def post(self, url, payload):
        self.saved.append((url, payload))
        return 200, b'{"success":true}'

    def run_preview(self, **kw):
        return preview.stage_preview(self.build, self.classrooms, post=kw.pop('post', self.post), **kw)

    def test_media_are_copied_and_the_classroom_is_saved_without_the_extra_body_fields(self):
        result = self.run_preview()
        self.assertEqual(result, {'stage': 'stage-x', 'media': 2, 'url': 'http://localhost:3100/classroom/stage-x'})
        self.assertEqual((self.classrooms / 'stage-x' / 'media' / self.audio_name).read_bytes(), self.audio)
        url, payload = self.saved[0]
        self.assertEqual(url, 'http://127.0.0.1:3100/api/classroom')
        self.assertEqual(set(payload), {'stage', 'scenes'})
        self.run_preview()  # staging again is harmless
        self.assertEqual(len(self.saved), 2)

    def test_a_damaged_or_missing_media_file_stops_before_anything_is_copied(self):
        (self.build / 'media' / self.audio_name).write_bytes(b'tampered')
        with self.assertRaises(preview.PreviewError) as caught:
            self.run_preview()
        self.assertEqual(caught.exception.args[0], 'media_hash_mismatch')
        self.assertFalse(self.classrooms.exists())
        (self.build / 'media' / self.audio_name).unlink()
        with self.assertRaises(preview.PreviewError) as caught:
            self.run_preview()
        self.assertEqual(caught.exception.args[0], 'media_missing')

    def test_a_different_staged_file_is_never_overwritten(self):
        target = self.classrooms / 'stage-x' / 'media'
        target.mkdir(parents=True)
        (target / self.picture_name).write_bytes(b'other')
        with self.assertRaises(preview.PreviewError) as caught:
            self.run_preview()
        self.assertEqual(caught.exception.args[0], 'media_conflict')
        self.assertEqual((target / self.picture_name).read_bytes(), b'other')

    def test_a_refused_save_and_a_bad_stage_id_are_errors(self):
        with self.assertRaises(preview.PreviewError) as caught:
            self.run_preview(post=lambda url, payload: (409, b'exists'))
        self.assertEqual(caught.exception.args[0], 'save_failed')
        body = json.loads((self.build / 'body.json').read_text())
        body['stage']['id'] = '../x'
        (self.build / 'body.json').write_text(json.dumps(body))
        with self.assertRaises(preview.PreviewError) as caught:
            self.run_preview()
        self.assertEqual(caught.exception.args[0], 'stage_id_invalid')

    def test_cli_exit_codes(self):
        errors = StringIO()
        argv = ['--build', str(self.build / 'missing'), '--classrooms', str(self.classrooms)]
        with redirect_stderr(errors), redirect_stdout(StringIO()):
            self.assertEqual(preview.main(argv), 1)
        self.assertIn('body_unreadable', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
