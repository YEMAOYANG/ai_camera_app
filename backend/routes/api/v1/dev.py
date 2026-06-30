from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import (
    auth_service,
    camera_bridge_service,
    camera_command_service,
    routine_reminder_service,
    task_runtime_service,
)
from services.task_event_stream import publish_task_runtime_result, task_event_stream_status
from services.task_scheduler_runner import task_scheduler_status


dev_bp = Blueprint("dev", __name__)


@dev_bp.post("/tasks/scheduler/tick")
def scheduler_tick():
    try:
        _ensure_dev_enabled()
        result = task_runtime_service().tick()
        publish_task_runtime_result(result)
        return jsonify(result)
    except ApiError as exc:
        return error_response(exc)


@dev_bp.post("/care/routine-reminder/tick")
def routine_reminder_tick():
    try:
        _ensure_dev_enabled()
        data = json_body(request)
        now_value = data.get("now")
        now = None
        if now_value is not None:
            try:
                now = int(now_value)
            except (TypeError, ValueError):
                raise ApiError("invalid_now", "now 必须是毫秒时间戳。", 400)
        family_id = _optional_dev_id(data.get("familyId"))
        child_id = _optional_dev_id(data.get("childId"))
        device_id = _optional_dev_id(data.get("deviceId"))
        return jsonify(
            routine_reminder_service().tick(
                now=now,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@dev_bp.get("/tasks/scheduler/status")
def scheduler_status():
    try:
        _ensure_dev_enabled()
        return jsonify(
            {
                "ok": True,
                "scheduler": task_scheduler_status(),
                "taskStream": task_event_stream_status(),
            }
        )
    except ApiError as exc:
        return error_response(exc)


@dev_bp.post("/camera/test-speak")
def test_speak():
    try:
        _ensure_dev_enabled()
        data = json_body(request)
        text = str(data.get("text") or "看护提醒测试。").strip()
        command = camera_command_service()._execute_command(
            family_id="dev_family",
            command_type="speak",
            request_payload={"text": text},
            runner=lambda: camera_bridge_service().speak(text),
        )
        return jsonify({"ok": True, "command": command})
    except ApiError as exc:
        return error_response(exc)


@dev_bp.post("/camera/test-snapshot")
def test_snapshot():
    try:
        _ensure_dev_enabled()
        result = camera_bridge_service().fetch_snapshot()
        return jsonify({"ok": True, "contentType": result.content_type, "bytes": len(result.body)})
    except ApiError as exc:
        return error_response(exc)


def _ensure_dev_enabled() -> None:
    if current_app.config.get("APP_ENV") in {"development", "test"} and current_app.config.get(
        "DEV_ADAPTERS_ENABLED"
    ):
        auth_service().authenticate(bearer_token(request))
        return
    raise ApiError("dev_endpoint_not_available", "这个本地调试入口当前不可用。", 404)


def _optional_dev_id(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
