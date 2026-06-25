from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import camera_command_service, device_service


devices_bp = Blueprint("devices", __name__)


@devices_bp.get("")
def list_devices():
    try:
        return jsonify(device_service().list_devices(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.post("")
def bind_device():
    try:
        return jsonify(device_service().bind_device(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/default")
def default_device():
    try:
        return jsonify(device_service().default_device(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.post("/discovery-status")
def discovery_status():
    try:
        return jsonify(device_service().discovery_status(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>")
def get_device(device_id: str):
    try:
        return jsonify(device_service().get_device(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>/runtime-config")
def get_runtime_config(device_id: str):
    try:
        return jsonify(device_service().get_runtime_config(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.put("/<device_id>/runtime-config")
def update_runtime_config(device_id: str):
    try:
        return jsonify(
            device_service().update_runtime_config(
                bearer_token(request),
                device_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@devices_bp.patch("/<device_id>")
def update_device(device_id: str):
    try:
        return jsonify(device_service().update_device(bearer_token(request), device_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.post("/<device_id>/rename")
def rename_device(device_id: str):
    try:
        return jsonify(device_service().rename_device(bearer_token(request), device_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.post("/<device_id>/set-default")
def set_default_device(device_id: str):
    try:
        return jsonify(device_service().set_default_device(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.post("/<device_id>/unbind")
def unbind_device(device_id: str):
    try:
        return jsonify(device_service().unbind_device(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.get("/<device_id>/status")
def device_status(device_id: str):
    try:
        return jsonify(device_service().device_status(bearer_token(request), device_id))
    except ApiError as exc:
        return error_response(exc)


@devices_bp.post("/<device_id>/commands")
def device_command(device_id: str):
    try:
        return jsonify(
            camera_command_service().device_command(
                bearer_token(request),
                device_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
