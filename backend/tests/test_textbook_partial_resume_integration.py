"""Isolated mock: inherited partial TTS stays bound to its original request."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from content.textbook_partial_audio_inheritance import partial_declaration, validate_partial_release, verify_partial_audio
from content.textbook_preview_audio_contract import new_audio_plan, tts_request_id
from services.textbook_partial_preview_revision import bind_inherited_audio
from services.textbook_preview_audio import core_content, narrate_preview
from tests import test_textbook_preview_audio_v2 as audio_fixtures


class PartialResumeIntegrationTest(unittest.TestCase):
    def test_inherited_paid_clip_is_not_posted_again_and_remaining_are_once(self):
        case = audio_fixtures.PreviewAudioV2Tests(methodName='runTest')
        self.addCleanup(case.doCleanups)
        f = case.unnarrated()
        # Model the real course's 34 successful paid clips in a single slide,
        # leaving seven separate page narrations to generate exactly once.
        f.classroom['scenes'][0]['actions'].extend(
            {'id': 'source-extra-' + str(i), 'type': 'speech', 'text': '旧语音' + str(i)}
            for i in range(1, 34))
        case.persist(f)
        clean = deepcopy(f.classroom)
        frozen = json.loads(f.service.get(f.key)['input_json'])
        binding = {k: frozen[k] for k in ('editionId', 'alignmentRevisionId', 'manifestSha256',
                                          'nodeId', 'gradeCode', 'subject')}
        author, candidate = {'stageId': 'source-stage', 'sessionId': 'source-session'}, {
            'sha256': 'b' * 64, 'interactionPolicyVersion': 1, 'interactionPolicySha256': 'c' * 64}
        source_id = 'tbadopt_' + digest({'schemaVersion': 'mira.textbook.operator-adoption-materialization.v1',
            'sourceStageId': author['stageId'], 'candidateSha256': candidate['sha256'], 'teachingRevision': '5'})[:24]
        source = deepcopy(clean)
        source['id'] = source['stage']['id'] = source_id
        source_input = {**binding, 'sourceSha256': digest(source), 'authoring': author,
                        'authoringCandidate': candidate, 'teachingRevision': '5'}
        source_input['previewKey'] = digest(source_input)
        source_plan = new_audio_plan(preview_key=source_input['previewKey'], classroom_sha256=digest(source),
                                    core_sha256=digest(core_content(source)), frozen_input=source_input)
        scene, action = source['scenes'][0], source['scenes'][0]['actions'][0]
        wav = f.runtime.download_formal_audio_tts.return_value
        import hashlib
        sha = hashlib.sha256(wav).hexdigest()
        receipts = [{'requestId': tts_request_id(source_plan, scene['id'], a['id'], a['text']),
                     'status': 'succeeded', 'audioSha256': sha, 'mimeType': 'audio/wav',
                     'previewAudioIdentity': {'planSha256': digest(source_plan), 'attempt': 1}}
                    for a in scene['actions']]
        requests = {r['requestId'] for r in receipts}
        providers = {r['requestId']: {k: r[k] for k in ('requestId', 'status', 'audioSha256', 'mimeType')}
                     for r in receipts}
        checkpoint = receipts[:-1] + [{'requestId': receipts[-1]['requestId'], 'status': 'unknown', 'audioSha256': None}]
        rebuilt = deepcopy(clean)
        rebuilt['id'] = rebuilt['stage']['id'] = author['stageId']
        for s in rebuilt['scenes']:
            s['stageId'] = author['stageId']
        chain = {'schemaVersion': 'mira.textbook.partial-preview-repair-chain.v1',
                 'sourceCoreSha256': digest(core_content(source)), 'targetSha256': digest(rebuilt),
                 'sessionId': author['sessionId'], 'stageId': author['stageId'],
                 'frozenFileSha256': 'c' * 64, 'patches': [{'eventSeq': 1}]}
        target_input = {**frozen, 'sourceSha256': digest(clean), 'teachingRevision': '6',
                        'authoringCandidate': candidate, 'partialRevisionSource': {
                            'identity': {'schemaVersion': 'mira.textbook.partial-preview-identity.v1',
                                'parentPreviewKey': source_input['previewKey'], 'sourceStageId': author['stageId'],
                                'candidateSha256': candidate['sha256'], 'targetStageSha256': digest(rebuilt),
                                'teachingRevision': '6'},
                            'chainSha256': digest(chain), 'parentClassroomSha256': digest(source)}}
        target_input.pop('previewKey', None)
        target_input['previewKey'] = digest({k: v for k, v in target_input.items() if k != 'requirement'})
        def plan():
            return new_audio_plan(preview_key=target_input['previewKey'], classroom_sha256=digest(clean),
                                  core_sha256=digest(core_content(clean)), frozen_input=target_input)
        def verify(p):
            return verify_partial_audio(source_input=source_input, source_room=source,
                source_room_sha256=digest(source), source_plan=source_plan, database_receipts=receipts,
                checkpoint_receipts=checkpoint, target_input=target_input, target_room=clean,
                target_plan=p, get_receipt=lambda req: providers[req], get_audio=lambda *_: wav)
        target_input['partialAudioParent'] = partial_declaration(verify(plan()))
        target_input['previewKey'] = digest({k: v for k, v in target_input.items()
                                             if k not in ('previewKey', 'requirement')})
        target_plan = plan()
        proof = verify(target_plan)
        prepared = {'targetRoom': clean, 'targetPlan': target_plan, 'databaseReceipts': receipts,
                    'proof': proof, 'wavs': {request: wav for request in requests}}
        bound, inherited = bind_inherited_audio(prepared, f.runtime.base_url)
        archive = f.folder / 'partial-parent'
        (archive / 'audio').mkdir(parents=True)
        docs = {'source-input': source_input, 'source-room': source, 'source-plan': source_plan,
                'database-receipts': receipts, 'checkpoint-receipts': checkpoint,
                'target-input': target_input, 'target-room': clean,
                'provider-receipts': providers, 'proof': proof, 'repair-chain': chain}
        for name, value in docs.items():
            (archive / (name + '.json')).write_text(canonical(value))
        for request in requests:
            (archive / 'audio' / (request + '.wav')).write_bytes(wav)
            (f.root / f.cid / 'audio' / (request + '.wav')).write_bytes(wav)
        old_key, f.key = f.key, target_input['previewKey']
        f.classroom, f.result = bound, {'audioReceipts': inherited, 'audioStopCode': None, 'audioPartial': True}
        f.db.raw.commit()
        f.db.execute('PRAGMA foreign_keys=OFF')
        f.db.execute('UPDATE learning_textbook_course_previews SET preview_key=?,input_json=? WHERE preview_key=?',
                     (f.key, canonical(target_input), old_key))
        case.persist(f)
        (f.folder / 'plan.json').write_text(canonical(target_plan))
        (f.folder / 'checkpoint.json').write_text(canonical(bound))
        f.runtime.start_formal_audio_tts.reset_mock()
        result = narrate_preview(f.service, f.key, f.root)
        posts = f.runtime.start_formal_audio_tts.call_args_list
        self.assertEqual(len(posts), 7)
        self.assertFalse(requests & {p.kwargs['request_id'] for p in posts})
        self.assertEqual(len({p.kwargs['request_id'] for p in posts}), 7)
        self.assertEqual(result['status'], 'preview_ready')
        self.assertEqual(result['result']['audioCompleted'], 41)
        self.assertEqual({a['audioId'] for a in f.classroom['scenes'][0]['actions']}, requests)
        audit = case.audit(f, ('--strict-segment-gate',))
        self.assertTrue(audit['passed'])
        self.assertEqual(len(audit['segments']), 41)
        inherited_asr = [entry for entry in audit['segments'] if entry['ttsRequestId'] in requests]
        self.assertEqual(len(inherited_asr), 34)
        self.assertTrue(all(entry.get('partialAudioParent', {}).get('sourcePreviewKey')
                            == source_input['previewKey'] for entry in inherited_asr))
        calls = f.runtime.start_formal_audio_asr.call_args_list
        self.assertEqual(len(calls), 41)
        for call in calls:
            if call.kwargs['tts_request_id'] in requests:
                self.assertEqual(call.kwargs['classroom_id'], source_id)
                self.assertEqual(call.kwargs['classroom_content_sha256'], source_plan['classroomSha256'])
                self.assertEqual(call.kwargs['scene_order'], scene['order'])
            else:
                self.assertEqual(call.kwargs['classroom_id'], f.cid)

        parent_row = {'input_json': canonical(source_input), 'classroom_json': canonical(source),
            'classroom_sha256': digest(source), 'result_json': canonical({'audioReceipts': receipts})}
        actual_get = f.service.get
        recorded_tts = {**f.provider_receipts, **providers}
        recorded_asr = {entry['asr']['requestId']: entry['asr'] for entry in audit['segments']}
        f.runtime.get_formal_audio_tts.side_effect = lambda request, **_: deepcopy(recorded_tts[request])
        f.runtime.get_formal_audio_asr.side_effect = lambda request, **_: deepcopy(recorded_asr[request])
        with patch.object(f.service, 'get', side_effect=lambda key: parent_row if key == source_input['previewKey'] else actual_get(key)), \
             patch('services.textbook_publication_service.freeze_interaction_policy', return_value={'policy': {'version': 1}}):
            release = case.prepare(f, audit)
        self.assertEqual(release['release']['audioAudit']['acceptanceMethod'], 'partial-parent-literal-asr')
        self.assertEqual(release['release']['audioAudit']['partialAudioEvidence']['proof'], proof)
        self.assertEqual(len(release['release']['audioAudit']['literalAudit']['segments']), 41)
        self.assertEqual(validate_partial_release(frozen=release['frozen'], release=release['release'])['segmentCount'], 34)
        changed = next(iter(recorded_asr))
        recorded_asr[changed] = {**recorded_asr[changed], 'transcriptSha256': '0' * 64}
        with patch.object(f.service, 'get', side_effect=lambda key: parent_row if key == source_input['previewKey'] else actual_get(key)), \
             patch('services.textbook_publication_service.freeze_interaction_policy', return_value={'policy': {'version': 1}}):
            with self.assertRaises(ApiError):
                case.prepare(f, audit)



if __name__ == '__main__':
    unittest.main()
