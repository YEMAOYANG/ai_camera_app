"""One human-approved reupload; isolated DB, photos and fake providers only."""
import sqlite3
import unittest
from unittest.mock import Mock

from core.errors import ApiError
from services.homework_assets import transformed_image
from services.homework_reupload_authorization import APPROVAL, CONTRACT, MARKER, TTL, USE_MARKER, authorize_reupload, reupload_grant
from services.homework_service import parsed
from tests import test_homework_analysis as fixtures
from tests import test_homework_recognition_response_recovery as recovery_fixtures


class HomeworkReuploadTest(unittest.TestCase):
    create = fixtures.HomeworkTest.create
    upload = fixtures.HomeworkTest.upload
    error = fixtures.HomeworkTest.error

    def setUp(self):
        recovery_fixtures.ResponseRecoveryTest.setUp(self)
        self.approved_at = self.clock() + 10
        self.service.clock = lambda: self.approved_at + 20

    def authorize(self, *, execute=True, approval=APPROVAL, approved_at=None):
        with self.db.transaction() as conn:
            return authorize_reupload(self.service, conn, self.scope,
                approved_at=self.approved_at if approved_at is None else approved_at,
                execute=execute, approval_text=approval)

    def new_upload(self, key='new-upload', *, token='parent-a', child='child-a', both=True):
        submission = self.create(key, token=token, child=child)
        for index, old in enumerate(self.old_pages[:2 if both else 1]):
            submission = self.service.upload(token, submission['id'],
                {'revision': submission['revision'], 'idempotencyKey': f'photo-{index}'},
                self.old_images[old['storage_key']])['submission']
        return submission

    def enqueue(self, submission, token='parent-a'):
        self.service.analyze(token, submission['id'], {'revision': submission['revision']})

    def old_unchanged(self):
        recovery_fixtures.ResponseRecoveryTest.snapshot_unchanged(self)

    def counts(self, marker=MARKER):
        return self.db.execute('SELECT COUNT(*) n FROM homework_actions WHERE item_id=?', (marker,)).fetchone()['n']

    def claim(self, submission, page_index=0):
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (submission['id'],)).fetchone()
        job = self.db.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=?', (row['id'], row['revision'])).fetchone()
        page = self.service.repository.pages(self.db, row['id'])[page_index]
        image, _ = transformed_image(self.store.read(page['storage_key']), page['rotation'], parsed(page['crop_json']))
        base = self.service._recognition_repair_input(page)['baseRequestSha256']
        with self.db.transaction() as conn:
            return reupload_grant(self.service, conn, job, row, page, image, base)

    def test_default_preflight_is_read_only_and_never_queues_the_old_task(self):
        before = self.db.raw.total_changes
        writes = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}
        self.db.raw.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in writes else sqlite3.SQLITE_OK)
        try:
            result = authorize_reupload(self.service, self.db, self.scope, approved_at=self.approved_at)
        finally:
            self.db.raw.set_authorizer(None)
        self.assertFalse(result['authorized'])
        self.assertFalse(result['oldTaskQueued'])
        self.assertEqual(result['maximumNewVisionCalls'], 1)
        self.assertEqual(self.db.raw.total_changes, before)
        self.assertEqual(self.counts(), 0)
        self.provider.analyze_image.assert_not_called()
        self.transport.assert_not_called()
        self.old_unchanged()

    def test_execution_records_only_the_new_explicit_approval_once(self):
        for wrong in (None, '允许重新分析一次', '允许这份两页作业重新分析一次'):
            self.error('homework_repair_approval_required', lambda: self.authorize(approval=wrong))
        first = self.authorize()
        again = self.authorize()
        self.assertTrue(first['authorized'])
        self.assertTrue(again['alreadyAuthorized'])
        self.assertEqual(first['authorizationId'], again['authorizationId'])
        self.assertEqual(first['expiresAt'], again['expiresAt'])
        self.assertEqual(self.counts(), 1)
        self.assertEqual(self.counts(USE_MARKER), 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'], 1)
        self.assertFalse(self.service.process_next()['processed'])
        self.provider.analyze_image.assert_not_called()
        self.old_unchanged()

    def test_reuploaded_same_photos_override_only_the_one_old_unknown_call(self):
        authorization = self.authorize()
        submission = self.new_upload()
        self.enqueue(submission)
        self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        calls = self.db.execute('SELECT * FROM homework_provider_calls WHERE submission_id=?', (submission['id'],)).fetchall()
        approved = [call for call in calls if parsed(call['receipt_json']).get('operatorRepairAuthorizationId')]
        self.assertEqual(len(approved), 1)
        self.assertEqual(parsed(approved[0]['receipt_json'])['operatorRepairAuthorizationId'], authorization['authorizationId'])
        self.assertEqual(parsed(approved[0]['receipt_json'])['wireContract'], CONTRACT)
        self.assertEqual(parsed(approved[0]['receipt_json'])['maximumNewVisionCalls'], 1)
        self.assertNotEqual(approved[0]['request_sha256'], self.old_call['request_sha256'])
        normal = next(call for call in calls if call not in approved)
        normal_page = next(page for page in self.service.repository.pages(self.db, submission['id']) if page['id'] == normal['page_id'])
        self.assertEqual(normal['request_sha256'], self.service._recognition_repair_input(normal_page)['baseRequestSha256'])
        self.assertEqual(self.counts(USE_MARKER), 1)
        self.assertEqual(self.service.get('parent-a', submission['id'])['submission']['status'], 'ready')
        self.old_unchanged()

    def test_a_third_same_photo_submission_has_no_remaining_repeat_credit(self):
        self.authorize()
        second = self.new_upload('second')
        self.enqueue(second)
        self.assertTrue(self.service.process_next()['ok'])
        third = self.new_upload('third')
        self.enqueue(third)
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        self.assertEqual(self.counts(USE_MARKER), 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=?', (third['id'],)).fetchone()['n'], 0)
        self.old_unchanged()

    def test_deleting_new_work_cannot_restore_the_credit_on_the_old_work(self):
        self.authorize()
        second = self.new_upload('second')
        self.enqueue(second)
        self.provider.analyze_image.side_effect = TimeoutError('isolated unknown after credit claim')
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.service.delete('parent-a', second['id'], {'revision': second['revision']})
        self.assertEqual(self.counts(USE_MARKER), 1)
        saved_use = self.db.execute('SELECT * FROM homework_actions WHERE item_id=?', (USE_MARKER,)).fetchone()
        self.assertEqual(saved_use['submission_id'], self.submission['id'])
        third = self.new_upload('third')
        self.enqueue(third)
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count, 1)
        self.old_unchanged()

    def test_preexisting_submission_cannot_spend_the_new_human_approval(self):
        self.service.clock = self.clock
        preexisting = self.new_upload('before-approval')
        self.service.clock = lambda: self.approved_at + 20
        self.authorize()
        self.enqueue(preexisting)
        self.assertEqual(self.service.process_next()['error'], 'homework_reupload_authorization_invalid')
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.counts(USE_MARKER), 0)
        self.old_unchanged()

    def test_approval_cannot_be_issued_for_future_or_expired_human_timestamp(self):
        for approved_at in (self.service.clock() + 1, self.service.clock() - TTL, 'today', True):
            self.error('homework_reupload_authorization_invalid', lambda: self.authorize(approved_at=approved_at))
        self.assertEqual(self.counts(), 0)
        self.provider.analyze_image.assert_not_called()
        self.old_unchanged()

    def test_expired_unused_approval_does_not_dispatch_or_claim_credit(self):
        self.authorize()
        self.service.clock = lambda: self.approved_at + TTL
        second = self.new_upload()
        self.enqueue(second)
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.counts(USE_MARKER), 0)
        self.provider.analyze_image.assert_not_called()
        self.old_unchanged()

    def test_scope_family_phone_and_child_mismatch_cannot_record_an_approval(self):
        for key, value in [('phone', '19900009302'), ('familyId', 'family-b'), ('childId', 'child-b')]:
            old = self.scope[key]; self.scope[key] = value
            with self.subTest(key=key), self.assertRaises(ApiError): self.authorize()
            self.scope[key] = old
        self.assertEqual(self.counts(), 0)
        self.provider.analyze_image.assert_not_called()

    def test_another_family_or_child_cannot_claim_this_approval(self):
        self.authorize()
        self.db.execute('INSERT INTO children VALUES (?,?,?,?)', ('child-c', 'family-a', 'primary_1', 1)); self.db.raw.commit()
        for key, token, child in [('other-family', 'parent-b', 'child-b'), ('other-child', 'parent-a', 'child-c')]:
            submission = self.new_upload(key, token=token, child=child)
            self.enqueue(submission, token)
            self.assertIsNone(self.claim(submission))
        self.assertEqual(self.counts(USE_MARKER), 0)
        self.provider.analyze_image.assert_not_called()
        self.old_unchanged()

    def test_changing_any_old_input_or_receipt_after_approval_blocks_new_dispatch(self):
        self.authorize()
        second = self.new_upload()
        self.db.execute('UPDATE homework_pages SET rotation=90 WHERE id=?', (self.old_pages[1]['id'],)); self.db.raw.commit()
        self.enqueue(second)
        self.assertEqual(self.service.process_next()['error'], 'homework_reupload_authorization_invalid')
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.counts(USE_MARKER), 0)
        self.old_unchanged()

    def test_changing_old_call_snapshot_cannot_claim_a_reupload(self):
        self.authorize()
        second = self.new_upload()
        self.db.execute("UPDATE homework_provider_calls SET error_code='changed' WHERE id=?", (self.old_call['id'],)); self.db.raw.commit()
        self.enqueue(second)
        self.assertEqual(self.service.process_next()['error'], 'homework_reupload_authorization_invalid')
        self.provider.analyze_image.assert_not_called()

    def test_changed_json_or_timeout_contract_blocks_same_photo_before_any_call(self):
        self.authorize()
        for index, (attribute, changed) in enumerate([('json_output', True), ('timeout_seconds', 121)]):
            second = self.new_upload(f'changed-contract-{index}')
            original = getattr(self.provider, attribute)
            setattr(self.provider, attribute, changed)
            self.enqueue(second)
            self.assertEqual(self.service.process_next()['error'], 'homework_reupload_authorization_invalid')
            self.assertEqual(self.counts(USE_MARKER), 0)
            self.provider.analyze_image.assert_not_called()
            setattr(self.provider, attribute, original)
        self.old_unchanged()

    def test_ambiguous_new_request_is_not_repeated_after_worker_crash(self):
        self.authorize()
        second = self.new_upload()
        self.enqueue(second)
        self.provider.analyze_image.side_effect = TimeoutError('isolated ambiguous new request')
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        job = self.db.execute('SELECT * FROM homework_jobs WHERE submission_id=?', (second['id'],)).fetchone()
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old' WHERE id=?", (job['id'],)); self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count, 1)
        self.assertEqual(self.counts(USE_MARKER), 1)
        self.old_unchanged()

    def test_worker_reuses_a_saved_success_after_crash_without_second_payment(self):
        self.authorize()
        second = self.new_upload()
        self.enqueue(second)
        save = self.service._save_items
        self.service._save_items = Mock(side_effect=ApiError('isolated_interruption', 'test interruption', 409))
        self.assertEqual(self.service.process_next()['error'], 'isolated_interruption')
        self.service._save_items = save
        job = self.db.execute('SELECT * FROM homework_jobs WHERE submission_id=?', (second['id'],)).fetchone()
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old' WHERE id=?", (job['id'],)); self.db.raw.commit()
        self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        self.assertEqual(self.counts(USE_MARKER), 1)
        self.old_unchanged()

    def test_new_revision_cannot_use_a_previous_revision_claim(self):
        self.authorize()
        second = self.new_upload()
        self.enqueue(second)
        self.assertIsNotNone(self.claim(second))
        edits = [{'id': page['id'], 'rotation': page['rotation'], 'crop': parsed(page['crop_json'])}
                 for page in self.service.repository.pages(self.db, second['id'])]
        changed = self.service.update_pages('parent-a', second['id'], {'revision': second['revision'], 'pages': edits})['submission']
        self.enqueue(changed)
        self.assertEqual(self.service.process_next()['error'], 'homework_reupload_authorization_invalid')
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.counts(USE_MARKER), 1)
        self.old_unchanged()

    def test_no_permission_never_overrides_same_child_unknown_deduplication(self):
        second = self.new_upload()
        self.enqueue(second)
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.counts(USE_MARKER), 0)
        self.old_unchanged()


if __name__ == '__main__':
    unittest.main()
