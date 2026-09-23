"""Versioned fine-lesson bindings, append-only evidence, and derived progress.

The caller owns the transaction. Publication candidates still require the
existing formal publication/runtime checks before any student can launch them.
"""
from __future__ import annotations

from contextlib import contextmanager


class ProgressiveLearningRepository:
    def __init__(self, database):
        self.database = database

    @contextmanager
    def transaction(self):
        with self.database.transaction() as conn:
            yield conn

    def lock_child(self, conn, *, family_id, child_id):
        return conn.execute(
            "SELECT * FROM children WHERE family_id = ? AND id = ? LIMIT 1 FOR UPDATE",
            (family_id, child_id),
        ).fetchone()

    def binding_for_course(self, conn, *, course_id, course_version):
        return conn.execute(
            "SELECT * FROM learning_progressive_course_bindings "
            "WHERE course_id = ? AND course_version = ? AND retired_at IS NULL LIMIT 1",
            (course_id, course_version),
        ).fetchone()

    def bind_course(self, conn, *, binding):
        columns = tuple(binding)
        conn.execute(
            f"INSERT INTO learning_progressive_course_bindings({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)}) "
            "ON DUPLICATE KEY UPDATE course_id = course_id",
            tuple(binding[column] for column in columns),
        )
        existing = conn.execute(
            "SELECT * FROM learning_progressive_course_bindings "
            "WHERE course_id = ? AND course_version = ? LIMIT 1 FOR UPDATE",
            (binding["course_id"], binding["course_version"]),
        ).fetchone()
        immutable = ("curriculum_version", "lesson_id", "grade_code", "subject",
                     "assessment_set_id", "content_sha256")
        if (existing is None or existing.get("retired_at") is not None
                or any(existing[key] != binding[key] for key in immutable)):
            raise ValueError("progressive course binding changed without a new course version")
        return dict(existing)

    def course_candidates(self, conn, *, curriculum_version, lesson_id):
        return [dict(row) for row in conn.execute(
            "SELECT course.*, binding.lesson_id AS progressive_lesson_id, "
            "binding.assessment_set_id, binding.content_sha256 AS binding_content_sha256 "
            "FROM learning_progressive_course_bindings AS binding "
            "JOIN learning_courses AS course ON course.id = binding.course_id "
            "AND course.version = binding.course_version "
            "AND course.grade_code = binding.grade_code AND course.subject = binding.subject "
            "WHERE binding.curriculum_version = ? AND binding.lesson_id = ? "
            "AND binding.retired_at IS NULL AND course.status = 'published' "
            "AND course.quality_status = 'released' AND course.retired_at IS NULL "
            "ORDER BY binding.created_at, course.id, course.version",
            (curriculum_version, lesson_id),
        ).fetchall()]

    def course_activity(self, conn, *, family_id, child_id, curriculum_version, lesson_id):
        """Latest assigned task per exact course, matching catalog task reuse.

        Evidence alone does not cover an unfinished session or an observed
        lesson without questions. Read their persisted task/session identity.
        """
        rows = conn.execute(
            "SELECT task.learning_course_id AS course_id, "
            "task.learning_course_version AS course_version, task.status AS task_status, "
            "session.id AS session_id, session.status AS session_status, "
            "session.updated_at AS session_updated_at, binding.assessment_set_id "
            "FROM tasks AS task "
            "JOIN learning_progressive_course_bindings AS binding "
            "ON binding.course_id = task.learning_course_id "
            "AND binding.course_version = task.learning_course_version "
            "LEFT JOIN learning_sessions AS session "
            "ON session.task_id = task.id AND session.family_id = task.family_id "
            "AND session.child_id = task.child_id "
            "AND session.course_id = task.learning_course_id "
            "AND session.course_version = task.learning_course_version "
            "WHERE task.family_id = ? AND task.child_id = ? AND task.type = 'learning' "
            "AND binding.curriculum_version = ? AND binding.lesson_id = ? "
            "AND binding.retired_at IS NULL "
            "ORDER BY task.created_at DESC, task.id DESC",
            (family_id, child_id, curriculum_version, lesson_id),
        ).fetchall()
        latest = {}
        for row in rows:
            key = (str(row["course_id"]), str(row["course_version"]))
            latest.setdefault(key, dict(row))
        return latest

    def completed_observation_courses(self, conn, *, family_id, child_id, curriculum_version, lesson_id):
        return [dict(row) for row in conn.execute(
            "SELECT course.*, session.id AS observation_session_id, "
            "session.completed_at AS observation_completed_at "
            "FROM learning_sessions AS session "
            "JOIN tasks AS task ON task.id = session.task_id "
            "AND task.family_id = session.family_id AND task.child_id = session.child_id "
            "AND task.learning_course_id = session.course_id "
            "AND task.learning_course_version = session.course_version "
            "JOIN learning_courses AS course ON course.id = session.course_id "
            "AND course.version = session.course_version "
            "JOIN learning_progressive_course_bindings AS binding "
            "ON binding.course_id = course.id AND binding.course_version = course.version "
            "WHERE session.family_id = ? AND session.child_id = ? "
            "AND session.status = 'completed' AND session.completed_at IS NOT NULL "
            "AND task.type = 'learning' AND task.status = 'completed' "
            "AND binding.curriculum_version = ? AND binding.lesson_id = ? "
            "AND binding.retired_at IS NULL AND course.retired_at IS NULL "
            "AND course.status = 'published' AND course.quality_status = 'released' "
            "ORDER BY session.completed_at DESC, session.id DESC",
            (family_id, child_id, curriculum_version, lesson_id),
        ).fetchall()]

    def append_evidence(self, conn, *, evidence):
        """Replay cannot alter an earlier answer or its source identity."""
        columns = tuple(evidence)
        conn.execute(
            f"INSERT INTO learning_progressive_evidence({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)}) ON DUPLICATE KEY UPDATE id = id",
            tuple(evidence[column] for column in columns),
        )
        existing = conn.execute(
            "SELECT * FROM learning_progressive_evidence WHERE id = ? LIMIT 1",
            (evidence["id"],),
        ).fetchone()
        if existing is None or existing["evidence_sha256"] != evidence["evidence_sha256"]:
            raise ValueError("conflicting progressive evidence replay")
        return dict(existing)

    def list_evidence(self, conn, *, family_id, child_id, curriculum_version,
                      subject=None, lesson_id=None):
        conditions = ["family_id = ?", "child_id = ?", "curriculum_version = ?"]
        params = [family_id, child_id, curriculum_version]
        for column, value in (("subject", subject), ("lesson_id", lesson_id)):
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)
        return [dict(row) for row in conn.execute(
            "SELECT * FROM learning_progressive_evidence WHERE "
            + " AND ".join(conditions) + " ORDER BY occurred_at, id", params,
        ).fetchall()]

    def list_progress(self, conn, *, family_id, child_id, curriculum_version,
                      subject=None):
        params = [family_id, child_id, curriculum_version]
        subject_sql = ""
        if subject is not None:
            subject_sql = " AND subject = ?"
            params.append(subject)
        return {row["lesson_id"]: dict(row) for row in conn.execute(
            "SELECT * FROM learning_progressive_lesson_progress "
            "WHERE family_id = ? AND child_id = ? AND curriculum_version = ?"
            + subject_sql, params,
        ).fetchall()}

    def save_progress(self, conn, *, progress):
        columns = tuple(progress)
        identity = {"family_id", "child_id", "curriculum_version", "lesson_id"}
        mutable = [column for column in columns if column not in identity]
        conn.execute(
            f"INSERT INTO learning_progressive_lesson_progress({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)}) ON DUPLICATE KEY UPDATE "
            + ",".join(f"{column}=VALUES({column})" for column in mutable),
            tuple(progress[column] for column in columns),
        )
        return dict(progress)
