from __future__ import annotations

import copy
import json
import unittest
import unicodedata
from contextlib import contextmanager
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from content.formal_curriculum_registry import (
    formal_content_contract, formal_content_validation_identity,
    formal_registered_boundary, require_formal_grade,
)
from content.formal_objective_rules import (
    objective_question_policy, solve_objective_question, validate_objective_question,
    bounded_numeric_ast,
)
from content.primary_skill_boundaries import PRIMARY_SKILL_BOUNDARIES, PRIMARY_ONE_CONTENT_DATASET_SHA256
from integrations.openmaic_question_adapter import _build_question_fingerprints, question_candidate_course_id
from services.learning_catalog_validator import PrimaryOneCourseTarget
from services.learning_generated_course_validator import (
    AcceptedPrimaryOneHostReceipt, LearningGeneratedCourseValidator, PrimaryOneHostGateControlError,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target, preparation_target_fingerprint, preparation_authority_grade,
)
from services.learning_curriculum_preparation_runner import LearningCurriculumPreparationRunner
from tests.test_learning_generated_course_validator import _formal_course, _formal_evidence, _choice
from tests.test_learning_curriculum_preparation_runner import _app
from tests.test_course_supply_availability import RecordedConnection


def grade_host_fixture(grade: str):
    """A local candidate/evidence fixture; no Provider or transport is used."""
    skill = 'number_operations_100' if grade == 'primary_2' else 'fraction_ratio_percentage'
    full_target = build_preparation_target(grade)
    slot = next(x for x in full_target['courseTargets'] if x['subject']=='math' and x['skillId']==skill and x['variantOrdinal']==1)
    target = PrimaryOneCourseTarget(grade,'math',slot['subjectOrdinal'],skill,slot['boundaryOrdinal'],slot['boundaryVersion'],1,'zh-CN','zh-CN')
    registered = formal_registered_boundary(grade,'math',skill)
    boundary = registered.to_openmaic_payload(); boundary.pop('language')
    course,_,_,request_id = _formal_course('pinyin_syllables')
    course.update(id=question_candidate_course_id(grade_code=grade,subject='math',skill_id=skill,generation_request_id=request_id,logical_attempt=1),gradeCode=grade,subject='math',nodeCode=skill,
                  objective=unicodedata.normalize('NFKC','；'.join(registered.learning_objectives)))
    prompts = ([f'计算：{n}+18。' for n in range(23,28)] if grade=='primary_2' else
               [f'某活动共有{n}人，其中3/5参加阅读。参加阅读的有多少人，占总人数的百分之几？按“人数;百分数”回答。' for n in (40,60,80,100,120)])
    course['content']['difficultyCode'] = target.difficulty_code
    old_questions=course['content']['questions']
    questions=[]
    for i,prompt in enumerate(prompts):
        expected=solve_objective_question(grade,'math',skill,prompt)
        q=_choice(prompt,expected,('91%' if '%' in expected else '91','92%' if '%' in expected else '92','93%' if '%' in expected else '93'))
        q.update(id=old_questions[i]['id'],skill=registered.skill_title)
        questions.append({k:unicodedata.normalize('NFKC',v).strip() if isinstance(v,str) else v for k,v in q.items()})
    course['content']['questions']=questions
    course['content']['teachingFlow']['teach'].update(sayText='先读清题目给出的数量条件，再按本课的方法一步一步比较和计算。',keyPoints=['读清条件','独立作答'])
    course['content']['teachingFlow']['recap']['sayText']='我们学会了依据题目条件认真计算和检查。'
    evidence,identity=_formal_evidence(course,target,boundary,request_id)
    evidence.independent_solution['gradeCode']=grade
    command=SimpleNamespace(grade_code=grade,subject='math',boundary=boundary)
    evidence=replace(evidence,question_fingerprints=_build_question_fingerprints(command,course))
    authority=formal_content_validation_identity(grade)
    identity=replace(identity,content_validation_contract_version=authority['contentValidationContractVersion'],content_validation_dataset_sha256=authority['contentValidationDatasetSha256'])
    return course,target,boundary,evidence,identity


