from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import ai_care_reminder_service, internal_request_guard


internal_reminders_bp = Blueprint("internal_reminders", __name__)


@internal_reminders_bp.post("/trigger")
def trigger_reminder():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/reminders/trigger",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("reminderDecisionId") or data.get("sourceEventId") or "")[:255],
        )
        payload = ai_care_reminder_service().trigger_internal(data)
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)
