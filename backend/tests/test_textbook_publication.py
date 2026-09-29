"""Release integrity, private answers, and student authority boundaries."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, MagicMock

from content.textbook_catalog import canonical, digest
from content.textbook_release import INPUT_SCHEMA, RELEASE_SCHEMA, validate_release, public_classroom, grade_answers
from core.errors import ApiError
from core.security import now_ms
from services.textbook_classroom_service import TextbookClassroomService


def fixture():
    node = {'nodeId': 'u1-l1', 'brief': {'status': 'draft'}}
    manifest = {'editionId': 'book', 'revisionId': 'directory', 'gradeCode': 'primary_1',
                'units': [{'lessons': [node]}]}
    frozen = {'schemaVersion': INPUT_SCHEMA, 'previewKey': 'a' * 64, 'sourceSha256': 'b' * 64,
              'gradeCode': 'primary_1', 'subject': 'chinese', 'knowledgeBrief': node['brief'],
              'textbookBinding': {'editionId': 'book', 'alignmentRevisionId': 'directory',
                  'alignmentManifestSha256': digest(manifest), 'nodeId': 'u1-l1', 'partIndex': 1,
                  'teachingRevision': '1'}}
    key = digest(frozen)
    frozen['contentKey'] = key
    classroom_id = 'tbpub_' + key[:24]
    classroom = {'id': classroom_id, 'stage': {'id': classroom_id, 'name': '天地人', 'languageDirective': 'private'},
        'scenes': [{'id': 'quiz1', 'type': 'quiz', 'order': 1, 'actions': [{'id': 'a1', 'type': 'speech', 'text': '天'}],
            'content': {'questions': [{'id': 'q1', 'type': 'single', 'question': '天空是哪一个字？',
                'options': [{'value': 'A', 'label': '天'}, {'value': 'B', 'label': '地'}], 'answer': ['A'],
                'analysis': '天，天空的天。', 'points': 5,
                'questionAudioUrl': f'/api/classroom-media/{classroom_id}/audio/one.wav'}]}}]}
    release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': key, 'classroomId': classroom_id,
        'classroom': classroom, 'classroomSha256': digest(classroom),
        'media': [{'path': '/one.wav'}], 'audioAudit': {'passed': True, 'segments': 1}}
    release['sha256'] = digest(release)
    review = {'reviewer': 'test', 'basis': 'original', 'alignmentConfirmed': True,
              'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True, 'publicationAuthorized': True,
              'release': release}
    build = {'status': 'published', 'content_key': key, 'node_id': 'u1-l1', 'part_index': 1,
             'teaching_revision': '1', 'input_json': canonical(frozen), 'review_json': canonical(review),
             'course_id': 'course', 'course_version': '1', 'course_content_sha256': digest({'title': '天地人'})}
    return manifest, build, release


class ReleaseTests(unittest.TestCase):
    def test_valid_review_is_for_one_exact_directory_lesson(self):
        manifest, build, release = fixture()
        self.assertEqual(validate_release(build, manifest), release)
        changed = deepcopy(manifest)
        changed['revisionId'] = 'other'
        with self.assertRaises(ApiError):
            validate_release(build, changed)

    def test_withdrawal_changed_course_and_changed_snapshot_are_rejected(self):
        manifest, build, _ = fixture()
        for changed in ({**build, 'status': 'retired'}, {**build, 'content_key': 'c' * 64}):
            with self.assertRaises(ApiError):
                validate_release(changed, manifest)
        with self.assertRaises(ApiError):
            validate_release(build, manifest, {'id': 'course', 'version': '1', 'status': 'published',
                'quality_status': 'released', 'content_json': canonical({'title': 'changed'})})
        review = __import__('json').loads(build['review_json'])
        review['release']['classroom']['scenes'][0]['content']['questions'][0]['answer'] = ['B']
        with self.assertRaises(ApiError):
            validate_release({**build, 'review_json': canonical(review)}, manifest)

    def test_no_answers_or_private_prompt_in_student_snapshot(self):
        _, _, release = fixture()
        public = public_classroom(release)
        question = public['scenes'][0]['content']['questions'][0]
        self.assertNotIn('answer', question)
        self.assertNotIn('analysis', question)
        self.assertNotIn('languageDirective', public['stage'])
        self.assertEqual(release['classroom']['scenes'][0]['content']['questions'][0]['answer'], ['A'])

    def test_session_roster_uses_authoritative_subject_and_child_without_mutating_release(self):
        _, build, release = fixture()
        original = deepcopy(release)
        service = object.__new__(TextbookClassroomService)
        service.repository = Mock()
        service.repository.parse.side_effect = __import__('json').loads
        service._authority = Mock(return_value=(None, {'name': '小朋友', 'nickname': '小芽'}, build, release, None, None))
        for subject, teacher_name in [('chinese', '小语老师'), ('math', '小数老师'), ('english', 'Mia 老师')]:
            frozen = __import__('json').loads(build['input_json'])
            build['input_json'] = canonical({**frozen, 'subject': subject})
            classroom = service.classroom('runtime')['classroom']
            teacher = classroom['stage']['generatedAgentConfigs'][0]
            self.assertEqual(teacher['name'], teacher_name)
            self.assertEqual(classroom['stage']['agentIds'], [teacher['id'], *['default-' + str(i) for i in range(2, 7)]])
            self.assertEqual(teacher['persona'], '')
            self.assertEqual(classroom['stage']['miraStudent'], {'name': '小芽', 'avatar': '/avatars/user.png'})
            self.assertNotIn('answer', classroom['scenes'][0]['content']['questions'][0])
        self.assertEqual(release, original)

    def test_fixed_lesson_discussion_keeps_classmates_and_uses_the_frozen_content(self):
        from content.textbook_classroom import discussion_request
        _, build, release = fixture()
        frozen = __import__('json').loads(build['input_json'])
        body = {'messages': [{'role': 'user', 'parts': [{'type': 'text', 'text': '我们一起说一说天空吧'}]}],
            'config': {'agentIds': ['evil'], 'agentConfigs': [{'id': 'evil'}], 'sessionType': 'qa'},
            'storeState': {'stage': {'id': release['classroomId']}, 'scenes': [{'id': 'forged'}],
                           'currentSceneId': 'quiz1', 'whiteboardOpen': True}}
        request = discussion_request(frozen, release, body)
        self.assertEqual(request['messages'], body['messages'])
        self.assertEqual(len(request['config']['agentIds']), 6)
        self.assertEqual(request['config']['agentConfigs'][0]['name'], '小语老师')
        self.assertIn('wb_open', request['config']['agentConfigs'][0]['allowedActions'])
        self.assertEqual(request['storeState']['scenes'][0]['id'], 'quiz1')
        self.assertNotIn('answer', request['storeState']['scenes'][0]['content']['questions'][0])
        for invalid in ({'stage': {'id': 'other'}, 'currentSceneId': 'quiz1'},
                        {'stage': {'id': release['classroomId']}, 'currentSceneId': 'other'}):
            with self.assertRaises(ApiError):
                discussion_request(frozen, release, {**body, 'storeState': invalid})

    def test_interaction_uses_existing_teaching_authority_and_never_allows_course_generation(self):
        _, build, release = fixture()
        service = object.__new__(TextbookClassroomService)
        service.repository = Mock()
        service.repository.parse.side_effect = __import__('json').loads
        service.budget_service = Mock()
        service._authority = Mock(return_value=(None, {'id': 'child'}, build, release,
                                                {'id': 'course', 'version': '1'}, {'id': 'session'}))
        binding = {'schemaVersion': 'mira.learning.paid-budget-binding.v1', 'authorizationId': 'a' * 64, 'required': True}
        service.budget_service.issue_course_authorization.return_value = binding
        for path in ['/api/generate/tts', '/api/transcription']:
            result = service.admit_interaction('runtime', {'path': path, 'request': {}})
            self.assertEqual(result['paidBudget'], binding)
            scope = service.budget_service.issue_course_authorization.call_args.kwargs['scope']
            self.assertEqual((scope['courseId'], scope['userId'], scope['sessionId']), ('course', 'child', 'session'))
            self.assertEqual(scope['approvalReference'], release['sha256'])
        for path in ['/api/generate-classroom', '/api/classroom', '/api/quiz-grade']:
            with self.assertRaises(ApiError):
                service.admit_interaction('runtime', {'path': path, 'request': {}})
        service._authority.side_effect = ApiError('textbook_session_invalid', 'expired', 401)
        with self.assertRaises(ApiError):
            service.admit_interaction('revoked', {'path': '/api/transcription', 'request': {}})

    def test_voice_turn_is_persisted_without_marking_any_answer_or_lesson_complete(self):
        _, build, release = fixture()
        service = object.__new__(TextbookClassroomService)
        service.repository = MagicMock()
        conn = service.repository.transaction.return_value.__enter__.return_value
        conn.execute.return_value.fetchone.return_value = None
        service.learning = Mock()
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': None}
        service.learning.get_session.return_value = session
        service._authority = Mock(return_value=(None, {'family_id': 'family'}, build, release, {}, session))
        event = {'schemaVersion': 'mira.openmaic.student-runtime-event.v1', 'sequence': 1,
            'type': 'asr_transcribed', 'payload': {'sceneIndex': 0, 'sceneId': 'quiz1',
                                                'turnId': 'voice-1', 'transcript': '天空里有白云'}}
        self.assertFalse(service.events('runtime', event)['completed'])
        update = next(call.args[1] for call in conn.execute.call_args_list if call.args[0].startswith('UPDATE learning_sessions'))
        state = __import__('json').loads(update[0])
        self.assertEqual((state['visited'], state['actions'], state['quiz']), ([], [], None))
        for payload in ({**event['payload'], 'transcript': ''}, {**event['payload'], 'score': 100}):
            with self.assertRaises(ApiError):
                service.events('runtime', {**event, 'payload': payload})

    def test_only_server_answers_determine_the_score(self):
        _, _, release = fixture()
        self.assertEqual(grade_answers(release, {'q1': 'A'})['score'], 5)
        self.assertEqual(grade_answers(release, {'q1': 'B'})['score'], 0)
        for payload in ({'q1': 'D'}, {'q1': 'A', 'score': 100}, {}, {'q1': ['A']}):
            with self.assertRaises(ApiError):
                grade_answers(release, payload)

    def test_interactive_queued_audio_uses_archived_speech_identity(self):
        _, _, release = fixture()
        aliases = ['speaker-teal', 'speaker-coral', 'cue-me', 'cue-you', 'cue-he']
        scene = {'type': 'interactive', 'content': {'html': "player.src='/api/classroom-media/preview/audio/'+queue.shift()+'.wav';player.play()"},
                 'actions': [{'id': 'review_' + alias, 'type': 'speech', 'audioUrl': '/archived/' + alias + '.wav'} for alias in aliases]}
        release['classroom']['scenes'].append(scene)
        release['media'] = [{'path': a['audioUrl'], 'mimeType': 'audio/wav'} for a in scene['actions']]
        html = public_classroom(release)['scenes'][-1]['content']['html']
        self.assertNotIn('/api/classroom-media/preview/', html)
        self.assertIn('/archived/cue-me.wav', html)
        self.assertIn('/api/classroom-media/preview/', scene['content']['html'])
        release['media'].pop()
        with self.assertRaises(ApiError):
            public_classroom(release)

    def test_opening_a_page_does_not_count_as_completed_narration(self):
        _, _, release = fixture()
        state = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 2,
                 'visited': ['quiz1'], 'actions': [], 'quiz': grade_answers(release, {'q1': 'A'})}
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': canonical(state)}
        self.assertFalse(TextbookClassroomService._status(session, release)['completionReady'])
        self.assertEqual(TextbookClassroomService._status(session, release)['completedActionSceneIds'], [])
        state['actions'] = ['a1']
        session['runtime_state_json'] = canonical(state)
        self.assertTrue(TextbookClassroomService._status(session, release)['completionReady'])

    def test_preview_without_publication_contract_is_never_admitted(self):
        manifest, build, _ = fixture()
        self.assertIsNone(validate_release({**build, 'input_json': '{}'}, manifest))
        review = __import__('json').loads(build['review_json'])
        review['publicationAuthorized'] = False
        with self.assertRaises(ApiError):
            validate_release({**build, 'review_json': canonical(review)}, manifest)

    def test_signed_runtime_cannot_use_ticket_or_other_student_session(self):
        repository = Mock()
        conn = Mock()
        repository.transaction.return_value.__enter__ = Mock(return_value=conn)
        repository.transaction.return_value.__exit__ = Mock(return_value=None)
        auth = Mock()
        service = TextbookClassroomService(repository, student_auth=auth,
            signing_key='test-signing-secret-only', public_url='https://runtime.test')
        with self.assertRaises(ApiError):
            service._authority('tbpr_modified')
        with self.assertRaises(ApiError):
            service._authority('tbpr_' + service.signer.dumps({'purpose': 'ticket'}))
        auth.repository.get_session.return_value = {'revoked_at': now_ms(), 'refresh_expires_at': now_ms() + 100000}
        with self.assertRaises(ApiError):
            service._authority('tbpr_' + service.signer.dumps({'purpose': 'runtime', 'studentSession': 'revoked'}))


if __name__ == '__main__':
    unittest.main()
