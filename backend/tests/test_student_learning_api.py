from __future__ import annotations

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier, Event, local

from app import create_app
from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.learning_repository import LearningRepository
from services.formal_student_learning_access import assert_formal_student_grade_open
from tests.fixtures.primary_subject_catalog import PRIMARY_COURSE_CATALOG
from tests.support import fresh_test_config, request_debug_code


class StudentLearningApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.app.extensions["mira_formal_learning_access_checker"] = (
            lambda conn, child: assert_formal_student_grade_open(child)
        )
        self.client = self.app.test_client()
        LearningRepository(
            Database(self.app.config["DATABASE_URL"])
        ).ensure_published_courses(
            PRIMARY_COURSE_CATALOG,
            now=int(datetime.now().timestamp() * 1000),
        )
        self.parent_access_token = self._login_parent("13800002911")
        self._create_parent_identity()
        self.child_id = self._create_child("乐乐", "primary_1")
        self.sibling_id = self._insert_sibling("安安")
        self.student_access_token = self._pair_student(self.child_id, "2468")

    def test_student_today_retains_automatic_assignment_without_starting_session(self):
        before = self._learning_write_counts()

        response = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": "2026-09-14"},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["itemCount"], 3)
        self.assertTrue(all(item["task"] is not None for item in response.json["items"]))
        after = self._learning_write_counts()
        self.assertEqual(after[0] - before[0], 3)
        self.assertEqual(after[1], before[1])

    def test_today_carries_one_recent_started_lesson_without_rewriting_history(self):
        target_date = datetime.now().date()
        origin_date = target_date - timedelta(days=1)
        origin = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": origin_date.isoformat()},
            headers=self._student_headers(),
        )
        self.assertEqual(origin.status_code, 200, origin.json)
        source_task_id = origin.json["items"][0]["task"]["id"]
        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": source_task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        source_session_id = started.json["session"]["id"]

        today = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": target_date.isoformat()},
            headers=self._student_headers(),
        )
        self.assertEqual(today.status_code, 200, today.json)
        self.assertEqual(today.json["itemCount"], 3)
        self.assertEqual(today.json["carryoverCount"], 1)
        self.assertEqual(today.json["newCount"], 2)
        carried = next(
            item for item in today.json["items"] if item["dayBucket"] == "carryover"
        )
        self.assertEqual(carried["task"]["id"], source_task_id)
        self.assertEqual(carried["session"]["id"], source_session_id)
        self.assertEqual(carried["originDate"], origin_date.isoformat())
        self.assertEqual(carried["carryover"]["daysOverdue"], 1)
        self.assertEqual(carried["state"], "in_progress")

        replay = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": target_date.isoformat()},
            headers=self._student_headers(),
        )
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertEqual(replay.json["carryoverCount"], 1)
        self.assertEqual(
            next(
                item
                for item in replay.json["items"]
                if item["dayBucket"] == "carryover"
            )["task"]["id"],
            source_task_id,
        )

        resumed = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": source_task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(resumed.status_code, 200, resumed.json)
        self.assertTrue(resumed.json["resumed"])
        self.assertEqual(resumed.json["session"]["id"], source_session_id)

        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            source = conn.execute(
                "SELECT scheduled_date, status FROM tasks WHERE id = ?",
                (source_task_id,),
            ).fetchone()
            target_task_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM tasks
                    WHERE child_id = ? AND scheduled_date = ?
                      AND type = 'learning' AND status <> 'cancelled'
                    """,
                    (self.child_id, target_date.isoformat()),
                ).fetchone()["count"]
            )
            carryover_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM learning_task_carryovers
                    WHERE child_id = ? AND target_date = ?
                    """,
                    (self.child_id, target_date.isoformat()),
                ).fetchone()["count"]
            )
        self.assertEqual(source["scheduled_date"], origin_date.isoformat())
        self.assertEqual(source["status"], "in_progress")
        self.assertEqual(target_task_count, 2)
        self.assertEqual(carryover_count, 1)

        makeup = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "makeup"},
            headers=self._student_headers(),
        )
        self.assertEqual(makeup.status_code, 200, makeup.json)
        self.assertNotIn(
            source_task_id,
            {item["taskId"] for item in makeup.json["items"]},
        )
        self.assertGreaterEqual(len(makeup.json["items"]), 2)

    def test_today_does_not_auto_stack_lessons_older_than_two_days(self):
        target_date = datetime.now().date()
        old_date = target_date - timedelta(days=3)
        old = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": old_date.isoformat()},
            headers=self._student_headers(),
        )
        self.assertEqual(old.status_code, 200, old.json)
        old_task_ids = {item["task"]["id"] for item in old.json["items"]}

        today = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": target_date.isoformat()},
            headers=self._student_headers(),
        )
        self.assertEqual(today.status_code, 200, today.json)
        self.assertEqual(today.json["itemCount"], 3)
        self.assertEqual(today.json["carryoverCount"], 0)
        self.assertTrue(
            old_task_ids.isdisjoint(
                {item["task"]["id"] for item in today.json["items"]}
            )
        )

        makeup = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "makeup"},
            headers=self._student_headers(),
        )
        self.assertEqual(makeup.status_code, 200, makeup.json)
        self.assertTrue(
            old_task_ids.issubset(
                {item["taskId"] for item in makeup.json["items"]}
            )
        )

    def test_newer_equivalent_assignment_supersedes_old_makeup_entry(self):
        target_date = datetime.now().date()
        origin_date = target_date - timedelta(days=1)
        old_task_id = "task_old_equivalent_lesson"
        new_task_id = "task_new_equivalent_lesson"
        timestamp = now_ms()
        database = Database(self.app.config["DATABASE_URL"])
        repository = LearningRepository(database)

        with database.transaction() as conn:
            family = conn.execute(
                "SELECT family_id FROM children WHERE id = ? LIMIT 1",
                (self.child_id,),
            ).fetchone()
            course = conn.execute(
                """
                SELECT id, version, node_code
                FROM learning_courses
                WHERE grade_code = 'primary_1'
                ORDER BY subject, node_code, id
                LIMIT 1
                """
            ).fetchone()
            self.assertIsNotNone(family)
            self.assertIsNotNone(course)
            for task_id, status, learning_date, created_at in (
                (old_task_id, "missed", origin_date.isoformat(), timestamp),
                (new_task_id, "scheduled", target_date.isoformat(), timestamp + 1),
            ):
                conn.execute(
                    """
                    INSERT INTO tasks(
                      id, family_id, child_id, title, type, status,
                      scheduled_date, created_at, updated_at,
                      learning_course_id, learning_course_version, learning_slot
                    ) VALUES (?, ?, ?, ?, 'learning', ?, ?, ?, ?, ?, ?, 'core')
                    """,
                    (
                        task_id,
                        family["family_id"],
                        self.child_id,
                        "等价课程去重验证",
                        status,
                        learning_date,
                        created_at,
                        created_at,
                        course["id"],
                        course["version"],
                    ),
                )

            candidates = repository.list_carryover_candidates(
                conn,
                family_id=family["family_id"],
                child_id=self.child_id,
                earliest_date=origin_date.isoformat(),
                target_date=target_date.isoformat(),
            )
            backlog_count = repository.count_learning_backlog(
                conn,
                family_id=family["family_id"],
                child_id=self.child_id,
                before_date=target_date.isoformat(),
            )

        self.assertNotIn(old_task_id, {row["id"] for row in candidates})
        self.assertEqual(backlog_count, 0)

        all_courses = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "all"},
            headers=self._student_headers(),
        )
        self.assertEqual(all_courses.status_code, 200, all_courses.json)
        matching = [
            item
            for item in all_courses.json["items"]
            if item["course"]["nodeCode"] == course["node_code"]
        ]
        self.assertEqual([item["taskId"] for item in matching], [new_task_id])

        makeup = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "makeup"},
            headers=self._student_headers(),
        )
        self.assertEqual(makeup.status_code, 200, makeup.json)
        self.assertNotIn(old_task_id, {item["taskId"] for item in makeup.json["items"]})

    def test_student_today_rechecks_grade_inside_task_write_transaction(self):
        gate_calls = 0

        def switch_grade_after_auth_gate(conn, child):
            del conn
            nonlocal gate_calls
            gate_calls += 1
            assert_formal_student_grade_open(child)
            if gate_calls != 1:
                return
            with Database(self.app.config["DATABASE_URL"]).transaction() as update_conn:
                update_conn.execute(
                    """
                    UPDATE children
                    SET grade_code = 'primary_2', grade_selection_revision =
                      grade_selection_revision + 1
                    WHERE id = ?
                    """,
                    (self.child_id,),
                )

        self.app.extensions["mira_formal_learning_access_checker"] = (
            switch_grade_after_auth_gate
        )
        before = self._learning_write_counts()

        response = self.client.get(
            "/api/v2/student/learning/today",
            query_string={"date": "2026-09-15"},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_grade_not_open")
        self.assertGreaterEqual(gate_calls, 2)
        self.assertEqual(self._learning_write_counts(), before)

    def test_student_assign_rechecks_grade_inside_task_write_transaction(self):
        gate_calls = 0

        def switch_grade_after_auth_gate(conn, child):
            del conn
            nonlocal gate_calls
            gate_calls += 1
            assert_formal_student_grade_open(child)
            if gate_calls != 1:
                return
            with Database(self.app.config["DATABASE_URL"]).transaction() as update_conn:
                update_conn.execute(
                    """
                    UPDATE children
                    SET grade_code = 'primary_2', grade_selection_revision =
                      grade_selection_revision + 1
                    WHERE id = ?
                    """,
                    (self.child_id,),
                )

        self.app.extensions["mira_formal_learning_access_checker"] = (
            switch_grade_after_auth_gate
        )
        before = self._learning_write_counts()

        response = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-16", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_grade_not_open")
        self.assertGreaterEqual(gate_calls, 2)
        self.assertEqual(self._learning_write_counts(), before)

    def test_student_start_rechecks_revision_inside_session_write_transaction(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-17", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            initial_revision = int(
                conn.execute(
                    "SELECT grade_selection_revision FROM children WHERE id = ?",
                    (self.child_id,),
                ).fetchone()["grade_selection_revision"]
            )

        gate_calls = 0

        def advance_revision_after_auth_gate(conn, child):
            del conn
            nonlocal gate_calls
            gate_calls += 1
            assert_formal_student_grade_open(child)
            if gate_calls == 1:
                with Database(self.app.config["DATABASE_URL"]).transaction() as update_conn:
                    update_conn.execute(
                        """
                        UPDATE children
                        SET grade_selection_revision = grade_selection_revision + 1
                        WHERE id = ?
                        """,
                        (self.child_id,),
                    )
                return
            if int(child["grade_selection_revision"]) != initial_revision:
                raise ApiError(
                    "student_learning_release_not_ready",
                    "该年级正式课程尚未准备完成",
                    409,
                )

        student_service = self.app.extensions["mira_student_learning_service"]
        student_service.student_auth_service.formal_learning_access_checker = (
            advance_revision_after_auth_gate
        )
        before = self._learning_write_counts()

        response = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_release_not_ready")
        self.assertGreaterEqual(gate_calls, 2)
        self.assertEqual(self._learning_write_counts(), before)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            task = conn.execute(
                "SELECT status FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        self.assertEqual(task["status"], "scheduled")

    def test_student_answer_rechecks_revision_inside_answer_write_transaction(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-18", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        session_id = started.json["session"]["id"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            initial_revision = int(
                conn.execute(
                    "SELECT grade_selection_revision FROM children WHERE id = ?",
                    (self.child_id,),
                ).fetchone()["grade_selection_revision"]
            )
            before_session = conn.execute(
                """
                SELECT attempted_count, correct_count, current_question_index,
                  answers_json
                FROM learning_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            before_events = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_events
                    WHERE task_id = ? AND event_type = 'learning_answer_evaluated'
                    """,
                    (task_id,),
                ).fetchone()["count"]
            )

        gate_calls = 0

        def advance_revision_after_auth_gate(conn, child):
            del conn
            nonlocal gate_calls
            gate_calls += 1
            assert_formal_student_grade_open(child)
            if gate_calls == 1:
                with Database(self.app.config["DATABASE_URL"]).transaction() as update_conn:
                    update_conn.execute(
                        """
                        UPDATE children
                        SET grade_selection_revision = grade_selection_revision + 1
                        WHERE id = ?
                        """,
                        (self.child_id,),
                    )
                return
            if int(child["grade_selection_revision"]) != initial_revision:
                raise ApiError(
                    "student_learning_release_not_ready",
                    "该年级正式课程尚未准备完成",
                    409,
                )

        student_service = self.app.extensions["mira_student_learning_service"]
        student_service.student_auth_service.formal_learning_access_checker = (
            advance_revision_after_auth_gate
        )

        response = self.client.post(
            f"/api/v2/student/learning/sessions/{session_id}/answer",
            json={"answer": self._correct_answers_for_task(task_id)[0]},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "student_learning_release_not_ready")
        self.assertGreaterEqual(gate_calls, 2)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            after_session = conn.execute(
                """
                SELECT attempted_count, correct_count, current_question_index,
                  answers_json
                FROM learning_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            after_events = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_events
                    WHERE task_id = ? AND event_type = 'learning_answer_evaluated'
                    """,
                    (task_id,),
                ).fetchone()["count"]
            )
        self.assertEqual(dict(after_session), dict(before_session))
        self.assertEqual(after_events, before_events)

    def test_concurrent_answers_append_both_attempts_without_overwriting(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-19", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        session_id = started.json["session"]["id"]
        submitted_answer = self._correct_answers_for_task(task_id)[0]
        barrier = Barrier(2)

        class BarrierRepository(LearningRepository):
            def __init__(self, database):
                super().__init__(database)
                self._thread_state = local()

            def get_session(
                self,
                conn,
                *,
                family_id: str,
                session_id: str,
                for_update: bool = False,
            ):
                row = super().get_session(
                    conn,
                    family_id=family_id,
                    session_id=session_id,
                    **({"for_update": True} if for_update else {}),
                )
                if not for_update and not getattr(
                    self._thread_state, "initial_read_seen", False
                ):
                    self._thread_state.initial_read_seen = True
                    barrier.wait(timeout=10)
                return row

        student_service = self.app.extensions["mira_student_learning_service"]
        student_service.learning_service.repository = BarrierRepository(
            Database(self.app.config["DATABASE_URL"])
        )
        context = student_service.student_auth_service.authenticate(
            self.student_access_token
        )

        def answer_once():
            with student_service._auth_adapter.bind(context):
                return student_service.learning_service.answer(
                    self.student_access_token,
                    session_id,
                    {"answer": submitted_answer},
                    formal_student_child_id=self.child_id,
                )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: answer_once(), range(2)))
        self.assertEqual(len(results), 2)

        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            session = conn.execute(
                """
                SELECT attempted_count, answers_json
                FROM learning_sessions WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
            event_count = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_events
                    WHERE task_id = ? AND event_type = 'learning_answer_evaluated'
                    """,
                    (task_id,),
                ).fetchone()["count"]
            )
        self.assertEqual(int(session["attempted_count"]), 2)
        self.assertEqual(len(json.loads(session["answers_json"])), 2)
        self.assertEqual(event_count, 2)

    def test_start_rereads_locked_task_after_concurrent_course_replacement(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-20", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            original = conn.execute(
                """
                SELECT learning_course_id, learning_course_version
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            replacement = conn.execute(
                """
                SELECT id, version, title, objective
                FROM learning_courses
                WHERE grade_code = 'primary_1' AND status = 'published'
                  AND NOT (id = ? AND version = ?)
                ORDER BY id, version
                LIMIT 1
                """,
                (
                    original["learning_course_id"],
                    original["learning_course_version"],
                ),
            ).fetchone()
        self.assertIsNotNone(replacement)
        initial_read = Barrier(2)
        replacement_committed = Event()

        class BarrierRepository(LearningRepository):
            def __init__(self, database):
                super().__init__(database)
                self._thread_state = local()

            def get_task(
                self,
                conn,
                *,
                family_id: str,
                task_id: str,
                for_update: bool = False,
            ):
                row = super().get_task(
                    conn,
                    family_id=family_id,
                    task_id=task_id,
                    **({"for_update": True} if for_update else {}),
                )
                if not for_update and not getattr(
                    self._thread_state, "initial_read_seen", False
                ):
                    self._thread_state.initial_read_seen = True
                    initial_read.wait(timeout=10)
                    if not replacement_committed.wait(timeout=10):
                        raise TimeoutError("replacement did not commit")
                return row

        student_service = self.app.extensions["mira_student_learning_service"]
        student_service.learning_service.repository = BarrierRepository(
            Database(self.app.config["DATABASE_URL"])
        )
        context = student_service.student_auth_service.authenticate(
            self.student_access_token
        )

        def start_once():
            with student_service._auth_adapter.bind(context):
                return student_service.learning_service.start_session(
                    self.student_access_token,
                    {"taskId": task_id},
                    formal_student_child_id=self.child_id,
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(start_once)
            initial_read.wait(timeout=10)
            try:
                with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
                    conn.execute(
                        """
                        UPDATE tasks
                        SET learning_course_id = ?, learning_course_version = ?,
                          title = ?, description = ?, updated_at = updated_at + 1
                        WHERE id = ?
                        """,
                        (
                            replacement["id"],
                            replacement["version"],
                            replacement["title"],
                            replacement["objective"],
                            task_id,
                        ),
                    )
            finally:
                replacement_committed.set()
            future.result(timeout=10)

        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            session = conn.execute(
                """
                SELECT course_id, course_version
                FROM learning_sessions WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        self.assertEqual(
            (session["course_id"], session["course_version"]),
            (replacement["id"], replacement["version"]),
        )

    def test_start_rejects_task_from_previous_formal_release_without_writes(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-21", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            task = conn.execute(
                """
                SELECT learning_course_id, learning_course_version, status
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
            current_course = conn.execute(
                """
                SELECT id, version FROM learning_courses
                WHERE grade_code = 'primary_1' AND status = 'published'
                  AND NOT (id = ? AND version = ?)
                ORDER BY id, version LIMIT 1
                """,
                (task["learning_course_id"], task["learning_course_version"]),
            ).fetchone()
        fixture = self._install_release_classroom_fixture(
            course_id=current_course["id"],
            course_version=current_course["version"],
        )
        self._activate_formal_pointer(fixture["release_id"])
        student_service = self.app.extensions["mira_student_learning_service"]
        student_service.learning_service.static_catalog_enabled = False
        before = self._learning_write_counts()

        response = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(response.json["error"], "learning_classroom_release_changed")
        self.assertEqual(self._learning_write_counts(), before)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            after_task = conn.execute(
                "SELECT status FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            started_events = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_events
                    WHERE task_id = ? AND event_type = 'learning_session_started'
                    """,
                    (task_id,),
                ).fetchone()["count"]
            )
        self.assertEqual(after_task["status"], task["status"])
        self.assertEqual(started_events, 0)

    def test_start_accepts_task_from_exact_active_formal_release(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-22", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            task = conn.execute(
                """
                SELECT learning_course_id, learning_course_version
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        fixture = self._install_release_classroom_fixture(
            course_id=task["learning_course_id"],
            course_version=task["learning_course_version"],
        )
        self._activate_formal_pointer(fixture["release_id"])
        student_service = self.app.extensions["mira_student_learning_service"]
        student_service.learning_service.static_catalog_enabled = False

        response = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=self._student_headers(),
        )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(
            response.json["session"]["courseId"],
            task["learning_course_id"],
        )
        self.assertEqual(
            response.json["session"]["courseVersion"],
            task["learning_course_version"],
        )

    def test_student_completes_learning_loop_and_external_child_id_is_ignored(self):
        today = self.client.get(
            "/api/v2/student/learning/today",
            query_string={
                "childId": self.sibling_id,
                "date": "2026-09-01",
            },
            headers=self._student_headers(),
        )
        self.assertEqual(today.status_code, 200, today.json)
        self.assertEqual(today.json["childId"], self.child_id)
        self.assertEqual(today.json["itemCount"], 3)
        self.assertEqual(
            {item["subject"] for item in today.json["items"]},
            {"chinese", "math", "english"},
        )

        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={
                "childId": self.sibling_id,
                "date": "2026-09-01",
                "scheduledStart": "18:45",
            },
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        self.assertEqual(assigned.json["childId"], self.child_id)
        self.assertEqual(assigned.json["task"]["childId"], self.child_id)

        task_id = assigned.json["task"]["id"]
        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id, "childId": self.sibling_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        self.assertFalse(started.json["resumed"])
        session_id = started.json["session"]["id"]

        completed = None
        for answer in self._correct_answers_for_task(task_id):
            completed = self.client.post(
                f"/api/v2/student/learning/sessions/{session_id}/answer",
                json={"answer": answer, "childId": self.sibling_id},
                headers=self._student_headers(),
            )
            self.assertEqual(completed.status_code, 200, completed.json)
            self.assertTrue(completed.json["correct"])
        self.assertIsNotNone(completed)
        self.assertTrue(completed.json["completed"])
        self.assertEqual(completed.json["report"]["childId"], self.child_id)

        latest = self.client.get(
            "/api/v2/student/learning/reports/latest",
            query_string={
                "childId": self.sibling_id,
                "subject": completed.json["report"]["subject"],
            },
            headers=self._student_headers(),
        )
        self.assertEqual(latest.status_code, 200, latest.json)
        self.assertEqual(latest.json["report"]["childId"], self.child_id)
        self.assertEqual(
            latest.json["report"]["id"],
            completed.json["report"]["id"],
        )

    def test_student_cannot_open_sibling_task_or_session(self):
        sibling_student_token = self._pair_student(self.sibling_id, "1357")
        sibling_assignment = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={
                "childId": self.sibling_id,
                "date": "2026-09-02",
                "scheduledStart": "19:00",
            },
            headers=self._student_headers(sibling_student_token),
        )
        self.assertEqual(sibling_assignment.status_code, 200, sibling_assignment.json)
        sibling_task_id = sibling_assignment.json["task"]["id"]

        cross_task = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": sibling_task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(cross_task.status_code, 404, cross_task.json)
        self.assertEqual(cross_task.json["error"], "task_not_found")

        sibling_started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": sibling_task_id},
            headers=self._student_headers(sibling_student_token),
        )
        self.assertEqual(sibling_started.status_code, 200, sibling_started.json)
        sibling_session_id = sibling_started.json["session"]["id"]

        cross_session = self.client.post(
            f"/api/v2/student/learning/sessions/{sibling_session_id}/answer",
            json={"answer": "test"},
            headers=self._student_headers(),
        )
        self.assertEqual(cross_session.status_code, 404, cross_session.json)
        self.assertEqual(
            cross_session.json["error"],
            "learning_session_not_found",
        )

    def test_student_library_continue_favorite_detail_and_completed_history(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-03", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        task_id = assigned.json["task"]["id"]
        course_id = assigned.json["recommendation"]["courseId"]
        course_version = assigned.json["recommendation"]["courseVersion"]

        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)

        library = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "continue", "limit": 1},
            headers=self._student_headers(),
        )
        self.assertEqual(library.status_code, 200, library.json)
        self.assertEqual(library.json["continueItem"]["taskId"], task_id)
        self.assertEqual(library.json["items"][0]["taskId"], task_id)
        self.assertFalse(library.json["items"][0]["favorite"])
        self.assertFalse(library.json["items"][0]["classroomAvailable"])
        self.assertFalse(library.json["items"][0]["packageClassroomAvailable"])
        self.assertFalse(library.json["items"][0]["fullClassroomAvailable"])

        favorite = self.client.put(
            f"/api/v2/student/learning/courses/{course_id}/versions/"
            f"{course_version}/favorite",
            headers=self._student_headers(),
        )
        self.assertEqual(favorite.status_code, 200, favorite.json)
        self.assertTrue(favorite.json["favorite"])

        favorites = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "favorites"},
            headers=self._student_headers(),
        )
        self.assertEqual(favorites.status_code, 200, favorites.json)
        self.assertEqual(favorites.json["items"][0]["course"]["id"], course_id)
        self.assertTrue(favorites.json["items"][0]["favorite"])

        detail = self.client.get(
            f"/api/v2/student/learning/courses/{course_id}",
            query_string={"version": course_version},
            headers=self._student_headers(),
        )
        self.assertEqual(detail.status_code, 200, detail.json)
        self.assertEqual(detail.json["item"]["taskId"], task_id)
        self.assertIn("intro", detail.json["item"]["course"])
        self.assertFalse(detail.json["item"]["packageClassroomAvailable"])
        self.assertFalse(detail.json["item"]["fullClassroomAvailable"])

        session_id = started.json["session"]["id"]
        completed = None
        for answer in self._correct_answers_for_task(task_id):
            completed = self.client.post(
                f"/api/v2/student/learning/sessions/{session_id}/answer",
                json={"answer": answer},
                headers=self._student_headers(),
            )
            self.assertEqual(completed.status_code, 200, completed.json)
        self.assertIsNotNone(completed)
        self.assertTrue(completed.json["completed"])

        completed_library = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "completed"},
            headers=self._student_headers(),
        )
        self.assertEqual(completed_library.status_code, 200, completed_library.json)
        item = next(
            entry
            for entry in completed_library.json["items"]
            if entry["taskId"] == task_id
        )
        self.assertEqual(item["session"]["status"], "completed")
        self.assertEqual(item["report"]["id"], completed.json["report"]["id"])

        unfavorite = self.client.delete(
            f"/api/v2/student/learning/courses/{course_id}/versions/"
            f"{course_version}/favorite",
            headers=self._student_headers(),
        )
        self.assertEqual(unfavorite.status_code, 200, unfavorite.json)
        self.assertFalse(unfavorite.json["favorite"])

    def test_library_and_detail_fail_closed_until_release_media_and_runtime_are_approved(self):
        assigned = self.client.post(
            "/api/v2/student/learning/today/assign",
            json={"date": "2026-09-04", "scheduledStart": "18:45"},
            headers=self._student_headers(),
        )
        self.assertEqual(assigned.status_code, 200, assigned.json)
        course_id = assigned.json["recommendation"]["courseId"]
        course_version = assigned.json["recommendation"]["courseVersion"]
        fixture = self._install_release_classroom_fixture(
            course_id=course_id,
            course_version=course_version,
        )

        def assert_availability(package: bool, full: bool) -> None:
            library = self.client.get(
                "/api/v2/student/learning/library",
                query_string={"bucket": "all"},
                headers=self._student_headers(),
            )
            self.assertEqual(library.status_code, 200, library.json)
            item = next(
                value
                for value in library.json["items"]
                if value["course"]["id"] == course_id
                and value["course"]["version"] == course_version
            )
            self.assertEqual(item["classroomAvailable"], package)
            self.assertEqual(item["packageClassroomAvailable"], package)
            self.assertEqual(item["fullClassroomAvailable"], full)

            detail = self.client.get(
                f"/api/v2/student/learning/courses/{course_id}",
                query_string={"version": course_version},
                headers=self._student_headers(),
            )
            self.assertEqual(detail.status_code, 200, detail.json)
            self.assertEqual(detail.json["item"]["classroomAvailable"], package)
            self.assertEqual(
                detail.json["item"]["packageClassroomAvailable"], package
            )
            self.assertEqual(detail.json["item"]["fullClassroomAvailable"], full)

        # A published package outside an active release is historical data,
        # not a student-launchable classroom.
        assert_availability(False, False)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_releases SET status = 'active' WHERE id = ?",
                (fixture["release_id"],),
            )
        assert_availability(True, False)

        # The controlled package is available before the separately reviewed
        # full OpenMAIC runtime.  Once approved, both flags are true.
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE learning_openmaic_runtime_classrooms
                SET quality_status = 'approved' WHERE id = ?
                """,
                (fixture["runtime_id"],),
            )
        assert_availability(True, True)

        # The active release, its exact item, the course, and the bound package
        # are all part of the public launch decision.  A stale or partially
        # reviewed row in any one of those layers must close both entry modes.
        catalog_gate_updates = (
            (
                "UPDATE learning_catalog_releases SET quality_status = 'pending_review' WHERE id = ?",
                "UPDATE learning_catalog_releases SET quality_status = 'ready' WHERE id = ?",
                (fixture["release_id"],),
            ),
            (
                "UPDATE learning_catalog_release_items SET status = 'draft' "
                "WHERE release_id = ? AND course_id = ? AND course_version = ?",
                "UPDATE learning_catalog_release_items SET status = 'published' "
                "WHERE release_id = ? AND course_id = ? AND course_version = ?",
                (fixture["release_id"], course_id, course_version),
            ),
            (
                "UPDATE learning_catalog_release_items SET quality_status = 'pending_review' "
                "WHERE release_id = ? AND course_id = ? AND course_version = ?",
                "UPDATE learning_catalog_release_items SET quality_status = 'ready' "
                "WHERE release_id = ? AND course_id = ? AND course_version = ?",
                (fixture["release_id"], course_id, course_version),
            ),
            (
                "UPDATE learning_courses SET status = 'validated' "
                "WHERE id = ? AND version = ?",
                "UPDATE learning_courses SET status = 'published' "
                "WHERE id = ? AND version = ?",
                (course_id, course_version),
            ),
            (
                "UPDATE learning_courses SET quality_status = 'auto_validated' "
                "WHERE id = ? AND version = ?",
                "UPDATE learning_courses SET quality_status = 'released' "
                "WHERE id = ? AND version = ?",
                (course_id, course_version),
            ),
            (
                "UPDATE learning_lesson_packages SET status = 'draft' "
                "WHERE id = ? AND version = ?",
                "UPDATE learning_lesson_packages SET status = 'published' "
                "WHERE id = ? AND version = ?",
                (fixture["package_id"], fixture["package_version"]),
            ),
        )
        for fail_sql, restore_sql, params in catalog_gate_updates:
            with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
                conn.execute(fail_sql, params)
            assert_availability(False, False)
            with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
                conn.execute(restore_sql, params)
            assert_availability(True, True)

        # A controlled package may remain launchable while the richer runtime
        # is still processing or has been retired; only the full flag closes.
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE learning_openmaic_runtime_classrooms
                SET status = 'processing' WHERE id = ?
                """,
                (fixture["runtime_id"],),
            )
        assert_availability(True, False)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE learning_openmaic_runtime_classrooms
                SET status = 'ready' WHERE id = ?
                """,
                (fixture["runtime_id"],),
            )
        assert_availability(True, True)

        # Every required media gate fails closed for both entry modes.
        gate_updates = (
            (
                "UPDATE learning_media_assets SET status = 'processing' WHERE id = ?",
                "UPDATE learning_media_assets SET status = 'ready' WHERE id = ?",
            ),
            (
                "UPDATE learning_media_quality_reviews SET status = 'rejected' "
                "WHERE asset_id = ?",
                "UPDATE learning_media_quality_reviews SET status = 'approved' "
                "WHERE asset_id = ?",
            ),
            (
                "UPDATE learning_media_assets SET scan_status = 'pending' WHERE id = ?",
                "UPDATE learning_media_assets SET scan_status = 'passed' WHERE id = ?",
            ),
            (
                "UPDATE learning_media_assets SET moderation_status = 'rejected' WHERE id = ?",
                "UPDATE learning_media_assets SET moderation_status = 'passed' WHERE id = ?",
            ),
            (
                "UPDATE learning_media_assets SET transcode_status = 'pending' WHERE id = ?",
                "UPDATE learning_media_assets SET transcode_status = 'not_required' WHERE id = ?",
            ),
            (
                "UPDATE learning_media_asset_variants SET status = 'pending' WHERE asset_id = ?",
                "UPDATE learning_media_asset_variants SET status = 'ready' WHERE asset_id = ?",
            ),
        )
        for fail_sql, restore_sql in gate_updates:
            with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
                conn.execute(fail_sql, (fixture["asset_id"],))
            assert_availability(False, False)
            with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
                conn.execute(restore_sql, (fixture["asset_id"],))
            assert_availability(True, True)

    def test_library_is_read_only_and_rejects_invalid_filters(self):
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            before = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM tasks
                WHERE family_id = (
                  SELECT family_id FROM children WHERE id = ?
                ) AND child_id = ? AND type = 'learning'
                """,
                (self.child_id, self.child_id),
            ).fetchone()["count"]

        response = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "all", "subject": "chinese"},
            headers=self._student_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)

        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            after = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM tasks
                WHERE family_id = (
                  SELECT family_id FROM children WHERE id = ?
                ) AND child_id = ? AND type = 'learning'
                """,
                (self.child_id, self.child_id),
            ).fetchone()["count"]
        self.assertEqual(after, before)

        invalid_bucket = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"bucket": "deleted"},
            headers=self._student_headers(),
        )
        self.assertEqual(invalid_bucket.status_code, 400, invalid_bucket.json)
        self.assertEqual(
            invalid_bucket.json["error"],
            "invalid_learning_library_bucket",
        )

        invalid_cursor = self.client.get(
            "/api/v2/student/learning/library",
            query_string={"cursor": "not-a-cursor"},
            headers=self._student_headers(),
        )
        self.assertEqual(invalid_cursor.status_code, 400, invalid_cursor.json)
        self.assertEqual(
            invalid_cursor.json["error"],
            "invalid_learning_library_cursor",
        )

    def test_student_selects_a_versioned_teacher_without_provider_details(self):
        teachers = self.client.get(
            "/api/v2/student/learning/teachers",
            query_string={"subject": "math"},
            headers=self._student_headers(),
        )
        self.assertEqual(teachers.status_code, 200, teachers.json)
        self.assertEqual(len(teachers.json["items"]), 1)
        profile = teachers.json["items"][0]
        self.assertEqual(profile["id"], "mira_math_clear")
        self.assertEqual(profile["version"], 2)
        self.assertEqual(profile["avatarPath"], "/teachers/ashu-math-v1.png")
        self.assertNotIn("providerId", profile)
        self.assertNotIn("providerModel", profile)
        self.assertNotIn("voicePrompt", profile)
        self.assertNotIn("cloneAllowed", profile)
        self.assertIsNone(teachers.json["selected"])

        selected = self.client.put(
            "/api/v2/student/learning/preferences/teacher",
            json={
                "subject": "math",
                "teacherProfileId": profile["id"],
                "teacherProfileVersion": profile["version"],
            },
            headers=self._student_headers(),
        )
        self.assertEqual(selected.status_code, 200, selected.json)
        self.assertEqual(selected.json["teacher"]["id"], "mira_math_clear")

        reloaded = self.client.get(
            "/api/v2/student/learning/teachers",
            query_string={"subject": "math"},
            headers=self._student_headers(),
        )
        self.assertEqual(reloaded.status_code, 200, reloaded.json)
        self.assertEqual(
            reloaded.json["selected"],
            {"id": "mira_math_clear", "version": 2},
        )

        legacy = self.client.put(
            "/api/v2/student/learning/preferences/teacher",
            json={
                "subject": "math",
                "teacherProfileId": "mira_math_clear",
                "teacherProfileVersion": 1,
            },
            headers=self._student_headers(),
        )
        self.assertEqual(legacy.status_code, 200, legacy.json)
        self.assertEqual(legacy.json["teacher"]["version"], 1)
        legacy_reloaded = self.client.get(
            "/api/v2/student/learning/teachers",
            query_string={"subject": "math"},
            headers=self._student_headers(),
        )
        self.assertEqual(
            legacy_reloaded.json["selected"],
            {"id": "mira_math_clear", "version": 1},
        )

        mismatch = self.client.put(
            "/api/v2/student/learning/preferences/teacher",
            json={
                "subject": "english",
                "teacherProfileId": "mira_math_clear",
                "teacherProfileVersion": 1,
            },
            headers=self._student_headers(),
        )
        self.assertEqual(mismatch.status_code, 400, mismatch.json)
        self.assertEqual(mismatch.json["error"], "teacher_subject_mismatch")

    def test_student_learning_requires_student_access_token(self):
        missing = self.client.get("/api/v2/student/learning/today")
        self.assertEqual(missing.status_code, 401, missing.json)
        self.assertEqual(missing.json["error"], "missing_student_access_token")

        invalid = self.client.get(
            "/api/v2/student/learning/today",
            headers=self._student_headers("msa_invalid"),
        )
        self.assertEqual(invalid.status_code, 401, invalid.json)
        self.assertEqual(invalid.json["error"], "student_access_expired")

        parent_in_student_api = self.client.get(
            "/api/v2/student/learning/today",
            headers=self._student_headers(self.parent_access_token),
        )
        self.assertEqual(parent_in_student_api.status_code, 401, parent_in_student_api.json)

        student_in_parent_api = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id},
            headers=self._student_headers(),
        )
        self.assertEqual(student_in_parent_api.status_code, 401, student_in_parent_api.json)

    def _login_parent(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        response = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _learning_write_counts(self) -> tuple[int, int]:
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            task_count = conn.execute(
                "SELECT COUNT(*) AS count FROM tasks"
            ).fetchone()["count"]
            session_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_sessions"
            ).fetchone()["count"]
        return int(task_count), int(session_count)

    def _create_parent_identity(self) -> None:
        response = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)

    def _create_child(self, name: str, grade_code: str) -> str:
        response = self.client.post(
            "/api/setup/child",
            json={
                "name": name,
                "nickname": name,
                "gradeCode": grade_code,
                "schoolYearStartYear": datetime.now().year,
            },
            headers=self._parent_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["child"]["id"]

    def _insert_sibling(self, name: str) -> str:
        sibling_id = "child_student_learning_sibling"
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                INSERT INTO children(
                  id, family_id, name, nickname, gender, age_stage,
                  education_stage, grade, grade_code,
                  grade_school_year_start, grade_confirmed_at, birthday,
                  sleep_time, created_at, updated_at
                )
                SELECT ?, family_id, ?, ?, gender, age_stage,
                  education_stage, grade, grade_code,
                  grade_school_year_start, grade_confirmed_at, birthday,
                  sleep_time, created_at + 1, updated_at
                FROM children
                WHERE id = ?
                """,
                (sibling_id, name, name, self.child_id),
            )
        return sibling_id

    def _pair_student(self, child_id: str, pin: str) -> str:
        pairing = self.client.post(
            f"/api/v2/parent/children/{child_id}/student-access/pairing-codes",
            json={"pin": pin},
            headers=self._parent_headers(),
        )
        self.assertEqual(pairing.status_code, 200, pairing.json)
        paired = self.client.post(
            "/api/v2/student/auth/pair",
            json={
                "pairingCode": pairing.json["pairingCode"],
                "clientDevice": {
                    "label": "测试学习浏览器",
                    "type": "browser",
                    "platform": "web",
                },
            },
        )
        self.assertEqual(paired.status_code, 200, paired.json)
        return paired.json["tokens"]["accessToken"]

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
            elif question_type == "sequence":
                answers.append(
                    list(evaluation.get("expectedSequence") or question.get("answer"))
                )
            elif "answer" in question:
                answers.append(question["answer"])
            elif "expectedOptionId" in evaluation:
                answers.append({"optionId": evaluation["expectedOptionId"]})
            elif "expectedSequence" in evaluation:
                answers.append(list(evaluation["expectedSequence"]))
            elif "acceptedAnswers" in evaluation:
                answers.append(evaluation["acceptedAnswers"][0])
            else:
                answers.append(evaluation.get("expected"))
        return answers

    def _install_release_classroom_fixture(
        self,
        *,
        course_id: str,
        course_version: str,
    ) -> dict[str, str]:
        timestamp = now_ms()
        suffix = course_id[-12:]
        job_id = f"job_library_{suffix}"
        artifact_id = f"artifact_library_{suffix}"
        package_id = f"package_library_{suffix}"
        release_id = f"release_library_{suffix}"
        asset_id = f"asset_library_{suffix}"
        review_id = f"review_library_{suffix}"
        runtime_id = f"runtime_library_{suffix}"
        curriculum = "mira.primary.cn.v1"
        boundary = f"boundary-library-{suffix}"
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            course = conn.execute(
                """
                SELECT grade_code, subject, node_code
                FROM learning_courses WHERE id = ? AND version = ?
                """,
                (course_id, course_version),
            ).fetchone()
            self.assertIsNotNone(course)
            conn.execute(
                """
                UPDATE learning_courses
                SET status = 'published', quality_status = 'released',
                  content_origin = 'openmaic_generated',
                  curriculum_version = ?, boundary_version = ?, retired_at = NULL
                WHERE id = ? AND version = ?
                """,
                (curriculum, boundary, course_id, course_version),
            )
            conn.execute(
                """
                INSERT INTO learning_classroom_generation_jobs(
                  id, request_id, course_id, course_version, generator, status,
                  source_artifact_id, package_id, package_version,
                  started_at, completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'openmaic', 'completed', ?, ?, 1,
                  ?, ?, ?, ?)
                """,
                (
                    job_id,
                    f"request-{suffix}",
                    course_id,
                    course_version,
                    artifact_id,
                    package_id,
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_classroom_source_artifacts(
                  id, job_id, request_id, source_format, source_package_version,
                  dsl_version, status, source_hash, payload_json,
                  validation_report_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'openmaic_dsl', '0.3.2', '0.3.2',
                  'validated', ?, '{}', '{}', ?, ?)
                """,
                (
                    artifact_id,
                    job_id,
                    f"request-{suffix}",
                    "1" * 64,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_lesson_packages(
                  id, version, course_id, course_version,
                  source_course_content_hash, schema_version,
                  status, source_artifact_id, compiler_version,
                  public_content_hash, private_content_hash,
                  public_payload_json, validation_report_json,
                  created_at, published_at, updated_at
                ) VALUES (?, 1, ?, ?, SHA2((
                    SELECT content_json FROM learning_courses
                    WHERE id = ? AND version = ? LIMIT 1
                  ), 256), 'mira.lesson-package.v2', 'published', ?,
                  'library-gate-test', ?, ?, '{}', '{}', ?, ?, ?)
                """,
                (
                    package_id,
                    course_id,
                    course_version,
                    course_id,
                    course_version,
                    artifact_id,
                    "2" * 64,
                    "3" * 64,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_course_lesson_package_bindings(
                  course_id, course_version, package_id, package_version, updated_at
                ) VALUES (?, ?, ?, 1, ?)
                """,
                (course_id, course_version, package_id, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_releases(
                  id, curriculum_version, title, status, quality_status,
                  required_boundary_count, ready_item_count,
                  created_at, updated_at
                ) VALUES (?, ?, 'Library gate release', 'draft', 'ready',
                  1, 1, ?, ?)
                """,
                (release_id, curriculum, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_catalog_release_items(
                  release_id, course_id, course_version, grade_code, subject,
                  skill_id, curriculum_version, boundary_version,
                  variant_ordinal, package_id, package_version, status,
                  quality_status, published_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 1,
                  'published', 'ready', ?, ?, ?)
                """,
                (
                    release_id,
                    course_id,
                    course_version,
                    course["grade_code"],
                    course["subject"],
                    course["node_code"],
                    curriculum,
                    boundary,
                    package_id,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_media_assets(
                  id, kind, storage_key, content_hash, mime_type, byte_size,
                  scan_status, moderation_status, transcode_status, status,
                  source_type, created_at, updated_at
                ) VALUES (?, 'audio', ?, ?, 'audio/wav', 128,
                  'passed', 'passed', 'not_required', 'ready',
                  'library_gate_test', ?, ?)
                """,
                (
                    asset_id,
                    f"library-gate/{suffix}.wav",
                    "4" * 64,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_media_asset_variants(
                  asset_id, variant_key, storage_key, content_hash,
                  mime_type, byte_size, status, created_at, updated_at
                ) VALUES (?, 'original', ?, ?, 'audio/wav', 128,
                  'ready', ?, ?)
                """,
                (
                    asset_id,
                    f"library-gate/{suffix}.wav",
                    "4" * 64,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_media_quality_reviews(
                  id, asset_id, review_kind, required_review, status,
                  reviewer_type, reviewer_id, findings_json, reviewed_at,
                  created_at, updated_at
                ) VALUES (?, ?, 'content_integrity', 1, 'approved',
                  'automated', 'library-gate-test', '{}', ?, ?, ?)
                """,
                (review_id, asset_id, timestamp, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO learning_lesson_package_assets(
                  package_id, package_version, asset_id, scene_id,
                  usage_kind, required_asset
                ) VALUES (?, 1, ?, 'scene-teach', 'narration', 1)
                """,
                (package_id, asset_id),
            )
            conn.execute(
                """
                INSERT INTO learning_openmaic_runtime_classrooms(
                  id, request_id, course_id, course_version, package_id,
                  package_version, upstream_job_id, upstream_classroom_id,
                  status, quality_status, feature_manifest_json,
                  created_at, updated_at, ready_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 'ready',
                  'pending_review', '{}', ?, ?, ?)
                """,
                (
                    runtime_id,
                    f"runtime-request-{suffix}",
                    course_id,
                    course_version,
                    package_id,
                    f"upstream-job-{suffix}",
                    f"upstream-classroom-{suffix}",
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        return {
            "release_id": release_id,
            "package_id": package_id,
            "package_version": "1",
            "asset_id": asset_id,
            "runtime_id": runtime_id,
        }

    def _activate_formal_pointer(self, release_id: str) -> None:
        timestamp = now_ms()
        history_id = f"history_{release_id}"
        fingerprint = "a" * 64
        receipt = "b" * 64
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE learning_catalog_releases
                SET status = 'published', quality_status = 'ready',
                  activated_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, release_id),
            )
            conn.execute(
                """
                INSERT INTO learning_curriculum_grade_release_history(
                  id, grade_code, pointer_revision, target_fingerprint,
                  contract_version, release_id, previous_history_id,
                  previous_release_id, activation_source,
                  publication_request_id, publication_receipt_hash,
                  activated_at, superseded_at, created_at
                ) VALUES (?, 'primary_1', 1, ?,
                  'mira.learning.formal-publication.v1', ?, NULL, NULL,
                  'formal_publication', ?, ?, ?, NULL, ?)
                """,
                (
                    history_id,
                    fingerprint,
                    release_id,
                    f"publish-{release_id}",
                    receipt,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute(
                """
                INSERT INTO learning_curriculum_grade_release_pointers(
                  grade_code, pointer_revision, target_fingerprint,
                  contract_version, release_id, history_id,
                  activated_at, updated_at
                ) VALUES ('primary_1', 1, ?,
                  'mira.learning.formal-publication.v1', ?, ?, ?, ?)
                """,
                (fingerprint, release_id, history_id, timestamp, timestamp),
            )

    def _parent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.parent_access_token}"}

    def _student_headers(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token or self.student_access_token}"}


if __name__ == "__main__":
    unittest.main()
