"""Released courses open from exact directories without changing school choices."""
import json
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from core.errors import ApiError
from core.security import now_ms
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
