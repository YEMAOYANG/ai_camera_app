"""Publication/read integration with synthetic WAVs, mock DB and no providers."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_pronunciation import provider_pronunciation, sha_text
from content.textbook_preview_audio_contract import asr_request_id, compare_transcript, tts_request_id
from content.textbook_release import validate_release
from core.errors import ApiError
from tests import test_textbook_pinyin_asr_reconciliation as reconciliation_fixtures
from tests import test_textbook_pinyin_pronunciation as publication_fixtures


class PinyinReconciliationPublicationTests(unittest.TestCase):
    def setUp(self):
        self.f = publication_fixtures.PinyinPublicationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        # Preserve actual comparison/ASR contract fields, with a real low
        # literal score. A pronunciation approval alone cannot accept it.
        entry = self.f.audit['segments'][0]
        transcript = '鹅，轻跟劳实读。'
        entry['transcript'] = transcript
        entry['asr'].update(transcript=transcript, transcriptSha256=sha_text(transcript))
        entry['comparison'] = compare_transcript(self.f.plan, entry['text'], transcript)
        entry['similarityBps'] = entry['comparison']['similarityBps']
        self.assertLess(entry['similarityBps'], 8500)
        self.assertFalse(entry['comparison']['passed'])
        self.f.audit['passed'] = False
        for heard in self.f.listening['segments']:
            heard['reviewedAt'] = 1000
        publication_fixtures.sign(self.f.listening)
        publication_fixtures.sign(self.f.audit)
        self.builder = reconciliation_fixtures.PinyinAsrReconciliationTests()
        self.reconciliation = self.builder.make_manifest({
            'plan': self.f.plan, 'classroom': self.f.classroom, 'audit': self.f.audit,
            'listening_review': self.f.listening,
            'expected_source_sha256': self.f.row['classroom_sha256'], 'now_ms': 4000,
        })

    def prepare(self, manifest=...):
        f = self.f
        return f.service.prepare(key=f.key, edition=f.manifest['editionId'], revision=f.manifest['revisionId'],
            node='u2-l1', teaching_revision='1', review=f.review, audio_audit=f.audit,
            classroom_directory=f.root,
            asr_reconciliation=self.reconciliation if manifest is ... else manifest)

    def read(self, prepared):
        return validate_release(self.f.build(prepared), self.f.manifest)

    def reseal_release(self, prepared):
        """Keep every outer identity valid so failures exercise evidence gates."""
        frozen, release = prepared['frozen'], prepared['review']['release']
        old_id = release['classroomId']
        key = digest({k: v for k, v in frozen.items() if k != 'contentKey'})
        frozen['contentKey'] = key
        new_id = 'tbpub_' + key[:24]

        def rename(value):
            if isinstance(value, dict):
                return {k: rename(v) for k, v in value.items()}
            if isinstance(value, list):
                return [rename(v) for v in value]
            if isinstance(value, str):
                return new_id if value == old_id else value.replace(
                    '/api/classroom-media/' + old_id + '/',
                    '/api/classroom-media/' + new_id + '/')
            return value

        release = rename(release)
        release.update(contentKey=key, classroomId=new_id,
                       classroomSha256=digest(release['classroom']))
        publication_fixtures.sign(release)
        prepared['release'] = prepared['review']['release'] = release
        return prepared

    def test_explicit_reconciliation_preserves_failed_literal_audit_in_archive_and_read(self):
        f = self.f
        before = canonical({'audit': f.audit, 'manifest': self.reconciliation, 'row': f.row})
        original_wavs = {p.name: p.read_bytes() for p in (f.root / f.cid / 'audio').glob('*.wav')}
        prepared = self.prepare()
        release = self.read(prepared)
        archived = release['audioAudit']
        self.assertTrue(archived['passed'])
        self.assertFalse(archived['literalPassed'])
        self.assertEqual(archived['acceptanceMethod'], 'human-listening-reconciliation')
        self.assertEqual(canonical(archived['literalAudit']), canonical(f.audit))
        self.assertFalse(archived['literalAudit']['passed'])
        self.assertEqual(archived['reconciliation'], self.reconciliation)
        self.assertEqual(archived['minSimilarityBps'], f.audit['segments'][0]['similarityBps'])
        self.assertEqual(prepared['frozen']['audioAuditSha256'], f.audit['sha256'])
        self.assertEqual(prepared['frozen']['audioAcceptance'], {
            'method': 'human-listening-reconciliation', 'literalAuditSha256': f.audit['sha256'],
            'reconciliationSha256': self.reconciliation['sha256'],
        })
        for asset in release['media']:
            archived_bytes = (f.root / asset['path'].removeprefix('/api/classroom-media/')).read_bytes()
            self.assertIn(archived_bytes, original_wavs.values())
        self.assertEqual(original_wavs, {p.name: p.read_bytes() for p in (f.root / f.cid / 'audio').glob('*.wav')})
        self.assertEqual(canonical({'audit': f.audit, 'manifest': self.reconciliation, 'row': f.row}), before)
        f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_phonetic_approval_without_whole_sentence_manifest_cannot_prepare(self):
        with self.assertRaises(ApiError):
            self.prepare(None)
        self.assertFalse(list(self.f.root.glob('tbpub_*')))
        self.assertFalse(self.f.audit['passed'])

    def test_stale_or_tampered_reconciliation_rejected_by_prepare_and_read(self):
        prepared = self.prepare()
        for mutation in ('source', 'plan', 'audit', 'listening', 'asr_receipt',
                         'audio', 'whole_sentence_rejected', 'future_review'):
            with self.subTest(mutation=mutation):
                manifest = deepcopy(self.reconciliation)
                if mutation in ('source', 'plan', 'audit', 'listening'):
                    field = {'source': 'sourceSha256', 'plan': 'planSha256',
                             'audit': 'auditSha256', 'listening': 'listeningReviewSha256'}[mutation]
                    manifest[field] = '0' * 64
                elif mutation == 'asr_receipt':
                    manifest['segments'][0]['asrReceiptSha256'] = '0' * 64
                elif mutation == 'audio':
                    manifest['segments'][0]['audioSha256'] = '0' * 64
                elif mutation == 'whole_sentence_rejected':
                    manifest['humanReview']['segments'][0]['noSubstitutions'] = False
                    self.builder.reseal_human(manifest)
                else:
                    manifest['reviewedAt'] = 10 ** 20
                publication_fixtures.sign(manifest)
                with self.assertRaises(ApiError):
                    self.prepare(manifest)
                bad = deepcopy(prepared)
                bad['review']['release']['audioAudit']['reconciliation'] = manifest
                bad['frozen']['audioAcceptance']['reconciliationSha256'] = manifest['sha256']
                self.reseal_release(bad)
                with self.assertRaises(ApiError):
                    self.read(bad)

    def test_stripping_frozen_acceptance_or_release_evidence_still_fails_after_rehash(self):
        prepared = self.prepare()
        for field in ('audioAcceptance', 'literalAudit', 'reconciliation',
                      'literalPassed', 'acceptanceMethod'):
            with self.subTest(field=field):
                bad = deepcopy(prepared)
                if field == 'audioAcceptance':
                    bad['frozen'].pop(field)
                else:
                    bad['review']['release']['audioAudit'].pop(field)
                self.reseal_release(bad)
                with self.assertRaises(ApiError):
                    self.read(bad)

    def test_stripping_all_reconciliation_and_inflating_summary_does_not_fake_literal_pass(self):
        bad = self.prepare()
        bad['frozen'].pop('audioAcceptance')
        audit = bad['review']['release']['audioAudit']
        for field in ('literalAudit', 'reconciliation', 'literalPassed', 'acceptanceMethod'):
            audit.pop(field)
        audit['minSimilarityBps'] = 10000
        self.reseal_release(bad)
        with self.assertRaises(ApiError):
            self.read(bad)

    def test_reconciliation_does_not_accept_changed_source_wav(self):
        path = self.f.root / self.f.cid / 'audio' / (self.f.audit['segments'][0]['ttsRequestId'] + '.wav')
        changed = bytearray(path.read_bytes())
        changed[-1] ^= 1
        path.write_bytes(changed)
        with self.assertRaises(ApiError):
            self.prepare()
        self.assertFalse(list(self.f.root.glob('tbpub_*')))

    def test_release_media_source_identity_still_matches_reviewed_wav(self):
        prepared = self.prepare()
        for field in ('sha256', 'sourceSha256'):
            with self.subTest(field=field):
                bad = deepcopy(prepared)
                bad['review']['release']['media'][0][field] = '0' * 64
                self.reseal_release(bad)
                with self.assertRaises(ApiError):
                    self.read(bad)

    def test_non_pinyin_speech_url_cannot_point_to_another_reviewed_clip(self):
        f = self.f
        scene = f.classroom['scenes'][1]
        action = scene['actions'][0]
        text = '请把图卡放回原处。'
        request = tts_request_id(f.plan, scene['id'], action['id'], text)
        # A distinct, valid PCM fixture is necessary: deduplicated identical
        # bytes would make swapping the URL a harmless change.
        audio = bytearray(publication_fixtures.wav_fixture())
        audio[-1] = 1
        audio = bytes(audio)
        wav_fields = publication_fixtures.wav_receipt(audio)
        action.update(text=text, audioId=request,
                      audioUrl=f'/api/classroom-media/{f.cid}/audio/{request}.wav')
        (f.root / f.cid / 'audio' / (request + '.wav')).write_bytes(audio)
        result = json.loads(f.row['result_json'])
        result['audioReceipts'][1].update(**wav_fields, **publication_fixtures.usage_receipt(text),
            requestId=request, providerPronunciation=provider_pronunciation(text))
        entry = f.audit['segments'][1]
        entry.update(text=text, textSha256=sha_text(text), ttsRequestId=request,
            audioSha256=wav_fields['audioSha256'], transcript=text, similarityBps=10000,
            comparison=compare_transcript(f.plan, text, text))
        entry['asr'].update(requestId=asr_request_id(f.plan, request, wav_fields['audioSha256']),
            transcript=text, transcriptSha256=sha_text(text), providerPronunciation=provider_pronunciation(text))
        f.listening['segments'] = [s for s in f.listening['segments'] if s['sceneId'] != scene['id']]
        publication_fixtures.sign(f.listening)
        source_sha = digest(f.classroom)
        f.audit['sourceSha256'] = source_sha
        publication_fixtures.sign(f.audit)
        f.review['sourceSha256'] = source_sha
        f.row.update(classroom_json=canonical(f.classroom), classroom_sha256=source_sha,
                     result_json=canonical(result))
        (f.root / (f.cid + '.json')).write_text(canonical(f.classroom))
        self.reconciliation = self.builder.make_manifest({'plan': f.plan, 'classroom': f.classroom,
            'audit': f.audit, 'listening_review': f.listening,
            'expected_source_sha256': source_sha, 'now_ms': 4000})
        prepared = self.prepare()
        self.read(prepared)
        published = prepared['review']['release']['classroom']['scenes']
        plain_action = published[1]['actions'][0]
        original_id = plain_action['audioId']
        self.assertNotEqual(plain_action['audioUrl'], published[0]['actions'][0]['audioUrl'])
        plain_action['audioUrl'] = published[0]['actions'][0]['audioUrl']
        self.reseal_release(prepared)
        self.assertEqual(prepared['release']['classroom']['scenes'][1]['actions'][0]['audioId'], original_id)
        with self.assertRaises(ApiError):
            self.read(prepared)


if __name__ == '__main__':
    unittest.main()
