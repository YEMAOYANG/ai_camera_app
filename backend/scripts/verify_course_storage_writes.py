#!/usr/bin/env python3
"""Exercise version writes with private SQLite heads and real immutable storage.

prepare reads one unlinked saved preview from MySQL; serve uses the production
blueprint, repository, writer and authentication with private audit/registry DB;
verify exercises a separately started Native runtime. No business DB write,
provider call, object deletion, or service launch is available here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from repositories.course_storage_repository import CourseStorageRepository, storage_id_for, storage_identity
from scripts.verify_course_storage_runtime import ReadOnlyDatabase
from services.course_file_store import CourseFileStore
from services.course_file_writer import NodeCourseFileUploader


ROOT = Path(__file__).resolve().parents[2]
STATE_ROOT = ROOT / "backend/data/course-storage/write-verifications"
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_HTTP = 64 * 1024 * 1024


class ShadowVerificationError(ValueError):
    pass


def require(value, code):
    if not value:
        raise ShadowVerificationError(code)


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def _private_write(path, body):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def _directory(path, *, create=False):
    path = Path(path).absolute()
    require(path.parent == STATE_ROOT and re.fullmatch(r"[A-Za-z0-9_-]{8,100}", path.name), "shadow_state_path_invalid")
    for parent in reversed(path.parents):
        require(not parent.is_symlink(), "shadow_state_symlink")
    require(not path.is_symlink(), "shadow_state_symlink")
    if create:
        STATE_ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
        path.mkdir(mode=0o700)
    require(path.is_dir() and path.stat().st_mode & 0o077 == 0, "shadow_state_not_private")
    return path


def _snapshot(database, preview_key, storage):
    storage_id = storage_id_for(**storage)
    with database.transaction() as conn:
        preview = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=?", (preview_key,)).fetchone()
        require(preview and preview["status"] in {"preview_ready", "review_required"}, "shadow_preview_not_editable")
        cid = preview["classroom_id"]
        require(isinstance(cid, str) and re.fullmatch(r"[A-Za-z0-9_-]+", cid)
            and not cid.startswith("tbpub_"), "shadow_classroom_invalid")
        published = conn.execute("SELECT content_key,status,input_json FROM learning_textbook_course_builds "
            "WHERE status='published' AND JSON_UNQUOTE(JSON_EXTRACT(input_json,'$.previewKey'))=?", (preview_key,)).fetchall()
        require(not published, "shadow_preview_is_published")
        path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + cid + ".json"
        path_sha = digest(path.encode())
        head = conn.execute("SELECT * FROM course_storage_heads WHERE storage_id=? AND source_path_sha256=?", (storage_id, path_sha)).fetchone()
        require(head, "shadow_registered_head_missing")
        file = conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? AND source_path_sha256=? AND content_sha256=?",
            (storage_id, path_sha, head["content_sha256"])).fetchone()
        scope = conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=?", (storage_id, head["scope_key"])).fetchone()
        require(file and scope, "shadow_registry_incomplete")
        meta = json.loads(scope["scope_json"])
        require(meta.get("sourceKind") == "textbook_preview" and meta.get("status") == "generated_saved"
            and meta.get("previewKey") == preview_key and meta.get("classroomId") == cid, "shadow_preview_scope_invalid")
        parents = conn.execute("SELECT scope_key FROM course_storage_scopes WHERE storage_id=? "
            "AND JSON_UNQUOTE(JSON_EXTRACT(scope_json,'$.status'))='published' AND JSON_CONTAINS(bindings_json,?)",
            (storage_id, json.dumps({"sourcePathSha256": path_sha, "sha256": file["content_sha256"]}, separators=(",", ":")))).fetchall()
        require(not parents, "shadow_published_parent_reference")
        return {"preview": dict(preview), "head": dict(head), "file": dict(file), "scope": dict(scope),
                "builds": [], "path": path, "classroomId": cid}


class SQLiteConnection:
    """Dialect adaptation only; production validation/transactions stay intact."""
    def __init__(self, connection):
        self.raw = connection

    def execute(self, sql, params=()):
        require(";" not in sql, "shadow_multiple_statements_forbidden")
        sql = sql.replace(" FOR UPDATE", "")
        if " ON DUPLICATE KEY UPDATE " in sql:
            sql, update = sql.split(" ON DUPLICATE KEY UPDATE ", 1)
            if "content_sha256=VALUES" in update:
                sql += (" ON CONFLICT(storage_id,source_path_sha256) DO UPDATE SET content_sha256=excluded.content_sha256,"
                        "scope_key=excluded.scope_key,updated_at=excluded.updated_at")
            else:
                sql += " ON CONFLICT DO NOTHING"
        return self.raw.execute(sql, tuple(params))


def _contains(data, query):
    wanted = json.loads(query)
    return int(any(isinstance(item, dict) and all(item.get(k) == v for k, v in wanted.items()) for item in json.loads(data)))


class ShadowDatabase:
    def __init__(self, path):
        self.path = Path(path)
        require(self.path.is_file() and not self.path.is_symlink()
            and self.path.stat().st_nlink == 1 and self.path.stat().st_mode & 0o077 == 0, "shadow_database_not_private")

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect("file:" + str(self.path) + "?mode=rw", uri=True, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.create_function("JSON_UNQUOTE", 1, lambda value: value)
        connection.create_function("JSON_CONTAINS", 2, _contains)
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield SQLiteConnection(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _seed(path, snapshot):
    _private_write(path, b"")
    connection = sqlite3.connect(path)
    try:
        connection.executescript("""
          PRAGMA foreign_keys=ON;
          CREATE TABLE course_storage_files(storage_id TEXT,source_path_sha256 TEXT,content_sha256 TEXT,
            source_path TEXT,byte_size INTEGER,mime_type TEXT,locator_json TEXT,created_at INTEGER,
            PRIMARY KEY(storage_id,source_path_sha256,content_sha256));
          CREATE TABLE course_storage_scopes(storage_id TEXT,scope_key TEXT,preview_key TEXT,content_key TEXT,
            classroom_id TEXT,course_id TEXT,course_version TEXT,scope_json TEXT,bindings_json TEXT,created_at INTEGER,
            PRIMARY KEY(storage_id,scope_key));
          CREATE TABLE course_storage_heads(storage_id TEXT,source_path_sha256 TEXT,content_sha256 TEXT,
            scope_key TEXT,updated_at INTEGER,PRIMARY KEY(storage_id,source_path_sha256),
            FOREIGN KEY(storage_id,source_path_sha256,content_sha256)
              REFERENCES course_storage_files(storage_id,source_path_sha256,content_sha256),
            FOREIGN KEY(storage_id,scope_key) REFERENCES course_storage_scopes(storage_id,scope_key));
          CREATE TABLE learning_textbook_course_builds(content_key TEXT,status TEXT,input_json TEXT);
          CREATE TABLE shadow_internal_audits(id TEXT PRIMARY KEY,event_json TEXT);
        """)
        preview = snapshot["preview"]
        require(all(re.fullmatch(r"[a-z][a-z0-9_]*", key) for key in preview), "shadow_preview_column_invalid")
        connection.execute("CREATE TABLE learning_textbook_course_previews(" + ",".join('"' + key + '" TEXT' for key in preview) + ")")
        rows = (("course_storage_files", snapshot["file"]), ("course_storage_scopes", snapshot["scope"]),
                ("course_storage_heads", snapshot["head"]), ("learning_textbook_course_previews", preview))
        for table, row in rows:
            columns = ",".join(row)
            connection.execute("INSERT INTO " + table + "(" + columns + ") VALUES(" + ",".join("?" for _ in row) + ")", tuple(row.values()))
        connection.commit()
    finally:
        connection.close()


def prepare(preview_key, state, *, app_config=None, database=None):
    require(bool(SHA.fullmatch(preview_key)), "shadow_preview_key_invalid")
    app_config = app_config or AppConfig.from_env()
    storage_config = replace(CourseStorageConfig.from_env(), mode="registry")
    storage = storage_identity(storage_config.endpoint, storage_config.bucket, storage_config.region)
    database = database or ReadOnlyDatabase(Database(app_config.DATABASE_URL))
    snapshot = _snapshot(database, preview_key, storage)
    repository = CourseStorageRepository(database)
    body = CourseFileStore(config=storage_config, repository=repository).read_bytes(ROOT / snapshot["path"],
        expected_sha256=snapshot["file"]["content_sha256"], max_bytes=MAX_HTTP)
    require(isinstance(body, bytes) and digest(body) == snapshot["file"]["content_sha256"], "shadow_original_remote_invalid")
    require(_snapshot(database, preview_key, storage) == snapshot, "shadow_source_changed_during_prepare")
    state = _directory(state, create=True)
    _seed(state / "shadow.sqlite3", snapshot)
    metadata = {"schemaVersion": "mira.course-storage.shadow.v1", "previewKey": preview_key,
        "classroomId": snapshot["classroomId"], "path": snapshot["path"], "originalSha256": digest(body),
        "storage": storage, "baselineSha256": digest(packed(snapshot)), "snapshot": snapshot}
    _private_write(state / "baseline.json", packed(metadata))
    return {k: metadata[k] for k in ("previewKey", "classroomId", "path", "originalSha256", "baselineSha256")}


def _load(state):
    state = _directory(state)
    baseline = state / "baseline.json"
    require(baseline.is_file() and not baseline.is_symlink() and baseline.stat().st_nlink == 1
        and baseline.stat().st_size <= MAX_HTTP and baseline.stat().st_mode & 0o077 == 0, "shadow_baseline_not_private")
    value = json.loads(baseline.read_bytes())
    snapshot = value.get("snapshot", {})
    require(value.get("schemaVersion") == "mira.course-storage.shadow.v1"
        and digest(packed(snapshot)) == value.get("baselineSha256")
        and value.get("previewKey") == snapshot.get("preview", {}).get("preview_key")
        and value.get("classroomId") == snapshot.get("classroomId") == snapshot.get("preview", {}).get("classroom_id")
        and value.get("path") == snapshot.get("path") == snapshot.get("file", {}).get("source_path")
        and isinstance(value.get("originalSha256"), str) and bool(SHA.fullmatch(value["originalSha256"]))
        and value["originalSha256"] == snapshot.get("file", {}).get("content_sha256") == snapshot.get("head", {}).get("content_sha256")
        and storage_id_for(**value["storage"]) == snapshot.get("head", {}).get("storage_id"), "shadow_baseline_invalid")
    return state, value


def _journal(state, value):
    fd = os.open(state / "object-attempts.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "ab") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_mode & 0o077 == 0, "shadow_journal_not_private")
        stream.write(packed(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def create_shadow_app(state, *, app_config=None):
    from flask import Flask
    from routes.internal import course_storage as routes
    from services.internal_request_guard import InternalRequestGuard
    from services import course_file_writer
    state, baseline = _load(state)
    app_config = app_config or AppConfig.from_env()
    config = replace(CourseStorageConfig.from_env(), mode="registry")
    require(storage_identity(config.endpoint, config.bucket, config.region) == baseline["storage"], "shadow_storage_changed")
    database = ShadowDatabase(state / "shadow.sqlite3")
    class AuditRepository:
        transaction = database.transaction
        def create_internal_audit_event(self, conn, **fields):
            identity = uuid.uuid4().hex
            conn.execute("INSERT INTO shadow_internal_audits VALUES(?,?)", (identity, packed(fields).decode()))
            return {"id": identity}
    guard = InternalRequestGuard(app_config.DATABASE_URL, token=app_config.INTERNAL_API_TOKEN, allowed_sources=["127.0.0.1", "::1"])
    guard.repository = AuditRepository()
    class RecordingUploader(NodeCourseFileUploader):
        def upload(self, *, object_key, raw, storage):
            attempt = {"objectKey": object_key, "sha256": digest(raw), "byteSize": len(raw), "storage": storage}
            _journal(state, {"phase": "attempt", **attempt})
            result = super().upload(object_key=object_key, raw=raw, storage=storage)
            _journal(state, {"phase": "verified", **attempt, "locator": result})
            return result
    original = (routes.Database, routes.internal_request_guard, routes.CourseStorageConfig, course_file_writer.NodeCourseFileUploader)
    class ShadowConfig:
        @staticmethod
        def from_env():
            return config
    def selected_database(url):
        require(url == "private-course-shadow", "shadow_real_database_write_forbidden")
        return database
    routes.Database, routes.internal_request_guard, routes.CourseStorageConfig = selected_database, lambda: guard, ShadowConfig
    course_file_writer.NodeCourseFileUploader = RecordingUploader
    app = Flask(__name__)
    app.config["DATABASE_URL"] = "private-course-shadow"
    app.register_blueprint(routes.internal_course_storage_bp, url_prefix="/internal/learning/course-storage")
    def restore():
        routes.Database, routes.internal_request_guard, routes.CourseStorageConfig, course_file_writer.NodeCourseFileUploader = original
    return app, restore


def _loopback(url):
    parsed = urlsplit(url)
    require(parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1"}
        and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        and parsed.path in {"", "/"} and parsed.port is not None, "shadow_loopback_url_required")
    return url.rstrip("/")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ShadowVerificationError("shadow_redirect_forbidden")


def _http(url, *, method="GET", body=None, headers=None):
    # Each caller constructs only the two fixed local API paths below.
    request = Request(url, data=body, method=method, headers=headers or {})
    try:
        response = build_opener(_NoRedirect()).open(request, timeout=90)
    except HTTPError as error:
        response = error
    with response:
        data = response.read(MAX_HTTP + 1)
        require(len(data) <= MAX_HTTP, "shadow_response_too_large")
        return response.status, response.headers, data


def verify(state, runtime_url, backend_url, *, app_config=None, database=None):
    state, baseline = _load(state)
    runtime_url, backend_url = _loopback(runtime_url), _loopback(backend_url)
    require(runtime_url != backend_url, "shadow_endpoints_must_differ")
    app_config = app_config or AppConfig.from_env()
    database = database or ReadOnlyDatabase(Database(app_config.DATABASE_URL))
    def source_unchanged():
        require(digest(packed(_snapshot(database, baseline["previewKey"], baseline["storage"]))) == baseline["baselineSha256"],
                "shadow_real_source_changed")
    source_unchanged()
    url = runtime_url + "/api/classroom?" + urlencode({"id": baseline["classroomId"]})
    try:
        code, headers, body = _http(url)
        require(code == 200 and headers.get("X-Mira-File-Sha256") == baseline["originalSha256"], "shadow_native_not_bound_to_original")
        original = json.loads(body)["classroom"]
        changed = deepcopy(original)
        changed["stage"]["name"] = str(original["stage"].get("name") or "课件") + "〔存储写入验收〕"
        code, edited_headers, _ = _http(runtime_url + "/api/classroom", method="POST", body=packed(changed),
            headers={"Content-Type": "application/json", "If-Match": baseline["originalSha256"]})
        changed_sha = edited_headers.get("X-Mira-File-Sha256", "")
        require(code == 201 and bool(SHA.fullmatch(changed_sha)) and changed_sha != baseline["originalSha256"], "shadow_native_write_failed")
        code, current_headers, body = _http(url)
        current = json.loads(body).get("classroom") if code == 200 else None
        require(current and current_headers.get("X-Mira-File-Sha256") == changed_sha
            and current["stage"] == changed["stage"] and current["scenes"] == original["scenes"], "shadow_native_readback_failed")
        code, _, _ = _http(runtime_url + "/api/classroom", method="POST", body=packed(original),
            headers={"Content-Type": "application/json", "If-Match": baseline["originalSha256"]})
        require(code == 409, "shadow_stale_write_was_not_rejected")
        code, old_headers, old_body = _http(backend_url + "/internal/learning/course-storage/file?" + urlencode({"path": baseline["path"], "sha256": baseline["originalSha256"]}),
            headers={"X-Mira-Internal-Token": app_config.INTERNAL_API_TOKEN, "X-Mira-Internal-Source": "course-storage-write-verification"})
        require(code == 200 and digest(old_body) == baseline["originalSha256"]
            and old_headers.get("X-Mira-File-Source") == "remote", "shadow_old_version_not_retained")
        code, restored_headers, _ = _http(runtime_url + "/api/classroom", method="POST", body=packed(original),
            headers={"Content-Type": "application/json", "If-Match": changed_sha})
        require(code == 201 and bool(SHA.fullmatch(restored_headers.get("X-Mira-File-Sha256", ""))), "shadow_restore_version_failed")
        code, _, body = _http(url)
        final = json.loads(body).get("classroom") if code == 200 else None
        require(final and final["stage"] == original["stage"] and final["scenes"] == original["scenes"], "shadow_final_readback_failed")
    finally:
        source_unchanged()
    result = {"ok": True, "previewKey": baseline["previewKey"], "classroomId": baseline["classroomId"],
        "realDatabaseUnchanged": True, "oldVersionReadback": True, "staleWriteRejected": True,
        "runtimeReadUrl": runtime_url, "objectJournal": str(state / "object-attempts.jsonl")}
    _private_write(state / ("verified-" + uuid.uuid4().hex + ".json"), packed(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--preview-key", required=True)
    setup.add_argument("--state-root", type=Path, default=None)
    server = commands.add_parser("serve")
    server.add_argument("--state-root", type=Path, required=True)
    server.add_argument("--port", type=int, default=8003)
    check = commands.add_parser("verify")
    check.add_argument("--state-root", type=Path, required=True)
    check.add_argument("--runtime-read-url", required=True)
    check.add_argument("--backend-read-url", default="http://127.0.0.1:8003")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            state = args.state_root or STATE_ROOT / (time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
            result = prepare(args.preview_key, state)
            print(json.dumps({**result, "stateRoot": str(state)}, ensure_ascii=False))
        elif args.command == "serve":
            require(1024 <= args.port <= 65535, "shadow_port_invalid")
            app, restore = create_shadow_app(args.state_root)
            try:
                app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False, threaded=False)
            finally:
                restore()
        else:
            print(json.dumps(verify(args.state_root, args.runtime_read_url, args.backend_read_url), ensure_ascii=False))
    except Exception as error:
        code = str(error) if isinstance(error, ShadowVerificationError) and re.fullmatch(r"[a-z0-9_]+", str(error)) else "course_storage_write_verification_failed"
        print(json.dumps({"ok": False, "error": code}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
