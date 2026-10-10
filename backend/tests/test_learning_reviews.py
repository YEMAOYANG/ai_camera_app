"""Real isolated transactions. No existing database, provider, device or paid calls."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from flask import Flask
from core.errors import ApiError
from services.learning_evidence_service import record_answer, revoke_event, revoke_source, weaknesses, digest, record_course_answers, record_textbook_changes
from services.learning_review_service import LearningReviewService
from services.learning_review_reminder import SafeReviewReminderSender
from services.task_runtime_service import TaskRuntimeService
from test_textbook_learning import IsolatedDatabase


def at(day, hour=9):
    return int(datetime.fromisoformat(f'{day}T{hour:02}:00:00').replace(tzinfo=ZoneInfo('Asia/Shanghai')).timestamp()*1000)


def question(skill='addition20', ordinal=0, course='math-1'):
    value={'id':f'{skill}-{ordinal}','version':'reviewed-1','renderer':'picture_choices','subject':'math',
        'gradeCode':'primary_1','knowledgeId':'math:primary_1:'+skill,'knowledgeLabel':skill,'courseId':course,
        'courseVersion':'1','courseTitle':course,'prompt':f'数一数第{ordinal}幅图里的苹果。',
        'visual':{'art':{'src':'/fixture/apples.png'}},'options':[{'value':'A','label':'2','picture':{'src':'/fixture/two.png'}},
        {'value':'B','label':'3','picture':{'src':'/fixture/three.png'}}],
        'correctAnswer':'A','hints':['数一数','点着数','选第一幅图'], 'explanation':'两个苹果。',
        'promptAudioAsset':'prompt.wav','hintAudioAssets':['hint1.wav','hint2.wav','hint3.wav'],
        'explanationAudioAsset':'explanation.wav','estimatedSeconds':60,'approved':True,'private':False}
    value['fingerprint']=digest({k:value[k] for k in ('knowledgeId','prompt','options','correctAnswer','visual')})
    return value


class ReviewsTest(unittest.TestCase):
    def setUp(self):
        self.db=IsolatedDatabase(('085_learning_reviews.sql',))
        self.addCleanup(self.db.raw.close)
        columns='id,family_id,child_id,title,description,type,status,scheduled_date,scheduled_start,scheduled_end,schedule_type,start_at,due_at,priority,reward_points,requires_parent_confirmation,created_by,reminder_minutes_before,reminder_status,timezone,learning_assignment_key,learning_slot,created_at,updated_at,next_reminder_at,started_at,completed_at,ended_at,completion_source,evidence_summary'
        self.db.execute('CREATE TABLE tasks ('+','.join(c+' TEXT' for c in columns.split(','))+')')
        self.child={'id':'child-a','family_id':'family-a','grade_code':'primary_1','grade_selection_revision':1}
        self.db.execute('INSERT INTO children VALUES (?,?,?,?)',tuple(self.child.values()))
        self.db.execute("INSERT INTO children VALUES ('child-b','family-b','primary_1',1)")
        self.now=at('2026-10-03')
        self.questions=[question(skill,i,course) for skill,course in [('addition20','math-1'),('subtract20','math-2')] for i in range(5)]
        self.auth=SimpleNamespace(authenticate=lambda token:{'family':{'id':'family-'+token[-1]},'user':{'id':'parent-'+token[-1]}})
        self.student=SimpleNamespace(authenticate=lambda token:{'principal':{'family_id':'family-'+token[-1],'child_id':'child-'+token[-1]}})
        self.sender=Mock(return_value={'delivered':True})
        self.service=LearningReviewService(self.db,auth_service=self.auth,student_auth_service=self.student,
            parent_authorize=lambda *args:None,question_pool=lambda c,ch:(deepcopy(self.questions),[]),clock=lambda:self.now,reminder_sender=self.sender)
        self.db.raw.commit()

    def evidence(self,q=None,**overrides):
        args={'family_id':'family-a','child_id':'child-a','source_kind':'classroom','source_id':'course-session',
            'event_key':'q'+str(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events').fetchone()['n']),
            'question':q or question(),'answer':'B','correct':False,'occurred_at':self.now-1000,
            'hint_used':False,'adult_help':False,'independent':True}
        args.update(overrides)
        with self.db.transaction():return record_answer(self.db,**args)

    def create(self):
        self.evidence(question())
        self.evidence(question('subtract20',0,'math-2'))
        with self.db.transaction():return self.service.ensure_week(self.db,self.child,self.now)

    def view(self,run):return self.service.student_detail('student-a',run['id'])

    def action(self,run,action,**extra):
        revision=self.view(run)['review']['revision']
        return self.service.student_action('student-a',run['id'],{'action':action,'revision':revision,'requestId':f'{action}-{revision}',**extra})

    def answer(self,run,value='A',**extra):
        view=self.view(run)
        return self.service.answer('student-a',run['id'],{'questionId':view['currentQuestion']['id'],'response':value,
            'requestId':'answer-'+str(view['review']['revision']),'revision':view['review']['revision'],**extra})

    def test_synthetic_score_and_report_do_not_enter_real_evidence_or_summary(self):
        from services.report_learning_summary import review_report_for_period
        run=self.create()
        baseline=self.db.execute('SELECT * FROM learning_answer_events ORDER BY id').fetchall()
        before=weaknesses(self.db,family_id='family-a',child_id='child-a')
        coverage=json.loads(run['coverage_json']);coverage.update(syntheticFixture=True,demoTitle='测试体验 · 报告样例')
        self.db.execute('UPDATE learning_review_runs SET coverage_json=? WHERE id=?',(json.dumps(coverage),run['id']));self.db.raw.commit()
        self.action(run,'start')
        total=self.view(run)['review']['totalQuestions']
        for index in range(total):
            self.answer(run,'B' if index==0 else 'A')
            result=self.action(run,'next')
        self.assertEqual(result['review']['status'],'completed')
        self.assertEqual(result['review']['correctCount'],total-1)
        self.assertEqual(result['review']['title'],'测试体验 · 报告样例')
        self.assertEqual(result['report']['answeredCount'],total)
        self.assertIn('不参与',result['report']['assessmentScope'])
        self.assertEqual(self.db.execute('SELECT * FROM learning_answer_events ORDER BY id').fetchall(),baseline)
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a'),before)
        summary=review_report_for_period(self.db,family_id='family-a',start=self.now-2000,end=self.now+1)
        self.assertEqual(summary['weekendReviews'],[])

    def test_only_exact_trusted_boolean_enables_fixture_isolation(self):
        from services.learning_review_service import synthetic_fixture
        from services.report_learning_summary import review_report_for_period
        for value in (False,'true',1,None,{},[]):
            self.assertFalse(synthetic_fixture({'coverage_json':json.dumps({'syntheticFixture':value})}))
        run=self.create()
        coverage=json.loads(run['coverage_json']);coverage.update(syntheticFixture='true',demoTitle='不能覆盖正式标题')
        self.db.execute('UPDATE learning_review_runs SET coverage_json=? WHERE id=?',(json.dumps(coverage),run['id']));self.db.raw.commit()
        self.action(run,'start');self.answer(run)
        self.assertEqual(self.view(run)['review']['title'],'周末小复习')
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM learning_answer_events WHERE source_kind='review'").fetchone()['n'],1)
        summary=review_report_for_period(self.db,family_id='family-a',start=self.now-2000,end=self.now+1)
        self.assertEqual(len(summary['weekendReviews']),1)
        view=self.view(run)
        with self.assertRaises(ApiError):
            self.service.answer('student-a',run['id'],{'questionId':view['currentQuestion']['id'],'response':'A',
                'requestId':'bad-fixture','revision':view['review']['revision'],'syntheticFixture':True})

    def test_synthetic_paused_run_does_not_block_real_week_or_send_reminder(self):
        run=self.create()
        coverage=json.loads(run['coverage_json']);coverage['syntheticFixture']=True
        self.db.execute('UPDATE learning_review_runs SET coverage_json=?,task_type=? WHERE id=?',
                        (json.dumps(coverage),'synthetic_review',run['id']));self.db.raw.commit()
        self.action(run,'start');self.action(run,'pause')
        unchanged=self.db.execute('SELECT * FROM learning_review_runs WHERE id=?',(run['id'],)).fetchone()
        self.now+=7*86400000
        with self.db.transaction():
            normal=self.service.ensure_week(self.db,self.child,self.now)
            synthetic=dict(unchanged,status='scheduled',reminder_status='pending',scheduled_at=self.now,reminder_expires_at=self.now+1000)
            self.service._remind(self.db,self.child,synthetic,self.now)
        self.assertNotEqual(normal['id'],run['id'])
        self.assertEqual(self.db.execute('SELECT * FROM learning_review_runs WHERE id=?',(run['id'],)).fetchone(),unchanged)
        self.sender.assert_not_called()

    def test_authorized_existing_child_seed_is_separate_and_idempotent(self):
        from scripts.dev_review_sample import create_review_samples
        normal=self.create()
        original=self.db.execute('SELECT * FROM learning_review_runs WHERE id=?',(normal['id'],)).fetchone()
        before=self.db.execute('SELECT * FROM learning_answer_events ORDER BY id').fetchall()
        pool=[question('skill'+str(skill),variant,'picture-course') for skill in range(6) for variant in range(4)]
        with patch('scripts.dev_review_sample._published_pool',return_value=pool):
            with self.db.transaction():
                seeded=create_review_samples(self.db,child=self.child,course={'id':'picture-course','version':'1'},
                    now=self.now,seed_namespace='explicit-test',authorized_existing_child=True)
            self.assertEqual(self.db.execute('SELECT * FROM learning_review_runs WHERE id=?',(normal['id'],)).fetchone(),original)
            states={row['scenario']:row for row in seeded['reviews']}
            self.assertEqual((states['completed']['answeredCount'],states['completed']['correctCount']),(6,5))
            self.assertEqual((states['paused']['status'],states['paused']['answeredCount']),('paused',0))
            self.assertEqual((states['ready']['status'],states['ready']['totalQuestions']),('scheduled',10))
            rows=self.db.execute('SELECT * FROM learning_review_runs ORDER BY id').fetchall()
            for row in rows:
                if row['id']==normal['id']:continue
                self.assertEqual(row['task_type'],'synthetic_review')
                self.assertNotEqual(row['week_start'],normal['week_start'])
                self.assertIs(json.loads(row['coverage_json'])['syntheticFixture'],True)
            with self.db.transaction():
                repeated=create_review_samples(self.db,child=self.child,course={'id':'picture-course','version':'1'},
                    now=self.now+7*86400000,seed_namespace='explicit-test',authorized_existing_child=True)
            self.assertEqual(seeded,repeated)
            self.assertEqual(self.db.execute('SELECT * FROM learning_review_runs ORDER BY id').fetchall(),rows)
            self.assertEqual(self.db.execute('SELECT * FROM learning_answer_events ORDER BY id').fetchall(),before)

    def test_evidence_dedupe_conflict_and_family_scope(self):
        first=self.evidence(event_key='first')
        self.assertEqual(self.evidence(event_key='first')['id'],first['id'])
        with self.assertRaises(ApiError):self.evidence(event_key='first',answer='A',correct=True)
        self.assertEqual(weaknesses(self.db,family_id='family-b',child_id='child-b'),[])
        rows=weaknesses(self.db,family_id='family-a',child_id='child-a')
        self.assertEqual((rows[0]['wrongCount'],rows[0]['independentCount']),(1,1))

    def test_photo_unknown_or_unconfirmed_never_becomes_independent_evidence(self):
        self.evidence(source_kind='homework',independent=True)
        self.evidence(source_kind='homework',source_id='other',confirmed=False,correct=None)
        row=weaknesses(self.db,family_id='family-a',child_id='child-a')[0]
        self.assertEqual((row['sampleCount'],row['independentCount'],row['pendingCount']),(1,0,1))

    def test_classroom_and_practice_share_skill_but_unknown_help_does_not_claim_independence(self):
        app=Flask(__name__);app.config['LEARNING_REVIEW_ENABLED']=True
        session={'id':'normal-session','family_id':'family-a','child_id':'child-a'}
        course={'id':'normal-course','version':'1','grade_code':'primary_1','subject':'math','node_code':'range20',
                'title':'数一数','content_json':json.dumps({'teachingFlow':{'independentQuestionIds':['q1']}})}
        questions=[{'id':'q1','type':'numeric','prompt':'数一数','answer':'2','skill':'count'}]
        answer={'questionId':'q1','answer':'3','correct':False,'attemptNumber':1,'answeredAt':self.now}
        with app.app_context(),self.db.transaction():
            record_course_answers(self.db,session,course,questions,[answer],self.now)
            record_course_answers(self.db,session,course,questions,[answer],self.now)
            record_course_answers(self.db,session,course,questions,[{**answer,'answer':'2','correct':True,'attemptNumber':2}],self.now)
            record_course_answers(self.db,{**session,'id':'practice-session'},course,questions,[answer],self.now,source_kind='practice')
        rows=weaknesses(self.db,family_id='family-a',child_id='child-a')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['sources'],['classroom','practice'])
        self.assertEqual((rows[0]['wrongCount'],rows[0]['independentCount']),(2,0))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events').fetchone()['n'],3)

    def test_authored_game_and_transfer_save_wrong_first_independent_answer(self):
        from content import textbook_journey as journey
        from test_textbook_activity import release_fixture
        release=release_fixture();state=journey.initial({},release)
        spec=journey.definition(state=state,release=release);skill=spec.skills[0]
        question=spec.flow['bank'][skill][0]
        previous=deepcopy(state)
        record={'phase':'transfer','index':0,'round':0,'skill':skill,'questionId':question['id'],
                'choice':next(o['value'] for o in question['options'] if o['value'] not in question['targets']),
                'correct':False,'hintUsed':False,'adultHelp':False}
        state['challenge']['records']=[record];state['updatedAt']=self.now
        session={'id':'authored','family_id':'family-a','child_id':'child-a'}
        course={'id':'天地人','version':'1','grade_code':'primary_1','subject':'chinese','title':'天地人'}
        app=Flask(__name__);app.config['LEARNING_REVIEW_ENABLED']=True
        with app.app_context(),self.db.transaction():
            record_textbook_changes(self.db,session,course,state,previous,release)
            record_textbook_changes(self.db,session,course,state,state,release)
        row=self.db.execute('SELECT * FROM learning_answer_events').fetchone()
        self.assertEqual((row['source_kind'],row['correct'],row['independent']),('textbook_play',0,1))
        self.assertIn('promptAudioAsset',json.loads(row['question_json']))

    def test_exact_arithmetic_unifies_photo_classroom_and_practice_without_fuzzy_labels(self):
        from services.homework_math import check_item
        from services.learning_knowledge import canonical_knowledge,POLICY
        raw={'id':'q','type':'numeric','prompt':'3 + 2 = ?','answer':'5','skill':'models-label'}
        checked=check_item({'type':'arithmetic','prompt':'3+2=?','studentAnswer':'4','confidence':1,'annotationAmbiguous':False},
                           grade='primary_1',subject='math',policy=POLICY)
        photo=question();photo.update(knowledgeId=checked['knowledgeId'],knowledgeLabel=checked['knowledgeLabel'])
        self.evidence(photo,source_kind='homework')
        course={'id':'addition-course','version':'1','grade_code':'primary_1','subject':'math','node_code':'mixed-course',
                'title':'计算','content_json':'{}'}
        session={'id':'classroom','family_id':'family-a','child_id':'child-a'}
        answer={'questionId':'q','correct':False,'answer':'4','answeredAt':self.now}
        app=Flask(__name__);app.config['LEARNING_REVIEW_ENABLED']=True
        with app.app_context(),self.db.transaction():
            record_course_answers(self.db,session,course,[raw],[answer],self.now)
            record_course_answers(self.db,{**session,'id':'practice'},course,[raw],[answer],self.now,source_kind='practice')
        result=weaknesses(self.db,family_id='family-a',child_id='child-a')
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['knowledgeId'],'math:primary_1:addition:range20')
        self.assertEqual(result[0]['sources'],['classroom','homework','practice'])
        self.assertEqual(result[0]['wrongCount'],3)
        for uncertain in ({**raw,'prompt':'有3个苹果，又来了2个'}, {**raw,'answer':'6'},
                          {**raw,'knowledgeId':'math:primary_1:subtraction:range20'}):
            self.assertIsNone(canonical_knowledge(uncertain,subject='math',grade='primary_1'))

    def test_revoke_and_delete_remove_weakness_and_private_text(self):
        self.evidence(source_kind='homework',source_id='photo',event_key='item:1')
        revoke_event(self.db,family_id='family-a',child_id='child-a',source_kind='homework',source_id='photo',
                     event_key='item:1',now=self.now,reason='correction')
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a'),[])
        revoke_source(self.db,family_id='family-a',child_id='child-a',source_kind='homework',source_id='photo',now=self.now,reason='deleted',purge=True)
        self.assertEqual(self.db.execute('SELECT question_json FROM learning_answer_events').fetchone()['question_json'],'{}')

    def private_review(self):
        q=question()
        source=self.evidence(q,source_kind='homework',source_id='photo',event_key='item:1')
        q.update(private=True,sourceEventId=source['id'],sourceSubmissionId='photo',sourceItemId='item',sourceRevision=1,
                 courseId=None,renderer='quantity_arithmetic',promptAudioAsset='homework.photo.item.1.prompt')
        self.service.question_pool=lambda conn,child:([],[])
        self.service.private_question_pool=lambda conn,child:([q],[])
        with self.db.transaction():run=self.service.ensure_week(self.db,self.child,self.now)
        return run,q

    def test_private_homework_question_is_original_practice_and_authenticated_audio(self):
        run,q=self.private_review()
        self.assertEqual(json.loads(run['coverage_json'])['lessonCount'],0)
        self.assertTrue(json.loads(run['coverage_json'])['contentGap'])
        callback=Mock(return_value='/private/test.wav')
        self.service.private_audio_file=callback
        with self.assertRaises(ApiError):self.service.audio('student-a',run['id'],q['promptAudioAsset'])
        view=self.action(run,'start')
        self.assertEqual(view['currentQuestion']['evidenceMode'],'repeated_practice')
        self.assertEqual(self.service.audio('student-a',run['id'],q['promptAudioAsset']),'/private/test.wav')
        with self.assertRaises(ApiError):self.service.audio('student-b',run['id'],q['promptAudioAsset'])
        self.assertFalse(self.answer(run)['feedback']['independent'])
        report=self.action(run,'next')['report']
        self.assertEqual((report['repeatedPracticeCount'],report['independentFirstCount']),(1,0))

    def test_photo_correction_withdraws_active_paper_and_derived_evidence(self):
        run,q=self.private_review();self.action(run,'start');self.answer(run)
        with self.db.transaction():
            revoke_event(self.db,family_id='family-a',child_id='child-a',source_kind='homework',source_id='photo',
                         event_key='item:1',now=self.now,reason='corrected')
        view=self.view(run)
        self.assertEqual((view['review']['status'],view['review']['correctCount']),('content_gap',0))
        self.assertIsNone(view['currentQuestion'])
        with self.assertRaises(ApiError):self.service.audio('student-a',run['id'],q['promptAudioAsset'])
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a'),[])
        item=self.service.repository.items(self.db,run['id'])[0]
        self.assertEqual(item['evidence_mode'],'withdrawn')
        self.assertNotIn('prompt',json.loads(item['snapshot_json']))

    def test_deleted_completed_photo_paper_preserves_completion_but_removes_score(self):
        run,q=self.private_review();self.action(run,'start');self.answer(run);self.action(run,'next')
        with self.db.transaction():
            revoke_source(self.db,family_id='family-a',child_id='child-a',source_kind='homework',source_id='photo',
                          now=self.now,reason='deleted',purge=True)
        result=self.service.parent_detail('parent-a','child-a',run['id'])
        self.assertEqual(result['review']['status'],'completed')
        self.assertEqual((result['report']['answeredCount'],result['report']['withdrawnCount']),(0,1))
        self.assertEqual(result['review']['correctCount'],0)
        self.assertEqual(self.db.execute("SELECT question_json FROM learning_answer_events WHERE source_kind='review'").fetchone()['question_json'],'{}')

    def test_two_lessons_week_unique_and_frozen_policy(self):
        run=self.create()
        with self.db.transaction():second=self.service.ensure_week(self.db,self.child,self.now)
        self.assertEqual(run['id'],second['id'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM tasks').fetchone()['n'],1)
        self.assertEqual(self.view(run)['review']['coverage']['lessonCount'],2)
        self.assertEqual(self.view(run)['review']['totalQuestions'],4)
        self.assertEqual(self.view(run)['review']['estimatedMinutes'],4)
        self.assertIsNone(self.view(run)['currentQuestion'])

    def test_start_only_current_question_and_no_answer_before_help(self):
        run=self.create();view=self.action(run,'start')
        self.assertNotIn('correctAnswer',view['currentQuestion'])
        self.assertNotIn('hintAudioAssets',view['currentQuestion'])
        self.assertEqual(len(view['currentQuestion']['options']),2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_review_items WHERE exposure_at IS NOT NULL').fetchone()['n'],1)

    def test_hint_persists_reload_and_cannot_be_client_erased(self):
        run=self.create();self.action(run,'start');self.action(run,'hint')
        self.assertTrue(self.view(run)['currentQuestion']['helpUsed'])
        response=self.answer(run)
        self.assertFalse(response['feedback']['independent'])
        self.assertEqual(response['review']['independentCorrectCount'],0)
        self.assertEqual(self.view(run)['feedback'],response['feedback'])
        with self.assertRaises(ApiError):self.answer(run,hintUsed=False)

    def test_independent_wrong_answer_keeps_denominator(self):
        run=self.create();self.action(run,'start');answer=self.answer(run,'B')
        self.assertTrue(answer['feedback']['independent'])
        report=self.service.parent_detail('parent-a','child-a',run['id'])['report']
        self.assertEqual((report['independentFirstCount'],report['independentFirstCorrect']),(1,0))

    def test_answer_retries_are_idempotent_and_payload_conflicts_rejected(self):
        run=self.create();view=self.action(run,'start')
        data={'questionId':view['currentQuestion']['id'],'response':'A','requestId':'network-retry','revision':view['review']['revision']}
        one=self.service.answer('student-a',run['id'],data)
        two=self.service.answer('student-a',run['id'],data)
        self.assertEqual(one,two)
        with self.assertRaises(ApiError):self.service.answer('student-a',run['id'],{**data,'response':'B'})
        with self.assertRaises(ApiError):self.service.answer('student-b',run['id'],data)

    def test_frozen_hash_and_grade_changes_are_rejected(self):
        run=self.create();self.action(run,'start')
        self.db.execute("UPDATE learning_review_items SET snapshot_json='{}' WHERE run_id=? AND ordinal=0",(run['id'],));self.db.raw.commit()
        with self.assertRaises(ApiError):self.view(run)
        self.db.execute("UPDATE children SET grade_selection_revision=2 WHERE id='child-a'");self.db.raw.commit()
        with self.assertRaises(ApiError):self.view(run)

    def test_finish_requires_answers_next_and_report_separates_evidence(self):
        run=self.create();self.action(run,'start')
        with self.assertRaises(ApiError):self.action(run,'next')
        for _ in range(run['total_questions']):
            self.answer(run);view=self.action(run,'next')
        self.assertEqual(view['review']['status'],'completed')
        self.assertEqual(view['report']['independentFirstCorrect'],4)
        self.assertEqual(self.db.execute('SELECT status FROM tasks').fetchone()['status'],'completed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events WHERE source_kind=\'review\'').fetchone()['n'],4)

    def test_previously_seen_item_is_practice_even_if_new_when_paper_created(self):
        run=self.create();view=self.action(run,'start')
        item=self.service.repository.items(self.db,run['id'])[0]
        q=json.loads(item['snapshot_json'])
        self.evidence(q,source_id='other-lesson',correct=True,answer='A')
        result=self.answer(run)
        self.assertFalse(result['feedback']['independent'])
        self.assertEqual(self.view(run)['currentQuestion']['evidenceMode'],'repeated_practice')

    def test_no_replay_of_expired_reminder_no_missed_or_auto_start(self):
        run=self.create();self.now=at('2026-10-03',12)
        self.service.tick(self.now)
        latest=self.view(run)['review']
        self.assertEqual((latest['status'],latest['reminderStatus']),('needs_schedule','expired'))
        self.sender.assert_not_called()
        runtime=object.__new__(TaskRuntimeService)
        task={'learning_slot':'weekend_review','status':'scheduled'}
        self.assertEqual(runtime._advance_task(None,task,now=datetime.now()),(task,[]))

    def test_new_week_supersedes_unstarted_but_retains_started_paper(self):
        run=self.create();self.now+=7*86400000
        with self.db.transaction():new=self.service.ensure_week(self.db,self.child,self.now)
        self.assertNotEqual(run['id'],new['id'])
        self.assertEqual(self.view(run)['review']['status'],'superseded')
        self.action(new,'start');self.now+=7*86400000
        with self.db.transaction():last=self.service.ensure_week(self.db,self.child,self.now)
        self.assertEqual(last['id'],new['id'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_review_runs').fetchone()['n'],2)

    def test_grade_revision_change_retires_started_review_without_blocking_new_week(self):
        run=self.create();self.action(run,'start')
        self.child['grade_selection_revision']=2
        self.db.execute("UPDATE children SET grade_selection_revision=2 WHERE id='child-a'");self.db.raw.commit()
        self.now+=7*86400000
        with self.db.transaction():new=self.service.ensure_week(self.db,self.child,self.now)
        self.assertNotEqual(new['id'],run['id'])
        self.assertEqual(new['grade_revision'],2)
        self.assertEqual(self.db.execute('SELECT status FROM learning_review_runs WHERE id=?',(run['id'],)).fetchone()['status'],'superseded')

    def test_skip_pause_preference_and_resume_never_add_negative_mark(self):
        run=self.create()
        result=self.service.schedule_action('parent-a',run['id'],{'childId':'child-a','action':'skip','appointmentRevision':0,'requestId':'skip'})
        self.assertEqual(result['review']['status'],'skipped')
        self.assertTrue(result['report']['notParticipated'])
        self.assertEqual(self.db.execute('SELECT status FROM tasks').fetchone()['status'],'cancelled')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events').fetchone()['n'],2)
        self.service.preferences('parent-a','child-a',{'revision':0,'pausedUntil':'2026-10-25'})
        self.now+=7*86400000
        with self.db.transaction():self.assertIsNone(self.service.ensure_week(self.db,self.child,self.now))

    def test_reschedule_revision_and_snooze_allowed_window(self):
        run=self.create()
        response=self.service.schedule_action('parent-a',run['id'],{'childId':'child-a','action':'reschedule','scheduledAt':self.now+86400000,
            'appointmentRevision':0,'requestId':'tomorrow'})
        self.assertEqual(response['review']['appointmentRevision'],1)
        with self.assertRaises(ApiError):self.service.schedule_action('parent-a',run['id'],{'childId':'child-a','action':'skip','appointmentRevision':0,'requestId':'stale'})
        self.now=at('2026-10-03',20)
        view=self.action(run,'snooze',minutes=20)
        self.assertEqual(view['review']['status'],'needs_schedule')
        task=self.db.execute('SELECT scheduled_date,scheduled_start,start_at FROM tasks').fetchone()
        self.assertEqual(task['scheduled_date'],'2026-10-04')
        self.assertIsNone(task['scheduled_start'])
        self.assertIsNone(task['start_at'])

    def test_defer_outside_window_preserves_nonnull_real_task_calendar_constraint(self):
        run=self.create()
        self.db.execute("CREATE TRIGGER require_task_calendar BEFORE UPDATE OF scheduled_date ON tasks WHEN NEW.scheduled_date IS NULL BEGIN SELECT RAISE(ABORT,'scheduled_date is NOT NULL'); END")
        self.db.raw.commit();self.now=at('2026-10-03',20)
        result=self.action(run,'snooze')
        self.assertEqual(result['review']['status'],'needs_schedule')
        self.assertEqual(self.db.execute('SELECT scheduled_date FROM tasks').fetchone()['scheduled_date'],'2026-10-03')

    def test_weekend_preferences_move_only_unstarted_appointment_and_invalidate_old_revision(self):
        run=self.create()
        snapshots=[i['snapshot_sha256'] for i in self.service.repository.items(self.db,run['id'])]
        self.service.preferences('parent-a','child-a',{'revision':0,'weekday':7})
        latest=self.view(run)['review']
        self.assertEqual(latest['scheduledAt'],at('2026-10-04',10))
        self.assertEqual(latest['appointmentRevision'],1)
        self.assertEqual(self.db.execute('SELECT scheduled_date FROM tasks').fetchone()['scheduled_date'],'2026-10-04')
        self.assertEqual(snapshots,[i['snapshot_sha256'] for i in self.service.repository.items(self.db,run['id'])])
        with self.assertRaises(ApiError):self.service.schedule_action('parent-a',run['id'],{
            'childId':'child-a','action':'skip','appointmentRevision':0,'requestId':'stale-appointment'})
        self.now=at('2026-10-03',10)
        self.service.tick(self.now)
        self.sender.assert_not_called()
        self.action(run,'start')
        self.service.preferences('parent-a','child-a',{'revision':1,'weekday':6})
        self.assertEqual(self.view(run)['review']['scheduledAt'],latest['scheduledAt'])

    def test_past_weekend_preference_requires_reschedule_without_replaying_reminder(self):
        run=self.create();self.now=at('2026-10-04',12)
        self.service.preferences('parent-a','child-a',{'revision':0,'weekday':6})
        self.assertEqual(self.view(run)['review']['status'],'needs_schedule')
        self.service.tick(self.now)
        self.sender.assert_not_called()

    def test_audio_membership_and_answer_audio_not_exposed_early(self):
        run=self.create();self.action(run,'start')
        with self.assertRaises(ApiError):self.service.audio('student-a',run['id'],'explanation.wav')
        with self.assertRaises(ApiError):self.service.audio('student-b',run['id'],'prompt.wav')
        with patch('content.textbook_journey.audio_file',return_value='/verified/audio.wav'):
            self.assertEqual(self.service.audio('student-a',run['id'],'prompt.wav'),'/verified/audio.wav')
            self.action(run,'explanation')
            self.assertEqual(self.service.audio('student-a',run['id'],'explanation.wav'),'/verified/audio.wav')

    def test_content_gap_is_honest_and_no_questions_or_generation(self):
        self.service.question_pool=lambda *args:([],['尚未配置的第二课'])
        run=self.create();view=self.view(run)
        self.assertEqual(view['review']['status'],'content_gap')
        self.assertTrue(view['review']['coverage']['contentGap'])
        self.assertEqual(view['review']['totalQuestions'],0)

    def test_quiet_mode_and_disabled_voice_do_not_send(self):
        run=self.create();self.now=at('2026-10-03',10)
        self.db.execute("INSERT INTO app_settings VALUES ('family-a','notifications',?,?)",(json.dumps({'quietHoursEnabled':True,'quietHoursStart':'09:00','quietHoursEnd':'11:00'}),self.now))
        self.db.execute("INSERT INTO app_settings VALUES ('family-a','privacy',?,?)",(json.dumps({'voiceBroadcastAuthorized':True}),self.now));self.db.raw.commit()
        self.service.tick(self.now)
        self.sender.assert_not_called()
        self.assertEqual(self.view(run)['review']['reminderStatus'],'silent_quiet')

    def test_one_reminder_receipt_no_repeat_on_poll(self):
        run=self.create();self.now=at('2026-10-03',10)
        self.db.execute("INSERT INTO app_settings VALUES ('family-a','privacy',?,?)",(json.dumps({'voiceBroadcastAuthorized':True}),self.now));self.db.raw.commit()
        self.service.tick(self.now);self.service.tick(self.now+15000)
        self.sender.assert_called_once()
        self.assertEqual(self.view(run)['review']['status'],'scheduled')
        self.assertEqual(self.view(run)['review']['reminderStatus'],'delivered')

    def test_week_is_not_created_before_weekend_and_no_empty_child_task(self):
        self.now=at('2026-10-01');self.evidence()
        with self.db.transaction():self.assertIsNone(self.service.ensure_week(self.db,self.child,self.now))
        self.now=at('2026-10-03')
        with self.db.transaction():self.assertIsNone(self.service.ensure_week(self.db,{'id':'child-b','family_id':'family-b','grade_code':'primary_1','grade_selection_revision':1},self.now))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM tasks').fetchone()['n'],0)

    def test_flask_student_parent_blueprints_complete_saved_progress_and_report(self):
        from routes.api.v2.student_reviews import student_reviews_bp
        from routes.api.v1.learning_reviews import parent_learning_reviews_bp,parent_review_preferences_bp,parent_learning_weaknesses_bp
        run=self.create()
        app=Flask(__name__);app.config.update(TESTING=True,LEARNING_REVIEW_ENABLED=True)
        app.register_blueprint(student_reviews_bp,url_prefix='/api/v2/student/learning/reviews')
        app.register_blueprint(parent_learning_reviews_bp,url_prefix='/api/learning/reviews')
        app.register_blueprint(parent_review_preferences_bp,url_prefix='/api/children')
        app.register_blueprint(parent_learning_weaknesses_bp,url_prefix='/api/reports/learning')
        client=app.test_client();student={'Authorization':'Bearer student-a'};parent={'Authorization':'Bearer parent-a'}
        base='/api/v2/student/learning/reviews/'+run['id']
        with patch('services.service_factory.learning_review_service',return_value=self.service):
            self.assertEqual(client.get('/api/v2/student/learning/reviews',headers=student).json['reviews'][0]['id'],run['id'])
            current=client.get(base,headers=student).json
            def action(name):
                nonlocal current
                response=client.post(base+'/actions',headers=student,json={'action':name,'revision':current['review']['revision'],
                    'requestId':name+str(current['review']['revision'])})
                self.assertEqual(response.status_code,200,response.json)
                current=response.json
            action('start');action('hint');action('pause')
            self.assertIsNone(client.get(base,headers=student).json['currentQuestion'])
            action('start')
            self.assertTrue(current['currentQuestion']['helpUsed'])
            for index in range(run['total_questions']):
                payload={'questionId':current['currentQuestion']['id'],'response':'A','revision':current['review']['revision'],'requestId':f'answer-{index}'}
                answer=client.post(base+'/answers',headers=student,json=payload)
                self.assertEqual(answer.status_code,200,answer.json)
                self.assertEqual(client.post(base+'/answers',headers=student,json=payload).json,answer.json)
                current=client.get(base,headers=student).json
                self.assertEqual(current['feedback'],answer.json['feedback'])
                action('next')
            self.assertEqual(current['review']['status'],'completed')
            report=client.get('/api/learning/reviews/'+run['id']+'?childId=child-a',headers=parent)
            self.assertEqual(report.status_code,200)
            self.assertEqual(report.json['report']['answeredCount'],run['total_questions'])
            self.assertEqual(report.json['report']['independentFirstCorrect'],run['total_questions']-1)
            self.assertEqual(client.get(base,headers={'Authorization':'Bearer student-b'}).status_code,404)
            self.assertEqual(client.get('/api/reports/learning/weaknesses?childId=child-a',headers=parent).status_code,200)

    def test_legacy_task_http_writes_cannot_override_weekend_answers_or_speak(self):
        from routes.api.v1.tasks import tasks_bp
        from services.task_service import TaskService
        run=self.create()
        service=object.__new__(TaskService)
        service.auth_service=self.auth
        service._assert_capability=lambda *args:None
        service.repository=SimpleNamespace(transaction=self.db.transaction,
            get_task=lambda conn,**scope:dict(conn.execute('SELECT * FROM tasks WHERE id=? AND family_id=?',
                (scope['task_id'],scope['family_id'])).fetchone()))
        app=Flask(__name__);app.config['TESTING']=True
        app.register_blueprint(tasks_bp,url_prefix='/api/tasks')
        client=app.test_client()
        with patch('routes.api.v1.tasks.task_service',return_value=service):
            for action in ('start','complete','reminder','acknowledge-missed','parent-confirm','reject-confirmation'):
                result=client.post('/api/tasks/'+run['task_id']+'/'+action,
                    headers={'Authorization':'Bearer parent-a'},json={})
                self.assertEqual(result.status_code,409,(action,result.json))
                self.assertEqual(result.json['error'],'review_task_owned')
        self.assertEqual(self.db.execute('SELECT status FROM tasks').fetchone()['status'],'scheduled')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events').fetchone()['n'],2)


class ReminderContractTest(unittest.TestCase):
    def sender(self,adapter):
        resolver=SimpleNamespace(resolve=lambda **kwargs:SimpleNamespace(bridge=SimpleNamespace(adapter=adapter),device_id='device'))
        return SafeReviewReminderSender(resolver,clock=lambda:1000)

    def send(self,adapter,expires=2000):
        return self.sender(adapter)(family_id='f',child_id='c',task_id='t',request_id='r:1',appointment_revision=1,expires_at=expires,non_preemptive=True,text='温和提醒')

    def test_legacy_never_falls_back_to_plain_speak(self):
        adapter=SimpleNamespace(speak=Mock())
        self.assertEqual(self.send(adapter)['reason'],'silent_unsupported')
        adapter.speak.assert_not_called()

    def test_atomic_capability_busy_and_exact_delivery_receipt(self):
        caps={k:True for k in ('atomicIdleSpeech','expiry','idempotency','noQueue','appointmentRevision','sleepAndQuietHours')}
        caps['schemaVersion']=1
        adapter=SimpleNamespace(review_reminder_capabilities=lambda:caps,
            speak_review_if_idle=Mock(return_value={'delivered':False,'requestId':'r:1','appointmentRevision':1,'reason':'speaker_busy'}))
        self.assertEqual(self.send(adapter)['reason'],'speaker_busy')
        adapter.speak_review_if_idle.return_value={'delivered':True,'requestId':'r:1','appointmentRevision':1,'playedAt':1000}
        self.assertTrue(self.send(adapter)['delivered'])
        adapter.speak_review_if_idle.return_value={'delivered':True,'requestId':'old','appointmentRevision':0,'playedAt':1000}
        self.assertFalse(self.send(adapter)['delivered'])
        adapter.speak_review_if_idle.reset_mock()
        self.assertFalse(self.send(adapter,expires=999)['delivered'])
        adapter.speak_review_if_idle.assert_not_called()

if __name__=='__main__':unittest.main()
