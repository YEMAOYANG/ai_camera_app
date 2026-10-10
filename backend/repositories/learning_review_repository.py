"""Review transactions serialize on children; week identity never includes policy version."""
from core.errors import ApiError
from services.learning_evidence_service import canonical, digest


class LearningReviewRepository:
    def __init__(self, database):
        self.database = database

    def transaction(self):
        return self.database.transaction()

    def child(self, conn, family_id, child_id):
        row = conn.execute('SELECT * FROM children WHERE family_id=? AND id=? FOR UPDATE', (family_id, child_id)).fetchone()
        if row is None:
            raise ApiError('child_not_found', '没有找到孩子', 404)
        return dict(row)

    def run(self, conn, family_id, child_id, run_id):
        row = conn.execute('SELECT * FROM learning_review_runs WHERE family_id=? AND child_id=? AND id=? FOR UPDATE',
            (family_id, child_id, run_id)).fetchone()
        if row is None:
            raise ApiError('review_not_found', '没有找到这次复习', 404)
        return dict(row)

    def items(self, conn, run_id):
        return [dict(r) for r in conn.execute('SELECT * FROM learning_review_items WHERE run_id=? ORDER BY ordinal', (run_id,)).fetchall()]

    def request(self, conn, run, data, now):
        key = data.get('requestId')
        if not isinstance(key, str) or not 1 <= len(key) <= 128:
            raise ApiError('review_request_invalid', '请重新打开复习', 400)
        row = conn.execute('SELECT payload_sha256 FROM learning_review_requests WHERE run_id=? AND request_id=?', (run['id'], key)).fetchone()
        checksum = digest(data)
        if row:
            if row['payload_sha256'] != checksum:
                raise ApiError('review_request_conflict', '这次操作已保存，请刷新进度', 409)
            return True
        return False

    def remember(self, conn, run, data, now):
        conn.execute('INSERT INTO learning_review_requests(run_id,request_id,payload_sha256,created_at) VALUES (?,?,?,?)',
            (run['id'], data['requestId'], digest(data), now))

    def update(self, conn, run, now, **fields):
        fields.update(updated_at=now, revision=run['revision'] + 1)
        conn.execute('UPDATE learning_review_runs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', (*fields.values(), run['id']))
        run.update(fields)

    def task_status(self, conn, run, status, now):
        fields = {'status': status, 'updated_at': now, 'next_reminder_at': None}
        if status == 'in_progress':
            fields['started_at'] = run.get('started_at') or now
        elif status == 'completed':
            fields.update(completed_at=now, ended_at=now, completion_source='learning_review',
                          evidence_summary='复习已提交，具体表现见学习报告。')
        conn.execute('UPDATE tasks SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=? AND family_id=?',
                     (*fields.values(), run['task_id'], run['family_id']))

    def create(self, conn, run, questions, created_by, timezone='Asia/Shanghai'):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        local = datetime.fromtimestamp((run['scheduled_at'] or run['created_at']) / 1000, ZoneInfo(timezone))
        conn.execute('''INSERT INTO tasks(id,family_id,child_id,title,description,type,status,
            scheduled_date,scheduled_start,schedule_type,start_at,priority,reward_points,requires_parent_confirmation,
            created_by,reminder_minutes_before,reminder_status,timezone,learning_assignment_key,learning_slot,created_at,updated_at)
            VALUES (?,?,?,?,?,'learning','scheduled',?,?,'one_time',?,3,0,0,?,0,'review_owned',?,?,'weekend_review',?,?)''',
            (run['task_id'],run['family_id'],run['child_id'],'周末小复习','按已学内容做一次短复习；没有参加不计学习失败。',
             local.date().isoformat(),local.strftime('%H:%M'),local.isoformat(),created_by,timezone,
             digest([run['child_id'],run['week_start'],'weekend_review']),run['created_at'],run['created_at']))
        columns = list(run)
        conn.execute('INSERT INTO learning_review_runs(' + ','.join(columns) + ') VALUES (' + ','.join('?' for _ in columns) + ')', tuple(run.values()))
        for ordinal, (question, mode) in enumerate(questions):
            checksum = digest(question)
            conn.execute('INSERT INTO learning_review_items(run_id,ordinal,question_id,snapshot_json,snapshot_sha256,knowledge_id,evidence_mode) VALUES (?,?,?,?,?,?,?)',
                (run['id'], ordinal, checksum, canonical(question), checksum, question['knowledgeId'], mode))
