"""ZHCHSHR exact recipes and isolated evidence checks; never real audio approval."""
from copy import deepcopy
import json
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_visual_revision import sha_bytes
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan
from tests import test_textbook_pinyin_gkh as gkh_fixtures
from tests import test_textbook_pinyin_zcs as zcs_fixtures
from tests import test_textbook_preview_pronunciation_initialization as fixtures

VERSION = 'mira.textbook.pinyin-zhchshr-ssml.v1'
POLICY_SHA = 'e4faadb5854f3813b1ea94a20aee7ff4496dc6f2ac9b889686555d4405c8b800'
TOKENS = [
    ('zh', 'zhi1', '知'), ('ch', 'chi1', '吃'), ('sh', 'shi1', '诗'), ('r', 'ri1', '日'),
    ('zhi', 'zhi1', '知'), ('chi', 'chi1', '吃'), ('shi', 'shi1', '诗'), ('ri', 'ri1', '日'),
    ('zhí', 'zhi2', '直'), ('chī', 'chi1', '吃'), ('shī', 'shi1', '诗'), ('rì', 'ri4', '日'),
    ('zhā', 'zha1', '扎'), ('zhè', 'zhe4', '这'), ('zhù', 'zhu4', '住'),
    ('zhuǎ', 'zhua3', '爪'), ('zhuō', 'zhuo1', '桌'),
    ('chá', 'cha2', '茶'), ('chē', 'che1', '车'), ('chū', 'chu1', '出'), ('chuō', 'chuo1', '戳'),
    ('shà', 'sha4', '煞'), ('shé', 'she2', '蛇'), ('shǔ', 'shu3', '鼠'),
    ('shuā', 'shua1', '刷'), ('shuō', 'shuo1', '说'),
    ('rè', 're4', '热'), ('rǔ', 'ru3', '乳'), ('ruò', 'ruo4', '若'),
    ('u', 'wu1', '乌'), ('à', 'a4', '啊'), ('á', 'a2', '啊'), ('è', 'e4', '鹅'),
    ('é', 'e2', '鹅'), ('ò', 'o4', '哦'), ('ù', 'wu4', '乌'), ('ā', 'a1', '啊'),
    ('ē', 'e1', '鹅'), ('ō', 'o1', '哦'), ('ū', 'wu1', '乌'), ('ǎ', 'a3', '啊'), ('ǔ', 'wu3', '乌'),
]
PROBE_TOKENS = {
    'zh-call-and-blending-context': ('zh', 'zhā'), 'ch-call-and-blending-context': ('ch', 'chá'),
    'sh-call-and-blending-context': ('sh', 'shà'), 'r-call-and-blending-context': ('r', 'rè'),
    'zhi-whole-and-tone': ('zhi', 'zhí'), 'chi-whole-and-tone': ('chi', 'chī'),
    'shi-whole-and-tone': ('shi', 'shī'), 'ri-whole-and-tone': ('ri', 'rì'),
}
PRIOR_HASHES = {
    'mira.textbook.pinyin-aoe-ssml.v1': 'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7',
    'mira.textbook.pinyin-iuu-ssml.v1': '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb',
    'mira.textbook.pinyin-bpmf-ssml.v1': '0db25c66499d66ddf8569e6c621d74fc63e344ff3436cfd7908e78e5509a84de',
    'mira.textbook.pinyin-dtnl-ssml.v1': '20e7b95f0c368e54f2ca219643381d8fec6244ede8d44c7f106a47c7c4a4a709',
    'mira.textbook.pinyin-garden2-ssml.v1': '36c5b794c1e80ff0d6491e83e983d60915229c3f4275d5c69f7ad842588ad72b',
    'mira.textbook.pinyin-gkh-ssml.v1': 'c007c1ba8cbfab2b565a432de8f3e379290839dbe3f10df678e2b3c4757b382c',
    'mira.textbook.pinyin-jqx-ssml.v1': '0f1957af0ce218d3f0323c79886f199a80210d2e1c49a7b68f6dc70071d6366b',
    'mira.textbook.pinyin-zcs-ssml.v1': '5d311c9a903e00c9f819ec404af571bf21ef9a9caed229109ec7e2768e73815a',
    'mira.textbook.pinyin-zcs-ssml.v2': 'aa4ccf02d781fcbec0212f469abdfc035f610de1c5ef56ce8688c7fa8683017c',
}

