from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.auth_service import AuthService
from services.point_service import PointService
from services.sms_provider import MockSmsProvider


points_bp = Blueprint("points", __name__)


def _auth_service() -> AuthService:
    return AuthService(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
        sms_provider=MockSmsProvider(current_app.config["AUTH_DEV_SMS_CODE"]),
    )


def _point_service() -> PointService:
    return PointService(current_app.config["AUTH_DB_PATH"], auth_service=_auth_service())


@points_bp.get("/account")
def account():
    try:
        return jsonify(
            _point_service().account(
                bearer_token(request),
                child_id=request.args.get("childId"),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@points_bp.get("/ledger")
def ledger():
    try:
        return jsonify(
            _point_service().ledger(
                bearer_token(request),
                child_id=request.args.get("childId"),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@points_bp.post("/adjust")
def adjust():
    try:
        return jsonify(_point_service().adjust(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)
