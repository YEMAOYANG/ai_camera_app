"""IE/ÜE/ER source scope and finite initialization, using synthetic media only."""
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
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan


VERSION = 'mira.textbook.pinyin-ieueer-ssml.v1'
POLICY_SHA = '27b702593fc628848ecad8dff8b21859d2bae2cc4de33f373e65c62a8f24da46'
AOUIU_SHA = 'e23f67fe90ab412d17e1260bf2d1ee4a510c0407bfbfacac9ebce16016583a0d'
WHOLE_RECIPES = {
    'ie': 'ye1', 'üe': 'yue1', 'er': 'er1', 'ye': 'ye1', 'yue': 'yue1',
    'piě': 'pie3', 'dié': 'die2', 'bié': 'bie2', 'xié': 'xie2', 'qiē': 'qie1', 'jiě': 'jie3',
    'lüè': 'lve4', 'nüè': 'nve4', 'jué': 'jue2', 'quē': 'que1', 'xué': 'xue2',
    'xiě': 'xie3', 'zuò': 'zuo4', 'yè': 'ye4', 'méi': 'mei2', 'huā': 'hua1', 'kāi': 'kai1',
    'xuě': 'xue3', 'piāo': 'piao1', 'sè': 'se4', 'měi': 'mei3', 'yuè': 'yue4', 'ér': 'er2',
}
SUPPORT = 'p b d l n x q j y'.split()
PROBE_TEXTS = {
    'ie-whole-context': '请听：ie、ye。piě、dié、bié、xié、qiē、jiě。',
    'ue-whole-context': '请听：üe、yue。lüè、nüè、jué、quē、xué。',
    'er-source-context': '请听：er、ér。xiě zuò yè。méi huā kāi。xuě huā piāo。yè sè měi。yuè。',
}
PROBE_TOKENS = {
    'ie-whole-context': ('ie', 'ye', 'piě', 'dié', 'bié', 'xié', 'qiē', 'jiě'),
    'ue-whole-context': ('üe', 'yue', 'lüè', 'nüè', 'jué', 'quē', 'xué'),
    'er-source-context': ('er', 'ér', 'xiě', 'zuò', 'yè', 'méi', 'huā', 'kāi',
                          'xuě', 'huā', 'piāo', 'yè', 'sè', 'měi', 'yuè'),
}
PROBE_TARGETS = {label: tokens[0] for label, tokens in PROBE_TOKENS.items()}


def seal(value):
    value['sha256'] = digest({key: item for key, item in value.items() if key != 'sha256'})
    return value


class IeUeErPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = registry.registered_policy(VERSION)

    def test_lesson_identity_and_old_policy_hashes_are_preserved(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u4-l3'}
        self.assertEqual(digest(registry.select_policy(binding)), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        plan = pinyin_plan()
        plan.update(binding=binding, pronunciationPolicy=self.policy,
                    pronunciationPolicySha256=POLICY_SHA)
        self.assertEqual(registry.policy_for_plan(plan), self.policy)
        for field in registry._BINDING_FIELDS:
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy({**binding, field: binding[field] + '-other'})
        historical = {**PRIOR_HASHES, registry.AIEIUI_V4_POLICY_VERSION: AIEIUI_V4_SHA,
                      registry.AOUIU_POLICY_VERSION: AOUIU_SHA}
        self.assertTrue((set(historical) | {VERSION}) <= set(registry._POLICIES))
        for version, expected in historical.items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            old = registry.registered_policy(version)
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan({**plan, 'pronunciationPolicy': old,
                                          'pronunciationPolicySha256': digest(old)})
        with self.assertRaises(ApiError):
            registry.policy_for_plan({**plan, 'binding': {**binding, 'nodeId': 'u4-l2'}})
        self.policy['symbols']['ué'] = {'ph': 'yue2', 'carrier': '月'}
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_source_scope_uses_single_whole_phonemes_not_a_tone_table(self):
        self.assertEqual(set(self.policy['symbols']), set(WHOLE_RECIPES) | set(SUPPORT))
        self.assertEqual(len(self.policy['symbols']), 37)
        for token, ph in WHOLE_RECIPES.items():
            with self.subTest(token=token):
                elements = ElementTree.fromstring(registry.pinyin_ssml(token, policy_version=VERSION))
                self.assertEqual(len(elements), 1)
                self.assertEqual(elements[0].attrib, {'alphabet': 'py', 'ph': ph})
                self.assertEqual(elements[0].text, self.policy['symbols'][token]['carrier'])
        prior = [registry.registered_policy(v) for v in registry._POLICIES if v != VERSION]
        for token in SUPPORT + ['huā', 'kāi', 'sè']:
            self.assertTrue(any(p['symbols'].get(token) == self.policy['symbols'][token] for p in prior))
        previous = registry.registered_policy(registry.AOUIU_POLICY_VERSION)
        for field in ('providerId', 'modelId', 'voiceId', 'endpointPath', 'inputParameters', 'textHandling'):
            self.assertEqual(self.policy[field], previous[field])
        self.assertEqual(self.policy['words'], {})
        self.assertNotIn('exactTextSsml', self.policy)
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'pronunciationApproved', 'formalUseAllowed'):
            self.assertIs(self.policy['approvalBoundary'][field], False)

    def test_unvoiced_components_full_tone_expansion_and_unknown_runs_fail_closed(self):
        for text in ('uē', 'ué', 'u é', 'üè', 'iě', 'ié', 'iē', 'ie1', 'ye2',
                     'yē', 'yé', 'yě', 'ǖe', 'üe4', 'ēr', 'ěr', 'èr', 'lue', 'nue',
                     'jve2', 'quēxué', 'xuéyè', 'e\u0304', 'Ａ', 'IE', '11', 'ɑo'):
            with self.subTest(text=text), self.assertRaises(ApiError):
                registry.provider_body('请听：' + text + '。', policy_version=VERSION)
        body = registry.provider_body('看看<&>：yè。梅花开，雪花飘，夜色美。', policy_version=VERSION)
        self.assertEqual(body['input']['text'],
            '<speak>看看&lt;&amp;&gt;：<phoneme alphabet="py" ph="ye4">夜</phoneme>。梅花开，雪花飘，夜色美。</speak>')

    def test_three_finite_probes_bind_every_source_token_in_exact_order(self):
        self.assertEqual(dict(initialization._IEUEER_PROBE_TEXTS), PROBE_TEXTS)
        self.assertEqual(dict(initialization._IEUEER_PROBE_TOKENS), PROBE_TOKENS)
        probes, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(probes), PROBE_TARGETS)
        self.assertEqual({t for seq in PROBE_TOKENS.values() for t in seq}, set(WHOLE_RECIPES))
        for label, source in PROBE_TEXTS.items():
            root = ElementTree.fromstring(registry.pinyin_ssml(source, policy_version=VERSION))
            self.assertEqual([p.attrib['ph'] for p in root], [WHOLE_RECIPES[t] for t in PROBE_TOKENS[label]])


