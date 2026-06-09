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


@account_bp.post("/sessions/<session_id>/revoke")
def revoke_session(session_id: str):
    try:
        return jsonify(profile_service().revoke_account_session(bearer_token(request), session_id))
    except ApiError as exc:
        return error_response(exc)


@account_bp.post("/deletion")
def request_deletion():
    try:
        return jsonify(
            profile_service().request_account_deletion(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@account_bp.post("/phone/code")
def request_phone_change_code():
    try:
        return jsonify(
            profile_service().request_account_phone_code(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@account_bp.patch("/phone")
def change_phone():
    try:
        return jsonify(
            profile_service().change_account_phone(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
