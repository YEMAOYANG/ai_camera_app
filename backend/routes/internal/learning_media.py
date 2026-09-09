from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.learning_media_materialization_service import (
    LearningMediaMaterializationError,
)
from services.learning_media_worker_runner import learning_media_worker_status
from services.service_factory import (
    internal_request_guard,
    learning_media_materialization_service,
    lesson_package_service,
)


internal_learning_media_bp = Blueprint("internal_learning_media", __name__)


@internal_learning_media_bp.get("/status")
def media_status():
    try:
        job_id = str(request.args.get("jobId") or "").strip()
        package_id = str(request.args.get("packageId") or "").strip()
        package_version = request.args.get("packageVersion")
        context = internal_request_guard().authorize(
            route="/internal/learning/media/status",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=(job_id or package_id)[:255],
        )
        service = learning_media_materialization_service()
        payload = {
            "ok": True,
            "availability": service.availability(),
            "runner": learning_media_worker_status(),
            "job": service.get_job(job_id=job_id) if job_id else None,
            "package": None,
            "internal": context,
        }
        if package_id:
            if package_version is None:
                raise ApiError(
                    "invalid_packageVersion",
                    "查询课件媒体状态需要 packageVersion",
                )
            payload["package"] = lesson_package_service().media_status(
                package_id,
                package_version,
            )
        return jsonify(payload)
    except LearningMediaMaterializationError as exc:
        return error_response(_media_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_learning_media_bp.post("/materialize")
def materialize_media():
    try:
        data = json_body(request)
        job_id = str(data.get("jobId") or "").strip()
        context = internal_request_guard().authorize(
            route="/internal/learning/media/materialize",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=job_id[:255],
        )
        service = learning_media_materialization_service()
        if not job_id:
            pending = service.next_pending_job()
            if pending is None:
                return jsonify(
                    {
                        "ok": True,
                        "status": "idle",
                        "job": None,
                        "package": None,
                        "internal": context,
                    }
                )
            job_id = str(pending["id"])
        job = service.materialize_job(job_id=job_id)
        package = _finalize_job_package(job)
        return jsonify(
            {
                "ok": True,
                "status": str(job["status"]),
                "job": job,
                "package": package,
                "internal": context,
            }
        )
    except LearningMediaMaterializationError as exc:
        # A real upstream failure records a failed job. Synchronize its staged
        # package before returning the safe error; an unconfigured provider
        # leaves the job/package pending.
        if "job_id" in locals() and job_id:
            try:
                failed_job = learning_media_materialization_service().get_job(
                    job_id=job_id
                )
                _finalize_job_package(failed_job)
            except Exception:
                pass
        return error_response(_media_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_learning_media_bp.post("/review")
def review_media():
    try:
        data = json_body(request)
        asset_id = str(data.get("assetId") or "").strip()
        context = internal_request_guard().authorize(
            route="/internal/learning/media/review",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=asset_id[:255],
        )
        if not isinstance(data.get("approved"), bool):
            raise ApiError("invalid_media_review", "approved 必须是布尔值")
        reviewer_id = str(context.get("sourceName") or "").strip()
        if not reviewer_id:
            reviewer_id = f"internal-audit:{context['auditId']}"
        review = learning_media_materialization_service().review_pronunciation_asset(
            asset_id=asset_id,
            approved=bool(data["approved"]),
            reviewer_type="content_reviewer",
            reviewer_id=reviewer_id,
            notes=str(data.get("notes") or ""),
            findings=(
                dict(data["findings"])
                if isinstance(data.get("findings"), dict)
                else {}
            ),
        )
        package = _finalize_job_package(review.get("job"))
        return jsonify(
            {
                "ok": True,
                "review": review,
                "package": package,
                "internal": context,
            }
        )
    except LearningMediaMaterializationError as exc:
        return error_response(_media_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


def _finalize_job_package(job: object) -> dict | None:
    if not isinstance(job, dict):
        return None
    package = job.get("package")
    if not isinstance(package, dict) or package.get("id") is None:
        return None
    return lesson_package_service().finalize_media_package(
        package_id=str(package["id"]),
        package_version=int(package["version"]),
    )


def _media_api_error(exc: LearningMediaMaterializationError) -> ApiError:
    if exc.code == "tts_provider_unconfigured":
        status = 503
    elif exc.code in {"media_job_not_found", "manual_review_not_found"}:
        status = 404
    elif exc.code in {"media_job_busy", "idempotency_conflict"}:
        status = 409
    elif exc.code.startswith("tts_upstream_"):
        status = 502
    else:
        status = 422
    return ApiError(exc.code, exc.safe_message, status)
