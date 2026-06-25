from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Callable

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.points import LEDGER_TASK_COMPLETED
from models.tasks import (
    TASK_ACTIVE_SCHEDULED_STATUSES,
    TASK_AWAITING_PARENT_CONFIRMATION,
    TASK_CONFIRMED,
    TASK_DELAYED,
    TASK_EXPIRED,
    TASK_IN_PROGRESS,
    TASK_MISSED,
)
from repositories.point_repository import PointRepository
from repositories.profile_repository import ProfileRepository
from repositories.task_repository import TaskRepository
from schemas.profile import role_capabilities_from_option
from schemas.tasks import task_event_payload, task_payload, validate_task_status, validate_task_type
from services.auth_service import AuthService
from services.ai_text_provider import AiTextProvider, UnavailableAiTextProvider
from services.camera_command_service import CameraCommandService
from services.point_service import PointService
from services.prompt_registry import PromptRegistry
from services.setting_policy import setting_value
from services.task_reminder_policy import build_task_reminder, normalize_task_reminder_phase


FALLBACK_ROLE_CAPABILITIES = {
    "admin": {"manage_tasks", "confirm_tasks"},
    "guardian": {"manage_tasks", "confirm_tasks"},
    "viewer": set(),
}


class TaskService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        camera_command_service: CameraCommandService | None = None,
        camera_command_service_factory: Callable[[], CameraCommandService] | None = None,
        ai_text_provider: AiTextProvider | None = None,
        prompt_registry: PromptRegistry | None = None,
    ):
        self.auth_service = auth_service
        database = Database(database_url)
        self.repository = TaskRepository(database)
        self.point_repository = PointRepository(database)
        self.profile_repository = ProfileRepository(database)
        self._camera_command_service = camera_command_service
        self._camera_command_service_factory = camera_command_service_factory
        self.ai_text_provider = ai_text_provider or UnavailableAiTextProvider()
        self.prompt_registry = prompt_registry
        self._task_reminder_prompt_cache: str | None = None
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

    def current_in_progress(
        self,
        access_token: str,
        *,
        device_id: str | None = None,
        include_unassigned: bool = False,
    ) -> dict | None:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            # Tasks created before multi-camera selection may not have device_id.
            # Treat those legacy tasks as belonging to the explicit default camera only.
            rows = self.repository.list_in_progress_tasks(
                conn,
                family_id=context["family"]["id"],
                scheduled_date=date.today().isoformat(),
                device_id=device_id,
                include_unassigned=include_unassigned,
            )
            return task_payload(rows[0]) if rows else None

    def create_task(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_tasks")
            task = self._create_task_from_data(conn, context, data)
            self._add_event(
                conn,
                task,
                "task_created",
                "任务已创建",
                {"source": "parent"},
                now_ms(),
            )
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
            self._assert_capability(conn, context, "manage_tasks")
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
                self._add_event(
                    conn,
                    task,
                    "task_created",
                    "任务已创建",
                    {"source": "parent_batch", "row": index + 1},
                    now_ms(),
                )
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
        )
        if not scheduled_date:
            raise ApiError("missing_scheduled_date", "请选择任务日期")
        scheduled_start = self._optional_text(data, "scheduledStart") or self._time_part(start_at)
        scheduled_end = self._optional_text(data, "scheduledEnd") or self._time_part(due_at)
        reward_points = self._non_negative_int(data.get("rewardPoints", 0), "rewardPoints")
        reminder_minutes_before = self._non_negative_int(
            data.get("reminderMinutesBefore", 5),
            "reminderMinutesBefore",
        )
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
            reminder_minutes_before=reminder_minutes_before,
            device_id=self._optional_text(data, "deviceId"),
            timezone=self._optional_text(data, "timezone") or "Asia/Shanghai",
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
            "reminderMinutesBefore": "reminder_minutes_before",
            "deviceId": "device_id",
            "timezone": "timezone",
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
            elif key == "reminderMinutesBefore":
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
            self._assert_capability(conn, context, "manage_tasks")
            self._task_or_error(conn, context["family"]["id"], task_id)
            task = self.repository.update_task(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                fields=fields,
                now=now,
            )
            self._add_event(
                conn,
                task,
                "task_updated",
                "任务已更新",
                {"fields": list(fields.keys())},
                now,
            )
            return {"ok": True, "task": task_payload(task)}

    def start_task(self, access_token: str, task_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_tasks")
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            if task["status"] not in (
                *TASK_ACTIVE_SCHEDULED_STATUSES,
                TASK_IN_PROGRESS,
                TASK_DELAYED,
            ):
                raise ApiError("task_cannot_start", "这个任务暂时不能开始")
            task = self.repository.mark_in_progress(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                observation_status="parent_started",
                now=now,
            )
            self._add_event(conn, task, "manual_started", "任务已开始", {"source": "parent"}, now)
            return {"ok": True, "task": task_payload(task)}

    def send_reminder(self, access_token: str, task_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        phase = normalize_task_reminder_phase(
            self._optional_text(data, "phase"),
            default="follow_up",
        )
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_tasks")
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            child = self.profile_repository.get_child(
                conn,
                family_id=context["family"]["id"],
                child_id=task["child_id"],
            )
            reminder = build_task_reminder(
                task,
                phase=phase,
                child=child,
                ai_text_provider=self.ai_text_provider,
                prompt=self._task_reminder_prompt(),
            )
            voice_enabled = self._voice_reminder_enabled(conn, context["family"]["id"])
            has_camera_device = (
                self._has_camera_device(
                    family_id=context["family"]["id"],
                    device_id=task.get("device_id"),
                )
                if voice_enabled
                else False
            )
            command = (
                self.camera_command_service.internal_speak(
                    family_id=context["family"]["id"],
                    task_id=task["id"],
                    device_id=task.get("device_id"),
                    text=reminder["text"],
                )
                if voice_enabled and has_camera_device
                else self._skipped_command(
                    "voice_reminder_disabled" if not voice_enabled else "no_camera_device"
                )
            )
            sent = command.get("status") != "failed" and command.get("status") != "skipped"
            event_type = (
                self._manual_reminder_event_type(phase, sent=sent)
                if voice_enabled and has_camera_device
                else self._manual_reminder_event_type(phase, skipped=True)
            )
            self._add_event(
                conn,
                task,
                event_type,
                self._manual_reminder_message(
                    phase,
                    sent=sent,
                    skipped=not voice_enabled or not has_camera_device,
                    skip_reason=command.get("reason"),
                ),
                {"command": command, **reminder},
                now,
            )
            refreshed = self._task_or_error(conn, context["family"]["id"], task_id)
            return {
                "ok": True,
                "task": task_payload(refreshed),
                "command": command,
                "reminder": reminder,
            }

    def list_task_events(self, access_token: str, task_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._task_or_error(conn, context["family"]["id"], task_id)
            rows = self.repository.list_events(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
            )
            return {"ok": True, "events": [task_event_payload(row) for row in rows]}

    def complete_task(self, access_token: str, task_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "confirm_tasks")
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            evidence_summary = self._optional_text(data, "evidenceSummary")
            evidence = self._json_text(data.get("evidence"))
            ai_summary = self._optional_text(data, "aiObservationSummary") or evidence_summary
            completion_source = self._optional_text(data, "completionSource") or "parent"
            if completion_source not in {"parent", "parent_manual", "camera"}:
                completion_source = "parent"
            manual_parent_completion = completion_source == "parent_manual"
            task = self.repository.mark_completed(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                evidence_summary=evidence_summary,
                completion_source=completion_source,
                evidence=evidence,
                ai_observation_summary=ai_summary,
                requires_parent_confirmation=(
                    bool(task["requires_parent_confirmation"])
                    and not manual_parent_completion
                ),
                now=now,
            )
            self._add_event(
                conn,
                task,
                "task_completed",
                "家长手动记录完成，未发放积分" if manual_parent_completion else "任务已完成",
                {
                    "completionSource": completion_source,
                    "pointsGranted": not manual_parent_completion,
                },
                now,
            )
            ledger_payload = None
            if task["status"] == "completed" and not manual_parent_completion:
                ledger_payload = self._grant_task_points_if_needed(conn, context, task, now)
                if ledger_payload:
                    self._add_event(conn, task, "points_awarded", "奖励积分已发放", ledger_payload, now)
                else:
                    self._add_event(conn, task, "points_award_skipped", "没有重复发放积分", {}, now)
                task = self._task_or_error(conn, context["family"]["id"], task_id)
            payload = {"ok": True, "task": task_payload(task)}
            if ledger_payload:
                payload["ledgerEntry"] = ledger_payload
            return payload

    def acknowledge_missed_task(self, access_token: str, task_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "confirm_tasks")
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            if task["status"] not in (TASK_MISSED, TASK_EXPIRED):
                raise ApiError("task_not_missed", "这项安排还不能这样处理")
            if not self.repository.has_event(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                event_type="missed_acknowledged",
            ):
                self._add_event(
                    conn,
                    task,
                    "missed_acknowledged",
                    "已选择不处理",
                    {"source": "parent"},
                    now,
                )
            refreshed = self._task_or_error(conn, context["family"]["id"], task_id)
            return {"ok": True, "task": task_payload(refreshed)}

    def parent_confirm(self, access_token: str, task_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "confirm_tasks")
            task = self._task_or_error(conn, context["family"]["id"], task_id)
            if task["status"] not in (TASK_AWAITING_PARENT_CONFIRMATION, TASK_CONFIRMED):
                raise ApiError("task_not_awaiting_confirmation", "任务还不能确认")

            ledger_payload = self._grant_task_points_if_needed(conn, context, task, now)

            task = self.repository.mark_confirmed(
                conn,
                family_id=context["family"]["id"],
                task_id=task_id,
                now=now,
            )
            self._add_event(conn, task, "parent_confirmed", "家长已确认完成情况", {}, now)
            payload = {"ok": True, "task": task_payload(task)}
            if ledger_payload:
                payload["ledgerEntry"] = ledger_payload
            return payload

    def reject_confirmation(self, access_token: str, task_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "confirm_tasks")
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
            self._add_event(
                conn,
                task,
                "parent_rejected",
                "家长已驳回完成确认",
                {"reason": self._optional_text(data, "reason")},
                now,
            )
            self._add_event(
                conn,
                task,
                "points_award_skipped",
                "本次任务未发放积分",
                {"reason": "parent_rejected"},
                now,
            )
            return {"ok": True, "task": task_payload(task)}

    def _grant_task_points_if_needed(
        self,
        conn,
        context: dict,
        task,
        now: int,
    ) -> dict | None:
        if task["points_granted_at"] or task["reward_points"] <= 0:
            return None
        if not self.repository.mark_points_granted_once(
            conn,
            family_id=context["family"]["id"],
            task_id=task["id"],
            now=now,
        ):
            return None
        ledger = self.point_service.apply_delta(
            conn,
            family_id=context["family"]["id"],
            child_id=task["child_id"],
            delta=task["reward_points"],
            ledger_type=LEDGER_TASK_COMPLETED,
            source_type="task",
            source_id=task["id"],
            note=f"任务完成奖励：{task['title']}",
            now=now,
        )
        return {
            "id": ledger["id"],
            "delta": ledger["delta"],
            "balanceAfter": ledger["balance_after"],
            "type": ledger["type"],
        }

    def _add_event(
        self,
        conn,
        task,
        event_type: str,
        message: str,
        payload: dict | None,
        now: int,
    ) -> None:
        if not task:
            return
        self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type=event_type,
            message=message,
            payload=payload,
            now=now,
        )

    def _manual_reminder_event_type(
        self,
        phase: str,
        *,
        sent: bool = False,
        skipped: bool = False,
    ) -> str:
        suffix = "skipped" if skipped else "sent" if sent else "failed"
        return {
            "prepare": f"manual_prepare_reminder_{suffix}",
            "start": f"manual_start_reminder_{suffix}",
            "follow_up": f"manual_reminder_{suffix}",
            "delay": f"manual_reminder_{suffix}",
            "wrap_up": f"wrap_up_reminder_{suffix}",
            "finish": f"manual_finish_reminder_{suffix}",
        }.get(phase, f"manual_reminder_{suffix}")

    def _manual_reminder_message(
        self,
        phase: str,
        *,
        sent: bool,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> str:
        if skipped:
            if skip_reason == "no_camera_device":
                return "未连接摄像头，本次只记录安排。"
            return "语音提醒已关闭，未向摄像头播报"
        if not sent:
            return "摄像头暂时离线，提醒没有播出"
        return {
            "prepare": "已提醒孩子准备",
            "start": "已提醒孩子开始",
            "follow_up": "已提醒孩子",
            "delay": "已提醒孩子",
            "wrap_up": "已提醒孩子收尾",
            "finish": "已提醒孩子结束",
        }.get(phase, "已提醒孩子")

    def _voice_reminder_enabled(self, conn, family_id: str) -> bool:
        row = self.profile_repository.get_setting(conn, family_id=family_id, key="ai-care-rules")
        return setting_value(row, "ai-care-rules").get("voiceReminderEnabled") is True

    def _task_reminder_prompt(self) -> str:
        if self._task_reminder_prompt_cache is not None:
            return self._task_reminder_prompt_cache
        if self.prompt_registry is None:
            self._task_reminder_prompt_cache = ""
            return ""
        prompt = self.prompt_registry.get_prompt("task.reminder.voice", "v1")
        self._task_reminder_prompt_cache = prompt.body if prompt else ""
        return self._task_reminder_prompt_cache

    def _skipped_command(self, reason: str) -> dict:
        return {"status": "skipped", "reason": reason}

    def _has_camera_device(self, *, family_id: str, device_id: str | None = None) -> bool:
        if not hasattr(self.camera_command_service, "has_available_device"):
            return True
        return bool(
            self.camera_command_service.has_available_device(
                family_id=family_id,
                device_id=device_id,
            )
        )

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    @property
    def camera_command_service(self) -> CameraCommandService:
        if self._camera_command_service is None:
            if self._camera_command_service_factory is None:
                raise ApiError("camera_command_not_configured", "摄像头提醒暂时不可用", 503)
            self._camera_command_service = self._camera_command_service_factory()
        return self._camera_command_service

    def _task_or_error(self, conn, family_id: str, task_id: str):
        task = self.repository.get_task(conn, family_id=family_id, task_id=task_id)
        if task is None:
            raise ApiError("task_not_found", "任务不存在", 404)
        return task

    def _ensure_child(self, conn, family_id: str, child_id: str) -> None:
        if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
            raise ApiError("child_not_found", "孩子资料不存在", 404)

    def _assert_capability(self, conn, context: dict, capability: str) -> None:
        member = self.profile_repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            member = self.profile_repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=context["user"]["id"],
                name=context["user"].get("displayName") or "家长",
                phone=context["user"].get("phone") or "",
                now=now_ms(),
            )
        role = member["role"]
        row = self.profile_repository.get_app_option_item(
            conn,
            catalog_key="family_role",
            item_key=role,
        )
        capabilities = set(role_capabilities_from_option(row)) or FALLBACK_ROLE_CAPABILITIES.get(
            role,
            set(),
        )
        if capability not in capabilities:
            raise ApiError("permission_denied", "当前身份不能进行此操作", 403)

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
