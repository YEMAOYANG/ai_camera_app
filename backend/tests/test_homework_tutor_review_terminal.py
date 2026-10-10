"""Terminal image review must not become a new paid request on every click."""
from copy import deepcopy
import json
from unittest import TestCase

from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_tutor_service import encoded
from tests.test_homework_tutor_answer_quality import HomeworkTutorAnswerQualityTests
from tests.test_homework_tutor import teacher_reply


class HomeworkTutorReviewTerminalTests(TestCase):
    def setUp(self):
        HomeworkTutorAnswerQualityTests.setUp(self)
        # These regression cases retain saved visual-model request provenance.
        # New production Tencent requests use the immutable-reference route.
        self.service.tutor.policy={**self.service.tutor.policy,'unreferencedTencentImageTeaching':True}
    create=HomeworkTutorAnswerQualityTests.create
    upload=HomeworkTutorAnswerQualityTests.upload
    ready=HomeworkTutorAnswerQualityTests.ready
    error=HomeworkTutorAnswerQualityTests.error
    events=HomeworkTutorAnswerQualityTests.events
    queue_question=HomeworkTutorAnswerQualityTests.queue_question
    request=HomeworkTutorAnswerQualityTests.request
    install_review=HomeworkTutorAnswerQualityTests.install_review

    def blocked_turn(self):
        submission,item,result=self.queue_question()
        self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        reply=teacher_reply(teacherText='图中雪雪是第二位，所以答案是二。',
            assessment={'status':'guidance_only','reason':'模型根据错误目标讲解','expectedAnswer':'2'},
            sourceCheck={'status':'unclear','basis':'original_image','questionLocated':True,
                'questionReadable':False,'answerLocated':True,'studentAnswerReadable':True,
                'answerOrdinal':1,'reason':'没看清印刷人物标签。'})
        self.provider.analyze_image.side_effect=lambda **_:AiVisionResponse(encoded(reply),'fixture','fixture-vision')
        self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        return submission,item,result

    def test_new_keys_cannot_repeat_completed_unverified_explanation_or_consume_limit(self):
        submission,item,_=self.blocked_turn()
        before=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']
        turn=before['turns'][0]
        self.assertEqual(turn['status'],'ready')
        self.assertEqual(turn['reviewState'],'required')
        self.assertFalse(turn['reviewRetryAllowed'])
        self.assertEqual(turn['reviewReasonCode'],'visual_source_unverified')
        self.assertNotIn('答案是二',turn['teacherText'])
        self.assertEqual(turn['assessment']['expectedAnswer'],'')
        self.assertEqual(turn['audio']['status'],'unavailable')
        self.assertNotIn('reviewScopeSha256',turn)
        summary=self.service.get('parent-a',submission['id'])['submission']['tutorSummary']
        self.assertEqual(summary['readyTurnCount'],0)
        self.assertEqual(summary['reviewRequiredTurnCount'],1)
        self.assertEqual(summary['needsConfirmationCount'],1)
        counts=(self.provider.analyze_image.call_count,self.transport.call_count,len(self.events()))
        actions=self.db.execute('SELECT result_json FROM homework_actions WHERE item_id=?',(item['id'],)).fetchall()
        for index in range(3):
            self.error('homework_tutor_review_required',lambda:self.service.tutor.submit(
                'student-a',submission['id'],item['id'],self.request(item,'retry-'+str(index))))
        self.assertFalse(self.service.process_next(submission_id=submission['id'])['processed'])
        self.assertEqual(self.service.tutor.get('student-a',submission['id'],item['id'])['tutor'],before)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE item_id=?',(item['id'],)).fetchall(),actions)
        self.assertEqual((self.provider.analyze_image.call_count,self.transport.call_count,len(self.events())),counts)

    def test_followup_and_answer_cannot_bypass_same_source_terminal(self):
        submission,item,_=self.blocked_turn()
        before=self.provider.analyze_image.call_count
        for mode in ('followup','answer'):
            self.error('homework_tutor_review_required',lambda:self.service.tutor.submit(
                'student-a',submission['id'],item['id'],{**self.request(item,'new-'+mode),
                    'mode':mode,'message':'为什么？'}))
        self.assertEqual(self.provider.analyze_image.call_count,before)

    def test_same_key_reconciles_saved_review_terminal_and_conflict_is_not_silently_accepted(self):
        submission,item,_=self.blocked_turn()
        result=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        self.assertEqual(result,self.service.tutor.get('student-a',submission['id'],item['id']))
        self.error('homework_idempotency_conflict',lambda:self.service.tutor.submit(
            'student-a',submission['id'],item['id'],{**self.request(item),'mode':'followup','message':'为什么？'}))
        self.assertEqual(len(result['tutor']['turns']),1)

    def test_unknown_transport_still_blocks_new_key_before_review_and_never_replays(self):
        submission,item,_=self.blocked_turn()
        turn=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE item_id=?',(item['id'],)).fetchone()['result_json'])
        turn.update(status='unknown',errorCode='homework_tutor_unknown')
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(encoded(turn),turn['id']));self.db.raw.commit()
        before=self.provider.analyze_image.call_count
        self.error('homework_tutor_pending',lambda:self.service.tutor.submit(
            'student-a',submission['id'],item['id'],self.request(item,'cannot-replay-unknown')))
        self.assertFalse(self.service.process_next(submission_id=submission['id'])['processed'])
        self.assertEqual(self.provider.analyze_image.call_count,before)

    def test_confirmed_source_after_old_bad_lesson_can_use_reviewed_lesson_without_model(self):
        submission,item,result=self.blocked_turn();before=self.provider.analyze_image.call_count
        with self.install_review(submission,item,result):
            old=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertEqual(old['reviewState'],'required');self.assertTrue(old['reviewRetryAllowed'])
            self.assertEqual(old['assessment']['expectedAnswer'],'')
            self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item,'now-reviewed'))
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
            current=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][-1]
            self.assertEqual(current['reviewState'],'not_required');self.assertFalse(current['reviewRetryAllowed'])
            self.assertEqual(current['teachingQuality']['status'],'verified')
            self.assertEqual(current['assessment']['expectedAnswer'],'4')
            self.assertEqual(current['audio']['status'],'ready')
        self.assertEqual(self.provider.analyze_image.call_count,before)

    def test_changed_model_or_prompt_can_authorize_explicit_new_request(self):
        for field in ('model','prompt'):
            with self.subTest(field=field):
                self.setUp()
                submission,item,_=self.blocked_turn()
                if field=='model': self.provider.model_name='fixture-improved-vision'
                else:
                    self.service.tutor.policy=deepcopy(self.service.tutor.policy)
                    self.service.tutor.policy['prompt']['version']='v7'
                turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
                self.assertTrue(turn['reviewRetryAllowed'])
                view=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item,'new-scope'))
                self.assertEqual(view['tutor']['turns'][-1]['status'],'queued')

    def test_legacy_receipt_is_reconciled_without_replay_and_detects_real_model_drift(self):
        submission,item,_=self.blocked_turn()
        stored=self.db.execute('SELECT result_json FROM homework_actions WHERE item_id=?',(item['id'],)).fetchone()['result_json']
        turn=json.loads(stored);turn.pop('reviewScopeSha256')
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(encoded(turn),turn['id']));self.db.raw.commit()
        unchanged=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertFalse(unchanged['reviewRetryAllowed'])
        self.error('homework_tutor_review_required',lambda:self.service.tutor.submit(
            'student-a',submission['id'],item['id'],self.request(item,'legacy-retry')))
        self.provider.max_image_dimension=1500
        changed=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertTrue(changed['reviewRetryAllowed'])
        self.assertEqual(self.service.tutor.submit('student-a',submission['id'],item['id'],
            self.request(item,'new-image-encoding'))['tutor']['turns'][-1]['status'],'queued')

    def test_verified_exact_lesson_remains_available_for_new_explanation(self):
        submission=self.ready();item=submission['items'][0]
        self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))
        self.provider.analyze_image.side_effect=lambda **_:AiVisionResponse(encoded(teacher_reply()),'fixture','fixture-vision')
        self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertEqual(turn['teachingQuality']['status'],'verified')
        self.assertEqual(turn['reviewState'],'not_required')
        self.assertEqual(self.service.tutor.submit('student-a',submission['id'],item['id'],
            self.request(item,'another-explanation'))['tutor']['turns'][-1]['status'],'queued')
