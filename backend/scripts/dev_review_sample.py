"""Explicit local-demo helper, using existing published assets and real grading.

The caller creates/authorizes a dedicated test family and owns one transaction.
This module never connects, commits, generates content, publishes or speaks.
Week buckets distinguish demo scenarios; all actual event timestamps are `now`.
"""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime,timedelta
import re
from zoneinfo import ZoneInfo

from core.errors import ApiError
from content import textbook_journey as journey
from content.textbook_release import validate_release
from repositories.textbook_repository import TextbookRepository
from services.learning_evidence_service import canonical,digest
from services.learning_review_questions import authored_question
from services.learning_review_service import LearningReviewService,POLICY,decode


class _CallerTransaction:
    def __init__(self,conn):
        self.conn=conn

    @contextmanager
    def transaction(self):
        # Deliberately no nested commit/rollback: the root seed is atomic.
        yield self.conn


class _ScopedStudentAuth:
    def __init__(self,child,token):
        self.child,self.token=child,token

    def authenticate(self,token):
        if token!=self.token:
            raise ApiError('demo_scope_invalid','体验数据范围无效',403)
        return {'principal':{'family_id':self.child['family_id'],'child_id':self.child['id']}}


def _published_pool(conn,course):
    if course.get('subject')!='chinese' or course.get('grade_code')!='primary_1':
        raise ValueError('This demo requires the existing published primary-one Chinese course')
    build=conn.execute("SELECT * FROM learning_textbook_course_builds WHERE course_id=? AND course_version=? AND status='published'",
        (course['id'],course['version'])).fetchone()
    if not build:
        raise ValueError('Demo cannot create or publish a missing course')
    repo=TextbookRepository(None)
    directory=repo.get_revision(conn,build['edition_id'],build['revision_id'])
    if directory is None:
        raise ValueError('Published directory is unavailable')
    release=validate_release(build,repo.manifest(directory),course)
    if release is None or not journey.supported(release):
        raise ValueError('Published course has no registered picture activity')
    spec=journey.definition(release=release)
    return [authored_question(spec,course,skill,q) for skill in spec.skills for q in spec.flow['bank'][skill]]


