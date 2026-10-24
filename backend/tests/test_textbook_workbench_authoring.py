"""Operator safety checks: isolated files/DB and mocked HTTP; no provider calls."""
from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
from http.cookiejar import Cookie
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request
from PIL import Image

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import digest
from content.textbook_interaction_policy import interaction_policy_prompt
from content.textbook_scene_contract import SNAPSHOT_SCHEMA, render_scene_contract
from integrations.openmaic_workbench_client import OpenMaicWorkbenchClient, WorkbenchError, local_origin, private_write, _NoRedirect
from repositories.textbook_repository import TextbookRepository
from services.textbook_learning_service import TextbookLearningService
from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring, WorkbenchCatalogGuard, amendment_draft, sha
from tests.test_textbook_learning import IsolatedDatabase, sample


def reviewed_draft():
    manifest = sample(reviewed=True)
    unit, lesson = manifest['units'][0], manifest['units'][0]['lessons'][0]
    voice = get_formal_subject_qwen_voice_identity('chinese')
    return {'schemaVersion': 'mira.operator.workbench-request-draft.v1', 'draftOnly': True,
            'binding': {**{k: manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')},
                        'unitId': unit['unitId'], 'unitTitle': unit['title'], 'lessonTitle': lesson['title'], 'nodeId': lesson['nodeId']},
            'skillIds': ['mira-primary-courseware', 'stage-design'],
            'request': '/mira-primary-courseware 加载 stage-design，按冻结教材与教师制作。',
            'teacherContract': {'subject': voice.subject, 'teacherProfileId': voice.teacher_profile_id,
                                'teacherProfileVersion': voice.teacher_profile_version,
                                'teacherProfileHash': voice.teacher_profile_hash, 'teacherName': voice.teacher_name,
                                'voiceId': voice.voice_id, 'languageCode': voice.language_code},
            'qualityRules': ['图片与语音共同支持儿童操作，反馈来自真实教学状态。'],
            'scopeReview': {'objectives': ['观察并辨认教材范围内的学校情境。'], 'excludedTopics': ['未学汉字阅读评分']},
            'pagePlan': [{'page': 1, 'type': 'slide', 'title': '完整保留额外已审核内容',
                          'move': '按图示范学校情境，不将看过图片推断为独立识字。'}],
            'lockedAssessments': []}


class WorkbenchAuthoringTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.draft = reviewed_draft()
        self.draft_path = self.root / 'reviewed.json'
        self.draft_path.write_text(json.dumps(self.draft, ensure_ascii=False, indent=2))
        self.guard = Mock()
        self.guard.inspect.return_value = {'manifestSha256': 'a' * 64, 'lessonScopeSha256': 'b' * 64,
                                          'existingArtifacts': []}
        self.client = Mock()
        self.client.scene_contract_schema = SNAPSHOT_SCHEMA
        self.client.sessions.return_value = []
        self.client.owner_fingerprint.return_value = 'owner-fingerprint-not-cookie'
        self.client.stage_events.return_value = []
        self.factory = Mock(return_value=self.client)
        self.service = TextbookWorkbenchAuthoring(self.guard, self.root / 'output', origin='http://127.0.0.1:3100',
                                                  client_factory=self.factory)
        self.prepared = self.service.prepare(self.draft_path)
        self.job = Path(self.prepared['jobDirectory'])
        if not getattr(self, 'freeze_new_policy', False):
            # These original safety cases also protect already-frozen historical
            # jobs, whose dispatch bytes must never acquire a new policy.
            frozen = json.loads((self.job / 'frozen.json').read_text())
            frozen.pop('interactionPolicy')
            frozen.pop('sceneContract')
            frozen['schemaVersion'] = 'mira.operator.workbench-authoring.v1'
            (self.job / 'frozen.json').write_text(json.dumps(frozen))
            self.prepared = self.service.run(self.job)
        frozen = json.loads((self.job / 'frozen.json').read_text())
        prompt = self.service._base_dispatch_payload(frozen, self.draft)['prompt']
        self.session = {'id': 'session-one', 'status': 'queued', 'prompt': prompt,
                        'skillId': self.draft['skillIds'][0], 'stageId': 'placeholder'}
        self.client.create_session.return_value = self.session
        self.client.session.return_value = self.session
        self.client.stage.return_value = {'stage': {'id': 'placeholder'}, 'scenes': []}

    def test_prepare_preserves_exact_bytes_all_fields_teacher_and_makes_no_http(self):
        self.assertEqual(self.prepared['status'], 'prepared')
        self.assertEqual((self.job / 'draft.json').read_bytes(), self.draft_path.read_bytes())
        self.assertEqual(self.prepared['requestSha256'], sha(self.draft['request'].encode()))
        self.assertEqual(self.prepared['teacherContract'], self.draft['teacherContract'])
        self.factory.assert_not_called()
        self.assertFalse((self.job / 'owner.cookies').exists())
        self.assertEqual(stat.S_IMODE((self.job / 'draft.json').stat().st_mode), 0o600)
        self.assertEqual(self.service.run(self.job)['status'], 'prepared')
        self.factory.assert_not_called()

    def test_changed_draft_and_teacher_cannot_overwrite_prepared_job(self):
        self.draft['request'] += '改变任务'
        self.draft_path.write_text(json.dumps(self.draft))
        with self.assertRaisesRegex(WorkbenchError, '禁止覆盖'):
            self.service.prepare(self.draft_path)
        self.draft['teacherContract']['voiceId'] = 'wrong-subject'
        self.draft_path.write_text(json.dumps(self.draft))
        with self.assertRaises(WorkbenchError) as error:
            self.service.prepare(self.draft_path)
        self.assertEqual(error.exception.code, 'teacher_invalid')

    def test_post_has_durable_intent_and_repeated_start_never_posts_twice(self):
        def post(payload):
            self.assertTrue((self.job / 'dispatch.json').exists())
            self.assertEqual(json.loads((self.job / 'state.json').read_text())['status'], 'dispatch_unknown')
            self.client.sessions.assert_called_once()
            self.assertEqual(payload, {'prompt': self.draft['request'], 'skill': 'mira-primary-courseware'})
            return self.session
        self.client.create_session.side_effect = post
        self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'session_queued')
        self.client.create_session.assert_called_once()

    def test_unknown_post_is_get_only_until_exact_prompt_and_skill_recover(self):
        self.client.create_session.side_effect = WorkbenchError('workbench_unavailable', '连接中断')
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        self.client.sessions.return_value = [{**self.session, 'prompt': '相同标题，不同完整请求'}]
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        self.client.sessions.return_value = [{**self.session, 'skillId': 'different-skill'}]
        self.assertEqual(self.service.run(self.job)['status'], 'dispatch_unknown')
        self.client.sessions.return_value = [self.session]
        self.assertEqual(self.service.run(self.job)['sessionId'], 'session-one')
        self.client.create_session.assert_called_once()

    def test_crash_after_marker_without_state_remains_fenced(self):
        self.client.create_session.side_effect = RuntimeError('simulated process interruption')
        with self.assertRaises(RuntimeError):
            self.service.run(self.job, start=True)
        (self.job / 'state.json').unlink()
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        self.client.create_session.assert_called_once()

    def test_existing_exact_session_is_reused_without_post(self):
        self.client.sessions.return_value = [self.session]
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['sessionId'], 'session-one')
        self.client.create_session.assert_not_called()
        self.assertEqual(json.loads((self.job / 'dispatch.json').read_text())['action'], 'reuse_existing_session')

    def test_ambiguous_sessions_or_missing_original_owner_block_dispatch(self):
        self.client.sessions.return_value = [self.session, {**self.session, 'id': 'session-two'}]
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'session_match_ambiguous')
        self.client.create_session.assert_not_called()
        self.client.sessions.return_value = []
        self.service.run(self.job, start=True)
        self.client.owner_fingerprint.side_effect = WorkbenchError('owner_cookie_missing', '原身份丢失')
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'owner_cookie_missing')
        self.client.create_session.assert_called_once()

    def test_node_artifact_appearing_after_prepare_blocks_new_post(self):
        self.guard.inspect.return_value['existingArtifacts'] = [
            {'kind': 'build', 'status': 'published', 'sameScope': False, 'key': 'legacy'}]
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['status'], 'reuse_review_required')
        self.client.create_session.assert_not_called()
        self.client.sessions.assert_not_called()

    def test_existing_authoring_or_other_teaching_job_fences_generation(self):
        (self.job.parent / 'authoring.json').write_text(json.dumps({'sessionId': 'previous-pro-session'}))
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'reuse_review_required')
        self.client.create_session.assert_not_called()

    def test_successful_session_with_empty_placeholder_is_not_saved_lesson(self):
        self.session['status'] = 'succeeded'
        self.service.run(self.job, start=True)
        result = self.service.run(self.job)
        self.assertEqual(result['status'], 'session_succeeded')
        self.assertEqual(result['savedStages'], [])

    def test_actual_created_stage_is_saved_with_hash_not_placeholder_or_linked_reference(self):
        self.session['status'] = 'succeeded'
        self.client.stage_events.return_value = [
            {'type': 'stage_link', 'data': {'stageId': 'reference-only'}},
            {'type': 'library_changed', 'data': {'change': 'stage_created', 'stageId': 'real-stage'}}]
        document = {'stage': {'id': 'real-stage'}, 'scenes': [{'id': 'scene-1'}], 'outline': {'requirement': 'original'}}
        self.client.stage.return_value = document
        self.service.run(self.job, start=True)
        result = self.service.run(self.job)
        self.assertEqual(result['status'], 'saved_stage_available')
        self.assertEqual(result['savedStages'][0]['sha256'], digest(document))
        self.assertEqual(json.loads(Path(result['savedStages'][0]['path']).read_text()), document)
        self.client.stage.assert_called_once_with('real-stage')

    def test_status_rejects_session_prompt_changes_and_frozen_request_tamper(self):
        self.service.run(self.job, start=True)
        self.client.session.return_value = {**self.session, 'prompt': self.draft['request'] + 'changed'}
        self.assertEqual(self.service.run(self.job)['error'], 'session_identity_mismatch')
        (self.job / 'draft.json').write_text('{}')
        with self.assertRaises(WorkbenchError):
            self.service.run(self.job, start=True)
        self.client.create_session.assert_called_once()

    def test_registry_upgrade_blocks_first_post_but_not_recovery_of_frozen_session(self):
        with patch('services.textbook_workbench_authoring.get_formal_subject_qwen_voice_identity', side_effect=KeyError()):
            self.assertEqual(self.service.run(self.job, start=True)['error'], 'teacher_invalid')
        self.client.create_session.assert_not_called()
        self.service.run(self.job, start=True)
        with patch('services.textbook_workbench_authoring.get_formal_subject_qwen_voice_identity', side_effect=KeyError()):
            self.assertEqual(self.service.run(self.job)['sessionId'], 'session-one')
        self.client.create_session.assert_called_once()

    def test_marker_owner_change_cannot_query_as_new_owner_or_redispatch(self):
        self.service.run(self.job, start=True)
        self.client.owner_fingerprint.return_value = 'different-owner'
        self.assertEqual(self.service.run(self.job, start=True)['error'], 'dispatch_identity_mismatch')
        self.client.session.assert_not_called()
        self.client.create_session.assert_called_once()


class EmptyWidgetSuccessorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.guard = Mock()
        self.guard.inspect.return_value = {'manifestSha256': 'a' * 64, 'lessonScopeSha256': 'b' * 64,
                                          'existingArtifacts': []}
        self.client = Mock()
        self.client.scene_contract_schema = SNAPSHOT_SCHEMA
        self.client.owner_fingerprint.return_value = 'test-owner'
        self.client.sessions.return_value = []
        self.client.stage_events.return_value = []
        self.client.session_materials.return_value = []
        self.client.stage.side_effect = WorkbenchError('workbench_http_error', 'missing', http_status=404)
        self.service = TextbookWorkbenchAuthoring(self.guard, self.root / 'output',
            origin='http://127.0.0.1:3100', client_factory=Mock(return_value=self.client))
        self.draft = reviewed_draft()
        self.draft['pagePlan'][0].update(type='interactive', widgetType='illustration')
        self.draft['request'] += ' ' + json.dumps({'pagePlan': self.draft['pagePlan']}, ensure_ascii=False)
        path = self.root / 'original.json'
        path.write_text(json.dumps(self.draft, ensure_ascii=False))
        with patch('services.textbook_workbench_authoring.validate_native_widget_types'):
            result = self.service.prepare(path)
            self.source = Path(result['jobDirectory'])
            self.source_sha = result['draftSha256']
            frozen = json.loads((self.source / 'frozen.json').read_text())
            self.parent_session = {'id': 'source-session', 'status': 'queued', 'stageId': 'empty-stage',
                'skillId': self.draft['skillIds'][0],
                'prompt': self.service._base_dispatch_payload(frozen, self.draft)['prompt']}
            self.client.create_session.return_value = self.parent_session
            self.service.run(self.source, start=True)
        self.parent_session = {**self.parent_session, 'status': 'succeeded'}
        self.client.session.return_value = self.parent_session
        self.client.create_session.reset_mock()
        self.corrected = deepcopy(self.draft)
        self.corrected['pagePlan'][0]['widgetType'] = 'diagram'
        self.corrected['request'] = self.draft['request'].replace('"widgetType": "illustration"',
                                                                '"widgetType": "diagram"')
        self.corrected_path = self.root / 'corrected.json'
        self.corrected_path.write_text(json.dumps(self.corrected, ensure_ascii=False))
        self.store = self.root / 'classrooms'
        self.store.mkdir()

    def successor(self):
        return self.service.supersede_unsupported_widget(self.source, self.corrected_path,
            teaching_revision='2', expected_source_draft_sha256=self.source_sha,
            reviewer='operator', basis='Correct unsupported renderer only; preserve original.',
            classroom_directory=self.store)

    def test_review_archives_original_and_start_posts_corrected_contract_once(self):
        self.client.session_materials.return_value = [{'kind': 'web', 'materialId': 'web-1'}]
        original = {name: (self.source / name).read_bytes() for name in ('draft.json', 'frozen.json', 'dispatch.json')}
        result = self.successor()
        job = Path(result['jobDirectory'])
        self.assertEqual(result['status'], 'prepared')
        self.client.create_session.assert_not_called()
        for name, raw in original.items():
            self.assertEqual((self.source / name).read_bytes(), raw)
            self.assertEqual((job / 'predecessor' / name).read_bytes(), raw)
        receipt = json.loads((job / 'widget-successor.json').read_text())
        self.assertEqual(receipt['change'], {'page': 1, 'from': 'illustration', 'to': 'diagram'})
        self.assertEqual(json.loads((job / 'predecessor/terminal-empty-source.json').read_text())['materials'],
                         [{'kind': 'web', 'materialId': 'web-1'}])
        def post(payload):
            self.assertIn('"widgetType": "diagram"', payload['prompt'])
            return {'id': 'target-session', 'status': 'queued', 'stageId': 'target-stage',
                    'skillId': self.draft['skillIds'][0], 'prompt': payload['prompt']}
        self.client.create_session.side_effect = post
        started = self.service.run(job, start=True)
        self.assertEqual(started['sessionId'], 'target-session')
        self.client.session.return_value = post(self.client.create_session.call_args.args[0])
        self.service.run(job, start=True)
        self.client.create_session.assert_called_once()

    def test_active_parent_is_rejected_without_target_or_post(self):
        self.client.session.return_value = {**self.parent_session, 'status': 'running'}
        with self.assertRaises(WorkbenchError) as caught:
            self.successor()
        self.assertEqual(caught.exception.code, 'successor_parent_active')
        self.assertFalse((self.source.parent.parent / 'teaching-2').exists())
        self.client.create_session.assert_not_called()

    def test_images_saved_stages_candidate_and_local_media_each_block(self):
        for kind in ('image-material', 'stage-event', 'stage-document', 'candidate', 'export'):
            with self.subTest(kind=kind):
                self.client.session_materials.return_value = []
                self.client.stage_events.return_value = []
                self.client.stage.side_effect = WorkbenchError('workbench_http_error', 'missing', http_status=404)
                artifact = None
                if kind == 'image-material':
                    self.client.session_materials.return_value = [{'kind': 'image'}]
                elif kind == 'stage-event':
                    self.client.stage_events.return_value = [{'type': 'library_changed', 'data': {'stageId': 'saved'}}]
                elif kind == 'stage-document':
                    self.client.stage.side_effect = None
                    self.client.stage.return_value = {'stage': {'id': 'empty-stage'}, 'scenes': []}
                elif kind == 'candidate':
                    artifact = self.store / 'empty-stage/textbook-authoring-candidate.json'
                    artifact.parent.mkdir(exist_ok=True)
                    artifact.write_text('{}')
                else:
                    artifact = self.store / 'empty-stage.json'
                    artifact.write_text('{}')
                with self.assertRaises(WorkbenchError) as caught:
                    self.successor()
                self.assertEqual(caught.exception.code, 'successor_parent_has_artifacts')
                if artifact:
                    artifact.unlink()
                self.client.create_session.assert_not_called()

    def test_request_prose_or_scope_change_cannot_hide_in_enum_correction(self):
        for variant in ('prose', 'title', 'second-token'):
            with self.subTest(variant=variant):
                changed = deepcopy(self.corrected)
                if variant == 'prose':
                    changed['request'] += ' silently expand the task'
                elif variant == 'title':
                    changed['pagePlan'][0]['title'] = 'different lesson'
                else:
                    changed['request'] += ' "widgetType": "diagram"'
                self.corrected_path.write_text(json.dumps(changed, ensure_ascii=False))
                with self.assertRaises(WorkbenchError) as caught:
                    self.successor()
                self.assertEqual(caught.exception.code, 'successor_scope_changed')
        self.client.create_session.assert_not_called()

    def test_other_job_and_published_artifact_are_never_exempted(self):
        other = self.source.parent.parent / 'teaching-other/authoring-job'
        other.mkdir(parents=True)
        (other / 'frozen.json').write_text('{}')
        with self.assertRaises(WorkbenchError) as caught:
            self.successor()
        self.assertEqual(caught.exception.code, 'successor_other_artifacts')
        self.guard.inspect.return_value['existingArtifacts'] = [{'kind': 'build', 'status': 'published'}]
        with self.assertRaises(WorkbenchError) as caught:
            self.successor()
        self.assertEqual(caught.exception.code, 'successor_parent_has_artifacts')
        self.client.create_session.assert_not_called()

    def test_start_rechecks_parent_activity_and_new_assets(self):
        job = Path(self.successor()['jobDirectory'])
        self.client.session.return_value = {**self.parent_session, 'status': 'running'}
        self.assertEqual(self.service.run(job, start=True)['error'], 'successor_parent_active')
        self.client.session.return_value = self.parent_session
        (self.store / 'empty-stage').mkdir()
        (self.store / 'empty-stage/new-image.png').write_bytes(b'new image')
        self.assertEqual(self.service.run(job, start=True)['error'], 'successor_parent_has_artifacts')
        self.client.create_session.assert_not_called()
        self.assertFalse((job / 'dispatch.json').exists())

    def test_parent_and_receipt_tampering_block_recovery(self):
        job = Path(self.successor()['jobDirectory'])
        path = self.source / 'dispatch.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ')
        with self.assertRaises(WorkbenchError) as caught:
            self.service.run(job, start=True)
        self.assertEqual(caught.exception.code, 'successor_integrity_error')
        path.write_bytes(original)
        receipt_path = job / 'widget-successor.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['sourceEvidenceSha256'] = '0' * 64
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaises(WorkbenchError) as caught:
            self.service.run(job)
        self.assertEqual(caught.exception.code, 'successor_integrity_error')
        self.client.create_session.assert_not_called()


