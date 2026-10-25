from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

from itsdangerous import URLSafeTimedSerializer

from core.security import now_ms
from scripts import verify_course_storage_student as verification


class FakeGateway:
    def __init__(self, identity, release, signer):
        self.identity, self.release, self.signer = identity, release, signer
        self.cookies, self.paths, self.requests = {}, [], 0
        self.closed = False
        self.invalid_audio = False
        self.expose_answer = False

    def get(self, path, *, limit):
        self.paths.append(path)
        self.requests += 1
        cid = self.release['classroomId']
        if path == '/health':
            return 200, {}, b'{"service":"mira-openmaic-runtime-gateway","sourceVersion":"fixture"}'
        if path.startswith('/mira/textbook-launch?'):
            ticket = parse_qs(urlsplit(path).query)['ticket'][0]
            self.authority = self.signer.loads(ticket[5:])
            runtime = {**self.authority, 'purpose': 'runtime', 'expiresAt': now_ms() + 14400_000}
            self.cookies['mira_openmaic_runtime'] = 'tbpr_' + self.signer.dumps(runtime)
            return 303, {'location': '/classroom/' + cid + '?mira=1&textbook=1'}, b''
        if path.startswith('/classroom/'):
            return 200, {}, b'<!doctype html><html><body>Native</body></html>'
        if path.startswith('/api/classroom?'):
            question = {'id': 'question'}
            if self.expose_answer:
                question['answer'] = ['A']
            body = {'success': True, 'classroom': {'id': cid, 'stage': {'id': cid, 'fixedTextbook': True},
                    'scenes': [{'id': 'scene', 'type': 'quiz', 'content': {'questions': [question]}}]}}
            return 200, {'content-type': 'application/json'}, verification.json_bytes(body)
        if path == self.release['media'][0]['path']:
            return 200, {'content-type': 'audio/wav'}, b'broken' if self.invalid_audio else b'fixture-audio'
        raise AssertionError('unexpected read')

    def close(self):
        self.closed = True
        self.cookies.clear()


