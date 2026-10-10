"""Teacher questions are not mastery and invented diagrams are not source proof."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_tutor_service import POLICY, parse_response, teaching_view, trusted_exact_reference
from tests.test_homework_analysis import HomeworkTest
from tests.test_homework_tutor import teacher_reply


class HomeworkTutorGuardrailTests(TestCase):
    region={'x':.1,'y':.1,'width':.7,'height':.2}

    def result(self,**changes):
        return {'prompt':'3 + 2 =','studentAnswer':'4','confidence':.99,'region':self.region,
            'method':'decimal_arithmetic.v1','expectedAnswer':'5',**changes}

    def reply(self,**changes):
        return {'sourceCheck':{'status':'matched','reason':'已核对原图'},
            'teacherText':'把两组放在一起数一数。',
            'assessment':{'status':'correct','reason':'模型声称答对','expectedAnswer':'5'},
            'steps':[{'text':'三颗和两颗合起来。','visual':{'kind':'groups','groups':[3,2]}}],**changes}

    def parse(self,reply=None,result=None,mode='followup'):
        return parse_response(json.dumps(reply or self.reply(),ensure_ascii=False),
            policy=POLICY,result=result or self.result(),mode=mode)

    def test_explanation_or_followup_never_assesses_even_if_message_contains_answer(self):
        for mode in ('explain','followup'):
            with self.subTest(mode=mode):
                value=self.parse(mode=mode)
                self.assertEqual(value['assessment']['status'],'guidance_only')
                self.assertFalse(value['assessment']['countsForAbility'])
                self.assertIsNone(value['assessment']['independent'])
        self.assertEqual(self.parse(mode='answer')['assessment']['status'],'correct')

    def test_saved_followup_read_projection_cannot_restore_model_correctness(self):
        original={**self.reply(),'status':'ready','mode':'followup'};before=deepcopy(original)
        value=teaching_view(original,self.result())
        self.assertEqual(value['assessment']['status'],'guidance_only')
        self.assertEqual(original,before)

    def test_removal_groups_fall_back_to_owned_photo(self):
        result=self.result(prompt='5 - 2 =',expectedAnswer='3')
        reply=self.reply(teacherText='拿走两颗，数一数还剩三颗。',
            assessment={'status':'incorrect','reason':'','expectedAnswer':'3'},
            steps=[{'text':'五颗拿走两颗。','visual':{'kind':'groups','groups':[5,2]}}])
        value=self.parse(reply,result,mode='answer')
        self.assertEqual(value['steps'][0]['visual'],{'kind':'paper_region','region':self.region})
        self.assertEqual(value['assessment']['status'],'guidance_only')

    def test_zero_quantity_and_groups_cannot_fake_fraction_diagram(self):
        result=self.result(prompt='比较1/2和1/3',method='ai_guidance',expectedAnswer=None)
        for image in ({'kind':'quantity','count':0},{'kind':'groups','groups':[1,2]}):
            with self.subTest(image=image):
                value=self.parse(self.reply(teacherText='我们用分数比较。',
                    steps=[{'text':'看二分之一。','visual':image}]),result)
                self.assertEqual(value['steps'][0]['visual']['kind'],'paper_region')
                self.assertFalse(value['assessment']['countsForAbility'])

    def test_addition_groups_match_source_operands_and_classification_remains_possible(self):
        value=self.parse(self.reply(steps=[{'text':'合起来数。','visual':{'kind':'groups','groups':[4,1]}}]),mode='answer')
        self.assertEqual(value['steps'][0]['visual']['kind'],'paper_region')
        self.assertEqual(self.parse()['steps'][0]['visual']['kind'],'groups')
        result=self.result(prompt='把红色和蓝色的珠子分组',method='ai_guidance',expectedAnswer=None)
        self.assertEqual(self.parse(self.reply(),result)['steps'][0]['visual']['kind'],'groups')

    def test_null_confidence_without_strict_trust_requires_confirmation(self):
        result=self.result(confidence=None,method='tencent_question.v1',recognitionConfirmed=False,
            sourceValidation={'provider':'tencent','trusted':True,'issues':[]})
        self.assertEqual(self.parse(result=result)['assessment']['status'],'needs_confirmation')
        trusted={**result,'sourceValidation':{'provider':'tencent','scope':'paper_answer_unknown_help',
            'trusted':True,'strictIsCorrect':True,'studentAnswerPresent':True,
            'geometryVerified':True,'angleVerified':True,'issues':[]}}
        value=self.parse(result=trusted)
        self.assertEqual(value['assessment']['status'],'guidance_only')
        self.assertEqual(value['steps'][0]['visual']['kind'],'groups')
        for field in ('strictIsCorrect','studentAnswerPresent','geometryVerified','angleVerified'):
            with self.subTest(field=field):
                changed=deepcopy(trusted);changed['sourceValidation'][field]=False
                self.assertEqual(self.parse(result=changed)['assessment']['status'],'needs_confirmation')

    def test_essay_guidance_uses_source_photo_without_fabricated_score_or_ocr_comparison(self):
        result=self.result(type='writing',prompt='根据原作文页和已保存建议讲解',confidence=None,
            method='tencent_essay.v1',expectedAnswer=None,region=None,recognitionConfirmed=False,
            sourceValidation={'provider':'tencent','scope':'guidance_only','trusted':False,'issues':[]})
        reply=self.reply(sourceCheck={'status':'matched','reason':'看清原作文页','prompt':'我的一天'},
            teacherText='看看原文，把句子说清楚。',
            assessment={'status':'correct','reason':'作文不错','expectedAnswer':'95分'},
            steps=[{'text':'看原来的句子。','visual':{'kind':'paper_region','region':{'x':0,'y':0,'width':1,'height':1}}}])
        value=self.parse(reply,result,mode='answer')
        self.assertEqual(value['sourceCheck']['status'],'matched')
        self.assertEqual(value['assessment']['status'],'guidance_only')
        self.assertEqual(value['assessment']['expectedAnswer'],'')
        self.assertFalse(value['assessment']['countsForAbility'])
        reply['sourceCheck']['status']='unclear'
        self.assertEqual(self.parse(reply,result)['assessment']['status'],'needs_confirmation')

    def hybrid(self,**changes):
        value=self.result(method='tencent_question.v1',correctionMethod='decimal_arithmetic.v1',
            confidence=None,recognitionConfirmed=False,recognitionNeedsConfirmation=False,
            annotationAmbiguous=False,deterministicValidation={
                'method':'decimal_arithmetic.v1','status':'incorrect','expectedAnswer':'5'},
            sourceValidation={'provider':'tencent','scope':'paper_answer_unknown_help','trusted':True,
                'strictIsCorrect':True,'studentAnswerPresent':True,'referenceAnswerPresent':True,
                'geometryVerified':True,'angleVerified':True,'issues':[]},
            tencentRaw={'answer':{'RightAnswer':'5.0','HandwriteInfo':'4','IsCorrect':False}})
        value.update(changes)
        return value

    def test_trusted_tencent_hybrid_wrong_reference_is_neutral_and_old_audio_disabled(self):
        reply=self.reply(teacherText='3加2等于6，你已经答对了。',
            assessment={'status':'correct','reason':'模型算错','expectedAnswer':'6'},
            steps=[{'text':'一共六颗。','visual':{'kind':'quantity','count':6}}])
        value=self.parse(reply,self.hybrid(),mode='answer')
        self.assertEqual(value['assessment']['status'],'needs_confirmation')
        self.assertEqual(value['assessment']['expectedAnswer'],'')
        self.assertEqual(value['steps'][0]['visual']['kind'],'paper_region')
        self.assertNotIn('等于6',value['teacherText'])
        historical={**reply,'status':'ready','mode':'followup','audio':{'status':'ready','url':'old-local-audio'}}
        view=teaching_view(historical,self.hybrid())
        self.assertEqual(view['audio']['status'],'unavailable')
        self.assertEqual(view['audio']['errorCode'],'homework_tutor_source_unconfirmed')
        self.assertEqual(historical['audio']['status'],'ready')

    def test_trusted_tencent_hybrid_correct_reply_gets_only_verified_local_reference(self):
        result=self.hybrid()
        self.assertEqual(trusted_exact_reference(result),{'method':'decimal_arithmetic.v1','expectedAnswer':'5'})
        value=self.parse(result=result,mode='answer')
        self.assertEqual(value['assessment']['verifiedReferenceAnswer'],'5')
        self.assertFalse(value['assessment']['countsForAbility'])
        self.assertIsNone(value['assessment']['independent'])
        self.assertEqual(value['steps'][0]['visual']['kind'],'groups')

    def test_untrusted_or_inconsistent_tencent_hybrid_cannot_supply_exact_reference(self):
        for update in (
            {'sourceValidation':{**self.hybrid()['sourceValidation'],'trusted':False}},
            {'deterministicValidation':{'method':'ai_guidance','expectedAnswer':'5'}},
            {'deterministicValidation':{'method':'decimal_arithmetic.v1','expectedAnswer':'6'}},
            {'tencentRaw':{'answer':{'RightAnswer':'6'}}},
        ):
            with self.subTest(update=update):
                result=self.hybrid(**update)
                self.assertIsNone(trusted_exact_reference(result))
                value=self.parse(result=result,mode='answer')
                self.assertEqual(value['assessment']['status'],'needs_confirmation')
                self.assertNotIn('verifiedReferenceAnswer',value['assessment'])


class HomeworkIndependentTeacherFlowTests(TestCase):
    def setUp(self):
        HomeworkTest.setUp(self)
        self.service.tutor.policy={**self.service.tutor.policy,'unreferencedTencentImageTeaching':True}
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    events=HomeworkTest.events

    def test_teacher_turn_uses_dedicated_provider_and_preserves_grading_receipt(self):
        submission=self.ready();item=submission['items'][0]
        grading_calls=self.provider.analyze_image.call_count
        response=teacher_reply(assessment={'status':'correct','reason':'模型称会了','expectedAnswer':'5'})
        teacher=SimpleNamespace(provider_name='deepseek',model_name='deepseek-flash',
            analyze_image=Mock(return_value=AiVisionResponse(json.dumps(response,ensure_ascii=False),'deepseek','deepseek-flash')))
        self.service.tutor_provider=teacher
        self.service.tutor.submit('student-a',submission['id'],item['id'],
            {'itemRevision':item['revision'],'idempotencyKey':'isolated-teacher','mode':'followup','message':'为什么要合起来？'})
        outcome=self.service.process_next(submission_id=submission['id'])
        self.assertTrue(outcome['ok'])
        self.assertEqual(teacher.analyze_image.call_count,1)
        self.assertEqual(self.provider.analyze_image.call_count,grading_calls)
        turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertEqual(turn['assessment']['status'],'guidance_only')
        self.assertFalse(turn['assessment']['countsForAbility'])
        call=self.db.execute("SELECT provider,model FROM homework_provider_calls WHERE id LIKE 'hwtcall_%'").fetchone()
        self.assertEqual((call['provider'],call['model']),('deepseek','deepseek-flash'))

    def test_actual_hybrid_turn_reuses_exact_reference_without_dispatching_conflicting_solver(self):
        submission=self.ready();item=submission['items'][0]
        result=HomeworkTutorGuardrailTests().hybrid()
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',
            (json.dumps(result,ensure_ascii=False),item['id']))
        reply=teacher_reply(teacherText='3加2等于6。',
            assessment={'status':'correct','reason':'错误计算','expectedAnswer':'6'},
            steps=[{'text':'一共六颗。','visual':{'kind':'quantity','count':6}}])
        teacher=SimpleNamespace(provider_name='deepseek',model_name='deepseek-flash',
            analyze_image=Mock(return_value=AiVisionResponse(json.dumps(reply,ensure_ascii=False),'deepseek','deepseek-flash')))
        self.service.tutor_provider=teacher
        self.service.tutor.submit('student-a',submission['id'],item['id'],
            {'itemRevision':item['revision'],'idempotencyKey':'hybrid-conflict','mode':'explain','message':''})
        outcome=self.service.process_next(submission_id=submission['id'])
        self.assertTrue(outcome['ok'])
        teacher.analyze_image.assert_not_called()
        turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertEqual(turn['assessment']['status'],'guidance_only')
        self.assertEqual(turn['assessment']['expectedAnswer'],'5')
        self.assertNotIn('等于6',turn['teacherText'])
        self.assertEqual(turn['steps'][0]['visual']['kind'],'paper_region')
