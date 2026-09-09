from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from core.database import Database
from core.errors import ApiError
from repositories.learning_repository import LearningRepository
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from repositories.student_learning_library_repository import (
    StudentLearningLibraryRepository,
)
from services.learning_service import LearningService
from services.lesson_runtime_service import LessonRuntimeService
from services.learning_media_materialization_service import (
    LearningMediaMaterializationError,
)
from services.learning_teacher_library_service import (
    LearningTeacherLibraryService,
)
from services.student_auth_service import StudentAuthService


class _StudentLearningAuthAdapter:
    """Expose a student principal through LearningService's legacy auth shape."""

    def __init__(self, student_auth_service: StudentAuthService):
        self.student_auth_service = student_auth_service
        self._bound_context: ContextVar[dict | None] = ContextVar(
            "student_learning_auth_context",
            default=None,
        )

    @contextmanager
    def bind(self, context: dict) -> Iterator[None]:
        token = self._bound_context.set(context)
        try:
            yield
        finally:
            self._bound_context.reset(token)

    def authenticate(self, access_token: str) -> dict:
        context = self._bound_context.get()
        if context is None:
            context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        return {
            "family": {"id": principal["family_id"]},
            "user": {"id": f"student:{principal['id']}"},
            "student": context["student"],
        }


class StudentLearningService:
    """Bind the existing learning domain to exactly one student child."""

    def __init__(
        self,
        database_url: str | Path,
        *,
        student_auth_service: StudentAuthService,
        static_catalog_enabled: bool = True,
        dynamic_generation_service: Any | None = None,
        dynamic_pool_target: int = 1,
        lesson_runtime_service: LessonRuntimeService | None = None,
        teacher_library_service: LearningTeacherLibraryService | None = None,
        classroom_student_release_enabled: bool = False,
        course_library_enabled: bool = False,
    ):
        self.student_auth_service = student_auth_service
        self.repository = LearningRepository(Database(database_url))
        self.library_repository = StudentLearningLibraryRepository(
            Database(database_url)
        )
        self.lesson_runtime_service = lesson_runtime_service
        self.static_catalog_enabled = bool(static_catalog_enabled)
        self.teacher_library_service = teacher_library_service or (
            LearningTeacherLibraryService(
                LearningTeacherMediaRepository(Database(database_url))
            )
        )
        self.classroom_student_release_enabled = bool(
            classroom_student_release_enabled
        )
        self._auth_adapter = _StudentLearningAuthAdapter(student_auth_service)
        self.learning_service = LearningService(
            database_url,
            auth_service=self._auth_adapter,
            course_library_enabled=course_library_enabled,
            static_catalog_enabled=static_catalog_enabled,
            dynamic_generation_service=dynamic_generation_service,
            dynamic_pool_target=dynamic_pool_target,
            formal_learning_access_checker=(
                self.student_auth_service._assert_formal_learning_access
            ),
        )

    def today(self, access_token: str, query: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        forced_query = dict(query or {})
        forced_query["childId"] = context["principal"]["child_id"]
        with self._auth_adapter.bind(context):
            return self.learning_service.today(
                access_token,
                forced_query,
                formal_student_child_id=context["principal"]["child_id"],
            )

    def assign_today(self, access_token: str, data: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        forced_data = dict(data or {})
        forced_data["childId"] = context["principal"]["child_id"]
        with self._auth_adapter.bind(context):
            return self.learning_service.assign_today(
                access_token,
                forced_data,
                formal_student_child_id=context["principal"]["child_id"],
            )

    def start_session(self, access_token: str, data: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        self._assert_task_belongs_to_student(
            family_id=principal["family_id"],
            child_id=principal["child_id"],
            task_id=str((data or {}).get("taskId") or "").strip(),
        )
        atomic_binder = None
        if self.classroom_student_release_enabled and self.lesson_runtime_service:

            def bind_classroom(conn, start_payload):
                classroom_payload = (
                    self.lesson_runtime_service.attach_classroom_in_transaction(
                        conn,
                        family_id=principal["family_id"],
                        child_id=principal["child_id"],
                        start_payload=start_payload,
                    )
                )
                session = classroom_payload.get("session")
                session_id = (
                    str(session.get("id") or "")
                    if isinstance(session, dict)
                    else ""
                )
                if self.lesson_runtime_service.has_formal_runtime_binding_in_transaction(
                    conn,
                    family_id=principal["family_id"],
                    child_id=principal["child_id"],
                    learning_session_id=session_id,
                ):
                    return classroom_payload
                if not isinstance(
                    classroom_payload.get("classroom"), dict
                ) or not isinstance(classroom_payload.get("package"), dict):
                    raise ApiError(
                        "learning_classroom_preparing",
                        "这节课还在完成课件与声音制作，请稍后再来",
                        409,
                    )
                return classroom_payload

            atomic_binder = bind_classroom

        with self._auth_adapter.bind(context):
            return self.learning_service.start_session(
                access_token,
                dict(data or {}),
                formal_student_child_id=principal["child_id"],
                atomic_session_binder=atomic_binder,
            )

    def answer(
        self,
        access_token: str,
        session_id: str,
        data: dict,
    ) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        self._assert_session_belongs_to_student(
            family_id=principal["family_id"],
            child_id=principal["child_id"],
            session_id=session_id,
        )
        with self._auth_adapter.bind(context):
            return self.learning_service.answer(
                access_token,
                session_id,
                dict(data or {}),
                formal_student_child_id=principal["child_id"],
            )

    def latest_report(self, access_token: str, query: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        forced_query = dict(query or {})
        forced_query["childId"] = context["principal"]["child_id"]
        with self._auth_adapter.bind(context):
            return self.learning_service.latest_report(access_token, forced_query)

    def library(self, access_token: str, query: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        bucket = str((query or {}).get("bucket") or "all").strip().lower()
        if bucket not in {"all", "continue", "makeup", "completed", "favorites"}:
            raise ApiError(
                "invalid_learning_library_bucket",
                "不支持的课程筛选方式",
                400,
            )
        subject = str((query or {}).get("subject") or "").strip().lower() or None
        if subject is not None and subject not in {"chinese", "math", "english"}:
            raise ApiError("invalid_learning_subject", "不支持的学科", 400)
        try:
            limit = int((query or {}).get("limit") or 20)
        except (TypeError, ValueError) as exc:
            raise ApiError("invalid_learning_library_limit", "分页数量无效", 400) from exc
        if limit < 1 or limit > 50:
            raise ApiError("invalid_learning_library_limit", "分页数量须为 1 到 50", 400)
        try:
            cursor = self.library_repository.decode_cursor(
                (query or {}).get("cursor")
            )
        except ValueError as exc:
            raise ApiError("invalid_learning_library_cursor", "分页位置无效", 400) from exc
        with self.library_repository.transaction() as conn:
            items, next_cursor = self.library_repository.list_library(
                conn,
                family_id=principal["family_id"],
                child_id=principal["child_id"],
                bucket=bucket,
                subject=subject,
                before_date=date.today().isoformat(),
                cursor=cursor,
                limit=limit,
            )
            continue_item = self.library_repository.get_continue_item(
                conn,
                family_id=principal["family_id"],
                child_id=principal["child_id"],
            )
            child = self.learning_service.profile_repository.get_child(
                conn,
                family_id=principal["family_id"],
                child_id=principal["child_id"],
            )
            if child is None:
                raise ApiError("child_not_found", "孩子资料不存在", 404)
            catalog = self.learning_service._catalog_status_payload(conn, child)
            if not self.static_catalog_enabled and bucket in {"all", "favorites"}:
                visible_courses = self.repository.list_student_visible_courses(
                    conn,
                    family_id=principal["family_id"],
                    child_id=principal["child_id"],
                    grade_code=str(child["grade_code"]),
                    grade_selection_revision=int(
                        child.get("grade_selection_revision") or 0
                    ),
                    subject=subject,
                    favorite_only=bucket == "favorites",
                    limit=50,
                )
                merged = {
                    (str(item["course"]["id"]), str(item["course"]["version"])): item
                    for item in (
                        self._catalog_library_item(course) for course in visible_courses
                    )
                }
                for item in items:
                    merged[
                        (str(item["course"]["id"]), str(item["course"]["version"]))
                    ] = item
                items = sorted(
                    merged.values(),
                    key=lambda item: (
                        int(item.get("lastActivityAt") or 0),
                        str(item["course"]["id"]),
                    ),
                    reverse=True,
                )[:limit]
        return {
            "ok": True,
            "bucket": bucket,
            "subject": subject,
            "continueItem": continue_item,
            "items": items,
            "nextCursor": next_cursor,
            **catalog,
        }

    def course_detail(
        self,
        access_token: str,
        course_id: str,
        query: dict,
    ) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        normalized_course_id = str(course_id or "").strip()
        version = str((query or {}).get("version") or "").strip() or None
        if not normalized_course_id:
            raise ApiError("learning_course_not_found", "课程不存在", 404)
        with self.library_repository.transaction() as conn:
            item = self.library_repository.get_course_detail(
                conn,
                family_id=principal["family_id"],
                child_id=principal["child_id"],
                course_id=normalized_course_id,
                course_version=version,
            )
            if not self.static_catalog_enabled:
                child = self.learning_service.profile_repository.get_child(
                    conn,
                    family_id=principal["family_id"],
                    child_id=principal["child_id"],
                )
                visible = (
                    self.repository.get_student_visible_course(
                        conn,
                        family_id=principal["family_id"],
                        child_id=principal["child_id"],
                        grade_code=str((child or {}).get("grade_code") or ""),
                        grade_selection_revision=int(
                            (child or {}).get("grade_selection_revision") or 0
                        ),
                        course_id=normalized_course_id,
                        course_version=(
                            version
                            or str((item or {}).get("course", {}).get("version") or "")
                        ),
                    )
                    if child is not None
                    else None
                )
                if visible is None:
                    item = None
                elif item is None:
                    item = self._catalog_library_item(visible, include_intro=True)
        if item is None:
            raise ApiError("learning_course_not_found", "课程不存在", 404)
        return {"ok": True, "item": item}

    def set_course_favorite(
        self,
        access_token: str,
        course_id: str,
        course_version: str,
        *,
        favorite: bool,
    ) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        normalized_course_id = str(course_id or "").strip()
        normalized_version = str(course_version or "").strip()
        if not normalized_course_id or not normalized_version:
            raise ApiError("learning_course_not_found", "课程不存在", 404)
        from core.security import now_ms

        with self.library_repository.transaction() as conn:
            allow_unassigned = False
            if not self.static_catalog_enabled:
                child = self.learning_service.profile_repository.get_child(
                    conn,
                    family_id=principal["family_id"],
                    child_id=principal["child_id"],
                )
                allow_unassigned = bool(
                    child is not None
                    and self.repository.get_student_visible_course(
                        conn,
                        family_id=principal["family_id"],
                        child_id=principal["child_id"],
                        grade_code=str(child["grade_code"]),
                        grade_selection_revision=int(
                            child.get("grade_selection_revision") or 0
                        ),
                        course_id=normalized_course_id,
                        course_version=normalized_version,
                    )
                    is not None
                )
            updated = self.library_repository.set_favorite(
                conn,
                family_id=principal["family_id"],
                child_id=principal["child_id"],
                course_id=normalized_course_id,
                course_version=normalized_version,
                favorite=favorite,
                now=now_ms(),
                allow_unassigned=allow_unassigned,
            )
        if not updated:
            raise ApiError("learning_course_not_found", "课程不存在", 404)
        return {
            "ok": True,
            "courseId": normalized_course_id,
            "courseVersion": normalized_version,
            "favorite": bool(favorite),
        }

    def teachers(self, access_token: str, query: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        subject = str((query or {}).get("subject") or "").strip().lower() or None
        try:
            payload = self.teacher_library_service.list_teachers(
                subject=subject,
                family_id=principal["family_id"] if subject else None,
                child_id=principal["child_id"] if subject else None,
            )
        except LearningMediaMaterializationError as exc:
            raise self._teacher_api_error(exc) from exc
        return {"ok": True, **payload}

    def set_teacher_preference(self, access_token: str, data: dict) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        subject = str((data or {}).get("subject") or "").strip().lower()
        profile_id = str((data or {}).get("teacherProfileId") or "").strip()
        raw_version = (data or {}).get("teacherProfileVersion")
        try:
            profile_version = int(raw_version) if raw_version is not None else None
        except (TypeError, ValueError) as exc:
            raise ApiError(
                "invalid_teacher_profile_version",
                "教师版本无效",
                400,
            ) from exc
        if profile_version is not None and profile_version < 1:
            raise ApiError(
                "invalid_teacher_profile_version",
                "教师版本无效",
                400,
            )
        try:
            preference = self.teacher_library_service.set_teacher_preference(
                family_id=principal["family_id"],
                child_id=principal["child_id"],
                subject=subject,
                teacher_profile_id=profile_id,
                teacher_profile_version=profile_version,
                updated_by_user_id=f"student:{principal['id']}",
            )
        except LearningMediaMaterializationError as exc:
            raise self._teacher_api_error(exc) from exc
        return {"ok": True, **preference}

    def classroom_runtime(self, access_token: str, session_id: str) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        if (
            not self.classroom_student_release_enabled
            or self.lesson_runtime_service is None
        ):
            raise ApiError(
                "learning_classroom_not_available",
                "本次学习暂时没有互动课堂",
                404,
            )
        principal = context["principal"]
        return self.lesson_runtime_service.runtime(
            family_id=principal["family_id"],
            child_id=principal["child_id"],
            session_id=session_id,
        )

    def complete_classroom_action(
        self,
        access_token: str,
        session_id: str,
        action_id: str,
        data: dict,
    ) -> dict:
        context = self.student_auth_service.authenticate(access_token)
        if (
            not self.classroom_student_release_enabled
            or self.lesson_runtime_service is None
        ):
            raise ApiError(
                "learning_classroom_not_available",
                "本次学习暂时没有互动课堂",
                404,
            )
        principal = context["principal"]
        return self.lesson_runtime_service.complete_action(
            family_id=principal["family_id"],
            child_id=principal["child_id"],
            session_id=session_id,
            action_id=action_id,
            data=dict(data or {}),
        )

    @staticmethod
    def _catalog_library_item(
        course,
        *,
        include_intro: bool = False,
    ) -> dict:
        content = LearningRepository.parse_json(course.get("content_json"), {})
        if not isinstance(content, dict):
            content = {}
        questions = content.get("questions")
        subject = str(course.get("subject") or "")
        public_course = {
            "id": str(course["id"]),
            "version": str(course["version"]),
            "gradeCode": str(course["grade_code"]),
            "subject": subject,
            "subjectLabel": {
                "chinese": "语文",
                "math": "数学",
                "english": "英语",
            }.get(subject, subject),
            "nodeCode": str(course["node_code"]),
            "title": str(course["title"]),
            "objective": str(course["objective"]),
            "estimatedMinutes": int(content.get("estimatedMinutes") or 10),
            "questionCount": len(questions) if isinstance(questions, list) else 0,
        }
        if include_intro:
            public_course["intro"] = str(content.get("intro") or "")
        published_at = int(course.get("published_at") or 0)
        return {
            "taskId": None,
            "taskStatus": "available",
            "learningDate": str(course.get("last_learning_date") or date.today()),
            "scheduledStart": None,
            "slot": "catalog",
            "course": public_course,
            "session": None,
            "report": None,
            "favorite": course.get("favorite_course_id") is not None,
            "classroomAvailable": True,
            "packageClassroomAvailable": True,
            "fullClassroomAvailable": True,
            "lastActivityAt": int(
                course.get("last_task_activity_at") or published_at
            ),
        }

    def _assert_task_belongs_to_student(
        self,
        *,
        family_id: str,
        child_id: str,
        task_id: str,
    ) -> None:
        if not task_id:
            return
        with self.repository.transaction() as conn:
            task = self.repository.get_task(
                conn,
                family_id=family_id,
                task_id=task_id,
            )
        if task is not None and task["child_id"] != child_id:
            raise ApiError("task_not_found", "学习任务不存在", 404)

    def _assert_session_belongs_to_student(
        self,
        *,
        family_id: str,
        child_id: str,
        session_id: str,
    ) -> None:
        with self.repository.transaction() as conn:
            session = self.repository.get_session(
                conn,
                family_id=family_id,
                session_id=session_id,
            )
        if session is not None and session["child_id"] != child_id:
            raise ApiError(
                "learning_session_not_found",
                "学习记录不存在",
                404,
            )

    @staticmethod
    def _teacher_api_error(error: LearningMediaMaterializationError) -> ApiError:
        status_by_code = {
            "teacher_profile_not_found": 404,
            "child_not_found": 404,
            "invalid_subject": 400,
            "teacher_subject_mismatch": 400,
            "invalid_teacher_preference_scope": 400,
        }
        message_by_code = {
            "teacher_profile_not_found": "教师暂时不可用",
            "child_not_found": "孩子资料不存在",
            "invalid_subject": "不支持的学科",
            "teacher_subject_mismatch": "这位老师不教授所选学科",
            "invalid_teacher_preference_scope": "教师选择范围无效",
        }
        return ApiError(
            error.code,
            message_by_code.get(error.code, "教师设置暂时不可用"),
            status_by_code.get(error.code, 503),
        )
