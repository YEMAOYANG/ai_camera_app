"""Prepared-predecessor evidence correction: local files and mocked workbench only."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import digest
from content.textbook_scene_contract import AUTHOR_DISPATCH_SNAPSHOT_SCHEMA, SNAPSHOT_SCHEMA
from integrations.openmaic_workbench_client import WorkbenchError
from services.textbook_workbench_authoring import TextbookWorkbenchAuthoring, sha
from tests.test_textbook_workbench_authoring import reviewed_draft


class PreparedRevisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.guard = Mock()
        self.guard.inspect.return_value = {
            'manifestSha256': 'a' * 64,
            'lessonScopeSha256': 'b' * 64,
            'existingArtifacts': [],
        }
        self.client = Mock()
        self.client.scene_contract_schema = f'{SNAPSHOT_SCHEMA},{AUTHOR_DISPATCH_SNAPSHOT_SCHEMA}'
        self.client.owner_fingerprint.return_value = 'prepared-owner-fingerprint'
        self.client.sessions.return_value = []
        self.client.stage_events.return_value = []
        self.factory = Mock(return_value=self.client)
        self.service = TextbookWorkbenchAuthoring(
            self.guard, self.root / 'output', origin='http://127.0.0.1:3100', client_factory=self.factory)

        self.source_draft = reviewed_draft()
        self.source_draft['binding']['teachingRevision'] = '1'
        self.source_path = self.root / 'source.json'
        self.source_path.write_text(json.dumps(self.source_draft, ensure_ascii=False))
        self.prepared = self.service.prepare(self.source_path, teaching_revision='1')
        self.source = Path(self.prepared['jobDirectory'])

        self.source_asset = self.root / 'source-evidence.txt'
        self.source_asset.write_text('reviewed source evidence\n', encoding='utf-8')
        self.source_manifest = self.root / 'source-materials.json'
        self.source_manifest.write_text(json.dumps({
            'schemaVersion': 'mira.operator.material-attachments.v1',
            'assets': [{
                'assetKey': 'source-evidence',
                'path': self.source_asset.name,
                'sha256': sha(self.source_asset.read_bytes()),
                'mimeType': 'text/plain',
                'byteSize': len(self.source_asset.read_bytes()),
            }],
        }))

        def uploaded(raw, original_name, request_id, mime):
            return {
                'httpStatus': 201,
                'requestId': request_id,
                'material': {
                    'materialId': 'material-' + request_id[-12:],
                    'mime': mime,
                    'bytes': len(raw),
                    'originalName': original_name,
                },
            }

        self.client.upload_material.side_effect = uploaded
        self.service.attach_materials(self.source, self.source_manifest)
        (self.source / 'owner.cookies').write_text('private synthetic owner; never archived')
        self.service.hold(self.source, reviewer='fixture-independent-reviewer',
                          basis='video evidence was captions and sampled frames, not a continuous review')

        self.target_draft = deepcopy(self.source_draft)
        self.target_draft['binding']['teachingRevision'] = '2'
        evidence = ('teaching-1从未派发；teaching-2已在官方播放器以1x无拖动连续观看并听完。')
        self.target_draft['request'] = evidence + self.source_draft['request']
        self.target_draft['qualityRules'] = [
            'teaching-2只修正teaching-1的视频审阅证据；不得据此删除父稿或改变课程。',
            *self.source_draft['qualityRules'],
        ]
        review = self.target_draft['scopeReview']['officialResourceReview']
        video = review['classHours'][0]['resources']['video']
        video['method'] = '官方播放器1x无拖动连续观看并听完。'
        video['locations'] = [*video['locations'], '连续观察00:00至片尾']
        review['reviewedAt'] = '2026-10-27T07:08:03+00:00'
        review['reviewedBy'] = 'fixture-continuous-video-reviewer'
        modalities = video['videoModalityReview']
        for modality in (modalities['visual'], modalities['audio']):
            modality['reviewedAt'] = review['reviewedAt']
            modality['reviewedBy'] = review['reviewedBy']
        modalities['visual']['method'] = '合成测试在官方播放器连续查看原视频画面。'
        modalities['audio']['method'] = '合成测试通过音频工具输出实际听取原视频音轨。'
        review['reviewCorrection'] = {
            'schemaVersion': 'mira.operator.official-review-correction.v1',
            'predecessorDraftSha256': self.prepared['draftSha256'],
            'predecessorDispatchStatus': 'never_started',
            'predecessorJob': str(self.source),
            'reason': '父稿只有字幕和关键帧，本稿补做连续观看。',
        }
        self.target_draft['scopeReview']['correctionLineage'] = {
            'schemaVersion': 'mira.operator.review-evidence-correction-lineage.v1',
            'predecessorTeachingRevision': '1',
            'predecessorDraftSha256': self.prepared['draftSha256'],
            'predecessorDispatchStatus': 'never_started',
            'predecessorJob': str(self.source),
            'correctedAt': '2026-10-27T07:08:03+00:00',
            'correctionReason': '补做官方视频连续观看，课程内容不变。',
            'authorizationBoundary': '本记录不伪造用户授权，也不能据此派发、删除或发布。',
        }
        post_class = self.target_draft['scopeReview']['postClassPractice']
        post_class['officialResourceReviewSha256'] = digest(review)
        post_class['sourceContract'] += ' 当前仅追踪未派发父稿的审阅证据修正。'
        self.target_path = self.root / 'target.json'
        self.write_target()
        self.target = self.service._path(self.target_draft['binding'], '2')
        self.client.reset_mock()
        self.client.owner_fingerprint.return_value = 'prepared-owner-fingerprint'
        self.client.sessions.return_value = []
        self.client.scene_contract_schema = f'{SNAPSHOT_SCHEMA},{AUTHOR_DISPATCH_SNAPSHOT_SCHEMA}'
        self.client.upload_material.side_effect = uploaded

    def write_target(self):
        self.target_path.write_text(json.dumps(self.target_draft, ensure_ascii=False))

    def authorize_video_waiver(self):
        evidence = ('teaching-1从未派发；teaching-2按用户授权将DRM视频记为'
                    'waived_unavailable；连续画面或1x播放不得冒充原音轨听审。')
        self.target_draft['request'] = evidence + self.source_draft['request']
        self.target_draft['qualityRules'][0] = (
            'teaching-2只修正teaching-1的视频DRM豁免证据；不得据此改变课程或自动派发。')
        review = self.target_draft['scopeReview']['officialResourceReview']
        review['reviewedAt'] = '2026-10-27T15:56:46+08:00'
        review['reviewedBy'] = 'fixture-user-authorized-video-waiver'
        video = review['classHours'][0]['resources']['video']
        video['status'] = 'waived_unavailable'
        video['locations'] = ['官方课时资源详情标记视频DRM，当前审阅工具无法取得原音轨。']
        video['method'] = '仅记录本课用户授权的不可用例外；没有把画面、字幕或ASR写成原音轨听审。'
        video['findings'] = ['本次只依其余四类已核材料保持原课程目标；视频内容不声称已审阅。']
        video.pop('videoModalityReview', None)
        review['reviewExceptions'] = [{
            'resourceType': 'video', 'binding': deepcopy(review['binding']),
            'classHourIds': [review['classHours'][0]['classHourId']],
            'authorizedBy': 'user', 'authorizedAt': '2026-10-27T15:56:46+08:00',
            'userInstruction': '直接开始，别这确认那确认的，一课接一课的做啊',
            'reason': '用户回应精确课次授权；官方视频为DRM且当前工具无法取得原音轨。',
        }]
        review['reviewCorrection']['reason'] = '父稿误把不含音轨的画面证据列为reviewed；本稿按用户授权如实改为waived_unavailable。'
        lineage = self.target_draft['scopeReview']['correctionLineage']
        lineage['correctionReason'] = '补录用户对本课DRM视频的精确不可用授权；课程内容不变。'
        lineage['authorizationBoundary'] = (
            '本记录不伪造授权；用户授权只修正本课视频状态，继任本身不能自动派发或发布。')
        post_class = self.target_draft['scopeReview']['postClassPractice']
        post_class['officialResourceReviewSha256'] = digest(review)
        post_class['sourceContract'] += ' 当前记录精确视频不可用授权，不产生新的官方课后目标。'

    def revise(self, **overrides):
        values = {
            'teaching_revision': '2',
            'expected_source_draft_sha256': self.prepared['draftSha256'],
            'reviewer': 'fixture-reviewer',
            'basis': '完整复核连续视频证据；课程结构、教师、技能、锁题与页面不变',
        }
        values.update(overrides)
        return self.service.revise_prepared(self.source, self.target_path, **values)

    def assert_error(self, operation):
        with self.assertRaises(WorkbenchError) as caught:
            operation()
        self.assertEqual(caught.exception.code, 'prepared_predecessor_invalid')

    def test_happy_path_archives_parent_without_cookie_and_never_starts(self):
        original = {path.relative_to(self.source): path.read_bytes()
                    for path in self.source.rglob('*') if path.is_file()}
        result = self.revise()
        self.assertEqual(result['status'], 'prepared')
        receipt = json.loads((self.target / 'prepared-predecessor.json').read_text())
        self.assertEqual(receipt['providerCalls'], 0)
        self.assertEqual(receipt['sourceSessionMatchCount'], 0)
        self.assertEqual(receipt['source']['sourceMaterialsStatus'], 'ready')
        self.assertEqual(self.service._other_artifacts(self.target), [])
        self.assertFalse((self.target / 'dispatch.json').exists())
        self.assertEqual((self.target / 'owner.cookies').read_bytes(),
                         (self.source / 'owner.cookies').read_bytes())
        self.assertFalse(any('cookie' in name for name in receipt['archiveFiles']))
        self.assertFalse(any(path.name == 'owner.cookies'
                             for path in (self.target / 'prepared-predecessor').rglob('*')))
        for relative, raw in original.items():
            self.assertEqual((self.source / relative).read_bytes(), raw)
        self.client.create_session.assert_not_called()
        self.client.upload_material.assert_not_called()

    def test_replay_is_idempotent_and_does_not_rewrite_receipt_or_archive(self):
        self.revise()
        receipt = (self.target / 'prepared-predecessor.json').read_bytes()
        archive = {path.relative_to(self.target): path.read_bytes()
                   for path in (self.target / 'prepared-predecessor').rglob('*') if path.is_file()}
        self.assertEqual(self.revise()['status'], 'prepared')
        self.assertEqual((self.target / 'prepared-predecessor.json').read_bytes(), receipt)
        self.assertEqual({path.relative_to(self.target): path.read_bytes()
                          for path in (self.target / 'prepared-predecessor').rglob('*') if path.is_file()}, archive)
        self.client.create_session.assert_not_called()
        self.client.upload_material.assert_not_called()

    def test_target_can_attach_its_own_reviewed_material_without_starting(self):
        self.revise()
        asset = self.root / 'corrected-evidence.txt'
        asset.write_text('continuous reviewed evidence\n')
        manifest = self.root / 'target-materials.json'
        manifest.write_text(json.dumps({
            'schemaVersion': 'mira.operator.material-attachments.v1',
            'assets': [{
                'assetKey': 'corrected-evidence', 'path': asset.name,
                'sha256': sha(asset.read_bytes()), 'mimeType': 'text/plain',
                'byteSize': len(asset.read_bytes()),
            }],
        }))
        result = self.service.attach_materials(self.target, manifest)
        self.assertEqual(result['materialsStatus'], 'ready')
        self.assertEqual(result['materialCount'], 1)
        self.assertFalse((self.target / 'dispatch.json').exists())
        self.client.upload_material.assert_called_once()
        self.client.create_session.assert_not_called()

    def test_user_authorized_video_waiver_is_an_evidence_only_successor(self):
        self.authorize_video_waiver()
        self.write_target()
        result = self.revise(basis='用户对精确课时DRM视频授权waived_unavailable；其他课程内容不变')
        self.assertEqual(result['status'], 'prepared')
        self.assertFalse((self.target / 'dispatch.json').exists())
        self.client.create_session.assert_not_called()
        self.client.upload_material.assert_not_called()

    def test_video_waiver_cannot_cover_other_resources_or_omit_exact_exception(self):
        self.authorize_video_waiver()
        review = self.target_draft['scopeReview']['officialResourceReview']
        review['reviewExceptions'] = []
        self.target_draft['scopeReview']['postClassPractice']['officialResourceReviewSha256'] = digest(review)
        self.write_target()
        with self.assertRaises(WorkbenchError):
            self.revise()
        self.assertFalse(self.target.exists())

        self.authorize_video_waiver()
        review = self.target_draft['scopeReview']['officialResourceReview']
        courseware = review['classHours'][0]['resources']['courseware']
        courseware['status'] = 'waived_unavailable'
        courseware['locations'] = ['本次课件无法取得。']
        courseware['findings'] = ['用户只授权视频，不授权课件。']
        review['reviewExceptions'].append({
            **deepcopy(review['reviewExceptions'][0]), 'resourceType': 'courseware',
        })
        self.target_draft['scopeReview']['postClassPractice']['officialResourceReviewSha256'] = digest(review)
        self.write_target()
        self.assert_error(self.revise)
        self.client.create_session.assert_not_called()

    def test_matching_parent_session_and_database_artifact_both_block(self):
        source_frozen, source_draft, _ = self.service._load(self.source)
        payload, _ = self.service._material_payload(self.source, source_frozen, source_draft)
        self.client.sessions.return_value = [{
            'id': 'existing-parent-session', 'prompt': payload['prompt'],
            'skillId': source_draft['skillIds'][0], 'status': 'cancelled',
        }]
        self.assert_error(self.revise)
        self.assertFalse((self.target / 'prepared-predecessor.json').exists())
        self.client.sessions.return_value = []
        self.guard.inspect.return_value['existingArtifacts'] = [{'kind': 'preview', 'status': 'failed'}]
        self.assert_error(self.revise)
        self.client.create_session.assert_not_called()
        self.client.upload_material.assert_not_called()

    def test_parent_dispatch_session_state_or_extra_sibling_is_never_exempted(self):
        (self.source / 'dispatch.json').write_text('{}')
        self.assert_error(self.revise)
        (self.source / 'dispatch.json').unlink()
        state = json.loads((self.source / 'state.json').read_text())
        (self.source / 'state.json').write_text(json.dumps({**state, 'sessionId': 'unknown'}))
        self.assert_error(self.revise)
        (self.source / 'state.json').write_text(json.dumps(state))
        other = self.service._path(self.target_draft['binding'], '9')
        other.mkdir(parents=True)
        (other / 'frozen.json').write_text('{}')
        self.assert_error(self.revise)
        self.client.create_session.assert_not_called()

    def test_changed_page_teacher_skill_or_locked_answer_is_not_evidence_only(self):
        for mutate in (
            lambda draft: draft['pagePlan'][0].update(title='changed teaching'),
            lambda draft: draft['teacherContract'].update(teacherName='changed teacher'),
            lambda draft: draft['skillIds'].append('changed-skill'),
            lambda draft: draft['lockedAssessments'].append({'id': 'new-question'}),
        ):
            with self.subTest(mutate=mutate):
                original = deepcopy(self.target_draft)
                mutate(self.target_draft)
                self.write_target()
                self.assert_error(self.revise)
                self.assertFalse((self.target / 'prepared-predecessor.json').exists())
                self.target_draft = original
        self.client.create_session.assert_not_called()

    def test_missing_lineage_wrong_parent_hash_and_fake_terminal_authorization_fail(self):
        original = deepcopy(self.target_draft)
        self.target_draft['scopeReview'].pop('correctionLineage')
        self.write_target()
        self.assert_error(self.revise)
        self.assertFalse(self.target.exists())
        self.target_draft = deepcopy(original)
        self.target_draft['scopeReview']['correctionLineage']['predecessorDraftSha256'] = '0' * 64
        self.write_target()
        self.assert_error(self.revise)
        self.assertFalse(self.target.exists())
        self.target_draft = deepcopy(original)
        self.target_draft['scopeReview']['authoringRevisionAuthorization'] = {
            'authorizedBy': 'user', 'authorizedAt': '2026-10-27T07:08:03+00:00',
            'userInstruction': 'fabricated', 'reason': 'must not be accepted here',
            'binding': deepcopy(self.target_draft['binding']),
        }
        self.write_target()
        self.assert_error(self.revise)
        self.assertFalse(self.target.exists())

    def test_parent_or_archive_drift_blocks_attach_and_first_post(self):
        self.revise()
        archive_file = self.target / 'prepared-predecessor' / 'review-hold.json'
        archive_file.write_text('changed archive')
        with self.assertRaises(WorkbenchError):
            self.service.attach_materials(self.target, self.root / 'not-read.json')
        with self.assertRaises(WorkbenchError):
            self.service.run(self.target, start=True)
        self.client.upload_material.assert_not_called()
        self.client.create_session.assert_not_called()

    def test_parent_change_or_late_matching_session_blocks_before_external_write(self):
        self.revise()
        (self.source / 'material-attachments/source-evidence.txt').write_text('changed')
        with self.assertRaises(WorkbenchError):
            self.service.attach_materials(self.target, self.root / 'not-read.json')
        self.client.upload_material.assert_not_called()
        self.client.create_session.assert_not_called()

    def test_late_parent_request_session_blocks_target_attachment_before_upload(self):
        self.revise()
        source_frozen, source_draft, _ = self.service._load(self.source)
        payload, _ = self.service._material_payload(self.source, source_frozen, source_draft)
        self.client.sessions.return_value = [{
            'id': 'late-parent-session', 'prompt': payload['prompt'],
            'skillId': source_draft['skillIds'][0], 'status': 'cancelled',
        }]
        with self.assertRaises(WorkbenchError) as caught:
            self.service.attach_materials(self.target, self.root / 'must-not-be-read.json')
        self.assertEqual(caught.exception.code, 'prepared_predecessor_invalid')
        self.client.upload_material.assert_not_called()
        self.client.create_session.assert_not_called()


class PreparedRevisionCliTest(unittest.TestCase):
    def test_cli_routes_prepared_revision_without_classroom_or_start(self):
        from scripts import author_textbook_lesson as cli
        args = [
            'revise-prepared', '--source-job', '/source', '--draft', '/corrected',
            '--teaching-revision', '2', '--expected-source-draft-sha256', 'a' * 64,
            '--reviewer', 'reviewer', '--basis', 'continuous video review completed',
        ]
        with patch.object(cli.AppConfig, 'from_env'), patch.object(cli, 'Database'), \
                patch.object(cli, 'TextbookWorkbenchAuthoring') as service, redirect_stdout(io.StringIO()):
            service.return_value.revise_prepared.return_value = {'status': 'prepared'}
            self.assertEqual(cli.main(args), 0)
            service.return_value.revise_prepared.assert_called_once_with(
                Path('/source'), Path('/corrected'), teaching_revision='2',
                expected_source_draft_sha256='a' * 64, reviewer='reviewer',
                basis='continuous video review completed')
            service.return_value.run.assert_not_called()
            service.return_value.attach_materials.assert_not_called()


if __name__ == '__main__':
    unittest.main()
