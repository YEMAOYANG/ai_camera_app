"""One append-only evidence boundary for classroom, review and private homework.

Call inside the source's transaction. A repeated event must be byte-identical;
corrections revoke evidence rather than rewriting a child's first response.
"""
from collections import defaultdict
import hashlib
import json

from core.errors import ApiError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def enabled():
    from flask import current_app, has_app_context
    return has_app_context() and bool(current_app.config.get('LEARNING_REVIEW_ENABLED', False))


def event_id(family_id, child_id, source_kind, source_id, event_key):
    return digest([family_id, child_id, source_kind, source_id, event_key])


def record_answer(conn, *, family_id, child_id, source_kind, source_id, event_key,
                  question, answer, correct, occurred_at, attempt=1, hint_used=None,
                  adult_help=None, independent=None, confidence=None, confirmed=True, diagnosis=None):
    if source_kind not in ('classroom', 'textbook_play', 'practice', 'homework', 'review'):
        raise ValueError('Unsupported evidence source')
    if (not isinstance(question, dict) or not all(question.get(k) for k in
            ('id', 'subject', 'gradeCode', 'knowledgeId', 'knowledgeLabel'))
            or type(attempt) is not int or attempt < 1 or type(occurred_at) is not int):
        raise ValueError('Evidence requires a stable question and knowledge identity')
    if any(value is not None and type(value) is not bool for value in
           (correct, hint_used, adult_help, independent)) or type(confirmed) is not bool:
        raise ValueError('Evidence outcomes must be boolean or unknown')
    if confidence is not None and (type(confidence) not in (int, float) or not 0 <= confidence <= 1):
        raise ValueError('Invalid evidence confidence')
    from services.learning_knowledge import canonical_knowledge,MATH_ID
    mapping=canonical_knowledge(question,subject=question['subject'],grade=question['gradeCode'])
    if mapping:
        changed=question['knowledgeId']!=mapping[0]
        question={**question,'knowledgeId':mapping[0],'knowledgeLabel':mapping[1]}
        if changed:
            question.pop('fingerprint',None)
    elif MATH_ID.fullmatch(str(question['knowledgeId'])):
        # A canonical-looking but contradictory/other-grade identifier is not
        # permission to contaminate another skill's consolidated evidence.
        question={**question,'knowledgeId':f"{question['subject']}:{question['gradeCode']}:unmapped:{digest([source_kind,source_id,question['id']])[:24]}",
                  'knowledgeLabel':'待确认知识点'}
        question.pop('fingerprint',None)
    # A photo can support correctness, never unaided performance.
    if source_kind == 'homework':
        independent = None
    elif hint_used or adult_help or attempt > 1:
        independent = False
    elif independent is True and (hint_used is None or adult_help is None):
        independent = None
    fingerprint = question.get('fingerprint') or digest({k: question.get(k) for k in
        ('knowledgeId', 'prompt', 'options', 'correctAnswer', 'visual')})
    value = dict(family_id=family_id, child_id=child_id, source_kind=source_kind,
        source_id=source_id, event_key=event_key, knowledge_id=question['knowledgeId'],
        knowledge_label=question['knowledgeLabel'], subject=question['subject'],
        grade_code=question['gradeCode'], question_fingerprint=fingerprint,
        question_json=canonical(question), answer_json=canonical(answer),
        correct=None if correct is None else int(correct), independent=None if independent is None else int(independent),
        hint_used=None if hint_used is None else int(hint_used), adult_help=None if adult_help is None else int(adult_help),
        attempt=attempt, confirmed=int(confirmed), confidence=confidence,
        diagnosis_json=canonical(diagnosis), occurred_at=occurred_at)
    identifier = event_id(family_id, child_id, source_kind, source_id, event_key)
    payload_hash = digest(value)
    # Serialize source adapters and review scheduling on the child's existing row.
    child = conn.execute('SELECT id FROM children WHERE id=? AND family_id=? FOR UPDATE', (child_id, family_id)).fetchone()
    if child is None:
        raise ApiError('child_not_found', '没有找到孩子', 404)
    row = conn.execute('SELECT * FROM learning_answer_events WHERE id=?', (identifier,)).fetchone()
    if row:
        if row['payload_sha256'] != payload_hash:
            raise ApiError('learning_evidence_conflict', '这条作答已保存，更正需要新的版本', 409)
        return dict(row)
    value = {'id': identifier, **value, 'payload_sha256': payload_hash}
    conn.execute('INSERT INTO learning_answer_events(' + ','.join(value) + ') VALUES (' + ','.join('?' for _ in value) + ')', tuple(value.values()))
    return value


