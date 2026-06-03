from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.auth_service import AuthService
from services.sms_provider import MockSmsProvider
from services.task_service import TaskService


tasks_bp = Blueprint("tasks", __name__)


def _auth_service() -> AuthService:
    return AuthService(
        current_app.config["AUTH_DB_PATH"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        dev_sms_code=current_app.config["AUTH_DEV_SMS_CODE"],
        sms_provider=MockSmsProvider(current_app.config["AUTH_DEV_SMS_CODE"]),
    )


def _task_service() -> TaskService:
    return TaskService(current_app.config["AUTH_DB_PATH"], auth_service=_auth_service())


@tasks_bp.get("/today")
def today():
    try:
        return jsonify(_task_service().list_today(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.get("")
def list_tasks():
    try:
        return jsonify(_task_service().list_tasks(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("")
def create_task():
    try:
        return jsonify(_task_service().create_task(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.get("/<task_id>")
def get_task(task_id: str):
    try:
        return jsonify(_task_service().get_task(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.patch("/<task_id>")
def update_task(task_id: str):
    try:
        return jsonify(_task_service().update_task(bearer_token(request), task_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/complete")
def complete_task(task_id: str):
    try:
        return jsonify(_task_service().complete_task(bearer_token(request), task_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/parent-confirm")
def parent_confirm(task_id: str):
    try:
        return jsonify(_task_service().parent_confirm(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/reject-confirmation")
def reject_confirmation(task_id: str):
    try:
        return jsonify(
            _task_service().reject_confirmation(
                bearer_token(request),
                task_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
