import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from courseware.tools import post_publish


class PostPublicationTest(unittest.TestCase):
    def setUp(self):
        self.content_key = 'a' * 64
        self.room = 'tbpub_' + self.content_key[:24]
        self.room_path = f'{post_publish.CLASSROOMS}/{self.room}'
        self.classroom_bytes = b'{"scenes": []}'
        self.media_bytes = b'test-recording'
        self.media_hash = hashlib.sha256(self.media_bytes).hexdigest()
        self.release = {'contentKey': self.content_key, 'classroomId': self.room, 'sha256': 'b' * 64,
                        'classroomSha256': 'digest'}
        self.inventory = [{'path': f'/api/classroom-media/{self.room}/audio/{self.media_hash}.wav',
                           'sha256': self.media_hash, 'byteSize': len(self.media_bytes)}]
        self.scope = {'scopeKey': 'c' * 64, 'metadata': {'sourceDigest': self.release['sha256']},
                      'bindings': [{'sourcePath': self.room_path + '.json',
                                    'sha256': hashlib.sha256(self.classroom_bytes).hexdigest()},
                                   {'sourcePath': self.room_path + f'/audio/{self.media_hash}.wav',
                                    'sha256': self.media_hash}]}

    def test_waits_for_same_release_hash(self):
        wrong = {**self.scope, 'metadata': {'sourceDigest': 'stale'}}
        registry = Mock()
        registry.find_scopes.side_effect = [[wrong], [wrong, self.scope]]
        sleep = Mock()
        scope = post_publish.wait_for_scope(registry, 'store', self.release, timeout=10,
                                            clock=lambda: 0, sleep=sleep)
        self.assertIs(scope, self.scope)
        sleep.assert_called_once_with(5)
        registry.find_scopes.assert_called_with(storage_id='store', content_key=self.content_key, classroom_id=self.room)

    def test_readback_checks_each_registered_asset_and_does_not_allow_local_fallback(self):
        store = Mock()
        store.read_bytes.side_effect = [self.classroom_bytes, self.media_bytes]
        readback = post_publish.readback(self.scope, self.release, self.inventory, store,
                                         classroom_digest=lambda _: 'digest')
        self.assertEqual(readback['mediaVerifiedCount'], 1)
        store.read_bytes.assert_called_with(
            post_publish.ROOT / self.room_path / f'audio/{self.media_hash}.wav',
            expected_sha256=self.media_hash, expected_bytes=len(self.media_bytes))
        store.read_bytes.side_effect = [self.classroom_bytes, None]
        with self.assertRaisesRegex(ValueError, 'Remote media verification failed'):
            post_publish.readback(self.scope, self.release, self.inventory, store, classroom_digest=lambda _: 'digest')
        store.read_bytes.side_effect = [self.classroom_bytes]
        with self.assertRaisesRegex(ValueError, 'Media absent from exact archive'):
            post_publish.readback({**self.scope, 'bindings': self.scope['bindings'][:1]}, self.release,
                                  self.inventory, store, classroom_digest=lambda _: 'digest')

    def test_ledger_merges_timings_for_one_owner_and_rejects_conflicting_release(self):
        identity = {'editionId': 'edition', 'revisionId': 'directory', 'nodeId': 'lesson'}
        ledger = {'other': 'kept', 'currentGoalBatch': {'active': {'lane': {
            **identity, 'owner': '/root/lane', 'slug': 'old', 'sourceSlug': 'new',
            'timingsSeconds': {'officialReview': 20}
        }}}}
        receipt = {**self.release, 'releaseSha256': self.release['sha256'], 'verifiedAt': 'timestamp',
                   'receiptPath': 'receipt.json', 'timingsSeconds': {'studentPlayback': 7}}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'production-run.json'
            path.write_text(json.dumps(ledger))
            def complete(document):
                post_publish.record_completion(document, 'lane', identity, 'new', receipt)
            post_publish.update_ledger(path, complete)
            result = post_publish.read_json(path)
            assignment = result['currentGoalBatch']['active']['lane']
            self.assertEqual(result['other'], 'kept')
            self.assertEqual(assignment['timingsSeconds'], {'officialReview': 20, 'studentPlayback': 7})
            self.assertEqual(assignment['slowestStep'], 'officialReview')
            self.assertEqual(assignment['localCleanup'], 'awaiting_independent_second_backup')
            with self.assertRaisesRegex(ValueError, 'Ledger release changed'):
                post_publish.record_completion(result, 'lane', identity, 'new', {**receipt, 'contentKey': 'new-key'})
            with self.assertRaisesRegex(ValueError, 'Ledger lesson mismatch'):
                post_publish.record_completion(result, 'lane', identity, 'old', receipt)

    def test_portable_restore_rechecks_the_release_from_the_extracted_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            package = root / 'package'
            package.mkdir()
            (package / 'body.json').write_bytes(self.classroom_bytes)
            download, restore_workspace = root / 'download', root / 'work'
            restore_workspace.mkdir()
            plan = post_publish.courseware_backup.build_plan(root, ['package'])
            local = post_publish.courseware_backup.create_backup(plan, download)
            receipt = {'archiveSha256': local['sha256'], 'releaseSha256': self.release['sha256']}

            def check_release(restored):
                self.assertEqual(restored, restore_workspace / 'restored/package')
                self.assertEqual((restored / 'body.json').read_bytes(), self.classroom_bytes)
                return {'ok': True, 'prepared': {'release': self.release}}

            with patch.object(post_publish, 'ROOT', root):
                result = post_publish.verify_restore(download, restore_workspace, receipt, package, check_release)
            self.assertTrue(result['portableRestore'])
            self.assertEqual(result['restoredFiles'], 1)

    def test_primary_backup_resume_preserves_exact_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            package = root / 'package'
            package.mkdir()
            (package / 'body.json').write_bytes(self.classroom_bytes)
            backup = root / 'backup'
            roots = ['package']
            local = post_publish.courseware_backup.create_backup(
                post_publish.courseware_backup.build_plan(root, roots), backup)
            raw = (backup / 'backup-receipt.json').read_bytes()
            remote = {'schemaVersion': 'mira.courseware-backup.remote.v1', 'complete': True,
                      'archiveSha256': local['sha256'], 'files': [
                          {'path': local['archiveFile'], 'sha256': local['sha256'], 'byteSize': local['byteSize']},
                          {'path': 'backup-receipt.json', 'sha256': hashlib.sha256(raw).hexdigest(),
                           'byteSize': len(raw)}]}
            proof = backup / 'remote-verification.json'
            proof.write_text(json.dumps(remote))
            with patch.object(post_publish, 'command_json') as command:
                original = proof.read_bytes()
                self.assertEqual(post_publish.save_primary_backup(backup, roots)['files'], 2)
                self.assertEqual(proof.read_bytes(), original)

                remote['files'][1]['sha256'] = 'f' * 64
                proof.write_text(json.dumps(remote))
                with self.assertRaisesRegex(ValueError, 'does not match the local archive'):
                    post_publish.save_primary_backup(backup, roots)
                command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
