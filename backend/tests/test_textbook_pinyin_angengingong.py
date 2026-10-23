"""Finite back-nasal recipes and protocol initialization; no provider calls."""
from copy import deepcopy
import json
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_operator_review import AUTHORIZATION_SCHEMA
from core.errors import ApiError
from core.security import now_ms
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization as fixtures
from tests.test_textbook_pinyin_aneninunun import POLICY_SHA as FRONT_NASAL_SHA
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan


VERSION = 'mira.textbook.pinyin-angengingong-ssml.v1'
POLICY_SHA = '77c1218ebc89639fbcb6360dfa0db0fdb5faccdeb09b3559c4c124a9acc63514'
# Source-derived inventory, not expanded tone rows or Cartesian combinations.
RECIPES = {
    'ɑng': 'ang1', 'eng': 'eng1', 'ing': 'ying1', 'ong': 'ong1', 'ying': 'ying1',
    'bāng': 'bang1', 'huáng': 'huang2', 'qiáng': 'qiang2', 'chuāng': 'chuang1',
    'rēng': 'reng1', 'héng': 'heng2', 'fēng': 'feng1', 'dēng': 'deng1',
    'jǐng': 'jing3', 'bǐng': 'bing3', 'tīng': 'ting1', 'qīng': 'qing1',
    'hǒng': 'hong3', 'zhōng': 'zhong1', 'sòng': 'song4', 'qióng': 'qiong2',
    'míng': 'ming2', 'liàng': 'liang4', 'bīng': 'bing1', 'zì': 'zi4',
    'xíng': 'xing2', 'chē': 'che1',
}
PROBE_TEXTS = {
    'finals-whole-bases': '请听：ɑng、eng、ing、ong。ying。',
    'printed-syllables-context': (
        '请听：bāng、huáng、qiáng、chuāng；rēng、héng、fēng、dēng；'
        'jǐng、bǐng、tīng、qīng；hǒng、zhōng、sòng、qióng。'),
    'writing-recognition-context': '请听：míng liàng。bīng、zì、xíng、chē。',
}
PROBE_TOKENS = {
    'finals-whole-bases': ('ɑng', 'eng', 'ing', 'ong', 'ying'),
    'printed-syllables-context': (
        'bāng', 'huáng', 'qiáng', 'chuāng', 'rēng', 'héng', 'fēng', 'dēng',
        'jǐng', 'bǐng', 'tīng', 'qīng', 'hǒng', 'zhōng', 'sòng', 'qióng'),
    'writing-recognition-context': ('míng', 'liàng', 'bīng', 'zì', 'xíng', 'chē'),
}
PROBE_TARGETS = {label: tokens[0] for label, tokens in PROBE_TOKENS.items()}


def seal(value):
    value['sha256'] = digest({key: item for key, item in value.items() if key != 'sha256'})
    return value


class AngEngIngOngPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = registry.registered_policy(VERSION)

    def test_lesson_identity_initialization_gate_and_no_cross_lesson_reuse(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u4-l5'}
        self.assertEqual(digest(registry.select_policy(binding)), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        plan = {**pinyin_plan(), 'binding': binding, 'pronunciationPolicy': self.policy,
                'pronunciationPolicySha256': POLICY_SHA}
        self.assertEqual(registry.policy_for_plan(plan), self.policy)
        for field in registry._BINDING_FIELDS:
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy({**binding, field: binding[field] + '-other'})
        for node in ('u4-l4', 'u4-l6'):
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan({**plan, 'binding': {**binding, 'nodeId': node}})
        previous = registry.registered_policy(registry.ANENINUNUN_POLICY_VERSION)
        self.assertEqual(digest(previous), FRONT_NASAL_SHA)
        self.assertEqual(registry.select_policy({**binding, 'nodeId': 'u4-l4'}), previous)
        with self.assertRaises(ApiError):
            registry.policy_for_plan({**plan, 'pronunciationPolicy': previous,
                                      'pronunciationPolicySha256': digest(previous)})
        self.policy['symbols']['ong']['ph'] = 'weng1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_inventory_body_and_unverified_boundaries(self):
        self.assertEqual(len(RECIPES), 27)
        self.assertEqual(set(self.policy['symbols']), set(RECIPES))
        for token, ph in RECIPES.items():
            with self.subTest(token=token):
                root = ElementTree.fromstring(registry.pinyin_ssml(token, policy_version=VERSION))
                self.assertEqual(len(root), 1)
                self.assertEqual(root[0].attrib, {'alphabet': 'py', 'ph': ph})
                self.assertEqual(root[0].text, self.policy['symbols'][token]['carrier'])
        old = registry.registered_policy(registry.ANENINUNUN_POLICY_VERSION)
        for field in ('providerId', 'modelId', 'voiceId', 'endpointPath', 'inputParameters', 'textHandling'):
            self.assertEqual(self.policy[field], old[field])
        for old_version, token in ((registry.ZHCHSHR_POLICY_VERSION, 'chē'),
                                   (registry.GARDEN3_V2_POLICY_VERSION, 'zì')):
            self.assertEqual(self.policy['symbols'][token], registry.registered_policy(old_version)['symbols'][token])
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'pronunciationApproved', 'formalUseAllowed'):
            self.assertIs(self.policy['approvalBoundary'][field], False)
        self.assertIn('no existing registered policy or real protocol/audio evidence',
                      self.policy['approvalBoundary']['unverifiedBareFinalBoundary'])
        self.assertEqual(self.policy['words'], {})
        self.assertNotIn('exactTextSsml', self.policy)

    def test_unknown_aliases_components_and_unplanned_tones_fail_closed(self):
        for token in ('ang', 'āng', 'áng', 'ǎng', 'àng', 'ɑng1', 'eng1', 'éng', 'ǒng',
                      'ong1', 'weng', 'hong', 'yīng', 'ying1', 'ɑngeng', 'bāngqīng',
                      'a', 'ɑ', 'e', 'i', 'o', 'n', 'ng', 'g', 'y', 'u', 'ü',
                      'men', 'liǎng', 'yáng', 'dōng', 'shàng', 'ràng', 'tōng', 'yāng',
                      'ANG', 'ａｎｇ', 'a\u0304ng', 'i\u0304ng', '坏\x00字符'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.provider_body('请听：' + token + '。', policy_version=VERSION)
        with self.assertRaises(ApiError):
            registry.provider_body('请听：ong。', policy_version=registry.ANENINUNUN_POLICY_VERSION)

    def test_natural_chinese_and_exact_request_identity_are_preserved(self):
        text = '游泳、滑冰、骑自行车、打乒乓球。这里是自行车的行。'
        self.assertEqual(registry.pinyin_ssml(text, policy_version=VERSION), '<speak>' + text + '</speak>')
        self.assertEqual(registry.pinyin_ssml('看<&>：ong。', policy_version=VERSION),
                         '<speak>看&lt;&amp;&gt;：<phoneme alphabet="py" ph="ong1">嗡</phoneme>。</speak>')
        receipt = registry.provider_pronunciation('请听：míng liàng。', policy_version=VERSION)
        registry.validate_provider_pronunciation(receipt, '请听：míng liàng。', policy_version=VERSION)
        with self.assertRaises(ApiError):
            registry.validate_provider_pronunciation(receipt, '请听：míng。', policy_version=VERSION)

    def test_fixed_three_probe_sources_cover_only_actual_inventory_in_order(self):
        self.assertEqual(dict(initialization._ANGENGINGONG_PROBE_TEXTS), PROBE_TEXTS)
        self.assertEqual(dict(initialization._ANGENGINGONG_PROBE_TOKENS), PROBE_TOKENS)
        probes, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(probes), PROBE_TARGETS)
        self.assertEqual(sum(map(len, PROBE_TOKENS.values())), 27)
        self.assertEqual({t for tokens in PROBE_TOKENS.values() for t in tokens}, set(RECIPES))
        for label, text in PROBE_TEXTS.items():
            root = ElementTree.fromstring(registry.pinyin_ssml(text, policy_version=VERSION))
            self.assertEqual([p.attrib['ph'] for p in root], [RECIPES[t] for t in PROBE_TOKENS[label]])


class AngEngIngOngAutomaticInitializationTests(unittest.TestCase):
    def setUp(self):
        fx = self.fx = fixtures.PronunciationInitializationTests()
        fx.node_id, fx.probe_targets = 'u4-l5', PROBE_TARGETS
        fx.probe_token_sequences, fx.probe_source_texts = PROBE_TOKENS, PROBE_TEXTS
        fx.approval_result = 'three_angengingong_fixed_probes_pronunciation_and_source_context_approved'
        fx.approval_statement = 'Synthetic fixture; no provider call or listening verdict.'
        fx.first_speech = PROBE_TEXTS['finals-whole-bases']
        fx.setUp(); self.addCleanup(fx.doCleanups)
        timestamp = now_ms(); frozen = json.loads(fx.row['input_json'])
        auth = seal({'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message',
            'statement': 'SYNTHETIC automatic checks and publication authorization, not listening.',
            'recordedAt': timestamp - 1000,
            'scope': {k: frozen[k] for k in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True,
            'individualListeningConfirmationRequired': False})
        self.review = {k: deepcopy(fx.approval[k]) for k in ('previewKey', 'sourceSha256',
            'pronunciationPolicyVersion', 'pronunciationPolicySha256', 'formalUseAllowed', 'probePlanSha256')}
        self.review.update(schemaVersion=initialization.OPERATOR_REVIEW_SCHEMA,
            method=initialization.OPERATOR_METHOD, coreSha256=fx.patch['expectedCoreSha256'],
            reviewer='Synthetic operator', recordedAt=timestamp, authorization=auth,
            result=initialization.OPERATOR_RESULT, humanListeningVerified=False, perceptualToneVerified=False,
            evidenceLimit=initialization.OPERATOR_EVIDENCE_LIMIT,
            samples=[{**s, 'result': initialization.OPERATOR_RESULT} for s in fx.approval['samples']])
        fx.patch = {k: v for k, v in fx.patch.items() if k != 'approvedProbeEvidence'}
        fx.patch.update(schemaVersion=initialization.OPERATOR_SCHEMA,
            basis='Synthetic protocol and unchanged PCM only; bare eng/ong audible accuracy remains unverified.',
            verifiedProbeEvidence={'path': str(fx.probes / 'operator-probe-review.json'), 'sha256': ''})
        self.write_review()

    def write_review(self):
        seal(self.review); raw = canonical(self.review).encode()
        (self.fx.probes / 'operator-probe-review.json').write_bytes(raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def test_prepare_activate_and_resume_preserve_source_and_no_audio_or_human_claims(self):
        fx = self.fx; source = (fx.f.root / (fx.f.cid + '.json')).read_bytes()
        evidence = {p: p.read_bytes() for p in fx.probes.rglob('*') if p.is_file()}
        self.assertTrue(fx.run_initialization(False)['prepared'])
        self.assertFalse((fx.f.folder / 'plan.json').exists())
        result = fx.run_initialization()
        for field in ('generationDispatched', 'publicationAllowed', 'requiresFormalHumanListening',
                      'humanListeningVerified', 'perceptualToneVerified'):
            self.assertIs(result[field], False)
        self.assertTrue(result['requiresFormalOperatorReview'])
        self.assertEqual(registry.policy_for_plan(json.loads((fx.f.folder / 'plan.json').read_text()))['policyVersion'], VERSION)
        self.assertEqual(fx.run_initialization(), result)
        self.assertEqual(fx.f.service.get(fx.f.key), fx.row)
        self.assertEqual((fx.f.root / (fx.f.cid + '.json')).read_bytes(), source)
        for path, raw in evidence.items(): self.assertEqual(path.read_bytes(), raw)
        fx.assert_no_external_write()

    def test_uninitialized_default_voice_is_stopped_before_any_provider_access(self):
        self.fx.test_default_and_injected_v2_narration_stop_before_any_tts_get_or_post()

    def test_resigned_source_or_token_sequence_cannot_change_protocol(self):
        fx = self.fx; original = initialization._evidence_files(fx.patch, fx.policy)
        probes, _ = initialization._probe_contract(fx.policy)
        for mutation in ('source', 'tokens'):
            files = deepcopy(original); plan = json.loads(files['evidence/plan.json'])
            review = json.loads(files['evidence/operator-probe-review.json'])
            if mutation == 'source': plan['samples'][1]['sourceText'] = '请听：bāng。'
            else: plan['samples'][0]['tokens'][1:3] = reversed(plan['samples'][0]['tokens'][1:3])
            files['evidence/plan.json'] = canonical(plan).encode()
            review['probePlanSha256'] = sha_bytes(files['evidence/plan.json'])
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                initialization._verify_probe_files(files, review, json.loads(fx.row['input_json']),
                    fx.policy, probes, sample_result=initialization.OPERATOR_RESULT)
        fx.assert_no_external_write()

    def test_human_claims_missing_probe_and_changed_pcm_cannot_install(self):
        original = deepcopy(self.review)
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'formalUseAllowed'):
            self.review = {**deepcopy(original), field: True}; self.write_review()
            with self.subTest(field=field), self.assertRaises(ApiError): self.fx.run_initialization()
        self.review = deepcopy(original); self.review['samples'].pop(); self.write_review()
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.review = deepcopy(original); self.write_review()
        wav = self.fx.probes / 'finals-whole-bases' / 'playback.wav'
        wav.write_bytes(wav.read_bytes() + b'changed')
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.assertFalse((self.fx.f.folder / 'plan.json').exists()); self.fx.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
