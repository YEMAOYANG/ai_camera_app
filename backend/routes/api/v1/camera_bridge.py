from __future__ import annotations

from flask import Blueprint, Response, jsonify, request, stream_with_context

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.camera_bridge_service import CameraBridgeError, CameraBridgeService
from services.service_factory import auth_service, camera_bridge_service, camera_command_service, task_service


camera_bp = Blueprint("camera", __name__)


def _json_response(payload: dict):
    if payload["ok"]:
        return jsonify(payload)
    return jsonify(payload), 502


@camera_bp.get("/health")
def camera_health():
    try:
        return _json_response(camera_bridge_service().health())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/status")
def camera_status():
    try:
        access_token = bearer_token(request)
        current_task = task_service().current_in_progress(access_token)
        return jsonify(camera_bridge_service().status(current_task=current_task))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/runtime")
def camera_runtime():
    try:
        return _json_response(camera_bridge_service().runtime())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/speaker/status")
def speaker_status():
    try:
        return _json_response(camera_bridge_service().speaker_status())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/snapshot")
def snapshot():
    try:
        auth_service().authenticate(bearer_token(request))
        result = camera_bridge_service().fetch_snapshot()
        return Response(
            result.body,
            mimetype=result.content_type,
            headers={"Cache-Control": "no-store"},
        )
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/stream")
def stream():
    try:
        auth_service().authenticate(bearer_token(request))
        upstream = camera_bridge_service().open_stream()
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
        auth_service().authenticate(bearer_token(request))
        return jsonify(camera_bridge_service().webrtc_session())
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": "实时画面暂时无法连接，请稍后再试。"}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/webrtc/offer")
def webrtc_offer():
    try:
        auth_service().authenticate(bearer_token(request))
        data = json_body(request)
        offer_sdp = str(data.get("sdp") or "").strip()
        if not offer_sdp:
            return jsonify({"ok": False, "error": "invalid_webrtc_offer", "message": "实时画面连接信息不完整。"}), 400
        return jsonify(camera_bridge_service().webrtc_offer(offer_sdp))
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
        auth_service().authenticate(bearer_token(request))
        payload = camera_bridge_service().monitor_status()
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
