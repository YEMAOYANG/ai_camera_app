"""Versioned lexical/quiz repairs with fake providers and the existing local fixture."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import unittest

from content.textbook_catalog import canonical, digest
from content.textbook_asr_source_reuse import ORIGIN_SCHEMA, build_audit, formal_request
from content.textbook_audio_recheck import seal
from content.textbook_interactive_narration import interactive_cues
from content.textbook_pinyin_pronunciation import (
    ZCS_POLICY_VERSION, ZCS_V2_POLICY_VERSION, provider_pronunciation, sha_text,
)
from content.textbook_preview_audio_contract import compare_transcript
from core.errors import ApiError
from services.learning_media_materialization_service import asr_similarity_bps
from services.textbook_preview_narration_revision import (
    SCHEMA, SCHEMA_V2, SCHEMA_V3, text_candidate, validate_patch, bind_revised_question_audio,
)
from tests import test_textbook_preview_narration_revision as legacy_fixtures
from tests import test_textbook_narration_policy_revision as policy_fixtures
from tests import test_textbook_pinyin_pronunciation as pinyin_fixtures


class NarrationRevisionV2Tests(unittest.TestCase):
    def setUp(self):
        self.f = f = legacy_fixtures.NarrationRevisionTests()
        f.setUp(); self.addCleanup(f.doCleanups)
        self.old_done = '四次字卡联系都完成了，你可以再点任意目标字，听一听它的词语。'
        self.new_done = '四张字卡都找到了对应的活动图片，你还可以点选字卡，再听一次词语。'
        self.old_question = '请你看一看，哪一张图片和老师说的一样？'
        self.new_question = '请看这些图片，选出和老师说的一样的那一张。'
        room = f.fixture.classroom
        room['scenes'][0]['actions'][0]['text'] = self.old_done
        q = room['scenes'][6]['content']['questions'][0]
        q.update(question=self.old_question,
                 visual={'kind': 'image', 'src': f.fixture.cover, 'alt': '目标图片'},
                 optionVisuals={'A': {'kind': 'image', 'src': f.fixture.cover, 'alt': '第一张图片'}})
        room['scenes'][6]['actions'][0]['text'] = self.old_question
        f.fixture.persist_source()
        f.source_sha = f.fixture.source_sha
        f.original = deepcopy(room)
        self.before_question = deepcopy(q)
        for index, entry in enumerate(f.audit['segments']):
            text = room['scenes'][index]['actions'][0]['text']
            transcript = (text.replace('联系', '练习') if index == 0 else
                          '完全不同的句子' if index in (5, 6) else text)
            entry.update(text=text, textSha256=sha_text(text), transcript=transcript,
                         similarityBps=asr_similarity_bps(text, transcript))
            entry['asr'].update(transcript=transcript, transcriptSha256=sha_text(transcript))
        f.audit['sourceSha256'] = f.source_sha
        pinyin_fixtures.sign(f.audit); f.audit_path.write_text(canonical(f.audit))
        self.assertGreaterEqual(f.audit['segments'][0]['similarityBps'], 8500)
        changes = []
        for index, text in [(0, self.new_done), (5, '请点一点这些图片，数一数。'), (6, self.new_question)]:
            action = room['scenes'][index]['actions'][0]
            changes.append({'sceneId': room['scenes'][index]['id'], 'actionId': action['id'],
                'beforeTextSha256': sha_text(action['text']), 'text': text,
                'auditSegmentSha256': digest(f.audit['segments'][index]), 'reason': 'asr-lexical-mismatch'})
        f.revision = {'schemaVersion': SCHEMA_V2, 'expectedSourceSha256': f.source_sha,
            'reviewer': 'Synthetic operator', 'basis': 'Synthetic exact ASR lexical mismatch correction',
            'changes': changes, 'questionChanges': [{'sceneId': 'scene-6', 'questionId': q['id'], 'actionId': 'action-6',
                'beforeQuestionSha256': digest(q), 'afterQuestionSha256': digest({**q, 'question': self.new_question}),
                'text': self.new_question}]}

    def test_free_prepare_then_only_three_paid_lines_and_one_question_audio_link_change(self):
        f = self.f
        prepared = f.run_revision(execute=False)
        self.assertEqual(prepared['segments'], 3)
        f.runtime.start_formal_audio_tts.assert_not_called()
        f.runtime.save_preview_classroom.assert_not_called()
        draft = json.loads((f.archive() / 'target-text.json').read_text())
        self.assertEqual(draft['scenes'][6]['content']['questions'][0],
                         {**self.before_question, 'question': self.new_question})
        receipt = f.run_revision()
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 3)
        after = f.fixture.classroom
        action = after['scenes'][6]['actions'][0]
        question = after['scenes'][6]['content']['questions'][0]
        self.assertEqual(question, {**self.before_question, 'question': self.new_question,
                         'questionAudioUrl': action['audioUrl'].removeprefix(f.runtime.base_url)})
        self.assertNotEqual(question['questionAudioUrl'], self.before_question['questionAudioUrl'])
        for i in (1, 2, 3, 4, 7): self.assertEqual(f.original['scenes'][i], after['scenes'][i])
        self.assertEqual(after['scenes'][6]['content']['questions'][1:], f.original['scenes'][6]['content']['questions'][1:])
        self.assertEqual(interactive_cues(after['scenes'][5]['content']['html'])[0]['text'], f.revision['changes'][1]['text'])
        self.assertEqual(receipt['schemaVersion'], 'mira.textbook.preview-narration-amendment.v2')
        self.assertEqual(receipt['questionChanges'][0]['deliveredQuestionSha256'], digest(question))
        self.assertEqual((f.archive() / 'failed-audit.json').read_bytes(), f.audit_path.read_bytes())
        self.assertEqual((f.folder / 'plan.json').read_bytes(), f.original_plan)
        for name, raw in f.original_wavs.items(): self.assertEqual((f.root / f.cid / 'audio' / name).read_bytes(), raw)
        self.assertEqual(f.run_revision(), receipt)
        f.runtime.save_preview_classroom.assert_called_once()
        f.runtime.start_formal_audio_asr.assert_not_called()

    def test_v1_still_rejects_passing_lexical_mismatch_and_quiz_rewrite(self):
        f = self.f
        for index in (0, 2):
            value = deepcopy(f.revision)
            value['schemaVersion'] = SCHEMA; value.pop('questionChanges')
            value['changes'] = [{k: v for k, v in value['changes'][index].items()
                                 if k not in ('reason', 'auditSegmentSha256')}]
            with self.subTest(index=index), self.assertRaises(ApiError): f.run_revision(execute=False, revision=value)
        f.runtime.start_formal_audio_tts.assert_not_called()

    def test_question_hash_pair_and_verbatim_speech_must_match_without_other_field_changes(self):
        for mutation in ('before', 'after', 'speech', 'extra-answer', 'missing-link', 'wrong-question', 'duplicate'):
            value = deepcopy(self.f.revision); q = value['questionChanges'][0]
            if mutation == 'before': q['beforeQuestionSha256'] = '0' * 64
            elif mutation == 'after': q['afterQuestionSha256'] = digest({**self.before_question, 'question': self.new_question, 'answer': ['B']})
            elif mutation == 'speech': q['text'] = '不同的话。'
            elif mutation == 'extra-answer': q['answer'] = ['B']
            elif mutation == 'missing-link': value['questionChanges'] = []
            elif mutation == 'wrong-question': q['questionId'] = 'q-1'
            else: value['questionChanges'].append(deepcopy(q))
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.f.run_revision(execute=False, revision=value)
        self.f.runtime.start_formal_audio_tts.assert_not_called()

    def test_perfect_asr_stale_segment_receipt_false_aggregate_and_punctuation_only_not_repairable(self):
        original = deepcopy(self.f.audit)
        for mutation in ('perfect', 'punctuation', 'changed-entry-sha', 'false-aggregate', 'failed-receipt'):
            audit, value = deepcopy(original), deepcopy(self.f.revision)
            entry = audit['segments'][0]
            if mutation in ('perfect', 'punctuation'):
                text = entry['text'] if mutation == 'perfect' else entry['text'].replace('，', ',')
                entry.update(transcript=text, similarityBps=asr_similarity_bps(entry['text'], text))
                entry['asr'].update(transcript=text, transcriptSha256=sha_text(text))
                value['changes'][0]['auditSegmentSha256'] = digest(entry)
            elif mutation == 'changed-entry-sha': value['changes'][0]['auditSegmentSha256'] = '0' * 64
            elif mutation == 'false-aggregate': audit['passed'] = True
            else: entry['asr']['status'] = 'failed'; value['changes'][0]['auditSegmentSha256'] = digest(entry)
            pinyin_fixtures.sign(audit)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): text_candidate(self.f.original, value, audit)

    def test_all_passed_aggregate_can_still_repair_real_lexical_mismatch_without_claiming_failure(self):
        audit, value = deepcopy(self.f.audit), deepcopy(self.f.revision)
        for entry in audit['segments'][1:]:
            entry.update(transcript=entry['text'], similarityBps=10000)
            entry['asr'].update(transcript=entry['text'], transcriptSha256=entry['textSha256'])
        audit['passed'] = True; pinyin_fixtures.sign(audit)
        value['changes'] = value['changes'][:1]; value['questionChanges'] = []
        result = text_candidate(self.f.original, value, audit)
        self.assertEqual(result['scenes'][0]['actions'][0]['text'], self.new_done)
        self.assertTrue(audit['passed'])

    def test_lost_tts_response_and_save_response_recover_without_repeating_paid_calls(self):
        f = self.f
        def lost_tts(**kwargs):
            result = f.start_tts(**kwargs)
            if len(f.provider_receipts) == 1: raise TimeoutError('Synthetic response loss')
            return result
        f.runtime.start_formal_audio_tts.side_effect = lost_tts
        with self.assertRaises(TimeoutError): f.run_revision()
        f.runtime.start_formal_audio_tts.side_effect = f.start_tts
        def lost_save(value):
            f.fixture.save(value); raise TimeoutError('Synthetic save response loss')
        f.runtime.save_preview_classroom.side_effect = lost_save
        with self.assertRaises(TimeoutError): f.run_revision()
        receipt = f.run_revision()
        self.assertEqual(f.runtime.start_formal_audio_tts.call_count, 3)
        f.runtime.save_preview_classroom.assert_called_once()
        self.assertEqual(receipt['questionChanges'][0]['deliveredQuestionSha256'],
                         digest(f.fixture.classroom['scenes'][6]['content']['questions'][0]))

    def test_unknown_dispatch_and_tampered_question_target_stop_before_save(self):
        self.f.runtime.start_formal_audio_tts.side_effect = TimeoutError('Synthetic unknown')
        with self.assertRaises(TimeoutError): self.f.run_revision()
        with self.assertRaises(ApiError): self.f.run_revision(retry=True)
        self.f.runtime.start_formal_audio_tts.assert_called_once()
        self.f.runtime.save_preview_classroom.assert_not_called()
        target = text_candidate(self.f.original, self.f.revision, self.f.audit)
        target['scenes'][6]['content']['questions'][0]['points'] = 99
        with self.assertRaises(ApiError): bind_revised_question_audio(target, self.f.revision)

    def test_pinyin_preflight_rejects_unknown_new_token_before_any_execution(self):
        f = pinyin_fixtures.PinyinPublicationTests(); f.setUp(); self.addCleanup(f.doCleanups)
        entry = f.audit['segments'][0]
        transcript = '不同的结果'
        entry.update(transcript=transcript, comparison=compare_transcript(f.plan, entry['text'], transcript))
        entry['similarityBps'] = entry['comparison']['similarityBps']
        entry['asr'].update(transcript=transcript, transcriptSha256=sha_text(transcript))
        f.audit['passed'] = False; pinyin_fixtures.sign(f.audit)
        value = {'schemaVersion': SCHEMA_V2, 'expectedSourceSha256': digest(f.classroom),
            'reviewer': 'Synthetic operator', 'basis': 'Unsupported token preflight', 'questionChanges': [],
            'changes': [{'sceneId': 's1', 'actionId': 'a1', 'beforeTextSha256': sha_text(entry['text']),
                'text': 'unknown，跟老师读。', 'auditSegmentSha256': digest(entry), 'reason': 'asr-lexical-mismatch'}]}
        with self.assertRaises(ApiError): text_candidate(f.classroom, value, f.audit, f.plan)
        value['changes'][0]['text'] = 'e，请再和老师一起读。'
        target = text_candidate(f.classroom, value, f.audit, f.plan)
        self.assertEqual(target['scenes'][0]['actions'][0]['text'], value['changes'][0]['text'])
        f.service.preview.runtime.start_formal_audio_tts.assert_not_called()


class NarrationRevisionOriginAuditTests(unittest.TestCase):
    """The lexical adapter consumes origin provenance without inventing ASR ids."""

    def setUp(self):
        self.f = f = policy_fixtures.PolicyRevisionTests()
        f.setUp(); self.addCleanup(f.doCleanups)
        room = f.f.classroom

        # The older fixture deliberately used one silent WAV for unrelated
        # text. Give each distinct provider body its own PCM, while retaining
        # one shared recording/origin for all six identical “数一数” actions.
        base = f.audio
        audio_by_text = {}
        for index, text in enumerate(dict.fromkeys(
                a['text'] for scene in room['scenes'] for a in scene['actions']), 1):
            raw = bytearray(base); raw[-1] = index
            audio_by_text[text] = bytes(raw)

        receipts, targets, first_by_text = [], [], {}
        for scene in room['scenes']:
            action = scene['actions'][0]
            audio = audio_by_text[action['text']]
            f.audio = audio
            receipt = f.tts_receipt(action['audioId'], action['text'], ZCS_POLICY_VERSION)
            receipt['previewAudioIdentity'] = {'planSha256': digest(f.plan), 'attempt': 1}
            receipts.append(receipt)
            (f.f.root / f.f.cid / 'audio' / (action['audioId'] + '.wav')).write_bytes(audio)
            target = {'sceneId': scene['id'], 'sceneOrder': scene.get('order', 0),
                'action': deepcopy(action), 'ttsReceipt': deepcopy(receipt), 'requestPlan': None,
                'audioBase64': base64.b64encode(audio).decode()}
            targets.append(target); first_by_text.setdefault(action['text'], target)

        origins, origin_by_text = [], {}
        for text, target in first_by_text.items():
            f.audio = base64.b64decode(target['audioBase64'])
            transcript = text.replace('句子', '巨灾') if '句子' in text else text
            response = f.audit_entry({'id': target['sceneId']}, target['action'],
                                     target['ttsReceipt'], transcript)['asr']
            attempt = {'kind': 'formal', 'role': 'routine', 'source': deepcopy(target),
                'plan': deepcopy(f.plan), 'classroomId': f.f.cid,
                'request': formal_request(target, f.plan, f.f.cid, response['requestId']),
                'response': deepcopy(response)}
            origin = {'schemaVersion': ORIGIN_SCHEMA, 'kind': 'formal',
                'source': deepcopy(target), 'plan': deepcopy(f.plan),
                'classroomId': f.f.cid, 'attempts': [attempt]}
            origins.append(origin); origin_by_text[text] = digest(origin)

        self.audit = build_audit(plan=f.plan, classroom=room,
            targets=[{'target': target,
                'originSha256': origin_by_text[target['action']['text']]} for target in targets],
            origins=origins)
        f.receipts = receipts
        f.f.result = {'audioReceipts': receipts, 'audioStopCode': None}
        f.store()
        (f.f.folder / 'receipts.json').write_text(canonical(receipts))
        f.audit = self.audit
        f.audit_path.write_text(canonical(self.audit))
        entry = self.audit['segments'][0]
        self.patch = {'schemaVersion': SCHEMA_V2,
            'expectedSourceSha256': digest(room), 'reviewer': 'Synthetic operator',
            'basis': 'Synthetic origin-audit lexical repair', 'questionChanges': [],
            'changes': [{'sceneId': entry['sceneId'], 'actionId': entry['actionId'],
                'beforeTextSha256': entry['textSha256'],
                'text': '我们一起说一句完整的话。',
                'auditSegmentSha256': digest(entry), 'reason': 'asr-lexical-mismatch'}]}

    def test_origin_audit_prepares_without_provider_and_keeps_shared_request_provenance(self):
        repeated = self.audit['segments'][2:]
        self.assertEqual(len({entry['originSha256'] for entry in repeated}), 1)
        self.assertEqual(len({entry['asr']['requestId'] for entry in repeated}), 1)
        self.assertEqual(len({entry['ttsRequestId'] for entry in repeated}), len(repeated))
        origin = next(item for item in self.audit['origins']
                      if digest(item) == repeated[0]['originSha256'])
        self.assertEqual(repeated[0]['asr']['requestId'],
                         origin['attempts'][0]['response']['requestId'])
        self.assertNotEqual(repeated[-1]['ttsRequestId'],
                            origin['source']['action']['audioId'])
        self.assertLess(self.audit['segments'][0]['comparison']['similarityBps'], 10000)

        prepared = self.f.revise(self.patch, execute=False)
        self.assertTrue(prepared['prepared'])
        self.assertEqual(prepared['segments'], 1)
        archived = json.loads(Path(prepared['failedAudit']).read_text())
        self.assertEqual(archived, self.audit)
        self.f.runtime.start_formal_audio_tts.assert_not_called()
        self.f.runtime.start_formal_audio_asr.assert_not_called()

    def test_tampered_receipt_incomplete_audit_and_wrong_source_are_rejected(self):
        for mutation in ('receipt', 'incomplete', 'source'):
            audit = deepcopy(self.audit)
            if mutation == 'receipt':
                audit['segments'][-1]['target']['ttsReceipt']['providerRequestId'] += '-changed'
            elif mutation == 'incomplete':
                audit['segments'].pop()
            else:
                audit['sourceSha256'] = '0' * 64
            seal(audit)
            self.f.audit_path.write_text(canonical(audit))
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                self.f.revise(self.patch, execute=False)
        self.f.runtime.start_formal_audio_tts.assert_not_called()
        self.f.runtime.start_formal_audio_asr.assert_not_called()

    def test_policy_revision_does_not_accept_origin_audit(self):
        entry = self.audit['segments'][0]
        value = {'schemaVersion': SCHEMA_V3,
            'expectedSourceSha256': self.patch['expectedSourceSha256'],
            'reviewer': 'Synthetic operator', 'basis': 'Synthetic policy mismatch',
            'policyVersion': ZCS_V2_POLICY_VERSION,
            'changes': [{**self.patch['changes'][0], 'text': entry['text'],
                'reason': 'asr-pronunciation-policy-mismatch'}]}
        with self.assertRaises(ApiError):
            self.f.revise(value, execute=False)
        self.f.runtime.start_formal_audio_tts.assert_not_called()
        self.f.runtime.start_formal_audio_asr.assert_not_called()


if __name__ == '__main__': unittest.main()
