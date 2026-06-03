from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import AuthError, error_response
from schemas.auth import bearer_token, json_body
from services.auth_service import AuthService
from services.sms_provider import MockSmsProvider


auth_bp = Blueprint("auth", __name__)


def _auth_service() -> AuthService:
    return AuthService(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
        sms_provider=MockSmsProvider(current_app.config["AUTH_DEV_SMS_CODE"]),
    )


@auth_bp.post("/sms/request")
def request_sms_code():
    try:
        result = _auth_service().request_sms_code(json_body(request).get("phone", ""))
        return jsonify(
            {
                "ok": True,
                "codeSent": True,
                "expiresAt": result["expiresAt"],
                "debugCode": result["debugCode"],
                "provider": result["provider"],
                "templateId": result["templateId"],
                "deliveryStatus": result["deliveryStatus"],
                "message": "验证码已发送",
            }
        )
    except AuthError as exc:
        return error_response(exc)


@auth_bp.post("/sms/login")
def login_with_sms():
    data = json_body(request)
    try:
        return jsonify(_auth_service().login_with_sms(data.get("phone", ""), data.get("code", "")))
    except AuthError as exc:
        return error_response(exc)


@auth_bp.post("/token/refresh")
def refresh_token():
    try:
        return jsonify(_auth_service().refresh(json_body(request).get("refreshToken", "")))
    except AuthError as exc:
        return error_response(exc)


@auth_bp.get("/session")
def current_session():
    try:
        return jsonify({"ok": True, **_auth_service().authenticate(bearer_token(request))})
    except AuthError as exc:
        return error_response(exc)


@auth_bp.post("/logout")
def logout():
    data = json_body(request)
    _auth_service().logout(
        access_token=bearer_token(request),
        refresh_token=data.get("refreshToken"),
    )
    return jsonify({"ok": True})
