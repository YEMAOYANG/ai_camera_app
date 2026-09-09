from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.openmaic_full_runtime_service import OpenMaicRuntimeServiceError
from services.service_factory import (
    openmaic_full_runtime_service,
    student_learning_service,
)


student_learning_bp = Blueprint("student_learning_v2", __name__)


@student_learning_bp.get("/today")
def today():
    try:
        return jsonify(
            student_learning_service().today(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.post("/today/assign")
def assign_today():
    try:
        return jsonify(
            student_learning_service().assign_today(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.post("/sessions")
def start_session():
    try:
        return jsonify(
            student_learning_service().start_session(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.post("/sessions/<session_id>/answer")
def answer(session_id: str):
    try:
        return jsonify(
            student_learning_service().answer(
                bearer_token(request),
                session_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.get("/sessions/<session_id>/runtime")
def classroom_runtime(session_id: str):
    try:
        return jsonify(
            student_learning_service().classroom_runtime(
                bearer_token(request),
                session_id,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.post(
    "/sessions/<session_id>/actions/<action_id>/complete"
)
def complete_classroom_action(session_id: str, action_id: str):
    try:
        return jsonify(
            student_learning_service().complete_classroom_action(
                bearer_token(request),
                session_id,
                action_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.post("/sessions/<session_id>/openmaic-launch")
def openmaic_launch(session_id: str):
    try:
        return jsonify(
            openmaic_full_runtime_service().create_student_launch(
                bearer_token(request),
                session_id,
            )
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(ApiError(exc.code, exc.safe_message, exc.status_code))
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.get("/reports/latest")
def latest_report():
    try:
        return jsonify(
            student_learning_service().latest_report(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.get("/library")
def library():
    try:
        return jsonify(
            student_learning_service().library(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.get("/courses/<course_id>")
def course_detail(course_id: str):
    try:
        return jsonify(
            student_learning_service().course_detail(
                bearer_token(request),
                course_id,
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.put("/courses/<course_id>/versions/<course_version>/favorite")
def favorite_course(course_id: str, course_version: str):
    try:
        return jsonify(
            student_learning_service().set_course_favorite(
                bearer_token(request),
                course_id,
                course_version,
                favorite=True,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.delete(
    "/courses/<course_id>/versions/<course_version>/favorite"
)
def unfavorite_course(course_id: str, course_version: str):
    try:
        return jsonify(
            student_learning_service().set_course_favorite(
                bearer_token(request),
                course_id,
                course_version,
                favorite=False,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.get("/teachers")
def teachers():
    try:
        return jsonify(
            student_learning_service().teachers(
                bearer_token(request),
                request.args,
            )
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_bp.put("/preferences/teacher")
def set_teacher_preference():
    try:
        return jsonify(
            student_learning_service().set_teacher_preference(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
