from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

from core.database import Database, DatabaseConnection
from core.errors import ApiError
from core.security import now_ms
from content.primary_skill_boundaries import (
    PRIMARY_CURRICULUM_VERSION,
    boundaries_for,
)
from repositories.learning_repository import LearningRepository
from repositories.profile_repository import ProfileRepository
from schemas.learning import (
    decode_question_response,
    learning_task_payload,
    lesson_payload,
    mastery_payload,
    question_payload,
    recommendation_payload,
    report_payload,
    public_teaching_flow_payload,
    session_payload,
)
from services.auth_service import AuthService
from services.learning_difficulty import available_skill_order, preferred_difficulty, selection_payload
from services.formal_student_learning_access import (
    FORMAL_STUDENT_GRADE_CODES,
    assert_formal_student_grade_open,
    assert_formal_student_release_ready,
    assert_formal_student_workspace_open,
)
from services.learning_question_evaluator import (
    STATUS_CORRECT,
    STATUS_INCORRECT,
    LearningQuestionEvaluator,
)


LEARNING_SLOTS = ("core", "rotation", "extension")
MAX_AUTOMATIC_CARRYOVER_COUNT = 1
MAX_AUTOMATIC_CARRYOVER_DAYS = 2
DEFAULT_SLOT_STARTS = {
    "core": "19:30",
    "rotation": "19:45",
    "extension": "20:00",
}

# This deterministic matrix is anchored to the September school-year boundary,
# not the weekday.  The first two subjects rotate and every primary grade
# follows the same auditable 14-day rhythm.  The first two entries keep
# the established daily ordering; the remaining subject is always assigned to
# the extension slot so every day contains Chinese, math, and English.
PRIMARY_14_DAY_SUBJECT_MATRIX = (
    ("math", "chinese"),
    ("english", "math"),
    ("chinese", "english"),
    ("math", "chinese"),
    ("english", "math"),
    ("chinese", "math"),
    ("english", "chinese"),
    ("math", "english"),
    ("chinese", "math"),
    ("english", "chinese"),
    ("math", "chinese"),
    ("english", "math"),
    ("chinese", "english"),
    ("math", "chinese"),
)

SUBJECT_LABELS = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
}

_FORMAL_DAILY_PREPARATION_SKIP_CODES = frozenset(
    {
        "student_learning_primary_only",
        "student_learning_grade_not_open",
        "student_learning_release_not_ready",
    }
)