class VerifyCourseStorageStudentTests(unittest.TestCase):
    def setUp(self):
        self.identity = {'content_key': 'a' * 64, 'student_session_id': 'existing-student-session',
                         'learning_session_id': 'existing-learning-session', 'grade_selection_revision': 1}
        cid = 'tbpub_' + 'a' * 24
        self.release = {'sha256': 'b' * 64, 'classroomId': cid,
                        'classroom': {'scenes': [{'id': 'scene'}]},
                        'media': [{'path': '/api/classroom-media/' + cid + '/audio/one.wav',
                                   'mimeType': 'audio/wav', 'byteSize': len(b'fixture-audio'),
                                   'sha256': hashlib.sha256(b'fixture-audio').hexdigest()}]}
        self.signer = URLSafeTimedSerializer('isolated-fixture', salt='mira-fixed-textbook-runtime-v1',
                                            signer_kwargs={'digest_method': hashlib.sha256})
        self.gateway = FakeGateway(self.identity, self.release, self.signer)
        self.before = {'business': {'learning_sessions': {'rows': 1, 'sha256': 'stable'}},
                       'guard': {'rows': 4, 'cutoff': 100, 'existing': {'rows': 4, 'sha256': 'stable'}}}
        self.after = deepcopy(self.before)
        self.after['guard']['rows'] = 10
        self.snapshot = Mock(side_effect=lambda database, **kwargs: deepcopy(self.after if kwargs else self.before))

    def verify(self):
        return verification.verify_student_entry(database=object(), identity=self.identity, release=self.release,
            signer=self.signer, gateway=self.gateway, snapshot=self.snapshot)

    def test_exchange_classroom_and_audio_are_reads_and_tokens_stay_in_memory(self):
        result = self.verify()
        self.assertTrue(result['ok'])
        self.assertEqual(result['gatewayReads'], 5)
        self.assertEqual(result['guardAuditAppends'], 6)
        self.assertEqual(result['businessTablesUnchanged'], 1)
        self.assertEqual(self.gateway.authority['studentSession'], self.identity['student_session_id'])
        self.assertEqual(self.gateway.authority['learningSession'], self.identity['learning_session_id'])
        self.assertEqual(self.gateway.authority['accessScope'], 'published_directory')
        self.assertEqual(self.gateway.authority['release'], self.release['sha256'])
        self.assertFalse(self.gateway.cookies)
        self.assertTrue(self.gateway.closed)
        public = json.dumps(result)
        self.assertNotIn('tbpt_', public)
        self.assertNotIn('tbpr_', public)
        self.assertNotIn(self.identity['student_session_id'], public)
        self.assertNotIn(self.identity['learning_session_id'], public)
        self.assertEqual(result['learningEventsSubmitted'], 0)
        self.assertEqual(result['providerCalls'], 0)

    def test_business_mutation_is_detected_even_when_http_reads_succeed(self):
        self.after['business']['learning_sessions']['sha256'] = 'changed'
        with self.assertRaisesRegex(verification.StudentVerificationError, 'business_database_changed'):
            self.verify()
        self.assertTrue(self.gateway.closed)

    def test_only_new_guard_appends_are_allowed(self):
        self.after['guard']['existing']['sha256'] = 'changed'
        with self.assertRaisesRegex(verification.StudentVerificationError, 'existing_guard_audit_changed'):
            self.verify()

    def test_bad_audio_still_clears_cookies_and_checks_business_rows(self):
        self.gateway.invalid_audio = True
        with self.assertRaisesRegex(verification.StudentVerificationError, 'audio_hash_mismatch'):
            self.verify()
        self.assertFalse(self.gateway.cookies)
        self.assertEqual(self.snapshot.call_count, 2)

    def test_private_quiz_answers_fail_acceptance(self):
        self.gateway.expose_answer = True
        with self.assertRaisesRegex(verification.StudentVerificationError, 'private_answer_exposed'):
            self.verify()

    def test_adaptive_scene_order_must_preserve_exact_published_ids(self):
        self.release['classroom']['scenes'].insert(0, {'id': 'reading'})
        original_get = self.gateway.get
        def get(path, *, limit):
            status, headers, raw = original_get(path, limit=limit)
            if path.startswith('/api/classroom?'):
                body = json.loads(raw)
                body['classroom']['scenes'].append({'id': 'reading', 'type': 'slide'})
                raw = verification.json_bytes(body)
            return status, headers, raw
        self.gateway.get = get
        result = verification.verify_student_entry(database=object(), identity=self.identity, release=self.release,
            signer=self.signer, gateway=self.gateway, snapshot=self.snapshot, expected_scene_ids=['scene', 'reading'])
        self.assertTrue(result['ok'])
        with self.assertRaisesRegex(verification.StudentVerificationError, 'scene_projection_invalid'):
            verification.verify_student_entry(database=object(), identity=self.identity, release=self.release,
                signer=self.signer, gateway=self.gateway, snapshot=self.snapshot, expected_scene_ids=['scene', 'invented'])

    def test_gateway_origin_is_loopback_only_and_has_no_supplied_credentials(self):
        for origin in ('https://external.invalid', 'http://user:password@127.0.0.1:3104',
                       'http://127.0.0.1:3104/path', 'http://127.0.0.1:3104?secret=x', 'http://127.0.0.1'):
            with self.subTest(origin=origin), self.assertRaises(verification.StudentVerificationError):
                verification.GatewayReader(origin)

    def test_missing_existing_identity_does_not_create_or_login(self):
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []
        database = Mock()
        database.transaction.return_value.__enter__ = Mock(return_value=conn)
        database.transaction.return_value.__exit__ = Mock(return_value=False)
        with self.assertRaisesRegex(verification.StudentVerificationError, 'no_valid_existing_identity'):
            verification.select_existing_identity(database)
        self.assertTrue(conn.execute.call_args.args[0].lstrip().startswith('SELECT'))
        self.assertEqual(conn.execute.call_count, 1)

    def test_database_hashing_returns_no_raw_rows_and_excludes_only_guard_audits(self):
        metadata = [{'table_name': table, 'column_name': 'id', 'column_type': 'character varying', 'is_nullable': 'NO'}
                    for table in ('audit_events', 'learning_sessions')]
        statements = []
        def execute(sql, params=()):
            statements.append((sql, params))
            if 'information_schema.columns' in sql:
                return SimpleNamespace(fetchall=lambda: metadata)
            if 'COUNT(*)' in sql:
                return SimpleNamespace(fetchone=lambda: {'row_count': 4, 'cutoff': 100})
            return SimpleNamespace(fetchall=lambda: [{'row_sha256': 'a' * 64}])
        connection = SimpleNamespace(execute=execute)
        database = Mock()
        database.transaction.return_value.__enter__ = Mock(return_value=connection)
        database.transaction.return_value.__exit__ = Mock(return_value=False)
        result = verification.database_snapshot(database)
        self.assertEqual(set(result['business']), {'audit_events', 'learning_sessions'})
        self.assertTrue(all(sql.startswith('SELECT') for sql, _ in statements))
        row_reads = [sql for sql, _ in statements if ' AS row_sha256' in sql]
        self.assertTrue(all('encode(sha256(convert_to(CAST(' in sql and 'SELECT *' not in sql for sql in row_reads))
        self.assertTrue(any('audit_domain IS NULL OR audit_domain<>?' in sql for sql in row_reads))


if __name__ == '__main__':
    unittest.main()
