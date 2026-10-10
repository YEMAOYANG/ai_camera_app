"""Upload → immutable grading → teacher → actual correction → frozen review.

Uses isolated transactions and fake Tencent/TTS responses. No existing data or
paid provider is touched, and no simulated answer is claimed as a child's work.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
import json

from core.errors import ApiError
from services.homework_service import canonical
from services.homework_tutor_service import HomeworkTutorService
from services.learning_review_service import LearningReviewService
from services.learning_evidence_service import weaknesses
from tests import test_homework_tencent_grading as tencent_fixtures
from tests.test_learning_reviews import at


class HomeworkLaunchLoopTest(TestCase):
    setUp = tencent_fixtures.TencentPipelineTest.setUp
    create = tencent_fixtures.TencentPipelineTest.create
    upload = tencent_fixtures.TencentPipelineTest.upload
    queued = tencent_fixtures.TencentPipelineTest.queued
    due = tencent_fixtures.TencentPipelineTest.due
    events = tencent_fixtures.TencentPipelineTest.events
    error = tencent_fixtures.TencentPipelineTest.error

    def paper(self, *, contradiction=False):
        prompt='从左数，第2棵树上有几个苹果？'
        raw=tencent_fixtures.marks(prompt=prompt,answer='5',right='3',correct=contradiction)
        answer=raw['Response']['MarkInfos'][0]['AnswerInfos'][0]
        answer.update(AnswerAnalysis='从左往右数，第2棵树上有3个苹果。',KnowledgePoints=['位置与方向','数一数'])
        def submit(path, *, receipt_callback, **kw):
            saved=tencent_fixtures.source(prompt)
            receipt_callback('SubmitQuestionMarkAgentJob',canonical(saved).encode(),{'httpStatus':200})
            return {'jobIds':['job-offline'],'rawReceipt':saved,'submitted':True}
        def query(job, *, receipt_callback):
            receipt_callback('DescribeQuestionMarkAgentJob',canonical(raw).encode(),{'httpStatus':200})
            return {'status':'DONE','rawReceipt':raw}
        self.tencent.submit_question.side_effect=submit
        self.tencent.describe_question.side_effect=query
        submission=self.queued('tree-original')
        self.service.process_next();self.due();self.service.process_next()
        return self.service.get('parent-a',submission['id'])['submission']

    def teach(self, submission, *, mode='explain', message='', key='explain'):
        self.service.tutor.process_next=HomeworkTutorService.process_next.__get__(self.service.tutor)
        item=submission['originalPaperItems'][0]
        data={'itemRevision':item['revision'],'idempotencyKey':key,'mode':mode,'message':message}
        self.service.tutor.submit('student-a',submission['id'],item['id'],data)
        outcome=self.service.process_next(submission_id=submission['id'])
        self.assertTrue(outcome['ok'],outcome)
        return self.service.tutor.get('student-a',submission['id'],item['id'])

    def reviews(self):
        self.db.execute('DROP TABLE tasks')
        columns='id,family_id,child_id,title,description,type,status,scheduled_date,scheduled_start,scheduled_end,schedule_type,start_at,due_at,priority,reward_points,requires_parent_confirmation,created_by,reminder_minutes_before,reminder_status,timezone,learning_assignment_key,learning_slot,created_at,updated_at,next_reminder_at,started_at,completed_at,ended_at,completion_source,evidence_summary'
        self.db.execute('CREATE TABLE tasks ('+','.join(c+' TEXT' for c in columns.split(','))+')')
        self.tick[0]=at('2026-10-03',10)
        self.db.raw.commit()
        return LearningReviewService(self.db,auth_service=SimpleNamespace(authenticate=lambda _:{'family':{'id':'family-a'}}),
            student_auth_service=self.service.student_auth,parent_authorize=lambda *args:None,clock=self.service.clock,
            question_pool=lambda *args:([],[]),private_question_pool=self.service.review_question_pool,
            private_source_alive=self.service.review_source_alive,private_audio_file=self.service.review_audio_file)

    def test_original_teacher_answer_parent_and_weekend_are_one_conservative_loop(self):
        submission=self.paper();item=submission['items'][0]
        self.assertEqual((item['status'],item['answerMode']),('incorrect','spoken'))
        self.assertTrue(item['readyForStudent'])
        original=self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json']
        self.provider.analyze_image=Mock(side_effect=AssertionError('reference explanation must not re-solve an image'))
        self.teach(submission)
        parent=self.service.get('parent-a',submission['id'])['submission']
        correction=parent['items'][0]['studentCorrection']
        self.assertTrue(correction['explanationViewed']);self.assertEqual(correction['attempts'],0)
        self.assertEqual(parent['summary']['corrected'],0)
        taught=self.teach(submission,mode='answer',message='三棵',key='actual-answer')
        self.assertTrue(taught['tutor']['correction']['correct'])
        calls=(self.transport.call_count,self.tencent.submit_question.call_count,self.tencent.describe_question.call_count)
        # Same answer key and all read surfaces reuse the saved turn/audio.
        self.teach(submission,mode='answer',message='三棵',key='actual-answer')
        parent=self.service.get('parent-a',submission['id'])['submission']
        self.assertEqual(parent['items'][0]['studentAnswer'],'5')
        self.assertEqual(parent['summary']['corrected'],1)
        self.assertEqual(parent['items'][0]['studentCorrection']['lastAnswer'],'三棵')
        self.assertEqual(parent['items'][0]['studentCorrection']['attempts'],1)
        self.assertFalse(parent['items'][0]['studentCorrection']['countsForAbility'])
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json'],original)
        self.assertEqual((self.transport.call_count,self.tencent.submit_question.call_count,self.tencent.describe_question.call_count),calls)
        self.provider.analyze_image.assert_not_called()
        self.assertEqual(len(self.events()),2)
        self.assertTrue(all(e['independent'] is None for e in self.events()))
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a')[0]['wrongCount'],1)

        service=self.reviews();child=self.db.execute('SELECT * FROM children WHERE id=?',('child-a',)).fetchone()
        with self.db.transaction() as conn:run=service.ensure_week(conn,child,self.tick[0])
        self.assertEqual(run['total_questions'],1)
        start=service.student_action('student-a',run['id'],{'action':'start','revision':run['revision'],'requestId':'start'})
        question=start['currentQuestion']
        self.assertEqual(question['renderer'],'homework_original');self.assertEqual(question['options'],[])
        self.assertNotIn('correctAnswer',question);self.assertIsNone(question['explanation'])
        answer={'questionId':question['id'],'response':'三个','revision':start['review']['revision'],'requestId':'answer'}
        result=service.answer('student-a',run['id'],answer)
        self.assertTrue(result['feedback']['correct']);self.assertFalse(result['feedback']['independent'])
        self.assertEqual(service.answer('student-a',run['id'],answer),result)
        result=service.student_action('student-a',run['id'],{'action':'next','revision':result['review']['revision'],'requestId':'next'})
        self.assertEqual(result['review']['status'],'completed');self.assertEqual(result['review']['independentCorrectCount'],0)
        self.assertEqual(result['report']['answeredCount'],1)
        changed=json.loads(original)
        changed['tencentRaw']['answer']['KnowledgePoints']=['更新后的计数参考']
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(changed),item['id']));self.db.raw.commit()
        # A source/reference change withdraws both same-paper marks and already
        # completed derived reports on read, without replaying or rewriting AI.
        after=service.parent_detail('parent-a','child-a',run['id'])
        self.assertEqual(after['review']['correctCount'],0)
        self.assertEqual(after['report']['answeredCount'],0)
        self.assertEqual(after['report']['sourceReviewCount'],1)
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a'),[])
        self.assertEqual(self.service.get('parent-a',submission['id'])['submission']['summary']['corrected'],0)
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(original,item['id']));self.db.raw.commit()
        self.service.delete('parent-a',submission['id'],{'revision':submission['revision']})
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a'),[])
        after=service.parent_detail('parent-a','child-a',run['id'])
        self.assertEqual(after['review']['correctCount'],0);self.assertEqual(after['report']['answeredCount'],0)

    def test_conflicting_tencent_judgment_never_produces_wrong_mark_or_review(self):
        submission=self.paper(contradiction=True)
        item=submission['items'][0]
        self.assertEqual(item['status'],'pending');self.assertFalse(item['readyForStudent'])
        self.assertNotIn('expectedAnswer',item);self.assertNotIn('explanation',item)
        self.assertFalse(item['studentCorrection']['answerEvaluationAllowed'])
        self.assertEqual(self.events(),[]);self.transport.assert_not_called()
        child=self.db.execute('SELECT * FROM children WHERE id=?',('child-a',)).fetchone()
        with self.db.transaction() as conn:self.assertEqual(self.service.review_question_pool(conn,child)[0],[])

    def test_changed_spoken_media_cannot_be_reused_as_the_current_answer_explanation(self):
        submission=self.paper();item=submission['items'][0]
        record=self.db.execute('SELECT media_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()
        media=json.loads(record['media_json']);media['explanation']['textSha256']='0'*64
        self.db.execute('UPDATE homework_items SET media_json=? WHERE id=?',(canonical(media),item['id']));self.db.raw.commit()
        current=self.service.student_detail('student-a',submission['id'])['submission']['items'][0]
        self.assertFalse(current['readyForStudent'])
        self.error('homework_media_preparing',lambda:self.service.student_answer('student-a',submission['id'],item['id'],
            {'itemRevision':item['revision'],'answer':'3','idempotencyKey':'stale-voice'}))
        child=self.db.execute('SELECT * FROM children WHERE id=?',('child-a',)).fetchone()
        with self.db.transaction() as conn:
            pool,gaps=self.service.review_question_pool(conn,child)
        self.assertEqual(pool,[]);self.assertTrue(gaps)

    def test_old_answer_receipt_is_not_replayed_after_reference_changes(self):
        submission=self.paper();item=submission['items'][0]
        data={'itemRevision':item['revision'],'answer':'三个','idempotencyKey':'same-answer'}
        first=self.service.student_answer('student-a',submission['id'],item['id'],data)
        self.assertTrue(first['feedback']['correct'])
        self.assertEqual(self.service.student_answer('student-a',submission['id'],item['id'],data),first)
        record=self.db.execute('SELECT result_json,correction_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()
        old_correction=json.loads(record['correction_json']);old_correction.pop('referenceDigest')
        self.db.execute('UPDATE homework_items SET correction_json=? WHERE id=?',(canonical(old_correction),item['id']));self.db.raw.commit()
        self.assertEqual(self.service.get('parent-a',submission['id'])['submission']['summary']['corrected'],0)
        changed=json.loads(record['result_json']);changed['tencentRaw']['answer']['KnowledgePoints']=['计数参考更新']
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(changed),item['id']));self.db.raw.commit()
        self.error('homework_reference_changed',lambda:self.service.student_answer('student-a',submission['id'],item['id'],data))
