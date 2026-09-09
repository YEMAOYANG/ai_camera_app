from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import student_auth_service


parent_student_access_bp = Blueprint("parent_student_access_v2", __name__)


@parent_student_access_bp.get(
    "/children/<child_id>/student-access/authorizations"
)
def list_authorizations(child_id: str):
    try:
        return jsonify(
            student_auth_service().list_authorizations(
                bearer_token(request),
                child_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@parent_student_access_bp.delete(
    "/children/<child_id>/student-access/authorizations/<device_id>"
)
def revoke_authorization(child_id: str, device_id: str):
    try:
        return jsonify(
            student_auth_service().revoke_authorization(
                bearer_token(request),
                child_id,
                device_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@parent_student_access_bp.post(
    "/children/<child_id>/student-access/pin/reset"
)
def reset_pin(child_id: str):
    try:
        return jsonify(
            student_auth_service().reset_pin(
                bearer_token(request),
                child_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@parent_student_access_bp.get("/student-access/qr-challenges/<challenge_id>")
def preview_qr_challenge(challenge_id: str):
    try:
        return jsonify(
            student_auth_service().preview_qr_challenge(
                bearer_token(request),
                challenge_id,
                child_id=request.args.get("childId"),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@parent_student_access_bp.post(
    "/student-access/qr-challenges/<challenge_id>/approve"
)
def approve_qr_challenge(challenge_id: str):
    try:
        return jsonify(
            student_auth_service().approve_qr_challenge(
                bearer_token(request),
                challenge_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@parent_student_access_bp.post(
    "/student-access/qr-challenges/<challenge_id>/reject"
)
def reject_qr_challenge(challenge_id: str):
    try:
        return jsonify(
            student_auth_service().reject_qr_challenge(
                bearer_token(request),
                challenge_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@parent_student_access_bp.post(
    "/children/<child_id>/student-access/pairing-codes"
)
def create_pairing_code(child_id: str):
    try:
        return jsonify(
            student_auth_service().create_pairing_code(
                bearer_token(request),
                child_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
