"""Synthetic no-provider fixtures and once-only transport interruption tests."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from content.textbook_audio_recheck import (SCHEMA, build_intent, logical_request, provider_body,
    request_id, seal, validate_asr_recheck)
from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import compare_transcript, revision_audio_plan, tts_request_id, asr_request_id
from content.textbook_pinyin_pronunciation import provider_pronunciation, sha_text
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts.recheck_textbook_audio import dispatch_once, immutable, preflight
from tests.test_textbook_pinyin_pronunciation import PinyinPublicationTests, sign, usage_receipt


def make_recheck(f, *, timestamp=None, make_low=True):
    """Reusable real-WAV fixture for publication's portable recheck integration."""
    timestamp = timestamp or now_ms()
    f.audit.pop('listeningReview', None)
    receipts = {r['requestId']: r for r in json.loads(f.row['result_json'])['audioReceipts']}
    original_texts = {}
    for e in f.audit['segments']:
        audio = (f.root / f.cid / 'audio' / (e['ttsRequestId'] + '.wav')).read_bytes()
        original_texts[(e['sceneId'], e['actionId'])] = e['text']
        e['asr']['providerAsrBodySha256'] = hashlib.sha256(provider_body(audio)).hexdigest()
        if make_low:
            e['transcript'] = '不相同的声音'
            e['asr'].update(transcript=e['transcript'], transcriptSha256=hashlib.sha256(e['transcript'].encode()).hexdigest())
            e['comparison'] = compare_transcript(f.plan, e['text'], e['transcript'])
            e['similarityBps'] = e['comparison']['similarityBps']
    f.audit['passed'] = all(e['comparison']['passed'] for e in f.audit['segments']); sign(f.audit)
    choices = [{'sceneId': e['sceneId'], 'actionId': e['actionId'], 'reason': 'Synthetic original transcript mismatch'}
               for e in f.audit['segments'] if e['similarityBps'] < 10000]
    intent = build_intent(plan=f.plan, classroom=f.classroom, audit=f.audit,
        expected_source_sha256=f.row['classroom_sha256'], selections=choices, created_at=timestamp - 10)
    scenes = {s['id']: s for s in f.classroom['scenes']}; results = []
    for e in f.audit['segments']:
        if e['similarityBps'] == 10000: continue
        scene = scenes[e['sceneId']]; action = next(a for a in scene['actions'] if a['id'] == e['actionId'])
        receipt = receipts[e['ttsRequestId']]
        payload = logical_request(f.plan, f.classroom, scene, action, receipt, e)
        audio = (f.root / f.cid / 'audio' / (e['ttsRequestId'] + '.wav')).read_bytes()
        response = {**e['asr'], 'requestId': payload['requestId'], 'transcript': e['text'],
            'transcriptSha256': hashlib.sha256(e['text'].encode()).hexdigest(), 'completionUsable': True}
        results.append({'sceneId': e['sceneId'], 'actionId': e['actionId'], 'originalSegmentSha256': digest(e),
            'request': payload, 'requestSha256': digest(payload), 'ttsReceipt': deepcopy(receipt),
            'ttsReceiptSha256': digest(receipt), 'audioBase64': base64.b64encode(audio).decode(),
            'asr': response, 'asrSha256': digest(response), 'comparison': compare_transcript(f.plan, e['text'], e['text']),
            'observedAt': timestamp})
    return seal({'schemaVersion': SCHEMA, 'intent': intent, 'segments': results, 'createdAt': timestamp})


