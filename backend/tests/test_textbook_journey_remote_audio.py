"""Cold published activity audio uses exact registered manifests and bytes."""
from copy import deepcopy
import hashlib
from io import BytesIO
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import unquote, urlsplit

from flask import Flask

from content import (textbook_activity, textbook_journey as journey, textbook_journey_registry as registry,
                     textbook_picture_questions)
from content import textbook_catalog
from core.course_storage_config import CourseStorageConfig
from core.errors import ApiError
from routes.internal.textbooks import internal_textbooks_bp
from services.course_file_store import CourseFileStore, CourseFileStorageError


class _RemoteResponse(BytesIO):
    status = 200
    def __init__(self, raw):
        super().__init__(raw)
        self.headers = {'ETag': '"' + 'a' * 32 + '"', 'Content-Length': str(len(raw))}


class JourneyRemoteAudioTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.activities = self.root / 'backend/content/textbooks/activities'
        self.activities.mkdir(parents=True)
        self.raw = b'RIFF' + bytes(range(4, 64))
        self.asset = journey.audio_id('老师请点图') + '.wav'
        self.audio_path = self.activities / 'audio-v2/qwen-proof' / self.asset
        self.manifest_path = self.activities / 'audio-v2/manifest.json'
        self.manifest = {self.asset: {'text': '老师请点图', 'file': 'qwen-proof/' + self.asset,
            'sha256': hashlib.sha256(self.raw).hexdigest(), 'bytes': len(self.raw)}}
        self.entries, self.objects, self.requests = {}, {}, []
        self.repository = Mock()
        self.repository.resolve.side_effect = self.resolve
        self.store = CourseFileStore(config=CourseStorageConfig(mode='registry', endpoint='http://store.invalid:9000', bucket='study'),
                                     project_root=self.root, repository=self.repository)
        self.opener = Mock()
        self.opener.open.side_effect = self.remote
        self.install(patch('services.course_file_store.CourseFileStore', return_value=self.store))
        self.install(patch('services.course_file_store.build_opener', return_value=self.opener))
        self.install(patch.object(journey, 'ROOT', self.activities))
        self.install(patch.object(journey, 'definition', return_value=SimpleNamespace(audio_pack='audio-v2')))
        self.install(patch.object(journey, 'definitions', return_value=(SimpleNamespace(audio_pack='audio-v2'),)))
        self.register(self.manifest_path, json.dumps(self.manifest).encode(), 'application/json')
        self.register(self.audio_path, self.raw, 'audio/wav')

    def install(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def register(self, path, raw, mime):
        name = path.relative_to(self.root).as_posix()
        key = 'originals/' + name
        self.objects[key] = raw
        self.entries[name] = {'sourcePath': name, 'sha256': hashlib.sha256(raw).hexdigest(),
            'byteSize': len(raw), 'mimeType': mime,
            'locator': {'kind': 'object', 'objectKey': key, 'etag': 'a' * 32}}

    def resolve(self, name, storage_id, expected_sha=None):
        record = self.entries.get(name)
        return record if expected_sha is None or (record and record['sha256'] == expected_sha) else None

    def remote(self, request, timeout):
        self.assertEqual(request.get_header('If-match'), '"' + 'a' * 32 + '"')
        self.requests.append(request)
        key = unquote(urlsplit(request.full_url).path).removeprefix('/study/')
        if key not in self.objects:
            raise URLError('missing remote original')
        return _RemoteResponse(self.objects[key])

    def published(self):
        return journey.audio_file(self.asset, release={'sha256': 'b' * 64})

    def assert_invalid(self):
        with self.assertRaises(ApiError) as failure:
            self.published()
        self.assertEqual((failure.exception.code, failure.exception.status_code), ('textbook_audio_invalid', 503))

    def test_cold_published_manifest_and_audio_read_only_exact_registered_bytes(self):
        self.assertFalse(self.manifest_path.exists())
        self.assertFalse(self.audio_path.exists())
        value = self.published()
        self.assertIsInstance(value, journey.VerifiedActivityAudio)
        self.assertEqual(value.read(), self.raw)
        self.assertEqual(value.sha256, self.manifest[self.asset]['sha256'])
        self.assertEqual(value.name, self.asset)
        self.assertEqual(len(self.requests), 2)
        self.assertFalse(self.audio_path.exists())

    def test_review_question_verifies_registered_pack_without_local_manifest_or_wavs(self):
        from services.learning_review_questions import authored_question
        original = {'id': 'point-tree', 'prompt': '请点小树。', 'hints': ['看看树叶。'], 'explanation': '这是小树。',
            'targets': ['A'], 'visual': {'art': {'src': '/tree.png'}},
            'options': [{'value': 'A', 'label': '小树', 'picture': {'src': '/tree.png'}}]}
        texts = ['请点小树。A，小树。', *original['hints'], original['explanation']]
        manifest = {}
        for text in texts:
            asset = journey.audio_id(text) + '.wav'
            manifest[asset] = {'text': text, 'file': 'qwen-proof/' + asset, 'providerId': 'qwen-tts',
                'fallbackUsed': False, 'sha256': hashlib.sha256(self.raw).hexdigest(), 'bytes': len(self.raw)}
            self.register(self.audio_path.parent / asset, self.raw, 'audio/wav')
        self.register(self.manifest_path, json.dumps(manifest).encode(), 'application/json')
        spec = SimpleNamespace(renderer='picture_choices', audio_pack='audio-v2',
            plan={'id': 'current-activity', 'releaseSha256': 'b' * 64, 'skills': {'tree': {'word': '小树'}}})
        course = {'subject': 'chinese', 'grade_code': 'primary_1', 'id': 'current-course',
                  'version': 'storybook-1', 'title': '天地人'}
        result = authored_question(spec, course, 'tree', original, release={'sha256': 'b' * 64})
        self.assertEqual(result['promptAudioAsset'], journey.audio_id(texts[0]) + '.wav')
        self.assertFalse(self.manifest_path.exists())
        self.assertTrue(self.requests)
        self.objects.pop('originals/' + self.manifest_path.relative_to(self.root).as_posix())
        with self.assertRaises(CourseFileStorageError):
            authored_question(spec, course, 'tree', original, release={'sha256': 'b' * 64})

    def test_registered_remote_failure_or_corruption_never_uses_valid_local_shadows(self):
        self.audio_path.parent.mkdir(parents=True)
        self.audio_path.write_bytes(self.raw)
        self.manifest_path.write_text(json.dumps(self.manifest))
        key = 'originals/' + self.audio_path.relative_to(self.root).as_posix()
        for raw in (None, b'x' * len(self.raw)):
            with self.subTest(missing=raw is None):
                if raw is None:
                    self.objects.pop(key, None)
                else:
                    self.objects[key] = raw
                self.assert_invalid()

    def test_published_requires_both_manifest_and_audio_registered_even_if_local_bytes_match(self):
        self.audio_path.parent.mkdir(parents=True)
        self.audio_path.write_bytes(self.raw)
        self.manifest_path.write_text(json.dumps(self.manifest))
        for path in (self.manifest_path, self.audio_path):
            with self.subTest(path=path.name):
                name = path.relative_to(self.root).as_posix()
                saved = self.entries.pop(name)
                self.assert_invalid()
                self.entries[name] = saved

    def test_expected_audio_sha_size_mime_and_manifest_ownership_must_match(self):
        audio_name = self.audio_path.relative_to(self.root).as_posix()
        manifest_name = self.manifest_path.relative_to(self.root).as_posix()
        for field, value in [('sha256', 'f' * 64), ('byteSize', len(self.raw) + 1), ('mimeType', 'image/png')]:
            saved = deepcopy(self.entries[audio_name])
            self.entries[audio_name][field] = value
            self.assert_invalid()
            self.entries[audio_name] = saved
        self.entries[manifest_name]['mimeType'] = 'text/plain'
        self.assert_invalid()

    def test_manifest_paths_cannot_escape_pack_and_unknown_assets_are_not_exposed(self):
        for relative in ('../elsewhere.wav', '/outside.wav', 'qwen\\outside.wav', 'qwen/./voice.wav', 'qwen/receipt.json'):
            bad = deepcopy(self.manifest)
            bad[self.asset]['file'] = relative
            self.register(self.manifest_path, json.dumps(bad).encode(), 'application/json')
            self.assert_invalid()
        for name in ('../manifest.json', 'other.wav', 'A' * 24 + '.wav'):
            with self.assertRaises(ApiError) as failure:
                journey.audio_file(name, release={})
            self.assertEqual(failure.exception.code, 'textbook_audio_missing')

    def test_authorized_pack_does_not_search_another_lesson(self):
        self.register(self.manifest_path, b'{}', 'application/json')
        self.register(self.activities / 'navigation-audio-v1/manifest.json', b'{}', 'application/json')
        self.register(self.activities / 'other-lesson/manifest.json', json.dumps(self.manifest).encode(), 'application/json')
        with self.assertRaises(ApiError) as failure:
            self.published()
        self.assertEqual(failure.exception.code, 'textbook_audio_missing')
        self.assertTrue(all('/other-lesson/' not in r.full_url for r in self.requests))

    def test_explicitly_unregistered_new_fixture_retains_legacy_local_path(self):
        self.entries.clear()
        self.audio_path.parent.mkdir(parents=True)
        self.audio_path.write_bytes(self.raw)
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.assertEqual(journey.audio_file(self.asset), self.audio_path.resolve())

    def test_registered_source_spelling_does_not_follow_a_local_symlink_before_lookup(self):
        self.audio_path.parent.mkdir(parents=True)
        elsewhere = self.root / 'different-local.wav'
        elsewhere.write_bytes(b'shadow')
        self.audio_path.symlink_to(elsewhere)
        self.assertEqual(self.published().read(), self.raw)

    def client(self, guard=None):
        app = Flask(__name__)
        app.register_blueprint(internal_textbooks_bp, url_prefix='/internal/learning/textbooks')
        service = Mock()
        service.activity_audio.side_effect = lambda token, asset: self.published()
        self.install(patch('routes.internal.textbooks.internal_request_guard', return_value=guard or Mock()))
        self.install(patch('routes.internal.textbooks.textbook_classroom_service', return_value=service))
        return app.test_client(), service

    def test_internal_route_preserves_authorization_wav_private_headers_and_byte_ranges(self):
        client, service = self.client()
        url = '/internal/learning/textbooks/runtime/play-audio/' + self.asset
        response = client.get(url, headers={'X-Mira-Textbook-Token': 'signed-runtime'})
        self.assertEqual((response.status_code, response.data), (200, self.raw))
        self.assertEqual(response.mimetype, 'audio/wav')
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(response.headers['ETag'], '"' + self.manifest[self.asset]['sha256'] + '"')
        service.activity_audio.assert_called_with('signed-runtime', self.asset)
        partial = client.get(url, headers={'Range': 'bytes=5-9'})
        self.assertEqual((partial.status_code, partial.data), (206, self.raw[5:10]))
        self.assertEqual(partial.headers['Content-Range'], 'bytes 5-9/64')
        self.assertEqual(partial.headers['Cache-Control'], 'private, no-store')
        self.assertEqual(client.get(url, headers={'Range': 'bytes=100-200'}).status_code, 416)

    def test_internal_authority_rejection_happens_before_any_course_read(self):
        guard = Mock()
        guard.authorize.side_effect = ApiError('internal_forbidden', 'Denied', 403)
        client, service = self.client(guard)
        response = client.get('/internal/learning/textbooks/runtime/play-audio/' + self.asset)
        self.assertEqual(response.status_code, 403)
        service.activity_audio.assert_not_called()
        self.assertEqual(self.requests, [])

    def test_teaching_module_reloads_do_not_read_any_course_file_at_import_time(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('import-time bytes read')), \
             patch.object(Path, 'read_text', side_effect=AssertionError('import-time text read')):
            importlib.reload(registry)
            importlib.reload(textbook_activity)
            importlib.reload(textbook_picture_questions)
            importlib.reload(journey)

    def test_fresh_import_has_no_activity_original_reads_before_configuration(self):
        code = r'''
from pathlib import Path
import sys
original_text, original_bytes = Path.read_text, Path.read_bytes
def guard(original):
    def read(path, *args, **kwargs):
        if '/content/textbooks/' in str(path):
            raise AssertionError('Teaching original read during fresh import')
        return original(path, *args, **kwargs)
    return read
Path.read_text, Path.read_bytes = guard(original_text), guard(original_bytes)
import content.textbook_journey
assert 'core.config' not in sys.modules
'''
        subprocess.run([sys.executable, '-c', code], check=True, timeout=20, capture_output=True)

    def teaching_originals(self):
        source = Path(registry.__file__).parent / 'textbooks/activities'
        result = {}
        for name in ('registry.v1.json', 'tiandiren.v1.json', 'tiandiren.journey.v2.json', 'tiandiren.visuals.v1.json'):
            raw = (source / name).read_bytes()
            self.register(self.activities / name, raw, 'application/json')
            result[name] = raw
        return result

    def test_cold_registry_plan_flow_and_legacy_constants_use_remote_registered_originals(self):
        originals = self.teaching_originals()
        registry.definitions.cache_clear()
        self.addCleanup(registry.definitions.cache_clear)
        with patch.object(registry, 'ROOT', self.activities), patch.object(textbook_activity, 'ROOT', self.activities), \
             patch.object(textbook_picture_questions, 'ROOT', self.activities):
            definitions = registry.definitions()
            self.assertEqual(len(definitions), 1)
            self.assertEqual(definitions[0].audio_pack, 'audio-v2')
            self.assertEqual(textbook_activity.PLAN, json.loads(originals['tiandiren.v1.json']))
            self.assertEqual(journey.FLOW, json.loads(originals['tiandiren.journey.v2.json']))
            self.assertEqual(journey.SKILLS, definitions[0].skills)
            self.assertEqual(textbook_picture_questions.VISUALS, json.loads(originals['tiandiren.visuals.v1.json']))
        self.assertTrue(all(not (self.activities / name).exists() for name in originals))

    def test_registry_expected_plan_sha_never_uses_a_valid_local_shadow_for_wrong_version(self):
        originals = self.teaching_originals()
        bad = json.loads(originals['registry.v1.json'])
        bad['definitions'][0]['plan']['sha256'] = 'f' * 64
        self.register(self.activities / 'registry.v1.json', json.dumps(bad).encode(), 'application/json')
        (self.activities / 'tiandiren.v1.json').write_bytes(originals['tiandiren.v1.json'])
        registry.definitions.cache_clear()
        self.addCleanup(registry.definitions.cache_clear)
        with patch.object(registry, 'ROOT', self.activities), self.assertRaises(CourseFileStorageError):
            registry.definitions()

    def test_unregistered_registry_cannot_escape_to_same_bytes_outside_its_source_root(self):
        originals = self.teaching_originals()
        self.entries.clear()
        for name, raw in originals.items():
            (self.activities / name).write_bytes(raw)
        plan = self.activities / 'tiandiren.v1.json'
        elsewhere = self.root / 'outside-plan.json'
        plan.rename(elsewhere)
        plan.symlink_to(elsewhere)
        registry.definitions.cache_clear()
        self.addCleanup(registry.definitions.cache_clear)
        with patch.object(registry, 'ROOT', self.activities), self.assertRaisesRegex(ValueError, 'escaped'):
            registry.definitions()

    def test_catalog_superseded_metadata_reads_registered_original_and_never_a_local_shadow(self):
        path = self.activities.parent / 'sources/smartedu-current-primary-20260928.json'
        self.register(path, b'{"supersededResourceIds":["old-fixture"]}', 'application/json')
        textbook_catalog.superseded_resources.cache_clear()
        self.addCleanup(textbook_catalog.superseded_resources.cache_clear)
        with patch.object(textbook_catalog, 'Path', return_value=self.root / 'backend/content/textbook_catalog.py'):
            self.assertEqual(textbook_catalog.superseded_resources(), frozenset({'old-fixture'}))
            self.assertFalse(path.exists())
            textbook_catalog.superseded_resources.cache_clear()
            self.objects.pop('originals/' + path.relative_to(self.root).as_posix())
            path.parent.mkdir(parents=True)
            path.write_bytes(b'{"supersededResourceIds":["local-shadow"]}')
            with self.assertRaises(CourseFileStorageError):
                textbook_catalog.superseded_resources()
