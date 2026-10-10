#!/usr/bin/env python3
"""Explicit, isolated learning examples for one human-authorized existing child.

No login/PIN/device/SMS changes, schema work, scheduler or paid Provider calls.
The exact phone and child identity are mandatory. One transaction verifies all
pre-existing scoped rows and real learning evidence before committing new rows.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import nullcontext, redirect_stdout, redirect_stderr
from copy import copy
import io
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]

from PIL import Image,ImageDraw
from core.errors import ApiError
from core.database import Database
from dev_homework_sample import _font
from dev_review_sample import create_review_samples
from seed_learning_demo import local_app
from services.learning_evidence_service import canonical,digest,weaknesses
from services.report_learning_summary import review_report_for_period
from services.service_factory import homework_service

SCHEMA='mira.authorized-existing-student-demo.v1'
AUTHORIZED_PHONE='13860469696'


def original_picture_sheet(index):
    """Original count pictures for the parent upload view; no OCR/answers."""
    page=Image.new('RGB',(1200,1500),'#fffdf5');draw=ImageDraw.Draw(page)
    draw.text((90,65),'测试照片 · 一年级看图算一算',font=_font(43),fill='#304844')
    draw.text((90,135),'原创上传样例 / 未分析 / 没有孩子作答',font=_font(28),fill='#66766f')
    groups=(3,2) if index==1 else (4,1)
    for group,count in enumerate(groups):
        left=110+group*590
        for item in range(count):
            x=left+(item%2)*125;y=355+(item//2)*140
            draw.ellipse((x,y,x+92,y+92),fill='#e88564',outline='#b86044',width=3)
            draw.line((x+46,y-16,x+48,y+7),fill='#5d6942',width=7)
            draw.ellipse((x+49,y-18,x+81,y-3),fill='#819868')
    draw.text((530,410),'+',font=_font(80),fill='#304844')
    draw.text((95,815),'一共有多少个？',font=_font(48),fill='#304844')
    for option,count in enumerate((4,5,6)):
        x=90+option*375
        draw.rounded_rectangle((x,935,x+315,1155),radius=22,outline='#b8c6b1',width=3)
        for item in range(count):
            px=x+38+(item%3)*86;py=975+(item//3)*85
            draw.ellipse((px,py,px+58,py+58),fill='#e88564',outline='#b86044',width=2)
    draw.text((90,1275),'图片已保存，AI分析尚未启用。',font=_font(31),fill='#66766f')
    draw.text((90,1340),'本页仅测试上传与编辑，不代表真实作业或成绩。',font=_font(28),fill='#66766f')
    result=io.BytesIO();page.save(result,format='PNG');return result.getvalue()


def scoped_rows(conn,family):
    """Hash rows in memory, retain no credentials or raw family records."""
    queries={table:('SELECT * FROM '+table+' WHERE family_id=?',(family,)) for table in (
        'children','devices','app_settings','family_members','tasks','learning_review_preferences',
        'learning_review_runs','learning_answer_events','homework_submissions','learning_sessions')}
    for table in ('learning_review_items','learning_review_requests','learning_review_reminders'):
        queries[table]=(f'SELECT i.* FROM {table} i JOIN learning_review_runs r ON r.id=i.run_id WHERE r.family_id=?',(family,))
    for table in ('homework_pages','homework_items','homework_item_revisions','homework_actions','homework_jobs',
                  'homework_provider_calls','homework_audio_receipts'):
        queries[table]=(f'SELECT i.* FROM {table} i JOIN homework_submissions s ON s.id=i.submission_id WHERE s.family_id=?',(family,))
    return {table:Counter(digest(dict(row)) for row in conn.execute(sql,args).fetchall())
            for table,(sql,args) in queries.items()}


def pending_photos(conn,*,child,user,service,now,namespace):
    scoped=copy(service);scoped.repository=copy(service.repository)
    scoped.repository.transaction=lambda:nullcontext(conn)
    scoped.profile=copy(service.profile)
    token='local-fixture:'+digest([namespace,user['id'],child['id']])
    context={'user':user,'family':{'id':child['family_id']}}
    def auth(value):
        if value!=token:raise ApiError('demo_scope_invalid','测试范围无效',403)
        return context
    scoped.profile._auth_context=auth
    scoped.provider=scoped.audio=scoped.capture_service=None
    scoped.processing_enabled=False;scoped.clock=lambda:now
    # Preserve the actual family role boundary; never create a missing member.
    if not conn.execute('SELECT id FROM family_members WHERE family_id=? AND user_id=?',
                        (child['family_id'],user['id'])).fetchone():
        raise ValueError('Existing authorized family membership is required')
    scoped.profile._assert_capability(conn,context,'manage_tasks')
    results=[]
    for index in (1,2):
        key=f'{namespace}:picture:{index}'
        existing=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND child_id=? AND idempotency_key=?',
            (child['family_id'],child['id'],key)).fetchone()
        if existing:
            if existing['source']!='synthetic_fixture':
                raise ValueError('Refusing to overwrite an unrelated photo submission')
            row=existing
        else:
            row=scoped.create(token,child['id'],{'idempotencyKey':key,'subject':'math','analysisConsent':True,
                'title':f'测试照片 · 看图加法{index}（未分析）'})['submission']
            row=scoped.upload(token,row['id'],{'revision':row['revision'],'idempotencyKey':'original-picture'},original_picture_sheet(index))['submission']
            conn.execute('UPDATE homework_submissions SET source=? WHERE id=? AND family_id=?',('synthetic_fixture',row['id'],child['family_id']))
            row=conn.execute('SELECT * FROM homework_submissions WHERE id=?',(row['id'],)).fetchone()
        results.append({'id':row['id'],'title':row['title'],'status':row['status'],
            'deleted':row['deleted_at'] is not None,'studentActivityReady':False,'parentOnly':True,
            'path':'/learning-center/homework/'+row['id']})
    return results


def seed_authorized(conn,*,user,child,service,now):
    if user['phone']!=AUTHORIZED_PHONE or user['family_id']!=child['family_id'] or child['grade_code']!='primary_1':
        raise ValueError('Exact human-authorized primary-one family identity required')
    namespace='explicit_learning_demo_v1_'+digest([child['family_id'],child['id']])[:20]
    before=scoped_rows(conn,child['family_id'])
    evidence_before=weaknesses(conn,family_id=child['family_id'],child_id=child['id'])
    report_before=review_report_for_period(conn,family_id=child['family_id'],start=0,end=now+86400000)
    courses=conn.execute("SELECT c.* FROM learning_courses c JOIN learning_textbook_course_builds b ON b.course_id=c.id AND b.course_version=c.version WHERE c.grade_code='primary_1' AND c.subject='chinese' AND c.status='published' AND b.status='published' ORDER BY b.created_at DESC").fetchall()
    from dev_review_sample import _published_pool
    course=None
    for candidate in courses:
        try:
            _published_pool(conn,candidate)
        except (ValueError,ApiError):
            continue
        course=dict(candidate);break
    if course is None:raise ValueError('An existing published picture/teacher-audio pool is required')
    review=create_review_samples(conn,child=child,course=course,now=now,seed_namespace=namespace,authorized_existing_child=True)
    photos=pending_photos(conn,child=child,user=user,service=service,now=now,namespace=namespace)
    after=scoped_rows(conn,child['family_id'])
    if any(before[table]-after[table] for table in before):
        raise ValueError('Pre-existing row changed; rolling back all fixture rows')
    if after['learning_answer_events']!=before['learning_answer_events']:
        raise ValueError('Synthetic fixture polluted real answer evidence')
    if weaknesses(conn,family_id=child['family_id'],child_id=child['id'])!=evidence_before:
        raise ValueError('Synthetic fixture changed actual weaknesses')
    if review_report_for_period(conn,family_id=child['family_id'],start=0,end=now+86400000)!=report_before:
        raise ValueError('Synthetic fixture changed normal learning summary')
    for photo in photos:
        if conn.execute('SELECT id FROM homework_jobs WHERE submission_id=?',(photo['id'],)).fetchone():
            raise ValueError('Test photos must never enqueue analysis')
    return {'schemaVersion':SCHEMA,'demoNamespace':namespace,'childId':child['id'],'childName':child['name'],
        'gradeCode':child['grade_code'],'syntheticFixture':True,'reviews':review['reviews'],'photos':photos,
        'source':review['source'],'providerCalls':0,'audioCalls':0,
        'explanation':'图片考试和预设报告仅用于测试；不写真实答题证据、不参与实际薄弱点或成长评分。照片只保存未分析的原创一年级页面，家长可查看编辑，学生端没有照片订正活动。',
        'verification':{'originalRowsUnchanged':True,'realAnswerEventsUnchanged':True,'realWeaknessesUnchanged':True,
            'normalLearningSummaryUnchanged':True,'noAnalysisJobs':True,
            'tables':{table:{'before':sum(before[table].values()),'after':sum(after[table].values())} for table in before}},
        'createdAt':now}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone',required=True,choices=[AUTHORIZED_PHONE])
    parser.add_argument('--child-id',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    output=Path(args.output).expanduser().resolve()
    if output.suffix!='.json' or output.exists():
        raise ValueError('Choose a new JSON evidence path; existing output is never overwritten')
    with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
        app=local_app()
        if app.config['APP_ENV']!='development':
            raise ValueError('Only the local development environment is allowed')
        database=Database(app.config['DATABASE_URL'])
        with app.app_context(),database.transaction() as conn:
            user=conn.execute('SELECT id,phone,family_id FROM users WHERE phone=?',(args.phone,)).fetchone()
            if user is None:raise ValueError('The authorized existing account was not found')
            child=conn.execute('SELECT * FROM children WHERE id=? AND family_id=? FOR UPDATE',
                (args.child_id,user['family_id'])).fetchone()
            if child is None:raise ValueError('The authorized existing child was not found in this family')
            result=seed_authorized(conn,user=dict(user),child=dict(child),service=homework_service(),now=int(time.time()*1000))
    output.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'ok':True,'evidenceFile':str(output),**result},ensure_ascii=False))


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        # Never dump database credentials, request headers or private row data.
        print(json.dumps({'ok':False,'error':str(error) if isinstance(error,ValueError) else type(error).__name__}))
        raise SystemExit(1)
