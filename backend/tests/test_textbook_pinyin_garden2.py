"""Garden 2 whole-token encoding and nine-probe/formal evidence boundaries."""
from copy import deepcopy
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import digest
from core.errors import ApiError
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan, sign
from tests import test_textbook_preview_pronunciation_initialization as initialization_fixtures


VERSION = 'mira.textbook.pinyin-garden2-ssml.v1'
POLICY_SHA = '36c5b794c1e80ff0d6491e83e983d60915229c3f4275d5c69f7ad842588ad72b'
TOKENS = [
    ('dǎ', 'da3', '打'), ('dà', 'da4', '大'), ('mō', 'mo1', '摸'), ('mó', 'mo2', '磨'),
    ('bí', 'bi2', '鼻'), ('bǐ', 'bi3', '笔'), ('pú', 'pu2', '葡'), ('pù', 'pu4', '铺'),
    ('là', 'la4', '蜡'), ('mǐ', 'mi3', '米'), ('fú', 'fu2', '扶'), ('tī', 'ti1', '梯'),
    ('dì', 'di4', '地'), ('tú', 'tu2', '图'), ('b', 'bo1', '波'), ('d', 'de1', '的'),
    ('f', 'fo1', '佛'), ('t', 'te1', '特'), ('ɑ', 'a1', '啊'), ('i', 'yi1', '衣'), ('u', 'wu1', '乌'),
]
PRIOR_HASHES = {
    registry.AOE_POLICY_VERSION: 'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7',
    registry.IUU_POLICY_VERSION: '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb',
    registry.BPMF_POLICY_VERSION: '0db25c66499d66ddf8569e6c621d74fc63e344ff3436cfd7908e78e5509a84de',
    registry.DTNL_POLICY_VERSION: '20e7b95f0c368e54f2ca219643381d8fec6244ede8d44c7f106a47c7c4a4a709',
}


def garden2_plan():
    value = pinyin_plan()
    value['binding']['nodeId'] = 'u2-l5'
    value['pronunciationPolicy'] = registry.registered_policy(VERSION)
    value['pronunciationPolicySha256'] = POLICY_SHA
    return value


def formal_texts():
    return [
        *['这一轮先听老师读完整音节，听清声调再选图卡：' + token + '。'
          for token in ('dǎ', 'dà', 'mō', 'mó', 'bí', 'bǐ', 'pú', 'pù')],
        *[prefix + token + '。' for first, second in (('b', 'd'), ('f', 't'))
          for prefix, token in (('先看第一种字形，愿意的话跟着老师轻短地读：', first),
                                ('再看另一种字形，愿意的话跟着老师轻短地读：', second))],
        *['听老师把两个音节连起来读，再联系图片：' + phrase + '。'
          for phrase in ('là bǐ，蜡笔', 'dà mǐ，大米', 'fú tī，扶梯', 'dì tú，地图')],
        '听老师读这个音节，请点相同的音节图卡：bǐ。',
        *['这一组字的读音里，都有同一个韵母，再听老师示范：' + token + '。'
          for token in ('ɑ', 'i', 'u')],
    ]


