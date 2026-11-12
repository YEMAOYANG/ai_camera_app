"""Light release evidence, byte identity and unchanged student validation."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from content.courseware_release import AUDIO_METHOD, WAIVER_LIGHT_SCHEMA, build_release, validate_light_release
from content.textbook_catalog import canonical, digest
from content.textbook_release import validate_release


def sample_inputs():
    audio = b'RIFF' + b'\x00' * 4 + b'WAVEfmt ' + b'\x00' * 28
    picture = b'\x89PNG\r\n\x1a\n' + b'original synthetic picture'
    audio_name = hashlib.sha256(audio).hexdigest() + '.wav'
    image_name = hashlib.sha256(picture).hexdigest() + '.png'
    audio_url = '/api/classroom-media/authored/media/' + audio_name
    image_url = '/api/classroom-media/authored/media/' + image_name
    brief = {'status': 'approved', 'objectives': ['Compare pictured quantities'],
        'knowledgePoints': ['quantity'], 'priorKnowledge': [], 'excludedTopics': [],
        'assessmentMode': 'objective', 'reviewNote': 'Synthetic fixture only'}
    manifest = {'editionId': 'synthetic-book', 'revisionId': 'synthetic-revision',
        'gradeCode': 'primary_1', 'subject': 'math', 'rightsReview': {'status': 'cleared'},
        'units': [{'unitId': 'unit', 'title': 'Unit', 'lessons': [{'nodeId': 'lesson', 'brief': brief}]}]}
    body = {'id': 'authored', 'stage': {'id': 'authored', 'name': 'Pictured quantities', 'createdAt': 1793608977483,
        'generatedAgentConfigs': [{'name': 'teacher', 'voiceConfig': {'voiceId': 'Ethan'}}]},
        'scenes': [{'id': 'slide', 'stageId': 'authored', 'type': 'slide',
            'content': {'canvas': {'elements': []}}, 'actions': [
                {'id': 'speech-%d' % i, 'type': 'speech',
                 'text': text, 'audioUrl': audio_url} for i, text in enumerate((
                    '先看左边的三个物品，点一个数一个。',
                    '最后数到三，就表示左边一共有三个。',
                    '再看右边的两个物品，也逐个数清楚。',
                    '最后数到二，就表示右边一共有两个。',
                    '三比二多，所以左边的数量比右边多。',
                    '比较数量时，先数清两边，再比较多少。'), 1)]},
            {'id': 'quiz', 'stageId': 'authored', 'type': 'quiz', 'actions': [], 'content': {'questions': [
                {'id': 'question-%d' % i, 'type': 'single', 'question': '哪边更多？',
                 'options': [{'value': 'A', 'label': '左边'}, {'value': 'B', 'label': '右边'}],
                 'answer': ['A' if i == 1 else 'B'], 'analysis': '逐个数清两边，再比较数量。', 'skill': 'quantity',
                 'questionAudioUrl': audio_url, 'optionVisuals': {
                     'A': {'kind': 'image', 'src': image_url, 'alt': 'Three objects'},
                     'B': {'kind': 'image', 'src': image_url, 'alt': 'Two objects'}}} for i in (1, 2)]}}]}
    notes = {'objectives': ['Compare pictured quantities'],
        'resources': {key: {'findings': ['Compare quantities; synthetic source notes'], 'pageRefs': ['p. 1']}
        for key in ('teachingDesign', 'courseware', 'learningTaskSheet', 'afterClassExercise')}}
    return {'identity': {'editionId': manifest['editionId'], 'revisionId': manifest['revisionId'],
        'nodeId': 'lesson', 'teachingRevision': '1', 'title': 'Pictured quantities',
        'objective': 'Compare pictured quantities', 'teacherCode': 'teacher',
        'authorModels': ['fixture-author', 'fixture-question-author'], 'estimatedMinutes': 15},
        'manifest': manifest, 'body': body,
        'notes': notes,
        'brief': {'objectives': ['Compare pictured quantities'], 'pages': ['slide', 'quiz']},
        'receipt': {'bodySha256': digest(body), 'ok': True, 'viewports': ['1280x720', '1000x563', '640x360']},
        'playReceipt': {'schemaVersion': 'mira.courseware.autoplay-receipt.v1', 'bodySha256': digest(body),
            'ok': True, 'pages': []},
        'verification': {'schemaVersion': 'mira.courseware.verification.v1',
            'bodySha256': digest(body), 'notesSha256': digest(notes), 'speechChecked': 6, 'questionsChecked': 2,
            'goalsChecked': 1,
            'disagreements': [], 'verifier': {'model': 'fixture-verifier', 'effort': 'high',
                'ranAt': '2026-11-03T11:00:00+08:00'}},
        'roster': {'teacher': 'male'}, 'gateIssues': [], 'media': {audio_name: audio, image_name: picture},
        'confirmation': {'userQuote': 'Publish this reviewed original lesson.',
            'confirmedAt': '2026-11-03T12:00:00+08:00', 'confirmedBy': 'owner',
            'authorAttestation': 'I authored the original lesson, narration and exercises; no official text, picture, question or layout was reproduced.'}}


def refresh_receipts(inputs):
    for name in ('receipt', 'playReceipt', 'verification'):
        inputs[name]['bodySha256'] = digest(inputs['body'])
    inputs['verification']['notesSha256'] = digest(inputs['notes'])


def waive_g7(inputs):
    """Bind the owner's direct-publication instruction to the current body and historical receipt."""
    inputs['verification']['bodySha256'] = '0' * 64
    inputs['ownerWaiver'] = {
        'schemaVersion': 'mira.courseware.g7-owner-waiver.v1', 'gate': 'G7',
        'bodySha256': digest(inputs['body']), 'notesSha256': digest(inputs['notes']),
        'priorVerificationSha256': digest(inputs['verification']), 'confirmedBy': 'owner',
        'userQuote': inputs['confirmation']['userQuote'],
        'confirmedAt': inputs['confirmation']['confirmedAt'],
        'reason': 'owner_direct_publication_without_independent_verification'}
    inputs['gateIssues'] = [{'gate': 'G7', 'code': 'verification_receipt_stale',
        'severity': 'waived', 'waiver': 'mira.courseware.g7-owner-waiver.v1'}]


