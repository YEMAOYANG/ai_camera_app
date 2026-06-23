from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.errors import ApiError
from repositories.task_template_repository import TaskTemplateRepository
from schemas.task_templates import (
    normalize_template_day_type,
    normalize_template_grade,
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
        requested_grade = normalize_template_grade(self._optional_text(query, "grade"))
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
                child_grade = self._optional_child_grade(
                    self.repository.child_grade(
                        conn,
                        family_id=context["family"]["id"],
                        child_id=child_id,
                    )
                )

            grade = requested_grade or child_grade
            templates = self.repository.list_templates(
                conn,
                grade=grade,
                day_type=day_type,
                tag=tag,
                include_rows=include_rows,
            )
            return template_catalog_payload(
                templates,
                recommended_grade=grade or child_grade or "small",
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

    def _optional_child_grade(self, value: str | None) -> str | None:
        try:
            return normalize_template_grade(value)
        except ApiError:
            return None
