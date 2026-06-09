from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import setup_service


setup_bp = Blueprint("setup", __name__)


@setup_bp.get("/status")
def status():
    try:
        return jsonify(setup_service().status(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/parent-identity")
def parent_identity():
    try:
        return jsonify(
            setup_service().save_parent_identity(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/device")
def device():
    try:
        return jsonify(setup_service().save_device(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/wifi")
def wifi():
    try:
        return jsonify(setup_service().save_wifi(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/child")
def child():
    try:
        return jsonify(setup_service().save_child(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/camera-name")
def camera_name():
    try:
        return jsonify(setup_service().save_camera_name(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/camera-name/intro")
def camera_name_intro():
    try:
        return jsonify(setup_service().camera_name_intro(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/camera-name/preview")
def camera_name_preview():
    try:
        return jsonify(setup_service().camera_name_preview(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/contacts")
def contacts():
    try:
        return jsonify(setup_service().save_contacts(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@setup_bp.post("/complete")
def complete():
    try:
        return jsonify(setup_service().complete(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
