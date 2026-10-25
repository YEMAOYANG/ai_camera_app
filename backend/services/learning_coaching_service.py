"""Optional parent-reported effort, separate from a child's learning evidence.

One versioned record per session/day in the existing runtime JSON. Neither a
missing record nor a child's help-button count means zero parent effort.
"""
from datetime import date, datetime
import json
from zoneinfo import ZoneInfo

from content.textbook_catalog import canonical
from core.errors import ApiError
from core.security import now_ms

ZONE = ZoneInfo('Asia/Shanghai')
REASONS = ('none', 'navigation', 'understanding', 'technical', 'company', 'other')


def object_value(raw):
    value = json.loads(raw or '{}') if isinstance(raw, str) else raw
    return value if isinstance(value, dict) else {}


def day_of(at):
    return datetime.fromtimestamp(at / 1000, ZONE).date().isoformat()


def validate_date(value):
    if not isinstance(value, str):
        raise ApiError('coaching_invalid', '请选择学习记录的日期', 400)
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise ApiError('coaching_invalid', '学习日期无效', 400)
    return value


def save_coaching(conn, *, family_id, user_id, session_id, data=None, record_date=None):
    if data is not None:
        if not isinstance(data, dict) or set(data) != {'recordDate', 'minutes', 'usualMinutes', 'reason', 'revision'}:
            raise ApiError('coaching_invalid', '辅导记录字段无效', 400)
        record_date = data['recordDate']
        if (type(data['minutes']) is not int or not 0 <= data['minutes'] <= 180
                or (data['usualMinutes'] is not None and
                    (type(data['usualMinutes']) is not int or not 0 <= data['usualMinutes'] <= 180))
                or data['reason'] not in REASONS or type(data['revision']) is not int or data['revision'] < 0
                or (data['minutes'] == 0) != (data['reason'] == 'none')):
            raise ApiError('coaching_invalid', '请填写 0—180 分钟；没有辅导时选择“没有介入”', 400)
    record_date = validate_date(record_date)
    row = conn.execute('SELECT s.id,s.runtime_state_json,s.started_at,r.created_at AS report_created_at '
        'FROM learning_sessions s LEFT JOIN learning_reports r ON r.session_id=s.id AND r.family_id=s.family_id '
        'AND r.child_id=s.child_id AND r.task_id=s.task_id AND r.course_id=s.course_id AND r.course_version=s.course_version '
        'WHERE s.id=? AND s.family_id=?' + (' FOR UPDATE OF s' if data is not None else ''),
        (session_id, family_id)).fetchone()
    if row is None:
        raise ApiError('learning_session_not_found', '没有找到这次学习记录', 404)
    runtime = object_value(row['runtime_state_json'])
    play = object_value(runtime.get('textbookPlay'))
    days = set(object_value(play.get('reportDays')))
    for at in (play.get('updatedAt'), row.get('report_created_at')):
        if at:
            days.add(day_of(at))
    if record_date not in days or record_date > day_of(now_ms()):
        raise ApiError('coaching_date_unavailable', '只能记录已有学习证据当天的辅导用时', 409)
    records = runtime.setdefault('parentCoaching', {})
    previous = records.get(record_date)
    if data is None:
        return {'ok': True, 'coaching': previous, 'revision': (previous or {}).get('revision', 0)}
    payload = {key: data[key] for key in ('recordDate', 'minutes', 'usualMinutes', 'reason')}
    # A repeated identical PUT after a lost response is safe and does not add time.
    if previous and all(previous.get(k) == v for k, v in payload.items()):
        return {'ok': True, 'coaching': previous, 'revision': previous['revision']}
    if data['revision'] != (previous or {}).get('revision', 0):
        raise ApiError('coaching_conflict', '家人已更新这条记录，请读取最新记录后再修改', 409)
    saved = {**payload, 'revision': data['revision'] + 1, 'source': 'parent_reported',
             'updatedAt': now_ms(), 'recordedBy': user_id}
    records[record_date] = saved
    conn.execute('UPDATE learning_sessions SET runtime_state_json=?,updated_at=? WHERE id=? AND family_id=?',
                 (canonical(runtime), saved['updatedAt'], session_id, family_id))
    return {'ok': True, 'coaching': saved, 'revision': saved['revision']}


def public_coaching(value):
    return {k: v for k, v in value.items() if k != 'recordedBy'} if value else None


def coaching_summary(records):
    values = list(records.values())
    compared = [v for v in values if v.get('usualMinutes') is not None]
    return {'source': 'parent_reported', 'recordedSessions': len(values),
            'totalMinutes': sum(v['minutes'] for v in values),
            'comparisonCount': len(compared),
            'usualMinutes': sum(v['usualMinutes'] for v in compared),
            'currentComparisonMinutes': sum(v['minutes'] for v in compared),
            'differenceMinutes': sum(v['usualMinutes'] - v['minutes'] for v in compared)}
