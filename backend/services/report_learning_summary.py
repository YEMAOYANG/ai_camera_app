"""Read course evidence into family reports; keep daily snapshots in the session."""
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
from zoneinfo import ZoneInfo

from content import textbook_journey as journey
from services.learning_coaching_service import coaching_summary, public_coaching

ZONE = ZoneInfo('Asia/Shanghai')
LABELS = {'learning': '正在学习', 'checking': '正在独立验证', 'reviewing': '正在复习',
          'needs_support': '需要家长留意', 'session_passed': '本轮独立通过',
          'retained': '间隔复习通过'}


def _day(timestamp):
    return datetime.fromtimestamp(timestamp / 1000, ZONE).date().isoformat()


def _object(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or '{}')
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def _transfer_evidence(records, *, first=False, skills=None):
    selected = {}
    for record in records:
        if record.get('phase') != 'transfer' or record.get('skill') not in (skills if skills is not None else journey.SKILLS):
            continue
        if not first or record['skill'] not in selected:
            selected[record['skill']] = record
    if not selected:
        return None
    return {'correct': sum(journey.independent(r) for r in selected.values()), 'total': len(selected),
            'detail': ('间隔复习首次作答，提示或家长帮助不计独立通过。' if first else
                       '图片支持下的新情境独立作答，不代表独立识字、朗读或书写。')}


def _journey_assessment(state):
    evidence = {}
    at = state.get('updatedAt')
    if not at:
        return evidence
    baseline = state.get('baseline', [])
    if state.get('baselineRecordedAt') and len(baseline) == len(journey.skills_for(state)):
        evidence['independence'] = {'correct': sum(journey.independent(r) for r in baseline),
            'total': len(baseline), 'recordDate': _day(state['baselineRecordedAt']),
            'detail': '首次练习独立答对比例；使用提示或家长帮助的题目不计独立答对。'}
    transfer = _transfer_evidence(state.get('challenge', {}).get('records', []), skills=journey.skills_for(state))
    if transfer:
        evidence['comprehension'] = {**transfer, 'recordDate': _day(at)}
    if state.get('reviewActive'):
        retention = _transfer_evidence(state.get('challenge', {}).get('records', []), first=True, skills=journey.skills_for(state))
        if retention:
            evidence['retention'] = {**retention, 'recordDate': _day(at)}
    else:
        completed = [r for r in state.get('reviewHistory', []) if r.get('completedAt', 0) <= at]
        if completed:
            review = max(completed, key=lambda r: r['completedAt'])
            retention = _transfer_evidence(review.get('records', []), first=True, skills=journey.skills_for(state))
            if retention:
                evidence['retention'] = {**retention, 'recordDate': _day(review['completedAt'])}
    return evidence


def journey_snapshot(state):
    at = state.get('updatedAt')
    info = journey.summary(state, timestamp=at)
    baseline = state['baseline']
    return {'kind': 'textbook', 'observedAt': at, 'status': info['status'],
        'statusLabel': LABELS.get(info['status'], '正在学习'), 'needsSupport': info['parentNeeded'],
        'evidenceLabel': '图片支持下的情境理解',
        'baseline': {'correct': info['independentBefore'], 'total': len(baseline),
                     'hints': sum(bool(r.get('hintUsed')) for r in baseline),
                     'adultHelp': sum(bool(r.get('adultHelp')) for r in baseline)},
        'verification': {'correct': info['verifiedCount'], 'total': len(journey.skills_for(state))},
        'remainingSkills': info['remainingSkills'], 'diagnoses': info['diagnoses'],
        'nextStep': info['nextStep'], 'reviewDueAt': info['reviewDueAt'], 'reviewLevel': info['reviewLevel'],
        'assessmentEvidence': _journey_assessment(state), 'parentSupport': info.get('parentSupport')}


def save_journey_report_day(state, previous):
    """Called inside the existing answer transaction; never changes the first score."""
    days = state.setdefault('reportDays', {})
    if (len(state.get('baseline', [])) == len(journey.skills_for(state))
            and len(previous.get('baseline', [])) < len(journey.skills_for(state)) and state.get('updatedAt')):
        state.setdefault('baselineRecordedAt', state['updatedAt'])
    # Preserve the last known day when upgrading an existing, unfinished session.
    if previous.get('updatedAt'):
        days.setdefault(_day(previous['updatedAt']), journey_snapshot(previous))
    if state.get('updatedAt'):
        days[_day(state['updatedAt'])] = journey_snapshot(state)


def _initial_report(row, *, adaptive=False):
    return {'kind': 'textbook' if adaptive else 'course', 'observedAt': row['report_created_at'],
        'status': 'initial_practice' if adaptive else row['mastery_level'],
        'statusLabel': '首次练习记录' if adaptive else '课程练习结果',
        'needsSupport': False,
        'evidenceLabel': '图片支持下的情境理解' if adaptive else '课程作答记录',
        'baseline': {'correct': row['independent_correct_count'], 'total': row['total_questions'],
                     'hints': row['hint_count'], 'adultHelp': None},
        'verification': None, 'remainingSkills': [], 'diagnoses': [],
        'nextStep': '早期记录仅展示首次练习，不将后续复习结果回填到当天。' if adaptive else row['next_step'],
        'reviewDueAt': None, 'reviewLevel': 0}


