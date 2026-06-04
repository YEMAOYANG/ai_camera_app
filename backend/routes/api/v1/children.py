from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


children_bp = Blueprint("children", __name__)


@children_bp.get("/current")
def current_child():
    try:
        return jsonify(profile_service().current_child(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@children_bp.patch("/<child_id>")
def update_child(child_id: str):
    try:
        return jsonify(profile_service().update_child(bearer_token(request), child_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)
