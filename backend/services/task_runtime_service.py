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
from services.ai_text_provider import AiTextProvider, UnavailableAiTextProvider
from services.camera_command_service import CameraCommandService
from services.prompt_registry import PromptRegistry
from services.setting_policy import setting_value
from services.task_reminder_policy import build_task_reminder


TASK_TYPES_REQUIRING_START_OBSERVATION = {
    "learning",
    "reading_interest",
}

TASK_TYPES_WITHOUT_CAMERA_MONITOR = {
    "sports_outdoor",
}

TASK_OBSERVATION_POLICIES = {
    "reading": {
        "task_keywords": ("绘本", "阅读", "看书", "故事书"),
        "evidence_keywords": ("绘本", "阅读", "看书", "书"),
    },
    "hydration": {
        "task_keywords": ("喝水", "补水", "饮水"),
        "evidence_keywords": ("喝水", "水杯", "饮水", "补水"),
    },
    "toy_cleanup": {
        "task_keywords": ("收玩具", "收纳", "整理玩具"),
        "evidence_keywords": ("收玩具", "收纳", "整理", "玩具"),
    },
    "meal": {
        "task_keywords": ("用餐", "吃饭", "早餐", "午餐", "晚餐", "餐桌"),
        "evidence_keywords": ("用餐", "吃饭", "餐具", "餐桌", "碗", "勺"),
    },
    "sleep": {
        "task_keywords": ("午睡", "入睡", "睡觉", "睡前", "躺下"),
        "evidence_keywords": ("午睡", "入睡", "睡觉", "睡前", "躺下", "安静"),
    },
    "outdoor": {
        "task_keywords": ("运动", "户外", "散步", "跑", "跳", "公园"),
        "evidence_keywords": ("运动", "户外", "散步", "跑", "跳", "公园"),
    },
}

BOUNDARY_DELAY_POLICY = {
    "loose": {"interval_seconds": 300, "max_count": 2},
    "balanced": {"interval_seconds": 180, "max_count": 3},
    "strict": {"interval_seconds": 120, "max_count": 4},
}


