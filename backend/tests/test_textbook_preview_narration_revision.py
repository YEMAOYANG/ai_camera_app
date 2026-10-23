"""Partial narration repairs use fake providers, an isolated DB and temporary WAVs."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import interactive_cues
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_preview_audio import narrate_preview
from services.textbook_preview_narration_revision import SCHEMA, revise_preview_narration, sha_bytes
from tests import test_textbook_preview_visual_revision as visual_fixtures


class NarrationRevisionTests(unittest.TestCase):
    def setUp(self):
        fixture = visual_fixtures.VisualRevisionTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        for field in ('service', 'runtime', 'db', 'key', 'root', 'cid', 'folder', 'source_sha'):
            setattr(self, field, getattr(fixture, field))
        self.original = deepcopy(fixture.classroom)
        self.original_wavs = {p.name: p.read_bytes() for p in (self.root / self.cid / 'audio').iterdir()}
        self.original_receipts = (self.folder / 'receipts.json').read_bytes()
        self.original_plan = (self.folder / 'plan.json').read_bytes()
        self.audit = {'schemaVersion': 'mira.textbook.audio-audit.v1', 'previewKey': self.key,
                      'sourceSha256': self.source_sha, 'segments': [], 'passed': False}
        for i, scene in enumerate(self.original['scenes']):
            action = scene['actions'][0]
            transcript = '完全不同。' if i in (0, 5) else action['text']
            self.audit['segments'].append({'sceneId': scene['id'], 'actionId': action['id'],
                'ttsRequestId': action['audioId'], 'audioSha256': sha_bytes(self.original_wavs[action['audioId'] + '.wav']),
                'textSha256': sha_bytes(action['text'].encode()), 'text': action['text'], 'transcript': transcript,
                'durationMs': 1000, 'similarityBps': asr_similarity_bps(action['text'], transcript),
                'asr': {'status': 'succeeded', 'transcript': transcript, 'transcriptSha256': sha_bytes(transcript.encode())}})
        self.audit['sha256'] = digest(self.audit)
        self.audit_path = self.root / 'failed-audit.json'
        self.audit_path.write_text(canonical(self.audit))
        self.revision = {'schemaVersion': SCHEMA, 'expectedSourceSha256': self.source_sha,
                         'reviewer': 'operator', 'basis': '只修两个识别失败的短句', 'changes': [
            {'sceneId': 'scene-0', 'actionId': 'action-0', 'beforeTextSha256': sha_bytes('数一数。'.encode()), 'text': '看图，数一数有几个。'},
            {'sceneId': 'scene-5', 'actionId': 'action-5', 'beforeTextSha256': sha_bytes('数一数。'.encode()), 'text': '请你点一点图片。'}]}
        self.provider_receipts = {}
        self.runtime.get_formal_audio_tts.side_effect = self.get_tts
        self.runtime.start_formal_audio_tts.side_effect = self.start_tts
        self.runtime.download_formal_audio_tts.return_value = next(iter(self.original_wavs.values()))

    def get_tts(self, request):
        if request not in self.provider_receipts:
            raise OpenMaicFullRuntimeError('not_found', 'not found', status_code=404)
        return deepcopy(self.provider_receipts[request])

    def start_tts(self, **kwargs):
        value = {'requestId': kwargs['request_id'], 'status': 'succeeded', 'mimeType': 'audio/wav',
                 'audioSha256': sha_bytes(next(iter(self.original_wavs.values())))}
        self.provider_receipts[kwargs['request_id']] = value
        return deepcopy(value)

    def run_revision(self, *, execute=True, revision=None, retry=False):
        return revise_preview_narration(self.service, self.key, self.root, revision or self.revision,
            self.audit_path, execute=execute, retry_recorded_failure=retry)

    def archive(self):
        return self.folder / 'narration-revisions' / digest({'previewKey': self.key, 'patch': self.revision,
                                                          'failedAuditSha256': sha_bytes(self.audit_path.read_bytes())})

    def test_prepare_is_free_and_two_line_repair_preserves_every_other_action_and_wav(self):
        prepared = self.run_revision(execute=False)
        self.assertTrue(prepared['prepared'])
        self.assertEqual(prepared['segments'], 2)
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.save_preview_classroom.assert_not_called()
        receipt = self.run_revision()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        for before, after in zip(self.original['scenes'], self.fixture.classroom['scenes']):
            if before['id'] not in ('scene-0', 'scene-5'):
                self.assertEqual(before, after)
        self.assertEqual(interactive_cues(self.fixture.classroom['scenes'][5]['content']['html'])[0]['text'], '请你点一点图片。')
        for name, raw in self.original_wavs.items():
            self.assertEqual((self.root / self.cid / 'audio' / name).read_bytes(), raw)
        self.assertEqual((self.folder / 'plan.json').read_bytes(), self.original_plan)
        self.assertEqual((self.archive() / 'original-receipts.json').read_bytes(), self.original_receipts)
        self.assertEqual((self.archive() / 'failed-audit.json').read_bytes(), self.audit_path.read_bytes())
        self.assertEqual(len(json.loads((self.folder / 'receipts.json').read_text())), 10)
        self.assertEqual(self.run_revision(), receipt)
        narrate_preview(self.service, self.key, self.root)
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_formal_audio_asr.assert_not_called()
        self.runtime.start_generation.assert_not_called()

    def test_source_freeze_after_prepare_preserves_intent_and_allows_same_revision(self):
        self.run_revision(execute=False)
        intent = (self.archive() / 'intent.json').read_bytes()
        snapshot_id = 'tbprev_' + self.source_sha[:24]
        def replace(value):
            if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
            if isinstance(value, list): return [replace(v) for v in value]
            return snapshot_id if value == self.cid else value
        snapshot = replace(self.original)
        (self.root / (snapshot_id + '.json')).write_text(canonical(snapshot))
        self.runtime.get_classroom.side_effect = lambda cid: deepcopy(snapshot if cid == snapshot_id else self.fixture.classroom)
        row = self.service.get(self.key)
        result = json.loads(row['result_json'])
        result['frozenPreview'] = {'classroomId': snapshot_id, 'sourceSha256': self.source_sha,
                                   'snapshotSha256': digest(snapshot)}
        self.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                        (canonical(result), self.key))
        self.run_revision()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        self.assertEqual((self.archive() / 'intent.json').read_bytes(), intent)
        self.assertTrue((self.archive() / 'source-preview-freeze.json').is_file())
        self.assertEqual(json.loads((self.root / (snapshot_id + '.json')).read_text()), snapshot)

    def test_other_result_changes_after_prepare_still_block_before_calls(self):
        self.run_revision(execute=False)
        row = self.service.get(self.key)
        result = json.loads(row['result_json'])
        result['audioSeconds'] = 999
        self.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                        (canonical(result), self.key))
        with self.assertRaises(ApiError): self.run_revision()
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_forged_source_preview_freeze_cannot_waive_changed_scene(self):
        self.run_revision(execute=False)
        snapshot_id = 'tbprev_' + self.source_sha[:24]
        snapshot = deepcopy(self.original)
        snapshot['id'] = snapshot_id
        snapshot['scenes'][0]['actions'][0]['text'] = 'changed scene'
        (self.root / (snapshot_id + '.json')).write_text(canonical(snapshot))
        self.runtime.get_classroom.side_effect = lambda cid: deepcopy(snapshot if cid == snapshot_id else self.fixture.classroom)
        result = json.loads(self.service.get(self.key)['result_json'])
        result['frozenPreview'] = {'classroomId': snapshot_id, 'sourceSha256': self.source_sha,
                                   'snapshotSha256': digest(snapshot)}
        self.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                        (canonical(result), self.key))
        with self.assertRaises(ApiError): self.run_revision()
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_passed_segments_stale_audit_changed_text_and_tampered_transcript_rejected_before_calls(self):
        changed = deepcopy(self.revision)
        changed['changes'][0].update(sceneId='scene-1', actionId='action-1')
        with self.assertRaises(ApiError):
            self.run_revision(revision=changed)
        changed = deepcopy(self.revision)
        changed['changes'][0]['beforeTextSha256'] = 'f' * 64
        with self.assertRaises(ApiError):
            self.run_revision(revision=changed)
        changed = deepcopy(self.revision)
        changed['expectedSourceSha256'] = 'f' * 64
        with self.assertRaises(ApiError):
            self.run_revision(revision=changed)
        audit = deepcopy(self.audit)
        audit['segments'][0]['transcript'] = '数一数。'
        audit['sha256'] = digest({k: v for k, v in audit.items() if k != 'sha256'})
        self.audit_path.write_text(canonical(audit))
        with self.assertRaises(ApiError):
            self.run_revision()
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_tts_response_loss_recovers_receipt_without_repeating_call(self):
        def lost(**kwargs):
            result = self.start_tts(**kwargs)
            if len(self.provider_receipts) == 1:
                raise TimeoutError('response lost')
            return result
        self.runtime.start_formal_audio_tts.side_effect = lost
        with self.assertRaises(TimeoutError):
            self.run_revision()
        self.runtime.start_formal_audio_tts.side_effect = self.start_tts
        self.run_revision()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)

    def test_unknown_dispatch_is_not_reposted_even_with_retry_flag(self):
        self.runtime.start_formal_audio_tts.side_effect = TimeoutError('unknown')
        with self.assertRaises(TimeoutError):
            self.run_revision()
        with self.assertRaises(ApiError):
            self.run_revision(retry=True)
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_recorded_failure_requires_explicit_new_identity_and_retains_failed_receipt(self):
        def failed(**kwargs):
            value = {'requestId': kwargs['request_id'], 'status': 'ambiguous', 'audioSha256': None, 'mimeType': None}
            self.provider_receipts[kwargs['request_id']] = value
            return value
        self.runtime.start_formal_audio_tts.side_effect = failed
        with self.assertRaises(ApiError):
            self.run_revision()
        first = self.runtime.start_formal_audio_tts.call_args.kwargs['request_id']
        with self.assertRaises(ApiError):
            self.run_revision()
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.start_formal_audio_tts.side_effect = self.start_tts
        self.run_revision(retry=True)
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 3)
        requests = [c.kwargs['request_id'] for c in self.runtime.start_formal_audio_tts.call_args_list]
        self.assertEqual(len(set(requests)), 3)
        receipts = json.loads((self.folder / 'receipts.json').read_text())
        self.assertEqual(next(r for r in receipts if r['requestId'] == first)['status'], 'ambiguous')

    def test_save_response_loss_and_post_commit_interruption_reconcile_without_new_calls(self):
        def lost(value):
            self.fixture.save(value)
            raise TimeoutError('save response lost')
        self.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError):
            self.run_revision()
        self.assertEqual(self.service.get(self.key)['classroom_sha256'], self.source_sha)
        from services import textbook_preview_narration_revision as module
        real = module.immutable
        def after_commit(path, raw):
            if path.name == 'amendment.json':
                raise OSError('after commit')
            real(path, raw)
        with patch.object(module, 'immutable', side_effect=after_commit), self.assertRaises(OSError):
            self.run_revision()
        receipt = self.run_revision()
        self.assertEqual(receipt['targetSha256'], self.service.get(self.key)['classroom_sha256'])
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        self.runtime.save_preview_classroom.assert_called_once()

    def test_unknown_save_is_not_reposted_and_archive_tamper_stops_recovery(self):
        self.runtime.save_preview_classroom.side_effect = TimeoutError('unknown save')
        with self.assertRaises(TimeoutError):
            self.run_revision()
        with self.assertRaises(ApiError):
            self.run_revision()
        self.runtime.save_preview_classroom.assert_called_once()
        (self.archive() / 'original-plan.json').write_text('{}')
        with self.assertRaises(ApiError):
            self.run_revision()

    def test_asr_reuses_old_cache_and_only_sends_two_new_calls_with_new_plan_identity(self):
        from scripts import audit_textbook_audio as audit_script
        output = self.root / 'audio-audit'
        output.mkdir()
        for entry in self.audit['segments']:
            request = 'tbasr_' + digest({'tts': entry['ttsRequestId'], 'audio': entry['audioSha256']})
            (output / (request + '.json')).write_text(canonical(entry))
        old_cache = {p.name: p.read_bytes() for p in output.iterdir()}
        receipt = self.run_revision()
        by_request = {a['audioId']: a['text'] for s in self.fixture.classroom['scenes'] for a in s['actions']}
        self.runtime.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('not_found', 'not found', status_code=404)
        self.runtime.start_formal_audio_asr.side_effect = lambda **kw: {
            'status': 'succeeded', 'requestId': kw['request_id'], 'transcript': by_request[kw['tts_request_id']]}
        argv = ['audit_textbook_audio.py', '--key', self.key, '--classroom-directory', str(self.root), '--output', str(output)]
        with patch.object(audit_script.AppConfig, 'from_env'), patch.object(audit_script, 'Database', return_value=self.db), \
                patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=self.runtime), patch('sys.argv', argv):
            audit_script.main()
            audit_script.main()
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 2)
        self.assertEqual({c.kwargs['classroom_content_sha256'] for c in self.runtime.start_formal_audio_asr.call_args_list},
                         {receipt['audioIdentityClassroomSha256']})
        for name, raw in old_cache.items():
            self.assertEqual((output / name).read_bytes(), raw)
        final = json.loads((output / 'audit.json').read_text())
        self.assertTrue(final['passed'])
        self.assertEqual(len(final['segments']), 8)
        self.assertEqual(final['sourceSha256'], receipt['targetSha256'])


if __name__ == '__main__':
    unittest.main()
