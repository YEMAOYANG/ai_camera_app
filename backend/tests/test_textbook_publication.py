"""Release integrity, private answers, and student authority boundaries."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, MagicMock, patch

from content.textbook_catalog import canonical, digest
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_release import INPUT_SCHEMA, RELEASE_SCHEMA, validate_release, public_classroom, grade_answers, check_questions
from core.errors import ApiError
from core.security import now_ms
from services.textbook_classroom_service import TextbookClassroomService


class CourseObjectiveProjectionTest(unittest.TestCase):
    def test_structured_goals_preserve_text_and_original_records(self):
        from services.textbook_publication_service import course_objective_texts
        goals = [{'id': 'listen-sit', 'objective': '听懂 Sit down! 并行动。'}, '理解 door 与 window。']
        original = deepcopy(goals)
        self.assertEqual(course_objective_texts(goals), ['听懂 Sit down! 并行动。', '理解 door 与 window。'])
        self.assertEqual(goals, original)
        for invalid in [[], {}, [None], [{'id': 'missing-text'}], [{'objective': []}], [' ']]:
            with self.assertRaises(ApiError):
                course_objective_texts(invalid)


class AuthoredNoQuizEvidenceTests(unittest.TestCase):
    def setUp(self):
        from services.textbook_publication_service import TextbookPublicationService
        self.preview = Mock()
        self.preview.runtime.base_url = 'http://127.0.0.1:3100'
        self.candidate = {'schemaVersion': 'mira.textbook.authoring-candidate.v1',
            'sha256': 'a' * 64, 'contractSha256': 'b' * 64,
            'verification': 'frozen_identity_and_artifact_integrity_only',
            'interactionPolicyVersion': 8, 'interactionPolicySha256': 'c' * 64,
            'wholeCourseQualityContractSha256': 'd' * 64}
        self.source = {'scenes': [{'type': 'interactive', 'id': 'scene-p2'}]}
        self.manifest = {'editionId': 'book', 'revisionId': 'directory'}
        self.original = {'authoring': {'stageId': 'stage-test', 'sessionId': 'session-test'},
            'previewPrompt': {'expectedQuestionCount': 0}, 'authoringCandidate': self.candidate}
        self.preview._operator_adoption_classroom.return_value = (self.source,
            {'jobSchema': 'mira.operator.workbench-authoring.v4', 'lockedAssessments': []})
        self.service = TextbookPublicationService(self.preview, course_media_store=Mock())

    def evidence(self):
        return self.service._authored_no_quiz_evidence(
            self.original, self.source, self.manifest, 'lesson', '/classrooms')

    def test_only_verified_empty_native_contract_is_accepted(self):
        with patch('content.textbook_authoring_candidate.validate_authoring_candidate', return_value=self.candidate):
            evidence = self.evidence()
            self.assertEqual(evidence['lockedAssessments'], [])
            for bad in [None, {}, {'jobSchema': 'legacy', 'lockedAssessments': []},
                        {'jobSchema': 'mira.operator.workbench-authoring.v4', 'lockedAssessments': [{'id': 'required'}]}]:
                self.preview._operator_adoption_classroom.return_value = (self.source, bad)
                with self.assertRaises(ApiError):
                    self.evidence()

    def test_changed_candidate_and_added_quiz_are_rejected(self):
        with patch('content.textbook_authoring_candidate.validate_authoring_candidate', return_value={**self.candidate, 'sha256': 'e' * 64}):
            with self.assertRaises(ApiError):
                self.evidence()
        with patch('content.textbook_authoring_candidate.validate_authoring_candidate', return_value=self.candidate):
            self.source['scenes'].append({'type': 'quiz'})
            with self.assertRaises(ApiError):
                self.evidence()

    def test_existing_paths_are_not_reclassified(self):
        for extra in [{'nativeRevisionSource': {'original': True}}, {'authoringCandidate': None},
                      {'previewPrompt': {'expectedQuestionCount': 3}}]:
            self.original.update(extra)
            self.assertIsNone(self.evidence())
        self.preview._operator_adoption_classroom.assert_not_called()

    def test_frozen_scene_types_are_rechecked_against_the_verified_author_plan(self):
        self.original['previewPrompt']['requiredSceneTypes'] = ['interactive']
        self.preview._operator_adoption_classroom.return_value = (self.source,
            {'jobSchema': 'mira.operator.workbench-authoring.v4', 'lockedAssessments': [],
             'pagePlan': [{'type': 'interactive'}]})
        with patch('content.textbook_authoring_candidate.validate_authoring_candidate', return_value=self.candidate):
            self.assertEqual(self.evidence()['lockedAssessments'], [])
            self.original['previewPrompt']['requiredSceneTypes'] = ['slide', 'interactive']
            with self.assertRaises(ApiError):
                self.evidence()

    def test_release_evidence_binds_lesson_policy_source_and_quality(self):
        from content.textbook_release import validate_authored_no_quiz_evidence
        with patch('content.textbook_authoring_candidate.validate_authoring_candidate', return_value=self.candidate):
            evidence = self.evidence()
        quality = {'status': 'passed', 'policySha256': 'c' * 64, 'sourceSha256': 'f' * 64}
        frozen = {'authoredNoQuizEvidence': evidence, 'sourceSha256': 'f' * 64,
            'wholeCourseQualityReviewSha256': digest(quality),
            'textbookBinding': {'editionId': 'book', 'alignmentRevisionId': 'directory', 'nodeId': 'lesson'}}
        self.assertTrue(validate_authored_no_quiz_evidence(frozen, {'coursewareQuality': quality}))
        for field, value in [('lockedAssessments', [1]), ('expectedQuestionCount', False),
                             ('sourceInputSha256', 'invalid'), ('binding', {'nodeId': 'other'}),
                             ('authoring', {}), ('authoringCandidate', {})]:
            bad = deepcopy(frozen); bad['authoredNoQuizEvidence'][field] = value
            with self.assertRaises(ApiError, msg=field):
                validate_authored_no_quiz_evidence(bad, {'coursewareQuality': quality})
        for field in ('policySha256', 'sourceSha256', 'status'):
            with self.assertRaises(ApiError, msg=field):
                validate_authored_no_quiz_evidence(frozen, {'coursewareQuality': {**quality, field: 'different'}})


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
    def test_zero_quiz_release_validates_actual_binding_and_delivered_html(self):
        from content.textbook_course_interaction import build_contract, html_templates
        manifest, build, _ = fixture()
        manifest['editionId'] = 'pep-chinese-g1-upper-2022-standard'
        manifest['revisionId'] = '20260924-directory-3'
        manifest['units'][0]['lessons'][0]['nodeId'] = 'u5-l1'
        frozen = {'schemaVersion': INPUT_SCHEMA, 'previewKey': 'a' * 64, 'sourceSha256': 'b' * 64,
            'gradeCode': 'primary_1', 'subject': 'chinese', 'knowledgeBrief': {'status': 'draft'},
            'textbookBinding': {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
                'alignmentManifestSha256': digest(manifest), 'nodeId': 'u5-l1', 'partIndex': 1, 'teachingRevision': '6'},
            'audioContract': {'previewKey': 'a' * 64, 'schemaVersion': 'ordinary'},
            'partialAudioParent': {}, 'zeroNativeQuiz': True}
        binding = {'editionId': manifest['editionId'], 'revisionId': manifest['revisionId'], 'nodeId': 'u5-l1'}
        source_room = {'scenes': [
            {'id': 'intro', 'order': 1, 'type': 'slide', 'actions': []}] + [
            {'id': f'scene-p{i}', 'order': i, 'type': 'interactive', 'actions': [],
             'content': {'html': f'<img src="/api/classroom-media/source/media/p{i}.png">'}}
            for i in range(2, 13)]}
        frozen['interactionCompletionTemplates'] = {
            'schemaVersion': 'mira.textbook.interaction-delivery-templates.v1',
            'scenes': html_templates(source_room, binding, lambda _: 'd' * 64),
            'assets': [{'sourceSha256': 'd' * 64, 'deliverySha256': 'e' * 64,
                        'mimeType': 'image/png', 'byteSize': 10}]}
        key = digest(frozen)
        frozen['contentKey'] = key
        cid = 'tbpub_' + key[:24]
        room = {'id': cid, 'stage': {'id': cid, 'name': '秋天'}, 'scenes': [
            {'id': 'intro', 'order': 1, 'type': 'slide', 'actions': []}] + [
            {'id': f'scene-p{i}', 'order': i, 'type': 'interactive', 'actions': [],
             'content': {'html': f'<img src="/api/classroom-media/{cid}/media/p{i}.png">'}}
            for i in range(2, 13)]}
        source = {'previewPrompt': {'expectedQuestionCount': 0}, 'authoringCandidate': {'contractSha256': 'c' * 64}}
        release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': key, 'classroomId': cid, 'classroom': room,
            'classroomSha256': digest(room), 'media': [
                {'path': f'/api/classroom-media/{cid}/media/p{i}.png', 'sha256': 'e' * 64,
                 'sourceSha256': 'd' * 64, 'mimeType': 'image/png', 'byteSize': 10}
                for i in range(2, 13)], 'textbookBinding': binding,
            'interactionCompletionContract': build_contract(room, binding),
            'assessmentPolicy': 'verified-frozen-no-native-quiz', 'audioAudit': {'passed': True, 'segments': 0,
                'contract': {'identity': 'test'}, 'partialAudioEvidence': {'sourceInput': source, 'targetInput': source}}}
        release['sha256'] = digest(release)
        review = {'reviewer': 'test', 'basis': 'isolated', 'alignmentConfirmed': True,
            'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True, 'publicationAuthorized': True,
            'release': release}
        build.update(content_key=key, node_id='u5-l1', teaching_revision='6',
                     input_json=canonical(frozen), review_json=canonical(review))
        with patch('content.textbook_preview_audio_contract.resolve_audio_contract', return_value={'legacy': False}), \
             patch('content.textbook_preview_audio_contract.audit_contract_identity', return_value={'identity': 'test'}), \
             patch('content.textbook_partial_audio_inheritance.validate_partial_release', return_value={}):
            self.assertEqual(validate_release(build, manifest), release)
            for mutate in ('missing', 'html', 'binding', 'rehashed_html', 'asset_provenance'):
                bad = deepcopy(review)
                changed = bad['release']
                if mutate == 'missing': changed['classroom']['scenes'].pop()
                elif mutate == 'html': changed['classroom']['scenes'][1]['content']['html'] += 'changed'
                elif mutate == 'binding': changed['textbookBinding']['nodeId'] = 'other'
                elif mutate == 'rehashed_html':
                    changed['classroom']['scenes'][1]['content']['html'] += 'changed'
                    changed['interactionCompletionContract'] = build_contract(changed['classroom'], changed['textbookBinding'])
                else:
                    changed['media'][0]['sha256'] = 'f' * 64
                changed['classroomSha256'] = digest(changed['classroom'])
                changed.pop('sha256')
                changed['sha256'] = digest(changed)
                with self.assertRaises(ApiError, msg=mutate):
                    validate_release({**build, 'review_json': canonical(bad)}, manifest)

    def test_interaction_contract_cannot_be_added_to_ordinary_or_legacy_release(self):
        manifest, build, _ = fixture()
        review = __import__('json').loads(build['review_json'])
        review['release']['interactionCompletionContract'] = {'schemaVersion': 'forged'}
        review['release'].pop('sha256')
        review['release']['sha256'] = digest(review['release'])
        with self.assertRaises(ApiError):
            validate_release({**build, 'review_json': canonical(review)}, manifest)

    def test_zero_quiz_marker_without_audio_provenance_is_rejected(self):
        manifest, build, _ = fixture()
        frozen = __import__('json').loads(build['input_json'])
        review = __import__('json').loads(build['review_json'])
        frozen.pop('contentKey')
        frozen['zeroNativeQuiz'] = True
        key = digest(frozen)
        frozen['contentKey'] = key
        release = review['release']
        classroom_id = 'tbpub_' + key[:24]
        release.update(contentKey=key, classroomId=classroom_id)
        release['classroom']['id'] = release['classroom']['stage']['id'] = classroom_id
        release['classroomSha256'] = digest(release['classroom'])
        release.pop('sha256')
        release['sha256'] = digest(release)
        with self.assertRaises(ApiError):
            validate_release({**build, 'content_key': key, 'input_json': canonical(frozen),
                              'review_json': canonical(review)}, manifest)

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

    def test_whole_course_quality_review_digest_is_immutable_after_publication(self):
        manifest, build, _ = fixture()
        frozen = __import__('json').loads(build['input_json'])
        review = __import__('json').loads(build['review_json'])
        quality = {'schemaVersion': 'mira.textbook.whole-course-quality-review.v1',
                   'status': 'passed', 'evidence': ['Synthetic immutable fixture.']}
        frozen.pop('contentKey')
        frozen['wholeCourseQualityReviewSha256'] = digest(quality)
        key = digest(frozen)
        frozen['contentKey'] = key
        release = review['release']
        classroom_id = 'tbpub_' + key[:24]
        release.update(contentKey=key, classroomId=classroom_id)
        release['classroom']['id'] = classroom_id
        release['classroom']['stage']['id'] = classroom_id
        release['classroom']['scenes'][0]['content']['questions'][0]['questionAudioUrl'] = (
            f'/api/classroom-media/{classroom_id}/audio/one.wav')
        release['classroomSha256'] = digest(release['classroom'])
        release.pop('sha256')
        release['sha256'] = digest(release)
        review['coursewareQuality'] = quality
        build.update(content_key=key, input_json=canonical(frozen), review_json=canonical(review))
        self.assertEqual(validate_release(build, manifest), release)

        review['coursewareQuality']['status'] = 'changed-after-publication'
        with self.assertRaises(ApiError):
            validate_release({**build, 'review_json': canonical(review)}, manifest)

    def test_complete_scene_followup_keeps_policy_quality_and_revision_trace_bound(self):
        manifest, build, _ = fixture()
        frozen = __import__('json').loads(build['input_json'])
        review = __import__('json').loads(build['review_json'])
        current = freeze_interaction_policy()
        followup_body = {'schemaVersion': 'mira.textbook.complete-scene-review-followup.v1',
            'status': 'quality_review_required',
            'verification': 'sealed_complete_scene_revision_chain_and_current_candidate',
            'sessionId': 'session-review', 'stageId': 'stage-review',
            'baseInteractionPolicyVersion': 1, 'baseInteractionPolicySha256': '1' * 64,
            'currentInteractionPolicyVersion': current['policy']['version'],
            'currentInteractionPolicySha256': current['sha256'],
            'wholeCourseQualityContractSha256': digest(current['policy']['wholeCourseQualityContract']),
            'candidateSourceSha256': '2' * 64, 'candidateSha256': '3' * 64,
            'candidateFileSha256': '4' * 64, 'revisionIds': ['5' * 64],
            'revisionReceiptSha256s': ['6' * 64], 'completeSceneIds': ['interactive']}
        followup = {**followup_body, 'sha256': digest(followup_body)}
        quality = {'schemaVersion': 'mira.textbook.whole-course-quality-review.v1',
            'status': 'passed', 'policySha256': current['sha256'],
            'sourceSha256': frozen['sourceSha256']}
        frozen.pop('contentKey')
        frozen.update(completeSceneReviewFollowup=followup, authoringSourceSha256='2' * 64,
                      wholeCourseQualityReviewSha256=digest(quality))
        key = digest(frozen)
        frozen['contentKey'] = key
        release = review['release']
        classroom_id = 'tbpub_' + key[:24]
        release.update(contentKey=key, classroomId=classroom_id)
        release['classroom']['id'] = classroom_id
        release['classroom']['stage']['id'] = classroom_id
        release['classroom']['scenes'][0]['content']['questions'][0]['questionAudioUrl'] = (
            f'/api/classroom-media/{classroom_id}/audio/one.wav')
        release['classroomSha256'] = digest(release['classroom'])
        release.pop('sha256')
        release['sha256'] = digest(release)
        review['coursewareQuality'] = quality
        build.update(content_key=key, input_json=canonical(frozen), review_json=canonical(review))
        self.assertEqual(validate_release(build, manifest), release)

        changed_quality = deepcopy(quality)
        changed_quality['policySha256'] = '7' * 64
        changed_frozen = deepcopy(frozen)
        changed_frozen.pop('contentKey')
        changed_frozen['wholeCourseQualityReviewSha256'] = digest(changed_quality)
        changed_key = digest(changed_frozen)
        changed_frozen['contentKey'] = changed_key
        changed_review = deepcopy(review)
        changed_review['coursewareQuality'] = changed_quality
        changed_release = changed_review['release']
        changed_id = 'tbpub_' + changed_key[:24]
        changed_release.update(contentKey=changed_key, classroomId=changed_id)
        changed_release['classroom']['id'] = changed_id
        changed_release['classroom']['stage']['id'] = changed_id
        changed_release['classroom']['scenes'][0]['content']['questions'][0]['questionAudioUrl'] = (
            f'/api/classroom-media/{changed_id}/audio/one.wav')
        changed_release['classroomSha256'] = digest(changed_release['classroom'])
        changed_release.pop('sha256')
        changed_release['sha256'] = digest(changed_release)
        changed_build = {**build, 'content_key': changed_key,
            'input_json': canonical(changed_frozen), 'review_json': canonical(changed_review)}
        with self.assertRaises(ApiError):
            validate_release(changed_build, manifest)

    def test_no_answers_or_private_prompt_in_student_snapshot(self):
        _, _, release = fixture()
        pictures = {'visual': {'kind': 'image', 'src': '/api/classroom-media/tbpub_x/media/one.png', 'alt': '天空'},
                    'optionVisuals': {'A': {'kind': 'quantity', 'count': 1}, 'B': {'kind': 'quantity', 'count': 2}}}
        release['classroom']['scenes'][0]['content']['questions'][0].update(pictures)
        public = public_classroom(release)
        question = public['scenes'][0]['content']['questions'][0]
        self.assertNotIn('answer', question)
        self.assertNotIn('analysis', question)
        self.assertEqual({key: question[key] for key in pictures}, pictures)
        self.assertNotIn('languageDirective', public['stage'])

    def test_verified_legacy_scene_stage_aliases_are_bound_only_in_public_projection(self):
        manifest, build, release = fixture()
        classroom_id = release['classroomId']
        scenes = release['classroom']['scenes']
        scenes[0]['stageId'] = 'tbrev_older_revision'
        scenes.extend([
            {'id': 'slide2', 'stageId': 'original-authoring-stage', 'type': 'slide', 'order': 2,
             'content': {'canvas': {'elements': [{'id': 'label', 'text': 'Unchanged lesson'}]}},
             'actions': [{'id': 'speech2', 'type': 'speech', 'text': 'Unchanged narration',
                          'audioId': 'audited-audio', 'audioUrl': f'/api/classroom-media/{classroom_id}/audio/two.wav'}]},
            {'id': 'game3', 'type': 'interactive', 'order': 3,
             'content': {'html': '<button>Unchanged activity</button>'}, 'actions': []},
        ])
        release['audioAudit']['segments'] = 2
        release['classroomSha256'] = digest(release['classroom'])
        release['sha256'] = digest({k: v for k, v in release.items() if k != 'sha256'})
        review = __import__('json').loads(build['review_json'])
        review['release'] = release
        build['review_json'] = canonical(review)
        original = deepcopy(release)
        original_build = deepcopy(build)

        verified = validate_release(build, manifest)
        public = public_classroom(verified)

        self.assertEqual(public['stage']['id'], classroom_id)
        self.assertEqual([s['stageId'] for s in public['scenes']], [classroom_id] * 3)
        self.assertEqual([(s['id'], s['order']) for s in public['scenes']],
                         [(s['id'], s['order']) for s in scenes])
        for source, delivered in zip(scenes, public['scenes']):
            self.assertEqual(delivered['actions'], source['actions'])
            if source['type'] != 'quiz':
                self.assertEqual({k: v for k, v in delivered.items() if k != 'stageId'},
                                 {k: v for k, v in source.items() if k != 'stageId'})
        self.assertNotIn('answer', public['scenes'][0]['content']['questions'][0])
        self.assertEqual(release, original)
        self.assertEqual(build, original_build)
        self.assertEqual(validate_release(build, manifest), original)

    def test_selected_option_feedback_stays_private_until_grading(self):
        _, _, release = fixture()
        question = release['classroom']['scenes'][0]['content']['questions'][0]
        question['optionFeedback'] = {
            'A': {'text': '你把天空和天字连起来了。', 'visual': {
                'kind': 'image', 'src': '/api/classroom-media/tbpub_x/media/feedback-a.png', 'alt': '天空连到天字'}},
            'B': {'text': '你选了大地，再看看天空。', 'visual': {
                'kind': 'image', 'src': '/api/classroom-media/tbpub_x/media/feedback-b.png', 'alt': '大地旁有天空提示'}},
        }
        public = public_classroom(release)
        self.assertNotIn('optionFeedback', public['scenes'][0]['content']['questions'][0])
        result = grade_answers(release, {'q1': 'B'})['results'][0]
        self.assertEqual(result['feedback'], question['optionFeedback']['B'])
        self.assertNotEqual(result['feedback'], question['optionFeedback']['A'])

    def test_option_feedback_requires_every_option_and_matching_audio_binding(self):
        _, _, release = fixture()
        question = release['classroom']['scenes'][0]['content']['questions'][0]
        question['optionFeedback'] = {'A': {'text': '反馈', 'visual': {
            'kind': 'image', 'src': '/api/classroom-media/tbpub_x/media/a.png', 'alt': '反馈图'}}}
        with self.assertRaises(ApiError):
            check_questions(release['classroom'])
        question['optionFeedback'] = {value: {'text': f'{value}反馈', 'visual': {
            'kind': 'image', 'src': f'/api/classroom-media/tbpub_x/media/{value}.png', 'alt': f'{value}反馈图'},
            'audioUrl': f'/api/classroom-media/tbpub_x/audio/{value}.wav', 'audioBinding': {
                'schemaVersion': 'mira.learning.quiz-feedback-audio-binding.v1', 'sceneId': 'quiz1',
                'questionId': 'q1', 'optionValue': value, 'ttsRequestId': f'tts-{value}',
                'sourceTextSha256': '0' * 64}} for value in ('A', 'B')}
        self.assertEqual(check_questions(release['classroom']), [question])
        question['optionFeedback']['B']['audioBinding']['optionValue'] = 'A'
        with self.assertRaises(ApiError):
            check_questions(release['classroom'])
        self.assertEqual(release['classroom']['scenes'][0]['content']['questions'][0]['answer'], ['A'])

    def test_option_feedback_accepts_bound_person_relationships(self):
        _, _, release = fixture()
        question = release['classroom']['scenes'][0]['content']['questions'][0]
        question['optionFeedback'] = {value: {'text': f'{value}人物关系反馈', 'visual': {
            'kind': 'relationship', 'alt': 'Alex把问候说给Lily听',
            'actors': [
                {'id': 'alex', 'src': '/api/classroom-media/tbpub_x/media/alex.png', 'alt': 'Alex说话', 'cue': 'speaking'},
                {'id': 'lily', 'src': '/api/classroom-media/tbpub_x/media/lily.png', 'alt': 'Lily倾听', 'cue': 'listening'}],
            'links': [{'fromId': 'alex', 'toId': 'lily', 'kind': 'speaks-to'}]}} for value in ('A', 'B')}
        self.assertEqual(check_questions(release['classroom']), [question])
        question['optionFeedback']['B']['visual']['links'][0]['toId'] = 'ben'
        with self.assertRaises(ApiError):
            check_questions(release['classroom'])

    def test_session_roster_uses_authoritative_subject_and_child_without_mutating_release(self):
        _, build, release = fixture()
        original = deepcopy(release)
        service = object.__new__(TextbookClassroomService)
        service.repository = Mock()
        service.repository.parse.side_effect = __import__('json').loads
        service._authority = Mock(return_value=(None, {'name': '小朋友', 'nickname': '小芽'}, build, release, None, None))
        service._playback_release = Mock(side_effect=deepcopy)
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

    def test_workbench_lesson_with_its_own_classmates_sits_with_the_built_in_classmates(self):
        from content.textbook_classroom import classroom_roster
        _, build, release = fixture()
        frozen = __import__('json').loads(build['input_json'])
        release['classroom']['stage']['agentIds'] = ['gen-teacher', 'gen-doudou', 'gen-xiaoman']
        ids, agents = classroom_roster(frozen, release)
        self.assertEqual(ids[1:], ['default-' + str(i) for i in range(2, 7)])
        self.assertEqual([agent['role'] for agent in agents], ['teacher'])
        release['classroom']['stage']['agentIds'] = ['gen-teacher', 'default-3']
        self.assertEqual(classroom_roster(frozen, release)[0][1:], ['default-3'])

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

    def test_native_single_choice_key_forms_preserve_full_value_and_source(self):
        for key in ('choice-two', ['choice-two']):
            with self.subTest(key=key):
                _, _, release = fixture()
                question = release['classroom']['scenes'][0]['content']['questions'][0]
                question['options'] = [{'value': 'choice-one', 'label': 'one'},
                                       {'value': 'choice-two', 'label': 'two'}]
                question['answer'] = key
                before = deepcopy(release)
                self.assertEqual(grade_answers(release, {'q1': 'choice-two'})['score'], 5)
                wrong = grade_answers(release, {'q1': 'choice-one'})
                self.assertEqual(wrong['score'], 0)
                self.assertEqual(wrong['results'][0]['correctAnswer'], 'choice-two')
                self.assertNotIn('answer', public_classroom(release)['scenes'][0]['content']['questions'][0])
                self.assertEqual(release, before)

    def test_native_answer_compatibility_keeps_unique_answer_and_audio_gates(self):
        for key in (None, '', ' ', [], ['A', 'B'], [['A']], [None], 1, {'answer': 'A'}, 'AB', 'Z'):
            with self.subTest(key=key):
                _, _, release = fixture()
                release['classroom']['scenes'][0]['content']['questions'][0]['answer'] = key
                with self.assertRaises(ApiError):
                    check_questions(release['classroom'])
        for field in ('questionAudioUrl', 'analysis'):
            _, _, release = fixture()
            question = release['classroom']['scenes'][0]['content']['questions'][0]
            question['answer'] = 'A'
            question[field] = ''
            with self.assertRaises(ApiError):
                check_questions(release['classroom'])

    def test_in_class_checks_are_graded_one_page_at_a_time_and_add_up_to_one_result(self):
        _, build, release = fixture()
        second = deepcopy(release['classroom']['scenes'][0])
        second.update(id='quiz2', order=2, actions=[{'id': 'a2', 'type': 'speech', 'text': '地'}])
        second['content']['questions'][0].update(id='q2', question='大地是哪一个字？', answer=['B'], analysis='地，大地的地。')
        release['classroom']['scenes'].append(second)
        self.assertEqual([r['questionId'] for r in grade_answers(release, {'q2': 'B'}, partial=True)['results']], ['q2'])
        for payload, partial in (({'q1': 'A'}, False), ({}, True), ({'q3': 'A'}, True), ({'q1': 'D'}, True)):
            with self.assertRaises(ApiError):
                grade_answers(release, payload, partial=partial)
        service = object.__new__(TextbookClassroomService)
        service.repository = MagicMock()
        conn = service.repository.transaction.return_value.__enter__.return_value
        service.learning = Mock()
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': None, 'task_id': 'task'}
        service.learning.get_session.return_value = session
        service._report = Mock()
        service._authority = Mock(return_value=(None, {'family_id': 'family', 'id': 'child'}, build, release, {'id': 'course'}, session))
        def saved():
            update = [call.args[1] for call in conn.execute.call_args_list if call.args[0].startswith('UPDATE learning_sessions')][-1]
            return update[0]
        first = service.quiz('runtime', {'q1': 'B'})
        self.assertIsNone(first['result'])
        self.assertEqual([(r['questionId'], r['correct']) for r in first['partial']['results']], [('q1', False)])
        service._report.assert_not_called()
        session['runtime_state_json'] = saved()
        self.assertEqual(service.quiz('runtime')['partial'], first['partial'])
        self.assertEqual(service._status(session, release)['answeredQuestionIds'], ['q1'])
        with self.assertRaises(ApiError):
            service.quiz('runtime', {'q1': 'A'})
        done = service.quiz('runtime', {'q2': 'B'})
        self.assertEqual((done['result']['correctCount'], done['result']['totalQuestions'], done['partial']), (1, 2, None))
        self.assertEqual([r['questionId'] for r in done['result']['results']], ['q1', 'q2'])
        service._report.assert_called_once()
        session['runtime_state_json'] = saved()
        self.assertEqual(service.quiz('runtime', {'q2': 'B'})['result'], done['result'])
        with self.assertRaises(ApiError):
            service.quiz('runtime', {'q2': 'A'})
        service._report.assert_called_once()

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
