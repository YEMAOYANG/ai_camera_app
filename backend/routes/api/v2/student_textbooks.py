from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import textbook_learning_service

student_textbooks_bp = Blueprint("student_textbooks", __name__)
parent_textbooks_bp = Blueprint("parent_textbooks", __name__)


@student_textbooks_bp.get("")
def catalog():
    try:
        return jsonify(textbook_learning_service().student_catalog(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@student_textbooks_bp.get("/<edition_id>/contents")
def contents(edition_id):
    try:
        return jsonify(textbook_learning_service().student_contents(bearer_token(request), edition_id, request.args))
    except ApiError as exc:
        return error_response(exc)


@parent_textbooks_bp.get("/<child_id>/textbooks")
def parent_catalog(child_id):
    try:
        return jsonify(textbook_learning_service().parent_catalog(bearer_token(request), child_id))
    except ApiError as exc:
        return error_response(exc)


@parent_textbooks_bp.put("/<child_id>/textbooks")
def select(child_id):
    try:
        return jsonify(textbook_learning_service().parent_select(bearer_token(request), child_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)
