"""Durable, private archive delivery; no generation, provider calls or app import."""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit
import zipfile


SCHEMA = "mira.course-archive.queue.v1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
MAX_JSON_BYTES = 128 * 1024 * 1024
ADAPTER_SOURCES = (
    "backend/services/course_archive_exporter.py",
    "backend/services/course_archive_history.py",
    "backend/services/course_media_object_store.py",
    "openmaic-runtime/scripts/course-archive-assets.mjs",
    "openmaic-runtime/.runtime/OpenMAIC/packages/@openmaic/dsl/dist/index.js",
)


class ArchiveQueueError(RuntimeError):
    pass


def _safe_error_code(error):
    known_type = (type(error).__module__, type(error).__name__) in {
        ("services.course_archive_exporter", "CourseArchiveError"),
        ("scripts.course_storage_releases", "InventoryError"),
    }
    if not isinstance(error, ArchiveQueueError) and not known_type:
        return None
    code = str(error)
    return code if re.fullmatch(r"[a-z0-9_]+", code) else None


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def storage_identity(endpoint, bucket, region="us-east-1"):
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", region)):
        raise ArchiveQueueError("archive_storage_invalid")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    port = parsed.port
    if port and port != (443 if parsed.scheme == "https" else 80):
        host += ":" + str(port)
    return {"endpoint": parsed.scheme + "://" + host, "bucket": bucket, "region": region}


def _directory(path):
    """Reject links, including existing ancestors, before creating private state."""
    path = Path(path).absolute()
    missing = []
    current = path
    while not current.exists() and not current.is_symlink():
        missing.append(current)
        current = current.parent
    for ancestor in (current, *current.parents):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise ArchiveQueueError("archive_state_symlink_or_non_directory")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ArchiveQueueError("archive_state_symlink_or_non_directory")
    return path


