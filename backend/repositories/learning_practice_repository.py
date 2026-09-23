from __future__ import annotations

from contextlib import contextmanager
import json
from core.database import Database
from repositories.student_learning_library_repository import _FULL_CLASSROOM_AVAILABILITY_SQL


class LearningPracticeRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self):
        with self.database.transaction() as conn:
            yield conn

    def lock_child(self, conn, principal):
        child = conn.execute("SELECT * FROM children WHERE id = ? AND family_id = ? LIMIT 1 FOR UPDATE",
            (principal['child_id'], principal['family_id'])).fetchone()
        if child is None:
            return None
        active = conn.execute("SELECT id FROM student_principals WHERE id = ? AND family_id = ? AND child_id = ? AND status = 'active' LIMIT 1 FOR UPDATE",
            (principal['id'], principal['family_id'], principal['child_id'])).fetchone()
        return child if active is not None else None

    def eligible_sources(self, conn, *, family_id, child_id, grade_code, subject, skill_id):
        # Fine provenance and full formal media authority are rechecked by the
        # service. Exact personal completion is required before revision.
        return conn.execute("""SELECT DISTINCT course.*
            FROM learning_sessions AS session
            JOIN tasks AS task ON task.id=session.task_id AND task.family_id=session.family_id AND task.child_id=session.child_id
            JOIN learning_courses AS course ON course.id=session.course_id AND course.version=session.course_version
            WHERE session.family_id=? AND session.child_id=? AND session.status='completed' AND session.completed_at IS NOT NULL
              AND course.curriculum_version='mira.primary.progressive.v1' AND course.subject=?
              AND (? IS NULL OR course.node_code=?) AND course.status='published' AND course.quality_status='released'
              AND course.retired_at IS NULL
            ORDER BY course.created_at DESC, course.id, course.version LIMIT 120""",
            (family_id, child_id, subject, skill_id, skill_id)).fetchall()

    def completed_progressive_course(self, conn, *, family_id, child_id, course_id, course_version):
        return conn.execute("""SELECT course.* FROM learning_courses AS course
            WHERE course.id=? AND course.version=? AND course.curriculum_version='mira.primary.progressive.v1'
              AND EXISTS (SELECT 1 FROM learning_sessions AS session JOIN tasks AS task ON task.id=session.task_id
                AND task.family_id=session.family_id AND task.child_id=session.child_id
                WHERE session.family_id=? AND session.child_id=? AND session.course_id=course.id
                AND session.course_version=course.version AND session.status='completed' AND session.completed_at IS NOT NULL)
            LIMIT 1""", (course_id, course_version, family_id, child_id)).fetchone()

    def difficulty_mastery(self, conn, *, family_id, child_id, grade_code, subject):
        rows = conn.execute('SELECT node_code,mastery_level,independent_correct_count,hint_count '
            'FROM learning_mastery_states WHERE family_id=? AND child_id=? AND grade_code=? AND subject=?',
            (family_id, child_id, grade_code, subject)).fetchall()
        return {row['node_code']: dict(row) for row in rows}

    def project(self, conn, row):
        # Two different children may project the same approved source at once.
        # The unique source identity arbitrates inserts without rewriting it.
        columns = list(row)
        conn.execute(f"INSERT IGNORE INTO learning_practice_questions({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(row.values()))
        prior = conn.execute('SELECT * FROM learning_practice_questions WHERE source_key_sha256 = ? FOR UPDATE', (row['source_key_sha256'],)).fetchone()
        if prior is None or prior['contract_sha256'] != row['contract_sha256'] or prior['source_content_sha256'] != row['source_content_sha256']:
            raise ValueError('published practice source changed without a version')
        return dict(prior)

    def seen(self, conn, *, family_id, child_id):
        return {row['dedupe_sha256'] for row in conn.execute(
            'SELECT dedupe_sha256 FROM learning_practice_exposures WHERE family_id = ? AND child_id = ?', (family_id, child_id)).fetchall()}

    def existing(self, conn, *, family_id, child_id, request_key):
        return conn.execute('SELECT * FROM learning_practice_sessions WHERE family_id = ? AND child_id = ? AND request_key_sha256 = ? LIMIT 1 FOR UPDATE',
            (family_id, child_id, request_key)).fetchone()

    def active(self, conn, *, family_id, child_id, grade_code, grade_revision, subject, skill_id):
        return conn.execute("""SELECT * FROM learning_practice_sessions WHERE family_id = ? AND child_id = ?
            AND grade_code = ? AND grade_revision = ? AND subject = ? AND skill_id <=> ? AND status = 'in_progress'
            AND EXISTS (SELECT 1 FROM learning_practice_session_questions AS question WHERE question.session_id=learning_practice_sessions.id
              AND JSON_UNQUOTE(JSON_EXTRACT(question.snapshot_json,'$.practiceSource.curriculumVersion'))='mira.primary.progressive.v1')
            ORDER BY created_at LIMIT 1 FOR UPDATE""", (family_id, child_id, grade_code, grade_revision, subject, skill_id)).fetchone()

    def get_session(self, conn, *, family_id, child_id, session_id):
        return conn.execute('SELECT * FROM learning_practice_sessions WHERE id = ? AND family_id = ? AND child_id = ? LIMIT 1 FOR UPDATE',
            (session_id, family_id, child_id)).fetchone()

    def items(self, conn, session_id):
        return conn.execute('SELECT * FROM learning_practice_session_questions WHERE session_id = ? ORDER BY ordinal', (session_id,)).fetchall()

    def create(self, conn, *, session, questions, exposures):
        columns = list(session)
        conn.execute(f"INSERT INTO learning_practice_sessions({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(session.values()))
        for ordinal, question in enumerate(questions):
            conn.execute('INSERT INTO learning_practice_session_questions(session_id,ordinal,question_id,contract_sha256,snapshot_json) VALUES (?,?,?,?,?)',
                (session['id'], ordinal, question['id'], question['contract_sha256'], question['question_json']))
        for exposure in exposures:
            columns = list(exposure)
            conn.execute(f"INSERT INTO learning_practice_exposures({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(exposure.values()))

    def answer(self, conn, *, session, item, response_sha256, feedback, now):
        conn.execute('UPDATE learning_practice_session_questions SET response_sha256=?, feedback_json=?, answered_at=? WHERE session_id=? AND ordinal=? AND response_sha256 IS NULL',
            (response_sha256, json.dumps(feedback, ensure_ascii=False, sort_keys=True, separators=(',', ':')), now, session['id'], item['ordinal']))
        index = int(session['current_index']) + 1
        completed = index == int(session['total_questions'])
        conn.execute('UPDATE learning_practice_sessions SET current_index=?,correct_count=?,status=?,updated_at=?,completed_at=? WHERE id=?',
            (index, int(session['correct_count']) + int(feedback['correct']), 'completed' if completed else 'in_progress', now, now if completed else None, session['id']))
