"""Automatic initialization uses synthetic local evidence, never paid services."""
from copy import deepcopy
import json
import unittest

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import AUTHORIZATION_SCHEMA
from core.errors import ApiError
from core.security import now_ms
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_audio import core_content
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization as fixtures


def seal(value):
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    return value


class OperatorPronunciationInitializationTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.PronunciationInitializationTests()
        self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.now = now_ms()
        frozen = json.loads(self.fx.row['input_json'])
        self.authorization = seal({
            'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message',
            'statement': 'SYNTHETIC authorization for automatic checks and publication, not listening.',
            'recordedAt': self.now - 1000,
            'scope': {k: frozen[k] for k in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True,
            'individualListeningConfirmationRequired': False})
        old = self.fx.approval
        self.review = {k: deepcopy(old[k]) for k in ('previewKey', 'sourceSha256',
            'pronunciationPolicyVersion', 'pronunciationPolicySha256', 'formalUseAllowed', 'probePlanSha256')}
        self.review.update(schemaVersion=initialization.OPERATOR_REVIEW_SCHEMA,
            method=initialization.OPERATOR_METHOD, coreSha256=self.fx.patch['expectedCoreSha256'],
            reviewer='Synthetic operator', recordedAt=self.now, authorization=deepcopy(self.authorization),
            result=initialization.OPERATOR_RESULT, humanListeningVerified=False, perceptualToneVerified=False,
            evidenceLimit=initialization.OPERATOR_EVIDENCE_LIMIT,
            samples=[{**s, 'result': initialization.OPERATOR_RESULT} for s in old['samples']])
        self.old_patch = deepcopy(self.fx.patch)
        self.old_approval_bytes = (self.fx.probes / 'human-approval.json').read_bytes()
        self.fx.patch = {k: v for k, v in self.fx.patch.items() if k != 'approvedProbeEvidence'}
        self.fx.patch.update(schemaVersion=initialization.OPERATOR_SCHEMA,
            basis='SYNTHETIC protocol and WAV verification; formal review remains pending.',
            verifiedProbeEvidence={'path': str(self.fx.probes / 'operator-probe-review.json'), 'sha256': ''})
        self.write_review()

    def write_review(self):
        seal(self.review)
        raw = canonical(self.review).encode()
        (self.fx.probes / 'operator-probe-review.json').write_bytes(raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def test_prepare_run_archive_no_human_claim_or_other_writes(self):
        fx = self.fx
        source = (fx.f.root / (fx.f.cid + '.json')).read_bytes()
        probes = {p: p.read_bytes() for p in fx.probes.rglob('*') if p.is_file()}
        pending = fx.run_initialization(False)
        self.assertTrue(pending['prepared']); self.assertFalse((fx.f.folder / 'plan.json').exists())
        result = fx.run_initialization()
        self.assertEqual(result['schemaVersion'], initialization.OPERATOR_SCHEMA)
        for field in ('generationDispatched', 'publicationAllowed', 'requiresFormalHumanListening',
                      'humanListeningVerified', 'perceptualToneVerified'):
            self.assertIs(result[field], False)
        self.assertIs(result['requiresFormalOperatorReview'], True)
        self.assertNotIn('approvedProbeEvidenceSha256', result)
        self.assertEqual(result['verifiedProbeEvidenceSha256'], fx.patch['verifiedProbeEvidence']['sha256'])
        intent = json.loads((fx.archive() / 'intent.json').read_text())
        self.assertEqual(intent['schemaVersion'], initialization.OPERATOR_SCHEMA)
        self.assertIn('evidence/operator-probe-review.json', intent['files'])
        self.assertNotIn('evidence/human-approval.json', intent['files'])
        self.assertEqual((fx.archive() / 'evidence/operator-probe-review.json').read_bytes(),
                         (fx.probes / 'operator-probe-review.json').read_bytes())
        self.assertEqual(fx.f.service.get(fx.f.key), fx.row)
        self.assertEqual((fx.f.root / (fx.f.cid + '.json')).read_bytes(), source)
        self.assertEqual(fx.run_initialization(), result)
        for path, raw in probes.items(): self.assertEqual(path.read_bytes(), raw)
        self.assertEqual((fx.probes / 'human-approval.json').read_bytes(), self.old_approval_bytes)
        fx.assert_no_external_write()

    def test_exact_authorization_scope_flags_seal_and_time_required(self):
        original = deepcopy(self.review)
        for mutation in ('absent', 'subject', 'edition', 'confirmation', 'checks', 'publish', 'source', 'seal', 'future'):
            self.review = deepcopy(original); auth = self.review['authorization']
            if mutation == 'absent': self.review.pop('authorization')
            elif mutation == 'subject': auth['scope']['subject'] = 'math'
            elif mutation == 'edition': auth['scope']['editionId'] = 'another-edition'
            elif mutation == 'confirmation': auth['individualListeningConfirmationRequired'] = True
            elif mutation == 'checks': auth['automatedChecksAuthorized'] = False
            elif mutation == 'publish': auth['publicationAuthorized'] = False
            elif mutation == 'source': auth['source'] = 'model-inference'
            elif mutation == 'seal': auth['statement'] += ' altered without seal'
            else: auth['recordedAt'] = self.now + 10_000_000
            if mutation not in ('absent', 'seal'): seal(auth)
            self.write_review()
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.fx.run_initialization()
        self.fx.assert_no_external_write()

    def test_automatic_review_cannot_assert_human_tone_formal_or_unknown_fields(self):
        original = deepcopy(self.review)
        variants = [('humanListeningVerified', True), ('perceptualToneVerified', True), ('formalUseAllowed', True),
            ('result', 'approved_by_human_listening'), ('method', 'human-listening'),
            ('evidenceLimit', 'All pronunciation verified'), ('recordedAt', self.now + 10_000_000),
            ('receivedAt', '2026-10-19T00:00:00+08:00')]
        for field, value in variants:
            self.review = {**deepcopy(original), field: value}; self.write_review()
            with self.subTest(field=field), self.assertRaises(ApiError): self.fx.run_initialization()
        self.review = deepcopy(original)
        self.review['samples'][0]['result'] = 'approved_by_human_listening'; self.write_review()
        with self.assertRaises(ApiError): self.fx.run_initialization()

    def test_source_core_policy_plan_and_fixed_inventory_remain_bound(self):
        original = deepcopy(self.review)
        for field in ('previewKey', 'sourceSha256', 'coreSha256', 'pronunciationPolicySha256', 'probePlanSha256'):
            self.review = {**deepcopy(original), field: '0' * 64}; self.write_review()
            with self.subTest(field=field), self.assertRaises(ApiError): self.fx.run_initialization()
        for mutation in ('missing', 'duplicate', 'extra', 'phoneme'):
            self.review = deepcopy(original)
            if mutation == 'missing': self.review['samples'].pop()
            elif mutation == 'duplicate': self.review['samples'][-1] = deepcopy(self.review['samples'][0])
            elif mutation == 'extra': self.review['samples'].append({**self.review['samples'][0], 'label': 'invented'})
            else: self.review['samples'][0]['phonemeCandidate'] = 'a1'
            self.write_review()
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.fx.run_initialization()

    def test_every_actual_probe_file_is_verified_not_just_review_seal(self):
        folder = self.fx.probes / next(iter(self.fx.probe_targets))
        for name in initialization.PROBE_FILES:
            path = folder / name; raw = path.read_bytes()
            path.write_bytes(raw + b'corruption')
            with self.subTest(file=name), self.assertRaises(ApiError): self.fx.run_initialization()
            path.write_bytes(raw)
        self.fx.assert_no_external_write()

    def test_unknown_or_unscoped_policy_rejected_before_evidence_read(self):
        for version in ('mira.textbook.pinyin-unregistered-ssml.v1', pronunciation.AOE_POLICY_VERSION):
            self.fx.patch.update(pronunciationPolicyVersion=version)
            self.fx.patch['verifiedProbeEvidence']['path'] = str(self.fx.probes / 'must-not-be-read.json')
            with self.subTest(policy=version), self.assertRaises(ApiError): self.fx.run_initialization()
        self.fx.f.runtime.get_classroom.assert_not_called()
        self.fx.assert_no_external_write()

    def test_v1_and_v2_evidence_or_active_plan_cannot_be_interchanged(self):
        automatic_patch = deepcopy(self.fx.patch)
        self.fx.patch['approvedProbeEvidence'] = self.old_patch['approvedProbeEvidence']
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.fx.patch = deepcopy(self.old_patch)
        self.fx.patch['approvedProbeEvidence'] = automatic_patch['verifiedProbeEvidence']
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.fx.patch = deepcopy(self.old_patch)
        historical = self.fx.run_initialization()
        original_plan = (self.fx.f.folder / 'plan.json').read_bytes()
        self.fx.patch = automatic_patch
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.assertEqual((self.fx.f.folder / 'plan.json').read_bytes(), original_plan)
        self.assertTrue(historical['requiresFormalHumanListening'])

    def test_actual_all_speech_preflight_rejects_unregistered_latin_before_install(self):
        fx = self.fx; f = fx.f
        f.classroom['scenes'][0]['actions'][0]['text'] = '未知映射 xyz。'
        f.save(f.classroom)
        f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                     (canonical(f.classroom), digest(f.classroom), f.key)); f.db.raw.commit()
        fx.patch.update(expectedSourceSha256=digest(f.classroom), expectedCoreSha256=digest(core_content(f.classroom)))
        self.review.update(sourceSha256=fx.patch['expectedSourceSha256'], coreSha256=fx.patch['expectedCoreSha256'])
        self.write_review()
        with self.assertRaises(ApiError): fx.run_initialization()
        self.assertFalse((f.folder / 'plan.json').exists()); fx.assert_no_external_write()

    def test_response_loss_and_exact_staging_recovery(self):
        self.fx.test_atomic_activation_response_loss_recovers_without_other_writes()

    def test_pre_rename_staging_only_recovers_verified_bytes(self):
        self.fx.test_interruption_before_plan_rename_recovers_only_exact_own_staging()

    def test_later_receipts_and_claims_are_preserved(self):
        self.fx.test_rerun_never_resets_later_formal_checkpoint_or_receipts()

    def test_actual_narrator_can_start_after_v2_and_reuses_completed_audio(self):
        # Real narrator code with synthetic provider only, not real audio calls.
        self.fx.test_real_narrator_sample_then_full_reuses_success_and_initialization_is_idempotent()

    def test_cli_prepare_preserves_unchanged_entrypoint(self):
        self.fx.test_cli_prepare_has_no_provider_or_database_writes()


if __name__ == '__main__':
    unittest.main()