class WorkbenchInteractionPolicyTest(unittest.TestCase):
    freeze_new_policy = True
    setUp = WorkbenchAuthoringTest.setUp

    def _widget_draft(self, widget):
        draft = deepcopy(self.draft)
        draft['pagePlan'][0].update(type='interactive', widgetType=widget)
        path = self.root / 'widget-draft.json'
        path.write_text(json.dumps(draft, ensure_ascii=False))
        return draft, path

    def _historical_widget_job(self):
        # Reproduce an actual pre-fix v3 freeze; do not alter its frozen bytes
        # when exercising the new first-dispatch check or GET-only recovery.
        draft, path = self._widget_draft('illustration')
        with patch('services.textbook_workbench_authoring.validate_native_widget_types'):
            result = self.service.prepare(path, teaching_revision='old-widget')
        job = Path(result['jobDirectory'])
        frozen = json.loads((job / 'frozen.json').read_text())
        self.session = {**self.session, 'prompt': self.service._base_dispatch_payload(frozen, draft)['prompt']}
        self.client.create_session.return_value = self.session
        self.client.session.return_value = self.session
        return job

    def test_unsupported_widget_is_rejected_before_freeze_or_any_http(self):
        for widget in ('illustration', 'procedural-skill', '', None, ['diagram']):
            with self.subTest(widget=widget):
                _, path = self._widget_draft(widget)
                with self.assertRaises(WorkbenchError) as caught:
                    self.service.prepare(path, teaching_revision='invalid-widget')
                self.assertEqual(caught.exception.code, 'unsupported_widget_type')
                self.assertFalse((self.job.parent.parent / 'teaching-invalid-widget').exists())
        self.factory.assert_not_called()

    def test_all_five_generate_scene_widget_values_can_freeze(self):
        for widget in ('simulation', 'game', 'visualization3d', 'diagram', 'code'):
            with self.subTest(widget=widget):
                _, path = self._widget_draft(widget)
                result = self.service.prepare(path, teaching_revision='widget-' + widget)
                frozen = json.loads((Path(result['jobDirectory']) / 'frozen.json').read_text())
                self.assertEqual(frozen['sceneContract']['contract']['pagePlan'][0]['widgetType'], widget)
        self.factory.assert_not_called()

    def test_previously_frozen_unsupported_widget_cannot_make_its_first_post(self):
        job = self._historical_widget_job()
        original = (job / 'frozen.json').read_bytes()
        # Ignore only the unrelated sibling-job reuse fence, so this test
        # reaches the first-dispatch capability check.
        with patch.object(self.service, '_other_artifacts', return_value=[]):
            state = json.loads((job / 'state.json').read_text())
            state.update(status='prepared', existingArtifacts=[])
            (job / 'state.json').write_text(json.dumps(state))
            result = self.service.run(job, start=True)
        self.assertEqual(result['error'], 'unsupported_widget_type')
        self.assertFalse((job / 'dispatch.json').exists())
        self.client.create_session.assert_not_called()
        self.assertEqual((job / 'frozen.json').read_bytes(), original)

    def test_already_dispatched_unsupported_widget_keeps_read_only_recovery(self):
        job = self._historical_widget_job()
        original = (job / 'frozen.json').read_bytes()
        with patch.object(self.service, '_other_artifacts', return_value=[]), \
                patch('services.textbook_workbench_authoring.validate_native_widget_types'):
            state = json.loads((job / 'state.json').read_text())
            state.update(status='prepared', existingArtifacts=[])
            (job / 'state.json').write_text(json.dumps(state))
            self.service.run(job, start=True)
        self.assertEqual(self.service.run(job)['sessionId'], self.session['id'])
        self.assertEqual(self.service.run(job, start=True)['sessionId'], self.session['id'])
        self.client.create_session.assert_called_once()
        self.assertEqual((job / 'frozen.json').read_bytes(), original)

    def test_new_job_keeps_reviewed_bytes_and_freezes_a_separate_dispatch_policy(self):
        frozen = json.loads((self.job / 'frozen.json').read_text())
        policy = frozen['interactionPolicy']
        self.assertEqual(frozen['schemaVersion'], 'mira.operator.workbench-authoring.v3')
        self.assertEqual(policy['sha256'], digest(policy['policy']))
        self.assertEqual((self.job / 'draft.json').read_bytes(), self.draft_path.read_bytes())
        self.assertEqual(frozen['requestSha256'], sha(self.draft['request'].encode()))
        self.assertEqual(frozen['payloadSha256'], digest({'prompt': self.draft['request'],
                                                         'skill': self.draft['skillIds'][0]}))
        expected = '【已冻结的逐页生成合同】' + render_scene_contract(frozen['sceneContract']) + interaction_policy_prompt(policy) + self.draft['request']
        self.assertEqual(self.session['prompt'], expected)
        self.assertEqual(expected.strip(), expected)  # Native POST trims the prompt.
        self.assertNotEqual(sha(expected.encode()), frozen['requestSha256'])
        self.assertEqual(self.prepared['interactionPolicy']['sha256'], policy['sha256'])
        self.assertEqual(self.prepared['interactionPolicy']['verification'], 'frozen_prompt_requirement_only')
        self.assertEqual(self.prepared['sceneContract']['sha256'], frozen['sceneContract']['sha256'])
        self.assertEqual(frozen['sceneContract']['contract']['pagePlan'], self.draft['pagePlan'])
        self.factory.assert_not_called()

    def test_effective_prompt_is_dispatched_once_and_marker_uses_effective_hashes(self):
        original = (self.job / 'frozen.json').read_bytes()
        self.client.sessions.return_value = [{**self.session, 'prompt': 'A genuinely different reviewed request'}]
        self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')
        payload = self.client.create_session.call_args.args[0]
        self.assertEqual(payload['prompt'], self.session['prompt'])
        marker = json.loads((self.job / 'dispatch.json').read_text())
        self.assertEqual(marker['requestSha256'], sha(payload['prompt'].encode()))
        self.assertEqual(marker['payloadSha256'], digest(payload))
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'session_queued')
        self.client.create_session.assert_called_once()
        self.assertEqual((self.job / 'frozen.json').read_bytes(), original)

    def test_historical_v2_keeps_exact_policy_prompt_without_new_contract(self):
        frozen = json.loads((self.job / 'frozen.json').read_text())
        frozen.pop('sceneContract')
        frozen['schemaVersion'] = 'mira.operator.workbench-authoring.v2'
        (self.job / 'frozen.json').write_text(json.dumps(frozen))
        original = (self.job / 'frozen.json').read_bytes()
        self.session['prompt'] = interaction_policy_prompt(frozen['interactionPolicy']) + self.draft['request']
        with patch('services.textbook_workbench_authoring.freeze_scene_contract', side_effect=AssertionError('Historical v2 is immutable')):
            self.service.run(self.job, start=True)
            self.service.run(self.job)
        self.assertEqual(self.client.create_session.call_args.args[0]['prompt'], self.session['prompt'])
        self.assertEqual((self.job / 'frozen.json').read_bytes(), original)

    def test_scene_contract_removal_downgrade_and_rehashed_scope_tamper_are_rejected(self):
        original = json.loads((self.job / 'frozen.json').read_text())
        missing = deepcopy(original)
        missing.pop('sceneContract')
        downgrade = {**original, 'schemaVersion': 'mira.operator.workbench-authoring.v2'}
        rehashed = deepcopy(original)
        rehashed['sceneContract']['contract']['binding']['gradeCode'] = 'primary_6'
        rehashed['sceneContract']['sha256'] = digest(rehashed['sceneContract']['contract'])
        for value in (missing, downgrade, rehashed):
            with self.subTest(value=value['schemaVersion']):
                (self.job / 'frozen.json').write_text(json.dumps(value))
                with self.assertRaises(WorkbenchError) as caught:
                    self.service.run(self.job, start=True)
                self.assertEqual(caught.exception.code, 'scene_contract_integrity_error')
        self.factory.assert_not_called()

    def test_new_prepare_rejects_incomplete_plan_without_freezing_or_http(self):
        broken = deepcopy(self.draft)
        broken['pagePlan'][0].pop('move')
        path = self.root / 'incomplete.json'
        path.write_text(json.dumps(broken))
        with self.assertRaises(WorkbenchError) as caught:
            self.service.prepare(path, teaching_revision='2')
        self.assertEqual(caught.exception.code, 'scene_contract_invalid')
        self.assertFalse(self.service._path(self.draft['binding'], '2').exists())
        self.factory.assert_not_called()

    def test_new_prompt_cannot_contain_another_contract_marker(self):
        broken = deepcopy(self.draft)
        broken['request'] += '\nMIRA_TEXTBOOK_SCENE_AUTHORING_CONTRACT:\n{}'
        path = self.root / 'duplicate-marker.json'
        path.write_text(json.dumps(broken))
        with self.assertRaises(WorkbenchError) as caught:
            self.service.prepare(path, teaching_revision='2')
        self.assertEqual(caught.exception.code, 'scene_contract_integrity_error')
        self.factory.assert_not_called()

    def test_old_native_runtime_cannot_receive_a_new_v3_request(self):
        self.client.scene_contract_schema = None
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['error'], 'scene_contract_runtime_unavailable')
        self.assertFalse((self.job / 'dispatch.json').exists())
        self.client.create_session.assert_not_called()
        self.client.scene_contract_schema = SNAPSHOT_SCHEMA
        self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')
        self.client.create_session.assert_called_once()

    def test_recovery_keeps_original_v3_session_when_capability_header_is_temporarily_absent(self):
        self.service.run(self.job, start=True)
        self.client.scene_contract_schema = None
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'session_queued')
        self.client.create_session.assert_called_once()

    def test_exact_legacy_prompt_requires_reuse_review_and_repeated_start_cannot_bypass(self):
        self.client.sessions.return_value = [{**self.session, 'id': 'legacy-session', 'prompt': self.draft['request']}]
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['status'], 'reuse_review_required')
        self.assertEqual(result['error'], 'legacy_session_requires_review')
        self.assertEqual(result['existingArtifacts'][0]['sessionId'], 'legacy-session')
        self.assertNotIn('sessionId', result)
        self.assertFalse((self.job / 'dispatch.json').exists())
        self.client.sessions.return_value = []
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'reuse_review_required')
        self.client.sessions.assert_called_once()
        self.client.create_session.assert_not_called()

    def test_v2_policy_prompt_requires_reuse_review_before_new_v3_dispatch(self):
        frozen = json.loads((self.job / 'frozen.json').read_text())
        v2_prompt = interaction_policy_prompt(frozen['interactionPolicy']) + self.draft['request']
        self.client.sessions.return_value = [{**self.session, 'id': 'legacy-v2-session', 'prompt': v2_prompt}]
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'legacy_session_requires_review')
        self.assertEqual(result['existingArtifacts'][0]['requestSha256'], sha(v2_prompt.encode()))
        self.assertFalse((self.job / 'dispatch.json').exists())
        self.client.sessions.return_value = []
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'reuse_review_required')
        self.client.sessions.assert_called_once()
        self.client.create_session.assert_not_called()

    def test_current_effective_session_is_recovered_when_a_legacy_match_also_exists(self):
        self.client.sessions.return_value = [
            {**self.session, 'id': 'legacy-session', 'prompt': self.draft['request']}, self.session]
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['sessionId'], self.session['id'])
        self.assertEqual(json.loads((self.job / 'dispatch.json').read_text())['action'], 'reuse_existing_session')
        self.client.create_session.assert_not_called()

    def test_policy_snapshot_tamper_is_rejected_before_http(self):
        original = json.loads((self.job / 'frozen.json').read_text())
        cases = []
        changed = deepcopy(original)
        changed['interactionPolicy']['policy']['policyId'] += '-changed'
        cases.append(changed)
        changed = deepcopy(original)
        changed['interactionPolicy']['schemaVersion'] = 'unreviewed'
        cases.append(changed)
        changed = deepcopy(original)
        changed['interactionPolicy'] = None
        cases.append(changed)
        for changed in cases:
            with self.subTest(policy=changed['interactionPolicy']):
                (self.job / 'frozen.json').write_text(json.dumps(changed))
                with self.assertRaises(WorkbenchError) as caught:
                    self.service.run(self.job, start=True)
                self.assertEqual(caught.exception.code, 'interaction_policy_integrity_error')
        self.factory.assert_not_called()

    def test_retry_start_and_status_never_refreeze_a_future_live_policy(self):
        original = (self.job / 'frozen.json').read_bytes()
        with patch('services.textbook_workbench_authoring.freeze_interaction_policy',
                   side_effect=AssertionError('An existing job must not read the new live policy')) as freeze:
            self.assertEqual(self.service.prepare(self.draft_path)['requestSha256'], self.prepared['requestSha256'])
            self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')
            self.assertEqual(self.service.run(self.job)['status'], 'session_queued')
            freeze.assert_not_called()
        self.assertEqual((self.job / 'frozen.json').read_bytes(), original)
        self.assertEqual(self.client.create_session.call_args.args[0]['prompt'], self.session['prompt'])

    def test_policy_presence_is_required_by_v2_and_unknown_schema_is_rejected(self):
        original = json.loads((self.job / 'frozen.json').read_text())
        missing = deepcopy(original)
        missing.pop('interactionPolicy')
        legacy_with_policy = {**original, 'schemaVersion': 'mira.operator.workbench-authoring.v1'}
        unknown = {**original, 'schemaVersion': 'mira.operator.workbench-authoring.v999'}
        for changed, code in ((missing, 'interaction_policy_integrity_error'),
                              (legacy_with_policy, 'interaction_policy_integrity_error'),
                              (unknown, 'frozen_integrity_error')):
            with self.subTest(schema=changed['schemaVersion'], policy='interactionPolicy' in changed):
                (self.job / 'frozen.json').write_text(json.dumps(changed))
                with self.assertRaises(WorkbenchError) as caught:
                    self.service.run(self.job, start=True)
                self.assertEqual(caught.exception.code, code)
        self.factory.assert_not_called()

    def test_unknown_post_recovers_only_the_effective_prompt_without_another_post(self):
        self.client.create_session.side_effect = WorkbenchError('workbench_unavailable', 'lost response')
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        marker = (self.job / 'dispatch.json').read_bytes()
        self.client.sessions.return_value = [{**self.session, 'prompt': self.draft['request']}]
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        self.client.sessions.return_value = [self.session]
        self.assertEqual(self.service.run(self.job)['sessionId'], 'session-one')
        self.assertEqual((self.job / 'dispatch.json').read_bytes(), marker)
        self.client.create_session.assert_called_once()

    def test_amend_preserves_the_original_policy_snapshot_and_raw_audit_contract(self):
        frozen = json.loads((self.job / 'frozen.json').read_text())
        new = deepcopy(self.draft)
        new['request'] += '\n增加可观察的状态结果与重试。'
        new['qualityRules'] = ['每次决策改变教学状态并展示结果。']
        path = self.root / 'revised.json'
        path.write_text(json.dumps(new, ensure_ascii=False))
        with patch('services.textbook_workbench_authoring.freeze_interaction_policy',
                   side_effect=AssertionError('Amend must preserve the original policy')):
            result = self.service.amend(self.job, path, expected_draft_sha256=self.prepared['draftSha256'],
                                        reviewer='AI-rule-review', basis='Only authoring guidance changes')
        revised = json.loads((self.job / 'frozen.json').read_text())
        self.assertEqual(revised['interactionPolicy'], frozen['interactionPolicy'])
        self.assertEqual(result['requestSha256'], sha(new['request'].encode()))
        self.assertEqual((self.job / 'draft.json').read_bytes(), path.read_bytes())
        self.assertNotEqual(revised['sceneContract']['sha256'], frozen['sceneContract']['sha256'])
        self.assertEqual(revised['sceneContract']['contract']['qualityRules'], new['qualityRules'])
        self.session['prompt'] = self.service._base_dispatch_payload(revised, new)['prompt']
        self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')

    def test_composed_utf16_prompt_limit_is_checked_before_prepare_or_http(self):
        new = deepcopy(self.draft)
        head = new['request'] + '\n'
        # Astral characters count as two UTF-16 code units, as on the server.
        new['request'] = head + '\U0001f331' * ((100_000 - len(head.encode('utf-16-le')) // 2) // 2)
        self.assertLessEqual(len(new['request'].encode('utf-16-le')) // 2, 100_000)
        path = self.root / 'oversized.json'
        path.write_text(json.dumps(new, ensure_ascii=False))
        with self.assertRaises(WorkbenchError) as caught:
            self.service.prepare(path, teaching_revision='2')
        self.assertEqual(caught.exception.code, 'dispatch_request_too_long')
        self.assertFalse(self.service._path(new['binding'], '2').exists())
        self.factory.assert_not_called()


class WorkbenchDraftAmendmentTest(unittest.TestCase):
    setUp = WorkbenchAuthoringTest.setUp

    def candidate(self, draft=None):
        draft = deepcopy(draft or self.draft)
        draft['request'] += '\n语音真实完成后再推进；1000×563 验收。'
        draft['qualityRules'] = ['真实语音 playing 后的 ready 才可推进']
        path = self.job / 'amendment-candidate.json'
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + '\n')
        return path, draft

    def amend(self, path, expected=None, **overrides):
        args = {'expected_draft_sha256': expected or self.prepared['draftSha256'],
                'reviewer': 'operator-reviewer', 'basis': '复核响应式和音频时序，原教材范围不变'}
        args.update(overrides)
        return self.service.amend(self.job, path, **args)

    def assert_error(self, code, operation):
        with self.assertRaises(WorkbenchError) as caught:
            operation()
        self.assertEqual(caught.exception.code, code)

    def test_amend_archives_exact_bytes_without_http_and_new_prompt_dispatches_once(self):
        originals = {name: (self.job / name).read_bytes() for name in ('draft.json', 'frozen.json', 'state.json')}
        path, revised = self.candidate()
        result = self.amend(path)
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['draftSha256'], sha(path.read_bytes()))
        self.assertEqual(result['requestSha256'], sha(revised['request'].encode()))
        archive = self.job / 'amendments' / result['amendment']['revisionId']
        for name, raw in originals.items():
            self.assertEqual((archive / ('source-' + name)).read_bytes(), raw)
            self.assertEqual((archive / ('target-' + name)).read_bytes(), (self.job / name).read_bytes())
        before_retry = {p.name: p.read_bytes() for p in archive.iterdir()}
        self.assertEqual(self.amend(path), result)
        self.assertEqual({p.name: p.read_bytes() for p in archive.iterdir()}, before_retry)
        self.factory.assert_not_called()
        self.session['prompt'] = revised['request']
        self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')
        self.service.run(self.job, start=True)
        self.client.create_session.assert_called_once_with({'prompt': revised['request'], 'skill': revised['skillIds'][0]})
        self.assertEqual({p.name: p.read_bytes() for p in archive.iterdir()}, before_retry)

    def test_dispatch_owner_saved_output_and_sibling_artifact_all_reject(self):
        path, _ = self.candidate()
        original = (self.job / 'draft.json').read_bytes()
        for artifact in (self.job / 'dispatch.json', self.job / 'owner.cookies', self.job / 'saved-a.json',
                         self.job.parent / 'authoring.json', self.job.parent / 'classroom.json'):
            with self.subTest(artifact=artifact.name):
                artifact.write_text('{}')
                self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
                self.assertEqual((self.job / 'draft.json').read_bytes(), original)
                artifact.unlink()
        self.factory.assert_not_called()

    def test_unknown_dispatched_and_session_state_reject_even_without_marker(self):
        path, _ = self.candidate()
        original = json.loads((self.job / 'state.json').read_text())
        for change in ({'status': 'dispatch_unknown'}, {'status': 'session_queued'}, {'sessionId': 'known'},
                       {'savedStages': [{'stageId': 'saved'}]}, {'error': 'workbench_unavailable'}):
            with self.subTest(change=change):
                (self.job / 'state.json').write_text(json.dumps({**original, **change}))
                self.assert_error('amendment_not_prepared', lambda: self.amend(path))
        self.factory.assert_not_called()

    def test_stale_hash_and_nonmutable_fields_are_rejected(self):
        path, revised = self.candidate()
        self.assert_error('amendment_source_changed', lambda: self.amend(path, expected='0' * 64))
        for field, value in (('binding', {**revised['binding'], 'nodeId': 'other'}),
                             ('pagePlan', []), ('lockedAssessments', [{'answer': 'changed'}]),
                             ('mediaBudget', 99), ('teachingRevision', '2')):
            with self.subTest(field=field):
                path.write_text(json.dumps({**revised, field: value}))
                self.assert_error('amendment_scope_changed', lambda: self.amend(path))
        path.write_text(json.dumps({**revised, 'teacherContract': {**revised['teacherContract'], 'voiceId': 'changed'}}))
        self.assert_error('teacher_invalid', lambda: self.amend(path))
        path.write_text(json.dumps({**revised, 'skillIds': list(reversed(revised['skillIds']))}))
        self.assert_error('amendment_scope_changed', lambda: self.amend(path))
        self.assertFalse((self.job / 'amendments').exists())
        self.factory.assert_not_called()

    def test_embedded_assessment_json_stays_exact_and_quality_rules_cannot_be_empty(self):
        old = deepcopy(self.draft)
        old['request'] += '\n{"questions": [{"id": "q1", "answer": "A"}]}'
        new = {**old, 'request': old['request'] + '\n补充交互要求。'}
        amendment_draft(old, new)
        self.assert_error('amendment_scope_changed', lambda: amendment_draft(
            old, {**new, 'request': new['request'].replace('"A"', '"B"')}))
        path, revised = self.candidate()
        path.write_text(json.dumps({**revised, 'qualityRules': []}))
        self.assert_error('amendment_scope_changed', lambda: self.amend(path))

    def test_current_catalog_scope_and_existing_builds_are_rechecked(self):
        path, _ = self.candidate()
        original = deepcopy(self.guard.inspect.return_value)
        for key in ('manifestSha256', 'lessonScopeSha256'):
            self.guard.inspect.return_value = {**original, key: 'c' * 64}
            self.assert_error('catalog_changed', lambda: self.amend(path))
        self.guard.inspect.return_value = {**original, 'existingArtifacts': [{'kind': 'preview'}]}
        self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
        self.factory.assert_not_called()

    def test_official_sources_preserved_hashed_and_changes_block_start(self):
        folder = self.job / 'source-evidence'
        folder.mkdir()
        source = folder / 'official-visible-design.txt'
        source.write_text('官方可见正文原文')
        path, _ = self.candidate()
        result = self.amend(path)
        archive = self.job / 'amendments' / result['amendment']['revisionId']
        intent = json.loads((archive / 'intent.json').read_text())
        self.assertEqual(intent['sourceEvidence'], [{'path': 'source-evidence/' + source.name,
                          'sha256': sha(source.read_bytes()), 'bytes': len(source.read_bytes())}])
        source.write_text('changed')
        self.assert_error('amendment_integrity_error', lambda: self.service.run(self.job, start=True))
        self.factory.assert_not_called()

    def test_source_symlink_and_hidden_dispatch_fence_rejected(self):
        folder = self.job / 'source-evidence'
        folder.mkdir()
        path, _ = self.candidate()
        for name in ('dispatch.json', 'owner.cookies', 'saved-stage.json'):
            file = folder / name
            file.write_text('{}')
            self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
            file.unlink()
        link = folder / 'official.txt'
        link.symlink_to(self.draft_path)
        self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
        self.factory.assert_not_called()

    def prepare_with_bound_lesson_sources(self):
        self.service.output_root = (self.root / 'bound-source-output').resolve()
        self.job = self.service._path(self.draft['binding'], '1')
        source = self.job.parent / 'sources/source-review.json'
        source.parent.mkdir(parents=True)
        self.draft = {**self.draft, 'sourceReview': str(source)}
        source.write_text(json.dumps({'schemaVersion': 'mira.operator.lesson-source-review.v1',
                                    'binding': self.draft['binding'], 'scopeStatus': 'synthetic reviewed scope'}))
        self.draft_path.write_text(json.dumps(self.draft, ensure_ascii=False, indent=2))
        original = self.job.parent / 'preauthoring-candidate.json'
        original.write_bytes(self.draft_path.read_bytes())
        self.prepared = self.service.prepare(self.draft_path)
        return source, original

    def test_bound_sibling_sources_and_original_draft_survive_amendment_chain(self):
        source, original = self.prepare_with_bound_lesson_sources()
        originals = {p: p.read_bytes() for p in (source, original)}
        path, revised = self.candidate()
        first = self.amend(path)
        path, revised = self.candidate(revised)
        second = self.amend(path, expected=first['draftSha256'])
        archive = self.job / 'amendments' / second['amendment']['revisionId']
        evidence = json.loads((archive / 'intent.json').read_text())['sourceEvidence']
        self.assertEqual({r['path']: r['sha256'] for r in evidence}, {
            '../sources/source-review.json': sha(originals[source]),
            '../preauthoring-candidate.json': self.prepared['draftSha256']})
        self.assertEqual({p: p.read_bytes() for p in originals}, originals)
        self.factory.assert_not_called()
        frozen = json.loads((self.job / 'frozen.json').read_text())
        self.session['prompt'] = self.service._base_dispatch_payload(frozen, revised)['prompt']
        self.service.run(self.job, start=True)
        self.service.run(self.job, start=True)
        self.client.create_session.assert_called_once()

    def test_bound_sibling_source_changes_fence_start(self):
        source, _ = self.prepare_with_bound_lesson_sources()
        path, _ = self.candidate()
        self.amend(path)
        review = json.loads(source.read_text())
        source.write_text(json.dumps({**review, 'scopeStatus': 'changed after review'}))
        self.assert_error('amendment_integrity_error', lambda: self.service.run(self.job, start=True))
        self.factory.assert_not_called()

    def test_bound_sibling_source_path_binding_and_unknown_leaf_reject(self):
        source, _ = self.prepare_with_bound_lesson_sources()
        path, _ = self.candidate()
        frozen = json.loads((self.job / 'frozen.json').read_text())
        for reference in (str(source.parent / '..' / 'sources' / source.name), str(self.draft_path)):
            with self.subTest(reference=reference):
                self.assert_error('amendment_existing_artifact', lambda: self.service._lesson_source_evidence(
                    self.job, {**self.draft, 'sourceReview': reference}, frozen))
        wrong = json.loads(source.read_text())
        wrong['binding']['nodeId'] = 'unrelated'
        before = source.read_bytes()
        source.write_text(json.dumps(wrong))
        self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
        source.write_bytes(before)
        extra = source.parent / 'owner.json'; extra.write_text('{}')
        self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
        extra.unlink()
        source.unlink(); source.symlink_to(self.draft_path)
        self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
        self.factory.assert_not_called()

    def test_sibling_pre_authoring_name_cannot_disguise_changed_or_new_draft(self):
        _, original = self.prepare_with_bound_lesson_sources()
        path, _ = self.candidate()
        original.write_bytes(path.read_bytes())
        self.assert_error('amendment_existing_artifact', lambda: self.amend(path))
        self.assertEqual(sha((self.job / 'draft.json').read_bytes()), self.prepared['draftSha256'])
        self.assertFalse((self.job / 'amendments').exists())
        self.factory.assert_not_called()

    def test_each_partial_write_fences_start_and_identical_amend_resumes(self):
        current = self.draft
        expected = self.prepared['draftSha256']
        points = ('intent.json', 'source-draft.json', 'target-frozen.json', 'draft.json',
                  'frozen.json', 'state.json', 'receipt.json')
        for point in points:
            with self.subTest(point=point):
                path, current = self.candidate(current)
                def interrupted(destination, raw):
                    if destination.name == point:
                        raise OSError('simulated disk interruption')
                    private_write(destination, raw)
                with patch('services.textbook_workbench_authoring.private_write', side_effect=interrupted):
                    with self.assertRaises(OSError):
                        self.amend(path, expected=expected)
                self.assert_error('amendment_pending', lambda: self.service.run(self.job, start=True))
                self.factory.assert_not_called()
                self.assert_error('amendment_pending', lambda: self.amend(path, expected=expected, basis='different intent'))
                existing = {str(p): p.read_bytes() for p in (self.job / 'amendments').rglob('*') if p.is_file()}
                result = self.amend(path, expected=expected)
                for file, raw in existing.items():
                    self.assertEqual(Path(file).read_bytes(), raw)
                self.assertEqual(result['status'], 'prepared')
                self.assertEqual((self.job / 'draft.json').read_bytes(), path.read_bytes())
                expected = result['draftSha256']

    def test_changed_live_file_during_interruption_refuses_to_overwrite(self):
        path, _ = self.candidate()
        def interrupted(destination, raw):
            if destination == self.job / 'frozen.json':
                raise OSError('stop after draft')
            private_write(destination, raw)
        with patch('services.textbook_workbench_authoring.private_write', side_effect=interrupted):
            with self.assertRaises(OSError):
                self.amend(path)
        (self.job / 'draft.json').write_text('unexpected live change')
        self.assert_error('amendment_conflict', lambda: self.amend(path))
        self.assertEqual((self.job / 'draft.json').read_text(), 'unexpected live change')
        self.factory.assert_not_called()

    def test_archived_bytes_cannot_be_rewritten_by_retry_or_start(self):
        path, _ = self.candidate()
        result = self.amend(path)
        archive = self.job / 'amendments' / result['amendment']['revisionId']
        source = archive / 'source-draft.json'
        source.write_text('tampered archive')
        self.assert_error('amendment_integrity_error', lambda: self.amend(path))
        self.assert_error('amendment_integrity_error', lambda: self.service.run(self.job, start=True))
        self.assertEqual(source.read_text(), 'tampered archive')
        self.factory.assert_not_called()

    def test_amendment_chain_does_not_allow_old_request_to_replace_latest(self):
        path, first = self.candidate()
        first_raw = path.read_bytes()
        result = self.amend(path)
        path, _ = self.candidate(first)
        self.amend(path, expected=result['draftSha256'])
        latest = (self.job / 'draft.json').read_bytes()
        path.write_bytes(first_raw)
        self.assert_error('amendment_conflict', lambda: self.amend(path))
        self.assertEqual((self.job / 'draft.json').read_bytes(), latest)
        self.assertEqual(self.service.run(self.job)['status'], 'prepared')
        self.factory.assert_not_called()


class WorkbenchAuthoringCliTest(unittest.TestCase):
    def test_successor_requires_explicit_review_and_routes_without_start(self):
        from scripts import author_textbook_lesson as cli
        args = ['supersede-widget', '--source-job', '/source', '--draft', '/corrected',
                '--teaching-revision', '2', '--expected-source-draft-sha256', 'a' * 64,
                '--classroom-directory', '/classrooms', '--reviewer', 'reviewer', '--basis', 'enum only']
        with patch.object(cli.AppConfig, 'from_env') as config, redirect_stderr(io.StringIO()):
            for invalid in (args[:-2], args + ['--job-directory', '/target'],
                            ['start', '--job-directory', '/target', '--source-job', '/source']):
                with self.assertRaises(SystemExit):
                    cli.main(invalid)
            config.assert_not_called()
        with patch.object(cli.AppConfig, 'from_env'), patch.object(cli, 'Database'), \
                patch.object(cli, 'TextbookWorkbenchAuthoring') as service, redirect_stdout(io.StringIO()):
            service.return_value.supersede_unsupported_widget.return_value = {'status': 'prepared'}
            self.assertEqual(cli.main(args), 0)
            service.return_value.supersede_unsupported_widget.assert_called_once_with(
                Path('/source'), Path('/corrected'), teaching_revision='2',
                expected_source_draft_sha256='a' * 64, reviewer='reviewer', basis='enum only',
                classroom_directory=Path('/classrooms'))
            service.return_value.run.assert_not_called()
            service.return_value.prepare.assert_not_called()

    def test_amend_requires_review_and_rejects_teaching_revision_before_loading_config(self):
        from scripts import author_textbook_lesson as cli
        with patch.object(cli.AppConfig, 'from_env') as config, redirect_stderr(io.StringIO()):
            for args in (['amend', '--job-directory', '/job', '--draft', '/draft'],
                         ['amend', '--job-directory', '/job', '--draft', '/draft',
                          '--expected-draft-sha256', 'a' * 64, '--reviewer', 'reviewer', '--basis', 'reviewed',
                          '--teaching-revision', '2'],
                         ['start', '--job-directory', '/job', '--reviewer', 'reviewer']):
                with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                    cli.main(args)
                self.assertEqual(caught.exception.code, 2)
            config.assert_not_called()

    def test_amend_routes_to_local_amend_without_start_or_status(self):
        from scripts import author_textbook_lesson as cli
        with patch.object(cli.AppConfig, 'from_env'), patch.object(cli, 'Database'), \
                patch.object(cli, 'TextbookWorkbenchAuthoring') as service, redirect_stdout(io.StringIO()):
            service.return_value.amend.return_value = {'status': 'prepared'}
            result = cli.main(['amend', '--job-directory', '/job', '--draft', '/draft',
                               '--expected-draft-sha256', 'a' * 64, '--reviewer', 'reviewer', '--basis', 'reviewed'])
            self.assertEqual(result, 0)
            service.return_value.amend.assert_called_once_with(
                Path('/job'), Path('/draft'), expected_draft_sha256='a' * 64, reviewer='reviewer', basis='reviewed')
            service.return_value.run.assert_not_called()
            service.return_value.prepare.assert_not_called()

    def test_materials_require_separate_action_and_do_not_start_session(self):
        from scripts import author_textbook_lesson as cli
        with patch.object(cli.AppConfig, 'from_env') as config, redirect_stderr(io.StringIO()):
            for args in (['attach-materials', '--job-directory', '/job'],
                         ['start', '--job-directory', '/job', '--materials-manifest', '/manifest']):
                with self.assertRaises(SystemExit):
                    cli.main(args)
            config.assert_not_called()
        with patch.object(cli.AppConfig, 'from_env'), patch.object(cli, 'Database'), \
                patch.object(cli, 'TextbookWorkbenchAuthoring') as service, redirect_stdout(io.StringIO()):
            service.return_value.attach_materials.return_value = {'status': 'prepared'}
            self.assertEqual(cli.main(['attach-materials', '--job-directory', '/job',
                                      '--materials-manifest', '/manifest']), 0)
            service.return_value.attach_materials.assert_called_once_with(Path('/job'), Path('/manifest'))
            service.return_value.run.assert_not_called()


class WorkbenchMaterialAttachmentsTest(unittest.TestCase):
    def setUp(self):
        WorkbenchAuthoringTest.setUp(self)
        assets = []
        for key, color in [('tone-flat', 'red'), ('tone-rise', 'blue')]:
            image = self.root / (key + '.png')
            Image.new('RGB', (7, 5), color).save(image, format='PNG')
            assets.append({'assetKey': key, 'path': image.name, 'sha256': sha(image.read_bytes()),
                           'width': 7, 'height': 5})
        self.manifest = self.root / 'materials.json'
        self.manifest.write_text(json.dumps({'schemaVersion': 'mira.operator.material-attachments.v1', 'assets': assets}))
        self.folder = self.job / 'material-attachments'
        self.original_frozen = (self.job / 'frozen.json').read_bytes()
        self.client.upload_material.side_effect = self.upload
        self.client.session_materials.side_effect = self.material_list
        self.client.stage_events.side_effect = self.opening_events

    def upload(self, raw, name, request_id, mime_type):
        key = name.rsplit('-', 1)[0]
        self.assertTrue((self.folder / (key + '-intent.json')).exists())
        self.assertFalse((self.job / 'dispatch.json').exists())
        return {'httpStatus': 201, 'requestId': request_id,
                'material': {'materialId': 'mat_' + key, 'mime': mime_type,
                             'bytes': len(raw), 'originalName': name, 'extraction': {'status': 'idle'}}}

    def material_list(self, session_id):
        return [{'materialId': json.loads(p.read_text())['response']['material']['materialId'],
                 'title': json.loads(p.read_text())['response']['material']['originalName'], 'kind': 'source'}
                for p in self.folder.glob('*-receipt.json')]

    def opening_events(self, session_id):
        ready = json.loads((self.folder / 'ready.json').read_text())
        receipts = {json.loads(p.read_text())['response']['material']['materialId']:
                    json.loads(p.read_text())['response']['material'] for p in self.folder.glob('*-receipt.json')}
        materials = [{key: receipts[mid][key] for key in ('materialId', 'originalName', 'mime', 'bytes')}
                     for mid in ready['payload']['materialIds']]
        return [{'type': 'user_message', 'data': {'text': ready['payload']['prompt'], 'materials': materials}}]

    def attach(self):
        return self.service.attach_materials(self.job, self.manifest)

    def add_text(self, raw='{"glyph":"ɑ","path":"M 1 2 L 3 4"}'.encode()):
        source = self.root / 'vectors.txt'
        source.write_bytes(raw)
        data = json.loads(self.manifest.read_text())
        data['assets'].append({'assetKey': 'shared-vectors', 'path': source.name,
                               'mimeType': 'text/plain', 'sha256': sha(raw), 'byteSize': len(raw)})
        self.manifest.write_text(json.dumps(data))
        return raw

    def test_mixed_text_and_images_keep_original_bytes_and_bind_before_first_run(self):
        raw = self.add_text()
        result = self.attach()
        self.assertEqual(result['materialCount'], 3)
        self.assertEqual((self.folder / 'shared-vectors.txt').read_bytes(), raw)
        intent = json.loads((self.folder / 'shared-vectors-intent.json').read_text())
        self.assertEqual(intent['mimeType'], 'text/plain')
        self.assertEqual(intent['sha256'], sha(raw))
        self.assertEqual(intent['bytes'], len(raw))
        self.assertNotIn('width', intent)
        self.assertNotIn('height', intent)
        args = self.client.upload_material.call_args.args
        self.assertEqual(args[0], raw)
        self.assertEqual(args[-1], 'text/plain')
        self.client.create_session.assert_not_called()
        self.service.run(self.job, start=True)
        self.assertEqual(self.client.create_session.call_args.args[0]['materialIds'],
                         ['mat_tone-flat', 'mat_tone-rise', 'mat_shared-vectors'])

    def test_binary_invalid_utf8_empty_or_changed_size_text_rejected_before_http(self):
        original = self.manifest.read_bytes()
        for raw in (b'\xff', b'{"value":"\x00"}', b'   ', b''):
            self.manifest.write_bytes(original)
            self.add_text(raw)
            with self.subTest(raw=raw), self.assertRaises(WorkbenchError):
                self.attach()
        self.manifest.write_bytes(original)
        self.add_text()
        data = json.loads(self.manifest.read_text())
        data['assets'][-1]['byteSize'] += 1
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'material_source_changed')
        self.factory.assert_not_called()

    def test_text_does_not_bypass_image_plan_and_only_supported_mime_types_upload(self):
        self.add_text()
        frozen, draft, _ = self.service._load(self.job)
        draft['assetPlan'] = {'assetKeys': ['tone-flat', 'tone-rise']}
        # Inject only the read contract, not a real job mutation, to check scope behavior.
        with patch.object(self.service, '_load', return_value=(frozen, draft, {'status': 'prepared'})):
            self.assertEqual(self.attach()['materialsStatus'], 'ready')
        data = json.loads(self.manifest.read_text())
        data['assets'][-1]['mimeType'] = 'image/svg+xml'
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'material_manifest_invalid')
        self.assertEqual(self.client.upload_material.call_count, 3)

    def test_all_uploads_frozen_before_one_session_post_and_old_frozen_untouched(self):
        result = self.attach()
        self.assertEqual(result['materialsStatus'], 'ready')
        self.assertEqual((self.job / 'frozen.json').read_bytes(), self.original_frozen)
        self.client.create_session.assert_not_called()
        self.attach()
        self.assertEqual(self.client.upload_material.call_count, 2)
        ready = json.loads((self.folder / 'ready.json').read_text())
        self.service.run(self.job, start=True)
        payload = self.client.create_session.call_args.args[0]
        self.assertEqual(payload['materialIds'], ['mat_tone-flat', 'mat_tone-rise'])
        self.assertEqual(ready['payloadSha256'], digest(payload))
        marker = json.loads((self.job / 'dispatch.json').read_text())
        self.assertEqual(marker['payloadSha256'], digest(payload))
        self.assertEqual(marker['materialsSha256'], digest(ready))
        self.service.run(self.job, start=True)
        self.client.create_session.assert_called_once()

    def test_changed_sha_dimensions_duplicate_keys_and_limit_fail_before_any_http(self):
        original = json.loads(self.manifest.read_text())
        cases = []
        for field, value in [('sha256', '0' * 64), ('width', 8)]:
            changed = deepcopy(original)
            changed['assets'][0][field] = value
            cases.append(changed)
        cases.extend([{**original, 'assets': original['assets'] * 2},
                      {**original, 'assets': original['assets'] * 11}])
        for case in cases:
            self.manifest.write_text(json.dumps(case))
            with self.subTest(case=case), self.assertRaises(WorkbenchError):
                self.attach()
        self.factory.assert_not_called()

    def test_unknown_upload_is_never_reposted_and_incomplete_assets_block_start(self):
        self.client.upload_material.side_effect = WorkbenchError('workbench_unavailable', 'lost response')
        with self.assertRaises(WorkbenchError):
            self.attach()
        self.assertTrue((self.folder / 'tone-flat-intent.json').exists())
        self.assertEqual(self.service.run(self.job)['materialsStatus'], 'upload_unknown')
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'material_upload_unknown')
        with self.assertRaises(WorkbenchError):
            self.service.run(self.job, start=True)
        self.client.upload_material.assert_called_once()
        self.client.create_session.assert_not_called()

    def test_resume_after_local_crash_preserves_successful_receipts_and_only_uploads_rest(self):
        import services.textbook_workbench_authoring as module
        original = module.immutable_write
        def interrupt(path, raw):
            if path.name == 'tone-rise-intent.json':
                raise OSError('local interruption before second upload intent')
            return original(path, raw)
        with patch.object(module, 'immutable_write', side_effect=interrupt), self.assertRaises(OSError):
            self.attach()
        first = (self.folder / 'tone-flat-receipt.json').read_bytes()
        self.attach()
        self.assertEqual(self.client.upload_material.call_count, 2)
        self.assertEqual((self.folder / 'tone-flat-receipt.json').read_bytes(), first)

    def test_snapshot_change_during_batch_is_detected_before_its_upload(self):
        def changed(raw, name, request_id, mime_type):
            response = self.upload(raw, name, request_id, mime_type)
            (self.folder / 'tone-rise.png').write_bytes(b'changed during first upload')
            return response
        self.client.upload_material.side_effect = changed
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'material_source_changed')
        self.client.upload_material.assert_called_once()
        self.assertFalse((self.folder / 'tone-rise-intent.json').exists())
        self.client.create_session.assert_not_called()

    def test_crash_after_upload_before_receipt_remains_unknown(self):
        import services.textbook_workbench_authoring as module
        original = module.immutable_write
        def interrupt(path, raw):
            if path.name == 'tone-flat-receipt.json':
                raise OSError('lost local receipt')
            return original(path, raw)
        with patch.object(module, 'immutable_write', side_effect=interrupt), self.assertRaises(OSError):
            self.attach()
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'material_upload_unknown')
        self.client.upload_material.assert_called_once()

    def test_materials_cannot_change_after_freeze_or_dispatch(self):
        self.attach()
        original = self.manifest.read_bytes()
        changed = json.loads(original)
        changed['assets'].reverse()
        self.manifest.write_text(json.dumps(changed))
        with self.assertRaises(WorkbenchError):
            self.attach()
        self.manifest.write_bytes(original)
        self.service.run(self.job, start=True)
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'materials_not_prepared')
        self.assertEqual(self.client.upload_material.call_count, 2)

    def test_owner_or_snapshot_change_blocks_session_without_post(self):
        self.attach()
        self.client.owner_fingerprint.return_value = 'another-owner'
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'material_owner_changed')
        self.client.owner_fingerprint.return_value = 'owner-fingerprint-not-cookie'
        (self.folder / 'tone-flat.png').write_bytes(b'changed')
        with self.assertRaises(WorkbenchError) as caught:
            self.service.run(self.job, start=True)
        self.assertEqual(caught.exception.code, 'material_source_changed')
        self.client.create_session.assert_not_called()

    def test_unknown_session_recovery_requires_expected_materials(self):
        self.attach()
        self.client.create_session.side_effect = WorkbenchError('workbench_unavailable', 'lost response')
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        self.client.sessions.return_value = [self.session]
        self.client.session_materials.side_effect = None
        self.client.session_materials.return_value = []
        self.assertEqual(self.service.run(self.job)['error'], 'session_materials_mismatch')
        self.client.session_materials.side_effect = self.material_list
        self.assertEqual(self.service.run(self.job)['sessionId'], 'session-one')
        self.client.create_session.assert_called_once()

    def test_same_prompt_without_expected_materials_is_not_reused_or_redispatched(self):
        self.attach()
        self.client.sessions.return_value = [self.session]
        self.client.session_materials.side_effect = None
        self.client.session_materials.return_value = []
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'session_materials_mismatch')
        self.client.create_session.assert_not_called()

    def test_same_prompt_with_extra_opening_source_is_not_reused_or_dispatched(self):
        self.attach()
        self.client.sessions.return_value = [self.session]
        events = self.opening_events('session-one')
        events[0]['data']['materials'].append({'materialId': 'mat_unreviewed', 'originalName': 'extra.png',
                                              'mime': 'image/png', 'bytes': 100})
        self.client.stage_events.side_effect = None
        self.client.stage_events.return_value = events
        records = self.material_list('session-one') + [
            {'materialId': 'mat_unreviewed', 'kind': 'source', 'title': 'extra.png'}]
        self.client.session_materials.side_effect = None
        self.client.session_materials.return_value = records
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'session_materials_mismatch')
        self.assertFalse((self.job / 'dispatch.json').exists())
        self.client.create_session.assert_not_called()

    def test_exact_opening_with_later_derived_extraction_can_be_reused(self):
        self.attach()
        self.client.sessions.return_value = [self.session]
        records = self.material_list('session-one') + [
            {'materialId': 'mat_derived', 'kind': 'extraction', 'title': 'vectors.extracted.md'}]
        self.client.session_materials.side_effect = None
        self.client.session_materials.return_value = records
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'session_queued')
        self.assertEqual(json.loads((self.job / 'dispatch.json').read_text())['action'], 'reuse_existing_session')
        self.client.create_session.assert_not_called()

    def test_unknown_dispatch_with_extra_opening_source_keeps_permanent_fence(self):
        self.attach()
        self.client.create_session.side_effect = WorkbenchError('workbench_unavailable', 'lost response')
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        marker = (self.job / 'dispatch.json').read_bytes()
        self.client.sessions.return_value = [self.session]
        events = self.opening_events('session-one')
        events[0]['data']['materials'].append({'materialId': 'mat_unreviewed', 'originalName': 'extra.png',
                                              'mime': 'image/png', 'bytes': 100})
        self.client.stage_events.side_effect = None
        self.client.stage_events.return_value = events
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['error'], 'session_materials_mismatch')
        self.assertEqual(result['status'], 'dispatch_unknown')
        self.assertEqual((self.job / 'dispatch.json').read_bytes(), marker)
        self.client.stage_events.side_effect = self.opening_events
        self.assertEqual(self.service.run(self.job)['sessionId'], 'session-one')
        self.client.create_session.assert_called_once()

    def test_opening_order_missing_event_and_extra_context_are_not_payload_matches(self):
        self.attach()
        self.client.sessions.return_value = [self.session]
        original = self.opening_events('session-one')
        reversed_materials = deepcopy(original)
        reversed_materials[0]['data']['materials'].reverse()
        wrong_text = deepcopy(original)
        wrong_text[0]['data']['text'] += 'changed'
        extra_context = deepcopy(original)
        extra_context[0]['data']['courseRefs'] = [{'courseId': 'unreviewed'}]
        self.client.stage_events.side_effect = None
        for events in ([], reversed_materials, wrong_text, extra_context):
            self.client.stage_events.return_value = events
            with self.subTest(events=events):
                self.assertEqual(self.service.run(self.job, start=True)['error'], 'session_materials_mismatch')
        self.client.create_session.assert_not_called()

    def test_attachment_directory_blocks_later_amend_without_changing_history(self):
        self.attach()
        candidate = deepcopy(self.draft)
        candidate['request'] += ' 修订'
        path = self.root / 'amend.json'
        path.write_text(json.dumps(candidate, ensure_ascii=False))
        with self.assertRaises(WorkbenchError):
            self.service.amend(self.job, path, expected_draft_sha256=self.prepared['draftSha256'],
                               reviewer='reviewer', basis='reviewed')
        self.assertEqual((self.job / 'frozen.json').read_bytes(), self.original_frozen)