def _read(path):
    path = Path(path)
    _directory(path.parent)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_JSON_BYTES:
            raise ArchiveQueueError("archive_json_not_regular_or_oversized")
        raw = stream.read(MAX_JSON_BYTES + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if len(raw) > MAX_JSON_BYTES or any(getattr(before, k) != getattr(after, k)
            or getattr(before, k) != getattr(current, k) for k in fields):
        raise ArchiveQueueError("archive_json_changed")
    return raw


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write(path, value):
    parent = _directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".queue-", dir=parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(_json(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ArchiveQueueError("archive_state_symlink")
        os.replace(temporary, path)
        _sync_directory(parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _snapshot_raw(raw):
    """Extract the producer's exact JSON value; Python and JS numbers differ."""
    text = raw.decode("utf8")
    decoder = json.JSONDecoder()
    position = len(text) - len(text.lstrip())
    if text[position:position + 1] != "{":
        raise ArchiveQueueError("archive_event_invalid")
    position += 1
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        key, position = decoder.raw_decode(text, position)
        while text[position].isspace():
            position += 1
        if text[position] != ":":
            raise ArchiveQueueError("archive_event_invalid")
        position += 1
        while text[position].isspace():
            position += 1
        start = position
        _, position = decoder.raw_decode(text, position)
        if key == "snapshot":
            return text[start:position]
        while text[position].isspace():
            position += 1
        if text[position] != ",":
            raise ArchiveQueueError("archive_event_snapshot_missing")
        position += 1


def _native_event(kind, digest, stage_id, snapshot, created_at, **extra):
    if (kind not in {"native_pg_stage", "legacy_classroom"} or not SHA.fullmatch(str(digest))
            or not isinstance(stage_id, str) or not ID.fullmatch(stage_id)
            or not isinstance(snapshot, dict) or not isinstance(snapshot.get("stage"), dict)
            or snapshot["stage"].get("id") != stage_id or snapshot.get("id", stage_id) != stage_id
            or not isinstance(snapshot.get("scenes"), list) or not snapshot["scenes"]):
        raise ArchiveQueueError("archive_event_identity_invalid")
    return {"sourceKind": kind, "sourceDigest": digest, "stageId": stage_id,
            "snapshot": snapshot, "createdAt": created_at, **extra}


def filesystem_event(path):
    raw = _read(path)
    event = json.loads(raw)
    if event.get("schemaVersion") != "mira.course-archive.event.v1":
        raise ArchiveQueueError("archive_event_schema_invalid")
    snapshot_raw = _snapshot_raw(raw)
    digest = event.get("sourceDigest")
    if _sha(snapshot_raw.encode()) != digest:
        raise ArchiveQueueError("archive_event_digest_mismatch")
    result = _native_event(event.get("sourceKind"), digest, event.get("stageId"),
        event.get("snapshot"), event.get("createdAt"), sourceRaw=snapshot_raw,
        origin="filesystem", eventPath=str(Path(path).absolute()), eventRawSha256=_sha(raw))
    expected = "legacy-" + _sha((result["stageId"] + ":" + digest).encode()) + ".json"
    if result["sourceKind"] != "legacy_classroom" or Path(path).name != expected:
        raise ArchiveQueueError("archive_event_filename_invalid")
    return result


def postgres_event(row):
    event_id = str(row.get("id", ""))
    revision = str(row.get("stage_revision", ""))
    if not re.fullmatch(r"[1-9][0-9]*", event_id) or not revision.isdigit():
        raise ArchiveQueueError("archive_pg_event_invalid")
    snapshot = row.get("snapshot_json")
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    binding = {}
    if row.get("session_id") is not None:
        if not isinstance(row["session_id"], str) or not ID.fullmatch(row["session_id"]):
            raise ArchiveQueueError("archive_pg_authoring_binding_invalid")
        binding["authoringBinding"] = {"sessionId": row["session_id"]}
    return _native_event(row.get("source_kind"), row.get("source_digest"), row.get("stage_id"),
        snapshot, row.get("created_at"), origin="postgres", eventId=event_id, revision=revision, **binding)


class NodeArchiveClient:
    """Only archive transport and outbox operations are available to this worker."""
    def __init__(self, *, project_root, node="node", timeout=3600):
        self.root, self.node, self.timeout = Path(project_root), node, timeout
        self.script = self.root / "openmaic-runtime/scripts/course-archive.mjs"

    def _run(self, command, **options):
        args = [self.node, str(self.script), command]
        for key, value in options.items():
            args.extend(["--" + key.replace("_", "-"), str(value)])
        try:
            result = subprocess.run(args, cwd=self.root, text=True, capture_output=True,
                                    timeout=self.timeout if command == "upload" else 45)
            value = json.loads(result.stdout) if result.returncode == 0 else None
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise ArchiveQueueError("archive_" + command + "_failed") from error
        if not isinstance(value, dict):
            # Provider responses, environment and untrusted stderr never enter logs.
            raise ArchiveQueueError("archive_" + command + "_failed")
        return value

    def events(self, *, after_id=0, limit=100):
        result = self._run("events", after_id=after_id, limit=limit)
        if not isinstance(result.get("events"), list):
            raise ArchiveQueueError("archive_events_invalid")
        return result["events"]

    def saved_stages(self, *, after_stage_id="", limit=100):
        options = {"limit": limit}
        if after_stage_id:
            options["after_stage_id"] = after_stage_id
        result = self._run("saved-stages", **options)
        if not isinstance(result.get("stages"), list):
            raise ArchiveQueueError("archive_saved_stages_invalid")
        return result["stages"]

    def upload(self, index):
        return self._run("upload", index=index)

    def acknowledge(self, event_id, digest):
        if self._run("ack", id=event_id, digest=digest).get("acknowledged") is not True:
            raise ArchiveQueueError("archive_ack_not_confirmed")


class CourseArchiveQueue:
    def __init__(self, state_root, storage, *, clock=time.time):
        self.root = _directory(Path(state_root).absolute())
        self.directory = _directory(self.root / "archive-queue")
        self.items = _directory(self.directory / "items")
        self.storage = storage_identity(storage["endpoint"], storage["bucket"], storage.get("region", "us-east-1"))
        self.clock = clock

    @contextmanager
    def lock(self):
        descriptor = os.open(self.directory / "worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ArchiveQueueError("archive_worker_already_running") from error
            yield
        finally:
            os.close(descriptor)

    def identity(self, event):
        return {"sourceKind": event["sourceKind"], "sourceDigest": event["sourceDigest"],
                **({"courseId": event["course"]["courseId"], "courseVersion": event["course"]["courseVersion"]}
                   if event.get("course") else {}),
                **({"archiveSourceRevision": event.get("archiveSourceRevision") or event.get("course", {}).get("archiveSourceRevision")}
                   if event.get("archiveSourceRevision") or event.get("course", {}).get("archiveSourceRevision") else {}),
                "storage": self.storage}

    def enqueue(self, event):
        identity = self.identity(event)
        if not SHA.fullmatch(identity["sourceDigest"]):
            raise ArchiveQueueError("archive_source_digest_invalid")
        key = _sha(_json(identity))
        path = self.items / (key + ".json")
        if path.exists() or path.is_symlink():
            job = json.loads(_read(path))
            if job.get("schemaVersion") != SCHEMA or job.get("identity") != identity:
                raise ArchiveQueueError("archive_queue_identity_conflict")
            if event.get("snapshot") != job["event"].get("snapshot"):
                raise ArchiveQueueError("archive_queue_snapshot_conflict")
            if event.get("priority", 0) < job.get("priority", 0):
                job["priority"] = event.get("priority", 0)
                self.save(job)
        else:
            job = {"schemaVersion": SCHEMA, "key": key, "identity": identity,
                   "event": event, "status": "pending", "attempts": 0, "nextAttemptAt": 0,
                   "createdAt": self.clock(), "priority": event.get("priority", 0)}
            _write(path, job)
        return job

    def save(self, job):
        if not SHA.fullmatch(job.get("key", "")) or job["identity"]["storage"] != self.storage:
            raise ArchiveQueueError("archive_job_identity_invalid")
        _write(self.items / (job["key"] + ".json"), job)

    def due(self, limit, max_priority=None):
        jobs = []
        for path in self.items.glob("*.json"):
            job = json.loads(_read(path))
            if (job.get("identity", {}).get("storage") != self.storage
                    or max_priority is not None and job.get("priority", 0) > max_priority
                    or job.get("status") == "complete" and job.get("stagingPruned") is True):
                continue
            if job.get("nextAttemptAt", 0) <= self.clock():
                jobs.append(job)
        return sorted(jobs, key=lambda j: (j.get("priority", 0), j.get("nextAttemptAt", 0), j["createdAt"], j["key"]))[:limit]


class CourseArchiveProcessor:
    def __init__(self, queue, exporter, client, *, database=None):
        self.queue, self.exporter, self.client, self.database = queue, exporter, client, database

    def _index(self, job):
        reference = job["export"]
        path = Path(reference["indexPath"])
        if not path.is_absolute() or not path.is_relative_to(self.queue.root / "archives"):
            raise ArchiveQueueError("archive_index_outside_staging")
        raw = _read(path)
        if _sha(raw) != reference["indexSha256"]:
            raise ArchiveQueueError("archive_frozen_index_changed")
        index = json.loads(raw)
        event = job["event"]
        if (index.get("complete") is not True or index.get("missingSources")
                or index.get("archiveId") != reference["archiveId"]
                or not isinstance(index.get("generatedPublicFiles"), list) or not index["generatedPublicFiles"]):
            raise ArchiveQueueError("archive_export_incomplete")
        if event.get("course"):
            course = event["course"]
            if any(index.get(k) != course[k] for k in ("courseId", "courseVersion")):
                raise ArchiveQueueError("archive_export_course_mismatch")
            actual = index.get("sourceDigest") or index.get("releaseSha256")
            if actual != event["sourceDigest"]:
                raise ArchiveQueueError("archive_export_digest_mismatch")
        elif index.get("sourceKind") != event["sourceKind"] or index.get("sourceDigest") != event["sourceDigest"]:
            raise ArchiveQueueError("archive_export_digest_mismatch")
        return index

    def _missing_dependencies(self, missing):
        """Retry a partial capture only when a missing dependency changes.

        A new catalog authority revision is a new job. Safety adapter repairs
        must also unblock a frozen capture without changing its source digest.
        Unchanged missing sources and unchanged adapters never re-pack a ZIP.
        """
        root = Path(getattr(self.exporter, "root", self.queue.root.parent)).resolve()
        evidence = []
        for item in missing:
            identity = item.get("sourceIdentity") if isinstance(item, dict) else None
            row = {"missing": item}
            if isinstance(identity, str) and identity:
                source = Path(identity)
                source = source if source.is_absolute() else root / source
                if source.is_relative_to(root) and ".." not in source.parts:
                    for path in (source, source.parent):
                        try:
                            info = path.lstat()
                            row[str(path.relative_to(root))] = [info.st_dev, info.st_ino, info.st_size,
                                info.st_mtime_ns, info.st_ctime_ns, stat.S_ISLNK(info.st_mode)]
                        except FileNotFoundError:
                            row[str(path.relative_to(root))] = None
            evidence.append(row)
        # A newly migrated remote source also resolves a missing local alias.
        manifest = self.queue.root / "active-manifest.json"
        try:
            info = manifest.lstat()
            evidence.append({"activeManifest": [info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]})
        except FileNotFoundError:
            pass
        adapters = []
        for relative in ADAPTER_SOURCES:
            path = root / relative
            try:
                info = path.lstat()
                raw = _read(path)
                adapters.append({"path": relative, "sha256": _sha(raw),
                    "stat": [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]})
            except FileNotFoundError:
                adapters.append({"path": relative, "missing": True})
        evidence.append({"adapters": adapters})
        return _sha(_json(evidence))

    def _export(self, job):
        event = job["event"]
        # Never consume the last free disk space on a repeated incomplete
        # capture. Retained failed captures need an operator, not a paid retry.
        space = os.statvfs(self.queue.root)
        previous = job.get("incompleteExports", [])
        if previous and previous[-1].get("dependencySignature") == self._missing_dependencies(
                previous[-1].get("missingSources", [])):
            raise ArchiveQueueError("archive_missing_dependencies_unchanged")
        estimate = max((item.get("stagingBytes", 0) for item in previous), default=0)
        if space.f_bavail * space.f_frsize < max(512 * 1024**2, estimate + 256 * 1024**2):
            raise ArchiveQueueError("archive_staging_space_unavailable")
        if event.get("course"):
            from scripts.course_storage_releases import read_only_connection
            course = event["course"]
            with read_only_connection(self.database) as conn:
                result = self.exporter.export_course(conn, course_id=course["courseId"],
                    course_version=course["courseVersion"], content_key=course.get("contentKey"),
                    staging_root=self.queue.root / "archives")
        elif event["origin"] == "authoring-history":
            from services.course_archive_history import export_authoring_history
            result = export_authoring_history(self.exporter, event,
                staging_root=self.queue.root / "archives")
        elif (event["origin"] == "legacy-reconcile" and Path(event["legacyPath"]).exists()
              and _sha(_read(Path(event["legacyPath"]))) == event["sourceDigest"]):
            result = self.exporter.export_legacy_classroom(event["stageId"],
                staging_root=self.queue.root / "archives")
        else:
            stage = event["snapshot"]["stage"]
            meta = {"courseId": "native-" + event["stageId"],
                "courseVersion": "saved-" + event["sourceDigest"],
                "title": stage.get("name") or stage.get("title") or "已保存课件",
                "subject": stage.get("subject") or stage.get("subjectCode") or "course",
                "generatedAt": event["createdAt"], **{k: stage[k] for k in
                    ("gradeCode", "gradeLabel", "editionId", "editionLabel", "schoolSystem",
                     "volumeCode", "volumeLabel", "storageEditionLabel", "storageGradeLabel") if stage.get(k)}}
            if event.get("sourceRaw"):
                meta["sourceRaw"] = event["sourceRaw"]
            extra = {"authoring_binding": event["authoringBinding"]} if event.get("authoringBinding") else {}
            result = self.exporter.export_native_snapshot(event["snapshot"],
                source_kind=event["sourceKind"], source_digest=event["sourceDigest"],
                staging_root=self.queue.root / "archives", meta=meta, **extra)
        path = Path(result["indexPath"])
        if not path.is_absolute() or not path.is_relative_to(self.queue.root / "archives"):
            raise ArchiveQueueError("archive_index_outside_staging")
        raw = _read(path)
        reference = {"indexPath": str(path), "indexSha256": _sha(raw), "archiveId": result["archiveId"]}
        if result.get("complete") is not True or result.get("missingSources"):
            # Keep the diagnostic capture, but allow the exact source event to
            # be retried when its missing media becomes available. Never call
            # generation/TTS to repair it, or send a partial ZIP to transport.
            reference["stagingBytes"] = sum(p.stat().st_size for p in path.parent.rglob("*")
                if p.is_file() and not p.is_symlink())
            reference["missingSources"] = result.get("missingSources", [])
            reference["dependencySignature"] = self._missing_dependencies(reference["missingSources"])
            job.setdefault("incompleteExports", []).append(reference)
            self.queue.save(job)
            raise ArchiveQueueError("archive_export_incomplete")
        job["export"] = reference
        # A complete export is frozen before any network operation. Upload
        # and acknowledgement retries must reuse the same index and ZIP.
        self.queue.save(job)

    def _receipt(self, job, index, returned=None):
        base = self.queue.root / "archive-transfers" / index["archiveId"]
        candidates = [base / "verifications" / _sha(_json(self.queue.storage)) /
            (job["export"]["indexSha256"] + ".json"),
            base / "verifications" / (job["export"]["indexSha256"] + ".json"),
            base / "verified-complete.json"]
        path = Path(job["receiptPath"]) if job.get("receiptPath") else next(
            (candidate for candidate in candidates if candidate.exists()), candidates[0])
        if not path.is_relative_to(base):
            raise ArchiveQueueError("archive_receipt_outside_state")
        raw = _read(path)
        receipt = json.loads(raw)
        expected = {e["relativePath"]: (e["sha256"], e["byteSize"]) for e in index["generatedPublicFiles"]}
        objects = receipt.get("objects")
        if (receipt.get("schemaVersion") != "mira.course-archive.verification.v1"
                or receipt.get("complete") is not True or receipt.get("storage") != self.queue.storage
                or receipt.get("archiveId") != index["archiveId"]
                or receipt.get("indexSha256") != job["export"]["indexSha256"]
                or receipt.get("sourceDigest") != index.get("sourceDigest")
                or any(receipt.get(k) != index.get(k) for k in ("courseId", "courseVersion"))
                or not isinstance(objects, list) or len(objects) != len(expected)
                or len(expected) != len(index["generatedPublicFiles"])
                or receipt.get("byteSize") != sum(size for _, size in expected.values())
                or returned is not None and returned != receipt):
            raise ArchiveQueueError("archive_verification_not_bound")
        seen = set()
        for obj in objects:
            key = obj.get("objectKey")
            if (key in seen or key not in expected or (obj.get("sha256"), obj.get("byteSize")) != expected[key]
                    or not isinstance(obj.get("etag"), str) or not obj["etag"]
                    or "versionId" in obj and (not isinstance(obj["versionId"], str) or not obj["versionId"])):
                raise ArchiveQueueError("archive_object_verification_incomplete")
            seen.add(key)
        if job.get("receiptSha256") and job["receiptSha256"] != _sha(raw):
            raise ArchiveQueueError("archive_receipt_changed")
        job["receiptPath"] = str(path)
        return _sha(raw)

    def _prune_staging(self, job, index):
        """Discard only this exporter-owned derived tree after upload AND ack."""
        if job.get("stagingPruned") is True:
            return
        stage = Path(job["export"]["indexPath"]).parent
        if (stage.parent != self.queue.root / "archives"
                or not re.fullmatch(re.escape(index["archiveId"]) + r"-[a-f0-9]{8}", stage.name)
                or index.get("stagingDirectory") != str(stage)):
            raise ArchiveQueueError("archive_cleanup_ownership_invalid")
        _directory(stage)
        payload = stage / "课程资料"
        original_manifest = Path(index.get("manifestPath", ""))
        if original_manifest != payload / "manifest.json":
            raise ArchiveQueueError("archive_cleanup_manifest_invalid")
        retained = stage / "manifest.json"
        manifest_entry = next((entry for entry in index["generatedPublicFiles"]
            if entry.get("localPath") == str(original_manifest)), None)
        if not manifest_entry:
            raise ArchiveQueueError("archive_cleanup_manifest_not_verified")
        raw = _read(retained if retained.exists() else original_manifest)
        if _sha(raw) != manifest_entry["sha256"] or len(raw) != manifest_entry["byteSize"]:
            raise ArchiveQueueError("archive_cleanup_manifest_changed")
        if not retained.exists():
            descriptor = os.open(retained, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            _sync_directory(stage)
        zip_path = Path(index.get("zip", {}).get("path", ""))
        if zip_path.parent != stage or zip_path.suffix != ".zip":
            raise ArchiveQueueError("archive_cleanup_zip_invalid")
        allowed = {"index.json", "manifest.json", "课程资料", "asset-sources", zip_path.name}
        if any(p.name not in allowed for p in stage.iterdir()):
            raise ArchiveQueueError("archive_cleanup_unexpected_file")
        removable = ([zip_path] if zip_path.exists() or zip_path.is_symlink() else [])
        for derived in (payload, stage / "asset-sources"):
            if derived.exists() or derived.is_symlink():
                if derived.is_symlink() or not derived.is_dir():
                    raise ArchiveQueueError("archive_cleanup_symlink")
                removable.extend(derived.rglob("*"))
                removable.append(derived)
        identities = {}
        for path in removable:
            _directory(path.parent)
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ArchiveQueueError("archive_cleanup_symlink_or_special_file")
            identities[path] = (info.st_dev, info.st_ino, info.st_mode)
        # Record the recovery manifest location before deleting any derivative.
        job["retainedManifestPath"] = str(retained)
        self.queue.save(job)
        for path in sorted(removable, key=lambda p: len(p.parts), reverse=True):
            _directory(path.parent)
            info = path.lstat()
            if (info.st_dev, info.st_ino, info.st_mode) != identities[path]:
                raise ArchiveQueueError("archive_cleanup_source_changed")
            path.rmdir() if stat.S_ISDIR(info.st_mode) else path.unlink()
        _sync_directory(stage)
        job["stagingPruned"] = True
        self.queue.save(job)

    @staticmethod
    def _cleanup_file(path):
        """Hash an owned regular file and detect replacement during the read."""
        _directory(path.parent)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ArchiveQueueError("archive_incomplete_cleanup_special_file")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ArchiveQueueError("archive_incomplete_cleanup_special_file")
            digest, size = hashlib.sha256(), 0
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
            after = os.fstat(stream.fileno())
        current = path.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) or getattr(before, k) != getattr(current, k)
               for k in fields):
            raise ArchiveQueueError("archive_incomplete_cleanup_file_changed")
        return {"sha256": digest.hexdigest(), "byteSize": size,
                "identity": [getattr(before, k) for k in fields]}

    @staticmethod
    def _cleanup_manifest_files(manifest):
        result = {}
        if not isinstance(manifest.get("files"), list):
            raise ArchiveQueueError("archive_incomplete_cleanup_manifest_invalid")
        for entry in manifest["files"]:
            name = entry.get("archivePath")
            if (not isinstance(name, str) or not name or "\\" in name or "\x00" in name
                    or name.startswith("/") or any(p in {"", ".", ".."} for p in name.split("/"))
                    or name in result or type(entry.get("original")) is not bool
                    or not isinstance(entry.get("sourceIdentity"), str) or not entry["sourceIdentity"]
                    or not SHA.fullmatch(str(entry.get("sha256", "")))
                    or type(entry.get("byteSize")) is not int or entry["byteSize"] < 0):
                raise ArchiveQueueError("archive_incomplete_cleanup_manifest_invalid")
            result[name] = entry
        return result

    def _review_asset_copy_ownership(self, name, evidence, old_files, new_files, stage, previous):
        """Bind the exporter's review-PNG cache name to its exact archived receipts."""
        match = re.fullmatch(r"review-([a-f0-9]{64})\.png", name)
        if not match or match[1] != evidence["sha256"]:
            return None
        native = [entry for entry in old_files.values() if entry.get("original") is True
                  and entry.get("sourceKind") == "native_standard_asset"
                  and all(entry.get(k) == evidence[k] for k in ("sha256", "byteSize"))]
        if not native:
            return None
        bindings = []
        for old in native:
            url, receipt = old["sourceIdentity"], old.get("sourceReceipt")
            if (old.get("mimeType") != "image/png"
                    or not re.fullmatch(r"/review-assets/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.png", url)
                    or not isinstance(receipt, dict) or not isinstance(receipt.get("archivePath"), str)
                    or not SHA.fullmatch(str(receipt.get("sha256", "")))):
                return None
            replacements = [entry for entry in new_files.values() if entry.get("original") is True
                and entry.get("sourceKind") == "native_standard_asset" and entry.get("sourceIdentity") == url
                and entry.get("sourceReceipt") == receipt
                and all(entry.get(k) == old[k] for k in ("sha256", "byteSize", "mimeType"))]
            old_receipt, new_receipt = old_files.get(receipt["archivePath"]), new_files.get(receipt["archivePath"])
            if (len(replacements) != 1 or not old_receipt or not new_receipt
                    or any(entry.get("original") is not True or entry.get("sourceKind") != "owned_original_file"
                           or entry.get("mimeType") != "application/json" or entry["sha256"] != receipt["sha256"]
                           for entry in (old_receipt, new_receipt))
                    or any(new_receipt.get(k) != old_receipt[k] for k in ("sourceIdentity", "sha256", "byteSize"))):
                return None
            receipt_binding = {"schemaVersion": "mira.textbook.review-asset-source-receipt.v1",
                               "reviewUrl": url, "sourceFileSha256": evidence["sha256"]}
            receipt_path = stage / "课程资料" / receipt["archivePath"]
            try:
                receipt_path.lstat()  # Do not recreate a removed receipt's parents on resume.
                raw = _read(receipt_path)
                value = json.loads(raw)
                if (not isinstance(value, dict) or _sha(raw) != receipt["sha256"] or len(raw) != old_receipt["byteSize"]
                        or any(value.get(k) != v for k, v in receipt_binding.items())):
                    return None
            except FileNotFoundError:
                prior = next((entry for entry in (previous or {}).get("files", [])
                    if entry.get("path") == receipt_path.relative_to(stage).as_posix()), {})
                if not previous or any(prior.get(k) != old_receipt[k] for k in ("sha256", "byteSize")):
                    return None
            except (OSError, ValueError, ArchiveQueueError):
                return None
            bindings.append({"sourceIdentity": url, "oldArchivePath": old["archivePath"],
                "replacementArchivePath": replacements[0]["archivePath"], "sourceReceipt": deepcopy(receipt),
                "receiptSourceIdentity": old_receipt["sourceIdentity"], "receiptByteSize": old_receipt["byteSize"],
                "receiptBinding": receipt_binding})
        return {"schemaVersion": "mira.course-archive.review-asset-copy.v1",
                "nativeAssets": sorted(bindings, key=lambda entry: entry["sourceIdentity"])}

    def _zip_only_cleanup_proof(self, job, reference, index, raw, manifest_raw, old_files, previous):
        """Accept only the private, byte-bound evidence of an earlier ZIP-only removal."""
        stage = Path(reference["indexPath"]).parent
        directory = self.queue.root / "archive-retirements" / job["key"] / "zip-only-captures" / stage.name
        journal = directory / "zip-only-cleanup.json"
        invalid = "archive_incomplete_cleanup_zip_only_proof_invalid"

        def private_bytes(path):
            # lstat first: a missing proof must not create its directory via _read.
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600:
                raise ArchiveQueueError(invalid)
            value = _read(path)
            after = path.lstat()
            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, k) != getattr(after, k) for k in fields):
                raise ArchiveQueueError(invalid)
            return value

        def file_identity(value, size):
            return (isinstance(value, list) and len(value) == 6
                    and all(type(part) is int for part in value)
                    and stat.S_ISREG(value[2]) and value[3] == size)

        try:
            journal_raw = private_bytes(journal)
            proof = json.loads(journal_raw)
            zip_record = proof.get("removedZip") if isinstance(proof, dict) else None
            expected = {"schemaVersion": "mira.course-archive.zip-only-cleanup.v1",
                "status": "zip-removed-payload-retained", "mode": "zip-only", "jobKey": job["key"],
                "indexPath": reference["indexPath"], "indexSha256": _sha(raw),
                "manifestPath": index["manifestPath"], "manifestSha256": _sha(manifest_raw),
                "retainedIndexPath": str(directory / "index.json"),
                "retainedManifestPath": str(directory / "manifest.json")}
            if (not isinstance(zip_record, dict) or any(proof.get(k) != v for k, v in expected.items())
                    or proof.get("payloadPruned") is not False or proof.get("establishesComplete") is not False
                    or proof.get("queueRecordChanged") is not False
                    or any(zip_record.get(k) != index["zip"].get(k) for k in ("path", "sha256", "byteSize"))
                    or not SHA.fullmatch(str(zip_record.get("sha256", "")))
                    or type(zip_record.get("byteSize")) is not int or zip_record["byteSize"] < 0
                    or not file_identity(zip_record.get("identity"), zip_record["byteSize"])
                    or private_bytes(directory / "index.json") != raw
                    or private_bytes(directory / "manifest.json") != manifest_raw):
                raise ArchiveQueueError(invalid)
            result = {"path": str(journal), "sha256": _sha(journal_raw)}
            if previous and previous.get("zipOnlyProof") != result:
                raise ArchiveQueueError(invalid)
            entries = proof.get("verifiedEntries")
            if not isinstance(entries, list) or len(entries) != len(old_files) + 1:
                raise ArchiveQueueError(invalid)
            expected_entries = {**old_files, "manifest.json": {
                "sha256": _sha(manifest_raw), "byteSize": len(manifest_raw), "original": False}}
            payload = stage / "课程资料"
            prior_files = {entry["path"]: entry for entry in previous.get("files", [])} if previous else {}
            seen = set()
            for entry in entries:
                name = entry.get("archivePath") if isinstance(entry, dict) else None
                if not isinstance(name, str) or name not in expected_entries or name in seen:
                    raise ArchiveQueueError(invalid)
                seen.add(name)
                wanted, filename = expected_entries[name], payload / name
                if (entry.get("payloadPath") != str(filename)
                        or any(entry.get(k) != wanted[k] for k in ("sha256", "byteSize", "original"))
                        or type(entry.get("byteSize")) is not int or type(entry.get("original")) is not bool
                        or not file_identity(entry.get("payloadIdentity"), wanted["byteSize"])
                        or type(entry.get("zipCRC")) is not int or not 0 <= entry["zipCRC"] <= 0xffffffff):
                    raise ArchiveQueueError(invalid)
                if previous and not filename.exists() and not filename.is_symlink():
                    # Only an already-persisted normal cleanup plan may account
                    # for payload files removed during an interrupted cleanup.
                    prior = prior_files.get(filename.relative_to(stage).as_posix(), {})
                    if any(prior.get(k) != wanted[k] for k in ("sha256", "byteSize")):
                        raise ArchiveQueueError(invalid)
                    continue
                _directory(filename.parent)
                info = filename.lstat()
                fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
                if [getattr(info, k) for k in fields] != entry["payloadIdentity"]:
                    raise ArchiveQueueError(invalid)
            return result
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ArchiveQueueError(invalid) from error

    @staticmethod
    def _inherited_audio_alias_coverage(uncovered, new_files, manifest):
        """Cover only a producer-proven alias of the exact same Native WAV member."""
        aliases = manifest.get("recoveredAliases", [])
        if not isinstance(aliases, list):
            return []
        prefix = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/"
        result = []
        for old in uncovered:
            match = re.fullmatch(r"媒体/(" + re.escape(prefix)
                + r"([A-Za-z0-9_-]{1,255})/audio/(tbprev_[a-f0-9]{64})\.wav)", old["archivePath"])
            new = new_files.get(old["archivePath"])
            if (not match or not new or old.get("original") is not True or old.get("sourceKind") != "referenced_media"
                    or new.get("sourceKind") != "referenced_media" or new.get("original") is not True
                    or old.get("mimeType") != "audio/wav"
                    or any(new.get(k) != old.get(k) for k in ("sha256", "byteSize", "mimeType"))):
                continue
            physical, stage, request = match.groups()
            uri = "/api/classroom-media/" + physical.removeprefix(prefix)
            named = re.fullmatch(re.escape("/api/classroom-media/" + stage + "/audio/")
                + r"(cue-(?:me|you|he)|speaker-(?:teal|coral))\.wav", str(new.get("sourceIdentity", "")))
            if old["sourceIdentity"] not in {physical, uri} or not named:
                continue
            matches = [entry for entry in aliases if isinstance(entry, dict)
                and entry.get("archivePath") == old["archivePath"]
                and entry.get("originalReference") == new["sourceIdentity"]]
            if len(matches) != 1:
                continue
            alias = matches[0]
            if (alias.get("recoveryReason") != "historical_audio_alias_from_verified_inherited_receipt"
                    or alias.get("ttsRequestId") != request or alias.get("actionId") != "review_" + named[1]
                    or not isinstance(alias.get("sceneId"), str) or not ID.fullmatch(alias["sceneId"])
                    or type(alias.get("byteSize")) is not int
                    or any(alias.get(k) != old.get(k) for k in ("sha256", "byteSize", "mimeType"))):
                continue
            evidence, hashes = alias.get("evidence"), alias.get("evidenceSha256")
            if (not isinstance(evidence, list) or not evidence or not all(isinstance(p, str) for p in evidence)
                    or len(set(evidence)) != len(evidence) or not isinstance(hashes, dict)
                    or set(hashes) != set(evidence)):
                continue
            base = prefix + stage + "/textbook-preview-audio/operator-parent/"
            audio = base + "audio/" + request + ".wav"
            paid_job = "openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/jobs/tts/" + _sha(request.encode()) + ".json"
            if not {base + "source-receipts.json", audio, paid_job}.issubset(evidence):
                continue
            valid = True
            for source in evidence:
                entry = new_files.get("原稿/" + source)
                if (source.startswith("/") or "\\" in source
                        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in source)
                        or any(part in {"", ".", ".."} for part in source.split("/"))
                        or not entry or entry.get("original") is not True
                        or entry.get("sourceKind") != "owned_original_file" or entry.get("sourceIdentity") != source
                        or not SHA.fullmatch(str(hashes[source])) or entry["sha256"] != hashes[source]):
                    valid = False
                    break
            original_audio = new_files.get("原稿/" + audio, {})
            if (not valid or original_audio.get("mimeType") not in ("audio/wav", "audio/x-wav")
                    or any(original_audio.get(k) != old[k] for k in ("sha256", "byteSize"))):
                continue
            result.append({"archivePath": old["archivePath"], "oldIdentity": old["sourceIdentity"],
                "newIdentity": new["sourceIdentity"], "sha256": old["sha256"], "byteSize": old["byteSize"],
                "mimeType": old["mimeType"], "alias": deepcopy(alias)})
        return sorted(result, key=lambda entry: entry["archivePath"])

    @staticmethod
    def _private_recovery_omissions(uncovered, manifest):
        def normalized_parts(value):
            if (not isinstance(value, str) or not value or value.startswith("/") or "\\" in value
                    or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)
                    or any(part in {"", ".", ".."} for part in value.split("/"))):
                return None
            return tuple(value.split("/"))

        approved = []
        entries = manifest.get("excludedFiles", [])
        for entry in entries if isinstance(entries, list) else []:
            if (isinstance(entry, dict) and isinstance(entry.get("reason"), str) and entry["reason"] in {
                    "retained_private_runtime_recovery_backup", "retained_private_runtime_compile_staging"}):
                parts = normalized_parts(entry.get("sourceIdentity"))
                if parts:
                    approved.append((parts, {k: entry[k] for k in ("sourceIdentity", "reason")}))
        result = {}
        for entry in uncovered:
            parts = normalized_parts(entry["sourceIdentity"])
            matches = [(prefix, omission) for prefix, omission in approved
                       if parts and len(prefix) <= len(parts) and parts[:len(prefix)] == prefix]
            if not matches:
                raise ArchiveQueueError("archive_incomplete_cleanup_original_not_covered")
            longest = max(len(prefix) for prefix, _ in matches)
            specific = {(omission["sourceIdentity"], omission["reason"]) for prefix, omission in matches
                        if len(prefix) == longest}
            if len(specific) != 1:
                raise ArchiveQueueError("archive_incomplete_cleanup_original_not_covered")
            source, reason = specific.pop()
            result[(entry["sourceIdentity"], entry["sha256"], entry["byteSize"])] = {
                "sourceIdentity": source, "reason": reason}
        return result

    def _private_recovery_cleanup_proof(self, job, reference, index, raw, manifest_raw, uncovered, omissions, previous):
        """Supplement explicit private omissions with independently retained original bytes."""
        stage = Path(reference["indexPath"]).parent
        directory = self.queue.root / "archive-retirements" / job["key"] / "private-recovery" / stage.name
        path = directory / "private-recovery.json"
        invalid = "archive_incomplete_cleanup_private_recovery_invalid"

        def private_bytes(filename):
            before = filename.lstat()
            if not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600:
                raise ArchiveQueueError(invalid)
            value = _read(filename)
            after = filename.lstat()
            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, k) != getattr(after, k) for k in fields):
                raise ArchiveQueueError(invalid)
            return value

        identity = lambda entry: (entry.get("sourceIdentity"), entry.get("sha256"), entry.get("byteSize"))
        try:
            proof_raw = private_bytes(path)
            proof = json.loads(proof_raw)
            old_binding = {"jobKey": job["key"], "captureStage": str(stage), "indexPath": reference["indexPath"],
                "indexSha256": _sha(raw), "manifestPath": index["manifestPath"],
                "manifestSha256": _sha(manifest_raw), "retainedIndexPath": str(directory / "index.json"),
                "retainedManifestPath": str(directory / "manifest.json")}
            expected = {**old_binding, "schemaVersion": "mira.course-archive.private-recovery.v2",
                "status": "bound-complete-replacement", "replacementIndexSha256": job["export"]["indexSha256"],
                "receiptSha256": job["receiptSha256"],
                "provisionalProofPath": str(directory / "private-recovery.provisional.json")}
            if (not isinstance(proof, dict) or any(proof.get(k) != v for k, v in expected.items())
                    or any(proof.get(k) is not False for k in ("publicUploadAllowed", "payloadPruned", "queueRecordChanged"))
                    or private_bytes(directory / "index.json") != raw
                    or private_bytes(directory / "manifest.json") != manifest_raw):
                raise ArchiveQueueError(invalid)
            provisional_raw = private_bytes(directory / "private-recovery.provisional.json")
            provisional = json.loads(provisional_raw)
            if (not isinstance(provisional, dict) or _sha(provisional_raw) != proof.get("provisionalProofSha256")
                    or provisional.get("schemaVersion") != "mira.course-archive.private-recovery.v1"
                    or provisional.get("status") != "verified-private-recovery"
                    or any(provisional.get(k) != v for k, v in old_binding.items())
                    or not isinstance(provisional.get("files"), list)
                    or not all(isinstance(entry, dict) for entry in provisional["files"])):
                raise ArchiveQueueError(invalid)
            provisional_files = {identity(entry): entry for entry in provisional["files"]}
            wanted = {identity(entry): entry for entry in uncovered}
            entries, seen = proof.get("files"), set()
            if (not isinstance(entries, list) or len(entries) != len(wanted)
                    or type(proof.get("fileCount")) is not int or proof["fileCount"] != len(wanted)
                    or type(proof.get("byteSize")) is not int
                    or proof["byteSize"] != sum(entry["byteSize"] for entry in wanted.values())):
                raise ArchiveQueueError(invalid)
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ArchiveQueueError(invalid)
                key = identity(entry)
                if (key not in wanted or key in seen or entry.get("original") is not True
                        or type(entry.get("byteSize")) is not int or entry.get("archivePath") != wanted[key]["archivePath"]
                        or entry.get("matchedOmission") != omissions[key]
                        or key not in provisional_files
                        or entry.get("recoveryPath") != provisional_files[key].get("recoveryPath")):
                    raise ArchiveQueueError(invalid)
                seen.add(key)
                filename = Path(entry["recoveryPath"])
                if (str(filename) != entry["recoveryPath"] or filename.parent != directory / "files"
                        or not re.fullmatch(r"[a-f0-9]{64}\.[A-Za-z0-9]+", filename.name)
                        or filename.stem != entry["sha256"]):
                    raise ArchiveQueueError(invalid)
                evidence = self._cleanup_file(filename)
                descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
                    if (stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                            or [getattr(info, k) for k in fields] != evidence["identity"]
                            or any(evidence[k] != entry[k] for k in ("sha256", "byteSize"))):
                        raise ArchiveQueueError(invalid)
                    os.fsync(stream.fileno())
                    current = filename.lstat()
                    if current.st_nlink != 1 or [getattr(current, k) for k in fields] != evidence["identity"]:
                        raise ArchiveQueueError(invalid)
            result = {"path": str(path), "sha256": _sha(proof_raw)}
            if previous and previous.get("privateRecoveryProof") != result:
                raise ArchiveQueueError(invalid)
            return result
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ArchiveQueueError(invalid) from error

    def _incomplete_cleanup_plan(self, job, reference, replacement, replacement_manifest):
        path = Path(reference.get("indexPath", ""))
        stage = path.parent
        if (not path.is_absolute() or path.name != "index.json"
                or stage.parent != self.queue.root / "archives" or path == Path(job["export"]["indexPath"])):
            raise ArchiveQueueError("archive_incomplete_cleanup_ownership_invalid")
        raw = _read(path)
        if _sha(raw) != reference.get("indexSha256"):
            raise ArchiveQueueError("archive_incomplete_cleanup_index_changed")
        index = json.loads(raw)
        if (index.get("archiveId") != reference.get("archiveId")
                or not re.fullmatch(re.escape(index.get("archiveId", "")) + r"-[a-f0-9]{8}", stage.name)
                or index.get("stagingDirectory") != str(stage)
                or index.get("complete") is not False or not index.get("missingSources")
                or index.get("generatedPublicFiles") != []
                or index.get("sourceKind") != job["event"]["sourceKind"]
                or (index.get("sourceDigest") or index.get("releaseSha256")) != job["event"]["sourceDigest"]
                or any(index.get(k) != replacement.get(k) for k in
                       ("courseId", "courseVersion", "contentKey", "classroomId", "releaseSha256"))):
            raise ArchiveQueueError("archive_incomplete_cleanup_source_mismatch")
        # Another queue identity must not be using this capture, even when an
        # operator accidentally attached the same index to multiple jobs.
        for other_path in self.queue.items.glob("*.json"):
            if other_path.name == job["key"] + ".json":
                continue
            other = json.loads(_read(other_path))
            refs = [other.get("export", {}), *other.get("incompleteExports", [])]
            if any(item.get("indexPath") == str(path) for item in refs):
                raise ArchiveQueueError("archive_incomplete_cleanup_other_consumer")
        payload, retained = stage / "课程资料", stage / "manifest.json"
        manifest_path = Path(index.get("manifestPath", ""))
        if manifest_path != payload / "manifest.json":
            raise ArchiveQueueError("archive_incomplete_cleanup_manifest_invalid")
        manifest_raw = _read(retained if retained.exists() else manifest_path)
        manifest = json.loads(manifest_raw)
        if (manifest.get("schemaVersion") != index.get("schemaVersion")
                or manifest.get("archiveId") != index["archiveId"] or manifest.get("complete") is not False
                or any(manifest.get("identity", {}).get(k) != index.get(k) for k in
                       ("courseId", "courseVersion", "contentKey", "classroomId", "releaseSha256"))):
            raise ArchiveQueueError("archive_incomplete_cleanup_manifest_invalid")
        old_files = self._cleanup_manifest_files(manifest)
        new_files = self._cleanup_manifest_files(replacement_manifest)
        original = lambda entry: (entry["sourceIdentity"], entry["sha256"], entry["byteSize"])
        covered = {original(entry) for entry in new_files.values() if entry["original"]}
        originals = [entry for entry in old_files.values() if entry["original"]]
        uncovered = [entry for entry in originals if original(entry) not in covered]
        if not originals:
            raise ArchiveQueueError("archive_incomplete_cleanup_original_not_covered")
        audio_alias_coverage = self._inherited_audio_alias_coverage(uncovered, new_files, replacement_manifest)
        aliased_paths = {entry["archivePath"] for entry in audio_alias_coverage}
        uncovered = [entry for entry in uncovered if entry["archivePath"] not in aliased_paths]
        private_omissions = self._private_recovery_omissions(uncovered, replacement_manifest)
        zip_path = Path(index.get("zip", {}).get("path", ""))
        if zip_path.parent != stage or zip_path.suffix != ".zip":
            raise ArchiveQueueError("archive_incomplete_cleanup_zip_invalid")
        marker = stage / "incomplete-prune.json"
        binding = {"schemaVersion": "mira.course-archive.incomplete-prune.v1", "jobKey": job["key"],
            "oldIndexSha256": reference["indexSha256"], "oldManifestSha256": _sha(manifest_raw),
            "replacementIndexSha256": job["export"]["indexSha256"], "receiptSha256": job["receiptSha256"]}
        previous = json.loads(_read(marker)) if marker.exists() else None
        if previous and any(previous.get(k) != v for k, v in binding.items()):
            raise ArchiveQueueError("archive_incomplete_cleanup_plan_changed")
        if previous and previous.get("audioAliasCoverage", []) != audio_alias_coverage:
            raise ArchiveQueueError("archive_incomplete_cleanup_plan_changed")
        private_recovery_proof = None
        if uncovered:
            private_recovery_proof = self._private_recovery_cleanup_proof(
                job, reference, index, raw, manifest_raw, uncovered, private_omissions, previous)
        zip_only_proof = previous.get("zipOnlyProof") if previous else None
        if zip_path.exists() or zip_path.is_symlink():
            evidence = self._cleanup_file(zip_path)
            if (evidence["sha256"] != index["zip"].get("sha256")
                    or evidence["byteSize"] != index["zip"].get("byteSize")):
                raise ArchiveQueueError("archive_incomplete_cleanup_zip_changed")
            with zipfile.ZipFile(zip_path) as archive:
                if (len(archive.namelist()) != len(old_files) + 1
                        or set(archive.namelist()) != set(old_files) | {"manifest.json"}
                        or archive.read("manifest.json") != manifest_raw):
                    raise ArchiveQueueError("archive_incomplete_cleanup_zip_manifest_mismatch")
        elif not previous or zip_only_proof:
            zip_only_proof = self._zip_only_cleanup_proof(
                job, reference, index, raw, manifest_raw, old_files, previous)
        allowed = {"index.json", "manifest.json", "incomplete-prune.json", "课程资料", "asset-sources", zip_path.name}
        if any(item.name not in allowed for item in stage.iterdir()):
            raise ArchiveQueueError("archive_incomplete_cleanup_unexpected_file")
        files, directories = [], []
        candidates = [zip_path] if zip_path.exists() or zip_path.is_symlink() else []
        for directory in (payload, stage / "asset-sources"):
            if directory.exists() or directory.is_symlink():
                _directory(directory)
                for parent, children, names in os.walk(directory, followlinks=False):
                    directories.append(Path(parent))
                    for child in children:
                        if (Path(parent) / child).is_symlink():
                            raise ArchiveQueueError("archive_incomplete_cleanup_symlink")
                    candidates.extend(Path(parent) / name for name in names)
        old_bytes = {(entry["sha256"], entry["byteSize"]) for entry in old_files.values() if entry["original"]}
        old_plan = {item["path"]: item for item in previous.get("files", [])} if previous else {}
        expected_payload = {payload / name: entry for name, entry in old_files.items()}
        expected_payload[manifest_path] = {"sha256": _sha(manifest_raw), "byteSize": len(manifest_raw)}
        expected_directories = {payload, stage / "asset-sources"}
        for filename in expected_payload:
            expected_directories.update(p for p in filename.parents if p.is_relative_to(payload))
        if any(directory not in expected_directories for directory in directories):
            raise ArchiveQueueError("archive_incomplete_cleanup_unexpected_directory")
        for filename in candidates:
            evidence = self._cleanup_file(filename)
            expected = (index["zip"] if filename == zip_path else expected_payload.get(filename))
            review_asset_proof = None
            if expected is None and filename.parent == stage / "asset-sources":
                plain_cache_name = bool(re.fullmatch(r"[a-f0-9]{64}\.[A-Za-z0-9]+", filename.name)) and filename.stem == evidence["sha256"]
                if not plain_cache_name:
                    review_asset_proof = self._review_asset_copy_ownership(
                        filename.name, evidence, old_files, new_files, stage, previous)
                if ((not plain_cache_name and not review_asset_proof)
                        or (evidence["sha256"], evidence["byteSize"]) not in old_bytes):
                    raise ArchiveQueueError("archive_incomplete_cleanup_unowned_asset")
                expected = evidence
            if expected is None or any(evidence[k] != expected.get(k) for k in ("sha256", "byteSize")):
                raise ArchiveQueueError("archive_incomplete_cleanup_derivative_changed")
            relative = filename.relative_to(stage).as_posix()
            if previous and (relative not in old_plan or any(old_plan[relative].get(k) != evidence[k]
                                                             for k in ("sha256", "byteSize"))):
                raise ArchiveQueueError("archive_incomplete_cleanup_plan_changed")
            if previous and old_plan[relative].get("reviewAssetProof") != review_asset_proof:
                raise ArchiveQueueError("archive_incomplete_cleanup_plan_changed")
            files.append({"path": relative, **evidence,
                          **({"reviewAssetProof": review_asset_proof} if review_asset_proof else {})})
        if private_recovery_proof:
            # Payload hashing can be lengthy; recheck the independent recovery
            # bytes immediately before returning an actionable deletion plan.
            if self._private_recovery_cleanup_proof(
                    job, reference, index, raw, manifest_raw, uncovered, private_omissions, previous) != private_recovery_proof:
                raise ArchiveQueueError("archive_incomplete_cleanup_private_recovery_invalid")
        return {**binding, **({"zipOnlyProof": zip_only_proof} if zip_only_proof else {}),
                **({"privateRecoveryProof": private_recovery_proof} if private_recovery_proof else {}),
                **({"audioAliasCoverage": audio_alias_coverage} if audio_alias_coverage else {}),
                "originalFilesCovered": len(originals), "files": files,
                "directories": [str(p.relative_to(stage)) for p in directories],
                "bytes": sum(item["byteSize"] for item in files), "stage": str(stage),
                "manifestRaw": manifest_raw}

    def prune_incomplete_captures(self, job_key, *, dry_run=True):
        """Explicit, locked cleanup of superseded captures; never dispatch work.

        The worker does not call this method. A completed replacement, exact
        durable receipt and original-file coverage are required on every run.
        Index, manifest and cleanup diagnostics remain recoverable in place.
        """
        if not isinstance(job_key, str) or not SHA.fullmatch(job_key) or type(dry_run) is not bool:
            raise ArchiveQueueError("archive_incomplete_cleanup_job_invalid")
        with self.queue.lock():
            job = json.loads(_read(self.queue.items / (job_key + ".json")))
            if (job.get("schemaVersion") != SCHEMA or job.get("key") != job_key
                    or job.get("identity") != self.queue.identity(job["event"])
                    or _sha(_json(job["identity"])) != job_key or job.get("status") != "complete"
                    or "completedAt" not in job or job.get("stagingPruned") is not True
                    or not SHA.fullmatch(str(job.get("receiptSha256", "")))):
                raise ArchiveQueueError("archive_incomplete_cleanup_replacement_not_complete")
            replacement = self._index(job)
            if self._receipt(job, replacement) != job["receiptSha256"]:
                raise ArchiveQueueError("archive_incomplete_cleanup_receipt_changed")
            manifest_path = Path(job.get("retainedManifestPath", ""))
            if manifest_path != Path(job["export"]["indexPath"]).parent / "manifest.json":
                raise ArchiveQueueError("archive_incomplete_cleanup_replacement_manifest_invalid")
            manifest_raw = _read(manifest_path)
            public = next((entry for entry in replacement["generatedPublicFiles"]
                           if entry.get("localPath") == replacement.get("manifestPath")), None)
            manifest = json.loads(manifest_raw)
            if (not public or _sha(manifest_raw) != public["sha256"] or len(manifest_raw) != public["byteSize"]
                    or manifest.get("complete") is not True or manifest.get("missingSources")
                    or manifest.get("archiveId") != replacement["archiveId"]
                    or any(manifest.get("identity", {}).get(k) != replacement.get(k) for k in
                           ("courseId", "courseVersion", "contentKey", "classroomId", "releaseSha256"))):
                raise ArchiveQueueError("archive_incomplete_cleanup_replacement_manifest_changed")
            result = {"dryRun": dry_run, "jobKey": job_key, "eligibleCaptures": 0,
                      "removedBytes": 0, "eligibleBytes": 0, "captures": []}
            for reference in job.get("incompleteExports", []):
                try:
                    plan = self._incomplete_cleanup_plan(job, reference, replacement, manifest)
                    row = {"indexPath": reference["indexPath"], "eligible": True, "bytes": plan["bytes"]}
                    if not dry_run:
                        stage = Path(plan["stage"])
                        if not (stage / "manifest.json").exists():
                            descriptor = os.open(stage / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                            with os.fdopen(descriptor, "wb") as stream:
                                stream.write(plan["manifestRaw"])
                                stream.flush()
                                os.fsync(stream.fileno())
                        stored = {k: v for k, v in plan.items() if k != "manifestRaw"}
                        marker = stage / "incomplete-prune.json"
                        # A previous interrupted plan covers files now absent.
                        if not marker.exists():
                            _write(marker, stored)
                        _sync_directory(stage)
                        for entry in plan["files"]:
                            filename = stage / entry["path"]
                            info = filename.lstat()
                            fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
                            if [getattr(info, k) for k in fields] != entry["identity"]:
                                raise ArchiveQueueError("archive_incomplete_cleanup_file_changed")
                            filename.unlink()
                        for name in sorted(plan["directories"], key=lambda value: len(Path(value).parts), reverse=True):
                            directory = stage / name
                            _directory(directory)
                            directory.rmdir()
                        _sync_directory(stage)
                        reference.update(stagingPruned=True, retainedManifestPath=str(stage / "manifest.json"),
                            pruneReceiptPath=str(marker), prunedAt=self.queue.clock())
                        self.queue.save(job)
                        result["removedBytes"] += plan["bytes"]
                    result["eligibleCaptures"] += 1
                    result["eligibleBytes"] += plan["bytes"]
                    result["captures"].append(row)
                except (ArchiveQueueError, OSError, ValueError, zipfile.BadZipFile) as error:
                    result["captures"].append({"indexPath": reference.get("indexPath"), "eligible": False,
                                                "reason": _safe_error_code(error)})
            return result

    def _acknowledge(self, event):
        if event["origin"] == "postgres":
            self.client.acknowledge(event["eventId"], event["sourceDigest"])
        elif event["origin"] == "filesystem":
            path = Path(event["eventPath"])
            if path.parent != self.queue.root / "archive-events":
                raise ArchiveQueueError("archive_event_outside_outbox")
            if not path.exists():
                return  # A previous acknowledged move is safe to replay.
            raw = _read(path)
            if _sha(raw) != event["eventRawSha256"]:
                raise ArchiveQueueError("archive_event_changed_before_ack")
            processed = _directory(path.parent / "processed")
            target = processed / (path.stem + "-" + _sha(raw) + ".json")
            try:
                os.link(path, target, follow_symlinks=False)
            except FileExistsError:
                pass
            if _read(target) != raw or _read(path) != raw:
                raise ArchiveQueueError("archive_processed_event_conflict")
            path.unlink()
            _sync_directory(processed)
            _sync_directory(path.parent)

    def process(self, job, *, event=None):
        try:
            if "export" not in job:
                self._export(job)
            index = self._index(job)
            if job.get("receiptSha256"):
                self._receipt(job, index)
            else:
                returned = self.client.upload(job["export"]["indexPath"])
                job["receiptSha256"] = self._receipt(job, index, returned)
                job["status"] = "uploaded"
                self.queue.save(job)
            self._acknowledge(event or job["event"])
            job.update(status="complete", completedAt=self.queue.clock(), nextAttemptAt=0, lastError=None)
            self.queue.save(job)
            self._prune_staging(job, index)
            return True
        except Exception as error:
            # Only known, strictly formatted error codes are safe to persist;
            # filesystem/provider messages may contain private source data.
            attempts = job.get("attempts", 0) + 1
            job.update(status="failed", attempts=attempts, lastError=type(error).__name__,
                lastErrorCode=_safe_error_code(error),
                nextAttemptAt=self.queue.clock() + min(3600, 15 * 2 ** min(attempts - 1, 8)))
            self.queue.save(job)
            return False

    def adopt_verified(self, event, index_path):
        """Import an operator's exact verified index; never re-export or upload."""
        job = self.queue.enqueue(event)
        path = Path(index_path).absolute()
        if not path.is_relative_to(self.queue.root / "archives"):
            raise ArchiveQueueError("archive_index_outside_staging")
        raw = _read(path)
        value = json.loads(raw)
        job["export"] = {"indexPath": str(path), "indexSha256": _sha(raw), "archiveId": value["archiveId"]}
        index = self._index(job)
        job["receiptSha256"] = self._receipt(job, index)
        job["status"] = "uploaded"
        self.queue.save(job)
        return self.process(job)

    def relocate_verified(self, job_key, index_path, *, dry_run=True):
        """Bind verified identical remote bytes at a new readable directory.

        An immutable previous index and receipt remain in the layout history.
        This never uploads, deletes, generates or acknowledges an event.
        """
        if not SHA.fullmatch(str(job_key)) or type(dry_run) is not bool:
            raise ArchiveQueueError("archive_layout_job_invalid")
        with self.queue.lock():
            job = json.loads(_read(self.queue.items / (job_key + ".json")))
            if (job.get("schemaVersion") != SCHEMA or job.get("key") != job_key
                    or _sha(_json(job.get("identity"))) != job_key
                    or job.get("status") != "complete" or job.get("stagingPruned") is not True
                    or not job.get("completedAt") or job.get("identity") != self.queue.identity(job["event"])):
                raise ArchiveQueueError("archive_layout_source_not_complete")
            old = self._index(job)
            self._receipt(job, old)
            path = Path(index_path).absolute()
            if (path.parent.parent != self.queue.root / "archives"
                    or not re.fullmatch(re.escape(old["archiveId"]) + r"-[a-f0-9]{8}", path.parent.name)
                    or path.name != "index.json"):
                raise ArchiveQueueError("archive_layout_index_outside_staging")
            raw = _read(path)
            new = json.loads(raw)
            if job["export"]["indexPath"] == str(path) and job["export"]["indexSha256"] == _sha(raw):
                return {"dryRun": dry_run, "jobKey": job_key, "alreadyCurrent": True}

            def content_contract(value):
                result = deepcopy(value)
                for key in ("indexPath", "stagingDirectory", "manifestPath", "objectDirectory"):
                    result.pop(key, None)
                result.get("zip", {}).pop("path", None)
                for entry in result.get("generatedPublicFiles", []):
                    entry.pop("localPath", None)
                    entry["relativePath"] = entry["relativePath"].rsplit("/", 1)[-1]
                return result

            if content_contract(old) != content_contract(new):
                raise ArchiveQueueError("archive_layout_content_changed")
            directory = new.get("objectDirectory", "")
            parts = directory.split("/")
            if (len(parts) != 5 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[3])
                    or any(not p.strip() or p in {".", ".."} or re.search(r"[\\\x00-\x1f\x7f-\x9f]", p)
                           or len(p.encode()) > 255 for p in parts)
                    or any(e["relativePath"].rsplit("/", 1)[0] != directory for e in new["generatedPublicFiles"])
                    or new.get("stagingDirectory") != str(path.parent)
                    or new.get("indexPath") != str(path)
                    or new.get("manifestPath") != str(path.parent / "课程资料/manifest.json")
                    or Path(new.get("zip", {}).get("path", "")).parent != path.parent):
                raise ArchiveQueueError("archive_layout_directory_invalid")
            if Path(job.get("retainedManifestPath", "")) != Path(job["export"]["indexPath"]).parent / "manifest.json":
                raise ArchiveQueueError("archive_layout_source_manifest_invalid")
            old_manifest = _read(Path(job["retainedManifestPath"]))
            if _read(path.parent / "manifest.json") != old_manifest:
                raise ArchiveQueueError("archive_layout_manifest_changed")
            candidate = deepcopy(job)
            history = {key: job[key] for key in
                ("export", "receiptPath", "receiptSha256", "retainedManifestPath", "completedAt")}
            candidate.setdefault("archiveLayoutHistory", []).append(history)
            candidate["export"] = {"indexPath": str(path), "indexSha256": _sha(raw), "archiveId": new["archiveId"]}
            candidate.pop("receiptPath", None)
            candidate.pop("receiptSha256", None)
            self._index(candidate)
            candidate["receiptSha256"] = self._receipt(candidate, new)
            candidate["retainedManifestPath"] = str(path.parent / "manifest.json")
            candidate["layoutChangedAt"] = self.queue.clock()
            if not dry_run:
                self.queue.save(candidate)
            return {"dryRun": dry_run, "jobKey": job_key, "fromDirectory": old["objectDirectory"],
                    "toDirectory": directory, "verifiedFiles": len(new["generatedPublicFiles"])}


