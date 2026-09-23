"""Textbook scope gate shared by direct course and task/session entry paths."""
from content.textbook_catalog import digest, validate_frozen_brief
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository


def assert_textbook_course(conn, *, child, course):
    content = TextbookRepository.parse(course.get("content_json"))
    if not isinstance(content, dict) or "textbookBinding" not in content:
        return
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
    from services.textbook_learning_service import school_term
    year, semester = school_term()
    choices = repo.selections(conn, child, year, semester)
    if not any(r["edition_id"] == build["edition_id"] and r["revision_id"] == build["revision_id"] for r in choices):
        raise ApiError("textbook_selection_changed", "学校教材已变化，请从教材目录重新选课", 409)
