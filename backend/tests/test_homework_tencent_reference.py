"""Anonymous in-memory Tencent reuse and correction; no network/live database."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_answer_quality import (reference_for_correction, canonical_correction_answer,
    student_grading, teaching_quality, attach_reference_answer_layout)
from services.homework_tencent_lesson import lesson, plain_reference_text
from services.homework_tutor_service import HomeworkTutorService
from tests import test_homework_tencent_grading as fixtures
from tests import test_homework_analysis as analysis
from tests.test_homework_tutor import teacher_reply


def source():
    value=fixtures.NormalizerTest().normalize(fixtures.marks(prompt='看图：一共有几个苹果？',answer='4',right='5'))
    return value


class ReferenceGateTests(TestCase):
    def test_original_reference_is_available_without_claiming_human_or_mastery(self):
        raw=source();before=deepcopy(raw);reference=reference_for_correction(raw)
        self.assertEqual(reference['canonicalExpectedAnswer'],'5')
        self.assertEqual(reference['status'],'provider_consistent')
        self.assertFalse(reference['countsForAbility']);self.assertEqual(raw,before)
        grading=student_grading(raw)
        self.assertEqual(grading['referenceAnswer'],'5')
        self.assertEqual(grading['analysis'],raw['tencentRaw']['answer']['AnswerAnalysis'])
        self.assertEqual(grading['referenceGate']['status'],'provider_consistent')
        self.assertEqual(grading['studentQuality']['status'],'needs_review')
        self.assertEqual(grading['status'],'incorrect')

    def test_missing_conflicting_direction_and_handwriting_references_remain_blocked(self):
        for change in ('missing','reversal','annotation','arithmetic','verdict','geometry'):
            raw=source()
            if change=='missing':raw['tencentRaw']['answer']['RightAnswer']=''
            elif change=='reversal':raw['ancestorContext']=['向后转，雪雪排第几？']
            elif change=='annotation':raw['annotationAmbiguous']=True
            elif change=='arithmetic':raw['tencentRaw']['answer']['AnswerAnalysis']='3+2=6，所以答案是5。'
            elif change=='verdict':raw['tencentRaw']['answer']['IsCorrect']=True
            elif change=='geometry':raw['sourceValidation']['angleVerified']=False
            with self.subTest(change=change):
                self.assertIsNone(reference_for_correction(raw))
                self.assertFalse(student_grading(raw)['referenceGate']['available'])
                self.assertNotIn('referenceAnswer',student_grading(raw))

    def test_exact_derived_runtime_fields_do_not_change_reference_digest(self):
        raw=source();before=reference_for_correction(raw)['digest']
        raw.update(status='incorrect',answerMode='spoken',voiceTexts={'prompt':'音频'},explanation='派生副本')
        self.assertEqual(reference_for_correction(raw)['digest'],before)
        raw['tencentRaw']['answer']['AnswerAnalysis']='按原图逐个数。'
        self.assertNotEqual(reference_for_correction(raw)['digest'],before)

    def test_official_multi_blank_requires_complete_nonoverlapping_layout(self):
        raw=source();raw.update(sourceAnswerOrdinal=2,sourceAnswerCount=2)
        raw['sourceHierarchy'].update(answerIndex=2,answerCount=2)
        current=raw['providerAssessment']['answerRegion']
        other={**current,'x':.1,'width':.1}
        self.assertIsNone(reference_for_correction(raw))
        raw['_referenceAnswerLayout']=[{'ordinal':1,'count':2,'region':other,'geometryVerified':True},
            {'ordinal':2,'count':2,'region':current,'geometryVerified':True}]
        self.assertIsNotNone(reference_for_correction(raw))
        raw['_referenceAnswerLayout'][0]['region']=deepcopy(current)
        self.assertIsNone(reference_for_correction(raw))

    def test_real_spoken_short_answers_compare_deterministically(self):
        for actual,expected in [('答案是三','3'),('有三个','3'),('第二棵','2'),('3个','3'),('第十二题','12'),('二十二','22'),('一百','100'),('cat','cat')]:
            with self.subTest(actual=actual):self.assertEqual(canonical_correction_answer(actual),expected)
        for actual in ['因为图片很多所以可能是三','我不知道','答案是三或者四','A'*100]:
            self.assertIsNone(canonical_correction_answer(actual))

    def test_versioned_lesson_cannot_be_forged_by_changing_answer_or_steps(self):
        raw=source();ref=reference_for_correction(raw);reply=lesson(raw,ref)
        self.assertEqual(teaching_quality(reply,raw)['status'],'guidance')
        for key in ('assessment','steps'):
            changed=deepcopy(reply)
            if key=='assessment':changed[key]['expectedAnswer']='7'
            else:changed[key][0]['text']='答案是7'
            self.assertEqual(teaching_quality(changed,raw)['status'],'needs_review')
        self.assertEqual(plain_reference_text(r'$\boxed{4}\times2=8$'),'4乘2=8')


class TencentReferenceTutorTests(TestCase):
    setUp=fixtures.TencentPipelineTest.setUp
    create=analysis.HomeworkTest.create
    upload=analysis.HomeworkTest.upload
    queued=fixtures.TencentPipelineTest.queued
    due=fixtures.TencentPipelineTest.due
    error=analysis.HomeworkTest.error

    def prepare(self):
        from tests.test_homework_paper_structure import PaperStructureTest
        raw=fixtures.marks(prompt='看图：一共有几个苹果？',answer='4',right='5')
        PaperStructureTest.complete(self,submit=fixtures.source('看图：一共有几个苹果？'),result=raw)
        self.service.tutor=HomeworkTutorService(self.service)
        self.item=dict(self.service.repository.items(self.db,self.identity)[0])
        self.before_raw=self.item['result_json']
        self.main=SimpleNamespace(provider_name='fixture',model_name='fixture-tutor',analyze_image=Mock())
        self.service.tutor_provider=self.main
        self.calls_before=self.db.execute('SELECT COUNT(*) n FROM homework_provider_calls').fetchone()['n']
        self.voice_before=self.transport.call_count

    def turn(self,mode='explain',message='',key='ask-1'):
        return self.service.tutor.submit('student-a',self.identity,self.item['id'],
            {'itemRevision':self.item['revision'],'idempotencyKey':key,'mode':mode,'message':message})['tutor']

    def get(self):return self.service.tutor.get('student-a',self.identity,self.item['id'])['tutor']
    def work(self):return self.service.tutor.process_next(submission_id=self.identity)

    def test_explain_reuses_original_reference_and_voice_without_any_solver_call(self):
        self.prepare();first=self.turn()['turns'][-1]
        self.assertTrue(self.work()['ok']);shown=self.get()['turns'][-1]
        self.assertEqual(shown['teachingQuality']['status'],'guidance');self.assertEqual(shown['audio']['status'],'ready')
        self.assertEqual(shown['assessment']['expectedAnswer'],'5');self.assertFalse(shown['assessment']['countsForAbility'])
        self.assertEqual(self.transport.call_count,self.voice_before+1);self.main.analyze_image.assert_not_called()
        self.assertEqual(self.turn(key='new-explain')['turns'][-1]['id'],first['id'])
        self.assertEqual(self.transport.call_count,self.voice_before+1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_provider_calls').fetchone()['n'],self.calls_before)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(self.item['id'],)).fetchone()['result_json'],self.before_raw)
        self.assertEqual(self.get()['correction']['status'],'in_progress')
        self.assertEqual(self.get()['correction']['attempts'],0)

    def test_only_real_new_answer_records_correction_same_key_is_idempotent(self):
        self.prepare();self.turn();self.work()
        self.turn('answer','答案是五',key='answer-1');self.assertTrue(self.work()['ok'])
        correction=self.get()['correction'];self.assertEqual(correction['status'],'corrected');self.assertEqual(correction['attempts'],1)
        self.assertFalse(correction['countsForAbility']);self.turn('answer','答案是五',key='answer-1')
        self.assertFalse(self.work()['processed']);self.assertEqual(self.get()['correction']['attempts'],1)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(self.item['id'],)).fetchone()['result_json'],self.before_raw)

    def test_missing_reference_is_terminal_without_new_model_calls(self):
        self.prepare();raw=json.loads(self.before_raw);raw['tencentRaw']['answer']['RightAnswer']=''
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(json.dumps(raw),self.item['id']));self.db.raw.commit()
        self.turn();self.assertTrue(self.work()['ok']);turn=self.get()['turns'][-1]
        self.assertEqual(turn['reviewState'],'required');self.assertFalse(turn['reviewRetryAllowed'])
        self.main.analyze_image.assert_not_called();self.assertEqual(self.transport.call_count,self.voice_before)
        self.error('homework_tutor_review_required',lambda:self.turn(key='retry'))

    def test_free_followup_one_grounded_call_is_owned_and_does_not_change_fixed_reference(self):
        self.prepare()
        response=teacher_reply(teacherText='原解析用相加来求总数。',assessment={'status':'guidance_only','reason':'原解析','expectedAnswer':'5'},
            steps=[{'text':'按原解析先计算两个数相加。','visual':{'kind':'paper_region','region':{'x':0.,'y':0.,'width':1.,'height':1.}}}])
        self.main.analyze_image.return_value=AiVisionResponse(json.dumps(response),'fixture','fixture-tutor')
        self.turn('followup','这里为什么是相加？');self.assertTrue(self.work()['ok'])
        self.assertEqual(self.main.analyze_image.call_count,1)
        self.assertEqual(self.get()['turns'][-1]['teachingQuality']['status'],'guidance')
        self.assertEqual(self.get()['turns'][-1]['assessment']['expectedAnswer'],'5')
        self.assertEqual(self.get()['correction']['attempts'],0)
        self.assertIn('fixedReference',self.main.analyze_image.call_args.kwargs['user_prompt'])
        self.service.tutor.get('student-a',self.identity,self.item['id']);self.assertEqual(self.main.analyze_image.call_count,1)

    def test_free_followup_wrong_expected_or_unknown_cannot_override_or_replay(self):
        for failure in ('wrong','timeout'):
            with self.subTest(failure=failure):
                self.setUp();self.prepare()
                if failure=='wrong':self.main.analyze_image.return_value=AiVisionResponse(json.dumps(teacher_reply(assessment={'status':'guidance_only','reason':'','expectedAnswer':'8'})),'fixture','fixture-tutor')
                else:self.main.analyze_image.side_effect=TimeoutError()
                self.turn('followup','能再说说吗？');self.assertFalse(self.work()['ok']);self.assertEqual(self.main.analyze_image.call_count,1)
                self.assertEqual(self.get()['turns'][-1]['audio']['status'],'unavailable')
                self.error('homework_tutor_pending',lambda:self.turn('followup','能再说说吗？',key='retry'))
                self.assertFalse(self.work()['processed']);self.assertEqual(self.main.analyze_image.call_count,1)
