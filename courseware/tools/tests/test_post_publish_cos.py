import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from courseware.tools import post_publish


class TestCosRecovery(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=os.environ['MIRA_TASK_TMPDIR'])
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.backup = self.root / 'backup'
        self.backup.mkdir()
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        self.package = self.root / 'package'
        self.recovery = {'archiveSha256': 'archive', 'restoredFiles': 10, 'portableRestore': True,
                         'restoredReleaseSha256': 'release'}
        self.primary = {'contentKey': 'key', 'classroomId': 'classroom', 'releaseSha256': 'release',
                        'recovery': self.recovery}
        media = {'path': 'archive.zip', 'sha256': 'archive', 'byteSize': 12, 'objectKey': 'backup/archive.zip'}
        source = {'storage': {'endpoint': 'http://minio'}, 'archiveSha256': 'archive',
                  'complete': True, 'files': [media]}
        self.source_path = self.backup / 'remote-verification.json'
        self.source_path.write_text(json.dumps(source))
        cos = {**source, 'storage': {'endpoint': 'https://cos'}, 'files': [{**media, 'versionId': 'v1'}]}
        self.transfer = {'uploaded': cos, 'downloaded': cos}
        self.receipt_path = self.backup / 'post-publish-cos-receipt.json'
        self.current = Mock()

    def verify(self):
        return post_publish.verify_cos_recovery(self.backup, self.workspace, self.primary,
                                                self.package, Mock(), self.current)

    def test_success_and_resume_preserve_primary_receipt(self):
        primary_bytes = self.source_path.read_bytes()
        with patch.object(post_publish, 'ROOT', self.root), \
                patch.object(shutil, 'disk_usage', return_value=Mock(free=5 * 1024**3)), \
                patch.object(post_publish, 'command_json', return_value=self.transfer) as transfer, \
                patch.object(post_publish, 'verify_restore', return_value=self.recovery) as restore:
            receipt = self.verify()
            self.assertEqual(receipt['recovery'], self.recovery)
            self.assertEqual(self.verify(), receipt)
            transfer.assert_called_once_with(
                'node', 'courseware/tools/store_backup.mjs', 'mirror-cos',
                '--backup', str(self.backup), '--workspace', str(self.workspace / 'cos'),
                timeout=post_publish.COS_TRANSFER_TIMEOUT_SECONDS)
            restore.assert_called_once()
            self.assertEqual(self.current.call_count, 2)
        self.assertEqual(self.source_path.read_bytes(), primary_bytes)

    def test_inexact_cos_restore_leaves_no_completion_receipt(self):
        with patch.object(post_publish, 'ROOT', self.root), \
                patch.object(shutil, 'disk_usage', return_value=Mock(free=5 * 1024**3)), \
                patch.object(post_publish, 'command_json', return_value=self.transfer), \
                patch.object(post_publish, 'verify_restore',
                             return_value={**self.recovery, 'restoredReleaseSha256': 'wrong'}):
            with self.assertRaisesRegex(ValueError, 'differs from the primary'):
                self.verify()
        self.assertFalse(self.receipt_path.exists())
        self.current.assert_not_called()