class IeUeErAutomaticInitializationTests(unittest.TestCase):
    def setUp(self):
        fx = self.fx = fixtures.PronunciationInitializationTests()
        fx.node_id, fx.probe_targets = 'u4-l3', PROBE_TARGETS
        fx.probe_token_sequences, fx.probe_source_texts = PROBE_TOKENS, PROBE_TEXTS
        fx.approval_result = 'three_ieueer_fixed_probes_pronunciation_and_source_context_approved'
        fx.approval_statement = 'Synthetic fixture; no real listening or provider call.'
        fx.first_speech = '请听：ie、üe、er。'
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
            basis='Synthetic request and unchanged PCM verification; no audible accuracy claim.',
            verifiedProbeEvidence={'path': str(fx.probes / 'operator-probe-review.json'), 'sha256': ''})
        self.write_review()

    def write_review(self):
        seal(self.review); raw = canonical(self.review).encode()
        (self.fx.probes / 'operator-probe-review.json').write_bytes(raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def test_prepare_install_resume_and_narration_reuse_keep_originals(self):
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
        # The real narrator runs only against the fixture's in-memory fake provider.
        fx.test_real_narrator_sample_then_full_reuses_success_and_initialization_is_idempotent()

    def test_human_claims_missing_probe_and_changed_pcm_cannot_install(self):
        original = deepcopy(self.review)
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'formalUseAllowed'):
            self.review = {**deepcopy(original), field: True}; self.write_review()
            with self.subTest(field=field), self.assertRaises(ApiError): self.fx.run_initialization()
        self.review = deepcopy(original); self.review['samples'].pop(); self.write_review()
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.review = deepcopy(original); self.write_review()
        wav = self.fx.probes / 'ue-whole-context' / 'playback.wav'
        wav.write_bytes(wav.read_bytes() + b'changed')
        with self.assertRaises(ApiError): self.fx.run_initialization()
        self.assertFalse((self.fx.f.folder / 'plan.json').exists()); self.fx.assert_no_external_write()

    def test_resigned_probe_source_or_sequence_cannot_change_fixed_inventory(self):
        fx = self.fx; original = initialization._evidence_files(fx.patch, fx.policy)
        probes, _ = initialization._probe_contract(fx.policy)
        for mutation in ('source', 'tokens'):
            files = deepcopy(original); plan = json.loads(files['evidence/plan.json'])
            review = json.loads(files['evidence/operator-probe-review.json'])
            if mutation == 'source': plan['samples'][1]['sourceText'] = '请听：üe、yue。'
            else: plan['samples'][1]['tokens'][-2:] = reversed(plan['samples'][1]['tokens'][-2:])
            files['evidence/plan.json'] = canonical(plan).encode()
            review['probePlanSha256'] = sha_bytes(files['evidence/plan.json'])
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                initialization._verify_probe_files(files, review, json.loads(fx.row['input_json']),
                    fx.policy, probes, sample_result=initialization.OPERATOR_RESULT)
        fx.assert_no_external_write()

    def test_unvoiced_component_in_actual_speech_blocks_initialization(self):
        fx = self.fx; f = fx.f
        f.classroom['scenes'][0]['actions'][0]['text'] = '单独读这个：uē。'
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
