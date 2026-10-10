"""Operator boundaries, using isolated fixtures and no provider HTTP."""
import json
from pathlib import Path
import stat
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from scripts import recover_tencent_saved_homework as operator
from tests import test_homework_tencent_grading as fixtures


class SavedHomeworkRecoveryOperatorTest(unittest.TestCase):
    setUp = fixtures.TencentPipelineTest.setUp
    create = fixtures.TencentPipelineTest.create
    upload = fixtures.TencentPipelineTest.upload
    queued = fixtures.TencentPipelineTest.queued
    phone = '13800000000'

    def prepared(self):
        self.db.execute('CREATE TABLE users (phone TEXT, family_id TEXT)')
        self.db.execute('INSERT INTO users VALUES (?,?)', (self.phone, 'family-a'))
        submission = self.queued('operator-recovery')
        self.service.process_next()  # fixture submit has a durable JobId
        self.db.execute('UPDATE homework_jobs SET status=? WHERE submission_id=?', ('failed', submission['id']))
        self.db.execute('UPDATE homework_submissions SET status=? WHERE id=?', ('failed', submission['id']))
        self.db.raw.commit()
        return submission

    def invoke(self, submission, *, execute=False, database='mysql://fixture@127.0.0.1:3306/ai_camera_app_dev', revision=None):
        config = SimpleNamespace(to_flask_config=lambda: {'DATABASE_URL': database})
        with patch.object(operator, 'load_dotenv'), patch.object(operator, 'validate_flask_config'), \
                patch.object(operator.AppConfig, 'from_env', return_value=config), \
                patch.object(operator, 'homework_service', return_value=self.service), \
                patch.object(operator, 'ROOT', Path(self.tmp.name)):
            return operator.recover(self.phone, submission['id'], submission['revision'] if revision is None else revision, execute=execute)

    def test_preflight_does_not_change_rows_or_make_queries(self):
        submission = self.prepared()
        before = dict(self.db.execute('SELECT * FROM homework_submissions').fetchone())
        result = self.invoke(submission)
        self.assertTrue(result['resumable'])
        self.assertFalse(result['executed'])
        self.assertEqual(before, dict(self.db.execute('SELECT * FROM homework_submissions').fetchone()))
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.tencent.describe_question.assert_not_called()
        self.assertFalse(list(Path(self.tmp.name).glob('data/homework/tencent-recovery/*/*.json')))

    def test_execute_saves_private_snapshot_before_same_job_requeue(self):
        submission = self.prepared()
        call = dict(self.db.execute('SELECT * FROM homework_provider_calls').fetchone())
        result = self.invoke(submission, execute=True)
        self.assertTrue(result['resumed'])
        backup, = Path(self.tmp.name).glob('data/homework/tencent-recovery/*/*.before.json')
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(backup.parent.stat().st_mode), 0o700)
        saved = json.loads(backup.read_text())
        self.assertEqual(saved['submission']['status'], 'failed')
        self.assertEqual(saved['homework_provider_calls'][0]['id'], call['id'])
        self.assertEqual(saved['homework_provider_calls'][0]['request_sha256'], call['request_sha256'])
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'], 'queued')
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.tencent.describe_question.assert_not_called()

    def test_snapshot_failure_rolls_back_and_never_requeues(self):
        submission = self.prepared()
        with patch.object(operator, 'private_snapshot', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.invoke(submission, execute=True)
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'], 'failed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_actions WHERE item_id=?', ('__tencent_local_repair__',)).fetchone()['n'], 0)

    def test_wrong_database_revision_and_owner_refuse_without_backup(self):
        submission = self.prepared()
        for database in ('mysql://fixture@127.0.0.1:3306/production', 'mysql://fixture@remote.example:3306/ai_camera_app_dev'):
            with self.assertRaises(operator.SafetyStop):
                self.invoke(submission, execute=True, database=database)
        with self.assertRaises(operator.SafetyStop):
            self.invoke(submission, execute=True, revision=submission['revision'] + 1)
        self.db.execute('UPDATE users SET family_id=?', ('family-b',)); self.db.raw.commit()
        with self.assertRaises(operator.ApiError):
            self.invoke(submission, execute=True)
        self.assertFalse(list(Path(self.tmp.name).glob('data/homework/tencent-recovery/*/*.json')))

    def test_missing_saved_submit_refuses_without_paid_replay(self):
        submission = self.prepared()
        call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        key = json.loads(call['receipt_json'])['requestJournalKey']
        self.store.delete(key)
        result = self.invoke(submission, execute=True)
        self.assertFalse(result['resumable'])
        self.assertFalse(result['executed'])
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.tencent.describe_question.assert_not_called()
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
