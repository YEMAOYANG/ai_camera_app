"""Synthetic evidence fixtures: no browser observations, providers or real DB."""
from copy import deepcopy
import base64
import hashlib
import json
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import (
    AUTHORIZATION_SCHEMA, BROWSER_SCHEMA, build_operator_review, validate_operator_review,
)
from content.textbook_preview_audio_contract import compare_transcript, revision_audio_plan, tts_request_id, asr_request_id
from content.textbook_pinyin_pronunciation import sha_text, provider_pronunciation
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from tests import test_textbook_pinyin_pronunciation as fixtures
from tests import test_textbook_pinyin_reconciliation_publication as reconciliation_fixtures

sign, usage_receipt = fixtures.sign, fixtures.usage_receipt


class OperatorReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PinyinPublicationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.audit.pop('listeningReview')
        sign(self.f.audit)
        self.now = now_ms()
        self.auth = sign({'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message',
            'statement': 'SYNTHETIC TEST ONLY: user authorizes operator checks and publication without individual listening.',
            'recordedAt': self.now - 2000,
            'scope': {k: self.f.plan['binding'][k] for k in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True,
            'individualListeningConfirmationRequired': False})
        checks = [{'kind': 'picture-supported-layout', 'sceneId': s['id'], 'passed': True,
                   'observation': 'SYNTHETIC TEST browser observation', 'evidenceSha256': '1' * 64}
                  for s in self.f.classroom['scenes']]
        checks.append({'kind': 'interaction', 'sceneId': 's2', 'passed': True,
                       'observation': 'SYNTHETIC TEST interaction', 'evidenceSha256': '2' * 64})
        entry = self.f.audit['segments'][0]
        checks.append({'kind': 'audio-playback', **{k: entry[k] for k in
            ('sceneId', 'actionId', 'ttsRequestId', 'audioSha256')}, 'passed': True,
            'events': ['playing', 'ended'], 'syntheticAudio': False,
            'observation': 'SYNTHETIC TEST playback fixture, not an actual listening claim', 'evidenceSha256': '3' * 64})
        self.browser = sign({'schemaVersion': BROWSER_SCHEMA,
            'sourceSha256': self.f.row['classroom_sha256'], 'coreSha256': self.f.plan['coreSha256'],
            'planSha256': digest(self.f.plan), 'method': 'real-browser',
            'reviewer': 'Synthetic fixture', 'reviewedAt': self.now - 1000,
            'coverage': 'all-scenes-layout-and-recorded-action-samples', 'checks': checks})
        self.request_plans = []
        self.asr_recheck = None
        self.review = self.make_review()

    def make_review(self):
        f = self.f
        return build_operator_review(plan=f.plan, classroom=f.classroom, audit=f.audit,
            tts_receipts=json.loads(f.row['result_json'])['audioReceipts'],
            authorization=self.auth, browser_qa=self.browser, reviewer='Synthetic test operator',
            reviewed_at=self.now, expected_source_sha256=f.row['classroom_sha256'], now_ms=self.now,
            request_plans=self.request_plans, asr_recheck=self.asr_recheck)

    def validate(self, value=None):
        return validate_operator_review(value if value is not None else self.review, plan=self.f.plan,
            classroom=self.f.classroom, audit=self.f.audit,
            expected_source_sha256=self.f.row['classroom_sha256'], now_ms=self.now)

    def prepare(self, value=None, **kwargs):
        f = self.f
        return f.service.prepare(key=f.key, edition=f.manifest['editionId'], revision=f.manifest['revisionId'],
            node='u2-l1', teaching_revision='1', review=f.review, audio_audit=f.audit,
            classroom_directory=f.root, pronunciation_review=value if value is not None else self.review, **kwargs)

    def test_independent_evidence_preserves_raw_audit_and_no_human_claim(self):
        before = canonical({'audit': self.f.audit, 'review': self.review})
        accepted = self.validate()
        self.assertEqual(set(accepted), {('s1', 'a1'), ('s2', 'a2')})
        self.assertFalse(self.review['humanListeningVerified'])
        self.assertFalse(self.review['perceptualToneVerified'])
        accepted[('s1', 'a1')]['ttsReceipt'].clear()
        self.assertEqual(canonical({'audit': self.f.audit, 'review': self.review}), before)

    def test_prepare_and_portable_read_keep_original_audit_and_exact_media(self):
        original = canonical(self.f.audit)
        prepared = self.prepare()
        release = validate_release(self.f.build(prepared), self.f.manifest)
        self.assertEqual(canonical(release['audioAudit']['literalAudit']), original)
        self.assertEqual(release['audioAudit']['pronunciationReview'], self.review)
        self.assertNotIn('listeningReview', release['audioAudit'])
        self.assertEqual(release['audioAudit']['acceptanceMethod'], 'literal-asr')
        self.assertEqual(prepared['frozen']['pronunciationReviewSha256'], self.review['sha256'])
        self.f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        self.f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_raw_low_score_failure_and_false_comparison_cannot_be_waived(self):
        original = deepcopy(self.f.audit)
        for mutate in (
            lambda e: e['asr'].update(status='failed'),
            lambda e: e['asr'].update(completionUsable=False),
            lambda e: e.update(similarityBps=8499),
            lambda e: e['comparison'].update(passed=1),
        ):
            self.f.audit = deepcopy(original); mutate(self.f.audit['segments'][0]); sign(self.f.audit)
            review = deepcopy(self.review); review['auditSha256'] = digest(self.f.audit); sign(review)
            with self.subTest(mutation=mutate), self.assertRaises(ApiError): self.validate(review)
        self.f.audit = deepcopy(original)
        entry = self.f.audit['segments'][0]
        entry['transcript'] = '完全不同的内容'
        entry['asr'].update(transcript=entry['transcript'], transcriptSha256=sha_text(entry['transcript']))
        entry['comparison'] = compare_transcript(self.f.plan, entry['text'], entry['transcript'])
        entry['similarityBps'] = entry['comparison']['similarityBps']
        self.f.audit['passed'] = False; sign(self.f.audit)
        with self.assertRaises(ApiError): self.make_review()

    def test_missing_extra_duplicate_segments_and_tampered_evidence_rejected(self):
        for field in ('sourceSha256', 'coreSha256', 'planSha256', 'policySha256', 'auditSha256'):
            review = deepcopy(self.review); review[field] = '0' * 64; sign(review)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(review)
        for field in ('textSha256', 'ttsRequestId', 'audioSha256', 'pcmSha256', 'requestPlanSha256',
                      'ttsReceiptSha256', 'asrRequestId', 'asrReceiptSha256', 'auditSegmentSha256'):
            review = deepcopy(self.review); review['segments'][0][field] = '0' * 64; sign(review)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(review)
        for mutation in ('missing', 'duplicate', 'extra'):
            review = deepcopy(self.review)
            if mutation == 'missing': review['segments'].pop()
            elif mutation == 'duplicate': review['segments'].append(deepcopy(review['segments'][0]))
            else: review['segments'][0]['actionId'] = 'unknown'
            sign(review)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.validate(review)

    def test_no_unsupported_human_or_perceptual_claim_and_authorization_is_explicit(self):
        for field in ('humanListeningVerified', 'perceptualToneVerified'):
            review = deepcopy(self.review); review[field] = True; sign(review)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(review)
        for field, value in [('statement', ''), ('source', 'inferred'), ('automatedChecksAuthorized', False),
                             ('publicationAuthorized', False), ('recordedAt', self.now + 1)]:
            review = deepcopy(self.review); review['authorization'][field] = value
            sign(review['authorization']); sign(review)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(review)

    def test_real_browser_scope_and_current_actual_playback_required(self):
        for mutation in ('fake-audio', 'queued-only', 'old-audio', 'no-layout', 'no-interaction', 'old-source'):
            review = deepcopy(self.review); qa = review['browserQa']
            if mutation == 'fake-audio': qa['checks'][-1]['syntheticAudio'] = True
            elif mutation == 'queued-only': qa['checks'][-1]['events'] = ['queued']
            elif mutation == 'old-audio': qa['checks'][-1]['audioSha256'] = 'f' * 64
            elif mutation == 'no-layout': qa['checks'].pop(0)
            elif mutation == 'no-interaction': qa['checks'] = [x for x in qa['checks'] if x['kind'] != 'interaction']
            else: qa['sourceSha256'] = 'f' * 64
            sign(qa); sign(review)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.validate(review)

    def test_formal_helper_ready_after_real_playing_is_valid_completion_evidence(self):
        review = deepcopy(self.review)
        review['browserQa']['checks'][-1]['events'] = ['playing', 'ready-after-playing']
        review['browserQa']['checks'][-1]['observation'] = 'Synthetic formal helper same cue ready after its real playback began.'
        sign(review['browserQa']); sign(review)
        self.assertEqual(set(self.validate(review)), {('s1', 'a1'), ('s2', 'a2')})

    def test_actual_tts_receipts_and_wav_checked_before_archive(self):
        review = deepcopy(self.review)
        review['segments'][0]['ttsReceipt']['providerRequestId'] = 'changed-valid-looking-id'
        review['segments'][0]['ttsReceiptSha256'] = digest(review['segments'][0]['ttsReceipt']); sign(review)
        self.validate(review)  # Structurally valid; authoritative prepare must reject it.
        with self.assertRaises(ApiError): self.prepare(review)
        path = self.f.root / self.f.cid / 'audio' / (self.review['segments'][0]['ttsRequestId'] + '.wav')
        value = bytearray(path.read_bytes()); value[-1] ^= 1; path.write_bytes(value)
        with self.assertRaises(ApiError): self.prepare()
        self.assertFalse(list(self.f.root.glob('tbpub_*')))

    def test_narration_revision_requires_actual_archived_request_plan_and_remains_portable(self):
        f = self.f
        action = f.classroom['scenes'][0]['actions'][0]
        old_id = action['audioId']
        action['text'] = 'e，请再和老师一起读。'
        revision = revision_audio_plan(f.plan, revision_id='e' * 64,
            classroom_sha256=digest(f.classroom), core_sha256='f' * 64,
            frozen_input=json.loads(f.row['input_json']))
        request = tts_request_id(revision, 's1', 'a1', action['text'])
        action.update(audioId=request, audioUrl=f'/api/classroom-media/{f.cid}/audio/{request}.wav')
        f.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl'] = action['audioUrl']
        folder = f.root / f.cid / 'textbook-preview-audio' / 'narration-revisions' / revision['revisionId']
        folder.mkdir(parents=True)
        (folder / 'plan.json').write_text(canonical(revision))
        audio_folder = f.root / f.cid / 'audio'
        (audio_folder / (request + '.wav')).write_bytes((audio_folder / (old_id + '.wav')).read_bytes())
        receipts = json.loads(f.row['result_json'])['audioReceipts']
        receipt = receipts[0]
        receipt.update(requestId=request, narrationRevisionId=revision['revisionId'],
            classroomContentSha256=revision['classroomSha256'],
            previewAudioIdentity={'planSha256': digest(revision), 'attempt': 1},
            providerPronunciation=provider_pronunciation(action['text']), **usage_receipt(action['text']))
        f.row['result_json'] = canonical({'audioReceipts': receipts})
        entry = f.audit['segments'][0]
        entry.update(text=action['text'], textSha256=sha_text(action['text']), ttsRequestId=request,
                     transcript=action['text'], comparison=compare_transcript(f.plan, action['text'], action['text']))
        entry['asr'].update(requestId=asr_request_id(f.plan, request, entry['audioSha256']),
            transcript=action['text'], transcriptSha256=sha_text(action['text']),
            providerPronunciation=provider_pronunciation(action['text']))
        current_sha = digest(f.classroom)
        f.row.update(classroom_json=canonical(f.classroom), classroom_sha256=current_sha)
        (f.root / (f.cid + '.json')).write_text(canonical(f.classroom))
        f.audit['sourceSha256'] = current_sha; sign(f.audit)
        f.review['sourceSha256'] = current_sha
        self.browser['sourceSha256'] = current_sha
        self.browser['checks'][-1]['ttsRequestId'] = request; sign(self.browser)
        self.request_plans = [revision]
        self.review = self.make_review()
        prepared = self.prepare()
        self.assertEqual(validate_release(f.build(prepared), f.manifest)['audioAudit']['pronunciationReview']['requestPlans'], [revision])
        (folder / 'plan.json').write_text('{}')
        with self.assertRaises(ApiError): self.prepare()

    def add_synthetic_recheck(self):
        from content import textbook_audio_recheck as recheck
        f = self.f; original = f.audit['segments'][0]
        receipt = json.loads(f.row['result_json'])['audioReceipts'][0]
        audio = (f.root / f.cid / 'audio' / (receipt['requestId'] + '.wav')).read_bytes()
        body_sha = hashlib.sha256(recheck.provider_body(audio)).hexdigest()
        transcript = '完全不同的内容'
        original.update(transcript=transcript, comparison=compare_transcript(f.plan, original['text'], transcript))
        original['similarityBps'] = original['comparison']['similarityBps']
        original['asr'].update(transcript=transcript, transcriptSha256=sha_text(transcript),
                               providerAsrBodySha256=body_sha)
        f.audit['passed'] = False; sign(f.audit)
        intent = recheck.build_intent(plan=f.plan, classroom=f.classroom, audit=f.audit,
            expected_source_sha256=f.row['classroom_sha256'],
            selections=[{'sceneId': 's1', 'actionId': 'a1', 'reason': 'SYNTHETIC discrepancy'}],
            created_at=self.now - 500)
        request = recheck.logical_request(f.plan, f.classroom, f.classroom['scenes'][0],
            f.classroom['scenes'][0]['actions'][0], receipt, original)
        response = deepcopy(original['asr'])
        response.update(requestId=request['requestId'], transcript=original['text'],
                        transcriptSha256=sha_text(original['text']), completionUsable=True)
        entry = {'sceneId': 's1', 'actionId': 'a1', 'originalSegmentSha256': digest(original),
                 'request': request, 'requestSha256': digest(request), 'ttsReceipt': receipt,
                 'ttsReceiptSha256': digest(receipt), 'audioBase64': base64.b64encode(audio).decode(),
                 'asr': response, 'asrSha256': digest(response),
                 'comparison': compare_transcript(f.plan, original['text'], response['transcript']),
                 'observedAt': self.now - 100}
        self.asr_recheck = sign({'schemaVersion': recheck.SCHEMA, 'intent': intent, 'segments': [entry],
                                'createdAt': self.now})
        self.review = self.make_review()

    def test_one_independent_asr_recheck_roundtrips_publication_without_rewriting_failed_raw(self):
        self.add_synthetic_recheck()
        original = canonical(self.f.audit)
        prepared = self.prepare()
        release = validate_release(self.f.build(prepared), self.f.manifest)
        self.assertNotEqual(release['classroom']['id'], self.f.classroom['id'])
        self.assertEqual(prepared['frozen']['sourceClassroomId'], self.f.classroom['id'])
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertEqual(release['audioAudit']['acceptanceMethod'], 'independent-asr-recheck')
        self.assertEqual(canonical(release['audioAudit']['literalAudit']), original)
        self.assertNotIn('audioAcceptance', prepared['frozen'])
        self.assertNotIn('listeningReview', release['audioAudit'])
        self.assertEqual(canonical(self.f.audit), original)

    def test_failed_or_tampered_recheck_cannot_be_used_as_operator_waiver(self):
        self.add_synthetic_recheck()
        original = deepcopy(self.asr_recheck)
        for mutation in ('still-low', 'different-tts', 'different-wav', 'missing'):
            value = deepcopy(original)
            entry = value['segments'][0]
            if mutation == 'still-low':
                entry['asr'].update(transcript='完全错误', transcriptSha256=sha_text('完全错误'))
                entry['asrSha256'] = digest(entry['asr'])
                entry['comparison'] = compare_transcript(self.f.plan, self.f.audit['segments'][0]['text'], '完全错误')
            elif mutation == 'different-tts':
                entry['ttsReceipt']['providerRequestId'] = 'different-valid-looking-provider-request'
                entry['ttsReceiptSha256'] = digest(entry['ttsReceipt'])
            elif mutation == 'different-wav': entry['audioBase64'] = base64.b64encode(b'wrong').decode()
            else: value['segments'] = []
            self.asr_recheck = sign(value)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.make_review()

    def test_operator_acceptance_cannot_predate_its_independent_recheck(self):
        self.add_synthetic_recheck()
        review = deepcopy(self.review)
        review['reviewedAt'] = self.now - 200
        sign(review)
        with self.assertRaises(ApiError): self.validate(review)

    def test_ssml_body_pcm_provider_mutation_and_mixed_human_evidence_rejected(self):
        for field in ('ssmlSha256', 'providerBodySha256', 'sourceTextSha256'):
            review = deepcopy(self.review); r = review['segments'][0]['ttsReceipt']
            r['providerPronunciation'][field] = '0' * 64
            review['segments'][0]['ttsReceiptSha256'] = digest(r); sign(review)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(review)
        with self.assertRaises(ApiError): self.prepare(asr_reconciliation={})
        self.f.audit['listeningReview'] = self.f.listening; sign(self.f.audit)
        with self.assertRaises(ApiError): self.prepare()

    def test_portable_release_rejects_stripped_review_forged_pass_and_media_exchange(self):
        prepared = self.prepare()
        reseal = reconciliation_fixtures.PinyinReconciliationPublicationTests().reseal_release
        for mutation in ('strip-review', 'strip-frozen', 'human-claim', 'media-mismatch', 'strip-literal'):
            bad = deepcopy(prepared); audit = bad['review']['release']['audioAudit']
            if mutation == 'strip-review': audit.pop('pronunciationReview')
            elif mutation == 'strip-frozen': bad['frozen'].pop('pronunciationReviewSha256')
            elif mutation == 'human-claim':
                audit['pronunciationReview']['humanListeningVerified'] = True
                sign(audit['pronunciationReview'])
                bad['frozen']['pronunciationReviewSha256'] = audit['pronunciationReview']['sha256']
            elif mutation == 'media-mismatch': bad['review']['release']['media'][0]['sourceSha256'] = '0' * 64
            else: audit.pop('literalAudit')
            reseal(bad)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                validate_release(self.f.build(bad), self.f.manifest)


if __name__ == '__main__':
    unittest.main()
