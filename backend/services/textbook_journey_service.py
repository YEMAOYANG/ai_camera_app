"""Persist follow-up tasks and parent evidence in the existing learning domain."""
from datetime import datetime
import hashlib
from zoneinfo import ZoneInfo

from content import textbook_journey as journey
from content.textbook_catalog import canonical
from core.security import now_ms
from services.report_learning_summary import save_journey_report_day


def sync_journey(conn, learning, session, child, course, state, previous):
    now = now_ms()
    info = journey.summary(state, timestamp=now)
    before_task = previous.get('reviewTaskId')
    if len(state['reviewHistory']) > len(previous.get('reviewHistory', [])) and before_task:
        learning.mark_task_completed(conn, family_id=child['family_id'], task_id=before_task,
                                     summary='独立通过本轮间隔复习。', now=now)
        state['reviewTaskId'] = None
    if state.get('reviewActive') and state.get('reviewTaskId'):
        learning.mark_task_in_progress(conn, family_id=child['family_id'], task_id=state['reviewTaskId'], now=now)
    due = state.get('reviewDueAt')
    if due and not state.get('reviewActive') and not state.get('reviewTaskId'):
        local_due = datetime.fromtimestamp(due / 1000, ZoneInfo('Asia/Shanghai'))
        key = hashlib.sha256(f'textbook-review\n{session["id"]}\n{state["reviewLevel"]}'.encode()).hexdigest()
        original = learning.get_task(conn, family_id=child['family_id'], task_id=session['task_id'])
        task, _ = learning._insert_learning_task(conn, family_id=child['family_id'], child_id=child['id'],
            learning_date=local_due.date().isoformat(), slot='tbr_' + key[:24],
            scheduled_start=local_due.strftime('%H:%M'), course={**course, 'title': course['title'] + ' · 短复习',
                'objective': '换一个情境，独立试一试。系统只补练仍需帮助的字。'},
            created_by=original['created_by'], now=now, assignment_key=key)
        state['reviewTaskId'] = task['id']
        conn.execute('UPDATE tasks SET due_at=?,updated_at=? WHERE id=? AND family_id=?',
                     (local_due.isoformat(), now, task['id'], child['family_id']))
    save_journey_report_day(state, previous)
    if len(state['baseline']) == 6:
        stage = ('两轮间隔复习均已通过' if info['status'] == 'retained' else
                 '本次独立复核通过，等待间隔复习' if state['challenge']['phase'] == 'done' else
                 '连续补练后仍需帮助，建议休息后家长陪同确认题意' if info['parentNeeded'] else '正在自主学习')
        message = (f'《{course["title"]}》图片支持下的情境理解：前测独立答对 {info["independentBefore"]}/6，'
                   f'本轮新情境独立通过 {info["verifiedCount"]}/6；{stage}。')
        if info['remainingSkills'] and info['parentNeeded']:
            message += '仍需练习：' + '、'.join(info['remainingSkills']) + '。'
        next_step = info['nextStep']
        if due:
            next_step += ' 下次复习：' + datetime.fromtimestamp(due / 1000, ZoneInfo('Asia/Shanghai')).strftime('%m月%d日 %H:%M') + '。'
        conn.execute('UPDATE learning_reports SET summary=?,next_step=?,mastery_level=?,strengths_json=? '
                     'WHERE family_id=? AND session_id=?',
            (message, next_step, 'mastered' if info['status'] == 'retained' else 'developing',
             canonical([journey.PLAN['skills'][skill]['word'] + '：本轮新情境独立通过' for skill in state['verified']]), child['family_id'], session['id']))


def catalog_journeys(repository, conn, child, books, visible_courses):
    selected = {(b['editionId'], b['revisionId']) for b in books if b['selected']}
    if not selected:
        return []
    rows = conn.execute('SELECT session.*,build.content_key,build.edition_id,build.revision_id,course.content_json '
        'FROM learning_sessions session JOIN learning_textbook_course_builds build '
        'ON build.course_id=session.course_id AND build.course_version=session.course_version '
        'JOIN learning_courses course ON course.id=session.course_id AND course.version=session.course_version '
        "WHERE session.family_id=? AND session.child_id=? AND build.status='published'",
        (child['family_id'], child['id'])).fetchall()
    result = []
    for row in rows:
        if ((row['edition_id'], row['revision_id']) not in selected
                or (row['course_id'], row['course_version']) not in visible_courses):
            continue
        progress = repository.parse(row.get('runtime_state_json')) or {}
        state = progress.get('textbookPlay') or {}
        if state.get('flowVersion') != 2:
            continue
        result.append({**journey.summary(state), 'title': (repository.parse(row['content_json']) or {}).get('title', '教材课'), 'contentKey': row['content_key']})
    result.sort(key=lambda item: (not item['parentNeeded'], not item['reviewDue'], -(item.get('updatedAt') or 0)))
    return result
