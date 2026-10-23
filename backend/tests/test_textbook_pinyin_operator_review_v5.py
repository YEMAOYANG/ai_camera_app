"""Synthetic current-WAV evidence; no real provider, browser or student writes."""
from copy import deepcopy
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_audio_recheck import seal
from content.textbook_asr_source_reuse import sha, shared_recheck_id, verify_origin
from content.textbook_pinyin_operator_review import validate_operator_review
from content.textbook_pinyin_operator_review_v5 import (
    EXPLICIT_DECISION, METHOD_V5, UNRESOLVED_METHOD,
    build_explicit_acceptance, build_operator_review_v5,
)
from core.errors import ApiError
from tests import test_textbook_asr_source_reuse as origin_fixtures


class ExplicitUnresolvedAsrV5Tests(unittest.TestCase):
    def setUp(self):
        self.origin = origin_fixtures.AsrOriginTests()
        self.origin.setUp()
        self.addCleanup(self.origin.doCleanups)
        self.f = self.origin.f
        self.fx = self.origin.fx
        self.original_origins = deepcopy(self.origin.origins)
        first = self.origin.origins[0]
        response = first['attempts'][0]['response']
        response.update(transcript='擦波璃。', transcriptSha256=sha('擦波璃。'.encode()))
        facts = verify_origin(first)
        second = deepcopy(first['attempts'][0])
        second['role'] = 'recheck'
        request_id = shared_recheck_id(facts['pcmKey'])
        second['request']['requestId'] = request_id
        second['response']['requestId'] = request_id
        first['attempts'].append(second)
        self.origin.audit = self.origin.make_audit()
        self.audit = self.origin.audit
        self.decision = self.make_decision()
        self.review = self.make_review()

    def context(self):
        return dict(plan=self.f.plan, classroom=self.f.classroom, audit=self.audit,
            expected_source_sha256=digest(self.f.classroom), now_ms=self.fx.now)

    def make_decision(self, **changes):
        args = dict(approved_probe_sha256='8' * 64,
            question_item_id=['request_user_input_async', 'synthetic-question-not-a-real-user', 0],
            question='SYNTHETIC TEST: accept this exact unresolved set for this lesson and publish?',
            statement='SYNTHETIC TEST ONLY: expressly accept the unresolved set and publication.',
            decision=EXPLICIT_DECISION, recorded_at=self.fx.now - 100)
        args.update(changes)
        return build_explicit_acceptance(**self.context(), **args)

    def make_review(self, decision=None):
        return build_operator_review_v5(**self.context(), authorization=self.fx.auth,
            browser_qa=self.fx.browser, reviewer='Synthetic fixture only', reviewed_at=self.fx.now,
            explicit_acceptance=self.decision if decision is None else decision)

    def validate(self, review=None, **changes):
        args = self.context(); args.update(changes)
        return validate_operator_review(self.review if review is None else review, **args)

    def test_only_failed_set_changes_method_and_all_original_bytes_remain(self):
        before = canonical({'audit': self.audit, 'origins': self.origin.origins})
        result = self.validate()
        self.assertEqual(self.decision['unresolvedCount'], 1)
        unresolved = self.decision['unresolvedSegments'][0]
        self.assertEqual((unresolved['sceneId'], unresolved['actionId']), ('s1', 'a1'))
        self.assertEqual(len(unresolved['asrAttempts']), 2)
        self.assertEqual(unresolved['asrAttempts'][0]['transcriptSha256'], sha('擦波璃。'.encode()))
        self.assertEqual(result[('s1', 'a1')]['acceptanceMethod'], UNRESOLVED_METHOD)
        self.assertEqual(result[('s2', 'a2')]['acceptanceMethod'], 'literal-asr')
        self.assertFalse(self.audit['passed'])
        self.assertFalse(result[('s1', 'a1')]['originalLiteralPassed'])
        for key in ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified'):
            self.assertIs(self.review[key], False)
            self.assertIs(self.decision[key], False)
            self.assertIs(self.audit[key], False)
        result[('s1', 'a1')]['ttsReceipt'].clear()
        self.assertEqual(before, canonical({'audit': self.audit, 'origins': self.origin.origins}))

    def test_prepare_and_portable_release_accept_explicit_decision_but_v4_does_not(self):
        with self.assertRaises(ApiError):
            self.origin.make_review()
        self.origin.review = self.review
        release = self.fx.read(self.origin.prepare())
        self.assertEqual(release['audioAudit']['acceptanceMethod'], METHOD_V5)
        self.assertEqual(release['audioAudit']['literalAudit'], self.audit)
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertEqual(release['audioAudit']['pronunciationReview']['explicitAcceptance'], self.decision)
        self.f.service.preview.runtime.start_formal_audio_tts.assert_not_called()
        self.f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_resealed_source_audit_plan_scope_and_segment_identity_tampering_rejected(self):
        mutations = [lambda d, key=key: d.update({key: '0' * 64})
                     for key in ('sourceSha256', 'auditSha256', 'planSha256')]
        mutations += [lambda d, key=key: d['scope'].update({key: 'another-lesson'})
                      for key in ('editionId', 'nodeId', 'previewKey', 'sourceClassroomId')]
        mutations += [lambda d, key=key: d['unresolvedSegments'][0].update({key: '0' * 64})
                      for key in ('audioSha256', 'pcmSha256', 'textSha256', 'ttsRequestId', 'originSha256')]
        mutations += [lambda d, key=key: d['unresolvedSegments'][0]['asrAttempts'][1].update({key: 'changed'})
                      for key in ('requestId', 'transcriptSha256')]
        for index, mutate in enumerate(mutations):
            decision = deepcopy(self.decision); mutate(decision); seal(decision)
            with self.subTest(index=index), self.assertRaises(ApiError):
                self.make_review(decision)

    def test_missing_extra_duplicate_and_already_passed_items_cannot_be_accepted(self):
        for kind in ('missing', 'extra', 'duplicate', 'passed', 'wrong-count', 'omitted-attempt'):
            decision = deepcopy(self.decision)
            if kind == 'missing': decision['unresolvedSegments'].clear()
            elif kind in ('extra', 'duplicate'):
                decision['unresolvedSegments'].append(deepcopy(decision['unresolvedSegments'][0]))
                if kind == 'extra': decision['unresolvedSegments'][-1]['actionId'] = 'unknown'
            elif kind == 'passed': decision['unresolvedSegments'][0].update(sceneId='s2', actionId='a2')
            elif kind == 'wrong-count': decision['unresolvedCount'] = 47
            else: decision['unresolvedSegments'][0]['asrAttempts'].pop()
            seal(decision)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.make_review(decision)
        review = deepcopy(self.review)
        review['segments'][1]['acceptanceMethod'] = UNRESOLVED_METHOD
        seal(review)
        with self.assertRaises(ApiError): self.validate(review)

    def test_false_permissions_human_claims_and_wrong_decision_rejected(self):
        for key in ('onlyThisLesson', 'noFurtherProviderCalls', 'publicationAuthorized',
                    'unresolvedAsrAccepted', 'preserveRawEvidence', 'humanListeningVerified',
                    'phoneticAccuracyVerified', 'perceptualToneVerified'):
            decision = deepcopy(self.decision); decision[key] = not decision[key]; seal(decision)
            with self.subTest(key=key), self.assertRaises(ApiError): self.make_review(decision)
        for changes in ({'decision': 'declined'}, {'question': ''}, {'statement': ''},
                        {'approved_probe_sha256': 'invalid'}, {'recorded_at': self.fx.now + 1},
                        {'question_item_id': ['request_user_input_async', 'id', True]}):
            with self.subTest(changes=changes), self.assertRaises(ApiError): self.make_decision(**changes)
        for key in ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified'):
            review = deepcopy(self.review); review[key] = True; seal(review)
            with self.subTest(key=key), self.assertRaises(ApiError): self.validate(review)
        self.fx.auth['publicationAuthorized'] = False; seal(self.fx.auth)
        with self.assertRaises(ApiError): self.make_review()

    def test_real_audit_audio_receipt_and_source_checks_are_not_waived(self):
        for kind in ('wav', 'receipt', 'comparison', 'asr-transcript', 'source'):
            audit = deepcopy(self.audit)
            if kind == 'wav': audit['segments'][0]['target']['audioBase64'] = audit['segments'][1]['target']['audioBase64']
            elif kind == 'receipt': audit['segments'][0]['target']['ttsReceipt']['pcmSha256'] = '0' * 64
            elif kind == 'comparison': audit['segments'][0]['comparison']['passed'] = True
            elif kind == 'asr-transcript': audit['origins'][0]['attempts'][0]['response']['transcript'] = 'changed'
            else: audit['sourceSha256'] = '0' * 64
            seal(audit)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.validate(audit=audit)
        with self.assertRaises(ApiError): self.validate(expected_source_sha256='0' * 64)

    def test_no_new_uncertainty_for_an_already_accepted_lesson_or_empty_browser_qa(self):
        self.fx.browser['checks'] = []; seal(self.fx.browser)
        with self.assertRaises(ApiError): self.make_review()
        self.origin.origins = self.original_origins
        self.audit = self.origin.make_audit()
        with self.assertRaisesRegex(ApiError, 'already accepted'):
            self.make_decision()


if __name__ == '__main__':
    unittest.main()
