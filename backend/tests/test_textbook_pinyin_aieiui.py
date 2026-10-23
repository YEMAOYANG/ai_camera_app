"""AI/EI/UI whole-token policy and its six fixed, human-listened probes."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services import textbook_preview_pronunciation_initialization as initialization
from services import textbook_pronunciation_probe_aieiui_composite as aieiui_composite
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization as fixtures
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan, sign


V1 = 'mira.textbook.pinyin-aieiui-ssml.v1'
V2 = 'mira.textbook.pinyin-aieiui-ssml.v2'
V3 = 'mira.textbook.pinyin-aieiui-ssml.v3'
V4 = 'mira.textbook.pinyin-aieiui-ssml.v4'
VERSION = V4
V1_POLICY_SHA = '8b927f95d0f279c31c9ae90c7aebcaf8520c34ed829982fda8aa4dfebadd4188'
V2_POLICY_SHA = '2793692b3e4a0c56187028bb1dc79ee0920a11a08132559593f739b3714a75be'
V3_POLICY_SHA = '4e4abf730c7e63bb6dab44c68df0460b65fac17905fb4df78226d53c59a6310e'
POLICY_SHA = 'd26d1744a110f0ed327d08cdfeb950fe8f15b198fb322f98aa5611f866c6b8b8'
LUO_BO_V1_SSML = ('<speak><phoneme alphabet="py" ph="luo2">萝</phoneme> '
                  '<phoneme alphabet="py" ph="bo5">卜</phoneme></speak>')
LUO_BO_V2_SSML = ('<speak><phoneme alphabet="py" ph="luo2">萝</phoneme> '
                  '<phoneme alphabet="py" ph="bo5">卜</phoneme>。</speak>')
LUO_BO_V3_SSML = '<speak><phoneme alphabet="py" ph="luo2 bo5">萝卜</phoneme>。</speak>'
LUO_BO_V4_SSML = '<speak><sub alias="萝卜">luó bo</sub>。</speak>'
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
    'mira.textbook.pinyin-zhchshr-ssml.v1': 'e4faadb5854f3813b1ea94a20aee7ff4496dc6f2ac9b889686555d4405c8b800',
    'mira.textbook.pinyin-yw-ssml.v1': '77b30e78c17440453999a96b4dfb77fb95bd538e814419289a6bcbc942052335',
    'mira.textbook.pinyin-garden3-ssml.v1': '472da6bc4ce841cc9916593db4ec1837576a7ab66761975725d68622264b6e6a',
    'mira.textbook.pinyin-garden3-ssml.v2': '9ea68dcd614baeee676492b25f05c2b156d629ceced33a10eebf58ecb2e00f31',
    V1: V1_POLICY_SHA,
    V2: V2_POLICY_SHA,
    V3: V3_POLICY_SHA,
}
FINAL_TOKENS = [
    ('ɑi', 'ai1', '哀'), ('āi', 'ai1', '哀'), ('ái', 'ai2', '挨'),
    ('ǎi', 'ai3', '矮'), ('ài', 'ai4', '爱'),
    ('ei', 'ei1', '诶'), ('ēi', 'ei1', '诶'), ('éi', 'ei2', '诶'),
    ('ěi', 'ei3', '诶'), ('èi', 'ei4', '诶'),
    ('ui', 'wei1', '威'), ('uī', 'wei1', '威'), ('uí', 'wei2', '围'),
    ('uǐ', 'wei3', '伟'), ('uì', 'wei4', '味'),
]
SPELLING_TOKENS = [('g', 'ge1', '哥'), ('u', 'wu1', '乌'),
                   ('l', 'le1', '勒'), ('t', 'te1', '特')]
TEXTBOOK_SYLLABLES = [
    ('gāi', 'gai1', '该'), ('guāi', 'guai1', '乖'), ('tái', 'tai2', '台'),
    ('kāi', 'kai1', '开'), ('cāi', 'cai1', '猜'), ('huài', 'huai4', '坏'),
    ('kuài', 'kuai4', '快'), ('lèi', 'lei4', '泪'), ('bēi', 'bei1', '杯'),
    ('péi', 'pei2', '陪'), ('fēi', 'fei1', '飞'), ('gěi', 'gei3', '给'),
    ('wéi', 'wei2', '围'), ('hēi', 'hei1', '黑'), ('tuǐ', 'tui3', '腿'),
    ('huì', 'hui4', '会'), ('duī', 'dui1', '堆'), ('chuī', 'chui1', '吹'),
    ('zuǐ', 'zui3', '嘴'), ('suì', 'sui4', '岁'), ('ruì', 'rui4', '瑞'),
]
PICTURE_TOKENS = [
    ('pái', 'pai2', '排'), ('duì', 'dui4', '队'), ('luó', 'luo2', '萝'),
    ('bo', 'bo5', '卜'), ('bái', 'bai2', '白'), ('cài', 'cai4', '菜'),
    ('yā', 'ya1', '鸭'), ('lí', 'li2', '梨'), ('xī', 'xi1', '西'),
    ('guā', 'gua1', '瓜'), ('shū', 'shu1', '蔬'), ('shuǐ', 'shui3', '水'),
    ('guǒ', 'guo3', '果'),
]
TOKENS = FINAL_TOKENS + SPELLING_TOKENS + TEXTBOOK_SYLLABLES + PICTURE_TOKENS
PROBE_TEXTS = {
    'ai-final-and-tones': 'ɑi，āi、ái、ǎi、ài',
    'ei-final-and-tones': 'ei，ēi、éi、ěi、èi',
    'ui-final-and-tones': 'ui，uī、uí、uǐ、uì',
    'textbook-spelling-sequences': 'g、āi、gāi；g、u、āi、guāi；l、èi、lèi；t、uǐ、tuǐ',
    'pai-dui-whole': 'pái duì',
    'luo-bo-neutral': 'luó bo',
}
PROBE_TOKENS = {
    'ai-final-and-tones': ('ɑi', 'āi', 'ái', 'ǎi', 'ài'),
    'ei-final-and-tones': ('ei', 'ēi', 'éi', 'ěi', 'èi'),
    'ui-final-and-tones': ('ui', 'uī', 'uí', 'uǐ', 'uì'),
    'textbook-spelling-sequences': (
        'g', 'āi', 'gāi', 'g', 'u', 'āi', 'guāi', 'l', 'èi', 'lèi', 't', 'uǐ', 'tuǐ'),
    'pai-dui-whole': ('pái', 'duì'),
    'luo-bo-neutral': ('luó', 'bo'),
}
PROBE_TARGETS = {
    'ai-final-and-tones': 'ɑi', 'ei-final-and-tones': 'ei',
    'ui-final-and-tones': 'ui', 'textbook-spelling-sequences': 'gāi',
    'pai-dui-whole': 'pái', 'luo-bo-neutral': 'luó',
}

COMPOSITE_REVIEW = (Path(__file__).resolve().parents[2] / 'output/textbook-operator-lessons' /
    'pep-chinese-g1-upper-2022-standard/u4-l1/teaching-1/quality-repairs' /
    'pinyin-ssml-probe-composition-v1/human-approval-before-adoption-binding.json')


def lesson_plan(version=VERSION):
    plan = pinyin_plan()
    plan['binding']['nodeId'] = 'u4-l1'
    plan['pronunciationPolicy'] = registry.registered_policy(version)
    plan['pronunciationPolicySha256'] = digest(plan['pronunciationPolicy'])
    return plan


class AiEiUiPronunciationTests(unittest.TestCase):
    def test_exact_lesson_binding_v4_default_prior_recovery_and_hashes_are_immutable(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u4-l1'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertEqual(registry.policy_for_plan(lesson_plan()), policy)
        self.assertEqual(registry.policy_for_plan(lesson_plan(V1)), registry.registered_policy(V1))
        self.assertEqual(registry.policy_for_plan(lesson_plan(V2)), registry.registered_policy(V2))
        self.assertEqual(registry.policy_for_plan(lesson_plan(V3)), registry.registered_policy(V3))
        self.assertTrue(registry.initialization_required(binding))
        for version, expected in PRIOR_HASHES.items():
            with self.subTest(version=version):
                self.assertEqual(digest(registry.registered_policy(version)), expected)
        self.assertTrue((set(PRIOR_HASHES) | {V4}) <= set(registry._POLICIES))
        for field in registry._BINDING_FIELDS:
            wrong = {**binding, field: binding[field] + '-other'}
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy(wrong)
        policy['symbols']['ɑi']['ph'] = 'wrong1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_v2_changes_only_the_exact_luo_bo_request_and_v1_bytes_remain_stable(self):
        old = registry.registered_policy(V1)
        new = registry.registered_policy(V2)
        self.assertEqual(digest(old), V1_POLICY_SHA)
        old_common = {k: v for k, v in old.items()
                      if k not in {'policyVersion', 'approvalBoundary'}}
        new_common = {k: v for k, v in new.items()
                      if k not in {'policyVersion', 'approvalBoundary', 'exactTextSsml'}}
        self.assertEqual(new_common, old_common)
        changed = []
        for label, source in PROBE_TEXTS.items():
            before = registry.provider_body(source, policy_version=V1)
            after = registry.provider_body(source, policy_version=V2)
            if before != after:
                changed.append(label)
            self.assertEqual(registry.pronunciation_symbols(source, policy_version=V1),
                             registry.pronunciation_symbols(source, policy_version=V2))
        self.assertEqual(changed, ['luo-bo-neutral'])
        self.assertEqual(registry.pinyin_ssml('luó bo', policy_version=V1), LUO_BO_V1_SSML)
        self.assertEqual(registry.pinyin_ssml('luó bo', policy_version=V2), LUO_BO_V2_SSML)
        for source in ('请听：luó bo', 'luó bo。', 'luó  bo', 'luó bo！'):
            self.assertEqual(registry.provider_body(source, policy_version=V2),
                             registry.provider_body(source, policy_version=V1))

    def test_v3_changes_only_the_exact_luo_bo_request_and_keeps_v1_v2_hashes(self):
        old = registry.registered_policy(V2)
        new = registry.registered_policy(V3)
        self.assertEqual(digest(registry.registered_policy(V1)), V1_POLICY_SHA)
        self.assertEqual(digest(old), V2_POLICY_SHA)
        old_common = {k: v for k, v in old.items()
                      if k not in {'policyVersion', 'approvalBoundary', 'exactTextSsml'}}
        new_common = {k: v for k, v in new.items()
                      if k not in {'policyVersion', 'approvalBoundary', 'exactTextSsml'}}
        self.assertEqual(new_common, old_common)
        changed = []
        for label, source in PROBE_TEXTS.items():
            before = registry.provider_body(source, policy_version=V2)
            after = registry.provider_body(source, policy_version=V3)
            if before != after:
                changed.append(label)
            self.assertEqual(registry.pronunciation_symbols(source, policy_version=V2),
                             registry.pronunciation_symbols(source, policy_version=V3))
        self.assertEqual(changed, ['luo-bo-neutral'])
        self.assertEqual(registry.pinyin_ssml('luó bo', policy_version=V3), LUO_BO_V3_SSML)
        for source in ('请听：luó bo', 'luó bo。', 'luó  bo', 'luó bo！'):
            self.assertEqual(registry.provider_body(source, policy_version=V3),
                             registry.provider_body(source, policy_version=V2))

    def test_v4_changes_only_exact_luo_bo_and_keeps_all_historical_hashes(self):
        old = registry.registered_policy(V3)
        new = registry.registered_policy(V4)
        for version, expected in ((V1, V1_POLICY_SHA), (V2, V2_POLICY_SHA),
                                  (V3, V3_POLICY_SHA)):
            self.assertEqual(digest(registry.registered_policy(version)), expected)
        old_common = {k: v for k, v in old.items()
                      if k not in {'policyVersion', 'approvalBoundary', 'exactTextSsml'}}
        new_common = {k: v for k, v in new.items()
                      if k not in {'policyVersion', 'approvalBoundary', 'exactTextSsml'}}
        self.assertEqual(new_common, old_common)
        changed = []
        for label, source in PROBE_TEXTS.items():
            before = registry.provider_body(source, policy_version=V3)
            after = registry.provider_body(source, policy_version=V4)
            if before != after:
                changed.append(label)
            self.assertEqual(registry.pronunciation_symbols(source, policy_version=V3),
                             registry.pronunciation_symbols(source, policy_version=V4))
        self.assertEqual(changed, ['luo-bo-neutral'])
        self.assertEqual(registry.pinyin_ssml('luó bo', policy_version=V4), LUO_BO_V4_SSML)
        for source in ('请听：luó bo', 'luó bo。', 'luó  bo', 'luó bo！'):
            self.assertEqual(registry.provider_body(source, policy_version=V4),
                             registry.provider_body(source, policy_version=V3))
        boundary = new['approvalBoundary']
        self.assertFalse(boundary['humanListeningVerified'])
        self.assertFalse(boundary['perceptualToneVerified'])
        self.assertFalse(boundary['pronunciationApproved'])
        self.assertFalse(boundary['formalUseAllowed'])
        self.assertIn('user listening', boundary['neutralToneBoundary'])

    def test_exact_53_whole_tokens_include_textbook_and_picture_scope(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {token for token, _, _ in TOKENS})
        self.assertEqual(policy['words'], {})
        self.assertEqual(len(TEXTBOOK_SYLLABLES), 21)
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                encoded = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(encoded,
                    f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                self.assertEqual(len(ElementTree.fromstring(encoded).findall('phoneme')), 1)
        natural = '萝卜、白菜、鸭梨、西瓜、蔬菜、水果。'
        self.assertEqual(registry.pinyin_ssml(natural, policy_version=VERSION), '<speak>' + natural + '</speak>')

    def test_six_fixed_probe_sources_and_phoneme_order(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(dict(initialization._AIEIUI_PROBE_TEXTS), PROBE_TEXTS)
        self.assertEqual(dict(initialization._AIEIUI_PROBE_TOKENS), PROBE_TOKENS)
        probes, result = initialization._probe_contract(policy)
        self.assertEqual(dict(probes), PROBE_TARGETS)
        self.assertEqual(result, 'six_aieiui_fixed_probes_pronunciation_tones_and_neutral_tone_approved')
        for label, source in PROBE_TEXTS.items():
            ssml = registry.pinyin_ssml(source, policy_version=VERSION)
            phonemes = ElementTree.fromstring(ssml).findall('phoneme')
            if label == 'luo-bo-neutral':
                self.assertEqual(phonemes, [])
                aliases = ElementTree.fromstring(ssml).findall('sub')
                self.assertEqual([(item.attrib, item.text, item.tail) for item in aliases],
                                 [({'alias': '萝卜'}, 'luó bo', '。')])
            else:
                self.assertEqual([p.attrib['ph'] for p in phonemes],
                                 [policy['symbols'][token]['ph'] for token in PROBE_TOKENS[label]])

    def test_wrong_ui_marks_ascii_ai_numeric_tones_combining_marks_and_runs_fail_closed(self):
        invalid = ('ai', 'ai1', 'ɑi1', 'ei1', 'ui1', 'ūi', 'úi', 'ǔi', 'ùi',
                   'u\u0304i', 'a\u0304i', 'ɑ\u0304i', 'āiei', 'páiduì', 'luóbo',
                   'UI', 'ｕｉ', 'constructor', 'ui\x00')
        for token in invalid:
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
        self.assertEqual(registry.pinyin_ssml('😀<&>"\'uī。', policy_version=VERSION),
            '<speak>😀&lt;&amp;&gt;&quot;&apos;<phoneme alphabet="py" ph="wei1">威</phoneme>。</speak>')
        for version in (V1, V2, V3, V4):
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：luó unknown。', policy_version=version)

    def test_probe_approval_never_replaces_every_formal_latin_sentence_review(self):
        texts = [*PROBE_TEXTS.values(), '看图读一读：bái cài。']
        plan = lesson_plan()
        actions = [{'id': str(i), 'type': 'speech', 'text': text,
                    'audioId': 'tbptts1_' + f'{i:064x}'} for i, text in enumerate(texts)]
        classroom = {'scenes': [{'id': 's', 'actions': actions}]}
        review = sign({'schemaVersion': registry.LISTENING_SCHEMA, 'previewKey': plan['previewKey'],
            'planSha256': digest(plan), 'coreSha256': plan['coreSha256'], 'segments': [
                {'sceneId': 's', 'actionId': action['id'],
                 'textSha256': registry.sha_text(action['text']),
                 'ttsRequestId': action['audioId'], 'audioSha256': 'f' * 64,
                 'verdict': 'accepted', 'reviewer': 'fixture-human',
                 'reviewedAt': 1, 'basis': 'synthetic exact formal sentence'} for action in actions]})
        self.assertEqual(len(registry.validate_listening_review(
            plan, classroom, review, now_ms=2)), len(actions))
        six_only = deepcopy(review)
        six_only['segments'] = six_only['segments'][:6]
        with self.assertRaises(ApiError):
            registry.validate_listening_review(plan, classroom, sign(six_only), now_ms=2)


class AiEiUiPronunciationInitializationTests(fixtures.PronunciationInitializationTests):
    node_id = 'u4-l1'
    probe_targets = PROBE_TARGETS
    probe_token_sequences = PROBE_TOKENS
    probe_source_texts = PROBE_TEXTS
    approval_result = 'six_aieiui_fixed_probes_pronunciation_tones_and_neutral_tone_approved'
    approval_statement = '测试夹具：六段固定小样准确；正式整句、声调和轻声仍须逐段真人听验'
    first_speech = '请听：ɑi，āi、ái、ǎi、ài。'

    def use_real_composite_human_evidence(self):
        raw = COMPOSITE_REVIEW.read_bytes()
        self.patch = {
            'schemaVersion': initialization.COMPOSITE_HUMAN_SCHEMA,
            'expectedSourceSha256': self.row['classroom_sha256'],
            'expectedCoreSha256': digest(initialization.core_content(self.f.classroom)),
            'pronunciationPolicyVersion': self.policy['policyVersion'],
            'pronunciationPolicySha256': digest(self.policy),
            'reviewer': 'operator',
            'basis': '六段固定小样已真人听验；正式逐句仍须 ASR 与真人听验',
            'approvedCompositeProbeEvidence': {'path': str(COMPOSITE_REVIEW), 'sha256': sha_bytes(raw)},
        }

    def test_exact_v1_first_five_plus_v4_sixth_composite_initializes_without_formal_claim(self):
        self.use_real_composite_human_evidence()
        original = {path: path.read_bytes() for path in COMPOSITE_REVIEW.parent.parent.rglob('*')
                    if path.is_file() and ('pinyin-ssml-probe-v' in str(path)
                                           or 'pinyin-ssml-probe-composition-v1' in str(path))}
        prepared = self.run_initialization(False)
        self.assertTrue(prepared['prepared'])
        result = self.run_initialization()
        self.assertTrue(result['probeHumanListeningVerified'])
        self.assertTrue(result['perceptualToneVerifiedForProbeScope'])
        self.assertTrue(result['requiresFormalHumanListening'])
        self.assertTrue(result['requiresFormalSentenceListening'])
        self.assertFalse(result['publicationAllowed'])
        self.assertFalse(result['generationDispatched'])
        intent = json.loads((self.archive() / 'intent.json').read_text())
        expected = {'row.json', 'source.json', 'frozen.json', 'base-plan.json', 'plan.json'} | \
            aieiui_composite.evidence_names()
        self.assertEqual(set(intent['files']), expected)
        self.assertEqual((self.archive() / 'evidence/human-approval.json').read_bytes(),
                         COMPOSITE_REVIEW.read_bytes())
        self.assertEqual(self.run_initialization(), result)
        for path, raw in original.items():
            self.assertEqual(path.read_bytes(), raw)
        self.assert_no_external_write()

    def test_composite_human_evidence_cannot_be_downgraded_to_single_plan_schema(self):
        self.use_real_composite_human_evidence()
        evidence = self.patch.pop('approvedCompositeProbeEvidence')
        self.patch.update(schemaVersion=initialization.SCHEMA, approvedProbeEvidence=evidence)
        with self.assertRaises(ApiError):
            self.run_initialization()
        self.assert_no_external_write()

    def test_v4_exact_sub_alias_sixth_request_passes_fixed_probe_validation(self):
        files = initialization._evidence_files(self.patch, self.policy)
        plan = json.loads(files['evidence/plan.json'])
        sixth = next(item for item in plan['samples'] if item['label'] == 'luo-bo-neutral')
        self.assertEqual(sixth['sourceText'], 'luó bo')
        self.assertEqual(sixth['body']['input']['text'], LUO_BO_V4_SSML)
        root = ElementTree.fromstring(LUO_BO_V4_SSML)
        self.assertEqual(root.findall('phoneme'), [])
        self.assertEqual([(item.attrib, item.text, item.tail) for item in root.findall('sub')],
                         [({'alias': '萝卜'}, 'luó bo', '。')])
        probes, _ = initialization._probe_contract(self.policy)
        initialization._verify_probe_files(
            files, json.loads(files['evidence/human-approval.json']),
            json.loads(self.row['input_json']), self.policy, probes,
            sample_result='approved_by_human_listening')

    def test_fixed_source_text_cannot_be_relabelled_with_valid_same_policy_ssml(self):
        files = initialization._evidence_files(self.patch, self.policy)
        plan = json.loads(files['evidence/plan.json'])
        approval = json.loads(files['evidence/human-approval.json'])
        sample = next(item for item in plan['samples'] if item['label'] == 'pai-dui-whole')
        sample['sourceText'] = 'pái，duì'
        raw = canonical(plan).encode()
        files['evidence/plan.json'] = raw
        approval['probePlanSha256'] = sha_bytes(raw)
        probes, _ = initialization._probe_contract(self.policy)
        with self.assertRaises(ApiError):
            initialization._verify_probe_files(
                files, approval, json.loads(self.row['input_json']), self.policy,
                probes, sample_result='approved_by_human_listening')


class AiEiUiCompositeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.files = aieiui_composite.read_files(COMPOSITE_REVIEW)
        self.review = json.loads(self.files['evidence/human-approval.json'])
        self.frozen = dict(aieiui_composite.LESSON)
        self.policy = registry.registered_policy(V4)

    def verify(self, files=None, review=None, policy=None):
        return aieiui_composite.verify_files(
            files or self.files, review or self.review, self.frozen, policy or self.policy)

    def test_exact_existing_composition_verifies_every_history_and_audio_byte(self):
        self.assertIsNone(self.verify())
        self.assertEqual(len(self.files), 74)

    def test_byte_identical_cloned_evidence_tree_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            clone = Path(folder) / 'quality-repairs'
            shutil.copytree(COMPOSITE_REVIEW.parent.parent, clone)
            copied_review = (clone / 'pinyin-ssml-probe-composition-v1' /
                             'human-approval-before-adoption-binding.json')
            self.assertEqual(copied_review.read_bytes(), COMPOSITE_REVIEW.read_bytes())
            with self.assertRaises(ApiError):
                aieiui_composite.read_files(copied_review)

    def test_plan_request_receipt_wav_pcm_confirmation_seal_and_failure_tampering_fail(self):
        mutations = (
            ('evidence/plan.json', lambda raw: raw + b' '),
            ('evidence/origins/aieiui-v1/ai-final-and-tones/request.json', lambda raw: raw + b' '),
            ('evidence/origins/aieiui-v4/luo-bo-neutral/receipt.json', lambda raw: canonical({
                **json.loads(raw), 'status': 'failed'}).encode()),
            ('evidence/origins/aieiui-v4/luo-bo-neutral/playback.wav', lambda raw: raw[:-1] + bytes([raw[-1] ^ 1])),
            ('evidence/user-confirmation.json', lambda raw: raw.replace(
                b'"formalCourseNarrationApproved": false', b'"formalCourseNarrationApproved": true')),
            ('evidence/validation.json', lambda raw: raw.replace(
                b'"historicalFailuresPreserved": true', b'"historicalFailuresPreserved": false')),
            ('evidence/origins/aieiui-v2/machine-audio-audit.json', lambda raw: raw + b' '),
        )
        for name, mutate in mutations:
            files = dict(self.files)
            files[name] = mutate(files[name])
            review = json.loads(files['evidence/human-approval.json'])
            with self.subTest(name=name), self.assertRaises(ApiError):
                self.verify(files, review)

    def test_human_approval_self_digest_is_mandatory(self):
        review = deepcopy(self.review)
        review['humanListeningVerified'] = False
        files = dict(self.files)
        files['evidence/human-approval.json'] = canonical(review).encode()
        with self.assertRaises(ApiError):
            self.verify(files, review)

    def test_wrong_policy_and_garden3_composite_are_rejected(self):
        for version in (V1, registry.GARDEN3_V2_POLICY_VERSION):
            with self.subTest(version=version), self.assertRaises(ApiError):
                self.verify(policy=registry.registered_policy(version))


if __name__ == '__main__':
    unittest.main()
