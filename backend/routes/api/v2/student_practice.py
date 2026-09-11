from __future__ import annotations

from flask import Blueprint, jsonify, request
from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import learning_practice_service

student_practice_bp = Blueprint('student_practice_v2', __name__)


@student_practice_bp.post('/sessions')
def start():
    try:
        return jsonify(learning_practice_service().start(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@student_practice_bp.get('/sessions/<session_id>')
def current(session_id):
    try:
        return jsonify(learning_practice_service().get(bearer_token(request), session_id))
    except ApiError as exc:
        return error_response(exc)


@student_practice_bp.post('/sessions/<session_id>/answers')
def answer(session_id):
    try:
        return jsonify(learning_practice_service().answer(bearer_token(request), session_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)
