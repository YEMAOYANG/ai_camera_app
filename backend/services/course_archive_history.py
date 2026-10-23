"""Discover and bind historical authoring originals; never upload or generate."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile


AUTHORING_ROOT = Path("output/textbook-full-audit-20261009")
SOURCE_NAMES = frozenset({"classroom.json", "narrated-classroom.json", "source-narrated-classroom.json"})
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_ORIGINAL_BYTES = 768 * 1024 * 1024
MAX_FILES = 12000
SHA = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")


def _require(condition, code):
    if not condition:
        from services.course_archive_exporter import CourseArchiveError
        raise CourseArchiveError(code)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _stat(info):
    return [getattr(info, field) for field in
            ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")]


def _path(project, value, boundary):
    path = Path(value)
    path = path if path.is_absolute() else project / path
    path = path.absolute()
    _require(path.is_relative_to(boundary) and path.resolve() == path,
             "authoring_history_path_outside_or_linked")
    return path


def _read(path, *, maximum, keep=False):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        _require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                 "authoring_history_source_invalid")
        checksum, chunks, byte_count = hashlib.sha256(), [], 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            byte_count += len(chunk)
            _require(byte_count <= maximum, "authoring_history_source_invalid")
            checksum.update(chunk)
            if keep:
                chunks.append(chunk)
        after = os.fstat(stream.fileno())
    _require(_stat(before) == _stat(after) == _stat(path.lstat()), "authoring_history_source_changed")
    return checksum.hexdigest(), b"".join(chunks) if keep else None, _stat(after)


def _excluded(path):
    # Reuse the exporter's exclusions. Credentials are neither read nor hashed.
    from services.course_archive_exporter import _credential_file, _private_runtime_exclusion
    return bool(_credential_file(path) or _private_runtime_exclusion(path)
                or path.name == ".DS_Store" or path.suffix.lower() in {".lock", ".pid", ".tmp", ".part"})


def _tree(root):
    result = {}
    for parent, directories, names in os.walk(root, followlinks=False):
        directories.sort()
        for name in directories[:]:
            path = Path(parent) / name
            _require(not path.is_symlink(), "authoring_history_symlink_rejected")
            if _excluded(path):
                directories.remove(name)
        for name in sorted(names):
            path = Path(parent) / name
            info = path.lstat()
            _require(stat.S_ISREG(info.st_mode), "authoring_history_non_regular_source")
            result[path.relative_to(root).as_posix()] = _stat(info)
            _require(len(result) <= MAX_FILES, "authoring_history_file_limit")
    return result


def _root_version(root, previous=None):
    before = _tree(root)
    previous = previous or {}
    files, cache = [], {}
    for name, fingerprint in sorted(before.items()):
        path = root / name
        if _excluded(path):
            # Metadata alone notices private-control changes without opening it.
            files.append({"path": name, "excluded": True, "stat": fingerprint})
            continue
        old = previous.get(name, {})
        if old.get("stat") == fingerprint and SHA.fullmatch(old.get("sha256", "")):
            checksum = old["sha256"]
        else:
            checksum, _, _ = _read(path, maximum=MAX_ORIGINAL_BYTES)
        files.append({"path": name, "sha256": checksum, "byteSize": fingerprint[3]})
        cache[name] = {"stat": fingerprint, "sha256": checksum}
    _require(before == _tree(root), "authoring_history_directory_changed")
    return _sha(_json(files)), files, cache


def _owner(project, source):
    boundary = project / AUTHORING_ROOT
    for parent in source.parents:
        if parent == boundary:
            break
        if SHA.fullmatch(parent.name):
            return parent
    _require(False, "authoring_history_owner_not_bound")


def _snapshot(raw):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        _require(False, "authoring_history_json_invalid")
    _require(isinstance(value, dict) and isinstance(value.get("stage"), dict)
             and isinstance(value.get("scenes"), list) and value["scenes"],
             "authoring_history_not_complete_classroom")
    stage_id = value["stage"].get("id")
    _require(isinstance(stage_id, str) and ID.fullmatch(stage_id)
             and value.get("id", stage_id) == stage_id
             and all(isinstance(scene, dict) and isinstance(scene.get("id"), str) and scene["id"]
                     and scene.get("type") and scene.get("content")
                     and scene.get("stageId", stage_id) == stage_id for scene in value["scenes"]),
             "authoring_history_not_complete_classroom")
    return value


def discover_authoring_history(project_root, *, paths=None, cache=None, limit=100):
    """Return private events and a caller-persisted cursor; this function writes nothing.

    Default discovery accepts only classroom.json under the historical authoring
    root, with a nearest SHA-named course owner. Explicit paths may also name the
    two known complete narrated-classroom formats. Identity never dedupes stageId.
    """
    _require(type(limit) is int and 1 <= limit <= 1000, "authoring_history_limit_invalid")
    project = Path(project_root).absolute()
    _require(project.resolve() == project, "authoring_history_project_linked")
    boundary = _path(project, AUTHORING_ROOT, project)
    state = {"after": (cache or {}).get("after", ""), "files": dict((cache or {}).get("files", {})),
             "roots": dict((cache or {}).get("roots", {}))}
    if paths is None:
        candidates = []
        if boundary.is_dir():
            for parent, directories, names in os.walk(boundary, followlinks=False):
                directories[:] = sorted(name for name in directories if not (Path(parent) / name).is_symlink())
                if "classroom.json" in names:
                    candidates.append(Path(parent) / "classroom.json")
    else:
        candidates = [Path(value) if Path(value).is_absolute() else project / value for value in paths]
    _require(all(path.is_relative_to(project) for path in candidates), "authoring_history_path_outside_or_linked")
    selected = sorted(set(candidates), key=str)
    selected = [p for p in selected if p.relative_to(project).as_posix() > state["after"]][:limit]
    events, errors = [], []
    root_versions = {}
    for candidate in selected:
        name = candidate.relative_to(project).as_posix()
        try:
            source = _path(project, candidate, boundary)
            _require(source.name in SOURCE_NAMES, "authoring_history_filename_invalid")
            owner = _owner(project, source)
            owner_name = owner.relative_to(project).as_posix()
            if owner_name not in root_versions:
                root_versions[owner_name] = _root_version(owner, state["roots"].get(owner_name))
            revision, files, root_cache = root_versions[owner_name]
            fingerprint = [_stat(source.lstat()), revision]
            if state["files"].get(name) == fingerprint:
                continue
            checksum, raw, _ = _read(source, maximum=MAX_SOURCE_BYTES, keep=True)
            snapshot = _snapshot(raw)
            info = source.stat()
            events.append({"origin": "authoring-history", "sourceKind": "native_authoring_file",
                "sourceDigest": checksum, "stageId": snapshot["stage"]["id"], "snapshot": snapshot,
                "sourceRaw": raw.decode("utf8"), "createdAt": datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                "priority": 2, "authoringPath": name, "authoringRoot": owner_name,
                "archiveSourceRevision": _sha(_json({"ownerRoot": owner_name, "contentRevision": revision})),
                "authoringContentRevision": revision, "authoringFiles": files})
            state["files"][name] = fingerprint
            state["roots"][owner_name] = root_cache
        except Exception as error:
            # Diagnostic paths are private; never include exception messages.
            from services.course_archive_queue import _safe_error_code
            errors.append({"sourcePath": name, "error": _safe_error_code(error) or "authoring_history_read_failed"})
    state["after"] = selected[-1].relative_to(project).as_posix() if selected else ""
    return {"events": events, "cache": state, "visited": len(selected), "errors": errors}


def seed_authoring_history(queue, candidates):
    """Only enqueue private captured versions; caller holds the existing worker lock."""
    return [queue.enqueue(event) for event in candidates]


def export_authoring_history(exporter, event, *, staging_root):
    """Bind exact owned source bytes to the frozen event before the normal exporter."""
    from services.course_archive_exporter import ArchiveSnapshot
    from scripts.course_storage_releases import SUBJECT_NAMES

    project = exporter.root
    source = _path(project, event["authoringPath"], project / AUTHORING_ROOT)
    _require(source.name in SOURCE_NAMES, "authoring_history_filename_invalid")
    owner = _owner(project, source)
    _require(event.get("origin") == "authoring-history" and event.get("sourceKind") == "native_authoring_file"
             and owner.relative_to(project).as_posix() == event["authoringRoot"], "authoring_history_binding_invalid")
    checksum, raw, _ = _read(source, maximum=MAX_SOURCE_BYTES, keep=True)
    room = _snapshot(raw)
    _require(checksum == event["sourceDigest"] and raw.decode("utf8") == event["sourceRaw"]
             and room == event["snapshot"] and room["stage"]["id"] == event["stageId"],
             "authoring_history_source_version_changed")
    revision, files, _ = _root_version(owner)
    _require(revision == event["authoringContentRevision"] and files == event["authoringFiles"]
             and event["archiveSourceRevision"] == _sha(_json({"ownerRoot": event["authoringRoot"], "contentRevision": revision})),
             "authoring_history_owner_version_changed")
    stage = room["stage"]
    subject = stage.get("subject") or stage.get("subjectCode") or "course"
    identity = {"courseId": "native-authoring:" + event["stageId"],
        "courseVersion": "saved-" + checksum + "-" + event["archiveSourceRevision"],
        "contentKey": None, "classroomId": event["stageId"], "releaseSha256": None}
    metadata = {"title": stage.get("name") or stage.get("title") or event["stageId"],
        "subjectCode": subject, "subjectName": SUBJECT_NAMES.get(subject, "课程" if subject == "course" else subject),
        "generatedAt": event["createdAt"], "sourceSerialization": "exact-capture",
        "authoringSource": event["authoringPath"], "authoringOwnerRoot": event["authoringRoot"],
        "authoringRevision": event["archiveSourceRevision"], **{k: stage[k] for k in
            ("gradeCode", "gradeLabel", "editionLabel", "volumeCode", "volumeLabel") if stage.get(k)}}
    bound = ArchiveSnapshot(identity=identity, metadata=metadata, classroom=room,
        source_files=[source], source_roots=[owner], status="generated_saved")
    result = exporter.export_snapshot(bound, staging_root=staging_root,
        source_kind=event["sourceKind"], source_digest=checksum)
    if result.get("complete"):
        target = _path(project, result["indexPath"], Path(staging_root).absolute())
        manifest_path = _path(project, result["manifestPath"], target.parent)
        manifest = json.loads(manifest_path.read_bytes())
        originals = {(f["sourceIdentity"], f["sha256"], f["byteSize"])
                     for f in manifest["files"] if f.get("original")}
        expected = {(str(Path(event["authoringRoot"]) / f["path"]), f["sha256"], f["byteSize"])
                    for f in files if not f.get("excluded")}
        actual_owned = {f for f in originals if f[0].startswith(event["authoringRoot"] + "/")}
        if actual_owned != expected:
            # Capture diagnostics are retained by the queue; transport rejects
            # an incomplete index. Original sources are never changed or deleted.
            result["complete"] = False
            result.setdefault("missingSources", []).append({"kind": "authoring_version",
                "sourceIdentity": event["authoringRoot"], "reason": "captured_original_version_mismatch"})
            result["generatedPublicFiles"] = []
            descriptor, temporary = tempfile.mkstemp(prefix=".history-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(_json(result) + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
                directory = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                Path(temporary).unlink(missing_ok=True)
    return result
