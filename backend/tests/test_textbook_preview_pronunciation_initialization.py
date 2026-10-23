"""Initial pinyin profiles use isolated DB/media and mocked runtime only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import new_audio_plan
from core.errors import ApiError
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_audio import core_content, narrate_preview
from services.textbook_preview_visual_revision import sha_bytes
from scripts import initialize_textbook_preview_pronunciation as cli
from tests import test_textbook_preview_audio_v2 as audio_fixtures
from tests.test_textbook_pinyin_pronunciation import bind_audio_fixture, wav_fixture, wav_receipt


class PronunciationInitializationTests(unittest.TestCase):
    node_id = 'u2-l2'
    probe_targets = {'i-base': 'i', 'u-base': 'u', 'umlaut-base': 'ü'}
    approval_result = 'three_base_probes_pronunciation_approved'
    approval_statement = '三个基础音准确'
    first_speech = None
    probe_token_sequences = {}
    probe_source_texts = {}

    def setUp(self):
        helper = audio_fixtures.PreviewAudioV2Tests()
        self.addCleanup(helper.doCleanups)
        self.f = f = helper.unnarrated()
        frozen = bind_audio_fixture(f)
        frozen['nodeId'] = self.node_id
        f.db.execute('UPDATE learning_textbook_course_previews SET node_id=?,input_json=? WHERE preview_key=?',
                     (self.node_id, canonical(frozen), f.key))
        if self.first_speech:
            f.classroom['scenes'][0]['actions'][0]['text'] = self.first_speech
            f.save(f.classroom)
            f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                         (canonical(f.classroom), digest(f.classroom), f.key))
        f.db.raw.commit()
        # The generic fixture comes from a prior synthetic narrated lesson.
        # Remove those fixture artifacts to model a genuinely fresh adoption.
        for path in f.folder.iterdir():
            path.unlink()
        for path in (f.root / f.cid / 'audio').iterdir():
            path.unlink()
        self.row = f.service.get(f.key)
        self.policy = pronunciation.select_policy(frozen)
        self.probes = f.root / 'probe-evidence'
        self.probes.mkdir()
        audio = wav_fixture()
        self.plan = {'schemaVersion': 'mira.operator.phonetic-ssml-probe.v1',
            'provider': self.policy['providerId'], 'model': self.policy['modelId'], 'voice': self.policy['voiceId'],
            'formalUseAllowed': False, 'plannedCalls': len(self.probe_targets),
            'sourceLesson': {'editionId': frozen['editionId'], 'nodeId': frozen['nodeId']}, 'samples': []}
        for label, target in self.probe_targets.items():
            entry = self.policy['symbols'][target]
            entries = [self.policy['symbols'][token]
                       for token in self.probe_token_sequences.get(label, (target, target))]
            source_text = self.probe_source_texts.get(label)
            ssml = (pronunciation.pinyin_ssml(source_text, policy_version=self.policy['policyVersion'])
                    if source_text is not None else '<speak>听音。' + ''.join(
                        f'<phoneme alphabet="py" ph="{item["ph"]}">{item["carrier"]}</phoneme>'
                        for item in entries) + '</speak>')
            request = {'model': self.policy['modelId'], 'input': {**self.policy['inputParameters'], 'text': ssml}}
            folder = self.probes / label
            folder.mkdir()
            raw = canonical(request).encode()
            (folder / 'request.json').write_bytes(raw)
            sample = {'label': label, 'target': target, 'phonemeCandidate': entry['ph'],
                'carrier': entry['carrier'], 'body': request, 'requestSha256': sha_bytes(raw),
                'ssmlSha256': sha_bytes(ssml.encode())}
            if source_text is not None:
                sample.update(sourceText=source_text,
                              tokens=list(self.probe_token_sequences[label]))
            self.plan['samples'].append(sample)
        raw_plan = canonical(self.plan).encode()
        (self.probes / 'plan.json').write_bytes(raw_plan)
        self.approval = {'schemaVersion': initialization.APPROVAL_SCHEMA, 'previewKey': f.key,
            'sourceSha256': self.row['classroom_sha256'], 'pronunciationPolicyVersion': self.policy['policyVersion'],
            'pronunciationPolicySha256': digest(self.policy), 'reviewer': 'human',
            'receivedAt': '2026-10-16T21:00:00+08:00', 'statements': [self.approval_statement],
            'result': self.approval_result, 'formalUseAllowed': False,
            'probePlanSha256': sha_bytes(raw_plan), 'samples': []}
        for original in self.plan['samples']:
            label = original['label']
            folder = self.probes / label
            response = {'request_id': 'synthetic-' + label, 'output': {'finish_reason': 'stop'}, 'usage': {'characters': 10}}
            response_raw = canonical(response).encode()
            norm = wav_receipt(audio)
            receipt = {**norm, 'status': 'succeeded', 'formalUseAllowed': False,
                'humanReview': 'pending', 'pronunciationApproved': False, 'postAttempts': 1,
                'provider': self.policy['providerId'], 'model': self.policy['modelId'], 'voice': self.policy['voiceId'],
                'target': original['target'], 'phonemeCandidate': original['phonemeCandidate'],
                'requestSha256': original['requestSha256'], 'providerResponseSha256': sha_bytes(response_raw),
                'providerRequestId': response['request_id'], 'planSha256': sha_bytes(raw_plan),
                'playbackSha256': sha_bytes(audio), 'usage': response['usage']}
            sample = {k: receipt[k] for k in ('target', 'phonemeCandidate', 'providerRequestId', 'requestSha256',
                'providerResponseSha256', 'providerAudioSha256', 'playbackSha256', 'pcmSha256')}
            self.approval['samples'].append({**sample, 'label': label, 'result': 'approved_by_human_listening'})
            (folder / 'provider-response.json').write_bytes(response_raw)
            (folder / 'receipt.json').write_text(canonical(receipt))
            (folder / 'intent.json').write_text(canonical({'requestSha256': original['requestSha256'],
                'planSha256': sha_bytes(raw_plan), 'formalUseAllowed': False}))
            (folder / 'audio.wav').write_bytes(audio)
            (folder / 'playback.wav').write_bytes(audio)
            (folder / 'playback-validation.json').write_text(canonical({
                'schemaVersion': 'mira.operator.probe-wav-validation.v1', 'pcmUnchanged': True,
                'audioNormalization': norm['audioNormalization'], **{k: norm[k] for k in
                    ('providerAudioSha256', 'pcmSha256')}, 'playbackSha256': sha_bytes(audio)}))
        self.patch = {'schemaVersion': initialization.SCHEMA, 'expectedSourceSha256': self.row['classroom_sha256'],
            'expectedCoreSha256': digest(core_content(f.classroom)),
            'pronunciationPolicyVersion': self.policy['policyVersion'], 'pronunciationPolicySha256': digest(self.policy),
            'reviewer': 'operator', 'basis': self.approval_statement + '；正式片段待另行听验',
            'approvedProbeEvidence': {'path': str(self.probes / 'human-approval.json'), 'sha256': ''}}
        self.write_approval()
        f.runtime.reset_mock()

    def write_approval(self):
        path = self.probes / 'human-approval.json'
        path.write_text(canonical(self.approval))
        self.patch['approvedProbeEvidence']['sha256'] = sha_bytes(path.read_bytes())

    def run_initialization(self, execute=True):
        return initialization.initialize_preview_pronunciation(self.f.service, self.f.key, self.f.root,
                                                               self.patch, execute=execute)

    def archive(self):
        return self.f.folder / 'pronunciation-initializations' / digest({'previewKey': self.f.key, 'patch': self.patch})

    def assert_no_external_write(self):
        for name in ('start_formal_audio_tts', 'start_formal_audio_asr', 'download_formal_audio_tts',
                     'start_generation', 'save_preview_classroom'):
            getattr(self.f.runtime, name).assert_not_called()

    def test_prepare_then_activate_without_db_classroom_or_probe_changes(self):
        source = (self.f.root / (self.f.cid + '.json')).read_bytes()
        receipts = {(self.probes / label / 'receipt.json'): (self.probes / label / 'receipt.json').read_bytes()
                    for label in self.probe_targets}
        result = self.run_initialization(False)
        self.assertTrue(result['prepared'])
        self.assertFalse((self.f.folder / 'plan.json').exists())
        result = self.run_initialization()
        plan = json.loads((self.f.folder / 'plan.json').read_text())
        self.assertEqual(plan['schemaVersion'], pronunciation.PLAN_SCHEMA)
        self.assertEqual(plan['pronunciationPolicy'], self.policy)
        self.assertEqual(plan['parentPlanSha256'], digest(json.loads((self.archive() / 'base-plan.json').read_text())))
        self.assertEqual(plan['teacher']['voiceId'], 'longanwen_v3')
        expected_files = {'row.json', 'source.json', 'frozen.json', 'base-plan.json', 'plan.json',
                          'evidence/human-approval.json', 'evidence/plan.json'} | {
            f'evidence/{label}/{name}' for label in self.probe_targets for name in
            ('request.json', 'intent.json', 'receipt.json', 'provider-response.json',
             'audio.wav', 'playback.wav', 'playback-validation.json')}
        self.assertEqual(set(json.loads((self.archive() / 'intent.json').read_text())['files']), expected_files)
        self.assertFalse(result['publicationAllowed'])
        self.assertFalse(result['generationDispatched'])
        self.assertTrue(result['requiresFormalHumanListening'])
        self.assertEqual(self.f.service.get(self.f.key), self.row)
        self.assertEqual((self.f.root / (self.f.cid + '.json')).read_bytes(), source)
        self.assertFalse((self.f.folder / 'receipts.json').exists())
        self.assertFalse((self.f.folder / 'checkpoint.json').exists())
        self.assertEqual(self.run_initialization(), result)
        for path, raw in receipts.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assert_no_external_write()

    def test_default_and_injected_v2_narration_stop_before_any_tts_get_or_post(self):
        f = self.f
        for plan in (None, new_audio_plan(preview_key=f.key, classroom_sha256=self.row['classroom_sha256'],
                core_sha256=self.patch['expectedCoreSha256'], frozen_input=json.loads(self.row['input_json']))):
            if plan:
                (f.folder / 'plan.json').write_text(canonical(plan))
            with self.assertRaises(ApiError) as exc:
                narrate_preview(f.service, f.key, f.root)
            self.assertEqual(exc.exception.code, 'textbook_preview_pronunciation_initialization_required')
        f.runtime.get_formal_audio_tts.assert_not_called()
        self.assert_no_external_write()

    def test_stale_source_core_policy_and_extra_fields_fail_closed(self):
        original = deepcopy(self.patch)
        for key in ('expectedSourceSha256', 'expectedCoreSha256', 'pronunciationPolicyVersion', 'pronunciationPolicySha256'):
            with self.subTest(field=key):
                self.patch = {**deepcopy(original), key: 'f' * 64}
                with self.assertRaises(ApiError): self.run_initialization()
        self.patch = {**original, 'voiceId': 'caller-selected'}
        with self.assertRaises(ApiError): self.run_initialization()
        self.assert_no_external_write()

    def test_missing_duplicate_or_cross_policy_probe_does_not_count_as_approval(self):
        original = deepcopy(self.approval)
        variants = [original['samples'][:-1], original['samples'][:-1] + [original['samples'][0]],
                    [{**original['samples'][0], 'phonemeCandidate': 'a1'}, *original['samples'][1:]]]
        for samples in variants:
            self.approval = {**deepcopy(original), 'samples': samples}
            self.write_approval()
            with self.assertRaises(ApiError): self.run_initialization()
        self.assert_no_external_write()

    def test_wrong_formal_claim_or_cross_preview_approval_rejected(self):
        original = deepcopy(self.approval)
        for field, value in (('formalUseAllowed', True), ('previewKey', '0' * 64), ('sourceSha256', '0' * 64)):
            self.approval = {**deepcopy(original), field: value}
            self.write_approval()
            with self.assertRaises(ApiError): self.run_initialization()

    def test_vowel_and_consonant_call_name_approval_results_are_not_interchangeable(self):
        wrong_result = ('four_base_call_name_probes_pronunciation_approved'
                        if self.node_id == 'u2-l2' else 'three_base_probes_pronunciation_approved')
        self.approval['result'] = wrong_result
        self.write_approval()
        with self.assertRaises(ApiError): self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()

    def test_registered_policy_without_initialization_evidence_contract_fails_before_reading_evidence(self):
        # AOE is registered, but uses its historical revision lifecycle. A
        # caller cannot invent probe approval for it through this initializer.
        aoe = pronunciation.registered_policy(pronunciation.AOE_POLICY_VERSION)
        self.patch.update(pronunciationPolicyVersion=aoe['policyVersion'], pronunciationPolicySha256=digest(aoe))
        self.patch['approvedProbeEvidence']['path'] = str(self.probes / 'must-not-be-read.json')
        with self.assertRaises(ApiError): self.run_initialization()
        self.f.runtime.get_classroom.assert_not_called()
        self.assert_no_external_write()

    def test_probe_byte_tamper_rejected_even_when_playback_is_valid(self):
        path = self.probes / next(iter(self.probe_targets)) / 'audio.wav'
        path.write_bytes(path.read_bytes() + b'changed')
        with self.assertRaises(ApiError): self.run_initialization()
        self.assert_no_external_write()

    def test_existing_success_failed_and_unknown_receipts_are_not_erased(self):
        f = self.f
        for status in ('succeeded', 'failed', 'unknown'):
            result = {'audioReceipts': [{'requestId': 'previous', 'status': status}]}
            f.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                         (canonical(result), f.key))
            f.db.raw.commit()
            with self.assertRaises(ApiError): self.run_initialization()
            self.assertEqual(json.loads(f.service.get(f.key)['result_json']), result)
        self.assert_no_external_write()

    def test_local_claim_wav_or_existing_plan_block_initialization(self):
        for path in (self.f.folder / 'receipts.json', self.f.folder / 'plan.json',
                     self.f.root / self.f.cid / 'audio/claimed.wav'):
            with self.subTest(path=path.name):
                path.write_text('[]')
                with self.assertRaises(ApiError): self.run_initialization()
                self.assertEqual(path.read_text(), '[]')
                path.unlink()

    def test_prepared_archive_or_row_changes_prevent_activation(self):
        self.run_initialization(False)
        path = self.archive() / 'evidence' / next(iter(self.probe_targets)) / 'receipt.json'
        original = path.read_bytes()
        path.write_text('{}')
        with self.assertRaises(ApiError): self.run_initialization()
        path.write_bytes(original)
        f = self.f
        f.db.execute('UPDATE learning_textbook_course_previews SET updated_at=? WHERE preview_key=?',
                     (self.row['updated_at'] + 1, f.key))
        f.db.raw.commit()
        with self.assertRaises(ApiError): self.run_initialization()
        self.assertFalse((f.folder / 'plan.json').exists())

    def test_resigned_archive_with_extra_probe_is_rejected(self):
        self.run_initialization(False)
        path = self.archive() / 'intent.json'
        intent = json.loads(path.read_text())
        intent['files']['evidence/unregistered-base/request.json'] = '0' * 64
        intent['sha256'] = digest({k: v for k, v in intent.items() if k != 'sha256'})
        path.write_text(canonical(intent))
        with self.assertRaises(ApiError): self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()

    def test_recovery_evidence_cannot_select_a_policy_different_from_patch(self):
        self.run_initialization(False)
        intent = json.loads((self.archive() / 'intent.json').read_text())
        files = {name: (self.archive() / name).read_bytes() for name in intent['files']}
        # Re-evaluation of a frozen archive must bind the patch as well as the
        # approval. Initial prepare's policy check is not a recovery shortcut.
        for field in ('pronunciationPolicyVersion', 'pronunciationPolicySha256'):
            wrong_patch = {**self.patch, field: 'f' * 64}
            with self.subTest(field=field), self.assertRaises(ApiError):
                initialization._verify_evidence(files, wrong_patch, self.f.key,
                    json.loads(self.row['input_json']), self.policy)
        self.assert_no_external_write()

    def test_atomic_activation_response_loss_recovers_without_other_writes(self):
        real = initialization.immutable
        active = self.f.folder / 'plan.json'
        def lost(path, raw):
            real(path, raw)
            if path.resolve() == active.resolve():
                raise OSError('lost after atomic plan installation')
        with patch.object(initialization, 'immutable', side_effect=lost), self.assertRaises(OSError):
            self.run_initialization()
        before = active.read_bytes()
        result = self.run_initialization()
        self.assertEqual(active.read_bytes(), before)
        self.assertEqual(self.run_initialization(), result)
        self.assertEqual(self.f.service.get(self.f.key), self.row)
        self.assert_no_external_write()

    def test_interruption_before_plan_rename_recovers_only_exact_own_staging(self):
        self.run_initialization(False)
        staging = self.f.folder / 'plan.json.tmp'
        raw = (self.archive() / 'plan.json').read_bytes()
        staging.write_bytes(raw[:20])
        with self.assertRaises(ApiError): self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        staging.write_bytes(raw)
        self.run_initialization()
        self.assertEqual((self.f.folder / 'plan.json').read_bytes(), raw)
        self.assertFalse(staging.exists())
        self.assert_no_external_write()

    def test_rerun_never_resets_later_formal_checkpoint_or_receipts(self):
        result = self.run_initialization()
        # Existing downstream work is opaque to initialization; this action
        # neither certifies it nor changes it, including unresolved claims.
        f = self.f
        raw_receipts = canonical([{'requestId': 'later-formal-claim', 'status': 'unknown'}]).encode()
        (f.folder / 'receipts.json').write_bytes(raw_receipts)
        (f.folder / 'checkpoint.json').write_text(canonical(f.classroom))
        f.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                     (canonical({'audioReceipts': json.loads(raw_receipts), 'audioPartial': True}), f.key))
        f.db.raw.commit()
        self.assertEqual(self.run_initialization(), result)
        self.assertEqual((f.folder / 'receipts.json').read_bytes(), raw_receipts)
        self.assert_no_external_write()

    def test_real_narrator_sample_then_full_reuses_success_and_initialization_is_idempotent(self):
        result = self.run_initialization()
        f, audio = self.f, wav_fixture()
        version = self.policy['policyVersion']
        def speak(**kw):
            value = {'requestId': kw['request_id'], 'status': 'succeeded', 'mimeType': 'audio/wav',
                **wav_receipt(audio), **{k: self.policy[k] for k in ('providerId', 'modelId', 'voiceId')},
                'providerPronunciation': pronunciation.provider_pronunciation(kw['text'], policy_version=version),
                'providerRequestId': 'synthetic-' + kw['action_id'], 'providerUsage': {'characters': 1},
                'budgetMeasurement': {'kind': 'ssml-codepoint-upper-bound', 'estimated': True,
                    'characters': len(pronunciation.pinyin_ssml(kw['text'], policy_version=version))}}
            f.provider_receipts[kw['request_id']] = deepcopy(value)
            return value
        f.runtime.start_formal_audio_tts.side_effect = speak
        f.runtime.download_formal_audio_tts.return_value = audio
        selection = {'schemaVersion': 'mira.textbook.speech-selection.v1', 'previewKey': f.key,
            'coreSha256': self.patch['expectedCoreSha256'], 'speeches': [{'sceneId': 'scene-0', 'actionId': 'action-0'}]}
        narrate_preview(f.service, f.key, f.root, speech_selection=selection)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 1)
        first = (f.folder / 'receipts.json').read_bytes()
        self.assertEqual(self.run_initialization(), result)
        self.assertEqual((f.folder / 'receipts.json').read_bytes(), first)
        narrate_preview(f.service, f.key, f.root)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)
        receipts = (f.folder / 'receipts.json').read_bytes()
        checkpoint = (f.folder / 'checkpoint.json').read_bytes()
        self.assertEqual(self.run_initialization(), result)
        self.assertEqual((f.folder / 'receipts.json').read_bytes(), receipts)
        self.assertEqual((f.folder / 'checkpoint.json').read_bytes(), checkpoint)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 8)

    def test_same_plan_with_edited_content_is_rejected(self):
        self.run_initialization()
        f = self.f
        f.classroom['scenes'][0]['actions'][0]['text'] += '真实内容编辑。'
        f.save(f.classroom)
        f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                     (canonical(f.classroom), digest(f.classroom), f.key))
        f.db.raw.commit()
        with self.assertRaises(ApiError): self.run_initialization()

    def test_published_preview_and_cross_lesson_are_rejected(self):
        real = self.f.db.execute
        def published(sql, params=()):
            if "status='published'" in sql:
                return SimpleNamespace(fetchall=lambda: [{'input_json': canonical({'previewKey': self.f.key})}])
            return real(sql, params)
        with patch.object(self.f.db, 'execute', side_effect=published), self.assertRaises(ApiError):
            self.run_initialization()
        with patch.object(pronunciation, 'initialization_required', return_value=False), self.assertRaises(ApiError):
            self.run_initialization()
        self.assert_no_external_write()

    def test_cli_prepare_has_no_provider_or_database_writes(self):
        path = self.f.root / 'initialization-patch.json'
        path.write_text(canonical(self.patch))
        args = ['initialize_textbook_preview_pronunciation.py', 'prepare', '--key', self.f.key,
                '--classroom-directory', str(self.f.root), '--patch', str(path)]
        with patch.object(cli.AppConfig, 'from_env'), patch.object(cli, 'Database', return_value=self.f.db), \
             patch.object(cli, 'OpenMaicFullRuntimeClient', return_value=self.f.runtime), \
             patch('sys.argv', args), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(), 0)
        self.assertTrue(json.loads(output.getvalue())['prepared'])
        self.assertEqual(self.f.service.get(self.f.key), self.row)
        self.assert_no_external_write()


class BpmfPronunciationInitializationTests(PronunciationInitializationTests):
    """The same lifecycle must preserve all four call-name probes, not three."""
    node_id = 'u2-l3'
    probe_targets = {'b-base': 'b', 'p-base': 'p', 'm-base': 'm', 'f-base': 'f'}
    approval_result = 'four_base_call_name_probes_pronunciation_approved'
    approval_statement = '四个声母呼读音准确；不代表轻短本音或完整音节已听验'
    first_speech = '请听老师示范：b。'


if __name__ == '__main__':
    unittest.main()
