"""Student delivery boundary: only shared, reviewed textbook courses may open.

No generators, preparation services or personal course allocation are called here.
Existing task/session ownership and the downstream runtime/media gates still apply.
"""
from core.errors import ApiError
from services.textbook_course_policy import require_published_textbook_course, textbook_library_required


class StudentTextbookAccessService:
    def __init__(self, database, *, student_auth_service):
        self.database = database
        self.student_auth_service = student_auth_service

    def require_library(self, token):
        self.student_auth_service.authenticate(token)
        raise textbook_library_required()

    def authorize(self, token, *, course_id=None, course_version=None, task_id=None, session_id=None):
        principal = self.student_auth_service.authenticate(token)["principal"]
        family_id, child_id = principal["family_id"], principal["child_id"]
        with self.database.transaction() as conn:
            if task_id is not None:
                row = conn.execute("SELECT learning_course_id AS course_id, learning_course_version AS course_version "
                                   "FROM tasks WHERE id=? AND family_id=? AND child_id=? AND type='learning'",
                                   (task_id, family_id, child_id)).fetchone()
                if row is None:
                    raise ApiError("task_not_found", "学习任务不存在", 404)
                course_id, course_version = row["course_id"], row["course_version"]
            elif session_id is not None:
                row = conn.execute("SELECT course_id, course_version FROM learning_sessions "
                                   "WHERE id=? AND family_id=? AND child_id=?",
                                   (session_id, family_id, child_id)).fetchone()
                if row is None:
                    raise ApiError("learning_session_not_found", "学习记录不存在", 404)
                course_id, course_version = row["course_id"], row["course_version"]
            if not course_id or not course_version:
                raise textbook_library_required()
            require_published_textbook_course(conn, family_id=family_id, child_id=child_id,
                                             course_id=course_id, course_version=course_version)
