"""Container counterexamples and real immutable archive outputs, no DB writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, Mock

from content.textbook_catalog import canonical, digest
from content.textbook_release_media import MAX_MEDIA_BYTES, media_mime_type
from core.errors import ApiError
from core.security import now_ms
from services.textbook_publication_service import TextbookPublicationService


def mp4_bytes():
    def box(kind, data=b''):
        return struct.pack('>I', len(data) + 8) + kind + data
    return box(b'ftyp', b'isom\x00\x00\x02\x00isommp42') + box(b'moov') + box(b'mdat', b'\x00\x00\x00\x01')


def webm_bytes():
    # Minimal structural container fixture, not a playable codec acceptance.
    return b'\x1a\x45\xdf\xa3\x87\x42\x82\x84webm\x18\x53\x80\x67\xff\xec\x81\x00'


def glb_bytes(document=None):
    document = document or {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': []}]}
    body = canonical(document).encode()
    body += b' ' * (-len(body) % 4)
    return b'glTF' + struct.pack('<II', 2, 20 + len(body)) + struct.pack('<II', len(body), 0x4E4F534A) + body


class MediaContainerTests(unittest.TestCase):
    def test_new_formats_require_real_matching_container_headers(self):
        valid = {'.mp4': (mp4_bytes(), 'video/mp4'), '.webm': (webm_bytes(), 'video/webm'),
                 '.glb': (glb_bytes(), 'model/gltf-binary')}
        for suffix, (raw, mime) in valid.items():
            self.assertEqual(media_mime_type(suffix, raw), mime)
            with self.assertRaises(ApiError):
                media_mime_type(suffix, b'pretend-media')
        for suffix, raw in [('.mp4', webm_bytes()), ('.webm', mp4_bytes()), ('.glb', mp4_bytes()),
                            ('.mp4', mp4_bytes()[:-1]), ('.webm', webm_bytes()[:10]), ('.glb', glb_bytes()[:-1])]:
            with self.subTest(suffix=suffix, size=len(raw)), self.assertRaises(ApiError):
                media_mime_type(suffix, raw)

    def test_glb_rejects_wrong_version_invalid_chunks_and_external_resources(self):
        bad_version = bytearray(glb_bytes())
        struct.pack_into('<I', bad_version, 4, 1)
        bad_chunk = bytearray(glb_bytes())
        struct.pack_into('<I', bad_chunk, 12, len(bad_chunk))
        examples = [bytes(bad_version), bytes(bad_chunk),
            glb_bytes({'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 4, 'uri': 'outside.bin'}]}),
            glb_bytes({'asset': {'version': '2.0'}, 'images': [{'uri': 'https://outside.example/texture.png'}]}),
            glb_bytes({'asset': {'version': '2.0'}, 'buffers': [{'byteLength': 100}]})]
        for raw in examples:
            with self.assertRaises(ApiError):
                media_mime_type('.glb', raw)

    def test_oversize_executable_and_unarchived_resource_formats_are_rejected(self):
        for suffix in ['.js', '.html', '.gltf', '.bin']:
            with self.assertRaises(ApiError):
                media_mime_type(suffix, glb_bytes())
        with self.assertRaises(ApiError):
            media_mime_type('.mp4', b'x' * (MAX_MEDIA_BYTES + 1))
        for suffix, mime in [('.wav', 'audio/wav'), ('.mp3', 'audio/mpeg'),
                             ('.png', 'image/png'), ('.webp', 'image/webp')]:
            self.assertEqual(media_mime_type(suffix, b'previously reviewed fixture'), mime)


class MediaArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'classrooms'
        self.root.mkdir()
        self.source_id = 'synthetic-preview'
        self.media_origin = ''
        self.audio = b'existing-reviewed-audio-fixture'
        self.audio_path = f'/api/classroom-media/{self.source_id}/audio/tts1.wav'
        self.classroom = {'id': self.source_id, 'stage': {'id': self.source_id, 'name': 'Synthetic media archive'},
            'scenes': [{'id': 'slide', 'type': 'slide', 'content': {}, 'actions': [
                {'id': 'speech1', 'type': 'speech', 'text': 'Synthetic narration', 'audioId': 'tts1', 'audioUrl': self.audio_path}]},
                {'id': 'interactive', 'type': 'interactive', 'content': {'html': ''}, 'actions': []},
                {'id': 'quiz', 'type': 'quiz', 'actions': [], 'content': {'questions': [
                    {'id': 'q1', 'type': 'single', 'question': 'Synthetic question', 'options': [
                        {'value': 'A', 'label': 'A'}, {'value': 'B', 'label': 'B'}], 'answer': ['A'],
                     'analysis': 'Synthetic explanation', 'points': 1, 'questionAudioUrl': self.audio_path}]}}]}
        self.manifest = {'editionId': 'synthetic-book', 'revisionId': '1', 'gradeCode': 'primary_1', 'subject': 'math',
            'units': [{'title': 'Synthetic unit', 'lessons': [{'nodeId': 'one', 'brief': {'objectives': ['Synthetic objective']}}]}]}
        self.repository = MagicMock()
        self.repository.parse.side_effect = json.loads
        self.repository.get_revision.return_value = {'manifest_sha256': digest(self.manifest)}
        self.repository.manifest.return_value = self.manifest
        self.preview = Mock(repository=self.repository, runtime=Mock(base_url='http://127.0.0.1:3100'))
        self.service = TextbookPublicationService(self.preview)
        audio_file = self.root / self.source_id / 'audio/tts1.wav'
        audio_file.parent.mkdir(parents=True)
        audio_file.write_bytes(self.audio)

    def prepare(self, media):
        html = []
        for filename, raw in media.items():
            path = self.root / self.source_id / 'media' / filename
            path.parent.mkdir(exist_ok=True)
            if not path.exists():
                path.write_bytes(raw)
            html.append(f'<source src="{self.media_origin}/api/classroom-media/{self.source_id}/media/{filename}">')
        self.classroom['scenes'][1]['content']['html'] = ''.join(html)
        source_hash = digest(self.classroom)
        (self.root / (self.source_id + '.json')).write_text(canonical(self.classroom))
        audio_hash = hashlib.sha256(self.audio).hexdigest()
        row = {'status': 'preview_ready', 'classroom_id': self.source_id, 'classroom_json': canonical(self.classroom),
            'classroom_sha256': source_hash, 'edition_id': 'synthetic-book', 'node_id': 'one',
            'input_json': canonical({'previewPrompt': {'expectedSceneCount': 3, 'expectedQuestionCount': 1}}),
            'result_json': canonical({'audioReceipts': [{'requestId': 'tts1', 'audioSha256': audio_hash}]})}
        self.preview.get.return_value = row
        audit = {'previewKey': 'synthetic-key', 'sourceSha256': source_hash, 'passed': True, 'segments': [{
            'actionId': 'speech1', 'ttsRequestId': 'tts1', 'audioSha256': audio_hash,
            'textSha256': hashlib.sha256(b'Synthetic narration').hexdigest(),
            'similarityBps': 10000, 'asr': {'status': 'succeeded'}}]}
        audit['sha256'] = digest(audit)
        review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
            'publicationAuthorized': True, 'reviewer': 'Synthetic test reviewer', 'basis': 'Isolated fixture only',
            'sourceSha256': source_hash, 'reviewedAt': now_ms() - 1}
        return self.service.prepare(key='synthetic-key', edition='synthetic-book', revision='1', node='one',
            teaching_revision='test', review=review, audio_audit=audit, classroom_directory=self.root)

    def test_archive_hash_names_and_bytes_include_video_and_self_contained_model(self):
        assets = {'lesson.mp4': mp4_bytes(), 'scene.webm': webm_bytes(), 'model.glb': glb_bytes()}
        prepared = self.prepare(assets)
        items = {item['mimeType']: item for item in prepared['release']['media']}
        for filename, raw in assets.items():
            suffix = Path(filename).suffix
            item = items[media_mime_type(suffix, raw)]
            self.assertEqual(item['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(item['byteSize'], len(raw))
            self.assertTrue(item['path'].endswith('/media/' + item['sha256'] + suffix))
            path = self.root / item['path'].split('/api/classroom-media/')[1]
            self.assertEqual(path.read_bytes(), raw)
            self.assertIn(item['path'], prepared['release']['classroom']['scenes'][1]['content']['html'])
        self.repository.reserve_build.assert_not_called()
        self.assertEqual(self.prepare(assets)['release']['sha256'], prepared['release']['sha256'])

    def test_archive_rejects_renamed_executables_and_symlinks_outside_store(self):
        for name, raw in [('bad.mp4', b'alert(1)'), ('bad.js', mp4_bytes())]:
            with self.assertRaises(ApiError):
                self.prepare({name: raw})
        outside = Path(self.temporary.name) / 'outside.mp4'
        outside.write_bytes(mp4_bytes())
        escaped = self.root / self.source_id / 'media/escape.mp4'
        escaped.symlink_to(outside)
        with self.assertRaises(ApiError):
            self.prepare({'escape.mp4': mp4_bytes()})
        self.media_origin = 'https://unreviewed.example'
        with self.assertRaises(ApiError):
            self.prepare({'foreign.mp4': mp4_bytes()})


if __name__ == '__main__':
    unittest.main()
