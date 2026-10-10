"""Paid evaluation guards and fair inputs; no network or model calls."""
import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / 'scripts/evaluate_homework_teacher.py'
spec = importlib.util.spec_from_file_location('homework_teacher_eval', SCRIPT)
evaluation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evaluation
spec.loader.exec_module(evaluation)


def case():
    return {'id':'blank', 'teacherInput':{'gradeCode':'primary_1','subject':'math','prompt':'4−□=3',
        'studentOriginalAnswer':'□','region':{'x':0.,'y':0.,'width':1.,'height':1.},'recognitionConfidence':1},
        'initialStudentMessage':'我还没有填。', 'followupMessage':'我还是不会。',
        'groundTruth':{'privateExpectedAnswer':'do-not-send-this'},
        'scene':{'elements':[{'type':'text','x':10,'y':10,'text':'4−□=3'}]}}


class TeacherEvaluationGuards(unittest.TestCase):
    def test_response_is_journaled_even_if_crop_validation_fails(self):
        class Reply:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,*args):return json.dumps({'id':'test-receipt','choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':{'total_tokens':1}}).encode()
        with TemporaryDirectory() as temporary, patch.object(evaluation.urllib.request,'urlopen',return_value=Reply()), patch.object(evaluation,'parse_response',side_effect=evaluation.ApiError('homework_region_invalid','invalid crop',400)):
            row=evaluation.one_call(evaluation.Candidate('qwen','qwen3.8-max','https://dashscope.aliyuncs.com/compatible-mode/v1','secret'),case(),1,[],evaluation.render(case()['scene']),Path(temporary))
            saved=json.loads((Path(temporary)/'qwen-blank-1.json').read_text())
            self.assertEqual(row['status'],'invalid_contract')
            self.assertEqual(saved['response']['id'],'test-receipt')
            self.assertEqual(saved['contractError'],'homework_region_invalid')
            self.assertNotIn('secret',json.dumps(saved))

    def test_receipt_loss_is_excluded_from_latency_not_fabricated(self):
        rows=[{'provider':'qwen','status':'received_unavailable'}, {'provider':'qwen','status':'received','elapsedSeconds':2,'contractValid':True}]
        value=evaluation.summary(rows)['qwen']
        self.assertEqual(value['calls'],2)
        self.assertEqual(value['received'],1)
        self.assertEqual(value['medianSeconds'],2)
        self.assertIsNone(value['billingCost'])

    def test_same_initial_input_and_no_ground_truth_or_secret_in_payload(self):
        image = evaluation.render(case()['scene'])
        left = evaluation.request_payload(evaluation.Candidate('deepseek','deepseek-flash','https://api.deepseek.com','secret-a'),case(),1,[],image)
        right = evaluation.request_payload(evaluation.Candidate('qwen','qwen3.8-max','https://dashscope.aliyuncs.com/compatible-mode/v1','secret-b'),case(),1,[],image)
        self.assertEqual(left['messages'], right['messages'])
        self.assertEqual(left['max_tokens'], right['max_tokens'])
        self.assertEqual(left['temperature'], right['temperature'])
        self.assertEqual(left['thinking'], {'type':'disabled'})
        self.assertFalse(right['enable_thinking'])
        self.assertNotIn('do-not-send-this',json.dumps(left))
        self.assertNotIn('secret-a',json.dumps(left))
        self.assertNotIn('secret-a',repr(evaluation.Candidate('deepseek','deepseek-flash','https://api.deepseek.com','secret-a')))

    def test_existing_dispatch_cannot_be_replayed(self):
        with TemporaryDirectory() as temporary:
            target=Path(temporary)/'deepseek-blank-1.json'
            target.write_text('{"status":"dispatched"}')
            with self.assertRaisesRegex(ValueError,'existing_attempt_will_not_be_replayed'):
                evaluation.one_call(evaluation.Candidate('deepseek','deepseek-flash','https://api.deepseek.com','secret'),case(),1,[],evaluation.render(case()['scene']),Path(temporary))
            self.assertEqual(json.loads(target.read_text()),{'status':'dispatched'})

    def test_uncertain_transport_stops_that_lane(self):
        with patch.object(evaluation,'one_call',return_value={'status':'unknown'}) as call:
            result=evaluation.lane(evaluation.Candidate('deepseek','deepseek-flash','https://api.deepseek.com','secret'),[case(),case()],{'blank':b'image'},Path('/unused'))
            self.assertEqual(result,[{'status':'unknown'}])
            self.assertEqual(call.call_count,1)

    def test_followup_uses_each_candidates_own_validated_first_turn(self):
        calls=[]
        reply={'teacherText':'先看空格。','steps':[], 'assessment':{'status':'guidance_only'}}
        def received(candidate,fixture,turn,history,image,directory):
            calls.append((turn,list(history)))
            return {'status':'received','studentReply':reply}
        with patch.object(evaluation,'one_call',side_effect=received):
            evaluation.lane(evaluation.Candidate('qwen','qwen3.8-max','https://dashscope.aliyuncs.com/compatible-mode/v1','secret'),[case()],{'blank':b'image'},Path('/unused'))
        self.assertEqual(calls[0],(1,[]))
        self.assertEqual(calls[1][1][0]['teacherText'],'先看空格。')
        self.assertEqual(calls[1][1][0]['message'],'我还没有填。')


if __name__=='__main__':
    unittest.main()
