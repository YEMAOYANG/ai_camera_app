from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.auth_service import AuthService
from services.firmware_service import FirmwareService
from services.sms_provider import MockSmsProvider


firmware_bp = Blueprint("firmware", __name__)


def _auth_service() -> AuthService:
    return AuthService(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
        sms_provider=MockSmsProvider(current_app.config["AUTH_DEV_SMS_CODE"]),
    )


def _firmware_service() -> FirmwareService:
    return FirmwareService(current_app.config["AUTH_DB_PATH"], auth_service=_auth_service())


@firmware_bp.get("/devices/<device_id>/status")
def device_firmware_status(device_id: str):
    try:
        return jsonify(_firmware_service().device_status(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@firmware_bp.get("/packages")
def packages():
    try:
        return jsonify(_firmware_service().packages(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@firmware_bp.post("/jobs")
def create_job():
    try:
        return jsonify(_firmware_service().create_job(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)
