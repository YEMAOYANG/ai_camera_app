from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import profile_service


profile_bp = Blueprint("profile", __name__)


@profile_bp.get("/summary")
def summary():
    try:
        return jsonify(profile_service().summary(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
