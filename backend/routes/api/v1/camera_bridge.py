from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, stream_with_context

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.camera_bridge_service import CameraBridgeError
from services.service_factory import auth_service, camera_command_service, device_runtime_resolver, task_service


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
        status = payload.get("monitorRuntime", {}).get("data", {}).get("monitor_runtime") or {}
        return jsonify(
            {
                "ok": True,
                "monitor": {
                    "running": bool(status.get("running")),
                    "status": status.get("status") or "unavailable",
                    "lastObservation": status.get("last_observation"),
                    "lastReminder": status.get("last_reminder") or "",
                    "message": (
                        "摄像头正在观察当前任务"
                        if status.get("running")
                        else "当前没有进行中的观察"
                    ),
                },
            }
        )
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
