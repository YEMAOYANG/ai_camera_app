from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.service_factory import task_service
from services.task_event_stream import publish_task_update


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
        return _task_response(task_service().create_task(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/batch")
def create_tasks_batch():
    try:
        return _task_response(
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


@tasks_bp.get("/<task_id>/events")
def get_task_events(task_id: str):
    try:
        return jsonify(task_service().list_task_events(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.patch("/<task_id>")
def update_task(task_id: str):
    try:
        return _task_response(task_service().update_task(bearer_token(request), task_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/complete")
def complete_task(task_id: str):
    try:
        return _task_response(task_service().complete_task(bearer_token(request), task_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/start")
def start_task(task_id: str):
    try:
        return _task_response(task_service().start_task(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/reminder")
def send_task_reminder(task_id: str):
    try:
        return _task_response(
            task_service().send_reminder(
                bearer_token(request),
                task_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/parent-confirm")
def parent_confirm(task_id: str):
    try:
        return _task_response(task_service().parent_confirm(bearer_token(request), task_id))
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/reject-confirmation")
def reject_confirmation(task_id: str):
    try:
        return _task_response(
            task_service().reject_confirmation(
                bearer_token(request),
                task_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


@tasks_bp.post("/<task_id>/reject")
def reject(task_id: str):
    try:
        return _task_response(
            task_service().reject_confirmation(
                bearer_token(request),
                task_id,
                json_body(request),
            )
        )
    except ApiError as exc:
        return error_response(exc)


def _task_response(payload: dict):
    _publish_task_payload(payload)
    return jsonify(payload)


def _publish_task_payload(payload: dict) -> None:
    tasks = []
    task = payload.get("task")
    if isinstance(task, dict):
        tasks.append(task)
    raw_tasks = payload.get("tasks")
    if isinstance(raw_tasks, list):
        tasks.extend(item for item in raw_tasks if isinstance(item, dict))
    family_ids = {str(item.get("familyId") or "") for item in tasks}
    for family_id in family_ids:
        if not family_id:
            continue
        publish_task_update(
            family_id=family_id,
            tasks=[item for item in tasks if item.get("familyId") == family_id],
            source="task_action",
        )
