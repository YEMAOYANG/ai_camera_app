"""Real registry/service/repository checks in isolated in-memory SQLite."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
import unittest

from content.progressive_curriculum import CURRICULUM_VERSION, lesson_by_id, lessons_for, prerequisite_closure
from core.errors import ApiError
from repositories.progressive_learning_repository import ProgressiveLearningRepository
from services.progressive_course_generation import lesson_binding
from services.progressive_learning_service import DAY_MS, ProgressiveLearningService


class _Connection:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        migration = '\n'.join((Path(__file__).parents[1] / 'migrations' / filename).read_text()
            for filename in ('080_learning_progressive_curriculum.sql', '081_learning_prerequisite_placement.sql'))
        for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\)\s*(?:ENGINE=[^;]+)?;", migration, re.S):
            pieces, start, depth = [], 0, 0
            for index, character in enumerate(body):
                depth += (character == "(") - (character == ")")
                if character == "," and depth == 0:
                    pieces.append(body[start:index].strip())
                    start = index + 1
            pieces.append(body[start:].strip())
            # This adapter checks repository behavior, not MySQL CHECK syntax.
            columns = [re.sub(r'UNIQUE KEY \w+', 'UNIQUE', item) for item in pieces
                       if not item.startswith(('INDEX ', 'CONSTRAINT '))]
            self.raw.execute(f"CREATE TABLE {name} ({','.join(columns)})")
        self.raw.execute("CREATE TABLE children (id TEXT, family_id TEXT, grade_code TEXT)")
        self.raw.execute("CREATE TABLE learning_courses (id TEXT, version TEXT, grade_code TEXT, "
                         "subject TEXT, node_code TEXT, title TEXT, objective TEXT, status TEXT, "
                         "quality_status TEXT, content_origin TEXT, content_json TEXT, curriculum_version TEXT, "
                         "retired_at INTEGER, PRIMARY KEY(id,version))")
        self.raw.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, family_id TEXT, child_id TEXT, "
                         "type TEXT, learning_course_id TEXT, learning_course_version TEXT, "
                         "status TEXT, created_at INTEGER)")
        self.raw.execute("CREATE TABLE learning_sessions (id TEXT PRIMARY KEY, family_id TEXT, "
                         "child_id TEXT, task_id TEXT, course_id TEXT, course_version TEXT, "
                         "status TEXT, started_at INTEGER, completed_at INTEGER, "
                         "answers_json TEXT, updated_at INTEGER)")

    def execute(self, sql, params=()):
        sql = re.sub(r"\s+FOR UPDATE\b", "", sql)
        sql = sql.replace("ON DUPLICATE KEY UPDATE", "ON CONFLICT DO UPDATE SET")
        sql = re.sub(r"VALUES\((\w+)\)", r"excluded.\1", sql)
        cursor = self.raw.execute(sql, tuple(params))
        return SimpleNamespace(
            fetchone=lambda: self._row(cursor.fetchone()),
            fetchall=lambda: [dict(row) for row in cursor.fetchall()],
            rowcount=cursor.rowcount,
        )

    @staticmethod
    def _row(row):
        return dict(row) if row is not None else None


class _Database:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def transaction(self):
        try:
            yield self.conn
            self.conn.raw.commit()
        except Exception:
            self.conn.raw.rollback()
            raise


class ProgressiveLearningServiceTest(unittest.TestCase):
    def setUp(self):
        self.conn = _Connection()
        self.addCleanup(self.conn.raw.close)
        self.repository = ProgressiveLearningRepository(_Database(self.conn))
        self.service = ProgressiveLearningService(self.repository)
        self.child = {"family_id": "family-a", "id": "child-a", "grade_code": "primary_1"}
        self.conn.execute("INSERT INTO children VALUES (?,?,?)",
                          (self.child["id"], self.child["family_id"], self.child["grade_code"]))
        self.first = lessons_for("primary_1", "math")[0]["lessonId"]
        self.second = lessons_for("primary_1", "math")[1]["lessonId"]
        self.ordinal = 0
        self.conn.raw.commit()

    def course(self, label, count=5, *, lesson_id=None, questions=None):
        lesson = lesson_by_id(lesson_id or self.first)
        questions = questions if questions is not None else [
            {"id": f"q{index}", "type": "numeric", "prompt": f"{label} 的第 {index} 个独立任务",
             "answer": "1"} for index in range(count)
        ]
        content = {"schemaVersion": "mira.learning.progressive-course.v1",
                   "progressiveLesson": lesson_binding(lesson["lessonId"]),
                   "difficultyCode": "basic", "assessmentMode": lesson["assessmentMode"],
                   "questions": deepcopy(questions),
                   "progressiveFlow": [{"phase": "independent", "questionId": question["id"],
                                        "text": "独立完成", "knowledgeIds": [lesson["lessonId"]]}
                                       for question in questions]}
        if lesson["assessmentMode"] == "observed":
            content.update(questions=[], manualConfirmationRequired=True, autoMasteryEligible=False,
                progressiveFlow=[{"phase": "observe", "knowledgeIds": [lesson["lessonId"]],
                                  "text": f"请观察孩子独立完成：{lesson['title']}"}])
        course = {"id": f"course-{label}", "version": "1", "grade_code": lesson["gradeCode"],
                  "subject": lesson["subject"], "node_code": lesson["lessonId"],
                  "title": lesson["title"], "objective": "独立完成本课任务", "status": "published",
                  "quality_status": "released", "content_origin": "openmaic_generated",
                  "content_json": json.dumps(content, ensure_ascii=False),
                  "curriculum_version": CURRICULUM_VERSION, "retired_at": None}
        self.conn.execute(f"INSERT INTO learning_courses({','.join(course)}) VALUES ({','.join('?' for _ in course)})",
                          tuple(course.values()))
        self.service.bind_course(self.conn, course=course, lesson_id=lesson["lessonId"],
                                 assessment_set_id=label, now=1)
        self.conn.raw.commit()
        return course

    def session(self, course, *, at=1000, correct=None, hints=(), retry=()):
        self.ordinal += 1
        questions = json.loads(course["content_json"])["questions"]
        mask = correct if correct is not None else [True] * len(questions)
        answers = []
        for index, question in enumerate(questions):
            answers.append({"questionId": question["id"], "attemptNumber": 1,
                            "correct": mask[index], "answeredAt": at,
                            "hintProvided": not mask[index],
                            "hintCountBeforeAnswer": int(index in hints)})
            if index in retry:
                answers.append({"questionId": question["id"], "attemptNumber": 2,
                                "correct": True, "answeredAt": at})
        session = {"id": f"session-{self.ordinal}", "family_id": self.child["family_id"],
                   "child_id": self.child["id"], "course_id": course["id"],
                   "course_version": course["version"], "status": "completed",
                   "task_id": f"task-{self.ordinal}", "started_at": at - 1,
                   "completed_at": at, "answers_json": json.dumps(answers), "updated_at": at}
        self.conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)",
            (session["task_id"], session["family_id"], session["child_id"], "learning",
             course["id"], course["version"], "completed", at - 1))
        self.conn.execute(f"INSERT INTO learning_sessions({','.join(session)}) VALUES ({','.join('?' for _ in session)})",
                          tuple(session.values()))
        return session, questions, answers

    def record(self, course, *, at=1000, **options):
        session, questions, answers = self.session(course, at=at, **options)
        with self.repository.transaction() as conn:
            return self.service.record_session_evidence(conn, child=self.child, course=course,
                session=session, questions=questions, answers=answers, now=at)

    def evidence(self):
        return self.repository.list_evidence(self.conn, family_id=self.child["family_id"],
            child_id=self.child["id"], curriculum_version=CURRICULUM_VERSION)

    def test_five_independent_tasks_across_two_sets_unlock_the_next_lesson(self):
        first = self.course("set-a", 3)
        future = self.course("future", lesson_id=self.second)
        path = lambda: self.service.get_path(self.conn, child=self.child, subject="math", now=3000,
                                             course_validator=lambda *args, **kwargs: True)
        session, questions, answers = self.session(first, correct=[True, True, False])
        self.conn.execute("UPDATE tasks SET status='in_progress' WHERE id=?", (session["task_id"],))
        self.conn.execute("UPDATE learning_sessions SET status='in_progress', completed_at=NULL WHERE id=?", (session["id"],))
        self.assertEqual(path()["nextLesson"]["courseId"], first["id"])
        self.conn.execute("UPDATE tasks SET status='completed' WHERE id=?", (session["task_id"],))
        self.conn.execute("UPDATE learning_sessions SET status='completed', completed_at=1000 WHERE id=?", (session["id"],))
        progress = self.service.record_session_evidence(self.conn, child=self.child, course=first,
            session=session, questions=questions, answers=answers, now=1000)
        self.assertEqual(progress["mastery_status"], "needs_practice")
        self.assertEqual(progress["independent_correct_count"], 2)
        self.assertIsNone(path()["nextLesson"]["course"])
        with self.assertRaises(ApiError):
            self.service.assert_course_progression(self.conn, child=self.child, course=future)
        second = self.course("set-b", 2)
        self.assertEqual(path()["nextLesson"]["courseId"], second["id"])
        progress = self.record(second, at=2000)
        self.assertEqual(progress["independent_count"], 5)
        self.assertEqual(progress["accuracy"], 0.8)
        self.assertEqual(progress["mastery_status"], "mastered")
        self.assertTrue(self.service.assert_course_progression(self.conn, child=self.child, course=future))
        self.assertEqual(path()["nextLesson"]["lessonId"], self.second)

    def test_complete_five_question_sets_can_reach_mastery_without_window_starvation(self):
        first = self.course("five-a")
        second = self.course("five-b")
        self.assertEqual(self.record(first)["mastery_status"], "needs_practice")
        progress = self.record(second, at=2000)
        self.assertEqual(progress["mastery_status"], "mastered")
        self.assertEqual(progress["distinct_assessment_sets"], 2)
        self.assertEqual(progress["independent_count"], 5)

    def test_hints_retries_and_repeated_question_content_do_not_supply_fresh_evidence(self):
        original = self.course("original")
        result = self.record(original, correct=[True, False, True, True, True], hints=(0,), retry=(1,))
        self.assertEqual(result["independent_count"], 4)
        self.assertEqual(result["independent_correct_count"], 3)
        questions = json.loads(original["content_json"])["questions"]
        for item in questions:
            item["id"] = f"renamed-{item['id']}"
        repeated = self.course("repeated", questions=questions)
        result = self.record(repeated, at=2000)
        self.assertEqual(result["independent_count"], 4)
        self.assertEqual(result["independent_correct_count"], 3)
        self.assertEqual(result["mastery_status"], "needs_practice")
        self.assertEqual(len(self.evidence()), 10)

    def test_evidence_replay_is_idempotent_and_conflicting_answer_is_rejected(self):
        course = self.course("replay")
        session, questions, answers = self.session(course)
        for now in (1000, 2000):
            with self.repository.transaction() as conn:
                self.service.record_session_evidence(conn, child=self.child, course=course,
                    session=session, questions=questions, answers=answers, now=now)
        self.assertEqual(len(self.evidence()), 5)
        answers[0]["correct"] = False
        session["answers_json"] = json.dumps(answers)
        with self.assertRaisesRegex(ValueError, "conflicting progressive evidence"):
            with self.repository.transaction() as conn:
                self.service.record_session_evidence(conn, child=self.child, course=course,
                    session=session, questions=questions, answers=answers, now=3000)
        self.assertEqual(len(self.evidence()), 5)
        self.assertTrue(all(row["correct"] == 1 for row in self.evidence()))

    def test_delayed_stability_requires_new_independent_evidence_after_a_day(self):
        self.record(self.course("base-a", 3), at=1000)
        result = self.record(self.course("base-b", 2), at=2000)
        self.assertEqual(result["mastered_at"], 2000)
        self.assertIsNone(result["stable_at"])
        result = self.record(self.course("early", 2), at=2000 + DAY_MS - 1)
        self.assertIsNone(result["stable_at"])
        result = self.record(self.course("delayed", 2), at=2000 + DAY_MS + 1)
        self.assertEqual(result["mastered_at"], 2000)
        self.assertEqual(result["stable_at"], 2000 + DAY_MS + 1)

    def test_observed_lesson_requires_explicit_authorized_actor_confirmation(self):
        observed = next(row for row in lessons_for("primary_1", "math") if row["assessmentMode"] == "observed")
        self.service.course_validator = lambda *args, **kwargs: True
        for identifier in prerequisite_closure(observed["lessonId"]):
            earlier = lesson_by_id(identifier)
            self.conn.execute("INSERT INTO learning_progressive_lesson_progress "
                "(family_id,child_id,curriculum_version,lesson_id,grade_code,subject,mastery_status,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (self.child["family_id"], self.child["id"], CURRICULUM_VERSION,
                identifier, earlier["gradeCode"], earlier["subject"], "mastered", 1))
        course = self.course("observe-a", lesson_id=observed["lessonId"])
        def observation():
            path = self.service.get_path(self.conn, child=self.child, subject="math", now=3000)
            return next(row["observation"] for row in path["currentGradeLessons"]
                        if row["lessonId"] == observed["lessonId"])
        self.assertFalse(observation()["canConfirm"])
        result = self.record(course)
        self.assertNotEqual(result["mastery_status"], "mastered")
        first = observation()
        self.assertEqual(first["criteria"][0], json.loads(course["content_json"])["progressiveFlow"][0]["text"])
        arguments = dict(child=self.child, lesson_id=observed["lessonId"], confirmation_id=first["confirmationId"],
                         actor_id="parent-a", confirmed=False, now=2000)
        with self.assertRaises(ApiError):
            self.service.record_observed_confirmation(self.conn, actor_role="student", **arguments)
        with self.repository.transaction() as conn:
            result = self.service.record_observed_confirmation(conn, actor_role="parent", **arguments)
        self.assertEqual(result["mastery_status"], "needs_practice")
        second = observation()
        self.assertNotEqual(first["confirmationId"], second["confirmationId"])
        arguments.update(confirmation_id=second["confirmationId"], confirmed=True, now=2500)
        with self.repository.transaction() as conn:
            result = self.service.record_observed_confirmation(conn, actor_role="parent", **arguments)
        self.assertEqual(result["mastery_status"], "mastered")
        self.assertFalse(observation()["canConfirm"])
        with self.repository.transaction() as conn:
            replay = self.service.record_observed_confirmation(conn, actor_role="parent", **{**arguments, "now": 4000})
        self.assertEqual(replay["mastered_at"], result["mastered_at"])
        self.assertEqual(len(self.evidence()), 2)

    def test_session_scope_content_and_completion_are_required_for_evidence(self):
        course = self.course("scope")
        session, questions, answers = self.session(course)
        for changes in ({"family_id": "other-family"}, {"child_id": "other-child"},
                        {"course_version": "2"}, {"status": "in_progress"}):
            with self.subTest(changes=changes), self.assertRaises(ApiError):
                self.service.record_session_evidence(self.conn, child=self.child, course=course,
                    session={**session, **changes}, questions=questions, answers=answers, now=1000)
        changed = deepcopy(course)
        content = json.loads(changed["content_json"])
        content["questions"][0]["answer"] = "2"
        changed["content_json"] = json.dumps(content)
        with self.assertRaises(ApiError):
            self.service.record_session_evidence(self.conn, child=self.child, course=changed,
                session=session, questions=questions, answers=answers, now=1000)
        self.assertEqual(self.evidence(), [])

    def test_paths_start_in_selected_grade_and_other_grades_remain_read_only(self):
        self.child["grade_code"] = "primary_6"
        self.conn.execute("UPDATE children SET grade_code='primary_6'")
        entry_id = lessons_for('primary_6', 'math')[0]['lessonId']
        entry_course = self.course('grade-six-entry', lesson_id=entry_id)
        path = self.service.get_path(self.conn, child=self.child, subject="math", now=1000,
                                     course_validator=lambda *args, **kwargs: True)
        self.assertEqual(path["nextLesson"]["gradeCode"], "primary_6")
        self.assertEqual(path["nextLesson"]["lessonId"], entry_id)
        self.assertEqual(path["nextLesson"]["courseId"], entry_course['id'])
        self.assertFalse(path["assessment"]["required"])
        self.assertEqual(path['prerequisites'], [])
        self.assertTrue(all(row["subject"] == "math" and row['gradeCode'] == 'primary_6'
                            for row in path["lessons"]))
        self.assertEqual(path['lessons'][1]['status'], 'locked')
        self.assertEqual(self.evidence(), [], 'grade enrollment must not fabricate earlier mastery')
        self.assertEqual(self.repository.list_progress(self.conn, **self.service._scope(self.child)), {})
        lower = self.service.get_path(self.conn, child=self.child, subject='math', grade_code='primary_1', now=1000)
        self.assertIsNone(lower['nextLesson'])
        self.assertTrue(all(not row['canStart'] for row in lower['lessons']))
        self.child["grade_code"] = "primary_1"
        higher = self.service.get_path(self.conn, child=self.child, subject="math", grade_code="primary_6", now=1000)
        self.assertTrue(all(not row["canStart"] and row["status"] == "locked" for row in higher["lessons"]))
        self.assertIsNone(higher["nextLesson"])
        self.assertEqual(self.child["grade_code"], "primary_1")

    def test_public_course_selection_needs_full_validation_and_fresh_binding_hash(self):
        course = self.course("published")
        path = self.service.get_path(self.conn, child=self.child, subject="math", now=1000)
        self.assertIsNone(path["nextLesson"]["course"])
        path = self.service.get_path(self.conn, child=self.child, subject="math", now=1000,
                                     course_validator=lambda conn, **scope: scope["course"]["id"] == course["id"])
        self.assertEqual(path["nextLesson"]["courseId"], course["id"])
        stale = json.loads(course["content_json"])
        stale["progressiveLesson"]["identitySha256"] = "0" * 64
        stale_hash = hashlib.sha256(json.dumps(stale, ensure_ascii=False, sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
        self.conn.execute("UPDATE learning_courses SET content_json=? WHERE id=?",
                          (json.dumps(stale, ensure_ascii=False), course["id"]))
        self.conn.execute("UPDATE learning_progressive_course_bindings SET content_sha256=? WHERE course_id=?",
                          (stale_hash, course["id"]))
        path = self.service.get_path(self.conn, child=self.child, subject="math", now=1000,
                                     course_validator=lambda *args, **kwargs: True)
        self.assertIsNone(path["nextLesson"]["course"], "a rehashed old authority must not pass the current lesson binding")
        self.conn.execute("UPDATE learning_courses SET content_json='{}' WHERE id=?", (course["id"],))
        path = self.service.get_path(self.conn, child=self.child, subject="math", now=1000,
                                     course_validator=lambda *args, **kwargs: True)
        self.assertIsNone(path["nextLesson"]["course"])

    def test_new_version_without_binding_fails_closed_and_other_child_progress_is_not_used(self):
        course = self.course("identity")
        unbound = {**course, "id": "unbound-new-course"}
        with self.assertRaises(ApiError) as caught:
            self.service.progression_for_course(self.conn, child=self.child, course=unbound)
        self.assertEqual(caught.exception.code, "progressive_course_binding_required")
        self.record(course)
        self.record(self.course("other-set"), at=2000)
        self.child = {"family_id": "family-b", "id": "child-b", "grade_code": "primary_1"}
        path = self.service.get_path(self.conn, child=self.child, subject="math", now=3000)
        self.assertEqual(path["nextLesson"]["lessonId"], self.first)
        self.assertEqual(path["lessons"][0]["status"], "available")


if __name__ == "__main__":
    unittest.main()
