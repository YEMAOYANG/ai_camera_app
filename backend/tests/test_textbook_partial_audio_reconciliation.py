import unittest
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import json

from content.textbook_catalog import canonical
from core.errors import ApiError
from services.textbook_partial_audio_reconciliation import _checkpoint_prefix, _receipt_prefix, reconcile_partial_audio
from services.textbook_preview_audio import atomic_partial_audio_json
from services.course_file_store import CourseFileStorageError


class ReconciliationGuardTest(unittest.TestCase):
    def test_unresolved_claim_can_upgrade_and_append_in_same_order(self):
        old = [{'requestId': 'r1', 'status': 'succeeded', 'audioSha256': 'a'},
               {'requestId': 'r2', 'status': 'unknown', 'audioSha256': None}]
        new = [old[0], {'requestId': 'r2', 'status': 'succeeded', 'audioSha256': 'b'},
               {'requestId': 'r3', 'status': 'succeeded', 'audioSha256': 'c'}]
        _receipt_prefix(old, new)

    def test_failed_or_conflicting_receipt_cannot_be_promoted(self):
        for before in ({'requestId': 'r', 'status': 'failed', 'audioSha256': None},
                       {'requestId': 'r', 'status': 'succeeded', 'audioSha256': 'a'}):
            with self.assertRaises(ApiError):
                _receipt_prefix([before], [{'requestId': 'r', 'status': 'succeeded', 'audioSha256': 'b'}])

    def test_missing_reordered_or_duplicate_claims_are_rejected(self):
        old = [{'requestId': 'r1', 'status': 'unknown'}]
        for new in ([], [{'requestId': 'r2', 'status': 'succeeded'}],
                    [{'requestId': 'r1', 'status': 'succeeded'}, {'requestId': 'r1', 'status': 'succeeded'}]):
            with self.assertRaises(ApiError):
                _receipt_prefix(old, new)

    def test_checkpoint_can_only_add_audio_not_replace_or_change_core(self):
        old = {'id': 'room', 'stage': {'id': 'room'}, 'scenes': [{'id': 's', 'actions': [
            {'id': 'a', 'type': 'speech', 'text': '一句', 'audioId': 'r',
             'audioUrl': '/r', 'audioMetadata': {'voiceId': 'v'}},
            {'id': 'b', 'type': 'speech', 'text': '二句'}]}]}
        from copy import deepcopy
        new = deepcopy(old)
        new['scenes'][0]['actions'][1]['audioId'] = 'r2'
        _checkpoint_prefix(old, new)
        new['scenes'][0]['actions'][0]['audioId'] = 'different'
        with self.assertRaises(ApiError): _checkpoint_prefix(old, new)
        new = deepcopy(old); new['scenes'][0]['actions'][1]['text'] = 'change'
        with self.assertRaises(ApiError): _checkpoint_prefix(old, new)


