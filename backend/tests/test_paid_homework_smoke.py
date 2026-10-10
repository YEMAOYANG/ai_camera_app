"""Bounded paid-path preflight uses fake vision/Qwen; never external requests."""
from collections import Counter
import io
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from PIL import Image
from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_assets import quality_error
from services.homework_service import POLICY
from test_homework_analysis import HomeworkTest

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import verify_paid_homework_smoke as smoke


class PaidHomeworkValidationTest(unittest.TestCase):
    setUp=HomeworkTest.setUp
    error=HomeworkTest.error
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    events=HomeworkTest.events

    def validation(self,key='validation'):
        row=self.create(key)
        self.db.execute('UPDATE homework_submissions SET source=? WHERE id=?',('paid_validation',row['id']))
        self.db.raw.commit()
        return self.upload(row)

    def run_validation(self,row):
        self.service.analyze('parent-a',row['id'],{'revision':row['revision']})
        return self.service.process_next(submission_id=row['id'])

    def test_normal_client_cannot_select_trusted_source(self):
        row=self.service.create('parent-a','child-a',{'subject':'math','analysisConsent':True,
            'idempotencyKey':'attempted-source','source':'paid_validation'})['submission']
        self.assertEqual(row['source'],'parent_app')
        row=self.upload(row);self.run_validation(row)
        self.assertEqual(len(self.events()),1)

    def test_real_service_flow_ready_media_and_answers_exclude_assessment(self):
        row=self.validation();self.assertTrue(self.run_validation(row)['ok'])
        view=self.service.get('parent-a',row['id'])['submission'];item=view['items'][0]
        self.assertTrue(view['readyForStudent']);self.assertEqual(set(item['voice']),{'prompt','hint','explanation','success','retry'})
        self.assertEqual(self.provider.analyze_image.call_count,1);self.assertEqual(self.transport.call_count,5)
        result=self.service.student_answer('student-a',row['id'],item['id'],{'itemRevision':1,'idempotencyKey':'try1','answer':'n5'})
        self.assertTrue(result['feedback']['correct']);self.assertEqual(self.events(),[])
        pool,gaps=self.service.review_question_pool(self.db,{'family_id':'family-a','id':'child-a','grade_code':'primary_1'})
        self.assertEqual(pool,[])

    def test_targeted_worker_does_not_claim_or_recover_other_jobs(self):
        other=self.upload(self.create('normal'));self.service.analyze('parent-a',other['id'],{'revision':other['revision']})
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='other-lease' WHERE submission_id=?",(other['id'],));self.db.raw.commit()
        row=self.validation();self.assertTrue(self.run_validation(row)['ok'])
        job=self.db.execute('SELECT * FROM homework_jobs WHERE submission_id=?',(other['id'],)).fetchone()
        self.assertEqual(job['status'],'working');self.assertEqual(job['lease_token'],'other-lease')
        self.assertFalse(self.service.process_next(submission_id=row['id'])['processed'])

    def test_persisted_page_vision_and_audio_caps_survive_normal_service(self):
        row=self.validation()
        self.error('homework_page_limit',lambda:self.upload(row,key='second'))
        self.assertTrue(self.run_validation(row)['ok'])
        view=self.service.get('parent-a',row['id'])['submission'];item=view['items'][0]
        self.error('homework_audio_budget_exceeded',lambda:self.audio.ensure(request_id='sixth-clip',text='新的内容',subject='math',submission_id=row['id'],item_id=item['id'],revision=1))
        changed=self.service.update_pages('parent-a',row['id'],{'revision':row['revision'],'pages':[{'id':row['pages'][0]['id'],'rotation':90,'crop':None}]})['submission']
        self.assertEqual(self.run_validation(changed)['error'],'homework_budget_exceeded')
        self.assertEqual(self.provider.analyze_image.call_count,1);self.assertEqual(self.transport.call_count,5)

    def test_recognition_excess_items_stops_before_audio(self):
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps({'pageReadable':True,'items':[self.raw,self.raw]}),'fixture','fixture')
        # The provider returned a durable response; an over-limit envelope is
        # a known local parse failure, not an ambiguous paid dispatch.
        row=self.validation();self.assertEqual(self.run_validation(row)['error'],'homework_recognition_over_limit')
        self.assertFalse(self.run_validation(row)['processed'])
        self.assertEqual(self.provider.analyze_image.call_count,1);self.transport.assert_not_called()
        self.assertEqual(self.service.get('parent-a',row['id'])['submission']['items'],[])

    def test_unknown_audio_stops_all_following_clips_and_no_retry(self):
        self.transport.side_effect=TimeoutError()
        row=self.validation();self.assertEqual(self.run_validation(row)['error'],'homework_audio_unknown')
        item=self.service.get('parent-a',row['id'])['submission']['items'][0]
        self.error('homework_audio_unknown',lambda:self.audio.ensure(request_id='different-clip',text='不要在未知后继续付费',subject='math',submission_id=row['id'],item_id=item['id'],revision=1))
        self.assertFalse(self.run_validation(row)['processed']);self.assertEqual(self.transport.call_count,1)

    def test_native_flat_response_contract_and_missing_key_error_code(self):
        native=Path(__file__).parents[2]/'openmaic-runtime/.runtime/OpenMAIC/lib/server/api-response.ts'
        if native.exists():
            self.assertIn('NextResponse.json({ success: true, ...data }',native.read_text())
        from test_homework_analysis import wav_response
        response=wav_response({'audioId':'test'}, {})
        self.assertNotIn('data',response);self.assertEqual(response['audioId'],'test')
        failure=HTTPError('http://127.0.0.1/api/generate/tts',400,'Bad Request',{},io.BytesIO(json.dumps(
            {'success':False,'errorCode':'MISSING_API_KEY','error':'No API key configured'}).encode()))
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=failure
            self.error('homework_audio_unconfigured',lambda:self.audio._request({},{}))

    def saved_response_failure(self):
        row=self.validation()
        original_put=self.store.put
        def failing_put(body,*,namespace,suffix='png'):
            if suffix=='wav':
                saved=self.db.execute('SELECT result_json FROM homework_audio_receipts').fetchone()
                reference=json.loads(saved['result_json'])
                self.assertLess(len(saved['result_json']),1024)
                self.assertNotIn('transportResponse',reference)
                self.assertTrue(self.store.read(reference['savedResponseKey']))
                raise OSError('simulated media disk failure after durable response')
            return original_put(body,namespace=namespace,suffix=suffix)
        with patch.object(self.store,'put',side_effect=failing_put):
            self.assertEqual(self.run_validation(row)['error'],'homework_audio_unknown')
        call=self.db.execute('SELECT * FROM homework_audio_receipts').fetchone()
        args={'request_id':call['id'],'submission_id':row['id'],'item_id':call['item_id'],'revision':call['revision']}
        return row,call,args

    def test_saved_response_recovers_without_dispatch_then_explicit_parent_resume(self):
        row,call,args=self.saved_response_failure();reference=json.loads(call['result_json'])
        self.assertEqual(call['status'],'unknown');self.assertEqual(self.transport.call_count,1)
        # An outbox row cannot delete private response bytes while still unknown.
        with self.db.transaction() as conn:self.audio._queue_file_delete(conn,reference['savedResponseKey'])
        self.service.purge_files();self.assertTrue(self.store.read(reference['savedResponseKey']))
        self.audio.enabled=False
        result=self.audio.recover_saved_response(**args)
        self.assertEqual(result['status'],'ready');self.assertEqual(self.transport.call_count,1)
        self.assertEqual(self.budget.issue_homework_authorization.call_count,1)
        self.assertEqual(self.audio.recover_saved_response(**args),result)
        state=self.service.get('parent-a',row['id'])['submission']
        self.assertEqual(state['status'],'media_preparing');self.assertFalse(state['processing']);self.assertTrue(state['retryAllowed'])
        self.service.purge_files();self.assertFalse(self.store._path(reference['savedResponseKey']).exists())
        self.audio.enabled=True
        self.assertTrue(self.run_validation(state)['ok'])
        self.assertTrue(self.service.get('parent-a',row['id'])['submission']['readyForStudent'])
        self.assertEqual(self.transport.call_count,5);self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertEqual(sum(c.args[0]['audioId']==call['id'] for c in self.transport.call_args_list),1)

    def test_saved_response_hash_scope_and_delete_boundaries(self):
        row,call,args=self.saved_response_failure();reference=json.loads(call['result_json'])
        self.error('homework_audio_recovery_scope_invalid',lambda:self.audio.recover_saved_response(**{**args,'submission_id':'other'}))
        self.store._path(reference['savedResponseKey']).write_bytes(b'tampered')
        self.error('homework_audio_response_invalid',lambda:self.audio.recover_saved_response(**args))
        self.assertEqual(self.transport.call_count,1)
        self.service.delete('parent-a',row['id'],{'revision':row['revision']})
        deleted=self.db.execute('SELECT status,result_json FROM homework_audio_receipts').fetchone()
        self.assertEqual(deleted['status'],'deleted');self.assertIsNone(deleted['result_json'])
        self.assertFalse(self.store._path(reference['savedResponseKey']).exists())
        self.error('homework_audio_recovery_scope_invalid',lambda:self.audio.recover_saved_response(**args))

    def test_unknown_without_saved_response_cannot_recover_or_repeat(self):
        self.transport.side_effect=TimeoutError()
        row=self.validation();self.run_validation(row)
        call=self.db.execute('SELECT * FROM homework_audio_receipts').fetchone()
        self.error('homework_audio_response_missing',lambda:self.audio.recover_saved_response(request_id=call['id'],submission_id=row['id'],item_id=call['item_id'],revision=call['revision']))
        self.assertEqual(self.service.get('parent-a',row['id'])['submission']['error'],'homework_audio_unknown')
        self.assertFalse(self.run_validation(row)['processed']);self.assertEqual(self.transport.call_count,1)

    def test_worker_interruption_after_response_can_recover_dispatched_receipt(self):
        row,call,args=self.saved_response_failure()
        self.db.execute("UPDATE homework_audio_receipts SET status='dispatched' WHERE id=?",(call['id'],));self.db.raw.commit()
        self.assertEqual(self.audio.recover_saved_response(**args)['status'],'ready')
        self.assertEqual(self.transport.call_count,1)

    def test_visual_unknown_blocks_resume_even_after_audio_recovery(self):
        row,call,args=self.saved_response_failure()
        self.db.execute("UPDATE homework_provider_calls SET status='unknown' WHERE submission_id=?",(row['id'],));self.db.raw.commit()
        self.assertEqual(self.audio.recover_saved_response(**args)['status'],'ready')
        state=self.service.get('parent-a',row['id'])['submission']
        self.assertEqual(state['error'],'homework_audio_unknown');self.assertFalse(state['retryAllowed'])
        self.assertFalse(self.run_validation(state)['processed']);self.assertEqual(self.transport.call_count,1)

    def test_original_page_quality_and_local_guard(self):
        image=Image.open(io.BytesIO(smoke.original_page()))
        self.assertIsNone(quality_error(image,POLICY))
        config={'DATABASE_URL':'mysql://user:private@127.0.0.1/ai_camera_app_dev','APP_ENV':'development',
                'HOMEWORK_WORKER_ENABLED':False,'HOMEWORK_ANALYSIS_ENABLED':True,'HOMEWORK_AUDIO_ENABLED':True,
                'HOMEWORK_TTS_RUNTIME_URL':'http://127.0.0.1:3102','INTERNAL_API_TOKEN':'private'}
        smoke.validate_config(config)
        for key,value in [('HOMEWORK_WORKER_ENABLED',True),('HOMEWORK_AUDIO_ENABLED',False),('DATABASE_URL','mysql://user:private@remote/ai_camera_app_dev')]:
            with self.assertRaises(ValueError):smoke.validate_config({**config,key:value})

    def test_relative_prompt_root_is_script_local_and_existing_absolute_is_kept(self):
        config={'PROMPT_ROOT':'prompts','HOMEWORK_ASSET_ROOT':'unchanged'}
        smoke.normalize_prompt_root(config)
        self.assertEqual(config['PROMPT_ROOT'],str(smoke.ROOT/'prompts'))
        self.assertEqual(config['HOMEWORK_ASSET_ROOT'],'unchanged')
        config['PROMPT_ROOT']='/tmp/explicit-prompt-root';smoke.normalize_prompt_root(config)
        self.assertEqual(config['PROMPT_ROOT'],'/tmp/explicit-prompt-root')

    def test_full_smoke_helper_fake_preflight_is_idempotent(self):
        reports=[]
        def scoped(conn,family):
            names=('homework_submissions','homework_pages','homework_items','homework_item_revisions',
                   'homework_actions','homework_jobs','homework_provider_calls','homework_audio_receipts','learning_answer_events')
            return {name:Counter(smoke.digest(dict(r)) for r in conn.execute('SELECT * FROM '+name).fetchall()) for name in names}
        with patch.object(smoke,'FAMILY','family-a'),patch.object(smoke,'CHILD','child-a'),patch.object(smoke,'scoped_rows',scoped):
            first=smoke.execute(self.db,self.service,'parent-a',reports.append)
            second=smoke.execute(self.db,self.service,'parent-a',reports.append)
        self.assertTrue(first['readyForStudent']);self.assertTrue(first['originalUnrelatedRowsUnchanged'])
        self.assertEqual(first['submissionId'],second['submissionId']);self.assertEqual(self.events(),[])
        self.assertEqual(self.provider.analyze_image.call_count,1);self.assertEqual(self.transport.call_count,5)
        self.assertNotIn('test-internal',json.dumps(reports))


if __name__=='__main__':unittest.main()
