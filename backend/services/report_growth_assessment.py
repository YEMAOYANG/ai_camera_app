"""Dated, child-scoped growth evidence from camera outcomes and course answers.

No base points, confidence-as-ability scores, or completion-as-attention claims.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

POLICY = json.loads((Path(__file__).resolve().parents[1] / 'content/report_growth_policy.v1.json').read_text())
ZONE = ZoneInfo('Asia/Shanghai')
TASK_DIMENSIONS = {kind: dim['key'] for dim in POLICY['dimensions'] for kind in dim['taskTypes']}


def period_bounds(start_date, end_date):
    return tuple(int(datetime.combine(day, time.min, ZONE).timestamp() * 1000) for day in (
        date.fromisoformat(start_date), date.fromisoformat(end_date) + timedelta(days=1)))


def _count(value):
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0 else 0


def _evidence(source, label, correct, total, *, record_date, reference, detail=''):
    total = _count(total)
    if not total:
        return None
    return {'source': source, 'label': label, 'correct': min(_count(correct), total), 'total': total,
            'recordDate': record_date, 'referenceId': reference, 'detail': detail}


def growth_for_period(conn, *, family_id, start_date, end_date, tasks, learning):
    start, end = period_bounds(start_date, end_date)
    children = conn.execute('SELECT id,nickname FROM children WHERE family_id=? ORDER BY id', (family_id,)).fetchall()
    camera = conn.execute('''SELECT o.id,o.child_id,o.task_id,o.observed_at,o.scenario,o.source,
        b.signal_type,b.signal_value
        FROM camera_observation_events o
        JOIN children ch ON ch.id=o.child_id AND ch.family_id=o.family_id
        JOIN behavior_signals b ON b.observation_event_id=o.id AND b.family_id=o.family_id
          AND b.child_id=o.child_id AND b.device_id=o.device_id AND b.scenario=o.scenario
        WHERE o.family_id=? AND o.observed_at>=? AND o.observed_at<?
          AND o.confidence>=? AND b.confidence>=?
        ORDER BY o.observed_at,o.id''',
        (family_id, start, end, POLICY['cameraConfidenceThreshold'], POLICY['cameraConfidenceThreshold'])).fetchall()
    return build_growth_maps(children, tasks, learning.get('lessons', []), camera,
                             start_date=start_date, end_date=end_date)


def build_growth_maps(children, tasks, lessons, camera, *, start_date, end_date):
    start, end = period_bounds(start_date, end_date)
    evidence = {child['id']: defaultdict(dict) for child in children}
    # A task, its camera receipt and its parent confirmation are one sample.
    decided_tasks = set()
    for row in tasks:
        child = row.get('child_id')
        key = TASK_DIMENSIONS.get(row.get('type'))
        if child not in evidence or not key or row.get('learning_course_id') or row.get('learning_slot') == 'weekend_review':
            continue
        status = row.get('status')
        if status in ('confirmed', 'rejected'):
            observed = row.get('confirmed_at' if status == 'confirmed' else 'rejected_at')
        elif status == 'completed' and row.get('completion_source') in ('parent', 'parent_manual'):
            observed = row.get('completed_at')
        else:
            # Timer-driven camera completion and unconfirmed/missed tasks are not outcomes.
            continue
        if not observed or not start <= int(observed) < end:
            continue
        identity = (child, row['id'])
        decided_tasks.add(identity)
        detail = str(row.get('ai_observation_summary') or row.get('evidence_summary') or '')
        sample = _evidence('parent', '家长确认', int(status != 'rejected'), 1,
            record_date=datetime.fromtimestamp(int(observed) / 1000, ZONE).date().isoformat(),
            reference=row['id'], detail=f'{row.get("title") or "任务"}：{detail}')
        evidence[child][key]['task:' + row['id']] = sample
    for row in camera:
        child = row.get('child_id')
        key = POLICY['cameraCompletionSignals'].get(row.get('scenario'), {}).get(row.get('signal_type'))
        if child not in evidence or not key or row.get('source') in ('test', 'dry_run', 'mock'):
            continue
        if row.get('signal_value') not in ('observed', 'active', 'true', 'completed', 'done'):
            continue
        at = int(row.get('observed_at') or 0)
        if not start <= at < end:
            continue
        task_id = row.get('task_id')
        if (child, task_id) in decided_tasks:
            # Parent correction takes precedence; keep provenance without counting twice.
            sample = evidence[child][key].get('task:' + task_id)
            if sample:
                sample['source'] = 'camera_parent'
                sample['label'] = '摄像头观察 · 家长确认'
            continue
        day = datetime.fromtimestamp(at / 1000, ZONE).date().isoformat()
        # Continuous camera frames are one daily outcome per scenario, not many successes.
        identity = 'task:' + task_id if task_id else 'camera:' + day + ':' + row['scenario']
        evidence[child][key][identity] = _evidence('camera', '摄像头观察', 1, 1,
            record_date=day, reference=row['id'], detail='摄像头记录到收纳完成；识别置信度只用于筛选证据。')
    for lesson in lessons:
        child = lesson.get('childId')
        if child not in evidence:
            continue
        for key, metric in lesson.get('assessmentEvidence', {}).items():
            if key not in ('independence', 'comprehension', 'retention') or not isinstance(metric, dict):
                continue
            day = str(metric.get('recordDate') or '')
            if not start_date <= day <= end_date:
                continue
            identity = str(lesson.get('courseId') or lesson.get('reportId') or '') + ':' + str(lesson.get('courseVersion') or '')
            sample = _evidence('course', '课件作答', metric.get('correct'), metric.get('total'),
                record_date=day, reference=lesson.get('reportId'),
                detail=f'《{lesson["courseTitle"]}》：{metric.get("detail") or "独立作答记录"}')
            if sample:
                evidence[child][key]['course:' + identity] = sample
    result = []
    for child in children:
        skills = []
        for dim in POLICY['dimensions']:
            samples = list(evidence[child['id']][dim['key']].values())
            total = sum(s['total'] for s in samples)
            correct = sum(s['correct'] for s in samples)
            score = round(100 * correct / total) if total else None
            detail = ('本期尚无可用于这一项的直接证据。' if score is None else
                      f'本期记录 {correct}/{total}，来自 {len(samples)} 份证据。')
            if dim['key'] in ('focus', 'initiative'):
                detail = '需要直接的过程观察；完成任务或答对题目不能替代这一项的证据。'
            skills.append({'key': dim['key'], 'label': dim['label'], 'score': score, 'maxScore': 100,
                'status': 'observed' if total else 'unobserved', 'sampleCount': len(samples),
                'level': '待观察' if score is None else '本期记录', 'detail': detail,
                'evidence': samples, 'sources': list(dict.fromkeys(s['label'] for s in samples))})
        result.append({'childId': child['id'], 'childName': child['nickname'],
                       'policyVersion': POLICY['version'], 'scope': POLICY['scope'], 'skills': skills})
    return result
