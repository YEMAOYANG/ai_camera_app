"""Private, immutable course-file versions; registration never reads source bytes."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
import time
from urllib.parse import urlsplit


SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_LOCATOR_BYTES = 16 * 1024
MAX_SCOPE_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 ** 3
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ROOTS = ("output/", "backend/data/learning-media/", "backend/content/textbooks/",
          "openmaic-runtime/.runtime/OpenMAIC/data/", "openmaic-runtime/native-assets/review-assets/")
_FORBIDDEN = {".git", "git", "node_modules", ".next", ".codex", ".agents", ".ssh", ".aws"}
_SECRET_NAMES = {"owner.cookies", "cookies", "cookies.json", "credentials", "credentials.json",
                 "credentials.toml", "id_rsa", "id_ed25519"}
_INDEXES = {"previewKey": "preview_key", "contentKey": "content_key", "classroomId": "classroom_id",
            "courseId": "course_id", "courseVersion": "course_version"}


class CourseStorageRegistryError(ValueError):
    """Only stable error codes cross an API boundary."""


def _fail(code):
    raise CourseStorageRegistryError(code)


def _json(value):
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
        return result
    except (TypeError, ValueError, UnicodeError, RecursionError):
        _fail("course_storage_metadata_invalid")


def _sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        _fail("course_storage_sha_invalid")
    return value


def _relative(value, *, source=False, max_bytes=4096):
    try:
        size = len(value.encode("utf-8")) if isinstance(value, str) else 0
    except UnicodeError:
        _fail("course_storage_path_invalid")
    if (not isinstance(value, str) or not value or value != value.strip() or "\\" in value
            or _CONTROL.search(value) or value.startswith("/") or re.match(r"^[A-Za-z]:", value)
            or size > max_bytes
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        _fail("course_storage_path_invalid")
    parts = [p.lower() for p in value.split("/")]
    if any(p in _FORBIDDEN or p in _SECRET_NAMES or p == ".env" or p.startswith(".env.")
           or p.endswith((".pem", ".key", ".cookies")) for p in parts):
        _fail("course_storage_path_forbidden")
    if source and not value.startswith(_ROOTS):
        _fail("course_storage_path_forbidden")
    return value


def normalize_source_path(value):
    return _relative(value, source=True)


def storage_identity(endpoint, bucket, region="us-east-1"):
    """Exactly the queue identity: normalized endpoint/bucket/region, no prefix."""
    try:
        p = urlsplit(endpoint)
        if (p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password
                or p.path not in {"", "/"} or p.query or p.fragment
                or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", region)):
            raise ValueError()
        host = p.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        port = p.port
        if port and port != (443 if p.scheme == "https" else 80):
            host += ":" + str(port)
        return {"endpoint": p.scheme + "://" + host, "bucket": bucket, "region": region}
    except (TypeError, ValueError, AttributeError):
        _fail("course_storage_identity_invalid")


def storage_id_for(endpoint, bucket, region="us-east-1"):
    return hashlib.sha256(_json(storage_identity(endpoint, bucket, region)).encode()).hexdigest()


def _locator(value):
    if not isinstance(value, dict):
        _fail("course_storage_locator_invalid")
    required = {"kind", "objectKey", "etag"}
    if value.get("kind") == "zip_member":
        required |= {"archiveSha256", "archiveByteSize", "memberPath"}
    elif value.get("kind") != "object":
        _fail("course_storage_locator_invalid")
    if not required <= set(value) or set(value) - required - {"versionId"}:
        _fail("course_storage_locator_invalid")
    _relative(value["objectKey"], max_bytes=1024)
    etag = value["etag"]
    if (not isinstance(etag, str) or len(etag) > 1024
            or not re.fullmatch(r'"[A-Za-z0-9._-]+"|[A-Za-z0-9._-]+', etag)):
        _fail("course_storage_locator_invalid")
    if "versionId" in value and (not isinstance(value["versionId"], str) or not value["versionId"]
            or len(value["versionId"].encode()) > 1024 or _CONTROL.search(value["versionId"])):
        _fail("course_storage_locator_invalid")
    if value["kind"] == "zip_member":
        _sha(value["archiveSha256"])
        if type(value["archiveByteSize"]) is not int or not 0 < value["archiveByteSize"] <= MAX_FILE_BYTES:
            _fail("course_storage_locator_invalid")
        _relative(value["memberPath"])
    if len(_json(value).encode()) > MAX_LOCATOR_BYTES:
        _fail("course_storage_locator_invalid")
    return deepcopy(value)


def _file(value):
    if not isinstance(value, dict):
        _fail("course_storage_file_invalid")
    path = normalize_source_path(value.get("sourcePath"))
    digest = _sha(value.get("sha256"))
    size, mime = value.get("byteSize"), value.get("mimeType")
    mime = {"audio/x-wav": "audio/wav", "audio/mp3": "audio/mpeg", "image/jpg": "image/jpeg"}.get(mime, mime) if isinstance(mime, str) else mime
    if (type(size) is not int or not 0 <= size <= MAX_FILE_BYTES or not isinstance(mime, str)
            or len(mime) > 128 or not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", mime)):
        _fail("course_storage_file_invalid")
    return {"sourcePath": path, "sourcePathSha256": hashlib.sha256(path.encode()).hexdigest(),
            "sha256": digest, "byteSize": size, "mimeType": mime, "locator": _locator(value.get("locator"))}


class CourseStorageRepository:
    def __init__(self, database):
        self.database = database

    def _decoded_file(self, row):
        if row is None:
            return None
        try:
            value = _file({"sourcePath": row["source_path"], "sha256": row["content_sha256"],
                "byteSize": row["byte_size"], "mimeType": row["mime_type"], "locator": json.loads(row["locator_json"])})
            if value["sourcePathSha256"] != row["source_path_sha256"]:
                _fail("course_storage_record_invalid")
            return {"storageId": _sha(row["storage_id"]), "path": value["sourcePath"], **value}
        except (KeyError, TypeError, ValueError):
            _fail("course_storage_record_invalid")

    def resolve(self, source_path, storage_id, expected_sha=None):
        path, storage_id = normalize_source_path(source_path), _sha(storage_id)
        if expected_sha is not None:
            expected_sha = _sha(expected_sha)
        path_sha = hashlib.sha256(path.encode()).hexdigest()
        with self.database.transaction() as conn:
            if expected_sha is not None:
                row = conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? AND source_path_sha256=? AND content_sha256=?",
                    (storage_id, path_sha, expected_sha)).fetchone()
            else:
                row = conn.execute("SELECT f.* FROM course_storage_heads h JOIN course_storage_files f ON f.storage_id=h.storage_id "
                    "AND f.source_path_sha256=h.source_path_sha256 AND f.content_sha256=h.content_sha256 "
                    "WHERE h.storage_id=? AND h.source_path_sha256=?", (storage_id, path_sha)).fetchone()
            result = self._decoded_file(row)
            if result and result["sourcePath"] != path:
                _fail("course_storage_record_invalid")
            return result

    @staticmethod
    def _decoded_scope(row):
        if row is None:
            return None
        try:
            meta, bindings = json.loads(row["scope_json"]), json.loads(row["bindings_json"])
            if (not isinstance(meta, dict) or meta.get("scopeKey") != row["scope_key"]
                    or not isinstance(bindings, list)
                    or len(_json(meta).encode()) + len(_json(bindings).encode()) > MAX_SCOPE_BYTES):
                _fail("course_storage_record_invalid")
            for entry in bindings:
                p = normalize_source_path(entry["sourcePath"])
                if entry["sourcePathSha256"] != hashlib.sha256(p.encode()).hexdigest():
                    _fail("course_storage_record_invalid")
                _sha(entry["sha256"])
            for field, column in _INDEXES.items():
                if meta.get(field) != row[column]:
                    _fail("course_storage_record_invalid")
            return {"storageId": _sha(row["storage_id"]), "scopeKey": _sha(row["scope_key"]),
                    "metadata": meta, "bindings": bindings}
        except (KeyError, TypeError, ValueError):
            _fail("course_storage_record_invalid")

    def scope(self, scope_key, storage_id):
        with self.database.transaction() as conn:
            return self._decoded_scope(conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=?",
                (_sha(storage_id), _sha(scope_key))).fetchone())

    def _head_scope(self, conn, path, storage_id, *, lock=False):
        path_sha = hashlib.sha256(path.encode()).hexdigest()
        suffix = " FOR UPDATE" if lock else ""
        head = conn.execute("SELECT * FROM course_storage_heads WHERE storage_id=? AND source_path_sha256=?" + suffix,
                            (storage_id, path_sha)).fetchone()
        if head is None:
            return None, None
        record = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? "
            "AND source_path_sha256=? AND content_sha256=?" + suffix,
            (storage_id, path_sha, head["content_sha256"])).fetchone())
        scope = self._decoded_scope(conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=?" + suffix,
                                               (storage_id, head["scope_key"])).fetchone())
        if (record is None or record["sourcePath"] != path or scope is None
                or not any(e["sourcePath"] == path and e["sha256"] == record["sha256"] for e in scope["bindings"])):
            _fail("course_storage_record_invalid")
        return head, scope

    def head_scope(self, source_path, storage_id):
        """Return the scope selected by this exact current head, not any matching scope."""
        path, storage_id = normalize_source_path(source_path), _sha(storage_id)
        with self.database.transaction() as conn:
            return self._head_scope(conn, path, storage_id)[1]

    def paths_under(self, source_directory, storage_id):
        """List active registered source files within one exact directory boundary."""
        directory = _relative(source_directory)
        prefix = directory + "/"
        if not prefix.startswith(_ROOTS):
            _fail("course_storage_path_forbidden")
        pattern = prefix.replace("=", "==").replace("%", "=%").replace("_", "=_") + "%"
        with self.database.transaction() as conn:
            rows = conn.execute("SELECT f.source_path FROM course_storage_heads h JOIN course_storage_files f "
                "ON f.storage_id=h.storage_id AND f.source_path_sha256=h.source_path_sha256 "
                "AND f.content_sha256=h.content_sha256 WHERE h.storage_id=? AND f.source_path LIKE ? ESCAPE '=' "
                "ORDER BY f.source_path", (_sha(storage_id), pattern)).fetchall()
            result = [normalize_source_path(row["source_path"]) for row in rows]
            if any(not path.startswith(prefix) for path in result):
                _fail("course_storage_record_invalid")
            return result

    def find_scopes(self, *, storage_id, preview_key=None, content_key=None, classroom_id=None,
                    course_id=None, course_version=None):
        selected = {"previewKey": preview_key, "contentKey": content_key, "classroomId": classroom_id,
                    "courseId": course_id, "courseVersion": course_version}
        where, params = ["storage_id=?"], [_sha(storage_id)]
        for field, value in selected.items():
            if value is None:
                continue
            self._metadata_index(field, value)
            where.append(_INDEXES[field] + "=?")
            params.append(value)
        if len(where) == 1:
            _fail("course_storage_scope_filter_required")
        with self.database.transaction() as conn:
            rows = conn.execute("SELECT * FROM course_storage_scopes WHERE " + " AND ".join(where) + " ORDER BY scope_key",
                                params).fetchall()
            return [self._decoded_scope(row) for row in rows]

    @staticmethod
    def _metadata_index(field, value):
        if field in {"previewKey", "contentKey"}:
            _sha(value)
        elif (not isinstance(value, str) or not 1 <= len(value) <= 255 or _CONTROL.search(value)):
            _fail("course_storage_metadata_invalid")

    def _prepare_scope(self, scope_meta, files, storage_id):
        storage_id = _sha(storage_id)
        if not isinstance(scope_meta, dict) or not isinstance(files, list) or not files:
            _fail("course_storage_scope_invalid")
        meta = deepcopy(scope_meta)
        key = _sha(meta.get("scopeKey"))
        for field in _INDEXES:
            if meta.get(field) is not None:
                self._metadata_index(field, meta[field])
        normalized = sorted((_file(value) for value in files), key=lambda entry: entry["sourcePath"])
        if len({v["sourcePath"] for v in normalized}) != len(normalized):
            _fail("course_storage_duplicate_path")
        bindings = [{k: e[k] for k in ("sourcePath", "sourcePathSha256", "sha256")} for e in normalized]
        meta_json, bindings_json = _json(meta), _json(bindings)
        if len(meta_json.encode()) + len(bindings_json.encode()) > MAX_SCOPE_BYTES:
            _fail("course_storage_scope_too_large")
        return storage_id, key, meta, normalized, meta_json, bindings_json

    def register_scope(self, scope_meta, files, storage_id, *, activate=True):
        if type(activate) is not bool:
            _fail("course_storage_scope_invalid")
        storage_id, key, meta, normalized, meta_json, bindings_json = self._prepare_scope(scope_meta, files, storage_id)
        now = int(time.time() * 1000)
        with self.database.transaction() as conn:
            conn.execute("INSERT INTO course_storage_scopes(storage_id,scope_key,preview_key,content_key,classroom_id,course_id,course_version,scope_json,bindings_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (storage_id, key, *(meta.get(field) for field in _INDEXES), meta_json, bindings_json, now))
            saved = conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=? FOR UPDATE",
                                 (storage_id, key)).fetchone()
            if (saved is None or saved["scope_json"] != meta_json or saved["bindings_json"] != bindings_json):
                _fail("course_storage_scope_conflict")
            for value in normalized:
                identity = storage_id, value["sourcePathSha256"], value["sha256"]
                conn.execute("INSERT INTO course_storage_files(storage_id,source_path_sha256,content_sha256,source_path,byte_size,mime_type,locator_json,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                    (*identity, value["sourcePath"], value["byteSize"], value["mimeType"], _json(value["locator"]), now))
                existing = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? AND source_path_sha256=? AND content_sha256=? FOR UPDATE",
                                                          identity).fetchone())
                if existing is None or any(existing[k] != value[k] for k in ("sourcePath", "sha256", "byteSize", "mimeType")):
                    _fail("course_storage_file_conflict")
                # A shared original can occur in several verified ZIPs. Keep the
                # first locator immutable; a later scope binds that same version.
                if activate:
                    conn.execute("INSERT INTO course_storage_heads(storage_id,source_path_sha256,content_sha256,scope_key,updated_at) "
                        "VALUES(?,?,?,?,?) ON CONFLICT (storage_id, source_path_sha256) DO UPDATE SET content_sha256=EXCLUDED.content_sha256,scope_key=EXCLUDED.scope_key,updated_at=EXCLUDED.updated_at",
                        (*identity, key, now))
            return self._decoded_scope(saved)

    def compare_and_activate(self, scope_meta, files, storage_id, *, expected_old_sha,
                             expected_scope_key=None, before_activate=None):
        """Preserve immutable versions and advance one existing head atomically.

        The optional lifecycle check runs inside the head lock before any write.
        A stale SHA/scope or any validation failure leaves no scope or version.
        """
        if not isinstance(files, list) or len(files) != 1 or (before_activate is not None and not callable(before_activate)):
            _fail("course_storage_head_selection_invalid")
        expected_old_sha = _sha(expected_old_sha)
        if expected_scope_key is not None:
            expected_scope_key = _sha(expected_scope_key)
        storage_id, key, meta, normalized, meta_json, bindings_json = self._prepare_scope(scope_meta, files, storage_id)
        value = normalized[0]
        identity = storage_id, value["sourcePathSha256"], value["sha256"]
        with self.database.transaction() as conn:
            head, _ = self._head_scope(conn, value["sourcePath"], storage_id, lock=True)
            if head is None:
                _fail("course_storage_head_not_found")
            if (head["content_sha256"] != expected_old_sha
                    or (expected_scope_key is not None and head["scope_key"] != expected_scope_key)):
                _fail("course_storage_head_conflict")
            saved = conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=? FOR UPDATE",
                                 (storage_id, key)).fetchone()
            if saved is not None and (saved["scope_json"] != meta_json or saved["bindings_json"] != bindings_json):
                _fail("course_storage_scope_conflict")
            existing = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? "
                "AND source_path_sha256=? AND content_sha256=? FOR UPDATE", identity).fetchone())
            if existing is not None and any(existing[k] != value[k] for k in ("sourcePath", "sha256", "byteSize", "mimeType")):
                _fail("course_storage_file_conflict")
            if before_activate is not None:
                before_activate(conn)
            now = int(time.time() * 1000)
            conn.execute("INSERT INTO course_storage_scopes(storage_id,scope_key,preview_key,content_key,classroom_id,course_id,course_version,scope_json,bindings_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (storage_id, key, *(meta.get(field) for field in _INDEXES), meta_json, bindings_json, now))
            saved = conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=? FOR UPDATE",
                                 (storage_id, key)).fetchone()
            if saved is None or saved["scope_json"] != meta_json or saved["bindings_json"] != bindings_json:
                _fail("course_storage_scope_conflict")
            conn.execute("INSERT INTO course_storage_files(storage_id,source_path_sha256,content_sha256,source_path,byte_size,mime_type,locator_json,created_at) "
                "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
                (*identity, value["sourcePath"], value["byteSize"], value["mimeType"], _json(value["locator"]), now))
            existing = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? "
                "AND source_path_sha256=? AND content_sha256=? FOR UPDATE", identity).fetchone())
            if existing is None or any(existing[k] != value[k] for k in ("sourcePath", "sha256", "byteSize", "mimeType")):
                _fail("course_storage_file_conflict")
            # Preserve the first locator for any already registered exact version.
            if head["content_sha256"] != value["sha256"] or head["scope_key"] != key:
                changed = conn.execute("UPDATE course_storage_heads SET content_sha256=?,scope_key=?,updated_at=? "
                    "WHERE storage_id=? AND source_path_sha256=? AND content_sha256=? AND scope_key=?",
                    (value["sha256"], key, now, storage_id, value["sourcePathSha256"], expected_old_sha, head["scope_key"]))
                if changed.rowcount != 1:
                    _fail("course_storage_head_conflict")
            return self._decoded_scope(saved)

    def activate_heads(self, scope_key, source_hashes, storage_id):
        """Activate an explicit subset only after checking every scope/file version.

        Bulk imports register scopes inactive, then select heads from current
        source hashes. Scope iteration order must never choose a mutable file.
        """
        scope_key, storage_id = _sha(scope_key), _sha(storage_id)
        if not isinstance(source_hashes, dict) or not source_hashes:
            _fail("course_storage_head_selection_invalid")
        selected = sorted((normalize_source_path(path), _sha(sha)) for path, sha in source_hashes.items())
        with self.database.transaction() as conn:
            row = conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=? FOR UPDATE",
                               (storage_id, scope_key)).fetchone()
            scope = self._decoded_scope(row)
            if scope is None:
                _fail("course_storage_scope_not_found")
            by_path = {entry["sourcePath"]: entry for entry in scope["bindings"]}
            accepted = []
            for path, sha in selected:
                binding = by_path.get(path)
                if binding is None or binding["sha256"] != sha:
                    _fail("course_storage_head_not_bound")
                record = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? "
                    "AND source_path_sha256=? AND content_sha256=? FOR UPDATE",
                    (storage_id, binding["sourcePathSha256"], sha)).fetchone())
                if record is None or record["sourcePath"] != path:
                    _fail("course_storage_head_file_missing")
                accepted.append(binding)
            now = int(time.time() * 1000)
            for binding in accepted:
                conn.execute("INSERT INTO course_storage_heads(storage_id,source_path_sha256,content_sha256,scope_key,updated_at) "
                    "VALUES(?,?,?,?,?) ON CONFLICT (storage_id, source_path_sha256) DO UPDATE SET content_sha256=EXCLUDED.content_sha256,scope_key=EXCLUDED.scope_key,updated_at=EXCLUDED.updated_at",
                    (storage_id, binding["sourcePathSha256"], binding["sha256"], scope_key, now))
            return {"storageId": storage_id, "scopeKey": scope_key, "activated": len(accepted), "bindings": accepted}

    def activate_missing_heads(self, scope_key, storage_id):
        """Attach newly archived paths without replacing any working version.

        An archive is an immutable capture, which may finish uploading after a
        newer edit. Existing heads always win, including an identical SHA with
        another owner. Conflicting concurrent inserts roll back this activation.
        """
        scope_key, storage_id = _sha(scope_key), _sha(storage_id)
        with self.database.transaction() as conn:
            scope = self._decoded_scope(conn.execute(
                "SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=? FOR UPDATE",
                (storage_id, scope_key)).fetchone())
            if scope is None:
                _fail("course_storage_scope_not_found")
            pending = []
            for binding in sorted(scope['bindings'], key=lambda e: e['sourcePath']):
                record = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? "
                    "AND source_path_sha256=? AND content_sha256=? FOR UPDATE",
                    (storage_id, binding['sourcePathSha256'], binding['sha256'])).fetchone())
                if record is None or record['sourcePath'] != binding['sourcePath']:
                    _fail('course_storage_head_file_missing')
                head = conn.execute("SELECT * FROM course_storage_heads WHERE storage_id=? AND source_path_sha256=? FOR UPDATE",
                                    (storage_id, binding['sourcePathSha256'])).fetchone()
                if head is None:
                    pending.append(binding)
            now = int(time.time() * 1000)
            for binding in pending:
                try:
                    conn.execute("INSERT INTO course_storage_heads(storage_id,source_path_sha256,content_sha256,scope_key,updated_at) VALUES(?,?,?,?,?)",
                        (storage_id, binding['sourcePathSha256'], binding['sha256'], scope_key, now))
                except Exception as error:
                    if error.args and error.args[0] == 1062:
                        _fail('course_storage_head_conflict')
                    raise
            return {'storageId': storage_id, 'scopeKey': scope_key, 'activated': len(pending),
                    'preserved': len(scope['bindings']) - len(pending)}

    def activate_heads_if_unchanged(self, scope_key, storage_id, expected_heads):
        """Activate a complete verified scope only if every planned head is unchanged.

        None requires a still-missing head. An existing head must match both its
        content SHA and owning scope. No upsert can replace a concurrent insert.
        """
        scope_key, storage_id = _sha(scope_key), _sha(storage_id)
        if not isinstance(expected_heads, dict) or not expected_heads:
            _fail("course_storage_head_selection_invalid")
        expected = {}
        for path, head in expected_heads.items():
            path = normalize_source_path(path)
            if head is not None:
                if not isinstance(head, dict) or set(head) != {"sha256", "scopeKey"}:
                    _fail("course_storage_head_selection_invalid")
                head = {"sha256": _sha(head["sha256"]), "scopeKey": _sha(head["scopeKey"])}
            expected[path] = head
        with self.database.transaction() as conn:
            scope = self._decoded_scope(conn.execute("SELECT * FROM course_storage_scopes WHERE storage_id=? AND scope_key=? FOR UPDATE",
                                                    (storage_id, scope_key)).fetchone())
            if scope is None:
                _fail("course_storage_scope_not_found")
            bindings = sorted(scope["bindings"], key=lambda e: e["sourcePath"])
            if len(bindings) != len(expected) or {e["sourcePath"] for e in bindings} != set(expected):
                _fail("course_storage_head_not_bound")
            accepted = []
            for binding in bindings:
                record = self._decoded_file(conn.execute("SELECT * FROM course_storage_files WHERE storage_id=? "
                    "AND source_path_sha256=? AND content_sha256=? FOR UPDATE",
                    (storage_id, binding["sourcePathSha256"], binding["sha256"])).fetchone())
                if record is None or record["sourcePath"] != binding["sourcePath"]:
                    _fail("course_storage_head_file_missing")
                current, _ = self._head_scope(conn, binding["sourcePath"], storage_id, lock=True)
                old = expected[binding["sourcePath"]]
                if ((old is None and current is not None) or (old is not None and
                        (current is None or current["content_sha256"] != old["sha256"] or current["scope_key"] != old["scopeKey"]))):
                    _fail("course_storage_head_conflict")
                accepted.append((binding, old))
            now = int(time.time() * 1000)
            for binding, old in accepted:
                if old is None:
                    try:
                        conn.execute("INSERT INTO course_storage_heads(storage_id,source_path_sha256,content_sha256,scope_key,updated_at) VALUES(?,?,?,?,?)",
                            (storage_id, binding["sourcePathSha256"], binding["sha256"], scope_key, now))
                    except Exception as error:
                        # MySQL duplicate-key race: never turn this into an upsert.
                        if error.args and error.args[0] == 1062:
                            _fail("course_storage_head_conflict")
                        raise
                elif old != {"sha256": binding["sha256"], "scopeKey": scope_key}:
                    changed = conn.execute("UPDATE course_storage_heads SET content_sha256=?,scope_key=?,updated_at=? "
                        "WHERE storage_id=? AND source_path_sha256=? AND content_sha256=? AND scope_key=?",
                        (binding["sha256"], scope_key, now, storage_id, binding["sourcePathSha256"], old["sha256"], old["scopeKey"]))
                    if changed.rowcount != 1:
                        _fail("course_storage_head_conflict")
            return {"storageId": storage_id, "scopeKey": scope_key, "activated": len(accepted), "bindings": bindings}