def learning_for_period(conn, *, family_id, start_date, end_date):
    start = int(datetime.combine(date.fromisoformat(start_date), time.min, ZONE).timestamp() * 1000)
    end = int(datetime.combine(date.fromisoformat(end_date) + timedelta(days=1), time.min, ZONE).timestamp() * 1000)
    rows = conn.execute('''SELECT s.id,s.child_id,s.course_id,s.course_version,s.runtime_state_json,
        c.title,c.subject,ch.nickname AS child_name,r.id AS report_id,r.learning_date,
        r.created_at AS report_created_at,r.independent_correct_count,r.total_questions,r.hint_count,
        r.mastery_level,r.next_step
        FROM learning_sessions s
        JOIN children ch ON ch.id=s.child_id AND ch.family_id=s.family_id
        JOIN learning_courses c ON c.id=s.course_id AND c.version=s.course_version
        LEFT JOIN learning_reports r ON r.session_id=s.id AND r.family_id=s.family_id
          AND r.child_id=s.child_id AND r.task_id=s.task_id
          AND r.course_id=s.course_id AND r.course_version=s.course_version
        WHERE s.family_id=? AND s.started_at<?
          AND (s.updated_at>=? OR (r.created_at>=? AND r.created_at<?))''',
        (family_id, end, start, start, end)).fetchall()
    lessons = {}
    reviews = set()
    coaching_records = {}
    for row in rows:
        runtime = _object(row['runtime_state_json'])
        state = _object(runtime.get('textbookPlay'))
        coaching = _object(runtime.get('parentCoaching'))
        for day, record in coaching.items():
            if start_date <= day <= end_date and isinstance(record, dict):
                coaching_records[(row['id'], day)] = record
        adaptive = state.get('flowVersion') == 2
        candidates = []
        if adaptive:
            days = _object(state.get('reportDays'))
            candidates = [deepcopy(value) for day, value in days.items()
                          if start_date <= day <= end_date and isinstance(value, dict)]
            # Existing data can expose its actual last saved day, never a made-up past snapshot.
            at = state.get('updatedAt')
            if at and start <= at < end and _day(at) not in days:
                candidates.append(journey_snapshot(state))
            for review in state.get('reviewHistory', []):
                at = review.get('completedAt', 0)
                if start <= at < end:
                    reviews.add((row['id'], review['level']))
                    if _day(at) not in days:
                        candidates.append({'kind': 'textbook', 'observedAt': at,
                            'status': 'review_passed', 'statusLabel': '本次间隔复习通过',
                            'needsSupport': False, 'evidenceLabel': '图片支持下的情境理解',
                            'baseline': None, 'verification': {'correct': len(review['independentSkills']),
                                                              'total': len(journey.skills_for(state))},
                            'remainingSkills': [], 'diagnoses': [], 'nextStep': '',
                            'reviewDueAt': None, 'reviewLevel': review['level'] + 1})
        if not candidates and row['report_id'] and start <= row['report_created_at'] < end:
            candidates.append(_initial_report(row, adaptive=adaptive))
        if not candidates:
            continue
        latest = max(candidates, key=lambda item: item.get('observedAt') or 0)
        assessment = deepcopy(latest.get('assessmentEvidence') or {})
        # Older snapshots can only be augmented with contemporaneous evidence.
        if adaptive and latest.get('observedAt') == state.get('updatedAt'):
            assessment.update(_journey_assessment(state))
        if row['report_id'] and row['total_questions']:
            assessment.setdefault('independence', {
                'correct': row['independent_correct_count'], 'total': row['total_questions'],
                'recordDate': _day(row['report_created_at']),
                'detail': '首次练习独立答对比例，使用提示的题目不计独立答对。'})
        if (adaptive and latest.get('status') in ('session_passed', 'retained', 'needs_support', 'review_passed')
                and latest.get('verification')):
            assessment.setdefault('comprehension', {**latest['verification'],
                'recordDate': _day(latest['observedAt']), 'detail': '图片支持下的新情境独立验证。'})
        # Completed review records have their own timestamp, even in older sessions.
        completed = [r for r in state.get('reviewHistory', [])
                     if start <= r.get('completedAt', 0) <= (latest.get('observedAt') or 0)]
        if completed and 'retention' not in assessment:
            review = max(completed, key=lambda r: r['completedAt'])
            metric = _transfer_evidence(review.get('records', []), first=True, skills=journey.skills_for(state))
            if metric:
                assessment['retention'] = {**metric, 'recordDate': _day(review['completedAt'])}
        item = {**latest, 'assessmentEvidence': assessment,
                'courseTitle': row['title'], 'courseId': row['course_id'], 'courseVersion': row['course_version'], 'subject': row['subject'],
                'childName': row['child_name'], 'childId': row['child_id'], 'reportId': row['report_id'],
                'recordDate': _day(latest['observedAt']), 'learningSessionId': row['id'],
                'coaching': public_coaching(coaching.get(_day(latest['observedAt'])))}
        if adaptive and latest.get('observedAt') == state.get('updatedAt'):
            item['parentSupport'] = journey.parent_support(state)
        identity = (row['child_id'], row['course_id'], row['course_version'])
        if identity not in lessons or item['observedAt'] > lessons[identity]['observedAt']:
            lessons[identity] = item
    items = sorted(lessons.values(), key=lambda item: (not item['needsSupport'], -item['observedAt']))
    return {'schemaVersion': 'mira.report.learning.v1', 'lessonCount': len(items),
            'needsSupportCount': sum(item['needsSupport'] for item in items),
            'reviewCount': len(reviews), 'lessons': items, 'coachingSummary': coaching_summary(coaching_records)}
