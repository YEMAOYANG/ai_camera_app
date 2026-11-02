import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from services.textbook_partial_preview_revision import bind_inherited_audio, register_partial_revision, verify_reviewed_scene_chain


class ReviewedSceneChainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        (self.job / 'reviewed-patches').mkdir()
        self.sid, self.stage, self.frozen = 'session-1', 'stage-1', 'a' * 64
        self.before = {'id': 'scene-p6', 'stageId': self.stage, 'type': 'interactive',
                       'content': {'html': '<p>old</p>'},
                       'actions': [{'id': 'cue', 'type': 'speech', 'text': 'old'}]}
        self.after = {**self.before, 'content': {'html': '<p>new</p>'},
                      'actions': [{'id': 'cue', 'type': 'speech', 'text': 'new'}]}
        self.source = {'id': 'parent', 'stage': {'id': 'parent'},
                       'scenes': [{**self.before, 'stageId': 'parent'}]}
        self.target = {'id': self.stage, 'stage': {'id': self.stage}, 'scenes': [self.after]}
        self.ops = {'target': '/scenes/scene-p6', 'expectedSceneSha256': digest(self.before), 'ops': [
            {'op': 'str_replace', 'path': '/content/html', 'oldText': 'old', 'newText': 'new'},
            {'op': 'set', 'path': '/actions', 'value': self.after['actions']}]}
        raw = json.dumps(self.ops, separators=(',', ':')).encode()
        self.ops_sha = hashlib.sha256(raw).hexdigest()
        self.folder = self.job / 'reviewed-patches' / self.ops_sha
        self.folder.mkdir()
        data = {'sessionId': self.sid, 'stageId': self.stage, 'sceneId': self.before['id'],
                'beforeSceneSha256': digest(self.before), 'afterSceneSha256': digest(self.after),
                'opsSha256': self.ops_sha, 'frozenFileSha256': self.frozen}
        self.events = [{'id': 11, 'type': 'mira_textbook_reviewed_patch', 'data': data}]
        (self.folder / 'ops.json').write_bytes(raw)
        (self.folder / 'before.json').write_text(canonical(self.before))
        (self.folder / 'after.json').write_text(canonical(self.after))
        (self.folder / 'receipt.json').write_text(json.dumps({'status': 'applied', 'eventSeq': 11, **data}))

    def verify(self):
        return verify_reviewed_scene_chain(source_room=self.source, target_room=self.target,
            stage_id=self.stage, session_id=self.sid, frozen_file_sha256=self.frozen,
            job_directory=self.job, events=self.events)

    def test_authenticated_patch_reproduces_exact_scene(self):
        result = self.verify()
        self.assertEqual([p['eventSeq'] for p in result['patches']], [11])
        self.assertEqual(result['targetSha256'], digest(self.target))

    def test_unlogged_or_wrong_owner_patch_cannot_be_selected(self):
        self.events[0]['data']['sessionId'] = 'someone-else'
        with self.assertRaises(ApiError):
            self.verify()

    def test_altered_operations_and_receipts_are_rejected(self):
        (self.folder / 'ops.json').write_text('{}')
        with self.assertRaises(ApiError):
            self.verify()

    def test_changes_not_supported_by_patch_are_rejected(self):
        self.target['scenes'][0]['content']['html'] = '<p>different</p>'
        with self.assertRaises(ApiError):
            self.verify()

    def test_symlinked_evidence_is_rejected(self):
        path = self.folder / 'before.json'
        target = self.folder / 'copy.json'
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(ApiError):
            self.verify()


