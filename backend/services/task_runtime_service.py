from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.database import Database
from core.security import now_ms
from models.points import LEDGER_TASK_COMPLETED
from models.tasks import (
    TASK_ACTIVE_SCHEDULED_STATUSES,
    TASK_DELAYED,
    TASK_IN_PROGRESS,
)
from repositories.point_repository import PointRepository
from repositories.profile_repository import ProfileRepository
from repositories.task_repository import TaskRepository
from schemas.tasks import task_event_payload, task_payload
from services.camera_command_service import CameraCommandService
from services.task_reminder_policy import build_task_reminder


TASK_TYPES_REQUIRING_START_OBSERVATION = {
    "learning",
    "reading_interest",
}


class TaskRuntimeService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        camera_command_service: CameraCommandService,
        reminder_lead_seconds: int = 300,
        delay_reminder_interval_seconds: int = 180,
        max_delay_reminders: int = 3,
        monitor_enabled: bool = True,
        speaker_enabled: bool = True,
    ):
        database = Database(database_url)
        self.repository = TaskRepository(database)
        self.point_repository = PointRepository(database)
        self.profile_repository = ProfileRepository(database)
        self.camera_command_service = camera_command_service
        self.reminder_lead_seconds = max(0, int(reminder_lead_seconds))
        self.delay_reminder_interval_seconds = max(30, int(delay_reminder_interval_seconds))
        self.max_delay_reminders = max(0, int(max_delay_reminders))
        self.monitor_enabled = monitor_enabled
        self.speaker_enabled = speaker_enabled

    def tick(self, *, now: datetime | None = None) -> dict:
        now = now or datetime.now().astimezone()
        date_text = now.date().isoformat()
        changed: list[dict] = []
        events: list[dict] = []
        with self.repository.transaction() as conn:
            tasks = self.repository.list_scheduler_tasks(conn, end_date=date_text)
            for task in tasks:
                before_status = task["status"]
                updated, task_events = self._advance_task(conn, task, now=now)
                if updated is not None and updated["status"] != before_status:
                    changed.append(task_payload(updated))
                events.extend(task_event_payload(event) for event in task_events)
        return {
            "ok": True,
            "checkedAt": self._now_ms(now),
            "changedTasks": changed,
            "events": events,
        }

    def _advance_task(self, conn, task, *, now: datetime):
        start_at = self._task_datetime(task, "start")
        due_at = self._task_datetime(task, "due")
        if start_at is None and due_at is None:
            return task, []

        if self._is_history_task(task, now):
            return self._catch_up_history(conn, task, due_at=due_at, now=now)

        if due_at is not None and self._is_due(now, due_at):
            if task["status"] in TASK_ACTIVE_SCHEDULED_STATUSES:
                return self._mark_missed(conn, task, now=now, reason="任务时间已过去，仍未开始。")
            if task["status"] in {TASK_IN_PROGRESS, TASK_DELAYED}:
                return self._auto_finish(conn, task, now=now)
            return task, []

        if task["status"] in TASK_ACTIVE_SCHEDULED_STATUSES:
            if start_at is not None and self._is_due(now, start_at):
                return self._auto_start_or_delay(conn, task, now=now)
            if start_at is not None and self._in_reminder_window(task, now, start_at):
                updated, event = self._send_reminder(conn, task, now=now)
                return updated or task, [event] if event else []
            return task, []

        if task["status"] == TASK_DELAYED:
            return self._process_delayed(conn, task, now=now)

        return task, []

    def _send_reminder(self, conn, task, *, now: datetime):
        if self.repository.has_event(conn, task_id=task["id"], event_type="reminder_sent") or self.repository.has_event(
            conn,
            task_id=task["id"],
            event_type="reminder_failed",
        ):
            return None, None
        current_ms = self._now_ms(now)
        self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="reminder_due",
            message="任务快开始了，准备提醒孩子。",
            payload={},
            now=current_ms,
        )
        reminder = self._task_reminder(conn, task, phase="prepare")
        text = reminder["text"]
        command = None
        sent = False
        if self.speaker_enabled:
            command = self.camera_command_service.internal_speak(
                family_id=task["family_id"],
                task_id=task["id"],
                device_id=task.get("device_id"),
                text=text,
            )
            sent = command.get("status") != "failed"
        updated = self.repository.mark_reminder_result(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            sent=sent,
            now=current_ms,
        )
        event = self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="reminder_sent" if sent else "reminder_failed",
            message="已提醒孩子准备开始" if sent else "摄像头暂时离线，提醒没有播出",
            payload={"command": command, **reminder},
            now=current_ms,
        )
        return updated, event

    def _auto_start_or_delay(self, conn, task, *, now: datetime):
        if self.repository.has_event(conn, task_id=task["id"], event_type="auto_started"):
            return task, []
        if not self._requires_start_observation(task):
            return self._mark_in_progress_without_start_observation(conn, task, now=now)

        observation = self.camera_command_service.camera_service.task_observation(dict(task))
        verdict = observation.get("verdict")
        if verdict == "not_started":
            return self._mark_delayed(conn, task, observation=observation, now=now)

        status = "started" if verdict == "started" else "observation_unavailable"
        current_ms = self._now_ms(now)
        updated = self.repository.mark_in_progress(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            observation_status=status,
            now=current_ms,
        )
        events = [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="auto_started",
                message="任务已自动开始",
                payload={"observation": observation},
                now=current_ms,
            )
        ]
        start_event = self._send_phase_reminder(
            conn,
            updated,
            phase="start",
            now_ms_value=current_ms,
            success_event_type="start_reminder_sent",
            failed_event_type="start_reminder_failed",
            success_message="已提醒孩子开始",
            failed_message="摄像头暂时离线，开始提醒没有播出",
        )
        if start_event:
            events.append(start_event)
        if verdict in {"insufficient", "unavailable"}:
            events.append(
                self.repository.add_event(
                    conn,
                    family_id=task["family_id"],
                    task_id=task["id"],
                    event_type="observation_unavailable",
                    message="暂时没有可靠观察结果，任务仍会按计划记录。",
                    payload={"observation": observation},
                    now=current_ms,
                )
            )
        events.extend(self._start_monitor(conn, task, now_ms_value=current_ms))
        return updated, events

    def _mark_in_progress_without_start_observation(self, conn, task, *, now: datetime):
        current_ms = self._now_ms(now)
        updated = self.repository.mark_in_progress(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            observation_status="not_required",
            now=current_ms,
        )
        events = [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="auto_started",
                message="任务已按时间开始",
                payload={"observation": {"verdict": "not_required", "reason": "task_type"}},
                now=current_ms,
            )
        ]
        start_event = self._send_phase_reminder(
            conn,
            updated,
            phase="start",
            now_ms_value=current_ms,
            success_event_type="start_reminder_sent",
            failed_event_type="start_reminder_failed",
            success_message="已提醒孩子开始",
            failed_message="摄像头暂时离线，开始提醒没有播出",
        )
        if start_event:
            events.append(start_event)
        events.extend(self._start_monitor(conn, task, now_ms_value=current_ms))
        return updated, events

    def _mark_delayed(self, conn, task, *, observation: dict, now: datetime):
        current_ms = self._now_ms(now)
        next_reminder = self._plus_seconds_ms(now, self.delay_reminder_interval_seconds)
        updated = self.repository.mark_delayed(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            observation_status=str(observation.get("reason") or "not_started"),
            next_reminder_at=next_reminder,
            now=current_ms,
        )
        events = [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="child_not_ready",
                message="孩子还没有开始任务。",
                payload={"observation": observation},
                now=current_ms,
            ),
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="delayed",
                message="任务已进入提醒跟进。",
                payload={"nextReminderAt": next_reminder},
                now=current_ms,
            ),
        ]
        events.extend(self._start_monitor(conn, task, now_ms_value=current_ms))
        delay_event = self._send_delay_reminder(conn, updated, now=now)
        if delay_event:
            events.append(delay_event)
        return updated, events

    def _process_delayed(self, conn, task, *, now: datetime):
        observation = self.camera_command_service.camera_service.task_observation(dict(task))
        if observation.get("verdict") == "started":
            current_ms = self._now_ms(now)
            updated = self.repository.mark_in_progress(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                observation_status="started_after_delay",
                now=current_ms,
            )
            event = self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="auto_started",
                message="孩子已经开始任务。",
                payload={"observation": observation, "from": "delayed"},
                now=current_ms,
            )
            events = [event]
            start_event = self._send_phase_reminder(
                conn,
                updated,
                phase="start",
                now_ms_value=current_ms,
                success_event_type="start_reminder_sent",
                failed_event_type="start_reminder_failed",
                success_message="已提醒孩子开始",
                failed_message="摄像头暂时离线，开始提醒没有播出",
            )
            if start_event:
                events.append(start_event)
            return updated, events

        next_reminder_at = int(task.get("next_reminder_at") or 0)
        delay_count = int(task.get("delay_reminder_count") or 0)
        if next_reminder_at and self._now_ms(now) >= next_reminder_at and delay_count < self.max_delay_reminders:
            event = self._send_delay_reminder(conn, task, now=now)
            return task, [event] if event else []
        return task, []

    def _send_delay_reminder(self, conn, task, *, now: datetime):
        if int(task.get("delay_reminder_count") or 0) >= self.max_delay_reminders:
            return None
        current_ms = self._now_ms(now)
        next_reminder = self._plus_seconds_ms(now, self.delay_reminder_interval_seconds)
        reminder_count = int(task.get("delay_reminder_count") or 0) + 1
        reminder = self._task_reminder(
            conn,
            task,
            phase="delay",
            count=reminder_count,
        )
        text = reminder["text"]
        command = None
        sent = False
        if self.speaker_enabled:
            command = self.camera_command_service.internal_speak(
                family_id=task["family_id"],
                task_id=task["id"],
                device_id=task.get("device_id"),
                text=text,
            )
            sent = command.get("status") != "failed"
        self.repository.mark_delay_reminder_result(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            sent=sent,
            next_reminder_at=next_reminder,
            now=current_ms,
        )
        return self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="delay_reminder_sent" if sent else "delay_reminder_failed",
            message="已温和提醒孩子开始" if sent else "摄像头暂时离线，跟进提醒没有播出",
            payload={"command": command, **reminder, "nextReminderAt": next_reminder},
            now=current_ms,
        )

    def _auto_finish(self, conn, task, *, now: datetime):
        if self.repository.has_event(conn, task_id=task["id"], event_type="ended"):
            return task, []
        current_ms = self._now_ms(now)
        updated = self.repository.mark_completed(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            evidence_summary="任务时间已结束，等待家长确认完成情况。"
            if bool(task["requires_parent_confirmation"])
            else "任务时间已结束，已记录完成。",
            completion_source="camera",
            evidence=None,
            ai_observation_summary=task.get("ai_observation_summary"),
            requires_parent_confirmation=bool(task["requires_parent_confirmation"]),
            now=current_ms,
        )
        events = [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="ended",
                message="任务时间已结束",
                payload={},
                now=current_ms,
            )
        ]
        finish_event = self._send_phase_reminder(
            conn,
            updated,
            phase="finish",
            now_ms_value=current_ms,
            success_event_type="finish_reminder_sent",
            failed_event_type="finish_reminder_failed",
            success_message="已提醒孩子结束",
            failed_message="摄像头暂时离线，结束提醒没有播出",
        )
        if finish_event:
            events.append(finish_event)
        if updated["status"] == "awaiting_parent_confirmation":
            events.append(
                self.repository.add_event(
                    conn,
                    family_id=task["family_id"],
                    task_id=task["id"],
                    event_type="awaiting_parent_confirmation",
                    message="等待家长确认完成情况",
                    payload={},
                    now=current_ms,
                )
            )
        elif updated["status"] == "completed":
            events.append(
                self.repository.add_event(
                    conn,
                    family_id=task["family_id"],
                    task_id=task["id"],
                    event_type="completed",
                    message="任务已完成",
                    payload={},
                    now=current_ms,
                )
            )
            ledger_payload = self._grant_points_if_needed(conn, updated, current_ms)
            if ledger_payload:
                events.append(
                    self.repository.add_event(
                        conn,
                        family_id=task["family_id"],
                        task_id=task["id"],
                        event_type="points_awarded",
                        message="奖励积分已发放",
                        payload=ledger_payload,
                        now=current_ms,
                    )
                )
        return updated, events

    def _mark_missed(self, conn, task, *, now: datetime, reason: str):
        if self.repository.has_event(conn, task_id=task["id"], event_type="missed"):
            return task, []
        current_ms = self._now_ms(now)
        updated = self.repository.mark_missed(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            reason=reason,
            now=current_ms,
        )
        event = self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="missed",
            message="任务已错过",
            payload={"reason": reason},
            now=current_ms,
        )
        return updated, [event]

    def _catch_up_history(self, conn, task, *, due_at: datetime | None, now: datetime):
        if task["status"] in TASK_ACTIVE_SCHEDULED_STATUSES:
            return self._mark_missed(conn, task, now=now, reason="过去日期的任务未按时开始。")
        if task["status"] in {TASK_IN_PROGRESS, TASK_DELAYED}:
            if due_at is None or self._is_due(now, due_at):
                return self._auto_finish(conn, task, now=now)
        return task, []

    def _start_monitor(self, conn, task, *, now_ms_value: int):
        if not self.monitor_enabled:
            return []
        command = self.camera_command_service.internal_start_monitor(
            family_id=task["family_id"],
            task_id=task["id"],
            device_id=task.get("device_id"),
        )
        return [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="monitor_started" if command.get("status") != "failed" else "monitor_failed",
                message="摄像头已开始观察任务"
                if command.get("status") != "failed"
                else "摄像头暂时离线，任务仍会记录",
                payload={"command": command},
                now=now_ms_value,
            )
        ]

    def _send_phase_reminder(
        self,
        conn,
        task,
        *,
        phase: str,
        now_ms_value: int,
        success_event_type: str,
        failed_event_type: str,
        success_message: str,
        failed_message: str,
    ):
        if task is None:
            return None
        reminder = self._task_reminder(conn, task, phase=phase)
        command = None
        sent = False
        if self.speaker_enabled:
            command = self.camera_command_service.internal_speak(
                family_id=task["family_id"],
                task_id=task["id"],
                device_id=task.get("device_id"),
                text=reminder["text"],
            )
            sent = command.get("status") != "failed"
        return self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type=success_event_type if sent else failed_event_type,
            message=success_message if sent else failed_message,
            payload={"command": command, **reminder},
            now=now_ms_value,
        )

    def _task_reminder(self, conn, task, *, phase: str, count: int = 0) -> dict:
        child = self.profile_repository.get_child(
            conn,
            family_id=task["family_id"],
            child_id=task["child_id"],
        )
        return build_task_reminder(task, phase=phase, child=child, count=count)

    def _grant_points_if_needed(self, conn, task, now: int) -> dict | None:
        if task["points_granted_at"] or int(task["reward_points"] or 0) <= 0:
            return None
        ledger = self.point_repository.adjust_points(
            conn,
            family_id=task["family_id"],
            child_id=task["child_id"],
            delta=int(task["reward_points"]),
            ledger_type=LEDGER_TASK_COMPLETED,
            source_type="task",
            source_id=task["id"],
            note=f"任务完成奖励：{task['title']}",
            now=now,
        )
        self.repository.mark_points_granted(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            now=now,
        )
        return {
            "id": ledger["id"],
            "delta": ledger["delta"],
            "balanceAfter": ledger["balance_after"],
            "type": ledger["type"],
        }

    def _task_datetime(self, task, kind: str) -> datetime | None:
        value = task.get("start_at") if kind == "start" else task.get("due_at")
        if not value:
            clock = task.get("scheduled_start") if kind == "start" else task.get("scheduled_end")
            if not task.get("scheduled_date") or not clock:
                return None
            value = f"{task['scheduled_date']}T{clock}:00"
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _in_reminder_window(self, task, now: datetime, start_at: datetime) -> bool:
        lead_seconds = self._task_reminder_seconds(task)
        comparable_now = self._comparable_now(now, start_at)
        return start_at - timedelta(seconds=lead_seconds) <= comparable_now < start_at

    def _task_reminder_seconds(self, task) -> int:
        minutes = task.get("reminder_minutes_before")
        if minutes is not None:
            try:
                return max(0, int(minutes) * 60)
            except (TypeError, ValueError):
                pass
        return self.reminder_lead_seconds

    def _is_due(self, now: datetime, target: datetime) -> bool:
        return self._comparable_now(now, target) >= target

    def _comparable_now(self, now: datetime, target: datetime) -> datetime:
        if target.tzinfo is None:
            return now.replace(tzinfo=None)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc).astimezone(target.tzinfo)
        return now.astimezone(target.tzinfo)

    def _is_history_task(self, task, now: datetime) -> bool:
        scheduled_date = str(task.get("scheduled_date") or "")
        return bool(scheduled_date and scheduled_date < now.date().isoformat())

    def _requires_start_observation(self, task) -> bool:
        task_type = str(task.get("type") or task.get("task_type") or "").strip()
        return task_type in TASK_TYPES_REQUIRING_START_OBSERVATION

    def _now_ms(self, now: datetime) -> int:
        if now.tzinfo is None:
            return now_ms()
        return int(now.timestamp() * 1000)

    def _plus_seconds_ms(self, now: datetime, seconds: int) -> int:
        return self._now_ms(now + timedelta(seconds=seconds))
