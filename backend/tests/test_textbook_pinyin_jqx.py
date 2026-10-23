"""Lesson-bound JQX recipes and six-probe activation, without provider calls."""
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
from tests import test_textbook_preview_pronunciation_initialization as fixtures


VERSION = 'mira.textbook.pinyin-jqx-ssml.v1'
POLICY_SHA = '0f1957af0ce218d3f0323c79886f199a80210d2e1c49a7b68f6dc70071d6366b'
TOKENS = [
    ('j', 'ji1', '鸡'), ('q', 'qi1', '七'), ('x', 'xi1', '西'),
    ('jī', 'ji1', '鸡'), ('qì', 'qi4', '气'), ('xī', 'xi1', '西'),
    ('jiā', 'jia1', '家'), ('qiā', 'qia1', '掐'), ('xiá', 'xia2', '霞'),
    ('jū', 'ju1', '居'), ('qū', 'qu1', '区'), ('xū', 'xu1', '虚'),
    ('i', 'yi1', '衣'), ('ī', 'yi1', '衣'), ('ā', 'a1', '啊'),
    ('ü', 'yu1', '迂'), ('ǖ', 'yu1', '迂'), ('u', 'wu1', '乌'),
]
PROBES = {'j-call-short-context': 'j', 'q-call-short-context': 'q',
          'x-call-short-context': 'x', 'ju1-whole': 'jū', 'qu1-whole': 'qū', 'xu1-whole': 'xū'}
PRIOR_HASHES = {
    registry.AOE_POLICY_VERSION: 'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7',
    registry.IUU_POLICY_VERSION: '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb',
    registry.BPMF_POLICY_VERSION: '0db25c66499d66ddf8569e6c621d74fc63e344ff3436cfd7908e78e5509a84de',
    registry.DTNL_POLICY_VERSION: '20e7b95f0c368e54f2ca219643381d8fec6244ede8d44c7f106a47c7c4a4a709',
    registry.GARDEN2_POLICY_VERSION: '36c5b794c1e80ff0d6491e83e983d60915229c3f4275d5c69f7ad842588ad72b',
    registry.GKH_POLICY_VERSION: 'c007c1ba8cbfab2b565a432de8f3e379290839dbe3f10df678e2b3c4757b382c',
}


def jqx_plan():
    plan = pinyin_plan()
    plan['binding']['nodeId'] = 'u3-l2'
    plan['pronunciationPolicy'] = registry.registered_policy(VERSION)
    plan['pronunciationPolicySha256'] = POLICY_SHA
    return plan


