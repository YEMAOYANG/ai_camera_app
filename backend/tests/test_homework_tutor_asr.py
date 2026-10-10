"""Owned WAV transcription, durable receipts and zero blind paid retries.

SQLite and temporary assets only. Qwen/OpenMAIC transport and budget are fakes.
"""
import base64
import io
import json
import unittest
from unittest.mock import Mock, patch
import wave

from flask import Flask
from core.errors import ApiError
from services.homework_tutor_asr_service import (
    HomeworkTutorAsrService, MAX_AUDIO_BYTES, audio_details,
)
from tests import test_homework_analysis as fixture


def recording(*, rate=16000, channels=1, sample_width=2, seconds=0.1):
    body = io.BytesIO()
    with wave.open(body, 'wb') as output:
        output.setnchannels(channels)
        output.setsampwidth(sample_width)
        output.setframerate(rate)
        output.writeframes(b'\0' * (round(seconds * rate) * channels * sample_width))
    return body.getvalue()


class HomeworkTutorAsrTest(unittest.TestCase):
    create = fixture.HomeworkTest.create
    upload = fixture.HomeworkTest.upload
    ready = fixture.HomeworkTest.ready
    error = fixture.HomeworkTest.error
    events = fixture.HomeworkTest.events

    def setUp(self):
        fixture.HomeworkTest.setUp(self)
        self.submission = self.ready()
        self.item = self.submission['items'][0]
        self.now = self.clock()
        self.service.clock = lambda: self.now
        self.budget.issue_homework_authorization.reset_mock()
        self.asr_transport = Mock(return_value={'success': True, 'text': '老师，这道题为什么这样做？'})
        self.asr = HomeworkTutorAsrService(self.service, transport=self.asr_transport)
        self.wav = recording()

    def ask(self, key='voice1', *, audio=None, token='student-a', revision=None):
        return self.asr.transcribe(token, self.submission['id'], self.item['id'],
            {'itemRevision': self.item['revision'] if revision is None else revision,
             'idempotencyKey': key}, self.wav if audio is None else audio)

    def read(self, key='voice1', *, token='student-a', receipt=None):
        return self.asr.get(token, self.submission['id'], self.item['id'],
            transcription_id=receipt, item_revision=self.item['revision'], idempotency_key=key)

    def action(self):
        return self.db.execute("SELECT * FROM homework_actions WHERE idempotency_key LIKE 'asr:%'").fetchone()

    def test_native_response_same_key_replay_and_get_have_one_dispatch_and_no_assessment(self):
        events = len(self.events())
        result = self.ask()
        receipt = result['transcription']
        self.assertEqual(receipt['status'], 'ready')
        self.assertEqual(receipt['transcript'], '老师，这道题为什么这样做？')
        self.assertRegex(receipt['id'], r'^hwtr_[a-f0-9]{56}$')
        self.assertEqual(self.ask(), result)
        self.assertEqual(self.read(), result)
        self.assertEqual(self.read(receipt=receipt['id']), result)
        self.asr_transport.assert_called_once()
        self.budget.issue_homework_authorization.assert_called_once_with(
            submission_id=self.submission['id'], item_id=self.item['id'], revision=self.item['revision'])
        headers = self.asr_transport.call_args.args[1]
        self.assertEqual(headers['X-Mira-Runtime-Session'], 'homework-asr:' + receipt['id'])
        self.assertEqual(headers['X-Mira-Paid-Budget-Required'], '1')
        self.assertEqual(len(self.events()), events)
        state = json.loads(self.action()['result_json'])
        journal = json.loads(self.store.read(state['responseJournalKey']))
        self.assertNotIn('audio', journal)
        self.assertNotIn('storageKey', state['audio'])
        self.assertEqual(state['audio']['durationMs'], 100)

    def test_bad_audio_shape_is_rejected_before_reserving_or_budget(self):
        for body in [recording(rate=8000), recording(channels=2), recording(sample_width=1),
                     recording(seconds=60.1), self.wav[:-2], self.wav + b'extra',
                     b'not audio', b'x' * (MAX_AUDIO_BYTES + 1)]:
            with self.subTest(length=len(body)):
                with self.assertRaises(ApiError):
                    self.ask(audio=body)
        self.assertIsNone(self.action())
        self.budget.issue_homework_authorization.assert_not_called()
        self.asr_transport.assert_not_called()

    def test_real_wave_codec_must_be_pcm_not_mime(self):
        compressed = bytearray(self.wav)
        compressed[20:22] = (3).to_bytes(2, 'little')
        self.error('homework_asr_audio_invalid', lambda: audio_details(bytes(compressed)))

    def test_audio_changed_under_one_key_is_conflict_without_second_call(self):
        self.ask()
        self.error('homework_asr_conflict', lambda: self.ask(audio=recording(seconds=0.2)))
        self.assertEqual(self.asr_transport.call_count, 1)

    def test_scope_is_real_consented_same_family_child_and_exact_item_revision(self):
        self.error('homework_not_found', lambda: self.ask(token='student-b'))
        self.error('homework_revision_conflict', lambda: self.ask(revision=True))
        self.error('homework_revision_conflict', lambda: self.ask(revision=99))
        self.db.execute('UPDATE homework_submissions SET source=? WHERE id=?',
            ('paid_validation', self.submission['id']))
        self.db.raw.commit()
        self.error('homework_asr_scope_invalid', self.ask)
        self.asr_transport.assert_not_called()

    def test_budget_refusal_records_failed_with_reason_and_no_dispatch(self):
        self.budget.issue_homework_authorization.side_effect = ApiError('learning_budget_exhausted', 'fixture', 403)
        result = self.ask()
        self.assertEqual(result['transcription']['status'], 'failed')
        self.assertEqual(result['transcription']['errorCode'], 'learning_budget_exhausted')
        self.assertIsNone(json.loads(self.action()['result_json'])['dispatchedAt'])
        self.asr_transport.assert_not_called()
        self.assertEqual(self.ask(), result)
        self.assertEqual(self.budget.issue_homework_authorization.call_count, 1)

    def test_unknown_transport_never_repeats_and_retains_no_microphone_file(self):
        self.asr_transport.side_effect = TimeoutError('fixture unknown outcome')
        result = self.ask()
        self.assertEqual(result['transcription']['status'], 'unknown')
        self.assertEqual(self.ask(), result)
        self.assertEqual(self.read(), result)
        self.assertEqual(self.asr_transport.call_count, 1)
        self.assertFalse(list(self.store.root.rglob('*.json'))[-1:] and
            any('question.wav' in str(path) for path in self.store.root.rglob('*')))

    def test_concurrent_same_key_observes_reservation_and_dispatches_once(self):
        nested = []
        def transport(audio, headers):
            nested.append(self.ask())
            return {'success': True, 'text': '先数一数'}
        self.asr_transport.side_effect = transport
        result = self.ask()
        self.assertEqual(nested[0]['transcription']['status'], 'working')
        self.assertEqual(result['transcription']['status'], 'ready')
        self.assertEqual(self.asr_transport.call_count, 1)

    def test_expired_working_is_unknown_but_late_response_becomes_ready(self):
        during = []
        def transport(audio, headers):
            self.now += 46000
            during.append(self.read())
            return {'success': True, 'text': '这样数更容易'}
        self.asr_transport.side_effect = transport
        result = self.ask()
        self.assertEqual(during[0]['transcription']['status'], 'unknown')
        self.assertEqual(result['transcription']['status'], 'ready')
        self.assertEqual(self.read(), result)
        self.assertEqual(self.asr_transport.call_count, 1)

    def test_journal_survives_exit_before_database_link_and_get_recovers_without_call(self):
        put = self.store.put_response
        def exit_after_fsync(body, *, namespace):
            put(body, namespace=namespace)
            raise SystemExit('isolated exit')
        with patch.object(self.store, 'put_response', side_effect=exit_after_fsync):
            with self.assertRaises(SystemExit):
                self.ask()
        self.assertEqual(json.loads(self.action()['result_json'])['state'], 'working')
        recovered = self.read()
        self.assertEqual(recovered['transcription']['status'], 'ready')
        self.assertEqual(self.asr_transport.call_count, 1)
        self.assertEqual(self.budget.issue_homework_authorization.call_count, 1)

    def test_database_link_failure_recovers_saved_response_without_provider_replay(self):
        update = self.asr._update
        fault = {'raised': False}
        def fail_once(conn, identity, value):
            if value['state'] == 'ready' and not fault['raised']:
                fault['raised'] = True
                raise RuntimeError('isolated commit window')
            return update(conn, identity, value)
        with patch.object(self.asr, '_update', side_effect=fail_once):
            self.assertEqual(self.ask()['transcription']['status'], 'unknown')
        self.assertEqual(self.read()['transcription']['status'], 'ready')
        self.assertEqual(self.asr_transport.call_count, 1)

    def test_invalid_returned_bytes_preserved_and_failed_without_automatic_retry(self):
        for response in [{'success': True, 'text': ''},
                         {'success': True, 'text': 'x' * 1001},
                         {'success': True, 'text': '\ud800'},
                         {'httpStatus': 200, 'responseEnvelopeBase64': base64.b64encode(b'{"success":true,"text":"one","text":"two"}').decode(), 'truncated': False},
                         {'httpStatus': 500, 'responseEnvelopeBase64': base64.b64encode(b'{}').decode(), 'truncated': False}]:
            with self.subTest(response=str(response)[:60]):
                key = 'invalid' + str(self.asr_transport.call_count)
                self.asr_transport.return_value = response
                result = self.ask(key)
                self.assertIn(result['transcription']['status'], {'failed', 'unknown'})
                calls = self.asr_transport.call_count
                self.assertEqual(self.ask(key), result)
                self.assertEqual(self.asr_transport.call_count, calls)

    def test_get_scope_revision_and_unknown_receipt_do_not_dispatch(self):
        result = self.ask()
        self.error('homework_not_found', lambda: self.read(token='student-b'))
        self.error('homework_asr_not_found', lambda: self.read(key='missing'))
        self.error('homework_asr_not_found', lambda: self.read(receipt='hwtr_' + 'f' * 56))
        self.db.execute('UPDATE homework_items SET revision=2 WHERE id=?', (self.item['id'],))
        self.db.raw.commit()
        self.error('homework_asr_stale', lambda: self.asr.get('student-a', self.submission['id'], self.item['id'],
            transcription_id=result['transcription']['id']))
        self.assertEqual(self.asr_transport.call_count, 1)

    def test_http_received_malformed_json_utf8_nonfinite_and_error_are_journaled_not_unknown(self):
        for index, (code, raw) in enumerate([(200, b'{"success":true,"text":'),
                                            (200, b'\xff\xfe'),
                                            (200, b'{"success":true,"text":"ok","extra":NaN}'),
                                            (503, b'{"success":false,"errorCode":"TRANSCRIPTION_FAILED"}')]):
            with self.subTest(status=code, raw=raw[:30]):
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.code = code
                response.read.return_value = raw
                opener = Mock()
                if code >= 400:
                    from urllib.error import HTTPError
                    opener.open.side_effect = HTTPError('http://127.0.0.1:3100/api/transcription', code,
                        'synthetic provider error', {}, io.BytesIO(raw))
                else:
                    opener.open.return_value = response
                self.asr_transport.side_effect = self.asr._request
                with patch('urllib.request.build_opener', return_value=opener):
                    result = self.ask('httpbody' + str(index))
                self.assertEqual(result['transcription']['status'], 'failed')
                self.assertEqual(result['transcription']['errorCode'], 'homework_asr_response_invalid')
                action = self.db.execute('SELECT * FROM homework_actions WHERE id=?',
                    (result['transcription']['id'],)).fetchone()
                state = json.loads(action['result_json'])
                saved = json.loads(self.store.read(state['responseJournalKey']))
                self.assertEqual(base64.b64decode(saved['response']['responseEnvelopeBase64']), raw)
                calls = self.asr_transport.call_count
                self.assertEqual(self.ask('httpbody' + str(index)), result)
                self.assertEqual(self.read('httpbody' + str(index)), result)
                self.assertEqual(self.asr_transport.call_count, calls)

    def test_live_unlinked_journal_is_retained_by_purge_and_ready_delete_removes_it(self):
        put = self.store.put_response
        def exit_after_fsync(body, *, namespace):
            put(body, namespace=namespace)
            raise SystemExit('isolated exit')
        with patch.object(self.store, 'put_response', side_effect=exit_after_fsync):
            with self.assertRaises(SystemExit):
                self.ask()
        state = json.loads(self.action()['result_json'])
        key = state['responseJournalKey']
        with self.service.repository.transaction() as conn:
            self.service._enqueue_delete(conn, key)
        self.service.purge_files()
        self.assertTrue(self.store.read(key))
        self.assertEqual(self.read()['transcription']['status'], 'ready')
        self.service.delete('parent-a', self.submission['id'], {'revision': self.submission['revision']})
        self.error('homework_asset_missing', lambda: self.store.read(key))
        action = self.action()
        if action:
            revoked = json.loads(action['result_json'])
            self.assertFalse(revoked.get('transcript'))
            self.assertTrue(revoked['dispatchedAt'])

    def test_per_paper_cap_is_thirty_dispatches(self):
        for index in range(30):
            self.assertEqual(self.ask('bounded' + str(index))['transcription']['status'], 'ready')
        denied = self.ask('bounded31')['transcription']
        self.assertEqual(denied['status'], 'failed')
        self.assertEqual(denied['errorCode'], 'homework_asr_budget_exceeded')
        self.assertEqual(self.asr_transport.call_count, 30)

    def test_delete_during_external_request_enqueues_and_purges_late_response(self):
        def transport(audio, headers):
            self.service.delete('parent-a', self.submission['id'], {'revision': self.submission['revision']})
            return {'success': True, 'text': 'late private question'}
        self.asr_transport.side_effect = transport
        self.error('homework_asr_stale', self.ask)
        self.assertEqual(list(self.store.root.rglob('*.json')), [])

    def test_transport_pins_server_asr_and_never_follows_redirects(self):
        raw = json.dumps({'success': True, 'text': '请问老师'}).encode()
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.code = 200
        response.read.return_value = raw
        opener = Mock()
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener) as build:
            returned = self.asr._request(self.wav, {'X-Mira-Runtime-Session': 'homework-asr:test'})
        request = opener.open.call_args.args[0]
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 45)
        self.assertEqual(request.full_url, 'http://127.0.0.1:3100/api/transcription')
        self.assertIn(b'qwen-asr', request.data)
        self.assertIn(b'qwen3-asr-flash', request.data)
        self.assertIn(b'name="language"\r\n\r\nauto', request.data)
        self.assertIsNone(build.call_args.args[0].redirect_request(None))
        self.assertEqual(self.asr._transcript(returned), '请问老师')

    def test_multipart_routes_validate_actual_wave_and_get_by_key_and_id(self):
        from routes.api.v2.student_homework_tutor_asr import student_homework_tutor_asr_bp
        app = Flask(__name__)
        app.register_blueprint(student_homework_tutor_asr_bp, url_prefix='/api/v2/student/learning')
        client = app.test_client()
        path = '/api/v2/student/learning/homework/' + self.submission['id'] + '/items/' + self.item['id'] + '/tutor/transcribe'
        headers = {'Authorization': 'Bearer student-a'}
        with patch('routes.api.v2.student_homework_tutor_asr.service', return_value=self.service), \
             patch('routes.api.v2.student_homework_tutor_asr.HomeworkTutorAsrService', return_value=self.asr):
            result = client.post(path, data={'itemRevision': '1', 'idempotencyKey': 'route1',
                'audio': (io.BytesIO(self.wav), 'anything.bin', 'application/octet-stream')}, headers=headers)
            self.assertEqual(result.status_code, 200)
            value = result.get_json()
            self.assertEqual(client.get(path, query_string={'itemRevision': '1', 'idempotencyKey': 'route1'}, headers=headers).get_json(), value)
            self.assertEqual(client.get(path + '/' + value['transcription']['id'], headers=headers).get_json(), value)
            self.assertEqual(client.post(path, data={'itemRevision': '1', 'idempotencyKey': 'evil', 'providerId': 'client-model',
                'audio': (io.BytesIO(self.wav), 'question.wav')}, headers=headers).status_code, 400)
            self.assertEqual(client.get(path + '?itemRevision=1&itemRevision=2&idempotencyKey=route1', headers=headers).status_code, 400)
        self.assertEqual(self.asr_transport.call_count, 1)


if __name__ == '__main__':
    unittest.main()