def revoke_source(conn, *, family_id, child_id, source_kind, source_id, now, reason, purge=False):
    conn.execute('SELECT id FROM children WHERE id=? AND family_id=? FOR UPDATE', (child_id, family_id))
    identifiers = {row['id'] for row in conn.execute('SELECT id FROM learning_answer_events WHERE family_id=? AND child_id=? AND source_kind=? AND source_id=?',
        (family_id,child_id,source_kind,source_id)).fetchall()}
    _withdraw_review_sources(conn, family_id, child_id, identifiers, now, reason)
    conn.execute('UPDATE learning_answer_events SET revoked_at=?,revoke_reason=? WHERE family_id=? AND child_id=? '
        'AND source_kind=? AND source_id=? AND revoked_at IS NULL', (now, reason[:255], family_id, child_id, source_kind, source_id))

    if purge:
        conn.execute("UPDATE learning_answer_events SET question_json='{}',answer_json='null',diagnosis_json='null' WHERE family_id=? AND child_id=? AND source_kind=? AND source_id=?",
                     (family_id,child_id,source_kind,source_id))


def revoke_event(conn, *, family_id, child_id, source_kind, source_id, event_key, now, reason, purge=False):
    conn.execute('SELECT id FROM children WHERE id=? AND family_id=? FOR UPDATE', (child_id, family_id))
    identifier = event_id(family_id, child_id, source_kind, source_id, event_key)
    _withdraw_review_sources(conn, family_id, child_id, {identifier}, now, reason)
    conn.execute('UPDATE learning_answer_events SET revoked_at=?,revoke_reason=? WHERE id=? AND revoked_at IS NULL',
                 (now, reason[:255], identifier))

    if purge:
        conn.execute("UPDATE learning_answer_events SET question_json='{}',answer_json='null',diagnosis_json='null' WHERE id=?",(identifier,))


def _withdraw_review_sources(conn, family_id, child_id, identifiers, now, reason):
    """Withdraw frozen private questions and derived marks in the same transaction.

    A corrected/deleted photo must never survive as an answer-bearing snapshot,
    playable narration or a new assessment in another domain. Source evidence
    retains its own audit policy; downstream snapshots keep only a tombstone.
    """
    if not identifiers:
        return
    from repositories.learning_review_repository import LearningReviewRepository
    repository = LearningReviewRepository(None)
    runs = conn.execute('SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? FOR UPDATE',
                        (family_id,child_id)).fetchall()
    for row in runs:
        run = dict(row)
        items = repository.items(conn,run['id'])
        changed = False
        for item in items:
            question = json.loads(item['snapshot_json']) if isinstance(item['snapshot_json'],str) else item['snapshot_json']
            if not question.get('private') or question.get('sourceEventId') not in identifiers:
                continue
            tombstone = {'private':True,'withdrawn':True,'sourceEventId':question['sourceEventId']}
            conn.execute("UPDATE learning_review_items SET snapshot_json=?,snapshot_sha256=?,evidence_mode='withdrawn',answer_json=NULL,answer_sha256=NULL,feedback_json=NULL,answered_at=NULL WHERE run_id=? AND ordinal=?",
                         (canonical(tombstone),digest(tombstone),run['id'],item['ordinal']))
            conn.execute("UPDATE learning_answer_events SET revoked_at=?,revoke_reason=?,question_json='{}',answer_json='null',diagnosis_json='null' WHERE family_id=? AND child_id=? AND source_kind='review' AND source_id=? AND event_key=?",
                         (now,reason[:255],family_id,child_id,run['id'],item['question_id']))
            changed = True
        if not changed:
            continue
        remaining = repository.items(conn,run['id'])
        feedback = [json.loads(i['feedback_json']) if isinstance(i['feedback_json'],str) else i['feedback_json']
                    for i in remaining if i['answered_at'] and i['evidence_mode']!='withdrawn']
        coverage = json.loads(run['coverage_json']) if isinstance(run['coverage_json'],str) else run['coverage_json']
        coverage['contentGap'] = True
        note = '照片题已更正或删除，对应复习题和评分已撤回；不计为答错。'
        coverage['notes'] = list(dict.fromkeys([*coverage.get('notes',[]),note]))
        terminal = run['status'] in ('completed','skipped','superseded','rest','content_gap')
        conn.execute('UPDATE learning_review_runs SET status=?,revision=revision+1,appointment_revision=appointment_revision+1,reminder_status=?,correct_count=?,independent_correct_count=?,coverage_json=?,updated_at=? WHERE id=?',
                     (run['status'] if terminal else 'content_gap','invalidated',sum(bool(f['correct']) for f in feedback),
                      sum(bool(f['correct'] and f['independent']) for f in feedback),canonical(coverage),now,run['id']))
        if not terminal:
            repository.task_status(conn,run,'cancelled',now)


