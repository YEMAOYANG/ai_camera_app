"""Textbook-scoped AO/OU/IU registration and automatic initialization, no paid calls."""
from copy import deepcopy
import json
import unittest
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as registry
from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_carrier_equivalence import exact_representation
from content.textbook_pinyin_operator_review import AUTHORIZATION_SCHEMA
from core.errors import ApiError
from core.security import now_ms
from services import textbook_preview_pronunciation_initialization as initialization
from services.textbook_preview_audio import bind_question_audio, core_content
from services.textbook_preview_visual_revision import sha_bytes
from tests import test_textbook_preview_pronunciation_initialization as fixtures
from tests.test_textbook_pinyin_aieiui import PRIOR_HASHES, POLICY_SHA as AIEIUI_V4_SHA
from tests.test_textbook_pinyin_pronunciation import PINYIN_BINDING, pinyin_plan


VERSION = 'mira.textbook.pinyin-aouiu-ssml.v1'
FINALS = (
    ('ɑo', 'ao1'), ('āo', 'ao1'), ('áo', 'ao2'), ('ǎo', 'ao3'), ('ào', 'ao4'),
    ('ou', 'ou1'), ('ōu', 'ou1'), ('óu', 'ou2'), ('ǒu', 'ou3'), ('òu', 'ou4'),
    ('iu', 'you1'), ('iū', 'you1'), ('iú', 'you2'), ('iǔ', 'you3'), ('iù', 'you4'),
)
TEXTBOOK_SYLLABLES = (
    'niǎo shǎo yào rào zǎo tiào ròu tóu lóu yóu zǒu shōu kǒu '
    'qiú diū liù niú xiū jiù'
).split()
PICTURE_AND_WRITING = 'xiǎo qiáo liú shuǐ chuí liǔ táo huā'.split()
COMPONENTS = 'ɑ o i u n sh y r z t l q d x j k'.split()
PROBE_TEXTS = {
    'ao-final-and-tones': 'ɑo，āo、áo、ǎo、ào',
    'ou-final-and-tones': 'ou，ōu、óu、ǒu、òu',
    'iu-final-and-tones': 'iu，iū、iú、iǔ、iù',
}
PROBE_TOKENS = {
    'ao-final-and-tones': ('ɑo', 'āo', 'áo', 'ǎo', 'ào'),
    'ou-final-and-tones': ('ou', 'ōu', 'óu', 'ǒu', 'òu'),
    'iu-final-and-tones': ('iu', 'iū', 'iú', 'iǔ', 'iù'),
}
PROBE_TARGETS = {label: tokens[0] for label, tokens in PROBE_TOKENS.items()}


def seal(value):
    value['sha256'] = digest({key: item for key, item in value.items() if key != 'sha256'})
    return value


class AoOuIuPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = registry.registered_policy(VERSION)

    def test_frozen_lesson_binding_rejects_old_lesson_policy_and_keeps_all_old_hashes(self):
        binding = {**PINYIN_BINDING, 'nodeId': 'u4-l2'}
        self.assertEqual(registry.select_policy(binding), self.policy)
        self.assertTrue(registry.initialization_required(binding))
        plan = pinyin_plan()
        plan.update(binding=binding, pronunciationPolicy=self.policy,
                    pronunciationPolicySha256=digest(self.policy))
        self.assertEqual(registry.policy_for_plan(plan), self.policy)
        for field in registry._BINDING_FIELDS:
            with self.subTest(field=field), self.assertRaises(ApiError):
                registry.select_policy({**binding, field: binding[field] + '-other'})
        historical = {**PRIOR_HASHES, registry.AIEIUI_V4_POLICY_VERSION: AIEIUI_V4_SHA}
        for version, sha in historical.items():
            self.assertEqual(digest(registry.registered_policy(version)), sha)
        self.assertTrue((set(historical) | {VERSION}) <= set(registry._POLICIES))
        old = registry.registered_policy(registry.AIEIUI_V4_POLICY_VERSION)
        plan.update(pronunciationPolicy=old, pronunciationPolicySha256=digest(old))
        with self.assertRaises(ApiError):
            registry.policy_for_plan(plan)

    def test_only_verified_lesson_tokens_and_existing_component_recipes_are_registered(self):
        expected = {token for token, _ in FINALS} | set(TEXTBOOK_SYLLABLES + PICTURE_AND_WRITING + COMPONENTS)
        self.assertEqual(set(self.policy['symbols']), expected)
        self.assertEqual(len(expected), 58)
        self.assertEqual(len(TEXTBOOK_SYLLABLES), 19)
        self.assertEqual(self.policy['words'], {})
        self.assertNotIn('exactTextSsml', self.policy)
        prior = [registry.registered_policy(version) for version in registry._POLICIES if version != VERSION]
        for token in COMPONENTS + ['shuǐ']:
            entry = self.policy['symbols'][token]
            self.assertTrue(any(policy['symbols'].get(token) == entry for policy in prior), token)
        base = registry.registered_policy(registry.AIEIUI_V4_POLICY_VERSION)
        for field in ('providerId', 'modelId', 'voiceId', 'endpointPath', 'inputParameters', 'textHandling'):
            self.assertEqual(self.policy[field], base[field])
        boundary = self.policy['approvalBoundary']
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'pronunciationApproved', 'formalUseAllowed'):
            self.assertIs(boundary[field], False)

    def test_correct_whole_final_tones_and_fixed_probe_order_without_letter_concatenation(self):
        for token, ph in FINALS:
            with self.subTest(token=token):
                ssml = registry.pinyin_ssml(token, policy_version=VERSION)
                phonemes = ElementTree.fromstring(ssml).findall('phoneme')
                self.assertEqual(len(phonemes), 1)
                self.assertEqual(phonemes[0].attrib, {'alphabet': 'py', 'ph': ph})
        self.assertEqual(dict(initialization._AOUIU_PROBE_TEXTS), PROBE_TEXTS)
        self.assertEqual(dict(initialization._AOUIU_PROBE_TOKENS), PROBE_TOKENS)
        probes, _ = initialization._probe_contract(self.policy)
        self.assertEqual(dict(probes), PROBE_TARGETS)
        for label, source in PROBE_TEXTS.items():
            root = ElementTree.fromstring(registry.pinyin_ssml(source, policy_version=VERSION))
            self.assertEqual([item.attrib['ph'] for item in root.findall('phoneme')],
                             [self.policy['symbols'][token]['ph'] for token in PROBE_TOKENS[label]])

    def test_wrong_tone_position_unregistered_runs_and_compatibility_forms_fail_closed(self):
        invalid = ('ao', 'ao1', 'ɑo1', 'ou1', 'iu1', 'īu', 'íu', 'ǐu', 'ìu',
                   'i\u0301u', 'a\u0304o', 'ɑ\u0304o', 'ɑoou', 'xiǎoniú', 'IU', 'ｉｕ', 'péng', 'luó bo')
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ApiError):
                registry.pinyin_ssml('请听：' + text + '。', policy_version=VERSION)
        self.assertEqual(registry.pinyin_ssml('老师<&>说：iǔ。', policy_version=VERSION),
            '<speak>老师&lt;&amp;&gt;说：<phoneme alphabet="py" ph="you3">有</phoneme>。</speak>')

    def test_exact_carrier_evidence_remains_context_complete_and_does_not_infer_tone(self):
        evidence = exact_representation('请听，xiǎo qiáo。', '请听，小桥。', self.policy)
        self.assertTrue(evidence['orthographicEquivalent'])
        self.assertEqual([target['ph'] for target in evidence['targets']], ['xiao3', 'qiao2'])
        for transcript in ('小桥', '请听，小。', '请听，小乔。', '请说，小桥。', '请听，小桥小桥。'):
            with self.subTest(transcript=transcript), self.assertRaises(ApiError):
                exact_representation('请听，xiǎo qiáo。', transcript, self.policy)


