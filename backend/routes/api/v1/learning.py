from __future__ import annotations

from flask import Blueprint, jsonify, make_response, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import (
    learning_curriculum_preparation_service,
    learning_service,
)
from services.learning_curriculum_preparation_contract import (
    PREPARATION_SCHEMA_HEADER,
)


learning_bp = Blueprint("learning", __name__)


@learning_bp.get("/today")
def today():
    try:
        return jsonify(
            learning_service().parent_overview(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@learning_bp.get("/overview")
def overview():
    try:
        return jsonify(
            learning_service().parent_overview(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@learning_bp.get("/availability")
def learning_availability():
    try:
        return jsonify(
            learning_curriculum_preparation_service().learning_availability(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@learning_bp.get("/preparations/current")
def current_preparation():
    try:
        response = make_response(jsonify(
            learning_curriculum_preparation_service().current(
                bearer_token(request),
                request.args,
                schema_header_present=PREPARATION_SCHEMA_HEADER in request.headers,
                requested_schema=request.headers.get(PREPARATION_SCHEMA_HEADER),
            )
        ))
    except ApiError as exc:
        response = make_response(error_response(exc))
    response.vary.add(PREPARATION_SCHEMA_HEADER)
    return response


@learning_bp.post("/preparations/<plan_id>/retry")
def retry_preparation(plan_id: str):
    try:
        payload, created = learning_curriculum_preparation_service().retry(
            bearer_token(request),
            plan_id,
            lambda: request.get_json(silent=True),
            schema_header_present=PREPARATION_SCHEMA_HEADER in request.headers,
            requested_schema=request.headers.get(PREPARATION_SCHEMA_HEADER),
        )
        response = make_response(jsonify(payload), 202 if created else 200)
    except ApiError as exc:
        response = make_response(error_response(exc))
    response.vary.add(PREPARATION_SCHEMA_HEADER)
    return response


@learning_bp.post("/today/assign")
def assign_today():
    return _student_learning_api_required()


@learning_bp.post("/sessions")
def start_session():
    return _student_learning_api_required()


@learning_bp.post("/sessions/<session_id>/answer")
def answer(session_id: str):
    del session_id
    return _student_learning_api_required()


def _student_learning_api_required():
    # Deliberately do not read auth, JSON, Provider configuration, or storage.
    # Formal learning mutations are owned by the v2 student-auth boundary.
    return error_response(
        ApiError(
            "student_learning_api_required",
            "请从学生端进入正式学习流程",
            410,
        )
    )


@learning_bp.get("/reports/latest")
def latest_report():
    try:
        return jsonify(
            learning_service().latest_report(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@learning_bp.get("/reports")
def list_reports():
    try:
        return jsonify(
            learning_service().list_reports(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@learning_bp.get("/reports/<report_id>")
def report_detail(report_id: str):
    try:
        return jsonify(
            learning_service().report_detail(
                bearer_token(request),
                report_id,
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)
