"""Owned homework questions transcribed once through the existing Qwen ASR.

Only a digest of microphone input is retained. Returned provider bytes are
journaled privately before the database link, so a GET can recover a lost reply
without repeating a paid request. ASR never creates learning assessment data.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import uuid
import wave
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request

from core.errors import ApiError
from services.homework_service import canonical, digest, identifier, parsed

SCHEMA = 'mira.homework-tutor-asr.v1'
RESPONSE_SCHEMA = 'mira.homework-tutor-asr-response.v1'
MAX_AUDIO_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TRANSCRIPT_CHARACTERS = 1000
MAX_CALLS = 30
TIMEOUT_SECONDS = 45
PROVIDER_ID = 'qwen-asr'
MODEL_ID = 'qwen3-asr-flash'


def audio_details(audio):
    if not isinstance(audio, bytes) or not 44 <= len(audio) <= MAX_AUDIO_BYTES:
        raise ApiError('homework_asr_audio_size', '请录制不超过60秒的语音', 413)
    if (audio[:4] != b'RIFF' or audio[8:12] != b'WAVE'
            or int.from_bytes(audio[4:8], 'little') + 8 != len(audio)):
        raise ApiError('homework_asr_audio_invalid', '语音格式无效，请重新录制', 400)
    try:
        with wave.open(io.BytesIO(audio), 'rb') as source:
            channels, sample_width, rate, frames, compression, _ = source.getparams()
            if (channels != 1 or sample_width != 2 or rate != 16000
                    or compression != 'NONE' or not 1 <= frames <= 60 * 16000
                    or len(source.readframes(frames + 1)) != frames * 2):
                raise ValueError('unsupported recording')
    except (wave.Error, EOFError, ValueError, OSError):
        raise ApiError('homework_asr_audio_invalid', '请使用16kHz单声道PCM语音，最长60秒', 400)
    return {'sha256': hashlib.sha256(audio).hexdigest(), 'bytes': len(audio),
            'sampleRate': rate, 'channels': channels, 'sampleWidth': sample_width,
            'frames': frames, 'durationMs': round(frames * 1000 / rate)}


class HomeworkTutorAsrService:
    def __init__(self, host, *, transport=None):
        self.host = host
        self.transport = transport or self._request

    def _scope(self, conn, principal, identity, item_id, item_revision=None, *, lock=False):
        row = self.host.repository.submission(conn, principal['family_id'], identity,
                child=principal['child_id'], lock=lock)
        item = self.host._item(conn, identity, item_id)
        if item_revision is not None and (type(item_revision) is not int or item_revision != item['revision']):
            raise ApiError('homework_revision_conflict', '题目已更新，请刷新', 409)
        result = parsed(item['result_json'], {})
        if (row['source'] not in {'parent_app', 'document_camera'} or not row['consent_at']
                or not isinstance(result.get('prompt'), str) or not result['prompt'].strip()):
            raise ApiError('homework_asr_scope_invalid', '这份作业暂不支持语音提问', 403)
        return row, item

    @staticmethod
    def _key(key):
        return 'asr:' + hashlib.sha256(identifier(key).encode()).hexdigest()

    @staticmethod
    def _identity(row, item_id, key):
        return 'hwtr_' + digest({'schema': SCHEMA, 'familyId': row['family_id'],
            'childId': row['child_id'], 'submissionId': row['id'], 'itemId': item_id,
            'idempotencyKey': key})[:56]

    @staticmethod
    def _public(identity, value):
        return {'ok': True, 'transcription': {'id': identity, 'status': value['state'],
            'transcript': value.get('transcript', ''), 'errorCode': value.get('errorCode')}}

    def _existing(self, conn, identity, item_id, key):
        return conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=? AND idempotency_key=?',
            (identity, item_id, key)).fetchone()

    def _validate_action(self, action, row, item):
        value = parsed(action['result_json'], {})
        if (value.get('schema') != SCHEMA or value.get('itemRevision') != item['revision']
                or value.get('submissionRevision') != row['revision']
                or value.get('state') not in {'working', 'ready', 'unknown', 'failed'}):
            raise ApiError('homework_asr_stale', '这次语音提问已失效，请重新打开题目', 409)
        return value

    def _update(self, conn, identity, value):
        conn.execute('UPDATE homework_actions SET result_json=? WHERE id=?', (canonical(value), identity))

    def _response_key(self, identity):
        return self.host.store.response_key('homework-tutor-asr:' + identity)

    def transcribe(self, token, identity, item_id, data, audio):
        principal = self.host._student(token)
        self.host._processing_enabled()
        key = self._key(data.get('idempotencyKey'))
        item_revision = data.get('itemRevision')
        if type(item_revision) is not int:
            raise ApiError('homework_revision_conflict', '请携带题目版本', 400)
        details = audio_details(audio)
        with self.host.repository.transaction() as conn:
            row, item = self._scope(conn, principal, identity, item_id, item_revision, lock=True)
            request_sha = digest({'schema': SCHEMA, 'familyId': row['family_id'],
                'childId': row['child_id'], 'submissionId': identity, 'itemId': item_id,
                'submissionRevision': row['revision'], 'itemRevision': item_revision,
                'source': row['source'], 'audio': details,
                'providerId': PROVIDER_ID, 'modelId': MODEL_ID, 'language': 'auto'})
            existing = self._existing(conn, identity, item_id, key)
            if existing:
                if existing['request_sha256'] != request_sha:
                    raise ApiError('homework_asr_conflict', '同一次语音请求的内容已变化', 409)
                value = self._read(conn, existing, row, item)
                return self._public(existing['id'], value)
            receipt_id = self._identity(row, item_id, key)
            value = {'schema': SCHEMA, 'state': 'working', 'transcript': '', 'errorCode': None,
                'itemRevision': item_revision, 'submissionRevision': row['revision'],
                'requestSha256': request_sha, 'audio': details, 'createdAt': self.host.clock(),
                'expiresAt': self.host.clock() + TIMEOUT_SECONDS * 1000,
                'responseJournalKey': self._response_key(receipt_id), 'dispatchedAt': None}
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (receipt_id, identity, item_id, key, request_sha, canonical(value), self.host.clock()))
        dispatched = False
        try:
            audio_service = self.host.audio
            origin = urlparse(str(getattr(audio_service, 'url', '') or ''))
            if (not audio_service or not audio_service.enabled or not audio_service.budget
                    or not audio_service.internal_token or origin.scheme not in {'http', 'https'}
                    or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment):
                raise ApiError('homework_asr_unconfigured', '语音提问服务尚未配置', 503)
            binding = audio_service.budget.issue_homework_authorization(
                submission_id=identity, item_id=item_id, revision=item_revision)
            if (not isinstance(binding, dict) or binding.get('required') is not True
                    or not isinstance(binding.get('authorizationId'), str)
                    or not re.fullmatch(r'[a-f0-9]{64}', binding['authorizationId'])):
                raise ApiError('homework_asr_budget_required', '语音提问预算尚未授权', 503)
            with self.host.repository.transaction() as conn:
                current_row, current_item = self._scope(conn, principal, identity, item_id, item_revision, lock=True)
                action = self._existing(conn, identity, item_id, key)
                if action is None:
                    raise ApiError('homework_asr_stale', '这次语音提问已失效', 409)
                current = self._validate_action(action, current_row, current_item)
                # Count only real dispatches. Budget refusals consume no calls;
                # stale or deleted records cannot reset a live paper's cap.
                records = conn.execute('SELECT result_json FROM homework_actions WHERE submission_id=? AND idempotency_key LIKE ?',
                    (identity, 'asr:%')).fetchall()
                calls = sum(bool(parsed(record['result_json'], {}).get('dispatchedAt')) for record in records)
                if calls >= MAX_CALLS:
                    raise ApiError('homework_asr_budget_exceeded', '这份作业已达到语音提问次数上限', 409)
                if current['state'] != 'working' or current.get('dispatchedAt'):
                    return self._public(receipt_id, self._read(conn, action, current_row, current_item))
                current['dispatchedAt'] = self.host.clock()
                self._update(conn, receipt_id, current)
                value = current
            headers = {'X-Mira-Runtime-Session': 'homework-asr:' + receipt_id,
                'X-Mira-Paid-Budget-Required': '1',
                'X-Mira-Paid-Budget-Authorization': binding['authorizationId'],
                'X-Mira-Internal-Token': audio_service.internal_token}
            dispatched = True
            response = self.transport(audio, headers)
            saved = {'schema': RESPONSE_SCHEMA, 'id': receipt_id, 'submissionId': identity,
                'itemId': item_id, 'familyId': row['family_id'], 'childId': row['child_id'],
                'itemRevision': item_revision, 'submissionRevision': row['revision'],
                'requestSha256': request_sha, 'receivedAt': self.host.clock(), 'response': response}
            self.host.store.put_response(canonical(saved).encode(), namespace='homework-tutor-asr:' + receipt_id)
            with self.host.repository.transaction() as conn:
                try:
                    current_row, current_item = self._scope(conn, principal, identity, item_id, item_revision, lock=True)
                    action = self._existing(conn, identity, item_id, key)
                    if action is None:
                        raise ApiError('homework_asr_stale', '语音提问已失效', 409)
                    self._validate_action(action, current_row, current_item)
                except ApiError:
                    self.host._enqueue_delete(conn, self._response_key(receipt_id))
                    stale = True
                else:
                    value = self._read(conn, action, current_row, current_item)
                    stale = False
            if stale:
                self.host.purge_files()
                raise ApiError('homework_asr_stale', '作业已删除或题目已更新', 409)
            return self._public(receipt_id, value)
        except Exception as error:
            if isinstance(error, ApiError) and error.code in {'homework_not_found', 'homework_asr_stale', 'homework_revision_conflict'}:
                raise
            # A received journal remains recoverable even if this update fails.
            state = 'unknown' if dispatched else 'failed'
            code = 'homework_asr_unknown' if dispatched else (error.code if isinstance(error, ApiError) else 'homework_asr_unconfigured')
            with self.host.repository.transaction() as conn:
                action = conn.execute('SELECT * FROM homework_actions WHERE id=? FOR UPDATE', (receipt_id,)).fetchone()
                if action:
                    current = parsed(action['result_json'], {})
                    if current.get('state') == 'working':
                        current.update(state=state, errorCode=code)
                        self._update(conn, receipt_id, current)
            return self._public(receipt_id, {**value, 'state': state, 'errorCode': code})

    def get(self, token, identity, item_id, *, item_revision=None, idempotency_key=None, transcription_id=None):
        principal = self.host._student(token)
        if transcription_id is not None and not re.fullmatch(r'hwtr_[a-f0-9]{56}', transcription_id):
            raise ApiError('homework_asr_not_found', '没有找到这次语音提问', 404)
        key = self._key(idempotency_key) if transcription_id is None else None
        if transcription_id is None and type(item_revision) is not int:
            raise ApiError('homework_revision_conflict', '请携带题目版本', 400)
        with self.host.repository.transaction() as conn:
            row, item = self._scope(conn, principal, identity, item_id, item_revision, lock=True)
            action = (conn.execute('SELECT * FROM homework_actions WHERE id=? AND submission_id=? AND item_id=?',
                (transcription_id, identity, item_id)).fetchone() if transcription_id is not None
                else self._existing(conn, identity, item_id, key))
            if action is None:
                raise ApiError('homework_asr_not_found', '没有找到这次语音提问', 404)
            return self._public(action['id'], self._read(conn, action, row, item))

    def _read(self, conn, action, row, item):
        value = self._validate_action(action, row, item)
        key = value.get('responseJournalKey')
        if key != self._response_key(action['id']):
            raise ApiError('homework_asr_response_invalid', '语音回执范围不匹配', 409)
        if value['state'] in {'working', 'unknown'}:
            try:
                body = self.host.store.read(key)
            except ApiError as error:
                if error.code != 'homework_asset_missing':
                    raise
            else:
                try:
                    if len(body) > 4 * 1024 * 1024:
                        raise ValueError('journal too large')
                    saved = json.loads(body)
                    expected = {'schema': RESPONSE_SCHEMA, 'id': action['id'], 'submissionId': row['id'],
                        'itemId': item['id'], 'familyId': row['family_id'], 'childId': row['child_id'],
                        'itemRevision': item['revision'], 'submissionRevision': row['revision'],
                        'requestSha256': action['request_sha256']}
                    if any(saved.get(field) != expected_value for field, expected_value in expected.items()):
                        raise ValueError('journal scope mismatch')
                    transcript = self._transcript(saved.get('response'))
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                    value.update(state='failed', errorCode='homework_asr_response_invalid', transcript='')
                else:
                    value.update(state='ready', errorCode=None, transcript=transcript,
                        receivedResponseSha256=hashlib.sha256(body).hexdigest())
                self._update(conn, action['id'], value)
        if value['state'] == 'working' and self.host.clock() >= value['expiresAt']:
            value.update(state='unknown', errorCode='homework_asr_unknown')
            self._update(conn, action['id'], value)
        return value

    @staticmethod
    def _transcript(response):
        if isinstance(response, dict) and 'responseEnvelopeBase64' in response:
            if response.get('httpStatus') != 200 or response.get('truncated'):
                raise ValueError('ASR did not succeed')
            raw = base64.b64decode(response['responseEnvelopeBase64'], validate=True)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError('ASR response too large')
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    if key in value:
                        raise ValueError('duplicate response field')
                    value[key] = item
                return value
            response = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid number')))
        if (not isinstance(response, dict) or response.get('success') is not True
                or not isinstance(response.get('text'), str)
                or not 1 <= len(response['text'].strip()) <= MAX_TRANSCRIPT_CHARACTERS
                or any(0xd800 <= ord(char) <= 0xdfff or (ord(char) < 32 and char not in '\t\r\n')
                    for char in response['text'])):
            raise ValueError('invalid ASR transcript')
        return response['text'].strip()

    def _request(self, audio, headers):
        import urllib.request
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        boundary = 'mira-' + uuid.uuid4().hex
        parts = []
        for name, value in [('providerId', PROVIDER_ID), ('modelId', MODEL_ID), ('language', 'auto')]:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="question.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode())
        body = b''.join(parts) + audio + f'\r\n--{boundary}--\r\n'.encode()
        request = Request(self.host.audio.url + '/api/transcription', data=body, method='POST',
            headers={'Content-Type': 'multipart/form-data; boundary=' + boundary,
                     'Accept': 'application/json', **headers})
        opener = urllib.request.build_opener(NoRedirect())
        try:
            response = opener.open(request, timeout=TIMEOUT_SECONDS)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            return {'httpStatus': response.code, 'responseEnvelopeBase64': base64.b64encode(raw[:MAX_RESPONSE_BYTES]).decode(),
                    'truncated': len(raw) > MAX_RESPONSE_BYTES}
