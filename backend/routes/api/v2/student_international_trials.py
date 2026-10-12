"""Authenticated, read-only readiness for the requested international books."""
from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.international_textbook_trial_service import InternationalTextbookTrialService
from services.service_factory import student_auth_service


student_international_trials_bp = Blueprint("student_international_trials", __name__)


@student_international_trials_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


@student_international_trials_bp.get("")
def catalog():
    try:
        service = InternationalTextbookTrialService(student_auth=student_auth_service())
        return jsonify(service.catalog(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)
