"""Formal UI snapshots reuse real event authority and never become evidence."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from flask import Flask

from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from repositories.openmaic_runtime_event_repository import OpenMaicRuntimeEventRepository
from services.openmaic_runtime_activity_state_service import OpenMaicRuntimeActivityStateService, _DEFINITIONS
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService
from services import textbook_activity_state as snapshots
from test_openmaic_runtime_event_bridge import _Repository, _LearningService, NOW


class _SnapshotRepository(_Repository):
    def __init__(self):
        super().__init__()
        self.publication = {'publication_receipt_hash': 'c' * 64}
        self.writes = []

    def get_activity_publication(self, _conn, *, authority):
        return deepcopy(self.publication)

    def save_activity_state(self, _conn, *, authority, runtime_state_json, now):
        self.writes.append((authority['learning_session_id'], runtime_state_json))
        self.session['runtime_state_json'] = runtime_state_json


class FormalActivityStateTests(unittest.TestCase):
    def setUp(self):
        _DEFINITIONS.clear()
        self.repo = _SnapshotRepository()
        self.original = {'lastSequence': 7, 'quiz': {'score': 1}, 'actions': ['action-1'],
            'answers': [{'questionId': 'q1', 'correct': False}], 'someOtherProgress': {'a': 1}}
        self.repo.session['runtime_state_json'] = canonical(self.original)
        self.learning = _LearningService()
        self.events = OpenMaicRuntimeEventService(repository=self.repo, learning_service=self.learning,
            clock=lambda: NOW)
        self.room = {'id': 'classroom-1', 'stage': {'id': 'classroom-1'}, 'scenes': [
            {'id': f'scene-{i}', 'stageId': 'classroom-1', 'order': i,
             'type': 'interactive' if i == 2 else 'slide',
             'content': {'type': 'interactive', 'html': '<button id="move">走一步</button>'}
                if i == 2 else {'type': 'slide'}} for i in range(10)]}
        self.source_sha = digest({'stage': self.room['stage'], 'scenes': self.room['scenes']})
        self.repo.authority['feature_manifest_json']['classroomContentSha256'] = self.source_sha
        self.repo.publication['classroom_content_sha256'] = self.source_sha
        self.reader = Mock(side_effect=lambda _: deepcopy(self.room))
        self.service = OpenMaicRuntimeActivityStateService(self.events, classroom_reader=self.reader)
        self.trusted = {'runtime_session_id': 'runtime-session-1',
            'learning_session_id': 'learning-session-1', 'upstream_classroom_id': 'classroom-1'}

    def state(self, data=None, **extra):
        return self.service.state(**self.trusted, data=data, **extra)

    def request(self, **changes):
        d = self.state()['activities'][0]
        return {'schemaVersion': snapshots.SCHEMA, 'learningSessionId': 'learning-session-1',
            'sceneId': d['sceneId'], 'sceneIndex': d['sceneIndex'], 'contentSha256': d['contentSha256'],
            'releaseSha256': 'c' * 64, 'mutationId': 'move-1', 'expectedRevision': 0,
            'state': {'position': 2, 'undo': [1]}, **changes}

    def error(self, code, fn):
        with self.assertRaises(ApiError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_manifest_and_fresh_state_prove_source_without_writing(self):
        manifest = self.state(manifest_only=True)
        self.assertEqual(manifest['releaseSha256'], 'c' * 64)
        self.assertEqual(manifest['activities'], [{'sceneId': 'scene-2', 'sceneIndex': 2,
            'contentSha256': hashlib.sha256(self.room['scenes'][2]['content']['html'].encode()).hexdigest()}])
        self.assertEqual(self.state()['activities'][0]['state'], None)
        self.reader.assert_called_once_with('classroom-1')
        self.assertEqual(self.repo.writes, [])
        self.assertEqual(self.repo.events, [])
        self.assertEqual(self.repo.session['runtime_state_json'], canonical(self.original))
        self.assertEqual(self.repo.lock_calls[:6], ['runtime_subject_snapshot', 'child', 'principal',
            'task', 'learning_session', 'formal_pointer'])

    def test_round_trip_and_reentry_preserve_answers_sequence_and_completion(self):
        data = self.request()
        saved = self.state(data)
        self.assertEqual(saved['activity']['revision'], 1)
        self.assertEqual(self.state()['activities'][0], saved['activity'])
        self.repo.authority['runtime_session_id'] = 'runtime-session-2'
        self.trusted['runtime_session_id'] = 'runtime-session-2'
        self.assertEqual(self.state()['activities'][0]['state'], data['state'])
        progress = json.loads(self.repo.session['runtime_state_json'])
        self.assertEqual({k: v for k, v in progress.items() if k != 'activitySnapshots'}, self.original)
        self.assertEqual(self.repo.stream, None)
        self.assertEqual(self.repo.events, [])
        self.assertEqual(self.learning.answer_calls, 0)
        self.assertEqual(self.learning.complete_calls, 0)

    def test_idempotence_conflicts_and_old_tab_cannot_overwrite(self):
        data = self.request()
        saved = self.state(data)
        self.assertEqual(self.state(data), saved)
        self.assertEqual(len(self.repo.writes), 1)
        self.error('textbook_activity_mutation_conflict', lambda: self.state({**data, 'state': {'position': 3}}))
        self.error('textbook_activity_revision_conflict', lambda: self.state({**data, 'mutationId': 'old-tab'}))
        current = self.state({**data, 'expectedRevision': 1, 'mutationId': 'move-2', 'state': {'position': 3}})
        self.assertEqual(self.state(data), current)
        self.assertEqual(len(self.repo.writes), 2)

    def test_post_cannot_change_release_scene_content_or_learning_session(self):
        data = self.request()
        for changes in ({'learningSessionId': 'other'}, {'sceneId': 'scene-3'}, {'sceneIndex': 3},
                        {'releaseSha256': 'd' * 64}, {'contentSha256': 'd' * 64}):
            self.error('textbook_activity_state_identity', lambda changes=changes: self.state({**data, **changes}))
        self.assertEqual(self.repo.writes, [])

    def test_grade_principal_expiry_and_probe_have_no_write_authority(self):
        data = self.request()
        self.repo.child['grade_code'] = 'primary_2'
        with self.assertRaises(ApiError):
            self.state(data)
        self.repo.child['grade_code'] = 'primary_1'
        self.repo.principal['child_id'] = 'other-child'
        with self.assertRaises(ApiError):
            self.state(data)
        self.repo.principal['child_id'] = 'child-1'
        self.repo.authority['runtime_expires_at'] = NOW - 1
        self.error('runtime_event_session_expired', lambda: self.state(data))
        self.repo.authority['runtime_expires_at'] = NOW + 1
        with self.assertRaises(ApiError):
            self.service.state(**{**self.trusted, 'runtime_session_id': 'probe-session'}, data=data)
        self.assertEqual(self.repo.writes, [])

    def test_missing_formal_publication_and_wrong_source_fail_closed(self):
        self.repo.publication = None
        self.error('runtime_activity_authority_invalid', self.state)
        self.repo.publication = {'publication_receipt_hash': 'c' * 64, 'classroom_content_sha256': self.source_sha}
        self.room['scenes'][2]['content']['html'] += '<p>changed</p>'
        self.error('runtime_activity_source_unavailable', self.state)
        self.assertEqual(self.repo.writes, [])

    def test_identity_rechecked_after_remote_read(self):
        def changed(_):
            self.repo.principal['child_id'] = 'other-child'
            return deepcopy(self.room)
        self.reader.side_effect = changed
        with self.assertRaises(ApiError):
            self.state()
        self.assertEqual(self.repo.writes, [])

    def test_bounded_storage_and_malformed_state_preserve_existing_bytes(self):
        data = self.request()
        original = self.repo.session['runtime_state_json']
        with patch.object(snapshots, 'MAX_STORED_BYTES', 10):
            self.error('textbook_activity_state_capacity', lambda: self.state(data))
        self.assertEqual(self.repo.session['runtime_state_json'], original)
        self.error('textbook_activity_state_invalid', lambda: self.state({**data, 'state': {'constructor': 1}}))
        self.repo.session['runtime_state_json'] = '[]'
        self.error('textbook_activity_state_unavailable', self.state)
        self.assertEqual(self.repo.writes, [])

    def test_http_boundary_requires_gateway_identity_and_strict_json(self):
        import routes.internal.openmaic_runtime as routes
        app = Flask(__name__)
        app.register_blueprint(routes.internal_openmaic_runtime_bp, url_prefix='/internal/learning/openmaic')
        headers = {'X-Mira-Runtime-Session': 'runtime-session-1',
            'X-Mira-Learning-Session': 'learning-session-1', 'X-Mira-Runtime-Classroom-Id': 'classroom-1'}
        with patch.object(routes, '_authorize', return_value={'sourceName': 'openmaic-runtime-gateway'}), \
             patch.object(routes, '_runtime_event_service', return_value=self.events), \
             patch.object(routes, 'openmaic_full_runtime_service', return_value=SimpleNamespace(
                 client=SimpleNamespace(get_classroom=self.reader))):
            client = app.test_client()
            self.assertEqual(client.get('/internal/learning/openmaic/runtime/activity-manifest', headers=headers).status_code, 200)
            self.assertEqual(client.get('/internal/learning/openmaic/runtime/activity-state').status_code, 400)
            data = self.request()
            duplicate = json.dumps(data)[:-1] + ',"mutationId":"duplicate"}'
            self.assertEqual(client.post('/internal/learning/openmaic/runtime/activity-state', headers=headers,
                data=duplicate, content_type='application/json').status_code, 400)
            self.assertEqual(client.post('/internal/learning/openmaic/runtime/activity-state', headers=headers,
                data='x' * (384 * 1024 + 1), content_type='application/json').status_code, 413)
            self.assertEqual(client.post('/internal/learning/openmaic/runtime/activity-state', headers=headers,
                json=data).status_code, 200)
            self.assertEqual(client.get('/internal/learning/openmaic/runtime/activity-state', headers=headers)
                .get_json()['activities'][0]['state'], data['state'])
        with patch.object(routes, '_authorize', return_value={'sourceName': 'other'}):
            self.assertEqual(app.test_client().get('/internal/learning/openmaic/runtime/activity-state', headers=headers).status_code, 403)

    def test_repository_publication_is_exact_and_state_update_excludes_evidence(self):
        repo = OpenMaicRuntimeEventRepository(None)
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = [self.repo.publication]
        self.assertEqual(repo.get_activity_publication(conn, authority=self.repo.authority), self.repo.publication)
        sql, params = conn.execute.call_args.args
        self.assertIn("receipt.publication_status='published'", sql)
        self.assertIn("audio.state='auto_validated'", sql)
        self.assertEqual(params[:4], ('runtime-row-1', 'build-item-1', 'release-1', 'a' * 64))
        repo.save_activity_state(conn, authority=self.repo.authority, runtime_state_json='{}', now=NOW)
        sql, params = conn.execute.call_args.args
        self.assertEqual(sql.split(' WHERE ')[0], 'UPDATE learning_sessions SET runtime_state_json=?,updated_at=?')
        self.assertEqual(params[-5:], ('learning-session-1', 'family-1', 'child-1', 'course-1', '1'))


if __name__ == '__main__':
    unittest.main()
