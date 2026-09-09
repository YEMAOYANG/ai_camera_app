from __future__ import annotations

import hashlib
import json
import unittest
from datetime import date, datetime, timedelta

from app import create_app
from core.database import Database
from repositories.learning_repository import LearningRepository
from services.learning_service import (
    LEARNING_SLOTS,
    PRIMARY_14_DAY_SUBJECT_MATRIX,
)
from services.service_factory import learning_service
from tests.fixtures.primary_subject_catalog import PRIMARY_COURSE_CATALOG
from tests.support import fresh_test_config, request_debug_code


LEGACY_PARENT_MUTATION_REMOVED = (
    "v1 parent learning mutations were removed; formal mutations are covered "
    "by the v2 student-auth suites"
)


class LearningApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.client = self.app.test_client()
        LearningRepository(Database(self.app.config["DATABASE_URL"])).ensure_published_courses(
            PRIMARY_COURSE_CATALOG,
            now=int(datetime.now().timestamp() * 1000),
        )
        self.access_token = self._login("13800002101")
        self.child_id = self._create_child("primary_3")

    def test_parent_overview_today_alias_and_reports_are_read_only(self):
        before = self._learning_write_counts()

        overview = self.client.get(
            "/api/learning/overview",
            query_string={"childId": self.child_id, "date": "2026-08-12"},
            headers=self._headers(),
        )
        self.assertEqual(overview.status_code, 200, overview.json)
        self.assertEqual(overview.json["state"], "recommended")
        self.assertIsNone(overview.json["task"])
        self.assertIsNone(overview.json["session"])
        self.assertTrue(
            all(item["task"] is None for item in overview.json["items"])
        )

        today_alias = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-08-12"},
            headers=self._headers(),
        )
        self.assertEqual(today_alias.status_code, 200, today_alias.json)
        self.assertEqual(today_alias.json, overview.json)

        latest = self.client.get(
            "/api/learning/reports/latest",
            query_string={"childId": self.child_id},
            headers=self._headers(),
        )
        self.assertEqual(latest.status_code, 200, latest.json)
        self.assertIsNone(latest.json["report"])

        reports = self.client.get(
            "/api/learning/reports",
            query_string={"childId": self.child_id},
            headers=self._headers(),
        )
        self.assertEqual(reports.status_code, 200, reports.json)
        self.assertEqual(reports.json["items"], [])

        self.assertEqual(self._learning_write_counts(), before)

    def test_legacy_parent_learning_mutations_fail_closed_before_body_or_auth(self):
        before = self._learning_write_counts()

        for path in (
            "/api/learning/today/assign",
            "/api/learning/sessions",
            "/api/learning/sessions/session-never-read/answer",
        ):
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    data="{not-json",
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 410, response.json)
                self.assertEqual(
                    response.json["error"],
                    "student_learning_api_required",
                )

        self.assertEqual(self._learning_write_counts(), before)

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_today_assign_is_idempotent_and_session_completes_with_report(self):
        today = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-08-12"},
            headers=self._headers(),
        )
        self.assertEqual(today.status_code, 200, today.json)
        self.assertEqual(today.json["itemCount"], 3)
        self.assertEqual([item["slot"] for item in today.json["items"]], list(LEARNING_SLOTS))
        self.assertEqual(len({item["subject"] for item in today.json["items"]}), 3)
        self.assertEqual(today.json["state"], "recommended")
        self.assertIsNone(today.json["task"])
        self.assertTrue(all(item["task"] is None for item in today.json["items"]))
        self.assertEqual(today.json["recommendation"]["gradeCode"], "primary_3")
        self.assertEqual(today.json["recommendation"]["questionCount"], 5)
        self.assertIsNone(today.json["mastery"])

        assigned = self._assign()
        assigned_again = self._assign()
        self.assertTrue(assigned["created"])
        self.assertFalse(assigned_again["created"])
        self.assertEqual(assigned["createdCount"], 3)
        self.assertEqual(len(assigned["items"]), 3)
        self.assertEqual(assigned["task"]["id"], assigned_again["task"]["id"])
        self.assertEqual(assigned["task"]["type"], "learning")
        self.assertEqual(
            assigned["task"]["learningCourseVersion"],
            assigned["recommendation"]["courseVersion"],
        )

        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        self.assertFalse(started.json["resumed"])
        current = started.json["session"]["currentQuestion"]
        self.assertNotIn("answer", current)
        session_id = started.json["session"]["id"]

        resumed = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(),
        )
        self.assertTrue(resumed.json["resumed"])
        self.assertEqual(resumed.json["session"]["id"], session_id)

        correct_answers = self._correct_answers_for_task(assigned["task"]["id"])
        last = None
        for expected in correct_answers:
            last = self.client.post(
                f"/api/learning/sessions/{session_id}/answer",
                json={"answer": expected},
                headers=self._headers(),
            )
            self.assertEqual(last.status_code, 200, last.json)
            self.assertTrue(last.json["correct"])
        self.assertTrue(last.json["completed"])
        self.assertEqual(last.json["report"]["score"], 100)
        self.assertEqual(last.json["report"]["masteryLevel"], "mastered")
        self.assertEqual(last.json["report"]["independentCorrectCount"], 5)
        self.assertEqual(last.json["report"]["hintCount"], 0)
        self.assertIn("下一个", last.json["report"]["nextStep"])
        self.assertIn("能力点", last.json["report"]["nextStep"])

        latest = self.client.get(
            "/api/learning/reports/latest",
            query_string={"childId": self.child_id},
            headers=self._headers(),
        )
        self.assertEqual(latest.status_code, 200, latest.json)
        self.assertEqual(latest.json["report"]["id"], last.json["report"]["id"])
        self.assertEqual(latest.json["mastery"]["latestScore"], 100)
        self.assertEqual(latest.json["mastery"]["courseVersion"], "1.0.0")
        self.assertEqual(latest.json["mastery"]["nextReviewDate"], "2026-08-19")

        next_day = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-08-13"},
            headers=self._headers(),
        )
        self.assertEqual(next_day.status_code, 200, next_day.json)
        self.assertEqual(next_day.json["state"], "recommended")
        self.assertEqual(len(next_day.json["items"]), 3)
        self.assertIsNone(next_day.json["task"])
        self.assertIsNone(next_day.json["latestReport"])

        next_assignment = self._assign(date_value="2026-08-13")
        next_assignment_replay = self._assign(date_value="2026-08-13")
        self.assertFalse(next_assignment_replay["created"])
        self.assertEqual(
            next_assignment["task"]["id"],
            next_assignment_replay["task"]["id"],
        )

        second_started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": next_assignment["task"]["id"]},
            headers=self._headers(),
        )
        self.assertEqual(second_started.status_code, 200, second_started.json)
        second_session_id = second_started.json["session"]["id"]
        for expected in self._correct_answers_for_task(next_assignment["task"]["id"]):
            second_last = self.client.post(
                f"/api/learning/sessions/{second_session_id}/answer",
                json={"answer": expected},
                headers=self._headers(),
            )
            self.assertEqual(second_last.status_code, 200, second_last.json)
            self.assertTrue(second_last.json["correct"])
        self.assertTrue(second_last.json["completed"])

        third_day = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-08-14"},
            headers=self._headers(),
        )
        self.assertEqual(third_day.status_code, 200, third_day.json)
        self.assertEqual(len(third_day.json["items"]), 3)

        events = self.client.get(
            f"/api/tasks/{assigned['task']['id']}/events",
            headers=self._headers(),
        )
        event_types = {item["eventType"] for item in events.json["events"]}
        self.assertIn("learning_assigned", event_types)
        self.assertIn("learning_session_started", event_types)
        self.assertIn("learning_answer_evaluated", event_types)
        self.assertIn("learning_completed", event_types)

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_assign_once_ensures_two_distinct_daily_slots(self):
        first = self._assign(date_value="2026-09-01")
        replay = self._assign(date_value="2026-09-01")

        self.assertTrue(first["created"])
        self.assertEqual(first["createdCount"], 2)
        self.assertFalse(replay["created"])
        self.assertEqual(replay["createdCount"], 0)
        self.assertEqual([item["slot"] for item in first["items"]], ["core", "rotation"])
        self.assertEqual(
            [item["subject"] for item in first["items"]],
            ["math", "chinese"],
        )
        self.assertEqual(
            [item["task"]["scheduledStart"] for item in first["items"]],
            ["19:30", "19:45"],
        )
        self.assertEqual(
            [item["task"]["id"] for item in first["items"]],
            [item["task"]["id"] for item in replay["items"]],
        )

        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            rows = conn.execute(
                """
                SELECT learning_slot, learning_assignment_key
                FROM tasks
                WHERE child_id = ? AND scheduled_date = '2026-09-01'
                  AND type = 'learning'
                ORDER BY CASE learning_slot WHEN 'core' THEN 0 ELSE 1 END
                """,
                (self.child_id,),
            ).fetchall()
        self.assertEqual([row["learning_slot"] for row in rows], ["core", "rotation"])
        self.assertEqual(len({row["learning_assignment_key"] for row in rows}), 2)

    def test_fourteen_day_matrix_is_deterministic_and_never_repeats_subject_in_a_day(self):
        start = date(2026, 9, 1)
        for offset, core_rotation in enumerate(PRIMARY_14_DAY_SUBJECT_MATRIX):
            learning_date = (start + timedelta(days=offset)).isoformat()
            response = self.client.get(
                "/api/learning/today",
                query_string={"childId": self.child_id, "date": learning_date},
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 200, response.json)
            actual = tuple(item["subject"] for item in response.json["items"])
            preferred = tuple(
                item["preferredSubject"] for item in response.json["items"]
            )
            expected = (
                *core_rotation,
                next(
                    subject
                    for subject in ("chinese", "math", "english")
                    if subject not in core_rotation
                ),
            )
            self.assertEqual(actual, expected)
            self.assertEqual(preferred, expected)
            self.assertEqual(len(set(actual)), 3)
            self.assertIsNone(response.json["task"])
            self.assertTrue(
                all(item["task"] is None for item in response.json["items"])
            )

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_legacy_unslotted_task_is_core_and_rotation_is_backfilled(self):
        assigned = self._assign(date_value="2026-09-02")
        core_id = assigned["items"][0]["task"]["id"]
        rotation_id = assigned["items"][1]["task"]["id"]
        rotation_course_id = assigned["items"][1]["task"]["learningCourseId"]
        rotation_course_version = assigned["items"][1]["task"][
            "learningCourseVersion"
        ]
        legacy_key = hashlib.sha256(
            f"{assigned['task']['familyId']}\n{self.child_id}\n2026-09-02".encode(
                "utf-8"
            )
        ).hexdigest()
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (rotation_id,))
            conn.execute(
                """
                UPDATE tasks
                SET learning_slot = NULL, learning_assignment_key = ?,
                    learning_course_id = ?, learning_course_version = ?
                WHERE id = ?
                """,
                (
                    legacy_key,
                    rotation_course_id,
                    rotation_course_version,
                    core_id,
                ),
            )

        repaired = self._assign(date_value="2026-09-02")
        self.assertEqual(len(repaired["items"]), 2)
        self.assertEqual(repaired["items"][0]["task"]["id"], core_id)
        self.assertEqual(repaired["items"][0]["task"]["learningSlot"], "core")
        self.assertNotEqual(repaired["items"][1]["task"]["id"], rotation_id)
        self.assertEqual(
            len({item["subject"] for item in repaired["items"]}),
            2,
        )

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_existing_unstarted_duplicate_subject_pair_is_repaired(self):
        assigned = self._assign(date_value="2026-09-01")
        core = assigned["items"][0]
        rotation = assigned["items"][1]
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET learning_course_id = ?, learning_course_version = ?
                WHERE id = ?
                """,
                (
                    core["task"]["learningCourseId"],
                    core["task"]["learningCourseVersion"],
                    rotation["task"]["id"],
                ),
            )

        repaired = self._assign(date_value="2026-09-01")
        self.assertEqual(len({item["subject"] for item in repaired["items"]}), 2)
        self.assertEqual(
            repaired["items"][1]["task"]["id"],
            rotation["task"]["id"],
        )
        self.assertNotEqual(
            repaired["items"][1]["task"]["learningCourseId"],
            core["task"]["learningCourseId"],
        )
        with database.transaction() as conn:
            event = conn.execute(
                """
                SELECT event_type FROM task_events
                WHERE task_id = ? AND event_type = 'learning_reassigned'
                LIMIT 1
                """,
                (rotation["task"]["id"],),
            ).fetchone()
        self.assertIsNotNone(event)

    def test_background_ensure_skips_unopened_grade_without_learning_writes(self):
        with self.app.app_context():
            result = learning_service().ensure_today_for_all_primary_children(
                learning_date="2026-09-03"
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["childrenChecked"], 1)
        self.assertEqual(result["childrenEnsured"], 0)
        self.assertEqual(result["childrenSkipped"], 1)
        self.assertEqual(result["createdCount"], 0)
        self.assertEqual(result["failures"], [])
        self.assertEqual(
            result["skipped"][0]["code"],
            "student_learning_grade_not_open",
        )
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            task_count = conn.execute(
                """
                SELECT COUNT(*) AS value FROM tasks
                WHERE child_id = ? AND scheduled_date = '2026-09-03'
                  AND type = 'learning'
                """,
                (self.child_id,),
            ).fetchone()["value"]
            session_count = conn.execute(
                """
                SELECT COUNT(*) AS value FROM learning_sessions
                WHERE child_id = ?
                """,
                (self.child_id,),
            ).fetchone()["value"]
        self.assertEqual(task_count, 0)
        self.assertEqual(session_count, 0)

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_latest_report_can_be_scoped_to_each_daily_subject(self):
        assigned = self._assign(date_value="2026-09-01")
        reports = {}
        for item in assigned["items"]:
            reports[item["subject"]] = self._complete_task(item["task"]["id"])

        for subject, expected in reports.items():
            response = self.client.get(
                "/api/learning/reports/latest",
                query_string={"childId": self.child_id, "subject": subject},
                headers=self._headers(),
            )
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json["report"]["id"], expected["id"])
            self.assertEqual(response.json["report"]["subject"], subject)
            self.assertEqual(
                response.json["report"]["subjectLabel"],
                "数学" if subject == "math" else "语文",
            )

        refreshed = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-09-01"},
            headers=self._headers(),
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.json)
        for item in refreshed.json["items"]:
            self.assertEqual(
                item["latestReport"]["id"],
                reports[item["subject"]]["id"],
            )
            self.assertEqual(
                item["latestReport"]["sessionId"],
                item["session"]["id"],
            )
        self.assertEqual(
            refreshed.json["latestReport"]["id"],
            refreshed.json["items"][0]["latestReport"]["id"],
        )

        invalid = self.client.get(
            "/api/learning/reports/latest",
            query_string={"childId": self.child_id, "subject": "science"},
            headers=self._headers(),
        )
        self.assertEqual(invalid.status_code, 400, invalid.json)
        self.assertEqual(invalid.json["error"], "invalid_learning_subject")

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_second_attempt_answers_do_not_inflate_independent_mastery(self):
        assigned = self._assign(date_value="2026-08-13")
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(),
        ).json
        session_id = started["session"]["id"]
        correct_answers = self._correct_answers_for_task(assigned["task"]["id"])
        last = None
        for expected in correct_answers:
            wrong = self.client.post(
                f"/api/learning/sessions/{session_id}/answer",
                json={"answer": "-999"},
                headers=self._headers(),
            )
            self.assertFalse(wrong.json["correct"])
            self.assertIsNotNone(wrong.json["hint"])
            self.assertTrue(wrong.json["canRetry"])
            self.assertEqual(wrong.json["hintLevel"], 1)
            self.assertEqual(wrong.json["session"]["hintCount"], correct_answers.index(expected) + 1)
            last = self.client.post(
                f"/api/learning/sessions/{session_id}/answer",
                json={"answer": expected},
                headers=self._headers(),
            )
            self.assertTrue(last.json["correct"])
            self.assertFalse(last.json["canRetry"])
            self.assertEqual(last.json["hintLevel"], 0)
        self.assertTrue(last.json["completed"])
        self.assertEqual(last.json["report"]["correctCount"], 5)
        self.assertEqual(last.json["report"]["independentCorrectCount"], 0)
        self.assertEqual(last.json["report"]["hintCount"], 5)
        self.assertEqual(last.json["report"]["score"], 0)
        self.assertEqual(last.json["report"]["masteryLevel"], "needs_practice")

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_second_wrong_answer_advances_and_disables_retry(self):
        assigned = self._assign(date_value="2026-08-14")
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(),
        ).json
        session_id = started["session"]["id"]
        first_question_id = started["session"]["currentQuestion"]["id"]

        first_wrong = self.client.post(
            f"/api/learning/sessions/{session_id}/answer",
            json={"answer": "-1"},
            headers=self._headers(),
        ).json
        self.assertTrue(first_wrong["canRetry"])
        self.assertEqual(first_wrong["nextQuestion"]["id"], first_question_id)

        second_wrong = self.client.post(
            f"/api/learning/sessions/{session_id}/answer",
            json={"answer": "-2"},
            headers=self._headers(),
        ).json
        self.assertFalse(second_wrong["correct"])
        self.assertFalse(second_wrong["canRetry"])
        self.assertEqual(second_wrong["hintLevel"], 0)
        self.assertNotEqual(second_wrong["nextQuestion"]["id"], first_question_id)

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_structured_choice_and_sequence_responses_use_deterministic_evaluator(self):
        assigned = self._assign(date_value="2026-09-04")
        task_id = assigned["task"]["id"]
        content = {
            "intro": "结构化作答测试",
            "estimatedMinutes": 5,
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "questions": [
                {
                    "id": "choice_contract",
                    "type": "single_choice",
                    "prompt": "请选择动词",
                    "skill": "词性",
                    "hint": "表示动作的词是动词。",
                    "explanation": "跑表示动作。",
                    "choices": [
                        {"id": "noun", "label": "桌子", "correct": False},
                        {"id": "verb", "label": "跑", "correct": True},
                    ],
                    "evaluation": {"expectedOptionId": "verb"},
                },
                {
                    "id": "sequence_contract",
                    "type": "sequence",
                    "prompt": "按顺序排列",
                    "skill": "顺序",
                    "hint": "先一，再二，最后三。",
                    "explanation": "正确顺序是一、二、三。",
                    "choices": [
                        {"id": "one", "label": "一"},
                        {"id": "two", "label": "二"},
                        {"id": "three", "label": "三"},
                    ],
                    "evaluation": {
                        "expectedSequence": ["one", "two", "three"]
                    },
                },
            ],
        }
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_courses AS course
                JOIN tasks AS task
                  ON task.learning_course_id = course.id
                 AND task.learning_course_version = course.version
                SET course.content_json = ?
                WHERE task.id = ?
                """,
                (json.dumps(content, ensure_ascii=False), task_id),
            )

        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": task_id},
            headers=self._headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        question = started.json["session"]["currentQuestion"]
        self.assertEqual(question["inputMode"], "single_choice")
        self.assertTrue(
            all(item["id"].startswith("choice_") for item in question["choices"])
        )
        self.assertNotIn("noun", {item["id"] for item in question["choices"]})
        resumed = self.client.post(
            "/api/learning/sessions",
            json={"taskId": task_id},
            headers=self._headers(),
        )
        self.assertEqual(
            resumed.json["session"]["currentQuestion"]["choices"],
            question["choices"],
        )
        self.assertNotIn("answer", question)
        self.assertNotIn("evaluation", question)

        session_id = started.json["session"]["id"]
        verb_choice_id = next(
            item["id"] for item in question["choices"] if item["label"] == "跑"
        )
        choice = self.client.post(
            f"/api/learning/sessions/{session_id}/answer",
            json={
                "response": {
                    "kind": "single_choice",
                    "optionId": verb_choice_id,
                }
            },
            headers=self._headers(),
        )
        self.assertEqual(choice.status_code, 200, choice.json)
        self.assertTrue(choice.json["correct"])
        self.assertEqual(choice.json["nextQuestion"]["inputMode"], "sequence")
        self.assertNotEqual(
            [item["id"] for item in choice.json["nextQuestion"]["choices"]],
            ["one", "two", "three"],
        )

        sequence_choice_ids = {
            item["label"]: item["id"]
            for item in choice.json["nextQuestion"]["choices"]
        }
        sequence = self.client.post(
            f"/api/learning/sessions/{session_id}/answer",
            json={
                "response": {
                    "kind": "sequence",
                    "items": [
                        sequence_choice_ids["一"],
                        sequence_choice_ids["二"],
                        sequence_choice_ids["三"],
                    ],
                }
            },
            headers=self._headers(),
        )
        self.assertEqual(sequence.status_code, 200, sequence.json)
        self.assertTrue(sequence.json["correct"])
        self.assertTrue(sequence.json["completed"])

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_unsupported_question_contract_fails_closed(self):
        assigned = self._assign(date_value="2026-09-05")
        task_id = assigned["task"]["id"]
        content = {
            "intro": "不可执行课程测试",
            "questions": [
                {
                    "id": "unsafe_rubric",
                    "type": "llm_rubric",
                    "prompt": "自由回答",
                    "skill": "开放表达",
                    "hint": "",
                    "explanation": "",
                    "evaluation": {"prompt": "让模型自行打分"},
                }
            ],
        }
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_courses AS course
                JOIN tasks AS task
                  ON task.learning_course_id = course.id
                 AND task.learning_course_version = course.version
                SET course.content_json = ?
                WHERE task.id = ?
                """,
                (json.dumps(content, ensure_ascii=False), task_id),
            )
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": task_id},
            headers=self._headers(),
        ).json
        response = self.client.post(
            f"/api/learning/sessions/{started['session']['id']}/answer",
            json={"response": {"kind": "text", "value": "任意回答"}},
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 503, response.json)
        self.assertEqual(response.json["error"], "learning_question_not_executable")

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_report_does_not_promise_new_skill_when_none_is_published(self):
        assigned = self._assign(date_value="2026-08-15")
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(),
        ).json
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE learning_courses
                SET status = 'retired'
                WHERE grade_code = 'primary_3' AND node_code <> ?
                """,
                (assigned["recommendation"]["nodeCode"],),
            )

        last = None
        for expected in self._correct_answers_for_task(assigned["task"]["id"]):
            last = self.client.post(
                f"/api/learning/sessions/{started['session']['id']}/answer",
                json={"answer": expected},
                headers=self._headers(),
            )
            self.assertEqual(last.status_code, 200, last.json)

        self.assertTrue(last.json["completed"])
        self.assertEqual(
            last.json["report"]["nextStep"],
            "下一次按复习日期巩固本年级已学能力点。",
        )
        self.assertNotIn("下一个", last.json["report"]["nextStep"])

    def test_all_practiced_courses_use_review_date_then_oldest_practice(self):
        seeded = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-08-12"},
            headers=self._headers(),
        )
        self.assertEqual(seeded.status_code, 200, seeded.json)
        database = Database(self.app.config["DATABASE_URL"])
        repository = LearningRepository(database)
        with database.transaction() as conn:
            child = conn.execute(
                "SELECT family_id FROM children WHERE id = ?",
                (self.child_id,),
            ).fetchone()
            courses = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE grade_code = 'primary_3' AND subject = 'math'
                  AND status = 'published'
                ORDER BY node_code
                """
            ).fetchall()
            self.assertEqual(len(courses), 3)
            review_dates = {
                "multi_digit_operations": "2026-09-01",
                "perimeter_area_intro": "2026-08-11",
                "remainder_division": "2026-08-10",
            }
            practiced_at = {
                "multi_digit_operations": 3000,
                "perimeter_area_intro": 2000,
                "remainder_division": 1000,
            }
            for course in courses:
                repository.upsert_mastery_state(
                    conn,
                    family_id=child["family_id"],
                    child_id=self.child_id,
                    node_code=course["node_code"],
                    subject=course["subject"],
                    grade_code=course["grade_code"],
                    attempts=5,
                    correct_count=5,
                    independent_correct_count=5,
                    hint_count=0,
                    latest_score=100,
                    mastery_level="mastered",
                    last_practiced_at=practiced_at[course["node_code"]],
                    next_review_date=review_dates[course["node_code"]],
                    course_id=course["id"],
                    course_version=course["version"],
                    now=4000,
                )

            earliest_review = repository.get_recommended_course(
                conn,
                family_id=child["family_id"],
                child_id=self.child_id,
                grade_code="primary_3",
                learning_date="2026-08-12",
                subject="math",
            )
        self.assertEqual(earliest_review["node_code"], "remainder_division")

        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_mastery_states
                SET next_review_date = '2026-08-10',
                    last_practiced_at = CASE node_code
                      WHEN 'perimeter_area_intro' THEN 1000
                      WHEN 'remainder_division' THEN 2000
                      ELSE last_practiced_at
                    END
                WHERE child_id = ?
                  AND node_code IN ('perimeter_area_intro', 'remainder_division')
                """,
                (self.child_id,),
            )
            oldest_practice = repository.get_recommended_course(
                conn,
                family_id=child["family_id"],
                child_id=self.child_id,
                grade_code="primary_3",
                learning_date="2026-08-12",
                subject="math",
            )
        self.assertEqual(oldest_practice["node_code"], "perimeter_area_intro")

    def test_all_primary_grades_receive_three_runnable_subjects(self):
        for grade in range(1, 7):
            phone = f"1380000211{grade}"
            token = self._login(phone)
            child_id = self._create_child(f"primary_{grade}", token=token)
            response = self.client.get(
                "/api/learning/today",
                query_string={"childId": child_id, "date": "2026-09-01"},
                headers=self._headers(token),
            )
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(
                response.json["recommendation"]["gradeCode"],
                f"primary_{grade}",
            )
            self.assertEqual(len(response.json["items"]), 3)
            self.assertEqual(
                {item["subject"] for item in response.json["items"]},
                {"chinese", "math", "english"},
            )
            self.assertGreater(response.json["recommendation"]["questionCount"], 0)

    @unittest.skip(LEGACY_PARENT_MUTATION_REMOVED)
    def test_family_isolation_hides_child_task_session_and_report(self):
        assigned = self._assign()
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(),
        ).json
        other_token = self._login("13800002102")

        cross_child = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id},
            headers=self._headers(other_token),
        )
        self.assertEqual(cross_child.status_code, 404)

        cross_task = self.client.post(
            "/api/learning/sessions",
            json={"taskId": assigned["task"]["id"]},
            headers=self._headers(other_token),
        )
        self.assertEqual(cross_task.status_code, 404)

        cross_session = self.client.post(
            f"/api/learning/sessions/{started['session']['id']}/answer",
            json={"answer": "395"},
            headers=self._headers(other_token),
        )
        self.assertEqual(cross_session.status_code, 404)

    def _assign(self, date_value: str = "2026-08-12") -> dict:
        response = self.client.post(
            "/api/learning/today/assign",
            json={
                "childId": self.child_id,
                "date": date_value,
                "scheduledStart": "19:30",
            },
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def _learning_write_counts(self) -> tuple[int, int]:
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            task_count = conn.execute(
                "SELECT COUNT(*) AS count FROM tasks"
            ).fetchone()["count"]
            session_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_sessions"
            ).fetchone()["count"]
        return int(task_count), int(session_count)

    def _correct_answers_for_task(self, task_id: str) -> list[object]:
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            row = conn.execute(
                """
                SELECT course.content_json
                FROM tasks AS task
                JOIN learning_courses AS course
                  ON course.id = task.learning_course_id
                 AND course.version = task.learning_course_version
                WHERE task.id = ?
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        content = json.loads(row["content_json"])
        answers: list[object] = []
        for question in content["questions"]:
            question_type = question.get("type")
            evaluation = question.get("evaluation") or {}
            if question_type == "accepted_text":
                accepted = (
                    evaluation.get("acceptedAnswers")
                    or question.get("acceptedAnswers")
                    or question.get("answer")
                )
                answers.append(accepted[0])
                continue
            if question_type == "sequence":
                answers.append(
                    list(
                        evaluation.get("expectedSequence")
                        or question.get("answer")
                    )
                )
                continue
            if "answer" in question:
                answers.append(question["answer"])
                continue
            if "expectedOptionId" in evaluation:
                answers.append({"optionId": evaluation["expectedOptionId"]})
            elif "expectedSequence" in evaluation:
                answers.append(list(evaluation["expectedSequence"]))
            elif "acceptedAnswers" in evaluation:
                answers.append(evaluation["acceptedAnswers"][0])
            else:
                answers.append(evaluation.get("expected"))
        return answers

    def _complete_task(self, task_id: str) -> dict:
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": task_id},
            headers=self._headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        session_id = started.json["session"]["id"]
        result = None
        for answer in self._correct_answers_for_task(task_id):
            result = self.client.post(
                f"/api/learning/sessions/{session_id}/answer",
                json={"answer": answer},
                headers=self._headers(),
            )
            self.assertEqual(result.status_code, 200, result.json)
            self.assertTrue(result.json["correct"])
        self.assertIsNotNone(result)
        self.assertTrue(result.json["completed"])
        return result.json["report"]

    def _login(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        response = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _create_child(self, grade_code: str, *, token: str | None = None) -> str:
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "家长",
                "relationship": "家长",
                "relationshipKey": "other",
            },
            headers=self._headers(token),
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        response = self.client.post(
            "/api/setup/child",
            json={
                "name": f"{grade_code}孩子",
                "nickname": f"{grade_code}孩子",
                "gradeCode": grade_code,
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._headers(token),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["child"]["id"]

    def _headers(self, token: str | None = None) -> dict:
        return {"Authorization": f"Bearer {token or self.access_token}"}

if __name__ == "__main__":
    unittest.main()
