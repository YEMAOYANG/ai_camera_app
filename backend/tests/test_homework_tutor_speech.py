"""Owned pronunciation repair using isolated SQL, files and fake WAV transport.

These cases verify text and paid-call contracts, not a real voice model's sound.
Ordinals change only in speech inputs; source teaching and paper grades stay put.
"""
from copy import deepcopy
import base64
import hashlib
import io
import json
from unittest import TestCase
from unittest.mock import patch
import wave

from services import homework_tutor_service as tutor_module
from services.homework_service import canonical
from services.teacher_speech import normalize_teacher_speech
from tests import test_homework_analysis as fixtures
from tests import test_homework_tutor as tutor_fixtures


class HomeworkTutorSpeechTests(TestCase):
    create = fixtures.HomeworkTest.create
    upload = fixtures.HomeworkTest.upload
    ready = fixtures.HomeworkTest.ready
    error = fixtures.HomeworkTest.error
    events = fixtures.HomeworkTest.events

    def setUp(self):
        fixtures.HomeworkTest.setUp(self)
        # Different texts produce different anonymous WAV bytes, so revocation
        # must queue both actual files rather than one shared fixture artifact.
        def distinct_sound(payload, headers):
            output = io.BytesIO()
            with wave.open(output, 'wb') as sound:
                sound.setnchannels(1); sound.setsampwidth(2); sound.setframerate(16000)
                sound.writeframes(hashlib.sha256(payload['text'].encode()).digest()[:2]*1600)
            return {'success': True, 'audioId': payload['audioId'], 'format': 'wav',
                'base64': base64.b64encode(output.getvalue()).decode()}
        self.transport.side_effect = distinct_sound

    def prepared(self):
        submission = self.ready()
        public = submission['items'][0]
        turn = self.service.tutor.submit('student-a', submission['id'], public['id'],
            {'itemRevision': public['revision'], 'idempotencyKey': 'pronunciation',
                'mode': 'explain', 'message': ''})['tutor']['turns'][0]
        record = self.db.execute('SELECT * FROM homework_actions WHERE id=?', (turn['id'],)).fetchone()
        self.turn = json.loads(record['result_json'])
        self.row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (submission['id'],)).fetchone()
        self.item = self.db.execute('SELECT * FROM homework_items WHERE id=?', (public['id'],)).fetchone()
        self.result = json.loads(self.item['result_json'])
        self.reply = tutor_fixtures.teacher_reply(
            teacherText='看第2棵树，先数2个果子；两棵树合起来看。',
            steps=[{'text': '第２个位置有2个，另一组有3个，3+2=5。',
                'visual': {'kind': 'groups', 'groups': [3, 2]}}])
        self.raw_speech = self.reply['teacherText']+' '+self.reply['steps'][0]['text']
        self.original_reply = deepcopy(self.reply)
        self.original_item_json = self.item['result_json']
        self.events_before = self.events()
        self.vision_before = self.provider.analyze_image.call_count
        self.voice_before = self.transport.call_count
        self.base_id = 'hwtaudio_'+tutor_module.sha(self.turn['id'])[:56]

    def receipt(self, identity):
        return self.db.execute('SELECT * FROM homework_audio_receipts WHERE id=?', (identity,)).fetchone()

    def repair_id(self):
        return 'hwtaudio_'+tutor_module.sha([self.turn['id'], tutor_module.SPEECH_POLICY_VERSION])[:56]

    def voice(self, *, repair=False):
        return self.service.tutor._voice(self.turn, self.row, self.item, self.reply,
            result=self.result, repair_speech=repair)

    def persist_ready(self, media):
        self.turn.update(self.reply, status='ready', audio=media, leaseUntil=None)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',
            (canonical(self.turn), self.turn['id']))
        self.db.raw.commit()

    def legacy_ready(self):
        # Construct a genuine pre-normalization receipt through the real audio
        # service. Only the new formatter is disabled during this old dispatch.
        with patch('services.homework_audio_service.normalize_teacher_speech', side_effect=lambda text, **_: text):
            media = self.audio.ensure(request_id=self.base_id, text=self.raw_speech,
                subject='math', submission_id=self.row['id'], item_id=self.item['id'], revision=self.item['revision'])
        self.assertEqual(self.transport.call_args.args[0]['text'], self.raw_speech)
        self.persist_ready(media)
        return media

    def assert_source_unchanged(self):
        self.assertEqual(self.reply, self.original_reply)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',
            (self.item['id'],)).fetchone()['result_json'], self.original_item_json)
        self.assertEqual(self.events(), self.events_before)
        self.assertEqual(self.provider.analyze_image.call_count, self.vision_before)

    def test_audio_boundary_converts_only_ordinals_and_keeps_quantity_math_and_display(self):
        self.prepared()
        text = '第2棵有2个果子，第１２题看两棵树，第20页有20个，2+3=5。'
        before = self.transport.call_count
        media = self.audio.ensure(request_id='speech-payload', text=text, subject='math',
            submission_id=self.row['id'], item_id=self.item['id'], revision=self.item['revision'])
        payload = self.transport.call_args.args[0]
        self.assertEqual(payload['text'], '第二棵有2个果子，第十二题看两棵树，第二十页有20个，2+3=5。')
        self.assertEqual(text, '第2棵有2个果子，第１２题看两棵树，第20页有20个，2+3=5。')
        self.assertEqual(self.receipt('speech-payload')['character_count'], len(payload['text']))
        self.assertEqual(self.audio.ensure(request_id='speech-payload', text=text, subject='math',
            submission_id=self.row['id'], item_id=self.item['id'], revision=self.item['revision']), media)
        self.assertEqual(self.transport.call_count, before+1)
        self.assert_source_unchanged()

    def test_new_turn_speech_says_second_without_rewriting_the_visible_lesson(self):
        self.prepared(); media = self.voice()
        self.assertEqual(media['status'], 'ready')
        payload = self.transport.call_args.args[0]
        self.assertEqual(payload['text'], normalize_teacher_speech(self.raw_speech))
        self.assertIn('第二棵', payload['text']); self.assertIn('第二个位置', payload['text'])
        self.assertIn('2个', payload['text']); self.assertIn('两棵树', payload['text']); self.assertIn('3+2=5', payload['text'])
        self.assertEqual(self.transport.call_count, self.voice_before+1)
        self.assert_source_unchanged()

    def test_old_ready_turn_and_default_voice_reuse_old_sound_without_silent_charge(self):
        self.prepared(); media = self.legacy_ready(); saved = dict(self.receipt(self.base_id))
        before = self.transport.call_count
        self.assertEqual(self.voice(), media)
        for _ in range(3):
            public = self.service.tutor.get('student-a', self.row['id'], self.item['id'])['tutor']['turns'][0]
            self.assertEqual(public['audio']['status'], 'ready')
            self.assertEqual(public['teacherText'], self.original_reply['teacherText'])
            self.assertTrue(self.service.tutor.audio('student-a', self.row['id'], self.item['id'], self.turn['id'])[0])
        self.assertEqual(self.transport.call_count, before)
        self.assertEqual(dict(self.receipt(self.base_id)), saved)
        self.assertIsNone(self.receipt(self.repair_id()))
        self.assert_source_unchanged()

    def test_explicit_repair_has_one_versioned_dispatch_cache_and_immutable_old_receipt(self):
        self.prepared(); old = self.legacy_ready(); original = dict(self.receipt(self.base_id))
        before = self.transport.call_count
        repaired = self.voice(repair=True)
        self.assertEqual(repaired['status'], 'ready')
        self.assertEqual(repaired['receiptId'], self.repair_id())
        self.assertNotEqual(repaired['receiptId'], old['receiptId'])
        self.assertNotEqual(repaired['storageKey'], old['storageKey'])
        self.assertEqual(self.transport.call_args.args[0]['text'], normalize_teacher_speech(self.raw_speech))
        for _ in range(3):
            self.assertEqual(self.voice(repair=True), repaired)
        self.assertEqual(self.transport.call_count, before+1)
        self.assertEqual(dict(self.receipt(self.base_id)), original)
        self.assertEqual(self.receipt(repaired['receiptId'])['status'], 'succeeded')
        self.assert_source_unchanged()

    def test_unknown_or_dispatched_old_sound_cannot_be_bypassed_by_speech_policy(self):
        self.prepared(); self.legacy_ready(); before = self.transport.call_count
        for status in ('unknown', 'dispatched'):
            with self.subTest(status=status):
                self.db.execute('UPDATE homework_audio_receipts SET status=? WHERE id=?', (status, self.base_id))
                self.db.raw.commit()
                for repair in (False, True):
                    media = self.voice(repair=repair)
                    self.assertEqual(media['status'], 'unavailable')
                    self.assertEqual(media['errorCode'], 'homework_audio_unknown')
                self.assertEqual(self.receipt(self.base_id)['status'], status)
                self.assertIsNone(self.receipt(self.repair_id()))
                self.assertEqual(self.transport.call_count, before)
        self.assert_source_unchanged()

    def test_old_receipt_scope_cannot_be_reused_or_repaired_for_another_owner_or_revision(self):
        self.prepared(); self.legacy_ready(); before = self.transport.call_count
        fields = {'submission_id': 'another-submission', 'item_id': 'another-item', 'revision': 2}
        for field, value in fields.items():
            with self.subTest(field=field):
                self.db.execute('UPDATE homework_audio_receipts SET '+field+'=? WHERE id=?', (value, self.base_id))
                self.db.raw.commit()
                for repair in (False, True):
                    self.assertEqual(self.voice(repair=repair)['status'], 'unavailable')
                self.assertEqual(self.transport.call_count, before)
                self.assertIsNone(self.receipt(self.repair_id()))
                correct = self.row['id'] if field == 'submission_id' else self.item['id'] if field == 'item_id' else self.item['revision']
                self.db.execute('UPDATE homework_audio_receipts SET '+field+'=? WHERE id=?', (correct, self.base_id))
                self.db.raw.commit()
        self.error('homework_not_found', lambda: self.service.tutor.audio('student-b',
            self.row['id'], self.item['id'], self.turn['id']))
        self.assert_source_unchanged()

    def test_revoke_removes_both_speech_versions_and_queues_both_owned_sound_files(self):
        self.prepared(); old = self.legacy_ready(); repaired = self.voice(repair=True)
        self.assertEqual(repaired['status'], 'ready')
        unrelated = self.db.execute('SELECT * FROM homework_audio_receipts WHERE submission_id=? AND id NOT LIKE ? LIMIT 1',
            (self.row['id'], 'hwtaudio_%')).fetchone()
        self.assertIsNotNone(unrelated)
        before = self.transport.call_count
        with self.service.repository.transaction() as conn:
            self.service.tutor.revoke(conn, self.row)
        for identity in (self.base_id, self.repair_id()):
            receipt = self.receipt(identity)
            self.assertEqual(receipt['status'], 'deleted')
            self.assertIsNone(receipt['result_json'])
        deleted = {value['storage_key'] for value in self.db.execute('SELECT * FROM homework_file_deletions').fetchall()}
        self.assertIn(old['storageKey'], deleted)
        self.assertIn(repaired['storageKey'], deleted)
        self.assertEqual(dict(self.receipt(unrelated['id'])), dict(unrelated))
        action = self.db.execute('SELECT result_json FROM homework_actions WHERE id=?', (self.turn['id'],)).fetchone()
        self.assertEqual(json.loads(action['result_json'])['status'], 'revoked')
        self.error('homework_tutor_audio_not_ready', lambda: self.service.tutor.audio('student-a',
            self.row['id'], self.item['id'], self.turn['id']))
        self.assertEqual(self.transport.call_count, before)
        self.assert_source_unchanged()
