"""Mixed-policy lifecycle with isolated DB, real WAV bytes and fake providers.

All browser/authorization objects below are explicitly synthetic test fixtures;
no listening claim, paid request or real publication is made.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from content.textbook_audio_recheck import (SCHEMA as RECHECK_SCHEMA, build_intent, provider_body as asr_body,
    seal, validate_asr_recheck)
from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import bind_interactive_audio, without_audio_helper
from content.textbook_pinyin_operator_review import (AUTHORIZATION_SCHEMA, BROWSER_SCHEMA,
    build_operator_review, validate_operator_review)
from content.textbook_pinyin_pronunciation import (ZCS_POLICY_VERSION as V1, ZCS_V2_POLICY_VERSION as V2,
    registered_policy, select_policy, pinyin_ssml, provider_body, provider_pronunciation, sha_text)
from content.textbook_preview_audio_contract import (new_audio_plan, new_pinyin_audio_plan, tts_request_id,
    asr_request_id, audit_contract_identity, compare_transcript, validate_v2_audit_segment,
    revision_audio_plan, validate_child_request_plan)
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from scripts import audit_textbook_audio as audit_script
from scripts import recheck_textbook_audio as recheck_script
from scripts.recheck_textbook_audio import preflight
from services.textbook_preview_audio import core_content, narrate_preview
from services.textbook_preview_narration_revision import (SCHEMA_V2, SCHEMA_V3, revise_preview_narration, text_candidate)
from services.textbook_publication_service import TextbookPublicationService
from tests import test_textbook_preview_visual_revision as visual_fixtures
from tests.test_textbook_pinyin_pronunciation import bind_audio_fixture, wav_receipt, sign


class PolicyRevisionTests(unittest.TestCase):
    def setUp(self):
        self.f = f = visual_fixtures.VisualRevisionTests(); f.setUp(); self.addCleanup(f.doCleanups)
        self.service, self.runtime = f.service, f.runtime
        frozen = bind_audio_fixture(f)
        frozen.update(nodeId='u3-l3', executionPolicy='operator-authored-saved-classroom.v1',
            authoring={'mode': 'openmaic_pro_workbench', 'request': 'SYNTHETIC fixture'},
            sourceSha256=digest(f.classroom), teachingRevision='1')
        old_key = f.key; f.key = digest({k: v for k, v in frozen.items() if k not in {'previewKey', 'requirement'}})
        frozen['previewKey'] = f.key
        row = dict(f.service.get(old_key))
        row.update(preview_key=f.key, node_id='u3-l3', input_json=canonical(frozen), runtime_job_id='synthetic-policy-revision-job')
        f.db.execute('INSERT INTO learning_textbook_course_previews (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
        f.db.raw.commit()
        self.frozen = frozen
        f.classroom['scenes'][0]['actions'][0]['text'] = '我们一起说一个完整的句子。'
        f.classroom['scenes'][1]['actions'][0]['text'] = 'z，请听老师读。'
        parent = new_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen)
        self.plan = new_pinyin_audio_plan(preview_key=f.key, classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)), frozen_input=frozen, parent_plan=parent, revision_id='d' * 64)
        self.audio = next((f.root / f.cid / 'audio').iterdir()).read_bytes()
        self.receipts = []; segments = []
        for scene in f.classroom['scenes']:
            action = scene['actions'][0]; text = action['text']
            rid = tts_request_id(self.plan, scene['id'], action['id'], text)
            receipt = self.tts_receipt(rid, text, V1)
            receipt['previewAudioIdentity'] = {'planSha256': digest(self.plan), 'attempt': 1}
            self.receipts.append(receipt)
            action.update(audioId=rid, audioUrl=f'/api/classroom-media/{f.cid}/audio/{rid}.wav',
                audioMetadata={'schemaVersion': 'mira.openmaic.speech-audio.v1', 'providerId': 'aliyun-cosyvoice',
                    'modelId': 'cosyvoice-v3-flash', 'voiceId': 'longanwen_v3', 'fallbackUsed': False})
            (f.root / f.cid / 'audio' / (rid + '.wav')).write_bytes(self.audio)
            if scene['type'] == 'interactive':
                scene['content']['html'] = bind_interactive_audio(without_audio_helper(scene['content']['html']), {'ask': action['audioUrl']}, f.cid)
            if scene['type'] == 'quiz':
                for q in scene['content']['questions']: q['questionAudioUrl'] = action['audioUrl']
            transcript = text.replace('句子', '巨灾') if scene['id'] == 'scene-0' else text
            segments.append(self.audit_entry(scene, action, receipt, transcript))
        f.result = {'audioReceipts': self.receipts, 'audioStopCode': None}
        self.store()
        (f.folder / 'plan.json').write_text(canonical(self.plan))
        (f.folder / 'receipts.json').write_text(canonical(self.receipts))
        self.audit = sign({'schemaVersion': 'mira.textbook.audio-audit.v2', 'previewKey': f.key,
            'sourceSha256': digest(f.classroom), 'contract': audit_contract_identity(self.plan), 'segments': segments,
            'passed': all(e['comparison']['passed'] for e in segments)})
        self.output = f.root / 'audit'; self.output.mkdir()
        for e in segments: (self.output / (e['asr']['requestId'] + '.json')).write_text(canonical(e))
        self.audit_path = self.output / 'audit.json'; self.audit_path.write_text(canonical(self.audit))
        self.patch = {'schemaVersion': SCHEMA_V3, 'expectedSourceSha256': digest(f.classroom),
            'reviewer': 'Synthetic operator', 'basis': 'Synthetic explicit Chinese override removal', 'policyVersion': V2,
            'changes': [self.change(segments[0], segments[0]['text'], 'asr-pronunciation-policy-mismatch')]}
        self.original = deepcopy(f.classroom); self.original_plan = (f.folder / 'plan.json').read_bytes()
        self.original_receipts = (f.folder / 'receipts.json').read_bytes()
        self.original_audit = self.audit_path.read_bytes()
        self.original_wavs = {p.name: p.read_bytes() for p in (f.root / f.cid / 'audio').iterdir()}
        self.generated = {}
        self.runtime.get_formal_audio_tts.side_effect = self.get_tts
        self.runtime.start_formal_audio_tts.side_effect = self.start_tts
        self.runtime.download_formal_audio_tts.return_value = self.audio

    def store(self):
        f = self.f
        f.db.execute("UPDATE learning_textbook_course_previews SET status='preview_ready',classroom_json=?,classroom_sha256=?,result_json=? WHERE preview_key=?",
                     (canonical(f.classroom), digest(f.classroom), canonical(f.result), f.key)); f.db.raw.commit()
        (f.root / (f.cid + '.json')).write_text(canonical(f.classroom))

    def tts_receipt(self, rid, text, version):
        return {**wav_receipt(self.audio), 'requestId': rid, 'status': 'succeeded', 'mimeType': 'audio/wav',
            'providerId': 'aliyun-cosyvoice', 'modelId': 'cosyvoice-v3-flash', 'voiceId': 'longanwen_v3',
            'providerRequestId': 'SYNTHETIC-' + rid, 'providerUsage': {'characters': len(text)},
            'budgetMeasurement': {'kind': 'ssml-codepoint-upper-bound', 'characters': len(pinyin_ssml(text, policy_version=version)), 'estimated': True},
            'providerPronunciation': provider_pronunciation(text, policy_version=version)}

    def audit_entry(self, scene, action, receipt, transcript):
        text = action['text']; comparison = compare_transcript(self.plan, text, transcript)
        return {'sceneId': scene['id'], 'actionId': action['id'], 'text': text, 'textSha256': sha_text(text),
            'ttsRequestId': action['audioId'], 'audioSha256': receipt['audioSha256'], 'transcript': transcript,
            'comparison': comparison, 'similarityBps': comparison['similarityBps'], 'durationMs': 1000,
            'asr': {'status': 'succeeded', 'completionUsable': True,
                'requestId': asr_request_id(self.plan, action['audioId'], receipt['audioSha256']),
                'transcript': transcript, 'transcriptSha256': sha_text(transcript),
                'providerId': 'qwen-asr', 'modelId': 'qwen3-asr-flash',
                'providerAsrBodySha256': hashlib.sha256(asr_body(self.audio)).hexdigest(),
                'providerPronunciation': receipt['providerPronunciation']}}

    def get_tts(self, request, **options):
        if request not in self.generated: raise OpenMaicFullRuntimeError('not_found', 'synthetic', status_code=404)
        return deepcopy(self.generated[request])

    def start_tts(self, **kwargs):
        r = self.tts_receipt(kwargs['request_id'], kwargs['text'], kwargs['pronunciation_policy_version'])
        self.generated[r['requestId']] = r
        return deepcopy(r)

    @staticmethod
    def change(entry, text, reason):
        return {'sceneId': entry['sceneId'], 'actionId': entry['actionId'], 'beforeTextSha256': entry['textSha256'],
                'text': text, 'auditSegmentSha256': digest(entry), 'reason': reason}

    def revise(self, value=None, execute=True):
        return revise_preview_narration(self.service, self.f.key, self.f.root, value or self.patch,
                                       self.audit_path, execute=execute)

    def collect(self, *, low=False):
        f = self.f; by_id = {a['audioId']: (s, a) for s in f.classroom['scenes'] for a in s['actions']}
        receipts = {r['requestId']: r for r in json.loads(self.service.get(f.key)['result_json'])['audioReceipts']}
        def asr(**kw):
            scene, action = by_id[kw['tts_request_id']]
            self.assertEqual(kw['pronunciation_policy_version'], receipts[action['audioId']]['providerPronunciation']['policyVersion'])
            transcript = '完全不同的声音' if low else action['text']
            return self.audit_entry(scene, action, receipts[action['audioId']], transcript)['asr']
        self.runtime.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('not_found', 'synthetic', status_code=404)
        self.runtime.start_formal_audio_asr.side_effect = asr
        argv = ['audit', '--key', f.key, '--classroom-directory', str(f.root), '--output', str(self.output), '--collect-only']
        with patch.object(audit_script.AppConfig, 'from_env'), patch.object(audit_script, 'Database', return_value=f.db), \
             patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=self.runtime), patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            audit_script.main()
        self.audit = json.loads(self.audit_path.read_text())
        return self.audit

    def review(self, recheck=None):
        f = self.f; stamp = now_ms(); sha = digest(f.classroom)
        auth = sign({'schemaVersion': AUTHORIZATION_SCHEMA, 'source': 'user-message', 'statement': 'SYNTHETIC TEST authorization',
            'recordedAt': stamp - 100, 'scope': {k: self.plan['binding'][k] for k in ('editionId', 'gradeCode', 'subject')},
            'automatedChecksAuthorized': True, 'publicationAuthorized': True, 'individualListeningConfirmationRequired': False})
        checks = [{'kind': 'picture-supported-layout', 'sceneId': s['id'], 'passed': True,
            'observation': 'SYNTHETIC TEST fixture', 'evidenceSha256': '1' * 64} for s in f.classroom['scenes']]
        checks += [{'kind': 'interaction', 'sceneId': 'scene-5', 'passed': True, 'observation': 'SYNTHETIC fixture', 'evidenceSha256': '2' * 64}]
        e = self.audit['segments'][0]
        checks += [{'kind': 'audio-playback', **{k: e[k] for k in ('sceneId', 'actionId', 'ttsRequestId', 'audioSha256')},
            'passed': True, 'events': ['playing', 'ended'], 'syntheticAudio': False,
            'observation': 'SYNTHETIC TEST fixture only', 'evidenceSha256': '3' * 64}]
        browser = sign({'schemaVersion': BROWSER_SCHEMA, 'sourceSha256': sha, 'coreSha256': self.plan['coreSha256'],
            'planSha256': digest(self.plan), 'method': 'real-browser', 'reviewer': 'Synthetic fixture', 'reviewedAt': stamp,
            'coverage': 'all-scenes-layout-and-recorded-action-samples', 'checks': checks})
        row = self.service.get(f.key)
        plans = [json.loads(p.read_text()) for p in (f.folder / 'narration-revisions').glob('*/plan.json')]
        return build_operator_review(plan=self.plan, classroom=f.classroom, audit=self.audit,
            tts_receipts=json.loads(row['result_json'])['audioReceipts'], authorization=auth, browser_qa=browser,
            reviewer='Synthetic fixture', reviewed_at=stamp, expected_source_sha256=sha, now_ms=stamp,
            request_plans=plans, asr_recheck=recheck)

    def publish_prepare(self, review):
        f = self.f; source_sha = digest(f.classroom)
        teaching = {'alignmentConfirmed': True, 'originalExpressionConfirmed': True, 'sourceUsageConfirmed': True,
            'publicationAuthorized': True, 'reviewer': 'Synthetic fixture', 'basis': 'SYNTHETIC fixture only',
            'sourceSha256': source_sha, 'reviewedAt': now_ms()}
        prepared = TextbookPublicationService(self.service).prepare(key=f.key, edition=self.frozen['editionId'],
            revision=self.frozen['alignmentRevisionId'], node='u3-l3', teaching_revision='1', review=teaching,
            audio_audit=self.audit, classroom_directory=f.root, pronunciation_review=review)
        build = {'status': 'published', 'input_json': canonical(prepared['frozen']), 'review_json': canonical(prepared['review']),
            'content_key': prepared['frozen']['contentKey'], 'node_id': 'u3-l3', 'teaching_revision': '1'}
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        self.parent = {'build': build, 'manifest': manifest, 'preview': dict(self.service.get(f.key)),
            'plan': deepcopy(self.plan), 'receipts': json.loads(self.service.get(f.key)['result_json'])['audioReceipts'],
            'audit': deepcopy(self.audit)}
        return prepared, validate_release(build, manifest)

    def test_only_affected_request_and_original_bytes_survive_full_publication(self):
        self.assertTrue(self.revise(execute=False)['prepared'])
        self.runtime.start_formal_audio_tts.assert_not_called()
        amendment = self.revise()
        self.assertEqual(amendment['schemaVersion'], 'mira.textbook.preview-narration-amendment.v3')
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.assertEqual(self.runtime.start_formal_audio_tts.call_args.kwargs['pronunciation_policy_version'], V2)
        for before, after in zip(self.original['scenes'][1:], self.f.classroom['scenes'][1:]): self.assertEqual(before, after)
        self.assertEqual((self.f.folder / 'plan.json').read_bytes(), self.original_plan)
        archive = self.f.folder / 'narration-revisions' / amendment['revisionId']
        self.assertEqual((archive / 'original-receipts.json').read_bytes(), self.original_receipts)
        self.assertEqual((archive / 'failed-audit.json').read_bytes(), self.original_audit)
        for name, raw in self.original_wavs.items(): self.assertEqual((self.f.root / self.f.cid / 'audio' / name).read_bytes(), raw)
        old_cache = {p.name: p.read_bytes() for p in self.output.glob('tbpasr1_*.json')}
        self.collect(); self.collect()
        self.runtime.start_formal_audio_asr.assert_called_once()
        for name, raw in old_cache.items(): self.assertEqual((self.output / name).read_bytes(), raw)
        self.assertEqual(self.audit['segments'][0]['requestPlan']['pronunciationPolicy']['policyVersion'], V2)
        self.assertNotIn('requestPlan', self.audit['segments'][1])
        prepared, release = self.publish_prepare(self.review())
        self.assertEqual(release['audioAudit']['literalAudit'], self.audit)
        self.assertEqual(prepared['frozen']['audioContract'], self.plan)
        narrate_preview(self.service, self.f.key, self.f.root)
        self.runtime.start_formal_audio_tts.assert_called_once()

    def test_same_text_only_exact_registered_removal_and_all_affected_selection(self):
        self.assertEqual(select_policy(self.frozen)['policyVersion'], V1)
        self.assertEqual(registered_policy(V1)['symbols'], registered_policy(V2)['symbols'])
        self.assertEqual(len(registered_policy(V1)['symbols']), 28)
        for token in registered_policy(V1)['symbols']:
            self.assertEqual(provider_body(token, policy_version=V1), provider_body(token, policy_version=V2))
        self.assertEqual(pinyin_ssml('句子', policy_version=V2), '<speak>句子</speak>')
        self.assertEqual(pinyin_ssml('句子', policy_version=V1), '<speak><phoneme alphabet="py" ph="ju4 zi5">句子</phoneme></speak>')
        self.assertEqual(hashlib.sha256((Path(__file__).parents[1] / 'content/textbook_pinyin_pronunciation_zcs.v1.json').read_bytes()).hexdigest(), 'ce205561b6173fb66587b7f47b233669864ef007e44f74567443d469b5248450')
        for mutate in ('text-change', 'other-policy', 'extra-unaffected', 'missing-affected', 'stale-audit'):
            value = deepcopy(self.patch)
            if mutate == 'text-change': value['changes'][0]['text'] += '请听。'
            elif mutate == 'other-policy': value['policyVersion'] = V1
            elif mutate == 'extra-unaffected': value['changes'].append(self.change(self.audit['segments'][1], self.audit['segments'][1]['text'], 'asr-pronunciation-policy-mismatch'))
            elif mutate == 'missing-affected': value['changes'] = [self.change(self.audit['segments'][1], self.audit['segments'][1]['text'], 'asr-pronunciation-policy-mismatch')]
            else: value['changes'][0]['auditSegmentSha256'] = '0' * 64
            with self.subTest(mutate=mutate), self.assertRaises(ApiError): self.revise(value, execute=False)
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_mixed_audit_requires_exact_child_request_and_no_old_asr_reuse(self):
        self.revise(); self.collect(); e = self.audit['segments'][0]; action = self.f.classroom['scenes'][0]['actions'][0]
        for mutate in ('missing-plan', 'missing-attempt', 'old-asr', 'wrong-parent', 'wrong-policy', 'wrong-model', 'wrong-scene'):
            bad = deepcopy(e)
            if mutate == 'missing-plan': bad.pop('requestPlan')
            elif mutate == 'missing-attempt': bad.pop('ttsAttempt')
            elif mutate == 'old-asr': bad['asr'] = json.loads(self.original_audit)['segments'][0]['asr']
            elif mutate == 'wrong-parent': bad['requestPlan']['parentPlanSha256'] = '0' * 64
            elif mutate == 'wrong-policy': bad['requestPlan']['pronunciationPolicy'] = registered_policy(V1)
            elif mutate == 'wrong-model': bad['requestPlan']['teacher']['voiceId'] = 'other'
            else: bad['sceneId'] = 'other'
            with self.subTest(mutate=mutate), self.assertRaises(ApiError): validate_v2_audit_segment(self.plan, action, bad, scene_id='scene-0')
        review = self.review(); altered = deepcopy(review)
        altered['segments'][0]['ttsReceipt']['providerPronunciation'] = provider_pronunciation(action['text'], policy_version=V1)
        altered['segments'][0]['ttsReceiptSha256'] = digest(altered['segments'][0]['ttsReceipt']); sign(altered)
        with self.assertRaises(ApiError): self.publish_prepare(altered)

    def test_v3_then_v2_revision_retains_both_exact_child_plans(self):
        self.revise(); self.collect()
        unchanged_policy_audio = self.f.classroom['scenes'][0]['actions'][0]['audioId']
        # A separate genuine ASR mismatch on an ordinary line, after v3.
        e = self.audit['segments'][2]; e['transcript'] = '漏读。'
        e['asr'].update(transcript=e['transcript'], transcriptSha256=sha_text(e['transcript']))
        e['comparison'] = compare_transcript(self.plan, e['text'], e['transcript']); e['similarityBps'] = e['comparison']['similarityBps']
        self.audit['passed'] = False; sign(self.audit); self.audit_path.write_text(canonical(self.audit))
        value = {'schemaVersion': SCHEMA_V2, 'expectedSourceSha256': digest(self.f.classroom), 'reviewer': 'Synthetic fixture',
            'basis': 'Separate literal mismatch fixture', 'questionChanges': [],
            'changes': [self.change(e, '请你数一数。', 'asr-lexical-mismatch')]}
        self.revise(value); self.collect()
        self.assertEqual(self.f.classroom['scenes'][0]['actions'][0]['audioId'], unchanged_policy_audio)
        self.assertEqual([c.kwargs['pronunciation_policy_version'] for c in self.runtime.start_formal_audio_tts.call_args_list], [V2, V1])
        review = self.review(); self.assertEqual(len(review['requestPlans']), 2)
        self.publish_prepare(review)
        narrate_preview(self.service, self.f.key, self.f.root)
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)

    def test_low_mixed_asr_once_recheck_and_portable_publish_keep_raw_failure(self):
        self.revise(); self.collect(low=True)
        self.assertFalse(self.audit['passed'])
        with self.assertRaises(ApiError): self.review()
        selection = [{'sceneId': 'scene-0', 'actionId': 'action-0', 'reason': 'Synthetic same-WAV independent check'}]
        plan, classroom, audit, entries = preflight(classroom_path=self.f.root / (self.f.cid + '.json'),
            audio_directory=self.f.root / self.f.cid, audit_path=self.audit_path, selection=selection,
            expected_source_sha256=digest(self.f.classroom))
        original = audit['segments'][0]
        response = {**deepcopy(original['asr']), 'success': True, 'state': 'succeeded',
            'requestId': entries[0]['request']['requestId'], 'transcript': original['text'],
            'transcriptSha256': sha_text(original['text'])}
        dispatched, profile_reads = [], []
        class FakeTransport(OpenMaicFullRuntimeClient):
            def __init__(self, *args, **kwargs):
                super().__init__('http://127.0.0.1:3100', formal_audio_internal_token='synthetic-test-token-with-thirty-two-characters')
            def get_formal_audio_asr(self, request_id, **kwargs):
                profile_reads.append(kwargs['pronunciation_policy_version'])
                raise OpenMaicFullRuntimeError('not_found', 'synthetic', status_code=404)
            def _request_formal_audio_json(self, method, path, body, **kwargs):
                dispatched.append(deepcopy(body)); return deepcopy(response)
        output = self.f.root / 'recheck'; selections = self.f.root / 'selection.json'
        selections.write_text(canonical(selection))
        argv = ['recheck', 'run', '--classroom', str(self.f.root / (self.f.cid + '.json')),
            '--audio-directory', str(self.f.root / self.f.cid), '--audit', str(self.audit_path),
            '--selection', str(selections), '--source-sha256', digest(classroom), '--output', str(output)]
        with patch.object(recheck_script.AppConfig, 'from_env'), \
             patch.object(recheck_script, 'OpenMaicFullRuntimeClient', FakeTransport), patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            recheck_script.main(); recheck_script.main()
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(profile_reads, [V2])
        self.assertNotIn('text', dispatched[0])
        self.assertNotIn('hints', dispatched[0])
        recheck = json.loads((output / 'recheck.json').read_text())
        self.assertEqual(recheck['segments'][0]['requestPlan']['pronunciationPolicy']['policyVersion'], V2)
        self.assertEqual(json.loads((output / 'original-audit.json').read_text()), audit)
        prepared, release = self.publish_prepare(self.review(recheck))
        self.assertFalse(release['audioAudit']['literalAudit']['passed'])
        self.assertEqual(release['audioAudit']['pronunciationReview']['asrRecheck'], recheck)
        bad = deepcopy(recheck); bad['segments'][0]['requestPlan'] = deepcopy(plan); sign(bad)
        with self.assertRaises(ApiError): self.review(bad)
        bad = deepcopy(recheck); r = bad['segments'][0]
        r['asr'].update(transcript='仍然错误', transcriptSha256=sha_text('仍然错误')); r['asrSha256'] = digest(r['asr'])
        r['comparison'] = compare_transcript(plan, original['text'], '仍然错误'); sign(bad)
        with self.assertRaises(ApiError): self.review(bad)

    def test_published_mixed_parent_visual_inheritance_keeps_original_request_identity(self):
        from content.textbook_operator_revision import (VISUAL_PATCH_SCHEMA, revision_candidate,
            inheritance_provenance, visual_audio_acceptance, validate_visual_audio_acceptance)
        from services.textbook_operator_revision_service import inherited_evidence, target_input
        self.revise(); self.collect(); self.publish_prepare(self.review())
        parent = self.parent; source = self.f.classroom
        old = source['scenes'][5]['content']['html']
        visual = {'schemaVersion': 'mira.textbook.preview-visual-patch.v1', 'expectedSourceSha256': digest(source),
            'reviewer': 'Synthetic fixture', 'basis': 'Synthetic layout only', 'changes': [
                {'sceneId': 'scene-5', 'beforeHtmlSha256': sha_text(old), 'html': '<div data-layout="new"></div>' + old}]}
        revision = {'schemaVersion': VISUAL_PATCH_SCHEMA, 'parentContentKey': parent['build']['content_key'],
            'expectedSourceSha256': digest(source), 'teachingRevision': '2', 'reviewer': 'Synthetic fixture',
            'basis': 'Synthetic unchanged audio inheritance', 'changes': []}
        candidate = revision_candidate(parent, revision, visual); frozen = target_input(parent, candidate)
        target_plan = {**deepcopy(self.plan), 'previewKey': frozen['previewKey'],
            'classroomSha256': digest(candidate['classroom']), 'coreSha256': digest(core_content(candidate['classroom'])),
            'revisionId': candidate['revisionId'], 'parentPlanSha256': digest(self.plan)}
        provenance = inheritance_provenance(candidate, target_plan)
        context = {'parent': parent, 'candidate': candidate, 'provenance': provenance, 'archive': self.f.root / self.f.cid,
            'segments': {(s['sceneId'], s['actionId']): s for s in candidate['inheritedSegments']}}
        receipts = {r['requestId']: r for r in parent['receipts']}
        entries = [inherited_evidence(context, target_plan, scene, action, receipts[action['audioId']])
            for scene in candidate['classroom']['scenes'] for action in scene['actions']]
        audit = sign({'schemaVersion': 'mira.textbook.audio-audit.v2', 'previewKey': target_plan['previewKey'],
            'sourceSha256': digest(candidate['classroom']), 'contract': audit_contract_identity(target_plan),
            'operatorParentProvenanceSha256': provenance['sha256'], 'segments': entries,
            'passed': all(e['comparison']['passed'] for e in entries)})
        evidence = visual_audio_acceptance(parent, candidate, target_plan, provenance)
        accepted = validate_visual_audio_acceptance(evidence, plan=target_plan, provenance=provenance,
            classroom=candidate['classroom'], audit=audit)
        self.assertEqual(accepted[('scene-0', 'action-0')]['requestPlan'], self.audit['segments'][0]['requestPlan'])
        # Run the real audit CLI against an inherited preview, where no target
        # narration-revision directory exists. The original proof must suffice.
        room = candidate['classroom']; cid = room['id']; target_root = self.f.root / cid
        (target_root / 'textbook-preview-audio').mkdir(parents=True); (target_root / 'audio').mkdir()
        (target_root / 'textbook-preview-audio/plan.json').write_text(canonical(target_plan))
        for e in entries:
            (target_root / 'audio' / (e['ttsRequestId'] + '.wav')).write_bytes(self.audio)
        row = {'classroom_id': cid, 'classroom_json': canonical(room), 'classroom_sha256': digest(room),
            'input_json': canonical(frozen), 'result_json': canonical({'audioReceipts': parent['receipts']})}
        output = self.f.root / 'inherited-audit'
        argv = ['audit', '--key', target_plan['previewKey'], '--classroom-directory', str(self.f.root),
                '--output', str(output), '--collect-only']
        before_calls = self.runtime.start_formal_audio_asr.call_count
        with patch.object(audit_script.AppConfig, 'from_env'), patch.object(audit_script, 'Database', return_value=self.f.db), \
             patch.object(audit_script, 'OpenMaicFullRuntimeClient', return_value=self.runtime), \
             patch.object(audit_script, 'TextbookPreviewService', return_value=Mock(get=Mock(return_value=row))), \
             patch.object(audit_script, 'load_inheritance', return_value=context), patch('sys.argv', argv), redirect_stdout(io.StringIO()):
            audit_script.main()
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, before_calls)
        self.assertEqual(json.loads((output / 'audit.json').read_text()), audit)
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 1)


if __name__ == '__main__': unittest.main()
