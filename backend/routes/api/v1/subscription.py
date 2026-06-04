from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import profile_service


subscription_bp = Blueprint("subscription", __name__)


@subscription_bp.get("/status")
def status():
    try:
        return jsonify(profile_service().subscription_status(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
