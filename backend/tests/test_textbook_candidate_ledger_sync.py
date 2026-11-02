from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from content.textbook_catalog import canonical, digest
from content.textbook_authoring_candidate import CANDIDATE_SCHEMA, V4_JOB_SCHEMA
from core.course_storage_config import CourseStorageConfig
from core.errors import ApiError
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for
from services.course_file_writer import CourseFileWriteError
from services.textbook_candidate_ledger_sync import CandidateLedgerWriter, verify_transition
from tests.test_course_storage_repository import _Database


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class CandidateTransitionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        (self.job / 'reviewed-patches').mkdir()
        self.sid, self.stage, self.frozen_sha = 'session-1', 'stage-1', 'a' * 64
        self.before = {'id': 'scene-p10', 'stageId': self.stage, 'order': 1, 'type': 'interactive',
                       'title': '写字', 'content': {'html': '<p>old</p>'},
                       'actions': [{'id': 'cue', 'type': 'speech', 'text': 'old'}]}
        self.after = {**self.before, 'content': {'html': '<p>new</p>'},
                      'actions': [{'id': 'cue', 'type': 'speech', 'text': 'new'}]}
        self.contract_ref = {'sha256': 'b' * 64}
        self.frozen = {'schemaVersion': V4_JOB_SCHEMA, 'authorDispatchContract': self.contract_ref}
        self.contract = {'pagePlan': [{'page': 1, 'type': 'interactive', 'title': '写字'}]}
        self.target = {'id': self.stage, 'stage': {'id': self.stage}, 'scenes': [self.after]}
        def ledger(scene):
            text = canonical(scene)
            body = {'schemaVersion': CANDIDATE_SCHEMA, 'sessionId': self.sid, 'stageId': self.stage,
                    'frozenContract': self.contract_ref, 'status': 'author_candidate',
                    'verification': 'static_contract_only_not_play_or_semantic_review',
                    'assetBindings': [], 'bindingHistory': [],
                    'scenes': [{'sceneId': scene['id'], 'order': 1, 'sha256': sha(text.encode()),
                                'canonicalJson': text, 'contractSha256': self.contract_ref['sha256']}]}
            return {**body, 'sha256': digest(body)}
        self.old, self.new = ledger(self.before), ledger(self.after)
        ops = {'target': '/scenes/scene-p10', 'expectedSceneSha256': digest(self.before), 'ops': [
            {'op': 'str_replace', 'path': '/content/html', 'oldText': 'old', 'newText': 'new'},
            {'op': 'set', 'path': '/actions', 'value': self.after['actions']}]}
        raw = json.dumps(ops, separators=(',', ':')).encode()
        key = sha(raw)
        folder = self.job / 'reviewed-patches' / key
        folder.mkdir()
        data = {'sessionId': self.sid, 'stageId': self.stage, 'sceneId': 'scene-p10',
                'beforeSceneSha256': digest(self.before), 'afterSceneSha256': digest(self.after),
                'opsSha256': key, 'frozenFileSha256': self.frozen_sha}
        self.events = [{'id': 11, 'type': 'mira_textbook_reviewed_patch', 'data': data}]
        (folder / 'ops.json').write_bytes(raw)
        (folder / 'before.json').write_text(canonical(self.before))
        (folder / 'after.json').write_text(canonical(self.after))
        (folder / 'receipt.json').write_text(json.dumps({'status': 'applied', 'eventSeq': 11, **data}))

    def verify(self):
        with patch('services.textbook_candidate_ledger_sync._image_coverage'), \
             patch('services.textbook_candidate_ledger_sync._questions'):
            return verify_transition(old=self.old, new=self.new, target=self.target, session=self.sid,
                stage=self.stage, frozen=self.frozen, contract=self.contract, job=self.job,
                events=self.events, frozen_sha=self.frozen_sha, classroom_directory=self.job)

    def test_reviewed_chain_and_exact_scene_pass(self):
        self.assertEqual(self.verify()['patchCount'], 1)

    def test_changed_binding_even_if_resealed_fails(self):
        self.new['assetBindings'] = [{'assetKey': 'unauthorized'}]
        self.new['sha256'] = digest({k: v for k, v in self.new.items() if k != 'sha256'})
        with self.assertRaisesRegex(ValueError, 'identity_changed'):
            self.verify()

    def test_changed_scene_or_unverified_event_fails(self):
        self.target['scenes'][0]['content']['html'] = '<p>different</p>'
        with self.assertRaises((ApiError, ValueError)):
            self.verify()
        self.target['scenes'][0]['content']['html'] = '<p>new</p>'
        self.events[0]['data']['sessionId'] = 'other-owner'
        with self.assertRaises(ApiError):
            self.verify()

    def test_tampered_seal_or_frozen_contract_fails(self):
        self.new['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'seal_invalid'):
            self.verify()
        self.new['sha256'] = digest({k: v for k, v in self.new.items() if k != 'sha256'})
        self.frozen['authorDispatchContract'] = {'sha256': 'c' * 64}
        with self.assertRaisesRegex(ValueError, 'seal_invalid'):
            self.verify()


class CandidateCasTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = _Database()
        self.addCleanup(self.db.raw.close)
        self.db.raw.create_function('JSON_UNQUOTE', 1, lambda v: v)
        self.db.raw.create_function('JSON_CONTAINS', 2, lambda data, query: int(any(
            all(item.get(k) == v for k, v in json.loads(query).items()) for item in json.loads(data))))
        self.db.raw.executescript('''CREATE TABLE learning_textbook_course_previews(preview_key TEXT,classroom_id TEXT,status TEXT);
            CREATE TABLE learning_textbook_course_builds(content_key TEXT,status TEXT,input_json TEXT);''')
        self.repo = CourseStorageRepository(self.db)
        self.config = CourseStorageConfig(mode='registry', endpoint='http://storage.invalid:9000', bucket='study')
        self.storage = storage_id_for(self.config.endpoint, self.config.bucket)
        self.path = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-1/textbook-authoring-candidate.json'
        local = self.root / self.path
        local.parent.mkdir(parents=True)
        self.old = b'{"test":"old"}'
        self.new = b'{"test":"new"}'
        local.write_bytes(self.new)
        self.meta = {'scopeKey': 'a' * 64, 'previewKey': 'b' * 64, 'classroomId': 'parent',
            'sourceKind': 'textbook_preview', 'courseId': 'textbook-preview:' + 'b' * 64,
            'courseVersion': 'v1', 'status': 'generated_saved', 'storageDirectory': '语文/测试'}
        self.db.raw.execute('INSERT INTO learning_textbook_course_previews VALUES(?,?,?)', ('b' * 64, 'parent', 'review_required'))
        self.repo.register_scope(self.meta, [{'sourcePath': self.path, 'sha256': sha(self.old),
            'byteSize': len(self.old), 'mimeType': 'application/json',
            'locator': {'kind': 'object', 'objectKey': 'old.json', 'etag': '"old"'}}], self.storage)
        self.writer = CandidateLedgerWriter(preview_service=Mock(), parent_key='b' * 64,
            classroom_directory=self.root / 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms',
            config=self.config, repository=self.repo)
        self.writer.root = self.root
        self.writer._verify = Mock(return_value={'chainSha256': 'c' * 64, 'patchCount': 1})
        self.objects = {sha(self.old): self.old}
        self.writer._read = Mock(side_effect=lambda path, expected: self.objects[expected])
        self.writer.uploader = Mock()
        def upload(**kw):
            self.objects[sha(kw['raw'])] = kw['raw']
            return {'kind': 'object', 'objectKey': kw['object_key'], 'etag': '"new"'}
        self.writer.uploader.upload.side_effect = upload

    def test_dry_run_has_no_upload_or_head_change(self):
        value = self.writer.dry_run(self.path, expected_old_sha256=sha(self.old), expected_new_sha256=sha(self.new))
        self.assertEqual(value['status'], 'validated_not_written')
        self.writer.uploader.upload.assert_not_called()
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(self.old))

    def test_cas_preserves_old_version_and_reads_back_new(self):
        result = self.writer.synchronize(self.path, expected_old_sha256=sha(self.old), expected_new_sha256=sha(self.new))
        self.assertEqual(result['remoteByteSha256'], sha(self.new))
        self.assertEqual(self.repo.resolve(self.path, self.storage, sha(self.old))['sha256'], sha(self.old))
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(self.new))
        self.assertGreaterEqual(self.writer._verify.call_count, 4)
        self.writer.uploader.upload.assert_called_once()

    def test_bad_expected_head_or_changed_candidate_does_not_upload(self):
        with self.assertRaises((CourseFileWriteError, KeyError)):
            self.writer.dry_run(self.path, expected_old_sha256='f' * 64, expected_new_sha256=sha(self.new))
        with self.assertRaisesRegex(CourseFileWriteError, 'local_changed'):
            self.writer.dry_run(self.path, expected_old_sha256=sha(self.old), expected_new_sha256='f' * 64)
        self.writer.uploader.upload.assert_not_called()

    def test_late_verification_failure_keeps_old_head(self):
        self.writer._verify.side_effect = [{'chainSha256': 'c' * 64}] * 3 + [ValueError('stage changed')]
        with self.assertRaisesRegex(CourseFileWriteError, 'verification_failed'):
            self.writer.synchronize(self.path, expected_old_sha256=sha(self.old), expected_new_sha256=sha(self.new))
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(self.old))
        self.assertIsNone(self.repo.resolve(self.path, self.storage, sha(self.new)))

    def test_head_advanced_after_upload_is_not_reported_as_success(self):
        winner = b'{"test":"concurrent"}'
        self.objects[sha(winner)] = winner
        def read(path, expected):
            if expected == sha(self.new):
                self.repo.compare_and_activate({**self.meta, 'scopeKey': 'd' * 64}, [{
                    'sourcePath': self.path, 'sha256': sha(winner), 'byteSize': len(winner),
                    'mimeType': 'application/json',
                    'locator': {'kind': 'object', 'objectKey': 'winner.json', 'etag': '"winner"'}}],
                    self.storage, expected_old_sha=sha(self.new))
            return self.objects[expected]
        self.writer._read.side_effect = read
        with self.assertRaisesRegex(CourseFileWriteError, 'head_conflict'):
            self.writer.synchronize(self.path, expected_old_sha256=sha(self.old), expected_new_sha256=sha(self.new))
        self.assertEqual(self.repo.resolve(self.path, self.storage)['sha256'], sha(winner))


if __name__ == '__main__':
    unittest.main()
