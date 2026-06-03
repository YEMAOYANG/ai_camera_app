from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import point_service


points_bp = Blueprint("points", __name__)


@points_bp.get("/account")
def account():
    try:
        return jsonify(
            point_service().account(
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
            point_service().ledger(
                bearer_token(request),
                child_id=request.args.get("childId"),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@points_bp.post("/adjust")
def adjust():
    try:
        return jsonify(point_service().adjust(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)
