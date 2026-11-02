"""Garden-four inventory and first-profile evidence; no provider calls."""
from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import AUTHORIZATION_SCHEMA
from core.errors import ApiError
from core.security import now_ms
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_audio import narrate_preview
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization as fixtures
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan


VERSION = 'mira.textbook.pinyin-garden4-ssml.v1'
POLICY_SHA = 'd3c08335bc9137633bba84d2d338c2dc23d9509bf6a923dab1ded03619f235a2'
CONTRASTS = 'yǎn yuǎn yīn yīng jiǎn juǎn zuān zhuān chán chuán chuáng'.split()
INITIALS = 'b p m f d t n l g k h j q x zh ch sh r z c s y w'.split()
FINALS = 'a o e i u ü ai ei ui ao ou iu ie üe er an en in un ün ang eng ing ong'.split()
WHOLE = 'zhi chi shi ri zi ci si yi wu yu ye yue yuan yin yun ying'.split()
CONTRAST_PH = 'yan3 yuan3 yin1 ying1 jian3 juan3 zuan1 zhuan1 chan2 chuan2 chuang2'.split()
PROBE_TOKENS = {
    'near-contrast-and-poem-context': (*CONTRASTS, '谁'),
    'initials-table-context': tuple(INITIALS),
    'finals-table-context': tuple(FINALS),
    'whole-table-context': tuple(WHOLE),
}
PROBE_TEXTS = {
    'near-contrast-and-poem-context': '请听：yǎn、yuǎn；yīn、yīng；jiǎn、juǎn；zuān、zhuān；chán、chuán、chuáng。谁知盘中餐。',
    'initials-table-context': '请听声母：b、p、m、f、d、t、n、l、g、k、h、j、q、x；zh、ch、sh、r、z、c、s；(y w)。',
    'finals-table-context': '请听韵母：a、o、e、i、u、ü；ai、ei、ui、ao、ou、iu、ie、üe、er；an、en、in、un、ün、ang、eng、ing、ong。',
    'whole-table-context': '请听整体认读音节：zhi、chi、shi、ri、zi、ci、si；yi、wu、yu、ye、yue、yuan、yin、yun、ying。',
}
PROBE_TARGETS = {label: tokens[0] for label, tokens in PROBE_TOKENS.items()}


def seal(value):
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    return value


class GardenFourPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = registry.registered_policy(VERSION)

    def test_current_binding_is_explicit_and_prior_lessons_are_unchanged(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u4-l6'}
        self.assertEqual(digest(registry.select_policy(binding)), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        plan = {**pinyin_plan(), 'binding': binding, 'pronunciationPolicy': self.policy,
                'pronunciationPolicySha256': POLICY_SHA}
        self.assertEqual(registry.policy_for_plan(plan), self.policy)
        for node in ('u4-l5', 'u4-l7', 'u3-l6'):
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan({**plan, 'binding': {**binding, 'nodeId': node}})
        self.assertEqual(digest(registry.select_policy({**binding, 'nodeId': 'u4-l5'})),
                         '77c1218ebc89639fbcb6360dfa0db0fdb5faccdeb09b3559c4c124a9acc63514')
        self.policy['symbols']['yuǎn']['ph'] = 'wu3'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_seventy_four_tokens_and_original_whole_contrast_readings(self):
        self.assertEqual(set(self.policy['symbols']), set(CONTRASTS + INITIALS + FINALS + WHOLE))
        self.assertEqual(len(self.policy['symbols']), 74)
        for token, expected in zip(CONTRASTS, CONTRAST_PH):
            with self.subTest(token=token):
                root = ElementTree.fromstring(registry.pinyin_ssml(token, policy_version=VERSION))
                self.assertEqual(len(root), 1)
                self.assertEqual(root[0].attrib, {'alphabet': 'py', 'ph': expected})
        self.assertEqual(self.policy['symbols']['yuǎn']['ph'], 'yuan3')
        self.assertEqual(self.policy['symbols']['juǎn']['ph'], 'juan3')

    def test_ascii_entries_are_explicit_not_unicode_normalization(self):
        prior = registry.registered_policy(registry.AIEIUI_V4_POLICY_VERSION)
        self.assertEqual(self.policy['symbols']['ai'], prior['symbols']['ɑi'])
        self.assertEqual(self.policy['symbols']['an'],
                         registry.registered_policy(registry.ANENINUNUN_POLICY_VERSION)['symbols']['ɑn'])
        for token in ('ɑi', 'ɑn', 'ɑng', 'ɑo', 'yuǎn1', 'yuan3', 'juǎnyǎn', 'yīngyīn',
                      'ａｉ', 'AI', 'ai1', 'a\u0304i', 'ng', 'weng', 'men', 'li5', 'luó bo'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.provider_body('请听：' + token + '。', policy_version=VERSION)

    def test_the_only_chinese_override_and_all_approval_boundaries_are_explicit(self):
        self.assertEqual(self.policy['words'], {'谁': {'ph': 'shui2', 'carrier': '谁'}})
        self.assertEqual(registry.pinyin_ssml('谁知盘中餐。', policy_version=VERSION),
                         '<speak><phoneme alphabet="py" ph="shui2">谁</phoneme>知盘中餐。</speak>')
        self.assertEqual(registry.pinyin_ssml('老师陪你读诗。', policy_version=VERSION),
                         '<speak>老师陪你读诗。</speak>')
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'pronunciationApproved', 'formalUseAllowed'):
            self.assertIs(self.policy['approvalBoundary'][field], False)
        self.assertNotIn('exactTextSsml', self.policy)
        self.assertIn('do not establish light-short', self.policy['approvalBoundary']['initialBoundary'])

    def test_four_fixed_probes_cover_every_actual_token_and_word_in_exact_order(self):
        self.assertEqual(dict(initialization._GARDEN4_PROBE_TOKENS), PROBE_TOKENS)
        self.assertEqual(dict(initialization._GARDEN4_PROBE_TEXTS), PROBE_TEXTS)
        targets, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(targets), PROBE_TARGETS)
        self.assertEqual(sum(map(len, PROBE_TOKENS.values())), 75)
        self.assertEqual({t for ts in PROBE_TOKENS.values() for t in ts}, set(self.policy['symbols']) | {'谁'})
        for label, text in PROBE_TEXTS.items():
            root = ElementTree.fromstring(registry.pinyin_ssml(text, policy_version=VERSION))
            expected = [self.policy['symbols'].get(token) or self.policy['words'][token]
                        for token in PROBE_TOKENS[label]]
            self.assertEqual([p.attrib['ph'] for p in root], [e['ph'] for e in expected])
            self.assertEqual([p.text for p in root], [e['carrier'] for e in expected])


class GardenFourInitializationTests(unittest.TestCase):
    def setUp(self):
        # Registry-backed production files are irrelevant to these isolated fixtures.
        self.enterContext(patch.dict(os.environ, {'COURSE_STORAGE_MODE': 'local'}))
        fx = self.fx = fixtures.PronunciationInitializationTests()
        fx.node_id, fx.probe_targets = 'u4-l6', PROBE_TARGETS
        fx.probe_token_sequences, fx.probe_source_texts = PROBE_TOKENS, PROBE_TEXTS
        fx.approval_result = 'four_garden4_fixed_probes_inventory_and_source_context_approved'
        fx.approval_statement = 'Synthetic fixture: no provider call or human listening.'
        fx.first_speech = PROBE_TEXTS['near-contrast-and-poem-context']
        fx.setUp(); self.addCleanup(fx.doCleanups)
        at = now_ms(); frozen = json.loads(fx.row['input_json'])
        auth = seal({'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message',
            'statement': 'SYNTHETIC automatic-check authorization, never a real listening verdict.',
            'recordedAt': at - 1000, 'scope': {k: frozen[k] for k in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True,
            'individualListeningConfirmationRequired': False})
        self.review = {k: deepcopy(fx.approval[k]) for k in ('previewKey', 'sourceSha256',
            'pronunciationPolicyVersion', 'pronunciationPolicySha256', 'formalUseAllowed', 'probePlanSha256')}
        self.review.update(schemaVersion=initialization.OPERATOR_REVIEW_SCHEMA,
            method=initialization.OPERATOR_METHOD, coreSha256=fx.patch['expectedCoreSha256'],
            reviewer='Synthetic operator', recordedAt=at, authorization=auth,
            result=initialization.OPERATOR_RESULT, humanListeningVerified=False, perceptualToneVerified=False,
            evidenceLimit=initialization.OPERATOR_EVIDENCE_LIMIT,
            samples=[{**s, 'result': initialization.OPERATOR_RESULT} for s in fx.approval['samples']])
        fx.patch = {k: v for k, v in fx.patch.items() if k != 'approvedProbeEvidence'}
        fx.patch.update(schemaVersion=initialization.OPERATOR_SCHEMA,
            basis='Exact current-lesson protocol/WAV only; audible initials and bare finals remain unverified.',
            verifiedProbeEvidence={'path': str(fx.probes / 'operator-probe-review.json'), 'sha256': ''})
        self.write_review()

    def write_review(self):
        raw = canonical(seal(self.review)).encode()
        (self.fx.probes / 'operator-probe-review.json').write_bytes(raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def test_atomic_activation_keeps_originals_and_never_dispatches_audio_or_publication(self):
        fx = self.fx
        source = (fx.f.root / (fx.f.cid + '.json')).read_bytes()
        result = fx.run_initialization()
        plan = json.loads((fx.f.folder / 'plan.json').read_text())
        self.assertEqual(plan['pronunciationPolicy']['policyVersion'], VERSION)
        self.assertEqual(plan['pronunciationPolicySha256'], POLICY_SHA)
        self.assertEqual((fx.f.root / (fx.f.cid + '.json')).read_bytes(), source)
        self.assertEqual(fx.f.service.get(fx.f.key), fx.row)
        self.assertFalse(result['publicationAllowed'])
        self.assertFalse(result['generationDispatched'])
        self.assertEqual(fx.run_initialization(), result)
        fx.assert_no_external_write()

    def test_missing_replayed_or_false_listening_probe_evidence_cannot_activate(self):
        before = deepcopy(self.review)
        for change in ({'samples': before['samples'][:-1]},
                       {'pronunciationPolicyVersion': registry.ANGENGINGONG_POLICY_VERSION},
                       {'humanListeningVerified': True}, {'perceptualToneVerified': True}):
            with self.subTest(change=list(change)):
                self.review = {**deepcopy(before), **change}; self.write_review()
                with self.assertRaises(ApiError): self.fx.run_initialization()
        self.assertFalse((self.fx.f.folder / 'plan.json').exists())
        self.fx.assert_no_external_write()

    def test_fresh_lesson_cannot_use_default_audio_before_the_probe_gate(self):
        with self.assertRaises(ApiError) as caught:
            narrate_preview(self.fx.f.service, self.fx.f.key, self.fx.f.root)
        self.assertEqual(caught.exception.code, 'textbook_preview_pronunciation_initialization_required')
        self.fx.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
