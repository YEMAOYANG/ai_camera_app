"""Original-image teaching is independent of pending paper grades; no paid AI."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import io
from PIL import Image

from integrations.ai.kimi_vision_provider import AiVisionResponse
from core.errors import ApiError
from services.homework_tutor_service import POLICY, SCHEMA, parse_response, teaching_view, teacher_input_image
from tests.test_homework_analysis import HomeworkTest
from tests.test_homework_tutor import teacher_reply


def image_observation(**updates):
    return {'status':'matched','basis':'original_image','questionLocated':True,
        'questionReadable':True,'studentAnswerReadable':True,'answerLocated':True,
        'prompt':'3 + 2 =','studentAnswer':'4','reason':'直接从原图看清当前小题和这个作答位置。',
        'questionRegion':{'x':.1,'y':.1,'width':.7,'height':.2},**updates}


def bound_image_contract():
    photo=Image.new('RGB',(800,1000),'white');output=io.BytesIO();photo.save(output,format='PNG')
    return teacher_input_image(output.getvalue(),photo,{},POLICY)[1]


class HomeworkOriginalImageGuidanceTests(TestCase):
    def result(self,**updates):
        return {'prompt':'3 + 2 =','studentAnswer':'4','confidence':None,
            'recognitionNeedsConfirmation':True,'annotationAmbiguous':False,
            'method':'tencent_question.v1','type':'arithmetic','status':'pending',
            'region':{'x':.1,'y':.1,'width':.7,'height':.2},
            'sourceValidation':{'provider':'tencent','trusted':False,
                'issues':['multiple_answer_alignment_unverified']},**updates}

    def parse(self,reply=None,result=None,mode='explain',message=''):
        return parse_response(json.dumps(reply or teacher_reply(sourceCheck=image_observation()),ensure_ascii=False),
            policy=POLICY,result=result or self.result(),mode=mode,student_message=message)

    def test_pending_grade_cannot_publish_model_self_reported_teaching_or_audio(self):
        result=self.result();before=deepcopy(result)
        value=self.parse(result=result)
        self.assertEqual(value['teacherText'],teacher_reply()['teacherText'])
        self.assertEqual(value['steps'][0]['visual']['kind'],'groups')
        self.assertEqual(value['teachingScope'],'original_image_guidance')
        self.assertEqual(value['assessment']['status'],'guidance_only')
        self.assertFalse(value['assessment']['countsForAbility'])
        self.assertIsNone(value['assessment']['independent'])
        self.assertNotIn('verifiedReferenceAnswer',value['assessment'])
        stored={**value,'status':'ready','sourceImageContract':bound_image_contract(),'audio':{'status':'ready','storageKey':'owned-original-audio'}}
        published=teaching_view(stored,result)
        self.assertEqual(published['audio']['status'],'unavailable')
        self.assertEqual(published['assessment']['status'],'needs_confirmation')
        self.assertEqual(published['assessment']['expectedAnswer'],'')
        self.assertEqual(result,before)

    def test_teacher_can_correct_ocr_observation_and_preserve_actual_blank_without_parent(self):
        reply=teacher_reply(sourceCheck=image_observation(status='matched',prompt='4 - □ = 3',studentAnswer='□'),
            teacherText='这里的空格还没有填。我们想一想，四拿走几会剩下三。',
            assessment={'status':'guidance_only','reason':'看原题讲方法','expectedAnswer':'1'},
            steps=[{'text':'看这个原来的空格，先不把参考答案当成你写过的答案。',
                'visual':{'kind':'paper_region','region':{'x':.1,'y':.1,'width':.7,'height':.2}}}])
        value=self.parse(reply,self.result(prompt='4 - 1 = 3',studentAnswer='1'))
        self.assertEqual(value['sourceCheck']['status'],'mismatch')
        self.assertEqual(value['sourceCheck']['studentAnswer'],'□')
        self.assertEqual(value['assessment']['status'],'guidance_only')
        self.assertEqual(value['assessment']['expectedAnswer'],'1')
        self.assertEqual(value['teacherText'],reply['teacherText'])
        self.assertNotIn('sourceConfirmationOnly',value)

    def test_clear_question_can_be_taught_when_original_handwriting_is_unreadable(self):
        reply=teacher_reply(sourceCheck=image_observation(status='unclear',studentAnswer='',
            studentAnswerReadable=False,answerLocated=False),teacherText='原来的手写字看不清，我们先学这道题怎么计算。')
        value=self.parse(reply)
        self.assertEqual(value['assessment']['status'],'guidance_only')
        self.assertFalse(value['assessment']['originalAnswerObserved'])
        self.assertEqual(value['assessment']['feedbackTarget'],'original_question')
        self.assertEqual(value['teacherText'],reply['teacherText'])

    def test_unclear_or_unlocated_question_still_cannot_publish_a_guessed_answer(self):
        for update in ({'questionReadable':False},{'questionLocated':False},{'prompt':''},
                {'prompt':'请看原图中的这道题。'},{'basis':None}):
            with self.subTest(update=update):
                observation=image_observation(**update)
                if update=={'basis':None}: observation.pop('basis')
                value=self.parse(teacher_reply(sourceCheck=observation,teacherText='答案是六，孩子已经会了。'))
                self.assertEqual(value['assessment']['status'],'needs_confirmation')
                self.assertEqual(value['assessment']['expectedAnswer'],'')
                self.assertNotIn('答案是六',value['teacherText'])

    def test_trusted_old_ocr_cannot_override_explicitly_unreadable_original_image(self):
        result=self.result(confidence=.99,recognitionNeedsConfirmation=False,
            method='decimal_arithmetic.v1',expectedAnswer='5')
        value=self.parse(teacher_reply(sourceCheck=image_observation(questionReadable=False)),result)
        self.assertEqual(value['assessment']['status'],'needs_confirmation')
        self.assertTrue(value['sourceConfirmationOnly'])

    def test_truly_unreadable_question_keeps_specific_source_limitation_in_safe_narration(self):
        observation=image_observation(status='unclear',questionReadable=False,
            reason='右边的最后一行条件被手指挡住了。')
        reply=teacher_reply(sourceCheck=observation,teacherText='猜一猜答案是六。')
        value=self.parse(reply)
        self.assertIn('最后一行条件被手指挡住',value['teacherText'])
        self.assertNotIn('答案是六',value['teacherText'])
        self.assertNotIn('家长',value['teacherText'])
        self.assertEqual(value['steps'][0]['visual']['region'],observation['questionRegion'])
        stored={**value,'status':'ready','sourceImageContract':bound_image_contract(),'audio':{'status':'ready','storageKey':'source-location-audio'}}
        self.assertEqual(teaching_view(stored,self.result())['audio']['status'],'unavailable')

    def test_observed_arithmetic_guard_rejects_wrong_reference_even_if_receipt_pending(self):
        reply=teacher_reply(sourceCheck=image_observation(),teacherText='三加二等于六。',
            assessment={'status':'correct','reason':'模型算错','expectedAnswer':'6'})
        value=self.parse(reply)
        self.assertEqual(value['assessment']['status'],'needs_confirmation')
        self.assertNotIn('等于六',value['teacherText'])
        self.assertTrue(value['sourceConfirmationOnly'])
        # Later DTO projection cannot accidentally revive rejected narration.
        stored={**value,'status':'ready','sourceImageContract':bound_image_contract(),'audio':{'status':'ready','storageKey':'safe-confirmation'}}
        projected=teaching_view(stored,self.result())
        self.assertEqual(projected['assessment']['status'],'needs_confirmation')
        self.assertNotIn('等于六',projected['teacherText'])
        self.assertEqual(projected['assessment']['expectedAnswer'],'')

    def test_stale_exact_ocr_is_not_reused_as_reference_for_changed_original_expression(self):
        result=self.result(prompt='3+2=',studentAnswer='4',confidence=.99,recognitionNeedsConfirmation=False,
            method='decimal_arithmetic.v1',expectedAnswer='5')
        reply=teacher_reply(sourceCheck=image_observation(status='mismatch',prompt='3+3=',studentAnswer='4'),
            teacherText='图上是三加三，两组都是三。',
            assessment={'status':'guidance_only','reason':'按看清的原图讲解','expectedAnswer':'6'},
            steps=[{'text':'两组三颗合起来。','visual':{'kind':'groups','groups':[3,3]}}])
        value=self.parse(reply,result)
        self.assertEqual(value['teacherText'],reply['teacherText'])
        self.assertEqual(value['steps'][0]['visual']['kind'],'groups')
        self.assertEqual(value['assessment']['expectedAnswer'],'6')
        self.assertNotIn('verifiedReferenceAnswer',value['assessment'])

    def test_multiple_answers_require_this_answer_ordinal_for_original_answer_observation(self):
        result=self.result(sourceAnswerOrdinal=2,sourceAnswerCount=4)
        for ordinal,expected in ((1,False),(2,True),(None,False)):
            with self.subTest(ordinal=ordinal):
                observation=image_observation()
                if ordinal is not None: observation['answerOrdinal']=ordinal
                value=self.parse(teacher_reply(sourceCheck=observation),result)
                self.assertEqual(value['assessment']['originalAnswerObserved'],expected)
                self.assertEqual(value['assessment']['status'],'guidance_only')

    def test_only_explicit_answer_mode_has_current_message_feedback_target(self):
        for mode,message,expected in (('explain','5','original_question'),('followup','是不是5','original_question'),
                ('answer','','original_question'),('answer','我这次填5','current_student_message')):
            with self.subTest(mode=mode,message=message):
                value=self.parse(mode=mode,message=message)
                self.assertEqual(value['assessment']['feedbackTarget'],expected)
                self.assertEqual(value['assessment']['status'],'guidance_only')

    def test_current_answer_feedback_does_not_guess_which_unaligned_blank_is_selected(self):
        result=self.result(sourceAnswerOrdinal=2,sourceAnswerCount=3)
        for update in ({'answerOrdinal':1},{'answerLocated':False,'answerOrdinal':2}):
            with self.subTest(update=update):
                value=self.parse(teacher_reply(sourceCheck=image_observation(**update)),result,
                    mode='answer',message='我这次填5')
                self.assertEqual(value['assessment']['feedbackTarget'],'original_question')
                self.assertFalse(value['assessment']['originalAnswerObserved'])
                self.assertEqual(value['assessment']['status'],'guidance_only')

    def test_pending_picture_choices_remain_unclickable_source_guidance(self):
        reply=teacher_reply(sourceCheck=image_observation(),steps=[{'text':'先看原题的候选图片。',
            'visual':{'kind':'choices','choices':[
                {'region':{'x':.12,'y':.11,'width':.2,'height':.1}},
                {'region':{'x':.45,'y':.11,'width':.2,'height':.1}}]}}])
        value=self.parse(reply,self.result(type='choice'))
        self.assertEqual(value['steps'][0]['visual']['kind'],'paper_region')
        self.assertEqual(value['assessment']['status'],'guidance_only')

    def test_observation_flags_and_positions_are_strict(self):
        for update in ({'questionReadable':1},{'studentAnswerReadable':'yes'},{'basis':'ocr'},
                {'answerOrdinal':True},{'answerOrdinal':201},{'questionRegion':{'x':0,'y':0,'width':2,'height':1}}):
            with self.subTest(update=update),self.assertRaises(ValueError):
                self.parse(teacher_reply(sourceCheck=image_observation(**update)))


class HomeworkOriginalImageTeacherFlowTests(TestCase):
    def setUp(self):
        HomeworkTest.setUp(self)
        self.service.tutor.policy={**self.service.tutor.policy,'unreferencedTencentImageTeaching':True}
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    events=HomeworkTest.events

    def seed_turns(self,submission,item,count,*,current=True,status='ready'):
        for index in range(count):
            identity=f'hwt_seed_{index}'
            value={'schemaVersion':SCHEMA,'id':identity,'itemRevision':item['revision'],
                'submissionRevision':submission['revision'] if current else submission['revision']-1,
                'familyId':'family-a','childId':'child-a','ordinal':index+1,'createdAt':self.clock(),
                'mode':'followup','message':'讲讲原题','status':status,'teacherText':'这次是指导。',
                'steps':[],'assessment':None,'audio':{'status':'unavailable'}}
            self.db.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (identity,submission['id'],item['id'],identity,'seed',json.dumps(value),self.clock()))
        self.db.raw.commit()

    def request(self,item,*,key='next-guidance'):
        return {'itemRevision':item['revision'],'idempotencyKey':key,'mode':'explain','message':''}

    def assert_public_turn_contract(self,turn):
        self.assertIsInstance(turn['teacherText'],str)
        self.assertIsInstance(turn['steps'],list)
        if turn['assessment'] is not None:
            self.assertIn(turn['assessment']['status'],{'correct','incorrect','guidance_only','needs_confirmation'})
            self.assertIsInstance(turn['assessment']['reason'],str)
            self.assertIsInstance(turn['assessment']['expectedAnswer'],str)
            self.assertFalse(turn['assessment']['countsForAbility'])
        for field in ('sourceCheck','teachingScope','sourceConfirmationOnly','feedbackTarget'):
            if field in turn: self.assertIsNotNone(turn[field])

    def test_queued_and_working_public_turns_keep_null_assessment_and_complete_empty_types(self):
        self.raw['confidence']=.2
        submission=self.ready();item=submission['items'][0]
        response=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        queued=response['tutor']['turns'][0]
        self.assert_public_turn_contract(queued)
        self.assertEqual(queued['status'],'queued')
        self.assertIsNone(queued['assessment'])
        self.assertEqual(queued['teacherText'],'')
        self.assertEqual(queued['steps'],[])
        self.assertNotIn('sourceConfirmationOnly',queued)
        self.assertNotIn('feedbackTarget',queued)
        value=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()['result_json'])
        value.update(status='working',teacherText=None,steps=None,assessment=None)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(json.dumps(value),queued['id']))
        self.db.raw.commit()
        working=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assert_public_turn_contract(working)
        self.assertEqual(working['status'],'working')
        self.assertIsNone(working['assessment'])
        self.assertEqual(working['teacherText'],'')
        self.assertEqual(working['steps'],[])
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_ready_image_guidance_public_turn_exposes_feedback_target_with_source_check(self):
        self.raw['confidence']=.2
        submission=self.ready();item=submission['items'][0]
        request={**self.request(item),'mode':'answer','message':'我现在填5'}
        self.service.tutor.submit('student-a',submission['id'],item['id'],request)
        self.provider.analyze_image.return_value=AiVisionResponse(json.dumps(teacher_reply(sourceCheck=image_observation())),'fixture','fixture-vision')
        self.provider.analyze_image.side_effect=None
        self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        ready=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assert_public_turn_contract(ready)
        self.assertEqual(ready['status'],'ready')
        self.assertNotIn('teachingScope',ready)
        self.assertNotIn('feedbackTarget',ready)
        self.assertEqual(ready['assessment']['status'],'needs_confirmation')
        self.assertEqual(ready['teachingQuality']['status'],'needs_review')
        self.assertEqual(ready['audio']['status'],'unavailable')

    def test_ready_source_confirmation_public_turn_exposes_flag_and_keeps_original_receipt(self):
        submission=self.ready();item=submission['items'][0]
        first=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))['tutor']['turns'][0]
        self.provider.analyze_image.return_value=AiVisionResponse(json.dumps(teacher_reply(sourceCheck={
            'status':'unclear','reason':'原图题干被挡住。'})),'fixture','fixture-vision')
        self.provider.analyze_image.side_effect=None
        self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        original=self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(first['id'],)).fetchone()['result_json']
        confirmed=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assert_public_turn_contract(confirmed)
        self.assertIs(confirmed['sourceConfirmationOnly'],True)
        self.assertEqual(confirmed['assessment']['status'],'needs_confirmation')
        self.assertNotIn('feedbackTarget',confirmed)
        self.assertNotIn('teachingScope',confirmed)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(first['id'],)).fetchone()['result_json'],original)
        self.assertEqual(self.provider.analyze_image.call_count,2)

    def test_each_item_still_has_twenty_turns_and_reading_cannot_dispatch(self):
        submission=self.ready();item=submission['items'][0]
        self.seed_turns(submission,item,20)
        calls=self.provider.analyze_image.call_count
        for _ in range(3):
            tutor=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']
            self.assertEqual(tutor['remainingTurnsPerItem'],0)
            self.assertEqual(tutor['remainingCallsPerSubmission'],180)
        with self.assertRaises(ApiError) as rejected:
            self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        self.assertEqual(rejected.exception.code,'homework_tutor_limit')
        self.assertNotIn('今天',str(rejected.exception))
        self.assertEqual(self.provider.analyze_image.call_count,calls)

    def test_submission_limit_cumulatively_keeps_past_revision_and_unknown_reservations(self):
        submission=self.ready();item=submission['items'][0]
        self.seed_turns(submission,item,200,current=False,status='unknown')
        tutor=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']
        self.assertEqual(tutor['remainingTurnsPerItem'],20)
        self.assertEqual(tutor['remainingCallsPerSubmission'],0)
        with self.assertRaises(ApiError) as rejected:
            self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        self.assertEqual(rejected.exception.code,'homework_tutor_limit')
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_last_reserved_turn_reaches_two_hundred_and_replay_uses_no_extra_slot(self):
        submission=self.ready();item=submission['items'][0]
        self.seed_turns(submission,item,199,current=False)
        request=self.request(item)
        first=self.service.tutor.submit('student-a',submission['id'],item['id'],request)
        self.assertEqual(first['tutor']['remainingCallsPerSubmission'],0)
        self.assertEqual(first['tutor']['remainingTurnsPerItem'],19)
        self.assertEqual(self.service.tutor.submit('student-a',submission['id'],item['id'],request),first)
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_old_thirty_call_cap_does_not_block_later_questions_in_sixty_six_item_work(self):
        submission=self.ready();item=submission['items'][0]
        self.seed_turns(submission,item,66,current=False)
        response=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        self.assertEqual(response['tutor']['remainingCallsPerSubmission'],133)
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_current_unknown_turn_keeps_its_slot_and_blocks_a_new_paid_key(self):
        submission=self.ready();item=submission['items'][0]
        self.seed_turns(submission,item,1,status='unknown')
        tutor=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']
        self.assertEqual(tutor['remainingCallsPerSubmission'],199)
        self.assertEqual(tutor['remainingTurnsPerItem'],19)
        with self.assertRaises(ApiError) as rejected:
            self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        self.assertEqual(rejected.exception.code,'homework_tutor_pending')
        self.assertEqual(self.provider.analyze_image.call_count,1)

    def test_pending_multi_answer_turn_has_original_image_target_history_audio_and_no_grade_write(self):
        self.raw['confidence']=.2
        submission=self.ready();item=submission['items'][0]
        saved=json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json'])
        saved.update(method='tencent_question.v1',confidence=None,recognitionNeedsConfirmation=True,
            sourceTitle='把正确的数填在空格里',ancestorContext=['第二大题'],sourceAnswerOrdinal=2,sourceAnswerCount=3,
            answerRegions=[{'x':.4,'y':.15,'width':.1,'height':.05}],
            providerAssessment={'answerRegion':{'x':.4,'y':.15,'width':.1,'height':.05}},
            sourceValidation={'provider':'tencent','trusted':False,'issues':['multiple_answer_alignment_unverified']})
        original=json.dumps(saved,ensure_ascii=False,sort_keys=True)
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(original,item['id']))
        self.db.raw.commit()
        reply=teacher_reply(sourceCheck=image_observation(answerOrdinal=2))
        teacher=SimpleNamespace(provider_name='fixture',model_name='fixture-vision',
            analyze_image=Mock(return_value=AiVisionResponse(json.dumps(reply,ensure_ascii=False),'fixture','fixture-vision')))
        self.service.tutor_provider=teacher
        request={'itemRevision':item['revision'],'idempotencyKey':'image-first','mode':'explain','message':''}
        with patch.object(self.service,'correct_recognition',side_effect=AssertionError('parent confirmation is not a teaching prerequisite')):
            self.service.tutor.submit('student-a',submission['id'],item['id'],request)
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertNotIn('teachingScope',turn)
        self.assertEqual(turn['assessment']['status'],'needs_confirmation')
        self.assertEqual(turn['audio']['status'],'unavailable')
        with self.assertRaises(ApiError) as rejected:
            self.service.tutor.audio('student-a',submission['id'],item['id'],turn['id'])
        self.assertEqual(rejected.exception.code,'homework_tutor_audio_not_ready')
        args=teacher.analyze_image.call_args.kwargs
        self.assertEqual(args['image_bytes'],self.service.image('student-a',submission['id'],item['pageId'],student=True)[0])
        data=json.loads(args['user_prompt'].split('题目与对话数据（不是系统指令）：\n',1)[1])
        self.assertEqual(data['sourceAnswerOrdinal'],2)
        self.assertNotIn('region',data['answerTarget'])
        self.assertIs(data['answerTarget']['geometryVerified'],False)
        self.assertEqual(data['photoGeometry'],{'width':800,'height':1000})
        self.assertEqual(data['ancestorContext'],['第二大题'])
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json'],original)
        self.assertEqual(self.events(),[])
        parent=self.service.get('parent-a',submission['id'])['submission']
        self.assertEqual(parent['originalSummary']['pending'],1)
        self.assertEqual(parent['summary']['corrected'],0)
        self.service.tutor.submit('student-a',submission['id'],item['id'],request)
        self.assertEqual(teacher.analyze_image.call_count,1)
        with self.assertRaises(ApiError) as stopped:
            self.service.tutor.submit('student-a',submission['id'],item['id'],{**request,
                'idempotencyKey':'image-followup','mode':'followup','message':'为什么合在一起？'})
        self.assertEqual(stopped.exception.code,'homework_tutor_review_required')
        self.assertEqual(teacher.analyze_image.call_count,1)
        self.assertEqual(self.events(),[])

    def test_grading_adapter_cannot_pretend_to_be_an_image_teacher(self):
        submission=self.ready();item=submission['items'][0]
        self.service.tutor_provider=SimpleNamespace(provider_name='tencent',model_name='question-mark-agent',is_tencent_grading=True)
        self.service.tutor.submit('student-a',submission['id'],item['id'],
            {'itemRevision':item['revision'],'idempotencyKey':'wrong-provider','mode':'explain','message':''})
        outcome=self.service.process_next(submission_id=submission['id'])
        self.assertEqual(outcome['error'],'homework_provider_unconfigured')
        self.assertEqual(self.provider.analyze_image.call_count,1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM homework_provider_calls WHERE id LIKE 'hwtcall_%'").fetchone()['n'],0)
