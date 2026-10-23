"""Synthetic raw routine evidence; no providers, real DB or browser claims."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import validate_operator_review
from content.textbook_pinyin_operator_review_v6 import (
    EXPLICIT_DECISION, METHOD_V6, UNRESOLVED_METHOD,
    build_explicit_acceptance_v6, build_operator_review_v6,
)
from content.textbook_pinyin_operator_review_v5 import build_explicit_acceptance
from content.textbook_pinyin_pronunciation import sha_text
from content.textbook_preview_audio_contract import compare_transcript, tts_request_id, asr_request_id
from content.textbook_release import validate_release
from core.errors import ApiError
from tests import test_textbook_pinyin_operator_review as fixtures

sign = fixtures.sign


class ExplicitRoutineAsrV6Tests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.OperatorReviewTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.f = self.fx.f
        entry = self.f.audit['segments'][0]
        entry['transcript'] = 'SYNTHETIC wrong recognition'
        entry['asr'].update(transcript=entry['transcript'], transcriptSha256=sha_text(entry['transcript']))
        entry['comparison'] = compare_transcript(self.f.plan, entry['text'], entry['transcript'])
        entry['similarityBps'] = entry['comparison']['similarityBps']
        self.f.audit['passed'] = False
        sign(self.f.audit)
        self.decision = self.make_decision()
        self.review = self.make_review()

    def context(self):
        return dict(plan=self.f.plan, classroom=self.f.classroom, audit=self.f.audit,
            tts_receipts=json.loads(self.f.row['result_json'])['audioReceipts'],
            expected_source_sha256=self.f.row['classroom_sha256'], now_ms=self.fx.now,
            request_plans=self.fx.request_plans)

    def make_decision(self, **changes):
        args = dict(probe_evidence_sha256='8' * 64,
            question_item_id=['request_user_input_async', 'synthetic-question-not-a-real-user', 0],
            question='SYNTHETIC TEST: accept these unresolved routine results for this lesson?',
            statement='SYNTHETIC TEST ONLY: explicitly accept and publish this lesson.',
            decision=EXPLICIT_DECISION, recorded_at=self.fx.now - 100)
        args.update(changes)
        return build_explicit_acceptance_v6(**self.context(), **args)

    def make_review(self, decision=None, **changes):
        args = self.context()
        args.update(authorization=self.fx.auth, browser_qa=self.fx.browser,
            reviewer='Synthetic fixture only', reviewed_at=self.fx.now,
            explicit_acceptance=self.decision if decision is None else decision)
        args.update(changes)
        return build_operator_review_v6(**args)

    def validate(self, review=None, **changes):
        args = self.context()
        args.pop('tts_receipts'); args.pop('request_plans'); args.update(changes)
        return validate_operator_review(self.review if review is None else review, **args)

    def test_exact_failed_set_preserves_raw_audit_and_false_claims(self):
        before = canonical(self.f.audit)
        result = self.validate()
        self.assertEqual(self.decision['unresolvedCount'], 1)
        self.assertEqual(result[('s1', 'a1')]['acceptanceMethod'], UNRESOLVED_METHOD)
        self.assertEqual(result[('s2', 'a2')]['acceptanceMethod'], 'literal-asr')
        self.assertEqual(result[('s1', 'a1')]['explicitAcceptanceSha256'], digest(self.decision))
        self.assertIsNone(result[('s2', 'a2')]['explicitAcceptanceSha256'])
        self.assertFalse(self.f.audit['passed'])
        for k in ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified'):
            self.assertIs(self.review[k], False); self.assertIs(self.decision[k], False)
        result[('s1', 'a1')]['ttsReceipt'].clear()
        self.assertEqual(before, canonical(self.f.audit))
        self.assertNotIn('origins', self.f.audit)
        self.assertNotIn('asrRecheck', self.review)

    def test_prepare_and_portable_release_keep_v2_raw_results(self):
        original = canonical(self.f.audit)
        prepared = self.fx.prepare(self.review)
        release = validate_release(self.f.build(prepared), self.f.manifest)
        self.assertEqual(canonical(release['audioAudit']['literalAudit']), original)
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertEqual(release['audioAudit']['acceptanceMethod'], METHOD_V6)
        self.assertEqual(release['audioAudit']['pronunciationReview'], self.review)
        self.f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        self.f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_three_equal_pcm_routines_preserve_all_original_request_ids(self):
        # Three distinct actions share identical text/WAV; each already has its
        # own routine response. No child may be renamed a recheck or discarded.
        old_action = self.f.classroom['scenes'][0]['actions'][0]
        old_entry = self.f.audit['segments'][0]
        result = json.loads(self.f.row['result_json'])
        old_receipt = result['audioReceipts'][0]
        for index in (3, 4):
            action = deepcopy(old_action); action['id'] = f'a{index}'
            rid = tts_request_id(self.f.plan, 's1', action['id'], action['text'])
            action.update(audioId=rid, audioUrl=f'/api/classroom-media/{self.f.cid}/audio/{rid}.wav')
            self.f.classroom['scenes'][0]['actions'].append(action)
            receipt = {**deepcopy(old_receipt), 'requestId': rid}
            result['audioReceipts'].append(receipt)
            entry = deepcopy(old_entry); entry.update(actionId=action['id'], ttsRequestId=rid)
            entry['asr']['requestId'] = asr_request_id(self.f.plan, rid, entry['audioSha256'])
            self.f.audit['segments'].append(entry)
            folder = self.f.root / self.f.cid / 'audio'
            (folder / (rid + '.wav')).write_bytes((folder / (old_action['audioId'] + '.wav')).read_bytes())
        source_sha = digest(self.f.classroom)
        self.f.row.update(classroom_json=canonical(self.f.classroom), classroom_sha256=source_sha,
                          result_json=canonical(result))
        (self.f.root / (self.f.cid + '.json')).write_text(canonical(self.f.classroom))
        self.f.review['sourceSha256'] = source_sha
        self.f.audit['sourceSha256'] = source_sha; sign(self.f.audit)
        self.fx.browser['sourceSha256'] = source_sha; sign(self.fx.browser)
        self.decision = self.make_decision(); self.review = self.make_review()
        self.assertEqual(self.decision['unresolvedCount'], 3)
        expected_ids = [e['asr']['requestId'] for e in self.f.audit['segments']]
        before = canonical(self.f.audit)
        prepared = self.fx.prepare(self.review)
        release = validate_release(self.f.build(prepared), self.f.manifest)
        self.assertEqual(canonical(release['audioAudit']['literalAudit']), before)
        self.assertEqual([s['asrRequestId'] for s in self.review['segments']], expected_ids)
        self.assertEqual(len(set(expected_ids)), 4)

    def test_resealed_decision_source_scope_and_identity_tampering_rejected(self):
        mutations = [lambda d, k=k: d.update({k: '0' * 64})
                     for k in ('sourceSha256', 'planSha256', 'auditSha256')]
        mutations += [lambda d, k=k: d['scope'].update({k: 'other-lesson'})
                      for k in ('editionId', 'nodeId', 'previewKey', 'sourceClassroomId')]
        mutations += [lambda d, k=k: d['unresolvedSegments'][0].update({k: '0' * 64})
                      for k in ('textSha256', 'audioSha256', 'pcmSha256', 'ttsRequestId', 'asrRequestId',
                                'asrReceiptSha256', 'transcriptSha256', 'auditSegmentSha256')]
        for i, mutate in enumerate(mutations):
            decision = deepcopy(self.decision); mutate(decision); sign(decision)
            with self.subTest(i=i), self.assertRaises(ApiError): self.make_review(decision)

    def test_missing_extra_duplicate_and_passed_entries_cannot_be_accepted(self):
        for kind in ('missing', 'extra', 'duplicate', 'passed', 'wrong-count'):
            d = deepcopy(self.decision)
            if kind == 'missing': d['unresolvedSegments'].clear()
            elif kind in ('extra', 'duplicate'):
                d['unresolvedSegments'].append(deepcopy(d['unresolvedSegments'][0]))
                if kind == 'extra': d['unresolvedSegments'][-1]['actionId'] = 'unknown'
            elif kind == 'passed': d['unresolvedSegments'][0].update(sceneId='s2', actionId='a2')
            else: d['unresolvedCount'] = 66
            sign(d)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.make_review(d)
        for kind in ('missing', 'extra', 'duplicate'):
            r = deepcopy(self.review)
            if kind == 'missing': r['segments'].pop()
            elif kind == 'duplicate': r['segments'].append(deepcopy(r['segments'][0]))
            else: r['segments'][0]['actionId'] = 'unknown'
            sign(r)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.validate(r)

    def test_false_permissions_human_claims_and_wrong_decision_rejected(self):
        for k in ('onlyThisLesson', 'noFurtherProviderCalls', 'publicationAuthorized',
                  'unresolvedAsrAccepted', 'preserveRawEvidence', 'humanListeningVerified',
                  'phoneticAccuracyVerified', 'perceptualToneVerified'):
            d = deepcopy(self.decision); d[k] = not d[k]; sign(d)
            with self.subTest(k=k), self.assertRaises(ApiError): self.make_review(d)
        for args in ({'decision': 'declined'}, {'question': ''}, {'statement': ''},
                     {'probe_evidence_sha256': 'invalid'}, {'recorded_at': self.fx.now + 1},
                     {'question_item_id': ['request_user_input_async', 'id', True]}):
            with self.subTest(args=args), self.assertRaises(ApiError): self.make_decision(**args)
        self.fx.auth['publicationAuthorized'] = False; sign(self.fx.auth)
        with self.assertRaises(ApiError): self.make_review()

    def test_raw_transcript_receipt_policy_and_source_tampering_rejected(self):
        for kind in ('transcript', 'response-transcript', 'comparison', 'status', 'unknown', 'asr-id', 'asr-body', 'drop'):
            audit = deepcopy(self.f.audit); e = audit['segments'][0]
            if kind == 'transcript': e['transcript'] = 'tampered'
            elif kind == 'response-transcript': e['asr']['transcript'] = 'tampered'
            elif kind == 'comparison': e['comparison']['passed'] = True
            elif kind == 'status': e['asr']['status'] = 'failed'
            elif kind == 'unknown': e['asr']['completionUsable'] = False
            elif kind == 'asr-id': e['asr']['requestId'] = 'tbpasr1_' + '0' * 64
            elif kind == 'asr-body': e['asr']['providerPronunciation']['providerBodySha256'] = '0' * 64
            else: audit['segments'].pop()
            sign(audit)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.validate(audit=audit)
        for field in ('pcmSha256', 'audioSha256', 'requestId'):
            r = deepcopy(self.review); r['segments'][0]['ttsReceipt'][field] = '0' * 64; sign(r)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(r)
        with self.assertRaises(ApiError): self.validate(expected_source_sha256='0' * 64)

    def test_authoritative_receipt_wav_and_actual_browser_checks_remain_required(self):
        d = deepcopy(self.decision)
        receipts = json.loads(self.f.row['result_json'])['audioReceipts']
        # A syntactically valid changed receipt still cannot replace the actual
        # row's receipt at the publication boundary.
        receipts[1]['providerRequestId'] = 'changed-valid-looking-id'
        r = self.make_review(tts_receipts=receipts)
        self.validate(r)
        with self.assertRaises(ApiError): self.fx.prepare(r)
        p = self.f.root / self.f.cid / 'audio' / (self.review['segments'][0]['ttsRequestId'] + '.wav')
        audio = bytearray(p.read_bytes()); audio[-1] ^= 1; p.write_bytes(audio)
        with self.assertRaises(ApiError): self.fx.prepare(self.review)
        self.assertFalse(list(self.f.root.glob('tbpub_*')))
        for kind in ('empty', 'synthetic', 'queued'):
            qa = deepcopy(self.fx.browser)
            if kind == 'empty': qa['checks'].clear()
            elif kind == 'synthetic': qa['checks'][-1]['syntheticAudio'] = True
            else: qa['checks'][-1]['events'] = ['queued']
            sign(qa)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.make_review(d, browser_qa=qa)

    def test_old_v1_and_v5_do_not_gain_an_unresolved_routine_exception(self):
        with self.assertRaises(ApiError): self.fx.make_review()
        with self.assertRaisesRegex(ApiError, 'Wrong origin audit schema'):
            build_explicit_acceptance(plan=self.f.plan, classroom=self.f.classroom, audit=self.f.audit,
                expected_source_sha256=self.f.row['classroom_sha256'], now_ms=self.fx.now,
                approved_probe_sha256='8' * 64,
                question_item_id=['request_user_input_async', 'synthetic', 0], question='test', statement='test',
                decision=EXPLICIT_DECISION, recorded_at=self.fx.now)


if __name__ == '__main__':
    unittest.main()
