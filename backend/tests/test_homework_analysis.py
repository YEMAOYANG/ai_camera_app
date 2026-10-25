"""Isolated photo homework contracts: no real DB migrations, devices or paid AI."""
import base64
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import wave

from flask import Flask
from PIL import Image,ImageDraw
from core.errors import ApiError
from integrations.ai.kimi_vision_provider import AiVisionResponse
from integrations.camera_runtime.document_capture import DocumentCaptureCapability,DocumentCaptureReceipt
from services.homework_assets import HomeworkAssetStore
from services.homework_audio_service import HomeworkAudioService
from services.homework_capture_service import HomeworkCaptureService
from services.homework_math import check_item
from services.homework_service import HomeworkService,POLICY,canonical
from services.prompt_registry import PromptRegistry
from tests.test_textbook_learning import IsolatedDatabase

ROOT=Path(__file__).parents[1]

def picture():
    output=io.BytesIO(); image=Image.new('RGB',(800,1000),'white'); draw=ImageDraw.Draw(image)
    for y in range(60,900,100):
        draw.rectangle((80,y,640,y+20),fill='black')
    image.save(output,format='PNG'); return output.getvalue()

def wav_response(payload,headers):
    data=io.BytesIO()
    with wave.open(data,'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\0\0'*1600)
    # OpenMAIC apiSuccess() returns {success: true, ...data} without an envelope.
    return {'success':True,'audioId':payload['audioId'],'format':'wav','base64':base64.b64encode(data.getvalue()).decode()}

