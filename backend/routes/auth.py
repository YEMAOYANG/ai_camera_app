from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from services.auth_store import AuthError, AuthStore


auth_bp = Blueprint("auth", __name__)


def _store() -> AuthStore:
    return AuthStore(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
    )


def _json() -> dict:
    return request.get_json(silent=True) or {}


def _bearer_token() -> str:
    value = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return value[len(prefix) :].strip() if value.startswith(prefix) else ""


def _error(exc: AuthError):
    return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status_code


@auth_bp.post("/sms/request")
def request_sms_code():
    try:
        result = _store().request_sms_code(_json().get("phone", ""))
        return jsonify(
            {
                "ok": True,
                "codeSent": True,
                "expiresAt": result["expiresAt"],
                "debugCode": result["debugCode"],
                "message": "验证码已发送",
            }
        )
    except AuthError as exc:
        return _error(exc)


@auth_bp.post("/sms/login")
def login_with_sms():
    data = _json()
    try:
        return jsonify(_store().login_with_sms(data.get("phone", ""), data.get("code", "")))
    except AuthError as exc:
        return _error(exc)


@auth_bp.post("/token/refresh")
def refresh_token():
    try:
        return jsonify(_store().refresh(_json().get("refreshToken", "")))
    except AuthError as exc:
        return _error(exc)


@auth_bp.get("/session")
def current_session():
    try:
        return jsonify({"ok": True, **_store().authenticate(_bearer_token())})
    except AuthError as exc:
        return _error(exc)


@auth_bp.post("/logout")
def logout():
    data = _json()
    _store().logout(access_token=_bearer_token(), refresh_token=data.get("refreshToken"))
    return jsonify({"ok": True})
