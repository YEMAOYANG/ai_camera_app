from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class TaskTemplateRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def child_grade(self, conn: DatabaseConnection, *, family_id: str, child_id: str) -> str | None:
        row = conn.execute(
            """
            SELECT grade_code, grade, age_stage
            FROM children
            WHERE family_id = ? AND id = ?
            """,
            (family_id, child_id),
        ).fetchone()
        if row is None:
            return None
        return (
            row.get("grade_code")
            or row.get("grade")
            or row.get("age_stage")
            or ""
        ).strip() or None

    def child_exists(self, conn: DatabaseConnection, *, family_id: str, child_id: str) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def list_templates(
        self,
        conn: DatabaseConnection,
        *,
        grade: str | None = None,
        day_type: str | None = None,
        tag: str | None = None,
        include_rows: bool = True,
    ) -> list[tuple[DatabaseRow, list[DatabaseRow]]]:
        clauses = ["status = 'active'"]
        values: list[str] = []
        if grade:
            clauses.append("grade = ?")
            values.append(grade)
        if day_type:
            clauses.append("day_type = ?")
            values.append(day_type)
        if tag:
            clauses.append("tags_json LIKE ?")
            values.append(f'%"{tag}"%')

        templates = list(
            conn.execute(
                f"""
                SELECT *
                FROM task_templates
                WHERE {' AND '.join(clauses)}
                ORDER BY grade, sort_order, template_key
                """,
                values,
            ).fetchall()
        )
        if not include_rows:
            return [(template, []) for template in templates]

        template_ids = [str(template["id"]) for template in templates]
        items_by_template = self.list_template_items(conn, template_ids=template_ids)
        return [
            (template, items_by_template.get(str(template["id"]), []))
            for template in templates
        ]

    def list_template_items(
        self,
        conn: DatabaseConnection,
        *,
        template_ids: list[str],
    ) -> dict[str, list[DatabaseRow]]:
        if not template_ids:
            return {}
        placeholders = ", ".join(["?"] * len(template_ids))
        rows = list(
            conn.execute(
                f"""
                SELECT *
                FROM task_template_items
                WHERE template_id IN ({placeholders})
                ORDER BY template_id, sort_order, start_time
                """,
                template_ids,
            ).fetchall()
        )
        grouped: dict[str, list[DatabaseRow]] = {}
        for row in rows:
            grouped.setdefault(str(row["template_id"]), []).append(row)
        return grouped