class HomeworkTest(unittest.TestCase):
    def setUp(self):
        self.db=IsolatedDatabase(('085_learning_reviews.sql','086_homework_analysis.sql'))
        self.addCleanup(self.db.raw.close)
        self.db.execute('CREATE TABLE tasks (id TEXT PRIMARY KEY,family_id TEXT,child_id TEXT,title TEXT,type TEXT,status TEXT)')
        self.db.execute('CREATE TABLE devices (id TEXT PRIMARY KEY,family_id TEXT,name TEXT,status TEXT)')
        for suffix in ('a','b'):
            self.db.execute('INSERT INTO children VALUES (?,?,?,?)',(f'child-{suffix}',f'family-{suffix}','primary_1',1))
            self.db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?)',(f'task-{suffix}',f'family-{suffix}',f'child-{suffix}','数学作业','learning','pending'))
            self.db.execute('INSERT INTO devices VALUES (?,?,?,?)',(f'device-{suffix}',f'family-{suffix}','桌面设备','online'))
        self.db.raw.commit()
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=HomeworkAssetStore(self.tmp.name)
        def auth(token,student=False):
            choices={'student-a','student-b'} if student else {'parent-a','parent-b','viewer'}
            if token not in choices: raise ApiError('unauthorized','请登录',401)
            suffix='b' if token.endswith('-b') else 'a'
            return {'principal':{'family_id':f'family-{suffix}','child_id':f'child-{suffix}'}} if student else {'family':{'id':f'family-{suffix}'},'user':{'id':token}}
        def permit(conn,context,capability):
            if context['user']['id']=='viewer' and capability=='manage_tasks': raise ApiError('forbidden','无权操作',403)
        self.raw={'prompt':'3 + 2 =','studentAnswer':'4','type':'arithmetic','confidence':0.99,'region':{'x':0.1,'y':0.1,'width':0.7,'height':0.2},'annotationAmbiguous':False}
        self.provider=SimpleNamespace(provider_name='fixture',model_name='fixture-vision',analyze_image=Mock(side_effect=lambda **kw:AiVisionResponse(json.dumps({'pageReadable':True,'items':[self.raw]}),'fixture','fixture-vision')))
        self.transport=Mock(side_effect=wav_response)
        self.budget=SimpleNamespace(issue_homework_authorization=Mock(return_value={'required':True,'authorizationId':'a'*64}))
        self.audio=HomeworkAudioService(self.db,asset_store=self.store,runtime_base_url='http://127.0.0.1:3100',enabled=True,transport=self.transport,paid_budget_service=self.budget,internal_token='test-internal')
        self.clock=lambda:1790730000000
        # This shared fixture represents persisted v2 receipts. Dedicated v3
        # tests exercise the stricter new provider response contract.
        legacy_policy=json.loads((ROOT/'content/homework_analysis_policy.v2.json').read_text())
        self.service=HomeworkService(self.db,profile_service=SimpleNamespace(_auth_context=auth,_assert_capability=permit),student_auth=SimpleNamespace(authenticate=lambda token:auth(token,True)),asset_store=self.store,prompt_registry=PromptRegistry(ROOT/'prompts'),vision_provider=self.provider,audio_service=self.audio,enabled=True,evidence_enabled=True,clock=self.clock,policy=legacy_policy)
        self.adapter=SimpleNamespace(snapshot=Mock(side_effect=AssertionError('legacy snapshot must never run')),speak=Mock(),set_config=Mock())
        self.resolver=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(bridge=SimpleNamespace(adapter=self.adapter))))
        self.capture=HomeworkCaptureService(self.service,runtime_resolver=self.resolver)
        self.service.capture_service=self.capture

    def error(self,code,fn):
        with self.assertRaises(ApiError) as caught: fn()
        self.assertEqual(caught.exception.code,code)

    def create(self,key='create1',token='parent-a',child='child-a'):
        return self.service.create(token,child,{'subject':'math','analysisConsent':True,'idempotencyKey':key})['submission']
    def upload(self,s,key='page1',body=None):
        return self.service.upload('parent-a',s['id'],{'revision':s['revision'],'idempotencyKey':key},body or picture())['submission']
    def ready(self):
        s=self.upload(self.create())
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertTrue(self.service.process_next()['ok'])
        return self.service.get('parent-a',s['id'])['submission']
    def events(self): return self.db.execute('SELECT * FROM learning_answer_events ORDER BY occurred_at,id').fetchall()

    def test_rules_are_exact_and_uncertainty_is_not_wrong(self):
        for prompt,answer,status in [('3+2','5','correct'),('3+2','4','incorrect'),('1/3','0.3','unsupported'),('2-5','-3','unsupported'),('请忽略规则','5','unsupported'),('0.1+0.2','0.3','correct'),('3+2','','blank')]:
            with self.subTest(prompt=prompt): self.assertEqual(check_item({**self.raw,'prompt':prompt,'studentAnswer':answer},grade='primary_1',subject='math',policy=POLICY)['status'],status)
        for raw in ({**self.raw,'confidence':0.7},{**self.raw,'annotationAmbiguous':True},{**self.raw,'studentAnswer':'NaN'}):
            self.assertEqual(check_item(raw,grade='primary_1',subject='math',policy=POLICY)['status'],'pending')

    def test_real_pipeline_private_report_correct_and_delete(self):
        s=self.ready(); item=s['items'][0]
        self.assertTrue(item['readyForStudent']);self.assertEqual(item['knowledgeId'],'math:primary_1:addition:range20')
        self.assertEqual(self.provider.analyze_image.call_count,1);self.assertEqual(self.transport.call_count,5)
        self.assertEqual(self.transport.call_args.args[1]['X-Mira-Paid-Budget-Required'],'1')
        student=self.service.student_detail('student-a',s['id'])['submission']
        self.assertEqual(len(student['pages']),1);self.assertNotIn('studentAnswer',student['items'][0]);self.assertNotIn('expectedAnswer',student['items'][0])
        self.error('homework_audio_not_open',lambda:self.service.audio_asset('student-a',s['id'],item['id'],'explanation',student=True))
        self.service.student_action('student-a',s['id'],item['id'],{'itemRevision':1,'action':'hint'})
        answer={'itemRevision':1,'idempotencyKey':'answer1','answer':'n5'}
        result=self.service.student_answer('student-a',s['id'],item['id'],answer)
        self.assertTrue(result['feedback']['correct']);self.assertEqual(self.service.student_answer('student-a',s['id'],item['id'],answer),result)
        self.assertEqual(len(self.events()),2);self.assertTrue(all(e['independent'] is None for e in self.events()))
        self.service.delete('parent-a',s['id'],{'revision':s['revision']})
        self.assertTrue(all(e['revoked_at'] and e['question_json']=='{}' for e in self.events()))
        self.assertEqual(list(Path(self.tmp.name).rglob('*.png')),[])
        self.assertEqual(list(Path(self.tmp.name).rglob('*.wav')),[])
        self.error('homework_not_found',lambda:self.service.get('parent-a',s['id']))

    def test_parent_and_student_scope_and_roles(self):
        s=self.upload(self.create());page=s['pages'][0]
        self.error('homework_not_found',lambda:self.service.get('parent-b',s['id']))
        self.error('homework_not_found',lambda:self.service.image('parent-b',s['id'],page['id']))
        self.error('homework_not_found',lambda:self.service.student_detail('student-b',s['id']))
        self.error('forbidden',lambda:self.service.analyze('viewer',s['id'],{'revision':s['revision']}))
        self.assertEqual(self.service.get('viewer',s['id'])['submission']['id'],s['id'])

    def test_student_teacher_correction_needs_no_parent_answer_edit(self):
        s=self.ready();item=s['items'][0]
        # The parent only uploaded and started analysis. The teacher's direct
        # explanation and the child's answer never call the OCR-edit endpoint.
        with patch.object(self.service,'correct_recognition',side_effect=AssertionError('parent editing is not a teaching step')):
            explained=self.service.student_action('student-a',s['id'],item['id'],{'itemRevision':1,'action':'explanation'})['submission']
            self.assertTrue(explained['items'][0]['explanationViewed'])
            self.assertEqual(explained['items'][0]['expectedAnswer'],'5')
            self.assertTrue(self.service.audio_asset('student-a',s['id'],item['id'],'explanation',student=True)[0])
            response=self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'idempotencyKey':'child-correction','answer':'n5'})
        self.assertTrue(response['feedback']['correct'])
        report=self.service.get('parent-a',s['id'])['submission']
        self.assertEqual(report['items'][0]['studentAnswer'],'4')
        self.assertEqual(report['summary']['corrected'],1)
        self.assertEqual(report['studentSummary'],{'ready':1,'awaitingMedia':0,'unsupportedCorrection':0,'corrected':1,'selfReportedCompleted':0})
        self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertEqual(self.transport.call_count,5)
        self.assertEqual(sum(event['hint_used']==1 for event in self.events()),1)

    def test_student_list_keeps_real_processing_failed_and_correct_submissions(self):
        draft=self.upload(self.create('draft'))
        queued=self.upload(self.create('queued'))
        self.service.analyze('parent-a',queued['id'],{'revision':queued['revision']})
        visible=self.service.list_student('student-a')['submissions']
        self.assertEqual([v['id'] for v in visible],[queued['id']])
        self.assertTrue(visible[0]['processing'])
        self.assertNotIn(draft['id'],[v['id'] for v in visible])
        self.provider.analyze_image.side_effect=TimeoutError()
        self.service.process_next()
        failed=self.service.list_student('student-a')['submissions'][0]
        self.assertEqual(failed['status'],'provider_unknown')
        self.assertFalse(failed['readyForStudent'])
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps({'pageReadable':True,'items':[{**self.raw,'studentAnswer':'5'}]}),'fixture','fixture-vision')
        correct=self.upload(self.create('correct'))
        # A different complete input avoids reuse of the earlier unknown call.
        correct=self.service.update_pages('parent-a',correct['id'],{'revision':correct['revision'],'pages':[{'id':correct['pages'][0]['id'],'rotation':90,'crop':None}]})['submission']
        self.service.analyze('parent-a',correct['id'],{'revision':correct['revision']});self.assertTrue(self.service.process_next()['ok'])
        student=self.service.student_detail('student-a',correct['id'])['submission']
        self.assertEqual(student['items'],[])
        self.assertEqual(student['originalSummary'],{'total':1,'correct':1,'incorrect':0,'blank':0,'pending':0,'unsupported':0})
        self.assertIn(correct['id'],[v['id'] for v in self.service.list_student('student-a')['submissions']])
        self.assertEqual(self.service.list_student('student-b')['submissions'],[])
        self.transport.assert_not_called()

    def test_student_summary_does_not_hide_unverified_or_unsupported_items(self):
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps({'pageReadable':True,'items':[
            self.raw,{**self.raw,'prompt':'4+2','confidence':0.1},
            {**self.raw,'prompt':'应用题','type':'unsupported'},
            {**self.raw,'prompt':'150/2','studentAnswer':'74'}]}),'fixture','fixture-vision')
        s=self.ready()
        student=self.service.student_detail('student-a',s['id'])['submission']
        self.assertEqual(student['originalSummary'],{'total':4,'correct':0,'incorrect':2,'blank':0,'pending':1,'unsupported':1})
        self.assertEqual(student['studentSummary'],{'ready':1,'awaitingMedia':0,'unsupportedCorrection':1,'corrected':0,'selfReportedCompleted':0})
        self.assertNotIn('expectedAnswer',student['items'][0])

    def test_idempotency_and_revision_conflicts(self):
        initial=self.create();self.assertEqual(self.create()['id'],initial['id'])
        s=self.upload(initial);self.assertEqual(self.upload(initial)['revision'],s['revision'])
        changed=Image.new('RGB',(800,1000),'red');out=io.BytesIO();changed.save(out,format='PNG')
        self.error('homework_idempotency_conflict',lambda:self.upload(initial,body=out.getvalue()))
        self.error('homework_revision_conflict',lambda:self.upload(initial,key='another'))
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],1)

    def test_crop_order_original_and_reanalysis_reuses_paid_recognition(self):
        s=self.ready();page=s['pages'][0]
        result=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[{'id':page['id'],'rotation':90,'crop':{'x':0,'y':0,'width':0.5,'height':1}}]})['submission']
        transformed=Image.open(io.BytesIO(self.service.image('parent-a',s['id'],page['id'])[0]))
        original=Image.open(io.BytesIO(self.service.image('parent-a',s['id'],page['id'],original=True)[0]))
        self.assertEqual(transformed.size,(500,800));self.assertEqual(original.size,(800,1000))
        # Return to the original geometry; same underlying input is reused, new revision has new item IDs.
        result=self.service.update_pages('parent-a',s['id'],{'revision':result['revision'],'pages':[{'id':page['id'],'rotation':0,'crop':None}]})['submission']
        self.service.analyze('parent-a',s['id'],{'revision':result['revision']});self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertNotEqual(self.service.get('parent-a',s['id'])['submission']['items'][0]['id'],s['items'][0]['id'])

    def test_unknown_provider_never_retries_even_after_worker_restart(self):
        s=self.upload(self.create());self.provider.analyze_image.side_effect=TimeoutError()
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});result=self.service.process_next()
        self.assertEqual(result['error'],'homework_provider_unknown')
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertFalse(self.service.process_next()['processed'])
        # Simulate loss of worker after dispatch: reopening lease must reuse the reservation, not send again.
        self.db.execute("UPDATE homework_jobs SET status='working',lease_until=0,lease_token='old'");self.db.raw.commit()
        self.assertEqual(self.service.process_next()['error'],'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_unconfigured_is_real_error_and_safe_explicit_retry(self):
        s=self.upload(self.create());self.service.provider=SimpleNamespace(provider_name='unconfigured')
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertEqual(self.service.process_next()['error'],'homework_provider_unconfigured')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_provider_calls').fetchone()['n'],0)
        self.service.provider=self.provider
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertTrue(self.service.process_next()['ok'])

    def test_low_grade_waits_for_audio_and_safe_media_resume(self):
        self.audio.enabled=False;s=self.upload(self.create())
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertEqual(self.service.process_next()['error'],'homework_audio_unconfigured')
        report=self.service.get('parent-a',s['id'])['submission'];self.assertFalse(report['readyForStudent']);self.assertFalse(report['processing']);self.assertTrue(report['retryAllowed'])
        self.error('homework_media_preparing',lambda:self.service.student_answer('student-a',s['id'],report['items'][0]['id'],{'itemRevision':1,'idempotencyKey':'a','answer':'n5'}))
        self.audio.enabled=True;self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_recognition_correction_revokes_original_and_all_correction_evidence(self):
        s=self.ready();item=s['items'][0]
        self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'idempotencyKey':'a','answer':'n4'})
        result=self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,'recognitionConfirmed':True,'studentAnswer':'5'})['submission']
        self.assertEqual(result['items'][0]['status'],'correct');self.assertEqual(len([e for e in self.events() if e['revoked_at'] is None]),1)
        self.assertTrue(self.service.process_next()['ok']);self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_pending_recognition_can_be_confirmed_without_new_vision(self):
        self.raw['confidence']=0.4;s=self.ready();item=s['items'][0]
        self.assertEqual(item['status'],'pending');self.assertEqual(self.events(),[])
        result=self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,'recognitionConfirmed':True,'prompt':'3+2','studentAnswer':'4'})['submission']
        self.assertEqual(result['status'],'media_preparing');self.assertEqual(result['items'][0]['status'],'incorrect')
        self.assertTrue(self.service.process_next()['ok']);self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_upper_grade_uses_numeric_with_real_teacher_clips(self):
        self.db.execute("UPDATE children SET grade_code='primary_3' WHERE id='child-a'");self.db.raw.commit()
        self.raw.update(prompt='150/2',studentAnswer='74');s=self.ready();item=s['items'][0]
        self.assertEqual(item['answerMode'],'numeric');self.assertIsNone(item['picture']);self.assertTrue(item['readyForStudent'])
        self.assertTrue(self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'idempotencyKey':'a','answer':'75.0'})['feedback']['correct'])

    def test_upper_grade_small_sum_also_uses_numeric_not_picture_ids(self):
        self.db.execute("UPDATE children SET grade_code='primary_3' WHERE id='child-a'");self.db.raw.commit()
        s=self.ready();item=s['items'][0]
        self.assertEqual(item['answerMode'],'numeric');self.assertIsNone(item['picture'])
        self.assertTrue(self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'idempotencyKey':'a','answer':'5'})['feedback']['correct'])

    def test_low_grade_unsupported_picture_stays_not_ready(self):
        self.raw.update(prompt='150/2',studentAnswer='74');s=self.ready()
        self.assertFalse(s['readyForStudent']);self.assertEqual(self.transport.call_count,0)

    def test_audio_unknown_does_not_repeat_or_fake_ready(self):
        self.transport.side_effect=TimeoutError();s=self.upload(self.create())
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertEqual(self.service.process_next()['error'],'homework_audio_unknown')
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertFalse(self.service.process_next()['processed'])
        self.assertEqual(self.transport.call_count,1);self.assertFalse(self.service.get('parent-a',s['id'])['submission']['readyForStudent'])

    def test_budget_unconfigured_blocks_audio_before_transport(self):
        self.budget.issue_homework_authorization.return_value=None
        s=self.upload(self.create());self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.service.process_next()['error'],'homework_audio_unconfigured');self.transport.assert_not_called()

    def test_delete_during_audio_dispatch_discards_result_and_cleans_file(self):
        s=self.upload(self.create());self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        def respond(payload,headers):
            self.service.delete('parent-a',s['id'],{'revision':s['revision']})
            return wav_response(payload,headers)
        self.transport.side_effect=respond
        self.assertEqual(self.service.process_next()['error'],'homework_job_superseded')
        self.service.purge_files();self.assertEqual(list(Path(self.tmp.name).rglob('*.wav')),[])
        self.assertEqual(self.db.execute('SELECT status FROM homework_audio_receipts').fetchone()['status'],'deleted')

    def test_disabled_authenticates_without_new_schema(self):
        self.service.enabled=False
        self.assertEqual(self.service.list_student('student-a'),{'ok':True,'enabled':False,'submissions':[],'captureTasks':[]})
        self.error('unauthorized',lambda:self.service.list_student('invalid'))
        self.error('unauthorized',lambda:self.service.create('invalid','child-a',{}))

    def authorize(self):
        return self.capture.authorize('parent-a','child-a',{'taskId':'task-a','deviceId':'device-a','revision':0,'enabled':True,'expiresAt':self.clock()+60000})

    def test_camera_defaults_to_fail_closed_and_never_touches_legacy_controls(self):
        self.authorize()
        self.error('homework_document_capture_unavailable',lambda:self.capture.capture('student-a',{'taskId':'task-a','idempotencyKey':'cap1'}))
        self.adapter.snapshot.assert_not_called();self.adapter.speak.assert_not_called();self.adapter.set_config.assert_not_called()
        tasks=self.service.list_student('student-a')['captureTasks'];self.assertEqual(len(tasks),1);self.assertFalse(tasks[0]['available'])
        self.error('homework_capture_request_invalid',lambda:self.capture.capture('student-a',{'taskId':'task-a','idempotencyKey':'cap1','deviceId':'device-b'}))
        self.error('homework_capture_consent_required',lambda:self.capture.capture('student-b',{'taskId':'task-a','idempotencyKey':'cap1'}))

    def approved_camera(self):
        self.capture.approved=frozenset({'fixture-validated'})
        self.adapter.document_capture_capability=lambda:DocumentCaptureCapability('device-a','fixture-validated',True,True,True,True)
        def capture(request):
            body=picture();return DocumentCaptureReceipt(request.request_id,request.device_id,self.clock(),body,'image/png',hashlib.sha256(body).hexdigest())
        self.adapter.capture_document_if_idle=Mock(side_effect=capture)

    def test_approved_atomic_capture_replays_and_creates_one_analysis(self):
        self.authorize();self.approved_camera();data={'taskId':'task-a','idempotencyKey':'capture'}
        result=self.capture.capture('student-a',data);again=self.capture.capture('student-a',data)
        self.assertEqual(result['submission']['id'],again['submission']['id']);self.assertEqual(self.adapter.capture_document_if_idle.call_count,1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],1);self.adapter.snapshot.assert_not_called()

    def test_camera_busy_or_unknown_does_not_repeat(self):
        self.authorize();self.approved_camera();self.adapter.capture_document_if_idle.side_effect=TimeoutError()
        data={'taskId':'task-a','idempotencyKey':'capture'}
        for _ in range(2): self.error('homework_capture_unknown',lambda:self.capture.capture('student-a',data))
        self.assertEqual(self.adapter.capture_document_if_idle.call_count,1);self.assertEqual(list(Path(self.tmp.name).rglob('*.png')),[])

    def test_camera_consent_revocation_inflight_discards_image(self):
        self.authorize();self.approved_camera();capture=self.adapter.capture_document_if_idle.side_effect
        def revoke(request):
            self.capture.authorize('parent-a','child-a',{'taskId':'task-a','deviceId':'device-a','revision':1,'enabled':False,'expiresAt':self.clock()+60000})
            return capture(request)
        self.adapter.capture_document_if_idle.side_effect=revoke
        self.error('homework_capture_consent_required',lambda:self.capture.capture('student-a',{'taskId':'task-a','idempotencyKey':'capture'}))
        self.assertEqual(list(Path(self.tmp.name).rglob('*.png')),[])

    def test_private_review_pool_uses_existing_media_and_revokes_on_correction(self):
        s=self.ready();child={'id':'child-a','family_id':'family-a','grade_code':'primary_1'}
        with self.db.transaction() as conn: questions,gaps=self.service.review_question_pool(conn,child)
        self.assertEqual(gaps,[]);self.assertEqual(len(questions),1);q=questions[0]
        self.assertTrue(q['private']);self.assertEqual(q['evidenceMode'],'repeated_practice')
        self.assertTrue(self.service.review_audio_file(q['promptAudioAsset']).is_file())
        item=s['items'][0];self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,'recognitionConfirmed':True,'studentAnswer':'5'})
        with self.db.transaction() as conn:self.assertFalse(self.service.review_source_alive(conn,child,q))
        self.error('homework_audio_not_found',lambda:self.service.review_audio_file(q['promptAudioAsset']))

    def test_lost_worker_after_receipt_resumes_without_second_paid_request(self):
        s=self.upload(self.create());self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        original=self.service._save_items
        self.service._save_items=Mock(side_effect=RuntimeError('simulated worker termination'))
        with self.assertRaises(RuntimeError):self.service.process_next()
        self.service._save_items=original
        self.db.execute("UPDATE homework_jobs SET lease_until=0");self.db.raw.commit()
        self.assertTrue(self.service.process_next()['ok']);self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_same_uncertain_image_in_another_submission_is_not_rebilled(self):
        self.provider.analyze_image.side_effect=TimeoutError()
        for key in ('first','second'):
            s=self.upload(self.create(key));self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
            self.assertEqual(self.service.process_next()['error'],'homework_provider_unknown')
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_blank_or_tiny_document_stops_before_paid_recognition(self):
        data=io.BytesIO();Image.new('RGB',(800,1000),'white').save(data,format='PNG')
        s=self.upload(self.create(),body=data.getvalue());self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.service.process_next()['status'],'needs_confirmation');self.provider.analyze_image.assert_not_called()

    def test_audio_cap_keeps_completed_clips_without_over_dispatch(self):
        self.audio.max_calls=2;s=self.upload(self.create());self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.service.process_next()['error'],'homework_audio_budget_exceeded')
        self.assertEqual(self.transport.call_count,2);self.assertFalse(self.service.get('parent-a',s['id'])['submission']['readyForStudent'])

    def test_replaying_old_answer_after_parent_correction_does_not_return_stale_success(self):
        s=self.ready();item=s['items'][0];data={'itemRevision':1,'idempotencyKey':'same','answer':'n4'}
        self.service.student_answer('student-a',s['id'],item['id'],data)
        self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,'recognitionConfirmed':True,'studentAnswer':'5'})
        self.error('homework_revision_conflict',lambda:self.service.student_answer('student-a',s['id'],item['id'],data))

    def test_private_path_traversal_and_corrupt_review_audio_rejected(self):
        self.error('homework_asset_invalid',lambda:self.store.read('../../other.png'))
        s=self.ready();child={'id':'child-a','family_id':'family-a','grade_code':'primary_1'}
        with self.db.transaction() as conn:q=self.service.review_question_pool(conn,child)[0][0]
        asset=self.service.review_audio_file(q['promptAudioAsset']);asset.write_bytes(b'bad')
        self.error('homework_audio_missing',lambda:self.service.review_audio_file(q['promptAudioAsset']))

    def test_camera_authority_cannot_pick_foreign_or_finished_task(self):
        args={'taskId':'task-a','deviceId':'device-b','revision':0,'enabled':True,'expiresAt':self.clock()+60000}
        self.error('homework_capture_device_invalid',lambda:self.capture.authorize('parent-a','child-a',args))
        self.db.execute("UPDATE tasks SET status='completed' WHERE id='task-a'");self.db.raw.commit()
        self.error('homework_capture_task_invalid',lambda:self.authorize())
        self.resolver.resolve.assert_not_called();self.adapter.snapshot.assert_not_called()

    def test_same_uncertain_audio_after_recognition_revision_is_not_rebilled(self):
        self.transport.side_effect=TimeoutError();s=self.upload(self.create())
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.service.process_next()
        report=self.service.get('parent-a',s['id'])['submission'];item=report['items'][0]
        self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,'recognitionConfirmed':True,'studentAnswer':'3'})
        self.assertEqual(self.service.process_next()['error'],'homework_audio_unknown');self.assertEqual(self.transport.call_count,1)

    def test_missing_audio_revokes_student_ready_without_paid_regeneration(self):
        s=self.ready();item=self.db.execute('SELECT * FROM homework_items').fetchone()
        self.store.delete(json.loads(item['media_json'])['prompt']['storageKey'])
        self.assertFalse(self.service.get('parent-a',s['id'])['submission']['readyForStudent'])
        self.assertEqual(self.transport.call_count,5)

    def test_disabling_evidence_does_not_prevent_existing_private_evidence_deletion(self):
        s=self.ready();self.service.evidence_enabled=False
        self.service.delete('parent-a',s['id'],{'revision':s['revision']})
        self.assertTrue(all(e['revoked_at'] and e['question_json']=='{}' for e in self.events()))

    def test_worker_disabled_saves_photos_but_analyze_never_queues(self):
        self.service.processing_enabled=False
        s=self.upload(self.create())
        self.assertFalse(s['analysisAvailable']);self.assertEqual(s['availabilityReason'],'照片已保存，AI分析尚未启用')
        with self.assertRaises(ApiError) as caught:self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(caught.exception.status_code,503);self.assertEqual(caught.exception.code,'homework_analysis_paused')
        self.assertEqual(caught.exception.message,'照片已保存，AI分析尚未启用')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],0)
        stored=self.service.get('parent-a',s['id'])['submission'];self.assertEqual(len(stored['pages']),1)
        self.assertEqual(stored['status'],'received');self.assertFalse(stored['processing']);self.assertFalse(stored['retryAllowed'])
        self.provider.analyze_image.assert_not_called();self.transport.assert_not_called()

    def test_worker_disabled_old_queue_is_paused_without_changing_job(self):
        s=self.upload(self.create());self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.service.processing_enabled=False
        paused=self.service.get('parent-a',s['id'])['submission']
        self.assertEqual(paused['status'],'queued');self.assertFalse(paused['processing']);self.assertFalse(paused['analysisAvailable'])
        self.error('homework_analysis_paused',lambda:self.service.process_next())
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'],'queued')
        self.provider.analyze_image.assert_not_called();self.transport.assert_not_called()

    def test_paused_analyze_still_checks_family_authorization(self):
        self.service.processing_enabled=False;s=self.upload(self.create())
        self.error('homework_not_found',lambda:self.service.analyze('parent-b',s['id'],{'revision':s['revision']}))
        self.error('forbidden',lambda:self.service.analyze('viewer',s['id'],{'revision':s['revision']}))

    def test_paused_recognition_correction_is_saved_without_new_job_and_resumes_media_only(self):
        s=self.ready();item=s['items'][0];self.service.processing_enabled=False
        corrected=self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,'recognitionConfirmed':True,'studentAnswer':'3'})['submission']
        self.assertEqual(corrected['items'][0]['studentAnswer'],'3');self.assertFalse(corrected['processing'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],1)
        self.service.processing_enabled=True
        self.service.analyze('parent-a',s['id'],{'revision':corrected['revision']})
        self.assertEqual(self.db.execute('SELECT stage FROM homework_jobs WHERE revision=?',(corrected['revision'],)).fetchone()['stage'],'media')
        self.assertTrue(self.service.process_next()['ok']);self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_paused_worker_does_not_disable_existing_ready_student_activity(self):
        s=self.ready();item=s['items'][0];self.service.processing_enabled=False
        self.assertTrue(self.service.student_detail('student-a',s['id'])['submission']['readyForStudent'])
        self.assertTrue(self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'idempotencyKey':'paused-answer','answer':'n5'})['feedback']['correct'])
        self.assertEqual(self.transport.call_count,5)

    def test_paused_camera_does_not_capture_or_queue(self):
        self.authorize();self.approved_camera();self.service.processing_enabled=False
        self.assertFalse(self.service.list_student('student-a')['captureTasks'][0]['available'])
        self.error('homework_analysis_paused',lambda:self.capture.capture('student-a',{'taskId':'task-a','idempotencyKey':'capture'}))
        self.adapter.capture_document_if_idle.assert_not_called();self.adapter.snapshot.assert_not_called()

    def test_factory_binds_worker_disabled_to_analysis_availability(self):
        from services import service_factory
        app=Flask(__name__)
        app.config.update(DATABASE_URL='postgresql://isolated/example',HOMEWORK_ANALYSIS_ENABLED=True,HOMEWORK_WORKER_ENABLED=False,HOMEWORK_ASSET_ROOT=self.tmp.name)
        with app.app_context(),patch.multiple(service_factory,Database=Mock(return_value=self.db),
            profile_service=Mock(return_value=self.service.profile),student_auth_service=Mock(return_value=self.service.student_auth),
            prompt_registry=Mock(return_value=self.service.prompts),homework_vision_provider=Mock(return_value=self.provider),
            learning_budget_service=Mock(return_value=self.budget),device_runtime_resolver=Mock(return_value=self.resolver)):
            actual=service_factory.homework_service()
        self.assertTrue(actual.enabled);self.assertFalse(actual.processing_enabled)

    def test_remove_last_page_keeps_empty_draft_and_retires_learning(self):
        s=self.ready();item=s['items'][0];page=s['pages'][0]
        self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'answer':'n5','idempotencyKey':'done'})
        self.service.processing_enabled=False
        cleared=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[]})['submission']
        self.assertEqual(cleared['revision'],s['revision']+1);self.assertEqual(cleared['status'],'received')
        self.assertEqual(cleared['pages'],[]);self.assertEqual(cleared['items'],[])
        self.assertFalse(cleared['analysisAvailable']);self.assertFalse(cleared['readyForStudent'])
        self.assertEqual(cleared['summary']['total'],0)
        self.assertTrue(all(event['revoked_at'] for event in self.events()))
        self.assertEqual(list(Path(self.tmp.name).rglob('*.png')),[])
        self.error('homework_page_not_found',lambda:self.service.image('parent-a',s['id'],page['id']))
        self.error('homework_item_not_found',lambda:self.service.audio_asset('student-a',s['id'],item['id'],'prompt',student=True))
        self.error('homework_revision_conflict',lambda:self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[]}))
        self.error('homework_pages_required',lambda:self.service.analyze('parent-a',s['id'],{'revision':cleared['revision']}))
        replaced=self.upload(cleared,key='replacement')
        self.assertEqual(len(replaced['pages']),1);self.assertEqual(replaced['revision'],cleared['revision']+1)

    def test_legacy_shared_picture_survives_partial_delete_and_stale_outbox(self):
        s=self.upload(self.upload(self.create()),key='page2')
        pages=self.db.execute('SELECT * FROM homework_pages ORDER BY page_order').fetchall()
        self.assertNotEqual(pages[0]['storage_key'],pages[1]['storage_key'])
        # Existing installations can still have content-addressed shared keys.
        self.store.delete(pages[1]['storage_key'])
        self.db.execute('UPDATE homework_pages SET storage_key=? WHERE id=?',(pages[0]['storage_key'],pages[1]['id']))
        self.service._enqueue_delete(self.db,pages[0]['storage_key']);self.db.raw.commit()
        self.service.processing_enabled=False
        kept=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[{'id':pages[1]['id']}]})['submission']
        self.assertEqual([page['id'] for page in kept['pages']],[pages[1]['id']])
        self.assertTrue(self.store._path(pages[0]['storage_key']).exists())
        self.assertEqual(self.service.image('parent-a',s['id'],pages[1]['id'])[1],'image/png')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_file_deletions').fetchone()['n'],0)
        self.service.update_pages('parent-a',s['id'],{'revision':kept['revision'],'pages':[]})
        self.assertFalse(self.store._path(pages[0]['storage_key']).exists())

    def test_same_photo_reupload_survives_delayed_cleanup_without_worker(self):
        s=self.upload(self.create());page=self.db.execute('SELECT * FROM homework_pages').fetchone()
        self.service.processing_enabled=False
        with patch.object(self.store,'delete',side_effect=OSError('temporary file busy')):
            empty=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[]})['submission']
        self.assertEqual(empty['pages'],[])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_file_deletions').fetchone()['n'],1)
        new=self.upload(empty,key='again');new_page=self.db.execute('SELECT * FROM homework_pages').fetchone()
        self.assertNotEqual(page['storage_key'],new_page['storage_key'])
        # Any subsequent page save drains the outbox without a paid worker.
        self.service.update_pages('parent-a',s['id'],{'revision':new['revision'],'pages':[{'id':new_page['id']}]})
        self.assertFalse(self.store._path(page['storage_key']).exists())
        self.assertEqual(self.service.image('parent-a',s['id'],new_page['id'])[1],'image/png')
        self.provider.analyze_image.assert_not_called();self.transport.assert_not_called()

    def test_page_edit_retains_paid_audio_cache_and_cleans_orphan_media(self):
        s=self.ready();page=s['pages'][0]
        extra=self.store.put(b'orphan original teacher clip',namespace=s['id'],suffix='wav')
        item=self.db.execute('SELECT * FROM homework_items').fetchone()
        media=json.loads(item['media_json']);media['retired']={'storageKey':extra,'status':'ready'}
        self.db.execute('UPDATE homework_items SET media_json=? WHERE id=?',(canonical(media),item['id']));self.db.raw.commit()
        edited=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[{'id':page['id']}]})['submission']
        self.assertFalse(self.store._path(extra).exists())
        for clip in media.values():
            if clip['storageKey']!=extra:self.assertTrue(self.store._path(clip['storageKey']).exists())
        self.service.analyze('parent-a',s['id'],{'revision':edited['revision']});self.assertTrue(self.service.process_next()['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,1);self.assertEqual(self.transport.call_count,5)

    def test_http_clear_pages_returns_fresh_detail_and_revokes_private_image(self):
        from routes.api.v1.homework import homework_bp
        s=self.upload(self.create());page=s['pages'][0]
        self.service.processing_enabled=False
        app=Flask(__name__);app.register_blueprint(homework_bp,url_prefix='/api')
        with patch('services.service_factory.homework_service',return_value=self.service):
            client=app.test_client();headers={'Authorization':'Bearer parent-a'}
            url=f"/api/homework-submissions/{s['id']}"
            result=client.patch(url+'/pages',headers=headers,json={'revision':s['revision'],'pages':[]})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json['submission']['pages'],[])
            self.assertEqual(result.json['submission']['revision'],s['revision']+1)
            self.assertEqual(client.get(url,headers=headers).json,result.json)
            self.assertEqual(client.get(page['assetUrl'],headers=headers).status_code,404)
            self.assertEqual(client.get(page['assetUrl']+'?original=1',headers=headers).status_code,404)
            self.assertFalse(result.json['submission']['analysisAvailable'])

    def test_synthetic_photos_cannot_dispatch_even_when_paid_workers_enabled(self):
        s=self.upload(self.create())
        self.db.execute('UPDATE homework_submissions SET source=? WHERE id=?',('synthetic_fixture',s['id']));self.db.raw.commit()
        view=self.service.get('parent-a',s['id'])['submission']
        self.assertFalse(view['analysisAvailable']);self.assertIn('测试照片',view['availabilityReason'])
        self.error('homework_sample_not_analyzable',lambda:self.service.analyze('parent-a',s['id'],{'revision':s['revision']}))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],0)
        # Defensive worker check also rejects a previously enqueued fixture.
        self.db.execute('INSERT INTO homework_jobs(id,submission_id,revision,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
            ('old-fixture-job',s['id'],s['revision'],'queued','quality_check',self.clock(),self.clock()));self.db.raw.commit()
        self.assertTrue(self.service.process_next()['processed'])
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'],'cancelled')
        self.provider.analyze_image.assert_not_called();self.transport.assert_not_called()

    def test_synthetic_student_correction_and_recognition_do_not_add_real_marks(self):
        s=self.ready();item=s['items'][0]
        self.db.execute('UPDATE homework_submissions SET source=? WHERE id=?',('synthetic_fixture',s['id']));self.db.raw.commit()
        baseline=self.events()
        result=self.service.student_answer('student-a',s['id'],item['id'],{'itemRevision':1,'answer':'n5','idempotencyKey':'demo-answer'})
        self.assertTrue(result['feedback']['correct']);self.assertEqual(self.events(),baseline)
        original_jobs=self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n']
        result=self.service.correct_recognition('parent-a',s['id'],item['id'],{'revision':s['revision'],'itemRevision':1,
            'recognitionConfirmed':True,'studentAnswer':'5'})
        self.assertEqual(result['submission']['items'][0]['status'],'correct')
        self.assertFalse(result['submission']['analysisAvailable'])
        self.assertEqual(len(self.events()),len(baseline))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_jobs').fetchone()['n'],original_jobs)

    def test_http_upload_private_asset_and_child_route(self):
        from routes.api.v1.homework import homework_bp
        from routes.api.v2.student_homework import student_homework_bp
        app=Flask(__name__);app.register_blueprint(homework_bp,url_prefix='/api');app.register_blueprint(student_homework_bp,url_prefix='/api/v2/student/learning')
        with patch('services.service_factory.homework_service',return_value=self.service):
            client=app.test_client();headers={'Authorization':'Bearer parent-a'}
            result=client.post('/api/children/child-a/homework-submissions',headers=headers,json={'subject':'math','analysisConsent':True,'idempotencyKey':'http'})
            self.assertEqual(result.status_code,200);s=result.json['submission']
            result=client.post(f"/api/homework-submissions/{s['id']}/pages",headers=headers,data={'revision':str(s['revision']),'idempotencyKey':'page','file':(io.BytesIO(picture()),'homework.png')})
            self.assertEqual(result.status_code,200);page=result.json['submission']['pages'][0]
            image=client.get(page['assetUrl']+'?original=1',headers=headers);self.assertEqual(image.status_code,200);self.assertIn('no-store',image.headers['Cache-Control'])
            self.assertEqual(client.get(page['assetUrl'],headers={'Authorization':'Bearer parent-b'}).status_code,404)
            self.assertEqual(client.get('/api/v2/student/learning/homework',headers={'Authorization':'Bearer student-a'}).status_code,200)

if __name__=='__main__':unittest.main()
