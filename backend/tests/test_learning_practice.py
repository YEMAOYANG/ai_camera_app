from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch
from flask import Flask
from core.errors import ApiError
from services.learning_practice_service import LearningPracticeService, canonical, digest
from repositories.learning_practice_repository import LearningPracticeRepository
from routes.api.v2.student_practice import student_practice_bp
from core.database import _split_sql_script
from pathlib import Path


def source():
    questions = [{ 'id': f'q{i}', 'type': 'numeric', 'prompt': f'把 {i} 和 10 合起来是多少？', 'answer': str(10+i),
                   'explanation': '把两个部分合起来，再数一数。' } for i in range(1, 5)]
    content = {'questions': questions, 'teachingFlow': {'independentQuestionIds': ['q3', 'q4']}}
    receipt = {'outcome': 'passed'}
    return {'id':'course-1', 'version':'1', 'grade_code':'primary_1', 'subject':'math', 'node_code':'number_sense_20',
            'release_id':'release-1', 'status':'published', 'quality_status':'released', 'retired_at':None,
            'title':'数一数', 'objective':'认识数量', 'boundary_version':'test-boundary', 'subject_ordinal':2,
            'boundary_ordinal':1, 'variant_ordinal':1, 'content_json':canonical(content),
            'feature_manifest_json':canonical({'sourceCourseContentSha256':digest(content)}),
            'content_receipt_hash':digest(receipt), 'validation_json':canonical({'hostGateReceipt':receipt,'hostGateReceiptHash':digest(receipt)})}


class Repository:
    def __init__(self):
        self.child = {'grade_code':'primary_1', 'education_stage_code':'primary', 'grade_selection_revision':1}
        self.sources = [source()]
        self.questions, self.sessions, self.session_items, self.exposures = {}, {}, {}, []
    @contextmanager
    def transaction(self):
        snapshot = deepcopy((self.questions,self.sessions,self.session_items,self.exposures))
        try: yield self
        except Exception:
            self.questions,self.sessions,self.session_items,self.exposures=snapshot
            raise
    def lock_child(self, conn, principal): return self.child
    def eligible_sources(self, conn, **scope):
        self.scope = scope
        return self.sources
    def project(self, conn, row):
        prior=next((q for q in self.questions.values() if q['source_key_sha256']==row['source_key_sha256']),None)
        if prior:
            if prior['contract_sha256'] != row['contract_sha256']: raise ValueError('source drift')
            return prior
        self.questions[row['id']]=deepcopy(row); return row
    def seen(self, conn, **scope): return {row['dedupe_sha256'] for row in self.exposures if all(row[key]==value for key,value in scope.items())}
    def existing(self,conn,**scope): return next((row for row in self.sessions.values() if row['request_key_sha256']==scope['request_key']),None)
    def active(self,conn,**scope): return next((row for row in self.sessions.values() if row['status']=='in_progress' and all(row[key]==value for key,value in scope.items())),None)
    def get_session(self,conn,**scope):
        row=self.sessions.get(scope['session_id']);return row if row and row['family_id']==scope['family_id'] and row['child_id']==scope['child_id'] else None
    def items(self,conn,session_id): return self.session_items[session_id]
    def create(self,conn,*,session,questions,exposures):
        self.sessions[session['id']]=deepcopy(session)
        self.session_items[session['id']]=[{'session_id':session['id'],'ordinal':i,'question_id':q['id'],'contract_sha256':q['contract_sha256'],
            'snapshot_json':q['question_json'],'response_sha256':None,'feedback_json':None} for i,q in enumerate(questions)]
        self.exposures.extend(exposures)
    def answer(self,conn,*,session,item,response_sha256,feedback,now):
        item.update(response_sha256=response_sha256,feedback_json=canonical(feedback))
        session['current_index']+=1;session['correct_count']+=int(feedback['correct'])
        if session['current_index']==session['total_questions']:session.update(status='completed',completed_at=now)


