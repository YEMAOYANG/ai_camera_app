"""Durable iframe continuity must remain isolated from learning evidence."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical
from core.errors import ApiError
from services.textbook_activity_state import SCHEMA, descriptors, load_post_bytes, parse_post
from services.textbook_classroom_service import TextbookClassroomService


class TextbookActivityStateTests(unittest.TestCase):
    def setUp(self):
        # Synthetic releases have no registered native-journey replacement.
        supported = patch('content.textbook_journey.supported', return_value=False)
        supported.start()
        self.addCleanup(supported.stop)
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE learning_sessions (id TEXT PRIMARY KEY,child_id TEXT,course_id TEXT,'
                        'course_version TEXT,runtime_state_json TEXT,updated_at INTEGER)')
        self.original = {'schemaVersion': 'mira.textbook.progress.v1', 'lastSequence': 7,
                         'visited': ['slide'], 'actions': ['speech-1'], 'quiz': {'score': 0},
                         'quizPartial': {'results': [{'questionId': 'q1', 'correct': False}]}}
        for key in ('session-a', 'session-b'):
            self.db.execute('INSERT INTO learning_sessions VALUES (?,?,?,?,?,?)',
                (key, 'child-' + key[-1], 'course', '1', canonical(self.original), 1))
        self.db.commit()
        self.release = {'sha256': 'a' * 64, 'classroomId': 'tbpub_' + 'b' * 24, 'media': [],
                        'classroom': {'scenes': [
                            {'id': 'slide', 'order': 1, 'type': 'slide', 'content': {'type': 'slide'}},
                            {'id': 'game-one', 'order': 2, 'type': 'interactive',
                             'content': {'type': 'interactive', 'html': '<button>one</button>'}},
                            {'id': 'game-two', 'order': 3, 'type': 'interactive',
                             'content': {'type': 'interactive', 'html': '<button>two</button>'}},
                            {'id': 'external', 'order': 4, 'type': 'interactive',
                             'content': {'type': 'interactive', 'url': 'https://external.invalid'}}]}}
        @contextmanager
        def transaction():
            with self.db:
                yield self.db
        self.service = object.__new__(TextbookClassroomService)
        self.service.repository = SimpleNamespace(transaction=transaction)
        self.service.learning = Mock()
        self.service.learning.get_session.side_effect = lambda conn, **kw: dict(conn.execute(
            'SELECT * FROM learning_sessions WHERE id=?', (kw['session_id'],)).fetchone())
        def authority(token):
            if token not in ('session-a', 'session-b'):
                raise ApiError('textbook_session_invalid', 'expired', 401)
            row = dict(self.db.execute('SELECT * FROM learning_sessions WHERE id=?', (token,)).fetchone())
            return {}, {'id': row['child_id'], 'family_id': 'family'}, {}, self.release, {'id': 'course', 'version': '1'}, row
        self.service._authority = Mock(side_effect=authority)

    def state(self, session='session-a'):
        return json.loads(self.db.execute('SELECT runtime_state_json FROM learning_sessions WHERE id=?',
                                          (session,)).fetchone()[0])

    def request(self, *, scene='game-one', revision=0, mutation='mutation-1', state=None, session='session-a'):
        definition = next(item for item in self.service.activity_state(session)['activities']
                          if item['sceneId'] == scene)
        return {'schemaVersion': SCHEMA, **{key: definition[key] for key in ('sceneId', 'sceneIndex', 'contentSha256')},
                'releaseSha256': self.release['sha256'], 'learningSessionId': session, 'expectedRevision': revision,
                'mutationId': mutation, 'state': state or {'position': 2, 'history': [1]}}

    def error(self, code, fn):
        with self.assertRaises(ApiError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_fresh_inline_scope_has_original_hash_and_no_writes(self):
        changes = self.db.total_changes
        result = self.service.activity_state('session-a')
        self.assertEqual(self.db.total_changes, changes)
        self.assertEqual(result['schemaVersion'], SCHEMA)
        self.assertEqual(result['learningSessionId'], 'session-a')
        self.assertEqual(len(result['activities']), 2)
        self.assertEqual(result['activities'][0], {'sceneId': 'game-one', 'sceneIndex': 1,
            'contentSha256': hashlib.sha256(b'<button>one</button>').hexdigest(),
            'revision': 0, 'mutationId': None, 'state': None})

    def test_round_trip_keeps_quiz_actions_sequence_and_other_session_unchanged(self):
        data = self.request()
        first = self.service.activity_state('session-a', data)
        self.assertEqual(first['activity']['revision'], 1)
        self.assertEqual(self.service.activity_state('session-a')['activities'][0], first['activity'])
        stored = self.state()
        self.assertEqual({k: v for k, v in stored.items() if k != 'activitySnapshots'}, self.original)
        self.assertEqual(self.state('session-b'), self.original)
        self.assertEqual(self.service.activity_state('session-b')['activities'][0]['state'], None)
        self.service.activity_state('session-a', self.request(scene='game-two', mutation='other-game'))
        self.assertEqual(self.service.activity_state('session-a')['activities'][0], first['activity'])
        first['activity']['state']['position'] = 99
        self.assertEqual(self.service.activity_state('session-a')['activities'][0]['state']['position'], 2)

    def test_optimistic_conflict_and_idempotence_do_not_overwrite(self):
        data = self.request()
        first = self.service.activity_state('session-a', data)
        changes = self.db.total_changes
        self.assertEqual(self.service.activity_state('session-a', data), first)
        self.assertEqual(self.db.total_changes, changes)
        self.error('textbook_activity_mutation_conflict', lambda: self.service.activity_state(
            'session-a', {**data, 'state': {'position': 4}}))
        self.error('textbook_activity_revision_conflict', lambda: self.service.activity_state(
            'session-a', {**data, 'mutationId': 'stale-tab'}))
        later = self.request(revision=1, mutation='mutation-2', state={'position': 3})
        current = self.service.activity_state('session-a', later)
        self.assertEqual(current['activity']['revision'], 2)
        self.assertEqual(self.service.activity_state('session-a', data), current)
        self.assertEqual(self.service.activity_state('session-a')['activities'][0]['state'], {'position': 3})

    def test_scene_release_content_and_session_authority_are_bound(self):
        good = self.request()
        for change in ({'sceneId': 'slide'}, {'sceneIndex': 2}, {'releaseSha256': 'c' * 64},
                       {'contentSha256': 'd' * 64}, {'sceneId': 'external'}):
            self.error('textbook_activity_state_identity', lambda change=change:
                       self.service.activity_state('session-a', {**good, **change}))
        self.error('textbook_session_invalid', lambda: self.service.activity_state('expired'))
        self.service.activity_state('session-a', good)
        self.release = {**self.release, 'sha256': 'e' * 64}
        self.assertEqual(self.service.activity_state('session-a')['activities'][0]['revision'], 0)
        self.service.activity_state('session-a', self.request(mutation='new-release'))
        self.assertEqual(len(self.state()['activitySnapshots']['releases']), 2)
        self.release = {**self.release, 'sha256': 'a' * 64}
        self.assertEqual(self.service.activity_state('session-a')['activities'][0]['mutationId'], good['mutationId'])

    def test_locked_session_revalidation_refuses_cross_child(self):
        self.service.learning.get_session.side_effect = lambda conn, **kw: {
            'id': kw['session_id'], 'child_id': 'other-child', 'course_id': 'course', 'course_version': '1'}
        self.error('textbook_activity_state_identity', lambda: self.service.activity_state('session-a'))

    def test_cookie_switch_after_get_cannot_write_another_learning_session(self):
        old = self.request()
        self.error('textbook_activity_state_identity', lambda: self.service.activity_state('session-b', old))
        self.assertEqual(self.state('session-a'), self.original)
        self.assertEqual(self.state('session-b'), self.original)
        new = self.request(session='session-b', mutation='new-child')
        accepted = self.service.activity_state('session-b', new)
        self.assertEqual(accepted['learningSessionId'], 'session-b')
        self.assertEqual(accepted['activity']['revision'], 1)
        self.assertEqual(self.state('session-a'), self.original)

    def test_corrupt_saved_progress_is_not_erased_or_replaced_with_fresh(self):
        self.service.activity_state('session-a', self.request())
        progress = self.state()
        snapshot = progress['activitySnapshots']['releases'][self.release['sha256']]['scenes']['game-one']
        snapshot['state'] = {'__proto__': {'bad': True}}
        self.db.execute('UPDATE learning_sessions SET runtime_state_json=? WHERE id=?',
                        (canonical(progress), 'session-a'))
        self.db.commit()
        before = self.state()
        self.error('textbook_activity_state_unavailable', lambda: self.service.activity_state('session-a'))
        self.assertEqual(self.state(), before)

    def test_unbounded_non_json_unsafe_and_non_exact_payloads_rejected(self):
        good = self.request()
        deep = {}
        node = deep
        for _ in range(18):
            node['nested'] = {}
            node = node['nested']
        for value in ([], deep, {'items': [None] * 4096}, {'n': float('nan')},
                      {'n': float('inf')}, {'n': 2**53}, {'n': 10**1000},
                      {'x': 'x' * 16385}, {'__proto__': {}}, {'nested': {'constructor': {}}}):
            self.error('textbook_activity_state_invalid', lambda value=value: parse_post({**good, 'state': value}))
        for change in ({'score': 100}, {'expectedRevision': True}, {'sceneIndex': True}, {'mutationId': ''}):
            self.error('textbook_activity_state_invalid', lambda change=change: parse_post({**good, **change}))
        oversized = {**good, 'state': {str(i): 'x' * 10000 for i in range(7)}}
        self.error('textbook_activity_state_invalid', lambda: parse_post(oversized))
        for raw in (b'{}', b'{"state":{},"state":{}}', b'{"state":NaN}', b'[' * 1100,
                    b'x' * (64 * 1024 + 1)):
            self.error('textbook_activity_state_invalid', lambda raw=raw: load_post_bytes(raw))

    def test_native_replacements_keep_their_existing_progress_owner(self):
        with patch('content.textbook_journey.supported', return_value=True), \
             patch('content.textbook_journey.definition', return_value=SimpleNamespace(
                 plan={'sceneIds': {'games': 'game-one', 'challenge': 'game-two'}})), \
             patch('content.textbook_journey.ordered_scenes', return_value=self.release['classroom']['scenes']):
            self.assertEqual(descriptors(self.release), [])

    def test_validation_exposes_only_source_binding_metadata_without_mutating_release(self):
        frozen = deepcopy(self.release)
        authority = self.service._authority('session-a')
        self.service._authority.return_value = ({'expiresAt': 9007199254740991}, *authority[1:])
        self.service._authority.side_effect = None
        result = self.service.validate('session-a')
        self.assertEqual(result['releaseSha256'], self.release['sha256'])
        self.assertEqual(result['activityPersistence'], descriptors(self.release))
        self.assertEqual(self.release, frozen)
        self.assertNotIn('state', canonical(result['activityPersistence']))

    def test_total_capacity_rejects_new_write_without_pruning_or_losing_existing_progress(self):
        self.service.activity_state('session-a', self.request())
        before = self.state()
        update = self.request(revision=1, mutation='more-work', state={'position': 3})
        with patch('services.textbook_activity_state.MAX_STORED_BYTES', 1):
            self.error('textbook_activity_state_capacity', lambda: self.service.activity_state('session-a', update))
        self.assertEqual(self.state(), before)
        self.assertEqual(self.service.activity_state('session-a')['activities'][0]['state']['position'], 2)
        # A new release cannot evict a previously saved one to make room.
        with patch('services.textbook_activity_state.MAX_RELEASE_SCOPES', 1):
            self.release = {**self.release, 'sha256': 'e' * 64}
            self.error('textbook_activity_state_capacity', lambda: self.service.activity_state(
                'session-a', self.request(mutation='new-release')))
        self.assertEqual(self.state(), before)

    def test_get_response_budget_counts_escaped_unicode_and_keeps_saved_data(self):
        self.service.activity_state('session-a', self.request(state={'word': '中' * 1000}))
        result = self.service.activity_state('session-a')
        before = self.state()
        utf8_size = len(canonical(result).encode('utf-8'))
        with patch('services.textbook_activity_state.MAX_RESPONSE_BYTES', utf8_size):
            self.error('textbook_activity_state_unavailable', lambda: self.service.activity_state('session-a'))
        self.assertEqual(self.state(), before)


class TextbookActivityStateRouteTests(unittest.TestCase):
    def setUp(self):
        from flask import Flask
        from routes.internal.textbooks import internal_textbooks_bp
        app = Flask(__name__)
        app.register_blueprint(internal_textbooks_bp, url_prefix='/internal/learning/textbooks')
        self.client = app.test_client()
        self.authorize = patch('routes.internal.textbooks.authorize')
        self.guard = self.authorize.start()
        self.addCleanup(self.authorize.stop)
        provider = patch('routes.internal.textbooks.textbook_classroom_service')
        self.service = provider.start().return_value
        self.addCleanup(provider.stop)
        self.service.activity_state.return_value = {'ok': True}
        self.path = '/internal/learning/textbooks/runtime/activity-state'
        self.good = {'schemaVersion': SCHEMA, 'sceneId': 'game', 'sceneIndex': 0,
                     'releaseSha256': 'a' * 64, 'contentSha256': 'b' * 64,
                     'learningSessionId': 'session-a', 'expectedRevision': 0, 'mutationId': 'move-1', 'state': {}}

    def test_get_and_post_use_existing_internal_guard_and_runtime_token(self):
        response = self.client.get(self.path, headers={'X-Mira-Textbook-Token': 'bound-runtime'})
        self.assertEqual(response.status_code, 200)
        self.service.activity_state.assert_called_once_with('bound-runtime', None)
        response = self.client.post(self.path, json=self.good, headers={'X-Mira-Textbook-Token': 'bound-runtime'})
        self.assertEqual(response.status_code, 200)
        self.service.activity_state.assert_called_with('bound-runtime', self.good)
        self.assertEqual(self.guard.call_count, 2)

    def test_internal_body_boundary_rejects_oversize_duplicate_and_non_json(self):
        for raw, content_type, status in (
            (b'x' * (64 * 1024 + 1), 'application/json', 413),
            (b'{"state":{},"state":{}}', 'application/json', 400),
            (b'{"state":NaN}', 'application/json', 400),
            (b'{}', 'text/plain', 415),
        ):
            with self.subTest(status=status):
                self.assertEqual(self.client.post(self.path, data=raw, content_type=content_type).status_code, status)
        self.service.activity_state.assert_not_called()

    def test_internal_authorization_failure_never_reads_or_saves_progress(self):
        self.guard.side_effect = ApiError('internal_denied', 'denied', 403)
        self.assertEqual(self.client.get(self.path).status_code, 403)
        self.service.activity_state.assert_not_called()


if __name__ == '__main__':
    unittest.main()
