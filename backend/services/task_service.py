from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.points import LEDGER_TASK_COMPLETED
from models.tasks import TASK_AWAITING_PARENT_CONFIRMATION, TASK_CONFIRMED
from repositories.point_repository import PointRepository
from repositories.task_repository import TaskRepository
from schemas.tasks import task_payload, validate_task_status, validate_task_type
from services.auth_service import AuthService
from services.point_service import PointService


class TaskService:
    def __init__(self, database_url: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        database = Database(database_url)
        self.repository = TaskRepository(database)
        self.point_repository = PointRepository(database)
        self.point_service = PointService(database_url, auth_service=auth_service)

    def list_today(self, access_token: str, query: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._optional_text(query, "childId")
        scheduled_date = self._optional_text(query, "date") or date.today().isoformat()
        with self.repository.transaction() as conn:
            if child_id:
                self._ensure_child(conn, context["family"]["id"], child_id)
            rows = self.repository.list_tasks(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                scheduled_date=scheduled_date,
            )
            return {
                "ok": True,
                "date": scheduled_date,
                "tasks": [task_payload(row) for row in rows],
            }

    def list_tasks(self, access_token: str, query: dict) -> dict:
        context = self._auth_context(access_token)
        child_id = self._optional_text(query, "childId")
        status = self._optional_text(query, "status")
        scheduled_date = self._optional_text(query, "date")
        start_date = self._optional_text(query, "startDate")
        end_date = self._optional_text(query, "endDate")
        if status:
            validate_task_status(status)
        with self.repository.transaction() as conn:
            if child_id:
                self._ensure_child(conn, context["family"]["id"], child_id)
            rows = self.repository.list_tasks(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                scheduled_date=scheduled_date,
                start_date=start_date,
                end_date=end_date,
                status=status,
            )
            return {"ok": True, "tasks": [task_payload(row) for row in rows]}

    def get_task(self, access_token: str, task_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            return {"ok": True, "task": task_payload(task)}

    def create_task(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            task = self._create_task_from_data(conn, context, data)
            return {"ok": True, "task": task_payload(task)}

    def create_tasks_batch(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        batch_date = self._optional_text(data, "date")
        items = data.get("tasks")
        if not isinstance(items, list) or not items:
            raise ApiError("missing_tasks", "请先添加至少一个任务")
        if len(items) > 30:
            raise ApiError("too_many_tasks", "一次最多添加 30 个任务")

        with self.repository.transaction() as conn:
            created = []
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ApiError("invalid_task_item", f"第 {index + 1} 项任务不完整")
                item_data = dict(item)
                if batch_date and not (
                    item_data.get("scheduledDate")
                    or item_data.get("startAt")
                    or item_data.get("dueAt")
                ):
                    item_data["scheduledDate"] = batch_date
                try:
                    task = self._create_task_from_data(conn, context, item_data)
                except ApiError as exc:
                    raise ApiError(
                        exc.code,
                        f"第 {index + 1} 项：{exc.message}",
                        exc.status_code,
                    ) from exc
                created.append(task_payload(task))
            return {"ok": True, "tasks": created}

    def _create_task_from_data(self, conn, context: dict, data: dict):
        child_id = self._required_text(data, "childId", "缺少孩子 ID")
        title = self._required_text(data, "title", "请输入任务标题")
        task_type = validate_task_type(
            self._optional_text(data, "taskType")
            or self._optional_text(data, "type")
            or "learning"
        )
        start_at = self._optional_text(data, "startAt")
        due_at = self._optional_text(data, "dueAt")
        scheduled_date = (
            self._optional_text(data, "scheduledDate")
            or self._date_part(start_at)
            or self._date_part(due_at)
            or date.today().isoformat()
        )
        scheduled_start = self._optional_text(data, "scheduledStart") or self._time_part(start_at)
        scheduled_end = self._optional_text(data, "scheduledEnd") or self._time_part(due_at)
        reward_points = self._non_negative_int(data.get("rewardPoints", 0), "rewardPoints")
        priority = self._priority(data.get("priority", 3))
        now = now_ms()
        self._ensure_child(conn, context["family"]["id"], child_id)
        return self.repository.create_task(
            conn,
            family_id=context["family"]["id"],
            child_id=child_id,
            title=title,
            description=self._optional_text(data, "description"),
            task_type=task_type,
            scheduled_date=scheduled_date,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            schedule_type=self._optional_text(data, "scheduleType") or "one_time",
            start_at=start_at,
            due_at=due_at,
            repeat_rule=self._json_text(data.get("repeatRule")),
            priority=priority,
            reward_points=reward_points,
            requires_parent_confirmation=bool(data.get("requiresParentConfirmation", True)),
            ai_observation_summary=self._optional_text(data, "aiObservationSummary"),
            created_by=context["user"]["id"],
            now=now,
        )

    def update_task(self, access_token: str, task_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        mapping = {
            "title": "title",
            "description": "description",
            "type": "type",
            "taskType": "type",
            "status": "status",
            "scheduleType": "schedule_type",
            "startAt": "start_at",
            "dueAt": "due_at",
            "repeatRule": "repeat_rule",
            "priority": "priority",
            "scheduledDate": "scheduled_date",
            "scheduledStart": "scheduled_start",
            "scheduledEnd": "scheduled_end",
            "rewardPoints": "reward_points",
            "requiresParentConfirmation": "requires_parent_confirmation",
            "aiObservationSummary": "ai_observation_summary",
        }
        for key, column in mapping.items():
            if key not in data:
                continue
            if key in ("type", "taskType"):
                fields[column] = validate_task_type(str(data[key]))
            elif key == "status":
                fields[column] = validate_task_status(str(data[key]))
            elif key == "rewardPoints":
                fields[column] = self._non_negative_int(data[key], key)
            elif key == "requiresParentConfirmation":
                fields[column] = int(bool(data[key]))
            elif key == "repeatRule":
                fields[column] = self._json_text(data.get(key))
            elif key == "priority":
                fields[column] = self._priority(data.get(key))
            else:
                fields[column] = self._optional_text(data, key)
        if "startAt" in data and "scheduledDate" not in data:
            start_date = self._date_part(self._optional_text(data, "startAt"))
            if start_date:
                fields["scheduled_date"] = start_date
        if "startAt" in data and "scheduledStart" not in data:
            start_time = self._time_part(self._optional_text(data, "startAt"))
            if start_time:
                fields["scheduled_start"] = start_time
        if "dueAt" in data and "scheduledEnd" not in data:
            due_time = self._time_part(self._optional_text(data, "dueAt"))
            if due_time:
                fields["scheduled_end"] = due_time
        now = now_ms()
        with self.repository.transaction() as conn:
            self._task_or_error(conn, context["family"]["id"], task_id)
            task = self.repository.update_task(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "task": task_payload(task)}

    def complete_task(self, access_token: str, task_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            evidence_summary = self._optional_text(data, "evidenceSummary")
            evidence = self._json_text(data.get("evidence"))
            ai_summary = self._optional_text(data, "aiObservationSummary") or evidence_summary
            task = self.repository.mark_completed(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                evidence_summary=evidence_summary,
                completion_source=self._optional_text(data, "completionSource") or "parent",
                evidence=evidence,
                ai_observation_summary=ai_summary,
                requires_parent_confirmation=bool(task["requires_parent_confirmation"]),
                now=now,
            )
            return {"ok": True, "task": task_payload(task)}

    def parent_confirm(self, access_token: str, task_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            if task["status"] not in (TASK_AWAITING_PARENT_CONFIRMATION, TASK_CONFIRMED):
                raise ApiError("task_not_awaiting_confirmation", "任务还不能确认")

            ledger_payload = None
            if not task["points_granted_at"] and task["reward_points"] > 0:
                ledger = self.point_service.apply_delta(
                    conn,
                    family_id=context["family"]["id"],
                    child_id=task["child_id"],
                    delta=task["reward_points"],
                    ledger_type=LEDGER_TASK_COMPLETED,
                    source_type="task",
                    source_id=task["id"],
                    note=f"任务确认奖励：{task['title']}",
                    now=now,
                )
                ledger_payload = {
                    "id": ledger["id"],
                    "delta": ledger["delta"],
                    "balanceAfter": ledger["balance_after"],
                    "type": ledger["type"],
                }
                self.repository.mark_points_granted(
                    conn,
                    family_id=context["family"]["id"],
                    task_id=task_id,
                    now=now,
                )

            task = self.repository.mark_confirmed(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                now=now,
            )
            payload = {"ok": True, "task": task_payload(task)}
            if ledger_payload:
                payload["ledgerEntry"] = ledger_payload
            return payload

    def reject_confirmation(self, access_token: str, task_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            if task["status"] != TASK_AWAITING_PARENT_CONFIRMATION:
                raise ApiError("task_not_awaiting_confirmation", "任务还不能驳回")
            task = self.repository.mark_rejected(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                reason=self._optional_text(data, "reason"),
                now=now,
            )
            return {"ok": True, "task": task_payload(task)}

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _task_or_error(self, conn, family_id: str, task_id: str):
        task = self.repository.get_task(conn, family_id=family_id, task_id=task_id)
        if task is None:
            raise ApiError("task_not_found", "任务不存在", 404)
        return task

    def _ensure_child(self, conn, family_id: str, child_id: str) -> None:
        if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
            raise ApiError("child_not_found", "孩子资料不存在", 404)

    def _required_text(self, data: dict, key: str, message: str) -> str:
        value = self._optional_text(data, key)
        if not value:
            raise ApiError(f"missing_{key}", message)
        return value

    def _optional_text(self, data: dict, key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _non_negative_int(self, value, key: str) -> int:
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ApiError(f"invalid_{key}", "数值必须是整数") from exc
        if result < 0:
            raise ApiError(f"invalid_{key}", "数值不能小于 0")
        return result

    def _priority(self, value) -> int:
        result = self._non_negative_int(value, "priority")
        if result < 1:
            return 1
        if result > 5:
            return 5
        return result

    def _json_text(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip() or None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _date_part(self, value: str | None) -> str | None:
        if not value or len(value) < 10:
            return None
        return value[:10]

    def _time_part(self, value: str | None) -> str | None:
        if not value or "T" not in value:
            return None
        time_part = value.split("T", 1)[1]
        return time_part[:5] if len(time_part) >= 5 else None
