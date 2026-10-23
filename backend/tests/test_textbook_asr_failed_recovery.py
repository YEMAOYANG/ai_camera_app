"""Bounded failed-routine recovery with synthetic bytes and a fake client only."""
import base64
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest
from content.textbook_asr_source_reuse import (
    FAILED_RECOVERY_ORIGIN_SCHEMA, FAILURE_RECOVERY_SCHEMA, LIBRARY_SCHEMA_V2,
    ORIGIN_SCHEMA, build_audit, build_failed_recovery_origin, failed_recovery_id,
    formal_request, sha, target_evidence, validate_audit, verify_origin,
)
from content.textbook_audio_recheck import provider_body as asr_body
from content.textbook_pinyin_operator_review_v5 import build_operator_review_v5
from content.textbook_preview_audio_contract import asr_request_id
from core.errors import ApiError
from services.textbook_asr_source_reuse import PcmLedger, collect, recover_failed_origins
from tests import test_textbook_asr_source_reuse as fixtures


def raw_json(value):
    # Preserve deliberately noncanonical original bytes, including whitespace.
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


class FailedRoutineRecoveryTests(unittest.TestCase):
    def setUp(self):
        # Compose the shared fixture without inheriting its unrelated test cases.
        self.original = fixtures.AsrOriginTests()
        self.original.setUp()
        self.addCleanup(self.original.doCleanups)
        self.f, self.fx = self.original.f, self.original.fx
        for index, scene in enumerate(self.f.classroom['scenes'], 1):
            scene['order'] = index
        self.fx.sync_source()
        old_responses = [deepcopy(origin['attempts'][0]['response']) for origin in self.original.origins]
        self.original.targets = [self.original.target(scene, index)
            for index, scene in enumerate(self.f.classroom['scenes'][:2])]
        self.original.origins = [self.original.origin(target, response)
            for target, response in zip(self.original.targets, old_responses)]
        self.original.audit = self.original.make_audit()
        self.original.review = self.original.make_review()
        self.target = deepcopy(self.original.targets[1])
        facts = target_evidence(self.target, self.f.plan)
        self.failed_id = asr_request_id(self.f.plan, self.target['action']['audioId'], sha(facts['audio']))
        request = formal_request(self.target, self.f.plan, self.f.cid, self.failed_id)
        self.job = {
            'schemaVersion': 'mira.openmaic.formal-audio-job.v1', 'kind': 'asr', **request,
            'languageCode': 'zh-CN', 'state': 'failed', 'providerId': 'qwen-asr',
            'modelId': 'qwen3-asr-flash', 'fallbackUsed': False,
            'providerAttemptedAt': '2026-10-22T01:00:00.000Z',
            'createdAt': '2026-10-22T01:00:00.000Z', 'updatedAt': '2026-10-22T01:00:01.000Z',
            'completedAt': '2026-10-22T01:00:01.000Z', 'safeErrorCode': 'provider_rejected',
            'providerPronunciation': deepcopy(self.target['ttsReceipt']['providerPronunciation']),
            'providerAsrBodySha256': sha(asr_body(facts['audio'])),
        }
        self.job['requestSha256'] = digest({'logicalRequest': request,
            'providerPronunciation': self.job['providerPronunciation']})
        self.cache = {
            'sceneId': self.target['sceneId'], 'actionId': self.target['action']['id'],
            'ttsRequestId': self.target['action']['audioId'], 'audioSha256': sha(facts['audio']),
            'textSha256': sha(facts['text'].encode()), 'text': facts['text'],
            'transcript': None, 'durationMs': (
                self.target['ttsReceipt']['audioNormalization']['pcmByteLength'] * 1000
                // (self.target['ttsReceipt']['audioNormalization']['channels']
                    * (self.target['ttsReceipt']['audioNormalization']['bitsPerSample'] // 8)
                    * self.target['ttsReceipt']['audioNormalization']['sampleRate'])), 'similarityBps': 0,
            'asr': {'requestId': self.failed_id, 'status': 'failed', 'transcript': None,
                    'transcriptSha256': None, 'completionUsable': False},
        }
        self.job_raw, self.cache_raw = raw_json(self.job), raw_json(self.cache)
        self.selection = {
            'sceneId': self.target['sceneId'], 'actionId': self.target['action']['id'],
            'failedRequestId': self.failed_id, 'sourceSha256': digest(self.f.classroom),
            'planSha256': digest(self.f.plan), 'audioSha256': sha(facts['audio']),
            'failedJobSha256': sha(self.job_raw), 'failedCacheSha256': sha(self.cache_raw),
        }
        self.pending = self.build_pending()
        self.directory, self.native, self.probes, _ = self.original.ledger_setup()
        self.routine_cache = self.directory / 'routine-cache'
        self.routine_cache.mkdir()
        self.job_path = self.native / 'jobs/asr' / (sha(self.failed_id.encode()) + '.json')
        self.cache_path = self.routine_cache / (self.failed_id + '.json')
        self.job_path.write_bytes(self.job_raw)
        self.cache_path.write_bytes(self.cache_raw)
        (self.native / 'jobs/tts' / (sha(self.target['action']['audioId'].encode()) + '.json')).write_bytes(
            raw_json(self.target['ttsReceipt']))
        self.ledger = self.new_ledger()
        self.client = self.original.fake_client(self.target, self.target['action']['text'])
        self.library = {'schemaVersion': LIBRARY_SCHEMA_V2,
            'origins': [deepcopy(self.original.origins[0])], 'probeProtocol': None}

    def new_ledger(self):
        return PcmLedger(self.directory / 'classrooms', self.native, [self.probes],
            routine_cache_directory=self.routine_cache)

    def build_pending(self, **changes):
        arguments = dict(source=self.target, plan=self.f.plan, classroom=self.f.classroom,
            selection=self.selection, failed_job_raw=self.job_raw, failed_cache_raw=self.cache_raw)
        arguments.update(changes)
        return build_failed_recovery_origin(**arguments)

    def collect(self, **changes):
        arguments = dict(plan=self.f.plan, classroom=self.f.classroom,
            targets=self.original.targets, library=self.library, ledger=self.ledger,
            client=self.client, failed_recoveries=[self.pending])
        arguments.update(changes)
        return collect(**arguments)

    def recovery_origin(self, audit):
        return next(origin for origin in audit['origins']
                    if origin['schemaVersion'] == FAILED_RECOVERY_ORIGIN_SCHEMA)

    def test_selection_preserves_complete_original_bytes_and_deterministic_identity(self):
        envelope = self.pending['failureRecovery']
        self.assertEqual(envelope['schemaVersion'], FAILURE_RECOVERY_SCHEMA)
        self.assertEqual(base64.b64decode(envelope['failedJobBase64']), self.job_raw)
        self.assertEqual(base64.b64decode(envelope['failedCacheBase64']), self.cache_raw)
        self.assertEqual(len(self.job), 29)
        facts = verify_origin(self.pending)
        expected = failed_recovery_id(self.failed_id, facts['pcmKey'])
        self.assertEqual(envelope['recoveryRequestId'], expected)
        self.assertNotEqual(expected, self.failed_id)
        self.assertEqual(facts['attempts'], [])

    def test_one_post_reused_across_collectors_and_completed_origin_libraries(self):
        before = (self.job_path.read_bytes(), self.cache_path.read_bytes())
        first = self.collect()
        again = self.collect(ledger=self.new_ledger())
        self.assertEqual(first, again)
        completed_library = {'schemaVersion': LIBRARY_SCHEMA_V2,
            'origins': deepcopy(first['origins']), 'probeProtocol': None}
        self.assertEqual(first, self.collect(library=completed_library, failed_recoveries=[]))
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)
        origin = self.recovery_origin(first)
        self.assertEqual(len(origin['attempts']), 1)
        self.assertEqual(origin['attempts'][0]['request']['requestId'],
                         self.pending['failureRecovery']['recoveryRequestId'])
        self.assertEqual(before, (self.job_path.read_bytes(), self.cache_path.read_bytes()))
        self.assertEqual(origin['failureRecovery'], self.pending['failureRecovery'])

    def test_unknown_recovery_consumes_attempt_without_second_post(self):
        self.client._request_formal_audio_json.side_effect = TimeoutError('Synthetic lost response')
        with self.assertRaises(TimeoutError):
            self.collect()
        with self.assertRaises(RuntimeError):
            self.collect(ledger=self.new_ledger())
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)
        self.assertEqual(len(list(self.ledger.root.rglob('claims/*/intent.json'))), 1)

    def test_second_terminal_failure_cannot_be_reposted_or_published(self):
        response = {'requestId': self.pending['failureRecovery']['recoveryRequestId'],
            'status': 'failed', 'transcript': None, 'transcriptSha256': None, 'completionUsable': False}
        self.client._request_formal_audio_json.side_effect = None
        self.client._request_formal_audio_json.return_value = response
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                self.collect(ledger=self.new_ledger())
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)
        self.assertFalse(list(self.ledger.root.rglob('origin.json')))

    def test_every_selection_fence_and_strict_selection_shape_are_enforced(self):
        for key in self.selection:
            changed = deepcopy(self.selection)
            changed[key] = '0' * 64 if key.endswith('Sha256') else 'foreign-identity'
            with self.subTest(field=key), self.assertRaises(ApiError):
                self.build_pending(selection=changed)
        for changed in ({k: v for k, v in self.selection.items() if k != 'actionId'},
                        {**self.selection, 'approved': True}):
            with self.assertRaises(ApiError):
                self.build_pending(selection=changed)
        self.client._request_formal_audio_json.assert_not_called()

    def test_resealed_unknown_job_or_usable_cache_cannot_authorize_recovery(self):
        job_mutations = [('state', 'ambiguous'), ('safeErrorCode', 'timeout'),
            ('requestId', 'foreign'), ('requestSha256', '0' * 64), ('languageCode', 'en-US'),
            ('audioSha256', '0' * 64), ('fallbackUsed', True)]
        for key, value in job_mutations:
            changed = deepcopy(self.job); changed[key] = value; raw = raw_json(changed)
            selected = {**self.selection, 'failedJobSha256': sha(raw)}
            with self.subTest(job=key), self.assertRaises(ApiError):
                self.build_pending(selection=selected, failed_job_raw=raw)
        for key, value in [('transcript', 'Synthetic text'), ('similarityBps', 10000),
                           ('ttsRequestId', 'foreign'), ('durationMs', 0)]:
            changed = deepcopy(self.cache); changed[key] = value; raw = raw_json(changed)
            with self.subTest(cache=key), self.assertRaises(ApiError):
                self.build_pending(selection={**self.selection, 'failedCacheSha256': sha(raw)},
                                   failed_cache_raw=raw)

    def test_original_disk_job_and_cache_changes_block_before_post(self):
        for path, original in [(self.job_path, self.job_raw), (self.cache_path, self.cache_raw)]:
            path.write_bytes(original + b' ')
            with self.subTest(path=path.name), self.assertRaises(RuntimeError):
                self.collect()
            path.write_bytes(original)
        self.client._request_formal_audio_json.assert_not_called()

    def test_additional_known_same_pcm_attempt_blocks_before_post(self):
        (self.native / 'jobs/asr/other.json').write_bytes(raw_json({
            'requestId': 'known-other-attempt', 'ttsRequestId': self.target['action']['audioId'],
            'state': 'ambiguous', 'audioSha256': self.target['ttsReceipt']['audioSha256']}))
        with self.assertRaises(RuntimeError):
            self.collect()
        self.client._request_formal_audio_json.assert_not_called()

    def test_failed_recovery_never_reserves_a_third_recheck(self):
        key = (self.target['sceneId'], self.target['action']['id'])
        with self.assertRaises(RuntimeError):
            self.collect(recheck_keys=[key])
        self.client._request_formal_audio_json.assert_not_called()
        audit = self.collect()
        completed_library = {'schemaVersion': LIBRARY_SCHEMA_V2,
            'origins': deepcopy(audit['origins']), 'probeProtocol': None}
        with self.assertRaises(RuntimeError):
            self.collect(library=completed_library, failed_recoveries=[], recheck_keys=[key])
        with self.assertRaises(RuntimeError):
            self.ledger.dispatch(origin=self.recovery_origin(audit), source=self.target,
                plan=self.f.plan, classroom_id=self.f.cid, client=self.client)
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)

    def test_literal_recovery_survives_v4_publication_and_portable_release(self):
        audit = self.collect()
        validate_audit(audit, plan=self.f.plan, classroom=self.f.classroom,
            expected_source_sha256=digest(self.f.classroom))
        self.original.audit = audit
        self.original.review = self.original.make_review()
        release = self.fx.read(self.original.prepare())
        self.assertEqual(release['audioAudit']['literalAudit'], audit)
        origins = release['audioAudit']['literalAudit']['origins']
        recovered = next(item for item in origins if item['schemaVersion'] == FAILED_RECOVERY_ORIGIN_SCHEMA)
        self.assertEqual(recovered['failureRecovery'], self.pending['failureRecovery'])
        self.assertFalse(release['audioAudit']['pronunciationReview']['humanListeningVerified'])
        self.f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        self.f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_low_success_remains_failed_and_cannot_use_v4_or_missing_v5_decision(self):
        self.client = self.original.fake_client(self.target, '完全不同的词语。')
        audit = self.collect()
        self.assertFalse(audit['passed'])
        self.original.audit = audit
        with self.assertRaises(ApiError):
            self.original.make_review()
        with self.assertRaises(ApiError):
            build_operator_review_v5(plan=self.f.plan, classroom=self.f.classroom, audit=audit,
                authorization=self.fx.auth, browser_qa=self.fx.browser, reviewer='Synthetic fixture only',
                reviewed_at=self.fx.now, expected_source_sha256=digest(self.f.classroom),
                now_ms=self.fx.now, explicit_acceptance=None)
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)

    def test_pending_or_downgraded_recovery_never_becomes_publishable_old_origin(self):
        with self.assertRaises(ApiError):
            build_audit(plan=self.f.plan, classroom=self.f.classroom,
                targets=[{'target': self.target, 'originSha256': digest(self.pending)}],
                origins=[self.pending])
        origin = deepcopy(self.pending)
        origin['schemaVersion'] = ORIGIN_SCHEMA
        with self.assertRaises(ApiError):
            verify_origin(origin)
        origin = deepcopy(self.pending)
        del origin['failureRecovery']
        with self.assertRaises(ApiError):
            verify_origin(origin)
        old = deepcopy(self.original.origins[0])
        self.assertNotIn('failureRecovery', verify_origin(old))
        self.assertEqual(verify_origin(old)['attempts'][0]['requestId'],
                         old['attempts'][0]['request']['requestId'])
        self.original.validate()

    def test_selected_failed_target_after_duplicate_pcm_keeps_original_request_identity(self):
        duplicate_action = deepcopy(self.target['action'])
        duplicate_action['id'] = 'duplicate-before-selected'
        scene = next(scene for scene in self.f.classroom['scenes'] if scene['id'] == self.target['sceneId'])
        previous_audio = self.fx.audio
        self.fx.audio = base64.b64decode(self.target['audioBase64'])
        try:
            duplicate_receipt = self.fx.audio_receipt(scene, duplicate_action, self.f.plan)
        finally:
            self.fx.audio = previous_audio
        duplicate = {**deepcopy(self.target), 'action': duplicate_action, 'ttsReceipt': duplicate_receipt}
        scene['actions'].insert(0, duplicate_action)
        self.selection['sourceSha256'] = digest(self.f.classroom)
        self.pending = self.build_pending()
        self.assertNotEqual(duplicate_action['audioId'], self.target['action']['audioId'])
        self.assertEqual(target_evidence(duplicate, self.f.plan)['pcmKey'],
                         target_evidence(self.target, self.f.plan)['pcmKey'])
        audit = self.collect(targets=[duplicate, *self.original.targets])
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)
        dispatched = self.client._request_formal_audio_json.call_args.args[2]
        self.assertEqual(dispatched['actionId'], self.target['action']['id'])
        self.assertEqual(dispatched['ttsRequestId'], self.target['action']['audioId'])
        self.assertEqual(dispatched['requestId'], self.pending['failureRecovery']['recoveryRequestId'])
        self.assertEqual(audit['segments'][0]['originSha256'], audit['segments'][-1]['originSha256'])
        self.assertEqual(self.recovery_origin(audit)['source'], self.target)

    def test_cli_selection_reads_exact_source_snapshot_and_immutable_originals(self):
        from scripts.audit_textbook_audio_origins import prepare_failed_recoveries
        arguments = dict(selection=[self.selection], plan=self.f.plan, classroom=self.f.classroom,
            targets=self.original.targets, native_audio_directory=self.native,
            routine_cache_directory=self.routine_cache)
        self.assertEqual(prepare_failed_recoveries(**arguments), [self.pending])
        changed = deepcopy(self.f.classroom)
        changed['scenes'][0]['title'] = 'Changed source after selection'
        with self.assertRaises(ApiError):
            prepare_failed_recoveries(**{**arguments, 'classroom': changed})
        for bad_selection in ([], [self.selection, self.selection],
                              [{**self.selection, 'actionId': 'foreign'}]):
            with self.subTest(selection=bad_selection), self.assertRaises(RuntimeError):
                prepare_failed_recoveries(**{**arguments, 'selection': bad_selection})
        self.client._request_formal_audio_json.assert_not_called()

    def test_recovery_only_preflights_all_selections_and_never_claims_a_full_audit(self):
        # Unrelated historical routines do not turn this selected recovery into
        # a full-course collection or a request to recognize any other audio.
        self.assertEqual(recover_failed_origins(plan=self.f.plan, classroom=self.f.classroom,
            origins=[self.pending], ledger=self.ledger), [self.pending])
        self.client._request_formal_audio_json.assert_not_called()
        with self.assertRaises(RuntimeError):
            recover_failed_origins(plan=self.f.plan, classroom=self.f.classroom,
                origins=[self.pending, self.pending], ledger=self.ledger, client=self.client)
        self.client._request_formal_audio_json.assert_not_called()
        args = dict(plan=self.f.plan, classroom=self.f.classroom,
            origins=[self.pending], ledger=self.ledger, client=self.client)
        completed = recover_failed_origins(**args)
        self.assertEqual(completed, recover_failed_origins(**{**args, 'ledger': self.new_ledger()}))
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)
        self.assertEqual(len(completed), 1)
        self.assertEqual(len(verify_origin(completed[0])['attempts']), 1)
        self.assertFalse(list(self.ledger.root.rglob('audit.json')))

    def test_successful_durable_recovery_uses_archived_transcript_without_post(self):
        rid = self.pending['failureRecovery']['recoveryRequestId']
        response = deepcopy(self.original.origins[1]['attempts'][0]['response'])
        response.update(requestId=rid, transcript=self.target['action']['text'],
                        transcriptSha256=sha(self.target['action']['text'].encode()))
        (self.native / 'jobs/asr' / (sha(rid.encode()) + '.json')).write_bytes(raw_json({
            'requestId': rid, 'ttsRequestId': self.target['action']['audioId'], 'state': 'succeeded',
            'audioSha256': self.target['ttsReceipt']['audioSha256'],
            'transcriptSha256': response['transcriptSha256']}))
        transcript_dir = self.native / 'transcripts'; transcript_dir.mkdir()
        (transcript_dir / (sha(rid.encode()) + '.json')).write_bytes(raw_json({
            'requestId': rid, 'audioSha256': self.target['ttsReceipt']['audioSha256'],
            'transcript': response['transcript'], 'transcriptSha256': response['transcriptSha256']}))
        self.client.get_formal_audio_asr.side_effect = None
        self.client.get_formal_audio_asr.return_value = {
            **response, 'transcript': None, 'completionUsable': False}
        result = recover_failed_origins(plan=self.f.plan, classroom=self.f.classroom,
            origins=[self.pending], ledger=self.ledger, client=self.client)
        self.assertEqual(result[0]['attempts'][0]['response'], response)
        self.client._request_formal_audio_json.assert_not_called()
        self.assertEqual((self.job_path.read_bytes(), self.cache_path.read_bytes()),
                         (self.job_raw, self.cache_raw))

    def test_portable_original_json_rejects_duplicate_fields_and_nonfinite_numbers(self):
        duplicate = self.job_raw.rstrip()[:-1] + b',"state":"failed"}'
        with self.assertRaises(ApiError):
            self.build_pending(failed_job_raw=duplicate,
                selection={**self.selection, 'failedJobSha256': sha(duplicate)})
        invalid = self.cache_raw.replace(b'"durationMs": ', b'"durationMs": NaN, "discard": ')
        with self.assertRaises(ApiError):
            self.build_pending(failed_cache_raw=invalid,
                selection={**self.selection, 'failedCacheSha256': sha(invalid)})

    def test_cli_recovery_only_prepare_and_repeat_run_keep_full_source_and_one_post(self):
        from scripts import audit_textbook_audio_origins as cli
        audio = self.f.root / self.f.cid
        (audio / 'textbook-preview-audio/receipts.json').write_bytes(raw_json(self.fx.receipts))
        source = self.directory / 'full-classroom.json'; source.write_bytes(raw_json(self.f.classroom))
        library = self.directory / 'empty-library.json'
        library.write_bytes(raw_json({'schemaVersion': LIBRARY_SCHEMA_V2, 'origins': [], 'probeProtocol': None}))
        selection = self.directory / 'failed-selection.json'; selection.write_bytes(raw_json([self.selection]))
        output = self.directory / 'selected-recovery'
        arguments = ['--classroom', str(source), '--audio-directory', str(audio),
            '--source-sha256', digest(self.f.classroom), '--origin-library', str(library),
            '--native-audio-directory', str(self.native), '--probe-history-root', str(self.probes),
            '--routine-cache-directory', str(self.routine_cache),
            '--failed-recovery-selection', str(selection), '--recover-failures-only', '--output', str(output)]
        before = (source.read_bytes(), self.job_path.read_bytes(), self.cache_path.read_bytes())
        config = SimpleNamespace(OPENMAIC_FULL_RUNTIME_INTERNAL_URL='http://127.0.0.1:3100', INTERNAL_API_TOKEN='synthetic')
        with patch.object(cli.AppConfig, 'from_env', return_value=config), \
                patch.object(cli, 'OpenMaicFullRuntimeClient', return_value=self.client), redirect_stdout(io.StringIO()):
            with patch('sys.argv', ['audit_textbook_audio_origins.py', 'prepare', *arguments]):
                cli.main()
            self.client._request_formal_audio_json.assert_not_called()
            for _ in range(2):
                with patch('sys.argv', ['audit_textbook_audio_origins.py', 'run', *arguments]):
                    cli.main()
        self.assertEqual(self.client._request_formal_audio_json.call_count, 1)
        self.assertFalse((output / 'audit.json').exists())
        recovered = json.loads((output / 'recovered-origins.json').read_text())
        self.assertEqual(recovered['schemaVersion'], LIBRARY_SCHEMA_V2)
        self.assertEqual(len(recovered['origins']), 1)
        self.assertEqual(recovered['origins'][0]['failureRecovery'], self.pending['failureRecovery'])
        self.assertEqual(before, (source.read_bytes(), self.job_path.read_bytes(), self.cache_path.read_bytes()))


if __name__ == '__main__':
    unittest.main()
