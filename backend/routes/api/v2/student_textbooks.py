from flask import Blueprint, Response, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import bearer_token, json_body
from services.courseware_asset_store import CoursewareAssetNotFound, CoursewareAssetStorageError
from services.service_factory import courseware_asset_store, textbook_learning_service, textbook_classroom_service

student_textbooks_bp = Blueprint("student_textbooks", __name__)
parent_textbooks_bp = Blueprint("parent_textbooks", __name__)


@student_textbooks_bp.post('/courses/<content_key>/launch')
def launch(content_key):
    try:
        if request.args or json_body(request) != {}:
            raise ApiError('textbook_query_invalid', '课堂请求参数无效', 400)
        return jsonify(textbook_classroom_service().launch(bearer_token(request), content_key))
    except ApiError as exc:
        return error_response(exc)


@student_textbooks_bp.get("")
def catalog():
    try:
        return jsonify(textbook_learning_service().student_catalog(bearer_token(request), request.args))
    except ApiError as exc:
        return error_response(exc)


@student_textbooks_bp.get("/assets/<path:asset_path>")
def asset(asset_path):
    """Serve only immutable, manifest-listed public courseware resources."""
    if request.args:
        return error_response(ApiError("courseware_asset_request_invalid", "课件资源请求无效", 400))
    try:
        entry, body = courseware_asset_store().read_public(asset_path)
        return Response(body, content_type=entry["mimeType"], headers={
            "Content-Length": str(len(body)),
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": entry["etag"],
            "X-Mira-File-Sha256": entry["sha256"],
            "X-Mira-File-Source": "remote",
            "X-Content-Type-Options": "nosniff",
        })
    except CoursewareAssetNotFound:
        return error_response(ApiError("courseware_asset_not_found", "课件资源不存在", 404))
    except CoursewareAssetStorageError:
        return error_response(ApiError("courseware_asset_unavailable", "课件资源暂时不可用", 502))
    except Exception:
        return error_response(ApiError("courseware_asset_unavailable", "课件资源暂时不可用", 502))


@student_textbooks_bp.get("/<edition_id>/contents")
def contents(edition_id):
    try:
        return jsonify(textbook_learning_service().student_contents(bearer_token(request), edition_id, request.args))
    except ApiError as exc:
        return error_response(exc)


@parent_textbooks_bp.get("/<child_id>/textbooks")
def parent_catalog(child_id):
    try:
        return jsonify(textbook_learning_service().parent_catalog(bearer_token(request), child_id))
    except ApiError as exc:
        return error_response(exc)


@parent_textbooks_bp.put("/<child_id>/textbooks")
def select(child_id):
    try:
        return jsonify(textbook_learning_service().parent_select(bearer_token(request), child_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@parent_textbooks_bp.put("/<child_id>/textbooks/selections")
def select_many(child_id):
    try:
        return jsonify(textbook_learning_service().parent_select_many(bearer_token(request), child_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@parent_textbooks_bp.put("/<child_id>/textbooks/context")
def update_context(child_id):
    try:
        return jsonify(textbook_learning_service().parent_update_context(bearer_token(request), child_id, json_body(request)))
    except ApiError as exc:
        return error_response(exc)
