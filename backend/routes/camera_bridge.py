from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from flask import Blueprint, Response, current_app, jsonify


camera_bp = Blueprint("camera", __name__)


def _base_url() -> str:
    return str(current_app.config["CAMERA_BACKEND_URL"]).rstrip("/")


def _open(path: str, *, timeout: float = 3.0):
    url = f"{_base_url()}{path}"
    return urllib.request.urlopen(url, timeout=timeout)


def _json_proxy(path: str, *, timeout: float = 3.0):
    try:
        with _open(path, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return jsonify({"ok": True, "cameraBackend": {"reachable": True, "baseUrl": _base_url(), "data": payload}})
    except Exception as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "cameraBackend": {
                        "reachable": False,
                        "baseUrl": _base_url(),
                        "error": str(exc),
                    },
                }
            ),
            502,
        )


@camera_bp.get("/health")
def camera_health():
    return _json_proxy("/api/health")


@camera_bp.get("/runtime")
def camera_runtime():
    return _json_proxy("/api/voice/runtime")


@camera_bp.get("/speaker/status")
def speaker_status():
    return _json_proxy("/api/camera/speaker/status")


@camera_bp.get("/snapshot")
def snapshot():
    try:
        with _open("/api/camera/snapshot", timeout=8.0) as response:
            return Response(
                response.read(),
                mimetype=response.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "no-store"},
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        return jsonify({"ok": False, "error": "camera_snapshot_failed", "message": body}), exc.code
    except Exception as exc:
        return jsonify({"ok": False, "error": "camera_snapshot_failed", "message": str(exc)}), 502
