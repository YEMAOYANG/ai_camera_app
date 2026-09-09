from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import (
    dynamic_learning_course_generation_service,
    internal_request_guard,
    learning_catalog_release_service,
    learning_content_pipeline_service,
)


internal_learning_content_bp = Blueprint("internal_learning_content", __name__)


@internal_learning_content_bp.get("/questions/status")
def generated_question_status():
    try:
        context = internal_request_guard().authorize(
            route="/internal/learning/content/questions/status",
            headers=request.headers,
            source_ip=request.remote_addr,
        )
        return jsonify(
            {
                "ok": True,
                "generation": dynamic_learning_course_generation_service().status(),
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.post("/questions/generate")
def generate_questions():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/learning/content/questions/generate",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(
                data.get("requestId")
                or data.get("skillId")
                or data.get("gradeCode")
                or ""
            )[:255],
        )
        result = dynamic_learning_course_generation_service().generate(data)
        payload = dict(result.payload)
        payload["internal"] = context
        return jsonify(payload), result.status_code
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.get("/status")
def learning_content_status():
    try:
        context = internal_request_guard().authorize(
            route="/internal/learning/content/status",
            headers=request.headers,
            source_ip=request.remote_addr,
        )
        return jsonify(
            {
                "ok": True,
                "generation": learning_content_pipeline_service().status(),
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.post("/generate")
def generate_learning_content():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/learning/content/generate",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("requestId") or data.get("courseId") or "")[:255],
        )
        result = learning_content_pipeline_service().generate(data)
        payload = dict(result.payload)
        payload["internal"] = context
        return jsonify(payload), result.status_code
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.post("/catalog/builds")
def create_catalog_build():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/learning/content/catalog/builds",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("requestId") or "")[:255],
        )
        payload = learning_catalog_release_service().create(data)
        payload["internal"] = context
        return jsonify(payload), 201 if payload.get("created") else 200
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.get("/catalog/builds/<build_id>")
def catalog_build_status(build_id: str):
    try:
        context = internal_request_guard().authorize(
            route="/internal/learning/content/catalog/builds/:buildId",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=build_id[:255],
        )
        payload = learning_catalog_release_service().status(build_id)
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.post("/catalog/builds/<build_id>/run")
def run_catalog_build(build_id: str):
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/learning/content/catalog/builds/:buildId/run",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=build_id[:255],
        )
        payload = learning_catalog_release_service().run(build_id, data)
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@internal_learning_content_bp.post("/catalog/releases/<release_id>/activate")
def activate_catalog_release(release_id: str):
    try:
        context = internal_request_guard().authorize(
            route="/internal/learning/content/catalog/releases/:releaseId/activate",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=release_id[:255],
        )
        payload = learning_catalog_release_service().activate(release_id)
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)
