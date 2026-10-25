"""Private, versioned homework analysis and deterministic correction workflow.

Provider calls are reserved durably before dispatch. An uncertain result is never
blindly retried; safe local stages and succeeded receipts can be resumed.
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import re
import uuid
from decimal import Decimal, InvalidOperation
from core.errors import ApiError
from core.security import now_ms
from repositories.homework_repository import HomeworkRepository
from services.homework_assets import normalize_image, transformed_image, transformed_geometry, quality_error, crop_region
from services.homework_math import check_item
from services.homework_recognition_parser import parse_recognition_response, RecognitionParseError
from services.homework_tencent_grading import TencentPending, HomeworkTencentGrading, QUERY_RETRY_ERRORS
from services.homework_tencent_normalizer import grading_reference, question_source_hierarchy
from services.homework_answer_quality import reviewed_result, student_grading, reference_for_correction, attach_reference_answer_layout
from services.homework_correction import (practice_result, correction_view, evaluate_response,
    evidence_question, correction_answer_state, self_reported_completion)

ROOT = Path(__file__).parents[1]
POLICY = json.loads((ROOT/'content/homework_analysis_policy.v3.json').read_text())
ACTIVE = {'queued','quality_check','recognizing','checking','media_preparing'}
SAFE_RETRY={'homework_provider_unconfigured','homework_audio_unconfigured','homework_media_pending','homework_prompt_missing'}|QUERY_RETRY_ERRORS
NON_ASSESSMENT_SOURCES={'synthetic_fixture','paid_validation'}
RECOGNITION_REPAIR_ITEM='__operator_recognition_repair__'
RECOGNITION_REPAIR_CONTRACT='complete-image-encoding.v2'
RECOGNITION_REPAIR_TTL_MS=30*60*1000
RECOGNITION_RESPONSE_SCHEMA='mira.homework-recognition-response.v1'
RECOGNITION_RESPONSE_MAX_BYTES=8*1024*1024
RECEIVED_RECOGNITION_ERRORS={'homework_recognition_invalid_json','homework_recognition_invalid_schema',
    'homework_recognition_truncated','homework_recognition_over_limit','homework_recognition_storage_failed'}


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parsed(value, fallback=None):
    return json.loads(value) if isinstance(value,str) else value if value is not None else fallback


def source_review_context(item, result, ordinal):
    """An OCR array position is not a question number printed on the paper."""
    context={'pageId':item['page_id'],'region':result.get('region'),
        'originalAnswer':result.get('studentAnswer',''),'originalOrdinal':ordinal,
        'recognitionConfirmed':result.get('recognitionConfirmed') is True,
        'recognitionNeedsConfirmation':result.get('recognitionNeedsConfirmation') is True}
    for key in ('sourceQuestionLabel','answerState'):
        if key in result:
            context[key]=result[key]
    hierarchy=question_source_hierarchy(result)
    grading=grading_reference(result)
    if hierarchy is not None:
        context.update(sourceHierarchy=hierarchy,sourcePath=hierarchy['sourcePath'],
            answerIndex=hierarchy['answerIndex'],answerCount=hierarchy['answerCount'])
    if grading is not None:
        context['grading']=grading
    return context


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value):
        raise ApiError('homework_idempotency_required','请携带有效的请求编号',400)
    return value


def revision(row, data):
    if type(data.get('revision')) is not int or data['revision'] != row['revision']:
        raise ApiError('homework_revision_conflict','作业已更新，请刷新后重试',409)


class HomeworkService:
    def __init__(self,database,*,profile_service,student_auth,asset_store,prompt_registry,
                 vision_provider=None,audio_service=None,capture_service=None,enabled=False,
                 evidence_enabled=False,processing_enabled=True,policy=None,clock=now_ms,
                 grading_provider=None,tutor_provider=None,source_review_provider=None):
        self.repository=HomeworkRepository(database)
        self.profile=profile_service
        self.student_auth=student_auth
        self.store=asset_store
        self.prompts=prompt_registry
        self.provider=grading_provider if grading_provider is not None else vision_provider
        self.grading_provider=self.provider
        self.tutor_provider=tutor_provider if tutor_provider is not None else vision_provider
        # Paper-image verification is separate from grading and language
        # teaching. The factory supplies the existing paper vision adapter;
        # legacy embedders can retain the teacher adapter when not configured.
        self.source_review_provider=source_review_provider
        self.audio=audio_service
        self.capture_service=capture_service
        self.enabled=enabled
        self.evidence_enabled=evidence_enabled
        self.processing_enabled=bool(processing_enabled)
        self.policy=policy or POLICY
        self.clock=clock
        from services.homework_tutor_service import HomeworkTutorService
        self.tutor=HomeworkTutorService(self)

    def _enabled(self):
        if not self.enabled:
            raise ApiError('homework_not_enabled','作业分析尚未开放',503)

    def _processing_enabled(self):
        if not self.processing_enabled:
            raise ApiError('homework_analysis_paused','照片已保存，AI分析尚未启用',503)

    def _parent(self,token):
        context=self.profile._auth_context(token)
        self._enabled()
        return context

    def _permit(self,conn,context,write=False):
        self.profile._assert_capability(conn,context,'manage_tasks' if write else 'view_reports')
        return context['family']['id']

    def _student(self,token):
        principal=self.student_auth.authenticate(token)['principal']
        self._enabled()
        return principal

    def create(self,token,child_id,data):
        context=self._parent(token)
        key=identifier(data.get('idempotencyKey'))
        subject=data.get('subject')
        if subject not in self.policy['supportedSubjects']:
            raise ApiError('homework_subject_unsupported','请选择语文、数学、英语、科学或其他科目',400)
        analysis_kind=data.get('analysisKind','questions')
        if not isinstance(analysis_kind,str) or analysis_kind not in {'questions','essay'}:
            raise ApiError('homework_analysis_kind_invalid','请选择题目批改或作文点评',400)
        if analysis_kind=='essay' and subject not in {'chinese','english'}:
            raise ApiError('homework_essay_subject_unsupported','作文点评仅支持语文和英语',400)
        if data.get('analysisConsent') is not True:
            raise ApiError('homework_consent_required','请确认使用AI分析这份作业',400)
        title=str(data.get('title') or {'math':'数学','chinese':'语文','english':'英语','science':'科学','other':'综合'}.get(subject,'')+'作业').strip()[:160]
        request_payload={'subject':subject,'title':title,'analysisConsent':True}
        request_hash=digest({**request_payload,'analysisKind':analysis_kind})
        now=self.clock()
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            child=self.repository.child(conn,family,child_id,lock=True)
            if child is None:
                raise ApiError('child_not_found','没有找到孩子',404)
            if child.get('grade_code') not in {f'primary_{n}' for n in range(1,7)}:
                raise ApiError('homework_grade_unsupported','此年级尚未开放作业检查',409)
            existing=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND child_id=? AND idempotency_key=?',(family,child_id,key)).fetchone()
            if existing:
                legacy_question=(analysis_kind=='questions' and existing['request_sha256']==digest(request_payload)
                    and not conn.execute('SELECT id FROM homework_actions WHERE submission_id=? AND item_id=?',(existing['id'],'__analysis_kind__')).fetchone())
                if (existing['request_sha256']!=request_hash and not legacy_question) or existing['deleted_at'] is not None:
                    raise ApiError('homework_idempotency_conflict','此请求编号已用于另一份或已删除的作业',409)
                return self._view(conn,existing)
            identity='hw_'+uuid.uuid4().hex
            conn.execute('INSERT INTO homework_submissions (id,family_id,child_id,grade_code,subject,title,source,idempotency_key,request_sha256,revision,status,consent_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,family,child_id,child['grade_code'],subject,title,'parent_app',key,request_hash,1,'received',now,now,now))
            marker={'schemaVersion':'mira.homework-analysis-kind.v1','analysisKind':analysis_kind}
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                ('hwkind_'+uuid.uuid4().hex,identity,'__analysis_kind__','analysis-kind.v1',digest(marker),canonical(marker),now))
            return self._view(conn,self.repository.submission(conn,family,identity))

    @staticmethod
    def _analysis_kind(conn,identity):
        saved=conn.execute('SELECT result_json FROM homework_actions WHERE submission_id=? AND item_id=? ORDER BY created_at,id LIMIT 1',(identity,'__analysis_kind__')).fetchone()
        value=parsed(saved['result_json'],{}) if saved else {}
        return 'essay' if value.get('analysisKind')=='essay' else 'questions'

    def list_parent(self,token,child_id):
        context=self._parent(token)
        with self.repository.transaction() as conn:
            family=self._permit(conn,context)
            if self.repository.child(conn,family,child_id) is None:
                raise ApiError('child_not_found','没有找到孩子',404)
            rows=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND child_id=? AND deleted_at IS NULL ORDER BY created_at DESC,id DESC LIMIT 50',(family,child_id)).fetchall()
            return {'ok':True,'submissions':[self._view(conn,row)['submission'] for row in rows]}

    def get(self,token,identity):
        context=self._parent(token)
        with self.repository.transaction() as conn:
            family=self._permit(conn,context)
            return self._view(conn,self.repository.submission(conn,family,identity),include_paper_structure=True)

    def upload(self,token,identity,data,body):
        context=self._parent(token)
        key=identifier(data.get('idempotencyKey'))
        # Check owner before spending CPU decoding an image.
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            self.repository.submission(conn,family,identity)
        body,width,height=normalize_image(body,self.policy)
        sha=hashlib.sha256(body).hexdigest()
        now=self.clock()
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            row=self.repository.submission(conn,family,identity,lock=True)
            pages=self.repository.pages(conn,identity)
            existing=next((p for p in pages if p['upload_key']==key),None)
            if existing:
                if existing['content_sha256']!=sha:
                    raise ApiError('homework_idempotency_conflict','同一上传编号不能替换图片',409)
                return self._view(conn,row)
            revision(row,data)
            maximum_pages=1 if row['source']=='paid_validation' else self.policy['maxPages']
            if len(pages)>=maximum_pages:
                raise ApiError('homework_page_limit',f'这份作业最多上传{maximum_pages}页',400)
            if row['status']!='received':
                raise ApiError('homework_upload_closed','分析已开始，请新建作业或先调整页面',409)
            page_id='hwp_'+uuid.uuid4().hex
            # Each upload owns its immutable asset. A removed page's queued
            # cleanup cannot race a later upload of the same photo.
            storage=self.store.put(body,namespace=page_id)
            conn.execute('INSERT INTO homework_pages (id,submission_id,upload_key,content_sha256,storage_key,mime_type,width,height,page_order,rotation,status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (page_id,identity,key,sha,storage,'image/png',width,height,len(pages),0,'received',now))
            conn.execute('UPDATE homework_submissions SET revision=revision+1,updated_at=? WHERE id=?',(now,identity))
            return self._view(conn,self.repository.submission(conn,family,identity))

    def update_pages(self,token,identity,data):
        context=self._parent(token)
        incoming=data.get('pages')
        if not isinstance(incoming,list) or not 0<=len(incoming)<=self.policy['maxPages']:
            raise ApiError('homework_pages_invalid','请选择需要保留的作业页',400)
        now=self.clock()
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            row=self.repository.submission(conn,family,identity,lock=True)
            revision(row,data)
            pages={p['id']:p for p in self.repository.pages(conn,identity)}
            if any(not isinstance(p,dict) or p.get('id') not in pages for p in incoming) or len({p['id'] for p in incoming})!=len(incoming):
                raise ApiError('homework_pages_invalid','作业页编号不匹配',400)
            normalized=[]
            for p in incoming:
                rotation=p.get('rotation',0)
                if type(rotation) is not int or rotation not in {0,90,180,270}:
                    raise ApiError('homework_rotation_invalid','图片旋转角度无效',400)
                normalized.append((p['id'],rotation,crop_region(p.get('crop'))))
            self._revoke(conn,row,reason='pages_changed')
            conn.execute('UPDATE homework_jobs SET status=?,updated_at=? WHERE submission_id=? AND status IN (?,?,?)',('cancelled',now,identity,'queued','working','media_preparing'))
            for item in self.repository.items(conn,identity):
                for media in parsed(item['media_json'],{}).values():
                    if media.get('storageKey'):
                        self._enqueue_delete(conn,media['storageKey'])
            conn.execute('DELETE FROM homework_items WHERE submission_id=?',(identity,))
            for action in conn.execute('SELECT id,item_id,result_json FROM homework_actions WHERE submission_id=?',(identity,)).fetchall():
                saved_action=parsed(action['result_json'],{})
                if action['item_id'] not in {'__analysis_kind__','__tencent_receipt__'} and saved_action.get('schemaVersion')!='mira.homework-tutor-turn.v1' and saved_action.get('schema')!='mira.homework-tutor-asr.v1' and saved_action.get('schemaVersion')!='mira.homework-tutor-asr.v1':
                    conn.execute('DELETE FROM homework_actions WHERE id=?',(action['id'],))
            for order,(page_id,rotation,crop) in enumerate(normalized):
                conn.execute('UPDATE homework_pages SET page_order=?,rotation=?,crop_json=?,status=?,error_code=NULL WHERE id=?',(order,rotation,canonical(crop) if crop else None,'received',page_id))
            for page_id in set(pages)-{p[0] for p in normalized}:
                conn.execute('DELETE FROM homework_pages WHERE id=?',(page_id,))
                key=pages[page_id]['storage_key']
                if not self.repository.asset_referenced(conn,key):
                    self._enqueue_delete(conn,key)
            conn.execute('UPDATE homework_submissions SET revision=revision+1,status=?,error_code=NULL,updated_at=? WHERE id=?',('received',now,identity))
            response=self._view(conn,self.repository.submission(conn,family,identity))
        # Saving page edits also drains the durable deletion outbox. This is
        # local file cleanup and must work even when paid analysis is disabled.
        self.purge_files()
        return response

    def image(self,token,identity,page_id,*,student=False,original=False):
        principal=self._student(token) if student else None
        context=None if student else self._parent(token)
        if student and original:
            raise ApiError('homework_original_parent_only','学生只能查看当前已处理的作业照片',403)
        with self.repository.transaction() as conn:
            family=principal['family_id'] if student else self._permit(conn,context)
            self.repository.submission(conn,family,identity,child=principal['child_id'] if student else None)
            page=conn.execute('SELECT * FROM homework_pages WHERE submission_id=? AND id=?',(identity,page_id)).fetchone()
            if page is None:
                raise ApiError('homework_page_not_found','作业页不存在',404)
            if original:
                return self.store.read(page['storage_key']),'image/png'
            data,_=transformed_image(self.store.read(page['storage_key']),page['rotation'],parsed(page['crop_json']))
            return data,'image/png'

    def audio_asset(self,token,identity,item_id,kind,*,student=False):
        principal=self._student(token) if student else None
        context=None if student else self._parent(token)
        with self.repository.transaction() as conn:
            family=principal['family_id'] if student else self._permit(conn,context)
            row=self.repository.submission(conn,family,identity,child=principal['child_id'] if student else None)
            item=self._item(conn,identity,item_id)
            if student:
                if not self._is_student_ready(parsed(item['result_json'],{}),parsed(item['media_json'],{})):
                    raise ApiError('homework_audio_not_ready','这道题的讲解答案需要先核实',409)
                correction=parsed(item['correction_json'],{})
                if kind in {'hint','explanation'} and not correction.get(kind+'Viewed'):
                    raise ApiError('homework_audio_not_open','请先请求提示或讲解',403)
            media=parsed(item['media_json'],{}).get(kind)
            if not media or media.get('status')!='ready':
                raise ApiError('homework_audio_not_ready','老师语音正在准备',409)
            audio=self.store.read(media['storageKey'])
            if hashlib.sha256(audio).hexdigest()!=media['sha256']:
                raise ApiError('homework_audio_missing','老师音频校验失败，请稍后再试',409)
            return audio,media['mimeType']

    def analyze(self,token,identity,data):
        context=self._parent(token)
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            row=self.repository.submission(conn,family,identity,lock=True)
            revision(row,data)
            pages=self.repository.pages(conn,identity)
            if not pages:
                raise ApiError('homework_pages_required','请先上传作业图片',400)
            self._validation_bounds(row,pages=pages)
            if row['source']=='synthetic_fixture':
                raise ApiError('homework_sample_not_analyzable','这份测试照片仅用于体验上传和编辑，不进行AI分析。请新建作业上传真实照片。',409)
            self._processing_enabled()
            job=conn.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=?',(identity,row['revision'])).fetchone()
            if job:
                # A safe media-only retry never re-sends recognition. Ambiguous paid calls stay blocked.
                if job['status']=='failed' and job['error_code'] in SAFE_RETRY:
                    if job['error_code'] in QUERY_RETRY_ERRORS and not HomeworkTencentGrading(self).resume_queries(conn,row):
                        return self._view(conn,row)
                    conn.execute('UPDATE homework_jobs SET status=?,error_code=NULL,updated_at=? WHERE id=?',('queued',self.clock(),job['id']))
                    conn.execute('UPDATE homework_submissions SET status=?,error_code=NULL WHERE id=?',('queued',identity))
                return self._view(conn,self.repository.submission(conn,family,identity))
            now=self.clock()
            stage='media' if row['status']=='media_preparing' and self.repository.items(conn,identity) else 'quality_check'
            conn.execute('INSERT INTO homework_jobs (id,submission_id,revision,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',('hwj_'+uuid.uuid4().hex,identity,row['revision'],'queued',stage,now,now))
            conn.execute('UPDATE homework_submissions SET status=?,error_code=NULL,updated_at=? WHERE id=?',('queued',now,identity))
            return self._view(conn,self.repository.submission(conn,family,identity))

    def authorize_recognition_recovery(self,conn,scope,*,execute=False,approval_text=None):
        # Internal audited recovery; ordinary analyze never grants paid retries.
        from services.homework_recognition_recovery import authorize_recovery
        return authorize_recovery(self,conn,scope,execute=execute,approval_text=approval_text)

    def authorize_recognition_repair(self,conn,scope,*,execute=False,approval_text=None):
        """Internal operator-only recovery. No route exposes this method.

        The caller owns the transaction (READ ONLY for preflight). Execution
        atomically records one immutable grant and its new revision/job. The old
        unknown receipt is evidence, never a reusable retry permission.
        """
        self._enabled()
        required={'phone','familyId','childId','submissionId','expectedRevision','unknownCallId'}
        if (not isinstance(scope,dict) or set(scope)!=required
                or not re.fullmatch(r'\d{11}',str(scope['phone']))
                or type(scope['expectedRevision']) is not int or scope['expectedRevision']<1):
            raise ApiError('homework_repair_scope_invalid','修复范围不完整',409)
        for key in ('familyId','childId','submissionId','unknownCallId'):
            identifier(scope[key])
        if execute and approval_text!='允许重新分析一次':
            raise ApiError('homework_repair_approval_required','需要这份作业的一次重新分析授权',409)
        user=conn.execute('SELECT id,phone,family_id FROM users WHERE phone=?',(scope['phone'],)).fetchone()
        if not user or user['family_id']!=scope['familyId']:
            raise ApiError('homework_repair_scope_invalid','授权家庭不匹配',409)
        self.profile._assert_capability(conn,{'user':dict(user),'family':{'id':scope['familyId']}},'manage_tasks')
        row=self.repository.submission(conn,scope['familyId'],scope['submissionId'],child=scope['childId'],lock=execute)
        audit_id='hwrepair_'+digest([RECOGNITION_REPAIR_CONTRACT,scope['submissionId'],scope['unknownCallId']])[:56]
        existing=conn.execute('SELECT * FROM homework_actions WHERE id=?',(audit_id,)).fetchone()
        if existing:
            grant=parsed(existing['result_json'],{})
            if existing['request_sha256']!=digest(grant) or grant.get('scopeSha256')!=digest(scope):
                raise ApiError('homework_repair_scope_invalid','修复授权范围不匹配',409)
            pages=self.repository.pages(conn,row['id'])
            if (row['revision']!=grant.get('newRevision') or row['source']!='parent_app' or len(pages)!=1
                    or grant.get('input')!=self._recognition_repair_input(pages[0])):
                raise ApiError('homework_repair_scope_changed','作业已变化，本次授权不能用于新的内容',409)
            job=conn.execute('SELECT id,status FROM homework_jobs WHERE id=?',(grant.get('jobId'),)).fetchone()
            if not job:
                raise ApiError('homework_repair_authorization_invalid','修复任务记录缺失，不会再次生成',409)
            return {'ok':True,'authorized':True,'alreadyAuthorized':True,'authorizationId':audit_id,
                'submissionId':row['id'],'revision':grant['newRevision'],'jobId':job['id'],
                'jobStatus':job['status'],'expiresAt':grant['expiresAt'],'maximumNewVisionCalls':1}
        if (row['revision']!=scope['expectedRevision'] or row['source']!='parent_app'
                or row['status']!='provider_unknown' or row['error_code']!='homework_provider_unknown'):
            raise ApiError('homework_repair_scope_changed','作业版本或失败状态已变化，不能使用本次授权',409)
        pages=self.repository.pages(conn,row['id'])
        # This bounded repair is for a single page that failed before any result.
        # Existing partial results require a separately reviewed recovery path.
        if len(pages)!=1 or self.repository.items(conn,row['id']):
            raise ApiError('homework_repair_scope_changed','仅允许修复尚无识别结果的单页作业',409)
        old_job=conn.execute('SELECT * FROM homework_jobs WHERE submission_id=? AND revision=?',
            (row['id'],row['revision'])).fetchone()
        old_call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(scope['unknownCallId'],)).fetchone()
        if (not old_job or old_job['status']!='failed' or old_job['error_code']!='homework_provider_unknown'
                or not old_call or old_call['status']!='unknown' or old_call['error_code']!='homework_provider_unknown'
                or old_call['submission_id']!=row['id'] or old_call['child_id']!=row['child_id']
                or old_call['page_id']!=pages[0]['id']):
            raise ApiError('homework_repair_scope_changed','原失败任务和未知请求不匹配',409)
        if conn.execute('SELECT id FROM homework_jobs WHERE submission_id=? AND status IN (?,?)',
                (row['id'],'queued','working')).fetchone():
            raise ApiError('homework_repair_scope_changed','已有分析任务正在运行',409)
        binding=self._recognition_repair_input(pages[0])
        if (old_call['request_sha256']!=binding['baseRequestSha256']
                or old_call['provider']!=self.provider.provider_name or old_call['model']!=self.provider.model_name):
            raise ApiError('homework_repair_scope_changed','原请求输入或模型已变化',409)
        count=conn.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=?',(row['id'],)).fetchone()['n']
        if count>=self.policy['maxProviderCallsPerSubmission']:
            raise ApiError('homework_budget_exceeded','这份作业已达到分析次数上限',409)
        now=self.clock()
        grant={'schema':'homework.operator-recognition-repair.v1','authorizationId':audit_id,
            'scopeSha256':digest(scope),'approvedByUserId':user['id'],'familyId':row['family_id'],
            'childId':row['child_id'],'submissionId':row['id'],'oldRevision':row['revision'],
            'newRevision':row['revision']+1,'oldCallId':old_call['id'],'oldCallSha256':digest(dict(old_call)),
            'oldJobId':old_job['id'],'oldJobSha256':digest(dict(old_job)),
            'jobId':'hwj_repair_'+digest(audit_id)[:48],'input':binding,
            'maximumNewVisionCalls':1,'approvedAt':now,'expiresAt':now+RECOGNITION_REPAIR_TTL_MS,
            'approvalText':'允许重新分析一次'}
        if execute:
            self._processing_enabled()
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (audit_id,row['id'],RECOGNITION_REPAIR_ITEM,old_call['id'],digest(grant),canonical(grant),now))
            conn.execute('UPDATE homework_submissions SET revision=?,status=?,error_code=NULL,updated_at=? WHERE id=?',
                (grant['newRevision'],'queued',now,row['id']))
            conn.execute('INSERT INTO homework_jobs (id,submission_id,revision,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',
                (grant['jobId'],row['id'],grant['newRevision'],'queued','quality_check',now,now))
        return {'ok':True,'authorized':execute,'alreadyAuthorized':False,'authorizationId':audit_id,
            'submissionId':row['id'],'revision':grant['newRevision'],'jobId':grant['jobId'],
            'jobStatus':'queued' if execute else 'not_created','expiresAt':grant['expiresAt'],
            'maximumNewVisionCalls':1,'inputSha256':binding['imageSha256'],
            'wireContract':RECOGNITION_REPAIR_CONTRACT,'wireImageSha256':binding['wire']['imageSha256']}

    def _recognition_repair_input(self,page):
        from integrations.ai.kimi_vision_provider import OpenAICompatibleVisionProvider,_encode_image
        if not isinstance(self.provider,OpenAICompatibleVisionProvider) or not self.provider.api_key:
            raise ApiError('homework_repair_contract_invalid','完整图片识别适配器尚未配置',409)
        original=self.store.read(page['storage_key'])
        if hashlib.sha256(original).hexdigest()!=page['content_sha256']:
            raise ApiError('homework_repair_scope_changed','作业图片已变化',409)
        image,_=transformed_image(original,page['rotation'],parsed(page['crop_json']))
        encoded=_encode_image(image,'image/png',self.provider.max_bytes,
            max_dimension=self.provider.max_image_dimension,jpeg_quality=self.provider.jpeg_quality)
        if encoded is None:
            raise ApiError('homework_repair_contract_invalid','完整图片无法编码，未授权调用',409)
        spec=self.policy['recognitionPrompt']
        prompt=self.prompts.get_prompt(spec['id'],spec['version'])
        if prompt is None:
            raise ApiError('homework_prompt_missing','作业分析策略尚未配置',503)
        return {'pageId':page['id'],'pageSha256':digest({key:page[key] for key in
                    ('id','submission_id','content_sha256','storage_key','rotation','crop_json','page_order')}),
            'imageSha256':hashlib.sha256(image).hexdigest(),
            'baseRequestSha256':digest({'image':hashlib.sha256(image).hexdigest(),'prompt':prompt.body,
                'policy':self.policy,'provider':str(self.provider.provider_name),'model':str(self.provider.model_name)}),
            'wire':{'contract':RECOGNITION_REPAIR_CONTRACT,'imageSha256':hashlib.sha256(encoded.encode()).hexdigest(),
                'provider':self.provider.provider_name,'model':self.provider.model_name,
                'endpointSha256':digest(self.provider.base_url),'maxBytes':self.provider.max_bytes,
                'maxDimension':self.provider.max_image_dimension,'jpegQuality':self.provider.jpeg_quality}}

    def _recognition_repair_grant(self,conn,job,row,page,image):
        if job['id'].startswith('hwj_response_repair_'):
            from services.homework_recognition_recovery import recognition_recovery_grant
            return recognition_recovery_grant(self,conn,job,row,page,image)
        if not job['id'].startswith('hwj_repair_'):
            return None
        records=conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=?',
            (row['id'],RECOGNITION_REPAIR_ITEM)).fetchall()
        for record in records:
            grant=parsed(record['result_json'],{})
            if grant.get('jobId')!=job['id']:
                continue
            if (record['request_sha256']!=digest(grant) or grant.get('schema')!='homework.operator-recognition-repair.v1'
                    or grant.get('authorizationId')!=record['id'] or grant.get('maximumNewVisionCalls')!=1
                    or grant.get('approvalText')!='允许重新分析一次' or grant.get('newRevision')!=row['revision']
                    or grant.get('familyId')!=row['family_id'] or grant.get('childId')!=row['child_id']
                    or grant.get('submissionId')!=row['id'] or row['source']!='parent_app'
                    or len(self.repository.pages(conn,row['id']))!=1
                    or grant.get('input')!=self._recognition_repair_input(page)
                    or grant['input']['imageSha256']!=hashlib.sha256(image).hexdigest()):
                break
            old_call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(grant.get('oldCallId'),)).fetchone()
            old_job=conn.execute('SELECT * FROM homework_jobs WHERE id=?',(grant.get('oldJobId'),)).fetchone()
            if (not old_call or not old_job or digest(dict(old_call))!=grant.get('oldCallSha256')
                    or digest(dict(old_job))!=grant.get('oldJobSha256')):
                break
            return {'id':record['id'],'sha256':record['request_sha256'],'expiresAt':grant['expiresAt'],'wire':grant['input']['wire']}
        raise ApiError('homework_repair_authorization_invalid','单次修复授权缺失或作业已变化，不会发出请求',409)

    def correct_recognition(self,token,identity,item_id,data):
        context=self._parent(token)
        if data.get('recognitionConfirmed') is not True:
            raise ApiError('homework_confirmation_required','请确认题干和孩子原作答',400)
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            row=self.repository.submission(conn,family,identity,lock=True)
            revision(row,data)
            item=self._item(conn,identity,item_id)
            if data.get('itemRevision')!=item['revision']:
                raise ApiError('homework_revision_conflict','这道题已更新，请刷新',409)
            if self.processing_enabled and row['status'] in {'queued','quality_check','recognizing','checking'}:
                raise ApiError('homework_analysis_running','请等待当前分析完成',409)
            old=parsed(item['result_json'])
            raw={**old,'prompt':data.get('prompt',old['prompt']),'studentAnswer':data.get('studentAnswer',old['studentAnswer']),
                'region':data.get('region',old['region']),'type':data.get('type','arithmetic')}
            if not isinstance(raw['prompt'],str) or not isinstance(raw['studentAnswer'],str) or len(raw['prompt'])>1000 or len(raw['studentAnswer'])>1000:
                raise ApiError('homework_item_invalid','题目或作答内容无效',400)
            result=check_item(raw,grade=row['grade_code'],subject=row['subject'],policy=self.policy,confirmed=True)
            self._revoke(conn,row,item=item,reason='recognition_corrected')
            new_revision=item['revision']+1
            now=self.clock()
            conn.execute('INSERT INTO homework_item_revisions (item_id,revision,submission_id,result_json,reason,created_at) VALUES (?,?,?,?,?,?)',(item_id,new_revision,identity,canonical(result),'parent_correction',now))
            conn.execute('UPDATE homework_items SET revision=?,result_json=?,media_json=?,correction_json=?,updated_at=? WHERE id=?',(new_revision,canonical(result),'{}','{}',now,item_id))
            conn.execute('UPDATE homework_submissions SET revision=revision+1,status=?,updated_at=? WHERE id=?',('media_preparing',now,identity))
            changed=self._item(conn,identity,item_id)
            self._evidence(conn,row,changed,result)
            # Queue a media-only continuation. Recognized items are already durable.
            new_row=self.repository.submission(conn,family,identity)
            if self.processing_enabled and row['source']!='synthetic_fixture':
                conn.execute('INSERT INTO homework_jobs (id,submission_id,revision,status,stage,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',('hwj_'+uuid.uuid4().hex,identity,new_row['revision'],'queued','media',now,now))
            return self._view(conn,new_row)

    def delete(self,token,identity,data):
        context=self._parent(token)
        with self.repository.transaction() as conn:
            family=self._permit(conn,context,True)
            # Idempotent deletion with an authenticated family lookup.
            row=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND id=?',(family,identity)).fetchone()
            if row is not None:
                self.repository.child(conn,family,row['child_id'],lock=True)
                row=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND id=? FOR UPDATE',(family,identity)).fetchone()
            if row is None:
                raise ApiError('homework_not_found','没有找到这份作业',404)
            if row['deleted_at'] is not None:
                return {'ok':True,'deleted':True,'submissionId':identity}
            revision(row,data)
            self._revoke(conn,row,reason='source_deleted')
            for page in self.repository.pages(conn,identity):
                self._enqueue_delete(conn,page['storage_key'])
            for item in self.repository.items(conn,identity):
                for media in parsed(item['media_json'],{}).values():
                    if media.get('storageKey'):
                        self._enqueue_delete(conn,media['storageKey'])
            if self.audio:
                self.audio.revoke_submission(conn,identity)
            for call in conn.execute('SELECT id,receipt_json FROM homework_provider_calls WHERE submission_id=?',(identity,)).fetchall():
                saved_receipt=parsed(call['receipt_json'],{})
                reference=saved_receipt.get('receivedResponse',{})
                if reference.get('storageKey'):
                    self._enqueue_delete(conn,reference['storageKey'])
                for key in ('requestJournalKey','responseJournalKey'):
                    if saved_receipt.get(key):
                        self._enqueue_delete(conn,saved_receipt[key])
                self._enqueue_delete(conn,self.store.response_key('homework-vision-response:'+call['id']))
            for action in conn.execute('SELECT result_json FROM homework_actions WHERE submission_id=? AND item_id=?',(identity,'__tencent_receipt__')).fetchall():
                key=parsed(action['result_json'],{}).get('storageKey')
                if key:
                    self._enqueue_delete(conn,key)
            for table in ('homework_items','homework_pages','homework_item_revisions','homework_actions'):
                conn.execute(f'DELETE FROM {table} WHERE submission_id=?',(identity,))
            conn.execute('UPDATE homework_provider_calls SET result_json=NULL,receipt_json=NULL,status=? WHERE submission_id=?',('deleted',identity))
            conn.execute('UPDATE homework_jobs SET status=?,updated_at=? WHERE submission_id=?',('cancelled',self.clock(),identity))
            conn.execute('UPDATE homework_submissions SET deleted_at=?,updated_at=?,status=?,title=?,error_code=NULL WHERE id=?',(self.clock(),self.clock(),'deleted','已删除',identity))
        self.purge_files()
        return {'ok':True,'deleted':True,'submissionId':identity}

    def _enqueue_delete(self,conn,key):
        if conn.execute('SELECT storage_key FROM homework_file_deletions WHERE storage_key=?',(key,)).fetchone() is None:
            conn.execute('INSERT INTO homework_file_deletions (storage_key,created_at) VALUES (?,?)',(key,self.clock()))

    def purge_files(self):
        with self.repository.transaction() as conn:
            keys=conn.execute('SELECT storage_key FROM homework_file_deletions LIMIT 100').fetchall()
        for row in keys:
            key=row['storage_key']
            with self.repository.transaction() as conn:
                if conn.execute('SELECT storage_key FROM homework_file_deletions WHERE storage_key=? FOR UPDATE',(key,)).fetchone() is None:
                    continue
                # Covers old shared image keys and audio retained by a
                # succeeded receipt for a future no-charge reuse.
                if not self.repository.asset_referenced(conn,key):
                    try:
                        self.store.delete(key)
                    except OSError:
                        continue
                conn.execute('DELETE FROM homework_file_deletions WHERE storage_key=?',(key,))

    def _item(self,conn,identity,item_id):
        item=conn.execute('SELECT * FROM homework_items WHERE submission_id=? AND id=?',(identity,item_id)).fetchone()
        if item is None:
            raise ApiError('homework_item_not_found','题目不存在',404)
        return item

    def _revoke(self,conn,row,*,item=None,reason):
        self.tutor.revoke(conn,row,item=item)
        if not self.evidence_enabled:
            # The feature switch gates new evidence, never deletion of older private data.
            if getattr(conn,'dialect',None)=='postgresql':
                exists=conn.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?',('learning_answer_events',)).fetchone()
            else:
                # Isolated verification database only; production uses PostgreSQL.
                exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",('learning_answer_events',)).fetchone()
            if exists is None:
                return
        from services.learning_evidence_service import revoke_event,revoke_source
        args={'family_id':row['family_id'],'child_id':row['child_id'],'source_kind':'homework','source_id':row['id'],'now':self.clock(),'reason':reason,'purge':reason=='source_deleted'}
        if item:
            revoke_event(conn,**args,event_key=f"{item['id']}:{item['revision']}")
            for attempt in range(1,int(parsed(item['correction_json'],{}).get('attempts',0))+1):
                revoke_event(conn,**args,event_key=f"{item['id']}:{item['revision']}:correction:{attempt}")
        else:
            revoke_source(conn,**args)

    def _evidence(self,conn,row,item,result):
        if not result.get('knowledgeId') or not result.get('knowledgeLabel'):
            return
        if result.get('method')=='tencent_question.v1':
            if not self.evidence_enabled or row['source'] in NON_ASSESSMENT_SOURCES:
                return
            result=self._learning_result(conn,row,item)
            reference=reference_for_correction(result)
            if reference is None or reference['originalStatus'] not in {'correct','incorrect'}:
                return
            from services.learning_evidence_service import record_answer,event_id
            key=f"{item['id']}:{item['revision']}"
            # Older immutable evidence is never rewritten during a re-read or
            # local parser repair. Read-side validation excludes unsafe records.
            if conn.execute('SELECT id FROM learning_answer_events WHERE id=?',
                    (event_id(row['family_id'],row['child_id'],'homework',row['id'],key),)).fetchone():
                return
            record_answer(conn,family_id=row['family_id'],child_id=row['child_id'],source_kind='homework',source_id=row['id'],
                event_key=key,question=evidence_question(row,item,result,reference),answer=result['studentAnswer'],
                correct=reference['originalStatus']=='correct',occurred_at=item['updated_at'],independent=None,
                confidence=None,confirmed=True,diagnosis={'method':reference['method'],'referenceAuthority':reference['authority'],
                    'referenceDigest':reference['digest'],'scope':'paper_answer_unknown_help','masteryClaim':False})
            return
        if not self.evidence_enabled or row['source'] in NON_ASSESSMENT_SOURCES or result['status'] not in {'correct','incorrect'}:
            return
        from services.learning_evidence_service import record_answer
        record_answer(conn,family_id=row['family_id'],child_id=row['child_id'],source_kind='homework',source_id=row['id'],
            event_key=f"{item['id']}:{item['revision']}",question={'id':item['id'],'version':str(item['revision']),
                'subject':row['subject'],'gradeCode':row['grade_code'],'knowledgeId':result['knowledgeId'],
                'knowledgeLabel':result['knowledgeLabel'],'prompt':result['prompt'],'correctAnswer':result['expectedAnswer'],
                'explanation':result['explanation'],'private':True,'knowledgePoints':result.get('knowledgePoints',[])},answer=result['studentAnswer'],correct=result['status']=='correct',
            occurred_at=item['updated_at'],independent=None,confidence=result['confidence'],confirmed=True,
            diagnosis={'method':result['method'],'recognitionConfirmed':result['recognitionConfirmed'],'scope':'paper_answer_unknown_help','sourceValidation':result.get('sourceValidation')})

    def _learning_result(self,conn,row,item):
        page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',(item['page_id'],row['id'])).fetchone()
        result=reviewed_result(row,item,page)
        return attach_reference_answer_layout(conn,row,item,result)

    def _record_tutor_correction(self,conn,row,item,result,turn,reply,reference=None):
        """Persist only this child's new response, separately from the paper."""
        current=self._item(conn,row['id'],item['id'])
        if current['revision']!=turn['itemRevision'] or row['revision']!=turn['submissionRevision']:
            raise ApiError('homework_job_superseded','原题已更新，请重新打开',409)
        result=self._learning_result(conn,row,current)
        reference=reference_for_correction(result)
        correction=parsed(current['correction_json'],{})
        if reply.get('teachingQuality',{}).get('status') not in {'verified','guidance'}:
            return correction_view(result,correction,item_revision=item['revision'])
        correction['tutorViewed']=True
        if turn['mode']!='answer':
            correction['explanationViewed']=True
        elif turn['id'] not in correction.get('answerTurnIds',[]):
            correction.pop('selfReportedCompletion',None)
            feedback=evaluate_response(turn['message'],reference) if reference else None
            if feedback is not None:
                attempts=int(correction.get('attempts',0))+1
                if attempts>10:
                    raise ApiError('homework_attempt_limit','先听老师讲一讲，再休息一下',409)
                now=self.clock()
                correction.update(attempts=attempts,correct=feedback['correct'],lastAnswer=turn['message'],
                    lastChoice=feedback['normalizedAnswer'],updatedAt=now,referenceDigest=reference['digest'],
                    referenceAuthority=reference['authority'],lastAnswerTurnId=turn['id'],
                    answerTurnIds=[*correction.get('answerTurnIds',[]),turn['id']],
                    correctedAt=now if feedback['correct'] else None)
                self._evidence(conn,row,current,result)
                if (self.evidence_enabled and row['source'] not in NON_ASSESSMENT_SOURCES
                        and result.get('knowledgeId') and result.get('knowledgeLabel')):
                    from services.learning_evidence_service import record_answer
                    record_answer(conn,family_id=row['family_id'],child_id=row['child_id'],source_kind='homework',source_id=row['id'],
                        event_key=f"{item['id']}:{item['revision']}:correction:{attempts}",
                        question=evidence_question(row,current,result,reference),answer=turn['message'],correct=feedback['correct'],
                        occurred_at=now,attempt=attempts+1,hint_used=bool(correction.get('hintViewed') or correction.get('explanationViewed')),
                        adult_help=None,independent=None,confirmed=True,diagnosis={**feedback,'masteryClaim':False,'turnId':turn['id']})
        conn.execute('UPDATE homework_items SET correction_json=? WHERE id=?',(canonical(correction),item['id']))
        return correction_view(result,correction,item_revision=item['revision'])

    def _view(self,conn,row,*,student=False,include_paper_structure=False):
        identity=row['id']
        analysis_kind=self._analysis_kind(conn,identity)
        essay_suggestions=[]
        assessment_methods=set()
        pages=[]
        source_pages=self.repository.pages(conn,identity)
        page_by_id={page['id']:page for page in source_pages}
        for page in source_pages:
            crop=parsed(page['crop_json'])
            width,height=(transformed_geometry(page['width'],page['height'],page['rotation'],crop)[0]
                if student else (page['width'],page['height']))
            prefix='v2/student/learning/homework' if student else 'homework-submissions'
            pages.append({'id':page['id'],'order':page['page_order'],'rotation':page['rotation'],'crop':crop,
                'width':width,'height':height,'status':page['status'],'error':page['error_code'],
                'assetUrl':f'/api/{prefix}/{identity}/pages/{page["id"]}/image'})
        items=[]
        tutor_items=[]
        original_paper_items=[]
        original_paper_summary={'correct':0,'incorrect':0,'unknown':0,'blank':0,'total':0,'countsForAbility':False}
        provisional_paper_summary={'correct':0,'incorrect':0,'unknown':0,'blank':0,'total':0,'countsForAbility':False}
        provider_verdict_summary={'correct':0,'incorrect':0,'unknown':0,'total':0}
        original_summary={status:0 for status in ('correct','incorrect','blank','pending','unsupported')}
        original_summary['total']=0
        student_summary={'ready':0,'awaitingMedia':0,'unsupportedCorrection':0,'corrected':0,'selfReportedCompleted':0}
        current_items=self.repository.items(conn,identity)
        for ordinal,item in enumerate(current_items,1):
            result=attach_reference_answer_layout(conn,row,item,reviewed_result(row,item,page_by_id.get(item['page_id'])),siblings=current_items)
            result=practice_result(result)
            is_essay=result.get('method')=='tencent_essay.v1'
            assessment_methods.add(result.get('method'))
            if is_essay:
                essay_suggestions.extend(result.get('essaySuggestions',[]))
            correction=parsed(item['correction_json'],{})
            student_correction=correction_view(result,correction,item_revision=item['revision'])
            media=parsed(item['media_json'],{})
            ready=self._is_student_ready(result,media)
            original_summary['total']+=int(not is_essay)
            if not is_essay and result['status'] in original_summary:
                original_summary[result['status']]+=1
            view={k:v for k,v in result.items() if k not in {'voiceTexts','tencentRaw'} and not k.startswith('_')}
            review_context=source_review_context(item,result,ordinal)
            if result.get('method')=='tencent_question.v1':
                review_context={**review_context,'grading':student_grading(result)}
                safe_status=review_context['grading'].get('status','unknown')
                view['status']=safe_status if safe_status in {'correct','incorrect'} else 'pending'
                view.pop('providerAssessment',None)
                if safe_status not in {'correct','incorrect'}:
                    for field in ('expectedAnswer','explanation','referenceSteps','deterministicValidation'):
                        view.pop(field,None)
                else:
                    view['expectedAnswer']=review_context['grading'].get('referenceAnswer')
                    view['explanation']=review_context['grading'].get('analysis','')
                    # Shared provider steps may still contain the superseded
                    # conclusion even when the answer itself was adjudicated.
                    view.pop('referenceSteps',None)
                # Parent and student formal results use the same safe verdict.
                # The original provider receipt stays in private storage.
                if not is_essay:
                    if result['status'] in original_summary:
                        original_summary[result['status']]-=1
                    original_summary[view['status']]+=1
            if view['status']=='incorrect':
                student_summary['corrected']+=int(student_correction['correct'] is True)
                student_summary['selfReportedCompleted']+=int(student_correction['selfReportedCompleted'])
                if ready:
                    student_summary['ready']+=1
                elif result.get('answerMode'):
                    student_summary['awaitingMedia']+=1
                else:
                    student_summary['unsupportedCorrection']+=1
            if result.get('method')=='tencent_question.v1':
                # Saved v2 items receive the additive original-paper contract
                # on read. No AI retry, result rewrite or score change is needed.
                view.update(gradingReference=review_context['grading'],
                    sourceHierarchy=review_context['sourceHierarchy'],reviewContext=review_context)
            tutor_turns=[v for _,v in self.tutor._turns(conn,row,item)]
            latest_tutor=next((v for v in reversed(tutor_turns) if v.get('status')=='ready'),None)
            if latest_tutor:
                from services.homework_tutor_service import teaching_view
                latest_tutor=teaching_view(latest_tutor,self.tutor._result(conn,row,item,result))
            view.update(studentCorrection=student_correction,latestTutorTeachingQuality=latest_tutor.get('teachingQuality') if latest_tutor else None,
                tutorAvailable=self.tutor.available(row,result),tutorEnabled=self.tutor.available(row,result),assessmentMethod=result.get('method'),tutorAssessment=latest_tutor.get('assessment') if latest_tutor else None,latestTutorAssessment=latest_tutor.get('assessment') if latest_tutor else None,latestTutorTeacherText=latest_tutor.get('teacherText') if latest_tutor else None,id=item['id'],pageId=item['page_id'],revision=item['revision'],readyForStudent=ready,
                correctionStatus='corrected' if student_correction['correct'] is True else 'pending',
                hintViewed=bool(correction.get('hintViewed')),explanationViewed=bool(correction.get('explanationViewed')),
                voice={key:{'assetUrl':f'/api/{"v2/student/learning/" if student else ""}homework{ "" if student else "-submissions"}/{identity}/items/{item["id"]}/audio/{key}',
                    'status':value['status'],'mimeType':value.get('mimeType'),'providerId':value.get('providerId'),'voiceId':value.get('voiceId')} for key,value in media.items()})
            if view['tutorAvailable']:
                tutor_items.append({'id':item['id'],'pageId':item['page_id'],'revision':item['revision'],'prompt':result['prompt'],'status':view['status'],'type':result.get('type'),'tutorAvailable':True,'assessmentMethod':result.get('method'),'tutorAssessment':view['tutorAssessment'],'reviewContext':review_context,
                    'studentCorrection':student_correction,'latestTutorTeachingQuality':view['latestTutorTeachingQuality']})
            if not is_essay:
                original_paper_items.append({'id':item['id'],'pageId':item['page_id'],'revision':item['revision'],
                    'prompt':result['prompt'],'status':view['status'],'type':result.get('type'),
                    'tutorAvailable':view['tutorAvailable'],'assessmentMethod':result.get('method'),
                    'tutorAssessment':view['tutorAssessment'],'reviewContext':review_context,
                    'studentCorrection':student_correction,'latestTutorTeachingQuality':view['latestTutorTeachingQuality']})
                paper_status=(review_context['grading']['status'] if 'grading' in review_context
                    else result['status'] if result['status'] in {'correct','incorrect'} else 'unknown')
                original_paper_summary[paper_status]+=1
                original_paper_summary['blank']+=int(review_context.get('grading',{}).get('answerState',result.get('answerState'))=='blank')
                original_paper_summary['total']+=1
                if 'grading' in review_context:
                    # An initial Tencent verdict is a separate display aid,
                    # never a formal wrong answer, correction or ability event.
                    grading=review_context['grading']
                    provisional=(grading.get('providerVerdict') or {}).get('status','unknown')
                    provisional_paper_summary[provisional]+=1
                    provisional_paper_summary['blank']+=int(grading.get('answerState')=='blank')
                    provisional_paper_summary['total']+=1
                    provider_correct=(review_context['grading'].get('status')=='correct'
                        if review_context['grading'].get('status') in {'correct','incorrect'} else None)
                    provider_verdict_summary['correct' if provider_correct is True else 'incorrect' if provider_correct is False else 'unknown']+=1
                    provider_verdict_summary['total']+=1
            if student:
                if view['status']!='incorrect':
                    continue
                view.pop('studentAnswer',None)
                if result.get('method') in {'decimal_arithmetic.v1','tencent_question.v1'}:
                    # This is the saved wrong answer in the photographed paper,
                    # never the reference answer. Regions use the transformed
                    # image above; the ordinal includes correct/unverified items.
                    view['reviewContext']=review_context
                # Reference answers belong to the expandable original-paper
                # review, not the active independent correction question.
                view.pop('gradingReference',None)
                if not correction.get('explanationViewed'):
                    view.pop('expectedAnswer',None)
                    view.pop('explanation',None)
                    view.pop('referenceSteps',None)
                    view.pop('deterministicValidation',None)
                if not correction.get('hintViewed'):
                    view.pop('hint',None)
                # Paper review is separate from answering a correction question.
                view.pop('region',None)
            if is_essay:
                continue
            items.append(view)
        summary={status:sum(i['status']==status for i in items) for status in ('correct','incorrect','blank','pending','unsupported')}
        summary.update(total=len(items),corrected=sum(i['correctionStatus']=='corrected' for i in items),
            selfReportedCompleted=sum(i['studentCorrection']['selfReportedCompleted'] for i in items))
        job=conn.execute('SELECT status,error_code FROM homework_jobs WHERE submission_id=? AND revision=?',(identity,row['revision'])).fetchone()
        analysis_available=self.processing_enabled and row['source']!='synthetic_fixture'
        unavailable_reason='这份测试照片仅用于体验上传和编辑，不进行AI分析。请新建作业上传真实照片。' if row['source']=='synthetic_fixture' else '照片已保存，AI分析尚未启用'
        processing=bool(analysis_available and job and job['status'] in {'queued','working'})
        retry_allowed=bool(analysis_available and job and job['status']=='failed' and job['error_code'] in SAFE_RETRY)
        query_retry=bool(retry_allowed and job['error_code'] in QUERY_RETRY_ERRORS)
        if query_retry:
            retry_allowed=HomeworkTencentGrading(self).can_resume_queries(conn,row)
        structure_fields={}
        if include_paper_structure and analysis_kind!='essay':
            from services.homework_paper_structure import paper_structure
            structure=paper_structure(self,conn,row)
            if structure is not None:
                structure_fields['paperStructure']=structure
        return {'ok':True,'submission':{'id':identity,'childId':row['child_id'],'gradeCode':row['grade_code'],'subject':row['subject'],
            'title':row['title'],'source':row['source'],'revision':row['revision'],'status':row['status'],'error':row['error_code'],'analysisKind':analysis_kind,
            'analysisAvailable':analysis_available,'availabilityReason':None if analysis_available else unavailable_reason,
            'processing':processing,'retryAllowed':retry_allowed,'retryReason':('继续查询已保存的原批改任务，不会重新提交照片。' if query_retry else '服务配置完成后，可继续处理已保存的作业。') if retry_allowed else None,
            'pages':pages,'items':items,'tutorItems':tutor_items,'originalPaperItems':original_paper_items,**structure_fields,
            'tutorAvailable':bool(tutor_items),'tutorSummary':self.tutor.summary(conn,row),'summary':summary,
            'originalSummary':original_summary,'originalPaperSummary':original_paper_summary,
            **({'provisionalPaperSummary':provisional_paper_summary} if provisional_paper_summary['total'] else {}),
            'providerVerdictSummary':provider_verdict_summary,'studentSummary':student_summary,
            'createdAt':row['created_at'],'updatedAt':row['updated_at'],
            'scope':('essay_guidance_only' if analysis_kind=='essay' else 'tencent_paper_grading_and_ai_guidance' if 'tencent_question.v1' in assessment_methods else 'exact_arithmetic_and_ai_guidance'),
            **({'essayReview':{'status':'ready' if 'tencent_essay.v1' in assessment_methods and row['status']=='ready' else 'failed' if row['status'] in {'failed','provider_unknown'} else 'pending',
                'scope':'guidance_only','suggestions':essay_suggestions,'countsForAbility':False}} if analysis_kind=='essay' else {}),
            'helpEvidence':'unknown','readyForStudent':any(i['readyForStudent'] for i in items)}}

    def list_student(self,token):
        # Authenticate even when disabled; never query an unmigrated table then.
        principal=self.student_auth.authenticate(token)['principal']
        if not self.enabled:
            return {'ok':True,'enabled':False,'submissions':[],'captureTasks':[]}
        with self.repository.transaction() as conn:
            rows=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND child_id=? AND deleted_at IS NULL AND source<>? ORDER BY created_at DESC,id DESC LIMIT 50',(principal['family_id'],principal['child_id'],'paid_validation')).fetchall()
            values=[self._view(conn,row,student=True)['submission'] for row in rows]
        capture_tasks=self.capture_service.student_tasks(principal) if self.capture_service else []
        # A real, submitted photo remains visible while processing, after a
        # failure, and when it has no mistakes. Upload drafts and empty
        # synthetic fixtures are not student assignments.
        visible=[value for value in values if value['items'] or
            value['source'] in {'parent_app','document_camera'} and value['status']!='received']
        return {'ok':True,'enabled':True,'submissions':visible,'captureTasks':capture_tasks}

    def student_detail(self,token,identity):
        principal=self._student(token)
        with self.repository.transaction() as conn:
            row=self.repository.submission(conn,principal['family_id'],identity,child=principal['child_id'])
            return self._view(conn,row,student=True,include_paper_structure=True)

    def student_action(self,token,identity,item_id,data):
        principal=self._student(token)
        action=data.get('action')
        if action not in {'hint','explanation','self_complete','reopen'}:
            raise ApiError('homework_action_invalid','学习操作无效',400)
        self_report_action=action in {'self_complete','reopen'}
        key=identifier(data.get('idempotencyKey')) if self_report_action else None
        request_hash=digest({'schemaVersion':'mira.homework-self-reported-action.v1',
            'itemRevision':data.get('itemRevision'),'action':action}) if self_report_action else None
        with self.repository.transaction() as conn:
            row=self.repository.submission(conn,principal['family_id'],identity,child=principal['child_id'],lock=True)
            item=self._item(conn,identity,item_id)
            if (data.get('itemRevision')!=item['revision']
                    or self_report_action and type(data.get('itemRevision')) is not int):
                raise ApiError('homework_revision_conflict','题目已更新，请刷新',409)
            result=self._student_ready(item,conn=conn,row=row)
            correction=parsed(item['correction_json'],{})
            if self_report_action:
                reference=reference_for_correction(result)
                if reference is None or reference['originalStatus']!='incorrect':
                    raise ApiError('homework_self_completion_unavailable','这道题还没核对清楚，暂不能标记完成',409)
                existing=conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=? AND idempotency_key=?',
                    (identity,item_id,key)).fetchone()
                if existing:
                    saved=parsed(existing['result_json'],{})
                    if (existing['request_sha256']!=request_hash
                            or saved.get('schemaVersion')!='mira.homework-self-reported-action.v1'):
                        raise ApiError('homework_idempotency_conflict','该操作编号已经使用',409)
                    if (saved.get('referenceDigest')!=reference['digest']
                            or saved.get('submissionRevision')!=row['revision']):
                        raise ApiError('homework_reference_changed','原题参考已更新，请刷新后重新操作',409)
                    # Read today's state, never reapply an old completion after
                    # a new answer or an explicit reopen.
                    return self._view(conn,row,student=True,include_paper_structure=True)
                now=self.clock()
                if action=='self_complete':
                    if correction_view(result,correction,item_revision=item['revision'])['correct'] is True:
                        raise ApiError('homework_already_corrected','这道题已经订正',409)
                    current=self_reported_completion(result,correction,item_revision=item['revision'])
                    if current is None:
                        correction['selfReportedCompletion']={
                            'schemaVersion':'mira.homework-self-reported-completion.v1',
                            'completed':True,'completedAt':now,'itemRevision':item['revision'],
                            'referenceDigest':reference['digest'],
                            'answerStateSha256':correction_answer_state(correction)}
                else:
                    # Only the child's task mark is reversible. Actual answers,
                    # reference checks and grading evidence remain untouched.
                    correction.pop('selfReportedCompletion',None)
                conn.execute('UPDATE homework_items SET correction_json=? WHERE id=?',(canonical(correction),item_id))
                receipt={'schemaVersion':'mira.homework-self-reported-action.v1','action':action,
                    'itemRevision':item['revision'],'submissionRevision':row['revision'],
                    'referenceDigest':reference['digest'],'createdAt':now,
                    'selfReportedCompleted':correction_view(result,correction,item_revision=item['revision'])['selfReportedCompleted']}
                conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                    ('hwa_'+uuid.uuid4().hex,identity,item_id,key,request_hash,canonical(receipt),now))
                return self._view(conn,row,student=True,include_paper_structure=True)
            correction[action+'Viewed']=True
            conn.execute('UPDATE homework_items SET correction_json=? WHERE id=?',(canonical(correction),item_id))
            return self._view(conn,row,student=True)

    def student_answer(self,token,identity,item_id,data):
        principal=self._student(token)
        key=identifier(data.get('idempotencyKey'))
        request_hash=digest({'itemRevision':data.get('itemRevision'),'answer':data.get('answer')})
        with self.repository.transaction() as conn:
            row=self.repository.submission(conn,principal['family_id'],identity,child=principal['child_id'],lock=True)
            item=self._item(conn,identity,item_id)
            if data.get('itemRevision')!=item['revision']:
                raise ApiError('homework_revision_conflict','题目已更新，请刷新',409)
            # A historical idempotent response must not bypass the current
            # answer gate or replay an obsolete student-visible reference.
            result=self._student_ready(item,conn=conn,row=row)
            existing=conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=? AND idempotency_key=?',(identity,item_id,key)).fetchone()
            if existing:
                if existing['request_sha256']!=request_hash:
                    raise ApiError('homework_idempotency_conflict','该作答编号已经使用',409)
                saved=parsed(existing['result_json'])
                active_reference=reference_for_correction(result) if result.get('method')=='tencent_question.v1' else None
                if active_reference and saved.get('_referenceDigest')!=active_reference['digest']:
                    raise ApiError('homework_reference_changed','原题参考已更新，请刷新后重新作答',409)
                return {**self._view(conn,row,student=True),'feedback':saved.get('feedback')}
            reference=reference_for_correction(result) if result.get('method')=='tencent_question.v1' else None
            if result.get('answerMode')=='spoken':
                evaluated=evaluate_response(data.get('answer'),reference) if reference else None
                if evaluated is None:
                    raise ApiError('homework_answer_unclear','这次答案还没听清，请只说这个空的答案再试一次',400)
                choice={'id':evaluated['normalizedAnswer'],'count':evaluated['normalizedAnswer']}
            elif result.get('answerMode')=='numeric':
                value=data.get('answer')
                if not isinstance(value,str) or not re.fullmatch(r'\d{1,10}(?:\.\d{1,12})?',value):
                    raise ApiError('homework_answer_invalid','请输入有效的计算结果',400)
                choice={'id':value,'count':value}
            else:
                choice=next((c for c in result['picture']['choices'] if c['id']==data.get('answer')),None)
                if choice is None:
                    raise ApiError('homework_answer_invalid','请点选一个有效答案图片',400)
            correction=parsed(item['correction_json'],{})
            if correction_view(result,correction,item_revision=item['revision'])['correct'] is True:
                raise ApiError('homework_already_corrected','这道题已经订正',409)
            correct=(evaluated['correct'] if result.get('answerMode')=='spoken' else
                Decimal(str(choice['count']))==Decimal(result['expectedAnswer']))
            attempt=int(correction.get('attempts',0))+1
            if attempt>10:
                raise ApiError('homework_attempt_limit','先听老师讲一讲，再休息一下',409)
            correction.pop('selfReportedCompletion',None)
            correction.update(attempts=attempt,correct=correct,lastChoice=choice['id'],lastAnswer=data.get('answer'),updatedAt=self.clock(),
                correctedAt=self.clock() if correct else None)
            if reference:
                correction.update(referenceDigest=reference['digest'],referenceAuthority=reference['authority'])
            conn.execute('UPDATE homework_items SET correction_json=? WHERE id=?',(canonical(correction),item_id))
            if self.evidence_enabled and row['source'] not in NON_ASSESSMENT_SOURCES:
                from services.learning_evidence_service import record_answer
                self._evidence(conn,row,item,result)
                record_answer(conn,family_id=row['family_id'],child_id=row['child_id'],source_kind='homework',source_id=identity,
                    event_key=f'{item_id}:{item["revision"]}:correction:{attempt}',question=evidence_question(row,item,result,reference) if reference else {'id':item_id,'version':str(item['revision']),
                        'subject':row['subject'],'gradeCode':row['grade_code'],'knowledgeId':result['knowledgeId'],
                        'knowledgeLabel':result['knowledgeLabel'],'prompt':result['prompt'],'correctAnswer':result['expectedAnswer'],'private':True},
                    answer=choice['count'],correct=correct,occurred_at=self.clock(),attempt=attempt+1 if reference else attempt,
                    hint_used=bool(correction.get('hintViewed') or correction.get('explanationViewed')),adult_help=None,independent=None,
                    confirmed=True,diagnosis={'scope':'same_question_correction','masteryClaim':False,
                        **({'referenceDigest':reference['digest'],'referenceAuthority':reference['authority']} if reference else {})})
            response={**self._view(conn,row,student=True),'feedback':{'correct':correct,'attempt':attempt,
                'scope':'same_question_correction','audioKind':'success' if correct else 'retry'}}
            saved_response={**response,**({'_referenceDigest':reference['digest']} if reference else {})}
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',('hwa_'+uuid.uuid4().hex,identity,item_id,key,request_hash,canonical(saved_response),self.clock()))
            return response

    def _is_student_ready(self,result,media):
        if result.get('answerMode')=='spoken':
            from services.homework_correction import speech_digest
            if any(media.get(kind,{}).get('textSha256')!=speech_digest(text)
                for kind,text in result.get('voiceTexts',{}).items()):
                return False
        if result.get('method')=='tencent_question.v1' and student_grading(result).get('status')!='incorrect':
            return False
        if not (result['status']=='incorrect' and result.get('answerMode') in {'picture_choice','numeric','spoken'}
            and set(result.get('voiceTexts',{}))=={'prompt','hint','explanation','success','retry'}
            and all(media.get(k,{}).get('status')=='ready' for k in result['voiceTexts'])):
            return False
        try:
            return all(hashlib.sha256(self.store.read(media[k]['storageKey'])).hexdigest()==media[k]['sha256'] for k in result['voiceTexts'])
        except (ApiError,KeyError,OSError):
            return False

    def _student_ready(self,item,*,conn=None,row=None):
        result=practice_result(self._learning_result(conn,row,item)) if conn is not None and row is not None else parsed(item['result_json'])
        media=parsed(item['media_json'],{})
        if result['status']!='incorrect' or not result.get('answerMode'):
            raise ApiError('homework_student_item_unsupported','这道题暂时没有适合的图片订正活动',409)
        if not self._is_student_ready(result,media):
            raise ApiError('homework_media_preparing','老师的图片语音活动正在准备',409)
        return result

    @staticmethod
    def _validation_bounds(row,*,pages=None,items=None):
        # This source is set only by the explicitly authorized local verification
        # helper, never by a create payload. Caps survive a normal worker restart.
        if row['source']=='paid_validation' and ((pages is not None and len(pages)!=1) or (items is not None and len(items)>1)):
            raise ApiError('homework_validation_scope_exceeded','链路验收仅允许一页一道题，已停止后续调用',409)

    def process_next(self,*,submission_id=None):
        self._enabled()
        self._processing_enabled()
        if submission_id is None:
            self.purge_files()
        now=self.clock()
        with self.repository.transaction() as conn:
            scope=' AND submission_id=?' if submission_id is not None else ''
            args=(submission_id,) if submission_id is not None else ()
            expired=conn.execute('SELECT * FROM homework_jobs WHERE status=? AND lease_until<?'+scope+' FOR UPDATE',('working',now)+args).fetchall()
            for job in expired:
                # A lease expiry never proves a paid HTTP request failed. Its call row decides.
                conn.execute('UPDATE homework_jobs SET status=?,lease_token=NULL,lease_until=NULL WHERE id=?',('queued',job['id']))
            job=conn.execute('SELECT * FROM homework_jobs WHERE status=? AND (stage<>? OR updated_at<=?)'+scope+' ORDER BY created_at,id LIMIT 1 FOR UPDATE',('queued','tencent_poll',now)+args).fetchone()
            if job is None:
                no_job=True
            else:
                no_job=False
            if no_job:
                pass
            else:
                lease=uuid.uuid4().hex
                conn.execute('UPDATE homework_jobs SET status=?,lease_token=?,lease_until=?,updated_at=? WHERE id=?',('working',lease,now+self.policy['leaseMilliseconds'],now,job['id']))
                row=conn.execute('SELECT * FROM homework_submissions WHERE id=?',(job['submission_id'],)).fetchone()
                if row is None or row['deleted_at'] is not None or row['revision']!=job['revision'] or row['source']=='synthetic_fixture':
                    conn.execute('UPDATE homework_jobs SET status=? WHERE id=?',('cancelled',job['id']))
                    return {'ok':True,'processed':True,'status':'cancelled'}
                pages=self.repository.pages(conn,row['id'])
        if no_job:
            return self.tutor.process_next(submission_id=submission_id)
        job=dict(job,lease_token=lease)
        try:
            self._validation_bounds(row,pages=pages)
            page_errors=[]
            if job['stage']!='media':
                for page in pages:
                    self._stage(job,'quality_check')
                    data,image=transformed_image(self.store.read(page['storage_key']),page['rotation'],parsed(page['crop_json']))
                    error=quality_error(image,self.policy)
                    if error:
                        with self.repository.transaction() as conn:
                            self._current(conn,job)
                            conn.execute('UPDATE homework_pages SET status=?,error_code=? WHERE id=?',('needs_confirmation',error,page['id']))
                        continue
                    self._stage(job,'recognizing')
                    try:
                        recognized=self._recognize(job,row,page,data)
                    except ApiError as error:
                        if error.code not in RECEIVED_RECOGNITION_ERRORS|{'homework_provider_unknown'}:
                            raise
                        with self.repository.transaction() as conn:
                            self._current(conn,job)
                            conn.execute('UPDATE homework_pages SET status=?,error_code=? WHERE id=?',
                                ('needs_confirmation',error.code,page['id']))
                        page_errors.append(error.code)
                        if error.code=='homework_provider_unknown':
                            # A missing external response stops further OCR,
                            # while already reliable pages can finish teaching.
                            break
                        continue
                    self._stage(job,'checking')
                    self._save_items(job,row,page,recognized)
            else:
                page_errors=[p['error_code'] for p in pages if p['error_code'] in RECEIVED_RECOGNITION_ERRORS|{'homework_provider_unknown'}]
            self._stage(job,'media_preparing',job_stage='media')
            self._prepare_media(job,row)
            with self.repository.transaction() as conn:
                row=self._current(conn,job)
                statuses=[parsed(item['result_json'])['status'] for item in self.repository.items(conn,row['id'])]
                page_pending=any(p['status']=='needs_confirmation' for p in self.repository.pages(conn,row['id']))
                error=page_errors[0] if page_errors else None
                status=('provider_unknown' if error=='homework_provider_unknown' else 'failed') if error and not statuses else 'needs_confirmation' if page_pending or 'pending' in statuses else 'ready'
                conn.execute('UPDATE homework_submissions SET status=?,error_code=?,updated_at=? WHERE id=?',(status,error,self.clock(),row['id']))
                conn.execute('UPDATE homework_jobs SET status=?,stage=?,error_code=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                    ('failed' if error else 'succeeded','recognizing' if error else 'done',error,self.clock(),job['id']))
            return {'ok':error is None,'processed':True,'submissionId':row['id'],'status':status,**({'error':error} if error else {})}
        except TencentPending as pending:
            with self.repository.transaction() as conn:
                row=self._current(conn,job)
                conn.execute('UPDATE homework_jobs SET status=?,stage=?,error_code=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',
                    ('queued','tencent_poll',pending.next_poll_at,job['id']))
                conn.execute('UPDATE homework_submissions SET status=?,error_code=NULL,updated_at=? WHERE id=?',('recognizing',self.clock(),row['id']))
            return {'ok':True,'processed':True,'submissionId':row['id'],'status':'queued','nextPollAt':pending.next_poll_at}
        except ApiError as error:
            with self.repository.transaction() as conn:
                fresh=conn.execute('SELECT * FROM homework_jobs WHERE id=? FOR UPDATE',(job['id'],)).fetchone()
                if fresh and fresh['lease_token']==lease and fresh['status']=='working':
                    state='provider_unknown' if error.code in {'homework_provider_unknown','homework_audio_unknown'} else 'media_preparing' if error.code.startswith('homework_audio') or error.code=='homework_media_pending' else 'failed'
                    conn.execute('UPDATE homework_jobs SET status=?,error_code=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?',('failed',error.code,self.clock(),job['id']))
                    conn.execute('UPDATE homework_submissions SET status=?,error_code=?,updated_at=? WHERE id=? AND revision=? AND deleted_at IS NULL',(state,error.code,self.clock(),row['id'],job['revision']))
            return {'ok':False,'processed':True,'submissionId':row['id'],'error':error.code}

    def _current(self,conn,job):
        scope=conn.execute('SELECT family_id,child_id FROM homework_submissions WHERE id=?',(job['submission_id'],)).fetchone()
        if scope:
            self.repository.child(conn,scope['family_id'],scope['child_id'],lock=True)
        row=conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE',(job['submission_id'],)).fetchone()
        latest=conn.execute('SELECT * FROM homework_jobs WHERE id=? FOR UPDATE',(job['id'],)).fetchone()
        if (latest is None or latest['status']!='working' or latest['lease_token']!=job['lease_token'] or row is None
                or row['deleted_at'] is not None or row['revision']!=job['revision']):
            raise ApiError('homework_job_superseded','作业分析已撤销或内容已变化',409)
        conn.execute('UPDATE homework_jobs SET lease_until=? WHERE id=?',(self.clock()+self.policy['leaseMilliseconds'],job['id']))
        return row

    def _stage(self,job,status,*,job_stage=None):
        with self.repository.transaction() as conn:
            row=self._current(conn,job)
            conn.execute('UPDATE homework_submissions SET status=?,updated_at=? WHERE id=?',(status,self.clock(),row['id']))
            conn.execute('UPDATE homework_jobs SET stage=?,updated_at=? WHERE id=?',(job_stage or status,self.clock(),job['id']))

    def _recognize(self,job,row,page,image):
        if getattr(self.provider,'is_tencent_grading',False) is True:
            return HomeworkTencentGrading(self).recognize(job,row,page,image)
        if self.provider is None or getattr(self.provider,'provider_name','') in {'unavailable','disabled','unconfigured'}:
            raise ApiError('homework_provider_unconfigured','作业识别模型尚未配置',503)
        if hasattr(self.provider,'api_key') and not self.provider.api_key:
            raise ApiError('homework_provider_unconfigured','作业识别模型尚未配置',503)
        provider=str(getattr(self.provider,'provider_name','unknown'))
        model=str(getattr(self.provider,'model_name','unknown'))
        spec=self.policy['recognitionPrompt']
        prompt=self.prompts.get_prompt(spec['id'],spec['version'])
        if prompt is None:
            raise ApiError('homework_prompt_missing','作业分析策略尚未配置',503)
        sha=digest({'image':hashlib.sha256(image).hexdigest(),'prompt':prompt.body,'policy':self.policy,'provider':provider,'model':model})
        identity='hwcall_'+digest([row['id'],page['id'],sha])[:56]
        now=self.clock()
        resume_call=None
        with self.repository.transaction() as conn:
            row=self._current(conn,job)
            repair=self._recognition_repair_grant(conn,job,row,page,image)
            if repair is None:
                from services.homework_reupload_authorization import reupload_grant
                repair=reupload_grant(self,conn,job,row,page,image,sha)
            repair_receipt={}
            if repair:
                # Only this audited job gets a different request identity. The
                # original unknown hash and receipt remain untouched forever.
                sha=digest({'baseRequestSha256':sha,'operatorRepair':repair['id'],
                    'authorizationSha256':repair['sha256'],'wire':repair['wire']})
                identity='hwcall_'+digest([row['id'],page['id'],sha])[:56]
                repair_receipt={'operatorRepairAuthorizationId':repair['id'],
                    'authorizationSha256':repair['sha256'],'wireContract':repair.get('wireContract',RECOGNITION_REPAIR_CONTRACT),
                    'wireImageSha256':repair['wire']['imageSha256'],'maximumNewVisionCalls':repair.get('maximumNewVisionCalls',1)}
            maximum_calls=1 if row['source']=='paid_validation' else self.policy['maxProviderCallsPerSubmission']
            call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE',(identity,)).fetchone()
            if call:
                if call['status']=='succeeded':
                    return parsed(call['result_json'])
                receipt=parsed(call['receipt_json'],{})
                if not receipt.get('receivedResponse'):
                    receipt=self._recover_recognition_link(conn,job,row,page,call,receipt)
                    call=dict(call,receipt_json=canonical(receipt))
                if receipt.get('receivedResponse'):
                    # A received response can be parsed again locally after a
                    # crash or parser repair. This path never calls a provider.
                    resume_call=dict(call)
                else:
                    raise ApiError('homework_provider_unknown','此前识别请求的结果需要核对，不会重复调用',409)
            if resume_call is None:
                if repair and self.clock()>=repair['expiresAt']:
                    raise ApiError('homework_repair_authorization_expired','单次修复授权已过期，未发出新的识别请求',409)
                cached=conn.execute('SELECT c.* FROM homework_provider_calls c JOIN homework_submissions s ON s.id=c.submission_id WHERE c.child_id=? AND s.family_id=? AND s.deleted_at IS NULL AND c.request_sha256=? AND c.status=? LIMIT 1',(row['child_id'],row['family_id'],sha,'succeeded')).fetchone()
                ambiguous=conn.execute('SELECT c.id FROM homework_provider_calls c JOIN homework_submissions s ON s.id=c.submission_id WHERE c.child_id=? AND s.family_id=? AND c.request_sha256=? AND c.status IN (?,?) LIMIT 1',(row['child_id'],row['family_id'],sha,'dispatched','unknown')).fetchone()
                if not cached and ambiguous:
                    raise ApiError('homework_provider_unknown','这张作业图片此前的识别结果仍待核对，不会再次调用',409)
                invalid=conn.execute('SELECT c.error_code FROM homework_provider_calls c JOIN homework_submissions s ON s.id=c.submission_id WHERE c.child_id=? AND s.family_id=? AND s.deleted_at IS NULL AND c.request_sha256=? AND c.status=? LIMIT 1',(row['child_id'],row['family_id'],sha,'returned_invalid')).fetchone()
                if not cached and invalid:
                    raise ApiError(invalid['error_code'] or 'homework_recognition_invalid_schema','这张图片已有待处理的识别响应，无需重复提交',409)
                count=conn.execute('SELECT COUNT(*) AS n FROM homework_provider_calls WHERE submission_id=?',(row['id'],)).fetchone()['n']
                if not cached and count>=maximum_calls:
                    raise ApiError('homework_budget_exceeded','这份作业已达到分析次数上限',409)
                conn.execute('INSERT INTO homework_provider_calls (id,submission_id,page_id,child_id,request_sha256,status,provider,model,prompt_version,result_json,receipt_json,dispatched_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (identity,row['id'],page['id'],row['child_id'],sha,'succeeded' if cached else 'dispatched',provider,model,spec['version'],cached['result_json'] if cached else None,canonical({'reusedFrom':cached['id'],**repair_receipt}) if cached else canonical({'responseJournalKey':self.store.response_key('homework-vision-response:'+identity),'maximumImages':1,'maximumOutputTokens':7000,'inputImageBytes':len(image),'inputTextCharacters':len(prompt.body)+len(self.policy['systemPrompt']),**repair_receipt}),None if cached else now,now,now))
                if cached:
                    return parsed(cached['result_json'])
        if resume_call is not None:
            return self._materialize_recognition_response(job,row,page,resume_call)
        # Exactly one dispatch after a durable reservation. Only a missing
        # transport response is ambiguous; parsing a returned body is local.
        try:
            response=self.provider.analyze_image(system_prompt=self.policy['systemPrompt'],user_prompt=prompt.body,image_bytes=image,
                content_type='image/png',max_tokens=7000,temperature=0.0)
            if response is None:
                raise ValueError('empty response')
        except Exception:
            with self.repository.transaction() as conn:
                conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status=?',('unknown','homework_provider_unknown',self.clock(),identity,'dispatched'))
            raise ApiError('homework_provider_unknown','识别结果尚未确认，已保留请求记录，不会重复计费',409)
        self._save_recognition_response(job,row,page,identity,response,request_sha=sha)
        with self.repository.transaction() as conn:
            call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=?',(identity,)).fetchone()
        return self._materialize_recognition_response(job,row,page,call)

    def _save_recognition_response(self,job,row,page,identity,response,*,request_sha):
        """Save private returned bytes before inspecting their JSON or fields."""
        envelope=getattr(response,'raw_response',None)
        saved={'schemaVersion':RECOGNITION_RESPONSE_SCHEMA,'callId':identity,
            'submissionId':row['id'],'pageId':page['id'],'childId':row['child_id'],
            'analysisRevision':job['revision'],'requestSha256':request_sha,'text':response.text,
            'finishReason':getattr(response,'finish_reason',None),
            'responseError':getattr(response,'response_error',None),
            'requestId':getattr(response,'request_id',None),
            'providerUsage':getattr(response,'usage',None),
            'responseEnvelopeBase64':base64.b64encode(envelope).decode() if isinstance(envelope,bytes) else None}
        key=None
        try:
            data=canonical(saved).encode()
            if len(data)>RECOGNITION_RESPONSE_MAX_BYTES:
                raise ValueError('bounded response exceeded')
            key=self.store.put_response(data,namespace='homework-vision-response:'+identity)
            with self.repository.transaction() as conn:
                self._current(conn,job)
                call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE',(identity,)).fetchone()
                if not call or call['status']!='dispatched':
                    raise ApiError('homework_job_superseded','识别任务已更新',409)
                receipt=parsed(call['receipt_json'],{})
                receipt.update(responseReceived=True,receivedResponse={'schemaVersion':RECOGNITION_RESPONSE_SCHEMA,
                    'storageKey':key,'sha256':hashlib.sha256(data).hexdigest(),
                    'requestSha256':call['request_sha256']},finishReason=saved['finishReason'],
                    providerRequestId=saved['requestId'],usage={'providerBilledTokens':(saved['providerUsage'] or {}).get('total_tokens'),
                        'providerCost':None,'providerUsageAvailable':bool(saved['providerUsage']),
                        'providerUsage':saved['providerUsage'],'outputCharacters':len(response.text),
                        **{k:receipt.get(k) for k in ('inputImageBytes','inputTextCharacters','maximumOutputTokens')}})
                conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=?',(canonical(receipt),self.clock(),identity))
        except Exception as error:
            with self.repository.transaction() as conn:
                if key and isinstance(error,ApiError) and error.code=='homework_job_superseded':
                    self._enqueue_delete(conn,key)
                if not isinstance(error,ApiError) or error.code!='homework_job_superseded':
                    conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status=?',('unknown','homework_recognition_storage_failed',self.clock(),identity,'dispatched'))
            if isinstance(error,ApiError) and error.code=='homework_job_superseded':
                raise
            raise ApiError('homework_recognition_storage_failed','识别响应保存失败，照片仍在，不会重复调用',409)

    def _recover_recognition_link(self,conn,job,row,page,call,receipt):
        """Replay a scoped private journal after a database-link interruption."""
        key=self.store.response_key('homework-vision-response:'+call['id'])
        try:
            data=self.store.read(key)
        except ApiError as error:
            if error.code=='homework_asset_missing':
                return receipt
            raise
        try:
            saved=json.loads(data)
            if len(data)>RECOGNITION_RESPONSE_MAX_BYTES or any(saved.get(k)!=v for k,v in {
                'schemaVersion':RECOGNITION_RESPONSE_SCHEMA,'callId':call['id'],'submissionId':row['id'],
                'pageId':page['id'],'childId':row['child_id'],'analysisRevision':job['revision'],
                'requestSha256':call['request_sha256']}.items()):
                raise ValueError('invalid journal scope')
        except Exception:
            raise ApiError('homework_recognition_storage_failed','保存的识别响应校验失败，未重复调用',409)
        receipt.update(responseReceived=True,receivedResponse={'schemaVersion':RECOGNITION_RESPONSE_SCHEMA,
            'storageKey':key,'sha256':hashlib.sha256(data).hexdigest(),'requestSha256':call['request_sha256']},
            recoveredDatabaseLink=True,finishReason=saved.get('finishReason'))
        conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=? AND status!=?',
            (canonical(receipt),self.clock(),call['id'],'deleted'))
        return receipt

    def _materialize_recognition_response(self,job,row,page,call):
        """Validate and parse only saved data, including after worker recovery."""
        receipt=parsed(call['receipt_json'],{})
        reference=receipt.get('receivedResponse',{})
        reason=None
        try:
            data=self.store.read(reference['storageKey'])
            if (len(data)>RECOGNITION_RESPONSE_MAX_BYTES or hashlib.sha256(data).hexdigest()!=reference.get('sha256')
                    or reference.get('schemaVersion')!=RECOGNITION_RESPONSE_SCHEMA
                    or reference.get('requestSha256')!=call['request_sha256']):
                raise ValueError('invalid saved reference')
            saved=json.loads(data)
            if any(saved.get(k)!=v for k,v in {'schemaVersion':RECOGNITION_RESPONSE_SCHEMA,'callId':call['id'],
                'submissionId':row['id'],'pageId':page['id'],'childId':row['child_id'],'analysisRevision':job['revision']}.items()):
                raise ValueError('invalid saved scope')
        except Exception:
            reason='homework_recognition_storage_failed'
        if reason is None:
            response_error=saved.get('responseError')
            if saved.get('finishReason')=='length' or response_error=='response_too_large':
                reason='homework_recognition_truncated'
            elif response_error:
                reason='homework_recognition_invalid_json' if response_error=='response_invalid_json' else 'homework_recognition_invalid_schema'
            else:
                try:
                    maximum=1 if row['source']=='paid_validation' else self.policy['maxItemsPerPage']
                    # Recovery parses the original receipt's contract. A new
                    # deployment must not apply v3 requirements to paid v1/v2
                    # responses that are already saved and await local repair.
                    source_version=call['prompt_version']
                    value,diagnostics=parse_recognition_response(saved['text'],maximum_items=maximum,
                        maximum_answer_characters=1000 if source_version in {'v2','v3'} else 160,
                        require_source_evidence=source_version=='v3')
                except RecognitionParseError as error:
                    reason='homework_recognition_'+error.reason
        if reason:
            with self.repository.transaction() as conn:
                self._current(conn,job)
                receipt.update(responseReceived=True,parseError=reason)
                conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,receipt_json=?,updated_at=? WHERE id=? AND status!=?',('returned_invalid',reason,canonical(receipt),self.clock(),call['id'],'deleted'))
            raise ApiError(reason,'识别响应需要处理，照片和返回内容已保存，无需重新上传',409)
        with self.repository.transaction() as conn:
            self._current(conn,job)
            receipt.update(resultSha256=digest(value),parserDiagnostics=diagnostics)
            receipt.pop('parseError',None)
            conn.execute('UPDATE homework_provider_calls SET status=?,error_code=NULL,result_json=?,receipt_json=?,updated_at=? WHERE id=?',('succeeded',canonical(value),canonical(receipt),self.clock(),call['id']))
        return value

    def _save_items(self,job,row,page,recognized):
        now=self.clock()
        with self.repository.transaction() as conn:
            row=self._current(conn,job)
            self._validation_bounds(row,items=recognized['items'])
            for order,raw in enumerate(recognized['items']):
                item_id='hwi_'+digest([row['id'],job['revision'],page['id'],page['content_sha256'],page['rotation'],parsed(page['crop_json']),order])[:56]
                existing=conn.execute('SELECT id FROM homework_items WHERE id=?',(item_id,)).fetchone()
                if existing:
                    continue
                result=raw if recognized.get('schemaVersion')=='mira.homework-tencent-normalized.v1' else check_item(raw,grade=row['grade_code'],subject=row['subject'],policy=self.policy)
                conn.execute('INSERT INTO homework_items (id,submission_id,page_id,revision,analysis_revision,item_order,result_json,media_json,correction_json,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (item_id,row['id'],page['id'],1,job['revision'],order,canonical(result),'{}','{}',now))
                conn.execute('INSERT INTO homework_item_revisions (item_id,revision,submission_id,result_json,reason,created_at) VALUES (?,?,?,?,?,?)',(item_id,1,row['id'],canonical(result),'recognition',now))
                self._evidence(conn,row,self._item(conn,row['id'],item_id),result)
            # Multi-answer positioning can be checked only after every sibling
            # is saved. The second pass is idempotent and never calls a model.
            for saved in self.repository.items(conn,row['id']):
                if saved['page_id']==page['id']:
                    self._evidence(conn,row,saved,parsed(saved['result_json']))
            readable=bool(recognized['pageReadable'] and recognized['items'])
            untrusted=any(raw.get('recognitionNeedsConfirmation') is True for raw in recognized['items'])
            conn.execute('UPDATE homework_pages SET status=?,error_code=? WHERE id=?',
                ('ready' if readable and not untrusted else 'needs_confirmation',
                    'recognition_fields_need_confirmation' if untrusted else None if readable else 'recognition_unreadable',page['id']))

    def _prepare_media(self,job,row):
        with self.repository.transaction() as conn:
            row=self._current(conn,job)
            items=self.repository.items(conn,row['id'])
            self._validation_bounds(row,items=items)
        for item in items:
            with self.repository.transaction() as conn:
                self._current(conn,job)
                result=practice_result(self._learning_result(conn,row,item))
            if result['status']!='incorrect' or not result.get('answerMode'):
                continue
            if self.audio is None:
                raise ApiError('homework_audio_unconfigured','老师语音服务尚未配置',503)
            for kind,text in result['voiceTexts'].items():
                with self.repository.transaction() as conn:
                    self._current(conn,job)
                    current=self._item(conn,row['id'],item['id'])
                    if current['revision']!=item['revision']:
                        raise ApiError('homework_job_superseded','题目已更新',409)
                    media=parsed(current['media_json'],{})
                    if media.get(kind,{}).get('status')=='ready':
                        clip=media[kind]
                        try:
                            valid=hashlib.sha256(self.store.read(clip['storageKey'])).hexdigest()==clip['sha256']
                        except (ApiError,KeyError,OSError):
                            valid=False
                        if not valid:
                            raise ApiError('homework_audio_missing','已保存的老师语音缺失或校验失败，不会重新计费生成',409)
                        from services.homework_correction import speech_digest
                        if result.get('answerMode')!='spoken' or clip.get('textSha256')==speech_digest(text):
                            continue
                request_id='hwaudio_'+digest([row['id'],item['id'],item['revision'],kind,text])[:56]
                receipt=self.audio.ensure(request_id=request_id,text=text,subject=row['subject'],submission_id=row['id'],item_id=item['id'],revision=item['revision'])
                if receipt.get('status')!='ready':
                    raise ApiError('homework_media_pending','老师语音正在准备',409)
                with self.repository.transaction() as conn:
                    self._current(conn,job)
                    current=self._item(conn,row['id'],item['id'])
                    if current['revision']!=item['revision']:
                        raise ApiError('homework_job_superseded','题目已更新',409)
                    media=parsed(current['media_json'],{})
                    from services.homework_correction import speech_digest
                    media[kind]={**receipt,'textSha256':speech_digest(text)}
                    conn.execute('UPDATE homework_items SET media_json=? WHERE id=?',(canonical(media),item['id']))

    def review_question_pool(self,conn,child):
        """Private, already materialized original questions; no generation on read."""
        if not self.enabled or not self.evidence_enabled:
            return [],[]
        from services.learning_evidence_service import event_id
        rows=conn.execute('''SELECT i.*,s.subject,s.grade_code,s.title FROM homework_items i
            JOIN homework_submissions s ON s.id=i.submission_id
            WHERE s.family_id=? AND s.child_id=? AND s.deleted_at IS NULL AND s.grade_code=?''',
            (child['family_id'],child['id'],child['grade_code'])).fetchall()
        questions,gaps=[],[]
        for item in rows:
            source=self.repository.submission(conn,child['family_id'],item['submission_id'],child=child['id'])
            result=practice_result(self._learning_result(conn,source,item))
            media=parsed(item['media_json'],{})
            source_event_id=event_id(child['family_id'],child['id'],'homework',item['submission_id'],f"{item['id']}:{item['revision']}")
            evidence=conn.execute('SELECT id FROM learning_answer_events WHERE id=? AND revoked_at IS NULL AND confirmed=1 AND correct=0',(source_event_id,)).fetchone()
            if evidence is None or result['status']!='incorrect':
                continue
            if not self._is_student_ready(result,media):
                gaps.append(item['title'])
                continue
            try:
                for clip in media.values():
                    if hashlib.sha256(self.store.read(clip['storageKey'])).hexdigest()!=clip['sha256']:
                        raise ValueError('asset invalid')
            except (ApiError,ValueError):
                gaps.append(item['title'])
                continue
            def asset(kind):
                return f"homework.{item['submission_id']}.{item['id']}.{item['revision']}.{kind}"
            if result.get('answerMode')=='spoken':
                reference=reference_for_correction(result)
                page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',(item['page_id'],item['submission_id'])).fetchone()
                if reference is None or page is None:
                    gaps.append(item['title']);continue
                (width,height),_=transformed_geometry(page['width'],page['height'],page['rotation'],parsed(page['crop_json']))
                question={'id':item['id'],'version':str(item['revision']),'renderer':'homework_original',
                    'subject':item['subject'],'gradeCode':item['grade_code'],'knowledgeId':result['knowledgeId'],
                    'knowledgeLabel':result['knowledgeLabel'],'courseId':None,'courseVersion':None,'courseTitle':item['title'],
                    'prompt':'看原图，自己说出圈出的空的答案',
                    'visual':{'kind':'homework_original','submissionId':item['submission_id'],'pageId':item['page_id'],
                        'width':width,'height':height,'region':result.get('region'),
                        'answerRegion':(result.get('providerAssessment') or {}).get('answerRegion')},
                    'homeworkSource':{'submissionId':item['submission_id'],'itemId':item['id'],'itemRevision':item['revision']},
                    'options':[],'correctAnswer':reference['canonicalExpectedAnswer'],
                    'hints':[result['hint']],'explanation':reference['analysis'],'promptAudioAsset':asset('prompt'),
                    'hintAudioAssets':[asset('hint')],'explanationAudioAsset':asset('explanation'),
                    'estimatedSeconds':90,'approved':True,'private':True,'evidenceMode':'repeated_practice',
                    'sourceEventId':source_event_id,'sourceSubmissionId':item['submission_id'],'sourceItemId':item['id'],
                    'sourceRevision':item['revision'],'referenceDigest':reference['digest']}
                question['fingerprint']=digest({k:question[k] for k in ('knowledgeId','prompt','options','correctAnswer','visual')})
                questions.append(question);continue
            if result.get('answerMode')!='picture_choice':
                gaps.append(item['title']);continue
            options=[{'value':c['id'],'label':str(c['count']),'picture':{'count':c['count']}} for c in result['picture']['choices']]
            question={'id':item['id'],'version':str(item['revision']),'renderer':'quantity_arithmetic',
                'subject':item['subject'],'gradeCode':item['grade_code'],'knowledgeId':result['knowledgeId'],
                'knowledgeLabel':result['knowledgeLabel'],'courseId':None,'courseVersion':None,'courseTitle':item['title'],
                'prompt':result['prompt'],'visual':result['picture'],'options':options,'correctAnswer':'n'+result['expectedAnswer'],
                'hints':[result['hint']],'explanation':result['explanation'],'promptAudioAsset':asset('prompt'),
                'hintAudioAssets':[asset('hint')],'explanationAudioAsset':asset('explanation'),
                'estimatedSeconds':60,'approved':True,'private':True,'evidenceMode':'repeated_practice',
                'sourceEventId':source_event_id,'sourceSubmissionId':item['submission_id'],'sourceItemId':item['id'],'sourceRevision':item['revision']}
            question['fingerprint']=digest({k:question[k] for k in ('knowledgeId','prompt','options','correctAnswer','visual')})
            questions.append(question)
        return questions,sorted(set(gaps))

    def review_source_alive(self,conn,child,question):
        if not self.enabled:
            return False
        row=conn.execute('''SELECT i.* FROM homework_items i JOIN homework_submissions s ON s.id=i.submission_id
            WHERE s.family_id=? AND s.child_id=? AND s.deleted_at IS NULL AND s.id=? AND i.id=? AND i.revision=?''',
            (child['family_id'],child['id'],question.get('sourceSubmissionId'),question.get('sourceItemId'),question.get('sourceRevision'))).fetchone()
        if row is None:
            return False
        source=self.repository.submission(conn,child['family_id'],question['sourceSubmissionId'],child=child['id'])
        result=practice_result(self._learning_result(conn,source,row))
        reference=reference_for_correction(result)
        return bool(self._is_student_ready(result,parsed(row['media_json'],{}))
            and (question.get('referenceDigest') is None or reference and reference['digest']==question['referenceDigest']))

    def review_audio_file(self,asset_id):
        """Caller must first authorize child/run and validate current source ownership."""
        match=re.fullmatch(r'homework\.(hw_[a-f0-9]{32})\.(hwi_[a-f0-9]{56})\.(\d+)\.(prompt|hint|explanation)',asset_id)
        if not match:
            raise ApiError('homework_audio_not_found','复习语音不存在',404)
        submission_id,item_id,version,kind=match.groups()
        with self.repository.transaction() as conn:
            row=conn.execute('''SELECT i.media_json FROM homework_items i JOIN homework_submissions s ON s.id=i.submission_id
                WHERE s.id=? AND i.id=? AND i.revision=? AND s.deleted_at IS NULL''',(submission_id,item_id,int(version))).fetchone()
            media=parsed(row['media_json'],{}).get(kind) if row else None
            if not media or media.get('status')!='ready':
                raise ApiError('homework_audio_not_found','复习语音已撤回',404)
            # Existing review audio routes use send_file(Path); never expose this private path in JSON.
            if hashlib.sha256(self.store.read(media['storageKey'])).hexdigest()!=media['sha256']:
                raise ApiError('homework_audio_missing','复习音频校验失败',409)
            return self.store._path(media['storageKey'])
