"""Guarded reads of registered course files, never an arbitrary path proxy."""
from __future__ import annotations

import hashlib
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

from core.course_storage_config import CourseStorageConfig
from core.database import Database
from core.errors import ApiError
from repositories.course_storage_repository import (
    CourseStorageRegistryError, CourseStorageRepository, normalize_source_path, storage_id_for, storage_identity,
)
from services.service_factory import internal_request_guard


internal_course_storage_bp = Blueprint("internal_course_storage", __name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
MAX_HTTP_FILE_BYTES = 64 * 1024 * 1024


def _request_asset(*, write=False, authorized=False):
    if not authorized:
        internal_request_guard().authorize(route=request.path, headers=request.headers,
            source_ip=request.remote_addr)
    if (set(request.args) - ({"path"} if write else {"path", "sha256"}) or len(request.args.getlist("path")) != 1
            or len(request.args.getlist("sha256")) > 1):
        raise ApiError("course_storage_request_invalid", "课件文件请求无效", 400)
    try:
        path = normalize_source_path(request.args.get("path"))
        expected = request.args.get("sha256")
        if expected is not None and (len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected)):
            raise CourseStorageRegistryError("course_storage_sha_invalid")
    except CourseStorageRegistryError:
        raise ApiError("course_storage_request_invalid", "课件文件请求无效", 400) from None
    config = CourseStorageConfig.from_env()
    identity = storage_identity(config.endpoint, config.bucket, config.region)
    repository = CourseStorageRepository(Database(current_app.config["DATABASE_URL"]))
    asset = repository.resolve(path, storage_id_for(**identity), expected_sha=expected)
    if asset is None:
        raise ApiError("course_storage_asset_not_found", "课件文件未登记", 404)
    return config, repository, {**asset, "storage": identity}, expected


def _storage_error():
    return _error_response(ApiError("course_storage_unavailable", "课件存储暂时不可用", 502))


def _error_response(error):
    return jsonify({"ok": False, "error": {"code": error.code, "message": error.message}}), error.status_code


@internal_course_storage_bp.get("/asset")
def asset():
    try:
        _, _, value, _ = _request_asset()
        return jsonify({"ok": True, "asset": {k: value[k] for k in
            ("path", "sourcePath", "sha256", "byteSize", "mimeType", "locator", "storage")}})
    except ApiError as error:
        return _error_response(error)
    except Exception:
        return _storage_error()


def _read_remote(config, repository, path, sha):
    # Lazy import keeps the registry API independent of the source-reader setup.
    from services.course_file_store import CourseFileStore
    return CourseFileStore(config=config, repository=repository).read_bytes(
        PROJECT_ROOT / path, expected_sha256=sha)


@internal_course_storage_bp.get("/file")
def file():
    try:
        config, repository, value, _ = _request_asset()
        if value["byteSize"] > MAX_HTTP_FILE_BYTES:
            raise ApiError("course_storage_file_too_large", "课件文件超过读取限制", 413)
        body = _read_remote(config, repository, value["path"], value["sha256"])
        if (not isinstance(body, bytes) or len(body) != value["byteSize"]
                or len(body) > MAX_HTTP_FILE_BYTES or hashlib.sha256(body).hexdigest() != value["sha256"]):
            raise ValueError("course_storage_content_changed")
        return Response(body, content_type=value["mimeType"], headers={
            "X-Mira-File-Sha256": value["sha256"], "X-Mira-File-Source": "remote",
            "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        })
    except ApiError as error:
        return _error_response(error)
    except Exception:
        return _storage_error()


def _write_remote(config, repository, path, raw, expected):
    from services.course_file_writer import CourseFileWriter
    return CourseFileWriter(config=config, repository=repository).write_bytes(
        PROJECT_ROOT / path, raw, expected_sha256=expected)


@internal_course_storage_bp.put("/file")
def put_file():
    from services.course_file_writer import CourseFileWriteError
    try:
        # Authorization precedes body parsing and registry work, including for
        # invalid requests. The exact raw bytes, rather than re-serialized JSON,
        # form the immutable content version.
        internal_request_guard().authorize(route=request.path, headers=request.headers,
            source_ip=request.remote_addr)
        expected = request.headers.get("If-Match", "")
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ApiError("course_storage_if_match_required", "需要读取时的原文件摘要", 428)
        if request.mimetype != "application/json" or request.headers.get("Content-Encoding", "identity") != "identity":
            raise ApiError("course_storage_request_invalid", "课件文件请求无效", 400)
        if request.content_length is not None and request.content_length > MAX_HTTP_FILE_BYTES:
            raise ApiError("course_storage_file_too_large", "课件文件超过写入限制", 413)
        config, repository, value, _ = _request_asset(write=True, authorized=True)
        if value["sha256"] != expected:
            raise ApiError("course_storage_head_conflict", "课件文件已改变，请重新读取", 409)
        raw = request.stream.read(MAX_HTTP_FILE_BYTES + 1)
        if len(raw) > MAX_HTTP_FILE_BYTES:
            raise ApiError("course_storage_file_too_large", "课件文件超过写入限制", 413)
        result = _write_remote(config, repository, value["path"], raw, expected)
        return jsonify({"ok": True, "asset": {k: result[k] for k in
            ("path", "sourcePath", "sha256", "byteSize", "mimeType", "locator", "storage")}})
    except ApiError as error:
        return _error_response(error)
    except CourseFileWriteError as error:
        return _error_response(ApiError(error.code, "课件工作记录未能更新", error.status_code))
    except Exception:
        return _storage_error()
