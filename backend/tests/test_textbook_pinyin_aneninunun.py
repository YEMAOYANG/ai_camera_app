"""Exact front-nasal lesson identity and initialization; no external provider calls."""
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
from services.textbook_preview_audio import core_content
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization as fixtures
from tests.test_textbook_pinyin_aieiui import PRIOR_HASHES, POLICY_SHA as AIEIUI_V4_SHA
from tests.test_textbook_pinyin_ieueer import POLICY_SHA as IEUEER_SHA, AOUIU_SHA
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan


VERSION = 'mira.textbook.pinyin-aneninunun-ssml.v1'
POLICY_SHA = 'f91fb1741934f79d0a2664aa68b69dccfec0042eb04f0000510669ef631d2865'
# Independent source-derived inventory: five finals; three base and three toned
# whole syllables; six three-part results; 29 petals; static lún chuán phrase.
RECIPES = {
    'ɑn': 'an1', 'en': 'en1', 'in': 'yin1', 'un': 'wen1', 'ün': 'yun1',
    'yuan': 'yuan1', 'yin': 'yin1', 'yun': 'yun1', 'yuán': 'yuan2', 'yīn': 'yin1', 'yùn': 'yun4',
    'guān': 'guan1', 'kuān': 'kuan1', 'huān': 'huan1', 'juān': 'juan1', 'quān': 'quan1', 'xuān': 'xuan1',
    'wān': 'wan1', 'yǎn': 'yan3', 'nán': 'nan2', 'zhàn': 'zhan4', 'duǎn': 'duan3', 'rǎn': 'ran3', 'jiān': 'jian1',
    'nèn': 'nen4', 'chén': 'chen2', 'kěn': 'ken3', 'zhēn': 'zhen1', 'rén': 'ren2', 'wén': 'wen2',
    'mín': 'min2', 'pīn': 'pin1', 'nín': 'nin2', 'jìn': 'jin4', 'xīn': 'xin1', 'qīn': 'qin1',
    'chūn': 'chun1', 'rùn': 'run4', 'tūn': 'tun1', 'hūn': 'hun1', 'zhǔn': 'zhun3', 'lún': 'lun2',
    'jūn': 'jun1', 'qún': 'qun2', 'xún': 'xun2', 'chuán': 'chuan2',
}
PROBE_TEXTS = {
    'finals-whole-bases': '请听：ɑn、en、in、un、ün。yuan、yin、yun。',
    'three-part-whole-context': '请听：yuán、yīn、yùn。guān、kuān、huān、juān、quān、xuān。',
    'petals-and-writing-context': (
        '请听：wān、yǎn、nán、zhàn、duǎn、rǎn、jiān、quān；'
        'nèn、chén、kěn、zhēn、rén、wén；mín、pīn、nín、jìn、xīn、qīn；'
        'chūn、rùn、tūn、hūn、zhǔn、lún；jūn、qún、xún。lún chuán。'),
}
PROBE_TOKENS = {
    'finals-whole-bases': ('ɑn', 'en', 'in', 'un', 'ün', 'yuan', 'yin', 'yun'),
    'three-part-whole-context': ('yuán', 'yīn', 'yùn', 'guān', 'kuān', 'huān', 'juān', 'quān', 'xuān'),
    'petals-and-writing-context': (
        'wān', 'yǎn', 'nán', 'zhàn', 'duǎn', 'rǎn', 'jiān', 'quān',
        'nèn', 'chén', 'kěn', 'zhēn', 'rén', 'wén', 'mín', 'pīn', 'nín', 'jìn', 'xīn', 'qīn',
        'chūn', 'rùn', 'tūn', 'hūn', 'zhǔn', 'lún', 'jūn', 'qún', 'xún', 'lún', 'chuán'),
}
PROBE_TARGETS = {label: tokens[0] for label, tokens in PROBE_TOKENS.items()}


def seal(value):
    value['sha256'] = digest({key: item for key, item in value.items() if key != 'sha256'})
    return value


class AnEnInUnUnPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = registry.registered_policy(VERSION)

    def test_exact_five_field_lesson_identity_and_historical_policies(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u4-l4'}
        self.assertEqual(digest(registry.select_policy(binding)), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        plan = {**pinyin_plan(), 'binding': binding, 'pronunciationPolicy': self.policy,
                'pronunciationPolicySha256': POLICY_SHA}
        self.assertEqual(registry.policy_for_plan(plan), self.policy)
        for field in registry._BINDING_FIELDS:
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy({**binding, field: binding[field] + '-other'})
        historical = {**PRIOR_HASHES, registry.AIEIUI_V4_POLICY_VERSION: AIEIUI_V4_SHA,
                      registry.AOUIU_POLICY_VERSION: AOUIU_SHA, registry.IEUEER_POLICY_VERSION: IEUEER_SHA}
        self.assertTrue((set(historical) | {VERSION}) <= set(registry._POLICIES))
        for version, expected in historical.items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            old = registry.registered_policy(version)
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan({**plan, 'pronunciationPolicy': old,
                                          'pronunciationPolicySha256': digest(old)})
        for node in ('u4-l3', 'u4-l5'):
            with self.subTest(node=node), self.assertRaises(ApiError):
                registry.policy_for_plan({**plan, 'binding': {**binding, 'nodeId': node}})
        self.policy['symbols']['ɑn']['ph'] = 'wrong1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_previous_lessons_keep_their_selected_recipe(self):
        selected = {
            'u2-l1': registry.AOE_POLICY_VERSION, 'u2-l2': registry.IUU_POLICY_VERSION,
            'u2-l3': registry.BPMF_POLICY_VERSION, 'u2-l4': registry.DTNL_POLICY_VERSION,
            'u2-l5': registry.GARDEN2_POLICY_VERSION, 'u3-l1': registry.GKH_POLICY_VERSION,
            'u3-l2': registry.JQX_POLICY_VERSION, 'u3-l3': registry.ZCS_POLICY_VERSION,
            'u3-l4': registry.ZHCHSHR_POLICY_VERSION, 'u3-l5': registry.YW_POLICY_VERSION,
            'u3-l6': registry.GARDEN3_V2_POLICY_VERSION, 'u4-l1': registry.AIEIUI_V4_POLICY_VERSION,
            'u4-l2': registry.AOUIU_POLICY_VERSION, 'u4-l3': registry.IEUEER_POLICY_VERSION,
        }
        for node, version in selected.items():
            with self.subTest(node=node):
                self.assertEqual(registry.select_policy({**PINYIN_BINDING, 'nodeId': node})['policyVersion'], version)

    def test_exact_46_tokens_are_indivisible_and_have_no_implicit_support(self):
        self.assertEqual(set(self.policy['symbols']), set(RECIPES))
        self.assertEqual(len(RECIPES), 46)
        for token, ph in RECIPES.items():
            with self.subTest(token=token):
                elements = ElementTree.fromstring(registry.pinyin_ssml(token, policy_version=VERSION))
                self.assertEqual(len(elements), 1)
                self.assertEqual(elements[0].attrib, {'alphabet': 'py', 'ph': ph})
                self.assertEqual(elements[0].text, self.policy['symbols'][token]['carrier'])
        previous = registry.registered_policy(registry.IEUEER_POLICY_VERSION)
        for field in ('providerId', 'modelId', 'voiceId', 'endpointPath', 'inputParameters', 'textHandling'):
            self.assertEqual(self.policy[field], previous[field])
        self.assertEqual(self.policy['words'], {})
        self.assertNotIn('exactTextSsml', self.policy)
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'pronunciationApproved', 'formalUseAllowed'):
            self.assertIs(self.policy['approvalBoundary'][field], False)

    def test_unvoiced_components_neutral_tone_aliases_and_unknown_runs_fail_closed(self):
        for token in ('an', 'ān', 'án', 'ǎn', 'àn', 'an1', 'ɑn1', 'ɑnɑn', 'en2', 'ün1', 'vn',
                      'g', 'k', 'h', 'j', 'q', 'x', 'u', 'ü', 'men', 'men5', 'mén',
                      'yuān', 'yǔn', 'jüān', 'qüān', 'xüān', 'yuan2', 'guānquān',
                      'ang', 'ɑng', 'eng', 'ing', 'ong', 'ying', 'AN', 'ａｎ', 'a\u0304n', 'u\u0308n'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.provider_body('请听：' + token + '。', policy_version=VERSION)
        for version in ('mira.textbook.pinyin-aneninunun-ssml.v2', 'unknown'):
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.provider_body('请听。', policy_version=version)

    def test_chinese_we_and_picture_words_remain_natural_not_neutral_overrides(self):
        chinese = '蓝天、白云、草原、森林。读到我们这个词时，后一个音节轻一些。'
        self.assertEqual(registry.pinyin_ssml(chinese, policy_version=VERSION), '<speak>' + chinese + '</speak>')
        self.assertEqual(registry.pinyin_ssml('看<&>：ɑn。', policy_version=VERSION),
                         '<speak>看&lt;&amp;&gt;：<phoneme alphabet="py" ph="an1">安</phoneme>。</speak>')
        receipt = registry.provider_pronunciation('lún chuán。', policy_version=VERSION)
        registry.validate_provider_pronunciation(receipt, 'lún chuán。', policy_version=VERSION)
        with self.assertRaises(ApiError):
            registry.validate_provider_pronunciation(receipt, 'lún。', policy_version=VERSION)

    def test_fixed_three_probes_cover_every_token_with_exact_source_and_order(self):
        self.assertEqual(dict(initialization._ANENINUNUN_PROBE_TEXTS), PROBE_TEXTS)
        self.assertEqual(dict(initialization._ANENINUNUN_PROBE_TOKENS), PROBE_TOKENS)
        probes, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(probes), PROBE_TARGETS)
        self.assertEqual(sum(map(len, PROBE_TOKENS.values())), 48)
        self.assertEqual({t for tokens in PROBE_TOKENS.values() for t in tokens}, set(RECIPES))
        for label, text in PROBE_TEXTS.items():
            root = ElementTree.fromstring(registry.pinyin_ssml(text, policy_version=VERSION))
            self.assertEqual([p.attrib['ph'] for p in root], [RECIPES[t] for t in PROBE_TOKENS[label]])


class AnEnInUnUnAutomaticInitializationTests(unittest.TestCase):
    def setUp(self):
        fx = self.fx = fixtures.PronunciationInitializationTests()
        fx.node_id, fx.probe_targets = 'u4-l4', PROBE_TARGETS
        fx.probe_token_sequences, fx.probe_source_texts = PROBE_TOKENS, PROBE_TEXTS
        fx.approval_result = 'three_aneninunun_fixed_probes_pronunciation_and_source_context_approved'
        fx.approval_statement = 'Synthetic fixture; no provider call or listening verdict.'
        fx.first_speech = '请听：ɑn、en、in、un、ün。'
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
            basis='Synthetic request and unchanged PCM checks; no audible accuracy claim.',
            verifiedProbeEvidence={'path': str(fx.probes / 'operator-probe-review.json'), 'sha256': ''})
        self.write_review()

    def write_review(self):
        seal(self.review); raw = canonical(self.review).encode()
        (self.fx.probes / 'operator-probe-review.json').write_bytes(raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def test_initialize_resume_and_narration_reuse_preserve_original_source_and_evidence(self):
        fx = self.fx
        source = (fx.f.root / (fx.f.cid + '.json')).read_bytes()
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
        fx.test_real_narrator_sample_then_full_reuses_success_and_initialization_is_idempotent()

    def test_uninitialized_default_voice_is_stopped_before_provider_access(self):
        self.fx.test_default_and_injected_v2_narration_stop_before_any_tts_get_or_post()

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

    def test_resigned_source_or_token_sequence_cannot_change_fixed_probe_contract(self):
        fx = self.fx; original = initialization._evidence_files(fx.patch, fx.policy)
        probes, _ = initialization._probe_contract(fx.policy)
        for mutation in ('source', 'tokens'):
            files = deepcopy(original); plan = json.loads(files['evidence/plan.json'])
            review = json.loads(files['evidence/operator-probe-review.json'])
            if mutation == 'source': plan['samples'][1]['sourceText'] = '请听：yuán、yīn、yùn。'
            else: plan['samples'][1]['tokens'][-2:] = reversed(plan['samples'][1]['tokens'][-2:])
            files['evidence/plan.json'] = canonical(plan).encode()
            review['probePlanSha256'] = sha_bytes(files['evidence/plan.json'])
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                initialization._verify_probe_files(files, review, json.loads(fx.row['input_json']),
                    fx.policy, probes, sample_result=initialization.OPERATOR_RESULT)
        fx.assert_no_external_write()

    def test_unvoiced_component_in_actual_speech_blocks_initialization(self):
        fx = self.fx; f = fx.f
        f.classroom['scenes'][0]['actions'][0]['text'] = 'j。'
        f.save(f.classroom)
        f.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                     (canonical(f.classroom), digest(f.classroom), f.key)); f.db.raw.commit()
        fx.patch.update(expectedSourceSha256=digest(f.classroom), expectedCoreSha256=digest(core_content(f.classroom)))
        self.review.update(sourceSha256=fx.patch['expectedSourceSha256'], coreSha256=fx.patch['expectedCoreSha256'])
        self.write_review()
        with self.assertRaises(ApiError): fx.run_initialization()
        self.assertFalse((f.folder / 'plan.json').exists()); fx.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
