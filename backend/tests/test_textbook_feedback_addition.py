"""Missing feedback fills use the existing durable delta transport, never a full rerun."""
from copy import deepcopy
import json
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_feedback_addition import SCHEMA, text_candidate, bind_added_feedback
from core.errors import ApiError
from services.textbook_preview_narration_revision import sha_bytes
from tests.test_textbook_preview_narration_revision import NarrationRevisionTests


class FeedbackAdditionTests(unittest.TestCase):
    def setUp(self):
        f = self.f = NarrationRevisionTests()
        f.setUp(); self.addCleanup(f.doCleanups)
        room = f.fixture.classroom
        scene = room['scenes'][6]
        question = scene['content']['questions'][0]
        scene['actions'][0]['text'] = question['question']
        question['optionVisuals'] = {o['value']: {'kind': 'image', 'src': f.fixture.cover,
             'alt': '原选项' + o['value']} for o in question['options']}
        f.fixture.persist_source(); f.source_sha = f.fixture.source_sha
        f.original = deepcopy(room)
        self.q = deepcopy(question)
        self.changes = [{'sceneId': scene['id'], 'questionId': question['id'], 'optionValue': o['value'],
            'actionId': 'feedback-' + o['value'], 'beforeQuestionSha256': digest(question),
            'feedback': {'text': '针对原选项' + o['value'] + '的具体反馈。',
                         'visual': deepcopy(question['optionVisuals'][o['value']])}}
             for o in question['options']]
        f.revision = {'schemaVersion': SCHEMA, 'expectedSourceSha256': f.source_sha,
            'reviewer': 'Synthetic operator', 'basis': 'Synthetic missing selected feedback', 'changes': self.changes}
        for i, entry in enumerate(f.audit['segments']):
            text = room['scenes'][i]['actions'][0]['text']
            entry.update(text=text, textSha256=sha_bytes(text.encode()), transcript=text, similarityBps=10000)
            entry['asr'].update(transcript=text, transcriptSha256=sha_bytes(text.encode()))
        f.audit.update(sourceSha256=f.source_sha, passed=True)
        f.audit['sha256'] = digest({k: v for k, v in f.audit.items() if k != 'sha256'})
        f.audit_path.write_text(canonical(f.audit))

    def test_only_delta_calls_immutable_source_audio_and_idempotent_receipt(self):
        f = self.f
        prepared = f.run_revision(execute=False)
        self.assertEqual(prepared['segments'], len(self.changes))
        f.runtime.start_formal_audio_tts.assert_not_called()
        receipt = f.run_revision()
        self.assertEqual(receipt['supersededTtsRequestIds'], [])
        self.assertEqual(receipt['schemaVersion'], 'mira.textbook.preview-feedback-addition-amendment.v1')
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, len(self.changes))
        self.assertEqual(f.run_revision(), receipt)
        for name, raw in f.original_wavs.items():
            self.assertEqual((f.root / f.cid / 'audio' / name).read_bytes(), raw)
        self.assertEqual((f.folder / 'plan.json').read_bytes(), f.original_plan)
        current = f.fixture.classroom
        for a, b in zip(f.original['scenes'], current['scenes']):
            self.assertEqual(a['actions'], b['actions'][:len(a['actions'])])
        q = current['scenes'][6]['content']['questions'][0]
        self.assertEqual({k: v for k, v in q.items() if k != 'optionFeedback'}, self.q)
        for value, item in q['optionFeedback'].items():
            self.assertEqual(item['audioBinding']['optionValue'], value)
            self.assertIn('/audio/', item['audioUrl'])
        f.runtime.start_formal_audio_asr.assert_not_called()

    def test_existing_text_only_feedback_can_be_filled_but_not_rewritten(self):
        source = deepcopy(self.f.original)
        q = source['scenes'][6]['content']['questions'][0]
        q['optionFeedback'] = {c['optionValue']: deepcopy(c['feedback']) for c in self.changes}
        patch = deepcopy(self.f.revision); patch['expectedSourceSha256'] = digest(source)
        for c in patch['changes']: c['beforeQuestionSha256'] = digest(q)
        target = text_candidate(source, patch)
        self.assertEqual(target['scenes'][6]['content']['questions'][0], q)
        patch['changes'][0]['feedback']['text'] += '改写'
        with self.assertRaises(ApiError): text_candidate(source, patch)

    def test_stale_question_other_image_duplicate_action_and_partial_coverage_rejected(self):
        for case in ('stale', 'image', 'duplicate', 'existing', 'partial'):
            patch = deepcopy(self.f.revision)
            if case == 'stale': patch['changes'][0]['beforeQuestionSha256'] = '0' * 64
            elif case == 'image': patch['changes'][0]['feedback']['visual']['src'] += '.png'
            elif case == 'duplicate': patch['changes'].append(deepcopy(patch['changes'][0]))
            elif case == 'existing': patch['changes'][0]['actionId'] = 'action-0'
            else: patch['changes'].pop()
            with self.subTest(case=case), self.assertRaises(ApiError): text_candidate(self.f.original, patch)

    def test_failing_source_audit_blocks_provider_dispatch(self):
        self.f.audit['passed'] = False
        self.f.audit['sha256'] = digest({k: v for k, v in self.f.audit.items() if k != 'sha256'})
        self.f.audit_path.write_text(canonical(self.f.audit))
        with self.assertRaises(ApiError): self.f.run_revision()
        self.f.runtime.start_formal_audio_tts.assert_not_called()

    def test_binding_rejects_changed_locked_answer(self):
        target = text_candidate(self.f.original, self.f.revision)
        target['scenes'][6]['content']['questions'][0]['answer'] = ['tampered']
        with self.assertRaises(ApiError): bind_added_feedback(target, self.f.original, self.f.revision)

    def test_feedback_preserves_prior_stem_metadata_without_repeating_paid_calls(self):
        f = self.f
        question = f.fixture.classroom['scenes'][6]['content']['questions'][0]
        stale = {'schemaVersion': 'mira.learning.question-narration-binding.v1',
                 'sceneId': f.fixture.classroom['scenes'][6]['id'],
                 'actionId': f.fixture.classroom['scenes'][6]['actions'][0]['id'],
                 'ttsRequestId': 'old-approved-stem', 'sourceTextSha256': '1' * 64}
        question['questionAudioBinding'] = deepcopy(stale)
        f.fixture.persist_source()
        f.original = deepcopy(f.fixture.classroom)
        f.revision['expectedSourceSha256'] = f.fixture.source_sha
        for change in f.revision['changes']:
            change['beforeQuestionSha256'] = digest(question)
        f.audit['sourceSha256'] = f.fixture.source_sha
        f.audit['sha256'] = digest({k: v for k, v in f.audit.items() if k != 'sha256'})
        f.audit_path.write_text(canonical(f.audit))
        receipt = f.run_revision()
        current = f.fixture.classroom['scenes'][6]['content']['questions'][0]
        self.assertEqual(current['questionAudioBinding'], stale)
        self.assertTrue(all(item.get('audioBinding') for item in current['optionFeedback'].values()))
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, len(self.changes))
        self.assertEqual(f.run_revision(), receipt)
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, len(self.changes))

    def test_feedback_does_not_waive_a_stem_url_pointing_to_another_clip(self):
        source = deepcopy(self.f.original)
        question = source['scenes'][6]['content']['questions'][0]
        question['questionAudioUrl'] = '/api/classroom-media/wrong/audio/foreign.wav'
        patch = deepcopy(self.f.revision)
        patch['expectedSourceSha256'] = digest(source)
        for change in patch['changes']:
            change['beforeQuestionSha256'] = digest(question)
        target = text_candidate(source, patch)
        for action in target['scenes'][6]['actions'][1:]:
            action.update(audioId=action['id'], audioUrl='/api/classroom-media/fixture/audio/' + action['id'] + '.wav')
        with self.assertRaisesRegex(ApiError, '已有听题或反馈录音与当前原文旁白不一致'):
            bind_added_feedback(target, source, patch)


if __name__ == '__main__': unittest.main()
