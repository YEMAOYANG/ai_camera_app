from __future__ import annotations

import json
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.camera_command_repository import CameraCommandRepository
from repositories.device_repository import DeviceRepository
from schemas.camera import camera_command_payload
from services.auth_service import AuthService
from services.camera_bridge_service import CameraBridgeError, CameraBridgeService
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.task_event_stream import (
    CAMERA_EVENT_CREATED,
    CAMERA_STATUS_CHANGED,
    publish_family_event,
)


class CameraCommandService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        camera_service: CameraBridgeService | None = None,
        runtime_resolver: DeviceRuntimeResolver | None = None,
    ):
        database = Database(database_url)
        self.repository = CameraCommandRepository(database)
        self.device_repository = DeviceRepository(database)
        self.auth_service = auth_service
        self.runtime_resolver = runtime_resolver
        self.camera_service = camera_service or (runtime_resolver.global_bridge() if runtime_resolver else None)

    def speak(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        text = self._required_text(data, "text", "请输入要提醒孩子的话")
        bridge, device_id = self._runtime_for_command(
            family_id=context["family"]["id"],
            device_id=self._optional_text(data, "deviceId"),
        )
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="speak",
                request_payload={"text": text},
                runner=lambda: bridge.speak(text),
                device_id=device_id,
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def snapshot(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        bridge, device_id = self._runtime_for_command(
            family_id=context["family"]["id"],
            device_id=self._optional_text(data, "deviceId"),
        )
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="snapshot",
                request_payload={},
                runner=lambda: {
                    "ok": True,
                    "contentType": bridge.fetch_snapshot().content_type,
                },
                device_id=device_id,
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def ptz_move(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        direction = self._ptz_direction(data.get("direction"))
        step = self._ptz_step(data.get("step"))
        bridge, device_id = self._runtime_for_command(
            family_id=context["family"]["id"],
            device_id=self._optional_text(data, "deviceId"),
        )
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="ptz_move",
                request_payload={"direction": direction, "step": step},
                runner=lambda: bridge.ptz_move(direction, step),
                device_id=device_id,
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def monitor_start(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        bridge, device_id = self._runtime_for_command(
            family_id=context["family"]["id"],
            device_id=self._optional_text(data, "deviceId"),
        )
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="start_monitor",
                request_payload={},
                runner=bridge.start_monitor,
                device_id=device_id,
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def monitor_stop(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        bridge, device_id = self._runtime_for_command(
            family_id=context["family"]["id"],
            device_id=self._optional_text(data, "deviceId"),
        )
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="stop_monitor",
                request_payload={},
                runner=bridge.stop_monitor,
                device_id=device_id,
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def device_command(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        command_type = self._required_text(data, "commandType", "请选择要执行的设备操作")
        with self.repository.transaction() as conn:
            if self.device_repository.get_device(conn, family_id=family_id, device_id=device_id) is None:
                raise ApiError("device_not_found", "设备不存在", 404)
        if command_type == "speak":
            next_data = dict(data)
            next_data["deviceId"] = device_id
            return self.speak(access_token, next_data)
        if command_type == "snapshot":
            next_data = dict(data)
            next_data["deviceId"] = device_id
            return self.snapshot(access_token, next_data)
        if command_type == "ptz_move":
            next_data = dict(data)
            next_data["deviceId"] = device_id
            return self.ptz_move(access_token, next_data)
        if command_type == "start_monitor":
            next_data = dict(data)
            next_data["deviceId"] = device_id
            return self.monitor_start(access_token, next_data)
        if command_type == "stop_monitor":
            next_data = dict(data)
            next_data["deviceId"] = device_id
            return self.monitor_stop(access_token, next_data)
        raise ApiError("unsupported_device_command", "暂不支持这个设备操作")

    def recent_events(
        self,
        access_token: str,
        args,
        *,
        device_id: str | None = None,
        include_unassigned: bool = False,
    ) -> dict:
        context = self.auth_service.authenticate(access_token)
        limit = self._limit_arg(args.get("limit") if args else None)
        with self.repository.transaction() as conn:
            commands = self.repository.list_recent_commands(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                limit=limit,
            )
            task_events = self.repository.list_recent_task_events(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                include_unassigned=include_unassigned,
                limit=limit,
            )
        events = [
            *(_camera_command_event_payload(row) for row in commands),
            *(_task_event_payload(row) for row in task_events),
        ]
        events.sort(key=lambda item: (item["createdAt"], item["id"]), reverse=True)
        parent_events = _parent_facing_events(events)
        camera_events = [event for event in parent_events if _is_camera_care_event(event)]
        return {"ok": True, "events": camera_events[:limit]}

    def record_observation_event(
        self,
        *,
        family_id: str,
        child_id: str | None,
        device_id: str,
        observation: dict,
    ) -> dict:
        display = _camera_observation_display(observation)
        now = now_ms()
        payload = {
            "childId": child_id or "",
            "observation": observation,
            "displayTitle": display["title"],
            "displayMessage": display["message"],
            "category": display["category"],
            "severity": display["severity"],
            "evidenceSummary": display["evidence"],
        }
        with self.repository.transaction() as conn:
            command = self.repository.create_command(
                conn,
                family_id=family_id,
                device_id=device_id,
                task_id=None,
                command_type="camera_observation",
                status="succeeded",
                message=display["message"],
                request_payload=self._json_text(payload),
                now=now,
            )
            updated = self.repository.update_command(
                conn,
                family_id=family_id,
                command_id=command["id"],
                status="succeeded",
                message=display["message"],
                response_payload=self._json_text(payload),
                now=now,
                completed=True,
            )
        publish_family_event(
            family_id=family_id,
            event_type=CAMERA_EVENT_CREATED,
            device_id=device_id,
            event_ids=[command["id"]],
            observation_id=str(observation.get("observedAt") or ""),
            is_reliable=bool(observation.get("isReliable")),
            source="camera_observation",
        )
        return camera_command_payload(updated)

    def internal_speak(
        self,
        *,
        family_id: str,
        text: str,
        task_id: str | None = None,
        device_id: str | None = None,
    ) -> dict:
        bridge, resolved_device_id = self._runtime_for_command(
            family_id=family_id,
            device_id=device_id,
        )
        return self._execute_command(
            family_id=family_id,
            command_type="speak",
            request_payload={"text": text},
            runner=lambda: bridge.speak(text),
            task_id=task_id,
            device_id=resolved_device_id,
        )

    def internal_start_monitor(
        self,
        *,
        family_id: str,
        task_id: str | None = None,
        device_id: str | None = None,
    ) -> dict:
        bridge, resolved_device_id = self._runtime_for_command(
            family_id=family_id,
            device_id=device_id,
        )
        return self._execute_command(
            family_id=family_id,
            command_type="start_monitor",
            request_payload={},
            runner=bridge.start_monitor,
            task_id=task_id,
            device_id=resolved_device_id,
        )

    def internal_task_observation(
        self,
        *,
        family_id: str,
        task: dict,
        device_id: str | None = None,
    ) -> dict:
        bridge, _ = self._runtime_for_command(family_id=family_id, device_id=device_id)
        return bridge.task_observation(task)

    def has_available_device(self, *, family_id: str, device_id: str | None = None) -> bool:
        requested_device_id = str(device_id or "").strip()
        with self.repository.transaction() as conn:
            if requested_device_id:
                device = self.device_repository.get_device(
                    conn,
                    family_id=family_id,
                    device_id=requested_device_id,
                )
                return device is not None and str(device.get("status") or "") != "unbound"
            return bool(self.device_repository.ensure_default_device(conn, family_id=family_id, now=now_ms()))

    def _runtime_for_command(self, *, family_id: str, device_id: str | None) -> tuple[CameraBridgeService, str | None]:
        if self.runtime_resolver is None:
            if self.camera_service is None:
                raise ApiError("camera_runtime_not_configured", "摄像头暂时不可用。", 503)
            return self.camera_service, device_id
        resolved = self.runtime_resolver.resolve(family_id=family_id, device_id=device_id)
        return resolved.bridge, resolved.device_id or device_id

    def _execute_command(
        self,
        *,
        family_id: str,
        command_type: str,
        request_payload: dict,
        runner,
        device_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        now = now_ms()
        with self.repository.transaction() as conn:
            command = self.repository.create_command(
                conn,
                family_id=family_id,
                device_id=device_id,
                task_id=task_id,
                command_type=command_type,
                status="running",
                message="正在执行",
                request_payload=self._json_text(request_payload),
                now=now,
            )
            command_id = command["id"]

        try:
            result = runner()
            message = "已执行"
            status = "succeeded"
            response_payload = self._public_command_response(result)
        except CameraBridgeError as exc:
            message = self._product_error_message(command_type)
            status = "failed"
            response_payload = {"error": exc.code, "message": exc.message}
        except Exception as exc:
            message = self._product_error_message(command_type)
            status = "failed"
            response_payload = {"error": "camera_command_failed", "message": str(exc)}

        with self.repository.transaction() as conn:
            updated = self.repository.update_command(
                conn,
                family_id=family_id,
                command_id=command_id,
                status=status,
                message=message,
                response_payload=self._json_text(response_payload),
                now=now_ms(),
                completed=True,
            )
            if _should_publish_camera_status(command_type, status):
                publish_family_event(
                    family_id=family_id,
                    event_type=CAMERA_STATUS_CHANGED,
                    device_id=device_id,
                    task_ids=[task_id] if task_id else [],
                    event_ids=[command_id],
                    source="camera_command",
                )
                publish_family_event(
                    family_id=family_id,
                    event_type=CAMERA_EVENT_CREATED,
                    device_id=device_id,
                    task_ids=[task_id] if task_id else [],
                    event_ids=[command_id],
                    is_reliable=status == "succeeded",
                    source="camera_command",
                )
            return camera_command_payload(updated)

    def _product_error_message(self, command_type: str) -> str:
        if command_type == "speak":
            return "摄像头暂时离线，提醒没有播出。"
        if command_type == "snapshot":
            return "暂时没有拿到最新画面。"
        if command_type == "ptz_move":
            return "摄像头暂时不支持云台控制。"
        return "摄像头暂时离线，操作没有完成。"

    def _ptz_direction(self, value: object) -> str:
        direction = str(value or "").strip().lower()
        if direction not in {"up", "down", "left", "right", "home"}:
            raise ApiError("invalid_ptz_direction", "请选择正确的云台方向")
        return direction

    def _ptz_step(self, value: object) -> int:
        try:
            step = int(value or 1)
        except (TypeError, ValueError):
            step = 1
        return max(1, min(step, 5))

    def _limit_arg(self, value: object) -> int:
        try:
            limit = int(value or 30)
        except (TypeError, ValueError):
            limit = 30
        return max(1, min(limit, 100))

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

    def _json_text(self, value: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _public_command_response(self, value: object) -> dict:
        if not isinstance(value, dict):
            return {"ok": True}
        response = {"ok": value.get("ok", True) is not False}
        for key in ("contentType", "status", "message", "direction", "step"):
            current = value.get(key)
            if isinstance(current, (str, bool, int, float)):
                response[key] = current
        monitor = value.get("monitor_runtime")
        if isinstance(monitor, dict):
            response["monitor"] = {
                "running": bool(monitor.get("running")),
                "status": str(monitor.get("status") or monitor.get("state") or ""),
            }
        speaker = value.get("speaker")
        if isinstance(speaker, dict):
            response["speaker"] = {"queued": bool(speaker.get("queued", True))}
        return response


def _camera_command_event_payload(row) -> dict:
    command_type = str(row.get("command_type") or "")
    request = _json_dict(row.get("request_payload"))
    response = _json_dict(row.get("response_payload"))
    status = str(row.get("status") or "")
    message = str(row.get("message") or _command_title(command_type))
    if command_type == "ptz_move":
        direction = str(request.get("direction") or response.get("direction") or "")
        message = f"{_ptz_direction_label(direction)} · {message}"
    return {
        "id": row["id"],
        "source": "camera_command",
        "eventType": command_type,
        "deviceId": row.get("device_id") or "",
        "taskId": row.get("task_id") or "",
        "title": _command_title(command_type),
        "message": message,
        "status": status,
        "tone": _event_tone(status),
        "createdAt": row.get("completed_at") or row.get("updated_at") or row["created_at"],
        "payload": {"request": request, "response": response},
    }


def _should_publish_camera_status(command_type: str, status: str) -> bool:
    if command_type in {"snapshot", "start_monitor", "stop_monitor"}:
        return True
    return status == "failed"


def _task_event_payload(row) -> dict:
    event_type = str(row.get("event_type") or "")
    return {
        "id": row["id"],
        "source": "task_event",
        "eventType": event_type,
        "deviceId": row.get("device_id") or "",
        "taskId": row.get("task_id") or "",
        "taskTitle": row.get("task_title") or "",
        "title": _task_event_title(event_type),
        "message": row.get("message") or _task_event_title(event_type),
        "status": "recorded",
        "tone": "info",
        "createdAt": row["created_at"],
        "payload": _json_dict(row.get("payload")),
    }


def _parent_facing_events(events: list[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for event in events:
        display = _parent_facing_event(event)
        if display is None:
            continue
        key = _parent_event_dedupe_key(display)
        if key in seen:
            continue
        seen.add(key)
        result.append(display)
    return result


def _parent_facing_event(event: dict) -> dict | None:
    source = str(event.get("source") or "")
    event_type = str(event.get("eventType") or "")
    if source == "camera_command":
        return _parent_camera_command_event(event)
    if source == "task_event":
        return _parent_task_event(event)
    return None


def _is_camera_care_event(event: dict) -> bool:
    return str(event.get("category") or "") in {
        "camera_observation",
        "child_presence",
        "snapshot",
        "camera_status",
    }


def _parent_camera_command_event(event: dict) -> dict | None:
    event_type = str(event.get("eventType") or "")
    status = str(event.get("status") or "")
    if event_type == "camera_observation":
        payload = _json_dict(event.get("payload"))
        response = _json_dict(payload.get("response"))
        request = _json_dict(payload.get("request"))
        data = response or request
        observation = _json_dict(data.get("observation"))
        display = _camera_observation_display(observation)
        return _with_display(
            event,
            display_title=str(data.get("displayTitle") or display["title"]),
            display_message=str(data.get("displayMessage") or display["message"]),
            category=str(data.get("category") or display["category"]),
            severity=str(data.get("severity") or display["severity"]),
        )
    if event_type in {"start_monitor", "stop_monitor"}:
        return None
    if event_type == "speak":
        return None
    if event_type == "snapshot":
        if status == "failed":
            return _with_display(
                event,
                display_title="画面暂时不可用",
                display_message=str(event.get("message") or "暂时没有拿到最新画面。"),
                category="camera_status",
                severity="warning",
            )
        return None
    if event_type == "ptz_move":
        return None
    return None


def _parent_task_event(event: dict) -> dict | None:
    event_type = str(event.get("eventType") or "")
    if event_type in {
        "created",
        "task_created",
        "updated",
        "task_updated",
        "reminder_due",
        "monitor_started",
        "monitor_not_required",
        "camera_monitor_started",
        "manual_started",
    }:
        return None
    task_title = str(event.get("taskTitle") or "").strip()
    payload = _json_dict(event.get("payload"))
    if event_type in {
        "reminder_sent",
        "start_reminder_sent",
        "manual_start_reminder_sent",
        "manual_prepare_reminder_sent",
        "manual_reminder_sent",
        "wrap_up_reminder_sent",
        "finish_reminder_sent",
        "manual_finish_reminder_sent",
        "delay_reminder_sent",
    }:
        return None
    if event_type in {
        "reminder_failed",
        "start_reminder_failed",
        "manual_start_reminder_failed",
        "manual_prepare_reminder_failed",
        "manual_reminder_failed",
        "wrap_up_reminder_failed",
        "finish_reminder_failed",
        "manual_finish_reminder_failed",
        "delay_reminder_failed",
    }:
        return _with_display(
            event,
            display_title="提醒没有播出",
            display_message=_task_message(event, fallback="摄像头暂时不可用，提醒没有播出。"),
            category="camera_status",
            severity="warning",
            task_title=task_title,
        )
    if event_type == "child_not_ready":
        return _with_display(
            event,
            display_title="还没看到孩子开始",
            display_message=_observation_message(payload, fallback="暂时还不能确认孩子已经开始。"),
            category="task_observation",
            severity="warning",
            task_title=task_title,
        )
    if event_type == "delayed":
        return None
    if event_type == "observation_unavailable" or event_type == "monitor_failed":
        return _with_display(
            event,
            display_title="暂时没有可靠观察",
            display_message=_observation_message(payload, fallback="这次画面还不能作为确认依据。"),
            category="task_observation",
            severity="warning",
            task_title=task_title,
        )
    if event_type == "auto_started":
        observation = _json_dict(payload.get("observation"))
        verdict = str(observation.get("verdict") or "")
        reason = str(observation.get("reason") or "")
        if verdict != "started" and reason in {"task_type", "not_required"}:
            return None
        if verdict != "started":
            return _with_display(
                event,
                display_title="暂时没有可靠观察",
                display_message="已按时间记录，但还不能确认孩子动作。",
                category="task_observation",
                severity="warning",
                task_title=task_title,
            )
        return _with_display(
            event,
            display_title="已看到孩子开始",
            display_message=_observation_message(payload, fallback="摄像头看到孩子开始了。"),
            category="task_observation",
            severity="success",
            task_title=task_title,
        )
    if event_type in {"awaiting_parent_confirmation", "completed"}:
        return None
    if event_type in {"missed", "camera_command_failed"}:
        return None
    return None


def _with_display(
    event: dict,
    *,
    display_title: str,
    display_message: str,
    category: str,
    severity: str,
    task_title: str = "",
) -> dict:
    next_event = dict(event)
    message = display_message.strip() or display_title
    next_event.update(
        {
            "displayTitle": display_title,
            "displayMessage": message,
            "category": category,
            "severity": severity,
            "taskTitle": task_title or event.get("taskTitle") or "",
            "evidenceSummary": _evidence_summary(event),
            "hasReplay": False,
            "title": display_title,
            "message": message,
            "tone": _severity_tone(severity),
        }
    )
    return next_event


def _task_message(event: dict, *, fallback: str) -> str:
    message = str(event.get("message") or "").strip()
    if not message or message in {"任务已自动开始", "任务已按时间开始"}:
        return fallback
    return message


def _observation_message(payload: dict, *, fallback: str) -> str:
    observation = _json_dict(payload.get("observation"))
    reason = str(observation.get("reason") or "")
    evidence = _json_dict(observation.get("evidence"))
    if evidence.get("hasPerson") is False or evidence.get("has_person") is False:
        return "暂时没在画面里看到孩子，还不能确认开始。"
    if reason in {"unsupported", "insufficient", "observation_unavailable", "unavailable"}:
        return "这次画面还不能确认孩子动作。"
    if reason == "child_not_present":
        return "暂时没在画面里看到孩子。"
    return fallback


def _evidence_summary(event: dict) -> str:
    payload = _json_dict(event.get("payload"))
    observation = _json_dict(payload.get("observation"))
    evidence = _json_dict(observation.get("evidence"))
    if evidence.get("hasPerson") is False or evidence.get("has_person") is False:
        return "未看到孩子"
    verdict = str(observation.get("verdict") or "")
    if verdict == "started":
        return "看到开始"
    if verdict in {"insufficient", "unavailable"}:
        return "观察暂不可用"
    return ""


def _severity_tone(severity: str) -> str:
    return {
        "success": "success",
        "warning": "warning",
        "danger": "danger",
        "info": "info",
    }.get(severity, "info")


def _parent_event_dedupe_key(event: dict) -> str:
    task_id = str(event.get("taskId") or "")
    category = str(event.get("category") or event.get("eventType") or "")
    created_at = int(event.get("createdAt") or 0)
    bucket = created_at // 120000 if created_at else 0
    if task_id and category in {"camera_observation", "task_observation"}:
        return f"{task_id}:{category}:{event.get('eventType')}:{bucket}"
    return f"{event.get('source')}:{event.get('eventType')}:{event.get('id')}"


def _json_dict(value: object) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _command_title(command_type: str) -> str:
    return {
        "speak": "语音提醒",
        "snapshot": "看护快照",
        "start_monitor": "看护观察",
        "stop_monitor": "看护观察",
        "ptz_move": "云台控制",
    }.get(command_type, "摄像头操作")


def _task_event_title(event_type: str) -> str:
    return {
        "created": "任务创建",
        "updated": "任务调整",
        "started": "任务开始",
        "auto_started": "任务开始",
        "reminder_sent": "提醒已发送",
        "start_reminder_sent": "开始提醒",
        "end_reminder_sent": "结束提醒",
        "camera_observation": "看护观察",
        "completed": "任务完成",
        "confirmed": "家长确认",
        "rejected": "家长退回",
    }.get(event_type, "看护记录")


def _event_tone(status: str) -> str:
    if status == "succeeded":
        return "success"
    if status == "failed":
        return "warning"
    if status == "running":
        return "info"
    return "neutral"


def _camera_observation_display(observation: dict) -> dict:
    has_person = observation.get("hasPerson")
    activity = str(observation.get("activity") or "").strip()
    summary = str(observation.get("summary") or "").strip()
    is_reliable = bool(observation.get("isReliable"))
    if not is_reliable:
        return {
            "title": "画面待确认",
            "message": "这次画面还不能判断孩子状态。",
            "category": "camera_status",
            "severity": "warning",
            "evidence": "画面不可判断",
        }
    if has_person is False:
        return {
            "title": "暂未看到孩子",
            "message": "刚才的画面里没有看到孩子。",
            "category": "child_presence",
            "severity": "warning",
            "evidence": "未看到孩子",
        }
    if activity == "玩玩具" or "玩具" in summary:
        return {
            "title": "孩子正在玩玩具",
            "message": "这条记录来自摄像头画面。",
            "category": "camera_observation",
            "severity": "info",
            "evidence": "看到玩具活动",
        }
    if summary:
        return {
            "title": summary.rstrip("。"),
            "message": "这条记录来自摄像头画面。",
            "category": "camera_observation",
            "severity": "info",
            "evidence": "看到孩子",
        }
    if has_person is True:
        return {
            "title": "看到孩子在画面里",
            "message": "这条记录来自摄像头画面。",
            "category": "child_presence",
            "severity": "info",
            "evidence": "看到孩子",
        }
    return {
        "title": "画面待确认",
        "message": "这次画面还不能判断孩子状态。",
        "category": "camera_status",
        "severity": "warning",
        "evidence": "画面不可判断",
    }


def _ptz_direction_label(direction: str) -> str:
    return {
        "up": "上移",
        "down": "下移",
        "left": "左移",
        "right": "右移",
        "home": "回到中位",
    }.get(direction, "移动")
