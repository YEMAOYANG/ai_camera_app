"""Export one course's exact, owned teaching artifacts without changing authority.

This is a Mira archive, not the OpenMAIC .maic interchange format. Database
reads, original files and verified delivery bytes are collected in a private
directory. Uploading, deleting, generation and publication are separate jobs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import uuid
import zipfile

from scripts import course_storage_releases as releases
from services.course_media_object_store import CourseMediaObjectStore
from core.course_storage_config import CourseStorageConfig


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "mira.course-archive.export.v1"
MAX_FILE_BYTES = 768 * 1024 * 1024
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
MAX_FILES = 12000
_ID = re.compile(r"[A-Za-z0-9_.:-]+\Z")
_SECRET_KEYS = frozenset({"apikey", "accesskey", "accesskeyid", "secretaccesskey", "secretkey", "password",
    "accesstoken", "refreshtoken", "runtimetoken", "cookie", "cookies", "privatekey",
    "clientsecret", "sessiontoken", "internalapitoken", "providerkey", "bearertoken",
    "tokenhash", "principalid", "childid", "familyid", "learningsessionid"})
_CREDENTIAL_NAMES = frozenset({"owner.cookies", ".env", ".env.local", ".env.production",
    "cookies.json", "storage-state.json", "storageState.json"})
_SOURCE_TEXT_EXTENSIONS = frozenset({".html", ".htm", ".md", ".txt", ".svg", ".csv",
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".scss", ".sass",
    ".less", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh", ".bash", ".zsh",
    ".sql", ".patch", ".diff", ".sha256", ".text", ".rst", ".xml", ".xhtml",
    ".sse", ".jsonl", ".body"})
_SOURCE_EXTENSIONS = frozenset({".json", ".html", ".htm", ".md", ".txt", ".pdf", ".png",
    ".webp", ".jpg", ".jpeg", ".gif", ".svg", ".mp3", ".wav", ".ogg", ".mp4",
    ".webm", ".glb", ".csv"}) | _SOURCE_TEXT_EXTENSIONS
_PRIVATE_RUNTIME_EXCLUSIONS = {
    PurePosixPath("output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard/"
        "u4-l1/teaching-1/quality-repairs/formal-audio-predispatch-recovery-v1/old-build"):
        "retained_private_runtime_recovery_backup",
    PurePosixPath("output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard/"
        "u4-l3/teaching-1/planning/native-operator-staging-0242"):
        "retained_private_runtime_compile_staging",
}
_PUBLIC_IMAGE_URL = re.compile(r"(?<![A-Za-z0-9_./])https://pics[0-7]\.baidu\.com/feed/"
    r"[a-f0-9]{40}\.jpeg@f_auto\?token=[a-f0-9]{32}(?![a-f0-9&/?#A-Za-z0-9_%-])")


class CourseArchiveError(ValueError):
    """Only stable error codes; never include configuration or credential data."""


def _require(value, code):
    if not value:
        raise CourseArchiveError(code)


def _json(value):
    return (releases.canonical(value) + "\n").encode("utf8")


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _hash_file(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _media_mime(name):
    value = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return {"audio/x-wav": "audio/wav", "audio/mp3": "audio/mpeg", "image/jpg": "image/jpeg"}.get(value, value)


def _safe_name(value):
    value = re.sub(r"[\\/\x00-\x1f\x7f-\x9f?#%]", "-", str(value)).strip(" .")
    _require(value and value not in {".", ".."}, "archive_name_invalid")
    while len(value.encode("utf8")) > 160:
        value = value[:-1]
    return value


def _safe_relative(value):
    _require(isinstance(value, str) and "\\" not in value
             and not re.search(r"[\x00-\x1f\x7f-\x9f]", value), "archive_path_invalid")
    parts = value.split("/")
    _require(parts and not any(not p.strip() or p in {".", ".."} for p in parts)
             and not PurePosixPath(value).is_absolute(), "archive_path_invalid")
    return value


def _credential_file(path):
    return any(p in _CREDENTIAL_NAMES or p.startswith(".env.") for p in path.parts) or path.suffix.lower() in {
        ".pem", ".key", ".p12", ".pfx", ".cookies", ".sqlite", ".db", ".log"}


def _private_runtime_exclusion(path):
    # These are explicitly retained operator recovery copies of the compiled
    # application, not lesson originals. Never follow or delete this subtree.
    parts = path.parts
    for root, reason in _PRIVATE_RUNTIME_EXCLUSIONS.items():
        approved = root.parts
        if any(parts[start:start + len(approved)] == approved
               for start in range(len(parts) - len(approved) + 1)):
            return reason
    return None


def _original_suffix(path):
    # Retained repair originals keep their exact backup filename, but use the
    # same parser and credential checks as their underlying source format.
    suffix = path.suffix.lower()
    if suffix in {".before", ".before-finite"}:
        base = Path(path.stem).suffix.lower()
        if base in _SOURCE_EXTENSIONS:
            return base
    return suffix


def _source_text_file(path):
    return _original_suffix(path) in _SOURCE_TEXT_EXTENSIONS or (
        path.name == "LICENSE" and "/provenance/vendor/three-0.160.0/" in path.as_posix())


def _supported_source_file(path):
    return (_original_suffix(path) in _SOURCE_EXTENSIONS or _source_text_file(path)
            or path.name in {"http-original-response.bin", "https-original-response.bin"})


def _check_public(value):
    """Fail closed on actual secret/session values; teaching token counts are OK."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            sensitive = normalized in _SECRET_KEYS or bool(re.search(
                r"(?:apikey|secretkey|accesstoken|refreshtoken|password|privatekey|clientsecret)$", normalized))
            _require(not (sensitive and item not in (None, "", [], {})),
                     "credential_or_student_data_in_artifact")
            # Course audit records also call a human approval explanation
            # "authorization". Only prose is acceptable; HTTP/opaque values
            # remain credentials. Nested approval objects are scanned normally.
            if normalized == "authorization" and isinstance(item, str) and item:
                human_prose = len(item.split()) >= 8 or len(re.findall(r"[\u3400-\u9fff]", item)) >= 4
                _require(human_prose and not re.match(
                    r"\s*(?:Bearer|Basic|Digest|Token|Negotiate|AWS4-HMAC-SHA256)\b", item, re.I),
                         "credential_or_student_data_in_artifact")
            _check_public(item)
    elif isinstance(value, list):
        for item in value:
            _check_public(item)
    elif isinstance(value, str):
        _require(not re.search(r"(?:(?:Bearer|Basic)\s+[A-Za-z0-9._+/=-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY|"
                               r"\b(?:tbpt|tbpr|ompr)_[A-Za-z0-9_-]{16,})", value),
                 "credential_or_student_data_in_artifact")
        _require(not re.search(r"\b(?:postgres(?:ql)?|mysql(?:\+pymysql)?|https?)://[^/\s:@]+:[^@\s]+@", value),
                 "credential_or_student_data_in_artifact")
        # Exact public image anti-hotlink references are research evidence,
        # not account/API credentials. This is a validation copy only; archives
        # retain the original string and byte serialization unchanged.
        credential_scan = _PUBLIC_IMAGE_URL.sub("public-image-reference", value)
        _require(not re.search(r"(?i)(?:[?&](?:api_key|access_token|token|secret)=)[^\s&#\"']+|"
                               r"(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*[\"'][A-Za-z0-9._/-]{12,}", credential_scan),
                 "credential_or_student_data_in_artifact")
        # Serialized JSON columns retain their exact original bytes below.
        if value.lstrip().startswith(("{", "[")):
            try:
                decoded = json.loads(value)
            except (ValueError, RecursionError):
                return
            _check_public(decoded)


def _check_source_text(raw, suffix, *, source_path=None):
    """Inspect inert source/config text without importing or executing it."""
    text = raw.decode("utf8")
    _check_public(text)
    # Logs keep their exact byte serialization. Inspect every complete JSON
    # row/SSE data payload as data; incomplete historical fragments remain text.
    for line in text.splitlines():
        candidate = line.strip()
        if candidate.startswith("data:"):
            candidate = candidate[5:].lstrip()
        if candidate.startswith(("{", "[")):
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            _check_public(value)
    key = (r"(?:[A-Za-z_]{0,80}api[_-]?key|access[_-]?key(?:[_-]?id)?|secret[_-]?(?:access[_-]?)?key|"
           r"access[_-]?token|refresh[_-]?token|runtime[_-]?token|password|cookie|cookies|"
           r"private[_-]?key|client[_-]?secret|internal[_-]?api[_-]?token|session[_-]?token|"
           r"provider[_-]?key|bearer[_-]?token|token[_-]?hash|principal[_-]?id|child[_-]?id|family[_-]?id|"
           r"learning[_-]?session[_-]?id|authorization)")
    # A quoted credential assignment is sensitive even when it is a short
    # literal. Names read from os.environ/process.env are not literal secrets.
    for match in re.finditer(r"(?i)(?<![A-Za-z0-9_])['\"]?(?P<key>" + key +
                             r")[ '\"]*[:=]\s*['\"](?P<value>[^'\"\r\n]*)['\"]", text):
        # `${occupied ? chair.childId : 'empty'}` reads a domain field in a
        # conditional; it does not assign a student's identity. A member's
        # `= 'literal'` assignment and quoted JSON/object keys remain scanned.
        if (match.start() and text[match.start() - 1] == "."
                and re.search(r":\s*['\"]", match[0])):
            continue
        normalized = re.sub(r"[^a-z0-9]", "", match["key"].lower())
        # Preserve inert DOM attribute maps and the exact all-ones UUID used
        # by retained unit-test fixtures. Neither is a live credential. This
        # does not exempt other literals or any directory of source files.
        if normalized == "accesskey" and match["value"] == "accessKey":
            continue
        if (normalized == "cookie" and source_path is not None
                and Path(source_path).name.endswith(".test.ts")
                and match["value"] == "11111111-1111-4111-8111-111111111111"):
            continue
        _check_public({match["key"]: match["value"]})
    if suffix in {".yaml", ".yml", ".toml", ".ini", ".cfg"}:
        for match in re.finditer(r"(?im)^\s*(?:-\s*)?['\"]?(?P<key>" + key +
                                 r")[ '\"]*[:=]\s*(?P<value>[^\r\n#;]*)", text):
            value = match["value"].strip().strip("'\"")
            if value.lower() in {"", "null", "none", "false", "true", "~"} or re.fullmatch(r"\$\{[A-Z_]+\}", value):
                continue
            _check_public({match["key"]: value})


