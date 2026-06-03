from __future__ import annotations

from flask import Blueprint, Response, jsonify, stream_with_context

from core.errors import ApiError, error_response
from services.camera_bridge_service import CameraBridgeError, CameraBridgeService
from services.service_factory import camera_bridge_service


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
