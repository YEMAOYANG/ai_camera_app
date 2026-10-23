"""YW exact recipe and five-probe contracts. Synthetic fixtures, no provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree
from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import digest, validate_manifest
from content.textbook_preview import lesson_blueprint, blueprint_prompt
from core.errors import ApiError
from services import textbook_preview_pronunciation_initialization as initialization
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan
from tests import test_textbook_preview_pronunciation_initialization as fixtures
from tests import test_textbook_pinyin_gkh as gkh_fixtures
from tests import test_textbook_pinyin_zcs as zcs_fixtures

VERSION = 'mira.textbook.pinyin-yw-ssml.v1'
POLICY_SHA = '77b30e78c17440453999a96b4dfb77fb95bd538e814419289a6bcbc942052335'
DATA = json.loads((Path(__file__).parent / 'fixtures/textbook_pinyin_yw/corpus.v1.json').read_text())
PROBE_TOKENS = {k: tuple(v) for k, v in DATA['probes'].items()}

class YwPronunciationTests(unittest.TestCase):
    def test_exact_binding_previous_policies_and_profile_rejection(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u3-l5'}
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
        for version, expected in DATA['priorHashes'].items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan({**plan, 'pronunciationPolicy': registry.registered_policy(version),
                                         'pronunciationPolicySha256': expected})
        with self.assertRaises(ApiError): registry.registered_policy(VERSION + '-unknown')
        policy['symbols']['yu']['ph'] = 'wu1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_whole_tokens_and_natural_words(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {t for t, _, _ in DATA['tokens']})
        self.assertEqual(policy['words'], {})
        for token, ph, carrier in DATA['tokens']:
            with self.subTest(token=token):
                self.assertEqual(registry.pinyin_ssml('请听：'+token+'。', policy_version=VERSION),
                    f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
        self.assertEqual([x['ph'] for x in registry.pronunciation_symbols('yu、yǔ、u、wǔ。', policy_version=VERSION)],
                         ['yu1', 'yu3', 'wu1', 'wu3'])
        text = '鱼、鸭子、乌鸦、蚂蚁、孩子、房子。'
        self.assertEqual(registry.pinyin_ssml(text, policy_version=VERSION), '<speak>'+text+'</speak>')
        self.assertEqual(policy['inputParameters'], registry.registered_policy()['inputParameters'])
        for key in ('formalUseAllowed','pronunciationApproved','humanListeningVerified','perceptualToneVerified','shortConsonantAccepted'):
            self.assertFalse(policy['approvalBoundary'][key])

    def test_unknown_and_combined_runs_never_fall_back(self):
        for token in ('y1','yi1','yū','yú','wā','yuü','yáwá','YW','hello','constructor','ｙ','𝒚','y\u0304','y\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：'+token+'。', policy_version=VERSION)

    def test_112_exact_sentences_provider_identity_and_all_26_controlled(self):
        tokens, controlled = set(), 0
        self.assertEqual(len(DATA['speech']), 112)
        for entry in DATA['speech']:
            text = entry['text']
            found = registry.pronunciation_symbols(text, policy_version=VERSION)
            controlled += bool(found); tokens.update(x['symbol'] for x in found)
            identity = registry.provider_pronunciation(text, policy_version=VERSION)
            self.assertEqual(identity, entry['providerPronunciation'], entry['actionId'])
            registry.validate_provider_pronunciation(identity, text, policy_version=VERSION)
            for key in ('policySha256','ssmlSha256','sourceTextSha256','providerBodySha256'):
                with self.subTest(action=entry['actionId'], field=key), self.assertRaises(ApiError):
                    registry.validate_provider_pronunciation({**identity,key:'0'*64}, text, policy_version=VERSION)
        self.assertEqual(controlled, 26)
        self.assertEqual(tokens, set(registry.registered_policy(VERSION)['symbols']))

    def test_unit_scope_loader_question_mapping_and_pending_readiness(self):
        # Use the real catalog with the explicitly selected candidate unit directory.
        import content.textbook_catalog as catalog
        manifest_path = Path(catalog.__file__).parent / 'textbooks/revisions/pep-chinese-g1-upper.directory.v3.json'
        manifest = validate_manifest(json.loads(manifest_path.read_text()))
        units = Path(__file__).parents[1] / 'content/textbooks/learning-units'
        b = lesson_blueprint(manifest, 'u3-l5', units_path=units)
        self.assertEqual(blueprint_prompt(b)['expectedQuestionCount'], 4)
        self.assertEqual([x['answer'] for x in b['assessmentMapping']], list('BCAB'))
        self.assertEqual([x['page'] for x in b['assessmentMapping']], [5,10,13,19])
        self.assertEqual(b['sourceScope']['scope']['ordinarySyllables'], ['yá','wá','wō'])
        self.assertEqual(b['sourceScope']['scope']['recognitionCharacters'], list('鱼鸭乌鸦'))
        self.assertEqual(b['sourceScope']['scope']['reading']['author'], '杨霞丹')
        self.assertFalse(b['sourceScope']['scope']['reading']['originalTextCopied'])
        self.assertFalse(b['generationReady'])
        self.assertEqual(b['knowledgeBrief']['review']['status'], 'reviewed')
        self.assertEqual(b['knowledgeBrief']['review']['scope'], 'static-textbook-and-original-implementation-plan-only')
        self.assertFalse(b['knowledgeBrief']['review']['dynamicOfficialStrokeObserved'])
        self.assertFalse(b['knowledgeBrief']['review']['formalAudioApproved'])
        self.assertIsNone(lesson_blueprint({**manifest,'revisionId':'other'}, 'u3-l5', units_path=units))

class YwInitializationTests(fixtures.PronunciationInitializationTests):
    node_id = 'u3-l5'
    probe_targets = {label: pair[0] for label, pair in PROBE_TOKENS.items()}
    probe_token_sequences = PROBE_TOKENS
    approval_result = 'five_yw_call_context_and_whole_recognition_probes_pronunciation_and_tones_approved'
    approval_statement = 'SYNTHETIC fixture only; no real YW audio, listening or approval.'
    first_speech = '先听整体认读音节：yu。再听第三声：yǔ。鸭子保持自然中文。'
    _evidence_with_ssml = gkh_fixtures.GkhPronunciationInitializationTests._evidence_with_ssml
    test_operator_v2_keeps_formal_review_pending = zcs_fixtures.ZcsInitializationTests.test_operator_v2_does_not_turn_probe_protocol_into_human_or_formal_approval

    def test_fixed_five_pairs_missing_or_extra_never_initialize(self):
        actual, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(actual), self.probe_targets)
        self.assertEqual(dict(initialization._YW_PROBE_TOKENS), PROBE_TOKENS)
        original = deepcopy(self.approval)
        for index in range(5):
            self.approval = deepcopy(original); self.approval['samples'].pop(index); self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError): self.run_initialization()
        self.approval = deepcopy(original); self.approval['samples'].append(deepcopy(original['samples'][0])); self.write_approval()
        with self.assertRaises(ApiError): self.run_initialization()
        self.assert_no_external_write()

    def test_rebound_hashes_do_not_allow_wrong_order_or_umlaut_loss(self):
        for label in PROBE_TOKENS:
            original = next(s for s in self.plan['samples'] if s['label'] == label)['body']['input']['text']
            nodes = ElementTree.fromstring(original).findall('phoneme')
            parts = [ElementTree.tostring(n,encoding='unicode') for n in nodes]
            variants = [('missing',parts[0]),('extra',''.join(parts+parts[:1])),
                        ('empty-carrier',''.join(parts).replace('>'+nodes[0].text+'<','><',1)),
                        ('wrong-tone',''.join(parts).replace(nodes[-1].attrib['ph'],'bo2'))]
            if parts[0] != parts[1]: variants.append(('reversed',''.join(reversed(parts))))
            if label == 'yu-whole-and-tone': variants.append(('umlaut-loss',''.join(parts).replace('yu1','wu1').replace('yu3','wu3')))
            for name, body in variants:
                files, patch = self._evidence_with_ssml(label,'<speak>听音。'+body+'</speak>')
                with self.subTest(label=label,variant=name), self.assertRaisesRegex(ApiError,'音素顺序'):
                    initialization._verify_evidence(files,patch,self.f.key,json.loads(self.row['input_json']),self.policy)
        self.assert_no_external_write()

if __name__ == '__main__': unittest.main()
