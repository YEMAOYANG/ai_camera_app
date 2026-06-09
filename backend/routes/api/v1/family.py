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


@family_bp.post("/members/<member_id>/transfer-admin")
def transfer_admin(member_id: str):
    try:
        return jsonify(profile_service().transfer_family_admin(bearer_token(request), member_id))
    except ApiError as exc:
        return error_response(exc)


@family_bp.delete("/members/<member_id>")
def delete_member(member_id: str):
    try:
        return jsonify(profile_service().delete_family_member(bearer_token(request), member_id))
    except ApiError as exc:
        return error_response(exc)


@family_bp.get("/invitations")
def list_invitations():
    try:
        return jsonify(profile_service().list_family_invitations(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/invitations")
def create_invitation():
    try:
        return jsonify(
            profile_service().create_family_invitation(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/invitations/<invitation_id>/resend")
def resend_invitation(invitation_id: str):
    try:
        return jsonify(
            profile_service().resend_family_invitation(
                bearer_token(request),
                invitation_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/invitations/<invitation_id>/cancel")
def cancel_invitation(invitation_id: str):
    try:
        return jsonify(
            profile_service().cancel_family_invitation(
                bearer_token(request),
                invitation_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/invitations/<invitation_id>/accept")
def accept_invitation(invitation_id: str):
    try:
        return jsonify(
            profile_service().accept_family_invitation(
                bearer_token(request),
                invitation_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/invitations/<invitation_id>/decline")
def decline_invitation(invitation_id: str):
    try:
        return jsonify(
            profile_service().decline_family_invitation(
                bearer_token(request),
                invitation_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@family_bp.get("/code")
def family_code():
    try:
        return jsonify(profile_service().family_code(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/code/reset")
def reset_family_code():
    try:
        return jsonify(profile_service().reset_family_code(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/join-code/preview")
def preview_join_code():
    try:
        return jsonify(
            profile_service().preview_join_code(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@family_bp.post("/join-code/accept")
def accept_join_code():
    try:
        return jsonify(
            profile_service().accept_join_code(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
