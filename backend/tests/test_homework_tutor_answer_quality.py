"""Answer publication barriers using isolated data and fake voice/model APIs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from services.homework_answer_quality import digest, SCHEMA as REVIEW_SCHEMA
from services.homework_tutor_service import POLICY, SCHEMA, encoded, teaching_view, teacher_input_image
from services.teacher_speech import normalize_teacher_speech
from tests.test_homework_analysis import HomeworkTest, picture
from tests.test_homework_tutor import teacher_reply


class HomeworkTutorAnswerQualityTests(TestCase):
    setUp=HomeworkTest.setUp
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    error=HomeworkTest.error
    events=HomeworkTest.events

    def queue_question(self):
        self.raw.update(prompt='正步训练',type='word_problem',confidence=.2)
        submission=self.ready(); item=submission['items'][0]
        result=json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json'])
        result.update(method='tencent_question.v1',prompt='请看原图中的这道题。',studentAnswer='4',expectedAnswer='2',
            status='pending',recognitionNeedsConfirmation=True,sourceAnswerOrdinal=1,sourceAnswerCount=1,
            sourceValidation={'trusted':False,'issues':['question_text_missing']},
            tencentRaw={'answer':{'HandwriteInfo':'4','IsCorrect':False,'RightAnswer':'2',
                'AnswerAnalysis':'原从左到右顺序为5、4、3、2、1，雪雪原来排第2，转后排第2。',
                'KnowledgePoints':['位置与顺序']}})
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(encoded(result),item['id']))
        self.db.raw.commit()
        return submission,item,result

    def request(self,item,key='teacher'):
        return {'itemRevision':item['revision'],'idempotencyKey':key,'mode':'explain','message':''}

    def install_review(self,submission,item,result):
        page=self.db.execute('SELECT * FROM homework_pages WHERE id=?',(item['pageId'],)).fetchone()
        record={'method':'operator_reviewed_order_reversal.v1','reviewBasis':'human_confirmed_original',
            'reviewId':'b'*64,'expectedAnswer':'4',
            'scope':{'submissionId':submission['id'],'submissionRevision':submission['revision'],
                'itemId':item['id'],'itemRevision':item['revision'],'pageId':page['id'],
                'sourceImageSha256':page['content_sha256'],'resultSha256':digest(result)},
            'teacherFacts':{'total':5,'targetLabel':'雪雪','originalOrdinal':2,'originalFront':'left',
                'transform':'turn_around','printedTargetConfirmed':True,'handwrittenAnnotationsExcluded':True}}
        record['reviewId']=digest({key:value for key,value in record.items() if key!='reviewId'})
        path=Path(self.tmp.name)/'reviews.json';path.write_text(encoded({'schemaVersion':REVIEW_SCHEMA,'reviews':[record]}))
        return patch.dict('os.environ',{'HOMEWORK_ANSWER_REVIEW_PATH':str(path)})

    def old_turn(self,submission,item,result):
        queued=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item))['tutor']['turns'][0]
        queued=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()['result_json'])
        from PIL import Image
        import io
        raw=picture(); photo=Image.open(io.BytesIO(raw)).convert('RGB')
        contract=teacher_input_image(raw,photo,result,POLICY)[1]
        audio=b'old paid speech';key=self.store.put(audio,namespace='old-unverified-audio',suffix='wav')
        value={**queued,**teacher_reply(teacherText='雪雪排第二，答案是二。',
            assessment={'status':'guidance_only','reason':'看图判断','expectedAnswer':'2'},
            sourceCheck={'status':'matched','basis':'original_image','questionLocated':True,'questionReadable':True,
                'answerLocated':False,'studentAnswerReadable':False,'answerOrdinal':1,
                'prompt':'五人向后转，雪雪排第几。','reason':'小字没有看清。'}),
            'schemaVersion':SCHEMA,'status':'ready','sourceImageContract':contract,
            'audio':{'status':'ready','storageKey':key,'sha256':hashlib.sha256(audio).hexdigest(),'mimeType':'audio/wav'},
            'gradingReferenceComparison':{'status':'unverified','referenceAnswer':'2','teacherAnswer':'2'}}
        original=encoded(value)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(original,queued['id']))
        self.db.raw.commit();return value,original

    def test_old_unverified_answer_text_audio_and_reference_are_withdrawn_without_ai_or_writes(self):
        submission,item,result=self.queue_question();turn,original=self.old_turn(submission,item,result)
        model_calls=self.provider.analyze_image.call_count; voice_calls=self.transport.call_count;events=len(self.events())
        for _ in range(2):
            public=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertEqual(public['assessment']['expectedAnswer'],'')
            self.assertEqual(public['assessment']['status'],'needs_confirmation')
            self.assertNotIn('答案是二',public['teacherText']);self.assertNotIn('gradingReferenceComparison',public)
            self.assertEqual(public['audio']['status'],'unavailable');self.assertNotIn('assetUrl',public['audio'])
            detail=self.service.student_detail('student-a',submission['id'])['submission']
            for entry in detail['originalPaperItems']+detail['tutorItems']:
                grading=entry['reviewContext']['grading']
                self.assertEqual(grading['status'],'unknown')
                self.assertNotIn('referenceAnswer',grading);self.assertNotIn('analysis',grading)
            self.assertEqual(detail['originalPaperSummary']['incorrect'],0)
        self.error('homework_tutor_audio_not_ready',lambda:self.service.tutor.audio('student-a',submission['id'],item['id'],turn['id']))
        self.error('homework_tutor_source_unconfirmed',lambda:self.service.tutor.resume_audio('student-a',submission['id'],item['id'],turn['id'],self.request(item,'resume')))
        self.assertEqual(self.provider.analyze_image.call_count,model_calls);self.assertEqual(self.transport.call_count,voice_calls)
        self.assertEqual(len(self.events()),events)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(turn['id'],)).fetchone()['result_json'],original)
        self.assertEqual(json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json']),result)
        parent=self.service.get('parent-a',submission['id'])['submission']
        for entry in parent['items']+parent['originalPaperItems']+parent['tutorItems']:
            self.assertEqual(entry['reviewContext']['grading']['status'],'unknown')
            self.assertNotIn('referenceAnswer',entry['reviewContext']['grading'])
            self.assertNotIn('analysis',entry['reviewContext']['grading'])
            self.assertNotIn('expectedAnswer',entry)
            self.assertNotIn('providerAssessment',entry)
            self.assertEqual(entry['status'],'pending')
        self.assertEqual(parent['originalPaperSummary']['incorrect'],0)
        self.assertEqual(parent['providerVerdictSummary']['incorrect'],0)
        self.assertEqual(parent['originalSummary']['pending'],1)

    def test_unverified_new_turn_does_not_dispatch_voice(self):
        submission,item,result=self.queue_question();before=self.transport.call_count
        reply=teaching_view({**teacher_reply(),'status':'ready'},result)
        media=self.service.tutor._voice({'id':'owned-turn'},submission,item,reply,result=result)
        self.assertEqual(media['errorCode'],'homework_tutor_source_unconfirmed');self.assertEqual(self.transport.call_count,before)

    def test_parent_formal_result_is_unknown_until_owned_review_then_reports_correct_four(self):
        submission,item,result=self.queue_question();model_calls=self.provider.analyze_image.call_count
        voice_calls=self.transport.call_count;events=len(self.events())
        pending=self.service.get('parent-a',submission['id'])['submission']
        self.assertEqual(pending['items'][0]['status'],'pending')
        self.assertNotIn('expectedAnswer',pending['items'][0])
        self.assertNotIn('analysis',pending['items'][0]['gradingReference'])
        self.assertEqual(pending['originalPaperSummary']['incorrect'],0)
        with self.install_review(submission,item,result):
            for _ in range(2):
                parent=self.service.get('parent-a',submission['id'])['submission']
                student=self.service.student_detail('student-a',submission['id'])['submission']
                self.assertEqual(parent['originalPaperSummary'],student['originalPaperSummary'])
                self.assertEqual(parent['items'][0]['status'],'correct')
                self.assertEqual(parent['items'][0]['expectedAnswer'],'4')
                self.assertEqual(parent['items'][0]['gradingReference']['referenceAnswer'],'4')
                self.assertEqual(parent['originalPaperItems'][0]['reviewContext']['grading']['status'],'correct')
                self.assertEqual(parent['originalSummary']['correct'],1)
                self.assertEqual(parent['originalSummary']['pending'],0)
                self.assertNotIn('providerIsCorrect',parent['items'][0]['gradingReference'])
                self.assertNotIn('tencentRaw',parent['items'][0])
                self.assertNotIn('_confirmedAnswerReview',encoded(parent))
        self.assertEqual(self.provider.analyze_image.call_count,model_calls);self.assertEqual(self.transport.call_count,voice_calls)
        self.assertEqual(len(self.events()),events)
        self.assertEqual(json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json']),result)

    def test_owned_reviewed_explain_uses_qwen_once_without_deepseek_and_keeps_paper_archive(self):
        submission,item,result=self.queue_question();before=deepcopy(result); model_calls=self.provider.analyze_image.call_count
        events=len(self.events());voice_calls=self.transport.call_count
        with self.install_review(submission,item,result):
            request=self.request(item,'reviewed-explain')
            self.service.tutor.submit('student-a',submission['id'],item['id'],request)
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
            for _ in range(2):
                turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
                self.assertEqual(turn['assessment']['expectedAnswer'],'4');self.assertEqual(turn['teachingQuality']['status'],'verified')
                self.assertEqual(turn['audio']['status'],'ready');self.assertTrue(self.service.tutor.audio('student-a',submission['id'],item['id'],turn['id'])[0])
                display_text=' '.join(step['text'] for step in turn['steps'])
                self.assertIn('第2位',display_text)
                self.assertEqual(self.transport.call_args.args[0]['text'],normalize_teacher_speech(display_text))
                self.assertFalse(turn['assessment']['countsForAbility']);self.assertIsNone(turn['assessment']['independent'])
                detail=self.service.student_detail('student-a',submission['id'])['submission']
                grading=detail['originalPaperItems'][0]['reviewContext']['grading']
                self.assertEqual(grading['status'],'correct');self.assertEqual(grading['referenceAnswer'],'4')
                self.assertEqual(detail['originalPaperSummary']['incorrect'],0)
                self.assertNotIn('_confirmedAnswerReview',encoded(detail))
                parent=self.service.get('parent-a',submission['id'])['submission']
                self.assertEqual(parent['items'][0]['status'],'correct')
                self.assertEqual(parent['items'][0]['expectedAnswer'],'4')
                self.assertEqual(parent['items'][0]['gradingReference']['referenceAnswer'],'4')
                self.assertEqual(parent['items'][0]['reviewContext']['grading']['status'],'correct')
                self.assertNotIn('providerAssessment',parent['items'][0])
                self.assertEqual(parent['originalPaperSummary']['correct'],1)
                self.assertEqual(parent['originalPaperSummary']['incorrect'],0)
                self.assertEqual(parent['originalSummary']['correct'],1)
                self.assertEqual(parent['originalSummary']['pending'],0)
                self.assertEqual(parent['providerVerdictSummary']['incorrect'],0)
            self.service.tutor.submit('student-a',submission['id'],item['id'],request)
            self.assertFalse(self.service.process_next(submission_id=submission['id'])['processed'])
        self.assertEqual(self.provider.analyze_image.call_count,model_calls);self.assertEqual(self.transport.call_count,voice_calls+1)
        self.assertEqual(len(self.events()),events)
        self.assertEqual(json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json']),before)

    def test_review_withdrawal_blocks_cached_text_and_audio_without_replaying_ai(self):
        submission,item,result=self.queue_question();model_calls=self.provider.analyze_image.call_count
        with self.install_review(submission,item,result):
            self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item,'approved'))
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
            turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            stored=self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(turn['id'],)).fetchone()['result_json']
            voice_calls=self.transport.call_count
            (Path(self.tmp.name)/'reviews.json').write_text(encoded({'schemaVersion':REVIEW_SCHEMA,'reviews':[]}))
            blocked=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertEqual(blocked['assessment']['expectedAnswer'],'');self.assertEqual(blocked['audio']['status'],'unavailable')
            self.error('homework_tutor_audio_not_ready',lambda:self.service.tutor.audio('student-a',submission['id'],item['id'],turn['id']))
            self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(turn['id'],)).fetchone()['result_json'],stored)
            self.assertEqual(self.transport.call_count,voice_calls)
        self.assertEqual(self.provider.analyze_image.call_count,model_calls)

    def test_reviewed_lesson_can_resume_original_voice_without_an_ai_provider_receipt(self):
        submission,item,result=self.queue_question();model_calls=self.provider.analyze_image.call_count
        with self.install_review(submission,item,result):
            self.audio.enabled=False
            queued=self.service.tutor.submit('student-a',submission['id'],item['id'],self.request(item,'approved'))['tutor']['turns'][0]
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
            turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertEqual(turn['audio']['errorCode'],'homework_audio_unconfigured')
            self.audio.enabled=True
            self.service.tutor.resume_audio('student-a',submission['id'],item['id'],queued['id'],self.request(item,'voice-resume'))
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
            restored=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertEqual(restored['audio']['status'],'ready');self.assertEqual(restored['assessment']['expectedAnswer'],'4')
            self.assertEqual(self.provider.analyze_image.call_count,model_calls)
            self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM homework_provider_calls WHERE id LIKE 'hwtcall_%'").fetchone()['n'],0)

    def test_reviewed_question_free_followup_is_rejected_before_any_call_or_turn(self):
        submission,item,result=self.queue_question();model_calls=self.provider.analyze_image.call_count
        voice_calls=self.transport.call_count
        with self.install_review(submission,item,result):
            request={**self.request(item,'arbitrary-question'),'mode':'followup','message':'我可以做一整套新的应用题吗？'}
            self.error('homework_tutor_answer_review_required',lambda:self.service.tutor.submit('student-a',submission['id'],item['id'],request))
            self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_actions WHERE item_id=?',(item['id'],)).fetchone()['n'],0)
        self.assertEqual(self.provider.analyze_image.call_count,model_calls);self.assertEqual(self.transport.call_count,voice_calls)

    def test_reviewed_preset_and_current_numeric_answer_use_only_approved_teacher_content(self):
        submission,item,result=self.queue_question();model_calls=self.provider.analyze_image.call_count
        with self.install_review(submission,item,result):
            for mode,message,key in [('followup','为什么要这样做？请看着原题再解释一下。','why'),('answer','4','my-answer')]:
                request={**self.request(item,key),'mode':mode,'message':message}
                self.service.tutor.submit('student-a',submission['id'],item['id'],request)
                self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
                turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][-1]
                self.assertEqual(turn['assessment']['expectedAnswer'],'4');self.assertEqual(turn['teachingQuality']['status'],'verified')
                self.assertEqual(turn['audio']['status'],'ready');self.assertFalse(turn['assessment']['countsForAbility'])
                self.assertIsNone(turn['assessment']['independent'])
            self.assertEqual(self.provider.analyze_image.call_count,model_calls)
            self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM homework_provider_calls WHERE id LIKE 'hwtcall_%'").fetchone()['n'],0)
