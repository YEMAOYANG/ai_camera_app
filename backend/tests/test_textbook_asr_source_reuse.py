"""Synthetic bytes and fake client only. No real course, provider or browser."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from content.textbook_catalog import canonical, digest
from content.textbook_asr_source_reuse import (
    ORIGIN_SCHEMA, build_audit, validate_audit, verify_origin, target_evidence,
    formal_request, shared_recheck_id, sha, verify_probe_protocol, probe_source,
    build_historical_excess_consensus, verify_origin_library, LIBRARY_SCHEMA_V2,
    EXCESS_ACCEPTANCE,
)
from content.textbook_pinyin_operator_review_v4 import build_operator_review_v4
from content.textbook_pinyin_operator_review import validate_operator_review
from content.textbook_audio_recheck import seal, provider_body as asr_body
from content.textbook_preview_audio_contract import asr_request_id, compare_transcript, revision_audio_plan
from content.textbook_pinyin_pronunciation import provider_body, provider_pronunciation
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.textbook_asr_source_reuse import PcmLedger, collect, immutable
from tests import test_textbook_pinyin_operator_review_v3 as v3fixtures
from tests import test_textbook_pinyin_garden3_v2 as composite_fixtures


def encoded(raw): return base64.b64encode(raw).decode()


class AsrOriginTests(unittest.TestCase):
    def setUp(self):
        self.fx = v3fixtures.AliasOperatorV3Tests(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.f = self.fx.f
        # The old fixture reuses a silent WAV for unrelated phrases. New tests
        # deliberately give different phrases different real PCM identities.
        audio = self.fx.audio
        self.fx.audio = audio[:-2] + b'\x01\x00'
        s = self.f.classroom['scenes'][1]; a = s['actions'][0]
        self.fx.receipts[1] = self.fx.audio_receipt(s, a, self.f.plan)
        self.f.audit['segments'][1] = self.fx.audit_entry(s, a, self.fx.receipts[1], a['text'])
        self.fx.audio = audio; self.fx.sync_source()
        self.targets = [self.target(s, i) for i, s in enumerate(self.f.classroom['scenes'][:2])]
        self.origins = [self.origin(t, self.f.audit['segments'][i]['asr']) for i, t in enumerate(self.targets)]
        self.audit = self.make_audit()
        self.review = self.make_review()

    def target(self, scene, index):
        action = scene['actions'][0]; receipt = self.fx.receipts[index]
        child = self.fx.request_plans[0] if receipt.get('narrationRevisionId') else None
        return {'sceneId': scene['id'], 'sceneOrder': scene.get('order', 0), 'action': deepcopy(action),
            'ttsReceipt': deepcopy(receipt), 'requestPlan': deepcopy(child),
            'audioBase64': encoded((self.f.root/self.f.cid/'audio'/(action['audioId']+'.wav')).read_bytes())}

    def origin(self, target, response):
        plan = deepcopy(self.f.plan)
        attempt = {'kind': 'formal', 'role': 'routine', 'source': deepcopy(target), 'plan': plan,
            'classroomId': self.f.cid, 'request': formal_request(target, plan, self.f.cid, response['requestId']),
            'response': deepcopy(response)}
        return {'schemaVersion': ORIGIN_SCHEMA, 'kind': 'formal', 'source': deepcopy(target),
                'plan': plan, 'classroomId': self.f.cid, 'attempts': [attempt]}

    def excess_origins(self, count=3):
        result = []
        text = self.targets[0]['action']['text']
        for index in range(count):
            scene = {'id': f'excess-s{index}', 'order': index + 1}
            action = {'id': f'excess-a{index}', 'type': 'speech', 'text': text}
            receipt = self.fx.audio_receipt(scene, action, self.f.plan)
            source = {'sceneId': scene['id'], 'sceneOrder': scene['order'], 'action': deepcopy(action),
                'ttsReceipt': deepcopy(receipt), 'requestPlan': None,
                'audioBase64': encoded(self.fx.audio)}
            response = self.fx.audit_entry(scene, action, receipt, text)['asr']
            result.append(self.origin(source, response))
        return result

    def install_excess_history(self, native, origins):
        for origin in origins:
            source = origin['source']; response = origin['attempts'][0]['response']
            immutable(native/'jobs/tts'/(sha(source['action']['audioId'].encode())+'.json'), source['ttsReceipt'])
            immutable(native/'jobs/asr'/(sha(response['requestId'].encode())+'.json'), {
                'requestId': response['requestId'], 'ttsRequestId': source['action']['audioId'],
                'state': 'succeeded', 'audioSha256': response['audioSha256'] if 'audioSha256' in response
                    else source['ttsReceipt']['audioSha256'],
                'transcriptSha256': response['transcriptSha256']})

    def make_audit(self):
        return build_audit(plan=self.f.plan, classroom=self.f.classroom,
            targets=[{'target': t, 'originSha256': digest(o)} for t, o in zip(self.targets, self.origins)],
            origins=list({digest(o): o for o in self.origins}.values()))

    def make_review(self):
        return build_operator_review_v4(plan=self.f.plan, classroom=self.f.classroom, audit=self.audit,
            authorization=self.fx.auth, browser_qa=self.fx.browser, reviewer='Synthetic fixture only',
            reviewed_at=self.fx.now, expected_source_sha256=digest(self.f.classroom), now_ms=self.fx.now)

    def validate(self, audit=None, review=None):
        return validate_operator_review(review or self.review, plan=self.f.plan, classroom=self.f.classroom,
            audit=audit or self.audit, expected_source_sha256=digest(self.f.classroom), now_ms=self.fx.now)

    def prepare(self):
        self.f.audit = self.audit
        return self.fx.prepare(self.review)

    def test_prepare_portable_preserves_raw_failed_and_original_request(self):
        original = canonical(self.origins)
        self.assertFalse(self.audit['passed']); self.assertEqual(self.audit['segments'][0]['similarityBps'], 0)
        release = self.fx.read(self.prepare())
        self.assertEqual(release['audioAudit']['literalAudit'], self.audit)
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertEqual(release['audioAudit']['acceptanceMethod'], 'automatic-asr-original-source-reuse')
        self.assertEqual(canonical(self.origins), original)
        self.assertEqual(len(self.validate()), 2)
        for key in ('humanListeningVerified', 'phoneticAccuracyVerified', 'perceptualToneVerified'):
            self.assertFalse(self.review[key]); self.assertFalse(self.audit[key])

    def test_same_wav_duplicate_target_uses_original_not_relabelled_asr(self):
        scene = self.f.classroom['scenes'][1]; a = scene['actions'][0]; a['text'] = self.targets[0]['action']['text']
        self.fx.receipts[1] = self.fx.audio_receipt(scene, a, self.f.plan)
        self.fx.sync_source(); self.targets[1] = self.target(scene, 1)
        self.origins[1] = self.origins[0]; self.audit = self.make_audit(); self.review = self.make_review()
        self.assertEqual(len(self.audit['origins']), 1)
        self.assertNotEqual(self.audit['segments'][1]['ttsRequestId'], self.audit['segments'][0]['ttsRequestId'])
        self.assertEqual(self.audit['segments'][1]['asr'], self.audit['segments'][0]['asr'])
        self.fx.read(self.prepare())

    def test_actual_wav_pcm_body_text_and_target_id_tampering_rejected(self):
        for kind in ('wav', 'pcm', 'text', 'voice', 'body', 'original-id', 'target-id', 'source-id', 'comparison'):
            audit = deepcopy(self.audit); e = audit['segments'][0]; o = audit['origins'][0]
            if kind == 'wav': e['target']['audioBase64'] = self.targets[1]['audioBase64']
            elif kind == 'pcm': e['target']['ttsReceipt']['pcmSha256'] = '0'*64
            elif kind == 'text': e['target']['action']['text'] += '多读'
            elif kind == 'voice': e['target']['action']['audioMetadata']['voiceId'] = 'other'
            elif kind == 'body': o['attempts'][0]['response']['providerAsrBodySha256'] = '0'*64
            elif kind == 'original-id': o['attempts'][0]['response']['requestId'] = 'tbpasr1_'+'0'*64
            elif kind == 'target-id': e['target']['action']['audioId'] = self.targets[1]['action']['audioId']
            elif kind == 'source-id': o['classroomId'] = 'different'
            else: e['comparison']['passed'] = True; e['similarityBps'] = 10000
            seal(audit)
            with self.subTest(kind=kind), self.assertRaises(ApiError): self.validate(audit=audit)

    def test_same_pcm_cannot_split_into_two_origins(self):
        scene = self.f.classroom['scenes'][1]; a = scene['actions'][0]; a['text'] = self.targets[0]['action']['text']
        self.fx.receipts[1] = self.fx.audio_receipt(scene, a, self.f.plan); self.fx.sync_source()
        self.targets[1] = self.target(scene, 1)
        response = self.fx.audit_entry(scene, a, self.fx.receipts[1], '擦玻璃。')['asr']
        self.origins[1] = self.origin(self.targets[1], response); self.audit = self.make_audit()
        with self.assertRaisesRegex(ApiError, 'one complete origin'): self.make_review()

    def test_source_and_browser_still_required_and_old_versions_cannot_route_new_audit(self):
        for key in ('sourceSha256', 'coreSha256', 'planSha256', 'humanListeningVerified'):
            bad = deepcopy(self.review); bad[key] = 'altered'; seal(bad)
            with self.subTest(key=key), self.assertRaises(ApiError): self.validate(review=bad)
        old = deepcopy(self.fx.browser); self.fx.browser['checks'] = []; seal(self.fx.browser)
        with self.assertRaises(ApiError): self.make_review()
        self.fx.browser = old
        for version in ('v1', 'v2', 'v3'):
            bad = deepcopy(self.review); bad['schemaVersion'] = 'mira.textbook.pinyin-operator-review.'+version; seal(bad)
            with self.subTest(version=version), self.assertRaises(ApiError): self.validate(review=bad)

    def test_alias_remains_exact_full_text_and_not_tone_evidence(self):
        for transcript in ('擦波璃。', '擦😀玻璃。', '擦\u200b玻璃。', '请擦玻璃。'):
            o = deepcopy(self.origins[0]); response = o['attempts'][0]['response']
            response.update(transcript=transcript, transcriptSha256=sha(transcript.encode()))
            self.origins[0] = o; self.audit = self.make_audit()
            with self.subTest(transcript=transcript), self.assertRaises(ApiError): self.make_review()

    def test_original_low_needs_recheck_and_both_carrier_exact_not_threshold_relaxation(self):
        scene = self.f.classroom['scenes'][1]; a = scene['actions'][0]; a['text'] = 'qí mǎ。'
        oldaudio = self.fx.audio; self.fx.audio = oldaudio[:-2]+b'\x02\x00'
        self.fx.receipts[1] = self.fx.audio_receipt(scene, a, self.f.plan); self.fx.audio = oldaudio
        self.fx.sync_source(); self.targets[1] = self.target(scene, 1)
        response = self.fx.audit_entry(scene, a, self.fx.receipts[1], '骑马。')['asr']
        response['providerAsrBodySha256'] = sha(asr_body(base64.b64decode(self.targets[1]['audioBase64'])))
        self.origins[1] = self.origin(self.targets[1], response); self.audit = self.make_audit()
        with self.assertRaisesRegex(ApiError, 'requires an independent'): self.make_review()
        o = self.origins[1]; facts = verify_origin(o); second = deepcopy(o['attempts'][0])
        second['role'] = 'recheck'; rid = shared_recheck_id(facts['pcmKey'])
        second['request']['requestId'] = rid; second['response']['requestId'] = rid; o['attempts'].append(second)
        self.audit = self.make_audit(); self.review = self.make_review()
        self.assertEqual(self.review['segments'][1]['acceptanceMethod'], 'exact-carrier-orthography-both-asr')
        self.fx.read(self.prepare())
        second['response'].update(transcript='骑蚂。', transcriptSha256=sha('骑蚂。'.encode()))
        self.audit = self.make_audit()
        with self.assertRaises(ApiError): self.make_review()

    def test_publication_rechecks_disk_wav_and_authoritative_receipt(self):
        path = self.f.root/self.f.cid/'audio'/(self.targets[0]['action']['audioId']+'.wav')
        path.write_bytes(path.read_bytes()[:-2]+b'\x07\x00')
        with self.assertRaises(ApiError): self.prepare()

    def test_revision_child_plan_missing_archive_cannot_publish(self):
        f = self.f; scene = f.classroom['scenes'][0]; a = scene['actions'][0]
        child = revision_audio_plan(f.plan, revision_id='e'*64, classroom_sha256=digest(f.classroom),
            core_sha256=f.plan['coreSha256'], frozen_input=self.fx.frozen)
        self.fx.request_plans = [child]
        self.fx.receipts[0] = self.fx.audio_receipt(scene, a, child); self.fx.sync_source()
        self.targets[0] = self.target(scene, 0)
        response = self.fx.audit_entry(scene, a, self.fx.receipts[0], '擦玻璃。')['asr']
        self.fx.browser['checks'][-1]['ttsRequestId'] = a['audioId']; seal(self.fx.browser)
        self.origins[0] = self.origin(self.targets[0], response)
        self.audit = self.make_audit(); self.review = self.make_review()
        with self.assertRaises(ApiError): self.prepare()
        directory = f.root/f.cid/'textbook-preview-audio/narration-revisions'/child['revisionId']; directory.mkdir(parents=True)
        (directory/'plan.json').write_text(canonical(child))
        self.fx.read(self.prepare())

    def ledger_setup(self):
        directory = Path(tempfile.mkdtemp()); self.addCleanup(__import__('shutil').rmtree, directory)
        native = directory/'native'; (native/'jobs/asr').mkdir(parents=True); (native/'jobs/tts').mkdir()
        probe = directory/'probes'; probe.mkdir()
        ledger = PcmLedger(directory/'classrooms', native, [probe])
        return directory, native, probe, ledger

    def fake_client(self, target, transcript):
        client = Mock()
        client.get_formal_audio_asr.side_effect = OpenMaicFullRuntimeError('missing', 'fixture', status_code=404)
        def post(method, path, request):
            self.assertEqual(set(request), set(formal_request(target, self.f.plan, self.f.cid, request['requestId'])))
            return {**self.fx.audit_entry({'id':target['sceneId']}, target['action'], target['ttsReceipt'], transcript)['asr'],
                    'requestId': request['requestId'],
                    'providerAsrBodySha256':sha(asr_body(base64.b64decode(target['audioBase64'])))}
        client._request_formal_audio_json.side_effect = post
        client._validate_formal_asr_response.side_effect = lambda response, **kwargs: response
        return client

    def test_cross_output_single_post_recovery_and_unknown_blocks(self):
        _, _, _, ledger = self.ledger_setup(); t = self.targets[1]
        origin = deepcopy(self.origins[1]); origin['attempts'] = []
        client = self.fake_client(t, t['action']['text'])
        first = ledger.dispatch(origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        second = ledger.dispatch(origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        self.assertEqual(first, second); self.assertEqual(client._request_formal_audio_json.call_count, 1)
        claim = next(ledger.root.rglob('response.json')); claim.unlink()
        with self.assertRaisesRegex(RuntimeError, 'Unknown prior'): ledger.dispatch(origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        self.assertEqual(client._request_formal_audio_json.call_count, 1)

    def test_old_unknown_or_overbudget_native_claims_prevent_new_ids(self):
        for count in (1, 3):
            _, native, _, ledger = self.ledger_setup(); t = self.targets[1]
            origin = deepcopy(self.origins[1]); origin['attempts'] = []
            rid = t['action']['audioId']; immutable(native/'jobs/tts'/(sha(rid.encode())+'.json'), t['ttsReceipt'])
            for i in range(count): immutable(native/'jobs/asr'/('x'+str(i)+'.json'),
                {'requestId':'historical-'+str(i), 'ttsRequestId':rid, 'state':'ambiguous', 'audioSha256':t['ttsReceipt']['audioSha256']})
            client = self.fake_client(t, t['action']['text'])
            with self.subTest(count=count), self.assertRaises(RuntimeError): ledger.dispatch(origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
            client._request_formal_audio_json.assert_not_called()

    def test_one_recheck_shared_across_actions_and_no_third(self):
        _, _, _, ledger = self.ledger_setup(); t = self.targets[1]
        client = self.fake_client(t, t['action']['text'])
        result = ledger.dispatch(origin=self.origins[1], source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        self.assertEqual(len(result['attempts']), 2)
        with self.assertRaisesRegex(RuntimeError, 'already retained'): ledger.dispatch(origin=result, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        self.assertEqual(client._request_formal_audio_json.call_count, 1)

    def test_historical_excess_consensus_is_versioned_literal_and_v4_accepted(self):
        children = self.excess_origins(3)
        consensus = build_historical_excess_consensus(children)
        facts = verify_origin(consensus)
        self.assertEqual(len(facts['attempts']), 3)
        self.assertEqual(facts['historicalExcessConsensus']['disposition'], EXCESS_ACCEPTANCE)
        self.assertEqual(facts['historicalExcessConsensus']['requestIds'],
            [verify_origin(item)['attempts'][0]['requestId'] for item in children])
        library = {'schemaVersion': LIBRARY_SCHEMA_V2, 'origins': [consensus, self.origins[1]],
            'probeProtocol': None}
        verify_origin_library(library, self.f.plan)
        audit = build_audit(plan=self.f.plan, classroom=self.f.classroom,
            targets=[{'target': self.targets[0], 'originSha256': digest(consensus)},
                     {'target': self.targets[1], 'originSha256': digest(self.origins[1])}],
            origins=library['origins'])
        review = build_operator_review_v4(plan=self.f.plan, classroom=self.f.classroom, audit=audit,
            authorization=self.fx.auth, browser_qa=self.fx.browser, reviewer='Synthetic fixture only',
            reviewed_at=self.fx.now, expected_source_sha256=digest(self.f.classroom), now_ms=self.fx.now)
        methods = {(item['sceneId'], item['actionId']): item['acceptanceMethod'] for item in review['segments']}
        self.assertEqual(methods[(self.targets[0]['sceneId'], self.targets[0]['action']['id'])], EXCESS_ACCEPTANCE)
        validate_audit(audit, plan=self.f.plan, classroom=self.f.classroom,
            expected_source_sha256=digest(self.f.classroom))
        validate_operator_review(review, plan=self.f.plan, classroom=self.f.classroom, audit=audit,
            expected_source_sha256=digest(self.f.classroom), now_ms=self.fx.now)
        self.audit, self.review = audit, review
        release = self.fx.read(self.prepare())
        self.assertEqual(release['audioAudit']['acceptanceMethod'],
            'automatic-asr-original-source-reuse')

    def test_historical_excess_ledger_requires_exact_history_and_never_dispatches(self):
        children = self.excess_origins(3); consensus = build_historical_excess_consensus(children)
        _, native, _, ledger = self.ledger_setup(); self.install_excess_history(native, children)
        client = self.fake_client(self.targets[0], self.targets[0]['action']['text'])
        library = {'schemaVersion': LIBRARY_SCHEMA_V2,
            'origins': [consensus, self.origins[1]], 'probeProtocol': None}
        audit = collect(plan=self.f.plan, classroom=self.f.classroom, targets=self.targets,
            library=library, ledger=ledger, client=client)
        self.assertTrue(audit['passed'])
        client._request_formal_audio_json.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'permanently forbids'):
            collect(plan=self.f.plan, classroom=self.f.classroom, targets=self.targets,
                library=library, ledger=ledger, client=client,
                recheck_keys=[(self.targets[0]['sceneId'], self.targets[0]['action']['id'])])
        with self.assertRaisesRegex(RuntimeError, 'permanently forbids'):
            ledger.dispatch(origin=consensus, source=self.targets[0], plan=self.f.plan,
                classroom_id=self.f.cid, client=client)
        client._request_formal_audio_json.assert_not_called()

    def test_historical_excess_missing_extra_low_or_inconsistent_is_rejected(self):
        children = self.excess_origins(3)
        with self.assertRaises(ApiError): build_historical_excess_consensus(children[:2])
        low = deepcopy(children)
        response = low[1]['attempts'][0]['response']; response['transcript'] = '不一致。'
        response['transcriptSha256'] = sha(response['transcript'].encode())
        with self.assertRaisesRegex(ApiError, 'literal exact'):
            build_historical_excess_consensus(low)
        mixed = deepcopy(children); mixed[2] = deepcopy(self.origins[1])
        with self.assertRaisesRegex(ApiError, 'identical text'):
            build_historical_excess_consensus(mixed)
        consensus = build_historical_excess_consensus(children)
        changed = deepcopy(consensus); changed['investigation']['requestIds'].reverse()
        with self.assertRaisesRegex(ApiError, 'missing, changed or unsealed'): verify_origin(changed)
        with self.assertRaisesRegex(ApiError, 'v2 library'):
            verify_origin_library({'schemaVersion':'mira.textbook.asr-origin-library.v1',
                'origins':[consensus], 'probeProtocol':None}, self.f.plan)

        _, native, _, ledger = self.ledger_setup(); self.install_excess_history(native, children[:2])
        with self.assertRaisesRegex(RuntimeError, 'exactly equal'):
            ledger.inspect(origin=consensus, facts=verify_origin(consensus))
        _, native, _, ledger = self.ledger_setup(); self.install_excess_history(native, children)
        extra = deepcopy(children[0]); source = extra['source']; response = extra['attempts'][0]['response']
        immutable(native/'jobs/asr'/'extra.json', {'requestId':'unexpected-history',
            'ttsRequestId':source['action']['audioId'], 'state':'failed',
            'audioSha256':source['ttsReceipt']['audioSha256'],
            'transcriptSha256':response['transcriptSha256']})
        with self.assertRaisesRegex(RuntimeError, 'exactly equal'):
            ledger.inspect(origin=consensus, facts=verify_origin(consensus))

    def test_readonly_native_recovery_without_redispatch_or_relabelling(self):
        _, native, _, ledger = self.ledger_setup(); t = self.targets[1]
        origin = deepcopy(self.origins[1]); original = origin['attempts'][0]['response']; origin['attempts'] = []
        rid = original['requestId']; transcript = {k: original[k] for k in ('requestId', 'transcript', 'transcriptSha256')}
        transcript['audioSha256'] = t['ttsReceipt']['audioSha256']
        immutable(native/'transcripts'/(sha(rid.encode())+'.json'), transcript)
        client = self.fake_client(t, t['action']['text']); client.get_formal_audio_asr.side_effect = None
        client.get_formal_audio_asr.return_value = {**original, 'transcript':None, 'completionUsable':False}
        result = ledger.dispatch(origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        self.assertEqual(result['attempts'][0]['response'], original)
        client._request_formal_audio_json.assert_not_called()
        # A different output invocation still reads the same managed recovery.
        again = PcmLedger(ledger.root.parent, native, ledger.probe_roots).dispatch(
            origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        self.assertEqual(again, result); client._request_formal_audio_json.assert_not_called()

    def test_unknown_probe_claim_consumes_pcm_even_without_receipt(self):
        _, _, probe, ledger = self.ledger_setup(); t = self.targets[1]
        origin = deepcopy(self.origins[1]); origin['attempts'] = []
        directory = probe/'a-different-output'/'asr-once'
        immutable(directory/'intent.json', {'schemaVersion':'mira.operator.probe-asr-intent.v1',
            'requestId':'old-unknown', 'audioSha256':t['ttsReceipt']['audioSha256']})
        immutable(directory/'request.json', json.loads(asr_body(base64.b64decode(t['audioBase64']))))
        client = self.fake_client(t, t['action']['text'])
        with self.assertRaisesRegex(RuntimeError, 'historical PCM claims'):
            ledger.dispatch(origin=origin, source=t, plan=self.f.plan, classroom_id=self.f.cid, client=client)
        client._request_formal_audio_json.assert_not_called()
        self.assertTrue(list(ledger.root.rglob('history/*.json')))

    def test_collect_duplicate_targets_one_call_then_literal_raw_failure_retained(self):
        scene = self.f.classroom['scenes'][1]; a = scene['actions'][0]; a['text'] = self.targets[0]['action']['text']
        self.fx.receipts[1] = self.fx.audio_receipt(scene, a, self.f.plan); self.fx.sync_source()
        self.targets[1] = self.target(scene, 1)
        _, _, _, ledger = self.ledger_setup(); client = self.fake_client(self.targets[0], '擦玻璃。')
        library = {'schemaVersion':'mira.textbook.asr-origin-library.v1', 'origins':[], 'probeProtocol':None}
        result = collect(plan=self.f.plan, classroom=self.f.classroom, targets=self.targets,
            library=library, ledger=ledger, client=client)
        self.assertEqual(len(result['origins']),1); self.assertFalse(result['passed'])
        self.assertEqual(client._request_formal_audio_json.call_count,1)
        validate_audit(result,plan=self.f.plan,classroom=self.f.classroom,expected_source_sha256=digest(self.f.classroom))

    def test_provider_free_cli_prepare_validates_actual_files(self):
        from scripts.audit_textbook_audio_origins import prepare
        directory = self.f.root/self.f.cid
        (directory/'textbook-preview-audio/receipts.json').write_text(canonical(self.fx.receipts))
        classroom = self.f.root/'input-classroom.json'; classroom.write_text(canonical(self.f.classroom))
        library = self.f.root/'library.json'; library.write_text(canonical({
            'schemaVersion':'mira.textbook.asr-origin-library.v1','origins':self.origins,'probeProtocol':None}))
        plan, source, targets, original = prepare(classroom,directory,library,digest(self.f.classroom))
        self.assertEqual(plan,self.f.plan); self.assertEqual(source,self.f.classroom)
        self.assertEqual(len(targets),2); self.assertEqual(original['origins'],self.origins)

    def test_exact_alias_recheck_exclusion_uses_verified_complete_origin(self):
        _, _, _, ledger = self.ledger_setup(); client = self.fake_client(self.targets[0], '擦玻璃。')
        library = {'schemaVersion':'mira.textbook.asr-origin-library.v1', 'origins':self.origins, 'probeProtocol':None}
        with self.assertRaisesRegex(RuntimeError, 'needs no additional'):
            collect(plan=self.f.plan,classroom=self.f.classroom,targets=self.targets,library=library,
                ledger=ledger,client=client,recheck_keys=[('s1','a1')])
        client._request_formal_audio_json.assert_not_called()

    def test_zero_post_reuse_cannot_omit_known_failed_or_unknown_recheck(self):
        _, native, _, ledger=self.ledger_setup();t=self.targets[1]
        immutable(native/'jobs/tts'/(sha(t['action']['audioId'].encode())+'.json'),t['ttsReceipt'])
        library={'schemaVersion':'mira.textbook.asr-origin-library.v1','origins':self.origins,'probeProtocol':None}
        client=self.fake_client(t,t['action']['text'])
        for status in ('failed','running'):
            path=native/'jobs/asr'/'concern.json'
            path.write_text(canonical({'requestId':'original-concern','ttsRequestId':t['action']['audioId'],
                'state':status,'audioSha256':t['ttsReceipt']['audioSha256']}))
            with self.subTest(status=status),self.assertRaisesRegex(RuntimeError,'omits known'):
                collect(plan=self.f.plan,classroom=self.f.classroom,targets=self.targets,library=library,ledger=ledger,client=client)
        client._request_formal_audio_json.assert_not_called()
        bad=deepcopy(library);bad['origins'][0]['attempts'][0]['response']['providerAsrBodySha256']='0'*64
        with self.assertRaises(ApiError):
            collect(plan=self.f.plan,classroom=self.f.classroom,targets=self.targets,library=bad,
                ledger=ledger,client=client,recheck_keys=[('s1','a1')])
        client._request_formal_audio_json.assert_not_called()

    def test_collect_prevalidates_all_before_post_and_same_text_is_insufficient(self):
        _, _, _, ledger = self.ledger_setup(); client = self.fake_client(self.targets[0], '擦玻璃。')
        library = {'schemaVersion':'mira.textbook.asr-origin-library.v1', 'origins':[], 'probeProtocol':None}
        bad = deepcopy(self.targets); bad[1]['ttsReceipt']['pcmSha256'] = '0'*64
        with self.assertRaises(ApiError): collect(plan=self.f.plan, classroom=self.f.classroom, targets=bad, library=library, ledger=ledger, client=client)
        client._request_formal_audio_json.assert_not_called()

    def test_real_probe_protocol_retains_preregistration_and_historical_policy(self):
        fx = composite_fixtures.CompositeInitializationTests(); fx.setUp(); self.addCleanup(fx.doCleanups)
        from services.textbook_pronunciation_probe_composite import evidence_names
        package = {'files': {n: encoded((fx.dir/n.removeprefix('evidence/')).read_bytes()) for n in evidence_names()}}
        protocol = {'probePlanSha256': fx.review['probePlanSha256'], 'samples': fx.review['samples'],
                    'previewBound':False,'formalUseAllowed':False,'humanListeningVerified':False,'perceptualToneVerified':False}
        package['files']['evidence/operator-probe-review.json'] = encoded(canonical(protocol).encode())
        files = verify_probe_protocol(package, self.f.plan)
        o = {'schemaVersion':ORIGIN_SCHEMA, 'kind':'probe-composition', 'label':'ca-boli-natural-alias','attempts':[]}
        facts = probe_source(o, files); response = {'request_id':'synthetic-asr-provider', 'usage':{},
            'output':{'choices':[{'finish_reason':'stop','message':{'content':[{'text':'擦玻璃。'}]}}]}}
        request = canonical(json.loads(asr_body(facts['audio']))).encode()
        common = {'requestId':'original-prereg-asr', 'requestSha256':sha(request), 'audioSha256':sha(facts['audio']),
            'planSha256':facts['originPlanSha256'],'label':facts['label'], 'asrPlanSha256':'a'*64,
            'provider':'qwen-asr','model':'qwen3-asr-flash','formalUseAllowed':False,
            'humanListeningVerified':False,'perceptualToneVerified':False,'expectedTextSentToProvider':False}
        receipt = {**common,'schemaVersion':'mira.operator.probe-asr-receipt.v1','status':'succeeded','postAttempts':1,
            'completedAt':'2026-01-01T00:00:02Z',
            'comparison':{'method':'original-text-literal-levenshtein','passed':False,'similarityBps':0,'thresholdBps':8500},
            'transcript':'擦玻璃。','transcriptSha256':sha('擦玻璃。'.encode()),'providerResponseSha256':digest(response),
            'providerRequestId':response['request_id'],'usage':{},'requestBytes':len(request), 'text':facts['text'],
            'textSha256':sha(facts['text'].encode()),'ttsReceiptSha256':facts['receiptFileSha256'],
            'ssmlSha256':sha(facts['body']['input']['text'].encode()),'pcmSha256':facts['receipt']['pcmSha256']}
        o['attempts']=[{'kind':'probe','role':'routine','files':{
            'request.json':encoded(request),'intent.json':encoded(canonical({**common,'maxPostAttempts':1,
                'schemaVersion':'mira.operator.probe-asr-intent.v1','createdAt':'2026-01-01T00:00:01Z'}).encode()),
            'receipt.json':encoded(canonical(receipt).encode()),'provider-response.json':encoded(canonical(response).encode())}}]
        self.origins[0] = o
        self.audit = build_audit(plan=self.f.plan,classroom=self.f.classroom,
            targets=[{'target':t,'originSha256':digest(o)} for t,o in zip(self.targets,self.origins)],
            origins=self.origins,probe_protocol=package)
        self.review=self.make_review(); self.fx.read(self.prepare())
        self.assertNotIn('policyVersion',receipt)
        bad=deepcopy(o); original=deepcopy(receipt); original['policyVersion']='mira.textbook.pinyin-garden3-ssml.v2'
        bad['attempts'][0]['files']['receipt.json']=encoded(canonical(original).encode())
        with self.assertRaisesRegex(ApiError,'Pre-registration'): verify_origin(bad,probe_files=files)

    def historical_probe_fixture(self, label='ca-boli-natural-alias'):
        fx = composite_fixtures.CompositeInitializationTests(); fx.setUp(); self.addCleanup(fx.doCleanups)
        from services.textbook_pronunciation_probe_composite import evidence_names
        from services.learning_media_materialization_service import asr_similarity_bps
        package = {'files': {n: encoded((fx.dir/n.removeprefix('evidence/')).read_bytes()) for n in evidence_names()}}
        protocol = {'probePlanSha256':fx.review['probePlanSha256'], 'samples':fx.review['samples'],
            'previewBound':False,'formalUseAllowed':False,'humanListeningVerified':False,'perceptualToneVerified':False}
        package['files']['evidence/operator-probe-review.json'] = encoded(canonical(protocol).encode())
        files = verify_probe_protocol(package, self.f.plan)
        origin = {'schemaVersion':ORIGIN_SCHEMA,'kind':'probe-composition','label':label,'attempts':[]}
        facts = probe_source(origin, files)
        transcript = '擦玻璃。' if label == 'ca-boli-natural-alias' else facts['text']
        response = {'request_id':'synthetic-original-'+label,'usage':{},
            'output':{'choices':[{'finish_reason':'stop','message':{'content':[{'text':transcript}]}}]}}
        request = canonical(json.loads(asr_body(facts['audio']))).encode()
        common = {'requestId':'original-asr-'+label,'requestSha256':sha(request),'audioSha256':sha(facts['audio']),
            'planSha256':facts['originPlanSha256'],'label':label,'provider':'qwen-asr','model':'qwen3-asr-flash',
            'formalUseAllowed':False,'humanListeningVerified':False,'perceptualToneVerified':False,
            'expectedTextSentToProvider':False}
        if 'policyVersion' in facts['receipt']:
            common.update({k:facts['receipt'][k] for k in ('policyVersion','policyCanonicalSha256')})
            common['asrPlanSha256'] = 'a'*64
        score = asr_similarity_bps(facts['text'], transcript)
        receipt = {**common,'schemaVersion':'mira.operator.probe-asr-receipt.v1','status':'succeeded','postAttempts':1,
            'completedAt':'2026-01-01T00:00:02Z','transcript':transcript,'transcriptSha256':sha(transcript.encode()),
            'providerResponseSha256':digest(response),'providerRequestId':response['request_id'],'usage':{},
            'requestBytes':len(request),'text':facts['text'],'textSha256':sha(facts['text'].encode()),
            'ttsReceiptSha256':facts['receiptFileSha256'],'pcmSha256':facts['receipt']['pcmSha256'],
            'comparison':{'method':'original-text-literal-levenshtein','passed':score>=8500,'similarityBps':score,'thresholdBps':8500}}
        if label != 'ca-boli-natural-alias': receipt['ssmlSha256'] = sha(facts['body']['input']['text'].encode())
        origin['attempts'] = [{'kind':'probe','role':'routine','files':{
            'request.json':encoded(request),'provider-response.json':encoded(canonical(response).encode()),
            'receipt.json':encoded(canonical(receipt).encode()),
            'intent.json':encoded(canonical({**common,'schemaVersion':'mira.operator.probe-asr-intent.v1',
                'maxPostAttempts':1,'createdAt':'2026-01-01T00:00:01Z'}).encode())}}]
        return package, files, origin, receipt

    def test_historical_alias_missing_duplicate_ssml_keeps_original_zero_and_portable_chain(self):
        package, files, origin, receipt = self.historical_probe_fixture()
        original = canonical(origin)
        self.assertNotIn('ssmlSha256', receipt); self.assertNotIn('asrPlanSha256', receipt)
        self.assertEqual(verify_origin(origin, probe_files=files)['attempts'][0]['receipt'], receipt)
        self.origins[0] = origin
        self.audit = build_audit(plan=self.f.plan,classroom=self.f.classroom,
            targets=[{'target':t,'originSha256':digest(o)} for t,o in zip(self.targets,self.origins)],
            origins=self.origins,probe_protocol=package)
        self.review = self.make_review(); self.fx.read(self.prepare())
        self.assertEqual(self.audit['segments'][0]['similarityBps'], 0)
        self.assertFalse(self.audit['segments'][0]['comparison']['passed'])
        self.assertEqual(canonical(origin), original)

    def test_alias_present_ssml_must_be_exact_even_if_null(self):
        _, files, origin, receipt = self.historical_probe_fixture()
        expected = sha(probe_source(origin, files)['body']['input']['text'].encode())
        for value in (None, '', '0'*64, expected):
            changed = deepcopy(origin); changed_receipt = {**receipt,'ssmlSha256':value}
            changed['attempts'][0]['files']['receipt.json'] = encoded(canonical(changed_receipt).encode())
            with self.subTest(value=value):
                if value == expected: verify_origin(changed, probe_files=files)
                else:
                    with self.assertRaises(ApiError): verify_origin(changed, probe_files=files)

    def test_all_six_historical_policy_probes_still_require_ssml(self):
        from services.textbook_pronunciation_probe_composite import SLOTS
        for label in SLOTS:
            if label == 'ca-boli-natural-alias': continue
            _, files, origin, receipt = self.historical_probe_fixture(label)
            verify_origin(origin, probe_files=files)
            receipt.pop('ssmlSha256')
            origin['attempts'][0]['files']['receipt.json'] = encoded(canonical(receipt).encode())
            with self.subTest(label=label), self.assertRaises(ApiError): verify_origin(origin, probe_files=files)

    def test_alias_missing_ssml_does_not_relax_tts_body_or_policy_binding(self):
        _, files, origin, receipt = self.historical_probe_fixture()
        for key in ('ttsReceiptSha256','planSha256','pcmSha256','audioSha256'):
            changed=deepcopy(origin); bad={**receipt,key:'0'*64}
            changed['attempts'][0]['files']['receipt.json']=encoded(canonical(bad).encode())
            with self.subTest(key=key), self.assertRaises(ApiError): verify_origin(changed,probe_files=files)
        base='evidence/origins/garden3-alias-preregistration/ca-boli-natural-alias/'
        for key in ('voice','ssml'):
            changed=deepcopy(files); body=json.loads(changed[base+'request.json'])
            if key=='voice':body['input']['voice']='Ethan'
            else:body['input']['text']=body['input']['text'].replace('擦玻璃','擦波璃')
            changed[base+'request.json']=canonical(body).encode()
            with self.subTest(key=key), self.assertRaises(ApiError): verify_origin(origin,probe_files=changed)
        for record in ('receipt.json','intent.json'):
            changed=deepcopy(origin); bad=json.loads(base64.b64decode(changed['attempts'][0]['files'][record]))
            bad['policyCanonicalSha256']='0'*64
            changed['attempts'][0]['files'][record]=encoded(canonical(bad).encode())
            with self.subTest(record=record), self.assertRaises(ApiError): verify_origin(changed,probe_files=files)
