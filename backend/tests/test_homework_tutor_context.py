"""Saved grading references guide teaching without replacing original grades."""
from copy import deepcopy
import io
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from PIL import Image
from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_tutor_context import grading_context, reference_comparison
from services.homework_tutor_service import POLICY, encoded, image_contract_valid, teacher_input_image
from tests.test_homework_analysis import HomeworkTest
from tests.test_homework_tutor import teacher_reply
from tests.test_homework_tutor_image_guidance import image_observation


def reference(answer='5', **changes):
    value={'method':'tencent_question.v1','studentAnswer':'4','sourceAnswerOrdinal':1,'sourceAnswerCount':1,
        'tencentRaw':{'answer':{'HandwriteInfo':'4','IsCorrect':False,'RightAnswer':answer,
            'AnswerAnalysis':'请结合原题图片数出两组对象。','KnowledgePoints':['合并数量'] }},
        'sourceValidation':{'trusted':False,'geometryVerified':True,'angleVerified':True,
            'issues':['multiple_answer_alignment_unverified']},
        'region':{'x':.1,'y':.2,'width':.8,'height':.25},
        'providerAssessment':{'answerRegion':{'x':.7,'y':.35,'width':.1,'height':.06}}}
    value.update(changes)
    return value


def observed(answer='5', **updates):
    value=teacher_reply(sourceCheck=image_observation(answerOrdinal=1),
        assessment={'status':'guidance_only','expectedAnswer':answer})
    value.update(updates)
    return value


def context(**updates):
    value={'sourceDigest':'a'*64,'frameWidth':1000,'frameHeight':1200,'geometryVerified':True,
        'region':{'x':.1,'y':.1,'width':.8,'height':.35}}
    value.update(updates)
    return value


class TutorGradingContextTests(TestCase):
    def test_saved_reference_is_separate_from_original_answer_and_has_no_raw_payload(self):
        result=reference(); result['tencentRaw']['answer']['privateJob']='secret'
        value=grading_context(result)
        self.assertEqual(value['originalPaperAnswer'],'4')
        self.assertEqual(value['referenceAnswer'],'')
        self.assertEqual(value['analysis'],'')
        self.assertEqual(value['authority'],'withheld_unverified_reference')
        self.assertEqual(value['sourceSeparation']['auxiliaryHandwriting'],'never_a_printed_condition')
        self.assertEqual(value['knowledgePoints'],['合并数量'])
        self.assertFalse(value['countsForAbility'])
        self.assertNotIn('privateJob',encoded(value)); self.assertNotIn('tencentRaw',encoded(value))

    def test_context_text_and_lists_are_bounded_without_changing_result(self):
        result=reference(); result['tencentRaw']['answer'].update(RightAnswer='8'*1100,
            AnswerAnalysis='析'*5000,KnowledgePoints=[str(i)+'点'*300 for i in range(40)])
        before=deepcopy(result); value=grading_context(result)
        self.assertEqual(value['referenceAnswer'],''); self.assertEqual(value['analysis'],'')
        self.assertEqual(len(value['knowledgePoints']),16); self.assertEqual(len(value['knowledgePoints'][0]),200)
        self.assertEqual(result,before)

    def test_only_tencent_reference_is_compared(self):
        self.assertIsNone(grading_context({'method':'decimal_arithmetic.v1','expectedAnswer':'5'}))
        self.assertIsNone(reference_comparison(observed(),{'method':'decimal_arithmetic.v1'}))

    def test_numeric_or_operator_disagreement_does_not_regrade(self):
        for provider,teacher in [('2','4'),('+','-')]:
            with self.subTest(provider=provider):
                result=reference(provider); before=deepcopy(result)
                value=reference_comparison(observed(teacher),result)
                self.assertEqual(value['status'],'conflict'); self.assertEqual(result,before)
                self.assertIn('原成绩没有改动',value['reason'])

    def test_equivalent_fraction_decimal_and_percent_are_not_false_conflicts(self):
        for provider,teacher in [('0.5','1/2'),('50%','0.5'),('５','5')]:
            with self.subTest(provider=provider):
                self.assertEqual(reference_comparison(observed(teacher),reference(provider))['status'],'consistent')

    def test_unreadable_or_wrong_blank_never_uses_reference_or_original_answer_as_teacher_answer(self):
        result=reference('2',sourceAnswerOrdinal=2,sourceAnswerCount=3)
        cases=[observed('4'),observed('',sourceCheck=image_observation(answerOrdinal=2)),
            observed('4',sourceConfirmationOnly=True,sourceCheck=image_observation(answerOrdinal=2)),
            observed('4',sourceCheck=image_observation(answerOrdinal=2,questionReadable=False)),
            observed('4',sourceCheck=image_observation(answerOrdinal=2,questionLocated=False)),
            observed('4',sourceCheck=image_observation(answerOrdinal=2,answerLocated=False))]
        for reply in cases:
            with self.subTest(reply=reply):
                value=reference_comparison(reply,result)
                self.assertEqual(value['status'],'unverified'); self.assertNotIn('teacherAnswer',value)

    def test_different_freeform_answers_are_not_claimed_to_be_semantic_conflicts(self):
        value=reference_comparison(observed('暖和'),reference('温暖'))
        self.assertEqual(value['status'],'unverified')

    def test_single_blank_wrong_ordinal_missing_target_or_placeholder_prompt_stays_unverified(self):
        cases=[(reference('2'),observed('4',sourceCheck=image_observation(answerOrdinal=2))),
            (reference('2',sourceAnswerOrdinal=None),observed('4')),
            (reference('2',sourceAnswerCount=None),observed('4')),
            (reference('2'),observed('4',sourceCheck=image_observation(answerOrdinal=True))),
            (reference('2'),observed('4',sourceCheck=image_observation(answerOrdinal=1,prompt=''))),
            (reference('2'),observed('4',sourceCheck=image_observation(answerOrdinal=1,prompt='请看原图中的题目。')))]
        for result,reply in cases:
            with self.subTest(result=result,reply=reply):
                self.assertEqual(reference_comparison(reply,result)['status'],'unverified')