class AudioRecheckTests(unittest.TestCase):
    def setUp(self):
        self.f = PinyinPublicationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.now = now_ms(); self.manifest = make_recheck(self.f, timestamp=self.now)

    def validate(self, manifest=None):
        return validate_asr_recheck(manifest if manifest is not None else self.manifest,
            plan=self.f.plan, classroom=self.f.classroom, audit=self.f.audit,
            expected_source_sha256=self.f.row['classroom_sha256'], now_ms=self.now)

    def test_complete_independent_results_preserve_original_false_and_bytes(self):
        before = canonical(self.f.audit)
        result = self.validate()
        self.assertEqual(len(result), 2); self.assertFalse(self.f.audit['passed'])
        self.assertTrue(all(e['comparison']['passed'] for e in result.values()))
        result[('s1', 'a1')]['asr'].clear()
        self.assertEqual(canonical(self.f.audit), before)
        self.assertTrue(self.validate()[('s1', 'a1')]['asr'])

    def test_request_id_independent_of_reason_time_and_output(self):
        e = self.f.audit['segments'][0]
        rid = request_id(e['asr']['requestId'], e['audioSha256'])
        self.assertNotEqual(rid, e['asr']['requestId'])
        manifest = deepcopy(self.manifest)
        manifest['intent']['selection'][0]['reason'] = 'Different operator wording'
        sign(manifest['intent']); sign(manifest)
        self.assertEqual(self.validate(manifest)[('s1', 'a1')]['request']['requestId'], rid)

    def test_missing_duplicate_extra_or_omitted_low_rejected(self):
        for change in ('missing', 'duplicate', 'extra', 'omit-low'):
            m = deepcopy(self.manifest)
            if change == 'missing': m['segments'].pop()
            elif change == 'duplicate': m['segments'].append(deepcopy(m['segments'][0]))
            elif change == 'extra': m['segments'][0]['actionId'] = 'unknown'
            else: m['segments'].pop(); m['intent']['selection'].pop(); sign(m['intent'])
            sign(m)
            with self.subTest(change=change), self.assertRaises(ApiError): self.validate(m)

    def test_forged_request_hints_body_wav_tts_provider_and_transcript_rejected(self):
        for change in ('request-id', 'hint', 'body', 'wav', 'tts', 'provider', 'transcript', 'original-sha'):
            m = deepcopy(self.manifest); e = m['segments'][0]
            if change == 'request-id': e['request']['requestId'] = 'tbpasr1_' + '0' * 64
            elif change == 'hint': e['request']['text'] = self.f.audit['segments'][0]['text']
            elif change == 'body': e['asr']['providerAsrBodySha256'] = '0' * 64
            elif change == 'wav': e['audioBase64'] = base64.b64encode(b'not an audio').decode()
            elif change == 'tts': e['ttsReceipt']['previewAudioIdentity']['planSha256'] = '0' * 64
            elif change == 'provider': e['asr']['modelId'] = 'different'
            elif change == 'transcript': e['asr']['transcript'] = 'forged'
            else: e['originalSegmentSha256'] = '0' * 64
            e['requestSha256'] = digest(e['request']); e['asrSha256'] = digest(e['asr']); e['ttsReceiptSha256'] = digest(e['ttsReceipt']); sign(m)
            with self.subTest(change=change), self.assertRaises(ApiError): self.validate(m)

    def test_still_low_retained_not_replaced_with_maximum_score(self):
        m = deepcopy(self.manifest); e = m['segments'][0]
        e['asr'].update(transcript='仍然不同', transcriptSha256=hashlib.sha256('仍然不同'.encode()).hexdigest())
        e['asrSha256'] = digest(e['asr']); e['comparison'] = compare_transcript(self.f.plan, self.f.audit['segments'][0]['text'], '仍然不同'); sign(m)
        self.assertFalse(self.validate(m)[('s1', 'a1')]['comparison']['passed'])
        e['comparison']['passed'] = True; sign(m)
        with self.assertRaises(ApiError): self.validate(m)

    def test_stale_plan_source_raw_and_future_times_rejected(self):
        for field in ('planSha256', 'sourceSha256', 'rawAuditSha256'):
            m = deepcopy(self.manifest); m['intent'][field] = '0' * 64; sign(m['intent']); sign(m)
            with self.subTest(field=field), self.assertRaises(ApiError): self.validate(m)
        m = deepcopy(self.manifest); m['segments'][0]['observedAt'] = self.now + 1; sign(m)
        with self.assertRaises(ApiError): self.validate(m)

    def revised_single_segment(self):
        f = self.f; action = f.classroom['scenes'][0]['actions'][0]
        previous_id = action['audioId']; action['text'] = 'e，请再和老师一起读。'
        revision = revision_audio_plan(f.plan, revision_id='e' * 64,
            classroom_sha256=digest(f.classroom), core_sha256='f' * 64,
            frozen_input=json.loads(f.row['input_json']))
        rid = tts_request_id(revision, 's1', 'a1', action['text'])
        action.update(audioId=rid, audioUrl=f'/api/classroom-media/{f.cid}/audio/{rid}.wav')
        f.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl'] = action['audioUrl']
        folder = f.root / f.cid / 'textbook-preview-audio'
        archive = folder / 'narration-revisions' / revision['revisionId']; archive.mkdir(parents=True)
        (archive / 'plan.json').write_text(canonical(revision))
        audio_folder = f.root / f.cid / 'audio'
        (audio_folder / (rid + '.wav')).write_bytes((audio_folder / (previous_id + '.wav')).read_bytes())
        receipts = json.loads(f.row['result_json'])['audioReceipts']; receipt = receipts[0]
        receipt.update(requestId=rid, narrationRevisionId=revision['revisionId'],
            classroomContentSha256=revision['classroomSha256'],
            previewAudioIdentity={'planSha256': digest(revision), 'attempt': 1},
            providerPronunciation=provider_pronunciation(action['text']), **usage_receipt(action['text']))
        f.row['result_json'] = canonical({'audioReceipts': receipts})
        (folder / 'receipts.json').write_text(canonical(receipts))
        original = f.audit['segments'][0]
        original.update(text=action['text'], textSha256=sha_text(action['text']), ttsRequestId=rid,
            comparison=compare_transcript(f.plan, action['text'], original['transcript']))
        original['similarityBps'] = original['comparison']['similarityBps']
        original['asr'].update(requestId=asr_request_id(f.plan, rid, original['audioSha256']),
            providerPronunciation=provider_pronunciation(action['text']))
        other = f.audit['segments'][1]; other['transcript'] = other['text']
        other.update(comparison=compare_transcript(f.plan, other['text'], other['text']), similarityBps=10000)
        other['asr'].update(transcript=other['text'], transcriptSha256=sha_text(other['text']))
        source_sha = digest(f.classroom)
        f.row.update(classroom_json=canonical(f.classroom), classroom_sha256=source_sha)
        f.review['sourceSha256'] = source_sha
        f.audit.update(sourceSha256=source_sha, passed=False); sign(f.audit)
        classroom_path = f.root / (f.cid + '.json'); classroom_path.write_text(canonical(f.classroom))
        audit_path = f.root / 'revised-audit.json'; audit_path.write_text(canonical(f.audit))
        kwargs = dict(classroom_path=classroom_path, audit_path=audit_path, audio_directory=f.root / f.cid,
            selection=[{'sceneId': 's1', 'actionId': 'a1', 'reason': 'Synthetic revised WAV mismatch'}],
            expected_source_sha256=source_sha)
        plan, classroom, audit, entries = preflight(**kwargs)
        self.assertEqual(len(entries), 1)
        intent = build_intent(plan=plan, classroom=classroom, audit=audit,
            expected_source_sha256=source_sha, selections=kwargs['selection'], created_at=self.now - 10)
        entry = entries[0]; response = deepcopy(original['asr'])
        response.update(requestId=entry['request']['requestId'], transcript=action['text'],
            transcriptSha256=sha_text(action['text']), completionUsable=True)
        entry.update(asr=response, asrSha256=digest(response),
            comparison=compare_transcript(plan, action['text'], action['text']), observedAt=self.now)
        self.manifest = seal({'schemaVersion': SCHEMA, 'intent': intent, 'segments': entries, 'createdAt': self.now})
        return revision, kwargs, archive

    def test_revision_single_wave_preflight_portable_and_fail_closed(self):
        revision, kwargs, archive = self.revised_single_segment()
        original = canonical(self.f.audit); entry = self.validate()[('s1', 'a1')]
        self.assertEqual(entry['requestPlan'], revision)
        self.assertEqual(entry['request']['classroomContentSha256'], revision['classroomSha256'])
        self.assertNotEqual(entry['request']['classroomContentSha256'], self.f.plan['classroomSha256'])
        for mutation in ('missing-plan', 'parent', 'plan-hash', 'content-sha', 'original-plan'):
            m = deepcopy(self.manifest); e = m['segments'][0]
            if mutation == 'missing-plan': e.pop('requestPlan')
            elif mutation == 'parent': e['requestPlan']['parentPlanSha256'] = '0' * 64
            elif mutation == 'plan-hash': e['ttsReceipt']['previewAudioIdentity']['planSha256'] = '0' * 64
            elif mutation == 'content-sha': e['ttsReceipt']['classroomContentSha256'] = self.f.plan['classroomSha256']
            else: e['requestPlan'] = deepcopy(self.f.plan)
            e['ttsReceiptSha256'] = digest(e['ttsReceipt']); sign(m)
            with self.subTest(mutation=mutation), self.assertRaises(ApiError): self.validate(m)
        self.assertEqual(canonical(self.f.audit), original)
        (archive / 'plan.json').write_text('{}')
        with self.assertRaises(ApiError): preflight(**kwargs)

    def test_revision_recheck_survives_publication_and_still_low_is_rejected(self):
        from tests.test_textbook_pinyin_operator_review import OperatorReviewTests
        from content.textbook_release import validate_release
        revision, _, _ = self.revised_single_segment()
        reviewer = OperatorReviewTests(); reviewer.setUp(); self.addCleanup(reviewer.doCleanups)
        reviewer.f = self.f; reviewer.now = self.now
        reviewer.request_plans = [revision]; reviewer.asr_recheck = self.manifest
        reviewer.browser['sourceSha256'] = self.f.row['classroom_sha256']
        reviewer.browser['checks'][-1]['ttsRequestId'] = self.f.classroom['scenes'][0]['actions'][0]['audioId']
        sign(reviewer.browser); reviewer.review = reviewer.make_review()
        prepared = reviewer.prepare(); release = validate_release(self.f.build(prepared), self.f.manifest)
        self.assertNotEqual(release['classroom']['id'], self.f.cid)
        self.assertEqual(release['audioAudit']['pronunciationReview']['asrRecheck'], self.manifest)
        self.assertFalse(release['audioAudit']['literalPassed'])
        failed = deepcopy(self.manifest); e = failed['segments'][0]
        e['asr'].update(transcript='仍然不同', transcriptSha256=sha_text('仍然不同'))
        e['asrSha256'] = digest(e['asr'])
        e['comparison'] = compare_transcript(self.f.plan, self.f.audit['segments'][0]['text'], '仍然不同')
        reviewer.asr_recheck = sign(failed)
        with self.assertRaises(ApiError): reviewer.make_review()

    def client(self):
        client = Mock()
        client.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('missing', 'missing', status_code=404)
        client._request_formal_audio_json.return_value = {'synthetic': 'raw response'}
        client._validate_formal_asr_response.return_value = self.manifest['segments'][0]['asr']
        return client

    def once(self, client, directory, native=None):
        e = self.manifest['segments'][0]
        return dispatch_once(client, entry=e, directory=directory,
            policy_version=self.f.plan['pronunciationPolicy']['policyVersion'], native_audio_directory=native)

    def test_success_reused_and_intent_precedes_post(self):
        client = self.client(); folder = self.f.root / 'recheck'
        def sent(*args, **kwargs):
            self.assertTrue((folder / 'dispatch-intent.json').exists())
            self.assertEqual(json.loads((folder / 'request.json').read_text()), args[2])
            self.assertNotIn('text', args[2]); return {'synthetic': 'raw response'}
        client._request_formal_audio_json.side_effect = sent
        self.once(client, folder); self.once(client, folder)
        self.assertEqual(client._request_formal_audio_json.call_count, 1)

    def test_unknown_post_then_missing_get_never_redispatches(self):
        client = self.client(); folder = self.f.root / 'recheck'
        client._request_formal_audio_json.side_effect = TimeoutError('response lost')
        with self.assertRaises(TimeoutError): self.once(client, folder)
        with self.assertRaisesRegex(RuntimeError, 'unknown outcome'): self.once(client, folder)
        self.assertEqual(client._request_formal_audio_json.call_count, 1)

    def test_existing_native_in_other_output_never_posts(self):
        client = self.client(); client.get_formal_audio_asr.side_effect = None
        client.get_formal_audio_asr.return_value = {'status': 'running'}
        with self.assertRaisesRegex(RuntimeError, 'read-only recovery'): self.once(client, self.f.root / 'other')
        client._request_formal_audio_json.assert_not_called()

    def test_succeeded_unknown_can_recover_authoritative_transcript_only(self):
        client = self.client(); e = self.manifest['segments'][0]; found = deepcopy(e['asr'])
        found.pop('transcript'); found['completionUsable'] = False
        client.get_formal_audio_asr.side_effect = None; client.get_formal_audio_asr.return_value = found
        native = self.f.root / 'native'; (native / 'transcripts').mkdir(parents=True)
        rid = e['request']['requestId']
        path = native / 'transcripts' / (hashlib.sha256(rid.encode()).hexdigest() + '.json')
        immutable(path, {'requestId': rid, 'audioSha256': e['request']['audioSha256'],
            'transcript': e['asr']['transcript'], 'transcriptSha256': e['asr']['transcriptSha256']})
        self.assertEqual(self.once(client, self.f.root / 'recover', native)['transcript'], e['asr']['transcript'])
        client._request_formal_audio_json.assert_not_called()
        data = json.loads(path.read_text()); data['audioSha256'] = '0' * 64; path.write_text(canonical(data))
        with self.assertRaisesRegex(RuntimeError, 'does not match'): self.once(client, self.f.root / 'bad', native)


if __name__ == '__main__': unittest.main()
