from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


settings_bp = Blueprint("settings", __name__)


@settings_bp.get("/ai-care-rules")
def ai_care_rules():
    return _get_setting("ai-care-rules")


@settings_bp.patch("/ai-care-rules")
def update_ai_care_rules():
    return _update_setting("ai-care-rules")


@settings_bp.get("/notifications")
def notifications():
    return _get_setting("notifications")


@settings_bp.patch("/notifications")
def update_notifications():
    return _update_setting("notifications")


@settings_bp.get("/privacy")
def privacy():
    return _get_setting("privacy")


@settings_bp.patch("/privacy")
def update_privacy():
    return _update_setting("privacy")


@settings_bp.get("/conversation")
def conversation():
    return _get_setting("conversation")


@settings_bp.patch("/conversation")
def update_conversation():
    return _update_setting("conversation")


@settings_bp.get("/education")
def education():
    return _get_setting("education")


@settings_bp.patch("/education")
def update_education():
    return _update_setting("education")


def _get_setting(key: str):
    try:
        return jsonify(profile_service().get_setting(bearer_token(request), key))
    except ApiError as exc:
        return error_response(exc)


def _update_setting(key: str):
    try:
        return jsonify(profile_service().update_setting(bearer_token(request), key, json_body(request)))
    except ApiError as exc:
        return error_response(exc)