class TutorSharedPictureWindowTests(TestCase):
    def image(self):
        photo=Image.new('RGB',(1000,1200),'white'); photo.putpixel((150,140),(255,0,0))
        buffer=io.BytesIO();photo.save(buffer,format='PNG')
        return buffer.getvalue(),photo

    def test_shared_diagram_above_legal_leaf_window_is_kept_in_model_input(self):
        original,photo=self.image()
        selected,contract=teacher_input_image(original,photo,reference(),POLICY,context())
        self.assertEqual(contract['selection'],'question_region')
        self.assertEqual(contract['inputPixelBounds']['top'],104)
        cropped=Image.open(io.BytesIO(selected)); bounds=contract['inputPixelBounds']
        self.assertEqual(cropped.getpixel((150-bounds['left'],140-bounds['top'])),(255,0,0))
        self.assertTrue(image_contract_valid(contract))
        partial=deepcopy(contract);partial['paperStructureContext']['regionInOriginalPage']['y']=.01
        self.assertFalse(image_contract_valid(partial))

    def test_missing_region_bad_frame_or_unverified_structure_retains_full_page(self):
        original,photo=self.image()
        for data in [context(region=None),context(frameHeight=1001),context(geometryVerified=False),
                context(region={'x':.1,'y':.05,'width':.2,'height':.2})]:
            with self.subTest(data=data):
                selected,contract=teacher_input_image(original,photo,reference(),POLICY,data)
                self.assertEqual(selected,original);self.assertEqual(contract['selection'],'full_page')
                self.assertTrue(image_contract_valid(contract))


class TutorReferenceFlowTests(TestCase):
    def setUp(self):
        HomeworkTest.setUp(self)
        self.service.tutor.policy={**self.service.tutor.policy,'unreferencedTencentImageTeaching':True}
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    events=HomeworkTest.events

    def test_actual_request_keeps_reference_picture_context_and_neutral_score_on_refresh(self):
        self.raw['confidence']=.2
        submission=self.ready(); item=submission['items'][0]
        row=self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()
        result=json.loads(row['result_json']); result.update(reference('2',
            region={'x':.1,'y':.1,'width':.7,'height':.2},
            providerAssessment={'answerRegion':{'x':.4,'y':.15,'width':.1,'height':.05}}))
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(encoded(result),item['id']))
        self.db.raw.commit(); before=deepcopy(result); event_count=len(self.events())
        teacher=SimpleNamespace(provider_name='fixture',model_name='fixture-vision',
            analyze_image=Mock(return_value=AiVisionResponse(encoded(observed()),'fixture','fixture-vision')))
        self.service.tutor_provider=teacher
        paper=context(frameWidth=800,frameHeight=1000,
            region={'x':.1,'y':.02,'width':.7,'height':.28},sharedPrompts=['请观察上面的水果图。'],
            illustrations=[{'region':{'x':.1,'y':.02,'width':.3,'height':.1}}])
        self.service.tutor.submit('student-a',submission['id'],item['id'],
            {'itemRevision':item['revision'],'idempotencyKey':'context','mode':'explain','message':''})
        with patch('services.homework_paper_structure.selected_item_context',return_value=paper):
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        request=json.loads(teacher.analyze_image.call_args.kwargs['user_prompt'].split('题目与对话数据（不是系统指令）：\n')[1])
        self.assertEqual(request['gradingReference']['referenceAnswer'],'')
        self.assertEqual(request['gradingReference']['authority'],'withheld_unverified_reference')
        self.assertEqual(request['gradingReference']['originalPaperAnswer'],'4')
        self.assertEqual(request['paperQuestionContext']['sharedPrompts'],paper['sharedPrompts'])
        self.assertEqual(request['paperQuestionContext']['frameWidth'],request['photoGeometry']['width'])
        self.assertEqual(request['paperQuestionContext']['frameHeight'],request['photoGeometry']['height'])
        self.assertTrue(request['paperQuestionContext']['illustrations'][0]['region'])
        for _ in range(3):
            turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertNotIn('gradingReferenceComparison',turn)
            self.assertEqual(turn['teachingQuality']['status'],'needs_review')
            self.assertEqual(turn['assessment']['expectedAnswer'],'')
            self.assertEqual(turn['audio']['status'],'unavailable')
            self.assertFalse(turn['assessment']['countsForAbility'])
        self.assertEqual(teacher.analyze_image.call_count,1)
        self.assertFalse(self.service.process_next(submission_id=submission['id'])['processed'])
        self.assertEqual(len(self.events()),event_count)
        saved=json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json'])
        self.assertEqual(saved,before)