class AoOuIuAutomaticInitializationTests(unittest.TestCase):
    def setUp(self):
        fx = self.fx = fixtures.PronunciationInitializationTests()
        fx.node_id = 'u4-l2'
        fx.probe_targets = PROBE_TARGETS
        fx.probe_token_sequences = PROBE_TOKENS
        fx.probe_source_texts = PROBE_TEXTS
        fx.approval_result = 'three_aouiu_fixed_probes_pronunciation_and_tones_approved'
        fx.approval_statement = 'Synthetic fixture; no real listening has occurred.'
        fx.first_speech = '请听：ɑo，āo、áo、ǎo、ào。'
        fx.setUp(); self.addCleanup(fx.doCleanups)
        timestamp = now_ms()
        frozen = json.loads(fx.row['input_json'])
        authorization = seal({
            'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message',
            'statement': 'SYNTHETIC reuse of confirmed speech setup with automatic checks and publication.',
            'recordedAt': timestamp - 1000,
            'scope': {key: frozen[key] for key in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True,
            'individualListeningConfirmationRequired': False,
        })
        self.review = {key: deepcopy(fx.approval[key]) for key in (
            'previewKey', 'sourceSha256', 'pronunciationPolicyVersion',
            'pronunciationPolicySha256', 'formalUseAllowed', 'probePlanSha256')}
        self.review.update(
            schemaVersion=initialization.OPERATOR_REVIEW_SCHEMA, method=initialization.OPERATOR_METHOD,
            coreSha256=fx.patch['expectedCoreSha256'], reviewer='Synthetic operator', recordedAt=timestamp,
            authorization=authorization, result=initialization.OPERATOR_RESULT,
            humanListeningVerified=False, perceptualToneVerified=False,
            evidenceLimit=initialization.OPERATOR_EVIDENCE_LIMIT,
            samples=[{**sample, 'result': initialization.OPERATOR_RESULT} for sample in fx.approval['samples']],
        )
        fx.patch = {key: value for key, value in fx.patch.items() if key != 'approvedProbeEvidence'}
        fx.patch.update(schemaVersion=initialization.OPERATOR_SCHEMA,
            basis='Synthetic protocol and unchanged PCM evidence; formal complete ASR and browser review remain required.',
            verifiedProbeEvidence={'path': str(fx.probes / 'operator-probe-review.json'), 'sha256': ''})
        self.write_review()

    def write_review(self):
        seal(self.review)
        raw = canonical(self.review).encode()
        (self.fx.probes / 'operator-probe-review.json').write_bytes(raw)
        self.fx.patch['verifiedProbeEvidence']['sha256'] = sha_bytes(raw)

    def test_prepare_install_and_resume_preserve_originals_without_provider_or_listening_claims(self):
        fx = self.fx
        source = (fx.f.root / (fx.f.cid + '.json')).read_bytes()
        evidence = {path: path.read_bytes() for path in fx.probes.rglob('*') if path.is_file()}
        self.assertTrue(fx.run_initialization(False)['prepared'])
        self.assertFalse((fx.f.folder / 'plan.json').exists())
        result = fx.run_initialization()
        for field in ('generationDispatched', 'publicationAllowed', 'requiresFormalHumanListening',
                      'humanListeningVerified', 'perceptualToneVerified'):
            self.assertIs(result[field], False)
        self.assertTrue(result['requiresFormalOperatorReview'])
        installed = json.loads((fx.f.folder / 'plan.json').read_text())
        self.assertEqual(registry.policy_for_plan(installed)['policyVersion'], VERSION)
        self.assertEqual(fx.run_initialization(), result)
        self.assertEqual(fx.f.service.get(fx.f.key), fx.row)
        self.assertEqual((fx.f.root / (fx.f.cid + '.json')).read_bytes(), source)
        for path, raw in evidence.items():
            self.assertEqual(path.read_bytes(), raw)
        fx.assert_no_external_write()

    def test_automatic_review_rejects_missing_tones_changed_audio_and_claimed_human_approval(self):
        original = deepcopy(self.review)
        for field in ('humanListeningVerified', 'perceptualToneVerified', 'formalUseAllowed'):
            self.review = {**deepcopy(original), field: True}; self.write_review()
            with self.subTest(field=field), self.assertRaises(ApiError):
                self.fx.run_initialization()
        self.review = deepcopy(original)
        self.review['samples'].pop(); self.write_review()
        with self.assertRaises(ApiError):
            self.fx.run_initialization()
        self.review = deepcopy(original); self.write_review()
        wav = self.fx.probes / 'iu-final-and-tones' / 'playback.wav'
        wav.write_bytes(wav.read_bytes() + b'changed')
        with self.assertRaises(ApiError):
            self.fx.run_initialization()
        self.assertFalse((self.fx.f.folder / 'plan.json').exists())
        self.fx.assert_no_external_write()

    def test_fixed_probe_source_cannot_be_relabelled_even_with_a_new_plan_digest(self):
        fx = self.fx
        files = initialization._evidence_files(fx.patch, fx.policy)
        plan = json.loads(files['evidence/plan.json'])
        review = json.loads(files['evidence/operator-probe-review.json'])
        plan['samples'][0]['sourceText'] = 'ɑo，āo、áo、ǎo'
        raw = canonical(plan).encode()
        files['evidence/plan.json'] = raw
        review['probePlanSha256'] = sha_bytes(raw)
        probes, _ = initialization._probe_contract(fx.policy)
        with self.assertRaises(ApiError):
            initialization._verify_probe_files(files, review, json.loads(fx.row['input_json']),
                fx.policy, probes, sample_result=initialization.OPERATOR_RESULT)
        fx.assert_no_external_write()

    def test_completed_narration_can_resume_initialization_without_regenerating(self):
        # Exercise the actual narrator with synthetic receipts, including its
        # generated question bindings. No provider service is called.
        self.fx.test_real_narrator_sample_then_full_reuses_success_and_initialization_is_idempotent()

    def test_derived_question_and_feedback_bindings_must_match_current_speech(self):
        classroom = {'scenes': [{'id': 's', 'type': 'quiz', 'actions': [
            {'id': 'stem', 'type': 'speech', 'text': '请选小桥。',
             'audioId': 'tts-stem', 'audioUrl': '/audio/tts-stem.wav'},
            {'id': 'feedback', 'type': 'speech', 'text': '小桥在这里。',
             'audioId': 'tts-feedback', 'audioUrl': '/audio/tts-feedback.wav'},
        ], 'content': {'questions': [{'id': 'q', 'question': '请选小桥。',
            'optionFeedback': {'bridge': {'text': '小桥在这里。'}}}]}}]}
        original = core_content(classroom)
        bind_question_audio(classroom)
        self.assertEqual(initialization._without_audio(classroom), original)
        for mutation in ('stem-request', 'stem-text', 'feedback-request', 'feedback-option', 'speech-text'):
            changed = deepcopy(classroom)
            scene = changed['scenes'][0]; question = scene['content']['questions'][0]
            if mutation == 'stem-request': question['questionAudioBinding']['ttsRequestId'] = 'other'
            elif mutation == 'stem-text': question['questionAudioBinding']['sourceTextSha256'] = '0' * 64
            elif mutation == 'feedback-request': question['optionFeedback']['bridge']['audioBinding']['ttsRequestId'] = 'other'
            elif mutation == 'feedback-option': question['optionFeedback']['bridge']['audioBinding']['optionValue'] = 'other'
            else: scene['actions'][0]['text'] = '请选柳树。'
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                initialization._without_audio(changed)


if __name__ == '__main__':
    unittest.main()
