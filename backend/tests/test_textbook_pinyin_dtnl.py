"""DTNL whole-syllable recipes and probe/formal evidence boundaries; no paid calls."""
from copy import deepcopy
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import digest
from core.errors import ApiError
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan, sign
from tests import test_textbook_preview_pronunciation_initialization as initialization_fixtures


VERSION = 'mira.textbook.pinyin-dtnl-ssml.v1'
POLICY_SHA = '20e7b95f0c368e54f2ca219643381d8fec6244ede8d44c7f106a47c7c4a4a709'
TOKENS = [
    ('d', 'de1', '的'), ('t', 'te1', '特'), ('n', 'ne1', '呢'), ('l', 'le1', '勒'),
    ('ǎ', 'a3', '啊'), ('dǎ', 'da3', '打'), ('dé', 'de2', '得'), ('dī', 'di1', '低'),
    ('dú', 'du2', '读'), ('tā', 'ta1', '他'), ('tè', 'te4', '特'), ('tǐ', 'ti3', '体'),
    ('tú', 'tu2', '图'), ('ná', 'na2', '拿'), ('né', 'ne2', '哪'), ('nǐ', 'ni3', '你'),
    ('nù', 'nu4', '怒'), ('nǚ', 'nv3', '女'), ('lā', 'la1', '拉'), ('lè', 'le4', '乐'),
    ('lǐ', 'li3', '里'), ('lù', 'lu4', '路'), ('lǘ', 'lv2', '驴'),
]
WORDS = [('大地', 'da4 di4'), ('马路', 'ma3 lu4'), ('泥土', 'ni2 tu3')]


def dtnl_plan():
    value = pinyin_plan()
    value['binding']['nodeId'] = 'u2-l4'
    value['pronunciationPolicy'] = registry.registered_policy(VERSION)
    value['pronunciationPolicySha256'] = POLICY_SHA
    return value


