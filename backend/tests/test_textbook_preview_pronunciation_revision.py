"""Pronunciation rotations use isolated DB/media and fake runtime, never providers."""
from contextlib import contextmanager
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import tts_request_id
from content.textbook_pinyin_pronunciation import pinyin_ssml, provider_pronunciation
from core.errors import ApiError
from services import textbook_preview_pronunciation_revision as revision
from services.textbook_preview_audio import core_content, narrate_preview, recover_completed_audio_save
from services.textbook_preview_visual_revision import sha_bytes, persisted
from tests import test_textbook_preview_audio_v2 as audio_fixtures
from tests.test_textbook_pinyin_pronunciation import bind_audio_fixture


class PronunciationRevisionTests(unittest.TestCase):
    def setUp(self):
        helper = audio_fixtures.PreviewAudioV2Tests()
        self.addCleanup(helper.doCleanups)
        self.f = helper.unnarrated()
        f = self.f
        bind_audio_fixture(f)
        narrate_preview(f.service, f.key, f.root, speech_selection=helper.selection(f, 0, 5))
        self.row = f.service.get(f.key)
        self.source = json.loads(self.row['classroom_json'])
        self.parent_plan = json.loads((f.folder / 'plan.json').read_text())
        self.original_files = {n: (f.folder / n).read_bytes() for n in ('plan.json', 'receipts.json', 'checkpoint.json')}
        self.original_wavs = {p.name: p.read_bytes() for p in (f.root / f.cid / 'audio').glob('*.wav')}
        receipts = json.loads(self.row['result_json'])['audioReceipts']
        rejected = {'schemaVersion': 'mira.textbook.phonetic-human-feedback.v1', 'previewKey': f.key,
                    'reviewer': 'human', 'receivedAt': '2026-10-16', 'statements': ['发音错误'], 'scope': 'selected',
                    'publicationAllowed': False, 'fullNarrationOnHold': True, 'samples': []}
        for scene in self.source['scenes']:
            action = scene['actions'][0]
            if action.get('audioId'):
                r = next(r for r in receipts if r['requestId'] == action['audioId'])
                rejected['samples'].append({'sceneId': scene['id'], 'actionId': action['id'],
                    'receiptRequestId': r['requestId'], 'audioSha256': r['audioSha256'], 'findings': ['音素错误']})
        reject_path = f.root / 'human-feedback.json'
        reject_path.write_text(canonical(rejected))
        probe_root = f.root / 'probes'
        probe_root.mkdir()
        approved = {'schemaVersion': 'mira.operator.phonetic-human-feedback.v1', 'reviewer': 'human',
                    'receivedAt': '2026-10-16', 'result': 'four_ssml_probes_pronunciation_approved',
                    'model': 'cosyvoice-v3-flash', 'voice': 'longanwen_v3', 'formalUseAllowed': False, 'samples': []}
        wav = next(iter(self.original_wavs.values()))
        pcm_sha = sha_bytes(revision._pcm(wav)[1])
        for label, phoneme in revision.PROBES.items():
            folder = probe_root / label
            folder.mkdir()
            request = {'model': approved['model'], 'input': {'voice': approved['voice'], 'enable_ssml': True,
                        'text': f'<speak><phoneme alphabet="py" ph="{phoneme}">示范</phoneme></speak>'}}
            raw = canonical(request).encode()
            sample = {'label': label, 'phoneme': phoneme, 'requestSha256': sha_bytes(raw),
                      'providerRequestId': 'provider-' + label, 'providerAudioSha256': sha_bytes(wav),
                      'playbackSha256': sha_bytes(wav), 'pcmSha256': pcm_sha, 'result': 'approved_by_human_listening'}
            (folder / 'request.json').write_bytes(raw)
            (folder / 'intent.json').write_text(canonical({'requestSha256': sha_bytes(raw), 'formalUseAllowed': False}))
            (folder / 'receipt.json').write_text(canonical({'status': 'succeeded', 'model': approved['model'],
                'voice': approved['voice'], 'phoneme': phoneme, 'requestSha256': sha_bytes(raw),
                'providerRequestId': sample['providerRequestId'], 'audioSha256': sha_bytes(wav),
                'pcmSha256': pcm_sha, 'formalUseAllowed': False}))
            (folder / 'playback-validation.json').write_text(canonical({
                'schemaVersion': 'mira.operator.audio-container-validation.v1', 'pcmChanged': False,
                'formalUseAllowed': False, **{k: sample[k] for k in ('providerAudioSha256', 'playbackSha256', 'pcmSha256')}}))
            (folder / 'audio.wav').write_bytes(wav)
            (folder / 'playback.wav').write_bytes(wav)
            approved['samples'].append(sample)
        approved_path = probe_root / 'human-feedback.json'
        approved_path.write_text(canonical(approved))
        self.patch = {'schemaVersion': revision.SCHEMA, 'expectedSourceSha256': self.row['classroom_sha256'],
                      'parentPlanSha256': digest(self.parent_plan), 'reviewer': 'operator', 'basis': '人工拒绝及小样方案认可',
                      'humanFeedback': {'path': str(reject_path), 'sha256': sha_bytes(reject_path.read_bytes())},
                      'approvedProbeEvidence': {'path': str(approved_path), 'sha256': sha_bytes(approved_path.read_bytes())}}
        f.runtime.reset_mock()

    def run_revision(self, *, execute=True, patch_value=None):
        f = self.f
        return revision.revise_preview_pronunciation(f.service, f.key, f.root, patch_value or self.patch, execute=execute)

    def archive(self):
        return self.f.folder / 'pronunciation-revisions' / digest({'previewKey': self.f.key, 'patch': self.patch})

    def assert_no_provider(self):
        for method in ('start_formal_audio_tts', 'start_formal_audio_asr', 'download_formal_audio_tts', 'start_generation'):
            getattr(self.f.runtime, method).assert_not_called()

    def test_prepare_free_then_rotate_only_audio_and_preserve_original_bytes(self):
        result = self.run_revision(execute=False)
        self.assertTrue(result['prepared'])
        self.assertEqual(result['parentAudioCount'], 2)
        self.f.runtime.save_preview_classroom.assert_not_called()
        self.assertFalse((self.f.folder / revision.PENDING).exists())
        self.assertEqual(self.f.service.get(self.f.key), self.row)
        receipt = self.run_revision()
        row = self.f.service.get(self.f.key)
        target = json.loads(row['classroom_json'])
        self.assertEqual(persisted(target), persisted(core_content(self.source)))
        self.assertEqual(row['status'], 'review_required')
        result = json.loads(row['result_json'])
        self.assertEqual(result['audioReceipts'], [])
        self.assertEqual(result['audioCompleted'], 0)
        self.assertTrue(result['audioPartial'])
        self.assertNotIn('frozenPreview', result)
        self.assertEqual(result['pronunciationRevisions'], [receipt])
        for name, raw in self.original_files.items():
            self.assertEqual((self.archive() / 'parent' / name).read_bytes(), raw)
        for name, raw in self.original_wavs.items():
            self.assertEqual((self.f.root / self.f.cid / 'audio' / name).read_bytes(), raw)
        plan = json.loads((self.f.folder / 'plan.json').read_text())
        self.assertEqual(plan['schemaVersion'], 'mira.textbook.preview-audio-plan.v3-pinyin')
        self.assertEqual(plan['teacher']['voiceId'], 'longanwen_v3')
        self.assertEqual(self.run_revision(), receipt)
        self.f.runtime.save_preview_classroom.assert_called_once()
        self.assert_no_provider()

    def test_stale_source_and_parent_plan_rejected(self):
        for field in ('expectedSourceSha256', 'parentPlanSha256'):
            p = deepcopy(self.patch)
            p[field] = 'f' * 64
            with self.assertRaises(ApiError):
                self.run_revision(patch_value=p)
        self.f.runtime.save_preview_classroom.assert_not_called()
        self.assert_no_provider()

    def test_feedback_or_probe_audio_tamper_rejected(self):
        path = self.f.root / 'probes/e-base/playback.wav'
        path.write_bytes(path.read_bytes() + b'tamper')
        with self.assertRaises(ApiError):
            self.run_revision()
        self.f.runtime.save_preview_classroom.assert_not_called()
        self.assert_no_provider()

    def test_unresolved_receipt_rejected(self):
        f = self.f
        r = json.loads(self.row['result_json'])
        r['audioReceipts'][0]['status'] = 'unknown'
        f.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?', (canonical(r), f.key))
        f.db.raw.commit()
        (f.folder / 'receipts.json').write_text(canonical(r['audioReceipts']))
        with self.assertRaises(ApiError):
            self.run_revision()
        f.runtime.save_preview_classroom.assert_not_called()
        self.assert_no_provider()

    def test_original_successful_wav_tamper_rejected_before_archive_or_save(self):
        f = self.f
        request = json.loads(self.row['result_json'])['audioReceipts'][0]['requestId']
        (f.root / f.cid / 'audio' / (request + '.wav')).write_bytes(b'changed')
        with self.assertRaises(ApiError):
            self.run_revision()
        f.runtime.save_preview_classroom.assert_not_called()
        self.assert_no_provider()

    def test_concurrent_plan_edit_after_prepare_stops_before_runtime_write(self):
        self.run_revision(execute=False)
        (self.f.folder / 'plan.json').write_text('{}')
        with self.assertRaises(ApiError):
            self.run_revision()
        self.f.runtime.save_preview_classroom.assert_not_called()

    def test_row_version_change_after_prepare_stops_before_runtime_write(self):
        self.run_revision(execute=False)
        f = self.f
        f.db.execute('UPDATE learning_textbook_course_previews SET updated_at=? WHERE preview_key=?',
                     (self.row['updated_at'] + 1, f.key))
        f.db.raw.commit()
        with self.assertRaises(ApiError):
            self.run_revision()
        f.runtime.save_preview_classroom.assert_not_called()
        self.assertFalse((f.folder / revision.PENDING).exists())
        for name, raw in self.original_files.items():
            self.assertEqual((f.folder / name).read_bytes(), raw)
        self.assert_no_provider()

    def test_content_change_with_same_version_still_stops_before_runtime_write(self):
        self.run_revision(execute=False)
        f = self.f
        changed = json.loads(self.row['result_json'])
        changed['otherReview'] = 'concurrent edit'
        f.db.execute('UPDATE learning_textbook_course_previews SET result_json=? WHERE preview_key=?',
                     (canonical(changed), f.key))
        f.db.raw.commit()
        self.assertEqual(f.service.get(f.key)['updated_at'], self.row['updated_at'])
        with self.assertRaises(ApiError):
            self.run_revision()
        f.runtime.save_preview_classroom.assert_not_called()
        self.assert_no_provider()

    def test_mysql_json_comparison_failure_recovers_with_locked_version_cas(self):
        from types import SimpleNamespace
        f, cas_count = self.f, 0
        real = f.db.execute

        def mysql_json_semantics(sql, params=()):
            nonlocal cas_count
            if sql.startswith('UPDATE learning_textbook_course_previews SET status='):
                cas_count += 1
                # MySQL JSON-column = bound string is false even when SELECT
                # returns the same text. Also inject one rejected version CAS
                # after runtime/file save, matching the interrupted real run.
                where = sql.split('WHERE', 1)[1]
                if 'result_json=?' in where or cas_count == 1:
                    return SimpleNamespace(rowcount=0)
            return real(sql, params)

        with patch.object(f.db, 'execute', side_effect=mysql_json_semantics):
            with self.assertRaises(ApiError):
                self.run_revision()
            self.assertEqual(f.service.get(f.key), self.row)
            self.assertTrue((f.folder / revision.PENDING).exists())
            intent_before = (self.archive() / 'intent.json').read_bytes()
            self.run_revision()
        self.assertEqual(cas_count, 2)
        self.assertEqual((self.archive() / 'intent.json').read_bytes(), intent_before)
        f.runtime.save_preview_classroom.assert_called_once()
        self.assertFalse((f.folder / revision.PENDING).exists())
        self.assert_no_provider()

    def test_bound_interactive_audio_is_rejected(self):
        from content.textbook_interactive_narration import bind_interactive_audio
        f = self.f
        current = deepcopy(self.source)
        scene = current['scenes'][5]
        scene['content']['html'] = bind_interactive_audio(scene['content']['html'],
            {'ask': scene['actions'][0]['audioUrl'].removeprefix(f.runtime.base_url)}, f.cid)
        f.save(current)
        f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                     (canonical(f.classroom), digest(f.classroom), f.key))
        f.db.raw.commit()
        (f.folder / 'checkpoint.json').write_text(canonical(f.classroom))
        p = deepcopy(self.patch)
        p['expectedSourceSha256'] = digest(f.classroom)
        with self.assertRaises(ApiError):
            self.run_revision(patch_value=p)
        f.runtime.save_preview_classroom.assert_not_called()

    def test_published_source_rejected(self):
        real = self.f.db.execute
        def published(sql, params=()):
            if "status='published'" in sql:
                from types import SimpleNamespace
                return SimpleNamespace(fetchall=lambda: [{'input_json': canonical({'previewKey': self.f.key})}])
            return real(sql, params)
        with patch.object(self.f.db, 'execute', side_effect=published), self.assertRaises(ApiError):
            self.run_revision()
        self.f.runtime.save_preview_classroom.assert_not_called()

    def test_save_response_loss_recovers_without_second_save(self):
        def lost(value):
            self.f.save(value)
            raise TimeoutError('response lost')
        self.f.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError):
            self.run_revision()
        self.assertTrue((self.f.folder / revision.PENDING).exists())
        self.run_revision()
        self.f.runtime.save_preview_classroom.assert_called_once()
        self.assert_no_provider()

    def test_unknown_save_stops_and_guard_blocks_narrate_and_recovery(self):
        self.f.runtime.save_preview_classroom.side_effect = TimeoutError('unknown')
        with self.assertRaises(TimeoutError):
            self.run_revision()
        with self.assertRaises(ApiError):
            self.run_revision()
        self.f.runtime.save_preview_classroom.assert_called_once()
        for operation in (lambda: narrate_preview(self.f.service, self.f.key, self.f.root),
                          lambda: recover_completed_audio_save(self.f.service, self.row, self.f.root, self.source)):
            with self.assertRaises(ApiError):
                operation()
        self.assert_no_provider()

    def test_plan_write_interruption_recovers_all_local_state(self):
        real = revision.atomic_json
        def lost(path, value):
            real(path, value)
            if path.name == 'plan.json':
                raise OSError('after plan rename')
        with patch.object(revision, 'atomic_json', side_effect=lost), self.assertRaises(OSError):
            self.run_revision()
        self.assertEqual(self.f.service.get(self.f.key)['classroom_sha256'], self.row['classroom_sha256'])
        self.run_revision()
        self.f.runtime.save_preview_classroom.assert_called_once()
        self.assertFalse((self.f.folder / revision.PENDING).exists())
        self.assert_no_provider()

    def test_commit_response_loss_recovers_lineage_without_rewriting(self):
        @contextmanager
        def lost_commit():
            yield self.f.db
            self.f.db.raw.commit()
            row = self.f.db.execute('SELECT result_json FROM learning_textbook_course_previews WHERE preview_key=?',
                                    (self.f.key,)).fetchone()
            if json.loads(row['result_json']).get('pronunciationRevisions'):
                raise TimeoutError('commit response lost')
        with patch.object(self.f.service.repository, 'transaction', side_effect=lost_commit), self.assertRaises(TimeoutError):
            self.run_revision()
        self.assertTrue((self.f.folder / revision.PENDING).exists())
        with patch.object(revision, 'atomic_json', side_effect=AssertionError('must not rewrite')):
            self.run_revision()
        self.f.runtime.save_preview_classroom.assert_called_once()
        self.assert_no_provider()

    def test_archive_tamper_stops(self):
        self.run_revision(execute=False)
        (self.archive() / 'parent/receipts.json').write_text('[]')
        with self.assertRaises(ApiError):
            self.run_revision()
        self.f.runtime.save_preview_classroom.assert_not_called()

    def test_rerun_after_new_partial_narration_never_clears_audio(self):
        receipt = self.run_revision()
        f = self.f
        plan = json.loads((f.folder / 'plan.json').read_text())
        current = deepcopy(f.classroom)
        scene, action = current['scenes'][0], current['scenes'][0]['actions'][0]
        request = tts_request_id(plan, scene['id'], action['id'], action['text'])
        wav = next(iter(self.original_wavs.values()))
        action.update(audioId=request, audioUrl=f'{f.runtime.base_url}/api/classroom-media/{f.cid}/audio/{request}.wav',
                      audioMetadata={'schemaVersion': 'mira.openmaic.speech-audio.v1',
                        'providerId': plan['teacher']['tts']['providerId'], 'modelId': plan['teacher']['tts']['modelId'],
                        'voiceId': plan['teacher']['voiceId'], 'fallbackUsed': False})
        new_receipts = [{'requestId': request, 'status': 'succeeded', 'audioSha256': sha_bytes(wav),
                         'previewAudioIdentity': {'planSha256': digest(plan), 'attempt': 1},
                         'providerId': plan['teacher']['tts']['providerId'], 'modelId': plan['teacher']['tts']['modelId'],
                         'voiceId': plan['teacher']['voiceId'], 'providerPronunciation': provider_pronunciation(action['text']),
                         'providerRequestId': 'synthetic-pronunciation-provider-request', 'providerUsage': {'characters': 1},
                         'budgetMeasurement': {'kind': 'ssml-codepoint-upper-bound',
                                               'characters': len(pinyin_ssml(action['text'])), 'estimated': True},
                         'providerAudioSha256': sha_bytes(wav), 'pcmSha256': sha_bytes(wav[44:]),
                         'audioNormalization': {'policyVersion': 'mira.wav.streaming-pcm-lengths.v1', 'applied': False,
                           'providerRiffSize': len(wav)-8, 'providerDataSize': len(wav)-44,
                           'riffSize': len(wav)-8, 'dataSize': len(wav)-44, 'pcmByteLength': len(wav)-44,
                           'sampleRate': 24000, 'channels': 1, 'bitsPerSample': 16}}]
        (f.root / f.cid / 'audio' / (request + '.wav')).write_bytes(wav)
        f.save(current)
        row = f.service.get(f.key)
        result = json.loads(row['result_json'])
        result.update(audioReceipts=new_receipts, audioCompleted=1)
        f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=?,result_json=? WHERE preview_key=?',
                     (canonical(f.classroom), digest(f.classroom), canonical(result), f.key))
        f.db.raw.commit()
        (f.folder / 'receipts.json').write_text(canonical(new_receipts))
        (f.folder / 'checkpoint.json').write_text(canonical(f.classroom))
        before = f.service.get(f.key)
        with patch.object(revision, 'atomic_json', side_effect=AssertionError('must not rewrite')):
            self.assertEqual(self.run_revision(), receipt)
        self.assertEqual(f.service.get(f.key), before)
        self.assertEqual(f.classroom['scenes'][0]['actions'][0]['audioId'], request)
        f.runtime.save_preview_classroom.assert_called_once()
        self.assert_no_provider()


if __name__ == '__main__':
    unittest.main()
