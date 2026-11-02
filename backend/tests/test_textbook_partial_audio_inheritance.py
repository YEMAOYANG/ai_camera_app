import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

from content.textbook_catalog import digest
from content.textbook_partial_audio_inheritance import partial_declaration, validate_partial_release, verify_partial_audio
from content.textbook_preview_audio_contract import (asr_request_id, audit_contract_identity, compare_transcript,
    new_audio_plan, tts_request_id)
from services.textbook_partial_audio_inheritance import load_partial_audio, verify_partial_segment
from content.textbook_release import check_questions


class PartialAudioInheritanceTest(unittest.TestCase):
    def setUp(self):
        binding = {'editionId': 'edition', 'alignmentRevisionId': 'revision', 'manifestSha256': 'a' * 64,
                   'nodeId': 'lesson', 'gradeCode': 'primary_1', 'subject': 'chinese'}
        author = {'stageId': 'stage-original', 'sessionId': 'session-original'}
        candidate = {'sha256': 'b' * 64}
        source_id = 'tbadopt_' + digest({'schemaVersion': 'mira.textbook.operator-adoption-materialization.v1',
            'sourceStageId': author['stageId'], 'candidateSha256': candidate['sha256'], 'teachingRevision': '5'})[:24]
        source = {'id': source_id, 'stage': {'id': source_id}, 'scenes': [{'id': 's1', 'stageId': source_id, 'order': 1, 'actions': [
            {'id': 'a1', 'type': 'speech', 'text': '树叶'}, {'id': 'a2', 'type': 'speech', 'text': '秋天'}]}]}
        self.source_input = {**binding, 'sourceSha256': digest(source), 'authoring': author,
                             'authoringCandidate': candidate, 'teachingRevision': '5'}
        self.source_input['previewKey'] = digest(self.source_input)
        self.source_plan = new_audio_plan(preview_key=self.source_input['previewKey'],
            classroom_sha256=self.source_input['sourceSha256'], core_sha256=digest(source), frozen_input=self.source_input)
        self.source_room = copy.deepcopy(source)
        self.target_room = copy.deepcopy(source)
        self.target_room['id'] = 'target-room'
        self.target_room['stage']['id'] = 'target-room'
        self.target_room['scenes'][0]['stageId'] = 'target-room'
        rebuilt = copy.deepcopy(self.target_room); rebuilt['id'] = rebuilt['stage']['id'] = author['stageId']
        rebuilt['scenes'][0]['stageId'] = author['stageId']
        self.chain = {'schemaVersion': 'mira.textbook.partial-preview-repair-chain.v1',
                      'sourceCoreSha256': digest(source), 'targetSha256': digest(rebuilt),
                      'sessionId': author['sessionId'], 'stageId': author['stageId'],
                      'frozenFileSha256': 'c' * 64, 'patches': [{'eventSeq': 1}]}
        self.target_input = {**binding, 'sourceSha256': digest(self.target_room), 'teachingRevision': '6',
            'authoringCandidate': candidate, 'partialRevisionSource': {'identity': {
                'schemaVersion': 'mira.textbook.partial-preview-identity.v1',
                'parentPreviewKey': self.source_input['previewKey'], 'sourceStageId': author['stageId'],
                'candidateSha256': candidate['sha256'], 'targetStageSha256': digest(rebuilt), 'teachingRevision': '6'},
                'chainSha256': digest(self.chain), 'parentClassroomSha256': digest(source)}}
        self.target_input['previewKey'] = digest(self.target_input)
        self.target_plan = new_audio_plan(preview_key=self.target_input['previewKey'],
            classroom_sha256=self.target_input['sourceSha256'], core_sha256=digest(self.target_room), frozen_input=self.target_input)
        stream = io.BytesIO()
        with wave.open(stream, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(b'\x00\x00' * 240)
        self.wav = stream.getvalue()
        self.sha = hashlib.sha256(self.wav).hexdigest()
        self.request = tts_request_id(self.source_plan, 's1', 'a1', '树叶')
        self.receipt = {'requestId': self.request, 'status': 'succeeded', 'audioSha256': self.sha,
                        'mimeType': 'audio/wav', 'previewAudioIdentity': {'planSha256': digest(self.source_plan), 'attempt': 1}}
        self.checkpoint = {'requestId': self.request, 'status': 'unknown', 'audioSha256': None}
        self.provider = {'requestId': self.request, 'status': 'succeeded', 'audioSha256': self.sha, 'mimeType': 'audio/wav'}

    def run_verification(self):
        return verify_partial_audio(source_input=self.source_input, source_room=self.source_room,
            source_room_sha256=digest(self.source_room), source_plan=self.source_plan,
            database_receipts=[self.receipt], checkpoint_receipts=[self.checkpoint],
            target_input=self.target_input, target_room=self.target_room, target_plan=self.target_plan,
            get_receipt=lambda _: self.provider, get_audio=lambda *_: self.wav)

    def test_original_success_survives_stale_claim_without_claiming_asr(self):
        proof = self.run_verification()
        self.assertEqual(proof['segments'][0]['sourceRequestId'], self.request)
        self.assertEqual(proof['segments'][0]['audioSha256'], self.sha)
        self.assertEqual(proof['asrStatus'], 'not_performed')
        self.assertFalse(proof['publicationAllowed'])

    def test_changed_text_cannot_inherit(self):
        self.target_room['scenes'][0]['actions'][0]['text'] = '新树叶'
        self.target_input['sourceSha256'] = digest(self.target_room)
        self.target_input['previewKey'] = digest({k: v for k, v in self.target_input.items() if k != 'previewKey'})
        self.target_plan = new_audio_plan(preview_key=self.target_input['previewKey'],
            classroom_sha256=self.target_input['sourceSha256'], core_sha256=digest(self.target_room), frozen_input=self.target_input)
        self.assertEqual(self.run_verification()['segments'], [])

    def test_provider_uncertainty_and_wav_tamper_fail_closed(self):
        self.provider['status'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'provider_evidence'):
            self.run_verification()
        self.provider['status'] = 'succeeded'
        self.wav += b'bad'
        with self.assertRaisesRegex(ValueError, 'wav_hash'):
            self.run_verification()

    def test_conflicting_or_failed_checkpoint_is_not_promoted(self):
        self.checkpoint['status'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'checkpoint_conflict'):
            self.run_verification()

    def test_forged_source_or_identity_does_not_inherit(self):
        self.source_room['id'] = 'forged'
        with self.assertRaises(ValueError):
            self.run_verification()

    def test_no_quiz_exception_is_explicit_and_rejects_empty_quiz_shell(self):
        clean = {'scenes': [{'type': 'interactive'}]}
        with self.assertRaises(Exception):
            check_questions(clean)
        self.assertEqual(check_questions(clean, allow_empty=True), [])
        with self.assertRaises(Exception):
            check_questions({'scenes': [{'type': 'quiz', 'content': {'questions': []}}]}, allow_empty=True)

    def test_archive_load_and_segment_bind_keep_source_identity(self):
        declaration = partial_declaration(self.run_verification())
        self.target_input['partialAudioParent'] = declaration
        self.target_input['previewKey'] = digest({k: v for k, v in self.target_input.items() if k != 'previewKey'})
        self.target_plan = new_audio_plan(preview_key=self.target_input['previewKey'],
            classroom_sha256=self.target_input['sourceSha256'], core_sha256=digest(self.target_room), frozen_input=self.target_input)
        proof = self.run_verification()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'target-room'; folder = root / 'textbook-preview-audio'; archive = folder / 'partial-parent'
            (archive / 'audio').mkdir(parents=True)
            docs = {'source-input': self.source_input, 'source-room': self.source_room, 'source-plan': self.source_plan,
                'database-receipts': [self.receipt], 'checkpoint-receipts': [self.checkpoint],
                'target-input': self.target_input, 'target-room': self.target_room,
                'provider-receipts': {self.request: self.provider}, 'proof': proof, 'repair-chain': self.chain}
            for name, doc in docs.items():
                (archive / (name + '.json')).write_text(json.dumps(doc), encoding='utf-8')
            (archive / 'audio' / (self.request + '.wav')).write_bytes(self.wav)
            (root / 'audio').mkdir()
            (root / 'audio' / (self.request + '.wav')).write_bytes(self.wav)
            context = load_partial_audio(folder, self.target_plan, frozen=self.target_input)
            scene = self.target_room['scenes'][0]; action = copy.deepcopy(scene['actions'][0]); teacher = self.target_plan['teacher']
            action.update(audioId=self.request, audioUrl='http://localhost/api/classroom-media/target-room/audio/' + self.request + '.wav',
                audioMetadata={'schemaVersion': 'mira.openmaic.speech-audio.v1', 'providerId': teacher['tts']['providerId'],
                    'modelId': teacher['tts']['modelId'], 'voiceId': teacher['voiceId'], 'fallbackUsed': False})
            identity = verify_partial_segment(context, scene, action, self.receipt, folder)
            self.assertEqual(identity['sourceClassroomId'], self.source_room['id'])
            self.assertEqual(identity['sourceClassroomSha256'], self.source_plan['classroomSha256'])
            (root / 'audio' / (self.request + '.wav')).write_bytes(b'tamper')
            with self.assertRaises(Exception):
                verify_partial_segment(context, scene, action, self.receipt, folder)

    def portable_release_fixture(self):
        self.target_input['partialAudioParent'] = partial_declaration(self.run_verification())
        self.target_input['previewKey'] = digest({k: v for k, v in self.target_input.items() if k != 'previewKey'})
        self.target_plan = new_audio_plan(preview_key=self.target_input['previewKey'],
            classroom_sha256=self.target_input['sourceSha256'], core_sha256=digest(self.target_room), frozen_input=self.target_input)
        proof = self.run_verification()
        evidence = {'sourceInput': self.source_input, 'sourceRoom': self.source_room, 'sourcePlan': self.source_plan,
            'databaseReceipts': [self.receipt], 'checkpointReceipts': [self.checkpoint], 'targetInput': self.target_input,
            'targetRoom': self.target_room, 'providerReceipts': {self.request: self.provider}, 'proof': proof,
            'repairChain': self.chain}
        room = copy.deepcopy(self.target_room); segments = []; media = []
        for action in room['scenes'][0]['actions']:
            old = action['id'] == 'a1'; request = self.request if old else tts_request_id(self.target_plan, 's1', action['id'], action['text'])
            action.update(audioId=request, audioUrl='/audio/' + action['id'])
            media.append({'path': action['audioUrl'], 'sha256': self.sha})
            text = action['text']; transcript_sha = hashlib.sha256(text.encode()).hexdigest()
            comparison = compare_transcript(self.target_plan, text, text)
            entry = {'sceneId': 's1', 'actionId': action['id'], 'ttsRequestId': request, 'audioSha256': self.sha,
                'text': text, 'textSha256': transcript_sha, 'transcript': text, 'comparison': comparison,
                'similarityBps': comparison['similarityBps'],
                'asr': {'requestId': asr_request_id(self.target_plan, request, self.sha), 'status': 'succeeded',
                        'transcript': text, 'transcriptSha256': transcript_sha}}
            if old:
                entry['partialAudioParent'] = {'sourceClassroomId': self.source_room['id'],
                    'sourceClassroomSha256': self.source_plan['classroomSha256'], 'sourceSceneOrder': 1,
                    'sourcePreviewKey': self.source_plan['previewKey'], 'sourceReceiptSha256': digest(self.receipt),
                    'parentDeclarationSha256': digest(self.target_input['partialAudioParent'])}
            segments.append(entry)
        source_sha = 'f' * 64
        audit = {'schemaVersion': 'mira.textbook.audio-audit.v2', 'previewKey': self.target_input['previewKey'],
                 'sourceSha256': source_sha, 'contract': audit_contract_identity(self.target_plan), 'passed': True,
                 'partialAudioParentSha256': digest(self.target_input['partialAudioParent']), 'segments': segments}
        audit['sha256'] = digest(audit)
        frozen = {'previewKey': self.target_input['previewKey'], 'sourceSha256': source_sha, 'audioContract': self.target_plan,
            'partialAudioParent': self.target_input['partialAudioParent'], 'partialAudioEvidenceSha256': digest(evidence),
            'audioAuditSha256': audit['sha256']}
        release = {'classroom': room, 'media': media, 'audioAudit': {'sha256': audit['sha256'],
            'acceptanceMethod': 'partial-parent-literal-asr', 'literalAudit': audit, 'partialAudioEvidence': evidence}}
        return frozen, release

    def test_portable_release_requires_real_source_identity_and_asr(self):
        frozen, release = self.portable_release_fixture()
        self.assertEqual(validate_partial_release(frozen=frozen, release=release)['segmentCount'], 1)
        release['media'][0]['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            validate_partial_release(frozen=frozen, release=release)
        release['media'][0]['sha256'] = self.sha
        release['audioAudit']['partialAudioEvidence']['repairChain']['patches'][0]['eventSeq'] = 2
        frozen['partialAudioEvidenceSha256'] = digest(release['audioAudit']['partialAudioEvidence'])
        with self.assertRaisesRegex(ValueError, 'repair_chain'):
            validate_partial_release(frozen=frozen, release=release)

    def test_partial_source_keeps_literal_failure_with_exact_user_confirmation(self):
        from content.textbook_user_audio_reconciliation import build_confirmation
        from core.security import now_ms
        from core.errors import ApiError
        frozen, release = self.portable_release_fixture()
        raw = release['audioAudit']['literalAudit']
        entry = raw['segments'][0]
        entry['transcript'] = '声音'
        entry['asr'].update(transcript=entry['transcript'],
            transcriptSha256=hashlib.sha256(entry['transcript'].encode()).hexdigest())
        entry['comparison'] = compare_transcript(self.target_plan, entry['text'], entry['transcript'])
        entry['similarityBps'] = entry['comparison']['similarityBps']
        raw['passed'] = False
        raw['sha256'] = digest({k: v for k, v in raw.items() if k != 'sha256'})
        frozen.update(sourceClassroomId=release['classroom']['id'], audioAuditSha256=raw['sha256'])
        confirmation = build_confirmation(plan=self.target_plan, classroom=release['classroom'], audit=raw,
            expected_source_sha256=frozen['sourceSha256'], statement='确认这一段',
            conversation_id='isolated-test', recorded_at=now_ms(),
            presented_segments=[{k: entry[k] for k in ('sceneId', 'actionId', 'textSha256', 'audioSha256')}])
        frozen['audioAcceptance'] = {'method': confirmation['method'], 'literalAuditSha256': raw['sha256'],
                                    'reconciliationSha256': confirmation['sha256']}
        release['audioAudit'].update(sha256=raw['sha256'], acceptanceMethod=confirmation['method'],
                                    literalPassed=False, reconciliation=confirmation)
        self.assertEqual(validate_partial_release(frozen=frozen, release=release)['segmentCount'], 1)
        self.assertFalse(raw['passed'])
        confirmation['presentedSegments'][0]['audioSha256'] = '0' * 64
        confirmation['sha256'] = digest({k: v for k, v in confirmation.items() if k != 'sha256'})
        frozen['audioAcceptance']['reconciliationSha256'] = confirmation['sha256']
        with self.assertRaises(ApiError):
            validate_partial_release(frozen=frozen, release=release)


if __name__ == '__main__':
    unittest.main()
