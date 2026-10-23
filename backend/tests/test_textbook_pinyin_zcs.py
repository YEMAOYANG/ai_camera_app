"""ZCS lesson scope and pronunciation activation, with no provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest, validate_manifest
from content.textbook_pinyin_operator_review import AUTHORIZATION_SCHEMA
from content.textbook_preview import lesson_blueprint, blueprint_prompt
from core.errors import ApiError
from core.security import now_ms
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_visual_revision import sha_bytes
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan, sign
from tests.test_textbook_pinyin_jqx import PRIOR_HASHES
from tests import test_textbook_preview_pronunciation_initialization as fixtures


VERSION = 'mira.textbook.pinyin-zcs-ssml.v1'
POLICY_SHA = '5d311c9a903e00c9f819ec404af571bf21ef9a9caed229109ec7e2768e73815a'
TOKENS = [
    ('z', 'zi1', '资'), ('c', 'ci1', '疵'), ('s', 'si1', '丝'),
    ('zi', 'zi1', '资'), ('ci', 'ci1', '疵'), ('si', 'si1', '丝'),
    ('zá', 'za2', '砸'), ('zé', 'ze2', '责'), ('zǔ', 'zu3', '祖'), ('zuó', 'zuo2', '昨'),
    ('cā', 'ca1', '擦'), ('cè', 'ce4', '册'), ('cū', 'cu1', '粗'), ('cuō', 'cuo1', '搓'),
    ('sǎ', 'sa3', '洒'), ('sè', 'se4', '色'), ('sù', 'su4', '素'), ('suǒ', 'suo3', '锁'),
    ('zǐ', 'zi3', '子'), ('cì', 'ci4', '次'), ('sī', 'si1', '丝'),
    ('á', 'a2', '啊'), ('ā', 'a1', '啊'), ('ǎ', 'a3', '啊'), ('u', 'wu1', '乌'),
    ('ó', 'o2', '哦'), ('ō', 'o1', '哦'), ('ǒ', 'o3', '哦'),
]
PROBES = {'z-call-short-context': 'z', 'c-call-short-context': 'c',
          's-call-short-context': 's', 'zi3-whole': 'zǐ', 'ci4-whole': 'cì', 'si1-whole': 'sī'}


class ZcsPronunciationTests(unittest.TestCase):
    def test_exact_lesson_binding_preserves_prior_policies(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u3-l3'}
        policy = registry.select_policy(binding)
        self.assertEqual(digest(policy), POLICY_SHA)
        self.assertTrue(registry.initialization_required(binding))
        plan = pinyin_plan()
        plan.update(binding=binding, pronunciationPolicy=policy, pronunciationPolicySha256=POLICY_SHA)
        self.assertEqual(registry.policy_for_plan(plan), policy)
        prior = {**PRIOR_HASHES, registry.JQX_POLICY_VERSION:
                 '0f1957af0ce218d3f0323c79886f199a80210d2e1c49a7b68f6dc70071d6366b'}
        for version, expected in prior.items():
            self.assertEqual(digest(registry.registered_policy(version)), expected)
            wrong = {**plan, 'pronunciationPolicy': registry.registered_policy(version),
                     'pronunciationPolicySha256': expected}
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.policy_for_plan(wrong)
        for field in registry._BINDING_FIELDS:
            wrong = {**binding, field: binding[field] + '-other'}
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy(wrong)
            self.assertFalse(registry.initialization_required(wrong))
        policy['symbols']['zi']['ph'] = 'yi1'
        self.assertEqual(digest(registry.registered_policy(VERSION)), POLICY_SHA)

    def test_whole_recognition_and_neutral_word_do_not_rewrite_other_zi(self):
        for token, ph, carrier in TOKENS:
            with self.subTest(token=token):
                xml = registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)
                self.assertEqual(xml, f'<speak>请听：<phoneme alphabet="py" ph="{ph}">{carrier}</phoneme>。</speak>')
                self.assertEqual(len(ElementTree.fromstring(xml).findall('phoneme')), 1)
        text = '字、词、句、子；句子和孩子。'
        self.assertEqual(registry.pinyin_ssml(text, policy_version=VERSION),
            '<speak>字、词、句、子；<phoneme alphabet="py" ph="ju4 zi5">句子</phoneme>和孩子。</speak>')
        self.assertEqual([v['symbol'] for v in registry.pronunciation_symbols(text, policy_version=VERSION)], ['句子'])
        for token in ('zci', 'zi3', 'zh', 'zhi', 'zǐci', 'zī', 'i', 'Z', 'ｚ', '𝒛', 'constructor', 'zi\u030c', 'z\x00'):
            with self.subTest(token=token), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：' + token + '。', policy_version=VERSION)

    def test_physical_body_vector_and_cross_policy_receipts(self):
        text = '请听：' + '，'.join(sorted(t for t, _, _ in TOKENS)) + '。字、词、句、子；句子和孩子。'
        receipt = registry.provider_pronunciation(text, policy_version=VERSION)
        self.assertEqual(receipt['ssmlSha256'], '1ff98e847ac4a526ad0492fe850a1c754e4eb858a85820ac5eb71d9fc6f3fad4')
        self.assertEqual(receipt['providerBodySha256'], '15439393da188e0d6639dc5ec62e5c172ef2aaad2ec4a8faaab2d129187ab0a4')
        for version in (*PRIOR_HASHES, registry.JQX_POLICY_VERSION):
            with self.subTest(version=version), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation(receipt, policy_version=version)
        for field, value in [('voiceId', 'Serena'), ('policySha256', 'f' * 64), ('providerBodySha256', '0' * 64)]:
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.validate_provider_pronunciation({**receipt, field: value}, text, policy_version=VERSION)

    def test_scope_loader_keeps_whole_syllable_and_reading_boundaries(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        validate_manifest(manifest)
        blueprint = lesson_blueprint(manifest, 'u3-l3')
        self.assertEqual(blueprint_prompt(blueprint)['expectedQuestionCount'], 4)
        self.assertEqual([q['answer'] for q in blueprint['assessmentMapping']], list('BCAB'))
        scope = blueprint['sourceScope']['scope']
        self.assertEqual(len(scope['twoPartSyllables']) + len(scope['threePartSyllables']), 12)
        self.assertEqual(scope['wholeRecognitionBase'], ['zi', 'ci', 'si'])
        self.assertEqual(scope['recognizedCharacters'], ['字', '词', '句', '子'])
        self.assertFalse(scope['cartesianExpansionAllowed'])
        self.assertTrue(scope['reading']['doNotCopyFullText'])
        self.assertFalse(blueprint['generationReady'])
        self.assertIsNone(lesson_blueprint({**manifest, 'revisionId': 'different'}, 'u3-l3'))


class ZcsInitializationTests(fixtures.PronunciationInitializationTests):
    node_id = 'u3-l3'
    probe_targets = PROBES
    approval_result = 'six_zcs_call_context_and_whole_recognition_probes_pronunciation_and_tones_approved'
    approval_statement = 'SYNTHETIC human fixture only; no real ZCS human verdict.'
    first_speech = '请听整体认读音节：zi。再听句子。'

    def test_all_six_required_before_activation(self):
        original = deepcopy(self.approval)
        for index in range(6):
            self.approval = deepcopy(original)
            self.approval['samples'].pop(index)
            self.write_approval()
            with self.subTest(index=index), self.assertRaises(ApiError):
                self.run_initialization()
        self.assertFalse((self.f.folder / 'plan.json').exists())
        self.assert_no_external_write()

    def test_operator_v2_does_not_turn_probe_protocol_into_human_or_formal_approval(self):
        frozen = json.loads(self.row['input_json'])
        old = (self.probes / 'human-approval.json').read_bytes()
        time = now_ms()
        authorization = sign({'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message',
            'statement': 'SYNTHETIC user authorizes automatic checks and publication, not human listening.',
            'recordedAt': time - 1000, 'scope': {k: frozen[k] for k in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True,
            'individualListeningConfirmationRequired': False})
        review = {k: deepcopy(self.approval[k]) for k in ('previewKey', 'sourceSha256',
            'pronunciationPolicyVersion', 'pronunciationPolicySha256', 'formalUseAllowed', 'probePlanSha256')}
        review.update(schemaVersion=initialization.OPERATOR_REVIEW_SCHEMA, method=initialization.OPERATOR_METHOD,
            coreSha256=self.patch['expectedCoreSha256'], reviewer='Synthetic operator', recordedAt=time,
            authorization=authorization, result=initialization.OPERATOR_RESULT,
            humanListeningVerified=False, perceptualToneVerified=False, evidenceLimit=initialization.OPERATOR_EVIDENCE_LIMIT,
            samples=[{**x, 'result': initialization.OPERATOR_RESULT} for x in self.approval['samples']])
        raw = canonical(sign(review)).encode()
        path = self.probes / 'operator-probe-review.json'
        path.write_bytes(raw)
        self.patch.pop('approvedProbeEvidence')
        self.patch.update(schemaVersion=initialization.OPERATOR_SCHEMA,
                          verifiedProbeEvidence={'path': str(path), 'sha256': sha_bytes(raw)})
        result = self.run_initialization()
        self.assertTrue(result['requiresFormalOperatorReview'])
        for key in ('generationDispatched', 'publicationAllowed', 'humanListeningVerified', 'perceptualToneVerified'):
            self.assertFalse(result[key])
        self.assertEqual(self.run_initialization(), result)
        self.assertEqual((self.probes / 'human-approval.json').read_bytes(), old)
        self.assert_no_external_write()


if __name__ == '__main__':
    unittest.main()