class Garden2PronunciationTests(unittest.TestCase):
    def test_exact_binding_does_not_change_previous_policies_or_grant_approval(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u2-l5'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        self.assertEqual(registry.policy_for_plan(garden2_plan()), policy)
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
            wrong = garden2_plan()
            wrong['pronunciationPolicy'] = registry.registered_policy(version)
            wrong['pronunciationPolicySha256'] = expected
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        for node in ('u2-l1', 'u2-l2', 'u2-l3', 'u2-l4', 'u3-l1'):
            wrong = garden2_plan()
            wrong['binding']['nodeId'] = node
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        policy['symbols']['bǐ']['ph'] = 'bi2'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_whole_tokens_preserve_tones_and_do_not_teach_chinese_annotation_as_pinyin(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {token for token, _, _ in TOKENS})
        self.assertEqual(policy['words'], {})
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                ssml = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(ssml, f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                self.assertEqual(len(ElementTree.fromstring(ssml).findall('phoneme')), 1)
        chinese = '蜡笔、大米、扶梯、地图；本、学、校、班、级、姓、名、王、九。'
        self.assertEqual(registry.pinyin_ssml(chinese, policy_version=VERSION), '<speak>' + chinese + '</speak>')
        self.assertEqual(registry.pronunciation_symbols(chinese, policy_version=VERSION), [])

    def test_unknown_complete_tokens_cannot_fall_back_to_individual_letters(self):
        for token in ('da', 'da3', 'dǎmō', 'momo', 'pu2', 'p', 'm', 'n', 'l', 'e', 'ü',
                      'xué', 'bān', 'jiǔ', 'di\u0300', 'D', 'ｄ', '𝒅', 'constructor', 'x\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听' + token + '。', policy_version=VERSION)
        self.assertEqual(registry.pinyin_ssml('😀<&>"\'bǐ。', policy_version=VERSION),
            '<speak>😀&lt;&amp;&gt;&quot;&apos;<phoneme alphabet="py" ph="bi3">笔</phoneme>。</speak>')

    def test_native_body_vector_and_cross_policy_receipt_rejection(self):
        text = '请听：' + '，'.join(token for token, _, _ in TOKENS) + '。蜡笔、大米、扶梯、地图。'
        receipt = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(receipt['ssmlSha256'], '6d0bd49f01e52829e1dac9c24769105ef6294e1a6f3a48203722815eb38f943e')
        self.assertEqual(receipt['providerBodySha256'], 'f2241ed04b80d52b573044a69012757a5398a10c4775727757f09b6e5387618e')
        self.assertEqual(registry.registered_policy(VERSION)['inputParameters'], registry.registered_policy()['inputParameters'])
        for version in PRIOR_HASHES:
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation(receipt, policy_version=version)

    def test_all_formal_contexts_need_listening_even_for_repeated_or_previously_used_tokens(self):
        texts = formal_texts()
        self.assertEqual(len(texts), 20)
        self.assertEqual(sum(len(registry.pronunciation_symbols(t, policy_version=VERSION)) for t in texts), 24)
        plan = garden2_plan()
        actions = [{'id': str(i), 'type': 'speech', 'text': text, 'audioId': 'tbptts1_' + f'{i:064x}'}
                   for i, text in enumerate(texts)]
        classroom = {'scenes': [{'id': 's', 'actions': actions}]}
        review = sign({'schemaVersion': registry.LISTENING_SCHEMA, 'previewKey': plan['previewKey'],
            'planSha256': digest(plan), 'coreSha256': plan['coreSha256'], 'segments': [
                {'sceneId': 's', 'actionId': a['id'], 'textSha256': registry.sha_text(a['text']),
                 'ttsRequestId': a['audioId'], 'audioSha256': 'f' * 64, 'verdict': 'accepted',
                 'reviewer': 'fixture-human', 'reviewedAt': 1, 'basis': 'synthetic exact formal sentence'} for a in actions]})
        self.assertEqual(len(registry.validate_listening_review(plan, classroom, review, now_ms=2)), 20)
        for index in range(20):
            missing = deepcopy(review)
            missing['segments'].pop(index)
            with self.subTest(missing=index), self.assertRaises(ApiError):
                registry.validate_listening_review(plan, classroom, sign(missing), now_ms=2)
        nine_only = deepcopy(review)
        nine_only['segments'] = nine_only['segments'][:9]
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, classroom, sign(nine_only), now_ms=2)
        changed = deepcopy(classroom)
        changed['scenes'][0]['actions'][16]['audioId'] = 'tbptts1_' + 'e' * 64
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, changed, review, now_ms=2)


class Garden2PronunciationInitializationTests(initialization_fixtures.PronunciationInitializationTests):
    """Synthetic evidence only; nine new probes never approve formal course audio."""
    node_id = 'u2-l5'
    probe_targets = {'da4-whole': 'dà', 'mo2-whole': 'mó', 'bi3-whole': 'bǐ',
                     'pu2-whole': 'pú', 'pu4-whole': 'pù', 'la4-whole': 'là',
                     'fu2-whole': 'fú', 'ti1-whole': 'tī', 'di4-whole': 'dì'}
    approval_result = 'nine_garden2_new_syllable_probes_pronunciation_and_tones_approved'
    approval_statement = '测试夹具：九个新增音节小样准确；正式整句尚未听验'
    first_speech = '请听老师示范：bǐ。'

    def test_each_of_nine_probes_is_required_including_word_support_syllables(self):
        original = deepcopy(self.approval)
        for index in range(9):
            self.approval = deepcopy(original)
            self.approval['samples'].pop(index)
            self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError):
                self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
