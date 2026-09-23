from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import internal_request_guard, textbook_learning_service

internal_textbooks_bp = Blueprint("internal_textbooks", __name__)


def authorize():
    internal_request_guard().authorize(route=request.path, headers=request.headers, source_ip=request.remote_addr)


@internal_textbooks_bp.post("/import")
def import_manifest():
    try:
        authorize()
        return jsonify(textbook_learning_service().import_manifest(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post("/prepare")
def prepare():
    try:
        authorize()
        return jsonify(textbook_learning_service().prepare(json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@internal_textbooks_bp.post("/bind-published")
def bind_published():
    try:
        authorize()
        return jsonify(textbook_learning_service().bind_published(json_body(request)))
    except ApiError as exc:
        return error_response(exc)
