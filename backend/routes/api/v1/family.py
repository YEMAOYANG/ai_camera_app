from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


family_bp = Blueprint("family", __name__)


@family_bp.get("/members")
def list_members():
    try:
        return jsonify(profile_service().list_family_members(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/members")
def create_member():
    try:
        return jsonify(profile_service().create_family_member(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@family_bp.patch("/members/<member_id>")
def update_member(member_id: str):
    try:
        return jsonify(profile_service().update_family_member(bearer_token(request), member_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@family_bp.delete("/members/<member_id>")
def delete_member(member_id: str):
    try:
        return jsonify(profile_service().delete_family_member(bearer_token(request), member_id))
    except ApiError as exc:
        return error_response(exc)
