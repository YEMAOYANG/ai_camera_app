"""Internal accounting only; no endpoint can mint spending authorizations."""
from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from services.service_factory import internal_request_guard, learning_budget_service

internal_learning_budget_bp = Blueprint("internal_learning_budget", __name__)
_PREFIX = "/internal/learning/budget"
_FIELDS = {
    "authorization_context": {"authorizationId": "authorization_id"},
    "reserve": {"authorizationId": "authorization_id", "dispatchId": "dispatch_id",
        "requestSha256": "request_sha256", "priceKey": "price_key", "maxUnits": "max_units"},
    "dispatch": {"authorizationId": "authorization_id", "reservationId": "reservation_id",
        "requestSha256": "request_sha256"},
    "settle": {"authorizationId": "authorization_id", "reservationId": "reservation_id",
        "actualUnits": "actual_units", "providerRequestId": "provider_request_id", "evidenceSha256": "evidence_sha256"},
    "unknown": {"authorizationId": "authorization_id", "reservationId": "reservation_id", "reasonCode": "reason_code"},
    "release": {"authorizationId": "authorization_id", "reservationId": "reservation_id", "reasonCode": "reason_code"},
}


def _handle(operation):
    try:
        internal_request_guard().authorize(route=_PREFIX + "/" + ("context" if operation == "authorization_context" else operation),
            headers=request.headers, source_ip=request.remote_addr)
        if request.args or (request.content_length or 0) > 16384:
            raise ApiError("learning_budget_invalid_request", "预算请求格式错误。", 400)
        service = learning_budget_service()
        if operation == "status":
            result = service.status()
        else:
            body = request.get_json(silent=True)
            fields = _FIELDS[operation]
            if not isinstance(body, dict) or set(body) != set(fields):
                raise ApiError("learning_budget_invalid_request", "预算请求字段错误。", 400)
            result = getattr(service, operation)(**{fields[key]: value for key, value in body.items()})
        response = jsonify({"ok": True, "budget": result})
        response.headers["Cache-Control"] = "no-store"
        return response
    except ApiError as exc:
        return error_response(exc)
    except (ValueError, TypeError, KeyError):
        return error_response(ApiError("learning_budget_invalid_request", "预算计量或策略无效。", 400))


@internal_learning_budget_bp.get("/status")
def status():
    return _handle("status")


@internal_learning_budget_bp.post("/context")
def authorization_context():
    return _handle("authorization_context")


@internal_learning_budget_bp.post("/reserve")
def reserve():
    return _handle("reserve")


@internal_learning_budget_bp.post("/dispatch")
def dispatch():
    return _handle("dispatch")


@internal_learning_budget_bp.post("/settle")
def settle():
    return _handle("settle")


@internal_learning_budget_bp.post("/unknown")
def unknown():
    return _handle("unknown")


@internal_learning_budget_bp.post("/release")
def release():
    return _handle("release")
