"""Isolated reuse regressions: no configured database, network or paid calls.

Threaded tests serialize transactions like the production edition row lock;
production SQL retains the FOR UPDATE + unique-key protection. They do not
claim to exercise a live MySQL server.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from content.textbook_preview import authoring_prompt, preview_input
from content.textbook_release import INPUT_SCHEMA
from core.errors import ApiError
from tests import test_textbook_preview as preview_fixture
from tests import test_textbook_publication as publication_fixture
from services.textbook_learning_service import TextbookLearningService


class CourseReuseTests(unittest.TestCase):
    def setUp(self):
        self.fixture = preview_fixture.TextbookPreviewTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db, self.repo, self.service, self.runtime = (
            self.fixture.db, self.fixture.repo, self.fixture.service, self.fixture.runtime)
        self.manifest = self.fixture.manifest

    def prepare(self, **kwargs):
        return self.service.prepare(self.manifest['editionId'], self.manifest['revisionId'], 'u1-l1', **kwargs)

    def count(self, table):
        return self.db.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n']

    def ready(self):
        self.fixture.test_success_snapshots_classroom_and_reuses_without_native_calls()
        return self.prepare()['previewKey']

    def changed_prompt(self):
        prompt = deepcopy(authoring_prompt())
        prompt['instructions'].append('保持讲解简短。')
        return patch('content.textbook_preview.authoring_prompt', return_value=prompt)

    def assert_error(self, code, function):
        with self.assertRaises(ApiError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)

    def test_completed_preview_survives_prompt_upgrade(self):
        key = self.ready()
        with self.changed_prompt():
            self.assertEqual(self.prepare()['previewKey'], key)
            self.assertEqual(self.service.start(key)['status'], 'preview_ready')
        self.assertEqual(self.count('learning_textbook_course_previews'), 1)
        self.runtime.start_generation.assert_called_once()

    def test_running_preview_survives_prompt_upgrade(self):
        key = self.prepare()['previewKey']
        self.service.start(key)
        with self.changed_prompt():
            self.assertEqual(self.prepare()['previewKey'], key)
            self.service.start(key)
        self.runtime.start_generation.assert_called_once()

    def test_queued_reservation_does_not_change_with_new_prompt(self):
        key = self.prepare()['previewKey']
        with self.changed_prompt():
            self.assertEqual(self.prepare()['previewKey'], key)
        self.assertEqual(self.count('learning_course_reuse_slots'), 1)
        self.runtime.start_generation.assert_not_called()

    def test_catalog_only_revision_reuses_original_artifact_before_generation_inputs(self):
        key = self.ready()
        changed = deepcopy(self.manifest)
        changed.update(revisionId='metadata-only', title='更新显示标题')
        TextbookLearningService(self.repo).import_manifest(changed)
        with patch('services.textbook_preview_service.preview_input', side_effect=AssertionError('must reuse first')):
            result = self.service.prepare(changed['editionId'], changed['revisionId'], 'u1-l1')
        self.assertEqual(result['previewKey'], key)
        row = self.service.get(key)
        self.assertEqual(row['revision_id'], self.manifest['revisionId'])
        self.runtime.start_generation.assert_called_once()

    def test_scope_change_does_not_silently_reuse_or_generate(self):
        self.ready()
        changed = deepcopy(self.manifest)
        changed['revisionId'] = 'new-teaching-scope'
        changed['units'][0]['lessons'][0]['brief']['objectives'].append('一个新教学目标')
        TextbookLearningService(self.repo).import_manifest(changed)
        self.assert_error('course_reuse_scope_changed', lambda: self.service.prepare(
            changed['editionId'], changed['revisionId'], 'u1-l1'))
        self.runtime.start_generation.assert_called_once()

    def test_explicit_upgrade_requires_difference_and_budget_then_reserves_once(self):
        old_key = self.ready()
        self.assert_error('course_reuse_upgrade_required', lambda: self.prepare(teaching_revision='2'))
        args = {'teaching_revision': '2', 'regeneration': {'reason': '新增迁移场景', 'budgetReference': 'reviewed-budget-2'}}
        result = self.prepare(**args)
        self.assertNotEqual(result['previewKey'], old_key)
        self.assertEqual(self.prepare(**args)['previewKey'], result['previewKey'])
        frozen = self.repo.parse(self.service.get(result['previewKey'])['input_json'])
        self.assertEqual(frozen['teachingRevision'], '2')
        self.assertEqual(self.count('learning_course_reuse_slots'), 2)
        # Reserving an explicitly authorized revision still does not dispatch.
        self.runtime.start_generation.assert_called_once()

    def test_unknown_dispatch_cannot_be_bypassed_by_prompt_or_new_version(self):
        key = self.prepare()['previewKey']
        self.runtime.start_generation.side_effect = TimeoutError()
        self.assert_error('textbook_preview_dispatch_unknown', lambda: self.service.start(key))
        with self.changed_prompt():
            self.assertEqual(self.prepare()['previewKey'], key)
            self.assertEqual(self.service.start(key)['status'], 'dispatch_unknown')
        self.assert_error('course_reuse_original_job_pending', lambda: self.prepare(
            teaching_revision='2', regeneration={'reason': 'retry', 'budgetReference': 'test'}))
        self.runtime.start_generation.assert_called_once()

    def test_legacy_hash_without_slot_is_adopted_and_conflicting_queued_hash_cannot_dispatch(self):
        original = self.ready()
        self.db.execute('DELETE FROM learning_course_reuse_slots')
        with self.changed_prompt():
            frozen = preview_input(self.manifest, 'u1-l1')
        self.db.execute('INSERT INTO learning_textbook_course_previews '
                        '(preview_key,edition_id,revision_id,node_id,input_json,runtime_origin,status,created_at,updated_at) '
                        'VALUES (?,?,?,?,?,?,?,?,?)', (frozen['previewKey'], self.manifest['editionId'],
                        self.manifest['revisionId'], 'u1-l1', canonical(frozen), self.runtime.base_url, 'queued', 2, 2))
        result = self.service.start(frozen['previewKey'])
        self.assertEqual(result['previewKey'], original)
        self.assertEqual(result['status'], 'preview_ready')
        self.runtime.start_generation.assert_called_once()

    def publish(self, preview_key):
        _, template, release = publication_fixture.fixture()
        frozen = {'schemaVersion': INPUT_SCHEMA, 'previewKey': preview_key,
                  'sourceSha256': 'b' * 64, 'gradeCode': self.manifest['gradeCode'],
                  'subject': self.manifest['subject'],
                  'knowledgeBrief': self.manifest['units'][0]['lessons'][0]['brief'],
                  'textbookBinding': {'editionId': self.manifest['editionId'],
                    'alignmentRevisionId': self.manifest['revisionId'],
                    'alignmentManifestSha256': digest(self.manifest), 'nodeId': 'u1-l1',
                    'partIndex': 1, 'teachingRevision': '1'}}
        key = digest(frozen)
        frozen['contentKey'] = key
        release['contentKey'] = key
        release['classroomId'] = 'tbpub_' + key[:24]
        release['classroom']['id'] = release['classroomId']
        release['classroom']['stage']['id'] = release['classroomId']
        release['classroomSha256'] = digest(release['classroom'])
        release['sha256'] = digest({k: v for k, v in release.items() if k != 'sha256'})
        review = json.loads(template['review_json'])
        review['release'] = release
        content = {'title': '天地人'}
        self.db.execute('INSERT INTO learning_courses VALUES (?,?,?,?,?,?,?,?,?)',
                        ('course', '1', self.manifest['gradeCode'], self.manifest['subject'], canonical(content),
                         'published', 'released', 'openmaic_generated', None))
        build, _ = self.repo.reserve_build(self.db, frozen, 1)
        self.repo.bind_published(self.db, build, {'id': 'course', 'version': '1', 'content_json': canonical(content)}, review, 2)
        self.db.raw.commit()
        return key

    def test_published_content_wins_and_shared_identity_contains_no_learner_fields(self):
        preview_key = self.ready()
        content_key = self.publish(preview_key)
        with self.changed_prompt(), patch('services.textbook_preview_service.preview_input', side_effect=AssertionError):
            a, b = self.prepare(), self.prepare()
        self.assertEqual(a, b)
        self.assertEqual(a['status'], 'published')
        self.assertEqual(a['contentKey'], content_key)
        self.assertEqual(self.service.start(preview_key)['status'], 'published')
        self.assertEqual(self.count('learning_course_reuse_slots'), 1)
        row = self.db.execute('SELECT * FROM learning_course_reuse_slots').fetchone()
        for private in ('familyId', 'childId', 'sessionId', 'answers', 'score'):
            self.assertNotIn(private, row['identity_json'])
            self.assertNotIn(private, a)
        self.runtime.start_generation.assert_called_once()

    def test_published_artifact_cannot_be_regenerated_when_withdrawn(self):
        key = self.ready()
        content_key = self.publish(key)
        self.prepare()
        self.db.execute("UPDATE learning_textbook_course_builds SET status='retired' WHERE content_key=?", (content_key,))
        self.assert_error('course_reuse_publication_unavailable', self.prepare)
        self.runtime.start_generation.assert_called_once()

    def test_missing_migration_fails_before_provider_or_new_preview(self):
        self.db.execute('DROP TABLE learning_course_reuse_slots')
        self.assert_error('course_reuse_schema_required', self.prepare)
        self.assertEqual(self.count('learning_textbook_course_previews'), 0)
        self.runtime.start_generation.assert_not_called()

    def test_runtime_change_never_creates_replacement(self):
        self.prepare()
        self.runtime.base_url = 'http://127.0.0.1:4100'
        self.assert_error('textbook_preview_runtime_changed', self.prepare)
        self.runtime.start_generation.assert_not_called()

    def test_changed_saved_artifact_fails_closed(self):
        key = self.ready()
        self.db.execute('UPDATE learning_textbook_course_previews SET classroom_sha256=? WHERE preview_key=?', ('0' * 64, key))
        self.assert_error('course_reuse_artifact_changed', self.prepare)
        self.runtime.start_generation.assert_called_once()

    def test_two_threads_share_one_reservation_and_one_dispatch(self):
        # SQLite fixture with explicit transaction serialization representing
        # the production edition-row lock, not a substitute for MySQL E2E.
        script = '\n'.join(self.db.raw.iterdump())
        self.db.raw.close()
        self.db.raw = sqlite3.connect(':memory:', check_same_thread=False)
        self.addCleanup(self.db.raw.close)
        self.db.raw.row_factory = sqlite3.Row
        self.db.raw.executescript(script)
        lock = threading.RLock()
        original_transaction = self.db.transaction
        @contextmanager
        def transaction():
            with lock:
                with original_transaction() as conn:
                    yield conn
        self.db.transaction = transaction
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.prepare) for _ in range(2)]
            keys = [future.result()['previewKey'] for future in futures]
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(self.count('learning_course_reuse_slots'), 1)
        entered, release = threading.Event(), threading.Event()
        def dispatch(**kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError('test dispatch was not released')
            return self.fixture.job
        self.runtime.start_generation.side_effect = dispatch
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.service.start, keys[0])
            self.assertTrue(entered.wait(3))
            second = pool.submit(self.service.start, keys[1])
            try:
                self.assertEqual(second.result(timeout=3)['status'], 'dispatching')
            finally:
                release.set()
            self.assertEqual(first.result(timeout=3)['status'], 'generating')
        self.runtime.start_generation.assert_called_once()


if __name__ == '__main__':
    unittest.main()
