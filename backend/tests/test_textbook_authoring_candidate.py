"""Candidate acceptance without network, provider calls or production databases."""
from copy import deepcopy
import hashlib
import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image

from content.textbook_authoring_candidate import (validate_authoring_candidate, CANDIDATE_FILE,
    _assets, _scenes, _questions, _image_coverage)
from content.textbook_catalog import canonical, digest, lesson_by_id
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_scene_contract import freeze_scene_contract, validate_scene_contract
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository
from services.course_reuse_resolver import lesson_scope
from services.textbook_learning_service import TextbookLearningService
from services.textbook_preview_service import TextbookPreviewService
from tests.test_textbook_learning import IsolatedDatabase


class CandidateFixture:
    def __init__(self, root):
        self.root, self.output, self.store = Path(root), Path(root) / 'jobs', Path(root) / 'classrooms'
        self.manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        self.node, self.stage, self.session = 'u2-l1', 'stage-candidate', 'session-candidate'
        unit, lesson = lesson_by_id(self.manifest, self.node)
        binding = {k: self.manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
        binding.update(nodeId=self.node, unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
        self.job = self.output / binding['editionId'] / self.node / 'teaching-1/authoring-job'
        self.job.mkdir(parents=True)
        self.media = self.store / self.stage / 'media'
        self.media.mkdir(parents=True)
        self.assets = []
        for key, color in [('left', 'red'), ('right', 'green'), ('scene', 'blue')]:
            raw = io.BytesIO()
            Image.new('RGB', (64, 64), color).save(raw, format='PNG')
            data = raw.getvalue()
            (self.media / f'generated-{key}.png').write_bytes(data)
            self.assets.append({'assetKey': key, 'src': f'/api/classroom-media/{self.stage}/media/generated-{key}.png',
                'sha256': hashlib.sha256(data).hexdigest(), 'width': 64, 'height': 64,
                'bindingVersion': 1, 'status': 'author_candidate'})
        self.src = {a['assetKey']: a['src'] for a in self.assets}
        self.draft = {'binding': binding, 'request': 'Synthetic frozen request. No provider calls.',
            'teacherContract': {'subject': binding['subject'], 'teacherProfileId': 'teacher-test',
                'teacherProfileHash': 'f' * 64, 'teacherProfileVersion': 1, 'teacherName': 'Teacher',
                'voiceId': 'voice-test', 'languageCode': 'zh-CN'},
            'qualityRules': ['Pictures and prerecorded narration.'], 'scopeReview': {'status': 'verified'},
            'pagePlan': [{'page': 1, 'type': 'slide', 'title': 'Observe', 'move': 'Look.'},
                         {'page': 2, 'type': 'interactive', 'title': 'Try', 'move': 'Try.'}],
            'lockedAssessments': []}
        cues = {'schemaVersion': 'mira.interactive.narration-cues.v1', 'cues': [{'id': 'try', 'text': '试一试。'}]}
        html = '<html><head><meta name="mira-responsive-activity" content="low-reading-v1"></head><body>'
        html += f'<img src="{self.src["scene"]}"><script type="application/json" id="mira-narration-cues">{json.dumps(cues, ensure_ascii=False)}</script>'
        html += '<button onclick="window.miraNarrate(\'try\')">听</button></body></html>'
        self.classroom = {'id': self.stage, 'stage': {'id': self.stage, 'name': 'Synthetic'}, 'scenes': [
            {'id': 'one', 'stageId': self.stage, 'order': 1, 'title': 'Observe', 'type': 'slide',
             'actions': [{'id': 'one-speech', 'type': 'speech', 'text': '看一看。'}],
             'content': {'canvas': {'elements': [{'type': 'image', 'src': self.src['scene'], 'left': 1e-7}]}}},
            {'id': 'two', 'stageId': self.stage, 'order': 2, 'title': 'Try', 'type': 'interactive',
             'actions': [{'id': 'two-speech', 'type': 'speech', 'text': '试一试。'}], 'content': {'html': html}}]}
        for i in range(4):
            page, qid = i + 3, f'q{i}'
            spec = {'id': qid, 'page': page, 'type': 'single', 'points': 10, 'question': f'听第{i}题。',
                    'analysis': '看图辨认。', 'choices': [{'value': 'A', 'label': '第一张图', 'asset': 'left'},
                                                         {'value': 'B', 'label': '第二张图', 'asset': 'right'}], 'answer': 'A'}
            self.draft['lockedAssessments'].append(spec)
            self.draft['pagePlan'].append({'page': page, 'type': 'quiz', 'title': f'Question {i}', 'move': 'Choose.', 'questionIds': [qid]})
            q = {k: spec[k] for k in ('id', 'type', 'points', 'question', 'analysis')}
            q.update(answer=['A'], options=[{k: c[k] for k in ('value', 'label')} for c in spec['choices']],
                     visual={'kind': 'image', 'src': self.src['scene'], 'alt': '场景'},
                     optionVisuals={c['value']: {'kind': 'image', 'src': self.src[c['asset']], 'alt': c['label']} for c in spec['choices']})
            self.classroom['scenes'].append({'id': f'scene-{page}', 'stageId': self.stage, 'order': page, 'type': 'quiz',
                'title': f'Question {i}', 'actions': [{'id': f'quiz-{i}', 'type': 'speech', 'text': spec['question']}], 'content': {'questions': [q]}})
        self.authoring = {'mode': 'openmaic_pro_workbench', 'sessionId': self.session, 'stageId': self.stage,
                          'request': 'Synthetic reviewed request', 'skillIds': ['mira-primary-courseware'], 'imageProvenance': 'Synthetic test images'}
        self.freeze()
        self.ledger = {'schemaVersion': 'mira.textbook.authoring-candidate.v1', 'sessionId': self.session,
            'stageId': self.stage, 'frozenContract': self.frozen['sceneContract'], 'status': 'author_candidate',
            'verification': 'static_contract_only_not_play_or_semantic_review', 'assetBindings': deepcopy(self.assets),
            'bindingHistory': [], 'scenes': []}
        self.snapshot()

    def freeze(self):
        raw = (json.dumps(self.draft, ensure_ascii=False, indent=2) + '\n').encode()
        check = {'manifestSha256': digest(self.manifest), 'lessonScopeSha256': lesson_scope(self.manifest, self.node)}
        policy = freeze_interaction_policy()
        self.frozen = {'schemaVersion': 'mira.operator.workbench-authoring.v3', 'binding': self.draft['binding'],
            'teacherContract': self.draft['teacherContract'], 'catalogCheck': check, 'interactionPolicy': policy,
            'draftSha256': hashlib.sha256(raw).hexdigest(), 'draftCanonicalSha256': digest(self.draft),
            'requestSha256': hashlib.sha256(self.draft['request'].encode()).hexdigest(), 'origin': 'http://127.0.0.1:3100',
            'sceneContract': freeze_scene_contract(self.draft, check, policy)}
        (self.job / 'draft.json').write_bytes(raw)
        self.write(self.job / 'frozen.json', self.frozen)
        self.write(self.job / 'state.json', {'sessionId': self.session, 'savedStages': [{'stageId': self.stage}]})

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def snapshot(self):
        self.ledger['scenes'] = [{'sceneId': s['id'], 'order': s['order'], 'canonicalJson': canonical(s),
            'sha256': digest(s), 'contractSha256': self.frozen['sceneContract']['sha256']} for s in self.classroom['scenes']]
        self.save()

    def save(self):
        self.ledger['sha256'] = digest({k: v for k, v in self.ledger.items() if k != 'sha256'})
        self.write(self.store / self.stage / CANDIDATE_FILE, self.ledger)

    def validate(self, **kwargs):
        return validate_authoring_candidate(self.classroom, self.store, kwargs.pop('authoring', self.authoring),
            kwargs.pop('manifest', self.manifest), self.node, output_root=self.output,
            runtime_origin='http://127.0.0.1:3100', **kwargs)

    def use_legacy_interaction_policy(self):
        policy = deepcopy(self.frozen['interactionPolicy'])
        policy['policy']['version'] = 1
        policy['policy'].pop('wholeCourseQualityContract', None)
        policy['sha256'] = digest(policy['policy'])
        self.frozen['interactionPolicy'] = policy
        self.frozen['sceneContract'] = freeze_scene_contract(
            self.draft, self.frozen['catalogCheck'], policy)
        self.write(self.job / 'frozen.json', self.frozen)
        self.ledger['frozenContract'] = self.frozen['sceneContract']
        self.snapshot()

    def archive_complete_scene_revision(self):
        after = deepcopy(self.ledger)
        after_raw = (self.store / self.stage / CANDIDATE_FILE).read_bytes()
        replacement = deepcopy(self.classroom['scenes'][1])
        original = deepcopy(replacement)
        original['actions'][0]['text'] = '这是修订前的互动讲解。'
        before = deepcopy(after)
        before['scenes'][1] = {'sceneId': original['id'], 'order': original['order'],
            'canonicalJson': canonical(original), 'sha256': digest(original),
            'contractSha256': self.frozen['sceneContract']['sha256']}
        before['sha256'] = digest({key: value for key, value in before.items() if key != 'sha256'})
        before_raw = (canonical(before) + '\n').encode()
        original_raw = (canonical(original) + '\n').encode()
        replacement_raw = (canonical(replacement) + '\n').encode()
        scene_suffix = hashlib.sha256(original['id'].encode()).hexdigest()
        complete = {'exactSceneId': original['id'],
            'frozenContractSha256': self.frozen['sceneContract']['sha256'],
            'originalSceneSha256': digest(original), 'currentSceneSha256': digest(original),
            'replacementSceneSha256': digest(replacement),
            'preservedIdentity': {key: original.get(key) for key in
                ('stageId', 'order', 'type', 'title', 'outlineId', 'createdAt')},
            'reason': 'Replace the complete scene after a body-quality review.',
            'originalSceneFileSha256': hashlib.sha256(original_raw).hexdigest(),
            'replacementSceneFileSha256': hashlib.sha256(replacement_raw).hexdigest(),
            'assetAdditions': []}
        revision = {'sceneId': original['id'], 'beforeSceneSha256': digest(original),
            'afterSceneSha256': digest(replacement), 'completeSceneEvidence': complete,
            'fieldDiffs': [{'path': '/', 'kind': 'exact-complete-scene-replacement',
                'beforeSha256': digest(original), 'afterSha256': digest(replacement),
                'reason': complete['reason']}], 'htmlEvidence': None,
            'reviewBasis': 'Synthetic complete-scene review fixture.'}
        plan_body = {'schemaVersion': 'mira.textbook.current-review-revision-plan.v1',
            'verification': 'static_review_only_not_play_audio_or_publication',
            'input': {'jobDir': str(self.job), 'stageId': self.stage,
                'expectedDocumentSha256': '1' * 64, 'expectedCandidateSha256': before['sha256'],
                'expectedCandidateFileSha256': hashlib.sha256(before_raw).hexdigest(),
                'stateTransitionNotes': ['Synthetic revision.'], 'revisions': []},
            'dataDir': str(self.store.parent), 'sessionId': self.session, 'stageId': self.stage,
            'ownerFingerprint': '2' * 64, 'contractSha256': self.frozen['sceneContract']['sha256'],
            'beforeDocumentSha256': '3' * 64, 'afterDocumentSha256': '4' * 64,
            'beforeCandidateSha256': before['sha256'],
            'beforeCandidateFileSha256': hashlib.sha256(before_raw).hexdigest(),
            'afterCandidateSha256': after['sha256'],
            'afterCandidateFileSha256': hashlib.sha256(after_raw).hexdigest(),
            'assetAdditions': [], 'stateTransitionNotes': ['Synthetic revision.'],
            'revisions': [revision]}
        plan = {**plan_body, 'sha256': digest(plan_body)}
        folder = (self.store.parent / 'textbook-current-review-revisions'
            / hashlib.sha256(self.session.encode()).hexdigest() / self.stage / plan['sha256'])
        folder.mkdir(parents=True)
        (folder / 'intent.json').write_text(canonical(plan) + '\n')
        (folder / 'original-candidate.json').write_bytes(before_raw)
        (folder / f'original-scene-{scene_suffix}.json').write_bytes(original_raw)
        (folder / f'declared-original-scene-{scene_suffix}.json').write_bytes(original_raw)
        (folder / f'replacement-scene-{scene_suffix}.json').write_bytes(replacement_raw)
        receipt_body = {'schemaVersion': 'mira.textbook.current-review-revision-receipt.v1',
            'revisionId': plan['sha256'], 'status': 'static_candidate_review_revised',
            'verification': 'static_review_only_not_play_audio_or_publication',
            'sessionId': self.session, 'stageId': self.stage, 'planSha256': plan['sha256'],
            'documentSha256': plan['afterDocumentSha256'], 'candidateSha256': after['sha256'],
            'candidateFileSha256': hashlib.sha256(after_raw).hexdigest(),
            'stateTransitionNotes': plan['stateTransitionNotes'], 'revisions': plan['revisions'],
            'assetAdditions': [], 'providerCalls': 0}
        receipt = {**receipt_body, 'sha256': digest(receipt_body)}
        (folder / 'receipt.json').write_text(canonical(receipt) + '\n')
        return folder


class CandidateIntegrityTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.f = CandidateFixture(tmp.name)

    def rejected(self):
        with self.assertRaises(ApiError) as error:
            self.f.validate()
        self.assertEqual(error.exception.code, 'textbook_preview_candidate_invalid')

    def test_complete_candidate_passes_without_changing_any_bytes(self):
        before = deepcopy(self.f.classroom)
        summary = self.f.validate()
        self.assertEqual(summary['sceneCount'], 6)
        self.assertEqual(summary['interactionPolicyVersion'], 2)
        self.assertEqual(summary['interactionPolicySha256'], self.f.frozen['interactionPolicy']['sha256'])
        self.assertEqual(summary['wholeCourseQualityContractSha256'],
                         digest(self.f.frozen['interactionPolicy']['policy']['wholeCourseQualityContract']))
        self.assertEqual(self.f.classroom, before)

    def test_complete_scene_followup_binds_legacy_candidate_to_current_policy(self):
        self.f.use_legacy_interaction_policy()
        folder = self.f.archive_complete_scene_revision()
        before = deepcopy(self.f.classroom)
        followup = self.f.validate()['completeSceneReviewFollowup']
        self.assertEqual(followup['baseInteractionPolicyVersion'], 1)
        self.assertGreaterEqual(followup['currentInteractionPolicyVersion'], 2)
        self.assertEqual(followup['revisionIds'], [folder.name])
        self.assertEqual(followup['completeSceneIds'], ['two'])
        self.assertEqual(self.f.classroom, before)

        replacement = folder / f'replacement-scene-{hashlib.sha256(b"two").hexdigest()}.json'
        replacement.write_text('{}')
        self.rejected()

    def test_js_scene_float_spelling_is_compared_as_parsed_json(self):
        rec = self.f.ledger['scenes'][0]
        rec['canonicalJson'] = rec['canonicalJson'].replace('1e-07', '1e-7')
        rec['sha256'] = hashlib.sha256(rec['canonicalJson'].encode()).hexdigest()
        self.f.save()
        self.assertIsNotNone(self.f.validate())

    def test_native_complete_scene_integral_float_input_retains_exact_byte_fences(self):
        folder = self.f.archive_complete_scene_revision()
        plan = json.loads((folder / 'intent.json').read_text())
        proof = plan['revisions'][0]['completeSceneEvidence']
        suffix = hashlib.sha256(b'two').hexdigest()
        for prefix, field in (
                ('declared-original-scene', 'originalSceneFileSha256'),
                ('replacement-scene', 'replacementSceneFileSha256'),
                ('original-scene', None)):
            path = folder / f'{prefix}-{suffix}.json'
            value = json.loads(path.read_text())
            value['order'] = float(value['order'])
            path.write_text(canonical(value) + '\n')
            if field:
                proof[field] = hashlib.sha256(path.read_bytes()).hexdigest()
        plan['sha256'] = digest({k: v for k, v in plan.items() if k != 'sha256'})
        receipt = json.loads((folder / 'receipt.json').read_text())
        receipt.update(revisionId=plan['sha256'], planSha256=plan['sha256'],
                       revisions=deepcopy(plan['revisions']))
        receipt['sha256'] = digest({k: v for k, v in receipt.items() if k != 'sha256'})
        (folder / 'intent.json').write_text(canonical(plan) + '\n')
        (folder / 'receipt.json').write_text(canonical(receipt) + '\n')
        renamed = folder.with_name(plan['sha256'])
        folder.rename(renamed)
        self.assertEqual(self.f.validate()['completeSceneReviewFollowup']['completeSceneIds'], ['two'])
        path = renamed / f'replacement-scene-{suffix}.json'
        # Even an equivalent JSON spelling cannot replace the approved bytes.
        path.write_text(path.read_text().replace('"order":2.0', '"order":2'))
        self.rejected()

    def test_missing_ledger_and_changed_session_cannot_downgrade_v3(self):
        (self.f.store / self.f.stage / CANDIDATE_FILE).unlink()
        self.rejected()
        self.f.authoring['sessionId'] = 'invented-session'
        self.rejected()

    def test_orphan_ledger_is_rejected(self):
        (self.f.job / 'frozen.json').unlink()
        self.rejected()

    def test_real_legacy_session_and_ordinary_classroom_remain_compatible(self):
        (self.f.store / self.f.stage / CANDIDATE_FILE).unlink()
        for version in (1, 2):
            self.f.frozen['schemaVersion'] = f'mira.operator.workbench-authoring.v{version}'
            self.f.write(self.f.job / 'frozen.json', self.f.frozen)
            self.assertIsNone(self.f.validate())
        (self.f.job / 'frozen.json').unlink()
        self.assertIsNone(self.f.validate())

    def test_real_legacy_session_can_coexist_with_another_v3_job(self):
        other = self.f.job.parent.parent / 'teaching-old/authoring-job'
        other.mkdir(parents=True)
        self.f.write(other / 'frozen.json', {**self.f.frozen, 'schemaVersion': 'mira.operator.workbench-authoring.v2'})
        self.f.write(other / 'state.json', {'sessionId': 'legacy-session', 'savedStages': [{'stageId': 'legacy-stage'}]})
        (self.f.store / self.f.stage / CANDIDATE_FILE).unlink()
        with self.assertRaises(ApiError):
            self.f.validate(authoring={**self.f.authoring, 'sessionId': 'legacy-session'})
        self.f.classroom['id'] = self.f.classroom['stage']['id'] = 'legacy-stage'
        self.assertIsNone(self.f.validate(authoring={**self.f.authoring, 'sessionId': 'legacy-session', 'stageId': 'legacy-stage'}))
        self.f.classroom['id'] = self.f.classroom['stage']['id'] = 'unknown-stage'
        with self.assertRaises(ApiError):
            self.f.validate(authoring={**self.f.authoring, 'sessionId': 'legacy-session', 'stageId': 'unknown-stage'})

    def test_session_stage_origin_and_frozen_contract_are_bound(self):
        original = deepcopy(self.f.ledger)
        for mutation in [lambda: self.f.ledger.update(sessionId='other'),
                         lambda: self.f.ledger.update(stageId='other'),
                         lambda: self.f.ledger['frozenContract'].update(sha256='0' * 64)]:
            self.f.ledger = deepcopy(original)
            mutation(); self.f.save(); self.rejected()
        self.f.ledger = original; self.f.save()
        self.f.authoring['stageId'] = 'other'; self.rejected()

    def test_catalog_and_self_reported_grade_cannot_override_real_manifest(self):
        changed = deepcopy(self.f.manifest)
        changed['units'][0]['title'] += ' changed'
        with self.assertRaises(ApiError):
            self.f.validate(manifest=changed)
        self.f.draft['binding']['gradeCode'] = 'primary_3'
        self.f.freeze()
        self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']; self.f.snapshot()
        self.rejected()

    def test_full_scene_coverage_order_title_and_content_are_checked(self):
        original = deepcopy(self.f.classroom)
        for mutation in [lambda: self.f.classroom['scenes'].pop(),
                         lambda: self.f.classroom['scenes'][0].update(order=9),
                         lambda: self.f.classroom['scenes'][0].update(title='Other'),
                         lambda: self.f.classroom['scenes'][1]['actions'][0].update(text='Changed')]:
            self.f.classroom = deepcopy(original); mutation(); self.rejected()
        self.f.classroom = deepcopy(original)
        self.f.classroom['scenes'][0]['title'] = 'Changed'
        self.f.snapshot(); self.rejected()  # Rehashed ledger cannot change frozen title.

    def test_locked_questions_and_visual_asset_bindings_are_independent_checks(self):
        original = deepcopy(self.f.classroom)
        def question():
            return self.f.classroom['scenes'][2]['content']['questions'][0]
        for mutation in [lambda: question().update(answer=['B']),
                         lambda: question().update(question='Changed'),
                         lambda: question()['options'][0].update(value='Z'),
                         lambda: question()['optionVisuals']['A'].update(src=self.f.src['right'])]:
            self.f.classroom = deepcopy(original); mutation(); self.f.snapshot(); self.rejected()

    def test_image_original_bytes_dimensions_and_link_paths_are_checked(self):
        self.f.ledger['assetBindings'][0]['width'] = 63; self.f.save(); self.rejected()
        self.f.ledger['assetBindings'][0]['width'] = 64; self.f.save()
        path = self.f.media / 'generated-left.png'
        data = path.read_bytes(); path.write_bytes(data + b'changed'); self.rejected()
        path.write_bytes(data)
        other = self.f.root / 'outside.png'; other.write_bytes(data)
        path.unlink(); path.symlink_to(other); self.rejected()

    def test_outer_digest_scene_digest_and_duplicate_json_members_are_rejected(self):
        self.f.ledger['sha256'] = '0' * 64
        self.f.write(self.f.store / self.f.stage / CANDIDATE_FILE, self.f.ledger); self.rejected()
        self.f.ledger['scenes'][0]['sha256'] = '0' * 64; self.f.save(); self.rejected()
        self.f.snapshot()
        record = self.f.ledger['scenes'][0]
        record['canonicalJson'] = record['canonicalJson'].replace('{', '{"id":"other",', 1)
        record['sha256'] = hashlib.sha256(record['canonicalJson'].encode()).hexdigest()
        self.f.save(); self.rejected()

    def test_rebinding_history_is_contiguous_and_checks_historical_bytes(self):
        before = deepcopy(self.f.ledger['assetBindings'][0])
        after = {**before, 'bindingVersion': 2}
        self.f.ledger['assetBindings'][0] = after
        self.f.ledger['bindingHistory'] = [{'assetKey': before['assetKey'], 'from': before, 'to': after}]
        self.f.save(); self.assertIsNotNone(self.f.validate())
        self.f.ledger['bindingHistory'][0]['from']['bindingVersion'] = 0
        self.f.save(); self.rejected()


    def test_optional_question_main_image_and_explicit_visual_asset(self):
        question = self.f.classroom['scenes'][2]['content']['questions'][0]
        question.pop('visual')
        self.f.snapshot(); self.assertIsNotNone(self.f.validate())
        self.f.draft['lockedAssessments'][0]['visualAsset'] = 'scene'
        self.f.freeze(); self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']; self.f.snapshot()
        self.rejected()
        question['visual'] = {'kind': 'image', 'src': self.f.src['scene']}
        self.f.snapshot(); self.assertIsNotNone(self.f.validate())
        question['visual']['src'] = self.f.src['left']
        self.f.snapshot(); self.rejected()

    def test_image_from_another_stage_is_rejected_even_with_correct_bytes(self):
        other = self.f.store / 'other-stage/media'; other.mkdir(parents=True)
        asset = self.f.ledger['assetBindings'][0]
        original = self.f.media / 'generated-left.png'
        (other / original.name).write_bytes(original.read_bytes())
        asset['src'] = asset['src'].replace(self.f.stage, 'other-stage')
        self.f.save(); self.rejected()

    def test_high_grade_candidate_can_have_no_images_without_weakening_low_grade(self):
        self.f.manifest['gradeCode'] = 'primary_3'
        self.f.draft['binding']['gradeCode'] = 'primary_3'
        for question in self.f.draft['lockedAssessments']:
            for choice in question['choices']:
                choice.pop('asset')
        self.f.classroom['scenes'][0]['content']['canvas']['elements'] = []
        html = self.f.classroom['scenes'][1]['content']['html']
        self.f.classroom['scenes'][1]['content']['html'] = html.replace(f'<img src="{self.f.src["scene"]}">', '')
        for scene in self.f.classroom['scenes'][2:]:
            q = scene['content']['questions'][0]
            q.pop('visual'); q.pop('optionVisuals')
        self.f.freeze(); self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']
        self.f.ledger['assetBindings'] = []; self.f.snapshot()
        self.assertEqual(self.f.validate()['assetCount'], 0)

    def test_low_grade_duplicate_picture_bytes_are_rejected(self):
        left, right = self.f.ledger['assetBindings'][:2]
        (self.f.media / 'generated-right.png').write_bytes((self.f.media / 'generated-left.png').read_bytes())
        right['sha256'] = left['sha256']
        self.f.save(); self.rejected()

    def test_frozen_widget_type_is_checked_independently_of_scene_hash(self):
        self.f.draft['pagePlan'][1]['widgetType'] = 'simulation'
        self.f.classroom['scenes'][1]['content']['widgetType'] = 'simulation'
        self.f.freeze(); self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']; self.f.snapshot()
        self.assertIsNotNone(self.f.validate())
        self.f.classroom['scenes'][1]['content']['widgetType'] = 'game'
        self.f.snapshot(); self.rejected()

    def test_interactive_cues_require_real_markup_marker_and_exact_speech_coverage(self):
        original = deepcopy(self.f.classroom)
        def page():
            return self.f.classroom['scenes'][1]
        def change_html(fn):
            page()['content']['html'] = fn(page()['content']['html'])
        for mutation in [
            lambda: change_html(lambda h: h.replace('<script type="application/json"', '<script type="text/plain"')),
            lambda: change_html(lambda h: h.replace('<script type="application/json"', '<template><script type="application/json"').replace('</script>', '</script></template>')),
            lambda: change_html(lambda h: h.replace('name="mira-responsive-activity"', 'name="other"')),
            lambda: page()['actions'].append({'id': 'extra', 'type': 'speech', 'text': '未绑定的句子。'}),
            lambda: page()['actions'].append({'id': 'duplicate', 'type': 'speech', 'text': '试一试。'}),
        ]:
            self.f.classroom = deepcopy(original); mutation(); self.f.snapshot(); self.rejected()

    def test_quiz_extra_speech_must_be_frozen_guidance_and_never_analysis(self):
        scene = self.f.classroom['scenes'][2]
        scene['actions'].append({'id': 'guidance', 'type': 'speech', 'text': '听完再选。'})
        self.f.snapshot(); self.rejected()
        self.f.draft['pagePlan'][2]['narrationGuidance'] = ['听完再选。']
        self.f.freeze(); self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']; self.f.snapshot()
        self.assertIsNotNone(self.f.validate())
        scene['actions'][-1]['text'] = scene['content']['questions'][0]['analysis']
        self.f.snapshot(); self.rejected()
        scene['actions'] = []
        self.f.snapshot(); self.rejected()

    def test_unbound_canvas_and_html_image_sources_are_rejected(self):
        original = deepcopy(self.f.classroom)
        for src in ('data:image/png;base64,aGVsbG8=', '/unbound/picture.png', 'https://example.com/picture.png'):
            self.f.classroom = deepcopy(original)
            self.f.classroom['scenes'][0]['content']['canvas']['elements'].append({'type': 'image', 'src': src})
            self.f.snapshot(); self.rejected()
            self.f.classroom = deepcopy(original)
            self.f.classroom['scenes'][1]['content']['html'] += f'<img src="{src}">'
            self.f.snapshot(); self.rejected()


    def test_high_grade_interactive_may_omit_cues_but_cannot_supply_invalid_block(self):
        self.f.manifest['gradeCode'] = self.f.draft['binding']['gradeCode'] = 'primary_3'
        self.f.freeze(); self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']
        self.f.classroom['scenes'][1]['content']['html'] = '<html><body><button>尝试</button></body></html>'
        self.f.snapshot(); self.assertIsNotNone(self.f.validate())
        self.f.classroom['scenes'][1]['content']['html'] += '<script type="application/json" id="mira-narration-cues">{}</script>'
        self.f.snapshot(); self.rejected()

    def test_slide_also_requires_real_nonempty_unique_speech_actions(self):
        original = deepcopy(self.f.classroom)
        for actions in ([], [{'id': 'speech', 'type': 'speech', 'text': ' '}],
                        [{'id': 'same', 'type': 'speech', 'text': '一句'}, {'id': 'same', 'type': 'speech', 'text': '另一句'}]):
            self.f.classroom = deepcopy(original)
            self.f.classroom['scenes'][0]['actions'] = actions
            self.f.snapshot(); self.rejected()


    def test_high_grade_visual_asset_stays_locked_when_choices_are_text_only(self):
        self.f.manifest['gradeCode'] = self.f.draft['binding']['gradeCode'] = 'primary_3'
        for question in self.f.draft['lockedAssessments']:
            for choice in question['choices']:
                choice.pop('asset')
        self.f.draft['lockedAssessments'][0]['visualAsset'] = 'scene'
        self.f.freeze(); self.f.ledger['frozenContract'] = self.f.frozen['sceneContract']; self.f.snapshot()
        self.assertIsNotNone(self.f.validate())
        self.f.classroom['scenes'][2]['content']['questions'][0]['visual']['src'] = self.f.src['left']
        self.f.snapshot(); self.rejected()


class CandidateAdoptionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.f = CandidateFixture(tmp.name)
        self.db = IsolatedDatabase(('082_fixed_textbook_learning.sql', '083_textbook_course_previews.sql', '087_learning_course_reuse.sql'))
        self.addCleanup(self.db.raw.close)
        self.repo = TextbookRepository(self.db)
        TextbookLearningService(self.repo).import_manifest(self.f.manifest)
        self.runtime = Mock(base_url='http://127.0.0.1:3100')
        self.runtime.get_classroom.side_effect = lambda _: deepcopy(self.f.classroom)
        self.service = TextbookPreviewService(self.repo, self.runtime, authoring_output_root=self.f.output)

    def adopt(self):
        f = self.f
        return self.service.adopt(f.manifest['editionId'], f.manifest['revisionId'], f.node, f.stage, f.store, f.authoring)

    def assert_no_writes(self):
        self.runtime.save_preview_classroom.assert_not_called()
        self.runtime.start_generation.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_course_previews').fetchone()['n'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_course_reuse_slots').fetchone()['n'], 0)

    def test_invalid_candidate_fails_before_native_normalization_or_database_reservation(self):
        self.f.classroom['scenes'][1]['actions'][0]['id'] = 'one-speech'  # Would normalize in legacy.
        with self.assertRaises(ApiError) as error:
            self.adopt()
        self.assertEqual(error.exception.code, 'textbook_preview_candidate_invalid')
        self.assert_no_writes()

    def test_v3_normalization_requires_explicit_revision_and_never_saves(self):
        self.f.classroom['scenes'][1]['actions'][0]['id'] = 'one-speech'
        self.f.snapshot()
        with self.assertRaises(ApiError) as error:
            self.adopt()
        self.assertEqual(error.exception.code, 'textbook_preview_candidate_revision_required')
        self.assert_no_writes()

    def test_valid_candidate_adopts_without_mutating_original_classroom(self):
        result = self.adopt()
        self.assertEqual(result['status'], 'review_required')
        self.runtime.save_preview_classroom.assert_not_called()
        self.runtime.start_generation.assert_not_called()
        row = self.db.execute('SELECT input_json FROM learning_textbook_course_previews WHERE preview_key=?',
                              (result['previewKey'],)).fetchone()
        candidate = json.loads(row['input_json'])['authoringCandidate']
        self.assertEqual(candidate['interactionPolicyVersion'], 2)
        self.assertEqual(candidate['interactionPolicySha256'], self.f.frozen['interactionPolicy']['sha256'])
        self.assertEqual(self.adopt()['previewKey'], result['previewKey'])

    def test_legacy_complete_scene_followup_is_frozen_into_the_preview_input(self):
        self.f.use_legacy_interaction_policy()
        folder = self.f.archive_complete_scene_revision()
        result = self.adopt()
        row = self.db.execute('SELECT input_json FROM learning_textbook_course_previews WHERE preview_key=?',
                              (result['previewKey'],)).fetchone()
        frozen = json.loads(row['input_json'])
        followup = frozen['authoringCandidate']['completeSceneReviewFollowup']
        self.assertEqual(followup['revisionIds'], [folder.name])
        self.assertEqual(followup['candidateSourceSha256'], frozen['sourceSha256'])
        self.assertEqual(followup['currentInteractionPolicySha256'], freeze_interaction_policy()['sha256'])


class NativeCandidateInteropTest(unittest.TestCase):
    def test_actual_native_candidate_bytes_verify_in_python(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/textbook_authoring_candidate/native_candidate_v1.json').read_text())
        ledger, classroom = fixture['candidate'], fixture['classroom']
        # The /api/classroom export adds this top-level identity to CourseDocument.
        classroom['id'] = classroom['stage']['id']
        self.assertEqual(digest({k: v for k, v in ledger.items() if k != 'sha256'}), ledger['sha256'])
        self.assertEqual(canonical(fixture['canonicalVector']['value']), fixture['canonicalVector']['canonical'])
        contract = validate_scene_contract(ledger['frozenContract'])
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            for relative, encoded in fixture['files'].items():
                path = store / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(encoded))
            assets = _assets(ledger, store, classroom['id'])
            _scenes(ledger, classroom, contract)
            _questions(classroom, contract, assets)
            _image_coverage(classroom, contract, assets)
        self.assertIn('1e-7', ledger['scenes'][0]['canonicalJson'])
