#!/usr/bin/env python3
"""Bounded, explicitly authorized local paid homework validation.

Default is a read-only preflight. --execute-paid-validation creates one original
page through the normal owned homework service and processes only that record.
The trusted paid_validation source prevents simulated answers entering growth.
No credentials, PINs, devices, environment files or old homework are changed.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stdout, redirect_stderr
from copy import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]

from PIL import Image,ImageDraw
from core.database import Database
from core.errors import ApiError
from dev_homework_sample import _font
from seed_existing_student_demo import scoped_rows
from services.homework_service import digest,parsed
from services.service_factory import homework_service
from setup_grade6_student_smoke import local_parent_app

PHONE='13860469696'
CHILD='child_6d57c9cfd92f4b29b2438cf6d9f42f51'
FAMILY='fam_0f796fdf858543069216ab17b523f8c3'
TITLE='付费链路验收（模拟作答）'
SOURCE='paid_validation'
KEY='paid-homework-validation-v1:'+CHILD
SCHEMA='mira.paid-homework-validation.v1'


def original_page():
    """A fresh original source page, not provider output or seeded recognition."""
    page=Image.new('RGB',(1200,1500),'white');draw=ImageDraw.Draw(page)
    draw.text((100,95),'数学 · 一年级',font=_font(52),fill='#202020')
    draw.text((100,210),'链路验收：以下为模拟作答，不是真实成绩',font=_font(30),fill='#404040')
    draw.line((100,295,1100,295),fill='#777777',width=3)
    draw.text((155,540),'1 + 2 = 4',font=_font(132),fill='#111111')
    draw.line((100,875,1100,875),fill='#777777',width=3)
    draw.text((100,1035),'原创测试题 · 无姓名及学校信息',font=_font(34),fill='#404040')
    output=io.BytesIO();page.save(output,format='PNG');return output.getvalue()


def validate_config(config):
    url=urlparse(config['DATABASE_URL'])
    if (config.get('APP_ENV')!='development' or url.scheme.split('+',1)[0]!='mysql'
            or url.hostname not in {'127.0.0.1','localhost'} or url.path!='/ai_camera_app_dev'):
        raise ValueError('Only exact localhost ai_camera_app_dev is allowed')
    if config.get('HOMEWORK_WORKER_ENABLED'):
        raise ValueError('Pause the shared homework worker before this bounded validation')
    if not config.get('HOMEWORK_ANALYSIS_ENABLED') or not config.get('HOMEWORK_AUDIO_ENABLED'):
        raise ValueError('Real homework analysis and Qwen audio must be configured first')
    runtime=urlparse(config.get('HOMEWORK_TTS_RUNTIME_URL') or '')
    if runtime.hostname not in {'127.0.0.1','localhost'} or runtime.scheme!='http':
        raise ValueError('A local private native TTS runtime is required')
    if not config.get('INTERNAL_API_TOKEN'):
        raise ValueError('The private native budget transport is not configured')


def normalize_prompt_root(config):
    path=Path(config['PROMPT_ROOT'])
    if not path.is_absolute():
        config['PROMPT_ROOT']=str((ROOT/path).resolve())


def authorized_service(database,service,*,phone,child_id):
    if phone!=PHONE or child_id!=CHILD:
        raise ValueError('Exact human-authorized phone and child are required')
    with database.transaction() as conn:
        user=conn.execute('SELECT id,phone,family_id FROM users WHERE phone=?',(phone,)).fetchone()
        child=conn.execute('SELECT * FROM children WHERE id=? AND family_id=?',(child_id,FAMILY)).fetchone()
        if not user or user['family_id']!=FAMILY or not child or child['name']!='阿一' or child['grade_code']!='primary_1':
            raise ValueError('Authorized existing identity changed; refusing to proceed')
        if not conn.execute('SELECT id FROM family_members WHERE family_id=? AND user_id=?',(FAMILY,user['id'])).fetchone():
            raise ValueError('Existing family membership is required')
        context={'user':dict(user),'family':{'id':FAMILY}}
        # Keep the real role/capability decision. This local sentinel is never a
        # network access token and is only accepted by this private service copy.
        service.profile._assert_capability(conn,context,'manage_tasks')
    scoped=copy(service);scoped.profile=copy(service.profile)
    token='local-paid-validation:'+digest([KEY,user['id']])
    def auth(value):
        if value!=token:raise ApiError('unauthorized','无效的本地验收范围',401)
        return context
    scoped.profile._auth_context=auth
    scoped.processing_enabled=True
    return scoped,token


def prepare_submission(database,service,token):
    """Atomically mark only this new record trusted; reuse its stable key."""
    with database.transaction() as conn:
        service.repository.child(conn,FAMILY,CHILD,lock=True)
        existing=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND child_id=? AND idempotency_key=?',(FAMILY,CHILD,KEY)).fetchone()
        if existing:
            if existing['source']!=SOURCE or existing['title']!=TITLE or existing['deleted_at'] is not None:
                raise ValueError('Existing validation identity is incompatible; no new dispatch')
            return existing['id']
        local=copy(service);local.repository=copy(service.repository)
        local.repository.transaction=lambda:nullcontext(conn)
        result=local.create(token,CHILD,{'idempotencyKey':KEY,'subject':'math','analysisConsent':True,'title':TITLE})['submission']
        conn.execute('UPDATE homework_submissions SET source=? WHERE id=? AND family_id=?',(SOURCE,result['id'],FAMILY))
        return result['id']


def safe_receipts(database,service,identity):
    with database.transaction() as conn:
        calls=[{'id':r['id'],'status':r['status'],'provider':r['provider'],'model':r['model'],
                'dispatched':r['dispatched_at'] is not None,'receipt':parsed(r['receipt_json'],{})}
               for r in conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=?',(identity,)).fetchall()]
        audio=[]
        for row in conn.execute('SELECT * FROM homework_audio_receipts WHERE submission_id=?',(identity,)).fetchall():
            clip=parsed(row['result_json'],{})
            body=service.store.read(clip['storageKey']) if clip.get('status')=='ready' else None
            audio.append({'id':row['id'],'status':row['status'],'characters':row['character_count'],
                'providerId':clip.get('providerId'),'modelId':clip.get('modelId'),'voiceId':clip.get('voiceId'),
                'sha256':clip.get('sha256'),'bytes':len(body) if body is not None else 0,
                'hashVerified':body is not None and hashlib.sha256(body).hexdigest()==clip['sha256']})
        jobs=[dict(r) for r in conn.execute('SELECT id,revision,status,stage,error_code FROM homework_jobs WHERE submission_id=?',(identity,)).fetchall()]
    return {'vision':calls,'audio':audio,'jobs':jobs}


def protected_rows(conn,identity):
    """Exclude only this owned validation; compare all original scoped data."""
    rows=scoped_rows(conn,FAMILY)
    for table in ('homework_submissions','homework_pages','homework_items','homework_item_revisions',
                  'homework_actions','homework_jobs','homework_provider_calls','homework_audio_receipts'):
        column='id' if table=='homework_submissions' else 'submission_id'
        for record in conn.execute(f'SELECT * FROM {table} WHERE {column}=?',(identity,)).fetchall():
            rows[table].subtract({digest(dict(record)):1})
        rows[table]=+rows[table]
    return rows


def execute(database,service,token,save):
    identity=prepare_submission(database,service,token)
    with database.transaction() as conn:
        before=protected_rows(conn,identity)
    report={'schemaVersion':SCHEMA,'submissionId':identity,'title':TITLE,'source':SOURCE,
        'childId':CHILD,'gradeCode':'primary_1','maximumVisionDispatches':1,'maximumTeacherClips':5,
        'maximumItems':1,'assessmentExcluded':True,'phase':'created'}
    save(report)
    current=service.get(token,identity)['submission']
    if not current['pages']:
        if current['revision']!=1 or current['status']!='received':
            raise ValueError('Validation page was edited; automatic replacement is forbidden')
        current=service.upload(token,identity,{'revision':current['revision'],'idempotencyKey':'original-page-v1'},original_page())['submission']
    if len(current['pages'])!=1:
        raise ValueError('Validation must contain exactly one page')
    page=current['pages'][0]
    original=service.image(token,identity,page['id'],original=True)[0]
    if page['rotation']!=0 or page['crop'] is not None or hashlib.sha256(original).digest()!=hashlib.sha256(original_page()).digest():
        raise ValueError('The validation original was changed; no automatic analysis')
    prior=safe_receipts(database,service,identity)
    if any(r['status'] in {'unknown','dispatched'} for r in prior['vision']+prior['audio']):
        report.update(phase='unknown_no_retry',receipts=prior);save(report);return report
    if current['status'] not in {'ready','needs_confirmation'}:
        service.analyze(token,identity,{'revision':current['revision']})
        report.update(phase='queued');save(report)
        report['worker']=service.process_next(submission_id=identity)
    current=service.get(token,identity)['submission']
    receipts=safe_receipts(database,service,identity)
    with database.transaction() as conn:
        after=protected_rows(conn,identity)
        new_events=conn.execute('SELECT COUNT(*) n FROM learning_answer_events WHERE source_kind=? AND source_id=?',('homework',identity)).fetchone()['n']
    report.update(phase='finished',status=current['status'],error=current['error'],
        readyForStudent=current['readyForStudent'],summary=current['summary'],receipts=receipts,
        originalPageSha256=hashlib.sha256(original_page()).hexdigest(),
        studentPath='/learning/homework/'+identity,parentPath='/learning-center/homework/'+identity,
        items=[{'id':i['id'],'status':i['status'],'prompt':i['prompt'],'recognizedAnswer':i.get('studentAnswer'),
            'confidence':i['confidence'],'recognitionConfirmed':i['recognitionConfirmed'],
            'picture':i.get('picture'),'readyForStudent':i['readyForStudent'],'voiceKinds':list(i.get('voice',{}))}
               for i in current['items']],
        realEvidenceCreated=new_events,studentAnswersSubmitted=0,
        originalUnrelatedRowsUnchanged=before==after,
        realAnswerEventsUnchanged=before['learning_answer_events']==after['learning_answer_events'])
    if (sum(c['dispatched'] for c in receipts['vision'])>1 or len(receipts['audio'])>5 or len(current['items'])>1 or new_events or before!=after):
        report['phase']='invariant_failed';save(report);raise ValueError('Bounded validation invariant failed; no retries')
    save(report);return report


def save_json(path,value):
    temporary=path.with_suffix('.pending')
    fd=os.open(temporary,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,ensure_ascii=False,indent=2)
    os.replace(temporary,path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone',required=True,choices=[PHONE])
    parser.add_argument('--child-id',required=True,choices=[CHILD])
    parser.add_argument('--output',required=True)
    parser.add_argument('--execute-paid-validation',action='store_true')
    args=parser.parse_args()
    output=Path(args.output).resolve()
    if output.suffix!='.json' or output.exists():raise ValueError('Use a new JSON evidence path')
    with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
        app=local_parent_app();validate_config(app.config);normalize_prompt_root(app.config);app.config['TESTING']=True
        database=Database(app.config['DATABASE_URL'])
        with app.app_context():
            service,token=authorized_service(database,homework_service(),phone=args.phone,child_id=args.child_id)
            if (getattr(service.provider,'provider_name','unavailable') in {'unavailable','disabled','unconfigured'}
                    or not getattr(service.provider,'api_key','') or service.audio is None
                    or not service.audio.enabled or service.audio.budget is None):
                raise ValueError('A real configured vision provider and budgeted teacher audio are required')
            prompt=service.policy['recognitionPrompt']
            if service.prompts.get_prompt(prompt['id'],prompt['version']) is None:
                raise ValueError('The versioned homework recognition prompt is missing')
            if not args.execute_paid_validation:
                with database.transaction() as conn:
                    queue=[dict(row) for row in conn.execute('SELECT j.status,COUNT(*) AS count FROM homework_jobs j JOIN homework_submissions s ON s.id=j.submission_id WHERE s.family_id=? AND j.status IN (?,?) GROUP BY j.status',(FAMILY,'queued','working')).fetchall()]
                result={'schemaVersion':SCHEMA,'phase':'preflight','identityVerified':True,
                    'sharedWorkerDisabled':True,'paidCalls':0,'maximumVisionDispatches':1,'maximumTeacherClips':5,
                    'familyQueueBefore':queue,'workerSelection':'exact_validation_submission_only'}
                save_json(output,result)
            else:
                result=execute(database,service,token,lambda value:save_json(output,value))
    print(json.dumps({'phase':result['phase'],'submissionId':result.get('submissionId'),'readyForStudent':result.get('readyForStudent'),'evidence':str(output)},ensure_ascii=False))


if __name__=='__main__':
    try:main()
    except Exception as error:
        reason=error.code if isinstance(error,ApiError) else str(error) if isinstance(error,ValueError) else type(error).__name__
        print(json.dumps({'stopped':True,'reason':reason},ensure_ascii=False),file=sys.stderr)
        raise SystemExit(1)
