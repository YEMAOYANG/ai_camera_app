from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.auth_service import AuthService
from services.device_service import DeviceService
from services.sms_provider import MockSmsProvider


devices_bp = Blueprint("devices", __name__)


def _auth_service() -> AuthService:
    return AuthService(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
        sms_provider=MockSmsProvider(current_app.config["AUTH_DEV_SMS_CODE"]),
    )


def _device_service() -> DeviceService:
    return DeviceService(current_app.config["AUTH_DB_PATH"], auth_service=_auth_service())


@devices_bp.get("")
def list_devices():
    try:
        return jsonify(_device_service().list_devices(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>")
def get_device(device_id: str):
    try:
        return jsonify(_device_service().get_device(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>/status")
def device_status(device_id: str):
    try:
        return jsonify(_device_service().device_status(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)
