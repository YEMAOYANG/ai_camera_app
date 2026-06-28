from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import camera_ai_observation_service, camera_observe_service, internal_request_guard


internal_camera_observations_bp = Blueprint("internal_camera_observations", __name__)


@internal_camera_observations_bp.post("/observations")
def record_camera_observation():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/camera/observations",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("sourceEventId") or data.get("observationId") or "")[:255],
        )
        payload = camera_ai_observation_service().record_observation(data)
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@internal_camera_observations_bp.post("/observe")
def observe_camera_tick():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/camera/observe",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("deviceId") or "")[:255],
        )
        family_id = str(data.get("familyId") or "").strip()
        child_id = str(data.get("childId") or "").strip()
        device_id = str(data.get("deviceId") or "").strip()
        image_b64 = str(data.get("imageBase64") or "").strip()
        if not family_id or not child_id or not device_id or not image_b64:
            raise ApiError("invalid_observe_request", "observe 请求缺少必要字段。", 400)
        import base64

        image_bytes = base64.b64decode(image_b64)
        content_type = str(data.get("contentType") or "image/jpeg").strip() or "image/jpeg"
        result = camera_observe_service().run_tick(
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            image_bytes=image_bytes,
            content_type=content_type,
            source=str(data.get("source") or "internal_observe")[:128],
            force_analyze=bool(data.get("forceAnalyze")),
            window_start_ms=int(data.get("windowStartMs") or 0) or None,
            window_end_ms=int(data.get("windowEndMs") or 0) or None,
        )
        return jsonify(
            {
                "ok": True,
                "skipped": result.skipped,
                "skipReason": result.skip_reason,
                "posted": result.posted,
                "analysis": result.analysis,
                "response": result.response,
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)