def weaknesses(conn, *, family_id, child_id, since=0, until=None):
    params = [family_id, child_id, since]
    sql = 'SELECT * FROM learning_answer_events WHERE family_id=? AND child_id=? AND occurred_at>=? AND revoked_at IS NULL'
    if until is not None:
        sql += ' AND occurred_at<?'
        params.append(until)
    rows = conn.execute(sql + ' ORDER BY occurred_at,id', params).fetchall()
    if any(row['source_kind'] in {'homework','review'} for row in rows):
        from services.homework_evidence_guard import current_homework_events
        rows=current_homework_events(conn,rows)
    groups = defaultdict(list)
    for row in rows:
        groups[row['knowledge_id']].append(dict(row))
    result = []
    for knowledge, items in groups.items():
        # Repeated answers on the same paper/session are practice, not new samples.
        first = {}
        for item in items:
            if item['confirmed'] and item['correct'] is not None and item['attempt'] == 1:
                first.setdefault((item['source_kind'], item['source_id'], item['question_fingerprint']), item)
        valid = list(first.values())
        wrong = [i for i in valid if not i['correct']]
        independent = [i for i in valid if i['independent'] == 1]
        assisted = [i for i in valid if i['hint_used'] or i['adult_help']]
        recent = valid[-5:]
        # Consolidated is deliberately modest: two different unseen independent
        # transfer items after the latest difficulty. It never changes mastery.
        last_problem = max((i['occurred_at'] for i in wrong + assisted), default=0)
        improved = {i['question_fingerprint'] for i in independent if i['correct'] and i['occurred_at'] > last_problem}
        status = 'consolidated' if last_problem and len(improved) >= 2 else 'needs_review' if wrong or assisted else 'observing'
        example = (wrong or assisted or valid or items)[-1]
        question = json.loads(example['question_json'])
        result.append({'knowledgeId': knowledge, 'label': items[-1]['knowledge_label'],
            'subject': items[-1]['subject'], 'gradeCode': items[-1]['grade_code'], 'status': status,
            'sampleCount': len(valid), 'wrongCount': len(wrong), 'helpCount': len(assisted),
            'independentCount': len(independent), 'independentCorrect': sum(i['correct'] for i in independent),
            'pendingCount': sum(not i['confirmed'] or i['correct'] is None for i in items),
            'recentWrongCount': sum(not i['correct'] for i in recent), 'lastOccurredAt': items[-1]['occurred_at'],
            'sources': sorted({i['source_kind'] for i in items}),
            'example': {'eventId': example['id'], 'sourceId': example['source_id'], 'source': example['source_kind'],
                'question': question, 'answer': json.loads(example['answer_json']), 'correct': example['correct'],
                'occurredAt': example['occurred_at'], 'diagnosis': json.loads(example['diagnosis_json'] or 'null')},
            'nextStep': '先按语音完成系统安排的短复习，家长仅在孩子求助时确认题意。' if status == 'needs_review' else
                        '继续观察新的独立作答；当前证据不等于完整能力评估。'})
    return sorted(result, key=lambda item: (item['status'] != 'needs_review', -item['recentWrongCount'], -item['lastOccurredAt']))