class TaskRuntimeService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        camera_command_service: CameraCommandService,
        ai_text_provider: AiTextProvider | None = None,
        prompt_registry: PromptRegistry | None = None,
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
        self.ai_text_provider = ai_text_provider or UnavailableAiTextProvider()
        self.prompt_registry = prompt_registry
        self._task_reminder_prompt_cache: str | None = None
        self.reminder_lead_seconds = max(0, int(reminder_lead_seconds))
        self.delay_reminder_interval_seconds = max(30, int(delay_reminder_interval_seconds))
        self.max_delay_reminders = max(0, int(max_delay_reminders))
        self.monitor_enabled = monitor_enabled
        self.speaker_enabled = speaker_enabled

    def learning_classroom_started(self, *, family_id: str, task_id: str) -> dict:
        """Consume a trusted classroom start without granting camera authority."""

        timestamp = now_ms()
        with self.repository.transaction() as conn:
            task = self.repository.get_task(
                conn,
                family_id=family_id,
                task_id=task_id,
            )
            if task is None or not self._is_runtime_learning_task(task):
                return {"ok": False, "reason": "learning_task_not_found"}
            if self.repository.has_event(
                conn,
                family_id=family_id,
                task_id=task_id,
                event_type="learning_classroom_started",
            ):
                return {"ok": True, "replayed": True}
            self.repository.update_task(
                conn,
                family_id=family_id,
                task_id=task_id,
                fields={
                    "next_reminder_at": None,
                    "reminder_status": "runtime_active",
                    "camera_observation_status": "runtime_active",
                },
                now=timestamp,
            )
            self.repository.add_event(
                conn,
                family_id=family_id,
                task_id=task_id,
                event_type="learning_classroom_started",
                message="互动课堂已开始，停止后续开课提醒",
                payload={"authority": "openmaic_runtime_event"},
                now=timestamp,
            )
            monitor = self._stop_learning_monitor(
                conn,
                task,
                now_ms_value=timestamp,
                reason="classroom_started",
            )
        return {"ok": True, "replayed": False, "monitor": monitor}

    def learning_classroom_completed(
        self,
        *,
        family_id: str,
        task_id: str,
    ) -> dict:
        """Stop auxiliary observation and optionally praise after completion."""

        timestamp = now_ms()
        with self.repository.transaction() as conn:
            task = self.repository.get_task(
                conn,
                family_id=family_id,
                task_id=task_id,
            )
            if task is None or not self._is_runtime_learning_task(task):
                return {"ok": False, "reason": "learning_task_not_found"}
            if self.repository.has_event(
                conn,
                family_id=family_id,
                task_id=task_id,
                event_type="learning_classroom_completed",
            ):
                return {"ok": True, "replayed": True}
            monitor = self._stop_learning_monitor(
                conn,
                task,
                now_ms_value=timestamp,
                reason="classroom_completed",
            )
            finish_event = self._send_phase_reminder(
                conn,
                task,
                phase="finish",
                now_ms_value=timestamp,
                success_event_type="learning_finish_reminder_sent",
                failed_event_type="learning_finish_reminder_failed",
                success_message="摄像头已向孩子送出完成鼓励",
                failed_message="课堂已完成，摄像头鼓励暂未播出",
            )
            self.repository.update_task(
                conn,
                family_id=family_id,
                task_id=task_id,
                fields={
                    "next_reminder_at": None,
                    "reminder_status": "runtime_completed",
                    "camera_observation_status": "runtime_completed",
                },
                now=timestamp,
            )
            self.repository.add_event(
                conn,
                family_id=family_id,
                task_id=task_id,
                event_type="learning_classroom_completed",
                message="互动课堂已完成，摄像头联动已收尾",
                payload={
                    "authority": "openmaic_runtime_event",
                    "monitor": monitor,
                    "finishReminderEventId": (
                        finish_event.get("id") if finish_event is not None else None
                    ),
                },
                now=timestamp,
            )
        return {"ok": True, "replayed": False, "monitor": monitor}

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
            if task["status"] == TASK_DELAYED:
                return self._mark_missed(
                    conn,
                    task,
                    now=now,
                    reason="这次没有看到孩子开始，可以重新安排或手动处理。",
                )
            if task["status"] == TASK_IN_PROGRESS:
                return self._finish_or_review(conn, task, now=now)
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
        if (
            self.repository.has_event(conn, task_id=task["id"], event_type="reminder_sent")
            or self.repository.has_event(conn, task_id=task["id"], event_type="reminder_failed")
            or self.repository.has_event(conn, task_id=task["id"], event_type="reminder_skipped")
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
        if not self._has_camera_device(task):
            event = self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="reminder_skipped",
                message="未连接摄像头，本次只记录安排。",
                payload={"command": self._skipped_command("no_camera_device"), **reminder},
                now=current_ms,
            )
            return task, event
        if not self._voice_reminder_enabled(conn, task["family_id"]):
            event = self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="reminder_skipped",
                message="语音提醒已关闭，未向摄像头播报",
                payload={"command": self._skipped_command("voice_reminder_disabled"), **reminder},
                now=current_ms,
            )
            return task, event
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
        if self._is_runtime_learning_task(task):
            return self._wait_for_authoritative_classroom(conn, task, now=now)
        if self.repository.has_event(conn, task_id=task["id"], event_type="auto_started"):
            return task, []
        if not self._has_camera_device(task):
            return self._mark_in_progress_without_camera(conn, task, now=now)
        if not self._requires_start_observation(conn, task):
            return self._mark_in_progress_without_start_observation(conn, task, now=now)

        observation = self.camera_command_service.internal_task_observation(
            family_id=task["family_id"],
            task=dict(task),
            device_id=task.get("device_id"),
        )
        observation = self._normalize_task_observation(task, observation)
        verdict = observation.get("verdict")
        if verdict == "not_started":
            return self._mark_delayed(conn, task, observation=observation, now=now)

        if verdict != "started":
            return self._mark_delayed(conn, task, observation=observation, now=now)
        status = "started"
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

    def _wait_for_authoritative_classroom(self, conn, task, *, now: datetime):
        """Remind and observe, but never let camera evidence start a lesson."""

        current_ms = self._now_ms(now)
        max_delay_reminders = self._max_delay_reminders(conn, task["family_id"])
        next_reminder = (
            self._plus_seconds_ms(
                now,
                self._delay_reminder_interval_seconds(conn, task["family_id"]),
            )
            if max_delay_reminders > 0
            else None
        )
        has_camera = self._has_camera_device(task)
        updated = self.repository.mark_delayed(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            observation_status=(
                "awaiting_runtime_event" if has_camera else "no_camera_device"
            ),
            next_reminder_at=next_reminder,
            now=current_ms,
        )
        events = [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="learning_classroom_waiting",
                message="等待孩子在互动课堂中开始学习",
                payload={
                    "runtimeScheduledDate": task.get("runtime_scheduled_date")
                    or task.get("scheduled_date"),
                    "cameraRole": "reminder_only",
                },
                now=current_ms,
            )
        ]
        start_event = self._send_phase_reminder(
            conn,
            updated,
            phase="start",
            now_ms_value=current_ms,
            success_event_type="learning_start_reminder_sent",
            failed_event_type="learning_start_reminder_failed",
            success_message="已提醒孩子打开互动课堂",
            failed_message="摄像头暂时离线，开课提醒没有播出",
        )
        if start_event:
            events.append(start_event)
        if has_camera:
            events.extend(self._start_monitor(conn, updated, now_ms_value=current_ms))
        else:
            events.append(
                self.repository.add_event(
                    conn,
                    family_id=task["family_id"],
                    task_id=task["id"],
                    event_type="learning_monitor_skipped",
                    message="未连接摄像头，本次只等待课堂开始事件",
                    payload={"reason": "no_camera_device"},
                    now=current_ms,
                )
            )
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

    def _mark_in_progress_without_camera(self, conn, task, *, now: datetime):
        current_ms = self._now_ms(now)
        updated = self.repository.mark_in_progress(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            observation_status="no_camera_device",
            now=current_ms,
        )
        event = self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="auto_started",
            message="安排已按时间开始，本次只记录安排。",
            payload={"observation": {"verdict": "unavailable", "reason": "no_camera_device"}},
            now=current_ms,
        )
        return updated, [event]

    def _mark_delayed(self, conn, task, *, observation: dict, now: datetime):
        current_ms = self._now_ms(now)
        max_delay_reminders = self._max_delay_reminders(conn, task["family_id"])
        next_reminder = (
            self._plus_seconds_ms(now, self._delay_reminder_interval_seconds(conn, task["family_id"]))
            if max_delay_reminders > 0
            else None
        )
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
        if max_delay_reminders > 0:
            delay_event = self._send_delay_reminder(conn, updated, now=now)
            if delay_event:
                events.append(delay_event)
        return updated, events

    def _process_delayed(self, conn, task, *, now: datetime):
        if self._is_runtime_learning_task(task):
            next_reminder_at = int(task.get("next_reminder_at") or 0)
            delay_count = int(task.get("delay_reminder_count") or 0)
            max_delay_reminders = self._max_delay_reminders(
                conn, task["family_id"]
            )
            if (
                next_reminder_at
                and self._now_ms(now) >= next_reminder_at
                and delay_count < max_delay_reminders
            ):
                event = self._send_delay_reminder(conn, task, now=now)
                return task, [event] if event else []
            return task, []
        if not self._has_camera_device(task):
            return task, []
        observation = self.camera_command_service.internal_task_observation(
            family_id=task["family_id"],
            task=dict(task),
            device_id=task.get("device_id"),
        )
        observation = self._normalize_task_observation(task, observation)
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
        max_delay_reminders = self._max_delay_reminders(conn, task["family_id"])
        if next_reminder_at and self._now_ms(now) >= next_reminder_at and delay_count < max_delay_reminders:
            event = self._send_delay_reminder(conn, task, now=now)
            return task, [event] if event else []
        return task, []

    def _send_delay_reminder(self, conn, task, *, now: datetime):
        max_delay_reminders = self._max_delay_reminders(conn, task["family_id"])
        if int(task.get("delay_reminder_count") or 0) >= max_delay_reminders:
            return None
        current_ms = self._now_ms(now)
        next_reminder = self._plus_seconds_ms(
            now,
            self._delay_reminder_interval_seconds(conn, task["family_id"]),
        )
        reminder_count = int(task.get("delay_reminder_count") or 0) + 1
        reminder = self._task_reminder(
            conn,
            task,
            phase="delay",
            count=reminder_count,
        )
        text = reminder["text"]
        if not self._has_camera_device(task):
            return self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="delay_reminder_skipped",
                message="未连接摄像头，本次只记录安排。",
                payload={"command": self._skipped_command("no_camera_device"), **reminder},
                now=current_ms,
            )
        if not self._voice_reminder_enabled(conn, task["family_id"]):
            self.repository.mark_delay_reminder_result(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                sent=False,
                next_reminder_at=next_reminder,
                now=current_ms,
            )
            return self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="delay_reminder_skipped",
                message="语音提醒已关闭，未向摄像头播报",
                payload={"command": self._skipped_command("voice_reminder_disabled"), **reminder},
                now=current_ms,
            )
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

    def _finish_or_review(self, conn, task, *, now: datetime):
        if not self._has_camera_device(task):
            return self._mark_missed(
                conn,
                task,
                now=now,
                reason="未连接摄像头，本次只记录安排。",
            )
        if not self._requires_start_observation(conn, task):
            return self._auto_finish(conn, task, now=now)
        observation_status = str(task.get("camera_observation_status") or "")
        if observation_status not in {"started", "started_after_delay"}:
            return self._mark_missed(
                conn,
                task,
                now=now,
                reason="这次没有看到孩子开始，可以重新安排或手动处理。",
            )
        if bool(task["requires_parent_confirmation"]):
            return self._finish_with_parent_review(conn, task, now=now)
        return self._mark_missed(
            conn,
            task,
            now=now,
            reason="只看到部分过程，没有可靠完成结果，需要家长看一下。",
        )

    def _finish_with_parent_review(self, conn, task, *, now: datetime):
        if self.repository.has_event(conn, task_id=task["id"], event_type="awaiting_parent_confirmation"):
            return task, []
        current_ms = self._now_ms(now)
        updated = self.repository.mark_completed(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            evidence_summary="只看到部分过程，请确认是否完成。",
            completion_source="camera",
            evidence=None,
            ai_observation_summary=task.get("ai_observation_summary"),
            requires_parent_confirmation=True,
            now=current_ms,
        )
        events = [
            self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type="awaiting_parent_confirmation",
                message="只看到部分过程，请确认是否完成。",
                payload={"reason": "partial_observation"},
                now=current_ms,
            )
        ]
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
            message="本次未记录完成",
            payload={"reason": reason},
            now=current_ms,
        )
        return updated, [event]

    def _catch_up_history(self, conn, task, *, due_at: datetime | None, now: datetime):
        if task["status"] in TASK_ACTIVE_SCHEDULED_STATUSES:
            return self._mark_missed(conn, task, now=now, reason="过去日期的任务未按时开始。")
        if task["status"] in {TASK_IN_PROGRESS, TASK_DELAYED}:
            if due_at is None or self._is_due(now, due_at):
                if task["status"] == TASK_DELAYED:
                    return self._mark_missed(
                        conn,
                        task,
                        now=now,
                        reason="这次没有看到孩子开始，可以重新安排或手动处理。",
                    )
                return self._finish_or_review(conn, task, now=now)
        return task, []

    def _start_monitor(self, conn, task, *, now_ms_value: int):
        if not self.monitor_enabled:
            return []
        if self._task_type(task) in TASK_TYPES_WITHOUT_CAMERA_MONITOR:
            return [
                self.repository.add_event(
                    conn,
                    family_id=task["family_id"],
                    task_id=task["id"],
                    event_type="monitor_not_required",
                    message="户外任务不需要摄像头观察，按时间记录并等待后续确认。",
                    payload={"reason": "out_of_camera_scope"},
                    now=now_ms_value,
                )
            ]
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

    def _stop_learning_monitor(
        self,
        conn,
        task,
        *,
        now_ms_value: int,
        reason: str,
    ) -> dict:
        if not self.repository.has_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="monitor_started",
        ):
            return {"status": "not_active", "reason": "monitor_not_started"}
        if self.repository.has_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type="learning_monitor_stopped",
        ):
            return {"status": "already_stopped"}
        if not self._has_camera_device(task):
            command = self._skipped_command("no_camera_device")
            event_type = "learning_monitor_stop_skipped"
            message = "摄像头未连接，观察停止指令已跳过"
        else:
            command = self.camera_command_service.internal_stop_monitor(
                family_id=task["family_id"],
                task_id=task["id"],
                device_id=task.get("device_id"),
            )
            succeeded = command.get("status") != "failed"
            event_type = (
                "learning_monitor_stopped"
                if succeeded
                else "learning_monitor_stop_failed"
            )
            message = (
                "课堂状态已确认，摄像头停止任务观察"
                if succeeded
                else "课堂状态已确认，但摄像头停止观察失败"
            )
        self.repository.add_event(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            event_type=event_type,
            message=message,
            payload={"reason": reason, "command": command},
            now=now_ms_value,
        )
        return command

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
        if not self._has_camera_device(task):
            return self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type=success_event_type.replace("_sent", "_skipped"),
                message="未连接摄像头，本次只记录安排。",
                payload={
                    "command": self._skipped_command("no_camera_device"),
                    **reminder,
                },
                now=now_ms_value,
            )
        if not self._voice_reminder_enabled(conn, task["family_id"]):
            return self.repository.add_event(
                conn,
                family_id=task["family_id"],
                task_id=task["id"],
                event_type=success_event_type.replace("_sent", "_skipped"),
                message="语音提醒已关闭，未向摄像头播报",
                payload={
                    "command": self._skipped_command("voice_reminder_disabled"),
                    **reminder,
                },
                now=now_ms_value,
            )
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
        return build_task_reminder(
            task,
            phase=phase,
            child=child,
            count=count,
            ai_text_provider=self.ai_text_provider,
            prompt=self._task_reminder_prompt(),
        )

    def _task_reminder_prompt(self) -> str:
        if self._task_reminder_prompt_cache is not None:
            return self._task_reminder_prompt_cache
        if self.prompt_registry is None:
            self._task_reminder_prompt_cache = ""
            return ""
        prompt = self.prompt_registry.get_prompt("task.reminder.voice", "v1")
        self._task_reminder_prompt_cache = prompt.body if prompt else ""
        return self._task_reminder_prompt_cache

    def _grant_points_if_needed(self, conn, task, now: int) -> dict | None:
        if task["points_granted_at"] or int(task["reward_points"] or 0) <= 0:
            return None
        if not self.repository.mark_points_granted_once(
            conn,
            family_id=task["family_id"],
            task_id=task["id"],
            now=now,
        ):
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
        return {
            "id": ledger["id"],
            "delta": ledger["delta"],
            "balanceAfter": ledger["balance_after"],
            "type": ledger["type"],
        }

    def _task_datetime(self, task, kind: str) -> datetime | None:
        runtime_date = str(task.get("runtime_scheduled_date") or "").strip()
        if runtime_date:
            clock = (
                task.get("scheduled_start")
                if kind == "start"
                else task.get("scheduled_end")
            )
            if not clock:
                return None
            try:
                return datetime.fromisoformat(f"{runtime_date}T{clock}:00")
            except ValueError:
                return None
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
        scheduled_date = str(
            task.get("runtime_scheduled_date") or task.get("scheduled_date") or ""
        )
        return bool(scheduled_date and scheduled_date < now.date().isoformat())

    def _requires_start_observation(self, conn, task) -> bool:
        if self._ai_rules(conn, task["family_id"]).get("taskObservationEnabled") is not True:
            return False
        if self._task_type(task) in TASK_TYPES_REQUIRING_START_OBSERVATION:
            return True
        return self._task_observation_policy(task) is not None

    def _normalize_task_observation(self, task, observation: dict) -> dict:
        if observation.get("verdict") != "started":
            return observation
        if self._observation_matches_task(task, observation):
            return observation
        next_observation = dict(observation)
        next_observation["verdict"] = "insufficient"
        next_observation["reason"] = "action_not_supported"
        evidence = dict(next_observation.get("evidence") or {})
        evidence["taskActionMatched"] = False
        next_observation["evidence"] = evidence
        return next_observation

    def _observation_matches_task(self, task, observation: dict) -> bool:
        policy = self._task_observation_policy(task)
        evidence = observation.get("evidence") or {}
        evidence_text = " ".join(
            str(evidence.get(key) or "")
            for key in ("activity", "raw_activity", "summary", "action")
        )
        if policy is not None:
            return any(word in evidence_text for word in policy["evidence_keywords"])
        if self._task_type(task) in {"reading_interest", "life", "checkin"}:
            return bool(evidence_text.strip()) and evidence_text not in {"其他", "unknown", "other"}
        return True

    def _task_observation_policy(self, task) -> dict | None:
        task_text = f"{task.get('type') or ''} {task.get('title') or ''} {task.get('description') or ''}"
        for policy in TASK_OBSERVATION_POLICIES.values():
            if any(word in task_text for word in policy["task_keywords"]):
                return policy
        return None

    def _task_type(self, task) -> str:
        return str(task.get("type") or task.get("task_type") or "").strip()

    def _is_runtime_learning_task(self, task) -> bool:
        return bool(
            self._task_type(task) == "learning"
            and str(task.get("learning_course_id") or "").strip()
        )

    def _ai_rules(self, conn, family_id: str) -> dict:
        row = self.profile_repository.get_setting(conn, family_id=family_id, key="ai-care-rules")
        return setting_value(row, "ai-care-rules")

    def _conversation_rules(self, conn, family_id: str) -> dict:
        row = self.profile_repository.get_setting(conn, family_id=family_id, key="conversation")
        return setting_value(row, "conversation")

    def _voice_reminder_enabled(self, conn, family_id: str) -> bool:
        return self.speaker_enabled and self._ai_rules(conn, family_id).get("voiceReminderEnabled") is True

    def _delay_reminder_enabled(self, conn, family_id: str) -> bool:
        return self._ai_rules(conn, family_id).get("delayReminderEnabled") is True

    def _delay_reminder_interval_seconds(self, conn, family_id: str) -> int:
        rules = self._ai_rules(conn, family_id)
        configured = self._positive_int(
            rules.get("delayReminderIntervalMinutes"),
            fallback=0,
        )
        if configured:
            return max(60, configured * 60)
        boundary = str(self._conversation_rules(conn, family_id).get("boundaryLevel") or "balanced")
        return BOUNDARY_DELAY_POLICY.get(boundary, BOUNDARY_DELAY_POLICY["balanced"])["interval_seconds"]

    def _max_delay_reminders(self, conn, family_id: str) -> int:
        if not self._delay_reminder_enabled(conn, family_id):
            return 0
        rules = self._ai_rules(conn, family_id)
        configured = self._positive_int(rules.get("maxDelayReminderCount"), fallback=-1)
        if configured >= 0:
            return configured
        boundary = str(self._conversation_rules(conn, family_id).get("boundaryLevel") or "balanced")
        return BOUNDARY_DELAY_POLICY.get(boundary, BOUNDARY_DELAY_POLICY["balanced"])["max_count"]

    def _positive_int(self, value, *, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return max(0, parsed)

    def _skipped_command(self, reason: str) -> dict:
        return {"status": "skipped", "reason": reason}

    def _has_camera_device(self, task) -> bool:
        if not hasattr(self.camera_command_service, "has_available_device"):
            return True
        return bool(
            self.camera_command_service.has_available_device(
                family_id=task["family_id"],
                device_id=task.get("device_id"),
            )
        )

    def _now_ms(self, now: datetime) -> int:
        if now.tzinfo is None:
            return now_ms()
        return int(now.timestamp() * 1000)

    def _plus_seconds_ms(self, now: datetime, seconds: int) -> int:
        return self._now_ms(now + timedelta(seconds=seconds))
