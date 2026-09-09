from __future__ import annotations

import json
import re
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.camera_command_repository import CameraCommandRepository
from repositories.device_repository import DeviceRepository
from schemas.camera import camera_command_payload
from schemas.vision import observation_is_reliable
from services.auth_service import AuthService
from services.conversation_policy_service import ConversationPolicyService
from services.camera_bridge_service import CameraBridgeError, CameraBridgeService
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.parent_facing_copy import sanitize_parent_facing_observation
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
        self.database_url = database.database_url
        self.repository = CameraCommandRepository(database)
        self.device_repository = DeviceRepository(database)
        self.auth_service = auth_service
        self.runtime_resolver = runtime_resolver
        self.camera_service = camera_service or (runtime_resolver.global_bridge() if runtime_resolver else None)

    def speak(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        text = self._required_text(data, "text", "请输入要提醒孩子的话")
        task_id = self._optional_text(data, "taskId")
        if not task_id:
            with self.device_repository.transaction() as conn:
                decision = ConversationPolicyService(self.database_url).evaluate_speak_context(
                    conn,
                    family_id=context["family"]["id"],
                )
            if not decision.get("allowed"):
                raise ApiError(
                    "conversation_speak_blocked",
                    str(decision.get("message") or "当前不允许自由聊天播报。"),
                    409,
                )
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
        limit = self._limit_arg(args.get("limit") if args else 10)
        offset = self._offset_arg(args.get("offset") if args else None)
        with self.repository.transaction() as conn:
            page, has_more = _paginate_camera_care_events(
                conn,
                self.repository,
                family_id=context["family"]["id"],
                device_id=device_id,
                include_unassigned=include_unassigned,
                offset=offset,
                limit=limit,
            )
        return {"ok": True, "events": page, "hasMore": has_more}

    def record_observation_event(
        self,
        *,
        family_id: str,
        child_id: str | None,
        device_id: str,
        observation: dict,
    ) -> dict | None:
        if not _observation_is_reliable(observation):
            return None
        display = _camera_observation_display(observation)
        now = now_ms()
        candidate_event = lightweight_camera_event_from_observation(
            event_id="pending",
            device_id=device_id,
            observation=observation,
            now=now,
        )
        dedupe_key = _parent_event_dedupe_key(candidate_event)
        with self.repository.transaction() as conn:
            recent = self.repository.list_recent_commands(
                conn,
                family_id=family_id,
                device_id=device_id,
                limit=30,
            )
            for row in recent:
                if int(row.get("created_at") or 0) < now - 600_000:
                    continue
                if str(row.get("command_type") or "") != "camera_observation":
                    continue
                payload = _json_dict(row.get("request_payload"))
                existing = lightweight_camera_event_from_observation(
                    event_id=str(row.get("id") or ""),
                    device_id=device_id,
                    observation=payload.get("observation") if isinstance(payload.get("observation"), dict) else observation,
                    now=int(row.get("created_at") or now),
                )
                if _parent_event_dedupe_key(existing) == dedupe_key:
                    return camera_command_payload(row)
        payload = {
            "childId": child_id or "",
            "observation": observation,
            "displayTitle": display["title"],
            "displayMessage": display["message"],
            "category": display["category"],
            "severity": display["severity"],
            "evidenceSummary": _observation_evidence_summary(display["evidence"], observation),
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
            event=lightweight_camera_event_from_observation(
                event_id=command["id"],
                device_id=device_id,
                observation=observation,
                now=now,
            ),
        )
        return camera_command_payload(updated)

    def internal_speak(
        self,
        *,
        family_id: str,
        text: str,
        task_id: str | None = None,
        device_id: str | None = None,
        source: str | None = None,
        scenario: str | None = None,
        prompt_id: str | None = None,
        signal_type: str | None = None,
    ) -> dict:
        bridge, resolved_device_id = self._runtime_for_command(
            family_id=family_id,
            device_id=device_id,
        )
        request_payload = {"text": text}
        if source:
            request_payload["source"] = source
        if scenario:
            request_payload["scenario"] = scenario
        if prompt_id:
            request_payload["promptId"] = prompt_id
        if signal_type:
            request_payload["signalType"] = signal_type
        return self._execute_command(
            family_id=family_id,
            command_type="speak",
            request_payload=request_payload,
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

    def internal_stop_monitor(
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
            command_type="stop_monitor",
            request_payload={},
            runner=bridge.stop_monitor,
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
            if _should_publish_camera_status(command_type, status) or _should_publish_care_reminder_event(
                command_type,
                status,
                request_payload,
            ):
                publish_family_event(
                    family_id=family_id,
                    event_type=CAMERA_STATUS_CHANGED,
                    device_id=device_id,
                    task_ids=[task_id] if task_id else [],
                    event_ids=[command_id],
                    source="camera_command",
                )
                realtime_event = None
                if command_type == "speak" and str(request_payload.get("source") or "") == "care_reminder":
                    scenario = str(request_payload.get("scenario") or "")
                    text = str(request_payload.get("text") or message or "").strip()
                    realtime_event = {
                        "id": command_id,
                        "deviceId": device_id or "",
                        "taskId": task_id or "",
                        "displayTitle": _care_reminder_title(
                            scenario,
                            prompt_id=str(request_payload.get("promptId") or ""),
                            signal_type=str(request_payload.get("signalType") or ""),
                        ),
                        "displayMessage": text or "摄像头已按看护规则轻声提醒。",
                        "category": "care_reminder",
                        "severity": "info" if status == "succeeded" else "warning",
                        "eventType": "speak",
                        "createdAt": now_ms(),
                        "observedAt": now_ms(),
                        "isReliable": status == "succeeded",
                        "source": "care_reminder",
                        "tone": "info" if status == "succeeded" else "warning",
                        "status": status,
                    }
                publish_family_event(
                    family_id=family_id,
                    event_type=CAMERA_EVENT_CREATED,
                    device_id=device_id,
                    task_ids=[task_id] if task_id else [],
                    event_ids=[command_id],
                    is_reliable=status == "succeeded",
                    source="camera_command",
                    event=realtime_event,
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
            limit = int(value if value is not None else 10)
        except (TypeError, ValueError):
            limit = 10
        return max(1, min(limit, 100))

    def _offset_arg(self, value: object) -> int:
        try:
            offset = int(value or 0)
        except (TypeError, ValueError):
            offset = 0
        return max(0, min(offset, 500))

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


def lightweight_camera_event_from_observation(
    *,
    event_id: str,
    device_id: str,
    observation: dict,
    now: int | None = None,
    event_type: str = "camera_observation",
    source: str = "camera_observation",
) -> dict:
    display = _camera_observation_display(observation)
    created_at = now if now is not None else now_ms()
    record_kind = _observation_record_kind(observation)
    payload = {
        "id": event_id,
        "deviceId": device_id,
        "displayTitle": display["title"],
        "displayMessage": display["message"],
        "category": display["category"],
        "severity": display["severity"],
        "eventType": event_type,
        "createdAt": created_at,
        "observedAt": observation.get("observedAt") or created_at,
        "isReliable": bool(observation.get("isReliable")),
        "source": source,
        "tone": "info",
        "status": "succeeded",
    }
    if record_kind:
        payload["recordKind"] = record_kind
    return payload


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


def _should_publish_care_reminder_event(command_type: str, status: str, request_payload: dict) -> bool:
    return (
        command_type == "speak"
        and status == "succeeded"
        and str(request_payload.get("source") or "") == "care_reminder"
    )


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


def _merged_recent_events(
    conn,
    repository,
    *,
    family_id: str,
    device_id: str | None,
    include_unassigned: bool,
    scan_limit: int,
) -> list[dict]:
    commands = repository.list_recent_commands(
        conn,
        family_id=family_id,
        device_id=device_id,
        limit=scan_limit,
    )
    task_events = repository.list_recent_task_events(
        conn,
        family_id=family_id,
        device_id=device_id,
        include_unassigned=include_unassigned,
        limit=scan_limit,
    )
    events = [
        *(_camera_command_event_payload(row) for row in commands),
        *(_task_event_payload(row) for row in task_events),
    ]
    events.sort(key=lambda item: (item["createdAt"], item["id"]), reverse=True)
    return events


def _camera_care_events_from_rows(events: list[dict]) -> list[dict]:
    parent_events = _parent_facing_events(events)
    return [event for event in parent_events if _is_camera_care_event(event)]


def _paginate_camera_care_events(
    conn,
    repository,
    *,
    family_id: str,
    device_id: str | None,
    include_unassigned: bool,
    offset: int,
    limit: int,
    max_scan: int = 500,
) -> tuple[list[dict], bool]:
    scan = max(40, (offset + limit + 1) * 4)
    camera_events: list[dict] = []
    while scan <= max_scan:
        camera_events = _camera_care_events_from_rows(
            _merged_recent_events(
                conn,
                repository,
                family_id=family_id,
                device_id=device_id,
                include_unassigned=include_unassigned,
                scan_limit=scan,
            )
        )
        if len(camera_events) >= offset + limit + 1:
            page = camera_events[offset : offset + limit]
            return page, True
        if scan >= max_scan:
            break
        scan = min(scan * 2, max_scan)
    page = camera_events[offset : offset + limit]
    has_more = len(camera_events) > offset + len(page)
    return page, has_more


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
        "care_reminder",
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
            display_title=_parent_display_text(data.get("displayTitle")) or display["title"],
            display_message=display["message"]
            or _parent_display_text(data.get("displayMessage")),
            category=str(data.get("category") or display["category"]),
            severity=str(data.get("severity") or display["severity"]),
            record_kind=_observation_record_kind(observation),
        )
    if event_type in {"start_monitor", "stop_monitor"}:
        return None
    if event_type == "speak":
        payload = _json_dict(event.get("payload"))
        request = _json_dict(payload.get("request"))
        if str(request.get("source") or "") == "care_reminder":
            text = str(request.get("text") or event.get("message") or "").strip()
            return _with_display(
                event,
                display_title=_care_reminder_title(
                    str(request.get("scenario") or ""),
                    prompt_id=str(request.get("promptId") or ""),
                    signal_type=str(request.get("signalType") or ""),
                ),
                display_message=text or "摄像头已按看护规则轻声提醒。",
                category="care_reminder",
                severity="info" if status == "succeeded" else "warning",
                record_kind="reminder",
            )
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
    record_kind: str = "",
) -> dict:
    next_event = dict(event)
    title = _parent_display_text(display_title) or "看护记录"
    message = _parent_display_text(display_message) or title
    next_event.update(
        {
            "displayTitle": title,
            "displayMessage": message,
            "category": category,
            "severity": severity,
            "taskTitle": task_title or event.get("taskTitle") or "",
            "evidenceSummary": _evidence_summary(event),
            "hasReplay": False,
            "title": title,
            "message": message,
            "tone": _severity_tone(severity),
        }
    )
    if record_kind:
        next_event["recordKind"] = record_kind
    return next_event


def _observation_record_kind(observation: dict) -> str:
    if str(observation.get("evidenceType") or "") == "routine_window":
        return "routine"
    if str(observation.get("source") or "") == "routine_reminder":
        return "routine"
    return "vision"


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
    response = _json_dict(payload.get("response"))
    request = _json_dict(payload.get("request"))
    explicit = str((response or request).get("evidenceSummary") or "").strip()
    if explicit:
        return _strip_confidence_text(explicit)
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
    if category in {
        "camera_observation",
        "child_presence",
        "care_reminder",
        "snapshot",
        "camera_status",
    }:
        title = _dedupe_text(event.get("displayTitle") or event.get("title"))
        if category in {"camera_observation", "child_presence"}:
            bucket = created_at // 600000 if created_at else 0
            return f"{event.get('deviceId')}:{category}:{title}:{bucket}"
        message = _dedupe_text(event.get("displayMessage") or event.get("message"))[:48]
        return f"{event.get('source')}:{event.get('eventType')}:{category}:{title}:{message}:{bucket}"
    return f"{event.get('source')}:{event.get('eventType')}:{event.get('id')}"


def _care_reminder_title(
    scenario: str,
    *,
    prompt_id: str = "",
    signal_type: str = "",
) -> str:
    signal = signal_type.strip().lower()
    prompt = prompt_id.strip().lower()
    if prompt == "reminder.toy_play_safety" or signal.startswith("toy_play_unsafe_"):
        return "已提醒玩玩具注意安全"
    if signal == "cleanup_done":
        return "玩具已收好"
    if signal == "cleanup_started":
        return "正在收纳玩具"
    return {
        "toy_cleanup": "已提醒收纳玩具",
        "posture": "已提醒调整坐姿",
        "meal_start": "已提醒开始用餐",
        "meal_habit": "已提醒用餐习惯",
        "nap_time": "已提醒午睡",
        "bedtime": "已提醒准备睡觉",
        "wake_up": "已提醒起床",
    }.get(scenario, "已轻声提醒")


def _dedupe_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


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
    summary = _parent_display_text(observation.get("summary"))
    description = _observation_description(observation)
    if summary and "玩具" in summary and _negated_toy_observation(description):
        summary = ""
    decision_reason = _parent_display_text(observation.get("decisionReason"))
    is_reliable = bool(observation.get("isReliable"))
    scenario = str(observation.get("scenario") or "").strip()
    try:
        confidence = float(observation.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if scenario == "transition" and has_person is not False and confidence >= 0.5:
        if summary and "看到孩子" in summary:
            title = "画面里看到孩子活动"
        else:
            title = "画面里有人活动"
        return {
            "title": title,
            "message": description or decision_reason or summary or title,
            "category": "child_presence",
            "severity": "info",
            "evidence": "画面恢复可见",
        }
    if not is_reliable:
        safe_message = _sanitize_unreliable_message(description, decision_reason)
        return {
            "title": "画面暂时看不清",
            "message": safe_message,
            "category": "camera_status",
            "severity": "warning",
            "evidence": "画面不可判断",
        }
    if has_person is False:
        message = _absent_display_message(description, decision_reason)
        return {
            "title": "暂未看到孩子",
            "message": message,
            "category": "child_presence",
            "severity": "warning",
            "evidence": "未看到孩子",
        }
    if str(observation.get("scenario") or "").strip() == "meal_habit":
        meal_title = _meal_habit_display_title(observation, summary)
        if meal_title:
            return {
                "title": meal_title,
                "message": description or decision_reason or summary or meal_title,
                "category": "camera_observation",
                "severity": "info",
                "evidence": "看到用餐情况",
            }
    if activity == "收玩具" or re.search(r"(收玩具|整理玩具|收拾玩具|收纳玩具)", description):
        return {
            "title": "孩子正在收纳玩具",
            "message": description or decision_reason or summary or "孩子正在收纳玩具。",
            "category": "camera_observation",
            "severity": "info",
            "evidence": "看到收纳动作",
        }
    if activity == "吃饭":
        return {
            "title": "孩子正在吃饭",
            "message": description or decision_reason or summary or "孩子正在吃饭。",
            "category": "camera_observation",
            "severity": "info",
            "evidence": "看到用餐情况",
        }
    if (activity == "玩玩具" and not _negated_toy_observation(description)) or _positive_toy_observation(summary, description):
        return {
            "title": "孩子正在玩玩具",
            "message": description or decision_reason or "孩子正在玩玩具。",
            "category": "camera_observation",
            "severity": "info",
            "evidence": "看到玩具活动",
        }
    if summary and not _summary_contradicts_presence(summary, has_person, activity):
        return {
            "title": summary.rstrip("。"),
            "message": _safe_person_message(
                description,
                decision_reason,
                summary,
                has_person=has_person,
                activity=activity,
            ),
            "category": "camera_observation",
            "severity": "info",
            "evidence": "看到孩子",
        }
    if has_person is True:
        return {
            "title": "画面暂时无法判断",
            "message": description or decision_reason or "这次画面还不能判断孩子状态。",
            "category": "camera_observation",
            "severity": "info",
            "evidence": "画面不可判断",
        }
    return {
        "title": "画面暂时看不清",
        "message": "这次画面还不能判断孩子状态。",
        "category": "camera_status",
        "severity": "warning",
        "evidence": "画面不可判断",
    }


def _observation_description(observation: dict) -> str:
    for key in ("description", "displayMessage", "aiDescription"):
        value = _parent_display_text(observation.get(key))
        if value:
            return value[:180]
    raw_detail = _json_dict(observation.get("rawDetail"))
    for key in ("description", "child_message", "decision_reason"):
        value = _parent_display_text(raw_detail.get(key))
        if value:
            return value[:180]
    return ""


def _observation_evidence_summary(evidence: str, observation: dict) -> str:
    return _strip_confidence_text(evidence.strip())


def _strip_confidence_text(value: str) -> str:
    text = re.sub(r"(?:\s*·\s*)?可信度\s*\d+%", "", value or "")
    return text.strip(" ·")


def _absent_display_message(description: str, decision_reason: str) -> str:
    combined = f"{description} {decision_reason}".strip()
    if not combined:
        return "刚才的画面里没有看到孩子。"
    blocked = (
        "看屏幕",
        "看电视",
        "玩手机",
        "注视",
        "用眼距离",
        "玩玩具",
        "弹跳",
        "蹦床上",
        "孩子在",
        "宝宝在",
        "小朋友",
    )
    if any(token in combined for token in blocked):
        return "刚才的画面里没有看到孩子。"
    return combined[:180]


def _sanitize_unreliable_message(description: str, decision_reason: str) -> str:
    combined = f"{description} {decision_reason}".strip()
    if not combined:
        return "这次画面还不能判断孩子状态。"
    blocked = ("看屏幕", "看电视", "玩手机", "注视", "用眼距离")
    if any(token in combined for token in blocked):
        return "这次画面还不能判断孩子状态。"
    return combined[:180]


def _summary_contradicts_presence(summary: str, has_person: object, activity: str) -> bool:
    if has_person is False or activity == "离开":
        blocked = ("看屏幕", "看电视", "玩手机", "孩子在", "注视", "用眼距离", "弹跳", "蹦床上")
        return any(token in summary for token in blocked)
    return False


def _safe_person_message(
    description: str,
    decision_reason: str,
    summary: str,
    *,
    has_person: object,
    activity: str,
) -> str:
    if has_person is False or activity == "离开":
        return _absent_display_message(description, decision_reason)
    combined = f"{description} {decision_reason} {summary}".strip()
    blocked = ("看屏幕", "看电视", "用眼距离")
    if any(token in combined for token in blocked) and "暂未看到" in summary:
        return "这次画面还不能判断孩子状态。"
    return (description or decision_reason or summary or "这次画面还不能判断孩子状态。")[:180]


def _meal_habit_display_title(observation: dict, summary: str) -> str:
    raw_detail = _json_dict(observation.get("rawDetail"))
    issue = str(raw_detail.get("meal_etiquette_issue") or "").strip()
    activity = str(observation.get("activity") or raw_detail.get("activity") or "").strip()
    mapping = {
        "toys_on_table": "餐桌上有玩具",
        "standing": "用餐时未坐好",
        "distracted": "用餐时注意力离开",
    }
    if issue in mapping:
        return mapping[issue]
    if raw_detail.get("toys_on_table") is True:
        return "餐桌上有玩具"
    text = f"{summary} {observation.get('parentSummary') or ''} {raw_detail.get('description') or ''}"
    if "未坐" in text or "站" in text or "餐椅" in text:
        return "用餐时未坐好"
    if activity == "吃饭" or re.search(r"(进食|吃东西|拿食物|正在吃|用餐|吃饭)", text):
        if re.search(r"(玩玩具|玩积木|搭积木|玩具车|摆弄玩具)", text) and not re.search(
            r"(进食|吃东西|拿食物|正在吃|用餐|吃饭)", text
        ):
            return ""
        return "孩子正在吃饭"
    return ""


def _positive_toy_observation(summary: str, description: str) -> bool:
    text = f"{summary} {description}".strip().lower()
    if _negated_toy_observation(text):
        return False
    if re.search(r"(用餐|吃饭|餐桌|餐椅|进食|吃东西)", text) and not re.search(
        r"(玩玩具|玩积木|搭积木|摆弄玩具|操作玩具|playing with toys)", text
    ):
        return False
    return any(token in text for token in ("玩玩具", "玩积木", "搭积木", "摆弄玩具", "操作玩具", "playing with toys"))


def _negated_toy_observation(text: str) -> bool:
    return re.search(r"(没有|没|未|未见|看不到|没有看到)[^，。,.]{0,18}(玩具|积木|toy|toys)", text.lower()) is not None


def _observation_is_reliable(observation: dict) -> bool:
    if observation.get("isReliable") is not None:
        return bool(observation.get("isReliable"))
    has_person = observation.get("hasPerson", observation.get("has_person"))
    return observation_is_reliable(has_person=has_person, confidence=observation.get("confidence"))


def _parent_display_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if _looks_like_structured_payload(text):
        return ""
    return sanitize_parent_facing_observation(text)


def _looks_like_structured_payload(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return False
    starts_structured = compact.startswith(("{", "["))
    ends_structured = compact.endswith(("}", "]"))
    has_structured_keys = any(
        token in compact
        for token in ("'score'", '"score"', "'skills'", '"skills"', "{'name'", '"name"')
    )
    return has_structured_keys or (starts_structured and ends_structured)


def _ptz_direction_label(direction: str) -> str:
    return {
        "up": "上移",
        "down": "下移",
        "left": "左移",
        "right": "右移",
        "home": "回到中位",
    }.get(direction, "移动")
