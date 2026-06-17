from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import ai_care_reminder_service


reminders_bp = Blueprint("reminders", __name__)


@reminders_bp.get("/next")
def next_reminder():
    try:
        return jsonify(ai_care_reminder_service().next_reminder(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@reminders_bp.get("/events")
def reminder_events():
    try:
        return jsonify(ai_care_reminder_service().list_events(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@reminders_bp.post("/test")
def test_reminder():
    try:
        return jsonify(ai_care_reminder_service().test_reminder(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)
