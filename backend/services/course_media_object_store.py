"""Read exact, already-authorized migrated media from the public course bucket.

This byte adapter grants no student or course access. Callers must authorize
their DB/session binding before consulting it. Unlisted paths remain local;
listed paths use verified immutable media bytes and can never fall back to disk.
"""
from __future__ import annotations

import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from core.course_storage_config import CourseStorageConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAX_MANIFEST_BYTES = 64 * 1024 * 1024
_MAX_MEDIA_BYTES = 32 * 1024 * 1024
_READ_SLOTS = threading.BoundedSemaphore(4)
_MANIFEST_LOCK = threading.Lock()
_MANIFEST_CACHE: tuple[tuple, dict[str, dict]] | None = None


# v2 uses readable names only for public audio/image/video objects. v1 hash
# objects keep their original key validation semantics.
_NAMED_MEDIA_MIME = {
    ".wav": {"audio/wav"}, ".mp3": {"audio/mpeg"}, ".ogg": {"audio/ogg"},
    ".aac": {"audio/aac"}, ".flac": {"audio/flac"}, ".webm": {"audio/webm", "video/webm"},
    ".mp4": {"video/mp4"}, ".png": {"image/png"}, ".webp": {"image/webp"},
    ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"}, ".gif": {"image/gif"},
}


def _valid_object_key(entry: dict, prefix: str, schema: str, key_layout=None) -> bool:
    if schema == "mira.course-storage.manifest.v1":
        return entry.get("objectKey") == f"{prefix}/blobs/sha256/{entry['sha256']}"
    key = entry.get("objectKey")
    subject_layout = key_layout == "subject-edition-grade-date-course-v1"
    if key_layout and not subject_layout:
        return False
    if not isinstance(key, str) or (not subject_layout and not key.startswith(prefix + "/")):
        return False
    parts = key.split("/") if subject_layout else key[len(prefix) + 1:].split("/")
    if subject_layout and (not re.fullmatch(r"\d{4}-\d{2}-\d{2}", prefix) or len(parts) < 4 or parts[3] != prefix):
        return False
    if len(parts) != (6 if subject_layout else 3) or any(
        not part.strip() or part in {".", ".."} or "\\" in part
        or re.search(r"[\x00-\x1f\x7f-\x9f]", part) or len(part.encode("utf8")) > 255
        for part in parts
    ):
        return False
    return entry.get("mimeType") in _NAMED_MEDIA_MIME.get(Path(parts[-1]).suffix.lower(), set())