class CourseArchiveWorker:
    def __init__(self, queue, processor, *, database=None, scan_catalog=True, scan_history=True):
        self.queue, self.processor, self.database = queue, processor, database
        self.scan_catalog = scan_catalog
        self.scan_history = scan_history

    def seed_native_snapshot(self, snapshot, *, source_kind, source_digest, created_at,
                             revision="0", source_raw=None):
        if source_kind not in {"native_pg_stage", "legacy_classroom", "native_legacy_file"}:
            raise ArchiveQueueError("archive_source_kind_invalid")
        stage_id = snapshot.get("stage", {}).get("id")
        event = _native_event("native_pg_stage" if source_kind == "native_pg_stage" else "legacy_classroom",
            source_digest, stage_id, snapshot, created_at, origin="reconcile", priority=2, revision=str(revision))
        event["sourceKind"] = source_kind
        if source_raw is not None:
            if _sha(source_raw.encode()) != source_digest or json.loads(source_raw) != snapshot:
                raise ArchiveQueueError("archive_seed_digest_mismatch")
            event["sourceRaw"] = source_raw
        return self.queue.enqueue(event)

    def _reconcile_legacy(self, *, limit=100):
        native = getattr(self.processor.exporter, "native_root", None)
        if native is None:
            return 0
        directory = Path(native) / "data/classrooms"
        if not directory.exists():
            return 0
        _directory(directory)
        cache_path = self.queue.directory / "legacy-cursor.json"
        cache = json.loads(_read(cache_path)) if cache_path.exists() else {"after": "", "files": {}}
        candidates = []
        for path in directory.iterdir():
            if path.suffix == ".json" and ID.fullmatch(path.stem):
                candidates.append((path.name, path, path.stem))
            elif path.name.startswith("omclass_") and ID.fullmatch(path.name) and not path.is_symlink():
                artifact = path / "artifact/classroom.json"
                if artifact.exists():
                    candidates.append((path.name + "/artifact/classroom.json", artifact, path.name))
        selected = [row for row in sorted(candidates) if row[0] > cache.get("after", "")][:limit]
        discovered = 0
        for name, path, stage_id in selected:
            info = path.lstat()
            fingerprint = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                           _sha(_json(self.queue.storage))]
            revision = []
            for folder in (directory / stage_id, directory / stage_id / "audio", directory / stage_id / "media"):
                try:
                    entry = folder.lstat()
                    revision.append([entry.st_ino, entry.st_size, entry.st_mtime_ns, entry.st_ctime_ns])
                except FileNotFoundError:
                    revision.append(None)
            fingerprint.append(revision)
            if cache["files"].get(name) == fingerprint:
                continue
            raw = _read(path)
            snapshot = json.loads(raw)
            if not isinstance(snapshot, dict) or not isinstance(snapshot.get("stage"), dict) or not snapshot.get("scenes"):
                # An empty saved shell is not a completed course.
                cache["files"][name] = fingerprint
                continue
            event = _native_event("legacy_classroom", _sha(raw), stage_id, snapshot,
                datetime.fromtimestamp(info.st_mtime, timezone.utc).isoformat(),
                origin="legacy-reconcile", sourceRaw=raw.decode(), legacyPath=str(path), priority=2,
                archiveSourceRevision=_sha(_json(revision)))
            event["sourceKind"] = "native_legacy_file"
            self.queue.enqueue(event)
            cache["files"][name] = fingerprint
            discovered += 1
        cache["after"] = selected[-1][0] if selected else ""
        _write(cache_path, cache)
        return discovered

    def _reconcile_postgres(self):
        if not hasattr(self.processor.client, "saved_stages"):
            return 0
        path = self.queue.directory / "stages-cursor.json"
        cursor = json.loads(_read(path)).get("after", "") if path.exists() else ""
        rows = self.processor.client.saved_stages(after_stage_id=cursor, limit=100)
        for row in rows:
            self.seed_native_snapshot(row["snapshot_json"], source_kind="native_pg_stage",
                source_digest=row["source_digest"], revision=row["stage_revision"], created_at=row["created_at"])
        _write(path, {"after": rows[-1]["stage_id"] if rows else ""})
        return len(rows)

    def run_once(self, *, limit=10, stop_requested=lambda: False):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ArchiveQueueError("archive_limit_invalid")
        summary = {"discovered": 0, "completed": 0, "failed": 0, "discoveryErrors": 0}
        deliveries = {}
        events_root = _directory(self.queue.root / "archive-events")
        for path in sorted(events_root.glob("*.json")):
            try:
                event = filesystem_event(path)
                job = self.queue.enqueue(event)
                deliveries.setdefault(job["key"], []).append(event)
                summary["discovered"] += 1
            except Exception:
                summary["discoveryErrors"] += 1
        cursor_path = self.queue.directory / "postgres-cursor.json"
        cursor = json.loads(_read(cursor_path)).get("afterId", 0) if cursor_path.exists() else 0
        try:
            rows = self.processor.client.events(after_id=cursor, limit=100)
            for row in rows:
                try:
                    event = postgres_event(row)
                    job = self.queue.enqueue(event)
                    deliveries.setdefault(job["key"], []).append(event)
                    summary["discovered"] += 1
                except Exception:
                    summary["discoveryErrors"] += 1
            _write(cursor_path, {"afterId": int(rows[-1]["id"]) if rows else 0})
        except Exception:
            summary["discoveryErrors"] += 1
        if self.scan_catalog and self.database is not None:
            try:
                from scripts.course_storage_releases import read_only_connection
                with read_only_connection(self.database) as conn:
                    courses = self.processor.exporter.list_courses(conn, include_saved=True)
                for course in courses:
                    try:
                        digest = course.get("sourceDigest") or course.get("releaseSha256")
                        if not isinstance(digest, str) or not SHA.fullmatch(digest):
                            raise ArchiveQueueError("archive_catalog_digest_missing")
                        event = {"origin": "catalog", "sourceKind": course["sourceKind"],
                            "sourceDigest": digest, "course": course,
                            "createdAt": datetime.now(timezone.utc).isoformat(), "priority": 1}
                        self.queue.enqueue(event)
                        summary["discovered"] += 1
                    except Exception:
                        summary["discoveryErrors"] += 1
            except Exception:
                summary["discoveryErrors"] += 1
        if self.scan_history:
            for reconcile in (self._reconcile_legacy, self._reconcile_postgres):
                try:
                    summary["discovered"] += reconcile()
                except Exception:
                    summary["discoveryErrors"] += 1
        ready = self.queue.due(limit, max_priority=None if self.scan_history else 1)
        # Completed content can have another producer event. Acknowledge it
        # against its durable verification without exporting/uploading again.
        for key, events in deliveries.items():
            if len(ready) >= limit:
                break
            job = json.loads(_read(self.queue.items / (key + ".json")))
            if job["status"] == "complete":
                ready.append(job)
        for job in ready:
            if stop_requested():
                break
            if self.processor.process(job):
                summary["completed"] += 1
                for event in deliveries.get(job["key"], []):
                    if event != job["event"]:
                        if not self.processor.process(job, event=event):
                            summary["failed"] += 1
            else:
                summary["failed"] += 1
        return summary
