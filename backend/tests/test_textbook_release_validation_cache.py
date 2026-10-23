"""Bounded release validation reuse without weakening mutable identity gates."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier, Lock
import time
import unittest
from unittest.mock import patch

from core.errors import ApiError
from services import textbook_directory_access as directory
from tests import test_textbook_learning as existing
from tests.test_textbook_activity_release import fixture


class TextbookReleaseValidationCacheTest(unittest.TestCase):
    def setUp(self):
        existing.TextbookLearningTest.setUp(self)
        self.db.execute('ALTER TABLE learning_courses ADD COLUMN title TEXT')
        directory._clear_validation_cache_for_tests()
        self.addCleanup(directory._clear_validation_cache_for_tests)

    def publish(self):
        manifest, frozen, build, release, course = fixture(
            self.manifest, 'unit_guide', 'cache-test-v1')
        course['id'] = 'course-' + frozen['contentKey'][:20]
        self.repo.reserve_build(self.db, frozen, 1)
        self.db.execute(
            "INSERT INTO learning_courses "
            "(id,version,grade_code,subject,content_json,status,quality_status,content_origin,title) "
            "VALUES (?,?,?,?,?,'published','released','openmaic_generated',?)",
            (course['id'], course['version'], course['grade_code'], course['subject'],
             course['content_json'], course['title']))
        self.repo.bind_published(
            self.db, self.repo.get_build(self.db, frozen['contentKey']),
            course, json.loads(build['review_json']), 1)
        self.db.raw.commit()
        return frozen['contentKey'], release

    def release(self, key):
        return directory.published_release(
            self.repo, self.db, key, {'grade_code': 'primary_1'})

    def test_identical_release_runs_deep_validation_once(self):
        key, expected = self.publish()
        with patch.object(directory, 'validate_release', wraps=directory.validate_release) as validator:
            self.assertEqual(self.release(key)[1], expected)
            self.assertEqual(self.release(key)[1], expected)
        self.assertEqual(validator.call_count, 1)

    def test_changed_review_without_timestamp_change_cannot_hit_cache(self):
        key, _ = self.publish()
        with patch.object(directory, 'validate_release', wraps=directory.validate_release) as validator:
            self.release(key)
            self.db.execute(
                "UPDATE learning_textbook_course_builds SET review_json='{}' WHERE content_key=?",
                (key,))
            self.db.raw.commit()
            with self.assertRaises(ApiError):
                self.release(key)
        self.assertEqual(validator.call_count, 2)

    def test_changed_course_content_forces_revalidation(self):
        key, _ = self.publish()
        with patch.object(directory, 'validate_release', wraps=directory.validate_release) as validator:
            self.release(key)
            self.db.execute(
                "UPDATE learning_courses SET content_json='{}' WHERE id=("
                "SELECT course_id FROM learning_textbook_course_builds WHERE content_key=?)",
                (key,))
            self.db.raw.commit()
            with self.assertRaises(ApiError):
                self.release(key)
        self.assertEqual(validator.call_count, 2)

    def test_course_retirement_and_manifest_change_still_fail_before_cache(self):
        key, _ = self.publish()
        with patch.object(directory, 'validate_release', wraps=directory.validate_release) as validator:
            self.release(key)
            self.db.execute(
                "UPDATE learning_courses SET retired_at=2 WHERE id=("
                "SELECT course_id FROM learning_textbook_course_builds WHERE content_key=?)",
                (key,))
            self.db.raw.commit()
            with self.assertRaises(ApiError):
                self.release(key)
            self.db.execute('UPDATE learning_courses SET retired_at=NULL')
            self.db.execute(
                "UPDATE learning_textbook_revisions SET manifest_json='{}' "
                "WHERE edition_id=? AND revision_id=?",
                (self.manifest['editionId'], self.manifest['revisionId']))
            self.db.raw.commit()
            with self.assertRaises(ApiError):
                self.release(key)
        self.assertEqual(validator.call_count, 1)

    def test_directory_scan_reuses_prefetched_build_row(self):
        key, _ = self.publish()
        builds = self.repo.builds(
            self.db, self.manifest['editionId'], self.manifest['revisionId'])
        with patch.object(self.repo, 'get_build', side_effect=AssertionError('duplicate build read')):
            releases = directory.published_node_releases(
                self.repo, self.db, {'grade_code': 'primary_1'}, builds)
        self.assertEqual(releases[builds[0]['node_id']][0]['content_key'], key)

    def test_parallel_identical_validation_is_singleflight(self):
        key, expected = self.publish()
        build = deepcopy(self.repo.get_build(self.db, key))
        revision = self.repo.get_revision(
            self.db, build['edition_id'], build['revision_id'])
        manifest = deepcopy(self.repo.manifest(revision))
        course = deepcopy(self.db.execute(
            'SELECT * FROM learning_courses WHERE id=? AND version=?',
            (build['course_id'], build['course_version'])).fetchone())
        barrier = Barrier(5)
        calls = 0
        calls_lock = Lock()
        real = directory.validate_release

        def slow_validate(*args):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.05)
            return real(*args)

        def worker(_):
            barrier.wait()
            return directory._validate_release_cached(
                self.repo, build, manifest, course)

        directory._clear_validation_cache_for_tests()
        with patch.object(directory, 'validate_release', side_effect=slow_validate):
            with ThreadPoolExecutor(max_workers=5) as executor:
                results = list(executor.map(worker, range(5)))
        self.assertEqual(calls, 1)
        self.assertTrue(all(result == expected for result in results))

    def test_cache_is_bounded_and_keeps_only_small_release_identity(self):
        manifest = {'editionId': 'cache-book', 'gradeCode': 'primary_1'}
        course = {
            'id': 'course-cache', 'version': '1', 'grade_code': 'primary_1',
            'subject': 'chinese', 'status': 'published', 'quality_status': 'released',
            'content_origin': 'openmaic_generated', 'retired_at': None,
            'content_json': '{}',
        }

        def accepted(build, _manifest, _course):
            return json.loads(build['review_json'])['release']

        with patch.object(directory, 'validate_release', side_effect=accepted):
            for index in range(directory._VALIDATION_CACHE_MAX_ENTRIES + 1):
                release = {'schemaVersion': 'test-release', 'sha256': f'{index:064x}'}
                build = {
                    'content_key': f'{index:064x}', 'edition_id': 'cache-book',
                    'revision_id': '1', 'node_id': f'node-{index}', 'part_index': 1,
                    'teaching_revision': '1', 'course_id': 'course-cache',
                    'course_version': '1', 'course_content_sha256': 'a' * 64,
                    'status': 'published', 'created_at': 1, 'updated_at': 1,
                    'input_json': '{}', 'review_json': json.dumps({'release': release}),
                }
                self.assertEqual(
                    directory._validate_release_cached(self.repo, build, manifest, course),
                    release)
        self.assertEqual(
            len(directory._validation_cache), directory._VALIDATION_CACHE_MAX_ENTRIES)
        self.assertTrue(all(set(entry) == {
            'expiresAt', 'releaseSha256', 'releaseSchemaVersion'
        } for entry in directory._validation_cache.values()))


if __name__ == '__main__':
    unittest.main()
