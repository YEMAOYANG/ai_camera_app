"""Validated teacher text is visible while TTS runs, never before source checks."""
from copy import deepcopy
import json
from unittest import TestCase

from core.errors import ApiError
from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_tencent_lesson import lesson
from services.homework_answer_quality import reference_for_correction
from services.homework_service import canonical
from tests import test_homework_tencent_reference as fixtures
from tests import test_homework_analysis as audio_fixtures
from tests.test_homework_tutor import teacher_reply


class HomeworkTutorEarlyReplyTest(TestCase):
    setUp=fixtures.TencentReferenceTutorTests.setUp
    create=fixtures.TencentReferenceTutorTests.create
    upload=fixtures.TencentReferenceTutorTests.upload
    queued=fixtures.TencentReferenceTutorTests.queued
    due=fixtures.TencentReferenceTutorTests.due
    error=fixtures.TencentReferenceTutorTests.error
    prepare=fixtures.TencentReferenceTutorTests.prepare
    turn=fixtures.TencentReferenceTutorTests.turn
    get=fixtures.TencentReferenceTutorTests.get
    work=fixtures.TencentReferenceTutorTests.work

    def followup(self):
        self.prepare()
        self.response=teacher_reply(teacherText='老师回答：按这道原题的解析，数图里的苹果，一共有5个。',
            assessment={'status':'guidance_only','reason':'依据原解析','expectedAnswer':'5'},
            steps=[{'text':'先看原图，数出全部苹果。','visual':{'kind':'paper_region','region':{'x':0.,'y':0.,'width':1.,'height':1.}}},
                   {'text':'一共有5个苹果，这道小题填5。','visual':{'kind':'paper_region','region':{'x':0.,'y':0.,'width':1.,'height':1.}}}])
        self.main.analyze_image.return_value=AiVisionResponse(json.dumps(self.response),'fixture','fixture-tutor')
        return self.turn('followup','能更详细解释一下吗？')['turns'][-1]

    def test_get_shows_full_validated_reply_during_tts_without_finishing_or_resubmitting(self):
        queued=self.followup()
        self.assertFalse(queued['replyReady'])
        self.assertEqual(queued['teacherText'],'')
        captured=[]
        def voice(payload,headers):
            shown=self.get()['turns'][-1]
            captured.append(deepcopy(shown))
            self.assertEqual(shown['status'],'working')
            self.assertTrue(shown['replyReady'])
            self.assertEqual(shown['audio']['status'],'pending')
            self.assertEqual(shown['teacherText'],self.response['teacherText'])
            self.assertEqual(len(shown['steps']),2)
            self.assertEqual(shown['teachingQuality']['status'],'guidance')
            self.error('homework_tutor_pending',lambda:self.turn('followup','再问一次',key='not-allowed'))
            self.assertEqual(self.get()['correction']['attempts'],0)
            return audio_fixtures.wav_response(payload,headers)
        self.transport.side_effect=voice
        self.assertTrue(self.work()['ok'])
        final=self.get()['turns'][-1]
        self.assertEqual(len(captured),1)
        self.assertTrue(final['replyReady'])
        self.assertEqual(final['status'],'ready')
        self.assertEqual(final['audio']['status'],'ready')
        self.assertEqual(self.main.analyze_image.call_count,1)
        self.assertEqual(self.transport.call_count,self.voice_before+1)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(self.item['id'],)).fetchone()['result_json'],self.before_raw)

    def test_voice_crash_keeps_validated_text_in_unknown_without_any_automatic_retry(self):
        self.followup()
        observed=[]
        def crash(*args,**kwargs):
            observed.append(self.get()['turns'][-1])
            raise RuntimeError('isolated worker interruption after text validation')
        self.service.tutor._voice=crash
        outcome=self.work()
        self.assertEqual(outcome['status'],'unknown')
        shown=self.get()['turns'][-1]
        self.assertEqual(shown['status'],'unknown')
        self.assertTrue(shown['replyReady'])
        self.assertEqual(shown['teacherText'],self.response['teacherText'])
        self.assertEqual(shown['audio']['status'],'unavailable')
        self.assertTrue(observed[0]['replyReady'])
        self.error('homework_tutor_pending',lambda:self.turn('followup','再发一次',key='retry'))
        self.assertFalse(self.work()['processed'])
        self.assertEqual(self.main.analyze_image.call_count,1)
        self.assertEqual(self.get()['correction']['attempts'],0)

    def test_known_voice_failure_keeps_text_but_cannot_create_new_paid_turn(self):
        self.followup()
        def fail(*args,**kwargs):
            raise ApiError('homework_audio_text_invalid','isolated validation failure',400)
        self.service.tutor._voice=fail
        outcome=self.work()
        self.assertEqual(outcome['status'],'failed')
        shown=self.get()['turns'][-1]
        self.assertTrue(shown['replyReady'])
        self.assertEqual(shown['teacherText'],self.response['teacherText'])
        self.assertEqual(shown['audio']['status'],'unavailable')
        self.error('homework_tutor_pending',lambda:self.turn('followup','继续问',key='retry'))
        self.assertFalse(self.work()['processed'])
        self.assertEqual(self.main.analyze_image.call_count,1)

    def test_changed_reference_withdraws_already_published_text_even_in_unknown_state(self):
        self.followup()
        self.service.tutor._voice=lambda *args,**kwargs:(_ for _ in ()).throw(RuntimeError('isolated interruption'))
        self.work()
        before=self.get()['turns'][-1]
        self.assertTrue(before['replyReady'])
        raw=json.loads(self.before_raw)
        raw['tencentRaw']['answer']['KnowledgePoints']=['current reference changed']
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(raw),self.item['id']))
        self.db.raw.commit()
        count=self.main.analyze_image.call_count
        shown=self.get()['turns'][-1]
        self.assertFalse(shown['replyReady'])
        self.assertEqual(shown['reviewState'],'required')
        self.assertNotEqual(shown['teacherText'],self.response['teacherText'])
        self.assertEqual(shown['assessment']['expectedAnswer'],'')
        self.assertNotIn('5',json.dumps(shown['steps'],ensure_ascii=False))
        self.assertEqual(self.main.analyze_image.call_count,count)
        # The immutable paid result remains saved; only read authority changes.
        stored=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(before['id'],)).fetchone()['result_json'])
        self.assertTrue(stored['replyReady'])
        self.assertEqual(stored['teacherText'],self.response['teacherText'])

    def test_marker_cannot_publish_forged_or_unverified_working_text(self):
        self.prepare()
        queued=self.turn()['turns'][-1]
        record=self.db.execute('SELECT * FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()
        row=self.service.repository.submission(self.db,'family-a',self.identity)
        source=self.service._learning_result(self.db,row,self.item)
        fake=lesson(source,reference_for_correction(source))
        turn=json.loads(record['result_json'])
        turn.update(**fake,status='working',replyReady=True)
        turn['teacherText']='直接填999，这是假造的未校验答案。'
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(canonical(turn),queued['id']))
        self.db.raw.commit()
        shown=self.get()['turns'][-1]
        self.assertFalse(shown['replyReady'])
        self.assertNotIn('999',shown['teacherText'])
        self.assertEqual(shown['reviewState'],'required')
        self.assertEqual(shown['assessment']['expectedAnswer'],'')
        self.main.analyze_image.assert_not_called()
        self.assertEqual(self.transport.call_count,self.voice_before)

    def test_conflicting_model_reference_never_becomes_early_reply_or_audio(self):
        self.followup()
        wrong=deepcopy(self.response)
        wrong['assessment']['expectedAnswer']='8'
        self.main.analyze_image.return_value=AiVisionResponse(json.dumps(wrong),'fixture','fixture-tutor')
        self.assertFalse(self.work()['ok'])
        shown=self.get()['turns'][-1]
        self.assertFalse(shown['replyReady'])
        self.assertNotEqual(shown['teacherText'],self.response['teacherText'])
        self.assertEqual(self.transport.call_count,self.voice_before)
        self.assertEqual(self.main.analyze_image.call_count,1)
