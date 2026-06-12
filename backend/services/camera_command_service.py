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


class CameraCommandService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        camera_service: CameraBridgeService,
    ):
        database = Database(database_url)
        self.repository = CameraCommandRepository(database)
        self.device_repository = DeviceRepository(database)
        self.auth_service = auth_service
        self.camera_service = camera_service

    def speak(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        text = self._required_text(data, "text", "请输入要提醒孩子的话")
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="speak",
                request_payload={"text": text},
                runner=lambda: self.camera_service.speak(text),
                device_id=self._optional_text(data, "deviceId"),
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def snapshot(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="snapshot",
                request_payload={},
                runner=lambda: {
                    "ok": True,
                    "contentType": self.camera_service.fetch_snapshot().content_type,
                },
                device_id=self._optional_text(data, "deviceId"),
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def ptz_move(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        direction = self._ptz_direction(data.get("direction"))
        step = self._ptz_step(data.get("step"))
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="ptz_move",
                request_payload={"direction": direction, "step": step},
                runner=lambda: self.camera_service.ptz_move(direction, step),
                device_id=self._optional_text(data, "deviceId"),
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def monitor_start(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="start_monitor",
                request_payload={},
                runner=self.camera_service.start_monitor,
                device_id=self._optional_text(data, "deviceId"),
                task_id=self._optional_text(data, "taskId"),
            ),
        }

    def monitor_stop(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        return {
            "ok": True,
            "command": self._execute_command(
                family_id=context["family"]["id"],
                command_type="stop_monitor",
                request_payload={},
                runner=self.camera_service.stop_monitor,
                device_id=self._optional_text(data, "deviceId"),
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

    def recent_events(self, access_token: str, args) -> dict:
        context = self.auth_service.authenticate(access_token)
        limit = self._limit_arg(args.get("limit") if args else None)
        with self.repository.transaction() as conn:
            commands = self.repository.list_recent_commands(
                conn,
                family_id=context["family"]["id"],
                limit=limit,
            )
            task_events = self.repository.list_recent_task_events(
                conn,
                family_id=context["family"]["id"],
                limit=limit,
            )
        events = [
            *(_camera_command_event_payload(row) for row in commands),
            *(_task_event_payload(row) for row in task_events),
        ]
        events.sort(key=lambda item: (item["createdAt"], item["id"]), reverse=True)
        return {"ok": True, "events": events[:limit]}

    def internal_speak(
        self,
        *,
        family_id: str,
        text: str,
        task_id: str | None = None,
        device_id: str | None = None,
    ) -> dict:
        return self._execute_command(
            family_id=family_id,
            command_type="speak",
            request_payload={"text": text},
            runner=lambda: self.camera_service.speak(text),
            task_id=task_id,
            device_id=device_id,
        )

    def internal_start_monitor(
        self,
        *,
        family_id: str,
        task_id: str | None = None,
        device_id: str | None = None,
    ) -> dict:
        return self._execute_command(
            family_id=family_id,
            command_type="start_monitor",
            request_payload={},
            runner=self.camera_service.start_monitor,
            task_id=task_id,
            device_id=device_id,
        )

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
        "title": _command_title(command_type),
        "message": message,
        "status": status,
        "tone": _event_tone(status),
        "createdAt": row.get("completed_at") or row.get("updated_at") or row["created_at"],
        "payload": {"request": request, "response": response},
    }


def _task_event_payload(row) -> dict:
    event_type = str(row.get("event_type") or "")
    return {
        "id": row["id"],
        "source": "task_event",
        "eventType": event_type,
        "title": _task_event_title(event_type),
        "message": row.get("message") or _task_event_title(event_type),
        "status": "recorded",
        "tone": "info",
        "createdAt": row["created_at"],
        "payload": _json_dict(row.get("payload")),
    }


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
        "start_monitor": "开始观察",
        "stop_monitor": "停止观察",
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
    }.get(event_type, "任务事件")


def _event_tone(status: str) -> str:
    if status == "succeeded":
        return "success"
    if status == "failed":
        return "warning"
    if status == "running":
        return "info"
    return "neutral"


def _ptz_direction_label(direction: str) -> str:
    return {
        "up": "上移",
        "down": "下移",
        "left": "左移",
        "right": "右移",
        "home": "回到中位",
    }.get(direction, "移动")
