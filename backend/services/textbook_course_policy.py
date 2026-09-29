"""Textbook scope gate shared by direct course and task/session entry paths."""
from content.textbook_catalog import digest, validate_frozen_brief
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository


def assert_textbook_course(conn, *, child, course, required=False):
    content = TextbookRepository.parse(course.get("content_json"))
    if not isinstance(content, dict) or "textbookBinding" not in content:
        if required:
            raise textbook_library_required()
        return False
    repo = TextbookRepository(None)
    build = repo.course_build(conn, course["id"], course["version"])
    if build is None:
        raise ApiError("textbook_course_unavailable", "这节教材课还未完成审核", 409)
    row = repo.get_revision(conn, build["edition_id"], build["revision_id"])
    if row is None:
        raise ApiError("textbook_course_unavailable", "这版教材已停止提供新课", 409)
    manifest = repo.manifest(row)
    brief = validate_frozen_brief(manifest, repo.parse(build["input_json"]))
    if (digest(manifest) != row["manifest_sha256"] or content["textbookBinding"] != brief["textbookBinding"]
            or brief["contentKey"] != build["content_key"] or digest(content) != build["course_content_sha256"]
            or brief["textbookBinding"]["nodeId"] != build["node_id"] or brief["textbookBinding"]["partIndex"] != build["part_index"]
            or child["grade_code"] != manifest["gradeCode"] or course["subject"] != manifest["subject"]):
        raise ApiError("textbook_course_unavailable", "课程与教材版本不一致，请刷新目录", 409)
    from services.textbook_learning_service import textbook_context
    context = textbook_context(repo, conn, child)
    year, semester = context['schoolYearStartYear'], context['semester']
    choices = repo.selections(conn, child, year, semester)
    if not any(r["edition_id"] == build["edition_id"] and r["revision_id"] == build["revision_id"] for r in choices):
        raise ApiError("textbook_selection_changed", "学校教材已变化，请从教材目录重新选课", 409)
    return True


def textbook_library_required():
    return ApiError("student_textbook_library_required", "请从教材课程库选择已准备好的课程", 409)


def require_published_textbook_course(conn, *, family_id, child_id, course_id, course_version):
    """Read-only gate for student links and existing runtime credentials."""
    repo = TextbookRepository(None)
    child = repo.child(conn, family_id, child_id)
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=? "
                          "AND status='published' AND quality_status='released' AND retired_at IS NULL",
                          (course_id, course_version)).fetchone()
    if child is None or course is None:
        raise ApiError("learning_course_not_found", "课程暂时不可用，请返回教材目录", 404)
    assert_textbook_course(conn, child=child, course=course, required=True)