def create_review_samples(conn, *, child, course, now, seed_namespace, authorized_existing_child=False):
    """Return 3 durable, idempotent demo runs for an explicitly owned test child.

    An existing child's identity requires explicit human authorization and
    authorized_existing_child=True. Re-running preserves all
    user interactions; an interrupted seed should roll back the caller's entire
    transaction. Never delete or overwrite an existing unrelated weekly run.
    """
    if type(authorized_existing_child) is not bool or type(now) is not int or not re.fullmatch(r'[a-zA-Z0-9_-]{3,80}',seed_namespace):
        raise ValueError('Explicit stable demo namespace and real timestamp required')
    token='demo-helper:'+digest([seed_namespace,child['family_id'],child['id']])
    service=LearningReviewService(_CallerTransaction(conn),auth_service=None,
        student_auth_service=_ScopedStudentAuth(child,token),clock=lambda:now)
    child=service.repository.child(conn,child['family_id'],child['id'])
    if child['grade_code']!='primary_1':
        raise ValueError('Picture exam demo requires a primary-one test child')
    preferences=service._preferences(conn,child)
    if not preferences['enabled'] or service._paused(preferences,now):
        raise ValueError('Dedicated test child must have review participation enabled')
    pool=_published_pool(conn,course)
    groups=defaultdict(list)
    for question in pool:
        groups[question['knowledgeId']].append(question)
    skills=sorted(groups)
    if len(skills)<6 or any(len(groups[s])<4 for s in skills):
        raise ValueError('Demo needs six real picture objectives and four existing variants each')
    local=datetime.fromtimestamp(now/1000,ZoneInfo(preferences['timezone']))
    monday=local.date()-timedelta(days=local.weekday())
    scenarios=[('completed',2,0,6),('paused',1,1,6),('ready',0,2,10)]
    results=[]
    for scenario,weeks_back,variant,count in scenarios:
        title={'ready':'测试体验 · 图片小考试','paused':'测试体验 · 继续未完成考试','completed':'测试体验 · 报告样例（预设）'}[scenario]
        task_type='synthetic_review' if authorized_existing_child else 'weekend_review'
        if authorized_existing_child:
            candidates=conn.execute('SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? FOR UPDATE',
                (child['family_id'],child['id'])).fetchall()
            matching=[row for row in candidates if decode(row['coverage_json'],{}).get('demoNamespace')==seed_namespace
                and decode(row['coverage_json'],{}).get('demoScenario')==scenario]
            if len(matching)>1:
                raise ValueError('Conflicting fixture namespace')
            existing=matching[0] if matching else None
            if existing:
                week=existing['week_start']
            else:
                occupied={row['week_start'] for row in candidates}
                for offset in range(1,261):
                    week=(monday-timedelta(weeks=offset)).isoformat()
                    key=digest([child['id'],week,'weekend_review'])
                    if week not in occupied and not conn.execute('SELECT id FROM tasks WHERE family_id=? AND learning_assignment_key=?',
                        (child['family_id'],key)).fetchone():
                        break
                else:
                    raise ValueError('No unoccupied historical fixture bucket')
        else:
            week=(monday-timedelta(weeks=weeks_back)).isoformat()
            existing=conn.execute("SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? AND week_start=? AND task_type='weekend_review' FOR UPDATE",
                (child['family_id'],child['id'],week)).fetchone()
        if existing:
            marker=decode(existing['coverage_json'],{})
            if marker.get('demoNamespace')!=seed_namespace or marker.get('demoScenario')!=scenario:
                raise ValueError('Refusing to overwrite an unrelated weekly review')
            if authorized_existing_child and (marker.get('syntheticFixture') is not True or existing['task_type']!=task_type):
                raise ValueError('Existing-child fixtures require exact synthetic isolation metadata')
            run=dict(existing)
        else:
            selected=[groups[skills[i%len(skills)]][variant+i//len(skills)] for i in range(count)]
            run_id='review_demo_'+digest([seed_namespace,child['family_id'],child['id'],week,scenario])[:32]
            run={'id':run_id,'family_id':child['family_id'],'child_id':child['id'],'week_start':week,
                'task_type':task_type,'task_id':'task_'+run_id,'grade_code':child['grade_code'],
                'grade_revision':int(child.get('grade_selection_revision') or 0),'status':'scheduled','revision':0,
                'appointment_revision':0,'scheduled_at':now,'reminder_expires_at':now,'reminder_status':'silent_demo',
                'current_index':0,'total_questions':len(selected),'correct_count':0,'independent_correct_count':0,
                'estimated_seconds':sum(q['estimatedSeconds'] for q in selected),
                'coverage_json':canonical({'lessonCount':1,'questionCount':len(selected),'homeworkQuestionCount':0,
                    'contentGap':True,'notes':['测试体验数据，周次仅区分样例，不表示真实学习历史。','复用《天地人》已审核图片和教师语音；第二课资源仍待补充。'],
                    'missingKnowledgeIds':[],'unsupportedCourses':[],'sourceCutoffAt':now,
                    'syntheticFixture':True,'demoTitle':title,
                    'demoNamespace':seed_namespace,'demoScenario':scenario,'demoCreatedAt':now}),
                'policy_json':canonical(POLICY),'created_at':now,'started_at':None,'completed_at':None,'updated_at':now}
            service.repository.create(conn,run,[(q,'new_variant') for q in selected],seed_namespace,preferences['timezone'])
            conn.execute('UPDATE tasks SET title=?,description=? WHERE id=? AND family_id=?',
                (title,'测试体验数据；成绩由演示作答产生，不代表真实孩子历史。',run['task_id'],child['family_id']))
            if scenario!='ready':
                sequence=0
                def action(name):
                    nonlocal sequence
                    sequence+=1
                    current=service.student_detail(token,run_id)
                    return service.student_action(token,run_id,{'action':name,'revision':current['review']['revision'],
                        'requestId':f'{seed_namespace}:{scenario}:action:{sequence}'})
                action('start')
                for index in range(6 if scenario=='completed' else 0 if authorized_existing_child else 2):
                    if index==1:
                        action('hint')
                    view=service.student_detail(token,run_id)
                    q=selected[index]
                    wrong=(scenario=='completed' and index in ((0,) if authorized_existing_child else (0,3))) or (scenario=='paused' and index==1)
                    answer=next(o['value'] for o in q['options'] if o['value']!=q['correctAnswer']) if wrong else q['correctAnswer']
                    service.answer(token,run_id,{'questionId':view['currentQuestion']['id'],'response':answer,
                        'requestId':f'{seed_namespace}:{scenario}:answer:{index}','revision':view['review']['revision']})
                    action('next')
                if scenario=='paused':
                    action('pause')
                run=service.repository.run(conn,child['family_id'],child['id'],run_id)
        report=service._report(run,service.repository.items(conn,run['id']))
        results.append({'id':run['id'],'taskId':run['task_id'],'title':title,'scenario':scenario,'status':run['status'],
            'answeredCount':report['answeredCount'],'totalQuestions':run['total_questions'],
            'correctCount':run['correct_count'],'independentCorrectCount':run['independent_correct_count'],
            'path':'/learning/reviews/'+run['id']})
    return {'reviews':results,'source':{'courseId':course['id'],'version':course['version'],'questionCount':len(pool)}}