class DtnlPronunciationTests(unittest.TestCase):
    def test_exact_lesson_registration_preserves_prior_policy_hashes(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u2-l4'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        self.assertEqual(registry.policy_for_plan(dtnl_plan()), policy)
        for field in registry._BINDING_FIELDS:
            wrong = {**binding, field: binding[field] + '-other'}
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy(wrong)
            self.assertFalse(registry.initialization_required(wrong))
        for version, expected in (
            (registry.AOE_POLICY_VERSION, 'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7'),
            (registry.IUU_POLICY_VERSION, '09776788ae5c1dfbbf137179be923550e5838256f5abd30ae8b78b5493f2f8fb'),
            (registry.BPMF_POLICY_VERSION, '0db25c66499d66ddf8569e6c621d74fc63e344ff3436cfd7908e78e5509a84de'),
        ):
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            wrong = dtnl_plan()
            wrong['pronunciationPolicy'] = registry.registered_policy(version)
            wrong['pronunciationPolicySha256'] = expected
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        for node in ('u2-l1', 'u2-l2', 'u2-l3', 'u2-l5'):
            wrong = dtnl_plan()
            wrong['binding']['nodeId'] = node
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        policy['symbols']['nǚ']['ph'] = 'nu3'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_complete_syllables_and_words_are_single_phoneme_elements(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {token for token, _, _ in TOKENS})
        self.assertEqual(set(policy['words']), {word for word, _ in WORDS})
        for token, ph, carrier in TOKENS + [(word, ph, word) for word, ph in WORDS]:
            with self.subTest(token=token):
                value = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(value, f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                root = ElementTree.fromstring(value)
                self.assertEqual(len(root.findall('phoneme')), 1)
                self.assertEqual(len(ph.split()), len(carrier))
        self.assertEqual(registry.pronunciation_symbols('大、马、路、土，大小和土地。', policy_version=VERSION), [])

    def test_unknown_runs_cannot_fall_back_to_letters_or_strip_umlaut(self):
        for token in ('da', 'da3', 'dā', 'dǎn', 'dǎdǎ', 'dɑ', 'nü', 'nü3', 'nv3',
                      'lǚ', 'lv2', 'nǚlǘ', 'n\u0308', 'a\u030c', 'D', 'ｄ', '𝒅',
                      'dK', 'Ⅳ', 'hello', 'constructor', '\x00', '\x85'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听' + token + '。', policy_version=VERSION)
        text = '😀<&>"\'大地，nǚ。'
        matches = registry.pronunciation_symbols(text, policy_version=VERSION)
        self.assertEqual([(m['index'], m['symbol']) for m in matches], [(6, '大地'), (9, 'nǚ')])
        self.assertEqual(registry.pinyin_ssml(text, policy_version=VERSION),
                         '<speak>😀&lt;&amp;&gt;&quot;&apos;<phoneme alphabet="py" ph="da4 di4">大地</phoneme>，'
                         '<phoneme alphabet="py" ph="nv3">女</phoneme>。</speak>')

    def test_shared_body_identity_and_probe_approval_are_not_formal_acceptance(self):
        text = '请听d t n l，ǎ，dǎ dé dī dú，tā tè tǐ tú，ná né nǐ nù nǚ，lā lè lǐ lù lǘ，大地、马路、泥土。'
        receipt = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(receipt['ssmlSha256'], '75e230efa0318c01bd06eb00b4cfb3e073274825a46a6333e09926e978b88f71')
        self.assertEqual(receipt['providerBodySha256'], 'ca50f115869da4fb627c9a3a7bf354ee35530933c789b7fa888a75b2ccf9cb2b')
        policy = registry.registered_policy(VERSION)
        self.assertEqual(policy['inputParameters'], registry.registered_policy()['inputParameters'])
        self.assertTrue(policy['listeningRequired'])
        self.assertFalse(policy['approvalBoundary']['shortConsonantAccepted'])
        self.assertEqual(policy['approvalBoundary']['approvedProbeScope'],
                         'four-base-call-names-and-two-whole-umlaut-syllables-only')
        for version in (registry.AOE_POLICY_VERSION, registry.IUU_POLICY_VERSION, registry.BPMF_POLICY_VERSION):
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation(receipt, policy_version=version)

    def test_six_probes_or_unique_token_coverage_cannot_replace_all_formal_contexts(self):
        # Repeated tokens/words in distinct sentences each need exact formal evidence.
        tokens = [token for token, _, _ in TOKENS] + ['d', 't', 'dǎ', 'nǚ']
        texts = ['请听老师完整示范：' + token + '。' for token in tokens]
        texts += ['听听这个词语，再看图片：' + word + '。' for word in ('大地', '马路', '泥土')]
        texts += ['看看词语后面的这个字，土就是画面里的泥土。',
                  '这个字可以表示土，看看图中地面的这些泥土。']
        self.assertEqual(len(texts), 32)
        plan = dtnl_plan()
        actions = [{'id': str(i), 'type': 'speech', 'text': text, 'audioId': 'tbptts1_' + f'{i:064x}'}
                   for i, text in enumerate(texts)]
        classroom = {'scenes': [{'id': 's', 'actions': actions}]}
        review = sign({'schemaVersion': registry.LISTENING_SCHEMA, 'previewKey': plan['previewKey'],
            'planSha256': digest(plan), 'coreSha256': plan['coreSha256'], 'segments': [
                {'sceneId': 's', 'actionId': a['id'], 'textSha256': registry.sha_text(a['text']),
                 'ttsRequestId': a['audioId'], 'audioSha256': 'f' * 64, 'verdict': 'accepted',
                 'reviewer': 'fixture-human', 'reviewedAt': 1, 'basis': 'fixture exact formal sentence'} for a in actions]})
        self.assertEqual(len(registry.validate_listening_review(plan, classroom, review, now_ms=2)), 32)
        six_only = deepcopy(review)
        six_only['segments'] = [six_only['segments'][i] for i in (0, 1, 2, 3, 17, 22)]
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, classroom, sign(six_only), now_ms=2)
        for index in range(32):
            missing = deepcopy(review)
            missing['segments'].pop(index)
            with self.subTest(missing=index), self.assertRaises(ApiError):
                registry.validate_listening_review(plan, classroom, sign(missing), now_ms=2)
        changed = deepcopy(classroom)
        changed['scenes'][0]['actions'][0]['audioId'] = 'tbptts1_' + 'e' * 64
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, changed, review, now_ms=2)


class DtnlPronunciationInitializationTests(initialization_fixtures.PronunciationInitializationTests):
    """Six exact probe artifacts permit preparation, never publication or audio reuse."""
    node_id = 'u2-l4'
    probe_targets = {'d-base': 'd', 't-base': 't', 'n-base': 'n', 'l-base': 'l',
                     'nv3-whole': 'nǚ', 'lv2-whole': 'lǘ'}
    approval_result = 'six_dtnl_probes_pronunciation_and_tones_approved'
    approval_statement = '六段小样读音与声调准确；正式整句与声母轻短程度待另行听验'
    first_speech = '请听老师示范：d。'

    def test_four_base_probes_cannot_omit_the_two_umlaut_syllables(self):
        self.approval['samples'] = self.approval['samples'][:4]
        self.write_approval()
        with self.assertRaises(ApiError):
            self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
