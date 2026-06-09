from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, client_device_payload, json_body
from services.service_factory import auth_service


auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/sms/request")
def request_sms_code():
    try:
        result = auth_service().request_sms_code(json_body(request).get("phone", ""))
        payload = {
            "ok": True,
            "codeSent": True,
            "expiresAt": result["expiresAt"],
            "provider": result["provider"],
            "templateId": result["templateId"],
            "deliveryStatus": result["deliveryStatus"],
            "message": "验证码已发送",
        }
        if result["debugCode"] is not None:
            payload["debugCode"] = result["debugCode"]
            print(
                f"[development-sms] phone={result['phone']} code={result['debugCode']}",
                flush=True,
            )
            current_app.logger.info(
                "Development SMS verification code phone=%s code=%s",
                result["phone"],
                result["debugCode"],
            )
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@auth_bp.post("/sms/login")
def login_with_sms():
    data = json_body(request)
    try:
        return jsonify(
            auth_service().login_with_sms(
                data.get("phone", ""),
                data.get("code", ""),
                client_device_payload(request, data),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@auth_bp.post("/token/refresh")
def refresh_token():
    data = json_body(request)
    try:
        return jsonify(
            auth_service().refresh(
                data.get("refreshToken", ""),
                client_device_payload(request, data),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@auth_bp.get("/session")
def current_session():
    try:
        return jsonify({"ok": True, **auth_service().authenticate(bearer_token(request))})
    except ApiError as exc:
        return error_response(exc)


@auth_bp.post("/logout")
def logout():
    data = json_body(request)
    try:
        auth_service().logout(
            access_token=bearer_token(request),
            refresh_token=data.get("refreshToken"),
        )
        return jsonify({"ok": True})
    except ApiError as exc:
        return error_response(exc)
