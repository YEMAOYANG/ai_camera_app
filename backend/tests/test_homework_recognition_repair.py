"""Single human-authorized recovery; isolated DB/files and fake transports only."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import Mock

from core.errors import ApiError
from integrations.ai.kimi_vision_provider import AiVisionResponse,OpenAICompatibleVisionProvider
from services.homework_service import RECOGNITION_REPAIR_ITEM,RECOGNITION_REPAIR_TTL_MS,parsed
from tests import test_homework_analysis as fixtures


class RecognitionRepairTest(unittest.TestCase):
    create=fixtures.HomeworkTest.create
    upload=fixtures.HomeworkTest.upload
    error=fixtures.HomeworkTest.error

    def setUp(self):
        fixtures.HomeworkTest.setUp(self)
        self.db.execute('CREATE TABLE users (id TEXT PRIMARY KEY,phone TEXT,family_id TEXT)')
        self.db.execute('INSERT INTO users VALUES (?,?,?)',('parent-a','19900009030','family-a'))
        self.db.raw.commit()
        self.provider=OpenAICompatibleVisionProvider(provider_name='qwen',model_name='fixture-vision',
            api_key='isolated-test-only',base_url='https://example.invalid/v1',max_bytes=8388608,max_image_dimension=3200)
        self.provider.analyze_image=Mock(side_effect=TimeoutError('simulated ambiguous call'))
        self.service.provider=self.provider
        self.submission=self.upload(self.create())
        self.service.analyze('parent-a',self.submission['id'],{'revision':self.submission['revision']})
        self.assertEqual(self.service.process_next()['error'],'homework_provider_unknown')
        self.old_call=self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        self.old_job=self.db.execute('SELECT * FROM homework_jobs').fetchone()
        self.old_page=self.db.execute('SELECT * FROM homework_pages').fetchone()
        self.original_image=self.store.read(self.old_page['storage_key'])
        self.scope={'phone':'19900009030','familyId':'family-a','childId':'child-a',
            'submissionId':self.submission['id'],'expectedRevision':self.submission['revision'],
            'unknownCallId':self.old_call['id']}
        self.provider.analyze_image.reset_mock()
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(
            json.dumps({'pageReadable':True,'items':[self.raw]}),'qwen','fixture-vision')

    def authorize(self,**kwargs):
        with self.db.transaction() as conn:
            return self.service.authorize_recognition_repair(conn,self.scope,execute=True,
                approval_text='允许重新分析一次',**kwargs)

    def assert_original_receipts_unchanged(self):
        self.assertEqual(self.db.execute('SELECT * FROM homework_provider_calls WHERE id=?',(self.old_call['id'],)).fetchone(),self.old_call)
        self.assertEqual(self.db.execute('SELECT * FROM homework_jobs WHERE id=?',(self.old_job['id'],)).fetchone(),self.old_job)
        self.assertEqual(self.store.read(self.old_page['storage_key']),self.original_image)

    def test_preflight_is_read_only_even_when_worker_is_enabled(self):
        before=self.db.raw.total_changes
        writes={sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE}
        self.db.raw.set_authorizer(lambda action,*_:sqlite3.SQLITE_DENY if action in writes else sqlite3.SQLITE_OK)
        try:
            result=self.service.authorize_recognition_repair(self.db,self.scope)
        finally:
            self.db.raw.set_authorizer(None)
        self.assertFalse(result['authorized'])
        self.assertEqual(result['wireContract'],'complete-image-encoding.v2')
        self.assertEqual(self.db.raw.total_changes,before)
        self.provider.analyze_image.assert_not_called()
        self.assert_original_receipts_unchanged()

    def test_atomic_once_grant_normal_worker_and_five_audio_segments(self):
        result=self.authorize()
        self.assertEqual(result['revision'],self.submission['revision']+1)
        self.assertEqual(self.db.execute('SELECT * FROM homework_pages').fetchone(),self.old_page)
        self.assertTrue(self.authorize()['alreadyAuthorized'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_actions WHERE item_id=?',(RECOGNITION_REPAIR_ITEM,)).fetchone()['n'],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],2)
        self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertEqual(self.transport.call_count,5)
        self.assertEqual(self.provider.analyze_image.call_args.kwargs['max_tokens'],7000)
        detail=self.service.get('parent-a',self.submission['id'])['submission']
        self.assertEqual(detail['status'],'ready')
        self.assertTrue(detail['items'][0]['readyForStudent'])
        self.assertEqual(self.db.execute('SELECT source FROM homework_submissions').fetchone()['source'],'parent_app')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events').fetchone()['n'],1)
        call=self.db.execute('SELECT * FROM homework_provider_calls WHERE id!=?',(self.old_call['id'],)).fetchone()
        self.assertNotEqual(call['request_sha256'],self.old_call['request_sha256'])
        self.assertEqual(call['model'],self.old_call['model'])
        self.assertEqual(parsed(call['receipt_json'])['operatorRepairAuthorizationId'],result['authorizationId'])
        self.assertTrue(self.authorize()['alreadyAuthorized'])
        self.assertFalse(self.service.process_next()['processed'])
        self.assert_original_receipts_unchanged()

    def test_scope_revision_phone_source_call_and_page_changes_fail_closed(self):
        for key,value in [('phone','19900009031'),('familyId','family-b'),('childId','child-b'),
                          ('expectedRevision',self.scope['expectedRevision']+1),('unknownCallId','other-call')]:
            original=self.scope[key];self.scope[key]=value
            with self.subTest(key=key),self.assertRaises(ApiError):self.authorize()
            self.scope[key]=original
        self.db.execute("UPDATE homework_submissions SET source='paid_validation'");self.db.raw.commit()
        self.error('homework_repair_scope_changed',self.authorize)
        self.db.execute("UPDATE homework_submissions SET source='parent_app'")
        self.db.execute('UPDATE homework_pages SET rotation=90');self.db.raw.commit()
        self.error('homework_repair_scope_changed',self.authorize)
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],1)

    def test_approval_and_transaction_failure_never_partially_enqueue(self):
        self.error('homework_repair_approval_required',lambda:self.service.authorize_recognition_repair(self.db,self.scope,execute=True))
        self.db.execute("CREATE TRIGGER refuse_repair_job BEFORE INSERT ON homework_jobs BEGIN SELECT RAISE(ABORT,'fake insertion failure'); END")
        self.db.raw.commit()
        with self.assertRaises(sqlite3.IntegrityError):self.authorize()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_actions WHERE item_id=?',(RECOGNITION_REPAIR_ITEM,)).fetchone()['n'],0)
        self.assertEqual(self.db.execute('SELECT revision FROM homework_submissions').fetchone()['revision'],self.scope['expectedRevision'])
        self.assert_original_receipts_unchanged()

    def test_expired_grant_cannot_be_renewed_or_dispatched(self):
        first=self.authorize()
        self.service.clock=lambda:self.clock()+RECOGNITION_REPAIR_TTL_MS
        repeated=self.authorize()
        self.assertEqual(repeated['expiresAt'],first['expiresAt'])
        self.assertEqual(self.service.process_next()['error'],'homework_repair_authorization_expired')
        self.provider.analyze_image.assert_not_called()
        self.assertTrue(self.authorize()['alreadyAuthorized'])
        self.assertFalse(self.service.process_next()['processed'])

    def test_changed_page_after_grant_blocks_worker_and_does_not_authorize_again(self):
        self.authorize()
        self.db.execute('UPDATE homework_pages SET rotation=90');self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'],'homework_repair_authorization_invalid')
        self.provider.analyze_image.assert_not_called()
        self.error('homework_repair_scope_changed',self.authorize)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],2)

    def test_actual_image_change_after_grant_cannot_dispatch(self):
        self.authorize()
        from PIL import Image
        import io
        image=Image.open(io.BytesIO(self.original_image)).convert('RGB')
        image.putpixel((20,20),(0,0,0))
        output=io.BytesIO();image.save(output,format='PNG')
        self.store._path(self.old_page['storage_key']).write_bytes(output.getvalue())
        self.assertEqual(self.service.process_next()['error'],'homework_repair_scope_changed')
        self.provider.analyze_image.assert_not_called()

    def test_missing_or_altered_authorization_cannot_use_repair_identity(self):
        self.authorize()
        self.db.execute("UPDATE homework_actions SET result_json='{}'");self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'],'homework_repair_authorization_invalid')
        self.provider.analyze_image.assert_not_called()

    def test_unknown_repair_is_not_dispatched_again_after_worker_lease_recovery(self):
        grant=self.authorize();self.provider.analyze_image.side_effect=TimeoutError('fake unknown')
        self.assertEqual(self.service.process_next()['error'],'homework_provider_unknown')
        self.service.analyze('parent-a',self.submission['id'],{'revision':grant['revision']})
        self.assertFalse(self.service.process_next()['processed'])
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old' WHERE id=?",(grant['jobId'],));self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'],'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count,1)
        self.transport.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_provider_calls').fetchone()['n'],2)
        self.assert_original_receipts_unchanged()

    def test_cached_repair_success_resumes_after_expiry_without_new_visual_dispatch(self):
        grant=self.authorize()
        save=self.service._save_items
        self.service._save_items=Mock(side_effect=ApiError('test_interruption','fake',409))
        self.assertEqual(self.service.process_next()['error'],'test_interruption')
        self.service._save_items=save
        self.service.clock=lambda:self.clock()+RECOGNITION_REPAIR_TTL_MS+1
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old' WHERE id=?",(grant['jobId'],));self.db.raw.commit()
        self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertEqual(self.transport.call_count,5)
        self.assert_original_receipts_unchanged()

    def test_cli_requires_exact_scope_and_defaults_to_preflight(self):
        path=Path(__file__).parents[1]/'scripts/recover_homework_recognition_once.py'
        spec=importlib.util.spec_from_file_location('repair_cli',path)
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        scope=cli.AUTHORIZED_SCOPE
        args=cli.parser().parse_args(['--phone',scope['phone'],'--child-id',scope['childId'],
            '--submission-id',scope['submissionId'],'--revision',str(scope['expectedRevision']),
            '--unknown-call-id',scope['unknownCallId']])
        self.assertFalse(args.execute_authorized_reanalysis)
        for url in ('postgresql://localhost/other_dev','postgresql://remote.invalid/mira','mysql://localhost/mira'):
            with self.assertRaises(ValueError):cli.validate_config({'DATABASE_URL':url,'APP_ENV':'development','HOMEWORK_ANALYSIS_ENABLED':True})


if __name__=='__main__':unittest.main()
