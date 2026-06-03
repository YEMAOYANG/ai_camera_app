from __future__ import annotations

from flask import Blueprint, Response, current_app, jsonify, stream_with_context

from services.camera_bridge_service import CameraBridgeError, CameraBridgeService


camera_bp = Blueprint("camera", __name__)


def _camera_bridge() -> CameraBridgeService:
    return CameraBridgeService(current_app.config["CAMERA_BACKEND_URL"])


def _json_response(payload: dict):
    if payload["ok"]:
        return jsonify(payload)
    return jsonify(payload), 502


@camera_bp.get("/health")
def camera_health():
    return _json_response(_camera_bridge().health())


@camera_bp.get("/runtime")
def camera_runtime():
    return _json_response(_camera_bridge().runtime())


@camera_bp.get("/speaker/status")
def speaker_status():
    return _json_response(_camera_bridge().speaker_status())


@camera_bp.get("/snapshot")
def snapshot():
    try:
        result = _camera_bridge().fetch_snapshot()
        return Response(
            result.body,
            mimetype=result.content_type,
            headers={"Cache-Control": "no-store"},
        )
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status_code


@camera_bp.get("/stream")
def stream():
    try:
        upstream = _camera_bridge().open_stream()
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
