from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from content.textbook_catalog import digest
from core.course_storage_config import CourseStorageConfig
from core.errors import ApiError
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
from services.course_file_store import CourseFileStore
from services.textbook_publication_service import TextbookPublicationService
from tests.test_course_storage_repository import _Database


class PublicationRegistryRaceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.database = _Database()
        self.addCleanup(self.database.raw.close)
        self.registry = CourseStorageRepository(self.database)
        self.config = CourseStorageConfig(mode='registry', endpoint='http://storage.invalid:9000', bucket='study')
        self.storage = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        self.cid = 'stage_publication_fixture'
        self.source_path = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/' + self.cid + '.json'
        self.source = {'id': self.cid, 'stage': {'id': self.cid, 'name': 'Old approved'}, 'scenes': []}
        self.raw = json.dumps(self.source, ensure_ascii=False, indent=2).encode()
        self.objects = {}
        self.install_version(self.source, 'a' * 64)
        self.store = CourseFileStore(config=self.config, project_root=self.root, repository=self.registry)
        self.locked = False
        self.registry_lock_observations = []
        original_transaction = self.database.transaction
        @contextmanager
        def registry_transaction():
            self.registry_lock_observations.append(self.locked)
            with original_transaction() as conn:
                yield conn
        self.database.transaction = registry_transaction
        self.preview_row = {'classroom_id': self.cid, 'classroom_sha256': digest(self.source), 'status': 'preview_ready'}
        self.sql = []
        self.repository = Mock()
        self.repository.transaction.side_effect = self.business_transaction
        self.repository.get_revision.return_value = {'manifest_sha256': 'c' * 64}
        self.repository.reserve_build.return_value = ({'id': 'build-fixture'}, False)
        self.repository.bind_published.return_value = True
        self.prepared = {'frozen': {'previewKey': 'fixture-preview', 'sourceSha256': digest(self.source),
            'contentKey': 'd' * 64, 'textbookBinding': {'editionId': 'edition', 'alignmentRevisionId': 'revision',
                'alignmentManifestSha256': 'c' * 64}},
            'course': {'id': 'course-fixture', 'version': 'v1', 'content_json': '{"approved":true}'},
            'review': {}, 'manifest': {}, 'release': {'classroomId': 'tbpub_fixture', 'classroom': {'scenes': []},
                'audioAudit': {'segments': 0}, 'sha256': 'e' * 64}}
        self.service = TextbookPublicationService(SimpleNamespacePreview(self.repository), course_media_store=Mock(), course_file_store=self.store)
        self.opener = Mock()
        self.opener.open.side_effect = self.remote
        self.patchers = [patch('services.course_file_store.build_opener', return_value=self.opener),
            patch('services.textbook_publication_service.validate_release'),
            patch('services.textbook_publication_service.questions_for', return_value=[])]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.database.statements.clear()

    @contextmanager
    def business_transaction(self):
        self.locked = True
        try:
            yield self
        finally:
            self.locked = False

    def execute(self, sql, params):
        self.sql.append(sql)
        if 'FROM learning_textbook_course_previews' in sql:
            return Mock(fetchone=lambda: self.preview_row)
        if 'FROM learning_courses' in sql:
            return Mock(fetchone=lambda: {'content_json': self.prepared['course']['content_json']})
        raise AssertionError('Unexpected publication write before guard')

    def install_version(self, source, scope):
        raw = json.dumps(source, ensure_ascii=False, indent=2).encode()
        key = 'classrooms/' + scope + '.json'
        self.objects[key] = raw
        self.registry.register_scope({'scopeKey': scope}, [{'sourcePath': self.source_path,
            'sha256': hashlib.sha256(raw).hexdigest(), 'byteSize': len(raw), 'mimeType': 'application/json',
            'locator': {'kind': 'object', 'objectKey': key, 'etag': 'a' * 32}}], self.storage)

    def remote(self, request, timeout):
        self.assertTrue(self.locked)
        self.assertFalse(self.repository.reserve_build.called)
        from urllib.parse import urlsplit
        key = urlsplit(request.full_url).path.removeprefix('/study/')
        raw = self.objects[key]
        response = io.BytesIO(raw)
        response.status = 200
        response.headers = {'Content-Length': str(len(raw)), 'ETag': '"' + 'a' * 32 + '"'}
        return response

    def assert_refused(self):
        with self.assertRaises(ApiError):
            self.service.publish(self.prepared)
        self.repository.reserve_build.assert_not_called()
        self.repository.bind_published.assert_not_called()
        self.assertFalse(any(s.startswith(('INSERT', 'UPDATE')) for s in self.sql))

    def test_approved_canonical_bytes_are_read_after_preview_lock_and_before_any_write(self):
        self.assertNotEqual(hashlib.sha256(self.raw).hexdigest(), self.prepared['frozen']['sourceSha256'])
        result = self.service.publish(self.prepared)
        self.assertTrue(result['ok'])
        self.assertTrue(self.sql[0].endswith('FOR UPDATE'))
        self.assertTrue(self.registry_lock_observations and all(self.registry_lock_observations))
        self.assertTrue(any('course_storage_heads' in s for s in self.database.statements))
        self.assertFalse(any('FOR UPDATE' in s for s in self.database.statements))
        self.repository.reserve_build.assert_called_once()

    def test_remote_head_committed_before_sql_snapshot_update_refuses_publication(self):
        changed = deepcopy(self.source)
        changed['stage']['name'] = 'A newer remote edit'
        self.install_version(changed, 'f' * 64)
        self.database.statements.clear()
        self.registry_lock_observations.clear()
        self.assertEqual(self.preview_row['classroom_sha256'], digest(self.source))
        self.assert_refused()
        self.assertTrue(all(self.registry_lock_observations))
        self.assertFalse(any('FOR UPDATE' in s for s in self.database.statements))
        # The approved old immutable version still exists; guard must select head.
        count = self.database.raw.execute('SELECT COUNT(*) FROM course_storage_files').fetchone()[0]
        self.assertEqual(count, 2)

    def test_registered_remote_failure_never_uses_valid_local_shadow(self):
        local = self.root / self.source_path
        local.parent.mkdir(parents=True)
        local.write_bytes(self.raw)
        self.opener.open.side_effect = URLError('private upstream unavailable')
        self.assert_refused()
        self.assertEqual(local.read_bytes(), self.raw)

    def test_registered_remote_bytes_must_match_raw_receipt_sha_before_canonical_comparison(self):
        key = next(iter(self.objects))
        self.objects[key] = b' ' * len(self.raw)
        self.assert_refused()

    def test_sql_status_or_sha_drift_refuses_before_registry_read(self):
        for change in ({'status': 'review_required'}, {'classroom_sha256': '0' * 64}):
            saved = dict(self.preview_row)
            self.preview_row.update(change)
            self.assert_refused()
            self.preview_row = saved
        self.assertEqual(self.database.statements, [])
        self.opener.open.assert_not_called()

    def test_unregistered_new_work_retains_existing_publication_behavior(self):
        self.database.raw.execute('DELETE FROM course_storage_heads')
        self.database.raw.commit()
        path = self.root / self.source_path
        path.parent.mkdir(parents=True)
        path.write_bytes(self.raw)
        self.assertTrue(self.service.publish(self.prepared)['ok'])
        self.opener.open.assert_not_called()

    def test_nonregistry_mode_does_not_query_a_registry_or_native_http(self):
        path = self.root / self.source_path
        path.parent.mkdir(parents=True)
        path.write_bytes(self.raw)
        store = CourseFileStore(config=replace(self.config, mode='local'), project_root=self.root)
        self.service._course_file_store = store
        self.assertTrue(self.service.publish(self.prepared)['ok'])
        self.assertEqual(self.database.statements, [])
        self.opener.open.assert_not_called()

    def test_local_source_changed_before_sql_snapshot_update_refuses_publication(self):
        path = self.root / self.source_path
        path.parent.mkdir(parents=True)
        changed = deepcopy(self.source)
        changed['stage']['name'] = 'A local edit before SQL update'
        path.write_text(json.dumps(changed))
        self.service._course_file_store = CourseFileStore(config=replace(self.config, mode='local'), project_root=self.root)
        self.assert_refused()
        self.opener.open.assert_not_called()

    def test_unregistered_missing_classroom_does_not_count_as_checked(self):
        self.database.raw.execute('DELETE FROM course_storage_heads')
        self.database.raw.commit()
        self.assert_refused()

    def test_explicit_prepare_directory_is_checked_without_changing_frozen_identity(self):
        path = self.root / 'private-operator-classrooms' / (self.cid + '.json')
        path.parent.mkdir()
        path.write_bytes(self.raw)
        self.prepared['sourceClassroomPath'] = str(path)
        self.service._course_file_store = CourseFileStore(config=replace(self.config, mode='local'), project_root=self.root)
        self.assertTrue(self.service.publish(self.prepared)['ok'])

    def test_custom_local_shadow_cannot_hide_changed_standard_registered_head(self):
        path = self.root / 'private-operator-classrooms' / (self.cid + '.json')
        path.parent.mkdir()
        path.write_bytes(self.raw)
        self.prepared['sourceClassroomPath'] = str(path)
        changed = deepcopy(self.source)
        changed['stage']['name'] = 'A newer registered head'
        self.install_version(changed, 'f' * 64)
        self.assert_refused()

    def test_explicit_prepare_path_must_match_current_classroom_id(self):
        self.prepared['sourceClassroomPath'] = str(self.root / 'another-stage.json')
        self.assert_refused()

    def test_registered_source_lookup_does_not_follow_local_symlink_into_an_unregistered_shadow(self):
        local = self.root / self.source_path
        local.parent.mkdir(parents=True)
        shadow = self.root / 'shadow.json'
        shadow.write_bytes(b'{"old":"shadow"}')
        local.symlink_to(shadow)
        self.assertTrue(self.service.publish(self.prepared)['ok'])
        self.assertEqual(shadow.read_bytes(), b'{"old":"shadow"}')

    def test_secondary_historical_registered_alias_does_not_veto_selected_primary(self):
        primary = self.source_path
        self.source_path = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/' + self.cid + '/classroom.json'
        changed = deepcopy(self.source)
        changed['stage']['name'] = 'A historical secondary alias'
        self.install_version(changed, 'f' * 64)
        self.source_path = primary
        self.assertTrue(self.service.publish(self.prepared)['ok'])
        self.assertEqual(self.opener.open.call_count, 1)

    def test_registered_secondary_precedes_unregistered_primary_local_shadow(self):
        self.database.raw.execute('DELETE FROM course_storage_heads')
        self.database.raw.commit()
        primary = self.root / self.source_path
        primary.parent.mkdir(parents=True)
        primary.write_bytes(self.raw)
        self.source_path = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/' + self.cid + '/classroom.json'
        changed = deepcopy(self.source)
        changed['stage']['name'] = 'The selected registered secondary version'
        self.install_version(changed, 'f' * 64)
        self.assert_refused()
        self.opener.open.assert_called_once()

    def test_local_secondary_historical_alias_does_not_veto_selected_primary(self):
        primary = self.root / self.source_path
        primary.parent.mkdir(parents=True)
        primary.write_bytes(self.raw)
        secondary = primary.parent / self.cid / 'classroom.json'
        secondary.parent.mkdir()
        secondary.write_text('{"historical":true}')
        self.service._course_file_store = CourseFileStore(config=replace(self.config, mode='local'), project_root=self.root)
        self.assertTrue(self.service.publish(self.prepared)['ok'])


class SimpleNamespacePreview:
    def __init__(self, repository):
        self.repository = repository


if __name__ == '__main__':
    unittest.main()