class JqxPronunciationTests(unittest.TestCase):
    def test_exact_lesson_binding_preserves_prior_policies_and_formal_listening(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u3-l2'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        self.assertEqual(registry.policy_for_plan(jqx_plan()), policy)
        self.assertTrue(policy['listeningRequired'])
        self.assertFalse(policy['approvalBoundary']['formalUseAllowed'])
        for field in registry._BINDING_FIELDS:
            wrong = {**binding, field: binding[field] + '-other'}
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy(wrong)
            self.assertFalse(registry.initialization_required(wrong))
        for version, expected in PRIOR_HASHES.items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            wrong = jqx_plan()
            wrong['pronunciationPolicy'] = registry.registered_policy(version)
            wrong['pronunciationPolicySha256'] = expected
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        for version in (None, 'unknown', '__proto__'):
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.registered_policy(version)
        policy['symbols']['jū']['ph'] = 'wu1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_tokens_keep_umlaut_syllables_whole_and_chinese_natural(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {t for t, _, _ in TOKENS})
        self.assertEqual(policy['words'], {})
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                encoded = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(encoded, f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                self.assertEqual(len(ElementTree.fromstring(encoded).findall('phoneme')), 1)
        text = '请听：j、ü、jū、qū、xū。'
        nodes = ElementTree.fromstring(registry.pinyin_ssml(text, policy_version=VERSION)).findall('phoneme')
        self.assertEqual([n.attrib['ph'] for n in nodes], ['ji1', 'yu1', 'ju1', 'qu1', 'xu1'])
        chinese = '打鼓、下棋、搭积木；棋、鸡、木、鼓。'
        self.assertEqual(registry.pinyin_ssml(chinese, policy_version=VERSION), '<speak>' + chinese + '</speak>')
        self.assertEqual(registry.pronunciation_symbols(chinese, policy_version=VERSION), [])

    def test_unknown_runs_cannot_fall_back_to_supported_letters(self):
        for token in ('ju', 'ju1', 'jü', 'jv', 'jūqū', 'qu', 'xu', 'qī', 'xì', 'nǚ',
                      'u\u0308', 'ju\u0304', 'J', 'ｊ', '𝒋', 'constructor', 'j\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
        self.assertEqual(registry.pinyin_ssml('😀<&>"\'jū。', policy_version=VERSION),
            '<speak>😀&lt;&amp;&gt;&quot;&apos;<phoneme alphabet="py" ph="ju1">居</phoneme>。</speak>')

    def test_python_native_physical_body_vector_and_swapped_receipts(self):
        text = '请听：' + '，'.join(sorted(t for t, _, _ in TOKENS)) + '。打鼓、下棋、搭积木。'
        value = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(value['ssmlSha256'], 'd95756d43afda86292fe6f83bfed97c56ee84c0766090e6e1ff765c2012507f4')
        self.assertEqual(value['providerBodySha256'], 'c5f46c420744cac583b079e0fec44d1190b1fd42d304b2ca2f94e2f6655ccd44')
        for version in PRIOR_HASHES:
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation(value, policy_version=version)
        for key, wrong in [('voiceId', 'Serena'), ('policySha256', 'f' * 64), ('providerBodySha256', '0' * 64)]:
            with self.subTest(key=key), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation({**value, key: wrong}, text, policy_version=VERSION)

    def test_six_probe_approval_cannot_substitute_for_each_formal_sentence(self):
        plan = jqx_plan()
        texts = ['请听完整声音：' + token + '。' for token, _, _ in TOKENS]
        texts += ['再听一次完整音节：jū。', '先听轻短的声母：j。']
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
            with self.subTest(index=index), self.assertRaises(ApiError):
                registry.validate_listening_review(plan, classroom, sign(missing), now_ms=2)
        six = deepcopy(review)
        six['segments'] = six['segments'][:6]
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, classroom, sign(six), now_ms=2)


class JqxPronunciationInitializationTests(fixtures.PronunciationInitializationTests):
    """Synthetic evidence exercises the existing no-provider activation lifecycle."""
    node_id = 'u3-l2'
    probe_targets = PROBES
    approval_result = 'six_jqx_call_context_and_umlaut_whole_probes_pronunciation_and_tones_approved'
    approval_statement = '测试夹具：六段小样准确；正式整句仍须另行听验'
    first_speech = '请先听声母：j。再听完整音节：jū。'

    def test_all_six_samples_required_and_no_probe_audio_adopted(self):
        original = deepcopy(self.approval)
        for index in range(6):
            self.approval = deepcopy(original)
            self.approval['samples'].pop(index)
            self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError):
                self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()

    def test_whole_umlaut_recipe_rejects_wrong_sound_even_after_rehashing_evidence(self):
        label = 'ju1-whole'
        for ph in ('wu1', 'jv1', 'ju4'):
            files = initialization._evidence_files(self.patch, self.policy)
            plan = json.loads(files['evidence/plan.json'])
            approval = json.loads(files['evidence/human-approval.json'])
            original = next(s for s in plan['samples'] if s['label'] == label)
            request = original['body']
            request['input']['text'] = request['input']['text'].replace('ph="ju1"', f'ph="{ph}"')
            raw = canonical(request).encode()
            files[f'evidence/{label}/request.json'] = raw
            original.update(requestSha256=sha_bytes(raw), ssmlSha256=sha_bytes(request['input']['text'].encode()))
            files['evidence/plan.json'] = canonical(plan).encode()
            approval['probePlanSha256'] = sha_bytes(files['evidence/plan.json'])
            for sample in approval['samples']:
                for name in ('intent.json', 'receipt.json'):
                    path = f'evidence/{sample["label"]}/{name}'
                    data = json.loads(files[path])
                    data['planSha256'] = approval['probePlanSha256']
                    if sample['label'] == label:
                        data['requestSha256'] = sample['requestSha256'] = sha_bytes(raw)
                    files[path] = canonical(data).encode()
            files['evidence/human-approval.json'] = canonical(approval).encode()
            patch = deepcopy(self.patch)
            patch['approvedProbeEvidence']['sha256'] = sha_bytes(files['evidence/human-approval.json'])
            with self.subTest(ph=ph), self.assertRaisesRegex(ApiError, '音素顺序'):
                initialization._verify_evidence(files, patch, self.f.key, json.loads(self.row['input_json']), self.policy)
        self.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
