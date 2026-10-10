"""Source identity survives a real queue flow; no paid calls or live database."""
import json
import unittest
from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_service import POLICY
from test_homework_analysis import HomeworkTest


class HomeworkSourcePipelineTests(unittest.TestCase):
    setUp=HomeworkTest.setUp
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    events=HomeworkTest.events

    def source_response(self, items, *, version='v3'):
        self.service.policy=POLICY
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(
            json.dumps({'transcriptVersion':version,'pageReadable':True,'items':items}),
            'fixture','fixture-vision')

    def source_item(self, **changes):
        return {**self.raw,'sourceQuestionLabel':'5（2）','answerState':'written',
            'answerRegions':[{'x':.6,'y':.15,'width':.05,'height':.05}],
            'visualEvidence':None,**changes}

    def test_printed_subquestion_and_original_answer_survive_to_student_and_tutor(self):
        self.source_response([self.source_item()])
        s=self.ready()
        student=self.service.student_detail('student-a',s['id'])['submission']
        context=student['items'][0]['reviewContext']
        self.assertEqual(context['sourceQuestionLabel'],'5（2）')
        self.assertEqual(context['answerState'],'written')
        self.assertEqual(context['originalAnswer'],'4')
        self.assertFalse(context['recognitionConfirmed'])
        self.assertEqual(context,student['tutorItems'][0]['reviewContext'])
        self.assertEqual(s['items'][0]['transcriptVersion'],'v3')
        self.assertEqual(s['items'][0]['answerRegions'][0]['x'],.6)
        self.assertEqual(self.provider.analyze_image.call_args.kwargs['temperature'],0.0)

    def test_empty_box_cannot_be_replaced_by_an_inferred_numeric_answer(self):
        self.source_response([self.source_item(studentAnswer='5',answerState='blank')])
        s=self.ready()
        self.assertEqual(s['items'][0]['status'],'pending')
        self.assertTrue(s['items'][0]['recognitionNeedsConfirmation'])
        self.assertEqual(self.events(),[])
        self.assertEqual(self.service.student_detail('student-a',s['id'])['submission']['items'],[])
        self.transport.assert_not_called()

    def test_blank_and_written_siblings_keep_separate_source_identity(self):
        self.source_response([self.source_item(sourceQuestionLabel='5（1）',studentAnswer='',answerState='blank'),
            self.source_item(sourceQuestionLabel='5（2）',answerRegions=[{'x':.4,'y':.15,'width':.05,'height':.05}])])
        s=self.ready()
        self.assertEqual([i['status'] for i in s['items']],['blank','incorrect'])
        student=self.service.student_detail('student-a',s['id'])['submission']
        self.assertEqual([i['reviewContext']['sourceQuestionLabel'] for i in student['tutorItems']],['5（1）','5（2）'])
        self.assertEqual(student['tutorItems'][0]['reviewContext']['originalAnswer'],'')

    def test_new_contract_missing_source_fields_is_not_assessed(self):
        self.source_response([self.raw],version='v2')
        s=self.ready()
        self.assertEqual(s['items'][0]['status'],'pending')
        self.assertTrue(s['items'][0]['recognitionNeedsConfirmation'])
        self.assertEqual(s['pages'][0]['status'],'needs_confirmation')
        self.assertEqual(self.events(),[])
        self.transport.assert_not_called()


if __name__=='__main__':unittest.main()
