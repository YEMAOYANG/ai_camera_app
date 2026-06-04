from __future__ import annotations

from flask import Blueprint, jsonify

from core.errors import ApiError, error_response
from services.service_factory import profile_service


legal_bp = Blueprint("legal", __name__)


@legal_bp.get("/user-agreement")
def user_agreement():
    return _document("user-agreement")


@legal_bp.get("/privacy-policy")
def privacy_policy():
    return _document("privacy-policy")


@legal_bp.get("/child-privacy-authorization")
def child_privacy_authorization():
    return _document("child-privacy-authorization")


def _document(key: str):
    try:
        return jsonify(profile_service().legal_document(key))
    except ApiError as exc:
        return error_response(exc)
