from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import internal_request_guard, lesson_package_service
from services.learning_classroom_generation_runner import (
    learning_classroom_generation_status,
)


internal_learning_classrooms_bp = Blueprint(
    "internal_learning_classrooms",
    __name__,
)


@internal_learning_classrooms_bp.get("/status")
def classroom_status():
    try:
        request_id = str(request.args.get("requestId") or "").strip()
        context = internal_request_guard().authorize(
            route="/internal/learning/classrooms/status",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=request_id[:255],
        )
        generation = (
            lesson_package_service().job_status(request_id)
            if request_id
            else lesson_package_service().status()
        )
        return jsonify(
            {
                "ok": True,
                "generation": generation,
                "runner": learning_classroom_generation_status(),
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_learning_classrooms_bp.post("/generate")
def generate_classroom():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/learning/classrooms/generate",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("requestId") or data.get("courseId") or "")[:255],
        )
        result = lesson_package_service().generate(data)
        payload = dict(result.payload)
        payload["internal"] = context
        return jsonify(payload), result.status_code
    except ApiError as exc:
        return error_response(exc)