class CourseMediaStorageError(ValueError):
    """Sanitized errors only: endpoint/credentials never enter API diagnostics."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CourseMediaStorageError("Course media redirect is not allowed")


class CourseMediaObjectStore:
    def __init__(self, *, config: CourseStorageConfig | None = None, project_root: Path | None = None):
        self.config = config
        self.project_root = (project_root or PROJECT_ROOT).resolve()

    def read(
        self, source: Path, *, expected_sha256: str | None = None,
        expected_bytes: int | None = None, max_bytes: int = _MAX_MEDIA_BYTES,
    ) -> bytes | None:
        """None means unlisted/local; every migrated failure raises instead."""
        try:
            config = self.config or CourseStorageConfig.from_env()
            if config.mode == "local":
                return None
            try:
                relative = source.resolve().relative_to(self.project_root).as_posix()
            except ValueError:
                # External/test storage roots have no entry in the project index.
                if config.mode == "remote":
                    raise CourseMediaStorageError("Course media is not migrated") from None
                return None
            entry = self._manifest(config).get(relative)
            if entry is None:
                if config.mode == "remote":
                    raise CourseMediaStorageError("Course media is not migrated")
                return None
            limit = min(max_bytes, _MAX_MEDIA_BYTES)
            if (
                not 0 <= entry["byteSize"] <= limit
                or (expected_sha256 is not None and entry["sha256"] != expected_sha256)
                or (expected_bytes is not None and entry["byteSize"] != expected_bytes)
            ):
                raise CourseMediaStorageError("Course media manifest integrity failed")
            return self._download(config, entry, limit)
        except CourseMediaStorageError:
            raise
        except (OSError, ValueError, KeyError, TypeError):
            raise CourseMediaStorageError("Course media storage unavailable") from None

    @staticmethod
    def _manifest(config: CourseStorageConfig) -> dict[str, dict]:
        global _MANIFEST_CACHE
        source = Path(config.manifest_path)
        stat = source.stat()
        if not source.is_file() or stat.st_size > _MAX_MANIFEST_BYTES:
            raise CourseMediaStorageError("Course media manifest unavailable")
        identity = (str(source), config.prefix, stat.st_dev, stat.st_ino,
                    stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        with _MANIFEST_LOCK:
            if _MANIFEST_CACHE is not None and _MANIFEST_CACHE[0] == identity:
                return _MANIFEST_CACHE[1]
            with source.open("rb") as handle:
                raw = handle.read(_MAX_MANIFEST_BYTES + 1)
            if len(raw) > _MAX_MANIFEST_BYTES:
                raise CourseMediaStorageError("Course media manifest unavailable")
            manifest = json.loads(raw)
            if (
                not isinstance(manifest, dict)
                or manifest.get("schemaVersion") not in {"mira.course-storage.manifest.v1", "mira.course-storage.manifest.v2"}
                or not isinstance(manifest.get("snapshotId"), str)
                or not manifest["snapshotId"].strip()
                or not isinstance(manifest.get("files"), list)
            ):
                raise CourseMediaStorageError("Course media manifest invalid")
            files = {}
            for entry in manifest["files"]:
                relative = entry.get("path") if isinstance(entry, dict) else None
                if (
                    not isinstance(relative, str) or not relative
                    or "\\" in relative or re.search(r"[\x00-\x1f]", relative)
                    or any(part in {"", ".", ".."} for part in relative.split("/"))
                    or not isinstance(entry.get("sha256"), str)
                    or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"])
                    or not _valid_object_key(entry, config.prefix, manifest["schemaVersion"], manifest.get("keyLayout"))
                    or type(entry.get("byteSize")) is not int or entry["byteSize"] < 0
                    or not isinstance(entry.get("mimeType"), str)
                    or not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", entry["mimeType"])
                    or relative in files
                ):
                    raise CourseMediaStorageError("Course media manifest invalid")
                files[relative] = entry
            _MANIFEST_CACHE = (identity, files)
            return files

    @staticmethod
    def _download(config: CourseStorageConfig, entry: dict, limit: int) -> bytes:
        encoded_key = "/".join(quote(segment, safe="") for segment in entry["objectKey"].split("/"))
        url = f"{config.endpoint.rstrip('/')}/{quote(config.bucket, safe='')}/{encoded_key}"
        # Public read is intentional. No credentials, cookies, generic proxy
        # configuration or redirects may participate in byte delivery.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        if not _READ_SLOTS.acquire(timeout=10):
            raise CourseMediaStorageError("Course media storage busy")
        try:
            with opener.open(Request(url, method="GET"), timeout=10) as response:
                if response.status != 200:
                    raise CourseMediaStorageError("Course media storage unavailable")
                declared = response.headers.get("Content-Length")
                if declared is not None and int(declared) != entry["byteSize"]:
                    raise CourseMediaStorageError("Course media size mismatch")
                chunks, total, checksum = [], 0, hashlib.sha256()
                deadline = time.monotonic() + 30
                while True:
                    chunk = response.read(min(64 * 1024, limit - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit or total > entry["byteSize"] or time.monotonic() > deadline:
                        raise CourseMediaStorageError("Course media size or time limit exceeded")
                    checksum.update(chunk)
                    chunks.append(chunk)
                if total != entry["byteSize"] or checksum.hexdigest() != entry["sha256"]:
                    raise CourseMediaStorageError("Course media integrity failed")
                return b"".join(chunks)
        except (HTTPError, URLError, HTTPException, OSError, ValueError):
            raise CourseMediaStorageError("Course media storage unavailable") from None
        finally:
            _READ_SLOTS.release()
