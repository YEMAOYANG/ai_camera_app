from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from app import create_app
from core.database import Database
from integrations.openmaic_classroom_adapter import ClassroomSourceResult
from repositories.learning_repository import LearningRepository
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    LearningMediaMaterializationService,
)
from services.openmaic_full_runtime_service import OpenMaicFullRuntimeService
from services.service_factory import student_auth_service
from services.lesson_package_service import LessonPackageService
from services.lesson_package_validator import (
    LessonPackageValidationError,
    LessonPackageValidator,
)
from tests.support import fresh_test_config, request_debug_code
from tests.test_learning_generated_course_validator import math_candidate
from tests.test_learning_teacher_media_assets import ContractFakeVoxCpmProvider


class _FakeClassroomAdapter:
    def __init__(self, *, unsafe_html: bool = False):
        self.calls: list[dict] = []
        self.unsafe_html = unsafe_html

    def availability(self):
        return {"available": True, "generator": "openmaic"}

    def generate(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        question_refs = [item["id"] for item in kwargs["public_questions"]]
        content = json.loads(kwargs["course"]["content_json"])
        flow = content["teachingFlow"]
        demo_question = next(
            item
            for item in content["questions"]
            if item["id"] == flow["demoQuestionId"]
        )
        intent = {
            "schemaVersion": "mira.learning.classroom-intent.v1",
            "layoutTemplate": "concept_focus.v1",
            "widgetTemplate": "match_pairs.v1",
            "assetBrief": [],
            "misconceptions": ["容易忽略运算顺序", "容易把进位写错位置"],
            "teach": {
                "title": flow["teach"]["title"],
                "sayText": flow["teach"]["sayText"],
                "keyPoints": flow["teach"]["keyPoints"],
            },
            "demo": {
                "title": "老师示范",
                "sayText": demo_question["explanation"],
                "keyPoints": [demo_question["explanation"].split("。")[0]],
            },
            "guided": {
                "title": "跟着老师练",
                "sayText": "完成两道引导练习，每次作答后根据反馈调整。",
                "keyPoints": [],
                "questionRefs": question_refs[:2],
            },
            "independent": {
                "title": "我来自己做",
                "sayText": "独立完成最后两道练习。",
                "keyPoints": [],
                "questionRefs": question_refs[2:],
            },
            "recap": {
                "title": "回顾一下",
                "sayText": flow["recap"]["sayText"],
                "keyPoints": [flow["recap"]["sayText"].split("。")[0]],
            },
            "gameRules": {
                "goal": "完成两道引导练习",
                "instructions": ["先看题", "再作答", "听反馈后继续"],
                "successCriterion": "两道引导练习都经过服务器判定",
                "maxAttempts": 2,
                "feedbackMode": "encouraging_retry",
            },
        }
        if self.unsafe_html:
            intent["html"] = "<script>fetch('https://evil.invalid')</script>"
        source = {
            "schemaVersion": "mira.openmaic.classroom_intent.v2",
            "dslVersion": "0.1.0",
            "generator": "openmaic",
            "requestId": kwargs["request_id"],
            "provider": "kimi",
            "model": "kimi-test",
            "status": "unverified",
            "publicationEligible": False,
            "authoritativeAnswersProvided": False,
            "sourceAuthority": "openmaic_generation_untrusted",
            "gradeCode": kwargs["course"]["grade_code"],
            "subject": kwargs["course"]["subject"],
            "skillBoundary": copy.deepcopy(kwargs["skill_boundary"]),
            "classroom": {
                "id": "stage-1",
                "title": "多位数计算互动课堂",
                "language": "zh-CN",
                "intent": intent,
            },
            "generationMeta": {
                "elapsedMs": 4,
                "teachingReview": {
                    "passed": True,
                    "issues": [],
                    "reviewer": "independent_ai_classroom_intent_review_v2",
                },
            },
        }
        return ClassroomSourceResult(
            request_id=kwargs["request_id"],
            source=source,
            provider="kimi",
            model="kimi-test",
            elapsed_ms=4,
        )


class LessonPackageV2ApiTest(unittest.TestCase):
    def setUp(self):
        self.internal_token = "lesson-package-token"
        self.app = create_app(
            fresh_test_config(
                INTERNAL_API_TOKEN=self.internal_token,
                LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED=True,
            )
        )
        self.app.extensions["mira_formal_learning_access_checker"] = (
            lambda conn, child: None
        )
        self.client = self.app.test_client()
        self.database = Database(self.app.config["DATABASE_URL"])
        self.temporary = tempfile.TemporaryDirectory(prefix="mira-lesson-v2-media-")
        self.media_service = LearningMediaMaterializationService(
            LearningTeacherMediaRepository(self.database),
            tts_provider=ContractFakeVoxCpmProvider(),
            asset_store=FilesystemLearningMediaAssetStore(
                Path(self.temporary.name)
            ),
        )
        self.app.extensions[
            "mira_learning_media_materialization_service"
        ] = self.media_service
        self.course = self._seed_course()
        self.parent_access_token = self._login_parent("13800002971")
        self._create_parent_identity()
        self.child_id = self._create_child("乐乐", "primary_3")
        self.sibling_id = self._insert_sibling("安安")
        self.student_access_token = self._pair_student(self.child_id, "2468")
        self.task_id = self._assign_task(self.child_id, "2026-09-08", "core")
        self.adapter = _FakeClassroomAdapter()
        self.app.extensions["mira_lesson_package_service"] = LessonPackageService(
            self.app.config["DATABASE_URL"],
            adapter=self.adapter,
            media_service=self.media_service,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_start_without_published_classroom_rolls_back_new_session(self):
        with self.database.transaction() as conn:
            before = conn.execute(
                """
                SELECT status FROM tasks WHERE id = ?
                """,
                (self.task_id,),
            ).fetchone()

        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": self.task_id},
            headers=self._student_headers(),
        )

        self.assertEqual(started.status_code, 409, started.json)
        self.assertEqual(started.json["error"], "learning_classroom_preparing")
        with self.database.transaction() as conn:
            sessions = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM learning_sessions
                    WHERE task_id = ?
                    """,
                    (self.task_id,),
                ).fetchone()["count"]
            )
            after = conn.execute(
                "SELECT status FROM tasks WHERE id = ?",
                (self.task_id,),
            ).fetchone()
            started_events = int(
                conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM task_events
                    WHERE task_id = ? AND event_type = 'learning_session_started'
                    """,
                    (self.task_id,),
                ).fetchone()["count"]
            )
        self.assertEqual(sessions, 0)
        self.assertEqual(after["status"], before["status"])
        self.assertEqual(started_events, 0)

    def test_publish_start_runtime_cursor_idempotency_and_terminal_contract(self):
        generated = self._generate("classroom-api-happy-path")
        self.assertEqual(generated.status_code, 200, generated.json)
        self.assertEqual(generated.json["status"], "published")
        self.assertEqual(
            [item["id"] for item in self.adapter.calls[0]["public_questions"]],
            self._practice_question_ids(),
        )

        classroom = generated.json["package"]["classroom"]
        self.assertEqual(classroom["schemaVersion"], "mira.learning.lesson-package.v2")
        self.assertEqual(
            [scene["phaseRole"] for scene in classroom["scenes"]],
            ["teach", "demo", "guided", "independent", "recap"],
        )
        self.assertEqual(classroom["scenes"][0]["layoutTemplate"], "concept_focus.v1")
        self.assertNotIn("canvas", classroom["scenes"][0])
        self.assertNotIn("html", classroom["scenes"][2])
        self.assertEqual(
            classroom["scenes"][2]["widgetTemplate"],
            "match_pairs.v1",
        )
        self.assertEqual(
            classroom["scenes"][2]["templateData"]["stateContract"]["completion"],
            "guided_questions_evaluated",
        )
        self.assertEqual(
            classroom["learningMetadata"]["masteryThreshold"]["evidenceCount"],
            2,
        )
        self.assertEqual(len(classroom["assetRefs"]), 5)
        self.assertTrue(all(item.startswith("asset:media_asset_") for item in classroom["assetRefs"]))
        self._assert_no_answer_fields(classroom)

        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": self.task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        self.assertEqual(started.json["classroom"]["id"], classroom["id"])
        self.assertEqual(started.json["package"]["contentHash"], generated.json["package"]["contentHash"])
        self.assertEqual(started.json["cursor"]["revision"], 0)
        self.assertEqual(len(self.adapter.calls), 1)
        session_id = started.json["session"]["id"]

        runtime = self._runtime(session_id)
        first_action = runtime["action"]["id"]
        first = self._complete(session_id, first_action, runtime["cursor"]["revision"], "step-1")
        self.assertEqual(first.status_code, 200, first.json)
        replay = self._complete(session_id, first_action, 0, "step-1")
        self.assertEqual(replay.status_code, 200, replay.json)
        self.assertEqual(replay.json, first.json)
        stale = self._complete(
            session_id,
            first.json["action"]["id"],
            0,
            "stale-step",
        )
        self.assertEqual(stale.status_code, 409, stale.json)
        self.assertEqual(stale.json["error"], "learning_cursor_conflict")

        runtime = first.json
        step = 2
        correct_answers = self._correct_answers()
        answered_count = 0
        while not (
            runtime["scene"]["type"] == "quiz"
            and runtime["action"]["type"] == "await_interaction"
        ):
            if (
                runtime["scene"].get("phaseRole") == "guided"
                and runtime["action"]["type"] == "await_interaction"
            ):
                blocked_guided = self._complete(
                    session_id,
                    runtime["action"]["id"],
                    runtime["cursor"]["revision"],
                    "guided-before-answers",
                    {"completed": True},
                )
                self.assertEqual(blocked_guided.status_code, 409, blocked_guided.json)
                self.assertEqual(
                    blocked_guided.json["error"],
                    "learning_guided_not_completed",
                )
                while answered_count < 2:
                    answered = self.client.post(
                        f"/api/v2/student/learning/sessions/{session_id}/answer",
                        json={"answer": correct_answers[answered_count]},
                        headers=self._student_headers(),
                    )
                    self.assertEqual(answered.status_code, 200, answered.json)
                    self.assertTrue(answered.json["correct"])
                    answered_count += 1
            result = (
                {"completed": True}
                if runtime["action"]["type"] == "await_interaction"
                else {}
            )
            response = self._complete(
                session_id,
                runtime["action"]["id"],
                runtime["cursor"]["revision"],
                f"step-{step}",
                result,
            )
            self.assertEqual(response.status_code, 200, response.json)
            runtime = response.json
            step += 1

        blocked = self._complete(
            session_id,
            runtime["action"]["id"],
            runtime["cursor"]["revision"],
            "quiz-before-answers",
            {"completed": True},
        )
        self.assertEqual(blocked.status_code, 409, blocked.json)
        self.assertEqual(blocked.json["error"], "learning_quiz_not_completed")

        for answer in correct_answers[answered_count:]:
            answered = self.client.post(
                f"/api/v2/student/learning/sessions/{session_id}/answer",
                json={"answer": answer},
                headers=self._student_headers(),
            )
            self.assertEqual(answered.status_code, 200, answered.json)
            self.assertTrue(answered.json["correct"])
        completed_quiz = self._complete(
            session_id,
            runtime["action"]["id"],
            runtime["cursor"]["revision"],
            "quiz-after-answers",
            {"completed": True},
        )
        self.assertEqual(completed_quiz.status_code, 200, completed_quiz.json)
        terminal = completed_quiz
        finish_step = 1
        while not terminal.json["completed"]:
            terminal = self._complete(
                session_id,
                terminal.json["action"]["id"],
                terminal.json["cursor"]["revision"],
                f"finish-classroom-{finish_step}",
            )
            self.assertEqual(terminal.status_code, 200, terminal.json)
            finish_step += 1
        self.assertEqual(terminal.json["scene"]["id"], "scene-recap")
        self.assertIsNone(terminal.json["action"])
        self.assertEqual(terminal.json["cursor"]["sceneId"], "scene-recap")
        self.assertEqual(terminal.json["cursor"]["sceneIndex"], 4)
        self.assertEqual(terminal.json["cursor"]["progress"], 1.0)

    def test_classroom_teaching_drift_is_rejected_before_package(self):
        with self.database.transaction() as conn:
            course = conn.execute(
                "SELECT * FROM learning_courses WHERE id = ? AND version = ?",
                (self.course["id"], self.course["version"]),
            ).fetchone()
        service = self.app.extensions["mira_lesson_package_service"]
        generated = self.adapter.generate(
            request_id="classroom-teaching-drift",
            course=course,
            skill_boundary=service._boundary(course),
            public_questions=service._public_practice_questions(course),
        )
        source = copy.deepcopy(generated.source)
        source["classroom"]["intent"]["teach"]["sayText"] = (
            "这段课堂教学故意偏离已经校验通过的课程内容。"
        )
        source_json = json.dumps(
            source,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.assertRaises(LessonPackageValidationError) as raised:
            LessonPackageValidator().compile(
                source=source,
                course=course,
                source_hash=hashlib.sha256(source_json.encode("utf-8")).hexdigest(),
            )
        self.assertEqual(
            raised.exception.code, "classroom_course_teaching_mismatch"
        )
        self.assertEqual(raised.exception.path, "classroom.intent")

    def test_student_isolation_fallback_and_rejected_source_preserve_binding(self):
        published = self._generate("classroom-binding-good")
        self.assertEqual(published.status_code, 200, published.json)

        sibling_task = self._assign_task(self.sibling_id, "2026-09-09", "core")
        sibling_student_token = self._pair_student(self.sibling_id, "1357")
        sibling_started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": sibling_task},
            headers=self._student_headers(sibling_student_token),
        )
        self.assertEqual(sibling_started.status_code, 200, sibling_started.json)
        isolated = self.client.get(
            f"/api/v2/student/learning/sessions/{sibling_started.json['session']['id']}/runtime",
            headers=self._student_headers(),
        )
        self.assertEqual(isolated.status_code, 404, isolated.json)
        self.assertEqual(isolated.json["error"], "learning_session_not_found")

        fallback_course = self._seed_course(course_id="course-without-classroom")
        fallback_task = self._assign_task(
            self.child_id,
            "2026-09-10",
            "core",
            course=fallback_course,
        )
        fallback = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": fallback_task},
            headers=self._student_headers(),
        )
        self.assertEqual(fallback.status_code, 409, fallback.json)
        self.assertEqual(fallback.json["error"], "learning_classroom_preparing")
        with self.database.transaction() as conn:
            fallback_session = conn.execute(
                """
                SELECT * FROM learning_sessions WHERE task_id = ? LIMIT 1
                """,
                (fallback_task,),
            ).fetchone()
        self.assertIsNone(fallback_session)

        unsafe_adapter = _FakeClassroomAdapter(unsafe_html=True)
        self.app.extensions["mira_lesson_package_service"] = LessonPackageService(
            self.app.config["DATABASE_URL"],
            adapter=unsafe_adapter,
            media_service=self.media_service,
        )
        rejected = self._generate("classroom-binding-unsafe")
        self.assertEqual(rejected.status_code, 422, rejected.json)
        self.assertEqual(rejected.json["error"], "unsafe_classroom_field")
        with self.database.transaction() as conn:
            binding = conn.execute(
                """
                SELECT * FROM learning_course_lesson_package_bindings
                WHERE course_id = ? AND course_version = ?
                """,
                (self.course["id"], self.course["version"]),
            ).fetchone()
            rejected_source = conn.execute(
                """
                SELECT status FROM learning_classroom_source_artifacts
                WHERE request_id = ?
                """,
                ("classroom-binding-unsafe",),
            ).fetchone()
        self.assertEqual(binding["package_id"], published.json["package"]["id"])
        self.assertEqual(rejected_source["status"], "rejected")

    def test_internal_guard_status_and_missing_teaching_flow_failure_are_explicit(self):
        unauthorized = self.client.get("/internal/learning/classrooms/status")
        self.assertEqual(unauthorized.status_code, 401, unauthorized.json)
        status = self.client.get(
            "/internal/learning/classrooms/status",
            headers=self._internal_headers(),
        )
        self.assertEqual(status.status_code, 200, status.json)
        self.assertFalse(status.json["generation"]["policy"]["studentRequestGeneration"])

        broken = copy.deepcopy(self.course)
        broken_content = copy.deepcopy(broken["content"])
        broken_content.pop("teachingFlow")
        with self.assertRaises(LessonPackageValidationError) as raised:
            LessonPackageService._public_practice_questions(
                {"content_json": json.dumps(broken_content, ensure_ascii=False)}
            )
        self.assertEqual(raised.exception.code, "invalid_classroom_course")
        self.assertEqual(raised.exception.path, "course.content.teachingFlow")

    def test_legacy_seed_course_is_hidden_at_openmaic_launch_lookup(self):
        generated = self._generate("classroom-full-runtime-launch")
        self.assertEqual(generated.status_code, 200, generated.json)
        package = generated.json["package"]

        with self.app.app_context():
            service = OpenMaicFullRuntimeService(
                self.app.config["DATABASE_URL"],
                student_auth_service=student_auth_service(),
                client=object(),
                enabled=True,
                public_url="https://classroom.mira.test",
            )
            self.app.extensions["mira_openmaic_full_runtime_service"] = service

        repository = OpenMaicRuntimeRepository(self.database)
        manifest = service._requested_manifest(
            ["slides", "html_game", "pbl", "multi_agent_roundtable"]
        )
        manifest["present"] = [
            "slides",
            "html_game",
            "pbl",
            "multi_agent_roundtable",
        ]
        with repository.transaction() as conn:
            runtime = repository.create_runtime_classroom(
                conn,
                runtime_id="openmaic-runtime-api-test",
                request_id="openmaic-runtime-api-request",
                course={
                    "course_id": self.course["id"],
                    "course_version": self.course["version"],
                    "package_id": package["id"],
                    "package_version": package["version"],
                },
                feature_manifest=manifest,
                now=1_780_000_000_000,
            )
            repository.mark_ready(
                conn,
                runtime_id=runtime["id"],
                upstream_classroom_id="openmaic-classroom-api-test",
                feature_manifest=manifest,
                now=1_780_000_000_001,
            )

        started = self.client.post(
            "/api/v2/student/learning/sessions",
            json={"taskId": self.task_id},
            headers=self._student_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        session_id = started.json["session"]["id"]

        pending = self.client.post(
            f"/api/v2/student/learning/sessions/{session_id}/openmaic-launch",
            headers=self._student_headers(),
        )
        self.assertEqual(pending.status_code, 404, pending.json)
        self.assertEqual(pending.json["error"], "learning_session_not_found")

    def _seed_course(self, course_id: str = "lesson-package-course") -> dict:
        candidate = math_candidate()
        content = copy.deepcopy(candidate["content"])
        for index, question in enumerate(content["questions"]):
            answer = int(question.get("answer") or index + 10)
            question["type"] = "single_choice"
            question["choices"] = [
                {"id": "a", "label": str(answer)},
                {"id": "b", "label": str(answer + 1)},
                {"id": "c", "label": str(max(0, answer - 1))},
            ]
            question["answer"] = "a"
            question["evaluation"] = {"expectedOptionId": "a"}
        course = {
            "id": course_id,
            "version": "1.0.0",
            "gradeCode": "primary_3",
            "subject": "math",
            "nodeCode": "multi_digit_operations",
            "title": candidate["title"],
            "objective": candidate["objective"],
            "status": "published",
            "content": content,
        }
        LearningRepository(self.database).ensure_published_courses(
            (course,), now=int(datetime.now().timestamp() * 1000)
        )
        return course

    def _assign_task(self, child_id, learning_date, slot, course=None):
        course = course or self.course
        with self.database.transaction() as conn:
            family = conn.execute(
                "SELECT family_id FROM children WHERE id = ?",
                (child_id,),
            ).fetchone()
            row = conn.execute(
                "SELECT * FROM learning_courses WHERE id = ? AND version = ?",
                (course["id"], course["version"]),
            ).fetchone()
            task, _ = LearningRepository(self.database).assign_today_task(
                conn,
                family_id=family["family_id"],
                child_id=child_id,
                learning_date=learning_date,
                slot=slot,
                scheduled_start="18:30",
                course=row,
                created_by="test",
                now=int(datetime.now().timestamp() * 1000),
            )
        return task["id"]

    def _generate(self, request_id):
        queued = self.client.post(
            "/internal/learning/classrooms/generate",
            json={
                "courseId": self.course["id"],
                "courseVersion": self.course["version"],
                "requestId": request_id,
            },
            headers=self._internal_headers(),
        )
        if queued.status_code != 202:
            return queued
        media = self.client.post(
            "/internal/learning/media/materialize",
            json={"jobId": queued.json["media"]["id"]},
            headers=self._internal_headers(),
        )
        self.assertEqual(media.status_code, 200, media.json)
        self.assertEqual(media.json["package"]["status"], "published")
        return self.client.post(
            "/internal/learning/classrooms/generate",
            json={
                "courseId": self.course["id"],
                "courseVersion": self.course["version"],
                "requestId": request_id,
            },
            headers=self._internal_headers(),
        )

    def _runtime(self, session_id):
        response = self.client.get(
            f"/api/v2/student/learning/sessions/{session_id}/runtime",
            headers=self._student_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def _complete(self, session_id, action_id, revision, key, result=None):
        return self.client.post(
            f"/api/v2/student/learning/sessions/{session_id}/actions/{action_id}/complete",
            json={
                "cursorRevision": revision,
                "idempotencyKey": key,
                "result": result or {},
            },
            headers=self._student_headers(),
        )

    def _practice_question_ids(self):
        flow = self.course["content"]["teachingFlow"]
        return [*flow["guidedQuestionIds"], *flow["independentQuestionIds"]]

    def _correct_answers(self):
        by_id = {item["id"]: item for item in self.course["content"]["questions"]}
        return [by_id[item]["answer"] for item in self._practice_question_ids()]

    def _login_parent(self, phone):
        code = request_debug_code(self.client, phone)
        response = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _create_parent_identity(self):
        response = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers=self._parent_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)

    def _create_child(self, name, grade_code):
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

    def _insert_sibling(self, name):
        sibling_id = "lesson_package_sibling"
        with self.database.transaction() as conn:
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
                FROM children WHERE id = ?
                """,
                (sibling_id, name, name, self.child_id),
            )
        return sibling_id

    def _pair_student(self, child_id, pin):
        pairing = self.client.post(
            f"/api/v2/parent/children/{child_id}/student-access/pairing-codes",
            json={"pin": pin},
            headers=self._parent_headers(),
        )
        self.assertEqual(pairing.status_code, 200, pairing.json)
        response = self.client.post(
            "/api/v2/student/auth/pair",
            json={
                "pairingCode": pairing.json["pairingCode"],
                "clientDevice": {"label": "课堂浏览器", "type": "browser", "platform": "web"},
            },
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["tokens"]["accessToken"]

    def _internal_headers(self):
        return {
            "X-Mira-Internal-Token": self.internal_token,
            "X-Mira-Internal-Source": "classroom-worker",
        }

    def _parent_headers(self):
        return {"Authorization": f"Bearer {self.parent_access_token}"}

    def _student_headers(self, token=None):
        return {"Authorization": f"Bearer {token or self.student_access_token}"}

    def _assert_no_answer_fields(self, value):
        forbidden = {
            "answer",
            "answers",
            "correct",
            "correctanswer",
            "analysis",
            "solution",
            "expected",
            "acceptedanswers",
            "score",
            "points",
        }
        if isinstance(value, list):
            for item in value:
                self._assert_no_answer_fields(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                normalized = "".join(char for char in key.casefold() if char.isalpha())
                self.assertNotIn(normalized, forbidden)
                self._assert_no_answer_fields(item)


if __name__ == "__main__":
    unittest.main()
