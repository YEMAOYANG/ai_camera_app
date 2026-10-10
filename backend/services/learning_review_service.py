"""Durable weekly review, frozen questions and child-authoritative progress.

This service never asks an AI to make questions and never changes classroom
marks. Legacy task timers have no authority over weekend_review tasks.
"""
from collections import Counter
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.errors import ApiError
from core.security import now_ms
from repositories.learning_review_repository import LearningReviewRepository
from services.learning_evidence_service import canonical, digest, record_answer, weaknesses
from services.learning_review_questions import published_question_pool

POLICY = json.loads((Path(__file__).parents[1] / 'content/learning_review_policy.v1.json').read_text())
SCHEMA = 'mira.learning.reviews.v1'
TERMINAL = ('completed', 'skipped', 'superseded', 'rest', 'content_gap')
CLOCK = re.compile(r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')


def decode(value, fallback=None):
    return json.loads(value) if isinstance(value, str) else value if value is not None else fallback


def synthetic_fixture(run):
    """Only trusted persisted fixture metadata opts out of real assessment."""
    coverage=decode(run.get('coverage_json'),{})
    return isinstance(coverage,dict) and coverage.get('syntheticFixture') is True


def local_at(timestamp, preferences):
    return datetime.fromtimestamp(timestamp / 1000, ZoneInfo(preferences['timezone']))


class LearningReviewService:
    def __init__(self, database, *, auth_service, student_auth_service, parent_authorize=None,
                 question_pool=published_question_pool, reminder_sender=None, clock=now_ms,
                 private_question_pool=None, private_audio_file=None, private_source_alive=None):
        self.repository = LearningReviewRepository(database)
        self.auth, self.student_auth = auth_service, student_auth_service
        self.parent_authorize, self.question_pool, self.reminder_sender, self.clock = parent_authorize, question_pool, reminder_sender, clock
        self.private_question_pool, self.private_audio_file = private_question_pool, private_audio_file
        self.private_source_alive=private_source_alive

    def _parent(self, token):
        return self.auth.authenticate(token)

    def _student(self, token):
        return self.student_auth.authenticate(token)['principal']

    def _write_authority(self, conn, context):
        if self.parent_authorize is None:
            raise ApiError('permission_denied', '当前身份不能调整学习安排', 403)
        self.parent_authorize(conn, context, 'manage_tasks')

    def _preferences(self, conn, child):
        row = conn.execute('SELECT * FROM learning_review_preferences WHERE family_id=? AND child_id=?',
            (child['family_id'], child['id'])).fetchone()
        return {**POLICY['defaults'], **(decode(row['preferences_json'], {}) if row else {}),
                'revision': row['revision'] if row else 0}

    def preferences(self, token, child_id, data=None):
        context = self._parent(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, context['family']['id'], child_id)
            old = self._preferences(conn, child)
            if data is None:
                return {'ok': True, 'preferences': old}
            self._write_authority(conn, context)
            if not isinstance(data, dict) or set(data) - set(POLICY['defaults']) or data.get('revision') != old['revision']:
                raise ApiError('review_preferences_conflict', '安排已经更新，请刷新后再试', 409)
            value = {**old, **data, 'revision': old['revision'] + 1}
            self._validate_preferences(value)
            now = self.clock()
            if old['revision']:
                conn.execute('UPDATE learning_review_preferences SET preferences_json=?,revision=?,updated_at=? WHERE family_id=? AND child_id=?',
                    (canonical(value), value['revision'], now, child['family_id'], child['id']))
            else:
                conn.execute('INSERT INTO learning_review_preferences(family_id,child_id,preferences_json,revision,updated_at) VALUES (?,?,?,?,?)',
                    (child['family_id'],child['id'],canonical(value),value['revision'],now))
            # Preserve the frozen paper. Unstarted appointments follow the
            # parent's chosen weekend; started work needs explicit rescheduling.
            active = conn.execute("SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? AND status NOT IN ('completed','skipped','superseded','rest','content_gap') FOR UPDATE",
                (child['family_id'],child['id'])).fetchall()
            for row in active:
                if synthetic_fixture(row):
                    continue
                run = dict(row)
                fields = {'appointment_revision': run['appointment_revision'] + 1, 'reminder_status': 'invalidated'}
                if not value['enabled'] or self._paused(value, now):
                    fields['status'] = 'paused'
                    self.repository.task_status(conn,run,'pending',now)
                elif not run['started_at'] and (run['status']!='paused' or not old['enabled'] or self._paused(old,now)):
                    day=date.fromisoformat(run['week_start'])+timedelta(days=value['weekday']-1)
                    planned=datetime.combine(day,time.fromisoformat(value['time']),ZoneInfo(value['timezone']))
                    at=int(planned.timestamp()*1000)
                    expired=now>at+POLICY['reminderValiditySeconds']*1000
                    fields.update(status='needs_schedule' if expired else 'scheduled',scheduled_at=at,
                        reminder_expires_at=at+POLICY['reminderValiditySeconds']*1000,
                        reminder_status='expired' if expired else 'pending')
                    self._sync_task_schedule(conn,run,at,value)
                    self.repository.task_status(conn,run,'pending' if expired else 'scheduled',now)
                self.repository.update(conn, run, now, **fields)
            return {'ok': True, 'preferences': value}

    @staticmethod
    def _validate_preferences(value):
        if type(value['weekday']) is not int or value['weekday'] not in (6,7):
            raise ApiError('review_preferences_invalid', '请选择周六或周日', 400)
        if any(type(value[k]) is not bool for k in ('enabled','reminderEnabled')):
            raise ApiError('review_preferences_invalid', '安排开关无效', 400)
        if type(value['dailyReminderLimit']) is not int or not 0 <= value['dailyReminderLimit'] <= 2:
            raise ApiError('review_preferences_invalid', '每日最多提醒两次', 400)
        if any(not isinstance(value[k], str) or not CLOCK.fullmatch(value[k]) for k in ('time','allowedStart','allowedEnd')):
            raise ApiError('review_preferences_invalid', '请选择有效时段', 400)
        if not value['allowedStart'] <= value['time'] < value['allowedEnd']:
            raise ApiError('review_preferences_invalid', '预约必须在允许时段内', 400)
        try:
            ZoneInfo(value['timezone'])
            if value['pausedUntil'] is not None:
                date.fromisoformat(value['pausedUntil'])
        except (ValueError, TypeError, ZoneInfoNotFoundError):
            raise ApiError('review_preferences_invalid', '暂停日期或时区无效', 400)

    @staticmethod
    def _paused(preferences, now):
        return bool(preferences['pausedUntil'] and local_at(now, preferences).date().isoformat() <= preferences['pausedUntil'])

    def _check_grade(self, child, run):
        if (child['grade_code'] != run['grade_code'] or int(child.get('grade_selection_revision') or 0) != run['grade_revision']):
            raise ApiError('review_grade_changed', '年级已变化，请返回书包查看新安排', 409)

    def parent_list(self, token, child_id):
        context = self._parent(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, context['family']['id'], child_id)
            return self._list(conn, child, parent=True)

    def student_list(self, token):
        principal = self._student(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, principal['family_id'], principal['child_id'])
            return self._list(conn, child)

    def _list(self, conn, child, parent=False):
        rows = conn.execute('SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? ORDER BY created_at DESC LIMIT 16',
            (child['family_id'],child['id'])).fetchall()
        runs = [dict(row) for row in rows if parent or (row['grade_code'] == child['grade_code'] and row['status'] not in ('superseded','skipped'))]
        return {'ok': True, 'enabled': True, 'schemaVersion': SCHEMA, 'reviews': [self._summary(run) for run in runs]}

    def parent_weaknesses(self, token, child_id):
        context = self._parent(token)
        with self.repository.transaction() as conn:
            self.repository.child(conn, context['family']['id'], child_id)
            return {'ok': True, 'weaknesses': weaknesses(conn, family_id=context['family']['id'], child_id=child_id)}

    def parent_detail(self, token, child_id, run_id):
        context = self._parent(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, context['family']['id'], child_id)
            run = self.repository.run(conn, child['family_id'], child['id'], run_id)
            return self._view(conn, run, parent=True)

    def student_detail(self, token, run_id):
        principal = self._student(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn, principal['family_id'], principal['child_id'])
            run = self.repository.run(conn, child['family_id'], child['id'], run_id)
            self._check_grade(child, run)
            return self._view(conn, run)

    def _snapshot(self, item):
        question = decode(item['snapshot_json'])
        if digest(question) != item['snapshot_sha256']:
            raise ApiError('review_content_changed', '复习题内容校验失败，请稍后重试', 409)
        return question

    def _check_private_source(self,conn,run,question):
        if question.get('private') and self.private_source_alive:
            child=self.repository.child(conn,run['family_id'],run['child_id'])
            if not self.private_source_alive(conn,child,question):
                raise ApiError('review_source_changed','原作业已更新或需要核实，请回到作业查看',409)

    @staticmethod
    def _audio(run_id, asset):
        return f'/api/v2/student/learning/reviews/{run_id}/media/{asset}'

    def _summary(self, run):
        coverage=decode(run['coverage_json'])
        title=coverage.get('demoTitle') if synthetic_fixture(run) else None
        return {'id':run['id'],'taskId':run['task_id'],'title':title if isinstance(title,str) and title else '周末小复习','status':run['status'],
            'weekStart':run['week_start'],'revision':run['revision'],'appointmentRevision':run['appointment_revision'],
            'scheduledAt':run['scheduled_at'],'estimatedMinutes':round(run['estimated_seconds']/60,1),
            'coverage':coverage, 'totalQuestions':run['total_questions'],
            'currentIndex':run['current_index'],'correctCount':run['correct_count'],
            'independentCorrectCount':run['independent_correct_count'],'startedAt':run['started_at'],'completedAt':run['completed_at'],
            'reminderStatus':run['reminder_status']}

    def _view(self, conn, run, parent=False):
        items = self.repository.items(conn, run['id'])
        current = next((i for i in items if i['ordinal']==run['current_index']), None)
        public, feedback = None, None
        if current and run['status'] == 'in_progress' and not parent:
            q = self._snapshot(current)
            self._check_private_source(conn,run,q)
            if not current['exposure_at']:
                conn.execute('UPDATE learning_review_items SET exposure_at=? WHERE run_id=? AND ordinal=?',
                    (self.clock(),run['id'],current['ordinal']))
            # The frozen evidenceMode was selected at creation. Another lesson
            # may expose this exact item before the child opens the review.
            public = {k:q.get(k) for k in ('renderer','prompt','visual','options','homeworkSource') if k in q}
            public.update(id=current['question_id'],promptAudioUrl=self._audio(run['id'],q['promptAudioAsset']),
                hint=None,hintAudioUrl=None,explanation=None,explanationAudioUrl=None,
                selectedResponse=decode(current['answer_json']),helpUsed=bool(current['hint_level'] or current['explanation_seen']),
                evidenceMode=current['evidence_mode'])
            if current['hint_level']:
                at = min(current['hint_level'],len(q['hints']))-1
                public.update(hint=q['hints'][at], hintAudioUrl=self._audio(run['id'],q['hintAudioAssets'][at]))
            if current['explanation_seen'] or current['answered_at']:
                public.update(explanation=q['explanation'],explanationAudioUrl=self._audio(run['id'],q['explanationAudioAsset']))
            feedback = decode(current['feedback_json'])
        report = self._report(run,items,conn=conn) if parent or run['status']=='completed' else None
        summary=self._summary(run)
        if report and report.get('sourceReviewCount'):
            summary.update(correctCount=sum(bool(i['correct']) for i in report['items']),
                independentCorrectCount=report['independentFirstCorrect'])
        return {'ok':True,'schemaVersion':SCHEMA,'review':summary,'currentQuestion':public,'feedback':feedback,'report':report}

    def _report(self, run, items, *, conn=None):
        evidence = [];source_review_count=0
        for item in items:
            if not item['answered_at'] or item['evidence_mode']=='withdrawn':
                continue
            q = self._snapshot(item)
            if conn is not None and q.get('private') and str(q.get('sourceSubmissionId') or '').startswith('hw_'):
                from services.homework_evidence_guard import private_review_reference_current
                if not private_review_reference_current(conn,family_id=run['family_id'],child_id=run['child_id'],question=q):
                    source_review_count+=1
                    continue
            feedback = decode(item['feedback_json'])
            answer=decode(item['answer_json'])
            labels={option['value']:option.get('label',option['value']) for option in q['options']}
            evidence.append({'questionId':item['question_id'],'knowledgeId':q['knowledgeId'],'knowledgeLabel':q['knowledgeLabel'],
                'courseTitle':q['courseTitle'],'prompt':q['prompt'],'answer':answer,'answerLabel':labels.get(answer,answer),
                'correctAnswerLabel':labels.get(q['correctAnswer'],q['correctAnswer']),'options':q['options'],
                'correctAnswer':q['correctAnswer'],'explanation':q['explanation'],'correct':feedback['correct'],
                'independent':feedback['independent'],'evidenceMode':item['evidence_mode'],
                'hintUsed':bool(item['hint_level']),'explanationSeen':bool(item['explanation_seen']),'answeredAt':item['answered_at']})
        return {'status':run['status'],'weekStart':run['week_start'],'completedAt':run['completed_at'],
            'answeredCount':len(evidence),'totalQuestions':run['total_questions'],
            'independentFirstCount':sum(e['independent'] for e in evidence),
            'independentFirstCorrect':sum(e['independent'] and e['correct'] for e in evidence),
            'repeatedPracticeCount':sum(e['evidenceMode']=='repeated_practice' for e in evidence),
            'withdrawnCount':sum(i['evidence_mode']=='withdrawn' for i in items),
            'sourceReviewCount':source_review_count,
            'items':evidence,'notParticipated':not bool(run['started_at']),
            'assessmentScope':'测试演示记录；不参与孩子真实薄弱点、成长评分或正式学习报告。' if synthetic_fixture(run) else '图片支持下的情境理解；原题重做与提示后作答不计新题独立掌握。',
            'parentAction':'仅用于体验答题和报告流程，预设表现不代表孩子的实际能力。' if synthetic_fixture(run) else '先看孩子需要帮助的具体一步；没有参加不代表不会。'}

    def _revision(self, run, data, key='revision'):
        expected = run['appointment_revision'] if key=='appointmentRevision' else run['revision']
        if type(data.get(key)) is not int or data[key] != expected:
            raise ApiError('review_progress_conflict', '进度已经更新，请刷新后继续', 409)

    def student_action(self, token, run_id, data):
        if not isinstance(data,dict) or set(data)-{'action','requestId','revision','minutes'}:
            raise ApiError('review_action_invalid','操作参数无效',400)
        principal = self._student(token)
        with self.repository.transaction() as conn:
            child = self.repository.child(conn,principal['family_id'],principal['child_id'])
            run = self.repository.run(conn,child['family_id'],child['id'],run_id)
            self._check_grade(child,run)
            now = self.clock()
            if self.repository.request(conn,run,data,now):
                return self._view(conn,run)
            self._revision(run,data)
            action = data.get('action')
            if run['status'] in TERMINAL:
                raise ApiError('review_finished','这次复习已经结束',409)
            preferences = self._preferences(conn,child)
            if not preferences['enabled'] or self._paused(preferences,now):
                raise ApiError('review_paused','这段时间先休息，之后再复习',409)
            items = self.repository.items(conn,run_id)
            item = next((i for i in items if i['ordinal']==run['current_index']),None)
            fields = {}
            if action=='start':
                if not items:
                    raise ApiError('review_content_gap','复习内容还在准备',409)
                fields.update(status='in_progress',started_at=run['started_at'] or now,
                    reminder_status='invalidated',appointment_revision=run['appointment_revision']+1)
                self.repository.task_status(conn,run,'in_progress',now)
            elif action in ('pause','snooze'):
                fields.update(status='paused' if action=='pause' else 'scheduled',reminder_status='invalidated',
                    appointment_revision=run['appointment_revision']+1)
                if action=='snooze':
                    if data.get('minutes',20)!=20:
                        raise ApiError('review_action_invalid','可以选择二十分钟后',400)
                    at=now+20*60*1000
                    local=local_at(at,preferences)
                    if local.date()!=local_at(now,preferences).date() or not preferences['allowedStart']<=local.strftime('%H:%M')<preferences['allowedEnd']:
                        fields.update(status='needs_schedule',scheduled_at=None)
                    else:
                        fields.update(scheduled_at=at,reminder_expires_at=at+POLICY['reminderValiditySeconds']*1000,reminder_status='pending')
                    self._sync_task_schedule(conn,run,fields['scheduled_at'],preferences)
                self.repository.task_status(conn,run,'pending',now)
            elif action in ('hint','explanation','next'):
                if run['status']!='in_progress' or item is None:
                    raise ApiError('review_not_started','请先开始复习',409)
                if action=='next':
                    if not item['answered_at']:
                        raise ApiError('review_answer_required','先试一试这道题',409)
                    index=run['current_index']+1
                    fields['current_index']=index
                    if index==run['total_questions']:
                        fields.update(status='completed',completed_at=now,reminder_status='invalidated',appointment_revision=run['appointment_revision']+1)
                        self.repository.task_status(conn,run,'completed',now)
                elif not item['answered_at']:
                    q=self._snapshot(item)
                    if action=='hint':
                        conn.execute('UPDATE learning_review_items SET hint_level=? WHERE run_id=? AND ordinal=?',
                            (min(item['hint_level']+1,len(q['hints'])),run_id,item['ordinal']))
                    else:
                        conn.execute('UPDATE learning_review_items SET explanation_seen=1 WHERE run_id=? AND ordinal=?',(run_id,item['ordinal']))
            else:
                raise ApiError('review_action_invalid','操作参数无效',400)
            self.repository.update(conn,run,now,**fields)
            self.repository.remember(conn,run,data,now)
            return self._view(conn,run)

    def answer(self, token, run_id, data):
        if not isinstance(data,dict) or set(data)!={'questionId','response','requestId','revision'}:
            raise ApiError('review_answer_invalid','请选一个图片答案',400)
        principal=self._student(token)
        with self.repository.transaction() as conn:
            child=self.repository.child(conn,principal['family_id'],principal['child_id'])
            run=self.repository.run(conn,child['family_id'],child['id'],run_id)
            self._check_grade(child,run)
            now=self.clock()
            if self.repository.request(conn,run,data,now):
                return self._view(conn,run)
            self._revision(run,data)
            item=next((i for i in self.repository.items(conn,run_id) if i['ordinal']==run['current_index']),None)
            if run['status']!='in_progress' or item is None or data['questionId']!=item['question_id']:
                raise ApiError('review_question_order','请完成当前题目',409)
            preferences=self._preferences(conn,child)
            if not preferences['enabled'] or self._paused(preferences,now):
                raise ApiError('review_paused','这段时间先休息，之后再复习',409)
            q=self._snapshot(item)
            self._check_private_source(conn,run,q)
            normalized_response=data['response']
            if q.get('renderer')=='homework_original':
                from services.homework_answer_quality import canonical_correction_answer
                normalized_response=canonical_correction_answer(data['response'])
                if normalized_response is None:
                    raise ApiError('review_answer_unclear','请只说这个空的答案，再试一次',400)
            elif data['response'] not in [o['value'] for o in q['options']]:
                raise ApiError('review_answer_invalid','请选一个图片答案',400)
            if item['answered_at']:
                raise ApiError('review_already_answered','答案已经保存，请继续下一题',409)
            correct=normalized_response==q['correctAnswer']
            prior=conn.execute('SELECT id FROM learning_answer_events WHERE family_id=? AND child_id=? AND question_fingerprint=? AND revoked_at IS NULL LIMIT 1',
                (child['family_id'],child['id'],q['fingerprint'])).fetchone()
            mode='repeated_practice' if prior else item['evidence_mode']
            independent=not item['hint_level'] and not item['explanation_seen'] and mode=='new_variant'
            feedback={'correct':correct,'independent':independent,'explanation':q['explanation'],
                'explanationAudioUrl':self._audio(run_id,q['explanationAudioAsset']),'correctAnswer':q['correctAnswer']}
            conn.execute('UPDATE learning_review_items SET answer_json=?,answer_sha256=?,feedback_json=?,answered_at=?,evidence_mode=? WHERE run_id=? AND ordinal=?',
                (canonical(data['response']),digest(data['response']),canonical(feedback),now,mode,run_id,item['ordinal']))
            if not synthetic_fixture(run):
                record_answer(conn,family_id=child['family_id'],child_id=child['id'],source_kind='review',source_id=run_id,
                    event_key=item['question_id'],question=q,answer=data['response'],correct=correct,occurred_at=now,
                    hint_used=bool(item['hint_level'] or item['explanation_seen']),adult_help=False,independent=independent)
            self.repository.update(conn,run,now,correct_count=run['correct_count']+int(correct),
                independent_correct_count=run['independent_correct_count']+int(correct and independent))
            self.repository.remember(conn,run,data,now)
            return self._view(conn,run)

    def schedule_action(self,token,run_id,data):
        if not isinstance(data,dict) or set(data)-{'childId','action','requestId','appointmentRevision','scheduledAt'}:
            raise ApiError('review_action_invalid','安排参数无效',400)
        context=self._parent(token)
        with self.repository.transaction() as conn:
            self._write_authority(conn,context)
            child=self.repository.child(conn,context['family']['id'],data.get('childId'))
            run=self.repository.run(conn,child['family_id'],child['id'],run_id)
            now=self.clock()
            if self.repository.request(conn,run,data,now):
                return self._view(conn,run,parent=True)
            self._revision(run,data,'appointmentRevision')
            if run['status'] in TERMINAL:
                raise ApiError('review_finished','这次复习已经结束',409)
            action=data.get('action')
            fields={'appointment_revision':run['appointment_revision']+1,'reminder_status':'invalidated'}
            if action=='skip':
                fields.update(status='skipped',scheduled_at=None)
                self.repository.task_status(conn,run,'cancelled',now)
            elif action=='pause':
                fields.update(status='paused',scheduled_at=None)
                self.repository.task_status(conn,run,'pending',now)
            elif action in ('reschedule','resume'):
                at=data.get('scheduledAt')
                preferences=self._preferences(conn,child)
                if type(at) is not int or not now<at<now+31*86400000:
                    raise ApiError('review_schedule_invalid','请选择未来三十天内的时间',400)
                local=local_at(at,preferences)
                if not preferences['allowedStart']<=local.strftime('%H:%M')<preferences['allowedEnd']:
                    raise ApiError('review_schedule_invalid','请选择允许提醒的时段',400)
                fields.update(status='scheduled',scheduled_at=at,reminder_expires_at=at+POLICY['reminderValiditySeconds']*1000,reminder_status='pending')
                self.repository.task_status(conn,run,'scheduled',now)
                self._sync_task_schedule(conn,run,at,preferences)
            else:
                raise ApiError('review_action_invalid','安排参数无效',400)
            self.repository.update(conn,run,now,**fields)
            self.repository.remember(conn,run,data,now)
            return self._view(conn,run,parent=True)

    @staticmethod
    def _sync_task_schedule(conn,run,at,preferences):
        local=local_at(at,preferences) if at is not None else None
        # tasks.scheduled_date is NOT NULL on the real schema. A deferred task
        # keeps its last calendar day while clearing its active start time.
        conn.execute('UPDATE tasks SET scheduled_date=COALESCE(?,scheduled_date),scheduled_start=?,start_at=?,due_at=NULL,timezone=? WHERE id=? AND family_id=?',
            (local.date().isoformat() if local else None,local.strftime('%H:%M') if local else None,
             local.isoformat() if local else None,preferences['timezone'],run['task_id'],run['family_id']))

    def audio(self,token,run_id,asset):
        from content.textbook_journey import audio_file
        principal=self._student(token)
        with self.repository.transaction() as conn:
            child=self.repository.child(conn,principal['family_id'],principal['child_id'])
            run=self.repository.run(conn,child['family_id'],child['id'],run_id)
            self._check_grade(child,run)
            allowed=set()
            # Don't leak future-question narration or a current answer before
            # the learner requests it. Reload preserves this authorization.
            for item in self.repository.items(conn,run_id):
                if item['ordinal']>run['current_index'] or not item['exposure_at'] or item['evidence_mode']=='withdrawn':
                    continue
                q=self._snapshot(item)
                self._check_private_source(conn,run,q)
                allowed.add(q['promptAudioAsset'])
                allowed.update(q['hintAudioAssets'][:item['hint_level']])
                if item['explanation_seen'] or item['answered_at']:
                    allowed.add(q['explanationAudioAsset'])
            if asset not in allowed:
                raise ApiError('review_audio_unavailable','这段语音暂不可用',404)
            if asset.startswith('homework.'):
                if self.private_audio_file is None:
                    raise ApiError('review_audio_unavailable','这段语音暂不可用',404)
                return self.private_audio_file(asset)
            return audio_file(asset)

    def ensure_week(self,conn,child,now):
        preferences=self._preferences(conn,child)
        if not preferences['enabled'] or self._paused(preferences,now):
            return None
        local=local_at(now,preferences)
        monday=local.date()-timedelta(days=local.weekday())
        week=monday.isoformat()
        outdated=conn.execute("SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? AND (grade_code<>? OR grade_revision<>?) AND status NOT IN ('completed','skipped','superseded','rest','content_gap') FOR UPDATE",
            (child['family_id'],child['id'],child['grade_code'],int(child.get('grade_selection_revision') or 0))).fetchall()
        for row in outdated:
            if synthetic_fixture(row):
                continue
            old=dict(row)
            self.repository.update(conn,old,now,status='superseded',reminder_status='invalidated',appointment_revision=old['appointment_revision']+1)
            self.repository.task_status(conn,old,'cancelled',now)
        existing=conn.execute("SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? AND week_start=? AND task_type='weekend_review'",
            (child['family_id'],child['id'],week)).fetchone()
        if existing:
            return dict(existing)
        older=conn.execute("SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? AND status NOT IN ('completed','skipped','superseded','rest','content_gap') ORDER BY created_at FOR UPDATE",
            (child['family_id'],child['id'])).fetchall()
        older=[row for row in older if not synthetic_fixture(row)]
        if any(row['started_at'] for row in older):
            return dict(next(row for row in older if row['started_at']))
        if any(row['scheduled_at'] and row['scheduled_at']>now for row in older):
            return dict(next(row for row in older if row['scheduled_at'] and row['scheduled_at']>now))
        if local.isoweekday()<preferences['weekday']:
            return None
        for row in older:
            old=dict(row)
            self.repository.update(conn,old,now,status='superseded',reminder_status='invalidated',appointment_revision=old['appointment_revision']+1)
            self.repository.task_status(conn,old,'cancelled',now)
        evidence=weaknesses(conn,family_id=child['family_id'],child_id=child['id'],since=now-POLICY['evidenceWindowDays']*86400000)
        evidence=[e for e in evidence if e['gradeCode']==child['grade_code']]
        if not evidence:
            return None
        wanted=[e['knowledgeId'] for e in evidence if e['status']=='needs_review']
        pool,gaps=self.question_pool(conn,child) if evidence else ([],[])
        pool,gaps=list(pool),list(gaps)
        if self.private_question_pool:
            private_pool,private_gaps=self.private_question_pool(conn,child)
            pool.extend(q for q in private_pool if q.get('private') is True and q.get('sourceEventId'))
            gaps.extend(private_gaps)
        known={e['knowledgeId'] for e in evidence if e['sampleCount']}
        pool=[q for q in pool if q['knowledgeId'] in known]
        seen={row['question_fingerprint'] for row in conn.execute('SELECT DISTINCT question_fingerprint FROM learning_answer_events WHERE family_id=? AND child_id=? AND revoked_at IS NULL',
            (child['family_id'],child['id'])).fetchall()}
        # Already displayed review questions remain exposures even if unanswered.
        for row in conn.execute("SELECT i.snapshot_json,r.coverage_json FROM learning_review_items i JOIN learning_review_runs r ON r.id=i.run_id WHERE r.family_id=? AND r.child_id=? AND i.exposure_at IS NOT NULL AND i.evidence_mode<>'withdrawn'",
                               (child['family_id'],child['id'])).fetchall():
            if synthetic_fixture(row):
                continue
            seen.add(decode(row['snapshot_json'])['fingerprint'])
        pool.sort(key=lambda q:(q['knowledgeId'] not in wanted,q['fingerprint'] in seen,
            wanted.index(q['knowledgeId']) if q['knowledgeId'] in wanted else len(wanted),digest([week,child['id'],q['fingerprint']])))
        chosen,counts,seconds=[],Counter(),0
        for q in pool:
            if counts[q['knowledgeId']]>=POLICY['maximumPerKnowledge'] or seconds+q['estimatedSeconds']>POLICY['maximumSeconds']:
                continue
            if not wanted and len(chosen)>=3:
                break
            chosen.append((q,'repeated_practice' if q.get('private') or q['fingerprint'] in seen else 'new_variant'))
            counts[q['knowledgeId']]+=1
            seconds+=q['estimatedSeconds']
            if seconds>=POLICY['targetSeconds'] or len(chosen)>=POLICY['maximumQuestions']:
                break
        lesson_count=len({q['courseId'] for q,_ in chosen if q.get('courseId')})
        homework_count=sum(bool(q.get('private')) for q,_ in chosen)
        missing=[key for key in wanted if key not in counts]
        notes=[]
        if missing:notes.append(f'{len(missing)} 个待巩固知识点尚无审核通过的图片语音复习题。')
        if lesson_count==1:notes.append('目前只有一课的已审核图片语音题，按实际题量安排。')
        if any(q.get('private') for q,_ in chosen):notes.append('照片错题使用已核验的原题订正；暂缺审核通过的数学变式，不计新题独立掌握。')
        if not chosen:notes.append('暂无可用复习题；系统不会临时生成或把未参加计为答错。')
        due_day=monday+timedelta(days=preferences['weekday']-1)
        scheduled=datetime.combine(due_day,time.fromisoformat(preferences['time']),ZoneInfo(preferences['timezone']))
        at=int(scheduled.timestamp()*1000)
        status='scheduled' if chosen else 'content_gap' if wanted else 'rest'
        if chosen and now>at+POLICY['reminderValiditySeconds']*1000:
            status='needs_schedule'
        identifier='review_'+digest([child['family_id'],child['id'],week,'weekend_review'])[:32]
        run={'id':identifier,'family_id':child['family_id'],'child_id':child['id'],'week_start':week,'task_type':'weekend_review',
            'task_id':'task_'+identifier,'grade_code':child['grade_code'],'grade_revision':int(child.get('grade_selection_revision') or 0),
            'status':status,'revision':0,'appointment_revision':0,'scheduled_at':at,
            'reminder_expires_at':at+POLICY['reminderValiditySeconds']*1000,'reminder_status':'pending' if status=='scheduled' else 'expired',
            'current_index':0,'total_questions':len(chosen),'correct_count':0,'independent_correct_count':0,'estimated_seconds':seconds,
            'coverage_json':canonical({'lessonCount':lesson_count,'homeworkQuestionCount':homework_count,'questionCount':len(chosen),'contentGap':bool(missing or gaps or lesson_count<2 or homework_count),
                'notes':notes,'missingKnowledgeIds':missing,'unsupportedCourses':gaps,'sourceCutoffAt':now}),
            'policy_json':canonical(POLICY),'created_at':now,'started_at':None,'completed_at':None,'updated_at':now}
        self.repository.create(conn,run,chosen,'learning_review_scheduler',preferences['timezone'])
        if status in TERMINAL:self.repository.task_status(conn,run,'cancelled',now)
        return run

    def tick(self,now=None):
        now=self.clock() if now is None else now
        results=[]
        with self.repository.transaction() as conn:
            children=conn.execute("SELECT id,family_id FROM children WHERE grade_code LIKE 'primary_%'").fetchall()
        for identity in children:
            with self.repository.transaction() as conn:
                child=self.repository.child(conn,identity['family_id'],identity['id'])
                run=self.ensure_week(conn,child,now)
                if run:
                    self._remind(conn,child,run,now)
                    results.append({'id':run['id'],'status':run['status'],'reminderStatus':run['reminder_status']})
        return {'ok':True,'reviews':results}

    def _remind(self,conn,child,run,now):
        if synthetic_fixture(run):
            return
        if run['status']!='scheduled' or run['reminder_status']!='pending' or now<run['scheduled_at']:
            return
        if now>run['reminder_expires_at']:
            self.repository.update(conn,run,now,reminder_status='expired',status='needs_schedule')
            return
        preferences=self._preferences(conn,child)
        if self._paused(preferences,now) or not preferences['enabled']:
            return
        local=local_at(now,preferences)
        if not preferences['allowedStart']<=local.strftime('%H:%M')<preferences['allowedEnd']:
            return
        previous=conn.execute('SELECT status FROM learning_review_reminders WHERE run_id=? AND appointment_revision=?',
            (run['id'],run['appointment_revision'])).fetchone()
        if previous:return
        count=conn.execute('SELECT COUNT(*) AS n FROM learning_review_reminders m JOIN learning_review_runs r ON r.id=m.run_id WHERE r.family_id=? AND r.child_id=? AND m.local_day=?',
            (child['family_id'],child['id'],local.date().isoformat())).fetchone()['n']
        reason=None
        if not preferences['reminderEnabled'] or count>=preferences['dailyReminderLimit']:reason='silent_limit'
        from repositories.profile_repository import ProfileRepository
        from services.setting_policy import setting_value
        profile=ProfileRepository(self.repository.database)
        settings={key:setting_value(profile.get_setting(conn,family_id=child['family_id'],key=key),key)
                  for key in ('ai-care-rules','privacy','notifications','conversation')}
        if not settings['ai-care-rules']['voiceReminderEnabled'] or not settings['privacy']['voiceBroadcastAuthorized']:
            reason='silent_disabled'
        notice=settings['notifications']
        clock=local.strftime('%H:%M')
        start,end=notice['quietHoursStart'],notice['quietHoursEnd']
        quiet=(start<=clock<end) if start<end else (clock>=start or clock<end)
        if notice['quietHoursEnabled'] and quiet:reason='silent_quiet'
        # Sleep/voice arbitration belongs to the bounded sender. Bare camera
        # speak is never a valid fallback, because it may interrupt care/teaching.
        if self.reminder_sender is None:reason='silent_unsupported'
        if reason:
            self.repository.update(conn,run,now,reminder_status=reason)
            return
        conn.execute('INSERT INTO learning_review_reminders(run_id,appointment_revision,local_day,status,attempted_at) VALUES (?,?,?,\'claimed\',?)',
            (run['id'],run['appointment_revision'],local.date().isoformat(),now))
        text=f'有一个大约{max(1,round(run["estimated_seconds"]/60))}分钟的小复习，现在开始，还是晚一点？'
        try:
            receipt=self.reminder_sender(family_id=child['family_id'],child_id=child['id'],task_id=run['task_id'],
                request_id=f'{run["id"]}:{run["appointment_revision"]}',appointment_revision=run['appointment_revision'],
                expires_at=run['reminder_expires_at'],non_preemptive=True,text=text)
            status='delivered' if isinstance(receipt,dict) and receipt.get('delivered') is True else 'not_delivered'
        except Exception:
            # An ambiguous device response must not trigger paid replay.
            receipt={'reason':'delivery_unknown'}
            status='delivery_unknown'
        conn.execute('UPDATE learning_review_reminders SET status=?,receipt_json=? WHERE run_id=? AND appointment_revision=?',
            (status,canonical(receipt),run['id'],run['appointment_revision']))
        self.repository.update(conn,run,now,reminder_status=status)
