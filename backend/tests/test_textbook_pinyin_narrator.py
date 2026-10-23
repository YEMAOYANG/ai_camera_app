"""Pinyin narrator dispatch/recovery boundaries with SQLite fixtures and mock HTTP only."""
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_pronunciation import pronunciation_identity, provider_pronunciation
from content.textbook_preview_audio_contract import new_audio_plan, new_pinyin_audio_plan
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.textbook_preview_audio import core_content, narrate_preview
from tests.test_textbook_pinyin_pronunciation import bind_audio_fixture, usage_receipt, wav_fixture, wav_receipt
from tests import test_textbook_preview_audio_v2 as fixtures


class PinyinNarratorTests(unittest.TestCase):
    def fixture(self, *, unsupported=False):
        harness = fixtures.PreviewAudioV2Tests()
        self.addCleanup(harness.doCleanups)
        f = harness.unnarrated()
        bind_audio_fixture(f)
        f.classroom['scenes'][0]['actions'][0]['text'] = '听第二声，é，请跟老师读。'
        f.classroom['scenes'][1]['actions'][0]['text'] = (
            '下一段含有未支持的 hello。' if unsupported else '听第四声，è，请再读一遍。')
        harness.persist(f)
        frozen = json.loads(f.service.get(f.key)['input_json'])
        parent = new_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen)
        f.plan = new_pinyin_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen,
            parent_plan=parent, revision_id='d' * 64)
        (f.folder / 'plan.json').write_text(canonical(f.plan))
        f.audio = wav_fixture()
        f.runtime.download_formal_audio_tts.return_value = f.audio
        f.client = OpenMaicFullRuntimeClient('http://127.0.0.1:3100',
            formal_audio_internal_token='synthetic-no-network-token-' * 3)

        def dispatch(method, route, payload, **kwargs):
            self.assertEqual((method, route), ('POST', '/api/mira/formal-audio/tts'))
            self.assertEqual(payload['pronunciationProfile'], pronunciation_identity(payload['text']))
            response = {'success': True, 'requestId': payload['requestId'], 'state': 'succeeded',
                'mimeType': 'audio/wav', 'providerId': 'aliyun-cosyvoice',
                'modelId': 'cosyvoice-v3-flash', 'voiceId': 'longanwen_v3',
                'providerPronunciation': provider_pronunciation(payload['text']),
                **wav_receipt(f.audio, normalized=True), **usage_receipt(payload['text'])}
            f.provider_receipts[payload['requestId']] = f.client._validate_formal_tts_response(
                response, request_id=payload['requestId'])
            return response

        f.client._request_formal_audio_json = Mock(side_effect=dispatch)
        f.runtime.start_formal_audio_tts.side_effect = f.client.start_formal_audio_tts
        f.selection = lambda *indexes: harness.selection(f, *indexes)
        return f

    def test_actual_client_adds_profile_and_full_success_reuses_all_verified_wavs(self):
        f = self.fixture()
        plan_before = (f.folder / 'plan.json').read_bytes()
        result = narrate_preview(f.service, f.key, f.root)
        self.assertEqual((result['status'], result['result']['audioCompleted']), ('preview_ready', 8))
        self.assertEqual(f.client._request_formal_audio_json.call_count, 8)
        for call in f.client._request_formal_audio_json.call_args_list:
            payload = call.args[2]
            self.assertTrue(payload['requestId'].startswith('tbptts1_'))
            self.assertEqual(payload['pronunciationProfile'], pronunciation_identity(payload['text']))
            self.assertEqual(payload['teacherProfileId'], 'mira_chinese_gentle')
            self.assertEqual(payload['teacherProfileVersion'], 2)
        for scene in f.classroom['scenes']:
            action = scene['actions'][0]
            self.assertEqual(action['audioMetadata']['providerId'], 'aliyun-cosyvoice')
            self.assertEqual(action['audioMetadata']['voiceId'], 'longanwen_v3')
            self.assertEqual((f.root / f.cid / 'audio' / (action['audioId'] + '.wav')).read_bytes(), f.audio)
        self.assertEqual((f.folder / 'plan.json').read_bytes(), plan_before)
        narrate_preview(f.service, f.key, f.root)
        self.assertEqual(f.client._request_formal_audio_json.call_count, 8)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 8)

    def test_unsupported_unselected_speech_blocks_every_paid_dispatch(self):
        f = self.fixture(unsupported=True)
        with self.assertRaises(ApiError) as raised:
            narrate_preview(f.service, f.key, f.root, speech_selection=f.selection(0))
        self.assertEqual(raised.exception.code, 'textbook_pinyin_pronunciation_invalid')
        f.client._request_formal_audio_json.assert_not_called()
        f.runtime.get_formal_audio_tts.assert_not_called()
        f.runtime.download_formal_audio_tts.assert_not_called()
        self.assertEqual(json.loads((f.folder / 'receipts.json').read_text()), [])

    def test_failed_and_ambiguous_full_runs_never_create_another_attempt(self):
        for status in ('failed', 'ambiguous'):
            with self.subTest(status=status):
                f = self.fixture()
                f.runtime.start_formal_audio_tts.side_effect = lambda **kw: {
                    'requestId': kw['request_id'], 'status': status, 'audioSha256': None}
                first = narrate_preview(f.service, f.key, f.root)
                self.assertEqual(first['result']['audioStopCode'], 'textbook_preview_audio_' + status)
                self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
                checkpoint = (f.folder / 'receipts.json').read_bytes()
                narrate_preview(f.service, f.key, f.root)
                self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
                self.assertEqual((f.folder / 'receipts.json').read_bytes(), checkpoint)
                self.assertEqual(len(json.loads(checkpoint)), 1)
                f.runtime.download_formal_audio_tts.assert_not_called()

    def test_dispatch_timeout_then_404_retains_unknown_without_new_paid_attempt(self):
        f = self.fixture()
        f.runtime.start_formal_audio_tts.side_effect = OpenMaicFullRuntimeError('timeout', 'unknown')
        narrate_preview(f.service, f.key, f.root)
        checkpoint = (f.folder / 'receipts.json').read_bytes()
        self.assertEqual(json.loads(checkpoint)[0]['status'], 'unknown')
        recovered = narrate_preview(f.service, f.key, f.root)
        self.assertEqual(recovered['result']['audioStopCode'], 'textbook_preview_audio_unknown')
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual((f.folder / 'receipts.json').read_bytes(), checkpoint)

    def test_interrupted_selected_save_recovers_existing_wav_and_receipt(self):
        f = self.fixture()
        selection = f.selection(0)
        f.runtime.save_preview_classroom.side_effect = OpenMaicFullRuntimeError('save_failed', 'interrupted')
        with self.assertRaises(OpenMaicFullRuntimeError):
            narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        checkpoint = (f.folder / 'receipts.json').read_bytes()
        self.assertEqual(json.loads(checkpoint)[0]['status'], 'succeeded')
        f.runtime.save_preview_classroom.side_effect = f.save
        narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 1)
        self.assertEqual((f.folder / 'receipts.json').read_bytes(), checkpoint)

    def test_lost_full_save_response_reconciles_without_overwrite_or_new_audio(self):
        f = self.fixture()
        narrate_preview(f.service, f.key, f.root, speech_selection=f.selection(0))
        def saved_without_response(value):
            f.save(value)
            raise OpenMaicFullRuntimeError('response_lost', 'saved but lost response')
        f.runtime.save_preview_classroom.side_effect = saved_without_response
        with self.assertRaises(OpenMaicFullRuntimeError):
            narrate_preview(f.service, f.key, f.root)
        saved = (f.root / (f.cid + '.json')).read_bytes()
        saves = f.runtime.save_preview_classroom.call_count
        f.runtime.save_preview_classroom.side_effect = f.save
        result = narrate_preview(f.service, f.key, f.root)
        self.assertEqual((result['status'], result['result']['audioCompleted']), ('preview_ready', 8))
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)
        self.assertEqual(f.runtime.download_formal_audio_tts.call_count, 8)
        self.assertEqual(f.runtime.save_preview_classroom.call_count, saves)
        self.assertEqual((f.root / (f.cid + '.json')).read_bytes(), saved)

    def test_corrupted_pcm_provenance_blocks_download_binding_and_saved_reuse(self):
        for source in ('download', 'reuse', 'full-reuse', 'lost-save'):
            with self.subTest(source=source):
                f = self.fixture()
                selection = f.selection(0)
                if source == 'download':
                    bad = bytearray(f.audio)
                    bad[-1] ^= 1
                    # Even a mocked transport that misses its audio SHA check cannot bind bad PCM.
                    f.runtime.download_formal_audio_tts.return_value = bytes(bad)
                elif source == 'full-reuse':
                    narrate_preview(f.service, f.key, f.root)
                elif source == 'lost-save':
                    def save_then_fail(value):
                        f.save(value)
                        raise OpenMaicFullRuntimeError('lost', 'saved without acknowledgement')
                    f.runtime.save_preview_classroom.side_effect = save_then_fail
                    with self.assertRaises(OpenMaicFullRuntimeError): narrate_preview(f.service, f.key, f.root)
                else:
                    narrate_preview(f.service, f.key, f.root, speech_selection=selection)
                if source != 'download':
                    row = f.service.get(f.key)
                    result = json.loads(row['result_json'])
                    receipts = json.loads((f.folder / 'receipts.json').read_text())
                    receipts[0]['pcmSha256'] = '0' * 64
                    (f.folder / 'receipts.json').write_text(canonical(receipts))
                    if source != 'lost-save':
                        result['audioReceipts'] = deepcopy(receipts)
                        f.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                                     (canonical(result), f.key))
                        f.db.raw.commit()
                calls_before = f.runtime.start_formal_audio_tts.call_count
                with self.assertRaises(ApiError) as raised:
                    narrate_preview(f.service, f.key, f.root,
                        speech_selection=selection if source in ('download', 'reuse') else None)
                self.assertEqual(raised.exception.code, 'textbook_pinyin_pronunciation_invalid')
                self.assertEqual(f.runtime.start_formal_audio_tts.call_count,
                                 calls_before + (1 if source == 'download' else 0))


if __name__ == '__main__':
    unittest.main()
