"""Pure regression checks for band authority; never starts production or a DB."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from content.formal_curriculum_registry import formal_content_contract, formal_slot_difficulty
from content.formal_difficulty_policy import DIFFICULTY_CODES, formal_difficulty_policy
from content.formal_objective_rules import objective_question_policy, solve_objective_question, validate_objective_question
from content.primary_skill_boundaries import PRIMARY_SKILL_BOUNDARIES, PRIMARY_ONE_CONTENT_DATASET_SHA256
from integrations.openmaic_question_adapter import OpenMaicQuestionPhaseAdapter, QuestionPhaseCommand
from services.learning_catalog_validator import PrimaryOneCourseTarget
from services.learning_curriculum_preparation_contract import build_preparation_target
from services.learning_generated_course_validator import LearningGeneratedCourseValidator
from tests.test_formal_multigrade_registry import grade_host_fixture


class FormalDifficultyContractTest(unittest.TestCase):
    def test_all_135_bands_have_solvable_and_distinct_enforced_examples(self):
        seen=0
        for boundary in PRIMARY_SKILL_BOUNDARIES:
            if boundary.grade_code=='primary_1': continue
            args=(boundary.grade_code,boundary.subject,boundary.skill_id)
            policies=[objective_question_policy(*args,band) for band in DIFFICULTY_CODES]
            self.assertEqual(len({p['publicPromptExample'] for p in policies}),3,args)
            for band,p in zip(DIFFICULTY_CODES,policies):
                with self.subTest(identity=args,band=band):
                    answer=solve_objective_question(*args,p['publicPromptExample'],band)
                    question={'type':'exact_text','prompt':p['publicPromptExample'],'answer':answer}
                    self.assertEqual(validate_objective_question(*args,question,band),answer)
                    question['answer']='wrong untrusted key'
                    with self.assertRaises(ValueError): validate_objective_question(*args,question,band)
                    for other in DIFFICULTY_CODES:
                        if other!=band:
                            with self.assertRaises((ValueError,SyntaxError),msg=f'{args} {band} accepted as {other}'):
                                solve_objective_question(*args,p['publicPromptExample'],other)
                    seen+=1
        self.assertEqual(seen,135)

    def test_grade_six_reading_rejects_single_fact_addition_and_redundant_sources(self):
        with self.assertRaises(ValueError): solve_objective_question('primary_6','english','reading_evidence','Tom is at the park. Where is Tom?','standard')
        with self.assertRaises(ValueError): solve_objective_question('primary_6','chinese','integrated_reading','短文：小林读了8页书，小雨读了6页书。问题：两人一共读了多少页书？','standard')
        redundant='资料1：周一开放运动、阅读。资料2：周二开放运动、美术。资料3：周三开放运动、音乐。问题：综合所有资料，哪项活动每天都开放？'
        with self.assertRaises(ValueError): solve_objective_question('primary_6','chinese','integrated_reading',redundant,'standard')
        ambiguous='观点：只有使用新纸才能完成作品。调查：甲组:使用新纸和旧纸，完成作品。乙组:使用新纸，完成作品。问题：哪些组的事实可以直接反驳观点？按调查顺序用顿号列出组名。'
        with self.assertRaises(ValueError): solve_objective_question('primary_6','chinese','argument_evidence',ambiguous,'basic')

    def test_fraction_activity_names_are_context_not_math_conditions(self):
        args=('primary_6','math','fraction_ratio_percentage')
        example=objective_question_policy(*args,'standard')['publicPromptExample']
        for activity in ('阅读','绘画','合唱','运动','手工','数学活动','三人篮球','除草','和声练习','再生纸制作'):
            self.assertEqual(solve_objective_question(*args,example.replace('阅读',activity),'standard'),'48;60%')
        invalid=(
            example.replace('阅读','绘画',1),
            example.replace('阅读','阅读并退出十人'),
            example.replace('阅读','阅读增加二人'),
            example.replace('阅读','阅读十人'),
            example.replace('阅读','不参加阅读'),
            example.replace('。参加阅读','。又有10人参加。参加阅读'),
            example.replace('80人','8人'),
            example.replace('3/5','3/101'),
            example.replace('80人','81人'),
            example.replace('3/5','1/16'), # 6.25% violates max one decimal.
        )
        for prompt in invalid:
            with self.assertRaises(ValueError,msg=prompt):solve_objective_question(*args,prompt,'standard')
        self.assertEqual(solve_objective_question(*args,example.replace('3/5','1/8'),'standard'),'10;12.5%')

    def test_explicit_slot_allocation_preserves_p1_and_binds_host_receipt(self):
        self.assertEqual(formal_content_contract('primary_1')['datasetSha256'],PRIMARY_ONE_CONTENT_DATASET_SHA256)
        self.assertTrue(all('difficultyCode' not in x for x in build_preparation_target('primary_1')['courseTargets']))
        for grade in range(2,7):
            target=build_preparation_target(f'primary_{grade}')
            self.assertEqual(len(target['courseTargets']),27)
            for subject in ('chinese','math','english'):
                counts={band:sum(x['subject']==subject and x['difficultyCode']==band for x in target['courseTargets']) for band in DIFFICULTY_CODES}
                self.assertEqual(counts,dict.fromkeys(DIFFICULTY_CODES,3))
        course,target,boundary,evidence,identity=grade_host_fixture('primary_6')
        self.assertEqual(target.difficulty_code,'standard')
        with self.assertRaises(ValueError):replace(target,difficulty_code='challenge')
        wrong=copy.deepcopy(course);wrong['content']['difficultyCode']='basic'
        result=LearningGeneratedCourseValidator().validate_primary_one_host_gate(replace(evidence,candidate_course=wrong),target=target,identity=identity,skill_boundary=boundary,accepted_host_receipts=())
        self.assertEqual(result.outcome,'rejected')
        self.assertIn('难度',result.receipt['issues'][0]['message'])

    def test_standard_candidate_checkpoint_and_teaching_brief_bind_same_policy(self):
        from integrations.openmaic_question_adapter import _build_candidate_course, _candidate_projection_from_course, _normalize_candidate_course
        from tests.test_openmaic_question_phase_adapter import _nfkc_fixture
        from services.lesson_package_validator import formal_runtime_teaching_brief
        course,target,boundary,evidence,identity=grade_host_fixture('primary_6')
        command=QuestionPhaseCommand('item',1,'outline',1,identity.generation_request_id,'primary_6','math','zh-CN','zh-CN',boundary,{'questionCount':5,'existingFingerprints':[],'generationFeedback':None},'standard')
        request=OpenMaicQuestionPhaseAdapter().canonicalize_phase(command).request
        projection=_nfkc_fixture(_candidate_projection_from_course(course))
        built=_build_candidate_course(command,projection)
        self.assertEqual(_normalize_candidate_course(built,command,existing_fingerprints=[]),built)
        row={**built,'grade_code':'primary_6','node_code':target.skill_id,'content_json':json.dumps(built['content'],ensure_ascii=False)}
        brief,_,_=formal_runtime_teaching_brief(row)
        self.assertEqual(brief['course']['difficultyCode'],'standard')
        self.assertEqual(brief['difficultyPolicy'],formal_difficulty_policy('primary_6','math',target.skill_id,'standard'))
        module=(Path(__file__).resolve().parents[1]/'openmaic-sidecar/src/question-contract.mjs').as_uri()
        script="import{buildQuestionCandidates,legacyQuestionPhaseRequest,buildQuestionGenerationPrompts,FORMAL_OBJECTIVE_PROMPT_VERSION}from "+json.dumps(module)+";import fs from'node:fs';const x=JSON.parse(fs.readFileSync(0,'utf8'));const legacy=legacyQuestionPhaseRequest(x.request);if(legacy.objectivePolicy.difficultyCode!=='standard')throw Error('CLI projection dropped difficulty');const prompts=buildQuestionGenerationPrompts(legacy,{});if(!prompts.user.includes('Do not add a mascot')||prompts.user.includes('Originality contract: naturally set this prompt'))throw Error('conflicting story blueprint');if(!prompts.system.includes(FORMAL_OBJECTIVE_PROMPT_VERSION))throw Error('missing prompt revision');const r=buildQuestionCandidates({request:legacy,generationPlan:{},generated:x.generated,elapsedMs:0});process.stdout.write(JSON.stringify(r.candidateCourse));"
        result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps({'request':request,'generated':projection}),text=True,capture_output=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),built)

    def test_actual_prepared_standard_request_passes_strict_reservation_and_rejects_policy_drift(self):
        from repositories.dynamic_learning_course_repository import _validate_strict_reservation_request
        from content.formal_curriculum_registry import formal_registered_boundary
        boundary=formal_registered_boundary('primary_6','math','fraction_ratio_percentage')
        command=QuestionPhaseCommand('item',1,'outline',1,'difficulty-reservation-fixture','primary_6','math','zh-CN','zh-CN',boundary.to_openmaic_payload(),{'questionCount':5,'existingFingerprints':[],'generationFeedback':None},'standard')
        prepared=OpenMaicQuestionPhaseAdapter().canonicalize_phase(command)
        def validate(request):
            encoded=json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            _validate_strict_reservation_request(phase=command.phase,phase_ordinal=command.phase_ordinal,generation_request_id=command.generation_request_id,provider=prepared.provider['name'],model=prepared.provider['model'],profile=prepared.profile_sha256,input_sha256=hashlib.sha256(encoded.encode()).hexdigest(),command_checkpoint=prepared.request['checkpoint'],prepared_request=request)
        validate(prepared.request)
        mutations=(
            lambda r:r.update(arbitraryExtra=True),
            lambda r:r['objectivePolicy'].update(arbitraryExtra=True),
            lambda r:r['objectivePolicy'].update(difficultyCode='challenge'),
            lambda r:r['objectivePolicy'].update(gradeCode='primary_5'),
            lambda r:r['skillBoundary'].update(skillTitle='wrong skill title'),
            lambda r:r.update(targetLanguageCode='en-US'),
            lambda r:r.update(gradeCode='primary_7'),
            lambda r:r.update(schemaVersion='old-schema'),
        )
        for mutate in mutations:
            wrong=copy.deepcopy(prepared.request);mutate(wrong)
            with self.assertRaises(ValueError):validate(wrong)
        primary_one=copy.deepcopy(prepared.request);primary_one['gradeCode']='primary_1'
        with self.assertRaises(ValueError):validate(primary_one)

    def test_early_gate_prevents_later_calls_without_invalidating_historical_decoding(self):
        from integrations.openmaic_question_adapter import _candidate_projection_from_course
        from services.learning_formal_question_preflight import validate_formal_phase_question_checkpoint, FormalQuestionPreflightError
        course,target,boundary,evidence,identity=grade_host_fixture('primary_6')
        candidate=_candidate_projection_from_course(course)
        command=QuestionPhaseCommand('item',1,'lesson_text',5,identity.generation_request_id,'primary_6','math','zh-CN','zh-CN',boundary,{'candidate':candidate},'standard')
        validate_formal_phase_question_checkpoint(command)
        wrong=copy.deepcopy(candidate);wrong['questions'][0]['prompt']='把分数3/5化成百分数是多少？'
        with self.assertRaises(FormalQuestionPreflightError) as raised:validate_formal_phase_question_checkpoint(replace(command,checkpoint={'candidate':wrong}))
        self.assertEqual(raised.exception.issues[0]['question'],1)
        # Known-invalid raw must reach the bounded repair phase, not require a
        # fresh paid attempt before it can be fixed.
        for phase, ordinal in [('candidate_repair', 3), ('candidate_repair_retry', 4)]:
            validate_formal_phase_question_checkpoint(replace(command,phase=phase,phase_ordinal=ordinal,checkpoint={'rawCandidate':wrong}))
        validate_formal_phase_question_checkpoint(replace(command,grade_code='primary_1',checkpoint={}))

    def test_phase_three_repairs_invalid_raw_once_and_never_autoaccepts_it(self):
        from integrations.openmaic_question_adapter import _candidate_projection_from_course
        from tests.test_openmaic_question_phase_adapter import _nfkc_fixture
        course,target,boundary,evidence,identity=grade_host_fixture('primary_6')
        valid=_nfkc_fixture(_candidate_projection_from_course(course))
        invalid=copy.deepcopy(valid)
        invalid['questions'][0]['prompt']='把分数3/5化成百分数是多少?'
        adapter=OpenMaicQuestionPhaseAdapter()
        env={**os.environ,'OPENMAIC_FAKE_MODE':'1','OPENMAIC_HOST_VALIDATOR_PYTHON':sys.executable,'PYTHONDONTWRITEBYTECODE':'1'}
        for raw,reply,expected_status,expected_source in (
            (invalid,valid,'accepted','candidate_repair_output'),
            (invalid,invalid,'rejected',None),
            (valid,'provider must not be called','accepted','accepted_raw_candidate'),
        ):
            command=QuestionPhaseCommand('item',1,'candidate_repair',3,identity.generation_request_id,'primary_6','math','zh-CN','zh-CN',boundary,{'questionCount':5,'existingFingerprints':[],'generationFeedback':None,'rawCandidate':raw},'standard')
            prepared=adapter.canonicalize_phase(command)
            request=copy.deepcopy(prepared.request)
            request.update(mode='fake',fakeResponses=[json.dumps(reply,ensure_ascii=False)])
            result=subprocess.run(['node',str(adapter.cli_path),'--question-phase-v2'],input=json.dumps(request,ensure_ascii=False),text=True,capture_output=True,env=env,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            normalized=adapter._normalize_result(prepared,json.loads(result.stdout),returncode=result.returncode)
            self.assertEqual(normalized.outcome,'succeeded')
            self.assertEqual(normalized.checkpoint['phaseStatus'],expected_status)
            self.assertEqual(normalized.checkpoint.get('hostCompilation',{}).get('source'),expected_source)

    def test_python_sidecar_all_bands_share_canonical_policy_hash(self):
        requests=[];adapter=OpenMaicQuestionPhaseAdapter()
        for boundary in PRIMARY_SKILL_BOUNDARIES:
            if boundary.grade_code=='primary_1':continue
            for band in DIFFICULTY_CODES:
                command=QuestionPhaseCommand('item',1,'outline',1,'difficulty-fixture',boundary.grade_code,boundary.subject,'zh-CN','en-US' if boundary.subject=='english' else 'zh-CN',boundary.to_openmaic_payload(),{'questionCount':5,'existingFingerprints':[],'generationFeedback':None},band)
                prepared=adapter.canonicalize_phase(command)
                requests.append({'request':prepared.request,'canonical':prepared.canonical_input_json})
        module=(Path(__file__).resolve().parents[1]/'openmaic-sidecar/src/question-contract.mjs').as_uri()
        script="import {normalizeQuestionPhaseRequest} from "+json.dumps(module)+"; import fs from 'node:fs'; const stable=x=>Array.isArray(x)?x.map(stable):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,stable(x[k])])):x; const rows=JSON.parse(fs.readFileSync(0,'utf8')); for (const row of rows) {const value=normalizeQuestionPhaseRequest(row.request);if(JSON.stringify(stable(value))!==row.canonical) throw Error('cross-language canonical hash mismatch');} process.stdout.write(String(rows.length));"
        result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(requests,ensure_ascii=False),text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout,'135')
