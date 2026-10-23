"""Container counterexamples and real immutable archive outputs, no DB writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

from content.textbook_catalog import canonical, digest
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_preview_audio_contract import (
    asr_request_id, audit_contract_identity, compare_transcript, new_audio_plan, tts_request_id,
)
from content.textbook_release_media import MAX_MEDIA_BYTES, media_mime_type
from content.textbook_whole_course_quality import DIMENSIONS, SCHEMA as WHOLE_COURSE_QUALITY_SCHEMA
from core.errors import ApiError
from core.security import now_ms
from services.textbook_preview_audio import core_content
from services.textbook_publication_service import TextbookPublicationService
from services.course_media_object_store import CourseMediaStorageError


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


def whole_course_quality_review(source_sha256, policy_sha256, scene_id='interactive'):
    return {'schemaVersion': WHOLE_COURSE_QUALITY_SCHEMA, 'status': 'passed',
        'policySha256': policy_sha256, 'sourceSha256': source_sha256,
        'dimensions': {name: {'status': 'passed', 'evidence': [f'Played evidence for {name}.']}
                       for name in DIMENSIONS},
        'coreActivities': [{'sceneId': scene_id,
            'childTask': 'Change the learning objects and compare the visible result.',
            'states': {name: {'description': f'Preserved {name} play state.',
                              'evidenceSha256': digest({'scene': scene_id, 'state': name})}
                       for name in ('before', 'action', 'after', 'revise')},
            'visibleWorldChange': 'The learning objects visibly change after the child decision.',
            'failureOrAlternative': [{'kind': 'failure', 'trigger': 'A specific relationship is broken.',
                'visibleOutcome': 'The affected object and relationship remain visible.',
                'teacherFeedback': 'The teacher identifies the affected object and exact break point.',
                'revisionStep': 'The child repairs the relationship and compares both results.'}],
            'targetShortcutCheck': {'shortcut': 'Use a fixed position instead of the lesson target.',
                'outcome': 'blocked', 'evidence': 'Positions were changed while the target stayed authoritative.'},
            'crossPageCarry': 'The changed object and same characters continue into the following page.',
            'newContextTransfer': 'A new arrangement checks the same target without a repeated answer position.'}],
        'hardFailures': []}


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
        self.key = digest('synthetic-preview')
        self.operator_input = {}
        self.courseware_quality = None
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
        frozen_input = {'editionId': self.manifest['editionId'], 'alignmentRevisionId': self.manifest['revisionId'],
            'manifestSha256': digest(self.manifest), 'nodeId': 'one', 'gradeCode': self.manifest['gradeCode'],
            'subject': self.manifest['subject'],
            'previewPrompt': {'expectedSceneCount': 3, 'expectedQuestionCount': 1}, **self.operator_input}
        self.repository.get_revision.return_value = {'manifest_sha256': digest(self.manifest)}
        # Freeze the pre-narration content so repeated prepares keep the same
        # deterministic request identity instead of hashing their own audio IDs.
        original = core_content(self.classroom)
        plan = new_audio_plan(preview_key=self.key, classroom_sha256=digest(original),
            core_sha256=digest(original), frozen_input=frozen_input)
        folder = self.root / self.source_id / 'textbook-preview-audio'
        folder.mkdir(exist_ok=True)
        (folder / 'plan.json').write_text(canonical(plan))
        scene = self.classroom['scenes'][0]
        action = scene['actions'][0]
        request_id = tts_request_id(plan, scene['id'], action['id'], action['text'])
        teacher = plan['teacher']
        action.update(audioId=request_id, audioMetadata={'schemaVersion': 'mira.openmaic.speech-audio.v1',
            'providerId': teacher['tts']['providerId'], 'modelId': teacher['tts']['modelId'],
            'voiceId': teacher['voiceId'], 'fallbackUsed': False})
        source_hash = digest(self.classroom)
        (self.root / (self.source_id + '.json')).write_text(canonical(self.classroom))
        audio_hash = hashlib.sha256(self.audio).hexdigest()
        receipt = {'requestId': request_id, 'status': 'succeeded', 'audioSha256': audio_hash,
            'mimeType': 'audio/wav', 'previewAudioIdentity': {'planSha256': digest(plan), 'attempt': 1}}
        row = {'status': 'preview_ready', 'classroom_id': self.source_id, 'classroom_json': canonical(self.classroom),
            'classroom_sha256': source_hash, 'edition_id': 'synthetic-book', 'node_id': 'one',
            'input_json': canonical(frozen_input), 'result_json': canonical({'audioReceipts': [receipt]})}
        self.preview.get.return_value = row
        transcript = action['text']
        text_hash = hashlib.sha256(transcript.encode()).hexdigest()
        comparison = compare_transcript(plan, transcript, transcript)
        audit = {'schemaVersion': 'mira.textbook.audio-audit.v2', 'previewKey': self.key,
            'sourceSha256': source_hash, 'passed': True, 'contract': audit_contract_identity(plan), 'segments': [{
                'sceneId': scene['id'], 'actionId': action['id'], 'text': transcript, 'textSha256': text_hash,
                'ttsRequestId': request_id, 'audioSha256': audio_hash, 'transcript': transcript,
                'comparison': comparison, 'similarityBps': comparison['similarityBps'],
                'asr': {'status': 'succeeded', 'requestId': asr_request_id(plan, request_id, audio_hash),
                    'transcript': transcript, 'transcriptSha256': text_hash}}]}
        audit['sha256'] = digest(audit)
        review = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
            'publicationAuthorized': True, 'reviewer': 'Synthetic test reviewer', 'basis': 'Isolated fixture only',
            'sourceSha256': source_hash, 'reviewedAt': now_ms() - 1}
        if self.courseware_quality is not None:
            review['coursewareQuality'] = (self.courseware_quality(source_hash)
                if callable(self.courseware_quality) else self.courseware_quality)
        return self.service.prepare(key=self.key, edition='synthetic-book', revision='1', node='one',
            teaching_revision='test', review=review, audio_audit=audit, classroom_directory=self.root)

    def test_new_release_binds_all_scene_owners_without_changing_reviewed_source(self):
        self.classroom['scenes'][0]['stageId'] = self.source_id
        self.classroom['scenes'][1]['stageId'] = 'tbrev_older_revision'
        self.classroom['scenes'][1]['content']['url'] = 'tbrev_older_revision'
        for order, scene in enumerate(self.classroom['scenes'], 1):
            scene['order'] = order
        prepared = self.prepare({})
        source = deepcopy(self.classroom)
        row = self.preview.get.return_value
        release = prepared['release']
        classroom_id = release['classroomId']
        self.assertEqual(release['classroom']['id'], classroom_id)
        self.assertEqual(release['classroom']['stage']['id'], classroom_id)
        self.assertEqual([s['stageId'] for s in release['classroom']['scenes']], [classroom_id] * 3)
        published_audio = next(m['path'] for m in release['media'] if m['mimeType'] == 'audio/wav')

        def original_media(value):
            if isinstance(value, dict):
                return {k: original_media(v) for k, v in value.items()}
            if isinstance(value, list):
                return [original_media(v) for v in value]
            return self.audio_path if value == published_audio else value

        for before, after in zip(source['scenes'], release['classroom']['scenes']):
            self.assertEqual(original_media({k: v for k, v in after.items() if k != 'stageId'}),
                             {k: v for k, v in before.items() if k != 'stageId'})
        self.assertEqual(self.classroom, source)
        self.assertEqual(json.loads(row['classroom_json']), source)
        self.assertEqual(json.loads((self.root / (self.source_id + '.json')).read_text()), source)
        self.assertEqual(prepared['frozen']['sourceSha256'], digest(source))
        self.assertEqual(row['classroom_sha256'], digest(source))
        self.assertEqual(release['classroomSha256'], digest(release['classroom']))
        self.assertEqual(release['sha256'], digest({k: v for k, v in release.items() if k != 'sha256'}))

    def test_policy_v2_candidate_requires_and_binds_whole_course_quality_review(self):
        policy_sha = digest({'policy': 'quality-v2'})
        self.operator_input = {'authoringCandidate': {
            'schemaVersion': 'mira.textbook.authoring-candidate.v1', 'sha256': 'a' * 64,
            'contractSha256': 'b' * 64, 'sceneCount': 3, 'assetCount': 1,
            'verification': 'frozen_identity_and_artifact_integrity_only',
            'interactionPolicyVersion': 2, 'interactionPolicySha256': policy_sha,
            'wholeCourseQualityContractSha256': 'c' * 64}}
        with self.assertRaises(ApiError):
            self.prepare({})

        self.courseware_quality = lambda source_sha: whole_course_quality_review(source_sha, policy_sha)
        prepared = self.prepare({})
        receipt = self.courseware_quality(prepared['frozen']['sourceSha256'])
        self.assertEqual(prepared['frozen']['wholeCourseQualityReviewSha256'], digest(receipt))
        self.assertEqual(prepared['review']['coursewareQuality'], receipt)

    def test_legacy_complete_scene_followup_requires_current_policy_quality_and_trace(self):
        current = freeze_interaction_policy()
        candidate_source_sha = 'd' * 64
        candidate = {'schemaVersion': 'mira.textbook.authoring-candidate.v1', 'sha256': 'a' * 64,
            'contractSha256': 'b' * 64, 'sceneCount': 3, 'assetCount': 1,
            'verification': 'frozen_identity_and_artifact_integrity_only',
            'interactionPolicyVersion': 1, 'interactionPolicySha256': 'c' * 64}
        body = {'schemaVersion': 'mira.textbook.complete-scene-review-followup.v1',
            'status': 'quality_review_required',
            'verification': 'sealed_complete_scene_revision_chain_and_current_candidate',
            'sessionId': 'session-review', 'stageId': self.source_id,
            'baseInteractionPolicyVersion': 1, 'baseInteractionPolicySha256': 'c' * 64,
            'currentInteractionPolicyVersion': current['policy']['version'],
            'currentInteractionPolicySha256': current['sha256'],
            'wholeCourseQualityContractSha256': digest(current['policy']['wholeCourseQualityContract']),
            'candidateSourceSha256': candidate_source_sha, 'candidateSha256': candidate['sha256'],
            'candidateFileSha256': 'e' * 64, 'revisionIds': ['f' * 64],
            'revisionReceiptSha256s': ['1' * 64], 'completeSceneIds': ['interactive']}
        followup = {**body, 'sha256': digest(body)}
        candidate['completeSceneReviewFollowup'] = followup
        self.operator_input = {'sourceSha256': candidate_source_sha,
            'authoring': {'sessionId': 'session-review', 'stageId': self.source_id},
            'authoringCandidate': candidate}
        target = 'services.textbook_publication_service.discover_complete_scene_review_followup'
        with patch(target, return_value=followup):
            with self.assertRaises(ApiError):
                self.prepare({})
            self.courseware_quality = lambda source_sha: whole_course_quality_review(
                source_sha, current['sha256'])
            prepared = self.prepare({})
        self.assertEqual(prepared['frozen']['completeSceneReviewFollowup'], followup)
        self.assertEqual(prepared['frozen']['authoringSourceSha256'], candidate_source_sha)
        self.assertEqual(prepared['review']['coursewareQuality']['policySha256'], current['sha256'])

        with patch(target, return_value=None), self.assertRaises(ApiError):
            self.prepare({})

    def test_operator_reviewed_objectives_replace_directory_placeholder_in_course_summary(self):
        placeholder = ['本课教学目标待逐页核验。']
        self.manifest['units'][0]['lessons'][0]['brief']['objectives'] = placeholder
        objectives = ['看图比较两组物品的多少。', '用配对的方法说明比较结果。']
        self.operator_input = {'sourceScope': {'reviewer': 'Synthetic scope reviewer',
            'basis': 'Isolated reviewed lesson objectives'}, 'knowledgeBrief': {'objectives': objectives}}

        prepared = self.prepare({'lesson.mp4': mp4_bytes()})

        self.assertEqual(prepared['course']['objective'], '；'.join(objectives))
        self.assertEqual(json.loads(prepared['course']['content_json'])['objectives'], objectives)
        self.assertEqual(prepared['manifest']['units'][0]['lessons'][0]['brief']['objectives'], placeholder)
        self.repository.reserve_build.assert_not_called()

    def test_prepare_preserves_native_string_key_and_full_course_answer(self):
        question = self.classroom['scenes'][2]['content']['questions'][0]
        question['options'] = [{'value': 'picture-one', 'label': 'one'},
                               {'value': 'picture-two', 'label': 'two'}]
        question['answer'] = 'picture-two'
        prepared = self.prepare({})
        self.assertEqual(json.loads(prepared['course']['content_json'])['questions'][0]['answer'], 'picture-two')
        self.assertEqual(prepared['release']['classroom']['scenes'][2]['content']['questions'][0]['answer'], 'picture-two')
        self.assertEqual(question['answer'], 'picture-two')
        self.repository.reserve_build.assert_not_called()

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

    def test_preparing_migrated_targets_reuses_remote_bytes_without_recreating_local_copies(self):
        assets = {'picture.png': b'reviewed-picture-fixture', 'lesson.mp4': mp4_bytes()}
        prepared = self.prepare(assets)
        archived = {(self.root / item['path'].removeprefix('/api/classroom-media/')).resolve(): item
                    for item in prepared['release']['media']}
        remote_bytes = {path: path.read_bytes() for path in archived}
        for path in archived:
            path.unlink()
        remote = Mock()
        remote.read.side_effect = lambda target, **_expected: remote_bytes.get(target)
        self.service.course_media_store = remote
        replayed = self.prepare(assets)
        self.assertEqual(replayed['release']['sha256'], prepared['release']['sha256'])
        self.assertFalse(any(path.exists() for path in archived))
        self.assertEqual((self.root / self.source_id / 'audio/tts1.wav').read_bytes(), self.audio)
        for call in remote.read.call_args_list:
            item = archived[call.args[0]]
            self.assertEqual(call.kwargs['expected_sha256'], item['sha256'])
            self.assertEqual(call.kwargs['expected_bytes'], item['byteSize'])
        remote.read.side_effect = CourseMediaStorageError('remote unavailable')
        with self.assertRaises(ApiError):
            self.prepare(assets)
        self.assertFalse(any(path.exists() for path in archived))
        self.repository.reserve_build.assert_not_called()

    def test_delivery_copy_is_archived_and_still_bound_to_the_reviewed_bytes(self):
        picture = b'reviewed-picture-fixture'
        self.service = TextbookPublicationService(self.preview, delivery_copy=lambda suffix, raw: {
            '.wav': ('.mp3', b'smaller-narration'), '.png': ('.webp', b'smaller-picture')}.get(suffix, (suffix, raw)))
        prepared = self.prepare({'picture.png': picture, 'lesson.mp4': mp4_bytes()})
        items = {item['mimeType']: item for item in prepared['release']['media']}
        for mime, delivered, reviewed in [('audio/mpeg', b'smaller-narration', self.audio), ('image/webp', b'smaller-picture', picture)]:
            item = items[mime]
            self.assertEqual((item['sha256'], item['byteSize'], item['sourceSha256']),
                             (hashlib.sha256(delivered).hexdigest(), len(delivered), hashlib.sha256(reviewed).hexdigest()))
            self.assertEqual((self.root / item['path'].split('/api/classroom-media/')[1]).read_bytes(), delivered)
        self.assertNotIn('sourceSha256', items['video/mp4'])
        scenes = prepared['release']['classroom']['scenes']
        self.assertEqual(scenes[0]['actions'][0]['audioUrl'], items['audio/mpeg']['path'])
        self.assertEqual(scenes[2]['content']['questions'][0]['questionAudioUrl'], items['audio/mpeg']['path'])
        self.assertIn(items['image/webp']['path'], scenes[1]['content']['html'])
        self.assertEqual(self.prepare({'picture.png': picture, 'lesson.mp4': mp4_bytes()})['release']['sha256'], prepared['release']['sha256'])
        # A copy made from other bytes than the audited narration is refused.
        self.audio = b'another-narration'
        with self.assertRaises(ApiError):
            self.prepare({'picture.png': picture})

    def test_compact_copy_keeps_the_original_when_it_cannot_help(self):
        from content.textbook_delivery_media import compact_copy
        self.assertEqual(compact_copy('.mp4', mp4_bytes()), ('.mp4', mp4_bytes()))
        self.assertEqual(compact_copy('.png', b'not a picture'), ('.png', b'not a picture'))
        from PIL import Image
        import io
        output = io.BytesIO()
        Image.effect_noise((256, 256), 60).convert('RGB').save(output, 'PNG')
        suffix, smaller = compact_copy('.png', output.getvalue())
        self.assertEqual(suffix, '.webp')
        self.assertLess(len(smaller), len(output.getvalue()))
        self.assertEqual(media_mime_type(suffix, smaller), 'image/webp')

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
