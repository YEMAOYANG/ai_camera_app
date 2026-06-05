from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import profile_service


subscription_bp = Blueprint("subscription", __name__)
subscriptions_bp = Blueprint("subscriptions", __name__)


@subscription_bp.get("/status")
def status():
    try:
        return jsonify(profile_service().subscription_status(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@subscriptions_bp.get("/plans")
def plans():
    try:
        return jsonify(profile_service().subscription_plans(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@subscriptions_bp.get("/current")
def current():
    try:
        return jsonify(profile_service().subscription_current(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@subscriptions_bp.get("/entitlements")
def entitlements():
    try:
        return jsonify(profile_service().subscription_entitlements(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)


@subscriptions_bp.post("/checkout-session")
def checkout_session():
    try:
        return jsonify(
            profile_service().subscription_checkout_session(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@subscriptions_bp.post("/restore")
def restore():
    try:
        return jsonify(profile_service().subscription_restore(bearer_token(request)))
    except ApiError as exc:
        return error_response(exc)
