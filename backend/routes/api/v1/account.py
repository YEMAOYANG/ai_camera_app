from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


account_bp = Blueprint("account", __name__)


@account_bp.get("/profile")
def profile():
    try:
        return jsonify(profile_service().account_profile(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@account_bp.patch("/profile")
def update_profile():
    try:
        return jsonify(profile_service().update_account_profile(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@account_bp.get("/security")
def security():
    try:
        return jsonify(profile_service().account_security(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
