"""Bounded two-page recovery: isolated files/DB and fake AI transports only."""
from contextlib import redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw
from core.errors import ApiError
from integrations.ai.kimi_vision_provider import AiVisionResponse, OpenAICompatibleVisionProvider
from services.homework_assets import transformed_image
from services.homework_recognition_recovery import APPROVAL_TEXT, ITEM_MARKER, TTL_MS, WIRE_CONTRACT, authorize_recovery, recognition_recovery_grant
from services.homework_service import canonical, digest, parsed
from tests import test_homework_analysis as fixtures


class ResponseRecoveryTest(unittest.TestCase):
    create = fixtures.HomeworkTest.create
    upload = fixtures.HomeworkTest.upload
    error = fixtures.HomeworkTest.error

    def setUp(self):
        fixtures.HomeworkTest.setUp(self)
        self.db.execute('CREATE TABLE users (id TEXT PRIMARY KEY,phone TEXT,family_id TEXT)')
        self.db.execute('INSERT INTO users VALUES (?,?,?)', ('parent-a', '19900009301', 'family-a'))
        self.db.raw.commit()
        self.provider = OpenAICompatibleVisionProvider(provider_name='qwen', model_name='fixture-vision',
            api_key='isolated-test-only', base_url='https://example.invalid/v1', max_bytes=8388608,
            max_image_dimension=3200, capture_received_response=True)
        self.provider.analyze_image = Mock(side_effect=TimeoutError('simulated unknown call'))
        self.service.provider = self.provider
        first = self.upload(self.create())
        second = Image.open(io.BytesIO(fixtures.picture())).convert('RGB')
        ImageDraw.Draw(second).rectangle((100, 930, 600, 945), fill='black')
        photo = io.BytesIO(); second.save(photo, format='PNG')
        self.submission = self.upload(first, key='page-two', body=photo.getvalue())
        self.service.analyze('parent-a', self.submission['id'], {'revision': self.submission['revision']})
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.old_call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        self.old_job = self.db.execute('SELECT * FROM homework_jobs').fetchone()
        self.old_pages = self.service.repository.pages(self.db, self.submission['id'])
        self.old_images = {page['storage_key']: self.store.read(page['storage_key']) for page in self.old_pages}
        self.scope = {'phone': '19900009301', 'familyId': 'family-a', 'childId': 'child-a',
            'submissionId': self.submission['id'], 'expectedRevision': self.submission['revision'],
            'unknownCallId': self.old_call['id']}
        self.provider.analyze_image.reset_mock()
        self.provider.analyze_image.side_effect = lambda **kw: AiVisionResponse(
            json.dumps({'pageReadable': True, 'items': [self.raw]}), 'qwen', 'fixture-vision', finish_reason='stop')

    def authorize(self, **kwargs):
        with self.db.transaction() as conn:
            return authorize_recovery(self.service, conn, self.scope, execute=True, approval_text=APPROVAL_TEXT, **kwargs)

    def snapshot_unchanged(self):
        self.assertEqual(self.db.execute('SELECT * FROM homework_provider_calls WHERE id=?', (self.old_call['id'],)).fetchone(), self.old_call)
        self.assertEqual(self.db.execute('SELECT * FROM homework_jobs WHERE id=?', (self.old_job['id'],)).fetchone(), self.old_job)
        for storage_key, original in self.old_images.items():
            self.assertEqual(self.store.read(storage_key), original)

    def grant(self, page_index=0):
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (self.submission['id'],)).fetchone()
        job = self.db.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=?', (row['id'], row['revision'])).fetchone()
        page = self.service.repository.pages(self.db, row['id'])[page_index]
        image, _ = transformed_image(self.store.read(page['storage_key']), page['rotation'], parsed(page['crop_json']))
        return recognition_recovery_grant(self.service, self.db, job, row, page, image)

    def test_preflight_is_read_only_and_has_no_provider_call(self):
        before = self.db.raw.total_changes
        writes = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}
        self.db.raw.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action in writes else sqlite3.SQLITE_OK)
        try:
            result = authorize_recovery(self.service, self.db, self.scope)
        finally:
            self.db.raw.set_authorizer(None)
        self.assertFalse(result['authorized'])
        self.assertEqual(result['maximumNewVisionCalls'], 2)
        self.assertEqual(result['pageCount'], 2)
        self.assertEqual(result['wireContract'], WIRE_CONTRACT)
        self.assertEqual(self.db.raw.total_changes, before)
        self.provider.analyze_image.assert_not_called()
        self.transport.assert_not_called()
        self.snapshot_unchanged()

    def test_only_the_new_approval_can_atomically_create_one_job(self):
        for approval in (None, '允许重新分析一次', '允许这份作业重新分析一次'):
            self.error('homework_repair_approval_required', lambda: authorize_recovery(
                self.service, self.db, self.scope, execute=True, approval_text=approval))
        first = self.authorize()
        again = self.authorize()
        self.assertTrue(again['alreadyAuthorized'])
        self.assertEqual(again['authorizationId'], first['authorizationId'])
        self.assertEqual(again['jobId'], first['jobId'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_actions WHERE item_id=?', (ITEM_MARKER,)).fetchone()['n'], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'], 2)
        self.assertEqual(self.service.repository.pages(self.db, self.submission['id']), self.old_pages)
        self.assertEqual(self.grant()['maximumNewVisionCalls'], 2)
        self.assertEqual(self.grant(1)['wireContract'], WIRE_CONTRACT)
        self.provider.analyze_image.assert_not_called()
        self.snapshot_unchanged()

    def test_worker_uses_at_most_one_new_call_per_page_and_keeps_old_receipts(self):
        authorization = self.authorize()
        self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        calls = self.db.execute('SELECT * FROM homework_provider_calls WHERE id!=?', (self.old_call['id'],)).fetchall()
        self.assertEqual(len(calls), 2)
        self.assertEqual({call['page_id'] for call in calls}, {page['id'] for page in self.old_pages})
        for call in calls:
            receipt = parsed(call['receipt_json'])
            self.assertEqual(receipt['operatorRepairAuthorizationId'], authorization['authorizationId'])
            self.assertEqual(receipt['wireContract'], WIRE_CONTRACT)
            self.assertEqual(receipt['maximumNewVisionCalls'], 2)
            self.assertTrue(receipt['receivedResponse'])
            self.assertNotEqual(call['request_sha256'], self.old_call['request_sha256'])
        self.assertEqual(self.service.get('parent-a', self.submission['id'])['submission']['status'], 'ready')
        self.assertTrue(self.authorize()['alreadyAuthorized'])
        self.assertFalse(self.service.process_next()['processed'])
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        self.snapshot_unchanged()

    def test_scope_owner_revision_and_exact_two_page_bounds_fail_closed(self):
        for key, value in [('phone', '19900009302'), ('familyId', 'family-b'), ('childId', 'child-b'),
                           ('expectedRevision', self.scope['expectedRevision'] + 1), ('unknownCallId', 'other-call')]:
            original = self.scope[key]; self.scope[key] = value
            with self.subTest(key=key), self.assertRaises(ApiError): self.authorize()
            self.scope[key] = original
        self.db.execute("UPDATE homework_submissions SET source='paid_validation'"); self.db.raw.commit()
        self.error('homework_repair_scope_changed', self.authorize)
        self.db.execute("UPDATE homework_submissions SET source='parent_app'")
        page = self.old_pages[1]
        self.db.execute('DELETE FROM homework_pages WHERE id=?', (page['id'],)); self.db.raw.commit()
        self.error('homework_repair_scope_changed', self.authorize)
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'], 1)

    def test_response_capture_is_required_and_whole_wire_contract_is_bound(self):
        self.provider.capture_received_response = False
        self.error('homework_repair_contract_invalid', self.authorize)
        self.provider.capture_received_response = True
        self.authorize()
        for attribute, value in [('model_name', 'changed-model'), ('base_url', 'https://other.invalid/v1'),
                                 ('json_output', True), ('disable_thinking', True), ('timeout_seconds', 121),
                                 ('max_image_dimension', 1600), ('jpeg_quality', 75)]:
            old = getattr(self.provider, attribute); setattr(self.provider, attribute, value)
            with self.subTest(attribute=attribute), self.assertRaises(ApiError): self.grant()
            setattr(self.provider, attribute, old)
        self.service.policy = deepcopy(self.service.policy)
        self.service.policy['systemPrompt'] += ' Changed policy.'
        self.error('homework_repair_scope_changed', self.grant)
        self.provider.analyze_image.assert_not_called()

    def test_change_to_any_page_blocks_even_the_other_page_and_reapproval(self):
        self.authorize()
        self.db.execute('UPDATE homework_pages SET rotation=90 WHERE id=?', (self.old_pages[1]['id'],)); self.db.raw.commit()
        self.error('homework_repair_scope_changed', self.grant)
        self.error('homework_repair_scope_changed', self.authorize)
        self.assertEqual(self.service.process_next()['error'], 'homework_repair_scope_changed')
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'], 2)
        self.snapshot_unchanged()

    def test_actual_image_change_after_approval_prevents_any_new_call(self):
        self.authorize()
        changed = Image.open(io.BytesIO(self.old_images[self.old_pages[1]['storage_key']])).convert('RGB')
        ImageDraw.Draw(changed).rectangle((100, 30, 500, 45), fill='black')
        photo = io.BytesIO(); changed.save(photo, format='PNG')
        self.store._path(self.old_pages[1]['storage_key']).write_bytes(photo.getvalue())
        self.assertEqual(self.service.process_next()['error'], 'homework_repair_scope_changed')
        self.provider.analyze_image.assert_not_called()

    def test_expiry_cannot_be_renewed_and_cannot_reserve_a_new_call(self):
        first = self.authorize()
        self.service.clock = lambda: self.clock() + TTL_MS
        self.assertEqual(self.authorize()['expiresAt'], first['expiresAt'])
        self.assertEqual(self.service.process_next()['error'], 'homework_repair_authorization_expired')
        self.provider.analyze_image.assert_not_called()
        self.assertTrue(self.authorize()['alreadyAuthorized'])
        self.assertFalse(self.service.process_next()['processed'])
        self.snapshot_unchanged()

    def test_ambiguous_recovery_never_replays_after_worker_lease_reclaim(self):
        authorization = self.authorize()
        self.provider.analyze_image.side_effect = TimeoutError('simulated unknown repair')
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.service.analyze('parent-a', self.submission['id'], {'revision': authorization['revision']})
        self.assertFalse(self.service.process_next()['processed'])
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old' WHERE id=?", (authorization['jobId'],)); self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count, 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_provider_calls').fetchone()['n'], 2)
        self.snapshot_unchanged()

    def test_partial_success_after_expiry_does_not_send_the_remaining_page(self):
        authorization = self.authorize()
        self.provider.analyze_image.side_effect = [
            AiVisionResponse(json.dumps({'pageReadable': True, 'items': [self.raw]}), 'qwen', 'fixture-vision'),
            TimeoutError('second page unknown'),
        ]
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.service.clock = lambda: self.clock() + TTL_MS + 1
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old' WHERE id=?", (authorization['jobId'],)); self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        self.snapshot_unchanged()

    def test_tampered_grant_old_snapshot_or_call_caps_cannot_be_used(self):
        self.authorize()
        self.db.execute("UPDATE homework_actions SET result_json='{}'"); self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.provider.analyze_image.assert_not_called()

    def test_a_third_reserved_call_or_duplicate_page_exceeds_the_grant(self):
        self.authorize()
        self.assertTrue(self.service.process_next()['ok'])
        calls = self.db.execute('SELECT * FROM homework_provider_calls WHERE id!=?', (self.old_call['id'],)).fetchall()
        extra = dict(calls[0], id='hwcall_extra', page_id='outside-approved-pages', request_sha256='f' * 64)
        columns = list(extra)
        self.db.execute('INSERT INTO homework_provider_calls (' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(extra.values()))
        self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.assertEqual(self.provider.analyze_image.call_count, 2)
        self.db.execute('DELETE FROM homework_provider_calls WHERE id=?', (extra['id'],))
        self.db.execute('UPDATE homework_provider_calls SET page_id=? WHERE id=?', (calls[0]['page_id'], calls[1]['id']))
        self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.assertEqual(self.provider.analyze_image.call_count, 2)

    def test_approved_call_receipt_and_request_sha_must_match_this_grant(self):
        self.authorize()
        self.assertTrue(self.service.process_next()['ok'])
        call = self.db.execute('SELECT * FROM homework_provider_calls WHERE id!=?', (self.old_call['id'],)).fetchone()
        self.db.execute('UPDATE homework_provider_calls SET request_sha256=? WHERE id=?', ('e' * 64, call['id'])); self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.db.execute('UPDATE homework_provider_calls SET request_sha256=? WHERE id=?', (call['request_sha256'], call['id']))
        receipt = parsed(call['receipt_json']); receipt['maximumNewVisionCalls'] = 3
        self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(receipt), call['id'])); self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.assertEqual(self.provider.analyze_image.call_count, 2)

    def test_existing_results_or_received_response_require_a_separate_local_recovery(self):
        self.db.execute('INSERT INTO homework_items (id,submission_id,page_id,revision,analysis_revision,item_order,result_json,media_json,correction_json,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        ('item-existing', self.submission['id'], self.old_pages[0]['id'], 1, self.submission['revision'], 1,
                         '{}', '{}', '{}', self.clock()))
        self.db.raw.commit()
        self.error('homework_repair_scope_changed', self.authorize)
        self.db.execute('DELETE FROM homework_items WHERE id=?', ('item-existing',))
        self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?',
                        (canonical({'receivedResponse': {'schemaVersion': 'existing-response'}}), self.old_call['id']))
        self.db.raw.commit()
        self.error('homework_repair_scope_changed', self.authorize)
        self.provider.analyze_image.assert_not_called()

    def test_old_snapshot_change_and_owner_change_are_detected_by_worker(self):
        self.authorize()
        self.db.execute("UPDATE homework_provider_calls SET error_code='changed' WHERE id=?", (self.old_call['id'],)); self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.db.execute('UPDATE homework_provider_calls SET error_code=? WHERE id=?', (self.old_call['error_code'], self.old_call['id']))
        self.db.execute("UPDATE users SET family_id='family-b' WHERE id='parent-a'"); self.db.raw.commit()
        self.error('homework_repair_authorization_invalid', self.grant)
        self.provider.analyze_image.assert_not_called()

    def test_transaction_failure_does_not_leave_a_grant_or_changed_revision(self):
        self.db.execute("CREATE TRIGGER refuse_response_job BEFORE INSERT ON homework_jobs BEGIN SELECT RAISE(ABORT,'isolated insertion failure'); END")
        self.db.raw.commit()
        with self.assertRaises(sqlite3.IntegrityError): self.authorize()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_actions WHERE item_id=?', (ITEM_MARKER,)).fetchone()['n'], 0)
        self.assertEqual(self.db.execute('SELECT revision FROM homework_submissions').fetchone()['revision'], self.scope['expectedRevision'])
        self.snapshot_unchanged()

    def test_global_call_budget_accounts_for_both_possible_new_calls(self):
        self.service.policy = deepcopy(self.service.policy)
        # Rebind the isolated old request for this deliberately lower policy cap.
        self.service.policy['maxProviderCallsPerSubmission'] = 2
        old_binding = self.service._recognition_repair_input(self.old_pages[0])
        self.db.execute('UPDATE homework_provider_calls SET request_sha256=? WHERE id=?', (old_binding['baseRequestSha256'], self.old_call['id'])); self.db.raw.commit()
        self.error('homework_budget_exceeded', self.authorize)
        self.provider.analyze_image.assert_not_called()


class ResponseRecoveryCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).parents[1] / 'scripts/recover_homework_recognition_response_once.py'
        spec = importlib.util.spec_from_file_location('response_recovery_cli', path)
        cls.cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.cli)

    def arguments(self):
        scope = self.cli.AUTHORIZED_SCOPE
        return ['--phone', scope['phone'], '--child-id', scope['childId'], '--submission-id', scope['submissionId'],
                '--revision', str(scope['expectedRevision']), '--unknown-call-id', scope['unknownCallId']]

    def test_defaults_to_preflight_and_does_not_accept_previous_approval(self):
        args = self.cli.parser().parse_args(self.arguments())
        self.assertFalse(args.execute_authorized_reanalysis)
        self.assertIsNone(args.approval_text)
        with patch.object(self.cli.AppConfig, 'from_env') as config, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.cli.main(self.arguments() + ['--execute-authorized-reanalysis']), 1)
        config.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['error'], 'homework_repair_approval_required')

    def test_exact_dev_database_target_only(self):
        self.cli.validate_config({'APP_ENV': 'development', 'DATABASE_URL': 'postgresql://127.0.0.1:5433/mira', 'HOMEWORK_ANALYSIS_ENABLED': True})
        self.cli.validate_config({'APP_ENV': 'development', 'DATABASE_URL': 'postgresql://mira:secret@127.0.0.1/mira', 'HOMEWORK_ANALYSIS_ENABLED': True})
        for url in ['postgresql://localhost:5433/mira', 'postgresql://remote.invalid/mira',
                    'postgresql://127.0.0.1:3307/mira', 'postgresql://127.0.0.1:5433/other',
                    'postgresql://127.0.0.1:5433/mira_test', 'mysql://127.0.0.1:3306/mira',
                    'sqlite:///mira', 'postgresql://127.0.0.1:5433/mira?other=1',
                    'postgresql://127.0.0.1:5433/mira?options=-c%20search_path%3Dpublic',
                    'postgresql://127.0.0.1:5433/mira#fragment']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.cli.validate_config({'APP_ENV': 'development', 'DATABASE_URL': url, 'HOMEWORK_ANALYSIS_ENABLED': True})

    def test_preflight_starts_a_read_only_transaction_without_worker_or_write(self):
        config = {'APP_ENV': 'development', 'DATABASE_URL': 'postgresql://127.0.0.1:5433/mira',
                  'HOMEWORK_ANALYSIS_ENABLED': True, 'PROMPT_ROOT': 'prompts'}
        fake_database = Mock(); conn = fake_database.connect.return_value
        fake_service = Mock()
        with patch.object(self.cli.AppConfig, 'from_env') as app_config, patch.object(self.cli, 'Database', return_value=fake_database), \
                patch.object(self.cli, 'homework_service', return_value=fake_service), \
                patch.object(self.cli, 'authorize_recovery', return_value={'ok': True, 'authorized': False}) as authorize, redirect_stdout(io.StringIO()):
            app_config.return_value.to_flask_config.return_value = config
            self.assertEqual(self.cli.main(self.arguments()), 0)
        conn.execute.assert_called_once_with('SET TRANSACTION READ ONLY')
        conn.rollback.assert_called_once(); conn.close.assert_called_once()
        fake_database.transaction.assert_not_called()
        authorize.assert_called_once_with(fake_service, conn, self.cli.AUTHORIZED_SCOPE)
        fake_service.process_next.assert_not_called()


if __name__ == '__main__':
    unittest.main()