class WorkbenchInteractionPolicyMaterialsTest(unittest.TestCase):
    freeze_new_policy = True
    setUp = WorkbenchMaterialAttachmentsTest.setUp
    upload = WorkbenchMaterialAttachmentsTest.upload
    material_list = WorkbenchMaterialAttachmentsTest.material_list
    opening_events = WorkbenchMaterialAttachmentsTest.opening_events
    attach = WorkbenchMaterialAttachmentsTest.attach
    add_text = WorkbenchMaterialAttachmentsTest.add_text

    def test_policy_and_mixed_materials_share_one_effective_dispatch_identity(self):
        self.add_text()
        self.assertEqual(self.attach()['materialsStatus'], 'ready')
        ready = json.loads((self.folder / 'ready.json').read_text())
        self.assertEqual(ready['payload']['prompt'], self.session['prompt'])
        self.assertEqual(ready['payloadSha256'], digest(ready['payload']))
        self.assertEqual(self.service.run(self.job, start=True)['sessionId'], 'session-one')
        self.client.create_session.assert_called_once_with(ready['payload'])
        marker = json.loads((self.job / 'dispatch.json').read_text())
        self.assertEqual(marker['requestSha256'], sha(self.session['prompt'].encode()))
        self.assertEqual(marker['payloadSha256'], ready['payloadSha256'])
        self.assertEqual(marker['materialsSha256'], digest(ready))
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'session_queued')
        self.client.create_session.assert_called_once()
        self.assertEqual(self.client.upload_material.call_count, 3)
        self.assertEqual((self.job / 'frozen.json').read_bytes(), self.original_frozen)

    def test_unknown_post_requires_policy_prompt_in_durable_material_opening(self):
        self.attach()
        self.client.create_session.side_effect = WorkbenchError('workbench_unavailable', 'lost response')
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'dispatch_unknown')
        marker = (self.job / 'dispatch.json').read_bytes()
        self.client.sessions.return_value = [self.session]
        opening = self.opening_events('session-one')
        opening[0]['data']['text'] = self.draft['request']
        self.client.stage_events.side_effect = None
        self.client.stage_events.return_value = opening
        self.assertEqual(self.service.run(self.job, start=True)['error'], 'session_materials_mismatch')
        self.client.stage_events.side_effect = self.opening_events
        self.assertEqual(self.service.run(self.job)['sessionId'], 'session-one')
        self.assertEqual((self.job / 'dispatch.json').read_bytes(), marker)
        self.client.create_session.assert_called_once()

    def test_material_contract_cannot_drop_policy_even_with_recomputed_payload_hash(self):
        self.attach()
        ready = json.loads((self.folder / 'ready.json').read_text())
        ready['payload']['prompt'] = self.draft['request']
        ready['payloadSha256'] = digest(ready['payload'])
        (self.folder / 'ready.json').write_text(json.dumps(ready))
        with self.assertRaises(WorkbenchError) as caught:
            self.service.run(self.job, start=True)
        self.assertEqual(caught.exception.code, 'material_integrity_error')
        self.client.create_session.assert_not_called()

    def test_existing_effective_session_fences_material_uploads(self):
        self.client.sessions.return_value = [self.session]
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'materials_existing_session')
        self.client.upload_material.assert_not_called()
        self.client.create_session.assert_not_called()

    def test_exact_legacy_session_fences_uploads_and_later_start(self):
        self.client.sessions.return_value = [{**self.session, 'id': 'legacy-session', 'prompt': self.draft['request']}]
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'legacy_session_requires_review')
        self.client.upload_material.assert_not_called()
        self.client.sessions.return_value = []
        result = self.service.run(self.job, start=True)
        self.assertEqual(result['status'], 'reuse_review_required')
        self.assertEqual(result['existingArtifacts'][0]['sessionId'], 'legacy-session')
        self.client.sessions.assert_called_once()
        self.client.create_session.assert_not_called()
        self.assertFalse((self.job / 'dispatch.json').exists())

    def test_exact_v2_policy_session_fences_uploads_before_v3_dispatch(self):
        frozen = json.loads((self.job / 'frozen.json').read_text())
        v2_prompt = interaction_policy_prompt(frozen['interactionPolicy']) + self.draft['request']
        self.client.sessions.return_value = [{**self.session, 'id': 'legacy-v2-session', 'prompt': v2_prompt}]
        with self.assertRaises(WorkbenchError) as caught:
            self.attach()
        self.assertEqual(caught.exception.code, 'legacy_session_requires_review')
        self.client.upload_material.assert_not_called()
        self.client.sessions.return_value = []
        self.assertEqual(self.service.run(self.job, start=True)['status'], 'reuse_review_required')
        self.client.create_session.assert_not_called()


