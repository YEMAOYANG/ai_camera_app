"""GKH whole-token recipes and exact six-probe evidence, with no real audio calls."""
from copy import deepcopy
import json
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_visual_revision import sha_bytes
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan, sign
from tests import test_textbook_preview_pronunciation_initialization as initialization_fixtures


VERSION = 'mira.textbook.pinyin-gkh-ssml.v1'
POLICY_SHA = 'c007c1ba8cbfab2b565a432de8f3e379290839dbe3f10df678e2b3c4757b382c'
TOKENS = [
    ('g', 'ge1', '哥'), ('k', 'ke1', '科'), ('h', 'he1', '喝'),
    ('gā', 'ga1', '嘎'), ('gè', 'ge4', '个'), ('gù', 'gu4', '固'),
    ('kǎ', 'ka3', '卡'), ('kē', 'ke1', '科'), ('kǔ', 'ku3', '苦'),
    ('hā', 'ha1', '哈'), ('hē', 'he1', '喝'), ('hǔ', 'hu3', '虎'),
    ('guā', 'gua1', '瓜'), ('guà', 'gua4', '挂'), ('kuā', 'kua1', '夸'),
    ('huá', 'hua2', '滑'), ('guō', 'guo1', '锅'), ('kuò', 'kuo4', '阔'), ('huǒ', 'huo3', '火'),
    ('u', 'wu1', '乌'), ('ā', 'a1', '啊'), ('ò', 'o4', '哦'), ('ǒ', 'o3', '哦'),
]
PROBE_TOKENS = {
    'g-call-short-context': ('g', 'g'), 'k-call-short-context': ('k', 'k'),
    'h-call-short-context': ('h', 'h'), 'gua1-three-part': ('g', 'u', 'ā', 'guā'),
    'kuo4-three-part': ('k', 'u', 'ò', 'kuò'), 'huo3-three-part': ('h', 'u', 'ǒ', 'huǒ'),
}
PRIOR_HASHES = {
    registry.AOE_POLICY_VERSION: 'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7',
    registry.IUU_POLICY_VERSION: '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb',
    registry.BPMF_POLICY_VERSION: '0db25c66499d66ddf8569e6c621d74fc63e344ff3436cfd7908e78e5509a84de',
    registry.DTNL_POLICY_VERSION: '20e7b95f0c368e54f2ca219643381d8fec6244ede8d44c7f106a47c7c4a4a709',
    registry.GARDEN2_POLICY_VERSION: '36c5b794c1e80ff0d6491e83e983d60915229c3f4275d5c69f7ad842588ad72b',
}


def gkh_plan():
    plan = pinyin_plan()
    plan['binding']['nodeId'] = 'u3-l1'
    plan['pronunciationPolicy'] = registry.registered_policy(VERSION)
    plan['pronunciationPolicySha256'] = POLICY_SHA
    return plan