class FormalMultigradeRegistryTest(unittest.TestCase):
    def test_six_separate_frozen_authorities_and_full_v2_slots(self):
        hashes=set();fingerprints=set()
        for n in range(1,7):
            grade=f'primary_{n}';contract=formal_content_contract(grade);target=build_preparation_target(grade)
            self.assertEqual(target['schemaVersion'],'mira.learning.preparation-target.v2')
            self.assertEqual(len(target['courseTargets']),30 if n==1 else 27)
            self.assertEqual(target['contentValidationDatasetSha256'],contract['datasetSha256'])
            self.assertEqual(len(target['canaryManifest']['targets']),3)
            hashes.add(contract['datasetSha256']);fingerprints.add(preparation_target_fingerprint(target))
        self.assertEqual(len(hashes),6);self.assertEqual(len(fingerprints),6)
        self.assertEqual(formal_content_contract('primary_1')['datasetSha256'],PRIMARY_ONE_CONTENT_DATASET_SHA256)

    def test_all_45_pilot_grammars_derive_answer_without_model_key(self):
        seen=0
        for boundary in PRIMARY_SKILL_BOUNDARIES:
            if boundary.grade_code=='primary_1':continue
            policy=objective_question_policy(boundary.grade_code,boundary.subject,boundary.skill_id)
            with self.subTest(grade=boundary.grade_code,skill=boundary.skill_id):
                expected=solve_objective_question(boundary.grade_code,boundary.subject,boundary.skill_id,policy['publicPromptExample'])
                self.assertTrue(expected)
                question={'type':'single_choice','prompt':policy['publicPromptExample'],'choices':[{'id':'a','label':expected},{'id':'b','label':'unrelated'}],'answer':'b'}
                with self.assertRaises(ValueError):validate_objective_question(boundary.grade_code,boundary.subject,boundary.skill_id,question)
                question['answer']='a';self.assertEqual(validate_objective_question(boundary.grade_code,boundary.subject,boundary.skill_id,question),expected)
                self.assertIn('subjective_literary_appreciation',policy['closedAssessmentTypes'])
            seen+=1
        self.assertEqual(seen,45)

    def test_unregistered_grade_cross_grade_skill_and_authority_disagreement_rejected(self):
        for grade in ('',None,'primary_7','primary_2 '):
            with self.assertRaises(ValueError):require_formal_grade(grade)
        with self.assertRaises(ValueError):objective_question_policy('primary_2','math','fraction_ratio_percentage')
        with self.assertRaises(ValueError):preparation_authority_grade({'grade_code':'primary_2','target_spec_json':build_preparation_target('primary_6')})

    def test_grade_bound_ast_rejects_out_of_range_complex_and_code(self):
        for expression in ('80+50','3*4','__import__("os")','2**100000','True+3'):
            with self.subTest(expression=expression),self.assertRaises((ValueError,SyntaxError)):
                bounded_numeric_ast(expression,mode='integer_add_sub_100')
        self.assertEqual(str(bounded_numeric_ast('1/3+1/6',mode='fraction_add_sub')[0]),'1/2')

    def test_primary_two_and_six_host_pass_and_receipt_replay(self):
        validator=LearningGeneratedCourseValidator()
        for grade in ('primary_2','primary_6'):
            with self.subTest(grade=grade):
                course,target,boundary,evidence,identity=grade_host_fixture(grade)
                result=validator.validate_primary_one_host_gate(evidence,target=target,identity=identity,skill_boundary=boundary,accepted_host_receipts=())
                self.assertEqual(result.outcome,'passed',result.receipt)
                self.assertEqual(result.receipt['gradeCode'],grade)
                proof=AcceptedPrimaryOneHostReceipt(target,result.course,result.receipt,result.receipt_hash)
                self.assertEqual(validator.validate_primary_one_accepted_receipt(proof),result.receipt['hostContentFingerprint'])
                from core.errors import ApiError
                with self.assertRaises((ValueError,PrimaryOneHostGateControlError,ApiError)):
                    validator.validate_primary_one_accepted_receipt(replace(proof,target=replace(target,grade_code='primary_1')))

    def test_model_and_verifier_agreement_cannot_override_host_wrong_answer(self):
        validator=LearningGeneratedCourseValidator()
        _,target,boundary,evidence,identity=grade_host_fixture('primary_2')
        wrong=copy.deepcopy(evidence.candidate_course)
        wrong['content']['questions'][0]['answer']='option_1'
        wrong['content']['questions'][0]['evaluation']['expectedOptionId']='option_1'
        solution=copy.deepcopy(evidence.independent_solution);solution['answers'][0]['answer']='option_1'
        result=validator.validate_primary_one_host_gate(replace(evidence,candidate_course=wrong,independent_solution=solution),target=target,identity=identity,skill_boundary=boundary,accepted_host_receipts=())
        self.assertEqual(result.outcome,'rejected')
        self.assertIsNone(result.course)

    def test_round_robin_fairness_does_not_open_unrequested_grade_scopes(self):
        class Repository:
            def __init__(self):self.grades=[]
            @contextmanager
            def transaction(self):yield object()
            def start_next_formal_pipeline(self,*args,**kw):pass
            def claim_next(self,*args,**kw):self.grades.append(kw['grade_code']);return None
        repo=Repository();runner=LearningCurriculumPreparationRunner(repository=repo,adapter=SimpleNamespace(supported_stages=frozenset({'planning'})),clock=lambda:1000)
        app=_app(LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=['primary_2','primary_6'],LEARNING_COURSE_LIBRARY_ENABLED=True)
        with patch('services.course_library_service.CourseLibraryService.request_scope') as request:
            for _ in range(4):runner.run_once(app,1000)
        self.assertEqual(repo.grades,['primary_2','primary_6','primary_2','primary_6']);request.assert_not_called()

    def test_runtime_candidate_query_binds_exact_leased_plan(self):
        from repositories.lesson_package_repository import LessonPackageRepository
        target=build_preparation_target('primary_6')
        plan={'id':'plan6','grade_code':'primary_6','target_spec_json':target,'target_fingerprint':preparation_target_fingerprint(target),'lease_token':'lease6','catalog_build_id':'build6','catalog_release_id':'release6'}
        conn=RecordedConnection([],[])
        repo=object.__new__(LessonPackageRepository)
        self.assertIsNone(repo.get_next_formal_candidate_authority(conn,preparation_plan=plan))
        sql,params=conn.calls[0]
        self.assertIn('plan.lease_token = ?',sql);self.assertIn('plan.lease_expires_at > ?',sql)
        self.assertIn('build.id = ?',sql);self.assertIn('build.total_item_count = 27',sql)
        self.assertEqual(params[0],'primary_6');self.assertTrue({'plan6','lease6','build6','release6'}.issubset(params))
