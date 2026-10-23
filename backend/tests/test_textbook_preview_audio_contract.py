"""Pure contract tests; no database, HTTP or provider initialization."""
from copy import deepcopy
import unittest

from content.textbook_audio_language import ENGLISH_AUTO_LANGUAGE_POLICY_SHA256
from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import (POLICY, asr_request_id, check_receipt_language_policy,
    compare_transcript, new_audio_plan, resolve_audio_contract, revision_audio_plan,
    tts_request_id, valid_tts_request_id)
from core.errors import ApiError
from services.learning_media_materialization_service import asr_similarity_bps


def frozen(subject='chinese', edition='book'):
    return {'editionId': edition, 'alignmentRevisionId': 'directory-1', 'manifestSha256': 'e' * 64,
            'nodeId': 'lesson-1', 'gradeCode': 'primary_1', 'subject': subject}


def plan(subject='chinese', edition='book'):
    return new_audio_plan(preview_key='a' * 64, classroom_sha256='b' * 64, core_sha256='c' * 64,
                          frozen_input=frozen(subject, edition))


def legacy():
    return {'previewKey': 'a' * 64, 'classroomSha256': 'b' * 64, 'coreSha256': 'c' * 64,
            'teacher': deepcopy(POLICY['subjects']['chinese']['teacher'])}


