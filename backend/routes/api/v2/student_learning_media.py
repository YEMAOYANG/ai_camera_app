from __future__ import annotations

from flask import Blueprint, request, send_file

from core.errors import ApiError, error_response
from schemas.auth import bearer_token
from services.service_factory import student_learning_media_service


student_learning_media_bp = Blueprint("student_learning_media_v2", __name__)


@student_learning_media_bp.get("/sessions/<session_id>/assets")
def session_asset_manifest(session_id: str):
    try:
        return student_learning_media_service().session_manifest(
            bearer_token(request),
            session_id,
        )
    except ApiError as exc:
        return error_response(exc)


@student_learning_media_bp.get("/assets/<asset_id>")
def deliver_learning_asset(asset_id: str):
    try:
        asset = student_learning_media_service().authorize_asset(
            bearer_token(request),
            asset_id,
            variant_key=request.args.get("variant") or "original",
        )
        response = send_file(
            asset.path,
            mimetype=asset.mime_type,
            conditional=True,
            etag=asset.content_hash,
            last_modified=asset.path.stat().st_mtime,
            max_age=0,
            download_name=asset.download_name,
        )
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
    except ApiError as exc:
        return error_response(exc)