class CoursewareReleaseTests(unittest.TestCase):
    def setUp(self):
        self.inputs = sample_inputs()

    def rejected(self, code):
        with self.assertRaisesRegex(ValueError, '^' + code + '$'):
            build_release(self.inputs)

    def test_alias_must_be_an_exact_sibling_in_the_same_section(self):
        first = self.inputs['manifest']['units'][0]['lessons'][0]
        first['sectionTitle'] = 'Reviewed lesson group'
        second = {**first, 'nodeId': 'second-lesson', 'sectionTitle': 'Different section'}
        self.inputs['manifest']['units'][0]['lessons'].append(second)
        self.inputs['identity']['directoryAliasNodeIds'] = [second['nodeId']]
        self.rejected('directory_aliases_invalid')
        second['sectionTitle'] = first['sectionTitle']
        prepared = build_release(self.inputs)
        self.assertEqual(prepared['frozen']['identity']['directoryAliasNodeIds'], [second['nodeId']])

    def test_valid_release_accepted_by_unchanged_validator(self):
        original = deepcopy(self.inputs)
        prepared = build_release(self.inputs)
        frozen, course = prepared['frozen'], prepared['course']
        build = {'status': 'published', 'content_key': frozen['contentKey'], 'node_id': 'lesson',
            'teaching_revision': '1', 'input_json': canonical(frozen), 'review_json': canonical(prepared['review']),
            'course_id': course['id'], 'course_version': course['version'],
            'course_content_sha256': digest(prepared['content_json'])}
        self.assertEqual(validate_release(build, self.inputs['manifest'], course), prepared['release'])
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])
        self.assertEqual(self.inputs, original)
        self.assertEqual(len(prepared['content_json']['questions']), 2)
        self.assertEqual(prepared['release']['audioAudit'], {'passed': True, 'segments': 6, 'method': AUDIO_METHOD})
        self.assertNotIn('previewKey', frozen)
        self.assertNotIn('taskId', frozen)
        self.assertEqual(set(frozen['coursewareLight']), {'schemaVersion', 'source', 'gates', 'confirmation', 'evidence'})
        self.assertEqual(set(frozen['coursewareLight']['confirmation']), {'userQuote', 'confirmedAt', 'confirmedBy'})
        self.assertEqual(course['content_origin'], 'openmaic_generated')
        for item in prepared['media']:
            self.assertIn('/' + ('audio' if item['mimeType'].startswith('audio/') else 'media') + '/', item['path'])
            self.assertIn(item['sha256'], item['path'])
        self.assertEqual(digest({k: v for k, v in frozen.items() if k != 'contentKey'}), frozen['contentKey'])

    def test_review_names_exact_evidence_and_limits(self):
        prepared = build_release(self.inputs)
        review = prepared['review']
        self.assertEqual(set(review), {'alignmentConfirmed', 'originalExpressionConfirmed', 'sourceUsageConfirmed',
            'publicationAuthorized', 'reviewer', 'basis', 'release'})
        for key in ('notes', 'brief', 'receipt', 'playReceipt', 'verification'):
            self.assertIn(digest(self.inputs[key]), review['basis'])
        self.assertIn(self.inputs['confirmation']['authorAttestation'], review['basis'])
        self.assertIn(self.inputs['confirmation']['userQuote'], review['basis'])
        self.assertIn(self.inputs['confirmation']['confirmedAt'], review['basis'])
        self.assertIn('not a human review', review['basis'])
        self.assertIn('not an independent originality check', review['basis'])
        self.assertIn(canonical(self.inputs['identity']['authorModels']), review['basis'])
        self.assertIn(canonical(self.inputs['verification']['verifier']['model']), review['basis'])

    def test_explicit_owner_waiver_is_truthful_bound_and_accepted(self):
        waive_g7(self.inputs)
        prepared = build_release(self.inputs)
        light = prepared['frozen']['coursewareLight']
        self.assertEqual(light['schemaVersion'], WAIVER_LIGHT_SCHEMA)
        self.assertEqual(light['gates']['G7'], {'passed': False, 'waived': True,
            'waiverSha256': digest(self.inputs['ownerWaiver'])})
        self.assertNotIn('verifier', prepared['frozen'])
        self.assertEqual(prepared['frozen']['verificationWaiver'], self.inputs['ownerWaiver'])
        self.assertIn('was not performed', prepared['review']['basis'])
        self.assertIn('not represented as current', prepared['review']['basis'])
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])

    def test_owner_waiver_cannot_cover_other_gates_or_be_rebound(self):
        waive_g7(self.inputs)
        self.inputs['gateIssues'].append({'gate': 'G2', 'code': 'overlap', 'severity': 'error'})
        self.rejected('gates_failed')
        for field, value in (('userQuote', 'different publication'), ('bodySha256', 'f' * 64),
                             ('priorVerificationSha256', 'e' * 64)):
            with self.subTest(field=field):
                self.inputs = sample_inputs()
                waive_g7(self.inputs)
                self.inputs['ownerWaiver'][field] = value
                self.rejected('verification_invalid')

    def test_waiver_release_validator_rejects_tampered_claims(self):
        waive_g7(self.inputs)
        for mutate in (
                lambda p: p['frozen']['coursewareLight']['gates']['G7'].update(passed=True),
                lambda p: p['frozen']['verificationWaiver'].update(userQuote='different'),
                lambda p: p['review'].update(reviewer='independently verified')):
            with self.subTest(mutate=mutate):
                prepared = build_release(self.inputs)
                mutate(prepared)
                self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), ['release_invalid'])

    def test_alignment_flag_refuses_missing_or_partial_evidence(self):
        for delta in ({'disagreements': ['wrong answer']}, {'speechChecked': 1}, {'questionsChecked': 1},
                      {'speechChecked': True}, {'bodySha256': '0' * 64}):
            with self.subTest(delta=delta):
                self.inputs = sample_inputs()
                self.inputs['verification'].update(delta)
                self.rejected('verification_invalid')

    def test_source_flag_refuses_notes_without_page_references(self):
        self.inputs['notes']['resources']['courseware']['pageRefs'] = []
        self.rejected('notes_invalid')

    def test_source_flag_accepts_structured_page_references(self):
        self.inputs['notes']['resources']['courseware']['pageRefs'] = [
            'p. 1', 2, {'package': 'official-hour-1', 'resourceId': 'slides', 'pages': [3, 4]},
        ]
        refresh_receipts(self.inputs)
        prepared = build_release(self.inputs)
        self.assertEqual(prepared['frozen']['coursewareLight']['evidence']['notesSha256'], digest(self.inputs['notes']))
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])

    def test_source_flag_refuses_incomplete_structured_page_references(self):
        source = {'package': 'official-hour-1', 'resourceId': 'slides', 'pages': [3]}
        for update in ({'package': ' '}, {'resourceId': None}, {'pages': []},
                       {'pages': '3'}, {'pages': [0]}, {'pages': [True]}):
            with self.subTest(update=update):
                self.inputs['notes']['resources']['courseware']['pageRefs'] = [source | update]
                self.rejected('notes_invalid')

    def test_source_flag_accepts_structured_findings_with_page_references(self):
        self.inputs['notes']['resources']['courseware']['findings'].append({
            'classHour': 'lesson_1', 'pageRefs': [3, 'p. 4'], 'finding': 'Compare two groups.',
        })
        refresh_receipts(self.inputs)
        prepared = build_release(self.inputs)
        self.assertEqual(prepared['frozen']['coursewareLight']['evidence']['notesSha256'], digest(self.inputs['notes']))
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])

    def test_source_flag_refuses_incomplete_structured_findings(self):
        source = {'classHour': 'lesson_1', 'pageRefs': [3], 'finding': 'Compare two groups.'}
        for update in ({'classHour': None}, {'finding': ' '}, {'pageRefs': []}, {'pageRefs': [False]}):
            with self.subTest(update=update):
                self.inputs['notes']['resources']['courseware']['findings'] = [source | update]
                self.rejected('notes_invalid')

    def test_source_flag_accepts_legacy_findings_bound_to_resource_pages(self):
        notes = self.inputs['notes']
        item = notes['resources']['courseware']
        item['findings'] = [
            {'classHour': 'lesson_1', 'finding': 'Compare two groups.'},
            {'classHour': 'lesson_2', 'finding': 'Use the comparison to explain a choice.'},
            {'classHour': 'lesson_3', 'finding': 'Apply the comparison.', 'pageRefs': [4]},
        ]
        item['pageRefs'] = ['lesson_1/courseware:3', 'lesson_2/courseware:12']
        original_notes = deepcopy(notes)
        refresh_receipts(self.inputs)

        prepared = build_release(self.inputs)

        self.assertEqual(notes, original_notes)
        self.assertEqual(prepared['frozen']['coursewareLight']['evidence']['notesSha256'], digest(original_notes))
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])

    def test_source_flag_refuses_unbound_legacy_findings(self):
        finding = {'classHour': 'lesson_1', 'finding': 'Compare two groups.'}
        cases = (
            (finding, 'lesson_2/courseware:3'),
            (finding, 'lesson_1/teachingDesign:3'),
            (finding, 'lesson_1/courseware:0'),
            (finding, 'lesson_1/courseware:3-4'),
            ({'finding': finding['finding']}, 'lesson_1/courseware:3'),
            (finding | {'extra': True}, 'lesson_1/courseware:3'),
            (finding | {'classHour': 'lesson_01'}, 'lesson_01/courseware:3'),
            (finding | {'classHour': ' lesson_1'}, ' lesson_1/courseware:3'),
        )
        for value, page_ref in cases:
            with self.subTest(value=value, page_ref=page_ref):
                item = self.inputs['notes']['resources']['courseware']
                item['findings'] = [value]
                item['pageRefs'] = [page_ref]
                # A matching string under a different resource cannot supply this finding's reference.
                self.inputs['notes']['resources']['teachingDesign']['pageRefs'] = ['lesson_1/courseware:3']
                refresh_receipts(self.inputs)
                self.rejected('notes_invalid')

    def test_source_flag_does_not_replace_invalid_explicit_finding_references(self):
        item = self.inputs['notes']['resources']['courseware']
        item['pageRefs'] = ['lesson_1/courseware:3']
        for refs in ([], None, 'lesson_1/courseware:3', [False], [{'package': 'slides', 'pages': [3]}]):
            with self.subTest(refs=refs):
                item['findings'] = [{'classHour': 'lesson_1', 'finding': 'Compare two groups.', 'pageRefs': refs}]
                refresh_receipts(self.inputs)
                self.rejected('notes_invalid')

    def test_a_resource_the_official_listing_lacks_needs_its_evidence(self):
        item = self.inputs['notes']['resources']['afterClassExercise']
        item.clear()
        item.update(status='not_provided', evidence='the saved lesson listing sha256 ab12 has no after-class exercise')
        refresh_receipts(self.inputs)
        self.assertEqual(validate_light_release(build_release(self.inputs), self.inputs['manifest']), [])
        item['evidence'] = ' '
        self.rejected('notes_invalid')

    def test_original_flag_refuses_missing_author_attestation(self):
        self.inputs['confirmation'].pop('authorAttestation')
        self.rejected('attestation_missing')

    def test_original_flag_also_requires_passed_notes(self):
        self.inputs['notes'] = {}
        self.rejected('notes_invalid')

    def test_authorization_flag_refuses_non_owner(self):
        self.inputs['confirmation']['confirmedBy'] = 'operator'
        self.rejected('authorization_missing')

    def test_authorization_missing(self):
        self.inputs['confirmation']['userQuote'] = ' '
        self.rejected('authorization_missing')

    def test_confirmation_time_invalid(self):
        for stamp in ('2026-11-03T12:00:00', 'nonsense', None):
            self.inputs['confirmation']['confirmedAt'] = stamp
            self.rejected('confirmation_time_invalid')

    def test_attestation_missing(self):
        self.inputs['confirmation']['authorAttestation'] = 'I approve this lesson for publication.'
        self.rejected('attestation_missing')

    def test_notes_invalid(self):
        self.inputs['notes'] = None
        self.rejected('notes_invalid')

    def test_brief_missing(self):
        self.inputs['brief'] = {}
        self.rejected('brief_missing')

    def test_verification_invalid(self):
        self.inputs['verification'] = None
        self.rejected('verification_invalid')

    def test_verification_not_independent(self):
        self.inputs['verification']['verifier']['model'] = self.inputs['identity']['authorModels'][0]
        self.rejected('verification_not_independent')

    def test_verifier_must_differ_from_every_author_case_insensitively(self):
        self.inputs['verification']['verifier']['model'] = 'FIXTURE-QUESTION-AUTHOR'
        self.rejected('verification_not_independent')

    def test_author_models_must_be_a_nonempty_list_of_model_ids(self):
        for models in (None, [], 'fixture-author', [''], [' '], [None], ['fixture-author', 1]):
            with self.subTest(models=models):
                self.inputs['identity']['authorModels'] = models
                self.rejected('verification_not_independent')
        self.inputs['identity'].pop('authorModels')
        self.rejected('verification_not_independent')

    def test_verifier_model_must_be_a_nonempty_string(self):
        for verifier in (None, {}, {'model': None}, {'model': ''}, {'model': ' '}, {'model': 1}):
            with self.subTest(verifier=verifier):
                self.inputs['verification']['verifier'] = verifier
                self.rejected('verification_not_independent')
        self.inputs['verification'].pop('verifier')
        self.rejected('verification_not_independent')

    def test_build_receipt_output_shape_is_accepted(self):
        receipt = self.inputs['verification']
        self.assertEqual(set(receipt), {'schemaVersion', 'bodySha256', 'notesSha256', 'speechChecked',
            'questionsChecked', 'goalsChecked', 'disagreements', 'verifier'})
        self.assertEqual(set(receipt['verifier']), {'model', 'effort', 'ranAt'})
        prepared = build_release(self.inputs)
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])
        self.assertEqual(prepared['frozen']['verifier'], receipt['verifier'])
        self.assertIn(digest(receipt), prepared['review']['basis'])

    def test_author_models_are_frozen_and_change_release_identity(self):
        first = build_release(self.inputs)
        self.inputs['identity']['authorModels'].append('another-page-author')
        second = build_release(self.inputs)
        self.assertNotEqual(first['frozen']['contentKey'], second['frozen']['contentKey'])
        self.assertNotIn('another-page-author', first['frozen']['identity']['authorModels'])
        self.assertIn('another-page-author', second['review']['basis'])

    def test_estimated_minutes_invalid(self):
        for minutes in (None, True, False, '15', 15.0, 4, 121):
            with self.subTest(minutes=minutes):
                self.inputs['identity']['estimatedMinutes'] = minutes
                self.rejected('estimated_minutes_invalid')
        self.inputs['identity'].pop('estimatedMinutes')
        self.rejected('estimated_minutes_invalid')

    def test_estimated_minutes_is_projected_and_frozen(self):
        keys = set()
        for minutes in (5, 37, 120):
            with self.subTest(minutes=minutes):
                self.inputs['identity']['estimatedMinutes'] = minutes
                prepared = build_release(self.inputs)
                self.assertEqual(prepared['content_json']['estimatedMinutes'], minutes)
                self.assertEqual(json.loads(prepared['course']['content_json'])['estimatedMinutes'], minutes)
                self.assertEqual(prepared['frozen']['identity']['estimatedMinutes'], minutes)
                keys.add(prepared['frozen']['contentKey'])
        self.assertEqual(len(keys), 3)

    def test_teaching_revision_uses_catalog_identifier_rules(self):
        for revision in ('1', 'v2.0_2026-11-03', 'a' * 80):
            with self.subTest(revision=revision):
                self.inputs['identity']['teachingRevision'] = revision
                self.assertEqual(build_release(self.inputs)['course']['version'], revision)
        for revision in ('', None, 1, '-v1', 'a b', '一', 'a' * 81, 'v1\n'):
            with self.subTest(revision=revision):
                self.inputs['identity']['teachingRevision'] = revision
                self.rejected('identity_invalid')

    def test_audit_invalid(self):
        self.inputs['receipt']['viewports'].pop()
        self.rejected('audit_invalid')

    def test_roster_missing(self):
        self.inputs['roster'] = None
        self.rejected('roster_missing')

    def test_gates_failed(self):
        self.inputs['gateIssues'] = [{'gate': 'G2', 'code': 'slide_text_overlap', 'severity': 'error'}]
        self.rejected('gates_failed')

    def test_identity_invalid(self):
        self.inputs['identity']['teacherCode'] = ''
        self.rejected('identity_invalid')

    def test_manifest_mismatch(self):
        self.inputs['identity']['editionId'] = 'different'
        self.rejected('manifest_mismatch')

    def test_node_missing(self):
        self.inputs['identity']['nodeId'] = 'missing'
        self.rejected('node_missing')

    def test_draft_catalog_is_accepted_and_frozen_as_registered(self):
        # Published lessons were built from a catalog whose brief is still a draft; the validator only needs equality.
        manifest = self.inputs['manifest']
        manifest['rightsReview']['status'] = 'pending'
        brief = manifest['units'][0]['lessons'][0]['brief']
        brief.update(status='draft', objectives=[])
        prepared = build_release(self.inputs)
        self.assertEqual(prepared['frozen']['knowledgeBrief'], brief)
        self.assertEqual(prepared['content_json']['objectives'], ['Compare pictured quantities'])

    def test_objectives_invalid(self):
        for value in (None, [], [{}], [' '], 'text'):
            self.inputs['notes']['objectives'] = value
            self.rejected('objectives_invalid')

    def test_classroom_invalid(self):
        self.inputs['body']['id'] = 'other'
        self.rejected('classroom_invalid')

    def test_questions_invalid(self):
        self.inputs['body']['scenes'][1]['content']['questions'][0]['answer'] = ['A', 'B']
        self.rejected('questions_invalid')

    def test_speech_missing(self):
        self.inputs['body']['scenes'][0]['actions'] = []
        self.rejected('speech_missing')

    def test_media_missing(self):
        self.inputs['media'] = {}
        self.rejected('media_missing')

    def test_media_invalid(self):
        self.inputs['media']['../escape.wav'] = b'invalid'
        self.rejected('media_invalid')

    def test_media_hash_mismatch(self):
        name = next(iter(self.inputs['media']))
        self.inputs['media'][name] += b'changed'
        self.rejected('media_hash_mismatch')

    def test_classroom_document_has_the_complete_native_shape(self):
        prepared = build_release(self.inputs)
        classroom = prepared['release']['classroom']
        self.assertEqual(set(classroom), {'id', 'stage', 'scenes', 'createdAt'})
        self.assertEqual(classroom['createdAt'], 1793608977483)

    def test_student_delivery_accepts_the_published_classroom(self):
        # The student path re-reads the stored classroom with its own strict checks; it must accept what we freeze.
        from collections import OrderedDict
        from pathlib import Path
        from threading import Lock
        from services.textbook_classroom_service import TextbookClassroomService
        release = build_release(self.inputs)['release']
        raw = json.dumps(release['classroom'], ensure_ascii=False).encode()

        class Store:
            class config:
                mode = 'registry'
            project_root = Path('/project')

            def resolve(self, source):
                return {'mimeType': 'application/json', 'sha256': hashlib.sha256(raw).hexdigest(),
                        'byteSize': len(raw), 'locator': {}}

            def read_bytes(self, source, expected_sha256, expected_bytes):
                return raw
        service = TextbookClassroomService.__new__(TextbookClassroomService)
        service.course_files, service._classroom_cache, service._classroom_cache_lock = Store(), OrderedDict(), Lock()
        self.assertEqual(service._playback_release(release)['classroom'], release['classroom'])

    def test_classroom_without_creation_time_is_refused(self):
        for value in (None, 0, '', ' ', 1.5):
            self.inputs = sample_inputs()
            self.inputs['body']['stage']['createdAt'] = value
            refresh_receipts(self.inputs)
            self.rejected('classroom_invalid')
        self.inputs = sample_inputs()
        del self.inputs['body']['stage']['createdAt']
        refresh_receipts(self.inputs)
        self.rejected('classroom_invalid')

    def test_media_reference_invalid(self):
        self.inputs['body']['scenes'][0]['actions'][0]['audioUrl'] = '/api/classroom-media/other/media/missing.wav'
        refresh_receipts(self.inputs)
        self.rejected('media_reference_invalid')

    def test_external_media(self):
        self.inputs['body']['scenes'][0]['content']['image'] = 'https://example.invalid/image.png'
        refresh_receipts(self.inputs)
        self.rejected('external_media')

    def test_svg_namespace_is_not_external_media(self):
        self.inputs['body']['scenes'][0]['content']['html'] = (
            "<svg xmlns='http://www.w3.org/2000/svg'></svg><script>document.createElementNS('http://www.w3.org/2000/svg','line')</script>")
        refresh_receipts(self.inputs)
        build_release(self.inputs)
        self.inputs['body']['scenes'][0]['content']['html'] += '<img src="http://www.w3.org.example.invalid/a.png">'
        refresh_receipts(self.inputs)
        self.rejected('external_media')

    def test_media_unreferenced(self):
        raw = b'extra picture'
        self.inputs['media'][hashlib.sha256(raw).hexdigest() + '.png'] = raw
        self.rejected('media_unreferenced')

    def test_audio_invalid(self):
        image_name = next(name for name in self.inputs['media'] if name.endswith('.png'))
        self.inputs['body']['scenes'][0]['actions'][0]['audioUrl'] = '/api/classroom-media/authored/media/' + image_name
        refresh_receipts(self.inputs)
        self.rejected('audio_invalid')

    def test_release_invalid(self):
        prepared = build_release(self.inputs)
        prepared['course']['content_json'] = canonical({'tampered': True})
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), ['release_invalid'])
        with patch('content.courseware_release.validate_release', return_value=None):
            self.rejected('release_invalid')

    def test_final_authority_rejects_each_missing_review_flag(self):
        for flag in ('alignmentConfirmed', 'originalExpressionConfirmed', 'sourceUsageConfirmed', 'publicationAuthorized'):
            prepared = build_release(self.inputs)
            prepared['review'][flag] = False
            self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), ['release_invalid'])

    def test_light_validator_rejects_changed_basis_and_evidence(self):
        for field in ('basis', 'reviewer'):
            prepared = build_release(self.inputs)
            prepared['review'][field] = 'unsupported claim'
            self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), ['release_invalid'])
        prepared = build_release(self.inputs)
        prepared['frozen']['coursewareLight']['evidence']['notesSha256'] = 'not-a-hash'
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), ['release_invalid'])

    def test_warnings_remain_in_frozen_gate_summary(self):
        self.inputs['gateIssues'] = [{'gate': 'G3', 'code': 'speech_too_long', 'severity': 'warn'}]
        prepared = build_release(self.inputs)
        self.assertEqual(prepared['frozen']['coursewareLight']['gates']['G3'],
            {'passed': True, 'warnings': ['speech_too_long']})

    def test_evidence_changes_change_identity(self):
        old = build_release(self.inputs)
        self.inputs['confirmation']['userQuote'] = 'Publish this exact revised lesson.'
        new = build_release(self.inputs)
        self.assertNotEqual(old['frozen']['contentKey'], new['frozen']['contentKey'])
        self.assertEqual(new, build_release(self.inputs))

    def test_native_body_without_top_level_id_gets_delivery_identity(self):
        self.inputs['body'].pop('id')
        refresh_receipts(self.inputs)
        prepared = build_release(self.inputs)
        self.assertEqual(prepared['classroom']['id'], prepared['release']['classroomId'])
        self.assertEqual(validate_light_release(prepared, self.inputs['manifest']), [])

    def test_filename_hash_suffix_is_preserved_as_normalized_delivery_hash(self):
        old = next(name for name in self.inputs['media'] if name.endswith('.wav'))
        new = 'narration-' + old[:-4] + '.WAV'
        self.inputs['media'][new] = self.inputs['media'].pop(old)
        for action in self.inputs['body']['scenes'][0]['actions']:
            action['audioUrl'] = action['audioUrl'].replace(old, new)
        for question in self.inputs['body']['scenes'][1]['content']['questions']:
            question['questionAudioUrl'] = question['questionAudioUrl'].replace(old, new)
        refresh_receipts(self.inputs)
        prepared = build_release(self.inputs)
        self.assertTrue(any(item['path'].endswith('/audio/' + old) for item in prepared['media']))


if __name__ == '__main__':
    unittest.main()
