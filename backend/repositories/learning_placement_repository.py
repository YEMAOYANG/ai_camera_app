"""Placement persistence. The child row lock serializes issuing and answering."""
from __future__ import annotations

from repositories.learning_practice_repository import LearningPracticeRepository


class LearningPlacementRepository(LearningPracticeRepository):
    def reserved_assessment_sets(self, conn, *, family_id, child_id, curriculum_version, lesson_id):
        return {row['assessment_set_id'] for row in conn.execute(
            'SELECT question.assessment_set_id FROM learning_placement_questions AS question '
            'JOIN learning_placement_attempts AS attempt ON attempt.id=question.attempt_id '
            'WHERE attempt.family_id=? AND attempt.child_id=? AND attempt.curriculum_version=? AND attempt.lesson_id=?',
            (family_id, child_id, curriculum_version, lesson_id),
        ).fetchall()}

    def existing_attempt(self, conn, *, family_id, child_id, curriculum_version, lesson_id):
        return conn.execute(
            'SELECT * FROM learning_placement_attempts WHERE family_id=? AND child_id=? '
            'AND curriculum_version=? AND lesson_id=? LIMIT 1 FOR UPDATE',
            (family_id, child_id, curriculum_version, lesson_id),
        ).fetchone()

    def get_attempt(self, conn, *, family_id, child_id, attempt_id):
        return conn.execute(
            'SELECT * FROM learning_placement_attempts WHERE id=? AND family_id=? AND child_id=? LIMIT 1 FOR UPDATE',
            (attempt_id, family_id, child_id),
        ).fetchone()

    def items(self, conn, attempt_id):
        return [dict(row) for row in conn.execute(
            'SELECT * FROM learning_placement_questions WHERE attempt_id=? ORDER BY ordinal',
            (attempt_id,),
        ).fetchall()]

    def source_course(self, conn, *, course_id, course_version):
        return conn.execute('SELECT * FROM learning_courses WHERE id=? AND version=? LIMIT 1',
                            (course_id, course_version)).fetchone()

    def exposure_sources(self, conn, *, family_id, child_id, exclude_attempt_id=None):
        # Starting a classroom can expose explanations and its full question
        # contract. Treat every question as seen, including unfinished sessions.
        courses = conn.execute(
            'SELECT course.content_json FROM learning_sessions AS session '
            'LEFT JOIN learning_courses AS course ON course.id=session.course_id '
            'AND course.version=session.course_version '
            'WHERE session.family_id=? AND session.child_id=?', (family_id, child_id),
        ).fetchall()
        practice = conn.execute(
            'SELECT question.question_json FROM learning_practice_exposures AS exposure '
            'LEFT JOIN learning_practice_questions AS question ON question.id=exposure.question_id '
            'WHERE exposure.family_id=? AND exposure.child_id=?', (family_id, child_id),
        ).fetchall()
        placement = conn.execute(
            'SELECT question.question_fingerprint FROM learning_placement_questions AS question '
            'JOIN learning_placement_attempts AS attempt ON attempt.id=question.attempt_id '
            'WHERE attempt.family_id=? AND attempt.child_id=? AND (? IS NULL OR attempt.id<>?)',
            (family_id, child_id, exclude_attempt_id, exclude_attempt_id),
        ).fetchall()
        evidence = conn.execute(
            'SELECT question_fingerprint FROM learning_progressive_evidence WHERE family_id=? AND child_id=? '
            'AND (? IS NULL OR source_kind<>? OR source_session_id<>?)',
            (family_id, child_id, exclude_attempt_id, 'placement_answer', exclude_attempt_id),
        ).fetchall()
        return courses, practice, [*placement, *evidence]

    def create_attempt(self, conn, *, attempt, questions):
        self._insert(conn, 'learning_placement_attempts', attempt)
        for ordinal, question in enumerate(questions):
            self._insert(conn, 'learning_placement_questions',
                         {'attempt_id': attempt['id'], 'ordinal': ordinal, **question})

    @staticmethod
    def _insert(conn, table, row):
        columns = tuple(row)
        conn.execute(f"INSERT INTO {table}({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                     tuple(row[key] for key in columns))

    def answer_item(self, conn, *, attempt, item, response_sha256, correct, passed, now):
        conn.execute(
            'UPDATE learning_placement_questions SET response_sha256=?,correct=?,answered_at=? '
            'WHERE attempt_id=? AND ordinal=? AND response_sha256 IS NULL',
            (response_sha256, int(correct), now, attempt['id'], item['ordinal']),
        )
        index = int(attempt['current_index']) + 1
        completed = index == int(attempt['total_questions'])
        conn.execute(
            'UPDATE learning_placement_attempts SET current_index=?,correct_count=?,status=?,passed=?,updated_at=?,completed_at=? WHERE id=?',
            (index, int(attempt['correct_count']) + int(correct), 'completed' if completed else 'in_progress',
             int(passed) if completed else None, now, now if completed else None, attempt['id']),
        )

    def invalidate_attempt(self, conn, *, attempt_id, now):
        conn.execute(
            "UPDATE learning_placement_attempts SET status='invalidated',updated_at=?,completed_at=? "
            "WHERE id=? AND status='in_progress'", (now, now, attempt_id),
        )
