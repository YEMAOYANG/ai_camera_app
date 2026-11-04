"""Verified reads of immutable courseware UI assets from object storage.

The checked-in manifest is the only public-path allowlist.  A listed asset is
always read from MinIO and verified; there is deliberately no filesystem
fallback, even when the old recovery copy is still present under Student Web.
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
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from core.course_storage_config import CourseStorageConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "backend/content/courseware-assets.v1.json"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_ASSET_BYTES = 32 * 1024 * 1024
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_ETAG = re.compile(r'"?[A-Fa-f0-9]{32}(?:-\d+)?"?\Z')
_MIME_TYPES = {
    "application/json",
    "audio/aac", "audio/flac", "audio/mpeg", "audio/ogg", "audio/wav", "audio/webm",
    "image/gif", "image/jpeg", "image/png", "image/webp",
    "model/gltf-binary", "video/mp4", "video/webm",
}
_CACHE_LOCK = threading.Lock()
_MANIFEST_CACHE: tuple[tuple, dict[str, dict]] | None = None
_READ_SLOTS = threading.BoundedSemaphore(6)


class CoursewareAssetNotFound(ValueError):
    pass


class CoursewareAssetStorageError(ValueError):
    """Sanitized diagnostics; storage endpoints and credentials never escape."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CoursewareAssetStorageError("Courseware asset redirect is not allowed")


def _safe_relative(value: object) -> str:
    if (not isinstance(value, str) or not value or value.startswith("/") or "\\" in value
            or re.search(r"[\x00-\x1f\x7f]", value)
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or len(value.encode("utf-8")) > 1024):
        raise CoursewareAssetStorageError("Courseware asset path is invalid")
    return value


def _safe_object_key(value: object) -> str:
    value = _safe_relative(value)
    if any(len(part.encode("utf-8")) > 255 for part in value.split("/")):
        raise CoursewareAssetStorageError("Courseware asset locator is invalid")
    return value


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise CoursewareAssetStorageError("Courseware asset storage is invalid")
    try:
        parsed.port
    except ValueError:
        raise CoursewareAssetStorageError("Courseware asset storage is invalid") from None
    return f"{parsed.scheme}://{parsed.netloc}"