class PartialBindingTest(unittest.TestCase):
    def setUp(self):
        self.wav = b'verified audio bytes'
        self.receipt = {'requestId': 'original-request', 'status': 'succeeded',
                        'audioSha256': hashlib.sha256(self.wav).hexdigest()}
        self.prepared = {'targetRoom': {'id': 'child', 'scenes': [{'id': 'p1',
            'actions': [{'id': 'line', 'type': 'speech', 'text': 'hello'},
                        {'id': 'new', 'type': 'speech', 'text': 'changed'}]}]},
            'targetPlan': {'teacher': {'tts': {'providerId': 'p', 'modelId': 'm'}, 'voiceId': 'v'}},
            'databaseReceipts': [self.receipt], 'wavs': {'original-request': self.wav},
            'proof': {'segments': [{'sceneId': 'p1', 'actionId': 'line',
                'sourceRequestId': 'original-request', 'audioSha256': self.receipt['audioSha256'],
                'sourceReceiptSha256': digest(self.receipt),
                'textSha256': hashlib.sha256(b'hello').hexdigest()}]}}

    def test_original_receipt_is_preserved_and_only_unchanged_line_is_bound(self):
        room, receipts = bind_inherited_audio(self.prepared, 'http://127.0.0.1:3100')
        self.assertEqual(receipts, [self.receipt])
        self.assertEqual(room['scenes'][0]['actions'][0]['audioId'], 'original-request')
        self.assertTrue(room['scenes'][0]['actions'][0]['audioUrl'].endswith('/child/audio/original-request.wav'))
        self.assertNotIn('audioId', room['scenes'][0]['actions'][1])
        self.assertNotIn('audioId', self.prepared['targetRoom']['scenes'][0]['actions'][0])

    def test_changed_target_text_cannot_inherit(self):
        self.prepared['targetRoom']['scenes'][0]['actions'][0]['text'] = 'different'
        with self.assertRaises(ApiError):
            bind_inherited_audio(self.prepared, 'http://127.0.0.1:3100')

    def test_changed_audio_bytes_cannot_inherit(self):
        self.prepared['wavs']['original-request'] = b'changed'
        with self.assertRaises(ApiError):
            bind_inherited_audio(self.prepared, 'http://127.0.0.1:3100')


