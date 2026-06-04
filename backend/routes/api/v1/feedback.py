from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


feedback_bp = Blueprint("feedback", __name__)


@feedback_bp.post("")
def create_feedback():
    try:
        return jsonify(profile_service().create_feedback(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)
