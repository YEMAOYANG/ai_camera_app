from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import device_service


devices_bp = Blueprint("devices", __name__)


@devices_bp.get("")
def list_devices():
    try:
        return jsonify(device_service().list_devices(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>")
def get_device(device_id: str):
    try:
        return jsonify(device_service().get_device(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>/status")
def device_status(device_id: str):
    try:
        return jsonify(device_service().device_status(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)
