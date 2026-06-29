from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import conversation_service, profile_service


conversation_bp = Blueprint("conversation", __name__)


@conversation_bp.get("/policy")
def conversation_policy():
    try:
        device_id = str(request.args.get("deviceId") or "").strip() or None
        return jsonify(
            conversation_service().policy_for_token(
                bearer_token(request),
                device_id=device_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@conversation_bp.post("/chat")
def conversation_chat():
    try:
        data = json_body(request)
        return jsonify(
            conversation_service().chat_for_token(
                bearer_token(request),
                data,
            )
        )
    except ApiError as exc:
        return error_response(exc)
