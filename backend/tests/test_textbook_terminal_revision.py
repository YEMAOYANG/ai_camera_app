"""Intentional terminal revisions preserve parents and retain duplicate fences."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical, digest
from content.textbook_scene_contract import AUTHOR_DISPATCH_SNAPSHOT_SCHEMA, SNAPSHOT_SCHEMA
from integrations.openmaic_workbench_client import WorkbenchError
from services.textbook_terminal_revision import _validated_operator_lineage, inspect_terminal_source
from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring, sha
from tests.test_textbook_workbench_authoring import reviewed_draft


class TerminalRevisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.guard = Mock()
        self.guard.inspect.return_value = {'manifestSha256': 'a' * 64, 'lessonScopeSha256': 'b' * 64,
                                          'existingArtifacts': []}
        self.client = Mock()
        self.client.scene_contract_schema = f'{SNAPSHOT_SCHEMA},{AUTHOR_DISPATCH_SNAPSHOT_SCHEMA}'
        self.client.owner_fingerprint.return_value = 'fixture-owner-fingerprint'
        self.client.sessions.return_value = []
        self.client.stage_events.return_value = []
        self.client.session_materials.return_value = []
        self.factory = Mock(return_value=self.client)
        self.service = TextbookWorkbenchAuthoring(self.guard, self.root / 'output',
            origin='http://127.0.0.1:3100', client_factory=self.factory)
        self.source_draft = reviewed_draft()
        self.source_draft['pagePlan'] = [
            {'page': 1, 'type': 'slide', 'title': '原教学开场', 'move': '先观察场景。'},
            {'page': 2, 'type': 'quiz', 'title': '原问题一', 'move': '按声音选择图。', 'questionIds': ['question-one']},
            {'page': 3, 'type': 'quiz', 'title': '原问题二', 'move': '换场景选择图。', 'questionIds': ['question-two']},
        ]
        self.source_draft['lockedAssessments'] = [
            {'id': 'question-' + name, 'page': page, 'type': 'single', 'points': 10,
             'question': '请找出' + name + '对应的图。', 'analysis': '观察当前图片的对象关系。',
             'choices': [{'value': 'A', 'label': '第一幅', 'asset': 'image-a'},
                         {'value': 'B', 'label': '第二幅', 'asset': 'image-b'}], 'answer': 'B'}
            for name, page in [('one', 2), ('two', 3)]]
        original = self.root / 'original.json'
        original.write_text(json.dumps(self.source_draft, ensure_ascii=False))
        self.prepared = self.service.prepare(original)
        self.source = Path(self.prepared['jobDirectory'])
        self.source_frozen = json.loads((self.source / 'frozen.json').read_text())
        _, identity = self.service._material_payload(self.source, self.source_frozen, self.source_draft)
        self.session = {'id': 'source-session', 'stageId': 'source-stage', 'status': 'cancelled',
                        'skillId': self.source_draft['skillIds'][0],
                        'prompt': self.service._base_dispatch_payload(self.source_frozen, self.source_draft)['prompt']}
        (self.source / 'owner.cookies').write_text('synthetic-cookie-file-not-used-by-mocked-client')
        (self.source / 'dispatch.json').write_text(json.dumps({
            'requestSha256': identity['requestSha256'], 'payloadSha256': identity['payloadSha256'],
            'ownerFingerprint': self.client.owner_fingerprint(), 'action': 'single_post_intent'}))
        (self.source / 'state.json').write_text(json.dumps({'status': 'session_cancelled', 'sessionId': self.session['id']}))
        self.document = {'stage': {'id': 'source-stage'}, 'outline': {'producerRef': 'source-session'},
                         'scenes': [{'id': 'saved-one', 'order': 1, 'type': 'slide', 'title': '原教学开场'}]}
        self.classrooms = self.root / 'classrooms'
        self.stage_folder = self.classrooms / 'source-stage'
        self.media = self.stage_folder / 'media'
        self.media.mkdir(parents=True)
        (self.media / 'generated-one.png').write_bytes(b'original-one-image-bytes')
        (self.media / 'generated-two.png').write_bytes(b'original-two-image-bytes')
        native_contract = (self.source_frozen['authorDispatchContract']
                           if self.source_frozen['schemaVersion'] == 'mira.operator.workbench-authoring.v4'
                           else self.source_frozen['sceneContract'])
        body = {'schemaVersion': 'mira.textbook.authoring-candidate.v1', 'sessionId': 'source-session',
                'stageId': 'source-stage', 'frozenContract': native_contract,
                'status': 'author_candidate', 'verification': 'static_contract_only_not_play_or_semantic_review',
                'assetBindings': [], 'bindingHistory': [], 'scenes': [
                    {'sceneId': scene['id'], 'order': scene['order'], 'canonicalJson': canonical(scene),
                     'sha256': sha(canonical(scene).encode()), 'contractSha256': native_contract['sha256']}
                    for scene in self.document['scenes']]}
        (self.stage_folder / 'textbook-authoring-candidate.json').write_text(json.dumps({**body, 'sha256': digest(body)}))
        self.client.session.return_value = self.session
        self.client.stage.return_value = self.document
        self.target_draft = deepcopy(self.source_draft)
        self.target_draft['request'] += ' 用户有意重做：复用原素材，补足原教学目标。'
        self.target_draft['scopeReview']['authoringRevisionAuthorization'] = {
            'authorizedBy': 'user', 'authorizedAt': '2026-10-26T17:00:00+08:00',
            'userInstruction': '合成测试授权：重新制作这一课，保留原件并复用素材。',
            'reason': '原教学遗漏，需要有意新修订而非重试未知请求。',
            'binding': deepcopy(self.target_draft['binding'])}
        self.target_draft['pagePlan'] = [
            {'page': 1, 'type': 'slide', 'title': '修订开场', 'move': '先理解准确教学目标。'},
            {'page': 2, 'type': 'slide', 'title': '新增教学步骤', 'move': '观察并修改自己的选择。'},
            {**self.source_draft['pagePlan'][1], 'page': 3},
            {'page': 4, 'type': 'slide', 'title': '迁移教学步骤', 'move': '在新场景比较关系。'},
            {**self.source_draft['pagePlan'][2], 'page': 5},
        ]
        self.target_draft['lockedAssessments'][0]['page'] = 3
        self.target_draft['lockedAssessments'][1]['page'] = 5
        self.target_path = self.root / 'revised.json'
        self.write_target()
        self.target = self.service._path(self.target_draft['binding'], '2')
        self.original_bytes = {str(path.relative_to(self.root)): path.read_bytes()
                               for path in self.root.rglob('*') if path.is_file()}

    def write_target(self):
        self.target_path.write_text(json.dumps(self.target_draft, ensure_ascii=False))

    def revise(self, **kwargs):
        values = {'teaching_revision': '2', 'expected_source_draft_sha256': self.prepared['draftSha256'],
                  'reviewer': 'fixture-reviewer', 'basis': '补足已核教学目标，原锁题只移页',
                  'classroom_directory': self.classrooms}
        values.update(kwargs)
        return self.service.revise_terminal(self.source, self.target_path, **values)

    def assert_parent_preserved(self):
        for relative, raw in self.original_bytes.items():
            self.assertEqual((self.root / relative).read_bytes(), raw, relative)

    def test_revision_archives_every_original_byte_and_only_exempts_the_exact_parent(self):
        result = self.revise()
        self.assertEqual(result['status'], 'prepared')
        receipt = json.loads((self.target / 'terminal-predecessor.json').read_text())
        self.assertEqual(receipt['providerCalls'], 0)
        self.assertEqual(receipt['source']['terminalStatus'], 'cancelled')
        self.assertEqual(len(receipt['source']['media']), 2)
        for image in self.media.iterdir():
            self.assertEqual((self.target / 'terminal-predecessor/media' / image.name).read_bytes(), image.read_bytes())
        self.assertEqual(self.service._other_artifacts(self.target), [])
        self.assertFalse((self.target / 'dispatch.json').exists())
        self.assert_parent_preserved()
        self.client.create_session.assert_not_called()
        self.client.upload_material.assert_not_called()

    def test_receipt_proven_prepared_ancestor_is_not_treated_as_an_unrelated_duplicate(self):
        ancestor = self.service._path(self.target_draft['binding'], 'ancestor')
        ancestor.mkdir(parents=True)
        (ancestor / 'frozen.json').write_text('{}')
        lineage = [str(self.source.resolve()), str(ancestor.resolve())]
        with patch('services.textbook_terminal_revision._validated_operator_lineage',
                   return_value=lineage):
            result = self.revise()
            self.assertEqual(result['status'], 'prepared')
            receipt = json.loads((self.target / 'terminal-predecessor.json').read_text())
            self.assertEqual(receipt['sourceOperatorLineageJobs'], lineage)
            self.assertEqual(self.service._other_artifacts(self.target), [])
        self.client.create_session.assert_not_called()

    def test_operator_lineage_requires_one_validated_same_lesson_receipt_at_each_step(self):
        ancestor = self.service._path(self.target_draft['binding'], 'ancestor')
        ancestor.mkdir(parents=True)
        prepared = lambda job, live=False: ({'sourceJob': str(ancestor)}
            if Path(job).resolve() == self.source.resolve() else None)
        with patch.object(self.service, '_prepared_predecessor_receipt', side_effect=prepared), \
             patch.object(self.service, '_terminal_predecessor_receipt', return_value=None), \
             patch.object(self.service, '_widget_successor_receipt', return_value=None):
            self.assertEqual(_validated_operator_lineage(self.service, self.source, live=True),
                             [str(self.source.resolve()), str(ancestor.resolve())])
        with patch.object(self.service, '_prepared_predecessor_receipt',
                          return_value={'sourceJob': str(ancestor)}), \
             patch.object(self.service, '_terminal_predecessor_receipt',
                          return_value={'sourceJob': str(ancestor)}), \
             patch.object(self.service, '_widget_successor_receipt', return_value=None):
            with self.assertRaises(WorkbenchError) as caught:
                _validated_operator_lineage(self.service, self.source, live=True)
        self.assertEqual(caught.exception.code, 'terminal_predecessor_invalid')

    def test_v4_terminal_inspection_accepts_only_the_compact_native_candidate_contract(self):
        summary, _, candidate = inspect_terminal_source(self.service, self.source, self.classrooms)
        ledger = json.loads(candidate.read_text())
        self.assertEqual(ledger['frozenContract'], self.source_frozen['authorDispatchContract'])
        self.assertEqual(summary['candidateFileSha256'], sha(candidate.read_bytes()))

        body = {key: value for key, value in ledger.items() if key != 'sha256'}
        body['frozenContract'] = self.source_frozen['sceneContract']
        candidate.write_text(json.dumps({**body, 'sha256': digest(body)}))
        with self.assertRaises(WorkbenchError) as caught:
            inspect_terminal_source(self.service, self.source, self.classrooms)
        self.assertEqual(caught.exception.code, 'terminal_predecessor_invalid')

    def test_historical_v3_terminal_inspection_still_uses_the_complete_scene_contract(self):
        frozen = json.loads((self.source / 'frozen.json').read_text())
        frozen.pop('authorDispatchContract')
        frozen['schemaVersion'] = 'mira.operator.workbench-authoring.v3'
        (self.source / 'frozen.json').write_text(json.dumps(frozen))
        payload, identity = self.service._material_payload(self.source, frozen, self.source_draft)
        self.session['prompt'] = payload['prompt']
        (self.source / 'dispatch.json').write_text(json.dumps({
            'requestSha256': identity['requestSha256'], 'payloadSha256': identity['payloadSha256'],
            'ownerFingerprint': self.client.owner_fingerprint(), 'action': 'single_post_intent'}))
        candidate = self.stage_folder / 'textbook-authoring-candidate.json'
        ledger = json.loads(candidate.read_text())
        body = {key: value for key, value in ledger.items() if key != 'sha256'}
        body['frozenContract'] = frozen['sceneContract']
        body['scenes'] = [{**record, 'contractSha256': frozen['sceneContract']['sha256']}
                          for record in body['scenes']]
        candidate.write_text(json.dumps({**body, 'sha256': digest(body)}))

        summary, _, _ = inspect_terminal_source(self.service, self.source, self.classrooms)
        self.assertEqual(summary['candidateFileSha256'], sha(candidate.read_bytes()))

    def test_registry_secret_path_prohibition_keeps_owner_strictly_local(self):
        import services.textbook_terminal_revision as module
        original_exists, original_bytes = module.course_exists, module.course_bytes
        def guarded(operation, path):
            if Path(path).suffix == '.cookies':
                raise AssertionError('Registry must never receive authentication paths')
            return operation(path)
        with patch.object(module, 'course_exists', side_effect=lambda path: guarded(original_exists, path)), \
             patch.object(module, 'course_bytes', side_effect=lambda path: guarded(original_bytes, path)):
            self.assertEqual(self.revise()['status'], 'prepared')
        self.assertEqual((self.target / 'owner.cookies').read_bytes(),
                         (self.source / 'owner.cookies').read_bytes())
        receipt = json.loads((self.target / 'terminal-predecessor.json').read_text())
        self.assertFalse(any('cookie' in name for name in receipt['archiveFiles']))
        self.assertFalse(any(path.suffix == '.cookies' for path in (self.target / 'terminal-predecessor').rglob('*')))

    def test_native_material_media_long_safe_basename_is_archived_exactly(self):
        name = 'material-mat_682cd099frzdn0d36cj830m6qg-' + '3796697f' * 8 + '.png'
        raw = b'original-native-material-portrait-bytes'
        self.assertGreater(len(Path(name).stem), 80)
        (self.media / name).write_bytes(raw)
        self.assertEqual(self.revise()['status'], 'prepared')
        self.assertEqual((self.target / 'terminal-predecessor/media' / name).read_bytes(), raw)
        receipt = json.loads((self.target / 'terminal-predecessor.json').read_text())
        entry = next(item for item in receipt['source']['media'] if item['name'] == name)
        self.assertEqual(entry['sha256'], sha(raw))

    def test_media_basename_rejects_paths_controls_secret_extensions_and_excess_length(self):
        for name in ('bad\\path.png', 'bad\nname.png', 'owner.cookies', '.env', 'a' * 201 + '.png'):
            path = self.media / name
            path.write_bytes(b'not-valid-media-name')
            with self.subTest(name=name), self.assertRaises(WorkbenchError):
                self.revise()
            path.unlink()
        link = self.media / 'linked.png'
        link.symlink_to(self.media / 'generated-one.png')
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.client.create_session.assert_not_called()

    def test_preparation_without_explicit_revision_review_keeps_duplicate_fence(self):
        self.assertEqual(self.service.prepare(self.target_path, teaching_revision='2')['status'], 'reuse_review_required')
        self.assertEqual(self.service.run(self.target, start=True)['status'], 'reuse_review_required')
        self.client.create_session.assert_not_called()

    def test_placeholder_meta_uses_unique_saved_stage_from_durable_creation_event(self):
        self.session['stageId'] = 'opening-placeholder'
        self.client.stage_events.return_value = [
            {'type': 'library_changed', 'data': {'change': 'stage_created', 'stageId': 'source-stage'}}]
        def stage(stage_id):
            if stage_id == 'opening-placeholder':
                raise WorkbenchError('workbench_http_error', 'not found', http_status=404)
            self.assertEqual(stage_id, 'source-stage')
            return self.document
        self.client.stage.side_effect = stage
        self.assertEqual(self.revise()['status'], 'prepared')
        receipt = json.loads((self.target / 'terminal-predecessor.json').read_text())
        self.assertEqual(receipt['source']['sessionMetaStageId'], 'opening-placeholder')
        self.assertEqual(receipt['source']['sourceStageId'], 'source-stage')
        self.assertEqual(json.loads((self.target / 'terminal-predecessor/session.json').read_text())['stageId'],
                         'opening-placeholder')
        self.assertEqual(self.session['stageId'], 'opening-placeholder')
        self.assert_parent_preserved()

    def test_multiple_saved_stage_candidates_or_foreign_producer_cannot_be_ignored(self):
        self.client.stage_events.return_value = [
            {'type': 'library_changed', 'data': {'change': 'stage_created', 'stageId': 'second-stage'}}]
        other = deepcopy(self.document)
        other['stage']['id'] = 'second-stage'
        self.client.stage.side_effect = lambda sid: self.document if sid == 'source-stage' else other
        with self.assertRaises(WorkbenchError) as caught:
            self.revise()
        self.assertEqual(caught.exception.code, 'terminal_predecessor_invalid')
        self.assertFalse((self.target / 'terminal-predecessor.json').exists())
        other['outline']['producerRef'] = 'foreign-session'
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.client.create_session.assert_not_called()

    def test_repeated_revision_review_is_idempotent_without_post_or_source_mutation(self):
        self.revise()
        original = (self.target / 'terminal-predecessor.json').read_bytes()
        frozen = (self.target / 'frozen.json').read_bytes()
        self.revise()
        self.assertEqual((self.target / 'terminal-predecessor.json').read_bytes(), original)
        self.assertEqual((self.target / 'frozen.json').read_bytes(), frozen)
        self.assert_parent_preserved()
        self.client.create_session.assert_not_called()

    def test_authorized_new_revision_posts_once_with_new_contract_and_keeps_parent(self):
        self.revise()
        frozen, draft, _ = self.service._load(self.target)
        payload, _ = self.service._material_payload(self.target, frozen, draft)
        new_session = {'id': 'target-session', 'stageId': 'target-stage', 'status': 'queued',
                       'skillId': draft['skillIds'][0], 'prompt': payload['prompt']}
        self.client.create_session.return_value = new_session
        self.client.session.side_effect = lambda sid: self.session if sid == 'source-session' else new_session
        self.client.stage.side_effect = lambda sid: self.document if sid == 'source-stage' else {
            'stage': {'id': 'target-stage'}, 'scenes': []}
        self.assertEqual(self.service.run(self.target, start=True)['sessionId'], 'target-session')
        self.assertEqual(self.service.run(self.target, start=True)['sessionId'], 'target-session')
        self.client.create_session.assert_called_once_with(payload)
        self.assert_parent_preserved()

    def test_wrong_parent_hash_and_changed_locked_content_cannot_authorize_revision(self):
        with self.assertRaises(WorkbenchError):
            self.revise(expected_source_draft_sha256='0' * 64)
        self.assertFalse((self.target / 'terminal-predecessor.json').exists())
        self.target_draft['lockedAssessments'][0]['answer'] = 'A'
        self.write_target()
        # A distinct revision avoids overwriting the already-frozen rejected input.
        with self.assertRaises(WorkbenchError):
            self.revise(teaching_revision='3')
        self.client.create_session.assert_not_called()

    def test_new_revision_needs_scoped_real_user_authorization_record(self):
        self.target_draft['scopeReview'].pop('authoringRevisionAuthorization')
        self.write_target()
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.assertFalse(self.target.exists())
        self.factory.assert_not_called()

    def test_active_parent_or_other_database_work_is_not_exempted(self):
        self.session['status'] = 'running'
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.assertFalse((self.target / 'terminal-predecessor.json').exists())
        self.session['status'] = 'cancelled'
        self.guard.inspect.return_value['existingArtifacts'] = [{'kind': 'build', 'status': 'published'}]
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.client.create_session.assert_not_called()

    def test_a_different_operator_job_keeps_the_duplicate_fence(self):
        other = self.service._path(self.target_draft['binding'], 'unrelated')
        other.mkdir(parents=True)
        (other / 'frozen.json').write_text('{}')
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.assertFalse((self.target / 'terminal-predecessor.json').exists())
        self.client.create_session.assert_not_called()

    def test_parent_reactivation_or_media_change_blocks_first_post(self):
        self.revise()
        self.session['status'] = 'running'
        self.assertEqual(self.service.run(self.target, start=True)['error'], 'terminal_predecessor_invalid')
        self.session['status'] = 'cancelled'
        (self.media / 'generated-one.png').write_bytes(b'changed-source-bytes')
        self.assertEqual(self.service.run(self.target, start=True)['error'], 'terminal_predecessor_invalid')
        self.assertFalse((self.target / 'dispatch.json').exists())
        self.client.create_session.assert_not_called()

    def test_parent_change_blocks_attachment_before_upload(self):
        self.revise()
        self.session['status'] = 'running'
        with self.assertRaises(WorkbenchError):
            self.service.attach_materials(self.target, self.root / 'not-yet-read.json')
        self.client.upload_material.assert_not_called()

    def test_archive_or_original_request_tamper_is_detected_without_redispatch(self):
        self.revise()
        (self.target / 'terminal-predecessor/media/generated-one.png').write_bytes(b'archive-changed')
        with self.assertRaises(WorkbenchError):
            self.service.run(self.target, start=True)
        self.client.create_session.assert_not_called()

