"""Public migration inventories must never become raw course/database exports."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical, digest
from scripts import course_storage_releases as storage
from tests.test_textbook_publication import fixture


class ReadCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class ReadConnection:
    def __init__(self, raw):
        self.raw, self.statements = raw, []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        return ReadCursor(self.raw.execute(sql, params))


class PublishedMediaInventoryTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(':memory:')
        self.raw.row_factory = sqlite3.Row
        self.addCleanup(self.raw.close)
        self.raw.executescript('''
            CREATE TABLE learning_textbook_course_builds (
                content_key TEXT,status TEXT,input_json TEXT,review_json TEXT,
                edition_id TEXT,revision_id TEXT,node_id TEXT,part_index INTEGER,
                teaching_revision TEXT,course_id TEXT,course_version TEXT,course_content_sha256 TEXT);
            CREATE TABLE learning_courses (id TEXT,version TEXT,title TEXT,status TEXT,
                quality_status TEXT,retired_at INTEGER,content_json TEXT,content_origin TEXT,
                subject TEXT,grade_code TEXT,published_at INTEGER);
            CREATE TABLE learning_textbook_revisions (edition_id TEXT,revision_id TEXT,
                retired_at INTEGER,manifest_json TEXT,manifest_sha256 TEXT);
            CREATE TABLE student_sessions (private_token TEXT);
            INSERT INTO student_sessions VALUES ('must-not-export');
        ''')
        manifest, build, release = fixture()
        cid = release['classroomId']
        media = {'path': f'/api/classroom-media/{cid}/audio/{"a" * 64}.mp3',
                 'sha256': 'a' * 64, 'byteSize': 12, 'mimeType': 'audio/mpeg',
                 'sourceSha256': 'b' * 64, 'privateDebug': 'must-not-export'}
        release['media'] = [media]
        release['sha256'] = digest({key: value for key, value in release.items() if key != 'sha256'})
        review = json.loads(build['review_json'])
        review['release'] = release
        self.key, self.release = build['content_key'], release
        build.update(edition_id='book', revision_id='directory', review_json=canonical(review))
        names = ','.join(build)
        self.raw.execute(f'INSERT INTO learning_textbook_course_builds ({names}) VALUES ({",".join("?" for _ in build)})', tuple(build.values()))
        self.raw.execute('INSERT INTO learning_courses VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         ('course', '1', '天地人', 'published', 'released', None,
                          canonical({'title': '天地人'}), 'openmaic_generated',
                          'chinese', 'primary_1', 1234567890000))
        self.raw.execute('INSERT INTO learning_textbook_revisions VALUES (?,?,?,?,?)',
                         ('book', 'directory', None, canonical(manifest), digest(manifest)))
        self.raw.commit()
        self.raw.execute('PRAGMA query_only=ON')
        self.conn = ReadConnection(self.raw)

    def test_exports_only_the_published_media_contract_and_public_identity(self):
        result = storage.inventory(self.conn, content_key=self.key)
        self.assertTrue(result['ok'])
        self.assertEqual(result['schemaVersion'], storage.SCHEMA)
        self.assertEqual(result['totals']['totalByteSize'], 12)
        self.assertEqual(set(result['releases'][0]), {'contentKey', 'releaseSha256', 'classroomId',
            'courseId', 'courseVersion', 'title', 'media', 'subjectCode', 'subjectName',
            'gradeCode', 'gradeLabel', 'volumeCode', 'volumeLabel', 'editionId', 'editionLabel',
            'publisher', 'textbookTitle', 'publishedAt'})
        self.assertEqual(result['releases'][0]['subjectName'], '语文')
        self.assertEqual(result['releases'][0]['gradeLabel'], '一年级')
        self.assertEqual(result['releases'][0]['publishedAt'], 1234567890000)
        self.assertEqual(set(result['releases'][0]['media'][0]), {'path', 'sha256', 'byteSize', 'mimeType'})
        text = canonical(result)
        for forbidden in ('must-not-export', 'classroomSha256', 'sourceSha256', 'input_json',
                          'review_json', 'questionAudioUrl', 'correctAnswer', 'audioAudit'):
            self.assertNotIn(forbidden, text)
        self.assertTrue(all(statement.lstrip().startswith('SELECT') for statement in self.conn.statements))
        self.assertFalse(any('student_sessions' in statement for statement in self.conn.statements))

    def test_retired_or_unreleased_course_cannot_authorize_public_upload(self):
        self.raw.execute('PRAGMA query_only=OFF')
        self.raw.execute("UPDATE learning_courses SET quality_status='pending_review'")
        self.raw.execute('PRAGMA query_only=ON')
        with self.assertRaisesRegex(storage.InventoryError, 'published_content_key_not_found'):
            storage.inventory(self.conn, content_key=self.key)

    def test_lists_non_textbook_courses_as_an_explicit_coverage_gap(self):
        self.raw.execute('PRAGMA query_only=OFF')
        self.raw.execute('INSERT INTO learning_courses VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         ('formal', '2', '另一份正式课', 'published', 'released', None, '{}', 'formal',
                          'math', 'primary_1', 1234567890001))
        self.raw.execute('PRAGMA query_only=ON')
        result = storage.inventory(self.conn)
        self.assertFalse(result['ok'])
        self.assertFalse(result['allPublishedCourseMediaCovered'])
        self.assertEqual(result['nonTextbookPublishedCourses'][0]['courseId'], 'formal')
        self.assertEqual(result['uncoveredPublishedCourses'][0]['courseId'], 'formal')

    def test_corrupt_release_is_reported_without_exporting_raw_error_material(self):
        self.raw.execute('PRAGMA query_only=OFF')
        self.raw.execute("UPDATE learning_textbook_course_builds SET review_json='{}'")
        self.raw.execute('PRAGMA query_only=ON')
        result = storage.inventory(self.conn)
        self.assertFalse(result['ok'])
        self.assertEqual(result['totals']['releaseCount'], 0)
        self.assertEqual(result['totals']['totalByteSize'], 0)
        self.assertEqual(result['validationFailures'][0]['error'], 'textbook_release_unavailable')

    def test_rejects_original_sources_other_classrooms_and_invalid_byte_contracts(self):
        mutations = [
            {'path': '/output/private/request.json'},
            {'path': '/api/classroom-media/tbpub_' + 'c' * 24 + '/media/x.webp'},
            {'path': self.release['media'][0]['path'] + '?token=private'},
            {'mimeType': 'application/json'}, {'byteSize': 0}, {'byteSize': True},
            {'sha256': 'invalid'},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(storage.InventoryError):
                release = deepcopy(self.release)
                release['media'][0].update(mutation)
                storage.delivery_media(release)

    def test_private_file_is_exclusive_and_invalid_inventory_has_no_file(self):
        result = storage.inventory(self.conn, content_key=self.key)
        with tempfile.TemporaryDirectory() as temporary, patch.object(storage, 'PRIVATE_ROOT', Path(temporary)):
            target = Path(temporary) / 'private' / 'pilot.json'
            receipt = storage.write_private_inventory(result, target)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
            self.assertEqual(json.loads(target.read_text()), result)
            self.assertEqual(receipt['bytes'], target.stat().st_size)
            with self.assertRaises(storage.InventoryError):
                storage.write_private_inventory(result, target)
            with self.assertRaises(storage.InventoryError):
                storage.write_private_inventory({**result, 'ok': False}, target.parent / 'failed.json')
            self.assertFalse((target.parent / 'failed.json').exists())
            outside = Path(temporary).parent / 'outside-course-inventory.json'
            with self.assertRaises(storage.InventoryError):
                storage.write_private_inventory(result, outside)
            with self.assertRaises(storage.InventoryError):
                storage.write_private_inventory(result, Path(temporary) / '..' / 'escaped.json')
            linked = Path(temporary) / 'linked'
            linked.symlink_to(target.parent, target_is_directory=True)
            with self.assertRaises(storage.InventoryError):
                storage.write_private_inventory(result, linked / 'link.json')

    def test_formal_inventory_uses_existing_receipt_and_verified_teacher_audio_only(self):
        from tests.test_openmaic_runtime_audio_service import OpenMaicRuntimeAudioServiceTest
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            audio_fixture = OpenMaicRuntimeAudioServiceTest()
            audio_fixture.root = root / 'audio'
            rows = audio_fixture._rows(count=1)
            rows[0]['scene_order'] = 0
            room = {'stage': {'id': 'stage-formal'}, 'scenes': []}
            room_hash = digest(room)
            authority = {'upstream_classroom_id': 'stage-formal', 'build_item_id': 'build',
                'publication_receipt_hash': 'a' * 64, 'classroom_content_sha256': room_hash,
                'terminal_receipt_hash': 'b' * 64, 'expected_segment_count': 1,
                'tts_attempted_count': 1, 'tts_completed_count': 1, 'audio_validated_count': 1,
                'asr_attempted_count': 1, 'asr_passed_count': 1,
                'feature_manifest_json': canonical({'classroomContentSha256': room_hash})}
            (root / 'stage-formal.json').write_text(canonical(room))
            course = {'courseId': 'formal', 'courseVersion': '1', 'title': '正式课'}
            with patch.object(storage, 'NATIVE_ROOT', root), \
                 patch.object(storage, '_formal_authorities', return_value=[authority]), \
                 patch.object(storage, '_formal_audio_rows', return_value=rows):
                result = storage._formal_release(None, course, audio_fixture.root)
                self.assertIsNone(result['contentKey'])
                self.assertEqual(result['releaseSha256'], authority['publication_receipt_hash'])
                self.assertEqual(result['media'][0]['path'], '/mira/runtime-audio/formal-audio-0')
                self.assertEqual(result['media'][0]['sourcePath'],
                                 'backend/data/learning-media/narration/formal-audio-0.wav')
                self.assertEqual(set(result['media'][0]),
                    {'path', 'sourcePath', 'sha256', 'byteSize', 'mimeType'})
                for path in audio_fixture.root.rglob('*.wav'):
                    path.unlink()
                logical = storage._formal_release(None, course, audio_fixture.root,
                                                  verify_source_bytes=False)
                self.assertEqual(logical, result)
                (root / 'stage-formal.json').write_text(canonical({**room, 'scenes': [{'changed': True}]}))
                with self.assertRaisesRegex(storage.InventoryError, 'formal_classroom_hash_mismatch'):
                    storage._formal_release(None, course, audio_fixture.root)

    def test_read_only_transaction_always_rolls_back_and_closes(self):
        connection = Mock()
        database = Mock(connect=Mock(return_value=connection))
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            with storage.read_only_connection(database):
                raise RuntimeError('interrupted')
        self.assertEqual(connection.execute.call_args_list[0].args,
                         ('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ',))
        self.assertEqual(connection.execute.call_args_list[1].args,
                         ('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY',))
        connection.rollback.assert_called_once()
        connection.close.assert_called_once()

    def test_display_metadata_uses_stored_codes_and_does_not_change_media_digest(self):
        course = {'subject': 'science', 'grade_code': 'primary_1', 'published_at': 1234,
                  'title': '英语不能用于猜科目'}
        manifest = {'subject': 'science', 'gradeCode': 'primary_1', 'volume': 'upper',
                    'editionId': 'verified-book', 'editionLabel': '已核验版本',
                    'publisher': '已核验出版社', 'title': '科学一年级上册'}
        original = deepcopy(manifest)
        metadata = storage.release_metadata(course, manifest)
        self.assertEqual(metadata['subjectCode'], 'science')
        self.assertEqual(metadata['subjectName'], '科学')
        self.assertEqual(metadata['volumeLabel'], '上册')
        self.assertEqual(metadata['editionLabel'], '已核验版本')
        self.assertEqual(manifest, original)
        with self.assertRaisesRegex(storage.InventoryError, 'release_display_identity_mismatch'):
            storage.release_metadata({**course, 'subject': 'english'}, manifest)
        unknown = storage.release_metadata({'subjectCode': 'unregistered', 'gradeCode': 'unregistered'})
        self.assertEqual(unknown['subjectCode'], 'unregistered')
        for field in ('subjectName', 'gradeLabel', 'volumeLabel', 'editionLabel', 'publisher'):
            self.assertIsNone(unknown[field])
        result = storage.inventory(self.conn, content_key=self.key)
        release = result['releases'][0]
        before = [{'contentKey': release['contentKey'], 'courseId': release['courseId'],
                   'releaseSha256': release['releaseSha256'], 'media': release['media']}]
        self.assertEqual(result['mediaInventorySha256'], digest(before))

    def test_explicit_local_verification_never_fetches_remote_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(storage, 'ROOT', Path(temporary).resolve()):
            source = 'backend/data/learning-media/narration/published.wav'
            target = storage.ROOT / source
            target.parent.mkdir(parents=True)
            target.write_bytes(b'published audio')
            item = {'sourcePath': source, 'path': '/mira/runtime-audio/published',
                    'byteSize': 15, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                    'mimeType': 'audio/wav'}
            storage._verify_local_media(item)
            target.write_bytes(b'tampered! audio')
            with self.assertRaisesRegex(storage.InventoryError, 'local_media_hash_mismatch'):
                storage._verify_local_media(item)
            with self.assertRaisesRegex(storage.InventoryError, 'local_media_source_invalid'):
                storage._verify_local_media({**item, 'sourcePath': 'backend/data/learning-media/narration/../../private'})


if __name__ == '__main__':
    unittest.main()
