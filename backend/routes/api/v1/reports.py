from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import profile_service


reports_bp = Blueprint("reports", __name__)
growth_bp = Blueprint("growth", __name__)


@reports_bp.get("/daily")
def daily():
    try:
        return jsonify(profile_service().daily_report(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@reports_bp.get("/weekly")
def weekly():
    try:
        return jsonify(profile_service().weekly_report(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@growth_bp.get("/moments")
def moments():
    try:
        return jsonify(profile_service().growth_moments(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
