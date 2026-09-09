from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import student_auth_service


student_auth_bp = Blueprint("student_auth_v2", __name__)


@student_auth_bp.post("/auth/qr/challenges")
def create_qr_challenge():
    try:
        return jsonify(
            student_auth_service().create_qr_challenge(
                json_body(request),
                request_ip=request.remote_addr,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_auth_bp.post("/auth/qr/exchange")
def exchange_qr_challenge():
    try:
        payload = student_auth_service().exchange_qr_challenge(json_body(request))
        return jsonify(payload), 202 if payload.get("status") == "pending" else 200
    except ApiError as exc:
        return error_response(exc)


@student_auth_bp.post("/auth/pair")
def pair():
    try:
        return jsonify(student_auth_service().pair(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@student_auth_bp.post("/auth/unlock")
def unlock():
    try:
        return jsonify(student_auth_service().unlock(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@student_auth_bp.post("/auth/refresh")
def refresh():
    try:
        return jsonify(student_auth_service().refresh(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@student_auth_bp.post("/auth/logout")
def logout():
    try:
        return jsonify(
            student_auth_service().logout(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_auth_bp.get("/me")
def me():
    try:
        return jsonify(student_auth_service().me(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
