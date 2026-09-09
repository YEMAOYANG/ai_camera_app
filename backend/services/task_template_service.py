from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.errors import ApiError
from repositories.task_template_repository import TaskTemplateRepository
from schemas.education import grade_definition_from_legacy
from schemas.task_templates import (
    normalize_template_day_type,
    normalize_template_tag,
    template_catalog_payload,
)
from services.auth_service import AuthService


class TaskTemplateService:
    def __init__(self, database_url: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        self.repository = TaskTemplateRepository(Database(database_url))

    def list_templates(self, access_token: str, query: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        child_id = self._optional_text(query, "childId")
        requested_grade_value = self._optional_text(query, "grade")
        requested_grade = (
            grade_definition_from_legacy(requested_grade_value)
            if requested_grade_value
            else None
        )
        day_type = normalize_template_day_type(self._optional_text(query, "dayType"))
        tag = normalize_template_tag(self._optional_text(query, "tag"))
        include_rows = self._bool_param(query.get("includeRows"), default=True)

        with self.repository.transaction() as conn:
            child_grade = None
            if child_id:
                if not self.repository.child_exists(
                    conn,
                    family_id=context["family"]["id"],
                    child_id=child_id,
                ):
                    raise ApiError("child_not_found", "孩子资料不存在", 404)
                stored_grade = self.repository.child_grade(
                    conn,
                    family_id=context["family"]["id"],
                    child_id=child_id,
                )
                child_grade = grade_definition_from_legacy(stored_grade, strict=False)
                if child_grade is None:
                    raise ApiError(
                        "grade_selection_required",
                        "请先选择孩子 9 月开学后的年级",
                        409,
                    )

            if requested_grade and child_grade and requested_grade.code != child_grade.code:
                raise ApiError("grade_conflict", "筛选年级与孩子年级不一致")

            selected_grade = requested_grade or child_grade
            if selected_grade and selected_grade.kindergarten_template_grade is None:
                return template_catalog_payload(
                    [],
                    recommended_grade=None,
                    requested_grade_code=selected_grade.code,
                    requested_grade_label=selected_grade.label,
                    content_mode=selected_grade.content_mode,
                    content_unavailable=True,
                    content_message=(
                        "当前不会套用幼儿园任务。"
                        "小学课程通过质量校验后会在这里开放。"
                    ),
                )

            template_grade = (
                selected_grade.kindergarten_template_grade
                if selected_grade
                else None
            )
            templates = self.repository.list_templates(
                conn,
                grade=template_grade,
                day_type=day_type,
                tag=tag,
                include_rows=include_rows,
            )
            return template_catalog_payload(
                templates,
                recommended_grade=template_grade or "small",
                requested_grade_code=selected_grade.code if selected_grade else "",
                requested_grade_label=selected_grade.label if selected_grade else "",
                content_mode=(
                    selected_grade.content_mode
                    if selected_grade
                    else "kindergarten_growth"
                ),
                content_unavailable=False,
            )

    def _optional_text(self, data: dict, key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _bool_param(self, value: object, *, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() not in {"0", "false", "no", "off"}
