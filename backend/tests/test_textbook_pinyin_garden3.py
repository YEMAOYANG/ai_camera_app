"""Garden 3 exact recipe and seven-phrase probe contracts. Synthetic fixtures, no provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
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

VERSION = 'mira.textbook.pinyin-garden3-ssml.v1'
POLICY_SHA = '472da6bc4ce841cc9916593db4ec1837576a7ab66761975725d68622264b6e6a'
DATA = json.loads((Path(__file__).parent / 'fixtures/textbook_pinyin_garden3/corpus.v1.json').read_text())
PROBE_TOKENS = {k: tuple(v) for k, v in DATA['probes'].items()}

class Garden3PronunciationTests(unittest.TestCase):
    def test_exact_binding_previous_policies_and_profile_rejection(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u3-l6'}
        self.assertEqual(registry.select_policy(binding)['policyVersion'], registry.GARDEN3_V2_POLICY_VERSION)
        policy = registry.registered_policy(VERSION)
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
        policy['symbols']['bo']['ph'] = 'bo1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_exact_whole_tokens_and_natural_words(self):
        policy = registry.registered_policy(VERSION)
        self.assertEqual(set(policy['symbols']), {t for t, _, _ in DATA['tokens']})
        self.assertEqual(policy['words'], {})
        for token, ph, carrier in DATA['tokens']:
            with self.subTest(token=token):
                self.assertEqual(registry.pinyin_ssml('请听：'+token+'。', policy_version=VERSION),
                    f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
        self.assertEqual([x['ph'] for x in registry.pronunciation_symbols('z、zh、c、ch、s、sh、li、bo。', policy_version=VERSION)],
                         ['zi1', 'zhi1', 'ci1', 'chi1', 'si1', 'shi1', 'li5', 'bo5'])
        text = '玻璃、萝卜、一模一样、星期、数学、孩子。'
        self.assertEqual(registry.pinyin_ssml(text, policy_version=VERSION), '<speak>'+text+'</speak>')
        self.assertEqual(policy['inputParameters'], registry.registered_policy()['inputParameters'])
        for key in ('formalUseAllowed','pronunciationApproved','humanListeningVerified','perceptualToneVerified','shortConsonantAccepted'):
            self.assertFalse(policy['approvalBoundary'][key])

    def test_unknown_and_combined_runs_never_fall_back(self):
        for token in ('zi4','li5','bo5','mú','zìmu','zìmǔ','zhì','zhīzhū','SH','hello','constructor','ｚ','𝒛','z\u0304','z\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：'+token+'。', policy_version=VERSION)

    def test_150_exact_sentences_provider_identity_and_all_28_controlled(self):
        tokens, controlled = set(), 0
        self.assertEqual(len(DATA['speech']), 150)
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
        self.assertEqual(controlled, 28)
        self.assertEqual(tokens, set(registry.registered_policy(VERSION)['symbols']))

    def test_frozen_probe_request_bytes_and_neutral_sequence(self):
        from content.textbook_catalog import canonical
        import hashlib
        for sample in DATA['probeRequests']:
            body = registry.provider_body(sample['sourceText'], policy_version=VERSION)
            self.assertEqual(body, sample['body'])
            self.assertEqual(hashlib.sha256(canonical(body).encode()).hexdigest(), sample['requestSha256'])
            self.assertEqual(hashlib.sha256(body['input']['text'].encode()).hexdigest(), sample['ssmlSha256'])
            self.assertEqual([x['symbol'] for x in registry.pronunciation_symbols(sample['sourceText'], policy_version=VERSION)],
                             list(PROBE_TOKENS[sample['label']]))
        self.assertEqual(sum(len(registry.pronunciation_symbols(e['text'], policy_version=VERSION))
                             for e in DATA['speech']), 52)

    def test_unit_scope_loader_three_samples_and_pending_readiness(self):
        import content.textbook_catalog as catalog
        manifest = validate_manifest(json.loads((Path(catalog.__file__).parent /
            'textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text()))
        units = Path(__file__).parents[1] / 'content/textbooks/learning-units'
        b = lesson_blueprint(manifest, 'u3-l6', units_path=units)
        self.assertEqual(blueprint_prompt(b)['expectedQuestionCount'], 3)
        self.assertEqual([x['answer'] for x in b['assessmentMapping']], list('BAC'))
        self.assertEqual([x['page'] for x in b['assessmentMapping']], [6,10,15])
        scope = b['sourceScope']['scope']
        self.assertEqual(scope['literacyStation']['recognitionCharacters'], list('午星期语文数写会'))
        self.assertEqual(scope['literacyStation']['sourceWednesdayExample'],
                         ['数学','语文','体育与健康','语文','道德与法治','劳动'])
        self.assertEqual(scope['sharedReading']['title'], '谁会飞')
        self.assertFalse(scope['sharedReading']['fullTextCopiedIntoProposal'])
        self.assertFalse(b['generationReady'])
        self.assertEqual(b['knowledgeBrief']['review']['scope'], 'static-textbook-and-original-implementation-plan-only')
        self.assertFalse(b['knowledgeBrief']['review']['dynamicOfficialStrokeObserved'])
        self.assertFalse(b['knowledgeBrief']['review']['formalAudioApproved'])
        self.assertIsNone(lesson_blueprint({**manifest,'revisionId':'other'}, 'u3-l6', units_path=units))

class Garden3InitializationTests(fixtures.PronunciationInitializationTests):
    node_id = 'u3-l6'
    probe_targets = DATA['probeTargets']
    probe_token_sequences = PROBE_TOKENS
    approval_result = 'seven_garden3_phrase_probes_pronunciation_and_tones_approved'
    approval_statement = 'SYNTHETIC fixture only; no real Garden 3 audio, listening or approval.'
    first_speech = '请听：zì mǔ。玻璃、萝卜、一模一样保持自然中文。'
    _evidence_with_ssml = gkh_fixtures.GkhPronunciationInitializationTests._evidence_with_ssml
    test_operator_v2_keeps_formal_review_pending = zcs_fixtures.ZcsInitializationTests.test_operator_v2_does_not_turn_probe_protocol_into_human_or_formal_approval

    def setUp(self):
        # Exercise the historical v1 lifecycle unchanged, even after the new
        # default moved to v2. New v2 composition has its own full lifecycle test.
        scope = patch.object(registry, '_LESSON_POLICIES',
                             {**registry._LESSON_POLICIES, registry._GARDEN3_LESSON_BINDING: VERSION})
        scope.start(); self.addCleanup(scope.stop)
        super().setUp()

    def test_fixed_seven_phrases_missing_or_extra_never_initialize(self):
        actual, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(actual), self.probe_targets)
        self.assertEqual(dict(initialization._GARDEN3_PROBE_TOKENS), PROBE_TOKENS)
        original = deepcopy(self.approval)
        for index in range(7):
            self.approval = deepcopy(original); self.approval['samples'].pop(index); self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError): self.run_initialization()
        self.approval = deepcopy(original); self.approval['samples'].append(deepcopy(original['samples'][0])); self.write_approval()
        with self.assertRaises(ApiError): self.run_initialization()
        self.assert_no_external_write()

    def test_historical_archive_recovers_after_default_moves_to_v2(self):
        original = self.run_initialization()
        with patch.object(registry, '_LESSON_POLICIES',
                          {**registry._LESSON_POLICIES, registry._GARDEN3_LESSON_BINDING: registry.GARDEN3_V2_POLICY_VERSION}):
            self.assertEqual(self.run_initialization(), original)
        self.assert_no_external_write()

    def test_rebound_hashes_do_not_allow_wrong_order_carrier_or_neutral_tone(self):
        for label in PROBE_TOKENS:
            original = next(s for s in self.plan['samples'] if s['label'] == label)['body']['input']['text']
            nodes = ElementTree.fromstring(original).findall('phoneme')
            parts = [ElementTree.tostring(n,encoding='unicode') for n in nodes]
            variants = [('missing',parts[0]),('extra',''.join(parts+parts[:1])),
                        ('empty-carrier',''.join(parts).replace('>'+nodes[0].text+'<','><',1)),
                        ('wrong-tone',''.join(parts).replace(nodes[-1].attrib['ph'],'bo2'))]
            if parts[0] != parts[1]: variants.append(('reversed',''.join(reversed(parts))))
            if 'li5' in original or 'bo5' in original:
                variants.append(('neutral-tone-loss',''.join(parts).replace('li5','li1').replace('bo5','bo1')))
            variants.append(('wrong-carrier',''.join(parts).replace('>'+nodes[-1].text+'<','>错<',1)))
            for name, body in variants:
                files, patch = self._evidence_with_ssml(label,'<speak>听音。'+body+'</speak>')
                with self.subTest(label=label,variant=name), self.assertRaisesRegex(ApiError,'音素顺序'):
                    initialization._verify_evidence(files,patch,self.f.key,json.loads(self.row['input_json']),self.policy)
        self.assert_no_external_write()

if __name__ == '__main__': unittest.main()