class PreviewAudioContractTests(unittest.TestCase):
    def test_legacy_plan_and_ids_stay_byte_for_byte_unchanged(self):
        value = legacy()
        before = canonical(value)
        contract = resolve_audio_contract(value, frozen())
        self.assertTrue(contract['legacy'])
        text = '请你数一数图中的三个花盆。'
        # Values frozen from the existing narrator/ASR algorithms, before v2.
        first = tts_request_id(value, 'scene-1', 'speech-1', text)
        self.assertEqual(first, 'tbprev_e9b50c9ec19e92ac56f58ae786120978b722bbbf9906afdcd317a2146df2fa29')
        self.assertEqual(tts_request_id(value, 'scene-1', 'speech-1', text, attempt=2), 'tbprev_e863234c78bbbbd14965c6dad7b14b800fd225d6d4c326da93d6b948b3cd6496')
        self.assertEqual(asr_request_id(value, first, 'd' * 64), 'tbasr_c5fcfc2b8fe87e293bf057f0a913a2e070ceb9c381dd7a6fb689b9846dfc7523')
        self.assertEqual(canonical(value), before)
        actual = '请你数一数图中的四个花盆。'
        self.assertEqual(compare_transcript(value, text, actual)['similarityBps'], asr_similarity_bps(text, actual))
        self.assertNotIn('schemaVersion', value)
        with self.assertRaises(ApiError): resolve_audio_contract(value, frozen('math'))

    def test_all_subjects_and_science_editions_get_distinct_frozen_identities(self):
        voices = {'chinese': 'Serena', 'math': 'Ethan', 'english': 'Jennifer', 'science': 'Serena'}
        ids = []
        for subject, voice in voices.items():
            value = plan(subject)
            contract = resolve_audio_contract(value, frozen(subject))
            self.assertEqual(contract['teacher']['voiceId'], voice)
            self.assertEqual(contract['subject'], subject)
            ids.append(tts_request_id(value, 'scene', 'speech', '请你认真观察图片。'))
            self.assertEqual(contract['teacher']['teacherProfile']['version'], 1 if subject == 'science' else 2)
        self.assertEqual(len(set(ids)), 4)
        self.assertNotEqual(tts_request_id(plan('science', 'jkes'), 'scene', 'speech', '请你认真观察图片。'),
                            tts_request_id(plan('science', 'pep-ej'), 'scene', 'speech', '请你认真观察图片。'))
        wrong = plan('math')
        wrong['teacher'] = plan('chinese')['teacher']
        with self.assertRaises(ApiError): resolve_audio_contract(wrong)
        with self.assertRaises(ApiError): resolve_audio_contract(plan('math'), frozen('science'))

    def test_english_uses_existing_auto_transport_and_requires_its_receipt(self):
        value = plan('english')
        request = tts_request_id(value, 'scene', 'speech', 'Hello, I am Mia.')
        self.assertTrue(request.startswith('tbbtts2_'))
        self.assertTrue(asr_request_id(value, request, 'd' * 64).startswith('tbbasr2_'))
        self.assertFalse(valid_tts_request_id(value, 'tbprev_' + 'd' * 64))
        with self.assertRaises(ApiError): asr_request_id(plan('math'), request, 'd' * 64)
        with self.assertRaises(ApiError): check_receipt_language_policy(value, {'status': 'succeeded'})
        receipt = {'status': 'succeeded', 'providerLanguagePolicy': {
            'policyVersion': 'mira.textbook.english-auto-language.v1',
            'policySha256': ENGLISH_AUTO_LANGUAGE_POLICY_SHA256, 'providerBodySha256': 'f' * 64}}
        check_receipt_language_policy(value, receipt)
        receipt['providerLanguagePolicy']['policySha256'] = '0' * 64
        with self.assertRaises(ApiError): check_receipt_language_policy(value, receipt)
        tampered = deepcopy(value)
        tampered['providerLanguagePolicy']['tts']['languageType'] = 'Chinese'
        tampered['providerLanguagePolicySha256'] = digest(tampered['providerLanguagePolicy'])
        with self.assertRaises(ApiError): resolve_audio_contract(tampered)

    def test_math_equivalence_preserves_counts_ordinal_roles_and_operations(self):
        value = plan('math')
        for expected, actual in [('校园里面一共有3个花盆。', '校园里面一共有三个花盆。'),
                                 ('请你观察第二层的窗户。', '请你观察第2层的窗户。'),
                                 ('请你算一算2+3=5。', '请你算一算二加三等于五。'),
                                 ('这里一共有两盆花，请数数。', '这里一共有2盆花，请数数。')]:
            with self.subTest(expected=expected): self.assertTrue(compare_transcript(value, expected, actual)['passed'])
        for expected, actual in [('请你仔细数一数校园里面一共有三个花盆。', '请你仔细数一数校园里面一共有四个花盆。'),
                                 ('请仔细观察教学楼第二层上面的窗户。', '请仔细观察教学楼第三层上面的窗户。'),
                                 ('请你看一看这道题，二加三等于五。', '请你看一看这道题，二减三等于五。')]:
            result = compare_transcript(value, expected, actual)
            self.assertGreaterEqual(result['similarityBps'], 8500)
            self.assertFalse(result['protectedContentMatched'])
            self.assertFalse(result['passed'])
        self.assertFalse(compare_transcript(value, '这座楼一共有三层。', '这座楼一共有第三层。')['passed'])
        self.assertFalse(compare_transcript(value, '这里的数字是1.5。', '这里的数字是一点五。')['passed'])

    def test_english_target_word_cannot_hide_in_high_sentence_similarity(self):
        value = plan('english')
        self.assertTrue(compare_transcript(value, "请跟老师说，Hello, I’m Mia.", "请跟老师说，hello, I'm Mia.")['passed'])
        result = compare_transcript(value, '请你仔细跟老师一起说，Hello, I am Mia.', '请你仔细跟老师一起说，Hello, I am Mila.')
        self.assertGreaterEqual(result['similarityBps'], 8500)
        self.assertFalse(result['passed'])

    def test_local_revision_inherits_contract_without_changing_original_ids(self):
        for subject in ('chinese', 'math', 'english', 'science'):
            original = plan(subject)
            before = canonical(original)
            existing_id = tts_request_id(original, 'old-scene', 'old-action', '未修改的讲解保持原来配音。')
            revised = revision_audio_plan(original, revision_id='f' * 64, classroom_sha256='1' * 64,
                                          core_sha256='2' * 64, frozen_input=frozen(subject))
            self.assertEqual(revised['teacher'], original['teacher'])
            self.assertEqual(revised['providerLanguagePolicy'], original['providerLanguagePolicy'])
            self.assertEqual(revised['comparisonPolicy'], original['comparisonPolicy'])
            self.assertEqual(revised['parentPlanSha256'], digest(original))
            self.assertEqual(canonical(original), before)
            self.assertEqual(tts_request_id(original, 'old-scene', 'old-action', '未修改的讲解保持原来配音。'), existing_id)
            self.assertNotEqual(tts_request_id(revised, 'scene', 'action', '修订过的讲解需要新身份。'), existing_id)
        old = legacy()
        revised = revision_audio_plan(old, revision_id='f' * 64, classroom_sha256='1' * 64,
                                      core_sha256='2' * 64, frozen_input=frozen())
        self.assertNotIn('schemaVersion', revised)
        self.assertEqual(set(revised), {'previewKey', 'revisionId', 'classroomSha256', 'coreSha256', 'teacher', 'subject'})


if __name__ == '__main__': unittest.main()
