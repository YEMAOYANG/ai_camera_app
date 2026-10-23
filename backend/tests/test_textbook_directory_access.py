"""Released courses open from exact directories without changing school choices."""
import json
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from core.errors import ApiError
from core.security import now_ms
from services import textbook_directory_access as directory
from services.textbook_classroom_service import TextbookClassroomService
from services.textbook_directory_access import published_release
from tests.test_textbook_activity_release import fixture
from tests import test_textbook_learning as existing


class TextbookDirectoryAccessTest(unittest.TestCase):
    def setUp(self):
        existing.TextbookLearningTest.setUp(self)
        self.db.execute('ALTER TABLE learning_courses ADD COLUMN title TEXT')

    def publish(self, manifest=None, *, kind='unit_guide', teaching_revision='test-v1', created_at=1):
        manifest, frozen, build, release, course = fixture(manifest or self.manifest, kind, teaching_revision)
        course['id'] = 'course-' + frozen['contentKey'][:20]
        self.repo.reserve_build(self.db, frozen, created_at)
        self.db.execute("INSERT INTO learning_courses (id,version,grade_code,subject,content_json,status,quality_status,content_origin,title) VALUES (?,?,?,?,?,'published','released','openmaic_generated',?)",
            (course['id'], course['version'], course['grade_code'], course['subject'], course['content_json'], course['title']))
        self.repo.bind_published(self.db, self.repo.get_build(self.db, frozen['contentKey']), course, json.loads(build['review_json']), 1)
        self.db.raw.commit()
        return frozen['contentKey'], course, release

    def test_teaching_revisions_count_once_and_directory_opens_latest(self):
        old_key, _, _ = self.publish()
        new_key, _, _ = self.publish(teaching_revision='test-detailed-v2', created_at=2)
        self.assertNotEqual(old_key, new_key)
        status = self.service.student_catalog('student-a', {})['books'][0]['learningStatus']
        self.assertEqual(status['availableActivityCount'], 1)
        contents = self.service.student_contents('student-a', self.manifest['editionId'],
            {'alignmentRevisionId': self.manifest['revisionId']})
        self.assertEqual(contents['units'][0]['guideCourse']['contentKey'], new_key)
        self.assertEqual(len(self.repo.builds(self.db, self.manifest['editionId'], self.manifest['revisionId'])), 2)
        self.publish(kind='book_exploration')
        status = self.service.student_catalog('student-a', {})['books'][0]['learningStatus']
        self.assertEqual(status['availableActivityCount'], 2)

    def test_published_directory_is_available_without_changing_school_choice(self):
        key, _, _ = self.publish()
        result = self.service.student_catalog('student-a', {})
        self.assertEqual(len(result['books']), 1)
        self.assertFalse(result['books'][0]['selected'])
        self.assertEqual(result['books'][0]['accessMode'], 'published')
        contents = self.service.student_contents('student-a', self.manifest['editionId'], {'alignmentRevisionId': self.manifest['revisionId']})
        self.assertEqual(contents['units'][0]['guideCourse']['contentKey'], key)
        self.assertFalse(contents['selected'])
        self.assertEqual(contents['accessMode'], 'published')
        self.assertEqual(self.db.execute('SELECT * FROM learning_textbook_selections').fetchall(), [])

    def test_directory_projection_never_returns_full_review_or_runs_full_validator(self):
        key, _, _ = self.publish()
        full = self.repo.get_build(self.db, key)
        projected = self.repo.directory_builds(
            self.db, self.manifest['editionId'], self.manifest['revisionId'])[0]
        self.assertNotIn('review_json', projected)
        self.assertIn('directory_review_evidence_json', projected)
        self.assertIn('directory_release_summary_json', projected)
        self.assertIsInstance(
            json.loads(projected['directory_release_summary_json'])['activityScope'], dict)
        self.assertLess(
            len(projected['directory_review_evidence_json'])
            + len(projected['directory_release_summary_json']),
            len(full['review_json']),
        )
        with patch.object(directory, 'validate_release',
                          side_effect=AssertionError('directory read used full release validator')):
            self.assertEqual(self.service.student_catalog('student-a', {})['books'][0]
                             ['learningStatus']['availableActivityCount'], 1)
            contents = self.service.student_contents('student-a', self.manifest['editionId'], {
                'alignmentRevisionId': self.manifest['revisionId']})
        self.assertEqual(contents['units'][0]['guideCourse']['contentKey'], key)

    def test_top_level_damage_falls_back_but_deep_damage_is_rejected_at_launch(self):
        old_key, _, _ = self.publish()
        new_key, _, _ = self.publish(teaching_revision='test-v2', created_at=2)
        stored = self.repo.get_build(self.db, new_key)['review_json']

        def visible_key():
            contents = self.service.student_contents('student-a', self.manifest['editionId'], {
                'alignmentRevisionId': self.manifest['revisionId']})
            return contents['units'][0]['guideCourse']['contentKey']

        for mutation in ('review_authority', 'review_authority_integer', 'release_identity',
                         'audio_boolean_type', 'unexpected_review_payload'):
            review = json.loads(stored)
            if mutation == 'review_authority':
                review['publicationAuthorized'] = False
            elif mutation == 'review_authority_integer':
                review['publicationAuthorized'] = 1
            elif mutation == 'release_identity':
                review['release']['sha256'] = '0' * 64
            elif mutation == 'audio_boolean_type':
                review['release']['audioAudit']['passed'] = 1
            else:
                review['unrelatedLargePayload'] = 'x' * 1100000
            with self.subTest(mutation=mutation):
                self.db.execute('UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key=?',
                                (json.dumps(review), new_key))
                self.db.raw.commit()
                self.assertEqual(visible_key(), old_key)
            self.db.execute('UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key=?',
                            (stored, new_key))
            self.db.raw.commit()

        # A directory projection is an availability hint. It deliberately does
        # not transfer the classroom body, so a deep-only mutation remains
        # visible until the strict launch boundary rejects its broken hash.
        review = json.loads(stored)
        review['release']['classroom']['directoryTestTamper'] = True
        self.db.execute('UPDATE learning_textbook_course_builds SET review_json=? WHERE content_key=?',
                        (json.dumps(review), new_key))
        self.db.raw.commit()
        self.assertEqual(visible_key(), new_key)
        auth = Mock()
        auth.authenticate.return_value = {'principal': {'id': 'principal', 'family_id': 'family-a',
                                                        'child_id': 'child-a'},
                                          'session': {'id': 'login'}}
        classroom = TextbookClassroomService(self.repo, student_auth=auth,
            signing_key='isolated-directory-boundary', public_url='http://runtime')
        with patch.object(directory, 'validate_release', wraps=directory.validate_release) as strict_validator:
            with self.assertRaises(ApiError) as caught:
                classroom.launch('student-a', new_key)
        self.assertEqual(strict_validator.call_count, 1)
        self.assertEqual(caught.exception.code, 'textbook_release_unavailable')

    @staticmethod
    def course_in_contents(contents, kind):
        if kind == 'book_exploration':
            return contents['explorationCourse']
        if kind == 'unit_guide':
            return contents['units'][0]['guideCourse']
        return contents['units'][0]['lessons'][0]['course']

    def assert_latest_valid_fallback(self, kind):
        old_key, old_course, _ = self.publish(kind=kind)
        new_key, new_course, _ = self.publish(kind=kind, teaching_revision='test-v2', created_at=2)
        new_build = self.repo.get_build(self.db, new_key)
        self.db.execute("INSERT INTO learning_sessions VALUES ('done','family-a','child-a',?,?,'completed')",
                        (old_course['id'], old_course['version']))
        query = {'alignmentRevisionId': self.manifest['revisionId']}
        failures = (
            ('learning_courses', 'retired_at', 2, None, new_course['id'], 'id'),
            ('learning_courses', 'status', 'unverified', 'published', new_course['id'], 'id'),
            ('learning_textbook_course_builds', 'status', 'retired', 'published', new_key, 'content_key'),
            ('learning_textbook_course_builds', 'review_json', '{}', new_build['review_json'], new_key, 'content_key'),
            ('learning_textbook_course_builds', 'review_json', '["damaged"]', new_build['review_json'], new_key, 'content_key'),
            ('learning_textbook_course_builds', 'review_json', '{broken', new_build['review_json'], new_key, 'content_key'),
            ('learning_textbook_course_builds', 'input_json', '{broken', new_build['input_json'], new_key, 'content_key'),
        )
        for table, column, invalid, restored, identity, key in failures:
            with self.subTest(kind=kind, column=column, value=invalid):
                self.db.execute(f'UPDATE {table} SET {column}=? WHERE {key}=?', (invalid, identity))
                for token in ('student-a', 'student-b'):
                    status = self.service.student_catalog(token, {})['books'][0]['learningStatus']
                    self.assertEqual(status['status'], 'ready')
                    self.assertEqual(status['availableLessonCount'], int(kind == 'lesson_courseware'))
                    self.assertEqual(status['availableActivityCount'], int(kind != 'lesson_courseware'))
                    contents = self.service.student_contents(token, self.manifest['editionId'], query)
                    self.assertEqual(self.course_in_contents(contents, kind)['contentKey'], old_key)
                    self.assertFalse(contents['selected'])
                self.assertIsNotNone(published_release(self.repo, self.db, old_key, self.child))
                self.db.execute(f'UPDATE {table} SET {column}=? WHERE {key}=?', (restored, identity))
                contents = self.service.student_contents('student-a', self.manifest['editionId'], query)
                self.assertEqual(self.course_in_contents(contents, kind)['contentKey'], new_key)
        self.assertEqual(self.db.execute('SELECT * FROM learning_textbook_selections').fetchall(), [])

    def test_lesson_falls_back_to_same_valid_revision_for_all_students(self):
        self.assert_latest_valid_fallback('lesson_courseware')

    def test_unit_guide_falls_back_to_same_valid_revision_for_all_students(self):
        self.assert_latest_valid_fallback('unit_guide')

    def test_book_exploration_falls_back_to_same_valid_revision_for_all_students(self):
        self.assert_latest_valid_fallback('book_exploration')

    def test_no_valid_release_never_advertises_a_ready_book_or_entry(self):
        for kind in ('lesson_courseware', 'unit_guide', 'book_exploration'):
            self.publish(kind=kind)
            self.publish(kind=kind, teaching_revision='test-v2', created_at=2)
        self.db.execute('UPDATE learning_courses SET retired_at=2')
        self.assertEqual(self.service.student_catalog('student-a', {})['books'], [])
        query = {'alignmentRevisionId': self.manifest['revisionId']}
        with self.assertRaises(ApiError):
            self.service.student_contents('student-a', self.manifest['editionId'], query)
        existing.TextbookLearningTest.choose(self)
        catalog = self.service.student_catalog('student-a', {})
        self.assertEqual(catalog['books'][0]['learningStatus']['status'], 'unpublished')
        self.assertEqual(catalog['books'][0]['learningStatus']['availableLessonCount'], 0)
        self.assertIsNone(catalog['startHere'])
        contents = self.service.student_contents('student-a', self.manifest['editionId'], query)
        for kind in ('lesson_courseware', 'unit_guide', 'book_exploration'):
            self.assertIsNone(self.course_in_contents(contents, kind))

    def test_fallback_never_substitutes_another_directory_revision(self):
        old_key, _, _ = self.publish()
        other = deepcopy(self.manifest)
        other['revisionId'] = 'other-directory'
        self.service.import_manifest(other)
        _, other_course, _ = self.publish(other, created_at=2)
        self.db.execute('UPDATE learning_courses SET retired_at=2 WHERE id=?', (other_course['id'],))
        catalog = self.service.student_catalog('student-a', {})
        self.assertEqual([book['revisionId'] for book in catalog['books']], [self.manifest['revisionId']])
        with self.assertRaises(ApiError):
            self.service.student_contents('student-a', other['editionId'], {'alignmentRevisionId': other['revisionId']})
        contents = self.service.student_contents('student-a', self.manifest['editionId'], {'alignmentRevisionId': self.manifest['revisionId']})
        self.assertEqual(contents['units'][0]['guideCourse']['contentKey'], old_key)

    def test_wrong_grade_retired_and_withdrawn_courses_never_appear(self):
        key, course, _ = self.publish()
        self.db.execute("UPDATE children SET grade_code='primary_2' WHERE id='child-a'")
        self.assertEqual(self.service.student_catalog('student-a', {})['books'], [])
        self.db.execute("UPDATE children SET grade_code='primary_1' WHERE id='child-a'")
        self.db.execute('UPDATE learning_courses SET retired_at=2 WHERE id=?', (course['id'],))
        self.assertEqual(self.service.student_catalog('student-a', {})['books'], [])
        self.db.execute('UPDATE learning_courses SET retired_at=NULL WHERE id=?', (course['id'],))
        self.db.execute("UPDATE learning_textbook_course_builds SET status='retired' WHERE content_key=?", (key,))
        self.assertEqual(self.service.student_catalog('student-a', {})['books'], [])

    def test_query_cannot_override_child_or_grade_and_requires_student_auth(self):
        for query in ({'gradeCode': 'primary_6'}, {'childId': 'child-b'}):
            with self.assertRaises(ApiError): self.service.student_catalog('student-a', query)
        with self.assertRaises(ApiError): self.service.student_catalog('parent-a', {})

    def test_directory_permission_is_signed_and_rechecked_after_grade_changes(self):
        key, course, _ = self.publish()
        principal = {'id': 'principal', 'family_id': 'family-a', 'child_id': 'child-a'}
        auth = Mock()
        auth.authenticate.return_value = {'principal': principal, 'session': {'id': 'login'}}
        auth.repository.get_session.return_value = {'revoked_at': None, 'refresh_expires_at': now_ms() + 60000}
        auth._active_principal_and_device.return_value = (principal, {})
        service = TextbookClassroomService(self.repo, student_auth=auth, signing_key='isolated-test', public_url='http://runtime')
        service.learning = Mock()
        service.learning.assign_catalog_task.return_value = ({'id': 'task'}, False)
        session = {'id': 'session', 'child_id': 'child-a', 'course_id': course['id'], 'course_version': course['version']}
        service.learning.create_or_get_session.return_value = (session, False)
        service.learning.get_session.return_value = session
        with self.assertRaises(ApiError): service.launch('student-a', key, access_scope='selected_textbook')
        result = service.launch('student-a', key)
        ticket = parse_qs(urlparse(result['launchUrl']).query)['ticket'][0]
        self.assertEqual(service.signer.loads(ticket[5:])['accessScope'], 'published_directory')
        runtime = service.exchange(ticket)['runtimeToken']
        self.assertEqual(service.validate(runtime)['classroomId'], 'tbpub_' + key[:24])
        self.db.execute("UPDATE children SET grade_code='primary_2',grade_selection_revision=2 WHERE id='child-a'")
        with self.assertRaises(ApiError): service.validate(runtime)



if __name__ == '__main__': unittest.main()
