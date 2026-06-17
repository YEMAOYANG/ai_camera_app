from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import camera_ai_observation_service, internal_request_guard


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