class PracticeTest(unittest.TestCase):
    def setUp(self):
        self.repo=Repository()
        self.auth=Mock();self.auth.authenticate.return_value={'principal':{'id':'principal-1','child_id':'child-1','family_id':'family-1'}}
        self.host=Mock()
        self.service=LearningPracticeService(repository=self.repo,student_auth_service=self.auth,host_validator=self.host,clock=lambda:100)
    def start(self,**change): return self.service.start('student-token',{'requestId':'request-1','subject':'math','count':5,**change})
    def solve(self,result):
        session=result['session'];item=next(row for row in self.repo.items(None,session['id']) if row['question_id']==session['currentQuestion']['id'])
        return self.service.answer('student-token',session['id'],{'questionId':item['question_id'],'response':json.loads(item['snapshot_json'])['answer']})
    def test_shared_projection_hides_answers_and_admits_only_independent_phase(self):
        result=self.start()
        self.assertEqual(result['session']['totalQuestions'],2)
        self.assertEqual(len(self.repo.questions),2)
        self.host.validate_primary_one_accepted_receipt.assert_called_once()
        self.assertNotIn('answer',result['session']['currentQuestion'])
        self.assertNotIn('evaluation',result)
        self.assertEqual(self.repo.scope['child_id'],'child-1')
        self.assertEqual(self.repo.scope['grade_code'],'primary_1')

    def test_real_host_receipt_projects_grade_two_and_six_independent_questions(self):
        from services.learning_generated_course_validator import LearningGeneratedCourseValidator
        from tests.test_formal_multigrade_registry import grade_host_fixture
        validator = LearningGeneratedCourseValidator()
        self.service.host_validator = validator
        for grade in ('primary_2', 'primary_6'):
            with self.subTest(grade=grade):
                _, target, boundary, evidence, identity = grade_host_fixture(grade)
                result = validator.validate_primary_one_host_gate(evidence, target=target, identity=identity,
                    skill_boundary=boundary, accepted_host_receipts=())
                self.assertEqual(result.outcome, 'passed')
                course = result.course
                row = {**source(), 'id': course['id'], 'version': course['version'], 'grade_code': grade,
                    'node_code': target.skill_id, 'boundary_version': target.boundary_version,
                    'subject_ordinal': target.subject_ordinal, 'boundary_ordinal': target.boundary_ordinal,
                    'variant_ordinal': target.variant_ordinal, 'title': course['title'], 'objective': course['objective'],
                    'content_json': canonical(course['content']), 'feature_manifest_json': canonical({'sourceCourseContentSha256': digest(course['content'])}),
                    'content_receipt_hash': result.receipt_hash, 'validation_json': canonical({'hostGateReceipt': result.receipt, 'hostGateReceiptHash': result.receipt_hash})}
                projected = self.service._project_source(row, grade=grade, subject='math', skill=None, timestamp=100)
                self.assertEqual({item['source_question_id'] for item in projected}, set(course['content']['teachingFlow']['independentQuestionIds']))
                self.assertTrue(all(item['grade_code'] == grade and item['subject'] == 'math' for item in projected))
    def test_repeat_start_and_answer_are_idempotent_and_next_practice_has_no_duplicates(self):
        result=self.start();sid=result['session']['id']
        self.assertEqual(self.start()['session']['id'],sid)
        self.assertEqual(self.start(requestId='another-request')['session']['id'],sid)
        first_question=result['session']['currentQuestion']['id']
        response=json.loads(self.repo.items(None,sid)[0]['snapshot_json'])['answer']
        result=self.solve(result)
        replay=self.service.answer('student-token',sid,{'questionId':first_question,'response':response})
        self.assertEqual(replay['session']['currentQuestionIndex'],1)
        result=self.solve(result)
        self.assertEqual(result['session']['status'],'completed')
        self.assertEqual(result['session']['correctCount'],2)
        self.assertIsNone(self.start(requestId='new-practice')['session'])
    def test_started_session_uses_frozen_answer_when_source_or_version_changes(self):
        result=self.start();self.repo.sources[0]['content_json']='{}';self.repo.sources[0]['version']='2'
        answered=self.solve(result)
        self.assertTrue(answered['evaluation']['correct'])
        self.assertEqual(len(self.repo.questions),2)
    def test_future_question_wrong_child_grade_and_client_score_cannot_mutate(self):
        result=self.start();sid=result['session']['id'];future=self.repo.items(None,sid)[1]['question_id']
        for data in [{'questionId':future,'response':'14'}, {'questionId':result['session']['currentQuestion']['id'],'response':'13','score':100}]:
            with self.assertRaises(ApiError): self.service.answer('student-token',sid,data)
        self.repo.child.update(grade_code='primary_2',grade_selection_revision=2)
        with self.assertRaises(ApiError):self.service.get('student-token',sid)
        self.repo.child.update(grade_code='primary_1',grade_selection_revision=1)
        self.auth.authenticate.return_value['principal']['child_id']='other-child'
        with self.assertRaises(ApiError):self.service.get('student-token',sid)
        self.assertEqual(self.repo.sessions[sid]['current_index'],0)
    def test_wrong_scope_or_failed_host_or_content_hash_never_enters_bank(self):
        for field,value in [('grade_code','primary_2'),('subject','english'),('status','draft'),('retired_at',1),('content_json','{}')]:
            self.repo.sources=[{**source(),field:value}]
            self.assertIsNone(self.start()['session'])
        self.repo.sources=[source()];self.host.validate_primary_one_accepted_receipt.side_effect=ValueError('not approved')
        self.assertIsNone(self.start()['session']);self.assertEqual(self.repo.questions,{})
    def test_source_identity_separates_course_version_and_answer_contract(self):
        first=self.service._project_source(source(),grade='primary_1',subject='math',skill=None,timestamp=1)[0]
        changed=source();changed['version']='2'
        second=self.service._project_source(changed,grade='primary_1',subject='math',skill=None,timestamp=1)[0]
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(first['dedupe_sha256'],second['dedupe_sha256'])
        self.assertEqual(first['contract_sha256'],second['contract_sha256'])
    def test_authenticated_http_path_completes_revision_without_a_model(self):
        app=Flask(__name__);app.register_blueprint(student_practice_bp,url_prefix='/api/v2/student/practice')
        with patch('routes.api.v2.student_practice.learning_practice_service',return_value=self.service):
            client=app.test_client();headers={'Authorization':'Bearer student-token'}
            response=client.post('/api/v2/student/practice/sessions',json={'requestId':'http-1','subject':'math','count':1},headers=headers)
            self.assertEqual(response.status_code,200);result=response.json;sid=result['session']['id']
            question=result['session']['currentQuestion'];private=json.loads(self.repo.items(None,sid)[0]['snapshot_json'])
            response=client.post(f'/api/v2/student/practice/sessions/{sid}/answers',json={'questionId':question['id'],'response':private['answer']},headers=headers)
            self.assertEqual(response.status_code,200);self.assertEqual(response.json['session']['status'],'completed')
            self.assertNotIn('answer',client.get(f'/api/v2/student/practice/sessions/{sid}',headers=headers).json)
    def test_query_requires_completed_exact_version_formal_and_media_ready_sources(self):
        conn=Mock();conn.execute.return_value.fetchall.return_value=[]
        LearningPracticeRepository(Mock()).eligible_sources(conn,family_id='family',child_id='child',grade_code='primary_2',subject='math',skill_id=None)
        sql,params=conn.execute.call_args.args
        for condition in ["session.status = 'completed'","course.version = session.course_version","item.content_gate_status = 'passed'",
            "runtime.feature_manifest_json","formal_audio.state = 'auto_validated'","course.grade_code = ?"]:
            self.assertIn(condition,sql)
        self.assertEqual(params,('family','child','primary_2','math',None,None))
    def test_migration_freezes_question_snapshots_and_never_updates_course_rows(self):
        sql=(Path(__file__).parents[1]/'migrations/078_learning_versioned_practice.sql').read_text()
        self.assertEqual(len(_split_sql_script(sql)),4)
        self.assertIn('snapshot_json JSON NOT NULL',sql)
        self.assertIn('UNIQUE KEY uq_practice_session_question',sql)
        self.assertNotIn('UPDATE learning_courses',sql)