def _inspect_original(raw, path):
    if _original_suffix(path) == ".json":
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            _check_source_text(raw, ".json", source_path=path)
            return None, False
        _check_public(value)
        return value, True
    if _source_text_file(path):
        _check_source_text(raw, _original_suffix(path), source_path=path)
    return None, False


@dataclass
class ArchiveSnapshot:
    """A source adapter must bind these artifacts to one verified course release."""
    identity: dict
    metadata: dict
    classroom: dict
    documents: dict[str, object] = field(default_factory=dict)
    # Repository-relative exact roots, established by the source adapter.
    source_roots: list[Path] = field(default_factory=list)
    source_files: list[Path] = field(default_factory=list)
    private_source_files: list[Path] = field(default_factory=list)
    media: list[dict] = field(default_factory=list)
    recovered_aliases: list[dict] = field(default_factory=list)
    missing_sources: list[dict] = field(default_factory=list)
    status: str = "published"


class CourseArchiveExporter:
    def __init__(self, *, project_root=None, media_store=None, native_document_loader=None,
                 standard_asset_resolver=None):
        self.root = Path(project_root or ROOT).resolve()
        self.native_root = self.root / "openmaic-runtime/.runtime/OpenMAIC"
        self.media_store = media_store or CourseMediaObjectStore(project_root=self.root)
        self.native_document_loader = native_document_loader or self._native_document
        self._workbench_index = None
        self._catalog_file_cache = {}
        self.standard_asset_resolver = standard_asset_resolver or self._standard_assets

    def _binary_original_mime(self, source):
        """A named HTTP response is a PDF only with exact retained evidence."""
        if source.suffix.lower() != ".bin":
            return None
        metadata = self._source_path(source.parent / "metadata.json")
        _require(metadata.is_file() and metadata.stat().st_size <= 64 * 1024,
                 "original_response_evidence_missing")
        records = json.loads(metadata.read_bytes())
        _check_public(records)
        _require(isinstance(records, list), "original_response_evidence_invalid")
        matches = [item for item in records if isinstance(item, dict) and isinstance(item.get("scheme"), str)
            and item.get("scheme") + "-original-response.bin" == source.name]
        _require(len(matches) == 1, "original_response_evidence_invalid")
        record = matches[0]
        _require(record.get("contentType") == "application/pdf" and record.get("startsPDF") is True
            and record.get("bytes") == source.stat().st_size and record.get("sha256") == _hash_file(source),
            "original_response_integrity_mismatch")
        with source.open("rb") as stream:
            header = stream.read(16)
            stream.seek(max(0, source.stat().st_size - 4096))
            tail = stream.read()
        _require(header.startswith(b"%PDF-") and b"%%EOF" in tail, "original_response_format_invalid")
        return "application/pdf"

    def _standard_assets(self, document, *, staging_root):
        """Use the Native DSL's pure enumeration and exact authority resolver."""
        helper = self.root / "openmaic-runtime/scripts/course-archive-assets.mjs"
        if not helper.is_file():
            return {"entries": [], "unresolved": [{"ref": "native-standard-assets",
                "reason": "standard_asset_resolver_unavailable"}]}
        result = subprocess.run(["node", str(helper)],
            input=json.dumps({"snapshot": document, "stageId": document["stage"]["id"],
                              "stagingRoot": str(staging_root)}, ensure_ascii=False),
            text=True, capture_output=True, timeout=90)
        if result.returncode:
            return {"entries": [], "unresolved": [{"ref": "native-standard-assets",
                "reason": "standard_asset_resolution_failed"}]}
        value = json.loads(result.stdout)
        _require(value.get("schemaVersion") == "mira.course-archive.assets.v1"
                 and isinstance(value.get("entries"), list) and isinstance(value.get("unresolved"), list),
                 "standard_asset_resolver_contract_invalid")
        return value

    def list_courses(self, conn, *, include_saved=False):
        """List identities without media reads, generation, session or DB writes."""
        result, published_previews = [], set()
        for key in releases._current_keys(conn, None):
            row = conn.execute("SELECT b.content_key,b.course_id,b.course_version,b.input_json,"
                "JSON_UNQUOTE(JSON_EXTRACT(b.review_json,'$.release.sha256')) AS release_sha256,"
                "b.updated_at AS build_updated_at,c.updated_at AS course_updated_at,"
                "c.title,c.subject,c.grade_code FROM learning_textbook_course_builds b "
                "JOIN learning_courses c ON c.id=b.course_id AND c.version=b.course_version "
                "WHERE b.content_key=?", (key,)).fetchone()
            frozen = releases.parsed(row["input_json"])
            if frozen.get("previewKey"):
                published_previews.add(frozen["previewKey"])
            preview = (conn.execute("SELECT updated_at,result_json FROM learning_textbook_course_previews WHERE preview_key=?",
                (frozen["previewKey"],)).fetchone() if frozen.get("previewKey") else None)
            source_revision = _sha(_json({"buildUpdatedAt": row["build_updated_at"],
                "courseUpdatedAt": row["course_updated_at"], "frozenSha256": _sha(row["input_json"].encode()),
                "releaseSha256": row["release_sha256"], "preview": dict(preview) if preview else None}))
            result.append({"courseId": row["course_id"], "courseVersion": row["course_version"],
                "contentKey": key, "title": row["title"], "subject": row["subject"],
                "gradeCode": row["grade_code"], "status": "published", "sourceKind": "textbook_release",
                "sourceDigest": row["release_sha256"], "releaseSha256": row["release_sha256"],
                "archiveSourceRevision": source_revision})
        for course in releases._other_published_courses(conn):
            authorities = releases._formal_authorities(conn, course)
            _require(len(authorities) == 1, "formal_publication_binding_missing_or_ambiguous")
            digest = authorities[0]["publication_receipt_hash"]
            revision = conn.execute("SELECT MAX(r.updated_at) AS runtime_updated_at,MAX(a.updated_at) AS audio_updated_at,"
                "MAX(receipt.updated_at) AS receipt_updated_at FROM learning_openmaic_runtime_classrooms r "
                "JOIN learning_formal_qwen_audio_jobs a ON a.runtime_classroom_id=r.id "
                "JOIN learning_curriculum_classroom_item_receipts receipt ON receipt.runtime_classroom_id=r.id "
                "WHERE r.course_id=? AND r.course_version=?", (course["courseId"], course["courseVersion"])).fetchone()
            course_revision = conn.execute("SELECT updated_at FROM learning_courses WHERE id=? AND version=?",
                (course["courseId"], course["courseVersion"])).fetchone()
            result.append({**course, "contentKey": None, "status": "published", "sourceKind": "formal_release",
                           "sourceDigest": digest, "releaseSha256": digest,
                           "archiveSourceRevision": _sha(_json({"authority": dict(authorities[0]),
                               "updates": dict(revision), "course": dict(course_revision)}))})
        if include_saved:
            rows = conn.execute("SELECT preview_key,classroom_id,classroom_sha256,status,input_json,result_json,updated_at "
                "FROM learning_textbook_course_previews WHERE classroom_json IS NOT NULL "
                "AND status IN ('preview_ready','review_required') ORDER BY preview_key").fetchall()
            for row in rows:
                if row["preview_key"] in published_previews:
                    continue
                frozen = releases.parsed(row["input_json"])
                result.append({"courseId": "textbook-preview:" + row["preview_key"],
                    "courseVersion": "saved-" + row["classroom_sha256"][:16], "contentKey": None,
                    "previewKey": row["preview_key"], "classroomId": row["classroom_id"],
                    "sourceDigest": row["classroom_sha256"], "title": frozen.get("lessonTitle", "已保存课件"),
                    "subject": frozen.get("subject"), "gradeCode": frozen.get("gradeCode"),
                    "status": "generated_saved", "reviewStatus": row["status"], "sourceKind": "textbook_preview",
                    "archiveSourceRevision": _sha(_json({"classroomSha256": row["classroom_sha256"],
                        "status": row["status"], "updatedAt": row["updated_at"], "input": row["input_json"],
                        "result": row["result_json"]}))})
        return result

    def export_saved_preview(self, conn, *, preview_key, staging_root, release=None):
        """Export a saved/review preview as such, never infer a publication."""
        snapshot, digest = self._saved_preview_snapshot(conn, preview_key)
        return self.export_snapshot(snapshot, staging_root=staging_root, release=release,
            source_kind="textbook_preview", source_digest=digest)

    def _saved_preview_snapshot(self, conn, preview_key):
        _require(isinstance(preview_key, str) and re.fullmatch(r"[a-f0-9]{64}", preview_key),
                 "preview_identity_invalid")
        row = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=?",
                           (preview_key,)).fetchone()
        _require(row and row["status"] in {"preview_ready", "review_required"} and row["classroom_json"],
                 "saved_preview_not_found")
        from content.textbook_catalog import digest
        room = releases.parsed(row["classroom_json"])
        _require(digest(room) == row["classroom_sha256"], "preview_original_hash_mismatch")
        frozen = releases.parsed(row["input_json"])
        course = {"subject": frozen["subject"], "grade_code": frozen["gradeCode"]}
        revision = conn.execute("SELECT * FROM learning_textbook_revisions WHERE edition_id=? AND revision_id=?",
            (row["edition_id"], row["revision_id"])).fetchone()
        manifest = releases.parsed(revision["manifest_json"]) if revision else None
        if revision:
            _require(digest(manifest) == revision["manifest_sha256"], "manifest_hash_mismatch")
        snapshot = ArchiveSnapshot(identity={"courseId": "textbook-preview:" + preview_key,
            "courseVersion": "saved-" + row["classroom_sha256"][:16], "contentKey": None,
            "classroomId": row["classroom_id"], "releaseSha256": None},
            metadata={"title": room.get("stage", {}).get("name") or frozen.get("lessonTitle", "已保存课件"),
                "reviewStatus": row["status"], **releases.release_metadata(course, manifest)},
            classroom=room, documents={"数据库/原始预览记录.json": dict(row),
                "原始课堂.json": row["classroom_json"], "冻结创作请求.json": row["input_json"]},
            status="generated_saved")
        if revision:
            snapshot.documents["数据库/教材目录记录.json"] = dict(revision)
        else:
            snapshot.missing_sources.append({"kind": "textbook_manifest", "reason": "bound_manifest_missing"})
        self._textbook_sources(snapshot, frozen, {"textbookBinding": {
            "editionId": row["edition_id"], "nodeId": row["node_id"], "teachingRevision": "saved"}})
        self._add_native_sources(snapshot, row["classroom_id"])
        self._collect_snapshot_media(snapshot, audio_receipts=releases.parsed(row.get("result_json") or "{}").get("audioReceipts", []))
        return snapshot, row["classroom_sha256"]

    def _owned_source_files(self, snapshot):
        files = set(snapshot.source_files)
        for root in snapshot.source_roots:
            root = self._source_path(root)
            _require(root.is_dir(), "owned_source_root_missing")
            for parent, directories, names in os.walk(root, followlinks=False):
                for name in directories[:]:
                    candidate = Path(parent) / name
                    if _private_runtime_exclusion(candidate):
                        files.add(candidate)
                        directories.remove(name)
                        continue
                    _require(not candidate.is_symlink(), "source_symlink_rejected")
                files.update(Path(parent) / name for name in names)
        return files

    def preflight_course(self, conn, *, course_id, course_version, content_key=None, file_cache=None):
        """Validate all DB metadata and original formats without writing a ZIP.

        Media byte delivery and Native asset resolution still run at export;
        this read-only preflight catches source format/credential issues before
        a large batch allocates staging space. file_cache is per invocation.
        """
        if course_id.startswith("textbook-preview:"):
            snapshot, _ = self._saved_preview_snapshot(conn, course_id.removeprefix("textbook-preview:"))
        else:
            snapshot = self._published_snapshot(conn, course_id, course_version, content_key)
        _require(snapshot.identity["courseId"] == course_id
                 and snapshot.identity["courseVersion"] == course_version, "preflight_identity_mismatch")
        for value in (snapshot.identity, snapshot.metadata, snapshot.classroom, *snapshot.documents.values()):
            _check_public(value)
        counts, failures, excluded, total = {}, [], 0, 0
        sources = self._owned_source_files(snapshot)
        file_cache = file_cache if file_cache is not None else {}
        for source in sorted(sources):
            if _private_runtime_exclusion(source):
                excluded += 1
                continue
            source = self._source_path(source)
            relative = source.relative_to(self.root).as_posix()
            suffix = source.suffix.lower()
            if _credential_file(source) or source.name == ".DS_Store" or suffix in {".lock", ".pid", ".tmp", ".part"}:
                excluded += 1
                continue
            counts[suffix or "<no-extension>"] = counts.get(suffix or "<no-extension>", 0) + 1
            if not _supported_source_file(source):
                failures.append({"sourceIdentity": relative, "reason": "original_requires_safe_format_adapter"})
                continue
            info = source.stat()
            total += info.st_size
            _require(source.is_file() and info.st_size <= MAX_FILE_BYTES, "source_file_unavailable_or_oversized")
            identity = (str(source), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if identity not in file_cache:
                try:
                    self._binary_original_mime(source)
                    if _original_suffix(source) == ".json" or _source_text_file(source):
                        _inspect_original(source.read_bytes(), source)
                    file_cache[identity] = None
                except (CourseArchiveError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    file_cache[identity] = str(error) if isinstance(error, CourseArchiveError) else "invalid_original_text_or_json"
            if file_cache[identity]:
                failures.append({"sourceIdentity": relative, "reason": file_cache[identity]})
        return {"courseId": course_id, "courseVersion": course_version,
            "validation": "metadata_and_original_source_formats", "readyForArchive": not failures and not snapshot.missing_sources,
            "sourceFileCount": len(sources), "sourceBytes": total, "extensionCounts": counts,
            "excludedFileCount": excluded, "missingSources": snapshot.missing_sources, "failures": failures}

    def export_native_snapshot(self, snapshot: dict, *, source_kind: str, source_digest: str,
                               staging_root, meta: dict, authoring_binding: dict | None = None):
        """Public event-worker entry point for one immutable saved Native document.

        source_digest is the canonical JSON hash, or the exact UTF-8 sourceRaw
        hash when that original serialization is supplied in meta. No caller
        cookies, database configuration or student session material is accepted.
        """
        _require(isinstance(snapshot, dict) and isinstance(snapshot.get("stage"), dict)
                 and isinstance(snapshot.get("scenes"), list) and snapshot["scenes"],
                 "native_snapshot_shape_invalid")
        _check_public(snapshot)
        _require(isinstance(meta, dict) and all(isinstance(meta.get(k), str) and meta[k]
                 for k in ("courseId", "courseVersion", "title", "subject", "generatedAt")),
                 "native_snapshot_metadata_missing")
        raw = meta.get("sourceRaw")
        if raw is not None:
            _require(isinstance(raw, str) and json.loads(raw) == snapshot
                     and _sha(raw.encode("utf8")) == source_digest, "native_snapshot_source_digest_mismatch")
        else:
            raw = self._native_canonical(snapshot)
            _require(_sha(raw.encode("utf8")) == source_digest,
                     "native_snapshot_source_digest_mismatch")
        stage_id = snapshot["stage"].get("id")
        _require(isinstance(stage_id, str) and _ID.fullmatch(stage_id), "native_stage_identity_invalid")
        identity = {"courseId": meta["courseId"], "courseVersion": meta["courseVersion"],
                    "contentKey": None, "classroomId": stage_id, "releaseSha256": None}
        subject = meta["subject"]
        metadata = {k: meta[k] for k in ("title", "gradeCode", "gradeLabel", "volumeCode", "volumeLabel", "editionLabel",
            "editionId", "schoolSystem", "storageEditionLabel", "storageGradeLabel") if k in meta}
        metadata.update(subjectCode=subject, subjectName=releases.SUBJECT_NAMES.get(subject, "课程" if subject == "course" else subject),
                        generatedAt=meta["generatedAt"])
        metadata["sourceSerialization"] = "exact-capture" if meta.get("sourceRaw") is not None else "producer-canonical-json-verified"
        # Caller/stage labels alone do not establish a textbook binding. Only
        # the matched frozen job and exact local catalog proof below may do so.
        metadata["storageEditionLabel"] = "未绑定教材（历史课件）"
        bound = ArchiveSnapshot(identity=identity, metadata=metadata, classroom=snapshot,
            documents={"Native终态快照.json": raw}, status="generated_saved")
        self._native_authoring_sources(bound, authoring_binding)
        self._collect_snapshot_media(bound)
        release = {**identity, **({"storageDirectory": meta["storageDirectory"]} if meta.get("storageDirectory") else {})}
        return self.export_snapshot(bound, source_kind=source_kind, source_digest=source_digest,
            staging_root=staging_root, release=release, meta={k: meta[k] for k in ("exportedAt",) if k in meta})

    def export_legacy_classroom(self, classroom_id, *, staging_root, meta=None):
        """Archive one exact legacy whole classroom, including retired versions.

        No publication or student-access inference is made. The calling
        operator supplies any independently established lifecycle metadata.
        """
        _require(isinstance(classroom_id, str) and _ID.fullmatch(classroom_id),
                 "native_stage_identity_invalid")
        directory = self.native_root / "data/classrooms"
        path = (directory / classroom_id / "artifact/classroom.json" if classroom_id.startswith("omclass_")
                else directory / (classroom_id + ".json"))
        path = self._source_path(path)
        _require(path.is_file() and path.stat().st_size <= MAX_FILE_BYTES, "legacy_classroom_source_missing")
        raw = path.read_bytes()
        room = json.loads(raw)
        _require(isinstance(room, dict) and room.get("stage", {}).get("id") == classroom_id
                 and isinstance(room.get("scenes"), list) and room["scenes"], "legacy_classroom_identity_mismatch")
        _check_public(room)
        meta = meta or {}
        _check_public(meta)
        title = room["stage"].get("name") or classroom_id
        subject = meta.get("subject") or room["stage"].get("subject") or "course"
        metadata = {k: meta[k] for k in ("gradeCode", "gradeLabel", "editionLabel", "volumeLabel", "lifecycleStatus", "retired",
            "editionId", "schoolSystem", "storageEditionLabel", "storageGradeLabel") if k in meta}
        if not metadata.get("editionId"):
            metadata["storageEditionLabel"] = "未绑定教材（历史课件）"
        metadata.update(title=title, subjectCode=subject,
                        subjectName=releases.SUBJECT_NAMES.get(subject, "课程" if subject == "course" else subject))
        snapshot = ArchiveSnapshot(identity={"courseId": "native-legacy:" + classroom_id,
            "courseVersion": "saved-original", "contentKey": None,
            "classroomId": classroom_id, "releaseSha256": None}, metadata=metadata,
            classroom=room, documents={"原始课堂.json": raw.decode("utf8")},
            source_files=[path], status="generated_saved")
        if (directory / classroom_id).is_dir():
            snapshot.source_roots.append(directory / classroom_id)
        self._collect_snapshot_media(snapshot)
        return self.export_snapshot(snapshot, staging_root=staging_root,
            source_kind="native_legacy_file", source_digest=_sha(raw),
            meta={k: meta[k] for k in ("exportedAt",) if k in meta})

    def _collect_snapshot_media(self, bound, *, audio_receipts=None):
        media_pattern = re.compile(r"/api/classroom-media/([A-Za-z0-9_-]+)/(audio|media)/([A-Za-z0-9_.-]+)")
        paths = sorted({m.group(0): m for m in media_pattern.finditer(releases.canonical(bound.classroom))}.values(),
                       key=lambda m: m.group(0))
        manifest = None
        for match in paths:
            _require(".." not in match[3], "native_snapshot_media_path_invalid")
            relative = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + match[1] + (
                "/artifact/" if match[1].startswith("omclass_") else "/") + match[2] + "/" + match[3]
            path = self._source_path(relative)
            if path.is_file():
                entry = {"sha256": _hash_file(path), "byteSize": path.stat().st_size,
                    "mimeType": _media_mime(path.name)}
            else:
                if manifest is None:
                    config = self.media_store.config or CourseStorageConfig.from_env()
                    manifest = {} if config.mode == "local" else self.media_store._manifest(config)
                entry = manifest.get(relative)
                if entry is None and match[2] == "media":
                    recovered = self._retained_material_alias(bound, match)
                    if recovered is not None:
                        media, alias, evidence = recovered
                        bound.media.append(media)
                        bound.recovered_aliases.append(alias)
                        bound.source_files.extend(evidence)
                        continue
                if entry is None and match[2] == "audio" and match[3].endswith(".wav"):
                    recovered = self._native_audio_original(match, audio_receipts=audio_receipts)
                    if recovered is not None:
                        entry, job_path, asset_path = recovered
                        bound.source_files.extend((job_path, asset_path))
                        bound.media.append({"path": match[0], "sourcePath": asset_path.relative_to(self.root).as_posix(),
                            "archiveSourcePath": relative,
                            **{k: entry[k] for k in ("sha256", "byteSize", "mimeType")}})
                        continue
                if entry is None:
                    bound.missing_sources.append({"kind": "native_media", "sourceIdentity": relative,
                                                  "reason": "saved_media_source_missing"})
                    continue
            bound.media.append({"path": match[0], "sourcePath": relative,
                                **{k: entry[k] for k in ("sha256", "byteSize", "mimeType")}})

    def _retained_material_alias(self, bound, match):
        """Recover an owned historical typo only from its exact upload proof.

        Filename hash resemblance never authorizes bytes. A frozen job, saved
        stage, upload intent/receipt and material manifest must agree before a
        derived archive sidecar can map the unchanged original reference.
        """
        named = re.fullmatch(r"material-(mat_[A-Za-z0-9_-]+)-([a-f0-9]{64})\.png", match[3])
        if not named or bound.classroom.get("stage", {}).get("id") != match[1]:
            return None
        material_id = named[1]
        candidates = []
        for root in set(bound.source_roots):
            if not root.name.startswith("teaching-"):
                continue
            job = root / "authoring-job"
            attachments = job / "page-assets-v1"
            if not (attachments / "manifest.json").is_file():
                continue
            try:
                paths = [self._source_path(p) for p in (job / "frozen.json", job / "draft.json", job / "state.json", attachments / "manifest.json")]
                _require(all(p.is_file() and p.stat().st_size <= 4 * 1024 * 1024 for p in paths), "material_alias_evidence_invalid")
                frozen, draft, state, manifest = [json.loads(p.read_bytes()) for p in paths]
                binding = frozen.get("binding", {})
                _require(all(binding.get(k) for k in ("editionId", "nodeId"))
                    and root.name == "teaching-" + str(frozen.get("teachingRevision"))
                    and _hash_file(paths[1]) == frozen.get("draftSha256")
                    and any(item.get("stageId") == match[1] for item in state.get("savedStages", []) if isinstance(item, dict)),
                    "material_alias_stage_unbound")
                _require(manifest.get("schemaVersion") == "mira.operator.frozen-material-attachments.v1"
                    and manifest.get("baseDraftSha256") == frozen["draftSha256"]
                    and manifest.get("basePayloadSha256") == frozen.get("payloadSha256")
                    and manifest.get("sha256") == _sha(releases.canonical({k: v for k, v in manifest.items() if k != "sha256"}).encode()),
                    "material_alias_manifest_invalid")
                for receipt_path in attachments.glob("*-receipt.json"):
                    receipt_path = self._source_path(receipt_path)
                    _require(receipt_path.stat().st_size <= 64 * 1024, "material_alias_evidence_invalid")
                    receipt = json.loads(receipt_path.read_bytes())
                    material = receipt.get("response", {}).get("material", {})
                    if material.get("materialId") != material_id:
                        continue
                    intent_path = self._source_path(receipt_path.with_name(receipt_path.name.removesuffix("-receipt.json") + "-intent.json"))
                    _require(intent_path.is_file() and intent_path.stat().st_size <= 64 * 1024, "material_alias_evidence_invalid")
                    intent_raw = intent_path.read_bytes()
                    intent = json.loads(intent_raw)
                    checksum, size = intent.get("sourceSha256"), intent.get("byteSize")
                    _require(receipt.get("intentSha256") == _sha(intent_raw)
                        and intent.get("sessionId") and intent["sessionId"] == state.get("sessionId")
                        and re.fullmatch(r"[a-f0-9]{64}", str(checksum))
                        and type(size) is int and 0 < size <= 32 * 1024 * 1024
                        and material.get("bytes") == size and material.get("mime") == "image/png",
                        "material_alias_intent_invalid")
                    records = [item for item in manifest.get("assets", []) if isinstance(item, dict) and item.get("assetKey") == intent.get("assetKey")]
                    _require(len(records) == 1 and records[0].get("sha256") == checksum
                        and records[0].get("bytes") == size and records[0].get("mimeType") == "image/png",
                        "material_alias_asset_invalid")
                    source = self._source_path(records[0]["sourcePath"])
                    _require(source.is_relative_to(root) and source.is_file() and source.stat().st_size == size
                        and _hash_file(source) == checksum, "material_alias_source_invalid")
                    with source.open("rb") as stream:
                        _require(stream.read(8) == b"\x89PNG\r\n\x1a\n", "material_alias_source_invalid")
                    correct = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + match[1] + "/media/material-" + material_id + "-" + checksum + ".png"
                    evidence = [paths[0], paths[3], intent_path, receipt_path]
                    alias = {"originalReference": match[0], "materialId": material_id,
                        "archivePath": "媒体/" + correct, "sha256": checksum, "byteSize": size, "mimeType": "image/png",
                        "recoveryReason": "historical_material_alias_from_verified_upload_receipt",
                        "evidence": [p.relative_to(self.root).as_posix() for p in evidence]}
                    media = {"path": match[0], "sourcePath": source.relative_to(self.root).as_posix(),
                        "archiveSourcePath": correct, "sha256": checksum, "byteSize": size, "mimeType": "image/png"}
                    candidates.append((media, alias, evidence))
            except (CourseArchiveError, OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
        return candidates[0] if len(candidates) == 1 else None

    def _native_audio_original(self, match, *, audio_receipts=None):
        """Recover an exact old alias from its retained, successful paid receipt.

        No provider API is called. The request owns one hashed job record and
        that record names one bounded local asset. A different encoding or a
        coincidentally similar narration can never satisfy this byte contract.
        """
        request_id = match[3].removesuffix(".wav")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", request_id):
            return None
        audio_root = self.native_root / "data/formal-audio"
        job_path = audio_root / "jobs/tts" / (_sha(request_id.encode("utf8")) + ".json")
        if not job_path.is_file():
            return None
        job_path = self._source_path(job_path)
        job = json.loads(job_path.read_bytes())
        if not (job.get("requestId") == request_id and job.get("classroomId") == match[1]
                and job.get("state") == "succeeded" and job.get("kind") == "tts"
                and re.fullmatch(r"[a-f0-9]{64}", str(job.get("audioSha256", "")))
                and isinstance(job.get("assetFileName"), str)
                and re.fullmatch(r"[A-Za-z0-9_-]+\.wav", job["assetFileName"])
                and type(job.get("sizeBytes")) is int and 0 < job["sizeBytes"] <= 32 * 1024 * 1024
                and job.get("mimeType") == "audio/wav"):
            return None
        if audio_receipts is not None:
            receipts = [r for r in audio_receipts if r.get("requestId") == request_id]
            if not (len(receipts) == 1 and receipts[0].get("status") == "succeeded"
                    and receipts[0].get("audioSha256") == job["audioSha256"]
                    and receipts[0].get("mimeType") == "audio/wav"):
                return None
        asset = self._source_path(audio_root / "assets" / job["assetFileName"])
        if not (asset.is_file() and asset.stat().st_size == job["sizeBytes"]
                and _hash_file(asset) == job["audioSha256"]):
            return None
        return {"sha256": job["audioSha256"], "byteSize": job["sizeBytes"], "mimeType": "audio/wav"}, job_path, asset

    @staticmethod
    def _native_canonical(snapshot):
        # Use the producer's JavaScript number and UTF-16 key serialization.
        # Python JSON differs for 1e-7, integral floats and astral object keys.
        code = r"""let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',()=>{const sort=x=>Array.isArray(x)?x.map(sort):x&&typeof x==='object'?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>[k,sort(v)])):x;process.stdout.write(JSON.stringify(sort(JSON.parse(s))));});"""
        result = subprocess.run(["node", "-e", code], input=releases.canonical(snapshot),
                                text=True, capture_output=True, timeout=15)
        _require(result.returncode == 0 and isinstance(json.loads(result.stdout), dict),
                 "native_snapshot_digest_unavailable")
        return result.stdout

    @classmethod
    def _native_digest(cls, snapshot):
        return _sha(cls._native_canonical(snapshot).encode("utf8"))

    def export_course(self, conn, *, course_id, course_version, staging_root,
                      content_key=None, release=None, source_adapter=None):
        """Read an already-published authority, then export; no commit or upload.

        release may be the existing dated inventory entry: storageDirectory is
        preserved exactly. The caller owns a READ ONLY consistent DB snapshot.
        Future saved-but-unpublished adapters use status='generated_saved' and
        explicitly state which review/publication artifacts are not applicable.
        """
        _require(all(isinstance(x, str) and x and len(x) <= 255 for x in
                     (course_id, course_version)), "course_identity_invalid")
        if source_adapter is None and course_id.startswith("textbook-preview:"):
            result = self.export_saved_preview(conn, preview_key=course_id.removeprefix("textbook-preview:"),
                                               staging_root=staging_root, release=release)
            _require(result["courseVersion"] == course_version, "saved_preview_version_mismatch")
            return result
        snapshot = (source_adapter(conn, course_id=course_id, course_version=course_version,
                                   content_key=content_key) if source_adapter else
                    self._published_snapshot(conn, course_id, course_version, content_key))
        _require(isinstance(snapshot, ArchiveSnapshot)
                 and snapshot.identity.get("courseId") == course_id
                 and snapshot.identity.get("courseVersion") == course_version,
                 "source_adapter_identity_mismatch")
        if release is None and snapshot.status == "published":
            release = self._dated_release(snapshot.identity)
        source = ({"source_kind": "textbook_release" if snapshot.identity.get("contentKey") else "formal_release",
                   "source_digest": snapshot.identity["releaseSha256"]} if snapshot.status == "published" else {})
        return self.export_snapshot(snapshot, staging_root=staging_root, release=release, **source)

    def _dated_release(self, identity):
        """Reuse an existing frozen name; verified new releases derive a name."""
        config = self.media_store.config or CourseStorageConfig.from_env()
        source = Path(config.manifest_path) if config.manifest_path else self.root / "backend/data/course-storage/active-manifest.json"
        if not source.is_file():
            _require(config.mode == "local", "published_storage_directory_manifest_missing")
            return None
        _require(not source.is_symlink() and source.stat().st_size <= 64 * 1024 * 1024,
                 "published_storage_directory_manifest_invalid")
        try:
            # A new course may be absent; an invalid active manifest may not be
            # mistaken for that case. Reuse the media adapter's validation.
            CourseMediaObjectStore._manifest(replace(config, manifest_path=str(source)))
            manifest = json.loads(source.read_bytes())
        except (OSError, ValueError, TypeError):
            raise CourseArchiveError("published_storage_directory_manifest_invalid") from None
        entries = manifest.get("releases", [])
        _require(isinstance(entries, list) and all(isinstance(r, dict)
            and all(isinstance(r.get(k), str) and r[k] for k in ("courseId", "courseVersion", "releaseSha256"))
            and re.fullmatch(r"[a-f0-9]{64}", r["releaseSha256"])
            for r in entries), "published_storage_directory_manifest_invalid")
        matching = [r for r in entries if all(r.get(k) == identity.get(k) for k in ("courseId", "courseVersion"))]
        if not matching:
            # export_course reaches this only after its published source adapter
            # has verified the release. No publication gate is bypassed here.
            return None
        _require(len(matching) == 1 and matching[0]["releaseSha256"] == identity.get("releaseSha256")
                 and all(k not in matching[0] or matching[0][k] == identity.get(k) for k in ("classroomId", "contentKey"))
                 and isinstance(matching[0].get("storageDirectory"), str) and matching[0]["storageDirectory"].strip(),
                 "published_storage_directory_not_bound")
        return matching[0]

    def _published_snapshot(self, conn, course_id, course_version, content_key):
        rows = conn.execute("SELECT content_key FROM learning_textbook_course_builds "
            "WHERE course_id=? AND course_version=? AND status='published'",
            (course_id, course_version)).fetchall()
        if content_key:
            rows = [row for row in rows if row["content_key"] == content_key]
            _require(len(rows) == 1, "published_content_key_not_found")
        if rows:
            _require(len(rows) == 1, "published_course_binding_ambiguous")
            return self._textbook_snapshot(conn, rows[0]["content_key"])
        _require(content_key is None, "published_content_key_not_found")
        return self._formal_snapshot(conn, course_id, course_version)

    def _textbook_snapshot(self, conn, key):
        build, course, release, manifest = releases._validated_release(conn, key)
        frozen = releases.parsed(build["input_json"])
        documents = {"数据库/课程记录.json": dict(course), "数据库/教材构建记录.json": dict(build),
                     "教材目录.json": manifest, "冻结发布请求.json": build["input_json"],
                     "审核与发布记录.json": build["review_json"], "发布记录.json": release}
        snapshot = ArchiveSnapshot(
            identity={"courseId": course["id"], "courseVersion": course["version"],
                      "contentKey": key, "classroomId": release["classroomId"],
                      "releaseSha256": release["sha256"]},
            metadata={"title": course["title"], **releases.release_metadata(course, manifest)},
            classroom=release["classroom"], documents=documents,
            media=releases.delivery_media(release))
        preview_key = frozen.get("previewKey")
        if preview_key:
            preview = conn.execute("SELECT * FROM learning_textbook_course_previews WHERE preview_key=?",
                                   (preview_key,)).fetchone()
            if not preview:
                snapshot.missing_sources.append({"kind": "preview", "reason": "bound_preview_missing"})
            else:
                original = releases.parsed(preview["classroom_json"])
                from content.textbook_catalog import digest
                _require(digest(original) == preview["classroom_sha256"] == frozen["sourceSha256"],
                         "preview_original_hash_mismatch")
                documents["数据库/原始预览记录.json"] = dict(preview)
                documents["原始课堂.json"] = preview["classroom_json"]
                original_input = releases.parsed(preview["input_json"])
                self._textbook_sources(snapshot, original_input, frozen)
                stage_id = preview["classroom_id"]
                self._add_native_sources(snapshot, stage_id)
        else:
            # Private batch activities are owned by their exact frozen task ID
            # and hash, not by an output directory name alone.
            task_id = frozen.get("taskId")
            candidates = []
            if isinstance(task_id, str) and re.fullmatch(r"[a-f0-9]{64}", task_id):
                for path in (self.root / "output").glob("**/" + task_id + "/input.json"):
                    if path.is_symlink():
                        continue
                    original = json.loads(path.read_bytes())
                    if (original.get("taskId") == task_id and original.get("inputSha256") == frozen.get("sourceInputSha256")):
                        candidates.append(path.parent)
            if candidates:
                # Prepared and compiled copies with the same frozen input hash
                # are independently owned originals, not conflicting authority.
                snapshot.source_roots.extend(candidates)
            else:
                snapshot.missing_sources.append({"kind": "authoring", "reason": "exact_batch_source_missing_or_ambiguous"})
        return snapshot

    def _textbook_sources(self, snapshot, original_input, frozen):
        binding = frozen["textbookBinding"]
        review_path = original_input.get("sourceScope", {}).get("localReviewPath")
        if review_path:
            path = self._source_path(review_path)
            # This exact stored source-review reference owns its sources dir;
            # the adjacent job needs an independent frozen binding check.
            if path.is_file():
                snapshot.source_roots.append(path.parent)
            else:
                snapshot.missing_sources.append({"kind": "source_review", "reason": "bound_source_review_missing"})
            teaching = path.parent.parent
            job = teaching / "authoring-job"
            job_frozen = job / "frozen.json"
            if job_frozen.is_file():
                value = json.loads(job_frozen.read_bytes())
                b = value.get("binding", {})
                _require(b.get("editionId") == binding["editionId"]
                         and b.get("nodeId") == binding["nodeId"]
                         and teaching.name == "teaching-" + str(value.get("teachingRevision")),
                         "authoring_original_binding_mismatch")
                # A later publication revision keeps its original authoring
                # version. Own exactly that frozen teaching directory, including
                # its attachments and repair receipts, never sibling versions.
                snapshot.source_roots.append(teaching)
                self._add_authoring_stage(snapshot, original_input)
                return
        stage_id = original_input.get("authoring", {}).get("stageId")
        if stage_id:
            matches = []
            for job, job_frozen, state in self._workbench_jobs():
                b = job_frozen.get("binding", {})
                if (b.get("editionId") == binding["editionId"]
                        and b.get("nodeId") == binding["nodeId"]
                        and any(s.get("stageId") == stage_id for s in state.get("savedStages", []))):
                    matches.append(job.parent)
            snapshot.source_roots.extend(matches)
            self._add_authoring_stage(snapshot, original_input)
        # Legacy native imports have their request/page plan in the raw frozen
        # preview input and their saved classroom in Native JSON/PG. A workbench
        # job that never existed is not manufactured as an expected artifact.

    def _workbench_jobs(self, *, refresh=False, session_id=None):
        if refresh:
            self._workbench_index = None
        if self._workbench_index is None:
            self._workbench_index = []
            for path in (self.root / "output").glob("**/authoring-job/frozen.json"):
                path = self._source_path(path)
                value = json.loads(path.read_bytes())
                draft = path.parent / "draft.json"
                state = path.parent / "state.json"
                if not state.is_file():
                    continue
                state_value = json.loads(self._source_path(state).read_bytes())
                valid = draft.is_file()
                if valid:
                    raw = self._source_path(draft).read_bytes()
                    draft_value = json.loads(raw)
                    valid = (_sha(raw) == value.get("draftSha256")
                        and path.parent.parent.name == "teaching-" + str(value.get("teachingRevision"))
                        and (not value.get("draftCanonicalSha256") or _sha(releases.canonical(draft_value).encode()) == value["draftCanonicalSha256"])
                        and (not value.get("requestSha256") or _sha(draft_value.get("request", "").encode()) == value["requestSha256"]))
                if session_id and state_value.get("sessionId") == session_id:
                    _require(valid, "native_authoring_original_integrity_mismatch")
                if valid:
                    self._workbench_index.append((path.parent, value, state_value))
        return self._workbench_index

    def _native_authoring_sources(self, snapshot, binding):
        """Bind private control identity to exact frozen originals, never export it."""
        session_id = None
        if binding is not None:
            _require(isinstance(binding, dict) and set(binding) == {"sessionId"}
                     and isinstance(binding["sessionId"], str)
                     and 0 < len(binding["sessionId"]) <= 255
                     and _ID.fullmatch(binding["sessionId"]), "native_authoring_binding_invalid")
            session_id = binding["sessionId"]
        stage_id = snapshot.identity["classroomId"]
        def matches(jobs):
            return [(job, frozen, state) for job, frozen, state in jobs
                if (state.get("sessionId") == session_id if session_id else
                    any(item.get("stageId") == stage_id for item in state.get("savedStages", []) if isinstance(item, dict)))]
        jobs = self._workbench_jobs(refresh=bool(session_id), session_id=session_id)
        owned = matches(jobs)
        if not owned and not session_id:
            owned = matches(self._workbench_jobs(refresh=True))
        # No Backend job means this was authored directly in Native. Its
        # captured outline/scenes are its originals; do not invent a missing job.
        if not owned:
            return
        _require(len({_sha(_json(frozen)) for _, frozen, _ in owned}) == 1,
                 "native_authoring_binding_ambiguous")
        for job, frozen, _ in owned:
            snapshot.source_roots.append(job.parent)
            # Mutable authoring-session control is not the frozen lesson. Keep
            # it local and explain its omission without publishing its values.
            snapshot.private_source_files.append(job / "state.json")
            self._native_textbook_metadata(snapshot, frozen)

    def _native_textbook_metadata(self, snapshot, frozen):
        """Project names only from the exact catalog frozen for this job."""
        binding = frozen.get("binding", {})
        keys = ("editionId", "revisionId", "gradeCode", "subject", "volume", "schoolSystem")
        catalog_check = frozen.get("catalogCheck")
        checksum = catalog_check.get("manifestSha256") if isinstance(catalog_check, dict) else None
        if (not isinstance(binding, dict) or not all(isinstance(binding.get(k), str) and binding[k] for k in keys)
                or not re.fullmatch(r"[a-f0-9]{64}", str(checksum))):
            return
        expected = tuple(binding[k] for k in keys)
        root = self.root / "backend/content/textbooks"
        matches = []
        for candidate in root.rglob("*.json"):
            try:
                path = self._source_path(candidate)
                info = path.stat()
                if not path.is_file() or info.st_size > 4 * 1024 * 1024:
                    continue
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                cached = self._catalog_file_cache.get(path)
                if cached is None or cached[0] != identity:
                    value = json.loads(path.read_bytes())
                    record = None
                    if isinstance(value, dict) and value.get("schemaVersion") == "mira.learning.textbook-manifest.v1":
                        record = (_sha(releases.canonical(value).encode()), tuple(value.get(k) for k in keys))
                    self._catalog_file_cache[path] = (identity, record)
                else:
                    record = cached[1]
                if record == (checksum, expected):
                    # Re-read the matching original, rather than retaining all
                    # catalog JSON bodies in a long-running worker's memory.
                    value = json.loads(path.read_bytes())
                    if (_sha(releases.canonical(value).encode()) == checksum
                            and tuple(value.get(k) for k in keys) == expected):
                        matches.append((path, value))
            except (CourseArchiveError, OSError, ValueError, TypeError):
                continue
        if not matches:
            return
        # Equivalent local copies are the same frozen manifest. Prefer its
        # revisions location, while never substituting a newer revision.
        path, manifest = min(matches, key=lambda item: (not item[0].is_relative_to(root / "revisions"), str(item[0])))
        metadata = releases.release_metadata({"subject": binding["subject"], "grade_code": binding["gradeCode"]}, manifest)
        snapshot.metadata.update(metadata, revisionId=binding["revisionId"], textbookManifestSha256=checksum)
        snapshot.source_files.append(path)

    def _add_authoring_stage(self, snapshot, original_input):
        stage_id = original_input.get("authoring", {}).get("stageId")
        if stage_id and stage_id != snapshot.identity["classroomId"]:
            directory = self.native_root / "data/classrooms"
            _require(_ID.fullmatch(stage_id), "native_stage_identity_invalid")
            if (directory / (stage_id + ".json")).is_file():
                snapshot.source_files.append(directory / (stage_id + ".json"))
            if (directory / stage_id).is_dir():
                snapshot.source_roots.append(directory / stage_id)

    def _add_native_sources(self, snapshot, stage_id):
        _require(isinstance(stage_id, str) and _ID.fullmatch(stage_id), "native_stage_identity_invalid")
        directory = self.native_root / "data/classrooms"
        path = directory / (stage_id + ".json")
        if path.is_file():
            snapshot.source_files.append(path)
        # Audio plans/audits and source receipts are scoped to exactly this
        # stage. Media absent after migration are supplied from the release.
        if (directory / stage_id).is_dir():
            snapshot.source_roots.append(directory / stage_id)
        document = self.native_document_loader(stage_id)
        if document is not None:
            _require(document.get("stage", {}).get("id") == stage_id,
                     "native_document_identity_mismatch")
            snapshot.documents["原稿/Native数据库课堂.json"] = document

    def _formal_snapshot(self, conn, course_id, course_version):
        course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
                              (course_id, course_version)).fetchone()
        _require(course and course["status"] == "published" and course["quality_status"] == "released"
                 and course["retired_at"] is None, "published_course_not_found")
        public_course = {"courseId": course_id, "courseVersion": course_version,
            "title": course["title"], "subjectCode": course["subject"],
            "gradeCode": course["grade_code"], "publishedAt": course["published_at"]}
        release = releases._formal_release(conn, public_course, self.root / "backend/data/learning-media")
        authority = releases._formal_authorities(conn, public_course)[0]
        classroom_id = release["classroomId"]
        directory = self.native_root / "data/classrooms"
        path = (directory / classroom_id / "artifact/classroom.json" if classroom_id.startswith("omclass_")
                else directory / (classroom_id + ".json"))
        raw = path.read_bytes()
        snapshot = ArchiveSnapshot(identity={k: release[k] for k in
            ("courseId", "courseVersion", "contentKey", "classroomId", "releaseSha256")},
            metadata={"title": course["title"], **releases.release_metadata(course)},
            classroom=json.loads(raw), media=release["media"], source_files=[path],
            documents={"数据库/课程记录.json": dict(course), "发布记录.json": release,
                       "审核权威记录.json": dict(authority), "原始课堂.json": raw.decode("utf8")})
        queries = {
            "发布回执": ("learning_curriculum_classroom_item_receipts", "course_id=? AND course_version=?", (course_id, course_version)),
            "课包绑定": ("learning_course_lesson_package_bindings", "course_id=? AND course_version=?", (course_id, course_version)),
            "课包": ("learning_lesson_packages", "course_id=? AND course_version=?", (course_id, course_version)),
            "运行课堂记录": ("learning_openmaic_runtime_classrooms", "course_id=? AND course_version=?", (course_id, course_version)),
            "配音审核任务": ("learning_formal_qwen_audio_jobs", "build_item_id=?", (authority["build_item_id"],)),
        }
        loaded = {}
        for name, (table, where, params) in queries.items():
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]
            loaded[name] = rows
            snapshot.documents[f"数据库/{name}.json"] = rows
        snapshot.documents["数据库/配音逐段审核.json"] = [dict(r) for r in releases._formal_audio_rows(conn, authority["build_item_id"])]
        for package in loaded["课包"]:
            for table, name, where, params in (
                ("learning_lesson_package_private", "课包私有教案", "package_id=? AND package_version=?", (package["id"], package["version"])),
                ("learning_classroom_source_artifacts", "生成原稿", "id=?", (package["source_artifact_id"],)),
            ):
                rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()]
                _require(len(rows) == 1, "formal_source_record_missing")
                snapshot.documents[f"数据库/{name}-{_safe_name(package['id'])}-{package['version']}.json"] = rows
        for runtime in loaded["运行课堂记录"]:
            job_id = runtime.get("upstream_job_id")
            if job_id and _ID.fullmatch(job_id):
                job = self.native_root / "data/classroom-jobs" / (job_id + ".json")
                if job.is_file():
                    value = json.loads(job.read_bytes())
                    _require(value.get("classroomId", value.get("result", {}).get("classroomId")) in
                             (None, classroom_id), "formal_job_identity_mismatch")
                    snapshot.source_files.append(job)
                else:
                    snapshot.missing_sources.append({"kind": "native_job", "reason": "bound_native_job_missing"})
        self._add_native_sources(snapshot, classroom_id)
        return snapshot

    def _source_path(self, value):
        path = Path(value)
        path = path if path.is_absolute() else self.root / path
        _require(not path.is_symlink() and path.resolve().is_relative_to(self.root)
                 and path.resolve() == path.absolute(), "source_path_outside_repository_or_linked")
        return path

    def _native_document(self, stage_id):
        """Read raw PG JSONB without store construction/schema writes/owner cookies."""
        url = os.environ.get("MIRA_OPENMAIC_AGENT_DATABASE_URL")
        if not url:
            return None
        code = r"""const {Client}=require(process.argv[1]);let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',async()=>{let x=JSON.parse(s),c=new Client({connectionString:x.url});try{await c.connect();await c.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');let a=await c.query('SELECT data FROM document_stages WHERE id=$1',[x.stage]);let b=await c.query('SELECT data FROM document_scenes WHERE stage_id=$1 ORDER BY scene_order,id',[x.stage]);let o=await c.query('SELECT data FROM document_outlines WHERE stage_id=$1',[x.stage]);await c.query('ROLLBACK');console.log(JSON.stringify(a.rows.length?{stage:a.rows[0].data,scenes:b.rows.map(r=>r.data),...(o.rows.length?{outline:o.rows[0].data}:{})}:null));}catch(e){process.exitCode=1;}finally{await c.end();}});"""
        result = subprocess.run(["node", "-e", code, str(self.native_root / "node_modules/pg")],
            input=json.dumps({"url": url, "stage": stage_id}), text=True,
            capture_output=True, timeout=30)
        _require(result.returncode == 0, "native_readonly_document_unavailable")
        return json.loads(result.stdout)

    def export_snapshot(self, snapshot, *, staging_root, release=None,
                        source_kind=None, source_digest=None, meta=None):
        """Archive a bound terminal snapshot supplied by an event/outbox adapter.

        Native workers supply their already-captured JSON and exact owned roots;
        this API never enumerates agent sessions or dispatches work. A source
        digest identifies the immutable capture, independently of release hash.
        """
        if source_kind is not None:
            _require(isinstance(source_kind, str) and _ID.fullmatch(source_kind), "source_kind_invalid")
            _require(isinstance(source_digest, str) and re.fullmatch(r"[a-f0-9]{64}", source_digest),
                     "source_digest_invalid")
        meta = meta or {}
        _check_public(meta)
        _require(snapshot.status in {"published", "generated_saved"}, "archive_status_invalid")
        _check_public(snapshot.identity)
        _check_public(snapshot.metadata)
        release = release or {}
        if release:
            _require(all(release.get(k) == snapshot.identity.get(k) for k in
                         ("courseId", "courseVersion", "releaseSha256")), "dated_release_identity_mismatch")
        object_directory = release.get("storageDirectory")
        if not object_directory:
            date = release.get("uploadDate") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            _require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date), "upload_date_invalid")
            storage_edition = snapshot.metadata.get("storageEditionLabel")
            edition = storage_edition or snapshot.metadata.get("editionLabel") or (
                "非教材课程" if snapshot.status == "published" and snapshot.identity.get("contentKey") is None else "未绑定教材（历史课件）")
            volume = snapshot.metadata.get("volumeLabel")
            if not storage_edition and volume and volume not in edition:
                edition += "-" + volume
            object_directory = "/".join((_safe_name(snapshot.metadata.get("subjectName") or "课程"),
                _safe_name(edition), _safe_name(snapshot.metadata.get("storageGradeLabel") or snapshot.metadata.get("gradeLabel") or "未标注年级"),
                date, _safe_name(snapshot.metadata["title"])))
        _safe_relative(object_directory)
        _require(len(object_directory.split("/")) == 5
                 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", object_directory.split("/")[3]),
                 "storage_directory_invalid")
        staging_root = self._staging_root(staging_root)
        archive_id = _sha(_json({"identity": snapshot.identity, "status": snapshot.status,
                                "sourceKind": source_kind, "sourceDigest": source_digest}))[:24]
        exported_at = meta.get("exportedAt") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        _require(isinstance(exported_at, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", exported_at),
                 "export_time_invalid")
        archive_version = exported_at.replace("T", " ").replace(":", "-").removesuffix("Z")
        target = staging_root / (archive_id + "-" + uuid.uuid4().hex[:8])
        target.mkdir(mode=0o700)
        payload = target / "课程资料"
        payload.mkdir(mode=0o700)
        files, omissions, missing, total = [], [], list(snapshot.missing_sources), 0
        all_media = {item["path"]: item for item in snapshot.media}
        queued_sources = set(snapshot.source_files)
        document_assets, resolved_assets = set(), {}
        recovered_aliases = {item["originalReference"]: item for item in snapshot.recovered_aliases}

        def ensure_document_assets(value):
            if not (isinstance(value, dict) and isinstance(value.get("stage"), dict)
                    and isinstance(value["stage"].get("id"), str)
                    and isinstance(value.get("scenes"), list) and value["scenes"]):
                return
            identity = _sha(_json(value))
            if identity in document_assets:
                return
            document_assets.add(identity)
            asset_root = target / "asset-sources"
            result = self.standard_asset_resolver(value, staging_root=asset_root)
            reported_refs = {str(entry.get("ref", "unknown")) for entry in result.get("unresolved", [])}
            for entry in result.get("unresolved", []):
                missing.append({"kind": "native_asset", "sourceIdentity": entry.get("ref", "unknown"),
                                "reason": entry.get("reason", "standard_asset_unresolved")})
            for entry in result.get("entries", []):
                status = entry.get("status")
                _require(status in {"inline", "already_collected", "resolved", "unresolved"},
                         "standard_asset_status_invalid")
                if status == "unresolved" and entry.get("ref") not in reported_refs:
                    missing.append({"kind": "native_asset", "sourceIdentity": entry.get("ref", "unknown"),
                                    "reason": entry.get("reason", "standard_asset_unresolved")})
                    reported_refs.add(entry.get("ref"))
                if status != "resolved":
                    continue
                path = Path(entry["sourcePath"])
                _require(not path.is_symlink() and path.resolve() == path
                         and path.is_relative_to(asset_root.resolve()) and path.is_file()
                         and path.stat().st_size == entry["byteSize"] <= MAX_FILE_BYTES
                         and _hash_file(path) == entry["sha256"], "standard_asset_bytes_mismatch")
                previous = resolved_assets.get(entry["ref"])
                _require(previous is None or previous == entry["sha256"], "standard_asset_identity_conflict")
                if previous is not None:
                    continue
                resolved_assets[entry["ref"]] = entry["sha256"]
                extension = mimetypes.guess_extension(entry["mimeType"]) or ".bin"
                kind = {"image": "图片", "background": "背景", "poster": "封面", "audio": "音频", "video": "视频"}.get(entry.get("kind"), "素材")
                raw = path.read_bytes()
                _require(len(raw) == entry["byteSize"] and _sha(raw) == entry["sha256"],
                         "standard_asset_bytes_changed")
                add(f"Native素材/{kind}-{len(resolved_assets):03d}{extension}", raw=raw,
                    kind="native_standard_asset", identity=entry["ref"], mime=entry["mimeType"])
            # The DSL evolves. A new allocatedAssetId field or a dynamically
            # referenced HTML asset must not silently disappear just because
            # an older enumeration does not yet visit that structural slot.
            allocated = set(re.findall(r"\bast_[A-Za-z0-9_-]+\b", releases.canonical(value)))
            enumerated = set()
            for entry in result.get("entries", []):
                enumerated.update(re.findall(r"\bast_[A-Za-z0-9_-]+\b", str(entry.get("ref", ""))))
            for ref in sorted(allocated - enumerated):
                missing.append({"kind": "native_asset", "sourceIdentity": ref,
                                "reason": "allocated_asset_reference_not_enumerated"})
            # Standard asset references and concrete classroom URLs can coexist
            # in the same original. Account for the latter independently of
            # the DSL enumeration, including HTML-embedded activity media.
            collected_refs = [entry.get("mappedRef") or entry.get("ref")
                for entry in result.get("entries", []) if entry.get("status") == "already_collected"]
            # The controlled Native resolver can expand a stage-owned BASE
            # directory into exact full references. This derived scan input is
            # never written back into the frozen/original classroom document.
            scan_document = {**value, "_miraArchiveReferencedMedia": collected_refs}
            extra = ArchiveSnapshot(identity=snapshot.identity, metadata=snapshot.metadata, classroom=scan_document,
                source_roots=list(snapshot.source_roots))
            self._collect_snapshot_media(extra)
            missing.extend(extra.missing_sources)
            queued_sources.update(extra.source_files)
            for alias in extra.recovered_aliases:
                old = recovered_aliases.get(alias["originalReference"])
                _require(old is None or old == alias, "material_alias_identity_conflict")
                recovered_aliases[alias["originalReference"]] = alias
            for item in extra.media:
                old = all_media.get(item["path"])
                _require(old is None or all(old[k] == item[k] for k in ("sha256", "byteSize", "mimeType")),
                         "original_media_identity_conflict")
                if old is None:
                    all_media[item["path"]] = item

        def add(relative, *, raw=None, source=None, kind, identity, original=True, mime=None):
            nonlocal total
            _safe_relative(relative)
            _require(not any(item["archivePath"] == relative for item in files), "duplicate_archive_path")
            _require(len(files) < MAX_FILES, "archive_file_count_exceeded")
            if source is not None:
                source = self._source_path(source)
                _require(source.is_file() and source.stat().st_size <= MAX_FILE_BYTES, "source_file_unavailable_or_oversized")
                before = source.stat()
                raw = source.read_bytes()
                after = source.stat()
                _require(len(raw) == before.st_size and all(getattr(before, key) == getattr(after, key)
                    for key in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")), "source_file_changed")
            _require(isinstance(raw, bytes) and len(raw) <= MAX_FILE_BYTES, "archive_file_oversized")
            suffix = _original_suffix(Path(relative))
            format_name = relative if Path(relative).suffix.lower() == suffix else str(Path(relative).with_suffix(""))
            original_format = None
            if suffix == ".json":
                value, structured = _inspect_original(raw, Path(relative))
                if structured:
                    ensure_document_assets(value)
                else:
                    original_format, mime = "raw-text-log", "text/plain"
            elif _source_text_file(Path(relative)):
                _check_source_text(raw, suffix, source_path=Path(relative))
            total += len(raw)
            _require(total <= MAX_ARCHIVE_BYTES, "archive_byte_limit_exceeded")
            path = payload / relative
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(raw)
            files.append({"archivePath": relative, "sourceKind": kind, "sourceIdentity": identity,
                "sha256": _sha(raw), "byteSize": len(raw),
                "mimeType": mime or mimetypes.guess_type(format_name)[0] or "application/octet-stream",
                "original": original, **({"originalFormat": original_format} if original_format else {})})

        try:
            add("classroom.json", raw=_json(snapshot.classroom), kind="classroom",
                identity=snapshot.identity["classroomId"], original=False)
            for relative, value in snapshot.documents.items():
                raw = value.encode("utf8") if isinstance(value, str) else _json(value)
                add(relative, raw=raw, kind="database_snapshot", identity=relative,
                    original=isinstance(value, str))
                # Preserve the exact DB JSON field strings as separate originals;
                # the row export itself is a derived representation of the row.
                rows = value if isinstance(value, list) else [value]
                for i, row in enumerate(rows):
                    if isinstance(row, dict):
                        for key, val in row.items():
                            if key.endswith("_json") and isinstance(val, str) and val.strip():
                                add(f"数据库原字段/{Path(relative).stem}/{i:03d}-{_safe_name(key)}.json",
                                    raw=val.encode("utf8"), kind="database_json_original",
                                    identity=f"{relative}:{i}:{key}")
            for i, scene in enumerate(snapshot.classroom.get("scenes", []), 1):
                html = scene.get("content", {}).get("html")
                if isinstance(html, str):
                    add(f"互动页面/{i:03d}-{_safe_name(scene.get('id', str(i)))}.html",
                        raw=html.encode("utf8"), kind="extracted_scene_html",
                        identity=scene.get("id", str(i)), original=False, mime="text/html")
            sources = queued_sources
            sources.update(self._owned_source_files(snapshot))
            processed_sources = set()
            while sources - processed_sources:
                source = sorted(sources - processed_sources)[0]
                processed_sources.add(source)
                relative = source.relative_to(self.root)
                if source in snapshot.private_source_files:
                    omissions.append({"sourceIdentity": relative.as_posix(), "reason": "private_authoring_runtime_control"})
                    continue
                exclusion = _private_runtime_exclusion(relative)
                if exclusion:
                    omissions.append({"sourceIdentity": relative.as_posix(), "reason": exclusion})
                    continue
                if _credential_file(relative):
                    omissions.append({"sourceIdentity": relative.as_posix(), "reason": "credential_or_runtime_file_excluded"})
                    continue
                if not _supported_source_file(source):
                    if source.name == ".DS_Store" or source.suffix.lower() in {".lock", ".pid", ".tmp", ".part"}:
                        omissions.append({"sourceIdentity": relative.as_posix(), "reason": "runtime_file_excluded"})
                    else:
                        missing.append({"kind": "unclassified_original", "sourceIdentity": relative.as_posix(),
                                        "reason": "original_requires_safe_format_adapter"})
                    continue
                try:
                    add("原稿/" + relative.as_posix(), source=source, kind="owned_original_file",
                        identity=relative.as_posix(), mime=self._binary_original_mime(source))
                except CourseArchiveError as error:
                    if str(error) != "credential_or_student_data_in_artifact":
                        raise
                    missing.append({"kind": "unsafe_original", "sourceIdentity": relative.as_posix(),
                                    "reason": "credential_or_student_data_in_artifact"})
            archived_media = {}
            for item in all_media.values():
                archive_path = "媒体/" + _safe_relative(item.get("archiveSourcePath", item.get("sourcePath") or "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + item["path"].removeprefix("/api/classroom-media/")))
                media_identity = tuple(item[k] for k in ("sha256", "byteSize", "mimeType"))
                if archive_path in archived_media:
                    _require(archived_media[archive_path] == media_identity, "recovered_media_archive_conflict")
                    continue
                archived_media[archive_path] = media_identity
                source = item.get("sourcePath") or "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + item["path"].removeprefix("/api/classroom-media/")
                source_path = self._source_path(source)
                raw = self.media_store.read(source_path, expected_sha256=item["sha256"], expected_bytes=item["byteSize"])
                if raw is None:
                    _require(source_path.is_file(), "published_media_source_missing")
                    raw = source_path.read_bytes()
                _require(len(raw) == item["byteSize"] and _sha(raw) == item["sha256"], "published_media_hash_mismatch")
                # Retain logical source paths inside ZIP so restored original
                # classroom links have an explicit path-to-file mapping.
                add(archive_path, raw=raw, kind="referenced_media",
                    identity=item["path"], mime=item["mimeType"])
            metadata = {"schemaVersion": SCHEMA, **snapshot.identity, **snapshot.metadata,
                "status": snapshot.status, "archiveFormat": "mira-course-archive-zip-v1",
                "objectDirectory": object_directory, "exportedAt": exported_at,
                "archiveVersion": archive_version,
                **({"sourceKind": source_kind, "sourceDigest": source_digest} if source_kind else {})}
            add("metadata.json", raw=_json(metadata), kind="archive_metadata", identity=archive_id, original=False)
            complete = not missing
            manifest = {"schemaVersion": SCHEMA, "archiveId": archive_id,
                "identity": snapshot.identity, "status": snapshot.status, "complete": complete,
                "missingSources": missing, "excludedFiles": omissions, "files": files,
                "recoveredAliases": list(recovered_aliases.values()),
                "totals": {"fileCount": len(files), "byteSize": total}}
            manifest_path = payload / "manifest.json"
            self._write_private(manifest_path, _json(manifest))
            title = _safe_name(snapshot.metadata["title"])
            zip_path = target / (title + "-完整课程资料包.zip")
            with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                                 allowZip64=True) as archive:
                for path in sorted(payload.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(payload).as_posix())
            zip_path.chmod(0o600)
            self._verify_zip(zip_path, manifest)
            public = []
            if complete:
                for path, suffix in ((payload / "classroom.json", "课堂结构.json"),
                    (manifest_path, "归档清单.json"), (payload / "metadata.json", "课程资料.json"),
                    (zip_path, "完整课件.zip")):
                    extension = Path(suffix).suffix
                    named = title + "-" + suffix.removesuffix(extension) + "-" + archive_version + extension
                    public.append({"localPath": str(path), "relativePath": object_directory + "/" + named,
                        "sha256": _hash_file(path), "byteSize": path.stat().st_size,
                        "mimeType": "application/zip" if path == zip_path else "application/json"})
            result = {"schemaVersion": SCHEMA, **snapshot.identity, "archiveId": archive_id,
                "status": snapshot.status, "complete": complete, "missingSources": missing,
                "stagingDirectory": str(target), "manifestPath": str(manifest_path),
                "indexPath": str(target / "index.json"), "objectDirectory": object_directory,
                "archiveVersion": archive_version, "exportedAt": exported_at,
                **({"sourceKind": source_kind, "sourceDigest": source_digest} if source_kind else {}),
                "zip": {"path": str(zip_path), "sha256": _hash_file(zip_path), "byteSize": zip_path.stat().st_size},
                "totals": manifest["totals"], "generatedPublicFiles": public}
            self._write_private(Path(result["indexPath"]), _json(result))
            return result
        except BaseException:
            # A failed/partial archive is not an upload candidate. The private
            # staging directory remains for the caller's explicit diagnostics.
            raise

    def _staging_root(self, value):
        path = Path(value)
        _require(path.is_absolute() and not path.is_symlink(),
                 "staging_root_invalid")
        path = path.resolve()
        allowed = [self.root / "backend/data/course-storage/archives"]
        if os.environ.get("MIRA_TASK_TMPDIR"):
            allowed.append(Path(os.environ["MIRA_TASK_TMPDIR"]).resolve())
        _require(any(path == root or path.is_relative_to(root) for root in allowed),
                 "staging_root_must_be_private_archive_or_task_directory")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.chmod(0o700)
        return path

    @staticmethod
    def _write_private(path, raw):
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _verify_zip(path, manifest):
        with zipfile.ZipFile(path) as archive:
            _require(archive.testzip() is None, "archive_zip_corrupt")
            _require(set(archive.namelist()) == {f["archivePath"] for f in manifest["files"]} | {"manifest.json"},
                     "archive_zip_file_set_mismatch")
            for entry in manifest["files"]:
                checksum, size = hashlib.sha256(), 0
                with archive.open(entry["archivePath"]) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        checksum.update(chunk)
                        size += len(chunk)
                _require(size == entry["byteSize"] and checksum.hexdigest() == entry["sha256"],
                         "archive_zip_original_hash_mismatch")