class CatalogGuardTest(unittest.TestCase):
    def setUp(self):
        self.db = IsolatedDatabase(('082_fixed_textbook_learning.sql', '083_textbook_course_previews.sql'))
        self.addCleanup(self.db.raw.close)
        self.repo = TextbookRepository(self.db)
        TextbookLearningService(self.repo).import_manifest(sample(reviewed=True))
        self.binding = reviewed_draft()['binding']

    def test_guard_is_select_only_and_exact_binding_is_required(self):
        trace = []
        self.db.raw.set_trace_callback(trace.append)
        check = WorkbenchCatalogGuard(self.repo).inspect(self.binding)
        self.assertEqual(check['existingArtifacts'], [])
        self.assertTrue(all(sql.startswith(('SELECT ', 'BEGIN', 'COMMIT')) for sql in trace))
        with self.assertRaises(WorkbenchError) as error:
            WorkbenchCatalogGuard(self.repo).inspect({**self.binding, 'lessonTitle': '另一课'})
        self.assertEqual(error.exception.code, 'binding_mismatch')

    def test_legacy_published_build_fences_new_work_even_without_claude_receipt(self):
        b = self.binding
        self.db.execute('INSERT INTO learning_textbook_course_builds '
                        '(content_key,edition_id,revision_id,node_id,part_index,teaching_revision,input_json,status,'
                        'course_id,course_version,course_content_sha256,review_json,created_at,updated_at) '
                        'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        ('old', b['editionId'], b['revisionId'], b['nodeId'], 1, '1', '{}', 'published',
                         'legacy-course', 'v1', 'old-hash', '{}', 1, 1))
        result = WorkbenchCatalogGuard(self.repo).inspect(b)
        self.assertEqual(result['existingArtifacts'][0]['status'], 'published')
        self.assertTrue(result['existingArtifacts'][0]['sameScope'])


class WorkbenchClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'owner.cookies'
        self.client = OpenMaicWorkbenchClient('http://127.0.0.1:3100', self.path)
        self.owner = 'a0b1c2d3-1111-4111-8111-123456789012'

    def cookie(self):
        return Cookie(0, 'anonymous_id', self.owner, None, False, '127.0.0.1', False, False,
                      '/', True, True, None, True, None, None, {}, False)

    def test_registry_mode_keeps_owner_cookie_local_without_consulting_course_storage(self):
        self.client.jar.set_cookie(self.cookie())
        self.client.opener = Mock()
        self.client.opener.open.return_value = io.BytesIO(b'[]')
        with patch.dict('os.environ', {'COURSE_STORAGE_MODE': 'registry'}), \
                patch('services.course_file_store.course_write_bytes',
                      side_effect=AssertionError('owner credentials must never reach course storage')) as remote:
            self.assertEqual(self.client.sessions(), [])
            self.path.chmod(0o666)
            self.client._save_owner()
            remote.assert_not_called()
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        restored = OpenMaicWorkbenchClient(self.client.origin, self.path)
        self.assertEqual(restored.owner_fingerprint(), sha(self.owner.encode()))
        self.assertEqual(list(self.path.parent.glob('.owner-*')), [])
        self.assertEqual(list(self.path.parent.glob('.authoring-*')), [])

    def test_registry_registered_state_still_uses_remote_writer_without_a_local_shadow(self):
        state = self.path.with_name('state.json')
        original = b'{"status":"saved-original"}'
        updated = b'{"status":"running"}'
        state.write_bytes(original)
        with patch.dict('os.environ', {'COURSE_STORAGE_MODE': 'registry'}), \
                patch('services.course_file_store.course_write_bytes', return_value=True) as remote:
            private_write(state, updated)
            remote.assert_called_once_with(state, updated)
        self.assertEqual(state.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob('.authoring-*')), [])

    def test_registry_state_write_error_never_falls_back_to_local(self):
        state = self.path.with_name('state.json')
        original = b'{"status":"saved-original"}'
        state.write_bytes(original)
        with patch.dict('os.environ', {'COURSE_STORAGE_MODE': 'registry'}), \
                patch('services.course_file_store.course_write_bytes',
                      side_effect=RuntimeError('remote state write failed')) as remote:
            with self.assertRaisesRegex(RuntimeError, 'remote state write failed'):
                private_write(state, b'{"status":"replacement"}')
            remote.assert_called_once()
        self.assertEqual(state.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob('.authoring-*')), [])

    def test_private_get_establishes_owner_secure_cookie_survives_loopback_http_and_reload(self):
        def get(request, timeout):
            self.assertEqual(request.get_method(), 'GET')
            self.client.jar.set_cookie(self.cookie())
            return io.BytesIO(b'[]')
        self.client.opener = Mock()
        self.client.opener.open.side_effect = get
        self.assertEqual(self.client.sessions(), [])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        restored = OpenMaicWorkbenchClient(self.client.origin, self.path)
        self.assertEqual(restored.owner_fingerprint(), sha(self.owner.encode()))
        request = Request(self.client.origin + '/api/agent/sessions')
        restored.jar.add_cookie_header(request)
        self.assertEqual(request.get_header('Cookie'), 'anonymous_id=' + self.owner)

    def test_post_requires_persisted_owner_no_remote_origin_no_redirect(self):
        self.client.opener = Mock()
        with self.assertRaises(WorkbenchError):
            self.client.create_session({'prompt': 'never sent'})
        self.client.opener.open.assert_not_called()
        for origin in ('https://example.com:443', 'http://localhost:3100@evil.test:80',
                       'http://127.0.0.1:3100/api', 'http://127.0.0.1:3100?x=1'):
            with self.assertRaises(WorkbenchError):
                local_origin(origin)
        with self.assertRaises(WorkbenchError):
            _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')

    def test_scene_contract_capability_comes_from_latest_session_list_response(self):
        class Response(io.BytesIO):
            headers = {'x-mira-textbook-scene-contract': SNAPSHOT_SCHEMA}
        self.client._open = Mock(side_effect=[Response(b'[]'), io.BytesIO(b'[]')])
        self.assertEqual(self.client.sessions(), [])
        self.assertEqual(self.client.scene_contract_schema, SNAPSHOT_SCHEMA)
        self.assertEqual(self.client.sessions(), [])
        self.assertIsNone(self.client.scene_contract_schema)

    def test_sse_stops_at_caught_up_and_does_not_follow_live_tail(self):
        raw = (b'event: library_changed\ndata: {"type":"library_changed","data":{"change":"stage_created","stageId":"real"}}\n\n'
               b'event: caught_up\ndata: {"type":"caught_up"}\n\n'
               b'event: stage_link\ndata: {"type":"stage_link","data":{"stageId":"late"}}\n\n')
        self.client._open = Mock(return_value=io.BytesIO(raw))
        result = self.client.stage_events('session-one')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['data']['stageId'], 'real')

    def test_sse_keeps_opening_input_in_order_for_exact_material_recovery(self):
        opening = {'type': 'user_message', 'data': {'text': 'reviewed prompt',
                   'materials': [{'materialId': 'mat_first'}, {'materialId': 'mat_second'}]}}
        followup = {'type': 'user_message', 'data': {'text': 'later input'}}
        raw = b''.join(('event: user_message\ndata: ' + json.dumps(e) + '\n\n').encode()
                       for e in (opening, followup)) + b'event: caught_up\ndata: {"type":"caught_up"}\n\n'
        self.client._open = Mock(return_value=io.BytesIO(raw))
        self.assertEqual(self.client.stage_events('session-one'), [opening, followup])

    def test_server_owner_replacement_preserves_original_cookie_file(self):
        self.client.jar.set_cookie(self.cookie())
        self.client._save_owner()
        original = self.path.read_bytes()
        def replaced(request, timeout):
            self.owner = 'b0b1c2d3-1111-4111-8111-123456789012'
            self.client.jar.set_cookie(self.cookie())
            return io.BytesIO(b'[]')
        self.client.opener = Mock()
        self.client.opener.open.side_effect = replaced
        with self.assertRaises(WorkbenchError) as error:
            self.client.sessions()
        self.assertEqual(error.exception.code, 'owner_changed')
        self.assertEqual(self.path.read_bytes(), original)

    def test_png_upload_uses_exact_bytes_persisted_owner_and_echoed_receipt(self):
        self.client.jar.set_cookie(self.cookie())
        self.client._save_owner()
        class Response(io.BytesIO):
            status = 201
            headers = {'x-request-id': 'upload-once'}
        def upload(request, timeout):
            self.assertEqual(request.get_method(), 'POST')
            self.assertEqual(request.full_url, 'http://127.0.0.1:3100/api/materials')
            self.assertEqual(request.data, b'original-png-bytes')
            self.assertEqual(request.get_header('Content-type'), 'image/png')
            self.assertEqual(request.get_header('Content-length'), '18')
            self.assertEqual(request.get_header('X-material-filename'), 'tone.png')
            return Response(b'{"materialId":"mat_one"}')
        self.client.opener = Mock()
        self.client.opener.open.side_effect = upload
        result = self.client.upload_png(b'original-png-bytes', 'tone.png', 'upload-once')
        self.assertEqual(result, {'httpStatus': 201, 'requestId': 'upload-once',
                                  'material': {'materialId': 'mat_one'}})
        self.client.opener.open.assert_called_once()

    def test_material_response_mismatch_never_retries(self):
        self.client.jar.set_cookie(self.cookie())
        self.client._save_owner()
        class Response(io.BytesIO):
            status = 201
            headers = {'x-request-id': 'wrong'}
        self.client.opener = Mock()
        self.client.opener.open.return_value = Response(b'{}')
        with self.assertRaises(WorkbenchError) as caught:
            self.client.upload_png(b'png', 'tone.png', 'expected')
        self.assertEqual(caught.exception.code, 'material_upload_response_unknown')
        self.client.opener.open.assert_called_once()

    def test_plain_text_upload_preserves_utf8_bytes_without_extracting(self):
        self.client.jar.set_cookie(self.cookie())
        self.client._save_owner()
        class Response(io.BytesIO):
            status = 201
            headers = {'x-request-id': 'text-once'}
        raw = '{"glyph":"ɑ","声调":[1,2,3,4]}'.encode()
        def upload(request, timeout):
            self.assertEqual(request.full_url, 'http://127.0.0.1:3100/api/materials')
            self.assertEqual(request.data, raw)
            self.assertEqual(request.get_header('Content-type'), 'text/plain')
            self.assertEqual(request.get_header('Content-length'), str(len(raw)))
            return Response(b'{"materialId":"mat_text"}')
        self.client.opener = Mock()
        self.client.opener.open.side_effect = upload
        self.client.upload_material(raw, 'vectors.txt', 'text-once', 'text/plain')
        self.client.opener.open.assert_called_once()
        with self.assertRaises(WorkbenchError):
            self.client.upload_material(raw, 'vectors.svg', 'text-once', 'image/svg+xml')
        self.client.opener.open.assert_called_once()


if __name__ == '__main__':
    unittest.main()