class GkhPronunciationTests(unittest.TestCase):
    def test_exact_lesson_binding_preserves_old_policies_and_pending_listening(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u3-l1'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        self.assertEqual(registry.policy_for_plan(gkh_plan()), policy)
        self.assertTrue(policy['listeningRequired'])
        self.assertEqual(policy['approvalBoundary']['humanReview'], 'pending')
        for flag in ('formalUseAllowed', 'pronunciationApproved', 'shortConsonantAccepted'):
            self.assertFalse(policy['approvalBoundary'][flag])
        for field in registry._BINDING_FIELDS:
            wrong = {**binding, field: binding[field] + '-other'}
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy(wrong)
            self.assertFalse(registry.initialization_required(wrong))
        for version, expected in PRIOR_HASHES.items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            wrong = gkh_plan()
            wrong['pronunciationPolicy'] = registry.registered_policy(version)
            wrong['pronunciationPolicySha256'] = expected
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        for node in ('u2-l1', 'u2-l2', 'u2-l3', 'u2-l4', 'u2-l5', 'u3-l2'):
            wrong = gkh_plan()
            wrong['binding']['nodeId'] = node
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        policy['symbols']['g']['ph'] = 'ga1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_23_tokens_keep_whole_syllables_and_natural_chinese(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {token for token, _, _ in TOKENS})
        self.assertEqual(policy['words'], {})
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                encoded = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(encoded, f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                self.assertEqual(len(ElementTree.fromstring(encoded).findall('phoneme')), 1)
        chinese = '哥哥、弟弟、画画、荷花；哥、弟、画、花。'
        self.assertEqual(registry.pinyin_ssml(chinese, policy_version=VERSION), '<speak>' + chinese + '</speak>')
        self.assertEqual(registry.pronunciation_symbols(chinese, policy_version=VERSION), [])
        for label, tokens in PROBE_TOKENS.items():
            encoded = registry.pinyin_ssml('请听：' + '，'.join(tokens) + '。', policy_version=VERSION)
            phonemes = ElementTree.fromstring(encoded).findall('phoneme')
            self.assertEqual([p.attrib['ph'] for p in phonemes], [policy['symbols'][t]['ph'] for t in tokens], label)

    def test_unknown_whole_tokens_are_not_split_or_normalized(self):
        for token in ('gua', 'gua1', 'guāguà', 'gu', 'kǒ', 'a', 'ɑ', 'i', 'ü', 'gē',
                      'āh', 'a\u0304', 'G', 'ｇ', '𝒈', 'constructor', 'g\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
        self.assertEqual(registry.pinyin_ssml('😀<&>"\'guā。', policy_version=VERSION),
            '<speak>😀&lt;&amp;&gt;&quot;&apos;<phoneme alphabet="py" ph="gua1">瓜</phoneme>。</speak>')

    def test_python_native_golden_body_vector_and_cross_policy_receipts(self):
        text = '请听：' + '，'.join(t for t, _, _ in TOKENS) + '。哥哥、弟弟、画画、荷花。'
        receipt = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(receipt['ssmlSha256'], '922b17c64a74da17ec9987e16cdf7ab79ca3b737dedba5a046e78bcdc1ad6bbd')
        self.assertEqual(receipt['providerBodySha256'], '58b01872eb555e2dca92f38020c68f6dacd50fb24785c152634a27e2441405f9')
        self.assertEqual(registry.registered_policy(VERSION)['inputParameters'], registry.registered_policy()['inputParameters'])
        for version in PRIOR_HASHES:
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation(receipt, policy_version=version)

    def test_six_probe_approval_cannot_replace_exact_formal_sentence_listening(self):
        # Synthetic contexts include repeated tokens with distinct action/audio identities.
        texts = ['请听完整音节：' + token + '。' for token, _, _ in TOKENS[3:19]]
        texts += ['请轻短地读：g。', '先听：g、u、ā。再听：guā。', '再听完整音节：guā。']
        plan = gkh_plan()
        actions = [{'id': str(i), 'type': 'speech', 'text': text, 'audioId': 'tbptts1_' + f'{i:064x}'}
                   for i, text in enumerate(texts)]
        classroom = {'scenes': [{'id': 's', 'actions': actions}]}
        review = sign({'schemaVersion': registry.LISTENING_SCHEMA, 'previewKey': plan['previewKey'],
            'planSha256': digest(plan), 'coreSha256': plan['coreSha256'], 'segments': [
                {'sceneId': 's', 'actionId': a['id'], 'textSha256': registry.sha_text(a['text']),
                 'ttsRequestId': a['audioId'], 'audioSha256': 'f' * 64, 'verdict': 'accepted',
                 'reviewer': 'fixture-human', 'reviewedAt': 1, 'basis': 'synthetic exact formal sentence'} for a in actions]})
        self.assertEqual(len(registry.validate_listening_review(plan, classroom, review, now_ms=2)), len(texts))
        for index in range(len(texts)):
            missing = deepcopy(review)
            missing['segments'].pop(index)
            with self.subTest(missing=index), self.assertRaises(ApiError):
                registry.validate_listening_review(plan, classroom, sign(missing), now_ms=2)
        six = deepcopy(review)
        six['segments'] = six['segments'][:6]
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, classroom, sign(six), now_ms=2)


class GkhPronunciationInitializationTests(initialization_fixtures.PronunciationInitializationTests):
    """All evidence and audio here are synthetic test fixtures, never human approval."""
    node_id = 'u3-l1'
    probe_targets = {label: tokens[-1] for label, tokens in PROBE_TOKENS.items()}
    probe_token_sequences = PROBE_TOKENS
    approval_result = 'six_gkh_call_context_and_three_part_probes_pronunciation_and_tones_approved'
    approval_statement = '测试夹具：六段小样准确；正式整句与轻短效果尚待另行听验'
    first_speech = '先听：g、u、ā。连起来听：guā。'

    def test_every_probe_is_required_and_approval_does_not_mark_formal_listening(self):
        original = deepcopy(self.approval)
        for index in range(6):
            self.approval = deepcopy(original)
            self.approval['samples'].pop(index)
            self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError):
                self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()

    def _evidence_with_ssml(self, label, ssml):
        """Rebind every dependent hash, so rejection tests the recipe, not stale hashes."""
        files = initialization._evidence_files(self.patch, self.policy)
        plan = json.loads(files['evidence/plan.json'])
        approval = json.loads(files['evidence/human-approval.json'])
        original = next(p for p in plan['samples'] if p['label'] == label)
        request = original['body']
        request['input']['text'] = ssml
        raw = canonical(request).encode()
        files[f'evidence/{label}/request.json'] = raw
        original.update(requestSha256=sha_bytes(raw), ssmlSha256=sha_bytes(ssml.encode()))
        plan_raw = canonical(plan).encode()
        files['evidence/plan.json'] = plan_raw
        approval['probePlanSha256'] = sha_bytes(plan_raw)
        for sample in approval['samples']:
            current = sample['label']
            for name in ('intent.json', 'receipt.json'):
                path = f'evidence/{current}/{name}'
                data = json.loads(files[path])
                data['planSha256'] = sha_bytes(plan_raw)
                if current == label:
                    data['requestSha256'] = sha_bytes(raw)
                    sample['requestSha256'] = sha_bytes(raw)
                files[path] = canonical(data).encode()
        files['evidence/human-approval.json'] = canonical(approval).encode()
        patch = deepcopy(self.patch)
        patch['approvedProbeEvidence']['sha256'] = sha_bytes(files['evidence/human-approval.json'])
        return files, patch

    def test_three_part_probe_rejects_missing_reordered_tone_carrier_and_extra_phonemes(self):
        label = 'gua1-three-part'
        original = self.plan['samples'][3]['body']['input']['text']
        nodes = ElementTree.fromstring(original).findall('phoneme')
        raw_nodes = [ElementTree.tostring(p, encoding='unicode') for p in nodes]
        variants = [
            ''.join(raw_nodes[:1] + raw_nodes[2:]),
            ''.join([raw_nodes[1], raw_nodes[0], *raw_nodes[2:]]),
            ''.join(raw_nodes).replace('ph="gua1"', 'ph="gua4"'),
            ''.join(raw_nodes).replace('>瓜<', '>挂<'),
            raw_nodes[-1] * 2,
            ''.join(raw_nodes + [raw_nodes[-1]]),
        ]
        for variant in variants:
            files, patch = self._evidence_with_ssml(label, '<speak>听音。' + variant + '</speak>')
            with self.subTest(variant=variant), self.assertRaisesRegex(ApiError, '音素顺序'):
                initialization._verify_evidence(files, patch, self.f.key,
                    json.loads(self.row['input_json']), self.policy)
        self.assert_no_external_write()

    def test_call_name_probes_still_require_exactly_two_registered_sounds(self):
        original = self.plan['samples'][0]['body']['input']['text']
        nodes = ElementTree.fromstring(original).findall('phoneme')
        single = ElementTree.tostring(nodes[0], encoding='unicode')
        files, patch = self._evidence_with_ssml('g-call-short-context', '<speak>' + single + '</speak>')
        with self.assertRaisesRegex(ApiError, '音素顺序'):
            initialization._verify_evidence(files, patch, self.f.key,
                json.loads(self.row['input_json']), self.policy)
        self.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