class CoursewareAssetStore:
    def __init__(self, *, config: CourseStorageConfig | None = None,
                 manifest_path: Path | None = None, opener=None):
        self.config = config
        self.manifest_path = Path(manifest_path or DEFAULT_MANIFEST)
        self.opener = opener or build_opener(ProxyHandler({}), _NoRedirect())

    def read_public(self, asset_path: str) -> tuple[dict, bytes]:
        try:
            public_path = "/" + _safe_relative(asset_path)
            entry = self._manifest().get(public_path)
            if entry is None:
                raise CoursewareAssetNotFound("Courseware asset is not listed")
            config = self.config or CourseStorageConfig.from_env()
            self._match_storage(config, entry["storage"])
            return entry, self._download(config, entry)
        except (CoursewareAssetNotFound, CoursewareAssetStorageError):
            raise
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise CoursewareAssetStorageError("Courseware asset storage is unavailable") from None

    def _manifest(self) -> dict[str, dict]:
        global _MANIFEST_CACHE
        stat = self.manifest_path.stat()
        if not self.manifest_path.is_file() or stat.st_size <= 0 or stat.st_size > MAX_MANIFEST_BYTES:
            raise CoursewareAssetStorageError("Courseware asset manifest is unavailable")
        identity = (str(self.manifest_path.resolve()), stat.st_dev, stat.st_ino,
                    stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        with _CACHE_LOCK:
            if _MANIFEST_CACHE is not None and _MANIFEST_CACHE[0] == identity:
                return _MANIFEST_CACHE[1]
            raw = self.manifest_path.read_bytes()
            if len(raw) > MAX_MANIFEST_BYTES:
                raise CoursewareAssetStorageError("Courseware asset manifest is unavailable")
            manifest = json.loads(raw)
            if not isinstance(manifest, dict):
                raise CoursewareAssetStorageError("Courseware asset manifest is invalid")
            storage = manifest.get("storage")
            if (manifest.get("schemaVersion") != "mira.courseware-assets.v1"
                    or not isinstance(manifest.get("snapshotId"), str) or not manifest["snapshotId"]
                    or not isinstance(storage, dict) or set(storage) != {"endpoint", "bucket", "region"}
                    or not isinstance(manifest.get("files"), list)):
                raise CoursewareAssetStorageError("Courseware asset manifest is invalid")
            normalized_storage = {
                "endpoint": _origin(storage["endpoint"]),
                "bucket": storage["bucket"], "region": storage["region"],
            }
            if (not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", str(storage["bucket"]))
                    or ".." in storage["bucket"]
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", str(storage["region"]))):
                raise CoursewareAssetStorageError("Courseware asset manifest is invalid")
            public: dict[str, dict] = {}
            sources: set[str] = set()
            keys: set[str] = set()
            for item in manifest["files"]:
                if not isinstance(item, dict):
                    raise CoursewareAssetStorageError("Courseware asset manifest is invalid")
                source = _safe_relative(item.get("sourcePath"))
                key = _safe_object_key(item.get("objectKey"))
                checksum = item.get("sha256")
                size = item.get("byteSize")
                mime = item.get("mimeType")
                etag = item.get("etag")
                version = item.get("versionId")
                path = item.get("publicPath")
                if (source in sources or key in keys or not _SHA256.fullmatch(str(checksum))
                        or type(size) is not int or not 0 < size <= MAX_ASSET_BYTES
                        or mime not in _MIME_TYPES or not isinstance(etag, str) or not _ETAG.fullmatch(etag)
                        or (version is not None and (not isinstance(version, str) or not version
                            or len(version) > 1024 or re.search(r"[\x00-\x1f]", version)))):
                    raise CoursewareAssetStorageError("Courseware asset manifest is invalid")
                sources.add(source)
                keys.add(key)
                if path is None:
                    continue
                if (not isinstance(path, str) or not path.startswith("/")
                        or "/" + _safe_relative(path[1:]) != path or path in public
                        or source != "student-web/public" + path):
                    raise CoursewareAssetStorageError("Courseware public asset manifest is invalid")
                public[path] = {**item, "storage": normalized_storage}
            _MANIFEST_CACHE = (identity, public)
            return public

    @staticmethod
    def _match_storage(config: CourseStorageConfig, storage: dict) -> None:
        if ({"endpoint": _origin(config.endpoint), "bucket": config.bucket, "region": config.region} != storage):
            raise CoursewareAssetStorageError("Courseware asset storage identity changed")

    def _download(self, config: CourseStorageConfig, entry: dict) -> bytes:
        key = "/".join(quote(part, safe="") for part in entry["objectKey"].split("/"))
        url = f"{config.endpoint.rstrip('/')}/{quote(config.bucket, safe='')}/{key}"
        if entry.get("versionId"):
            url += "?" + urlencode({"versionId": entry["versionId"]})
        if not _READ_SLOTS.acquire(timeout=10):
            raise CoursewareAssetStorageError("Courseware asset storage is busy")
        try:
            request = Request(url, headers={"If-Match": entry["etag"], "Accept-Encoding": "identity"})
            with self.opener.open(request, timeout=10) as response:
                if (response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity"
                        or int(response.headers.get("Content-Length", -1)) != entry["byteSize"]
                        or response.headers.get("ETag", "").strip('"') != entry["etag"].strip('"')):
                    raise CoursewareAssetStorageError("Courseware asset object changed")
                chunks, total, digest = [], 0, hashlib.sha256()
                deadline = time.monotonic() + 30
                while total < entry["byteSize"]:
                    chunk = response.read(min(64 * 1024, entry["byteSize"] - total))
                    if not chunk or time.monotonic() > deadline:
                        raise CoursewareAssetStorageError("Courseware asset object is incomplete")
                    total += len(chunk)
                    digest.update(chunk)
                    chunks.append(chunk)
                if response.read(1) or digest.hexdigest() != entry["sha256"]:
                    raise CoursewareAssetStorageError("Courseware asset integrity failed")
                return b"".join(chunks)
        except CoursewareAssetStorageError:
            raise
        except (HTTPError, URLError, HTTPException, OSError, ValueError):
            raise CoursewareAssetStorageError("Courseware asset storage is unavailable") from None
        finally:
            _READ_SLOTS.release()
