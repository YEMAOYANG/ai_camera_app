"""Student delivery must read registered originals, never the frozen DB body."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services.course_file_store import CourseFileStorageError
from services.textbook_classroom_service import TextbookClassroomService
from test_textbook_publication import fixture


class RemoteClassroomStore:
    def __init__(self, classroom):
        self.config = SimpleNamespace(mode='registry')
        self.project_root = Path('/isolated/courseware')
        self.resolve = Mock(side_effect=lambda path: deepcopy(self.entry))
        self.read_bytes = Mock(side_effect=lambda path, **kwargs: self.raw)
        self.set_room(classroom)

    def set_room(self, classroom, raw=None):
        self.raw = raw if raw is not None else canonical(classroom).encode()
        self.entry = {'sha256': hashlib.sha256(self.raw).hexdigest(), 'byteSize': len(self.raw),
                      'mimeType': 'application/json', 'locator': {'kind': 'zip_member',
                      'objectKey': '课程/原始课件.zip', 'etag': 'verified-etag', 'memberPath': '课堂数据.json'}}


class TextbookClassroomStorageTests(unittest.TestCase):
    def setUp(self):
        _, self.build, self.release = fixture()
        self.release['classroom']['createdAt'] = 1800000000000
        self.release['classroomSha256'] = digest(self.release['classroom'])
        self.release['sha256'] = digest({k: v for k, v in self.release.items() if k != 'sha256'})
        self.store = RemoteClassroomStore(self.release['classroom'])
        repository = SimpleNamespace(database=Mock(), parse=json.loads)
        self.service = TextbookClassroomService(repository, student_auth=Mock(), signing_key='isolated',
            public_url='https://runtime.invalid', course_file_store=self.store)
        self.child = {'name': '学生甲', 'nickname': '小芽'}
        self.service._authority = Mock(side_effect=lambda token: (
            {}, self.child, self.build, self.release, {}, {}))

    def assert_unavailable(self):
        with self.assertRaises(ApiError) as caught:
            self.service.classroom('authorized')
        self.assertEqual((caught.exception.code, caught.exception.status_code), ('textbook_content_unavailable', 503))

    def test_reads_exact_registered_alias_and_preserves_public_projection(self):
        frozen = deepcopy(self.release)
        with patch('services.textbook_classroom_service.public_classroom',
                   wraps=__import__('content.textbook_release', fromlist=['public_classroom']).public_classroom) as project:
            result = self.service.classroom('authorized')
        source = self.store.project_root / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms' / (
            self.release['classroomId'] + '.json')
        self.store.read_bytes.assert_called_once_with(source, expected_sha256=self.store.entry['sha256'],
                                                      expected_bytes=self.store.entry['byteSize'])
        self.assertIsNot(project.call_args.args[0]['classroom'], self.release['classroom'])
        self.assertEqual(result['classroom']['id'], self.release['classroomId'])
        question = result['classroom']['scenes'][0]['content']['questions'][0]
        self.assertNotIn('answer', question)
        self.assertNotIn('analysis', question)
        self.assertEqual(question['questionAudioUrl'], frozen['classroom']['scenes'][0]['content']['questions'][0]['questionAudioUrl'])
        self.assertEqual(result['classroom']['stage']['miraStudent']['name'], '小芽')
        self.assertEqual(self.release, frozen)

    def test_missing_registration_fails_even_with_valid_db_snapshot(self):
        self.store.entry = None
        with patch('services.textbook_classroom_service.public_classroom') as project:
            self.assert_unavailable()
        project.assert_not_called()
        self.store.read_bytes.assert_not_called()

    def test_nonregistry_mode_fails_without_local_or_db_fallback(self):
        self.store.config.mode = 'manifest'
        self.assert_unavailable()
        self.store.resolve.assert_not_called()
        self.store.read_bytes.assert_not_called()

    def test_remote_failure_and_none_never_use_db_body(self):
        for failure in (CourseFileStorageError('unavailable'), None):
            with self.subTest(failure=failure):
                self.store.read_bytes.side_effect = failure if isinstance(failure, Exception) else None
                self.store.read_bytes.return_value = None
                self.assert_unavailable()

    def test_registered_wrong_body_and_wrong_raw_sha_are_rejected(self):
        changed = deepcopy(self.release['classroom'])
        changed['scenes'][0]['content']['questions'][0]['question'] = 'unexpected'
        self.store.set_room(changed)
        self.assert_unavailable()
        self.store.set_room(self.release['classroom'])
        self.store.entry['sha256'] = '0' * 64
        self.assert_unavailable()

    def test_identity_and_exact_shape_are_not_recovered_by_trimming(self):
        original = deepcopy(self.release['classroom'])
        for mutate in (lambda room: room.update(id='other'),
                       lambda room: room['stage'].update(id='other'),
                       lambda room: room.update(extra='not an approved Native field'),
                       lambda room: room.pop('createdAt')):
            with self.subTest(mutate=mutate):
                room = deepcopy(original)
                mutate(room)
                self.release['classroom'] = room
                self.release['classroomSha256'] = digest(room)
                self.store.set_room(room)
                self.assert_unavailable()

    def test_current_integer_and_string_created_at_forms_preserve_exact_bytes(self):
        for created_at in (1800000000000, '2026-10-23T00:00:00Z'):
            with self.subTest(created_at=created_at):
                self.release['classroom']['createdAt'] = created_at
                self.release['classroomSha256'] = digest(self.release['classroom'])
                self.store.set_room(self.release['classroom'])
                self.assertEqual(self.service.classroom('authorized')['classroom']['createdAt'], created_at)

    def test_duplicate_members_are_refused_even_when_parser_final_value_matches(self):
        body = canonical(self.release['classroom'])
        raw = ('{"id":"wrong",' + body[1:]).encode()
        self.store.set_room(self.release['classroom'], raw)
        self.assert_unavailable()

    def test_cache_is_seeded_only_from_verified_remote_version_and_is_child_neutral(self):
        first = self.service.classroom('authorized')
        first['classroom']['scenes'][0]['content']['questions'][0]['question'] = 'caller mutation'
        self.child['nickname'] = '学生乙'
        second = self.service.classroom('authorized')
        self.assertEqual(self.store.read_bytes.call_count, 1)
        self.assertEqual(self.store.resolve.call_count, 2)
        self.assertEqual(second['classroom']['stage']['miraStudent']['name'], '学生乙')
        self.assertNotEqual(second['classroom']['scenes'][0]['content']['questions'][0]['question'], 'caller mutation')
        self.assertEqual(self.service._authority.call_count, 2)

    def test_changed_head_does_not_hit_prior_remote_version_cache(self):
        self.service.classroom('authorized')
        room = deepcopy(self.release['classroom'])
        room['createdAt'] += 1
        self.store.set_room(room)
        self.assert_unavailable()
        self.assertEqual(self.store.read_bytes.call_count, 2)

    def test_expired_authority_never_reads_course_material(self):
        self.service._authority.side_effect = ApiError('textbook_session_invalid', 'expired', 401)
        with self.assertRaises(ApiError) as caught:
            self.service.classroom('expired')
        self.assertEqual(caught.exception.status_code, 401)
        self.store.resolve.assert_not_called()


if __name__ == '__main__':
    unittest.main()
