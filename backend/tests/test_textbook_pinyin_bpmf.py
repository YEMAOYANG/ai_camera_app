"""Whole-syllable and whole-word pronunciation boundaries; no provider/DB calls."""
from copy import deepcopy
import unittest

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import digest
from core.errors import ApiError
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan, sign


VERSION = 'mira.textbook.pinyin-bpmf-ssml.v1'
POLICY_SHA = '0db25c66499d66ddf8569e6c621d74fc63e344ff3436cfd7908e78e5509a84de'
TOKENS = [
    ('b', 'bo1', '波'), ('p', 'po1', '坡'), ('m', 'mo1', '摸'), ('f', 'fo1', '佛'),
    ('ɑ', 'a1', '啊'), ('ba', 'ba1', '八'), ('bā', 'ba1', '八'), ('bá', 'ba2', '拔'),
    ('bǎ', 'ba3', '把'), ('bà', 'ba4', '坝'), ('bō', 'bo1', '波'), ('bí', 'bi2', '鼻'),
    ('bù', 'bu4', '布'), ('pá', 'pa2', '爬'), ('pò', 'po4', '破'), ('pī', 'pi1', '批'),
    ('pǔ', 'pu3', '普'), ('mǎ', 'ma3', '马'), ('mō', 'mo1', '摸'), ('mǐ', 'mi3', '米'),
    ('mù', 'mu4', '木'), ('fā', 'fa1', '发'), ('fó', 'fo2', '佛'), ('fǔ', 'fu3', '斧'),
]


def bpmf_plan():
    value = pinyin_plan()
    value['binding']['nodeId'] = 'u2-l3'
    value['pronunciationPolicy'] = registry.registered_policy(VERSION)
    value['pronunciationPolicySha256'] = digest(value['pronunciationPolicy'])
    return value


class BpmfPronunciationTests(unittest.TestCase):
    def test_exact_lesson_registration_and_old_hashes_are_unchanged(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u2-l3'}
        self.assertEqual(digest(registry.select_policy(binding)), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        self.assertEqual(registry.policy_for_plan(bpmf_plan()), registry.select_policy(binding))
        for node in ('u2-l1', 'u2-l2', 'u2-l4'):
            wrong = bpmf_plan()
            wrong['binding']['nodeId'] = node
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        self.assertEqual(registry.POLICY_SHA256,
                         'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7')
        self.assertEqual(digest(registry.registered_policy(registry.IUU_POLICY_VERSION)),
                         '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb')

    def test_every_complete_syllable_is_one_phoneme(self):
        self.assertEqual(set(registry.registered_policy(VERSION)['symbols']), {t[0] for t in TOKENS})
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                self.assertEqual(registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION),
                                 f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')

    def test_unknown_runs_are_not_split_into_known_symbols(self):
        for token in ('bai', 'e', 'baaa', 'bābá', 'bɑ', 'bǎng', 'B', 'pǐ', 'ba1',
                      'bā\u0301', 'b\u0304a', 'bK', 'Ⅳ', '𝒃', 'hello', 'constructor'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听' + token + '。', policy_version=VERSION)

    def test_whole_chinese_words_keep_neutral_second_syllable(self):
        self.assertEqual(registry.pinyin_ssml('爸爸和妈妈。', policy_version=VERSION),
                         '<speak><phoneme alphabet="py" ph="ba4 ba5">爸爸</phoneme>和'
                         '<phoneme alphabet="py" ph="ma1 ma5">妈妈</phoneme>。</speak>')
        self.assertEqual(registry.pronunciation_symbols('爸、妈、八。', policy_version=VERSION), [])

    def test_codepoint_offsets_and_xml_are_preserved(self):
        text = '😀<&>"\'爸爸，bā。'
        matches = registry.pronunciation_symbols(text, policy_version=VERSION)
        self.assertEqual([(m['index'], m['symbol']) for m in matches], [(6, '爸爸'), (9, 'bā')])
        self.assertEqual(registry.pinyin_ssml(text, policy_version=VERSION),
                         '<speak>😀&lt;&amp;&gt;&quot;&apos;<phoneme alphabet="py" ph="ba4 ba5">爸爸</phoneme>，'
                         '<phoneme alphabet="py" ph="ba1">八</phoneme>。</speak>')
        for char in ('\x00', '\x85', '\u0300'):
            with self.subTest(char=char), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听' + char, policy_version=VERSION)

    def test_cross_language_vector_and_recipe_not_acceptance(self):
        text = '请听b p m f，ɑ ba bā bá bǎ bà，爸爸、妈妈。'
        receipt = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(receipt['ssmlSha256'], '8343595c46dbef24126d661bb5360bd9f31a88c2b01e1963e9a888f8df7a2701')
        self.assertEqual(receipt['providerBodySha256'], 'c829841fca7dfa555c8d704612e60994774954387509c075ec1bbae2cf4d36ab')
        policy = registry.registered_policy(VERSION)
        self.assertEqual(policy['inputParameters'], registry.registered_policy()['inputParameters'])
        self.assertTrue(policy['listeningRequired'])
        self.assertFalse(policy['approvalBoundary']['shortConsonantAccepted'])
        for other in (registry.AOE_POLICY_VERSION, registry.IUU_POLICY_VERSION):
            with self.assertRaises(ApiError):
                registry.validate_provider_pronunciation(receipt, policy_version=other)

    def test_all_seven_family_contexts_require_exact_formal_listening(self):
        texts = [
            '图里的小朋友这样称呼这位家人，请听：爸爸。',
            '看看称呼中的这个字，它也能表示爸爸这个意思。',
            '爸爸的称呼认识过了，我们接着看看另一位家人。',
            '图里的小朋友这样称呼这位家人，请听：妈妈。',
            '妈妈的称呼也认识过了，再把两个称呼一起找一找。',
            '这一位是刚才认识的家人，听听完整称呼：爸爸。',
            '再听另一位家人的完整称呼，跟着试一试：妈妈。',
        ]
        plan = bpmf_plan()
        actions = [{'id': str(i), 'type': 'speech', 'text': text, 'audioId': 'tbptts1_' + f'{i:064x}'}
                   for i, text in enumerate(texts)]
        classroom = {'scenes': [{'id': 's', 'actions': actions}]}
        review = sign({'schemaVersion': registry.LISTENING_SCHEMA, 'previewKey': plan['previewKey'],
            'planSha256': digest(plan), 'coreSha256': plan['coreSha256'], 'segments': [
                {'sceneId': 's', 'actionId': a['id'], 'textSha256': registry.sha_text(a['text']),
                 'ttsRequestId': a['audioId'], 'audioSha256': 'f' * 64, 'verdict': 'accepted',
                 'reviewer': 'fixture-human', 'reviewedAt': 1, 'basis': 'fixture exact whole sentence'} for a in actions]})
        self.assertEqual(len(registry.validate_listening_review(plan, classroom, review, now_ms=2)), 7)
        for index in range(7):
            missing = deepcopy(review)
            missing['segments'].pop(index)
            sign(missing)
            with self.subTest(missing=index), self.assertRaises(ApiError):
                registry.validate_listening_review(plan, classroom, missing, now_ms=2)


if __name__ == '__main__':
    unittest.main()
