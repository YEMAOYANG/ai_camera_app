"""Runtime reuse must retain strict publication and student authority gates."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
import time
import unittest
from unittest.mock import Mock, patch

from core.errors import ApiError
from services import textbook_directory_access as directory
from services import textbook_runtime_release_cache as runtime
from tests.test_textbook_directory_access import TextbookDirectoryAccessTest
from tests import test_textbook_learning as existing


class RuntimeReleaseCacheTest(unittest.TestCase):
    publish = TextbookDirectoryAccessTest.publish

    def setUp(self):
        existing.TextbookLearningTest.setUp(self)
        self.db.execute('ALTER TABLE learning_courses ADD COLUMN title TEXT')
        runtime._clear_for_tests()
        directory._clear_validation_cache_for_tests()
        self.addCleanup(runtime._clear_for_tests)
        self.addCleanup(directory._clear_validation_cache_for_tests)

    def read(self, key):
        return runtime.published_runtime_release(self.repo, self.db, key, self.child)

    def test_hit_skips_large_build_and_keeps_original_frozen_input_and_answers(self):
        key, _, release = self.publish()
        first = self.read(key)
        with patch.object(self.repo, 'get_build', side_effect=AssertionError('large row read')):
            second = self.read(key)
        self.assertNotIn('review_json', second[0])
        self.assertNotIn('audioAudit', second[1])
        self.assertEqual(second[1]['classroom'], release['classroom'])
        self.assertEqual(first, second)
        second[1]['classroom']['scenes'].clear()
        self.assertTrue(self.read(key)[1]['classroom']['scenes'])
        self.assertIn('input_json', first[0])

    def test_changed_review_with_same_timestamp_must_fail(self):
        key, _, _ = self.publish()
        self.read(key)
        self.db.execute("UPDATE learning_textbook_course_builds SET review_json='{}' WHERE content_key=?", (key,))
        with self.assertRaises(ApiError):
            self.read(key)

    def test_mutable_authority_is_checked_on_every_hit(self):
        key, course, _ = self.publish()
        self.read(key)
        changes = [
            ('learning_courses', 'status', 'unverified', 'published'),
            ('learning_courses', 'quality_status', 'unverified', 'released'),
            ('learning_courses', 'retired_at', 2, None),
            ('learning_textbook_course_builds', 'status', 'retired', 'published'),
            ('learning_textbook_revisions', 'retired_at', 2, None),
            ('learning_textbook_revisions', 'manifest_json', '{}', None),
        ]
        for table, column, bad, original in changes:
            if column == 'manifest_json':
                original = self.repo.get_revision(self.db, self.manifest['editionId'], self.manifest['revisionId'])[column]
            self.db.execute(f'UPDATE {table} SET {column}=?', (bad,))
            with self.subTest(column=column, table=table), self.assertRaises(ApiError):
                self.read(key)
            self.db.execute(f'UPDATE {table} SET {column}=?', (original,))
        with self.assertRaises(ApiError):
            runtime.published_runtime_release(self.repo, self.db, key, {'grade_code': 'primary_2'})

    def test_changed_course_content_cannot_reuse_projection(self):
        key, _, _ = self.publish()
        self.read(key)
        self.db.execute("UPDATE learning_courses SET content_json='{}'")
        with self.assertRaises(ApiError):
            self.read(key)

    def test_singleflight_precedes_large_row_read(self):
        key, _, _ = self.publish()
        identity = self.repo.runtime_release_identity(self.db, key)
        build = self.repo.get_build(self.db, key)
        full = directory._published_release_from_build(self.repo, self.db, build, self.child)
        barrier = Barrier(4)
        def read(_):
            barrier.wait()
            return runtime.published_runtime_release(self.repo, None, key, self.child)
        def slow(*args):
            time.sleep(.03)
            return deepcopy(full)
        with patch.object(self.repo, 'runtime_release_identity', return_value=identity), \
                patch.object(self.repo, 'get_build', return_value=build) as getter, \
                patch.object(directory, '_published_release_from_build', side_effect=slow):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(read, range(4)))
        self.assertEqual(getter.call_count, 1)
        self.assertTrue(all(v == results[0] for v in results))

    def test_racing_build_change_is_rejected_before_cache(self):
        key, _, _ = self.publish()
        identity = self.repo.runtime_release_identity(self.db, key)
        identity['build']['review_sha256'] = '0' * 64
        with patch.object(self.repo, 'runtime_release_identity', return_value=identity):
            with self.assertRaises(ApiError):
                self.read(key)
        self.assertFalse(runtime._cache)

    def test_size_and_count_bounds(self):
        key, _, _ = self.publish()
        with patch.object(runtime, '_MAX_BYTES', 1):
            self.read(key)
        self.assertFalse(runtime._cache)
        with patch.object(runtime, '_MAX_ENTRIES', 1):
            self.read(key)
            other, _, _ = self.publish(teaching_revision='cache-v2')
            self.read(other)
        self.assertEqual(len(runtime._cache), 1)
        self.assertTrue(all('audioAudit' not in v['value'][1] for v in runtime._cache.values()))

    def test_server_hashes_original_bytes_with_current_reads(self):
        key, _, _ = self.publish()
        identity = self.repo.runtime_release_identity(self.db, key)
        conn = Mock(dialect='postgresql')
        conn.execute.side_effect = [Mock(fetchone=Mock(return_value=identity[name]))
                                    for name in ('build', 'revision', 'course')]
        self.assertEqual(self.repo.runtime_release_identity(conn, key), identity)
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertIn("encode(sha256(convert_to(CAST(review_json AS TEXT),'UTF8')),'hex')", statements[0])
        self.assertTrue(all(sql.endswith(' FOR SHARE') for sql in statements))


if __name__ == '__main__':
    unittest.main()
