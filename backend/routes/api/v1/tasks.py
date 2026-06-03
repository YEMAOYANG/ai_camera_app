from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import task_service


tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.get("/today")
def today():
    try:
        return jsonify(task_service().list_today(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.get("")
def list_tasks():
    try:
        return jsonify(task_service().list_tasks(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("")
def create_task():
    try:
        return jsonify(task_service().create_task(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/batch")
def create_tasks_batch():
    try:
        return jsonify(
            task_service().create_tasks_batch(
                bearer_token(request),
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.get("/<task_id>")
def get_task(task_id: str):
    try:
        return jsonify(task_service().get_task(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.patch("/<task_id>")
def update_task(task_id: str):
    try:
        return jsonify(task_service().update_task(bearer_token(request), task_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/complete")
def complete_task(task_id: str):
    try:
        return jsonify(task_service().complete_task(bearer_token(request), task_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/parent-confirm")
def parent_confirm(task_id: str):
    try:
        return jsonify(task_service().parent_confirm(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/reject-confirmation")
def reject_confirmation(task_id: str):
    try:
        return jsonify(
            task_service().reject_confirmation(
                bearer_token(request),
                task_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)
