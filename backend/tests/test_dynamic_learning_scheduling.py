from __future__ import annotations

import json
import unittest
from datetime import datetime

from app import create_app
from core.database import Database
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from repositories.learning_repository import LearningRepository
from core.security import now_ms
from tests.fixtures.primary_subject_catalog import PRIMARY_COURSE_CATALOG
from tests.support import fresh_test_config, request_debug_code
from tests.test_dynamic_learning_course_generation_service import (
    _WidgetCompatibleQuestionAdapter,
)
from tests.test_lesson_package_v2 import _FakeClassroomAdapter
from tests.support_learning_media import AutoPublishingLessonPackageService


FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE = (
    "formal v2 student mutations are release-gated and not open for this "
    "legacy primary-grade scheduling fixture"
)


class _SchedulingClassroomAdapter(_FakeClassroomAdapter):
    """Use the controlled phonics template for the first grade-one lesson."""

    def generate(self, **kwargs):
        result = super().generate(**kwargs)
        course = kwargs["course"]
        if (
            course["grade_code"] == "primary_1"
            and course["subject"] == "chinese"
            and course["node_code"] == "pinyin_syllables"
        ):
            intent = result.source["classroom"]["intent"]
            intent["layoutTemplate"] = "phonics_focus.v1"
            intent["widgetTemplate"] = "listen_tap_choice.v1"
            intent["misconceptions"] = [
                "把 a、o、e 的口形混在一起",
                "只看字形不认真听读音",
            ]
            result.source["classroom"]["title"] = "单韵母 a、o、e"
        return result


class DynamicLearningSchedulingTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config(
            LEARNING_DYNAMIC_GENERATION_ENABLED=True,
            LEARNING_STATIC_CATALOG_ENABLED=False,
            LEARNING_DYNAMIC_POOL_TARGET=1,
        )
        self.app = create_app(config)
        self.client = self.app.test_client()
        self.adapter = _WidgetCompatibleQuestionAdapter(vary_by_request=True)
        self.classroom_adapter = _SchedulingClassroomAdapter()
        self.lesson_service = AutoPublishingLessonPackageService(
            self.app.config["DATABASE_URL"], adapter=self.classroom_adapter
        )
        self.dynamic_service = DynamicLearningCourseGenerationService(
            self.app.config["DATABASE_URL"],
            adapter=self.adapter,
            classroom_enqueue=self.lesson_service.enqueue,
        )
        self.catalog_service = LearningCatalogReleaseService(
            self.app.config["DATABASE_URL"],
            dynamic_generation_service=self.dynamic_service,
            lesson_package_service=self.lesson_service,
        )
        with self.app.app_context():
            self.app.extensions[
                "mira_dynamic_learning_course_generation_service"
            ] = self.dynamic_service
            self.app.extensions["mira_lesson_package_service"] = (
                self.lesson_service.delegate
            )
            self.app.extensions[
                "mira_learning_catalog_release_service"
            ] = self.catalog_service
        self.access_token = self._login("13800002131")
        self.child_id = self._create_child("primary_3")
        if self._testMethodName not in {
            "test_primary_one_chinese_starts_with_aoe_then_unlocks_later_pinyin",
            "test_unstarted_legacy_later_skill_is_repaired_to_pinyin",
        }:
            variants = (
                2
                if self._testMethodName
                in {
                    "test_daily_scheduler_uses_only_generated_courses_and_replenishes",
                    "test_unstarted_old_dynamic_course_without_flow_is_replaced_but_not_deleted",
                }
                else 1
            )
            self._activate_catalog_for_grade("primary_3", variants=variants)

    def tearDown(self):
        self.lesson_service.close()

    @unittest.skip(FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE)
    def test_daily_scheduler_uses_only_generated_courses_and_replenishes(self):
        generated_before_request = len(self.adapter.generate_calls)
        first = self._assign("2026-09-01")
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(len(first.json["items"]), 2)
        first_course_ids = {
            item["recommendation"]["courseId"] for item in first.json["items"]
        }
        self.assertTrue(
            all(course_id.startswith("openmaic_") for course_id in first_course_ids)
        )
        self.assertEqual(len(self.adapter.generate_calls), generated_before_request)
        generated_targets = {
            (call["grade_code"], call["subject"])
            for call in self.adapter.generate_calls
        }
        self.assertEqual(
            generated_targets,
            {
                ("primary_3", "math"),
                ("primary_3", "chinese"),
                ("primary_3", "english"),
            },
        )

        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            rows = conn.execute(
                """
                SELECT id, content_origin, generator
                FROM learning_courses
                WHERE id IN (?, ?)
                """,
                tuple(first_course_ids),
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(
            all(
                row["content_origin"] == "openmaic_generated"
                and row["generator"] == "openmaic"
                for row in rows
            )
        )

        replay = self._assign("2026-09-01")
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertEqual(len(self.adapter.generate_calls), generated_before_request)

        second = self._assign("2026-09-02")
        self.assertEqual(second.status_code, 200, second.json)
        second_course_ids = {
            item["recommendation"]["courseId"] for item in second.json["items"]
        }
        self.assertTrue(first_course_ids.isdisjoint(second_course_ids))
        self.assertEqual(len(self.adapter.generate_calls), generated_before_request)

    @unittest.skip(FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE)
    def test_dynamic_session_publishes_teaching_flow_and_scores_only_four_practice_questions(self):
        today = self._assign("2026-09-01")
        self.assertEqual(today.status_code, 200, today.json)
        item = today.json["items"][0]
        self.assertEqual(item["recommendation"]["questionCount"], 4)
        self.assertNotIn("teachingFlow", item["recommendation"])
        self.assertNotIn("workedExample", item["recommendation"])

        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": item["task"]["id"]},
            headers=self._headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        session = started.json["session"]
        lesson = started.json["lesson"]
        self.assertEqual(session["totalQuestions"], 4)
        self.assertEqual(lesson["questionCount"], 4)
        self.assertEqual(session["teachingFlow"], lesson["teachingFlow"])
        flow = session["teachingFlow"]
        self.assertEqual(flow["schemaVersion"], "mira.learning.teaching-flow.v1")
        self.assertEqual(flow["workedExample"]["id"], "generated_math_g3_q1")
        self.assertEqual(session["currentQuestion"]["id"], "generated_math_g3_q2")
        self.assertEqual(flow["workedExample"]["answerDisplayText"], "395")
        self.assertIn("395", flow["workedExample"]["explanation"])
        self.assertNotIn("answer", flow["workedExample"])
        self.assertNotIn("evaluation", flow["workedExample"])
        self.assertEqual(
            flow["guidedQuestionIds"],
            ["generated_math_g3_q2", "generated_math_g3_q3"],
        )
        self.assertEqual(
            flow["independentQuestionIds"],
            ["generated_math_g3_q4", "generated_math_g3_q5"],
        )

    @unittest.skip(FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE)
    def test_dynamic_mastery_uses_only_two_independent_first_attempts(self):
        today = self._assign("2026-09-01")
        self.assertEqual(today.status_code, 200, today.json)
        item = today.json["items"][0]
        started = self.client.post(
            "/api/learning/sessions",
            json={"taskId": item["task"]["id"]},
            headers=self._headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        session_id = started.json["session"]["id"]
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            row = conn.execute(
                "SELECT content_json FROM learning_courses WHERE id = ? AND version = ?",
                (
                    item["recommendation"]["courseId"],
                    item["recommendation"]["courseVersion"],
                ),
            ).fetchone()
        content = LearningRepository.parse_json(row["content_json"], {})
        by_id = {question["id"]: question for question in content["questions"]}
        flow = content["teachingFlow"]
        runtime_ids = [*flow["guidedQuestionIds"], *flow["independentQuestionIds"]]

        final = None
        for question_id in runtime_ids[:-1]:
            final = self.client.post(
                f"/api/learning/sessions/{session_id}/answer",
                json={"answer": by_id[question_id]["answer"]},
                headers=self._headers(),
            )
            self.assertTrue(final.json["correct"], final.json)
        for wrong in ("-999999", "-999998"):
            final = self.client.post(
                f"/api/learning/sessions/{session_id}/answer",
                json={"answer": wrong},
                headers=self._headers(),
            )
            self.assertFalse(final.json["correct"], final.json)

        self.assertTrue(final.json["completed"])
        report = final.json["report"]
        self.assertEqual(report["score"], 50)
        self.assertEqual(report["masteryLevel"], "developing")
        self.assertEqual(report["independentCorrectCount"], 1)
        self.assertEqual(report["evidenceCount"], 2)
        self.assertEqual(report["evidencePolicy"], "independent_all_correct_v1")
        self.assertEqual(report["assessmentScope"], "this_lesson_only")

    @unittest.skip(FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE)
    def test_unstarted_old_dynamic_course_without_flow_is_replaced_but_not_deleted(self):
        first = self._assign("2026-09-01")
        self.assertEqual(first.status_code, 200, first.json)
        original = first.json["items"][0]
        original_course_id = original["recommendation"]["courseId"]
        original_task_id = original["task"]["id"]
        self._remove_course_teaching_flow(original_course_id)
        generate_count = len(self.adapter.generate_calls)

        repaired = self._assign("2026-09-01")
        self.assertEqual(repaired.status_code, 200, repaired.json)
        item = next(
            item
            for item in repaired.json["items"]
            if item["task"]["id"] == original_task_id
        )
        self.assertNotEqual(item["recommendation"]["courseId"], original_course_id)
        self.assertEqual(item["recommendation"]["questionCount"], 4)
        self.assertEqual(len(self.adapter.generate_calls), generate_count)
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            old_course = conn.execute(
                "SELECT id FROM learning_courses WHERE id = ?",
                (original_course_id,),
            ).fetchone()
        self.assertIsNotNone(old_course)

    @unittest.skip(FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE)
    def test_existing_session_on_old_dynamic_course_is_preserved(self):
        first = self._assign("2026-09-01")
        self.assertEqual(first.status_code, 200, first.json)
        original = first.json["items"][0]
        original_course_id = original["recommendation"]["courseId"]
        original_task_id = original["task"]["id"]
        self._remove_course_teaching_flow(original_course_id)
        repository = LearningRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            session, created = repository.create_or_get_session(
                conn,
                family_id=original["task"]["familyId"],
                child_id=self.child_id,
                task_id=original_task_id,
                course_id=original_course_id,
                course_version=original["recommendation"]["courseVersion"],
                now=now_ms(),
            )
        self.assertTrue(created)
        generate_count = len(self.adapter.generate_calls)

        preserved = self._assign("2026-09-01")
        self.assertEqual(preserved.status_code, 200, preserved.json)
        item = next(
            item
            for item in preserved.json["items"]
            if item["task"]["id"] == original_task_id
        )
        self.assertEqual(item["recommendation"]["courseId"], original_course_id)
        self.assertEqual(item["session"]["id"], session["id"])
        self.assertEqual(len(self.adapter.generate_calls), generate_count)

    def test_primary_one_chinese_starts_with_aoe_then_unlocks_later_pinyin(self):
        self._set_grade("primary_1")
        first = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-09-01"},
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 200, first.json)
        chinese = next(item for item in first.json["items"] if item["subject"] == "chinese")
        self.assertEqual(chinese["recommendation"]["nodeCode"], "pinyin_syllables")

        database = Database(self.app.config["DATABASE_URL"])
        repository = LearningRepository(database)
        with repository.transaction() as conn:
            child = conn.execute(
                "SELECT * FROM children WHERE id = ?",
                (self.child_id,),
            ).fetchone()
            repository.upsert_mastery_state(
                conn,
                family_id=child["family_id"],
                child_id=self.child_id,
                node_code="pinyin_syllables",
                subject="chinese",
                grade_code="primary_1",
                attempts=5,
                correct_count=5,
                independent_correct_count=2,
                hint_count=0,
                latest_score=100,
                mastery_level="mastered",
                last_practiced_at=now_ms(),
                next_review_date="2026-09-08",
                course_id=chinese["recommendation"]["courseId"],
                course_version=chinese["recommendation"]["courseVersion"],
                now=now_ms(),
            )

        next_chinese_day = self.client.get(
            "/api/learning/today",
            query_string={"childId": self.child_id, "date": "2026-09-03"},
            headers=self._headers(),
        )
        self.assertEqual(next_chinese_day.status_code, 200, next_chinese_day.json)
        chinese = next(
            item for item in next_chinese_day.json["items"] if item["subject"] == "chinese"
        )
        self.assertEqual(
            chinese["recommendation"]["nodeCode"],
            "pinyin_initials_syllables",
        )

    @unittest.skip(FORMAL_STUDENT_MUTATION_NOT_OPEN_FOR_GRADE)
    def test_unstarted_legacy_later_skill_is_repaired_to_pinyin(self):
        self._set_grade("primary_1")
        database = Database(self.app.config["DATABASE_URL"])
        repository = LearningRepository(database)
        repository.ensure_published_courses(PRIMARY_COURSE_CATALOG, now=now_ms())
        with repository.transaction() as conn:
            child = conn.execute(
                "SELECT * FROM children WHERE id = ?",
                (self.child_id,),
            ).fetchone()
            legacy = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE grade_code = 'primary_1' AND subject = 'chinese'
                  AND node_code = 'characters_words'
                LIMIT 1
                """
            ).fetchone()
            legacy_task, created = repository.assign_today_task(
                conn,
                family_id=child["family_id"],
                child_id=self.child_id,
                learning_date="2026-09-01",
                slot="rotation",
                scheduled_start="19:45",
                course=legacy,
                created_by="test",
                now=now_ms(),
            )
        self.assertTrue(created)

        response = self._assign("2026-09-01")
        self.assertEqual(response.status_code, 200, response.json)
        chinese = next(
            item for item in response.json["items"] if item["subject"] == "chinese"
        )
        self.assertEqual(chinese["task"]["id"], legacy_task["id"])
        self.assertEqual(chinese["recommendation"]["nodeCode"], "pinyin_syllables")
        self.assertTrue(
            chinese["recommendation"]["courseId"].startswith("openmaic_")
        )
        with repository.transaction() as conn:
            events = conn.execute(
                """
                SELECT payload FROM task_events
                WHERE task_id = ? AND event_type = 'learning_reassigned'
                """,
                (legacy_task["id"],),
            ).fetchall()
        self.assertTrue(events)

    def _set_grade(self, grade_code: str) -> None:
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                "UPDATE children SET grade_code = ?, education_stage = 'primary' WHERE id = ?",
                (grade_code, self.child_id),
            )
        self._activate_catalog_for_grade(grade_code, variants=1)

    def _activate_catalog_for_grade(self, grade_code: str, *, variants: int) -> None:
        request_id = f"scheduling-catalog-{grade_code}-{variants}"
        created = self.catalog_service.create(
            {
                "requestId": request_id,
                "grades": [grade_code],
                "subjects": ["chinese", "math", "english"],
                "variantsPerBoundary": variants,
                "allowPartial": True,
            }
        )
        built = self.catalog_service.run(
            created["build"]["id"],
            {"maxItems": 100, "retryFailed": True},
        )
        self.assertEqual(built["build"]["status"], "completed", built)
        activated = self.catalog_service.activate(created["release"]["id"])
        self.assertEqual(activated["release"]["status"], "active")

    def _remove_course_teaching_flow(self, course_id: str) -> None:
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            row = conn.execute(
                "SELECT content_json FROM learning_courses WHERE id = ?",
                (course_id,),
            ).fetchone()
            content = LearningRepository.parse_json(row["content_json"], {})
            content.pop("teachingFlow", None)
            conn.execute(
                "UPDATE learning_courses SET content_json = ? WHERE id = ?",
                (
                    json.dumps(
                        content,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    course_id,
                ),
            )

    def _assign(self, learning_date: str):
        response = self.client.post(
            "/api/learning/today/assign",
            json={"childId": self.child_id, "date": learning_date},
            headers=self._headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response

    def _login(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        response = self.client.post(
            "/api/auth/sms/login", json={"phone": phone, "code": code}
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _create_child(self, grade_code: str) -> str:
        headers = self._headers()
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "家长",
                "relationship": "家长",
                "relationshipKey": "other",
            },
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        response = self.client.post(
            "/api/setup/child",
            json={
                "name": "小米",
                "nickname": "小米",
                "gradeCode": grade_code,
                "schoolYearStartYear": datetime.now().year,
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["child"]["id"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

if __name__ == "__main__":
    unittest.main()
