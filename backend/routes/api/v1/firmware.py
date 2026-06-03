from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import firmware_service


firmware_bp = Blueprint("firmware", __name__)


@firmware_bp.get("/devices/<device_id>/status")
def device_firmware_status(device_id: str):
    try:
        return jsonify(firmware_service().device_status(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@firmware_bp.get("/packages")
def packages():
    try:
        return jsonify(firmware_service().packages(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@firmware_bp.post("/jobs")
def create_job():
    try:
        return jsonify(firmware_service().create_job(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)
