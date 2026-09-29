"""Keep old bookmarks/API clients from reviving student-driven course supply."""
from flask import current_app, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import student_textbook_access_service


def enforce_textbook_delivery():
    if request.method == "OPTIONS" or not current_app.config.get("LEARNING_TEXTBOOK_LIBRARY_ONLY", True):
        return None
    try:
        endpoint = (request.endpoint or "").rsplit(".", 1)[-1]
        access = student_textbook_access_service()
        token = bearer_token(request)
        args = request.view_args or {}
        if request.blueprint == "student_practice_v2":
            access.require_library(token)
        elif endpoint in {"teachers", "set_teacher_preference"}:
            return None  # Preferences do not supply or generate courses.
        elif "course_id" in args:
            access.authorize(token, course_id=args["course_id"],
                             course_version=args.get("course_version") or request.args.get("version"))
        elif "session_id" in args:
            access.authorize(token, session_id=args["session_id"])
        elif endpoint == "start_session":
            access.authorize(token, task_id=str(json_body(request).get("taskId") or ""))
        else:
            # Today, assignment, legacy library/path/placement/reports are retired
            # from the student surface. Fail before invoking their domain service.
            access.require_library(token)
    except ApiError as exc:
        return error_response(exc)
    return None
