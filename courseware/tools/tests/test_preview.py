import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from courseware.tools import preview
from courseware.tools.check import body_hash


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
        self.run_preview(post=lambda url, payload: (201, b'{"success":true}'))  # the runtime answers 201 Created
        self.assertEqual(len(self.saved), 1)

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

    def test_an_existing_build_can_be_staged_under_a_new_immutable_id(self):
        body = json.loads((self.build / 'body.json').read_text())
        body['scenes'][0]['stageId'] = 'stage-x'
        (self.build / 'body.json').write_text(json.dumps(body, ensure_ascii=False))
        result = self.run_preview(stage_id='stage-new')
        self.assertEqual(result['stage'], 'stage-new')
        self.assertTrue((self.classrooms / 'stage-new' / 'media' / self.picture_name).is_file())
        payload = self.saved[0][1]
        self.assertEqual(payload['stage']['id'], 'stage-new')
        self.assertEqual(payload['scenes'][0]['stageId'], 'stage-new')
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertIn('/api/classroom-media/stage-new/media/', encoded)
        self.assertNotIn('stage-x', encoded)

    def test_private_binding_pins_the_original_body_and_exact_retargeted_post(self):
        binding_path = self.build.parent / 'preview-binding.json'
        raw = (self.build / 'body.json').read_bytes()
        result = self.run_preview(stage_id='stage-bound', binding_out=binding_path)
        binding = json.loads(binding_path.read_bytes())
        self.assertEqual(binding_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(binding, {
            'schemaVersion': 'mira.courseware.preview-binding.v1', 'classroomId': result['stage'],
            'bodyFileSha256': hashlib.sha256(raw).hexdigest(), 'bodySha256': body_hash(json.loads(raw)),
            'projection': self.saved[0][1],
        })
        self.assertEqual(binding['projection']['stage']['id'], 'stage-bound')
        self.assertIn('/api/classroom-media/stage-bound/', binding['projection']['scenes'][0]['actions'][0]['audioUrl'])

    def test_binding_is_not_written_after_failed_post_or_overwritten(self):
        binding_path = self.build.parent / 'preview-binding.json'
        with self.assertRaisesRegex(preview.PreviewError, 'save_failed'):
            self.run_preview(stage_id='stage-refused', binding_out=binding_path, post=lambda *_: (409, b'exists'))
        self.assertFalse(binding_path.exists())
        binding_path.write_text('original')
        with self.assertRaisesRegex(preview.PreviewError, 'binding_output_invalid'):
            self.run_preview(stage_id='stage-other', binding_out=binding_path)
        self.assertEqual(binding_path.read_text(), 'original')
        self.assertEqual(self.saved, [])

    def test_binding_output_race_never_overwrites_the_other_file(self):
        binding_path = self.build.parent / 'preview-binding.json'

        def post(*_):
            binding_path.write_text('created during staging')
            return 201, b'{"success":true}'

        with self.assertRaisesRegex(preview.PreviewError, 'binding_output_failed'):
            self.run_preview(stage_id='stage-race', binding_out=binding_path, post=post)
        self.assertEqual(binding_path.read_text(), 'created during staging')

    def test_verified_preview_rejects_source_and_reserved_aliases_before_staging(self):
        binding_path = self.build.parent / 'preview-binding.json'
        for alias in (None, 'stage-x', 'tbpub_release', 'tbprev_frozen', 'omclass_existing'):
            with self.subTest(alias=alias), self.assertRaisesRegex(preview.PreviewError, 'binding_alias_invalid'):
                self.run_preview(stage_id=alias, binding_out=binding_path)
        self.assertFalse(self.classrooms.exists())
        self.assertFalse(binding_path.exists())
        self.assertEqual(self.saved, [])

    def test_verified_preview_rejects_both_local_storage_spellings_before_staging(self):
        binding_path = self.build.parent / 'preview-binding.json'
        nested = self.classrooms / 'stage-nested' / 'classroom.json'
        nested.parent.mkdir(parents=True)
        flat = self.classrooms / 'stage-flat.json'
        for existing in (flat, nested):
            existing.write_text('retained original')
        for alias in ('stage-flat', 'stage-nested'):
            with self.subTest(alias=alias), self.assertRaisesRegex(preview.PreviewError, 'binding_alias_conflict'):
                self.run_preview(stage_id=alias, binding_out=binding_path)
        self.assertFalse(binding_path.exists())
        self.assertEqual(self.saved, [])
        self.assertEqual(list(self.classrooms.glob('*/media')), [])
        self.assertEqual([file.read_text() for file in (flat, nested)], ['retained original'] * 2)

    def test_verified_preview_rejects_invalid_binding_parent_before_staging(self):
        non_directory = self.build.parent / 'not-directory'
        non_directory.write_text('retained original')
        for parent in (self.build.parent / 'not-created', non_directory):
            with self.subTest(parent=parent), self.assertRaisesRegex(preview.PreviewError, 'binding_output_invalid'):
                self.run_preview(stage_id='stage-fresh', binding_out=parent / 'binding.json')
        self.assertFalse(self.classrooms.exists())
        self.assertEqual(self.saved, [])

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

    def test_binding_only_cli_writes_exact_private_bytes_without_touching_runtime(self):
        path = self.build.parent / 'binding-only.json'
        output = StringIO()
        args = ['--binding-only', '--build', str(self.build), '--stage-id', 'stage-bound',
                '--binding-out', str(path)]
        with (patch.object(preview.urllib.request, 'urlopen', side_effect=AssertionError('HTTP attempted')),
              patch.object(preview.shutil, 'copyfile', side_effect=AssertionError('Media copy attempted')),
              redirect_stdout(output)):
            self.assertEqual(preview.main(args), 0)
        self.assertFalse(self.classrooms.exists())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('http', output.getvalue())

        native_path = self.build.parent / 'native-binding.json'
        self.run_preview(stage_id='stage-bound', binding_out=native_path)
        self.assertEqual(path.read_bytes(), native_path.read_bytes())
        self.assertEqual(json.loads(path.read_bytes())['projection'], self.saved[0][1])

        native_room = self.classrooms / 'stage-bound.json'
        native_room.write_bytes(b'existing runtime classroom')
        private_path = self.build.parent / 'binding-for-existing-alias.json'
        preview.write_preview_binding(self.build, stage_id='stage-bound', binding_out=private_path)
        self.assertEqual(private_path.read_bytes(), path.read_bytes())
        self.assertEqual(native_room.read_bytes(), b'existing runtime classroom')
        self.assertEqual(len(self.saved), 1)

    def test_binding_only_rejects_native_options_and_requires_an_explicit_alias_and_output(self):
        path = self.build.parent / 'binding-only.json'
        args = ['--binding-only', '--build', str(self.build)]
        complete = [*args, '--stage-id', 'stage-fresh', '--binding-out', str(path)]
        for argv in (
            [*complete, '--classrooms', str(self.classrooms)],
            [*complete, '--endpoint', 'http://localhost:3100'],
            [*args, '--binding-out', str(path)],
            [*args, '--stage-id', 'stage-fresh'],
        ):
            with self.subTest(argv=argv), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
                preview.main(argv)
            self.assertEqual(caught.exception.code, 2)
        self.assertFalse(path.exists())
        self.assertFalse(self.classrooms.exists())

    def test_binding_only_uses_the_same_alias_and_media_validation(self):
        path = self.build.parent / 'binding-only.json'
        for alias in (None, 'stage-x', 'tbpub_release', 'tbprev_frozen', 'omclass_existing'):
            with self.subTest(alias=alias), self.assertRaisesRegex(preview.PreviewError, 'binding_alias_invalid'):
                preview.write_preview_binding(self.build, stage_id=alias, binding_out=path)
        (self.build / 'media' / self.audio_name).write_bytes(b'tampered')
        with self.assertRaisesRegex(preview.PreviewError, 'media_hash_mismatch'):
            preview.write_preview_binding(self.build, stage_id='stage-fresh', binding_out=path)
        self.assertFalse(path.exists())
        self.assertFalse(self.classrooms.exists())

    def test_binding_only_rejects_unsafe_paths_and_does_not_replace_existing_files(self):
        original = self.build.parent / 'existing.json'
        original.write_bytes(b'keep')
        self.classrooms.mkdir(mode=0o700)
        symlink = self.build.parent / 'runtime-link'
        symlink.symlink_to(self.classrooms, target_is_directory=True)
        shared = self.build.parent / 'shared'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        with patch.object(preview, 'RUNTIME_ROOT', self.classrooms):
            for path in (original, symlink / 'binding.json', shared / 'binding.json'):
                with self.subTest(path=path), self.assertRaisesRegex(preview.PreviewError, 'binding_output_invalid'):
                    preview.write_preview_binding(self.build, stage_id='stage-fresh', binding_out=path)
        self.assertEqual(original.read_bytes(), b'keep')
        self.assertEqual(list(self.classrooms.iterdir()), [])
        self.assertEqual(list(shared.iterdir()), [])

    def test_binding_only_cleans_up_a_partial_write_or_failed_install(self):
        path = self.build.parent / 'binding-only.json'
        before = set(path.parent.iterdir())

        def fail_after_writing(_value, stream, **_options):
            stream.write('partial private binding')
            raise OSError('disk error')

        for name, failure in (
            ('json.dump', {'side_effect': fail_after_writing}),
            ('os.link', {'side_effect': OSError('installation failed')}),
        ):
            with (self.subTest(name=name), patch('courseware.tools.preview.' + name, **failure),
                  self.assertRaisesRegex(preview.PreviewError, 'binding_output_failed')):
                preview.write_preview_binding(self.build, stage_id='stage-fresh', binding_out=path)
            self.assertEqual(set(path.parent.iterdir()), before)
        self.assertFalse(self.classrooms.exists())


if __name__ == '__main__':
    unittest.main()
