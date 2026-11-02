"""Offline ancestry and dual-source binding tests; no providers or runtime writes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical, digest
from content.textbook_native_revision_adoption import (verify_native_revision_chain, verify_preview_clone,
                                                         verify_narrated_preview, verify_native_stage_quiescent)
from content.textbook_interactive_narration import bind_interactive_audio
from content.textbook_preview import operator_preview_input
from core.errors import ApiError
from services.textbook_preview_audio import core_content
from tests import test_textbook_authoring_candidate as candidate_fixture
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring


class NativeRevisionAdoptionTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.f = candidate_fixture.CandidateFixture(temp.name)
        self.f.use_v4()
        folder = self.f.archive_complete_scene_revision()
        plan = json.loads((folder / 'intent.json').read_text())
        receipt = json.loads((folder / 'receipt.json').read_text())
        suffix = hashlib.sha256(b'two').hexdigest()
        original = json.loads((folder / f'original-scene-{suffix}.json').read_text())
        self.document = {'stage': deepcopy(self.f.classroom['stage']),
                         'scenes': deepcopy(self.f.classroom['scenes']),
                         'dslVersion': 'test', 'outline': {'producerRef': self.f.session}}
        before = deepcopy(self.document); before['scenes'][1] = original
        self.f.write(self.f.job / ('saved-' + self.f.stage + '.json'), before)
        self.f.write(self.f.job / 'state.json', {'sessionId': self.f.session, 'savedStages': [{
            'stageId': self.f.stage, 'sha256': digest(before),
            'path': str(self.f.job / ('saved-' + self.f.stage + '.json'))}]})
        plan['input']['expectedDocumentSha256'] = digest(before)
        plan['beforeDocumentSha256'] = digest(before); plan['afterDocumentSha256'] = digest(self.document)
        plan['sha256'] = digest({k: v for k, v in plan.items() if k != 'sha256'})
        receipt['revisionId'] = receipt['planSha256'] = plan['sha256']
        receipt['documentSha256'] = plan['afterDocumentSha256']
        receipt['sha256'] = digest({k: v for k, v in receipt.items() if k != 'sha256'})
        (folder / 'original-document.json').write_text(canonical(before) + '\n')
        (folder / 'intent.json').write_text(canonical(plan) + '\n')
        (folder / 'receipt.json').write_text(canonical(receipt) + '\n')
        target = folder.parent / plan['sha256']; folder.rename(target); self.folder = target
        self.follow = self.f.validate()['completeSceneReviewFollowup']

    def check(self):
        return verify_native_revision_chain(self.document, self.f.classroom, self.f.store,
                                            self.f.job, self.follow, '2' * 64)

    def test_full_chain_and_distinct_preview_clone(self):
        proof = self.check(); self.assertEqual(proof['authoringSourceSha256'], digest(self.f.classroom))
        clone = deepcopy(self.f.classroom); clone['id'] = clone['stage']['id'] = 'tbadopt_test'
        for scene in clone['scenes']: scene['stageId'] = clone['id']
        self.assertNotEqual(digest(clone), proof['authoringSourceSha256'])
        verify_preview_clone(clone, self.f.stage, proof['authoringSourceSha256'])
        clone['createdAt'] = '2026-10-28T08:45:44.347Z'
        verify_preview_clone(clone, self.f.stage, proof['authoringSourceSha256'])
        with self.assertRaises(ValueError):
            verify_preview_clone({**clone, 'createdAt': 'not-a-time'}, self.f.stage, proof['authoringSourceSha256'])
        with self.assertRaises(ValueError):
            verify_preview_clone({**clone, 'extra': 'unrecorded'}, self.f.stage, proof['authoringSourceSha256'])
        clone['scenes'][0]['title'] = 'changed'
        with self.assertRaises(ValueError): verify_preview_clone(clone, self.f.stage, proof['authoringSourceSha256'])

    def test_saved_stage_and_original_document_are_mandatory(self):
        path = self.f.job / ('saved-' + self.f.stage + '.json')
        saved = json.loads(path.read_text()); saved['outline']['producerRef'] = 'wrong'; self.f.write(path, saved)
        with self.assertRaises(ValueError): self.check()

    def test_candidate_file_fence_rejects_changes_during_verification(self):
        from services.course_file_store import course_bytes
        target = (self.f.store / self.f.stage / 'textbook-authoring-candidate.json').resolve()
        def changed(path):
            raw = course_bytes(path)
            return raw + b' ' if Path(path).resolve() == target else raw
        with patch('content.textbook_native_revision_adoption.course_bytes', side_effect=changed):
            with self.assertRaises(ValueError): self.check()

    def test_saved_stage_fence_rejects_changes_during_verification(self):
        from services.course_file_store import course_bytes
        target = (self.f.job / ('saved-' + self.f.stage + '.json')).resolve()
        def changed(path):
            raw = course_bytes(path)
            return raw + b' ' if Path(path).resolve() == target else raw
        with patch('content.textbook_native_revision_adoption.course_bytes', side_effect=changed):
            with self.assertRaises(ValueError): self.check()

    def test_original_document_and_owner_tampering_fail(self):
        p = self.folder / 'original-document.json'; value = json.loads(p.read_text()); value['stage']['name'] = 'tampered'; self.f.write(p, value)
        with self.assertRaises(ValueError): self.check()
        with self.assertRaises(ValueError):
            verify_native_revision_chain(self.document, self.f.classroom, self.f.store, self.f.job, self.follow, '1' * 64)

    def test_resealed_historical_contract_tampering_is_rejected(self):
        path = self.folder / 'original-candidate.json'
        candidate = json.loads(path.read_text())
        candidate['frozenContract'] = {'sha256': '1' * 64, 'contract': {'altered': True}}
        candidate['sha256'] = digest({k: v for k, v in candidate.items() if k != 'sha256'})
        raw = (canonical(candidate) + '\n').encode(); path.write_bytes(raw)
        plan = json.loads((self.folder / 'intent.json').read_text())
        plan['beforeCandidateSha256'] = plan['input']['expectedCandidateSha256'] = candidate['sha256']
        plan['beforeCandidateFileSha256'] = plan['input']['expectedCandidateFileSha256'] = hashlib.sha256(raw).hexdigest()
        plan['sha256'] = digest({k: v for k, v in plan.items() if k != 'sha256'})
        receipt = json.loads((self.folder / 'receipt.json').read_text())
        receipt['revisionId'] = receipt['planSha256'] = plan['sha256']
        receipt['sha256'] = digest({k: v for k, v in receipt.items() if k != 'sha256'})
        (self.folder / 'intent.json').write_text(canonical(plan) + '\n')
        (self.folder / 'receipt.json').write_text(canonical(receipt) + '\n')
        target = self.folder.parent / plan['sha256']; self.folder.rename(target); self.folder = target
        self.follow = self.f.validate()['completeSceneReviewFollowup']
        with self.assertRaises(ValueError): self.check()

    def test_unrecorded_scene_and_ledger_image_tampering_fail(self):
        self.document['scenes'][0]['title'] = 'unrecorded'
        with self.assertRaises(ValueError): self.check()
        self.document['scenes'][0]['title'] = self.f.classroom['scenes'][0]['title']
        (self.f.media / 'generated-scene.png').write_bytes(b'tampered')
        with self.assertRaises(Exception): self.check()

    def test_preview_input_seals_both_sources_and_rejects_clone_tampering(self):
        candidate = self.f.validate()
        clone = deepcopy(self.f.classroom); clone['id'] = clone['stage']['id'] = 'tbadopt_test'
        for scene in clone['scenes']:
            scene['stageId'] = clone['id']
        clone['createdAt'] = '2026-10-28T08:45:44.347Z'
        proof = {**self.check(), 'cloneCoreSha256': digest(core_content(clone)),
                 'previewSourceSha256': digest(clone)}
        def freeze(value, evidence):
            return operator_preview_input(self.f.manifest, self.f.node, value, {}, self.f.authoring,
                authoring_candidate=candidate, verified_locked_assessments=self.f.draft['lockedAssessments'],
                native_revision_source=evidence)
        brief = freeze(clone, proof)
        self.assertEqual(brief['sourceSha256'], digest(clone))
        self.assertEqual(brief['authoringSourceSha256'], digest(self.f.classroom))
        self.assertNotEqual(brief['sourceSha256'], brief['authoringSourceSha256'])
        self.assertEqual(brief['nativeRevisionSource'], proof)
        changed = deepcopy(clone); changed['scenes'][0]['title'] = 'changed'
        with self.assertRaises(ApiError): freeze(changed, proof)
        with self.assertRaises(ApiError): freeze(clone, {**proof, 'authoringSourceSha256': '1' * 64})

    def test_native_owner_session_and_dispatch_are_checked_without_post(self):
        prompt = 'frozen opening request'; request_sha = hashlib.sha256(prompt.encode()).hexdigest()
        dispatch_frozen = {'requestSha256': request_sha, 'payloadSha256': '3' * 64,
                           'skillIds': ['mira-test']}
        self.f.write(self.f.job / 'dispatch.json', {'ownerFingerprint': '2' * 64,
            'requestSha256': request_sha, 'payloadSha256': '3' * 64})
        client = Mock(); client.owner_fingerprint.return_value = '2' * 64
        client.session.return_value = {'id': self.f.session, 'prompt': prompt,
                                       'skillId': 'mira-test', 'status': 'succeeded'}
        client.stage.return_value = deepcopy(self.document)
        service = TextbookPreviewService(Mock(), Mock(base_url='http://127.0.0.1:3100'),
                                         authoring_output_root=self.f.output,
                                         workbench_client_factory=lambda *_: client)
        state = json.loads((self.f.job / 'state.json').read_text())
        with patch.object(TextbookWorkbenchAuthoring, '_load', return_value=(self.f.frozen, self.f.draft, state)), \
             patch.object(TextbookWorkbenchAuthoring, '_material_payload', return_value=({}, dispatch_frozen)), \
             patch('content.textbook_native_revision_adoption.verify_native_stage_quiescent') as quiescent, \
             patch.object(TextbookWorkbenchAuthoring, '_verify_session_materials') as materials:
            result = service._native_revision_source(self.f.classroom, self.f.store, self.f.authoring,
                                                     self.f.manifest, self.f.node, self.f.validate())
            self.assertEqual(result, self.check())
            materials.assert_called_once()
            quiescent.assert_called_once_with(self.f.session, self.f.stage, '2' * 64)
            client.create_session.assert_not_called(); client.upload_material.assert_not_called()
            client.session.return_value['lease'] = {'workerId': 'still-active'}
            with self.assertRaises(ApiError):
                service._native_revision_source(self.f.classroom, self.f.store, self.f.authoring,
                                                self.f.manifest, self.f.node, self.f.validate())
            client.session.return_value.pop('lease')
            client.owner_fingerprint.return_value = '1' * 64
            with self.assertRaises(ApiError):
                service._native_revision_source(self.f.classroom, self.f.store, self.f.authoring,
                                                self.f.manifest, self.f.node, self.f.validate())

    def test_narrated_clone_accepts_only_exact_generated_audio_helper(self):
        clone = deepcopy(self.f.classroom); clone['scenes'] = clone['scenes'][:2]
        clone['id'] = clone['stage']['id'] = 'tbadopt_test'
        for scene in clone['scenes']:
            scene['stageId'] = clone['id']
        proof = {'previewSourceSha256': digest(clone), 'cloneCoreSha256': digest(core_content(clone))}
        plan = {'classroomSha256': proof['previewSourceSha256'], 'coreSha256': proof['cloneCoreSha256']}
        narrated = deepcopy(clone)
        scene = narrated['scenes'][1]
        scene['actions'][0].update(audioId='test-audio', audioUrl='/api/classroom-media/tbadopt_test/audio/test.wav')
        with self.assertRaises(ValueError): verify_narrated_preview(narrated, proof, plan)
        scene['content']['html'] = bind_interactive_audio(scene['content']['html'],
            {'try': '/api/classroom-media/tbadopt_test/audio/wrong.wav'}, 'tbadopt_test')
        with self.assertRaises(ValueError): verify_narrated_preview(narrated, proof, plan)
        scene['content']['html'] = bind_interactive_audio(scene['content']['html'],
            {'try': '/api/classroom-media/tbadopt_test/audio/test.wav'}, 'tbadopt_test')
        verify_narrated_preview(narrated, proof, plan)
        narrated['scenes'][0]['title'] = 'tampered'
        with self.assertRaises(ValueError): verify_narrated_preview(narrated, proof, plan)

    def test_native_idle_guard_requires_owned_session_without_any_stage_worker(self):
        owner_id = 'anon:synthetic-owner'; owner_sha = hashlib.sha256(b'synthetic-owner').hexdigest()
        conn = Mock(); connection = Mock(); connection.__enter__ = Mock(return_value=conn); connection.__exit__ = Mock(return_value=False)
        session_row = (owner_id, 'succeeded', None, None); meta_row = (owner_id, None)
        def check(active=None, session=session_row, meta=meta_row):
            conn.execute.side_effect = [Mock(), Mock(fetchone=Mock(return_value=session)),
                                        Mock(fetchone=Mock(return_value=meta)), Mock(fetchone=Mock(return_value=active))]
            verify_native_stage_quiescent('session', 'stage', owner_sha)
        with patch.dict('os.environ', {'MIRA_OPENMAIC_AGENT_DATABASE_URL': 'postgresql://localhost/test'}), \
             patch('psycopg.connect', return_value=connection):
            check()
            self.assertEqual(conn.execute.call_args_list[0].args[0], 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            with self.assertRaises(ValueError): check(active=('other-session',))
            with self.assertRaises(ValueError): check(session=(owner_id, 'succeeded', None, 'worker'))
            with self.assertRaises(ValueError): check(meta=('anon:other', None))
        with patch.dict('os.environ', {'MIRA_OPENMAIC_AGENT_DATABASE_URL': ''}):
            with self.assertRaises(ValueError): verify_native_stage_quiescent('session', 'stage', owner_sha)


class NativeRevisionPreviewIntegrationTest(unittest.TestCase):
    def setUp(self):
        harness = candidate_fixture.CandidateAdoptionTest(methodName='runTest')
        harness.setUp(); self.addCleanup(harness.doCleanups)
        self.h, self.f = harness, harness.f
        self.f.draft['lockedAssessments'] = []
        third = deepcopy(self.f.classroom['scenes'][1])
        third.update(id='three', order=3, title='Try again')
        third['actions'][0]['id'] = 'three-speech'
        self.f.classroom['scenes'] = self.f.classroom['scenes'][:2] + [third]
        self.f.draft['pagePlan'] = self.f.draft['pagePlan'][:2] + [{
            'page': 3, 'type': 'interactive', 'title': 'Try again', 'move': 'Revise.'}]
        self.f.use_v4()
        self.f.archive_complete_scene_revision()
        candidate = self.f.validate()
        followup = candidate['completeSceneReviewFollowup']
        self.proof = {'schemaVersion': 'mira.textbook.native-preview-source.v1',
                      'sessionId': self.f.session, 'stageId': self.f.stage,
                      'authoringSourceSha256': digest(self.f.classroom),
                      'followupSha256': followup['sha256'], 'ownerFingerprint': '2' * 64,
                      'nativeDocumentSha256': '3' * 64, 'savedStageFileSha256': '4' * 64,
                      'revisionIds': followup['revisionIds'],
                      'revisionReceiptSha256s': followup['revisionReceiptSha256s'],
                      'candidateSha256': followup['candidateSha256'],
                      'candidateFileSha256': followup['candidateFileSha256']}

    def test_adopt_keeps_source_and_clone_separate_without_provider_dispatch(self):
        original = deepcopy(self.f.classroom)
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof):
            result = self.h.adopt()
        self.assertEqual(result['status'], 'review_required')
        row = self.h.db.execute('SELECT input_json,classroom_json FROM learning_textbook_course_previews WHERE preview_key=?',
                                (result['previewKey'],)).fetchone()
        frozen = json.loads(row['input_json']); clone = json.loads(row['classroom_json'])
        self.assertEqual(frozen['authoringSourceSha256'], digest(original))
        self.assertEqual(frozen['sourceSha256'], digest(clone))
        self.assertNotEqual(frozen['sourceSha256'], frozen['authoringSourceSha256'])
        self.assertEqual(frozen['authoringCandidate']['completeSceneReviewFollowup']['candidateSourceSha256'], digest(original))
        self.assertEqual(frozen['nativeRevisionSource']['cloneCoreSha256'], digest(core_content(clone)))
        self.assertEqual(self.f.classroom, original)
        self.h.runtime.start_generation.assert_not_called()
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof):
            again = self.h.adopt()
        self.assertEqual(again['previewKey'], result['previewKey'])
        self.h.runtime.save_preview_classroom.assert_called_once()

    def test_invalid_native_proof_cannot_create_preview(self):
        with patch.object(TextbookPreviewService, '_native_revision_source',
                          side_effect=ApiError('textbook_preview_candidate_invalid', 'tampered', 409)):
            with self.assertRaises(ApiError): self.h.adopt()
        self.h.assert_no_writes()

    def test_video_waiver_cannot_adopt_from_disk_without_operator_selection(self):
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof), \
             patch('content.textbook_official_followup.requires_official_followup', return_value=True):
            with self.assertRaises(ApiError) as caught:
                self.h.adopt()
        self.assertEqual(caught.exception.code, 'textbook_preview_official_followup_required')
        self.h.assert_no_writes()

    def test_invalid_selected_waiver_stops_before_clone_or_reservation(self):
        selection = {'path': '/nonexistent', 'expectedSha256': '0' * 64,
                     'operatorAttestation': {'reviewer': 'test'}}
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof), \
             patch('content.textbook_official_followup.requires_official_followup', return_value=True), \
             patch('content.textbook_official_followup.validate_followup', side_effect=ValueError('changed')):
            with self.assertRaises(ApiError) as caught:
                self.h.service.adopt(self.f.manifest['editionId'], self.f.manifest['revisionId'], self.f.node,
                                     self.f.stage, self.f.store, self.f.authoring,
                                     official_followup_selection=selection)
        self.assertEqual(caught.exception.code, 'textbook_preview_official_followup_invalid')
        self.h.assert_no_writes()

    def test_same_candidate_reuses_narrated_preview_without_overwrite(self):
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof):
            result = self.h.adopt()
        preview_key, cid = result['previewKey'], result['classroomId']
        narrated = deepcopy(self.h.public_classrooms[cid])
        page = narrated['scenes'][1]
        page['actions'][0].update(audioId='one', audioUrl=f'/api/classroom-media/{cid}/audio/one.wav')
        page['content']['html'] = bind_interactive_audio(page['content']['html'],
            {'try': f'/api/classroom-media/{cid}/audio/one.wav'}, cid)
        self.h.public_classrooms[cid] = deepcopy(narrated)
        self.h.db.execute('UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=? WHERE preview_key=?',
                          (canonical(narrated), digest(narrated), preview_key))
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof):
            reused = self.h.adopt()
        self.assertEqual(reused['previewKey'], preview_key)
        self.assertEqual(self.h.public_classrooms[cid], narrated)
        self.h.runtime.save_preview_classroom.assert_called_once()
        self.h.runtime.start_generation.assert_not_called()

    def test_existing_matching_publication_keeps_published_reuse_result(self):
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof):
            result = self.h.adopt()
        published = {'publication': {'input_json': canonical({'previewKey': result['previewKey']})}}
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof), \
             patch.object(self.h.service.reuse, 'resolve', return_value=published), \
             patch.object(self.h.service, '_resolved_summary', return_value={'status': 'published', 'courseId': 'existing'}):
            reused = self.h.adopt()
        self.assertEqual(reused, {'status': 'published', 'courseId': 'existing'})
        self.h.runtime.save_preview_classroom.assert_called_once()

    def test_native_changes_during_clone_do_not_reserve_a_preview(self):
        original_save = self.h.runtime.save_preview_classroom.side_effect
        def save_then_change(clone):
            original_save(clone)
            changed = deepcopy(self.f.classroom)
            changed['scenes'][0]['title'] = 'concurrent edit'
            self.h.workbench.stage.side_effect = lambda _: {
                'stage': changed['stage'], 'scenes': changed['scenes'],
                'outline': {'producerRef': self.f.session}, 'dslVersion': 'synthetic-test'}
        self.h.runtime.save_preview_classroom.side_effect = save_then_change
        with patch.object(TextbookPreviewService, '_native_revision_source', return_value=self.proof):
            with self.assertRaises(ApiError): self.h.adopt()
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_course_previews').fetchone()['n'], 0)
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) AS n FROM learning_course_reuse_slots').fetchone()['n'], 0)
        self.h.runtime.start_generation.assert_not_called()