def record_course_answers(conn, session, course, questions, answers, now, *, source_kind='classroom'):
    """Adapter for trusted server evaluation. Unknown historic help stays unknown."""
    if not enabled():
        return
    indexed = {str(q['id']): q for q in questions}
    content = json.loads(course.get('content_json') or '{}') if isinstance(course.get('content_json'), str) else course.get('content_json') or {}
    independent_ids = set((content.get('teachingFlow') or {}).get('independentQuestionIds') or [])
    independent_ids.update(s.get('questionId') for s in content.get('progressiveFlow', []) if s.get('phase')=='independent')
    for record in answers:
        raw = indexed.get(str(record.get('questionId')))
        if raw is None or type(record.get('correct')) is not bool:
            continue
        question = {'id':raw['id'],'version':course['version'],'subject':course['subject'],'gradeCode':course['grade_code'],
            'knowledgeId': str(raw.get('knowledgeId') or ':'.join((course['subject'],course['grade_code'],str(course.get('node_code') or course['id']),str(raw.get('skill') or raw['id'])))),
            'knowledgeLabel':str(raw.get('skill') or course.get('objective') or course['title']),
            'courseId':course['id'],'courseVersion':course['version'],'courseTitle':course['title'],
            'type':raw.get('type'),'evaluation':raw.get('evaluation'),
            'prompt':raw.get('prompt') or raw.get('question') or raw.get('stem'), 'options':raw.get('options'),
            'correctAnswer':raw.get('answer'),'explanation':raw.get('explanation'),'private':False}
        attempt = int(record.get('attemptNumber') or 1)
        hint = record.get('hintUsedBeforeAnswer', record.get('hintUsed'))
        if record.get('hintCountBeforeAnswer') is not None:
            hint = bool(record['hintCountBeforeAnswer'])
        adult = record.get('adultHelp')
        independent = record.get('independent')
        if raw['id'] not in independent_ids:
            independent = False
        record_answer(conn,family_id=session['family_id'],child_id=session['child_id'],source_kind=source_kind,
            source_id=session['id'],event_key=str(raw['id'])+':'+str(attempt),question=question,
            answer=record.get('normalizedResponse',record.get('answer')),correct=record['correct'],
            occurred_at=int(record.get('answeredAt') or now),attempt=attempt,hint_used=hint,adult_help=adult,independent=independent)


def record_textbook_changes(conn, session, course, state, previous, release):
    if not enabled():
        return
    from content import textbook_journey as journey
    from services.learning_review_questions import authored_question, knowledge_id
    spec = journey.definition(state=state, release=release)
    for section_name in ('games','challenge'):
        old = previous.get(section_name, {}).get('records', [])
        old_keys = {(r['phase'],r['index'],r['round']) for r in old} if previous.get('run')==state.get('run') else set()
        for record in state[section_name]['records']:
            key=(record['phase'],record['index'],record['round'])
            if key in old_keys:
                continue
            skill=record['skill']
            raw=next((q for q in spec.flow['bank'][skill] if q['id']==record['questionId']),None)
            if raw:
                question=authored_question(spec,course,skill,raw,verify_audio=False)
            else:
                question={'id':record['questionId'],'version':spec.plan['releaseSha256'],'subject':course['subject'],
                    'gradeCode':course['grade_code'],'knowledgeId':knowledge_id(course,skill,spec.plan['id']),
                    'knowledgeLabel':spec.plan['skills'][skill].get('name') or spec.plan['skills'][skill]['word'],
                    'courseId':course['id'],'courseVersion':course['version'],'courseTitle':course['title'],
                    'prompt':spec.plan['skills'][skill]['word'],'explanation':spec.plan['skills'][skill]['explanation'],'private':False}
            # Each practice encounter has its own key; unknown retries never
            # erase the first choice retained in the authored activity state.
            event_key=':'.join(map(str,(state.get('run',0),section_name,*key)))
            record_answer(conn,family_id=session['family_id'],child_id=session['child_id'],source_kind='textbook_play',
                source_id=session['id'],event_key=event_key,question=question,answer=record['choice'],correct=record['correct'],
                occurred_at=state['updatedAt'],hint_used=bool(record.get('hintUsed')),adult_help=bool(record.get('adultHelp')),
                independent=(not record.get('hintUsed') and not record.get('adultHelp')) if record['phase'] in ('diagnostic','transfer','probe') else False,
                diagnosis=state.get('diagnoses',{}).get(skill))
