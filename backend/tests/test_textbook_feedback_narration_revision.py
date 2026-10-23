"""Exact selected-feedback repairs preserve locked questions and raw ASR."""
from copy import deepcopy
import unittest
from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import sha_text
from core.errors import ApiError
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_preview_narration_revision import (
    SCHEMA_V2, text_candidate, bind_revised_feedback_audio,
)


class FeedbackNarrationRevisionTests(unittest.TestCase):
    def setUp(self):
        self.old, self.new = '你选的是绿衣Ben。', '你选的是绿衣朋友。'
        q = {'id': 'q', 'type': 'single', 'question': '听名字，选朋友。', 'answer': ['B'], 'points': 2,
             'options': [{'value': 'A', 'label': '绿衣朋友'}, {'value': 'B', 'label': '蓝衣朋友'}],
             'optionFeedback': {'A': {'text': self.old, 'audioUrl': '/api/classroom-media/source/audio/old.wav',
                                     'visual': {'kind': 'image', 'src': '/api/classroom-media/source/media/wrong.png'},
                                     'audioBinding': {'old': 'retained in original'}}}}
        self.source = {'id': 'source', 'scenes': [{'id': 's', 'type': 'quiz', 'content': {'questions': [q]},
            'actions': [{'id': 'stem', 'type': 'speech', 'text': q['question'], 'audioId': 'stem', 'audioUrl': '/api/classroom-media/source/audio/stem.wav'},
                        {'id': 'feedback', 'type': 'speech', 'text': self.old, 'audioId': 'old', 'audioUrl': '/api/classroom-media/source/audio/old.wav'}]}]}
        self.audit = {'schemaVersion': 'mira.textbook.audio-audit.v1', 'sourceSha256': digest(self.source), 'passed': False, 'segments': []}
        for action in self.source['scenes'][0]['actions']:
            transcript = action['text'] if action['id'] == 'stem' else '你选的是绿衣笨。'
            self.audit['segments'].append({'sceneId': 's', 'actionId': action['id'], 'ttsRequestId': action['audioId'],
                'text': action['text'], 'textSha256': sha_text(action['text']), 'transcript': transcript,
                'similarityBps': asr_similarity_bps(action['text'], transcript),
                'asr': {'status': 'succeeded', 'transcript': transcript, 'transcriptSha256': sha_text(transcript)}})
        self.audit['sha256'] = digest(self.audit)
        after = deepcopy(q); after['optionFeedback']['A']['text'] = self.new
        after['optionFeedback']['A'].pop('audioUrl'); after['optionFeedback']['A'].pop('audioBinding')
        self.patch = {'schemaVersion': SCHEMA_V2, 'expectedSourceSha256': digest(self.source), 'reviewer': 'synthetic',
            'basis': 'Synthetic exact ASR difference; target stem unchanged', 'questionChanges': [],
            'changes': [{'sceneId': 's', 'actionId': 'feedback', 'beforeTextSha256': sha_text(self.old), 'text': self.new,
                         'auditSegmentSha256': digest(self.audit['segments'][1]), 'reason': 'asr-lexical-mismatch'}],
            'feedbackChanges': [{'sceneId': 's', 'questionId': 'q', 'optionValue': 'A', 'actionId': 'feedback',
                'beforeQuestionSha256': digest(q), 'afterQuestionSha256': digest(after), 'text': self.new}]}
        self.expected = after

    def test_replaces_only_selected_feedback_and_binds_its_exact_new_clip(self):
        source_sha, audit_sha = digest(self.source), digest(self.audit)
        target = text_candidate(self.source, self.patch, self.audit)
        self.assertEqual(target['scenes'][0]['content']['questions'][0], self.expected)
        action = target['scenes'][0]['actions'][1]
        action.update(audioId='new', audioUrl='/api/classroom-media/source/audio/new.wav')
        evidence = bind_revised_feedback_audio(target, self.patch)
        q = target['scenes'][0]['content']['questions'][0]
        feedback = q['optionFeedback']['A']
        self.assertEqual(feedback['audioUrl'], action['audioUrl'])
        self.assertEqual(feedback['audioBinding']['ttsRequestId'], 'new')
        self.assertEqual(feedback['audioBinding']['sourceTextSha256'], sha_text(self.new))
        self.assertEqual(evidence[0]['deliveredQuestionSha256'], digest(q))
        self.assertEqual(q['answer'], ['B']); self.assertEqual(q['question'], '听名字，选朋友。')
        self.assertEqual(digest(self.source), source_sha); self.assertEqual(digest(self.audit), audit_sha)

    def test_wrong_option_changed_answer_or_ambiguous_link_cannot_be_repaired(self):
        for change in ('option', 'answer', 'missing', 'duplicate', 'speech', 'stale'):
            patch = deepcopy(self.patch); link = patch['feedbackChanges'][0]
            if change == 'option': link['optionValue'] = 'B'
            elif change == 'answer': link['afterQuestionSha256'] = digest({**self.expected, 'answer': ['A']})
            elif change == 'missing': patch.pop('feedbackChanges')
            elif change == 'duplicate': patch['feedbackChanges'].append(deepcopy(link))
            elif change == 'speech': link['text'] = '其他内容'
            else: link['beforeQuestionSha256'] = '0' * 64
            with self.subTest(change=change), self.assertRaises(ApiError): text_candidate(self.source, patch, self.audit)

    def test_binding_rejects_changed_question_after_prepare(self):
        target = text_candidate(self.source, self.patch, self.audit)
        target['scenes'][0]['content']['questions'][0]['points'] = 99
        with self.assertRaises(ApiError): bind_revised_feedback_audio(target, self.patch)


if __name__ == '__main__': unittest.main()
