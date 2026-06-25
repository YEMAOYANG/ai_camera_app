from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, stream_with_context

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.camera_bridge_service import CameraBridgeError
from services.service_factory import auth_service, camera_command_service, device_runtime_resolver, task_service
from services.task_event_stream import (
    CAMERA_MONITOR_REFRESHED,
    CAMERA_OBSERVATION_UPDATED,
    publish_family_event,
)


camera_bp = Blueprint("camera", __name__)


def _json_response(payload: dict):
    if payload["ok"]:
        return jsonify(payload)
    return jsonify(payload), 502


def _resolve_camera_runtime_for_request():
    access_token = bearer_token(request)
    context = auth_service().authenticate(access_token)
    device_id = str(request.args.get("deviceId") or "").strip() or None
    resolved = device_runtime_resolver().resolve(
        family_id=context["family"]["id"],
        device_id=device_id,
    )
    return access_token, context, resolved


@camera_bp.get("/health")
def camera_health():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return _json_response(resolved.bridge.health())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/status")
def camera_status():
    try:
        access_token, _, resolved = _resolve_camera_runtime_for_request()
        current_task = task_service().current_in_progress(
            access_token,
            device_id=resolved.device_id,
            include_unassigned=bool((resolved.device or {}).get("is_default")),
        )
        return jsonify(resolved.bridge.status(current_task=current_task))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/runtime")
def camera_runtime():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return _json_response(resolved.bridge.runtime())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/speaker/status")
def speaker_status():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return _json_response(resolved.bridge.speaker_status())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/snapshot")
def snapshot():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        result = resolved.bridge.fetch_snapshot()
        return Response(
            result.body,
            mimetype=result.content_type,
            headers={"Cache-Control": "no-store"},
        )
    except CameraBridgeError as exc:
        return Response(
            status=204,
            headers={
                "Cache-Control": "no-store",
                "X-Mira-Snapshot-Status": "unavailable",
                "X-Mira-Snapshot-Error": exc.code,
                "X-Mira-Snapshot-Message": "snapshot_unavailable",
            },
        )
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/stream")
def stream():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        upstream = resolved.bridge.open_stream()
        content_type = upstream.headers.get("content-type", "multipart/x-mixed-replace")

        def generate():
            with upstream:
                while True:
                    chunk = upstream.read(8192)
                    if not chunk:
                        break
                    yield chunk

        return Response(
            stream_with_context(generate()),
            content_type=content_type,
            headers={"Cache-Control": "no-store"},
        )
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/webrtc/session")
def webrtc_session():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return jsonify(resolved.bridge.webrtc_session())
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": "实时画面暂时无法连接，请稍后再试。"}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/webrtc/offer")
def webrtc_offer():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        data = json_body(request)
        offer_sdp = str(data.get("sdp") or "").strip()
        if not offer_sdp:
            return jsonify({"ok": False, "error": "invalid_webrtc_offer", "message": "实时画面连接信息不完整。"}), 400
        return jsonify(resolved.bridge.webrtc_offer(offer_sdp))
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": "实时画面暂时无法连接，请稍后再试。"}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/commands/speak")
def speak_command():
    try:
        return jsonify(camera_command_service().speak(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/commands/snapshot")
def snapshot_command():
    try:
        return jsonify(camera_command_service().snapshot(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/commands/ptz")
def ptz_command():
    try:
        return jsonify(camera_command_service().ptz_move(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/monitor/start")
def monitor_start():
    try:
        return jsonify(camera_command_service().monitor_start(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/monitor/stop")
def monitor_stop():
    try:
        return jsonify(camera_command_service().monitor_stop(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/monitor/status")
def monitor_status():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        payload = resolved.bridge.monitor_status()
        return jsonify(_monitor_response(payload))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/monitor/refresh")
def monitor_refresh():
    try:
        _, context, resolved = _resolve_camera_runtime_for_request()
        payload = resolved.bridge.refresh_monitor_observation()
        response = _monitor_response(payload)
        observation = response["monitor"].get("lastObservation")
        is_reliable = bool(observation.get("isReliable")) if isinstance(observation, dict) else False
        publish_family_event(
            family_id=context["family"]["id"],
            event_type=CAMERA_MONITOR_REFRESHED,
            device_id=resolved.device_id,
            is_reliable=is_reliable,
            source="camera_monitor",
        )
        publish_family_event(
            family_id=context["family"]["id"],
            event_type=CAMERA_OBSERVATION_UPDATED,
            device_id=resolved.device_id,
            observation_id=_observation_id(observation),
            is_reliable=is_reliable,
            source="camera_monitor",
        )
        return jsonify(response)
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/events")
def camera_events():
    try:
        access_token, _, resolved = _resolve_camera_runtime_for_request()
        return jsonify(
            camera_command_service().recent_events(
                access_token,
                request.args,
                device_id=resolved.device_id,
                include_unassigned=bool((resolved.device or {}).get("is_default")),
            )
        )
    except ApiError as exc:
        return error_response(exc)


def _monitor_response(payload: dict) -> dict:
    runtime = payload.get("monitorRuntime") if isinstance(payload, dict) else {}
    data = runtime.get("data") if isinstance(runtime, dict) else {}
    status = data.get("monitor_runtime") if isinstance(data, dict) else {}
    if not isinstance(status, dict):
        status = data if isinstance(data, dict) else {}
    running = bool(status.get("running"))
    normalized = _normalize_monitor_observation(status.get("last_observation"))
    return {
        "ok": True,
        "monitor": {
            "running": running,
            "status": status.get("status") or status.get("state") or "unavailable",
            "lastObservation": normalized,
            "lastReminder": status.get("last_reminder") or "",
            "message": (
                "摄像头正在观察当前任务"
                if running
                else "当前没有进行中的观察"
            ),
        },
    }


def _normalize_monitor_observation(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    has_person_value = value.get("has_person", value.get("hasPerson"))
    has_person = has_person_value is True
    activity = _activity_label(value.get("activity") or value.get("raw_activity"))
    confidence = _float_or_zero(value.get("confidence"))
    observed_at = _int_or_zero(
        value.get("observedAt")
        or value.get("observed_at")
        or value.get("timestamp")
        or value.get("time")
    )
    summary = _summary_text(value, activity=activity, has_person_value=has_person_value)
    is_reliable = has_person and bool(activity) and confidence >= 0.65
    if not is_reliable and has_person_value is not False:
        if not activity or confidence < 0.65:
            summary = summary if summary and activity else ""
    return {
        "hasPerson": has_person,
        "activity": activity,
        "confidence": confidence,
        "observedAt": observed_at,
        "summary": summary,
        "isReliable": is_reliable,
        "source": "camera",
    }


def _summary_text(value: dict, *, activity: str, has_person_value: object) -> str:
    raw_summary = str(
        value.get("summary")
        or value.get("description")
        or value.get("child_message")
        or ""
    ).strip()
    if has_person_value is False:
        return "画面里暂时没看到孩子。"
    if activity:
        return f"看到孩子在{activity}。"
    if raw_summary and not _is_generic_activity(raw_summary):
        return raw_summary[:80]
    return ""


def _activity_label(value: object) -> str:
    activity = str(value or "").strip()
    if not activity or _is_generic_activity(activity):
        return ""
    return activity[:40]


def _is_generic_activity(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"其他", "未知", "无明显活动", "other", "unknown", "normal"}


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _observation_id(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("id", "observationId", "sourceEventId", "observedAt"):
        current = str(value.get(key) or "").strip()
        if current:
            return current[:255]
    return ""