class RegistrationTest(PartialBindingTest):
    def setUp(self):
        super().setUp()
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'parent' / 'textbook-preview-audio').mkdir(parents=True)
        self.source = {'id': 'parent', 'stage': {'id': 'parent'}, 'scenes': []}
        self.source_input = {'authoring': {'stageId': 'original'}}
        self.parent = {'preview_key': 'x' * 64, 'classroom_id': 'parent',
                       'classroom_sha256': digest(self.source), 'input_json': self.source_input,
                       'classroom_json': self.source, 'result_json': {'audioReceipts': [self.receipt]},
                       'edition_id': 'e', 'revision_id': 'r', 'node_id': 'n'}
        self.current = {'id': 'original', 'stage': {'id': 'original'}, 'scenes': []}
        self.prepared.update({'identity': {'targetStageSha256': digest(self.current), 'candidateSha256': 's'},
            'parentClassroomSha256': digest(self.source), 'sourceInput': self.source_input,
            'sourceRoom': self.source, 'sourcePlan': {}, 'checkpointReceipts': [self.receipt],
            'targetInput': {'previewKey': 'd' * 64}, 'providerReceipts': {}, 'chain': {},
            'checks': {'issues': ['speech_audio_missing']}})
        self.prepared['targetRoom']['stage'] = {'id': 'child'}
        self.row = None
        test = self
        class Connection:
            def execute(self, sql, params):
                if sql.startswith('SELECT'):
                    return SimpleNamespace(fetchone=lambda: test.parent)
                if sql.startswith('INSERT'):
                    test.row = {'preview_key': params[0], 'classroom_id': params[8],
                                'input_json': json.loads(params[4]), 'classroom_json': json.loads(params[10]),
                                'result_json': json.loads(params[11])}
                    return None
                raise AssertionError(sql)
        class Repository:
            def transaction(self): return nullcontext(Connection())
            def parse(self, v): return v
        class Runtime:
            base_url = 'http://127.0.0.1:3100'
            saved = None
            def get_classroom(self, cid):
                if self.saved is None:
                    raise OpenMaicFullRuntimeError('missing', 'missing', status_code=404)
                return deepcopy(self.saved)
            def save_preview_classroom(self, room): self.saved = deepcopy(room)
        self.service = SimpleNamespace(repository=Repository(), runtime=Runtime(), authoring_output_root=self.root,
            get=lambda key: self.parent if key == self.parent['preview_key'] else self.row,
            summary=lambda row: row, _manifest=lambda *args: {},
            _operator_adoption_classroom=lambda *args: (self.current, None),
            reuse=SimpleNamespace(resolve=lambda *args, **kwargs: {'source': 'new', 'slot': {}},
                                  repository=SimpleNamespace(bind_preview=lambda *args: None,
                                                             lock_edition=lambda *args: None)))
        self.patches = [
            patch('services.textbook_partial_preview_revision.prepare_partial_revision', return_value=self.prepared),
            patch('services.textbook_partial_preview_revision.validate_authoring_candidate', return_value={'sha256': 's'}),
            patch('services.textbook_operator_revision_service.locked', side_effect=lambda *args: nullcontext()),
            patch('services.textbook_partial_audio_inheritance.load_partial_audio', return_value={}),
            patch('services.course_file_store.course_exists', side_effect=lambda p: Path(p).is_file()),
            patch('services.course_file_store.course_bytes', side_effect=lambda p: Path(p).read_bytes()),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def register(self):
        return register_partial_revision(self.service, self.parent['preview_key'], '6',
            {'reason': 'repair', 'budgetReference': 'user authorization'}, self.root,
            expected_preview_key=self.prepared['targetInput']['previewKey'],
            expected_stage_sha256=self.prepared['identity']['targetStageSha256'],
            expected_parent_sha256=self.prepared['parentClassroomSha256'])

    def test_registers_independent_child_with_partial_original_receipt(self):
        row = self.register()
        self.assertEqual(row['classroom_id'], 'child')
        self.assertTrue(row['result_json']['audioPartial'])
        self.assertEqual(row['result_json']['audioReceipts'], [self.receipt])
        self.assertEqual(row['classroom_json']['scenes'][0]['actions'][0]['audioId'], 'original-request')
        self.assertEqual((self.root / 'child/audio/original-request.wav').read_bytes(), self.wav)
        self.assertEqual(self.parent['classroom_json'], self.source)

    def test_existing_different_child_is_never_overwritten(self):
        self.service.runtime.saved = {'id': 'child', 'stage': {'id': 'child'}, 'scenes': []}
        with self.assertRaises(ApiError):
            self.register()
        self.assertEqual(self.service.runtime.saved['scenes'], [])

    def test_changed_dry_run_fence_creates_no_child(self):
        with self.assertRaises(ApiError):
            register_partial_revision(self.service, self.parent['preview_key'], '6',
                {'reason': 'repair', 'budgetReference': 'user authorization'}, self.root,
                expected_preview_key='0' * 64,
                expected_stage_sha256=self.prepared['identity']['targetStageSha256'],
                expected_parent_sha256=self.prepared['parentClassroomSha256'])
        self.assertFalse((self.root / 'child').exists())
        self.assertIsNone(self.service.runtime.saved)

    def test_unknown_save_outcome_is_not_resent(self):
        self.service.runtime.save_preview_classroom = lambda room: (_ for _ in ()).throw(RuntimeError('lost response'))
        with self.assertRaises(RuntimeError):
            self.register()
        with self.assertRaises(ApiError):
            self.register()

    def test_registration_archive_is_accepted_by_real_partial_loader(self):
        from tests import test_textbook_partial_audio_inheritance as fixtures
        from content.textbook_partial_audio_inheritance import partial_declaration
        from content.textbook_preview_audio_contract import new_audio_plan
        f = fixtures.PartialAudioInheritanceTest(methodName='runTest')
        f.setUp()
        f.target_input['partialAudioParent'] = partial_declaration(f.run_verification())
        f.target_input['previewKey'] = digest({k: v for k, v in f.target_input.items() if k != 'previewKey'})
        f.target_plan = new_audio_plan(preview_key=f.target_input['previewKey'],
            classroom_sha256=f.target_input['sourceSha256'], core_sha256=digest(f.target_room), frozen_input=f.target_input)
        proof = f.run_verification()
        self.parent.update(preview_key=f.source_input['previewKey'], classroom_id=f.source_room['id'],
            classroom_sha256=digest(f.source_room), input_json=f.source_input,
            classroom_json=f.source_room, result_json={'audioReceipts': [f.receipt]})
        (self.root / f.source_room['id'] / 'textbook-preview-audio').mkdir(parents=True)
        self.prepared.update(sourceInput=f.source_input, sourceRoom=f.source_room,
            sourcePlan=f.source_plan, databaseReceipts=[f.receipt], checkpointReceipts=[f.checkpoint],
            targetInput=f.target_input, targetRoom=f.target_room, targetPlan=f.target_plan,
            providerReceipts={f.request: f.provider}, proof=proof, wavs={f.request: f.wav},
            chain=f.chain, parentClassroomSha256=digest(f.source_room))
        # Use the real loader and only redirect file storage to this isolated
        # temporary fixture; no runtime, database, or paid provider is touched.
        self.patches[3].stop()
        from services.textbook_partial_audio_inheritance import load_partial_audio
        with patch('services.textbook_partial_audio_inheritance.course_exists', side_effect=lambda p: Path(p).is_file()), \
             patch('services.textbook_partial_audio_inheritance.course_bytes', side_effect=lambda p: Path(p).read_bytes()), \
             patch('services.textbook_partial_audio_inheritance.course_text', side_effect=lambda p: Path(p).read_text()):
            row = self.register()
            folder = self.root / f.target_room['id'] / 'textbook-preview-audio'
            context = load_partial_audio(folder, f.target_plan, frozen=f.target_input)
        self.assertEqual(len(context['segments']), 1)
        self.assertEqual(row['result_json']['audioReceipts'], [f.receipt])


if __name__ == '__main__':
    unittest.main()
