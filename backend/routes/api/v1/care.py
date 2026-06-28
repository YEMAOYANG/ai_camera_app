from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import care_config_service


care_bp = Blueprint("care", __name__)


@care_bp.get("/capabilities")
def list_capabilities():
    try:
        return jsonify(care_config_service().list_capabilities(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@care_bp.patch("/capabilities")
def update_capabilities():
    try:
        return jsonify(care_config_service().update_capabilities(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@care_bp.get("/routine-windows")
def list_routine_windows():
    try:
        return jsonify(care_config_service().list_routine_windows(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@care_bp.put("/routine-windows")
def replace_routine_windows():
    try:
        return jsonify(care_config_service().replace_routine_windows(bearer_token(request), json_body(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@care_bp.get("/summary")
def care_summary():
    try:
        return jsonify(care_config_service().summary(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@care_bp.post("/parent-reviews/<review_id>/acknowledge")
def acknowledge_parent_review(review_id: str):
    try:
        return jsonify(care_config_service().acknowledge_parent_review(bearer_token(request), review_id))
    except ApiError as exc:
        return error_response(exc)