class ReconciliationCASTest(unittest.TestCase):
    def setUp(self):
        self.root = Path('/private/tmp/test-audio-reconcile')
        self.values = [b'old-receipts', b'old-checkpoint']
        self.paths = [self.root / 'receipts.json', self.root / 'checkpoint.json']
        self.p = {'previewKey': 'a' * 64, 'classroomId': 'c', 'classroomSha256': 'b' * 64,
            'planSha256': 'c' * 64, 'dbReceiptsSha256': 'd' * 64,
            'receiptsPath': str(self.paths[0]), 'checkpointPath': str(self.paths[1]),
            'receiptsOldSha256': hashlib.sha256(self.values[0]).hexdigest(),
            'checkpointOldSha256': hashlib.sha256(self.values[1]).hexdigest(),
            'receiptsNew': [{'requestId': 'r', 'status': 'succeeded'}], 'checkpointNew': {'id': 'c'},
            'oldReceipts': [], 'oldCheckpoint': {}, 'receiptCount': 1, 'boundCount': 0,
            'scopes': [{'metadata': {}}, {'metadata': {}}]}
        self.fences = {k: self.p[k] for k in ('previewKey', 'classroomSha256', 'planSha256',
            'dbReceiptsSha256', 'receiptsOldSha256', 'checkpointOldSha256')}
        self.writes = []
        test = self
        class Writer:
            root = test.root
            def _policy(self, *args): return 'validated'
            def write_bytes(self, path, raw, *, expected_sha256):
                index = test.paths.index(path)
                if hashlib.sha256(test.values[index]).hexdigest() != expected_sha256:
                    raise RuntimeError('CAS conflict')
                test.writes.append(index)
                test.values[index] = raw
                return {'sha256': hashlib.sha256(raw).hexdigest()}
        self.service = SimpleNamespace(get=lambda _: {'classroom_id': 'c'},
                                       repository=SimpleNamespace(transaction=lambda: nullcontext(object())))
        self.patches = [patch('services.textbook_partial_audio_reconciliation.prepare_reconciliation', return_value=self.p),
            patch('services.textbook_operator_revision_service.locked', side_effect=lambda *_: nullcontext()),
            patch('services.course_file_writer.CourseFileWriter', Writer),
            patch('services.textbook_partial_audio_reconciliation.course_bytes',
                  side_effect=lambda path: test.values[test.paths.index(path)])]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    def test_dry_run_never_writes(self):
        value = reconcile_partial_audio(self.service, self.p['previewKey'], self.root)
        self.assertEqual(value['status'], 'validated_not_applied')
        self.assertEqual(self.writes, [])

    def test_fenced_success_cas_order_and_readback(self):
        value = reconcile_partial_audio(self.service, self.p['previewKey'], self.root,
                                        expected_fences=self.fences, execute=True)
        self.assertEqual(value['status'], 'reconciled')
        self.assertEqual(self.writes, [0, 1])
        self.assertEqual(self.values[0], canonical(self.p['receiptsNew']).encode())

    def test_changed_fence_stops_without_writing(self):
        self.fences['planSha256'] = 'e' * 64
        with self.assertRaises(ApiError):
            reconcile_partial_audio(self.service, self.p['previewKey'], self.root,
                                    expected_fences=self.fences, execute=True)
        self.assertEqual(self.writes, [])

    def test_changed_remote_head_stops_without_checkpoint_write(self):
        self.values[0] = b'concurrent'
        with self.assertRaisesRegex(RuntimeError, 'CAS conflict'):
            reconcile_partial_audio(self.service, self.p['previewKey'], self.root,
                                    expected_fences=self.fences, execute=True)
        self.assertEqual(self.writes, [])

    def test_checkpoint_conflict_keeps_receipt_update_and_does_not_retry(self):
        self.values[1] = b'concurrent-checkpoint'
        with self.assertRaisesRegex(RuntimeError, 'CAS conflict'):
            reconcile_partial_audio(self.service, self.p['previewKey'], self.root,
                                    expected_fences=self.fences, execute=True)
        self.assertEqual(self.writes, [0])
        self.assertEqual(self.values[0], canonical(self.p['receiptsNew']).encode())
        self.assertEqual(self.values[1], b'concurrent-checkpoint')


class RegistryCutoverTest(unittest.TestCase):
    def test_receipt_cutover_reads_verified_head_then_retries_only_file_cas(self):
        old = [{'requestId': 'r1', 'status': 'unknown', 'audioSha256': None}]
        new = [{'requestId': 'r1', 'status': 'succeeded', 'audioSha256': 'a'}]
        with patch('services.textbook_preview_audio.atomic_json', side_effect=[
                CourseFileStorageError('Course file must be read before it is updated'), None]) as write, \
             patch('services.textbook_preview_audio.course_text', return_value=json.dumps(old)) as read:
            atomic_partial_audio_json(Path('receipts.json'), new)
        self.assertEqual(write.call_count, 2)
        self.assertEqual(read.call_count, 1)

    def test_divergent_registered_head_stops_before_second_write(self):
        old = [{'requestId': 'someone-else', 'status': 'succeeded'}]
        new = [{'requestId': 'r1', 'status': 'succeeded'}]
        with patch('services.textbook_preview_audio.atomic_json', side_effect=
                   CourseFileStorageError('Course file must be read before it is updated')) as write, \
             patch('services.textbook_preview_audio.course_text', return_value=json.dumps(old)):
            with self.assertRaises(ApiError): atomic_partial_audio_json(Path('receipts.json'), new)
        self.assertEqual(write.call_count, 1)

    def test_unrelated_failure_is_not_retried(self):
        with patch('services.textbook_preview_audio.atomic_json', side_effect=
                   CourseFileStorageError('Course file storage unavailable')) as write, \
             patch('services.textbook_preview_audio.course_text') as read:
            with self.assertRaises(CourseFileStorageError): atomic_partial_audio_json(Path('receipts.json'), [])
        self.assertEqual(write.call_count, 1)
        self.assertEqual(read.call_count, 0)

    def test_checkpoint_cutover_requires_monotonic_bindings(self):
        old = {'id': 'c', 'stage': {'id': 'c'}, 'scenes': [{'id': 's', 'actions': [
            {'id': 'a', 'type': 'speech', 'text': 'hi', 'audioId': 'old'}]}]}
        new = deepcopy(old); new['scenes'][0]['actions'][0]['audioId'] = 'other'
        with patch('services.textbook_preview_audio.atomic_json', side_effect=
                   CourseFileStorageError('Course file must be read before it is updated')) as write, \
             patch('services.textbook_preview_audio.course_text', return_value=json.dumps(old)):
            with self.assertRaises(ApiError): atomic_partial_audio_json(Path('checkpoint.json'), new)
        self.assertEqual(write.call_count, 1)



if __name__ == '__main__':
    unittest.main()
