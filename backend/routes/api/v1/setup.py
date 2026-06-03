from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.auth_service import AuthService
from services.setup_service import SetupService
from services.sms_provider import MockSmsProvider


setup_bp = Blueprint("setup", __name__)


def _auth_service() -> AuthService:
    return AuthService(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
        sms_provider=MockSmsProvider(current_app.config["AUTH_DEV_SMS_CODE"]),
    )


def _setup_service() -> SetupService:
    return SetupService(
        current_app.config["AUTH_DB_PATH"],
        auth_service=_auth_service(),
    )


@setup_bp.get("/status")
def status():
    try:
        return jsonify(_setup_service().status(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/parent-identity")
def parent_identity():
    try:
        return jsonify(
            _setup_service().save_parent_identity(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/device")
def device():
    try:
        return jsonify(_setup_service().save_device(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/wifi")
def wifi():
    try:
        return jsonify(_setup_service().save_wifi(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/child")
def child():
    try:
        return jsonify(_setup_service().save_child(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/contacts")
def contacts():
    try:
        return jsonify(_setup_service().save_contacts(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/complete")
def complete():
    try:
        return jsonify(_setup_service().complete(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