class ZhchshrPronunciationTests(unittest.TestCase):
    def test_exact_binding_prior_hashes_and_detached_policy(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u3-l4'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        plan = pinyin_plan()
        plan.update(binding=binding, pronunciationPolicy=policy, pronunciationPolicySha256=POLICY_SHA)
        self.assertEqual(registry.policy_for_plan(plan), policy)
        for field in registry._BINDING_FIELDS:
            wrong = {**binding, field: binding[field] + '-other'}
            with self.subTest(field=field), self.assertRaises(ApiError): registry.select_policy(wrong)
            self.assertFalse(registry.initialization_required(wrong))
        for version, expected in PRIOR_HASHES.items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            wrong = {**plan, 'pronunciationPolicy': registry.registered_policy(version), 'pronunciationPolicySha256': expected}
            with self.subTest(version=version), self.assertRaises(ApiError): registry.policy_for_plan(wrong)
        policy['symbols']['r']['ph'] = 'wrong'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_42_whole_tokens_and_natural_chinese(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {t for t, _, _ in TOKENS})
        self.assertEqual(policy['words'], {})
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                ssml = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(ssml, f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                self.assertEqual(len(ElementTree.fromstring(ssml).findall('phoneme')), 1)
        chinese = '桌子、擦桌子、折纸、读书、四、十、十四、四十。'
        self.assertEqual(registry.pinyin_ssml(chinese, policy_version=VERSION), '<speak>' + chinese + '</speak>')
        self.assertEqual(policy['inputParameters'], registry.registered_policy()['inputParameters'])
        for key in ('formalUseAllowed', 'pronunciationApproved', 'humanListeningVerified', 'perceptualToneVerified', 'shortConsonantAccepted'):
            self.assertFalse(policy['approvalBoundary'][key])

    def test_unknown_complete_tokens_cannot_fall_back_to_letters(self):
        for token in ('r1', 'R', 'zhr', 'shā', 'rú', 'hello', 'r\u030c', 'zhch', 'zhi1', 'i', 'yī', 'constructor', 'ｒ', '𝒓', 'r\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)

    def test_body_golden_and_wrong_receipt_identity(self):
        text = '请听：' + '，'.join(sorted(t for t, _, _ in TOKENS)) + '。桌子、擦桌子、折纸、读书、四、十、十四、四十。'
        receipt = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(receipt['ssmlSha256'], '6eda2cb6ab2394a30f7b34617be79772d425c13dfcfb1232c6c28ae63c25e4a1')
        self.assertEqual(receipt['providerBodySha256'], '3ff12b776b884c45bfb23b28b69620edb28cf7cad69896692b1c2b182f932b6e')
        for field, value in [('policySha256', '0'*64), ('voiceId', 'Serena'), ('providerBodySha256', 'f'*64)]:
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation({**receipt, field: value}, text, policy_version=VERSION)

class ZhchshrInitializationTests(fixtures.PronunciationInitializationTests):
    node_id = 'u3-l4'
    probe_targets = {label: pair[0] for label, pair in PROBE_TOKENS.items()}
    probe_token_sequences = PROBE_TOKENS
    approval_result = 'eight_zhchshr_call_context_and_whole_recognition_probes_pronunciation_and_tones_approved'
    approval_statement = 'SYNTHETIC fixture only; no real ZHCHSHR pronunciation or listening verdict.'
    first_speech = '先听声母：zh。再听整体认读音节：zhí。桌子保持自然中文。'
    _evidence_with_ssml = gkh_fixtures.GkhPronunciationInitializationTests._evidence_with_ssml
    test_operator_v2_keeps_formal_review_pending = zcs_fixtures.ZcsInitializationTests.test_operator_v2_does_not_turn_probe_protocol_into_human_or_formal_approval

    def test_fixed_eight_labels_and_sequences(self):
        actual, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(actual), self.probe_targets)
        self.assertEqual(dict(initialization._ZHCHSHR_PROBE_TOKENS), PROBE_TOKENS)
        original = deepcopy(self.approval)
        for index in range(8):
            self.approval = deepcopy(original); self.approval['samples'].pop(index); self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError): self.run_initialization()
        self.assert_no_external_write()

    def test_forged_recipe_rejected_after_rebinding_every_hash(self):
        for label in PROBE_TOKENS:
            original = next(s for s in self.plan['samples'] if s['label'] == label)['body']['input']['text']
            nodes = ElementTree.fromstring(original).findall('phoneme')
            parts = [ElementTree.tostring(p, encoding='unicode') for p in nodes]
            # chi/chī and shi/shī intentionally have identical acoustic recipes;
            # reversing identical XML cannot establish a detectable wrong order.
            variants = [('missing', parts[0]), ('extra', ''.join(parts + parts[:1])),
                        ('empty-carrier', ''.join(parts).replace('>' + nodes[0].text + '<', '><', 1)),
                        ('wrong-tone', ''.join(parts).replace(nodes[-1].attrib['ph'], 'yi1'))]
            if parts[0] != parts[1]: variants.append(('reversed', ''.join(reversed(parts))))
            for name, body in variants:
                files, patch = self._evidence_with_ssml(label, '<speak>听音。' + body + '</speak>')
                # Untrusted token metadata must not override the fixed server sequence.
                with self.subTest(label=label, variant=name), self.assertRaisesRegex(ApiError, '音素顺序'):
                    initialization._verify_evidence(files, patch, self.f.key, json.loads(self.row['input_json']), self.policy)
        self.assert_no_external_write()

if __name__ == '__main__':
    unittest.main()
