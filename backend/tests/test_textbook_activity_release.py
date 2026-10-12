"""Ungraded releases keep exact scope, student authority and honest progress."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import canonical, digest
from content.textbook_batch_release import INPUT_SCHEMA, RELEASE_SCHEMA, REVIEW_SCHEMA, REVIEW_FLAGS, node_key
from content.textbook_release import validate_release, public_classroom
from core.errors import ApiError
from services.textbook_classroom_service import TextbookClassroomService
from services.textbook_course_policy import assert_textbook_course
from services.textbook_activity_publication_service import (knowledge_brief, normalize_interactive_content,
                                                           reviewed_estimated_minutes)
from tests import test_textbook_learning as existing


def fixture(manifest=None, kind='unit_guide', teaching_revision='test-v1'):
    manifest = deepcopy(manifest or existing.sample())
    unit = manifest['units'][0]
    scope = {'kind': kind, 'unitId': None if kind == 'book_exploration' else unit['unitId'], 'nodeId': None}
    review = {'schemaVersion': REVIEW_SCHEMA, **{k: True for k in REVIEW_FLAGS},
              'reviewer': 'Synthetic test fixture', 'reviewedAt': 1, 'basis': 'Synthetic original activity',
              'evidence': ['Synthetic isolated fixture; no production review'],
              'sourceInputSha256': '1' * 64, 'sourceSha256': '2' * 64, 'audioAuditSha256': '3' * 64}
    frozen = {'schemaVersion': INPUT_SCHEMA, 'taskId': 'a' * 64, 'sourceInputSha256': '1' * 64,
        'sourceSha256': '2' * 64, 'audioAuditSha256': '3' * 64, 'reviewSha256': digest(review),
        'gradeCode': manifest['gradeCode'], 'subject': manifest['subject'], 'assessmentMode': 'ungraded',
        'teacher': get_formal_subject_qwen_voice_identity(manifest['subject']).to_target_payload(),
        'knowledgeBrief': {'objectives': ['看图观察'], 'priorKnowledge': [], 'excludedTopics': []}, 'activityScope': scope,
        'textbookBinding': {'editionId': manifest['editionId'], 'alignmentRevisionId': manifest['revisionId'],
            'alignmentManifestSha256': digest(manifest), 'nodeId': node_key(kind, scope['unitId']),
            'partIndex': 1, 'teachingRevision': teaching_revision}}
    key = digest(frozen); frozen['contentKey'] = key
    classroom_id = 'tbpub_' + key[:24]
    path = f'/api/classroom-media/{classroom_id}/audio/' + 'b' * 64 + '.wav'
    room = {'id': classroom_id, 'stage': {'id': classroom_id, 'name': '看图发现'},
            'scenes': [{'id': 'observe', 'type': 'slide', 'order': 0, 'content': {},
                        'actions': [{'id': 'speech', 'type': 'speech', 'text': '看看图片', 'audioUrl': path}]}]}
    release = {'schemaVersion': RELEASE_SCHEMA, 'contentKey': key, 'classroomId': classroom_id,
        'classroom': room, 'classroomSha256': digest(room), 'assessmentMode': 'ungraded', 'activityScope': scope,
        'media': [{'path': path, 'sha256': 'b' * 64, 'mimeType': 'audio/wav', 'byteSize': 100}],
        'audioAudit': {'passed': True, 'sha256': '3' * 64, 'segments': 1, 'minSimilarityBps': 9000}}
    release['sha256'] = digest(release)
    content = {'textbookBinding': frozen['textbookBinding'], 'questions': [], 'assessmentMode': 'ungraded', 'releaseSha256': release['sha256']}
    course = {'id': 'test-course', 'version': teaching_revision, 'title': '看图发现', 'content_json': canonical(content),
              'grade_code': manifest['gradeCode'], 'subject': manifest['subject'], 'status': 'published', 'quality_status': 'released'}
    build = {'content_key': key, 'edition_id': manifest['editionId'], 'revision_id': manifest['revisionId'],
        'node_id': frozen['textbookBinding']['nodeId'], 'part_index': 1, 'teaching_revision': teaching_revision,
        'input_json': canonical(frozen), 'status': 'published', 'review_json': canonical({**review, 'release': release}),
        'course_id': course['id'], 'course_version': course['version'], 'course_content_sha256': digest(content)}
    return manifest, frozen, build, release, course


class ActivityReleaseTest(unittest.TestCase):
    def test_author_reviewed_duration_keeps_legacy_receipts_and_rejects_invalid_values(self):
        self.assertEqual(reviewed_estimated_minutes({}), 10)
        self.assertEqual(reviewed_estimated_minutes({'estimatedMinutes': 35}), 35)
        for value in (True, 0, -1, 121, 12.5, '35', None):
            with self.subTest(value=value), self.assertRaises(ApiError):
                reviewed_estimated_minutes({'estimatedMinutes': value})

    def test_old_interactive_discriminator_is_filled_without_rewriting_html(self):
        html = '<main>exact original pictures and narration</main>'
        room = {'scenes': [{'type': 'interactive', 'content': {'html': html}}]}
        self.assertEqual(normalize_interactive_content(room)['scenes'][0]['content'],
                         {'type': 'interactive', 'html': html})
        for bad in ({'type': 'quiz', 'html': html}, {'type': 'interactive', 'html': ''}):
            with self.assertRaises(ApiError):
                normalize_interactive_content({'scenes': [{'type': 'interactive', 'content': bad}]})

    def test_legacy_design_requires_explicit_reviewed_teaching_scope(self):
        original = {'activityDesign': {'designName': '观察立体图形'}}
        with self.assertRaises(ApiError):
            knowledge_brief(original, {})
        brief = {'objectives': ['转动模型观察圆柱和圆锥的外形'], 'knowledgePoints': [],
                 'priorKnowledge': [], 'excludedTopics': ['不涉及体积计算']}
        self.assertEqual(knowledge_brief(original, {'knowledgeBrief': brief}), brief)
        with self.assertRaises(ApiError):
            knowledge_brief(original, {'knowledgeBrief': {**brief, 'objectives': '含糊目标'}})

    def test_review_cannot_replace_existing_frozen_lesson_scope(self):
        brief = {'objectives': ['认识十个一组成一个十'], 'knowledgePoints': ['具体数量不变'],
                 'priorKnowledge': [], 'excludedTopics': ['进位算法']}
        original = {'reviewedLessonScope': brief}
        self.assertEqual(knowledge_brief(original, {}), brief)
        with self.assertRaises(ApiError):
            knowledge_brief(original, {'knowledgeBrief': {**brief, 'objectives': ['学习进位算法']}})

    def test_exact_release_and_public_teacher_content(self):
        for kind in ('book_exploration', 'unit_guide'):
            manifest, _, build, release, course = fixture(kind=kind)
            self.assertEqual(validate_release(build, manifest, course), release)
            room = public_classroom(release)
            self.assertTrue(room['stage']['miraUngradedActivity'])
            self.assertNotIn('miraUngradedActivity', release['classroom']['stage'])

    def test_relabel_changed_teacher_wrong_media_or_review_never_delivers(self):
        manifest, _, build, _, course = fixture()
        for field, value in [('edition_id', 'other'), ('revision_id', 'other'), ('node_id', 'other'),
                             ('part_index', 2), ('teaching_revision', 'other'), ('course_content_sha256', '0' * 64)]:
            with self.subTest(field=field), self.assertRaises(ApiError):
                validate_release({**build, field: value}, manifest, course)
        for mutation in ('teacher', 'scope', 'review', 'media', 'quiz'):
            changed = deepcopy(build)
            frozen, review = json.loads(changed['input_json']), json.loads(changed['review_json'])
            if mutation == 'teacher': frozen['teacher']['voiceId'] = 'other'
            if mutation == 'scope': frozen['activityScope']['unitId'] = 'other'
            if mutation == 'review': review['visualInteractionConfirmed'] = False
            if mutation == 'media': review['release']['media'][0]['path'] = '/api/classroom-media/other/audio/a.wav'
            if mutation == 'quiz': review['release']['classroom']['scenes'].append({'id': 'quiz', 'type': 'quiz', 'content': {'questions': [{'id': 'q'}]}})
            changed.update(input_json=canonical(frozen), review_json=canonical(review))
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                validate_release(changed, manifest, course)

    def test_viewing_completion_requires_all_pages_and_speech_but_never_makes_quiz_credit(self):
        _, _, _, release, _ = fixture()
        state = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 1, 'visited': ['observe'], 'actions': [], 'quiz': None}
        session = {'id': 'session', 'status': 'in_progress', 'runtime_state_json': state}
        self.assertFalse(TextbookClassroomService._status(session, release)['completionReady'])
        state['actions'].append('speech')
        status = TextbookClassroomService._status(session, release)
        self.assertTrue(status['completionReady'])
        self.assertEqual(status['answeredQuestionIds'], [])
        self.assertFalse(status['completed'])
        service = object.__new__(TextbookClassroomService); service.learning = Mock()
        conn = Mock()
        service._complete(conn, {**session, 'task_id': 'task'}, {'family_id': 'family'}, {}, None)
        self.assertIn('未进行独立能力测评', service.learning.mark_task_completed.call_args.kwargs['summary'])
        service.learning.create_or_get_report.assert_not_called()


class ActivityCatalogTest(unittest.TestCase):
    setUp = existing.TextbookLearningTest.setUp
    choose = existing.TextbookLearningTest.choose

    def test_published_guide_opens_in_its_exact_directory_without_changing_school_selection(self):
        self.choose()
        self.db.execute('ALTER TABLE learning_courses ADD COLUMN title TEXT')
        manifest, frozen, build, release, course = fixture(self.manifest)
        self.repo.reserve_build(self.db, frozen, 1)
        self.db.execute("INSERT INTO learning_courses (id,version,grade_code,subject,content_json,status,quality_status,content_origin,title) VALUES (?,?,?,?,?,'published','released','openmaic_generated',?)",
            (course['id'], course['version'], course['grade_code'], course['subject'], course['content_json'], course['title']))
        reserved = self.repo.get_build(self.db, frozen['contentKey'])
        self.repo.bind_published(self.db, reserved, course, json.loads(build['review_json']), 1)
        self.db.raw.commit()
        result = self.service.student_contents('student-a', manifest['editionId'], {'alignmentRevisionId': manifest['revisionId']})
        self.assertEqual(result['units'][0]['guideCourse']['contentKey'], frozen['contentKey'])
        self.assertTrue(all(lesson['course'] is None for u in result['units'] for lesson in u['lessons']))
        catalog = self.service.student_catalog('student-a', {})
        self.assertEqual(catalog['books'][0]['learningStatus']['availableActivityCount'], 1)
        self.assertEqual(catalog['books'][0]['learningStatus']['availableLessonCount'], 0)
        self.assertEqual(catalog['startHere']['contentKey'], frozen['contentKey'])
        self.assertTrue(assert_textbook_course(self.db, child=self.child, course=course))
        self.db.execute('DELETE FROM learning_textbook_selections')
        public_directory = self.service.student_contents('student-a', manifest['editionId'], {'alignmentRevisionId': manifest['revisionId']})
        self.assertFalse(public_directory['selected'])
        self.assertEqual(public_directory['accessMode'], 'published')
        self.assertEqual(public_directory['units'][0]['guideCourse']['contentKey'], frozen['contentKey'])
        with self.assertRaises(ApiError):
            assert_textbook_course(self.db, child=self.child, course=course)
