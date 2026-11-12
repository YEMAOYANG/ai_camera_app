import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import wave

from PIL import Image

from courseware.tools import media_dispatch as dispatch, picture, voice


IMAGE_URL = 'http://127.0.0.1:3100/api/generate/image'
TTS_URL = 'http://127.0.0.1:3100/api/generate/tts'
DISK_FLOOR_ENV = 'MIRA_COURSEWARE_MIN_FREE_BYTES'
RATE_LIMITED = b'{"success":false,"errorCode":"RATE_LIMITED","error":"Qwen TTS rate limit exceeded (HTTP 429)"}'


def json_bytes(value):
    return json.dumps(value).encode()


def image_answer():
    stream = io.BytesIO()
    Image.new('RGB', (300, 300), 'orange').save(stream, 'PNG')
    return json_bytes({'success': True, 'result': {
        'base64': base64.b64encode(stream.getvalue()).decode()}})


def voice_answer(sample=b'\0\0'):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(sample * 4000)
    return json_bytes({'data': {'base64': base64.b64encode(stream.getvalue()).decode()}})


class MediaDispatchTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop(DISK_FLOOR_ENV, None)
        disk_usage = patch.object(dispatch.shutil, 'disk_usage',
                                  return_value=SimpleNamespace(free=dispatch.MINIMUM_FREE_BYTES))
        self.disk_usage = disk_usage.start()
        self.addCleanup(disk_usage.stop)
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source_root = self.root / 'sources'
        self.source = self.source_root / 'demo-lesson'
        self.source.mkdir(parents=True)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.slots = self.root / 'slots'
        self.pictures = [{'key': 'window', 'prompt': 'A classroom window'}]
        self.lines = [{'id': 'teacher-1', 'text': '请看窗户。', 'voice': 'Jennifer'}]
        self.write_inputs()
        self.calls = []
        self.health_calls = []
        self.image_body = image_answer()
        self.voice_body = voice_answer()

    def write_inputs(self):
        (self.source / 'pictures.json').write_bytes(json_bytes(self.pictures))
        (self.work / 'lines.json').write_bytes(json_bytes(self.lines))

    def health(self, url):
        self.health_calls.append(url)
        return 200, json_bytes({'success': True, 'status': 'ok'})

    def post(self, url, payload):
        self.calls.append((url, payload))
        digest = hashlib.sha256(dispatch._json_bytes(payload)).hexdigest()
        claim = self.ledger / digest / 'claim.json'
        self.assertTrue(claim.exists(), 'claim must be durable before a paid POST')
        health = json.loads(claim.read_text())['health']
        self.assertTrue((self.work / '.media-dispatch' / health['receipt']).exists())
        return 200, self.image_body if url == IMAGE_URL else self.voice_body

    @property
    def ledger(self):
        return self.work / '.media-dispatch' / 'requests'

    def run_media(self, **kwargs):
        return dispatch.run_dispatch(
            'demo-lesson', self.work, source_root=self.source_root, slots_dir=self.slots,
            post=kwargs.pop('post', self.post), health_get=kwargs.pop('health_get', self.health),
            **kwargs)

    def voice_dedupe_mode(self):
        lines_sha = hashlib.sha256((self.work / 'lines.json').read_bytes()).hexdigest()
        return {'steps': ('voice',), 'jobs': 1, 'dedupe_identical_tts': True, 'lines_sha256': lines_sha}

    def seed_authorized_timeout(self):
        line = self.lines[0]
        payload = {'text': line['text'], 'audioId': line['id'], 'ttsVoice': line['voice'],
                   'ttsProviderId': 'qwen-tts', 'ttsModelId': 'qwen3-tts-flash'}
        with dispatch.work_lock(self.work, 'demo-lesson'):
            def timeout(url, body):
                self.calls.append((url, body))
                return 500, b'{"success":false,"error":"upstream timeout"}'
            original = dispatch.RecordedPost(self.work, post=timeout, health_get=self.health,
                                             slots_dir=self.slots)
            with self.assertRaises(dispatch.DispatchError):
                original(TTS_URL, payload)
        digest = hashlib.sha256(dispatch._json_bytes(payload)).hexdigest()
        base = self.ledger / digest
        authorization = {
            'schemaVersion': 'mira.courseware.media-retry-authorization.v1',
            'lesson': 'demo-lesson', 'work': str(self.work.resolve()), 'payloadSha256': digest,
            'previousResponseSha256': hashlib.sha256((base / 'response.json').read_bytes()).hexdigest(),
            'question': '是否允许这一句重发一次并接受可能重复计费？',
            'userAnswer': '允许这1句重发一次', 'recordedAt': '2026-11-05T01:29:01Z',
            'acceptedPossibleDuplicateCharge': True, 'maxResends': 1}
        path = self.root / f'authorization-{self.work.name}.json'
        path.write_bytes(json_bytes(authorization))
        return path, payload, base

    def authorized(self, path, **kwargs):
        return dispatch.run_authorized_retry(
            'demo-lesson', self.work, path, post=kwargs.pop('post', self.post),
            health_get=kwargs.pop('health_get', self.health), slots_dir=self.slots, **kwargs)

    def test_success_and_recovery_from_raw_responses_without_post_or_health(self):
        first = self.run_media()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.health_calls, ['http://127.0.0.1:3100/api/health'] * 2)
        for directory in self.ledger.iterdir():
            receipt = json.loads((directory / 'response.json').read_text())
            expected = self.image_body if receipt['url'] == IMAGE_URL else self.voice_body
            self.assertEqual(base64.b64decode(receipt['bodyBase64']), expected)
            self.assertEqual(receipt['bodySha256'], hashlib.sha256(expected).hexdigest())
        (self.work / 'picture-cache.json').unlink()
        (self.work / 'voice-cache.json').unlink()
        (self.source / 'assets' / 'window.png').unlink()
        for path in (self.work / 'media').iterdir():
            path.unlink()
        with patch.object(dispatch, 'post_slot', side_effect=AssertionError('replay took a slot')):
            recovered = self.run_media(post=lambda *_: self.fail('paid replay'),
                                       health_get=lambda *_: self.fail('health during replay'))
        self.assertEqual(first, recovered)
        self.assertTrue((self.work / 'picture-cache.json').exists())
        self.assertTrue((self.work / 'voice-cache.json').exists())

    def test_opt_in_binds_103_exact_lines_from_98_original_responses(self):
        originals = [{'id': f'line-{index}', 'text': f'Line {index}', 'voice': 'Jennifer'}
                     for index in range(98)]
        aliases = [{**original, 'id': f'alias-{index}'} for index, original in enumerate(originals[:5])]
        self.lines = originals + aliases
        self.write_inputs()
        lines_path = self.work / 'lines.json'
        frozen = lines_path.read_bytes()
        mode = self.voice_dedupe_mode()

        def mock_pcm(url, payload):
            self.post(url, payload)
            index = int(payload['audioId'].split('-')[1])
            return 200, voice_answer(index.to_bytes(2, 'little'))

        result = self.run_media(**mode, post=mock_pcm)['voice']
        self.assertEqual((result['voiced'], result['reused'], result['posted'], result['aliased']),
                         (103, 0, 98, 5))
        self.assertEqual([payload['audioId'] for _, payload in self.calls], [line['id'] for line in originals])
        self.assertEqual(len(self.health_calls), 98)
        self.assertEqual(len(list(self.ledger.glob('*/response.json'))), 98)
        media = self.work / 'media'
        reuse = self.work / '.media-dispatch' / 'reused'
        self.assertEqual({path.stem for path in reuse.glob('*.json')}, {line['id'] for line in aliases})
        for index, alias in enumerate(aliases):
            original = originals[index]
            original_id, alias_id = original['id'], alias['id']
            payload_sha = hashlib.sha256(dispatch._json_bytes(voice._tts_payload(original))).hexdigest()
            alias_sha = hashlib.sha256(dispatch._json_bytes(voice._tts_payload(alias))).hexdigest()
            self.assertFalse((self.ledger / alias_sha).exists())
            receipt = self.ledger / payload_sha / 'response.json'
            source = json.loads(receipt.read_text())
            self.assertEqual(source['httpStatus'], 200)
            pcm = voice._wav_bytes(base64.b64decode(source['bodyBase64']))
            self.assertEqual(pcm, voice._wav_bytes(voice_answer(index.to_bytes(2, 'little'))))
            self.assertEqual((media / result['files'][original_id]).read_bytes(), pcm)
            self.assertEqual((media / result['files'][alias_id]).read_bytes(), pcm)
            record = json.loads((reuse / f'{alias_id}.json').read_text())
            self.assertEqual(record['representativeAudioId'], original_id)
            self.assertEqual(record['aliasUnsubmittedPayloadSha256'], alias_sha)
            self.assertEqual(record['representativeResponseSha256'], hashlib.sha256(receipt.read_bytes()).hexdigest())
            self.assertEqual(record['wavSha256'], hashlib.sha256(pcm).hexdigest())
            self.assertEqual(record['providerPostsForAlias'], 0)

        lock = self.work / '.media-dispatch.lock'
        inode = lock.stat().st_ino
        with patch.object(dispatch, 'post_slot', side_effect=AssertionError('replay took a slot')):
            replay = self.run_media(**mode, post=lambda *_: self.fail('paid replay'),
                                    health_get=lambda *_: self.fail('health during replay'))['voice']
        self.assertEqual(replay, {'voiced': 0, 'reused': 103, 'posted': 0, 'aliased': 0,
                                  'files': result['files']})
        self.assertEqual(lock.stat().st_ino, inode)
        self.assertEqual(lines_path.read_bytes(), frozen)

    def test_opt_in_uses_exact_spelling_and_voice(self):
        self.lines = [
            {'id': 'straight', 'text': "They're cute.", 'voice': 'Jennifer'},
            {'id': 'curly', 'text': 'They’re cute.', 'voice': 'Jennifer'},
            {'id': 'bella', 'text': 'They’re cute.', 'voice': 'Bella'},
            {'id': 'curly-copy', 'text': 'They’re cute.', 'voice': 'Jennifer'},
        ]
        self.write_inputs()
        result = self.run_media(**self.voice_dedupe_mode())['voice']
        self.assertEqual((result['posted'], result['aliased']), (3, 1))
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['straight', 'curly', 'bella'])

    def test_default_dispatch_keeps_independent_audio_ids(self):
        self.lines.append({**self.lines[0], 'id': 'teacher-2'})
        self.write_inputs()
        result = self.run_media(steps=('voice',), jobs=1)['voice']
        self.assertEqual(result['voiced'], 2)
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-2'])
        self.assertFalse((self.work / '.media-dispatch' / 'reused').exists())

    def test_opt_in_recovers_an_interrupted_alias_from_an_existing_response(self):
        original = self.lines[0]
        self.lines = [{**original, 'id': 'first-in-order'}, original]
        self.write_inputs()
        mode = self.voice_dedupe_mode()
        # The settled response predates this run and is for the second member.
        with dispatch.work_lock(self.work, 'demo-lesson'):
            post = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health, slots_dir=self.slots)
            post(TTS_URL, voice._tts_payload(original))
            with self.assertRaisesRegex(dispatch.DispatchError, 'work_locked'):
                self.run_media(**mode)

        with patch.object(dispatch, '_bind_voice_wav', side_effect=OSError('interrupted')):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.run_media(**mode, post=lambda *_: self.fail('paid replay'),
                               health_get=lambda *_: self.fail('health during replay'))
        evidence = self.work / '.media-dispatch' / 'reused' / 'first-in-order.json'
        before = evidence.read_bytes()
        record = json.loads(before)
        self.assertEqual(record['representativeAudioId'], original['id'])
        self.assertFalse((self.work / 'media' / record['targetWavFile']).exists())
        with self.assertRaisesRegex(dispatch.DispatchError, 'voice_dedupe_mode_required'):
            self.run_media(steps=('voice',), jobs=1, post=lambda *_: self.fail('paid alias'),
                           health_get=lambda *_: self.fail('health during alias replay'))

        recovered = self.run_media(**mode, post=lambda *_: self.fail('paid replay'),
                                   health_get=lambda *_: self.fail('health during replay'))['voice']
        self.assertEqual((recovered['voiced'], recovered['posted'], recovered['aliased']), (2, 0, 1))
        self.assertEqual(evidence.read_bytes(), before)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.health_calls), 1)
        self.assertEqual(len(list(self.ledger.glob('*/claim.json'))), 1)
        self.assertEqual((self.work / 'media' / recovered['files']['first-in-order']).read_bytes(),
                         voice._wav_bytes(self.voice_body))

    def test_opt_in_preserves_cache_only_clips_and_refuses_unverified_aliases(self):
        original = self.lines[0]
        voice.voice_lines(self.lines, self.work / 'media', post=lambda *_: (200, self.voice_body),
                          cache_path=self.work / 'voice-cache.json', jobs=1)
        cache_path = self.work / 'voice-cache.json'
        prior_cache = cache_path.read_bytes()
        self.lines = [{**original, 'id': 'another-text', 'text': 'New first group'}, original,
                      {**original, 'id': 'unproven-alias'}]
        self.write_inputs()
        with self.assertRaisesRegex(dispatch.DispatchError, 'voice_reuse_source_unverified'):
            self.run_media(**self.voice_dedupe_mode())
        self.assertEqual(cache_path.read_bytes(), prior_cache)
        self.assertEqual(self.calls + self.health_calls, [])
        self.assertFalse(self.ledger.exists())

    def test_opt_in_refuses_corrupt_cache_before_treating_lines_as_new(self):
        cache_path = self.work / 'voice-cache.json'
        cache_path.write_bytes(b'{"incomplete')
        with self.assertRaisesRegex(dispatch.DispatchError, 'record_invalid'):
            self.run_media(**self.voice_dedupe_mode())
        self.assertEqual(cache_path.read_bytes(), b'{"incomplete')
        self.assertEqual(self.calls + self.health_calls, [])
        self.assertFalse((self.work / dispatch.VOICE_DEDUPE_PLAN).exists())

    def test_opt_in_stops_at_first_unknown_and_keeps_original_receipts(self):
        for line_id, text in [('alias', '请看窗户。'), ('unknown', 'Second'),
                              ('unknown-copy', 'Second'), ('later', 'Third')]:
            self.lines.append({'id': line_id, 'text': text, 'voice': 'Jennifer'})
        self.write_inputs()
        mode = self.voice_dedupe_mode()
        error = b'{"success":false,"error":"upstream timeout"}'

        def mock_unknown(url, payload):
            self.post(url, payload)
            return (500, error) if payload['audioId'] == 'unknown' else (200, self.voice_body)

        with self.assertRaisesRegex(dispatch.DispatchError, 'unknown_upstream_outcome'):
            self.run_media(**mode, post=mock_unknown)
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'unknown'])
        responses = {path: path.read_bytes() for path in self.ledger.glob('*/response.json')}
        unknown = next(entry for raw in responses.values()
                       if (entry := json.loads(raw))['httpStatus'] == 500)
        self.assertEqual(base64.b64decode(unknown['bodyBase64']), error)
        reuse = self.work / '.media-dispatch' / 'reused'
        self.assertEqual({path.stem for path in reuse.glob('*.json')}, {'alias'})

        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            self.run_media(**mode, post=lambda *_: self.fail('paid replay'),
                           health_get=lambda *_: self.fail('health during replay'))
        self.assertEqual({path: path.read_bytes() for path in responses}, responses)
        self.assertEqual(len(self.health_calls), 2)

    def test_opt_in_rejects_http_200_with_invalid_pcm(self):
        self.lines.append({**self.lines[0], 'id': 'teacher-2'})
        self.write_inputs()
        mode = self.voice_dedupe_mode()

        def invalid_pcm(url, payload):
            self.post(url, payload)
            return 200, json_bytes({'base64': 'aW52YWxpZA=='})

        with self.assertRaisesRegex(voice.VoiceError, 'wav_invalid'):
            self.run_media(**mode, post=invalid_pcm)
        with self.assertRaisesRegex(voice.VoiceError, 'wav_invalid'):
            self.run_media(**mode, post=lambda *_: self.fail('paid replay'),
                           health_get=lambda *_: self.fail('health during replay'))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((self.work / '.media-dispatch' / 'reused').exists())
        self.assertFalse((self.work / 'voice-cache.json').exists())

    def test_opt_in_checks_the_reviewed_byte_hash_and_pins_it_for_resume(self):
        mode = self.voice_dedupe_mode()
        lines_path = self.work / 'lines.json'
        original = lines_path.read_bytes()
        lines_path.write_bytes(original + b'\n')
        with self.assertRaisesRegex(dispatch.DispatchError, 'voice_dedupe_lines_changed'):
            self.run_media(**mode)
        plan_path = self.work / dispatch.VOICE_DEDUPE_PLAN
        self.assertFalse(plan_path.exists())
        self.assertEqual(self.calls + self.health_calls, [])

        lines_path.write_bytes(original)
        self.run_media(**mode)
        plan = plan_path.read_bytes()
        self.assertEqual(json.loads(plan)['linesSha256'], mode['lines_sha256'])
        self.assertEqual(json.loads(plan)['ttsUrl'], TTS_URL)
        lines_path.write_bytes(original + b'\n')
        with self.assertRaisesRegex(dispatch.DispatchError, 'voice_dedupe_plan_mismatch'):
            self.run_media(**self.voice_dedupe_mode())
        self.assertEqual(plan_path.read_bytes(), plan)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.health_calls), 1)

    def test_low_disk_refuses_new_dispatch_before_health_or_claim(self):
        self.disk_usage.return_value = SimpleNamespace(free=dispatch.MINIMUM_FREE_BYTES - 1)
        with self.assertRaisesRegex(voice.VoiceError, 'disk_space_insufficient'):
            self.run_media(steps=('voice',))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.health_calls, [])
        self.assertEqual(list(self.ledger.rglob('claim.json')), [])

    def test_disk_is_rechecked_on_ledger_and_media_volumes_after_slot(self):
        media = self.work / 'media'
        media.mkdir()
        self.ledger.mkdir(parents=True)
        for low_volume in [self.ledger.resolve(), media.resolve()]:
            slot_held = False

            @contextmanager
            def slot(*args, **kwargs):
                nonlocal slot_held
                slot_held = True
                try:
                    yield
                finally:
                    slot_held = False

            def disk_usage(path):
                free = 100 * 1024**2 if slot_held and path == low_volume else dispatch.MINIMUM_FREE_BYTES
                return SimpleNamespace(free=free)

            self.disk_usage.side_effect = disk_usage
            recorded = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health,
                                             slots_dir=self.slots)
            with self.subTest(low_volume=low_volume), patch.object(dispatch, 'post_slot', slot):
                with self.assertRaisesRegex(dispatch.DispatchError, 'disk_space_insufficient'):
                    recorded(TTS_URL, {'text': 'queued until disk space dropped'})
            self.assertEqual(list(self.ledger.rglob('claim.json')), [])
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.health_calls), 2)

    def test_disk_floor_accepts_exact_default_and_configured_boundaries(self):
        for settings, floor, required in (
            ({}, 2 * 1024**3, '2 GiB'),
            ({DISK_FLOOR_ENV: str(5 * 1024**3)}, 5 * 1024**3, f'{5 * 1024**3} bytes'),
        ):
            with self.subTest(floor=floor), patch.dict(os.environ, settings):
                self.disk_usage.return_value = SimpleNamespace(free=floor - 1)
                with self.assertRaisesRegex(dispatch.DispatchError, f'requires at least {required}'):
                    dispatch._require_disk_space(self.work)
                self.disk_usage.return_value = SimpleNamespace(free=floor)
                dispatch._require_disk_space(self.work)

    def test_configured_disk_floor_blocks_claim_if_space_drops_after_slot(self):
        floor = 5 * 1024**3
        self.disk_usage.return_value = SimpleNamespace(free=floor)
        real_slot = dispatch.post_slot

        @contextmanager
        def slot(*args, **kwargs):
            with real_slot(*args, **kwargs):
                self.disk_usage.return_value = SimpleNamespace(free=floor - 1)
                yield

        with patch.dict(os.environ, {DISK_FLOOR_ENV: str(floor)}), patch.object(dispatch, 'post_slot', slot):
            with self.assertRaisesRegex(voice.VoiceError, f'requires at least {floor} bytes'):
                self.run_media(steps=('voice',), jobs=1)
        self.assertEqual(len(self.health_calls), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.ledger.rglob('claim.json')), [])

    def test_invalid_disk_floor_blocks_new_dispatch_before_health_or_claim(self):
        for value in ('', '5 GiB', '5.5', str(dispatch.MINIMUM_FREE_BYTES - 1)):
            with self.subTest(value=value), patch.dict(os.environ, {DISK_FLOOR_ENV: value}):
                with self.assertRaisesRegex(voice.VoiceError, 'disk_space_floor_invalid'):
                    self.run_media(steps=('voice',), jobs=1)
        self.disk_usage.assert_not_called()
        self.assertEqual(self.calls + self.health_calls, [])
        self.assertEqual(list(self.ledger.rglob('claim.json')), [])

    def assert_regular_voice_http_rejection(self, status, expected_ids, **options):
        self.lines.append({'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'})
        self.write_inputs()
        raw = b'{"success":false,"error":"provider rejected the request"}'

        def reject_first(url, payload):
            if payload['audioId'] == 'teacher-1':
                self.calls.append((url, payload))
                raise HTTPError(url, status, 'provider rejection', {}, io.BytesIO(raw))
            return self.post(url, payload)

        with self.assertRaisesRegex(voice.VoiceError, f'teacher-1: HTTP {status}'):
            self.run_media(steps=('voice',), jobs=1, post=reject_first, **options)
        self.assertEqual([p['audioId'] for _, p in self.calls], expected_ids)
        self.assertEqual(len(self.health_calls), len(expected_ids))
        claims = {json.loads(p.read_bytes())['payload']['audioId']: p
                  for p in self.ledger.rglob('claim.json')}
        self.assertEqual(set(claims), set(expected_ids))
        response = json.loads(claims['teacher-1'].with_name('response.json').read_bytes())
        self.assertEqual((response['httpStatus'], response['outcome']), (status, 'http_error'))
        self.assertEqual(base64.b64decode(response['bodyBase64']), raw)
        self.assertFalse((self.work / dispatch.VOICE_DEDUPE_PLAN).exists())

    def test_stop_on_voice_error_stops_after_http_402(self):
        self.assert_regular_voice_http_rejection(402, ['teacher-1'], stop_on_voice_error=True)

    def test_stop_on_voice_error_stops_after_http_403(self):
        self.assert_regular_voice_http_rejection(403, ['teacher-1'], stop_on_voice_error=True)

    def test_regular_voice_continues_after_http_rejection_by_default(self):
        self.assert_regular_voice_http_rejection(402, ['teacher-1', 'teacher-2'])

    def test_stop_on_voice_error_stays_stopped_when_disk_recovers(self):
        self.lines.append({'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'})
        self.write_inputs()
        floor = 5 * 1024**3
        self.disk_usage.return_value = SimpleNamespace(free=floor)
        real_slot = dispatch.post_slot
        acquisitions = 0

        @contextmanager
        def slot(*args, **kwargs):
            nonlocal acquisitions
            with real_slot(*args, **kwargs):
                acquisitions += 1
                if acquisitions == 1:
                    self.disk_usage.return_value = SimpleNamespace(free=floor - 1)
                try:
                    yield
                finally:
                    self.disk_usage.return_value = SimpleNamespace(free=floor)

        with patch.dict(os.environ, {DISK_FLOOR_ENV: str(floor)}), patch.object(dispatch, 'post_slot', slot):
            with self.assertRaisesRegex(voice.VoiceError, 'disk_space_insufficient'):
                self.run_media(steps=('voice',), jobs=1, stop_on_voice_error=True)
        self.assertEqual(acquisitions, 1)
        self.assertEqual(len(self.health_calls), 1)
        self.assertEqual(self.calls, [])
        self.assertEqual(list(self.ledger.rglob('claim.json')), [])

    def test_voice_stop_on_error_keeps_success_and_never_retries_invalid_pcm(self):
        self.lines.extend([{'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'},
                           {'id': 'teacher-3', 'text': '请找椅子。', 'voice': 'Jennifer'}])
        sleeps = []

        def post(url, payload):
            self.calls.append((url, payload))
            if payload['audioId'] == 'teacher-1':
                return 200, self.voice_body
            return 200, json_bytes({'data': {'base64': base64.b64encode(b'not RIFF').decode()}})

        cache_path = self.work / 'voice-cache.json'
        media = self.work / 'media'
        with self.assertRaisesRegex(voice.VoiceError, 'teacher-2: wav_invalid'):
            voice.voice_lines(self.lines, media, post=post, cache_path=cache_path, jobs=1,
                              sleep=sleeps.append, stop_on_error=True)
        self.assertEqual([p['audioId'] for _, p in self.calls], ['teacher-1', 'teacher-2'])
        self.assertEqual(sleeps, [])
        cache = json.loads(cache_path.read_bytes())
        self.assertEqual(set(cache), {voice._cache_key(self.lines[0])})
        self.assertTrue(voice._cached_name(self.lines[0], media, cache, require_pcm=True))

    def test_low_disk_preserves_settled_replay_without_new_post(self):
        payload = {'text': 'already generated'}
        recorded = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health,
                                         slots_dir=self.slots)
        response = recorded(TTS_URL, payload)
        claim = next(self.ledger.rglob('claim.json'))
        original = claim.read_bytes()
        self.disk_usage.reset_mock()
        self.disk_usage.return_value = SimpleNamespace(free=0)
        recorded = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health,
                                         slots_dir=self.slots)
        self.assertEqual(recorded(TTS_URL, payload), response)
        self.disk_usage.assert_not_called()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.health_calls), 1)
        self.assertEqual(claim.read_bytes(), original)

    def test_low_disk_does_not_consume_one_use_retry_authorization(self):
        authorization, _, base = self.seed_authorized_timeout()
        self.disk_usage.return_value = SimpleNamespace(free=0)
        with self.assertRaisesRegex(dispatch.DispatchError, 'disk_space_insufficient'):
            self.authorized(authorization)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((base / 'attempts').exists())

    def test_http_failure_is_recorded_and_lower_picture_retries_never_post(self):
        def denied(url, payload):
            self.calls.append((url, payload))
            return 402, b'{"success":false,"error":"balance exhausted"}'
        for _ in range(2):
            with self.assertRaises(picture.PictureError):
                self.run_media(steps=('pictures',), post=denied)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.health_calls), 1)
        receipt = json.loads(next(self.ledger.glob('*/response.json')).read_text())
        self.assertEqual(receipt['httpStatus'], 402)
        self.assertEqual(receipt['reason'], 'HTTP 402')
        self.assertIn(b'balance exhausted', base64.b64decode(receipt['bodyBase64']))

    def test_http_exception_keeps_original_body_and_tts_retries_are_replays(self):
        def busy(url, payload):
            self.calls.append((url, payload))
            raise HTTPError(url, 429, 'Too Many Requests', {}, io.BytesIO(b'provider busy'))
        with self.assertRaises(voice.VoiceError):
            self.run_media(steps=('voice',), post=busy)
        self.assertEqual(len(self.calls), 1)
        receipt = json.loads(next(self.ledger.glob('*/response.json')).read_text())
        self.assertEqual((receipt['httpStatus'], base64.b64decode(receipt['bodyBase64'])),
                         (429, b'provider busy'))
        self.assertEqual(receipt['reason'], 'Too Many Requests')

    def test_transport_exception_blocks_same_and_changed_payload_across_runs(self):
        def interrupted(url, payload):
            self.calls.append((url, payload))
            raise TimeoutError('response unknown after send')
        with self.assertRaises(picture.PictureError):
            self.run_media(steps=('pictures',), post=interrupted)
        error = json.loads(next(self.ledger.glob('*/error.json')).read_text())
        self.assertEqual(error['errorType'], 'TimeoutError')
        self.assertEqual(error['reason'], 'response unknown after send')
        self.assertFalse(error['retryAllowed'])
        self.assertEqual(list(self.ledger.glob('*/response.json')), [])
        self.pictures[0]['prompt'] = 'A changed prompt must not bypass an unknown claim'
        self.write_inputs()
        with self.assertRaises(picture.PictureError):
            self.run_media(steps=('pictures',), post=interrupted)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.health_calls), 1)
        with dispatch.post_slot(IMAGE_URL, self.slots):
            pass  # A transport exception released its global slot.

    def test_failed_preflight_creates_no_claim_and_has_auditable_reason(self):
        cases = [(503, b'unavailable'), (200, b'not json'),
                 (200, json_bytes({'success': False, 'status': 'ok'})),
                 (200, json_bytes({'success': True, 'status': 'degraded'}))]
        for index, response in enumerate(cases):
            self.work = self.root / f'work-{index}'
            self.work.mkdir()
            count = []
            def unhealthy(url):
                count.append(url)
                return response
            with self.subTest(response=response), self.assertRaises(picture.PictureError):
                self.run_media(steps=('pictures',), health_get=unhealthy)
            self.assertEqual(count, ['http://127.0.0.1:3100/api/health'])
            self.assertEqual(list(self.ledger.glob('*/claim.json')), [])
            receipt = json.loads(next((self.work / '.media-dispatch/preflights').glob('*.json')).read_text())
            self.assertFalse(receipt['ok'])
            self.assertTrue(receipt['reason'])
        self.assertEqual(self.calls, [])

    def test_crash_after_claim_and_corrupt_receipt_both_fail_closed(self):
        recorded = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health,
                                         slots_dir=self.slots)
        payload = {'prompt': 'same payload'}
        digest = hashlib.sha256(dispatch._json_bytes(payload)).hexdigest()
        directory = self.ledger / digest
        dispatch._atomic_record(directory / 'claim.json', {
            'url': IMAGE_URL, 'payload': payload, 'payloadSha256': digest})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recorded(IMAGE_URL, payload)
        (directory / 'response.json').write_text('{broken')
        with self.assertRaisesRegex(dispatch.DispatchError, 'record_invalid'):
            recorded(IMAGE_URL, payload)
        self.assertEqual(self.calls + self.health_calls, [])

    def test_successful_response_tampering_cannot_trigger_regeneration(self):
        self.run_media(steps=('pictures',))
        path = next(self.ledger.glob('*/response.json'))
        receipt = json.loads(path.read_text())
        receipt['bodySha256'] = '0' * 64
        path.write_bytes(json_bytes(receipt))
        (self.work / 'picture-cache.json').unlink()
        with self.assertRaisesRegex(picture.PictureError, 'response_invalid'):
            self.run_media(steps=('pictures',))
        self.assertEqual(len(self.calls), 1)

    def test_concurrent_identical_picture_payload_is_posted_once(self):
        self.pictures.append({'key': 'second-window', 'prompt': self.pictures[0]['prompt']})
        self.write_inputs()
        result = self.run_media(steps=('pictures',), jobs=2)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(set(result['pictures']['files']), {'window', 'second-window'})

    def test_global_slot_limits_bound_image_and_tts_posts(self):
        for step, expected in [('pictures', 2), ('voice', 2)]:
            self.work = self.root / f'parallel-{step}'
            self.work.mkdir()
            self.pictures = [{'key': f'picture-{i}', 'prompt': f'scene {i}'} for i in range(8)]
            self.lines = [{'id': f'line-{i}', 'text': f'sentence {i}', 'voice': 'Ethan'} for i in range(8)]
            self.write_inputs()
            active = maximum = 0
            mutex = Lock()
            def slow_post(url, payload):
                nonlocal active, maximum
                with mutex:
                    active += 1
                    maximum = max(maximum, active)
                try:
                    time.sleep(0.04)
                    return self.post(url, payload)
                finally:
                    with mutex:
                        active -= 1
            self.run_media(steps=(step,), jobs=8, post=slow_post)
            self.assertEqual(maximum, expected)

    def test_external_process_holds_all_image_slots_until_released(self):
        code = """
import fcntl, pathlib, sys
root = pathlib.Path(sys.argv[1]); root.mkdir()
streams = [(root / ('images-' + str(i) + '.lock')).open('a+b') for i in range(2)]
for stream in streams: fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
print('locked', flush=True)
sys.stdin.readline()
"""
        process = subprocess.Popen([sys.executable, '-B', '-c', code, str(self.slots)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            sent = Event()
            def post(url, payload):
                sent.set()
                return self.post(url, payload)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.run_media, steps=('pictures',), post=post)
                try:
                    self.assertFalse(sent.wait(0.15))
                    self.assertEqual(list(self.ledger.glob('*/claim.json')), [],
                                     'waiting for a global slot must not create a paid claim')
                finally:
                    process.communicate('\n', timeout=5)
                future.result(timeout=5)
            self.assertTrue(sent.is_set())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_work_lock_is_exclusive_across_processes_and_owner_cannot_change(self):
        code = """
import sys
from courseware.tools.media_dispatch import DispatchError, work_lock
try:
    with work_lock(sys.argv[1], 'demo-lesson'): pass
except DispatchError:
    sys.exit(23)
"""
        with dispatch.work_lock(self.work, 'demo-lesson'):
            result = subprocess.run([sys.executable, '-B', '-c', code, str(self.work)], check=False)
            self.assertEqual(result.returncode, 23)
        self.assertEqual(subprocess.run([sys.executable, '-B', '-c', code, str(self.work)],
                                        check=False).returncode, 0)
        with self.assertRaisesRegex(dispatch.DispatchError, 'work_owner_mismatch'):
            with dispatch.work_lock(self.work, 'another-lesson'):
                self.fail('owner changed')

    def test_cli_and_invalid_inputs_do_not_make_network_calls(self):
        with patch.object(dispatch, 'run_dispatch', return_value={'voice': {'reused': 1}}) as run:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(dispatch.main(['--lesson', 'demo-lesson', '--work', str(self.work),
                                                 '--steps', 'voice', '--jobs', '3']), 0)
            self.assertEqual(run.call_args.kwargs, {'steps': ('voice',), 'jobs': 3,
                                                    'retry_rate_limited': False,
                                                    'dedupe_identical_tts': False, 'lines_sha256': None})
        with patch.object(dispatch, 'run_dispatch', side_effect=dispatch.DispatchError('work_locked', 'path')):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(dispatch.main(['--lesson', 'demo-lesson', '--work', str(self.work)]), 1)
        for kwargs in [{'jobs': 0}, {'steps': ('unknown',)}, {'steps': ('voice', 'voice')}]:
            with self.assertRaises(dispatch.DispatchError):
                self.run_media(**kwargs)
        self.assertEqual(self.calls + self.health_calls, [])

    def test_cli_deduplication_requires_voice_only_and_one_job_without_retry(self):
        mode = self.voice_dedupe_mode()
        args = ['--lesson', 'demo-lesson', '--work', str(self.work), '--steps', 'voice', '--jobs', '1',
                '--dedupe-identical-tts', '--lines-sha256', mode['lines_sha256']]
        with patch.object(dispatch, 'run_dispatch', return_value={'voice': {'posted': 0}}) as run:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(dispatch.main(args), 0)
            run.assert_called_once_with('demo-lesson', str(self.work), steps=('voice',), jobs=1,
                                        retry_rate_limited=False, dedupe_identical_tts=True,
                                        lines_sha256=mode['lines_sha256'])
        for retry in [('--retry-rate-limited',), ('--retry-authorized-request', 'authorization.json'),
                      ('--continue-unsubmitted-tts-after', 'sha'), ('--lines-file', 'replacement.json')]:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                dispatch.main([*args, *retry])
        for invalid in [{'jobs': 2}, {'steps': ('pictures', 'voice')}, {'retry_rate_limited': True}]:
            with self.assertRaisesRegex(dispatch.DispatchError, 'arguments_invalid'):
                self.run_media(**(mode | invalid))
        with self.assertRaisesRegex(dispatch.DispatchError, 'voice_dedupe_hash_invalid'):
            self.run_media(**(mode | {'lines_sha256': None}))
        self.assertEqual(self.calls + self.health_calls, [])

    def test_cli_stop_on_voice_error_is_only_for_regular_serial_voice(self):
        args = ['--lesson', 'demo-lesson', '--work', str(self.work), '--steps', 'voice', '--jobs', '1',
                '--stop-on-voice-error']
        with patch.object(dispatch, 'run_dispatch', return_value={}) as run:
            self.assertEqual(dispatch.main(args), 0)
            self.assertIs(run.call_args.kwargs['stop_on_voice_error'], True)
        for conflict in [('--retry-rate-limited',), ('--retry-authorized-request', 'authorization.json'),
                         ('--continue-unsubmitted-tts-after', 'sha'), ('--dedupe-identical-tts',)]:
            with self.subTest(conflict=conflict), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                dispatch.main([*args, *conflict])
        for invalid in ({'jobs': 2}, {'steps': ('pictures', 'voice')}, {'retry_rate_limited': True},
                        {'dedupe_identical_tts': True}):
            options = {'steps': ('voice',), 'jobs': 1, 'stop_on_voice_error': True}
            with self.subTest(invalid=invalid), self.assertRaisesRegex(dispatch.DispatchError, 'arguments_invalid'):
                self.run_media(**(options | invalid))
        self.assertEqual(self.calls + self.health_calls, [])

    def test_health_transport_error_is_recorded_before_any_paid_claim(self):
        def offline(url):
            raise ConnectionError('health service unavailable')
        with self.assertRaises(picture.PictureError):
            self.run_media(steps=('pictures',), health_get=offline)
        receipt = json.loads(next((self.work / '.media-dispatch/preflights').glob('*.json')).read_text())
        self.assertEqual((receipt['errorType'], receipt['reason']),
                         ('ConnectionError', 'health service unavailable'))
        self.assertEqual(list(self.ledger.glob('*/claim.json')), [])
        self.assertEqual(self.calls, [])

    def test_immutable_claim_and_original_adapter_selection(self):
        path = self.root / 'immutable.json'
        dispatch._atomic_record(path, {'value': 1})
        with self.assertRaises(FileExistsError):
            dispatch._atomic_record(path, {'value': 2})
        self.assertEqual(json.loads(path.read_text()), {'value': 1})
        with patch.object(picture, 'default_post', return_value=(200, b'image')) as images:
            with patch.object(voice, 'default_post', return_value=(200, b'voice')) as tts:
                self.assertEqual(dispatch.default_post(IMAGE_URL, {}), (200, b'image'))
                self.assertEqual(dispatch.default_post(TTS_URL, {}), (200, b'voice'))
        images.assert_called_once_with(IMAGE_URL, {})
        tts.assert_called_once_with(TTS_URL, {})

    def test_unknown_response_blocks_later_payload_in_same_instance(self):
        def interrupted(url, payload):
            self.calls.append((url, payload))
            raise TimeoutError('unknown paid outcome')
        recorded = dispatch.RecordedPost(self.work, post=interrupted, health_get=self.health,
                                         slots_dir=self.slots)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recorded(IMAGE_URL, {'prompt': 'first'})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recorded(IMAGE_URL, {'prompt': 'second'})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.health_calls), 1)
        self.assertEqual(len(list(self.ledger.glob('*/claim.json'))), 1)

    def test_unknown_stops_queued_payload_and_preserves_inflight_response(self):
        unknown_started, inflight_started, queued_health = Event(), Event(), Event()
        fail_now, finish_inflight = Event(), Event()
        count_lock = Lock()
        health_count = 0
        def health(url):
            nonlocal health_count
            with count_lock:
                health_count += 1
                if health_count == 3:
                    queued_health.set()
            return self.health(url)
        def post(url, payload):
            self.calls.append((url, payload))
            if payload['prompt'] == 'unknown':
                unknown_started.set()
                if not fail_now.wait(3):
                    raise AssertionError('test did not release the unknown request')
                raise TimeoutError('unknown concurrent outcome')
            if payload['prompt'] == 'inflight':
                inflight_started.set()
                if not finish_inflight.wait(3):
                    raise AssertionError('test did not release the inflight request')
                return 200, self.image_body
            raise AssertionError('a queued payload was posted after an unknown outcome')
        recorded = dispatch.RecordedPost(self.work, post=post, health_get=health,
                                         slots_dir=self.slots)
        with ThreadPoolExecutor(max_workers=3) as executor:
            first = executor.submit(recorded, IMAGE_URL, {'prompt': 'unknown'})
            second = executor.submit(recorded, IMAGE_URL, {'prompt': 'inflight'})
            try:
                self.assertTrue(unknown_started.wait(2))
                self.assertTrue(inflight_started.wait(2))
                queued = executor.submit(recorded, IMAGE_URL, {'prompt': 'queued'})
                self.assertTrue(queued_health.wait(2))
                fail_now.set()
                with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
                    first.result(timeout=2)
                with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
                    queued.result(timeout=2)
                finish_inflight.set()
                self.assertEqual(second.result(timeout=2), (200, self.image_body))
            finally:
                fail_now.set()
                finish_inflight.set()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(list(self.ledger.glob('*/claim.json'))), 2)
        self.assertEqual(len(list(self.ledger.glob('*/error.json'))), 1)
        self.assertEqual(len(list(self.ledger.glob('*/response.json'))), 1)
        # Successful inflight responses remain recoverable after the stop latch.
        self.assertEqual(recorded(IMAGE_URL, {'prompt': 'inflight'}), (200, self.image_body))

    def test_interrupted_slot_queue_leaves_no_claim_or_unknown_receipt(self):
        @contextmanager
        def stopped(*args, **kwargs):
            raise KeyboardInterrupt('stopped while waiting for a slot')
            yield
        recorded = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health,
                                         slots_dir=self.slots)
        with patch.object(dispatch, 'post_slot', stopped):
            with self.assertRaises(KeyboardInterrupt):
                recorded(IMAGE_URL, {'prompt': 'queued'})
        self.assertEqual(list(self.ledger.glob('*/claim.json')), [])
        self.assertEqual(list(self.ledger.glob('*/error.json')), [])
        self.assertEqual(self.calls, [])

    def test_failed_response_persistence_latches_unknown_in_same_instance(self):
        def successful_post(url, payload):
            self.calls.append((url, payload))
            return 200, self.image_body
        recorded = dispatch.RecordedPost(self.work, post=successful_post, health_get=self.health,
                                         slots_dir=self.slots)
        atomic_record = dispatch._atomic_record
        def fail_response(path, value):
            if Path(path).name == 'response.json':
                raise OSError('response persistence unavailable')
            return atomic_record(path, value)
        with patch.object(dispatch, '_atomic_record', fail_response):
            with self.assertRaises(OSError):
                recorded(IMAGE_URL, {'prompt': 'first'})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recorded(IMAGE_URL, {'prompt': 'second'})
        self.assertEqual(len(self.calls), 1)
        error = json.loads(next(self.ledger.glob('*/error.json')).read_text())
        self.assertEqual(error['reason'], 'response persistence unavailable')

    def test_explicit_429_recovery_preserves_original_and_reuses_success_cache(self):
        def limited(url, payload):
            self.calls.append((url, payload))
            return 429, RATE_LIMITED
        with self.assertRaises(voice.VoiceError):
            self.run_media(steps=('voice',), post=limited)
        base = next(self.ledger.iterdir())
        original = {name: (base / name).read_bytes() for name in ['claim.json', 'response.json']}
        with self.assertRaises(voice.VoiceError):
            self.run_media(steps=('voice',), post=limited)
        self.assertEqual(len(self.calls), 1, 'recovery must be opt in')
        result = self.run_media(steps=('voice',), retry_rate_limited=True)
        self.assertEqual(len(self.calls), 2)
        attempt = base / 'attempts/0002'
        self.assertTrue((attempt / 'response.json').exists())
        claim = json.loads((attempt / 'claim.json').read_text())
        self.assertEqual(claim['payload'], json.loads(original['claim.json'])['payload'])
        self.assertEqual(claim['retryReason'], 'verified_rate_limited')
        self.assertEqual(claim['previousResponseSha256'], hashlib.sha256(original['response.json']).hexdigest())
        for name, raw in original.items():
            self.assertEqual((base / name).read_bytes(), raw)
        reused = self.run_media(steps=('voice',), retry_rate_limited=True,
                                post=lambda *_: self.fail('successful cache retried'))
        self.assertEqual(reused['voice']['reused'], 1)
        (self.work / 'voice-cache.json').unlink()
        (self.work / 'media' / result['voice']['files']['teacher-1']).unlink()
        self.run_media(steps=('voice',), retry_rate_limited=True,
                       post=lambda *_: self.fail('successful attempt retried'))
        self.assertEqual(len(self.calls), 2)

    def test_each_explicit_run_recovers_payload_only_once_and_initial_run_never_retries(self):
        def limited(url, payload):
            self.calls.append((url, payload))
            return 429, RATE_LIMITED
        with self.assertRaises(voice.VoiceError):
            self.run_media(steps=('voice',), retry_rate_limited=True, post=limited)
        base = next(self.ledger.iterdir())
        self.assertFalse((base / 'attempts').exists())
        for number in [2, 3]:
            with self.assertRaises(voice.VoiceError):
                self.run_media(steps=('voice',), retry_rate_limited=True, post=limited)
            self.assertEqual(len(self.calls), number)
            self.assertTrue((base / f'attempts/{number:04d}/response.json').exists())
        self.assertEqual(len(list((base / 'attempts').iterdir())), 2)

    def test_recovery_rejects_unknown_or_success_containing_429_and_non_tts(self):
        cases = [(TTS_URL, 429, b'RATE_LIMITED'),
                 (TTS_URL, 429, json_bytes({'success': False, 'error': 'RATE_LIMITED'})),
                 (TTS_URL, 429, json_bytes({'success': True, 'errorCode': 'RATE_LIMITED'})),
                 (TTS_URL, 429, json_bytes({'success': False, 'errorCode': 'OTHER'})),
                 (TTS_URL, 429, json_bytes({'success': False, 'errorCode': 'RATE_LIMITED',
                                           'data': {'base64': 'audio'}})),
                 (IMAGE_URL, 429, RATE_LIMITED)]
        for index, (url, status, body) in enumerate(cases):
            work = self.root / f'denied-{index}'
            calls = []
            def post(*args):
                calls.append(args)
                return status, body
            first = dispatch.RecordedPost(work, post=post, health_get=self.health, slots_dir=self.slots)
            self.assertEqual(first(url, {'text': 'test'}), (status, body))
            recovered = dispatch.RecordedPost(work, post=post, health_get=self.health,
                                              slots_dir=self.slots, retry_rate_limited=True)
            with self.subTest(body=body, url=url):
                self.assertEqual(recovered(url, {'text': 'test'}), (status, body))
                self.assertEqual(len(calls), 1)
                self.assertEqual(list(work.glob('.media-dispatch/requests/*/attempts')), [])

    def test_500_is_unknown_upstream_outcome_and_never_recovers(self):
        body = json_bytes({'success': False, 'error': 'Upstream request timed out after 30000ms'})
        def timed_out(url, payload):
            self.calls.append((url, payload))
            return 500, body
        first = dispatch.RecordedPost(self.work, post=timed_out, health_get=self.health,
                                      slots_dir=self.slots)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unknown_upstream_outcome'):
            first(TTS_URL, {'text': 'test'})
        path = next(self.ledger.glob('*/response.json'))
        raw = path.read_bytes()
        receipt = json.loads(raw)
        self.assertEqual(receipt['outcome'], 'unknown_upstream_outcome')
        self.assertEqual(base64.b64decode(receipt['bodyBase64']), body)
        recovered = dispatch.RecordedPost(self.work, post=timed_out, health_get=self.health,
                                          slots_dir=self.slots, retry_rate_limited=True)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unknown_upstream_outcome'):
            recovered(TTS_URL, {'text': 'test'})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recovered(TTS_URL, {'text': 'new payload'})
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(list(self.ledger.glob('*/attempts')), [])

    def test_image_rejection_replays_without_blocking_an_independent_request(self):
        for old_receipt, message in (
            (True, 'Green net check rejected text (input)'),
            (False, 'Green net check rejected image (output)'),
        ):
            with self.subTest(old_receipt=old_receipt):
                work = self.root / f'image-rejection-{old_receipt}'
                upstream = {'request_id': 'd9cdbce4-cee0-926c-9c5f-67e71697ac1d',
                            'code': 'DataInspectionFailed', 'message': message}
                rejected = json_bytes({'success': False, 'errorCode': 'INTERNAL_ERROR',
                                       'error': 'Qwen Image generation failed (400): ' + json.dumps(upstream)})
                rejected_payload = {'prompt': 'Original refused image'}
                other_payload = {'prompt': 'An unrelated classroom object'}
                calls = []

                def post(url, payload):
                    calls.append((url, payload))
                    return (500, rejected) if payload == rejected_payload else (200, self.image_body)

                first = dispatch.RecordedPost(work, post=post, health_get=self.health, slots_dir=self.slots)
                self.assertEqual(first(IMAGE_URL, rejected_payload), (500, rejected))
                receipt = next(work.glob('.media-dispatch/requests/*/response.json'))
                record = json.loads(receipt.read_text())
                self.assertEqual(record['outcome'], 'settled_rejected')
                if old_receipt:
                    record['outcome'] = 'unknown_upstream_outcome'
                    receipt.write_bytes(json_bytes(record))
                original = receipt.read_bytes()

                reopened = dispatch.RecordedPost(work, post=post, health_get=self.health,
                                                 slots_dir=self.slots, retry_rate_limited=True)
                self.assertEqual(reopened(IMAGE_URL, rejected_payload), (500, rejected))
                self.assertEqual(reopened(IMAGE_URL, other_payload), (200, self.image_body))
                self.assertEqual(calls, [(IMAGE_URL, rejected_payload), (IMAGE_URL, other_payload)])
                self.assertEqual(receipt.read_bytes(), original)

    def test_similar_image_500_does_not_unlock_an_unverified_outcome(self):
        upstream = {'request_id': 'missing-request-id', 'code': 'DataInspectionFailed',
                    'message': 'Green net check rejected text (input)'}
        body = json_bytes({'success': False, 'errorCode': 'INTERNAL_ERROR',
                           'error': 'Qwen Image generation failed (400): ' + json.dumps(upstream)})
        first = dispatch.RecordedPost(self.work, post=lambda *_: (500, body),
                                      health_get=self.health, slots_dir=self.slots)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unknown_upstream_outcome'):
            first(IMAGE_URL, {'prompt': 'Initial image'})
        reopened = dispatch.RecordedPost(self.work, post=lambda *_: self.fail('Unexpected POST'),
                                         health_get=self.health, slots_dir=self.slots)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            reopened(IMAGE_URL, {'prompt': 'Other image'})

    def test_unknown_recovery_attempt_remains_pending_and_cannot_be_retried(self):
        payload = {'text': 'test'}
        first = dispatch.RecordedPost(self.work, post=lambda *_: (429, RATE_LIMITED),
                                      health_get=self.health, slots_dir=self.slots)
        first(TTS_URL, payload)
        def lost(url, body):
            self.calls.append((url, body))
            raise TimeoutError('unknown after recovery POST')
        recovered = dispatch.RecordedPost(self.work, post=lost, health_get=self.health,
                                          slots_dir=self.slots, retry_rate_limited=True)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recovered(TTS_URL, payload)
        again = dispatch.RecordedPost(self.work, post=lost, health_get=self.health,
                                      slots_dir=self.slots, retry_rate_limited=True)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            again(TTS_URL, payload)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(list(self.ledger.glob('*/attempts/*/claim.json'))), 1)
        self.assertEqual(list(self.ledger.glob('*/attempts/*/response.json')), [])

    def test_unknown_work_stops_even_known_429_recovery(self):
        def post(url, payload):
            self.calls.append((url, payload))
            return (429, RATE_LIMITED) if payload['text'] == 'limited' else (500, b'upstream timeout')
        first = dispatch.RecordedPost(self.work, post=post, health_get=self.health,
                                      slots_dir=self.slots)
        first(TTS_URL, {'text': 'limited'})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unknown_upstream_outcome'):
            first(TTS_URL, {'text': 'unknown'})
        recovered = dispatch.RecordedPost(self.work, post=post, health_get=self.health,
                                          slots_dir=self.slots, retry_rate_limited=True)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            recovered(TTS_URL, {'text': 'limited'})
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(list(self.ledger.glob('*/attempts')), [])

    def continue_new(self, base, *, post=None, lines_sha=None, response_sha=None, additional=(), lines_file=None):
        return dispatch.run_unsubmitted_tts(
            'demo-lesson', self.work, base.name,
            response_sha or hashlib.sha256((base / 'response.json').read_bytes()).hexdigest(),
            lines_sha or hashlib.sha256((self.work / 'lines.json').read_bytes()).hexdigest(),
            post=post or self.post, health_get=self.health, slots_dir=self.slots,
            additional=additional, lines_file=lines_file)

    def test_continue_unsubmitted_tts_keeps_original_500_and_ignores_renamed_line(self):
        _, _, base = self.seed_authorized_timeout()
        old = (base / 'response.json').read_bytes()
        self.lines.extend([{**self.lines[0], 'id': 'renamed-unknown'},
                           {'id': 'teacher-2', 'text': '请找一张桌子。', 'voice': 'Jennifer'}])
        self.write_inputs()
        result = self.continue_new(base)
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-2'])
        self.assertEqual(result['pending']['outcome'], 'unknown_upstream_outcome')
        self.assertEqual(set(result['voice']['files']), {'teacher-2'})
        self.assertEqual((base / 'response.json').read_bytes(), old)
        new_claim = next(p for p in self.ledger.glob('*/claim.json') if p.parent != base)
        self.assertEqual(json.loads(new_claim.read_bytes())['firstTimeContinuation']['pendingPayloadSha256'], base.name)
        self.assertEqual(self.continue_new(base)['voice']['voiced'], 0)
        self.assertEqual(len(self.calls), 2)
        self.assertFalse((base / 'attempts').exists())

    def test_continue_unsubmitted_tts_requires_both_frozen_inputs(self):
        _, _, base = self.seed_authorized_timeout()
        self.lines.append({'id': 'teacher-2', 'text': '请找一张桌子。', 'voice': 'Jennifer'})
        self.write_inputs()
        with self.assertRaisesRegex(dispatch.DispatchError, 'continuation_response_mismatch'):
            self.continue_new(base, response_sha='0' * 64)
        with self.assertRaisesRegex(dispatch.DispatchError, 'continuation_lines_changed'):
            self.continue_new(base, lines_sha='0' * 64)
        self.lines[0]['text'] = '修改旧行后不能继续。'
        self.write_inputs()
        with self.assertRaisesRegex(dispatch.DispatchError, 'continuation_pending_line_changed'):
            self.continue_new(base)
        self.assertEqual(len(self.calls), 1)

    def test_continue_with_separate_lines_uses_original_request_ledger(self):
        _, _, base = self.seed_authorized_timeout()
        original_lines = self.work / 'lines.json'
        original_bytes = original_lines.read_bytes()
        original_response = (base / 'response.json').read_bytes()
        separate_lines = self.work.parent / 'reviewed-lines.json'
        separate_lines.write_text(json.dumps([
            {**self.lines[0], 'id': 'renamed-unknown'},
            {'id': 'teacher-2', 'text': '请找一张桌子。', 'voice': 'Jennifer'},
        ]), encoding='utf-8')
        with self.assertRaisesRegex(dispatch.DispatchError, 'continuation_lines_changed'):
            self.continue_new(base, lines_file=separate_lines)
        reviewed_sha = hashlib.sha256(separate_lines.read_bytes()).hexdigest()
        result = self.continue_new(base, lines_file=separate_lines, lines_sha=reviewed_sha)
        self.assertEqual(set(result['voice']['files']), {'teacher-2'})
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-2'])
        self.assertEqual(original_lines.read_bytes(), original_bytes)
        self.assertEqual((base / 'response.json').read_bytes(), original_response)
        claim = next(p for p in self.ledger.glob('*/claim.json') if p.parent != base)
        self.assertEqual(json.loads(claim.read_bytes())['firstTimeContinuation']['linesSha256'], reviewed_sha)

    def test_new_reviewed_line_can_replace_removed_pending_line_without_resending_it(self):
        _, _, base = self.seed_authorized_timeout()
        self.lines = [{'id': 'teacher-2', 'text': '每样物品配一个圆片。', 'voice': 'Jennifer'}]
        self.write_inputs()
        self.assertEqual(set(self.continue_new(base)['voice']['files']), {'teacher-2'})
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-2'])
        self.assertFalse((base / 'attempts').exists())

    def assert_continuation_stops_after_http_rejection(self, status):
        _, _, base = self.seed_authorized_timeout()
        original = (base / 'response.json').read_bytes()
        self.lines.extend([{'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'},
                           {'id': 'teacher-3', 'text': '请找椅子。', 'voice': 'Jennifer'}])
        self.write_inputs()
        raw = b'{"success":false,"error":"provider rejected the request"}'

        def reject(url, payload):
            self.calls.append((url, payload))
            raise HTTPError(url, status, 'provider rejection', {}, io.BytesIO(raw))

        with self.assertRaisesRegex(voice.VoiceError, f'teacher-2: HTTP {status}'):
            self.continue_new(base, post=reject)
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-2'])
        self.assertEqual(len(self.health_calls), 2)
        [new_claim] = [p for p in self.ledger.rglob('claim.json') if p.parent != base]
        self.assertEqual(json.loads(new_claim.read_bytes())['payload']['audioId'], 'teacher-2')
        response = json.loads(new_claim.with_name('response.json').read_bytes())
        self.assertEqual(response['httpStatus'], status)
        self.assertEqual(response['outcome'], 'http_error')
        self.assertEqual(base64.b64decode(response['bodyBase64']), raw)
        self.assertEqual((base / 'response.json').read_bytes(), original)
        recorded = dispatch.RecordedPost(self.work, post=self.post, health_get=self.health,
                                         slots_dir=self.slots)
        self.assertEqual(recorded._unresolved, {str((base / 'claim.json').resolve())})

    def test_continuation_stops_after_http_402(self):
        self.assert_continuation_stops_after_http_rejection(402)

    def test_continuation_stops_after_http_403(self):
        self.assert_continuation_stops_after_http_rejection(403)

    def test_continuation_stays_stopped_after_disk_space_recovers(self):
        _, _, base = self.seed_authorized_timeout()
        original = (base / 'response.json').read_bytes()
        self.lines.extend([{'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'},
                           {'id': 'teacher-3', 'text': '请找椅子。', 'voice': 'Jennifer'}])
        self.write_inputs()
        floor = 5 * 1024**3
        self.disk_usage.return_value = SimpleNamespace(free=floor)
        real_slot = dispatch.post_slot
        acquisitions = 0

        @contextmanager
        def slot(*args, **kwargs):
            nonlocal acquisitions
            with real_slot(*args, **kwargs):
                acquisitions += 1
                if acquisitions == 1:
                    self.disk_usage.return_value = SimpleNamespace(free=floor - 1)
                try:
                    yield
                finally:
                    self.disk_usage.return_value = SimpleNamespace(free=floor)

        with patch.dict(os.environ, {DISK_FLOOR_ENV: str(floor)}), patch.object(dispatch, 'post_slot', slot):
            with self.assertRaisesRegex(voice.VoiceError, 'disk_space_insufficient'):
                self.continue_new(base)
        self.assertEqual(acquisitions, 1)
        self.assertEqual(len(self.health_calls), 2)
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1'])
        self.assertEqual(list(self.ledger.rglob('claim.json')), [base / 'claim.json'])
        self.assertEqual((base / 'response.json').read_bytes(), original)

    def test_new_unknown_fences_remaining_first_time_tts(self):
        _, _, base = self.seed_authorized_timeout()
        self.lines.extend([{'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'},
                           {'id': 'teacher-3', 'text': '请找椅子。', 'voice': 'Jennifer'}])
        self.write_inputs()

        def second_timeout(url, payload):
            self.calls.append((url, payload))
            return 500, b'upstream timeout again'

        with self.assertRaises(voice.VoiceError):
            self.continue_new(base, post=second_timeout)
        with self.assertRaisesRegex(dispatch.DispatchError, 'continuation_unknown_scope'):
            self.continue_new(base)
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-2'])
        self.assertEqual(list(self.ledger.glob('*/attempts')), [])

    def test_continue_after_two_timeouts_requires_each_exact_response_hash(self):
        _, _, first = self.seed_authorized_timeout()
        self.lines.extend([{'id': 'teacher-2', 'text': '请找桌子。', 'voice': 'Jennifer'},
                           {'id': 'teacher-3', 'text': '请找椅子。', 'voice': 'Jennifer'}])
        self.write_inputs()
        with self.assertRaises(voice.VoiceError):
            self.continue_new(first, post=lambda *_: (500, b'second timeout'))
        second = next(path for path in self.ledger.iterdir() if path != first)
        with self.assertRaisesRegex(dispatch.DispatchError, 'continuation_response_mismatch'):
            self.continue_new(first, additional=[f'{second.name}:{"0" * 64}'])
        response_sha = hashlib.sha256((second / 'response.json').read_bytes()).hexdigest()
        result = self.continue_new(first, additional=[f'{second.name}:{response_sha}'])
        self.assertEqual(result['additionalPending'], [second.name])
        self.assertEqual(set(result['voice']['files']), {'teacher-3'})
        self.assertEqual([payload['audioId'] for _, payload in self.calls], ['teacher-1', 'teacher-3'])
        self.assertEqual(list(self.ledger.glob('*/attempts')), [])

    def test_recovery_spacing_is_global_across_processes(self):
        code = """
import sys, time
from courseware.tools.media_dispatch import recovery_spacing
with recovery_spacing(sys.argv[1], check=lambda: None):
    print(time.time_ns(), flush=True)
    time.sleep(0.05)
"""
        processes = [subprocess.Popen([sys.executable, '-B', '-c', code, str(self.slots)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        try:
            starts = []
            for process in processes:
                out, err = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, err)
                starts.append(int(out.strip()))
            self.assertGreaterEqual(abs(starts[1] - starts[0]), 1_000_000_000)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_cli_explicit_recovery_flag(self):
        with patch.object(dispatch, 'run_dispatch', return_value={}) as run:
            self.assertEqual(dispatch.main(['--lesson', 'demo-lesson', '--work', str(self.work),
                                            '--steps', 'voice', '--retry-rate-limited']), 0)
        self.assertIs(run.call_args.kwargs['retry_rate_limited'], True)

    def test_authorized_retry_sends_only_frozen_payload_and_resolves_old_500(self):
        path, payload, base = self.seed_authorized_timeout()
        originals = {name: (base / name).read_bytes() for name in ['claim.json', 'response.json']}
        raw_authorization = path.read_bytes()
        (self.work / 'lines.json').write_text('deliberately unreadable current lines')
        result = self.authorized(path)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[-1], (TTS_URL, payload))
        self.assertTrue((self.work / 'media' / result['voice']['files'][payload['audioId']]).exists())
        claim = json.loads((base / 'attempts/0002/claim.json').read_text())
        self.assertEqual(base64.b64decode(claim['authorizationRawBase64']), raw_authorization)
        self.assertEqual(claim['authorization'], json.loads(raw_authorization))
        self.assertEqual(claim['authorizationSha256'], hashlib.sha256(raw_authorization).hexdigest())
        for name, raw in originals.items():
            self.assertEqual((base / name).read_bytes(), raw)
        with self.assertRaises(dispatch.DispatchError):
            self.authorized(path)
        self.assertEqual(len(self.calls), 2)
        self.write_inputs()
        # Normal replay is no longer permanently stopped by the resolved old 500.
        rebuilt = dispatch.RecordedPost(self.work, post=lambda *_: self.fail('paid replay'),
                                        health_get=self.health, slots_dir=self.slots)
        rebuilt._check_unresolved()
        self.assertEqual(rebuilt(TTS_URL, payload), (200, self.voice_body))
        (self.work / 'voice-cache.json').unlink()
        (self.work / 'media' / result['voice']['files'][payload['audioId']]).unlink()
        self.run_media(steps=('voice',), post=lambda *_: self.fail('successful attempt was resent'))
        self.assertEqual(len(self.calls), 2)

    def test_authorization_rejects_binding_limits_or_original_response_changes(self):
        path, _, base = self.seed_authorized_timeout()
        original = json.loads(path.read_text())
        cases = [('lesson', 'another-lesson'), ('work', str(self.root / 'other-work')),
                 ('payloadSha256', '1' * 64), ('previousResponseSha256', '2' * 64),
                 ('maxResends', 2), ('maxResends', True), ('acceptedPossibleDuplicateCharge', False),
                 ('userAnswer', ''), ('recordedAt', '2026-11-05T01:29:01')]
        for key, value in cases:
            changed = {**original, key: value}
            path.write_bytes(json_bytes(changed))
            with self.subTest(key=key, value=value), self.assertRaises(dispatch.DispatchError):
                self.authorized(path)
        path.write_bytes(json_bytes(original))
        response = json.loads((base / 'response.json').read_text())
        response['reason'] = 'changed after authorization'
        (base / 'response.json').write_bytes(json_bytes(response))
        with self.assertRaisesRegex(dispatch.DispatchError, 'authorization_mismatch'):
            self.authorized(path)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((base / 'attempts').exists())

    def test_authorization_and_original_claim_are_rechecked_before_submission(self):
        for changed_file in ['authorization', 'claim']:
            self.work = self.root / f'recheck-{changed_file}'
            self.work.mkdir()
            path, _, base = self.seed_authorized_timeout()
            def health(url):
                result = self.health(url)
                target = path if changed_file == 'authorization' else base / 'claim.json'
                value = json.loads(target.read_text())
                if changed_file == 'authorization':
                    value['userAnswer'] = 'changed after dispatch started'
                else:
                    value['payload']['text'] = 'changed original payload'
                target.write_bytes(json_bytes(value))
                return result
            with self.subTest(changed_file=changed_file), self.assertRaises(dispatch.DispatchError):
                self.authorized(path, health_get=health)
            self.assertFalse((base / 'attempts').exists())
        self.assertEqual(len(self.calls), 2)

    def test_authorized_retry_cannot_pass_another_unknown_in_work(self):
        path, _, base = self.seed_authorized_timeout()
        payload = {'text': 'another pending request'}
        digest = hashlib.sha256(dispatch._json_bytes(payload)).hexdigest()
        dispatch._atomic_record(self.ledger / digest / 'claim.json', {
            'url': TTS_URL, 'payload': payload, 'payloadSha256': digest})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            self.authorized(path)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse((base / 'attempts').exists())

    def test_failed_authorized_attempt_consumes_grant_and_stays_blocked(self):
        for failure in ['timeout', '500', '429', 'invalid-audio']:
            self.work = self.root / f'failed-authorized-{failure}'
            self.work.mkdir()
            path, payload, base = self.seed_authorized_timeout()
            actual = []
            def post(url, body):
                actual.append((url, body))
                if failure == 'timeout':
                    raise TimeoutError('unknown authorized resend')
                if failure == '500':
                    return 500, b'upstream timeout again'
                if failure == '429':
                    return 429, RATE_LIMITED
                return 200, b'{"base64":"invalid"}'
            with self.subTest(failure=failure), self.assertRaises(dispatch.DispatchError):
                self.authorized(path, post=post)
            with self.assertRaises(dispatch.DispatchError):
                self.authorized(path, post=post)
            normal = dispatch.RecordedPost(self.work, post=post, health_get=self.health,
                                           slots_dir=self.slots, retry_rate_limited=True)
            with self.assertRaises(dispatch.DispatchError):
                normal(TTS_URL, payload)
            with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
                normal(TTS_URL, {'text': 'unrelated new request'})
            self.assertEqual(len(actual), 1)
            self.assertEqual(len(list((base / 'attempts').iterdir())), 1)

    def test_cli_authorized_request_is_standalone(self):
        with patch.object(dispatch, 'run_authorized_retry', return_value={}) as run:
            with patch.object(dispatch, 'run_dispatch', side_effect=AssertionError('ordinary dispatch called')):
                self.assertEqual(dispatch.main([
                    '--lesson', 'demo-lesson', '--work', str(self.work),
                    '--retry-authorized-request', '/explicit/authorization.json']), 0)
        run.assert_called_once_with('demo-lesson', str(self.work), '/explicit/authorization.json')

    def seed_two_authorized_timeouts(self):
        """Two TTS lines of one work timed out; the owner authorized one resend of each."""
        self.lines = [{'id': 'teacher-1', 'text': '请看窗户。', 'voice': 'Jennifer'},
                      {'id': 'teacher-2', 'text': '再看门。', 'voice': 'Jennifer'}]
        self.write_inputs()
        seeded = []
        with dispatch.work_lock(self.work, 'demo-lesson'):
            def timeout(url, body):
                self.calls.append((url, body))
                return 500, b'{"success":false,"error":"upstream timeout"}'
            for line in self.lines:
                payload = {'text': line['text'], 'audioId': line['id'], 'ttsVoice': line['voice'],
                           'ttsProviderId': 'qwen-tts', 'ttsModelId': 'qwen3-tts-flash'}
                original = dispatch.RecordedPost(self.work, post=timeout, health_get=self.health,
                                                 slots_dir=self.slots)
                original._unresolved.clear()  # the first seeded timeout must not block seeding the second
                with self.assertRaises(dispatch.DispatchError):
                    original(TTS_URL, payload)
                digest = hashlib.sha256(dispatch._json_bytes(payload)).hexdigest()
                base = self.ledger / digest
                authorization = {
                    'schemaVersion': 'mira.courseware.media-retry-authorization.v1',
                    'lesson': 'demo-lesson', 'work': str(self.work.resolve()), 'payloadSha256': digest,
                    'previousResponseSha256': hashlib.sha256((base / 'response.json').read_bytes()).hexdigest(),
                    'question': '是否允许这两句各重发一次并接受可能重复计费？',
                    'userAnswer': '允许这2句各重发一次', 'recordedAt': '2026-11-08T09:30:00+08:00',
                    'acceptedPossibleDuplicateCharge': True, 'maxResends': 1}
                path = self.root / f'authorization-{line["id"]}.json'
                path.write_bytes(json_bytes(authorization))
                seeded.append((path, payload, base))
        self.assertEqual(len(self.calls), 2)
        return seeded

    def test_owner_authorized_companion_lets_each_listed_timeout_resend_once(self):
        (first, first_payload, first_base), (second, second_payload, second_base) = (
            self.seed_two_authorized_timeouts())
        # Alone, the first resend is still blocked by the other open timeout.
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            self.authorized(first)
        self.assertEqual(len(self.calls), 2)
        result = self.authorized(first, companions=(second,))
        self.assertEqual(self.calls[-1], (TTS_URL, first_payload))
        self.assertEqual(len(self.calls), 3)
        self.assertTrue((self.work / 'media' / result['voice']['files']['teacher-1']).exists())
        # The companion was tolerated, not sent and not settled.
        self.assertFalse((second_base / 'attempts').exists())
        rebuilt = dispatch.RecordedPost(self.work, post=lambda *_: self.fail('paid replay'),
                                        health_get=self.health, slots_dir=self.slots)
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            rebuilt._check_unresolved()
        self.authorized(second)
        self.assertEqual(self.calls[-1], (TTS_URL, second_payload))
        self.assertEqual(len(self.calls), 4)
        for path in (first, second):
            with self.assertRaises(dispatch.DispatchError):
                self.authorized(path)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(len(list((first_base / 'attempts').iterdir())), 1)
        self.assertEqual(len(list((second_base / 'attempts').iterdir())), 1)
        dispatch.RecordedPost(self.work, post=lambda *_: self.fail('paid replay'),
                              health_get=self.health, slots_dir=self.slots)._check_unresolved()

    def test_companion_must_be_a_valid_unused_owner_authorization(self):
        (first, _, first_base), (second, _, second_base) = self.seed_two_authorized_timeouts()
        original = json.loads(second.read_text())
        for key, value in [('previousResponseSha256', '2' * 64), ('lesson', 'another-lesson'),
                           ('acceptedPossibleDuplicateCharge', False), ('maxResends', 2)]:
            second.write_bytes(json_bytes({**original, key: value}))
            with self.subTest(key=key), self.assertRaises(dispatch.DispatchError):
                self.authorized(first, companions=(second,))
        second.write_bytes(json_bytes(original))
        with self.assertRaisesRegex(dispatch.DispatchError, 'authorization_duplicate'):
            self.authorized(first, companions=(first,))
        # An open claim nobody authorized still blocks, companion or not.
        payload = {'text': 'another pending request'}
        digest = hashlib.sha256(dispatch._json_bytes(payload)).hexdigest()
        dispatch._atomic_record(self.ledger / digest / 'claim.json', {
            'url': TTS_URL, 'payload': payload, 'payloadSha256': digest})
        with self.assertRaisesRegex(dispatch.DispatchError, 'unreconciled_claim'):
            self.authorized(first, companions=(second,))
        self.assertEqual(len(self.calls), 2)
        self.assertFalse((first_base / 'attempts').exists())
        self.assertFalse((second_base / 'attempts').exists())

    def test_cli_several_authorized_requests_run_in_order_with_later_ones_as_companions(self):
        clips = [{'voice': {'files': {'a': 'a.wav'}, 'voiced': 1, 'reused': 0}},
                 {'voice': {'files': {'b': 'b.wav'}, 'voiced': 1, 'reused': 0}}]
        with patch.object(dispatch, 'run_authorized_retry', side_effect=clips) as run:
            with patch.object(dispatch, 'run_dispatch', side_effect=AssertionError('ordinary dispatch called')):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(dispatch.main([
                        '--lesson', 'demo-lesson', '--work', str(self.work),
                        '--retry-authorized-request', '/explicit/a.json',
                        '--retry-authorized-request', '/explicit/b.json']), 0)
        self.assertEqual(run.call_args_list[0].args, ('demo-lesson', str(self.work), '/explicit/a.json'))
        self.assertEqual(run.call_args_list[0].kwargs, {'companions': ('/explicit/b.json',)})
        self.assertEqual(run.call_args_list[1].args, ('demo-lesson', str(self.work), '/explicit/b.json'))
        self.assertEqual(run.call_args_list[1].kwargs, {'companions': ()})
        self.assertIn('"voiced": 2', output.getvalue())
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            dispatch.main(['--lesson', 'demo-lesson', '--work', str(self.work),
                           '--retry-authorized-request', '/explicit/a.json',
                           '--retry-authorized-request', '/explicit/a.json'])


if __name__ == '__main__':
    unittest.main()
