from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from core.errors import ApiError, error_response
from core.security import now_ms
from services.learning_curriculum_preparation_runner import (
    learning_curriculum_preparation_config_projection,
    learning_curriculum_preparation_runner,
)
from services.service_factory import internal_request_guard


internal_learning_curriculum_preparations_bp = Blueprint(
    "internal_learning_curriculum_preparations",
    __name__,
)


@internal_learning_curriculum_preparations_bp.get("/runner/status")
def curriculum_preparation_runner_status():
    try:
        context = internal_request_guard().authorize(
            route="/internal/learning/curriculum-preparations/runner/status",
            headers=request.headers,
            source_ip=request.remote_addr,
        )
        if request.args:
            raise ApiError(
                "invalid_request",
                "该状态接口不接受查询参数。",
                400,
            )
        config = learning_curriculum_preparation_config_projection(current_app)
        if config is None:
            raise ApiError(
                "learning_preparation_runner_config_invalid",
                "课程准备运行配置不可用。",
                503,
            )
        observed = learning_curriculum_preparation_runner.read_only_status(
            current_app,
            now_ms=now_ms(),
            config_projection=config,
        )
        runner = {
            "enabled": config.runner_enabled,
            "contentGenerationEnabled": config.content_generation_enabled,
            "gradeAllowlist": list(config.grade_allowlist),
            "maxProviderSubcallsPerTick": config.max_provider_subcalls_per_tick,
            "observationScope": "process",
            **observed,
        }
        return jsonify(
            {
                "ok": True,
                "schemaVersion": "mira.learning.preparation-runner-status.v1",
                "internal": {"auditId": str(context["auditId"])},
                "runner": runner,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_learning_curriculum_preparations_bp.get("/library/status")
def course_library_status():
    try:
        internal_request_guard().authorize(
            route="/internal/learning/curriculum-preparations/library/status",
            headers=request.headers, source_ip=request.remote_addr,
        )
        if request.args:
            raise ApiError("invalid_request", "该状态接口不接受查询参数。", 400)
        from services.course_library_service import CourseLibraryService
        status = CourseLibraryService(current_app.config["DATABASE_URL"]).status()
        response = jsonify({"ok": True, "library": status})
        response.set_etag(status["version"])
        response.headers["Cache-Control"] = "private, max-age=5"
        response.headers["Vary"] = "Authorization, X-Mira-Internal-Token"
        return response.make_conditional(request)
    except ApiError as exc:
        return error_response(exc)