class LearningService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        static_catalog_enabled: bool = True,
        dynamic_generation_service: Any | None = None,
        dynamic_pool_target: int = 1,
        formal_learning_access_checker: Any | None = None,
        course_library_enabled: bool = False,
    ):
        database = Database(database_url)
        self.auth_service = auth_service
        self.course_library_enabled = course_library_enabled
        self.repository = LearningRepository(database)
        self.profile_repository = ProfileRepository(database)
        self.question_evaluator = LearningQuestionEvaluator()
        self.static_catalog_enabled = bool(static_catalog_enabled)
        self.dynamic_generation_service = dynamic_generation_service
        self.dynamic_pool_target = max(1, int(dynamic_pool_target))
        self.formal_learning_access_checker = formal_learning_access_checker
        self._catalog_ready = False

    def today(
        self,
        access_token: str,
        query: dict,
        *,
        formal_student_child_id: str | None = None,
    ) -> dict:
        """Student-owned Today read that keeps the automatic assignment fallback."""

        self._ensure_catalog()
        context = self.auth_service.authenticate(access_token)
        child_id = self._required_text(query, "childId", "请选择孩子")
        learning_date = self._learning_date(query.get("date"))
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            child = self._child_or_error(conn, family_id, child_id)
        if formal_student_child_id is None:
            self._ensure_dynamic_supply(child=child, learning_date=learning_date)
        with self.repository.transaction() as conn:
            child = self._child_for_formal_student_write(
                conn,
                family_id=family_id,
                child_id=child_id,
                formal_student_child_id=formal_student_child_id,
            )
            tasks, _ = self._ensure_today_for_child(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                scheduled_start=None,
                created_by=context["user"]["id"],
                preserve_existing_tasks=formal_student_child_id is not None,
            )
            return self._today_payload(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                tasks=tasks,
            )

    def parent_overview(self, access_token: str, query: dict) -> dict:
        """Return the parent Home learning projection without materializing work.

        This path deliberately skips dynamic-supply checks and
        ``_ensure_today_for_child``. Existing tasks, sessions, mastery and reports
        remain visible; an unassigned slot is represented as a recommendation.
        """

        self._ensure_catalog()
        context = self.auth_service.authenticate(access_token)
        child_id = self._required_text(query, "childId", "请选择孩子")
        learning_date = self._learning_date(query.get("date"))
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            child = self._child_or_error(conn, family_id, child_id)
            tasks = self.repository.get_today_tasks(
                conn,
                family_id=family_id,
                child_id=child_id,
                learning_date=learning_date,
            )
            return self._today_payload(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                tasks=tasks,
            )

    def assign_today(
        self,
        access_token: str,
        data: dict,
        *,
        formal_student_child_id: str | None = None,
    ) -> dict:
        self._ensure_catalog()
        context = self.auth_service.authenticate(access_token)
        child_id = self._required_text(data, "childId", "请选择孩子")
        learning_date = self._learning_date(data.get("date"))
        scheduled_start = self._scheduled_start(data.get("scheduledStart"))
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            child = self._child_or_error(conn, family_id, child_id)
        if formal_student_child_id is None:
            self._ensure_dynamic_supply(child=child, learning_date=learning_date)
        with self.repository.transaction() as conn:
            child = self._child_for_formal_student_write(
                conn,
                family_id=family_id,
                child_id=child_id,
                formal_student_child_id=formal_student_child_id,
            )
            tasks, created_count = self._ensure_today_for_child(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                scheduled_start=scheduled_start,
                created_by=context["user"]["id"],
                preserve_existing_tasks=formal_student_child_id is not None,
            )
            payload = self._today_payload(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                tasks=tasks,
            )
            payload["created"] = created_count > 0
            payload["createdCount"] = created_count
            return payload

    def ensure_today_for_all_primary_children(
        self,
        *,
        learning_date: str | None = None,
    ) -> dict:
        """Materialize daily slots only for children with a ready formal release.

        This method is deliberately independent of the scheduler runner.  A
        backend startup/timer integration may call it; ``today`` remains the
        lazy safety net when that background call has not happened yet.
        """

        self._ensure_catalog()
        resolved_date = self._learning_date(learning_date)
        with self.repository.transaction() as conn:
            children = (
                self.repository.list_primary_children_pending_daily_preparation(
                    conn,
                    learning_date=resolved_date,
                )
            )

        created_count = 0
        ensured_count = 0
        skipped: list[dict] = []
        failures: list[dict] = []
        for child in children:
            try:
                with self.repository.transaction() as conn:
                    if (
                        str(child.get("grade_code") or "")
                        not in FORMAL_STUDENT_GRADE_CODES
                    ):
                        assert_formal_student_grade_open(child)
                    assert_formal_student_release_ready(conn, child)
                self._ensure_dynamic_supply(
                    child=child,
                    learning_date=resolved_date,
                )
                with self.repository.transaction() as conn:
                    live_child = self._child_for_formal_student_write(
                        conn,
                        family_id=child["family_id"],
                        child_id=child["id"],
                        formal_student_child_id=child["id"],
                    )
                    _, child_created = self._ensure_today_for_child(
                        conn,
                        family_id=live_child["family_id"],
                        child=live_child,
                        learning_date=resolved_date,
                        scheduled_start=None,
                        created_by="system_learning_scheduler",
                        preserve_existing_tasks=True,
                    )
                ensured_count += 1
                created_count += child_created
            except ApiError as exc:
                outcome = {
                    "childId": child["id"],
                    "code": exc.code,
                    "message": exc.message,
                }
                if exc.code in _FORMAL_DAILY_PREPARATION_SKIP_CODES:
                    skipped.append(outcome)
                else:
                    failures.append(outcome)

        return {
            "ok": not failures,
            "date": resolved_date,
            "childrenChecked": len(children),
            "childrenEnsured": ensured_count,
            "childrenSkipped": len(skipped),
            "createdCount": created_count,
            "skipped": skipped,
            "failures": failures,
        }

    def start_session(
        self,
        access_token: str,
        data: dict,
        *,
        formal_student_child_id: str | None = None,
        atomic_session_binder: (
            Callable[[DatabaseConnection, dict], dict] | None
        ) = None,
    ) -> dict:
        self._ensure_catalog()
        context = self.auth_service.authenticate(access_token)
        task_id = self._required_text(data, "taskId", "缺少学习任务 ID")
        family_id = context["family"]["id"]
        now = now_ms()
        with self.repository.transaction() as conn:
            task_snapshot = self.repository.get_task(
                conn,
                family_id=family_id,
                task_id=task_id,
            )
            if task_snapshot is None:
                raise ApiError("task_not_found", "学习任务不存在", 404)
            child = self._lock_formal_student_child(
                conn,
                family_id=family_id,
                child_id=task_snapshot["child_id"],
                formal_student_child_id=formal_student_child_id,
            )
            task = self.repository.get_task(
                conn,
                family_id=family_id,
                task_id=task_id,
                for_update=True,
            )
            if task is None or task["child_id"] != child["id"]:
                raise ApiError("task_not_found", "学习任务不存在", 404)
            if task["type"] != "learning" or not task.get("learning_course_id"):
                raise ApiError("not_learning_task", "这个任务不是可授课的学习任务")
            # One stable write order for start and answer: child, task,
            # session, then formal publication authority.
            self.repository.get_session_for_task(
                conn,
                family_id=family_id,
                task_id=task_id,
                for_update=True,
            )
            self._assert_formal_student_release_for_locked_child(
                conn,
                child=child,
                formal_student_child_id=formal_student_child_id,
            )
            if formal_student_child_id is not None and not self.static_catalog_enabled:
                course = self.repository.get_student_visible_course(
                    conn,
                    family_id=family_id,
                    child_id=str(child["id"]),
                    grade_code=str(child["grade_code"]),
                    grade_selection_revision=int(
                        child.get("grade_selection_revision") or 0
                    ),
                    course_id=str(task["learning_course_id"]),
                    course_version=str(task["learning_course_version"]),
                )
                if course is None:
                    raise ApiError(
                        "learning_classroom_release_changed",
                        "正式课程刚刚更新，请重新打开这节课",
                        409,
                    )
            else:
                course = self.repository.get_course(
                    conn,
                    course_id=task["learning_course_id"],
                    version=task["learning_course_version"],
                    for_update=True,
                )
            if course is None:
                raise ApiError("course_version_not_found", "课程版本不存在", 409)
            if child["grade_code"] != course["grade_code"]:
                raise ApiError("course_grade_mismatch", "课程与孩子当前年级不匹配", 409)
            session, created = self.repository.create_or_get_session(
                conn,
                family_id=family_id,
                child_id=task["child_id"],
                task_id=task["id"],
                course_id=course["id"],
                course_version=course["version"],
                now=now,
            )
            if (
                str(session.get("course_id") or "") != str(course["id"])
                or str(session.get("course_version") or "")
                != str(course["version"])
            ):
                raise ApiError(
                    "learning_session_course_conflict",
                    "学习任务的课程版本已变化，请重新打开",
                    409,
                )
            if session["status"] != "completed":
                self.repository.mark_task_in_progress(
                    conn,
                    family_id=family_id,
                    task_id=task_id,
                    now=now,
                )
            if created:
                self.repository.add_task_event(
                    conn,
                    family_id=family_id,
                    task_id=task_id,
                    event_type="learning_session_started",
                    message="孩子开始学习",
                    payload={
                        "sessionId": session["id"],
                        "courseId": course["id"],
                        "courseVersion": course["version"],
                    },
                    now=now,
                )
            runtime_questions = self._questions(course)
            teaching_flow = public_teaching_flow_payload(
                course,
                choice_seed=str(session["id"]),
            )
            payload = {
                "ok": True,
                "resumed": not created,
                "session": session_payload(
                    session,
                    questions=runtime_questions,
                    teaching_flow=teaching_flow,
                ),
                "lesson": lesson_payload(course, choice_seed=str(session["id"])),
            }
            if atomic_session_binder is not None:
                payload = atomic_session_binder(conn, payload)
            return payload

    def answer(
        self,
        access_token: str,
        session_id: str,
        data: dict,
        *,
        formal_student_child_id: str | None = None,
    ) -> dict:
        context = self.auth_service.authenticate(access_token)
        if "response" in data:
            submitted_answer = data.get("response")
        elif "answer" in data:
            submitted_answer = data.get("answer")
        else:
            raise ApiError("missing_answer", "请先回答这道题")
        if self._is_empty_answer(submitted_answer):
            raise ApiError("missing_answer", "请先回答这道题")
        family_id = context["family"]["id"]
        now = now_ms()
        with self.repository.transaction() as conn:
            session_snapshot = self.repository.get_session(
                conn,
                family_id=family_id,
                session_id=session_id,
            )
            if session_snapshot is None:
                raise ApiError("learning_session_not_found", "学习记录不存在", 404)
            child = self._lock_formal_student_child(
                conn,
                family_id=family_id,
                child_id=session_snapshot["child_id"],
                formal_student_child_id=formal_student_child_id,
            )
            task = self.repository.get_task(
                conn,
                family_id=family_id,
                task_id=session_snapshot["task_id"],
                for_update=True,
            )
            if task is None or task["child_id"] != child["id"]:
                raise ApiError("learning_session_not_found", "学习记录不存在", 404)
            session = self.repository.get_session(
                conn,
                family_id=family_id,
                session_id=session_id,
                for_update=True,
            )
            if (
                session is None
                or session["child_id"] != child["id"]
                or session["task_id"] != task["id"]
            ):
                raise ApiError("learning_session_not_found", "学习记录不存在", 404)
            self._assert_formal_student_release_for_locked_child(
                conn,
                child=child,
                formal_student_child_id=formal_student_child_id,
            )
            if formal_student_child_id is not None and not self.static_catalog_enabled:
                course = self.repository.get_student_visible_course(
                    conn,
                    family_id=family_id,
                    child_id=str(child["id"]),
                    grade_code=str(child["grade_code"]),
                    grade_selection_revision=int(
                        child.get("grade_selection_revision") or 0
                    ),
                    course_id=str(session["course_id"]),
                    course_version=str(session["course_version"]),
                )
            else:
                course = self.repository.get_course(
                    conn,
                    course_id=session["course_id"],
                    version=session["course_version"],
                    for_update=True,
                )
            if course is None:
                raise ApiError("course_version_not_found", "课程版本不存在", 409)
            questions = self._questions(course)
            if session["status"] == "completed":
                report = self.repository.get_report_for_session(
                    conn,
                    family_id=family_id,
                    session_id=session_id,
                    for_update=True,
                )
                return {
                    "ok": True,
                    "correct": None,
                    "feedback": "本次学习已经完成。",
                    "hint": None,
                    "canRetry": False,
                    "hintLevel": 0,
                    "nextQuestion": None,
                    "completed": True,
                    "session": session_payload(session, questions=questions),
                    "report": report_payload(report),
                }

            index = int(session.get("current_question_index") or 0)
            if index >= len(questions):
                raise ApiError("invalid_learning_progress", "学习进度异常", 409)
            question = questions[index]
            evaluated_answer = decode_question_response(
                question,
                submitted_answer,
                choice_seed=f"{session['id']}:{question['id']}",
            )
            evaluation = self.question_evaluator.evaluate(question, evaluated_answer)
            if evaluation.get("status") not in {STATUS_CORRECT, STATUS_INCORRECT}:
                raise ApiError(
                    "learning_question_not_executable",
                    "课程题目的判定规则不可执行，请稍后重试",
                    503,
                )
            correct = evaluation["status"] == STATUS_CORRECT
            answers = self.repository.parse_json(session.get("answers_json"), [])
            if not isinstance(answers, list):
                answers = []
            previous_attempts = sum(
                1
                for item in answers
                if isinstance(item, dict) and item.get("questionId") == question["id"]
            )
            attempt_number = previous_attempts + 1
            requires_correct_answer = self._teaching_flow_requires_correct_answer(
                course,
                question_id=str(question["id"]),
            )
            answers.append(
                {
                    "questionId": question["id"],
                    "questionIndex": index,
                    "answer": submitted_answer,
                    "normalizedResponse": evaluation.get("normalizedResponse"),
                    "evaluatorVersion": evaluation.get("evaluatorVersion"),
                    "correct": correct,
                    "attemptNumber": attempt_number,
                    "answeredAt": now,
                }
            )
            correct_count = int(session.get("correct_count") or 0)
            if correct:
                correct_count += 1
                next_index = index + 1
                feedback = f"答对了！{question['explanation']}"
                hint = None
                can_retry = False
                hint_level = 0
            elif requires_correct_answer:
                next_index = index
                feedback = (
                    "还差一点，按照提示再试一次。"
                    if attempt_number == 1
                    else f"我们换一种方法再想一遍。{question['explanation']}"
                )
                hint = question["hint"]
                can_retry = True
                hint_level = min(attempt_number, 2)
            elif attempt_number < 2:
                next_index = index
                feedback = "还差一点，按照提示再试一次。"
                hint = question["hint"]
                can_retry = True
                hint_level = 1
            else:
                next_index = index + 1
                feedback = f"这题先记下来。{question['explanation']}"
                hint = None
                can_retry = False
                hint_level = 0

            completed = next_index >= len(questions)
            session = self.repository.update_session(
                conn,
                family_id=family_id,
                session_id=session_id,
                status="completed" if completed else "in_progress",
                current_question_index=next_index,
                correct_count=correct_count,
                attempted_count=int(session.get("attempted_count") or 0) + 1,
                answers=answers,
                completed_at=now if completed else None,
                now=now,
            )
            self.repository.add_task_event(
                conn,
                family_id=family_id,
                task_id=session["task_id"],
                event_type="learning_answer_evaluated",
                message="学习题目已判定",
                payload={
                    "sessionId": session_id,
                    "questionId": question["id"],
                    "questionIndex": index,
                    "correct": correct,
                    "attemptNumber": attempt_number,
                    "evaluatorVersion": evaluation.get("evaluatorVersion"),
                },
                now=now,
            )
            report = None
            if completed:
                report = self._complete_and_report(
                    conn,
                    session=session,
                    course=course,
                    questions=questions,
                    answers=answers,
                    now=now,
                )
            session_data = session_payload(session, questions=questions)
            return {
                "ok": True,
                "correct": correct,
                "feedback": feedback,
                "hint": hint,
                "canRetry": can_retry,
                "hintLevel": hint_level,
                "nextQuestion": session_data["currentQuestion"],
                "completed": completed,
                "session": session_data,
                "report": report_payload(report),
            }

    def record_authoritative_runtime_answer(
        self,
        conn,
        *,
        authority: dict,
        question_id: str,
        submitted_answer: object,
        attempt_number: int,
        now: int,
    ) -> dict:
        """Score one full-Runtime answer without completing the lesson early.

        Runtime supplies only the source question id and response. The locked
        Mira course owns ordering, normalization, answers and scoring. Final
        session/report publication remains reserved for the separately
        authenticated ``classroom_completed`` event.
        """

        session, course = self._runtime_authority_session_course(authority)
        if str(session.get("status") or "") == "completed":
            raise ApiError(
                "runtime_learning_already_completed",
                "本次学习已经完成",
                409,
            )
        if self._is_empty_answer(submitted_answer):
            raise ApiError("missing_answer", "请先回答这道题")
        questions = self._questions(course)
        index = int(session.get("current_question_index") or 0)
        if index < 0 or index >= len(questions):
            raise ApiError(
                "runtime_answer_progress_conflict",
                "课堂作答进度与课程版本不一致",
                409,
            )
        question = questions[index]
        if str(question.get("id") or "") != str(question_id or ""):
            raise ApiError(
                "runtime_answer_question_conflict",
                "课堂题目与当前权威题目不一致",
                409,
            )
        evaluated_answer = decode_question_response(
            question,
            submitted_answer,
            choice_seed=f"{session['id']}:{question['id']}",
        )
        evaluation = self.question_evaluator.evaluate(question, evaluated_answer)
        if evaluation.get("status") not in {STATUS_CORRECT, STATUS_INCORRECT}:
            raise ApiError(
                "learning_question_not_executable",
                "课程题目的判定规则不可执行，请稍后重试",
                503,
            )
        answers = self.repository.parse_json(session.get("answers_json"), [])
        if not isinstance(answers, list):
            raise ApiError(
                "runtime_answer_history_invalid",
                "课堂作答记录不可用",
                503,
            )
        previous_attempts = sum(
            1
            for item in answers
            if isinstance(item, dict) and item.get("questionId") == question["id"]
        )
        if attempt_number != 1 or previous_attempts != 0:
            raise ApiError(
                "runtime_answer_attempt_conflict",
                "课堂题目只接受首次权威作答",
                409,
            )
        correct = evaluation["status"] == STATUS_CORRECT
        answers.append(
            {
                "questionId": question["id"],
                "questionIndex": index,
                "answer": submitted_answer,
                "normalizedResponse": evaluation.get("normalizedResponse"),
                "evaluatorVersion": evaluation.get("evaluatorVersion"),
                "correct": correct,
                "attemptNumber": attempt_number,
                "hintProvided": not correct,
                "answeredAt": now,
                "source": "openmaic_runtime_event",
            }
        )
        correct_count = int(session.get("correct_count") or 0)
        if correct:
            correct_count += 1
        next_index = index + 1
        questions_complete = next_index >= len(questions)
        updated = self.repository.update_session(
            conn,
            family_id=session["family_id"],
            session_id=session["id"],
            status="in_progress",
            current_question_index=next_index,
            correct_count=correct_count,
            attempted_count=int(session.get("attempted_count") or 0) + 1,
            answers=answers,
            completed_at=None,
            now=now,
        )
        if updated is None:
            raise ApiError(
                "runtime_answer_persistence_failed",
                "课堂作答记录未能安全保存",
                503,
            )
        self.repository.add_task_event(
            conn,
            family_id=session["family_id"],
            task_id=session["task_id"],
            event_type="learning_answer_evaluated",
            message="完整课堂题目已由服务端判定",
            payload={
                "sessionId": session["id"],
                "questionId": question["id"],
                "questionIndex": index,
                "correct": correct,
                "attemptNumber": attempt_number,
                "evaluatorVersion": evaluation.get("evaluatorVersion"),
                "source": "openmaic_runtime_event",
            },
            now=now,
        )
        return {
            "questionId": str(question["id"]),
            "attemptNumber": attempt_number,
            "correct": correct,
            "evaluatorVersion": str(evaluation.get("evaluatorVersion") or ""),
            "hint": None if correct else str(question.get("hint") or ""),
            "questionsComplete": questions_complete,
        }

    def authoritative_runtime_questions_complete(self, conn, *, authority: dict) -> bool:
        session, course = self._runtime_authority_session_course(authority)
        questions = self._questions(course)
        answers = self.repository.parse_json(session.get("answers_json"), [])
        if not isinstance(answers, list):
            return False
        progressed = int(session.get("current_question_index") or 0)
        answered_ids = {
            str(item.get("questionId") or "")
            for item in answers
            if isinstance(item, dict)
        }
        return progressed >= len(questions) and all(
            str(question.get("id") or "") in answered_ids for question in questions
        )

    def authoritative_runtime_answered_question_ids(
        self,
        conn,
        *,
        authority: dict,
    ) -> list[str]:
        """Return authoritative progress across every launch of one lesson."""

        session, course = self._runtime_authority_session_course(authority)
        questions = self._questions(course)
        answers = self.repository.parse_json(session.get("answers_json"), [])
        if not isinstance(answers, list):
            return []
        answered_ids = {
            str(item.get("questionId") or "")
            for item in answers
            if isinstance(item, dict)
        }
        return [
            str(question.get("id") or "")
            for question in questions
            if str(question.get("id") or "") in answered_ids
        ]

    def complete_authoritative_runtime_session(
        self,
        conn,
        *,
        authority: dict,
        now: int,
    ):
        session, course = self._runtime_authority_session_course(authority)
        if str(session.get("status") or "") == "completed":
            raise ApiError(
                "runtime_learning_already_completed",
                "本次学习已经完成",
                409,
            )
        if not self.authoritative_runtime_questions_complete(
            conn,
            authority=authority,
        ):
            raise ApiError(
                "runtime_event_evidence_incomplete",
                "权威作答证据尚未完成",
                409,
            )
        questions = self._questions(course)
        answers = self.repository.parse_json(session.get("answers_json"), [])
        assert isinstance(answers, list)
        completed_session = self.repository.update_session(
            conn,
            family_id=session["family_id"],
            session_id=session["id"],
            status="completed",
            current_question_index=len(questions),
            correct_count=int(session.get("correct_count") or 0),
            attempted_count=int(session.get("attempted_count") or 0),
            answers=answers,
            completed_at=now,
            now=now,
        )
        if completed_session is None:
            raise ApiError(
                "runtime_learning_completion_failed",
                "学习完成状态未能安全保存",
                503,
            )
        return self._complete_and_report(
            conn,
            session=completed_session,
            course=course,
            questions=questions,
            answers=answers,
            now=now,
        )

    @staticmethod
    def _runtime_authority_session_course(authority: dict) -> tuple[dict, dict]:
        session = {
            "id": authority.get("learning_session_id"),
            "family_id": authority.get("family_id"),
            "child_id": authority.get("child_id"),
            "task_id": authority.get("session_task_id"),
            "course_id": authority.get("session_course_id"),
            "course_version": authority.get("session_course_version"),
            "status": authority.get("session_status"),
            "current_question_index": authority.get(
                "session_current_question_index"
            ),
            "correct_count": authority.get("session_correct_count"),
            "attempted_count": authority.get("session_attempted_count"),
            "answers_json": authority.get("session_answers_json"),
            "started_at": authority.get("session_started_at"),
            "completed_at": authority.get("session_completed_at"),
        }
        course = {
            "id": authority.get("session_course_id"),
            "version": authority.get("session_course_version"),
            "grade_code": authority.get("course_grade_code"),
            "subject": authority.get("course_subject"),
            "node_code": authority.get("course_node_code"),
            "title": authority.get("course_title"),
            "objective": authority.get("course_objective"),
            "content_json": authority.get("course_content_json"),
        }
        required_session = (
            "id",
            "family_id",
            "child_id",
            "task_id",
            "course_id",
            "course_version",
        )
        required_course = (
            "id",
            "version",
            "grade_code",
            "subject",
            "node_code",
            "content_json",
        )
        if any(not session.get(key) for key in required_session) or any(
            not course.get(key) for key in required_course
        ):
            raise ApiError(
                "runtime_event_authority_invalid",
                "正式课堂的学习会话绑定不完整",
                409,
            )
        return session, course

    def latest_report(self, access_token: str, query: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        child_id = self._required_text(query, "childId", "请选择孩子")
        subject = str(query.get("subject") or "").strip() or None
        if subject is not None and subject not in SUBJECT_LABELS:
            raise ApiError("invalid_learning_subject", "学习科目不正确")
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            self._child_or_error(conn, family_id, child_id)
            report = self.repository.latest_report(
                conn,
                family_id=family_id,
                child_id=child_id,
                subject=subject,
            )
            mastery = None
            if report is not None:
                course = self.repository.get_course(
                    conn,
                    course_id=report["course_id"],
                    version=report["course_version"],
                )
                if course is not None:
                    mastery = self.repository.get_mastery_state(
                        conn,
                        family_id=family_id,
                        child_id=child_id,
                        node_code=course["node_code"],
                        subject=course["subject"],
                        grade_code=course["grade_code"],
                    )
            return {
                "ok": True,
                "report": report_payload(report),
                "mastery": mastery_payload(mastery),
            }

    def list_reports(self, access_token: str, query: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        child_id = self._required_text(query, "childId", "请选择孩子")
        subject = str(query.get("subject") or "").strip() or None
        if subject is not None and subject not in SUBJECT_LABELS:
            raise ApiError("invalid_learning_subject", "学习科目不正确")
        try:
            limit = int(query.get("limit") or 20)
        except (TypeError, ValueError) as exc:
            raise ApiError(
                "invalid_learning_report_limit",
                "分页数量无效",
                400,
            ) from exc
        if limit < 1 or limit > 50:
            raise ApiError(
                "invalid_learning_report_limit",
                "分页数量须为 1 到 50",
                400,
            )
        try:
            cursor = LearningRepository.decode_report_cursor(query.get("cursor"))
        except ValueError as exc:
            raise ApiError(
                "invalid_learning_report_cursor",
                "分页位置无效",
                400,
            ) from exc
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            self._child_or_error(conn, family_id, child_id)
            reports, next_cursor = self.repository.list_reports(
                conn,
                family_id=family_id,
                child_id=child_id,
                subject=subject,
                cursor=cursor,
                limit=limit,
            )
        return {
            "ok": True,
            "childId": child_id,
            "subject": subject,
            "items": [report_payload(report) for report in reports],
            "nextCursor": next_cursor,
        }

    def report_detail(
        self,
        access_token: str,
        report_id: str,
        query: dict,
    ) -> dict:
        context = self.auth_service.authenticate(access_token)
        child_id = self._required_text(query, "childId", "请选择孩子")
        normalized_report_id = str(report_id or "").strip()
        if not normalized_report_id:
            raise ApiError("learning_report_not_found", "学习报告不存在", 404)
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            self._child_or_error(conn, family_id, child_id)
            report = self.repository.get_report_detail(
                conn,
                family_id=family_id,
                child_id=child_id,
                report_id=normalized_report_id,
            )
        if report is None:
            raise ApiError("learning_report_not_found", "学习报告不存在", 404)
        return {
            "ok": True,
            "childId": child_id,
            "report": report_payload(report),
        }

    def _complete_and_report(
        self,
        conn,
        *,
        session,
        course,
        questions: list[dict],
        answers: list[dict],
        now: int,
    ):
        total = len(questions)
        correct_count = int(session.get("correct_count") or 0)
        first_attempts = {
            item.get("questionId"): item
            for item in answers
            if isinstance(item, dict) and int(item.get("attemptNumber") or 0) == 1
        }
        content = self.repository.parse_json(course.get("content_json"), {})
        flow = content.get("teachingFlow") if isinstance(content, dict) else None
        guided_ids = (
            [str(item) for item in flow.get("guidedQuestionIds") or []]
            if isinstance(flow, dict)
            else []
        )
        independent_ids = (
            [str(item) for item in flow.get("independentQuestionIds") or []]
            if isinstance(flow, dict)
            else []
        )
        has_lesson_roles = (
            isinstance(flow, dict)
            and flow.get("schemaVersion") == "mira.learning.teaching-flow.v1"
            and len(guided_ids) == 2
            and len(independent_ids) == 2
            and [str(question.get("id") or "") for question in questions]
            == [*guided_ids, *independent_ids]
        )
        evidence_count = 2 if has_lesson_roles else total
        evidence_ids = independent_ids if has_lesson_roles else list(first_attempts)
        independent_correct_count = sum(
            1
            for question_id in evidence_ids
            if isinstance(first_attempts.get(question_id), dict)
            and first_attempts[question_id].get("correct") is True
        )
        eventually_correct_ids = {
            str(item.get("questionId") or "")
            for item in answers
            if isinstance(item, dict) and item.get("correct") is True
        }
        eventual_independent_correct_count = sum(
            1 for question_id in evidence_ids if question_id in eventually_correct_ids
        )
        hint_count = sum(
            1
            for item in answers
            if isinstance(item, dict)
            and item.get("correct") is False
            and int(item.get("attemptNumber") or 0) == 1
        )
        score = (
            round(independent_correct_count / evidence_count * 100)
            if evidence_count
            else 0
        )
        has_unpracticed_course = self.repository.has_unpracticed_course(
            conn,
            family_id=session["family_id"],
            child_id=session["child_id"],
            grade_code=course["grade_code"],
            subject=course["subject"],
            excluding_node_code=course["node_code"],
            content_origins=self._scheduled_content_origins(),
            require_teaching_flow=not self.static_catalog_enabled,
            require_catalog_release=not self.static_catalog_enabled,
            curriculum_version=(
                PRIMARY_CURRICULUM_VERSION
                if not self.static_catalog_enabled
                else None
            ),
        )
        subject_label = SUBJECT_LABELS.get(str(course["subject"]), "本学科")
        if has_lesson_roles and eventual_independent_correct_count == evidence_count:
            mastery = "mastered"
            summary = (
                "两道独立练习首答全对；本结论只代表本课的 2 条学习证据。"
                if independent_correct_count == evidence_count
                else "经过提示、再讲和重新验证，两道独立练习都已答对，本能力点已完成当堂闭环。"
            )
            next_step = (
                f"下次{subject_label}练习进入同年级的下一个能力点。"
                if has_unpracticed_course
                else "下一次按复习日期巩固本年级已学能力点。"
            )
        elif has_lesson_roles and independent_correct_count == 1:
            mastery = "developing"
            summary = "两道独立练习中有 1 道首答正确，目前只有 2 条本课证据，需要巩固。"
            next_step = (
                f"下次{subject_label}练习先复习本课错题，再进入未练能力点。"
                if has_unpracticed_course
                else "下次先复习本课错题，再按复习日期安排巩固。"
            )
        elif has_lesson_roles:
            mastery = "needs_practice"
            summary = "两道独立练习首答都未通过，目前只有 2 条本课证据，需要放慢速度巩固。"
            next_step = "建议从提示题开始复习，并用同类小题再练一次。"
        elif score >= 80:
            mastery = "mastered"
            summary = f"完成 {total} 道题，掌握情况良好。"
            next_step = (
                f"下次{subject_label}练习进入同年级的下一个能力点。"
                if has_unpracticed_course
                else "下一次按复习日期巩固本年级已学能力点。"
            )
        elif score >= 60:
            mastery = "developing"
            summary = f"完成 {total} 道题，基础已经形成，还需要一次巩固。"
            next_step = (
                f"下次{subject_label}练习先复习本课错题，再进入未练能力点。"
                if has_unpracticed_course
                else "下次先复习本课错题，再按复习日期安排巩固。"
            )
        else:
            mastery = "needs_practice"
            summary = f"完成 {total} 道题，目前需要放慢速度巩固基础。"
            next_step = "建议从提示题开始复习，并用同类小题再练一次。"

        correct_question_ids = {
            item.get("questionId")
            for item in answers
            if isinstance(item, dict) and item.get("correct") is True
        }
        strengths = []
        for question in questions:
            skill = str(question.get("skill") or f"{subject_label}基础")
            if question["id"] in correct_question_ids and skill not in strengths:
                strengths.append(skill)
        if not strengths:
            strengths = ["坚持完成本次学习"]

        report = self.repository.create_or_get_report(
            conn,
            family_id=session["family_id"],
            child_id=session["child_id"],
            task_id=session["task_id"],
            session_id=session["id"],
            course_id=course["id"],
            course_version=course["version"],
            learning_date=self._task_date(conn, session),
            grade_code=course["grade_code"],
            subject=course["subject"],
            score=score,
            correct_count=correct_count,
            independent_correct_count=independent_correct_count,
            hint_count=hint_count,
            total_questions=total,
            mastery_level=mastery,
            summary=summary,
            strengths=strengths,
            next_step=next_step,
            now=now,
        )
        review_days = 7 if mastery == "mastered" else 3 if mastery == "developing" else 1
        learning_date = date.fromisoformat(self._task_date(conn, session))
        self.repository.upsert_mastery_state(
            conn,
            family_id=session["family_id"],
            child_id=session["child_id"],
            node_code=course["node_code"],
            subject=course["subject"],
            grade_code=course["grade_code"],
            attempts=int(session.get("attempted_count") or 0),
            correct_count=correct_count,
            independent_correct_count=independent_correct_count,
            hint_count=hint_count,
            latest_score=score,
            mastery_level=mastery,
            last_practiced_at=now,
            next_review_date=(learning_date + timedelta(days=review_days)).isoformat(),
            course_id=course["id"],
            course_version=course["version"],
            now=now,
        )
        self.repository.mark_task_completed(
            conn,
            family_id=session["family_id"],
            task_id=session["task_id"],
            summary=summary,
            now=now,
        )
        self.repository.add_task_event(
            conn,
            family_id=session["family_id"],
            task_id=session["task_id"],
            event_type="learning_completed",
            message="本次学习已完成",
            payload={
                "sessionId": session["id"],
                "reportId": report["id"],
                "score": score,
                "masteryLevel": mastery,
                "independentCorrectCount": independent_correct_count,
                "evidenceCount": evidence_count,
                "evidencePolicy": (
                    "independent_all_correct_v1"
                    if has_lesson_roles
                    else "all_runtime_questions_v1"
                ),
                "hintCount": hint_count,
            },
            now=now,
        )
        return report

    def _task_date(self, conn, session) -> str:
        task = self.repository.get_task(
            conn,
            family_id=session["family_id"],
            task_id=session["task_id"],
        )
        return task["scheduled_date"]

    def _ensure_today_for_child(
        self,
        conn,
        *,
        family_id: str,
        child,
        learning_date: str,
        scheduled_start: str | None,
        created_by: str,
        preserve_existing_tasks: bool = False,
    ) -> tuple[list, int]:
        grade_code = self._primary_grade_code(child)
        subjects = self._subjects_for_date(child, learning_date)
        carryovers = self._ensure_daily_carryover(
            conn,
            family_id=family_id,
            child=child,
            learning_date=learning_date,
        )
        carryover_by_slot = {
            str(item.get("carryover_target_slot") or "core"): item
            for item in carryovers
        }
        tasks = self.repository.get_today_tasks(
            conn,
            family_id=family_id,
            child_id=child["id"],
            learning_date=learning_date,
        )
        by_slot = {
            str(task.get("learning_slot") or "core"): task for task in tasks
        }
        courses_by_slot = {
            slot: self.repository.get_course(
                conn,
                course_id=task["learning_course_id"],
                version=task["learning_course_version"],
            )
            for slot, task in by_slot.items()
        }
        for slot, task in carryover_by_slot.items():
            courses_by_slot[slot] = self.repository.get_course(
                conn,
                course_id=task["learning_course_id"],
                version=task["learning_course_version"],
            )
        used_course_ids = {
            str(task.get("learning_course_id") or "")
            for task in [*tasks, *carryovers]
            if str(task.get("learning_course_id") or "")
        }
        used_subjects = {
            str(course["subject"])
            for course in courses_by_slot.values()
            if course is not None
        }
        created_count = 0
        created_at = now_ms()

        # Old development data and an earlier pool-based scheduler could leave
        # an unstarted slot pointing at a later skill (or a legacy seed course).
        # Repair only replaceable tasks; any task with a session remains an
        # immutable learning record.
        if not self.static_catalog_enabled and not preserve_existing_tasks:
            for slot in LEARNING_SLOTS:
                if slot in carryover_by_slot:
                    continue
                task = by_slot.get(slot)
                current_course = courses_by_slot.get(slot)
                if (
                    task is None
                    or current_course is None
                    or not self._task_can_replace_course(conn, task)
                ):
                    continue
                expected_subject = subjects[slot]
                expected_node = self._next_skill_node_for_child(
                    conn,
                    child=child,
                    subject=expected_subject,
                )
                if (
                    str(current_course.get("subject")) == expected_subject
                    and str(current_course.get("node_code")) == expected_node
                    and str(current_course.get("content_origin") or "")
                    in self._scheduled_content_origins()
                    and self._course_has_teaching_flow(current_course)
                    and self._course_is_assignable(conn, child, current_course)
                ):
                    continue
                other_courses = [
                    course
                    for other_slot, course in courses_by_slot.items()
                    if other_slot != slot and course is not None
                ]
                replacement = self._course_for_child(
                    conn,
                    family_id=family_id,
                    child=child,
                    learning_date=learning_date,
                    subject=expected_subject,
                    excluding_course_ids=tuple(
                        str(course["id"]) for course in other_courses
                    ),
                    excluding_subjects=tuple(
                        str(course["subject"]) for course in other_courses
                    ),
                    allow_missing=True,
                )
                if replacement is None:
                    continue
                previous_course_id = str(task["learning_course_id"])
                previous_node_code = str(current_course.get("node_code") or "")
                repaired_task = self.repository.replace_unstarted_task_course(
                    conn,
                    family_id=family_id,
                    task_id=task["id"],
                    course=replacement,
                    now=created_at,
                )
                if (
                    repaired_task is None
                    or str(repaired_task["learning_course_id"])
                    == previous_course_id
                ):
                    continue
                by_slot[slot] = repaired_task
                courses_by_slot[slot] = replacement
                used_course_ids = {
                    str(item["learning_course_id"])
                    for item in by_slot.values()
                    if item.get("learning_course_id")
                }
                used_subjects = {
                    str(course["subject"])
                    for course in courses_by_slot.values()
                    if course is not None
                }
                self.repository.add_task_event(
                    conn,
                    family_id=family_id,
                    task_id=repaired_task["id"],
                    event_type="learning_reassigned",
                    message="已按学习进度调整今日课程",
                    payload={
                        "reason": "skill_progression",
                        "slot": slot,
                        "previousCourseId": previous_course_id,
                        "previousNodeCode": previous_node_code,
                        "courseId": replacement["id"],
                        "nodeCode": replacement["node_code"],
                        "subject": replacement["subject"],
                    },
                    now=created_at,
                )

        core_course = courses_by_slot.get("core")
        rotation_course = courses_by_slot.get("rotation")
        if (
            core_course is not None
            and rotation_course is not None
            and core_course["subject"] == rotation_course["subject"]
            and "rotation" not in carryover_by_slot
            and "rotation" in by_slot
        ):
            rotation_task = by_slot["rotation"]
            replacement = self._course_for_child(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                subject=subjects["rotation"],
                excluding_course_ids=tuple(used_course_ids),
                excluding_subjects=(str(core_course["subject"]),),
                allow_missing=True,
            )
            if replacement is None:
                replacement = rotation_course
            previous_course_id = str(rotation_task["learning_course_id"])
            repaired_task = self.repository.replace_unstarted_task_course(
                conn,
                family_id=family_id,
                task_id=rotation_task["id"],
                course=replacement,
                now=created_at,
            )
            if (
                repaired_task is not None
                and str(repaired_task["learning_course_id"]) != previous_course_id
            ):
                by_slot["rotation"] = repaired_task
                courses_by_slot["rotation"] = replacement
                used_course_ids.discard(previous_course_id)
                used_course_ids.add(str(replacement["id"]))
                used_subjects = {
                    str(course["subject"])
                    for course in courses_by_slot.values()
                    if course is not None
                }
                self.repository.add_task_event(
                    conn,
                    family_id=family_id,
                    task_id=repaired_task["id"],
                    event_type="learning_reassigned",
                    message="已纠正今日重复学科安排",
                    payload={
                        "slot": "rotation",
                        "previousCourseId": previous_course_id,
                        "courseId": replacement["id"],
                        "subject": replacement["subject"],
                    },
                    now=created_at,
                )

        for slot in LEARNING_SLOTS:
            if slot in by_slot or slot in carryover_by_slot:
                continue
            course = self._course_for_child(
                conn,
                family_id=family_id,
                child=child,
                learning_date=learning_date,
                subject=subjects[slot],
                excluding_course_ids=tuple(used_course_ids),
                excluding_subjects=tuple(used_subjects),
                allow_missing=True,
            )
            if course is None:
                continue
            task, created = self.repository.assign_today_task(
                conn,
                family_id=family_id,
                child_id=child["id"],
                learning_date=learning_date,
                slot=slot,
                scheduled_start=self._slot_start(slot, scheduled_start),
                course=course,
                created_by=created_by,
                now=created_at,
            )
            by_slot[slot] = task
            used_course_ids.add(str(task["learning_course_id"]))
            used_subjects.add(str(course["subject"]))
            if not created:
                continue
            created_count += 1
            actual_subject = str(course["subject"])
            preferred_subject = subjects[slot]
            self.repository.add_task_event(
                conn,
                family_id=family_id,
                task_id=task["id"],
                event_type="learning_assigned",
                message={
                    "core": "今日核心学习已安排",
                    "rotation": "今日轮换学习已安排",
                    "extension": "今日第三科学习已安排",
                }[slot],
                payload={
                    "slot": slot,
                    "preferredSubject": preferred_subject,
                    "subject": actual_subject,
                    "subjectFallback": actual_subject != preferred_subject,
                    "gradeCode": grade_code,
                    "courseId": task["learning_course_id"],
                    "courseVersion": task["learning_course_version"],
                },
                now=created_at,
            )

        return self.repository.get_today_tasks(
            conn,
            family_id=family_id,
            child_id=child["id"],
            learning_date=learning_date,
        ), created_count

    def _ensure_daily_carryover(
        self,
        conn,
        *,
        family_id: str,
        child,
        learning_date: str,
    ) -> list:
        """Bind at most one recent unfinished task into today's three slots.

        A binding never rewrites the source task date/course/session.  If an
        unstarted task was already materialized for the same target slot, it is
        cancelled with an audit event instead of being deleted.  A started
        current-day task always wins and the next eligible historical task is
        considered.
        """

        existing = self.repository.list_daily_carryovers(
            conn,
            family_id=family_id,
            child_id=child["id"],
            target_date=learning_date,
        )
        if len(existing) >= MAX_AUTOMATIC_CARRYOVER_COUNT:
            return existing[:MAX_AUTOMATIC_CARRYOVER_COUNT]

        learning_day = date.fromisoformat(learning_date)
        earliest_date = (
            learning_day - timedelta(days=MAX_AUTOMATIC_CARRYOVER_DAYS)
        ).isoformat()
        today_tasks = self.repository.get_today_tasks(
            conn,
            family_id=family_id,
            child_id=child["id"],
            learning_date=learning_date,
        )
        today_by_slot = {
            str(task.get("learning_slot") or "core"): task
            for task in today_tasks
        }
        candidates = self.repository.list_carryover_candidates(
            conn,
            family_id=family_id,
            child_id=child["id"],
            earliest_date=earliest_date,
            target_date=learning_date,
        )
        timestamp = now_ms()
        for candidate in candidates:
            slot = str(candidate.get("learning_slot") or "core")
            if slot not in LEARNING_SLOTS:
                slot = "core"
            current = today_by_slot.get(slot)
            if current is not None:
                if not self._task_can_replace_course(conn, current):
                    continue
                cancelled = self.repository.cancel_unstarted_task_for_carryover(
                    conn,
                    family_id=family_id,
                    task_id=current["id"],
                    now=timestamp,
                )
                if cancelled is None:
                    continue
                self.repository.add_task_event(
                    conn,
                    family_id=family_id,
                    task_id=current["id"],
                    event_type="learning_replaced_by_carryover",
                    message="今日新课已由未完成课程替换",
                    payload={
                        "sourceTaskId": candidate["id"],
                        "originDate": candidate["scheduled_date"],
                        "targetDate": learning_date,
                        "slot": slot,
                    },
                    now=timestamp,
                )

            reason = (
                "started_incomplete"
                if candidate.get("carryover_session_id")
                else "missed_unstarted"
            )
            carryover = self.repository.create_daily_carryover(
                conn,
                family_id=family_id,
                child_id=child["id"],
                source_task=candidate,
                target_date=learning_date,
                target_slot=slot,
                reason=reason,
                now=timestamp,
            )
            self.repository.reactivate_task_for_carryover(
                conn,
                family_id=family_id,
                task_id=candidate["id"],
                now=timestamp,
            )
            self.repository.add_task_event(
                conn,
                family_id=family_id,
                task_id=candidate["id"],
                event_type="learning_carryover_scheduled",
                message="未完成课程已顺延到今日",
                payload={
                    "carryoverId": carryover["id"],
                    "originDate": candidate["scheduled_date"],
                    "targetDate": learning_date,
                    "slot": slot,
                    "reason": reason,
                },
                now=timestamp,
            )
            return self.repository.list_daily_carryovers(
                conn,
                family_id=family_id,
                child_id=child["id"],
                target_date=learning_date,
            )
        return existing

    def _today_payload(
        self,
        conn,
        *,
        family_id: str,
        child,
        learning_date: str,
        tasks: list,
    ) -> dict:
        subjects = self._subjects_for_date(child, learning_date)
        tasks_by_slot = {
            str(task.get("learning_slot") or "core"): task for task in tasks
        }
        carryovers = self.repository.list_daily_carryovers(
            conn,
            family_id=family_id,
            child_id=child["id"],
            target_date=learning_date,
        )
        carryover_by_slot = {
            str(item.get("carryover_target_slot") or "core"): item
            for item in carryovers
        }
        tasks_by_slot.update(carryover_by_slot)
        used_course_ids: set[str] = set()
        used_subjects: set[str] = set()
        items: list[dict] = []
        for slot in LEARNING_SLOTS:
            task = tasks_by_slot.get(slot)
            display_course = None
            session = None
            if task is not None:
                display_course = self.repository.get_course(
                    conn,
                    course_id=task["learning_course_id"],
                    version=task["learning_course_version"],
                )
                if (
                    display_course is not None
                    and not self._course_is_assignable(conn, child, display_course)
                ):
                    display_course = None
                    task = None
                if task is not None:
                    session = self.repository.get_session_for_task(
                        conn,
                        family_id=family_id,
                        task_id=task["id"],
                    )
                    used_course_ids.add(str(task["learning_course_id"]))
                if display_course is not None:
                    used_subjects.add(str(display_course["subject"]))
            if display_course is None:
                display_course = self._course_for_child(
                    conn,
                    family_id=family_id,
                    child=child,
                    learning_date=learning_date,
                    subject=subjects[slot],
                    excluding_course_ids=tuple(used_course_ids),
                    excluding_subjects=tuple(used_subjects),
                    allow_missing=True,
                )
                if display_course is None:
                    continue
                used_course_ids.add(str(display_course["id"]))
                used_subjects.add(str(display_course["subject"]))

            mastery = self.repository.get_mastery_state(
                conn,
                family_id=family_id,
                child_id=child["id"],
                node_code=display_course["node_code"],
                subject=display_course["subject"],
                grade_code=display_course["grade_code"],
            )
            if task is None:
                state = "recommended"
            elif session is None:
                state = "scheduled"
            elif session["status"] == "completed":
                state = "completed"
            else:
                state = "in_progress"
            actual_subject = str(display_course["subject"])
            item_report = None
            if session is not None and session["status"] == "completed":
                item_report = self.repository.get_report_for_session(
                    conn,
                    family_id=family_id,
                    session_id=session["id"],
                )
            if item_report is None:
                item_report = self.repository.latest_report(
                    conn,
                    family_id=family_id,
                    child_id=child["id"],
                    subject=actual_subject,
                )
            recommendation = recommendation_payload(display_course)
            if not self.static_catalog_enabled and display_course['grade_code'] != 'primary_1':
                selection = selection_payload(display_course, mastery,
                    review_fallback=bool(display_course.get('_difficulty_review_fallback')))
                recommendation['difficultySelection'] = selection
                if selection['message']:
                    recommendation['intro'] = selection['message']
            items.append(
                {
                    "slot": slot,
                    "preferredSubject": subjects[slot],
                    "subject": actual_subject,
                    "subjectFallback": actual_subject != subjects[slot],
                    "state": state,
                    "recommendation": recommendation,
                    "task": learning_task_payload(task),
                    "session": (
                        session_payload(
                            session,
                            questions=self._questions(display_course),
                        )
                        if session
                        else None
                    ),
                    "latestReport": report_payload(item_report),
                    "mastery": mastery_payload(mastery),
                    "dayBucket": (
                        "carryover" if slot in carryover_by_slot else "today"
                    ),
                    "originDate": (
                        str(task.get("scheduled_date") or learning_date)
                        if task is not None
                        else learning_date
                    ),
                    "carryover": (
                        {
                            "id": carryover_by_slot[slot]["carryover_id"],
                            "reason": carryover_by_slot[slot][
                                "carryover_reason"
                            ],
                            "originDate": carryover_by_slot[slot][
                                "carryover_origin_date"
                            ],
                            "targetDate": learning_date,
                            "daysOverdue": max(
                                1,
                                (
                                    date.fromisoformat(learning_date)
                                    - date.fromisoformat(
                                        str(
                                            carryover_by_slot[slot][
                                                "carryover_origin_date"
                                            ]
                                        )
                                    )
                                ).days,
                            ),
                        }
                        if slot in carryover_by_slot
                        else None
                    ),
                }
            )

        selected = items[0] if items else None
        displayed_carryover_count = sum(
            1 for item in items if item.get("dayBucket") == "carryover"
        )
        result = {
            "ok": True,
            "date": learning_date,
            "childId": child["id"],
            "items": items,
            "itemCount": len(items),
            "completedCount": sum(
                1 for item in items if item["state"] == "completed"
            ),
            "carryoverCount": displayed_carryover_count,
            "newCount": len(items) - displayed_carryover_count,
            "backlogCount": self.repository.count_learning_backlog(
                conn,
                family_id=family_id,
                child_id=child["id"],
                before_date=learning_date,
            ),
        }
        result.update(self._catalog_status_payload(conn, child))
        if selected is not None:
            # Compatibility fields for existing clients mirror the first slot.
            result.update(
                {
                    "state": selected["state"],
                    "recommendation": selected["recommendation"],
                    "task": selected["task"],
                    "session": selected["session"],
                    "latestReport": selected["latestReport"],
                    "mastery": selected["mastery"],
                }
            )
        return result

    def _subjects_for_date(self, child, learning_date: str) -> dict[str, str]:
        self._primary_grade_code(child)
        school_year = child.get("grade_school_year_start")
        try:
            anchor_year = int(school_year)
        except (TypeError, ValueError):
            anchor_year = date.fromisoformat(learning_date).year
        anchor = date(anchor_year, 9, 1)
        index = (date.fromisoformat(learning_date) - anchor).days % len(
            PRIMARY_14_DAY_SUBJECT_MATRIX
        )
        core_subject, rotation_subject = PRIMARY_14_DAY_SUBJECT_MATRIX[index]
        extension_subject = next(
            subject
            for subject in SUBJECT_LABELS
            if subject not in {core_subject, rotation_subject}
        )
        return {
            "core": core_subject,
            "rotation": rotation_subject,
            "extension": extension_subject,
        }

    def _catalog_status_payload(self, conn, child) -> dict[str, object]:
        grade_code = self._primary_grade_code(child)
        if self.static_catalog_enabled:
            count = self.repository.count_published_grade_courses(
                conn,
                grade_code=grade_code,
            )
            return {
                "catalogStatus": "complete",
                "availableCourseCount": count,
                "targetCourseCount": count,
            }
        result = self.repository.student_catalog_summary(
            conn,
            family_id=str(child["family_id"]),
            child_id=str(child["id"]),
            grade_code=grade_code,
            grade_selection_revision=int(
                child.get("grade_selection_revision") or 0
            ),
        )

        if self.course_library_enabled:
            from services.course_library_service import cached_supply_summary
            supply = cached_supply_summary(self.repository.database.database_url, grade_code=grade_code)
            if supply is not None:
                result["courseSupply"] = supply
        from services.learning_availability_state import personal_learning_state
        identity = {"family_id": str(child["family_id"]), "child_id": str(child["id"]), "grade_code": grade_code}
        state = personal_learning_state(
            grade_code=grade_code,
            courses=self.repository.personal_visible_course_inventory(conn, **identity,
                grade_selection_revision=int(child.get("grade_selection_revision") or 0)),
            mastery=self.repository.personal_grade_mastery(conn, **identity),
            supply=result.get("courseSupply"), grade_open=grade_code in FORMAL_STUDENT_GRADE_CODES,
        )
        result["learningState"] = state
        result["availableCourseCount"] = state["availableCourseCount"]
        if state["availabilityStatus"] in {"scope_completed", "empty", "not_open"}:
            result["catalogStatus"] = "complete"
            result["preparationProgressPercent"] = None
        return result

    def _teaching_flow_requires_correct_answer(
        self,
        course,
        *,
        question_id: str,
    ) -> bool:
        """Keep verified guided/independent practice open until it is correct."""

        content = self.repository.parse_json(course.get("content_json"), {})
        flow = content.get("teachingFlow") if isinstance(content, dict) else None
        if (
            not isinstance(flow, dict)
            or flow.get("schemaVersion") != "mira.learning.teaching-flow.v1"
        ):
            return False
        guided_ids = flow.get("guidedQuestionIds")
        independent_ids = flow.get("independentQuestionIds")
        if not isinstance(guided_ids, list) or not isinstance(independent_ids, list):
            return False
        practice_ids = {
            str(item)
            for item in [*guided_ids, *independent_ids]
        }
        return question_id in practice_ids

    @staticmethod
    def _slot_start(slot: str, requested_start: str | None) -> str:
        if requested_start is None:
            return DEFAULT_SLOT_STARTS[slot]
        if slot == "core":
            return requested_start
        hours, minutes = (int(part) for part in requested_start.split(":"))
        slot_offset = LEARNING_SLOTS.index(slot) * 15
        total_minutes = hours * 60 + minutes + slot_offset
        if total_minutes >= 24 * 60:
            return requested_start
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    @staticmethod
    def _primary_grade_code(child) -> str:
        grade_code = str(child.get("grade_code") or "").strip()
        if grade_code not in {f"primary_{grade}" for grade in range(1, 7)}:
            raise ApiError(
                "learning_not_available_for_grade",
                "当前可用课程覆盖小学一至六年级",
                409,
            )
        return grade_code

    def _ensure_catalog(self) -> None:
        if self._catalog_ready:
            return
        self._catalog_ready = True

    def _ensure_dynamic_supply(self, *, child, learning_date: str) -> None:
        """Verify today's skills exist in the active, package-ready catalog.

        Student traffic never triggers OpenMAIC generation. Catalog builds run
        through the internal batch API/CLI and publish atomically.
        """

        if self.static_catalog_enabled:
            return
        grade_code = self._primary_grade_code(child)
        subjects = tuple(
            dict.fromkeys(self._subjects_for_date(child, learning_date).values())
        )
        with ThreadPoolExecutor(
            max_workers=len(subjects),
            thread_name_prefix="learning-dynamic-supply",
        ) as executor:
            failures = [
                failure
                for failure in executor.map(
                    lambda subject: self._ensure_dynamic_subject_supply(
                        child=child,
                        learning_date=learning_date,
                        grade_code=grade_code,
                        subject=subject,
                    ),
                    subjects,
                )
                if failure is not None
            ]
        if failures:
            first = failures[0]
            raise ApiError(
                str(first.get("error") or "learning_generation_failed"),
                "当前课程目录尚未完成发布，请稍后重试",
                503,
            )

    def _ensure_dynamic_subject_supply(
        self,
        *,
        child,
        learning_date: str,
        grade_code: str,
        subject: str,
    ) -> dict | None:
        with self.repository.transaction() as conn:
            desired_node_code = self._next_skill_node_for_child(
                conn,
                child=child,
                subject=subject,
            )
            today_tasks = self.repository.get_today_tasks(
                conn,
                family_id=child["family_id"],
                child_id=child["id"],
                learning_date=learning_date,
            )
            already_assigned = False
            immutable_assignment = False
            for task in today_tasks:
                course = self.repository.get_course(
                    conn,
                    course_id=task["learning_course_id"],
                    version=task["learning_course_version"],
                )
                if course is None or str(course.get("subject")) != subject:
                    continue
                is_expected_course = (
                    str(course.get("node_code")) == desired_node_code
                    and str(course.get("content_origin") or "")
                    in self._scheduled_content_origins()
                    and self._course_has_teaching_flow(course)
                    and self._course_is_assignable(conn, child, course)
                )
                if is_expected_course:
                    already_assigned = True
                    break
                if not self._task_can_replace_course(conn, task):
                    immutable_assignment = True
                    break
            available = self.repository.count_unassigned_published_courses(
                conn,
                family_id=child["family_id"],
                child_id=child["id"],
                grade_code=grade_code,
                subject=subject,
                node_code=desired_node_code,
                content_origins=self._scheduled_content_origins(),
                require_teaching_flow=not self.static_catalog_enabled,
                require_catalog_release=True,
                curriculum_version=PRIMARY_CURRICULUM_VERSION,
                boundary_version=self._boundary_for_node(
                    grade_code=grade_code,
                    subject=subject,
                    node_code=desired_node_code,
                ).boundary_version,
            )
        if already_assigned or immutable_assignment:
            return None
        if available < 1:
            return {
                "error": "learning_catalog_not_ready",
                "message": "当前能力边界还没有完成课程发布",
            }
        return None

    def _next_skill_node_for_child(self, conn, *, child, subject: str) -> str:
        grade_code = self._primary_grade_code(child)
        progression = boundaries_for(grade_code, subject)
        if not progression:
            raise ApiError(
                "learning_skill_boundary_not_found",
                "当前年级科目的能力边界不存在",
                404,
            )
        completed_states = []
        for sequence, boundary in enumerate(progression):
            mastery = self.repository.get_mastery_state(
                conn,
                family_id=child["family_id"],
                child_id=child["id"],
                node_code=boundary.skill_id,
                subject=subject,
                grade_code=grade_code,
            )
            if mastery is None or str(mastery.get("mastery_level")) != "mastered":
                return boundary.skill_id
            completed_states.append((sequence, boundary, mastery))

        _, boundary, _ = min(
            completed_states,
            key=lambda item: (
                str(item[2].get("next_review_date") or "9999-12-31"),
                int(item[2].get("last_practiced_at") or 0),
                item[0],
            ),
        )
        return boundary.skill_id

    def _task_can_replace_course(self, conn, task) -> bool:
        if str(task.get("status")) not in {
            "scheduled",
            "pending",
            "reminder_sent",
            "delayed",
        }:
            return False
        return (
            self.repository.get_session_for_task(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
            )
            is None
        )

    def _scheduled_content_origins(self) -> tuple[str, ...]:
        return () if self.static_catalog_enabled else ("openmaic_generated",)

    def _child_for_formal_student_write(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        formal_student_child_id: str | None,
    ):
        child = self._lock_formal_student_child(
            conn,
            family_id=family_id,
            child_id=child_id,
            formal_student_child_id=formal_student_child_id,
        )
        self._assert_formal_student_release_for_locked_child(
            conn,
            child=child,
            formal_student_child_id=formal_student_child_id,
        )
        return child

    def _lock_formal_student_child(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        formal_student_child_id: str | None,
    ):
        if formal_student_child_id is None:
            return self._child_or_error(
                conn,
                family_id,
                child_id,
                for_update=True,
            )
        if child_id != formal_student_child_id:
            raise ApiError("child_not_found", "孩子资料不存在", 404)
        return self._child_or_error(
            conn,
            family_id,
            child_id,
            for_update=True,
        )

    def _assert_formal_student_release_for_locked_child(
        self,
        conn,
        *,
        child,
        formal_student_child_id: str | None,
    ) -> None:
        if formal_student_child_id is None:
            return
        checker = self.formal_learning_access_checker
        if checker is not None:
            checker(conn, child, for_update=True)
        assert_formal_student_workspace_open(child)

    def _child_or_error(
        self,
        conn,
        family_id: str,
        child_id: str,
        *,
        for_update: bool = False,
    ):
        child = self.profile_repository.get_child(
            conn,
            family_id=family_id,
            child_id=child_id,
            for_update=for_update,
        )
        if child is None:
            raise ApiError("child_not_found", "孩子资料不存在", 404)
        return child

    def _course_for_child(
        self,
        conn,
        *,
        family_id: str,
        child,
        learning_date: str,
        subject: str,
        excluding_course_ids: tuple[str, ...] = (),
        excluding_subjects: tuple[str, ...] = (),
        allow_missing: bool = False,
    ):
        grade_code = self._primary_grade_code(child)
        excluded_subject_set = {
            str(item).strip() for item in excluding_subjects if str(item).strip()
        }
        available_subjects = [
            item
            for item in self.repository.list_published_subjects(
                conn,
                grade_code=grade_code,
                content_origins=self._scheduled_content_origins(),
                require_teaching_flow=not self.static_catalog_enabled,
                require_catalog_release=not self.static_catalog_enabled,
                family_id=(family_id if not self.static_catalog_enabled else None),
                child_id=(str(child["id"]) if not self.static_catalog_enabled else None),
                student_grade_selection_revision=(
                    int(child.get("grade_selection_revision") or 0)
                    if not self.static_catalog_enabled
                    else None
                ),
                curriculum_version=(
                    PRIMARY_CURRICULUM_VERSION
                    if not self.static_catalog_enabled
                    else None
                ),
            )
            if item in SUBJECT_LABELS and item not in excluded_subject_set
        ]
        subject_candidates = [] if subject in excluded_subject_set else [subject]
        subject_candidates.extend(
            item for item in available_subjects if item not in subject_candidates
        )
        if not self.static_catalog_enabled:
            subject_candidates.extend(
                item
                for item in SUBJECT_LABELS
                if item not in subject_candidates and item in excluded_subject_set
            )
        exclusion_attempts = (
            (excluding_course_ids,)
            if allow_missing or not excluding_course_ids
            else (excluding_course_ids, ())
        )
        for exclusions in exclusion_attempts:
            for candidate in subject_candidates:
                required_node_code = (
                    None
                    if self.static_catalog_enabled
                    else self._next_skill_node_for_child(
                        conn,
                        child=child,
                        subject=candidate,
                    )
                )
                adaptive = not self.static_catalog_enabled and grade_code != 'primary_1'
                mastery_by_node = {}
                if adaptive:
                    progression = boundaries_for(grade_code, candidate)
                    mastery_by_node = {boundary.skill_id: self.repository.get_mastery_state(
                        conn, family_id=family_id, child_id=child['id'], grade_code=grade_code,
                        subject=candidate, node_code=boundary.skill_id) for boundary in progression}
                    node_attempts = available_skill_order(progression, mastery_by_node)
                else:
                    node_attempts = (
                    (required_node_code, None)
                    if required_node_code is not None
                    else (None,)
                    )
                attempts = [(node, False) for node in node_attempts]
                if adaptive:
                    attempts += [(node, True) for node in node_attempts]
                for node_code, review_fallback in attempts:
                    course = self.repository.get_recommended_course(
                        conn,
                        family_id=family_id,
                        child_id=child["id"],
                        grade_code=grade_code,
                        learning_date=learning_date,
                        subject=candidate,
                        required_node_code=node_code,
                        excluding_course_ids=exclusions,
                        content_origins=self._scheduled_content_origins(),
                        require_teaching_flow=not self.static_catalog_enabled,
                        require_catalog_release=not self.static_catalog_enabled,
                        require_formal_pointer=not self.static_catalog_enabled,
                        student_grade_selection_revision=(
                            int(child.get("grade_selection_revision") or 0)
                            if not self.static_catalog_enabled
                            else None
                        ),
                        curriculum_version=(
                            PRIMARY_CURRICULUM_VERSION
                            if not self.static_catalog_enabled
                            else None
                        ),
                        boundary_version=(
                            self._boundary_for_node(
                                grade_code=grade_code,
                                subject=candidate,
                                node_code=str(node_code),
                            ).boundary_version
                            if node_code
                            else None
                        ),
                        **({'difficulty_code': None if review_fallback else preferred_difficulty(mastery_by_node.get(node_code)),
                            'require_completed': review_fallback} if adaptive else {}),
                    )
                    if course is not None:
                        if adaptive and review_fallback:
                            course = {**course, '_difficulty_review_fallback': True}
                        return course
            if not excluding_course_ids:
                break
        if allow_missing:
            return None
        raise ApiError("published_course_not_found", "当前年级暂无已发布课程", 404)

    @staticmethod
    def _boundary_for_node(*, grade_code: str, subject: str, node_code: str):
        for boundary in boundaries_for(grade_code, subject):
            if boundary.skill_id == node_code:
                return boundary
        raise ApiError(
            "learning_skill_boundary_not_found",
            "当前年级科目的能力边界不存在",
            404,
        )

    def _course_is_assignable(self, conn, child, course) -> bool:
        if self.static_catalog_enabled:
            return str(course.get("status") or "") == "published"
        try:
            boundary = self._boundary_for_node(
                grade_code=str(course.get("grade_code") or ""),
                subject=str(course.get("subject") or ""),
                node_code=str(course.get("node_code") or ""),
            )
        except ApiError:
            return False
        formal_course = self.repository.get_student_visible_course(
            conn,
            family_id=str(child["family_id"]),
            child_id=str(child["id"]),
            grade_code=str(course.get("grade_code") or ""),
            grade_selection_revision=int(
                child.get("grade_selection_revision") or 0
            ),
            course_id=str(course.get("id") or ""),
            course_version=str(course.get("version") or ""),
        )
        return bool(
            formal_course is not None
            and str(formal_course.get("curriculum_version") or "")
            == boundary.curriculum_version
            and str(formal_course.get("boundary_version") or "")
            == boundary.boundary_version
        )

    def _questions(self, course) -> list[dict]:
        content = self.repository.parse_json(course.get("content_json"), {})
        questions = content.get("questions") if isinstance(content, dict) else None
        if not isinstance(questions, list) or not questions:
            raise ApiError("invalid_course_content", "课程内容暂时不可用", 503)
        flow = content.get("teachingFlow")
        if isinstance(flow, dict) and flow.get("schemaVersion") == (
            "mira.learning.teaching-flow.v1"
        ):
            ids = [
                *flow.get("guidedQuestionIds", []),
                *flow.get("independentQuestionIds", []),
            ]
            by_id = {
                str(question.get("id") or ""): question
                for question in questions
                if isinstance(question, dict)
            }
            if (
                len(ids) != 4
                or len(set(str(item) for item in ids)) != 4
                or any(str(item) not in by_id for item in ids)
            ):
                raise ApiError("invalid_course_content", "课程教学流程暂时不可用", 503)
            return [by_id[str(question_id)] for question_id in ids]
        return questions

    def _course_has_teaching_flow(self, course) -> bool:
        content = self.repository.parse_json(course.get("content_json"), {})
        if not isinstance(content, dict):
            return False
        flow = content.get("teachingFlow")
        questions = content.get("questions")
        if not isinstance(flow, dict) or not isinstance(questions, list):
            return False
        question_ids = [
            str(question.get("id") or "")
            for question in questions
            if isinstance(question, dict)
        ]
        referenced = [
            str(flow.get("demoQuestionId") or ""),
            *[str(item) for item in flow.get("guidedQuestionIds") or []],
            *[str(item) for item in flow.get("independentQuestionIds") or []],
        ]
        return (
            flow.get("schemaVersion") == "mira.learning.teaching-flow.v1"
            and len(question_ids) == 5
            and referenced == question_ids
            and len(set(referenced)) == 5
        )

    @staticmethod
    def _is_empty_answer(value: object) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, dict)):
            return not value
        return False

    def _learning_date(self, value: object) -> str:
        text = str(value or "").strip() or date.today().isoformat()
        try:
            parsed = date.fromisoformat(text)
        except ValueError as exc:
            raise ApiError("invalid_learning_date", "学习日期格式应为 YYYY-MM-DD") from exc
        return parsed.isoformat()

    def _scheduled_start(self, value: object) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text) is None:
            raise ApiError("invalid_scheduled_start", "开始时间格式应为 HH:MM")
        return text

    @staticmethod
    def _required_text(data: dict, key: str, message: str) -> str:
        value = str(data.get(key) or "").strip()
        if not value:
            raise ApiError(f"missing_{key}", message)
        return value
