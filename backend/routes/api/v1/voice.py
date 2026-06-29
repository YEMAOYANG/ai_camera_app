from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import voice_runtime_service


voice_bp = Blueprint("voice", __name__)


@voice_bp.get("/runtime")
def voice_runtime():
    try:
        device_id = str(request.args.get("deviceId") or "").strip() or None
        return jsonify(
            voice_runtime_service().runtime_for_token(
                bearer_token(request),
                device_id=device_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)
