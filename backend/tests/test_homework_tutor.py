"""Real domain/queue flows with fake providers; never calls paid AI or live DB."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from integrations.ai.kimi_vision_provider import AiVisionResponse
from core.errors import ApiError
from services.homework_service import canonical
from services.homework_tutor_service import POLICY,parse_response,sha,teaching_view
from tests.test_homework_analysis import HomeworkTest,picture


def teacher_reply(**changes):
    value={'sourceCheck':{'status':'matched','reason':'已核对原图中的选中小题和原作答。'},
        'teacherText':'先看图里的条件，再把两组放在一起。',
        'assessment':{'status':'incorrect','reason':'漏数了第二组','expectedAnswer':'5'},
        'steps':[{'text':'这里有三颗，再放来两颗。','visual':{'kind':'groups','groups':[3,2]}},
                 {'text':'数一数一共有几颗。','visual':{'kind':'quantity','count':5}}]}
    value.update(changes)
    return value


class HomeworkTutorTests(unittest.TestCase):
    setUp=HomeworkTest.setUp
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    error=HomeworkTest.error
    events=HomeworkTest.events

    def turn(self,s,item=None,*,key='question-1',mode='explain',message=''):
        item=item or s['items'][0]
        return self.service.tutor.submit('student-a',s['id'],item['id'],{'itemRevision':item['revision'],'idempotencyKey':key,'mode':mode,'message':message})

    def teach(self,s,reply=None):
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps(reply or teacher_reply(),ensure_ascii=False),'fixture','fixture-vision')
        return self.service.process_next(submission_id=s['id'])

    def test_original_image_and_free_question_history_are_real_model_inputs(self):
        s=self.ready();event_count=len(self.events());item=s['items'][0]
        first=self.turn(s)['tutor']['turns'][0]
        self.assertEqual(first['status'],'queued');self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertTrue(self.teach(s)['ok'])
        detail=self.service.tutor.get('student-a',s['id'],item['id'])['tutor']
        self.assertEqual(detail['turns'][0]['status'],'ready')
        self.assertEqual(detail['turns'][0]['audio']['status'],'ready')
        self.assertFalse(detail['turns'][0]['assessment']['countsForAbility'])
        self.assertTrue(self.service.tutor.audio('student-a',s['id'],item['id'],first['id'])[0])
        self.turn(s,key='question-2',mode='followup',message='为什么要把这两组放在一起？')
        self.teach(s,teacher_reply(teacherText='因为题目问的是一共，两组要合起来数。'))
        args=self.provider.analyze_image.call_args.kwargs
        self.assertEqual(args['image_bytes'],self.service.image('student-a',s['id'],item['pageId'],student=True)[0])
        self.assertIn('为什么要把这两组放在一起？',args['user_prompt'])
        self.assertIn('先看图里的条件',args['user_prompt'])
        self.assertEqual(len(self.events()),event_count)
        parent=self.service.get('parent-a',s['id'])['submission']
        self.assertEqual(parent['tutorSummary']['readyTurnCount'],2)
        self.assertEqual(parent['items'][0]['latestTutorAssessment']['method'],'ai_guidance')
        self.assertEqual(parent['items'][0]['expectedAnswer'],'5')

    def test_non_arithmetic_across_subjects_can_be_taught_without_parent_reentering_answer(self):
        for index,subject in enumerate(('chinese','english','math','science','other')):
            self.raw.update(prompt='小猫有三颗糖，小狗又给它两颗，一共有几颗？',type='word_problem')
            created=self.service.create('parent-a','child-a',{'subject':subject,'analysisConsent':True,'idempotencyKey':'subject-'+str(index)})['submission']
            s=self.upload(created,key='page-'+str(index))
            s=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[{'id':s['pages'][0]['id'],'rotation':90*(index%4),'crop':None}]})['submission']
            self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.service.process_next(submission_id=s['id'])
            detail=self.service.student_detail('student-a',s['id'])['submission']
            self.assertTrue(detail['tutorAvailable']);item=detail['tutorItems'][0]
            self.assertEqual(item['status'],'unsupported')
            self.turn(detail,item,key='teach-'+str(index))
            self.assertTrue(self.teach(detail)['ok'])
            self.assertEqual(self.service.tutor.get('student-a',s['id'],item['id'])['tutor']['turns'][0]['status'],'ready')
            # Restore OCR for the next submission; tutor need not edit it.
            self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps({'pageReadable':True,'items':[self.raw]}),'fixture','fixture-vision')
        self.assertEqual(self.events(),[])

    def test_correct_and_pending_original_items_have_tutor_entries_without_fabricated_mistakes(self):
        self.raw['studentAnswer']='5'
        s=self.ready()
        detail=self.service.student_detail('student-a',s['id'])['submission']
        self.assertEqual(detail['items'],[]);self.assertEqual(len(detail['tutorItems']),1)
        self.assertEqual(detail['originalSummary']['correct'],1)
        self.turn(detail,detail['tutorItems'][0]);self.teach(detail,teacher_reply(assessment={'status':'correct','reason':'这道算式正确','expectedAnswer':'5'}))
        self.assertEqual(self.service.get('parent-a',s['id'])['submission']['originalSummary']['correct'],1)

    def test_idempotent_same_request_and_refresh_do_not_dispatch_again(self):
        s=self.ready();queued=self.turn(s)
        self.assertEqual(self.turn(s),queued)
        self.teach(s)
        after=self.turn(s)
        for _ in range(3):self.service.tutor.get('student-a',s['id'],s['items'][0]['id'])
        self.assertFalse(self.service.process_next(submission_id=s['id'])['processed'])
        self.assertEqual(self.provider.analyze_image.call_count,2)
        self.assertEqual(after['tutor']['turns'][0]['status'],'ready')
        self.error('homework_idempotency_conflict',lambda:self.turn(s,mode='followup',message='新问题'))

    def test_identical_questions_at_same_time_reconcile_by_request_key(self):
        s=self.ready();item=s['items'][0]
        # A fixed server clock deliberately makes both creation timestamps equal.
        self.turn(s,key='why-first',mode='followup',message='为什么？')
        self.teach(s)
        second=self.turn(s,key='why-second',mode='followup',message='为什么？')
        turns=second['tutor']['turns']
        self.assertEqual([turn['requestKey'] for turn in turns],['why-first','why-second'])
        self.assertEqual(turns[0]['createdAt'],turns[1]['createdAt'])
        self.assertNotEqual(turns[0]['id'],turns[1]['id'])
        self.assertEqual(turns[1]['status'],'queued')
        refreshed=self.service.tutor.get('student-a',s['id'],item['id'])['tutor']['turns']
        self.assertEqual(next(turn for turn in refreshed if turn['requestKey']=='why-second')['id'],turns[1]['id'])
        self.assertEqual(self.turn(s,key='why-second',mode='followup',message='为什么？'),second)
        self.assertEqual(self.provider.analyze_image.call_count,2)

    def test_concurrent_or_unknown_turn_blocks_new_request_key(self):
        s=self.ready();self.turn(s)
        self.error('homework_tutor_pending',lambda:self.turn(s,key='question-2'))
        self.provider.analyze_image.side_effect=TimeoutError()
        outcome=self.service.process_next(submission_id=s['id']);self.assertEqual(outcome['error'],'homework_tutor_unknown')
        self.error('homework_tutor_pending',lambda:self.turn(s,key='question-3'))
        self.assertFalse(self.service.process_next(submission_id=s['id'])['processed'])
        self.assertEqual(self.provider.analyze_image.call_count,2)

    def test_owner_child_revision_and_same_key_body_are_server_enforced(self):
        s=self.ready();item=s['items'][0]
        data={'itemRevision':1,'idempotencyKey':'scoped','mode':'explain','message':''}
        self.error('homework_not_found',lambda:self.service.tutor.submit('student-b',s['id'],item['id'],data))
        self.error('homework_revision_conflict',lambda:self.service.tutor.submit('student-a',s['id'],item['id'],{**data,'itemRevision':True}))
        self.error('homework_revision_conflict',lambda:self.service.tutor.submit('student-a',s['id'],item['id'],{key:value for key,value in data.items() if key!='itemRevision'}))
        self.error('homework_revision_conflict',lambda:self.service.tutor.submit('student-a',s['id'],item['id'],{**data,'itemRevision':2}))
        self.error('homework_tutor_mode_invalid',lambda:self.service.tutor.submit('student-a',s['id'],item['id'],{**data,'mode':'operator-retry'}))
        self.error('homework_tutor_message_invalid',lambda:self.service.tutor.submit('student-a',s['id'],item['id'],{**data,'mode':'followup'}))
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_low_confidence_original_never_becomes_confirmed_wrong_or_ability_score(self):
        self.raw['confidence']=0.2
        s=self.ready();detail=self.service.student_detail('student-a',s['id'])['submission'];item=detail['tutorItems'][0]
        self.turn(detail,item);self.teach(detail)
        turn=self.service.tutor.get('student-a',s['id'],item['id'])['tutor']['turns'][0]
        self.assertEqual(turn['assessment']['status'],'needs_confirmation')
        self.assertFalse(turn['assessment']['countsForAbility']);self.assertEqual(self.events(),[])
        self.assertEqual(self.service.get('parent-a',s['id'])['submission']['originalSummary']['incorrect'],0)

    def test_response_saved_before_parsing_and_invalid_content_is_not_billed_again(self):
        s=self.ready();self.turn(s)
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse('{"teacherText":"x","teacherText":"y"}','fixture','fixture-vision',raw_response=b'private original envelope')
        result=self.service.process_next(submission_id=s['id'])
        self.assertEqual(result['error'],'homework_tutor_response_invalid')
        calls=self.db.execute('SELECT * FROM homework_provider_calls WHERE id LIKE ?',('hwtcall_%',)).fetchall()
        self.assertEqual(calls[0]['status'],'returned_invalid')
        receipt=json.loads(calls[0]['receipt_json']);body=self.store.read(receipt['responseJournalKey'])
        self.assertEqual(json.loads(body)['responseEnvelopeBase64'],'cHJpdmF0ZSBvcmlnaW5hbCBlbnZlbG9wZQ==')
        self.assertIn('responseEnvelopeBase64',json.loads(body))
        self.assertFalse(self.service.process_next(submission_id=s['id'])['processed'])
        self.assertEqual(self.provider.analyze_image.call_count,2)

    def test_lost_response_database_link_is_recovered_without_new_model_dispatch(self):
        s=self.ready();self.turn(s)
        original=self.service.tutor._save
        crashed=[False]
        def crash(conn,record,turn):
            if turn.get('status')=='ready' and not crashed[0]:
                crashed[0]=True;raise SystemExit('process restart after received model result')
            return original(conn,record,turn)
        self.service.tutor._save=crash
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps(teacher_reply()),'fixture','fixture-vision')
        with self.assertRaises(SystemExit):self.service.process_next(submission_id=s['id'])
        self.service.tutor._save=original
        self.service.clock=lambda:1790730000000+POLICY['leaseMilliseconds']+1
        self.assertTrue(self.service.process_next(submission_id=s['id'])['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,2)
        self.assertEqual(self.transport.call_count,6)

    def test_provider_settings_drift_does_not_dispatch_old_reserved_turn(self):
        s=self.ready();self.turn(s)
        original=self.store.put_response
        def crash(data,*,namespace):
            if namespace.startswith('homework-tutor-request:'):raise SystemExit('restart before HTTP')
            return original(data,namespace=namespace)
        self.store.put_response=crash
        with self.assertRaises(SystemExit):self.teach(s)
        self.store.put_response=original
        self.provider.max_image_dimension=2222
        self.service.clock=lambda:1790730000000+POLICY['leaseMilliseconds']+1
        result=self.service.process_next(submission_id=s['id'])
        self.assertEqual(result['error'],'homework_tutor_scope_changed')
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_unknown_provider_call_after_lease_expiry_never_dispatched_twice(self):
        s=self.ready();self.turn(s)
        original=self.store.put_response
        def crash(data,*,namespace):
            if namespace.startswith('homework-tutor-response:'):raise SystemExit('HTTP succeeded but process died before receipt fsync')
            return original(data,namespace=namespace)
        self.store.put_response=crash
        with self.assertRaises(SystemExit):self.teach(s)
        self.store.put_response=original
        self.service.clock=lambda:1790730000000+POLICY['leaseMilliseconds']+1
        outcome=self.service.process_next(submission_id=s['id'])
        self.assertEqual(outcome['error'],'homework_tutor_unknown');self.assertEqual(self.provider.analyze_image.call_count,2)

    def test_teacher_reference_conflict_does_not_replace_exact_math(self):
        s=self.ready();self.turn(s)
        outcome=self.teach(s,teacher_reply(assessment={'status':'correct','reason':'','expectedAnswer':'6'}))
        self.assertTrue(outcome['ok'])
        turn=self.service.tutor.get('student-a',s['id'],s['items'][0]['id'])['tutor']['turns'][0]
        self.assertEqual(turn['assessment']['status'],'needs_confirmation')
        self.assertEqual(turn['sourceCheck']['status'],'unclear')
        self.assertEqual(turn['assessment']['expectedAnswer'],'')
        self.assertEqual(turn['audio']['status'],'unavailable')
        detail=self.service.get('parent-a',s['id'])['submission']
        self.assertEqual(detail['items'][0]['expectedAnswer'],'5');self.assertEqual(detail['originalSummary']['incorrect'],1)
        self.assertEqual(self.transport.call_count,5)

    def test_explicit_media_only_resume_does_not_resend_vision(self):
        s=self.ready();self.audio.enabled=False;first=self.turn(s)['tutor']['turns'][0]
        self.teach(s)
        view=self.service.tutor.get('student-a',s['id'],s['items'][0]['id'])
        self.assertEqual(view['tutor']['turns'][0]['audio']['errorCode'],'homework_audio_unconfigured')
        self.audio.enabled=True
        self.service.tutor.resume_audio('student-a',s['id'],s['items'][0]['id'],first['id'],{'itemRevision':1,'idempotencyKey':'resume-voice'})
        self.assertTrue(self.service.process_next(submission_id=s['id'])['ok'])
        self.assertEqual(self.provider.analyze_image.call_count,2)
        self.assertEqual(self.service.tutor.get('student-a',s['id'],s['items'][0]['id'])['tutor']['turns'][0]['audio']['status'],'ready')

    def test_unknown_audio_not_allowed_to_repeat_via_media_resume(self):
        s=self.ready();first=self.turn(s)['tutor']['turns'][0]
        self.transport.side_effect=TimeoutError()
        self.teach(s)
        self.error('homework_tutor_audio_not_retriable',lambda:self.service.tutor.resume_audio('student-a',s['id'],s['items'][0]['id'],first['id'],{'itemRevision':1,'idempotencyKey':'resume-voice'}))
        self.assertEqual(self.transport.call_count,6)

    def test_delete_and_page_edit_revoke_history_audio_private_receipts(self):
        s=self.ready();first=self.turn(s)['tutor']['turns'][0];self.teach(s)
        before=set(Path(self.tmp.name).rglob('*.json'));self.assertGreaterEqual(len(before),3)
        edited=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[{'id':s['pages'][0]['id'],'rotation':90}]})['submission']
        retained=self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(first['id'],)).fetchone()
        self.assertEqual(json.loads(retained['result_json'])['status'],'revoked')
        self.assertEqual(json.loads(retained['result_json'])['teacherText'],'')
        self.assertEqual(self.db.execute('SELECT status FROM homework_provider_calls WHERE id LIKE ?',('hwtcall_%',)).fetchone()['status'],'deleted')
        self.assertEqual(self.db.execute('SELECT status FROM homework_audio_receipts WHERE id LIKE ?',('hwtaudio_%',)).fetchone()['status'],'deleted')
        self.service.delete('parent-a',s['id'],{'revision':edited['revision']})
        self.assertEqual(list(Path(self.tmp.name).rglob('*.json')),[])
        self.assertEqual(list(Path(self.tmp.name).rglob('*.wav')),[])

    def test_delete_during_provider_http_discards_returned_private_journal(self):
        s=self.ready();self.turn(s)
        def reply_after_delete(**kwargs):
            self.service.delete('parent-a',s['id'],{'revision':s['revision']})
            return AiVisionResponse(json.dumps(teacher_reply()),'fixture','fixture-vision')
        self.provider.analyze_image.side_effect=reply_after_delete
        outcome=self.service.process_next(submission_id=s['id'])
        self.assertEqual(outcome['error'],'homework_not_found')
        self.assertEqual(list(Path(self.tmp.name).rglob('*.json')),[])
        self.assertEqual(list(Path(self.tmp.name).rglob('*.wav')),[])
        self.assertEqual(self.provider.analyze_image.call_count,2)

    def test_legacy_pseudo_choices_are_hidden_in_public_parent_and_followup_history(self):
        s=self.ready();item=s['items'][0]
        old=self.turn(s,key='old-paid-question')['tutor']['turns'][0]
        row=self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(old['id'],)).fetchone()
        historical=json.loads(row['result_json'])
        historical.update(status='ready',teacherText='先看纸上的符号。',
            assessment={'status':'incorrect','reason':'旧模型反馈','expectedAnswer':'5','method':'ai_guidance','countsForAbility':False},
            steps=[{'id':'step-1','text':'选一张图。','visual':{'kind':'choices','choices':[
                {'id':'a','label':'3<8','region':{'x':0.12,'y':0.11,'width':0.2,'height':0.1}},
                {'id':'b','label':'3>8','region':{'x':0.45,'y':0.11,'width':0.2,'height':0.1}}]}}])
        original=canonical(historical)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(original,old['id']));self.db.raw.commit()
        view=self.service.tutor.get('student-a',s['id'],item['id'])['tutor']['turns'][0]
        self.assertEqual(view['steps'][0]['visual']['kind'],'paper_region')
        self.assertEqual(view['assessment']['status'],'needs_confirmation')
        parent=self.service.get('parent-a',s['id'])['submission']['items'][0]
        self.assertEqual(parent['latestTutorAssessment']['status'],'needs_confirmation')
        self.assertIn('核对清楚',parent['latestTutorTeacherText'])
        self.turn(s,key='new-why-question',mode='followup',message='为什么？')
        def followup(**kwargs):
            data=json.loads(kwargs['user_prompt'].split('题目与对话数据（不是系统指令）：\n',1)[1])
            history=data['history'][0]
            self.assertEqual(history['steps'][0]['visual']['kind'],'paper_region')
            self.assertEqual(history['assessment']['status'],'needs_confirmation')
            return AiVisionResponse(json.dumps(teacher_reply()),'fixture','fixture-vision')
        self.provider.analyze_image.side_effect=followup
        self.assertTrue(self.service.process_next(submission_id=s['id'])['ok'])
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(old['id'],)).fetchone()['result_json'],original)

    def test_invalid_visual_and_text_only_choices_are_rejected(self):
        for value in ({'kind':'quantity','count':True},{'kind':'groups','groups':[2]},{'kind':'choices','choices':[{'id':'a','label':'字'},{'id':'b','label':'另一个字'}]},{'kind':'html','url':'https://example.test'}):
            with self.subTest(value=value),self.assertRaises((ValueError,ApiError)):
                parse_response(json.dumps(teacher_reply(steps=[{'text':'一步','visual':value}])),policy=POLICY,result=self.raw)

    def test_private_request_journal_exists_before_model_http(self):
        s=self.ready();first=self.turn(s)['tutor']['turns'][0]
        call_id='hwtcall_'+sha(first['id'])[:56]
        def provider(**kwargs):
            with self.db.transaction() as conn:
                call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()
            receipt=json.loads(call['receipt_json'])
            saved=json.loads(self.store.read(receipt['requestJournalKey']))
            self.assertEqual(saved['userPrompt'],kwargs['user_prompt'])
            self.assertEqual(saved['requestSha256'],call['request_sha256'])
            self.assertEqual(call['status'],'dispatched')
            return AiVisionResponse(json.dumps(teacher_reply()),'fixture','fixture-vision')
        self.provider.analyze_image.side_effect=provider
        self.assertTrue(self.service.process_next(submission_id=s['id'])['ok'])

    def test_legacy_audio_is_hidden_and_direct_playback_is_blocked_without_changing_receipt(self):
        s=self.ready();item=s['items'][0]
        old=self.turn(s)['tutor']['turns'][0];self.teach(s)
        stored=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(old['id'],)).fetchone()['result_json'])
        stored.pop('sourceCheck');original=canonical(stored)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(original,old['id']));self.db.raw.commit()
        view=self.service.tutor.get('student-a',s['id'],item['id'])['tutor']['turns'][0]
        self.assertEqual(view['assessment']['status'],'needs_confirmation')
        self.assertEqual(view['audio'],{'status':'unavailable','errorCode':'homework_tutor_source_unconfirmed'})
        self.assertNotIn('assetUrl',view['audio'])
        self.error('homework_tutor_audio_not_ready',lambda:self.service.tutor.audio('student-a',s['id'],item['id'],old['id']))
        self.error('homework_tutor_source_unconfirmed',lambda:self.service.tutor.resume_audio('student-a',s['id'],item['id'],old['id'],{'itemRevision':1,'idempotencyKey':'resume-old'}))
        self.assertEqual(self.service.get('parent-a',s['id'])['submission']['tutorSummary']['needsConfirmationCount'],1)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(old['id'],)).fetchone()['result_json'],original)


class HomeworkTutorSourceCheckTests(unittest.TestCase):
    def result(self,**updates):
        return {'prompt':'3 + 2 =','studentAnswer':'4','confidence':0.99,'annotationAmbiguous':False,
            'recognitionNeedsConfirmation':False,'region':{'x':0.1,'y':0.1,'width':0.7,'height':0.2},
            'method':'decimal_arithmetic.v1','expectedAnswer':'5',**updates}

    def parse(self,reply,result=None,policy=None):
        return parse_response(json.dumps(reply,ensure_ascii=False),policy=policy or POLICY,result=result or self.result())

    def test_source_check_is_required_for_actual_v3_policy(self):
        reply=teacher_reply();reply.pop('sourceCheck')
        with self.assertRaisesRegex(ValueError,'source check required'):self.parse(reply)
        legacy={**POLICY,'prompt':{'id':'homework.tutor','version':'v2'},'requireSourceCheck':False}
        self.assertEqual(self.parse(reply,policy=legacy)['assessment']['status'],'incorrect')

    def test_readable_photo_disagrees_with_ocr_and_preserves_actual_blank(self):
        reply=teacher_reply(sourceCheck={'status':'mismatch','reason':'照片中第二个数没有填写，OCR把空框补成了1。',
            'prompt':'4 - □ = 3','studentAnswer':'4 - □ = 3'},teacherText='答案是1，小朋友这里写错了。')
        result=self.parse(reply,self.result(prompt='4-1=3',studentAnswer='4-1=3',expectedAnswer='3'))
        self.assertEqual(result['sourceCheck']['studentAnswer'],'4 - □ = 3')
        self.assertEqual(result['assessment']['status'],'needs_confirmation')
        self.assertEqual(result['assessment']['expectedAnswer'],'')
        self.assertNotIn('答案是1',result['teacherText'])
        self.assertFalse(result['assessment']['countsForAbility'])
        self.assertEqual(result['steps'][0]['visual']['region']['width'],1.0)

    def test_claimed_match_cannot_hide_changed_observed_prompt_or_original_answer(self):
        for field,observation in (('prompt','3+3='),('studentAnswer','□')):
            with self.subTest(field=field):
                result=self.parse(teacher_reply(sourceCheck={'status':'matched','reason':'核对原图',field:observation}))
                self.assertEqual(result['sourceCheck']['status'],'mismatch')
                self.assertEqual(result['assessment']['status'],'needs_confirmation')
                self.assertNotIn('verifiedReferenceAnswer',result['assessment'])

    def test_unclear_source_never_publishes_uncertain_model_steps(self):
        result=self.parse(teacher_reply(sourceCheck={'status':'unclear','reason':'涂改遮住了图中的星星数量。'}))
        self.assertEqual(len(result['steps']),1)
        self.assertEqual(result['steps'][0]['visual']['kind'],'paper_region')
        self.assertEqual(result['assessment']['status'],'needs_confirmation')
        self.assertNotIn('三颗',result['steps'][0]['text'])

    def test_exact_reference_conflict_becomes_source_confirmation_instead_of_failed_turn(self):
        result=self.parse(teacher_reply(assessment={'status':'correct','reason':'','expectedAnswer':'6'}))
        self.assertEqual(result['sourceCheck']['status'],'mismatch')
        self.assertEqual(result['assessment']['status'],'needs_confirmation')
        self.assertEqual(result['assessment']['expectedAnswer'],'')

    def test_matched_source_preserves_normal_teaching_without_claiming_independent_ability(self):
        result=self.parse(teacher_reply(sourceCheck={'status':'matched','reason':'从原图确认',
            'prompt':'３＋２＝','studentAnswer':' 4 '}))
        self.assertEqual(result['assessment']['status'],'incorrect')
        self.assertEqual(result['assessment']['verifiedReferenceAnswer'],'5')
        self.assertEqual(result['steps'][0]['visual']['kind'],'groups')
        self.assertFalse(result['assessment']['countsForAbility'])

    def test_source_check_has_strict_bounds_status_and_utf8(self):
        for source in ({'status':'solved','reason':'x'},{'status':'matched','reason':'x'*301},
            {'status':'unclear','reason':'x','studentAnswer':'x'*1001},{'status':'matched','reason':'\ud800'}):
            with self.subTest(source=repr(source)),self.assertRaises((ValueError,UnicodeError)):
                self.parse(teacher_reply(sourceCheck=source))


class HomeworkTutorChoiceBoundaryTests(unittest.TestCase):
    region={'x':0.1,'y':0.1,'width':0.7,'height':0.2}

    def reply(self):
        return teacher_reply(steps=[{'text':'看一看这两张候选图片。','visual':{'kind':'choices','choices':[
            {'id':'a','label':'左图','region':{'x':0.12,'y':0.11,'width':0.2,'height':0.1}},
            {'id':'b','label':'右图','region':{'x':0.45,'y':0.11,'width':0.2,'height':0.1}}]}}])

    def result(self,**updates):
        return {'type':'choice','region':self.region,'confidence':0.99,'annotationAmbiguous':False,**updates}

    def parsed(self,reply,result):
        return parse_response(json.dumps(reply),policy=POLICY,result=result)

    def test_non_choice_original_cannot_publish_picture_answer_buttons(self):
        reply=self.reply();before=deepcopy(reply)
        result=self.parsed(reply,self.result(type='unsupported'))
        self.assertEqual(result['steps'][0]['visual'],{'kind':'paper_region','region':self.region})
        self.assertEqual(result['assessment']['status'],'guidance_only')
        self.assertEqual(teaching_view(reply,self.result(type='unsupported'))['steps'][0]['visual']['kind'],'paper_region')
        self.assertEqual(reply,before)
        pending=deepcopy(reply);pending['assessment']['status']='needs_confirmation'
        self.assertEqual(teaching_view(pending,self.result(type='unsupported'))['assessment']['status'],'needs_confirmation')

    def test_neighbor_question_crop_is_downgraded(self):
        reply=self.reply();reply['steps'][0]['visual']['choices'][1]['region']={'x':0.82,'y':0.11,'width':0.1,'height':0.1}
        result=self.parsed(reply,self.result())
        self.assertEqual(result['steps'][0]['visual']['kind'],'paper_region')
        self.assertEqual(result['assessment']['status'],'guidance_only')
        self.assertNotIn('choices',result['steps'][0]['visual'])

    def test_real_choice_candidates_wholly_inside_original_question_remain_available(self):
        result=self.parsed(self.reply(),self.result())
        self.assertEqual(result['steps'][0]['visual']['kind'],'choices')
        self.assertEqual(len(result['steps'][0]['visual']['choices']),2)
        self.assertEqual(result['assessment']['status'],'incorrect')

    def test_missing_original_region_requires_confirmation_and_unclickable_whole_paper(self):
        result=self.parsed(self.reply(),self.result(region=None))
        self.assertEqual(result['steps'][0]['visual'],{'kind':'paper_region','region':{'x':0.0,'y':0.0,'width':1.0,'height':1.0}})
        self.assertEqual(result['assessment']['status'],'needs_confirmation')
        self.assertEqual(len(result['steps']),1)
