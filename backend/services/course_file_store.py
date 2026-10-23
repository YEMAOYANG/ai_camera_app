"""Versioned course originals in object storage; MySQL stores only locators.

Registered paths always read remote bytes, even when a local original exists.
Unregistered files belong to a new authoring workspace and may still be local.
ZIP originals reuse verified complete-course archives with conditional Range
reads: a small JSON never requires downloading a multi-gigabyte archive.
"""
from __future__ import annotations

from collections import OrderedDict
from contextvars import ContextVar
from fnmatch import fnmatchcase
import hashlib
from http.client import HTTPException
import io
import os
from pathlib import Path
import re
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import zipfile

from core.course_storage_config import CourseStorageConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Existing reviewed, image-embedded publication originals reach 412 MB.
# The Native HTTP adapter independently caps its smaller JSON/media requests.
MAX_FILE_BYTES = 512 * 1024 * 1024
_BLOCK_BYTES = 64 * 1024
_CACHE_BYTES = 64 * 1024 * 1024
_BLOCKS: OrderedDict[tuple, bytes] = OrderedDict()
_BLOCK_LOCK = threading.Lock()
_SLOTS = threading.BoundedSemaphore(4)
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_SOURCE_ROOTS = ("output/", "backend/data/learning-media/", "backend/content/textbooks/",
                 "openmaic-runtime/.runtime/OpenMAIC/data/", "openmaic-runtime/native-assets/review-assets/")
# Never obtain the compare-and-swap version at write time. Each execution
# context remembers only versions whose complete bytes it actually verified.
_READ_VERSIONS = ContextVar("course_file_read_versions", default=None)


def _version_key(store, source):
    from repositories.course_storage_repository import storage_id_for
    return (storage_id_for(store.config.endpoint, store.config.bucket, store.config.region),
            os.path.abspath(source))


def _remember_version(store, source, checksum):
    versions = dict(_READ_VERSIONS.get() or {})
    key = _version_key(store, source)
    versions.pop(key, None)
    versions[key] = checksum
    while len(versions) > 4096:
        versions.pop(next(iter(versions)))
    _READ_VERSIONS.set(versions)


def reset_course_read_versions():
    """A new API operation must prove its own input version."""
    _READ_VERSIONS.set(None)


class CourseFileStorageError(ValueError):
    """Public diagnostics never include file contents, endpoints or credentials."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CourseFileStorageError("Course file redirect is not allowed")


def _etag(value):
    if not isinstance(value, str) or not re.fullmatch(r'"?[a-fA-F0-9]{32}(?:-\d+)?"?', value):
        raise CourseFileStorageError("Course file object identity invalid")
    return value.strip('"')


def _key(value):
    if (not isinstance(value, str) or not value or len(value.encode()) > 1024
            or "\\" in value or re.search(r"[\x00-\x1f\x7f]", value)
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise CourseFileStorageError("Course file locator invalid")
    return value


class _RemoteObject:
    def __init__(self, config, locator, size):
        key = _key(locator.get("objectKey"))
        self.etag = _etag(locator.get("etag"))
        if type(size) is not int or size < 0:
            raise CourseFileStorageError("Course file object size invalid")
        self.size = size
        self.url = (config.endpoint.rstrip("/") + "/" + quote(config.bucket, safe="")
                    + "/" + "/".join(quote(p, safe="") for p in key.split("/")))
        version = locator.get("versionId")
        if version:
            if not isinstance(version, str) or len(version) > 1024 or re.search(r"[\x00-\x1f]", version):
                raise CourseFileStorageError("Course file version invalid")
            self.url += "?" + urlencode({"versionId": version})
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())
        self.deadline = time.monotonic() + 60

    def get(self, start=0, end=None, *, whole=False):
        end = self.size if end is None else end
        if not 0 <= start <= end <= self.size or time.monotonic() > self.deadline:
            raise CourseFileStorageError("Course file read limit exceeded")
        headers = {"If-Match": '"' + self.etag + '"', "Accept-Encoding": "identity"}
        if not whole:
            headers["Range"] = f"bytes={start}-{end - 1}"
        with self.opener.open(Request(self.url, headers=headers), timeout=10) as response:
            if (response.status != (200 if whole else 206)
                    or _etag(response.headers.get("ETag")) != self.etag
                    or int(response.headers.get("Content-Length", -1)) != end - start
                    or response.headers.get("Content-Encoding", "identity") != "identity"
                    or (not whole and response.headers.get("Content-Range") != f"bytes {start}-{end-1}/{self.size}")):
                raise CourseFileStorageError("Course file object changed")
            chunks, count = [], 0
            while count < end - start:
                chunk = response.read(min(1024 * 1024, end - start - count))
                if not chunk or time.monotonic() > self.deadline:
                    raise CourseFileStorageError("Course file object truncated")
                chunks.append(chunk)
                count += len(chunk)
            if response.read(1):
                raise CourseFileStorageError("Course file object size mismatch")
            return b"".join(chunks)


class _RangeFile(io.RawIOBase):
    def __init__(self, remote):
        self.remote, self.position = remote, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        target = offset + (self.position if whence == 1 else self.remote.size if whence == 2 else 0)
        if whence not in (0, 1, 2) or target < 0:
            raise ValueError("Invalid course archive seek")
        self.position = target
        return target

    def read(self, size=-1):
        end = self.remote.size if size < 0 else min(self.remote.size, self.position + size)
        if end - self.position > MAX_FILE_BYTES:
            raise CourseFileStorageError("Course archive read too large")
        result = []
        while self.position < end:
            block = self.position // _BLOCK_BYTES
            cache_key = (self.remote.url, self.remote.etag, self.remote.size, block)
            with _BLOCK_LOCK:
                raw = _BLOCKS.get(cache_key)
                if raw is not None:
                    _BLOCKS.move_to_end(cache_key)
            if raw is None:
                begin = block * _BLOCK_BYTES
                # Coalesce central-directory/large-member reads into one request.
                stop = min(self.remote.size, max(begin + _BLOCK_BYTES,
                    min(((end + _BLOCK_BYTES - 1) // _BLOCK_BYTES) * _BLOCK_BYTES, begin + 4 * 1024 * 1024)))
                fetched = self.remote.get(begin, stop)
                with _BLOCK_LOCK:
                    for offset in range(0, len(fetched), _BLOCK_BYTES):
                        _BLOCKS[(self.remote.url, self.remote.etag, self.remote.size,
                                 block + offset // _BLOCK_BYTES)] = fetched[offset:offset + _BLOCK_BYTES]
                    while len(_BLOCKS) > _CACHE_BYTES // _BLOCK_BYTES:
                        _BLOCKS.popitem(last=False)
                raw = fetched[:_BLOCK_BYTES]
            offset = self.position % _BLOCK_BYTES
            chunk = raw[offset:min(len(raw), offset + end - self.position)]
            if not chunk:
                raise CourseFileStorageError("Course archive truncated")
            result.append(chunk)
            self.position += len(chunk)
        return b"".join(result)


class CourseFileStore:
    def __init__(self, *, config=None, project_root=None, repository=None):
        self.config = config or CourseStorageConfig.from_env()
        self.input_root = Path(project_root or PROJECT_ROOT).absolute()
        self.project_root = (project_root or PROJECT_ROOT).resolve()
        self._repository = repository

    @property
    def repository(self):
        if self._repository is None:
            from core.config import AppConfig
            from core.database import Database
            from repositories.course_storage_repository import CourseStorageRepository
            self._repository = CourseStorageRepository(Database(AppConfig.from_env().DATABASE_URL))
        return self._repository

    def resolve(self, source, *, expected_sha256=None):
        if self.config.mode != "registry":
            return None
        # A local symlink must never rename an already registered source into
        # an unregistered path and thereby enable a local fallback.
        path = Path(os.path.abspath(source))
        try:
            relative = path.relative_to(self.project_root).as_posix()
        except ValueError:
            try:
                relative = path.relative_to(self.input_root).as_posix()
            except ValueError:
                return None
        if not relative.startswith(_SOURCE_ROOTS):
            return None
        from repositories.course_storage_repository import storage_id_for
        storage = storage_id_for(self.config.endpoint, self.config.bucket, self.config.region)
        entry = self.repository.resolve(relative, storage_id=storage, expected_sha=expected_sha256)
        if entry is None and expected_sha256 is not None:
            # A registered path with a different version must never fall back.
            if self.repository.resolve(relative, storage_id=storage) is not None:
                raise CourseFileStorageError("Course file version is not registered")
        return entry

    def read_bytes(self, source, *, expected_sha256=None, expected_bytes=None, max_bytes=MAX_FILE_BYTES):
        try:
            entry = self.resolve(source, expected_sha256=expected_sha256)
            if entry is None:
                return None
            size, checksum = entry["byteSize"], entry["sha256"]
            if (type(size) is not int or not 0 <= size <= min(max_bytes, MAX_FILE_BYTES)
                    or not _SHA.fullmatch(str(checksum))
                    or (expected_sha256 is not None and expected_sha256 != checksum)
                    or (expected_bytes is not None and expected_bytes != size)):
                raise CourseFileStorageError("Course file integrity invalid")
            locator = entry["locator"]
            if not _SLOTS.acquire(timeout=10):
                raise CourseFileStorageError("Course file storage busy")
            try:
                if locator.get("kind") == "object":
                    raw = _RemoteObject(self.config, locator, size).get(whole=True)
                elif locator.get("kind") == "zip_member":
                    if not _SHA.fullmatch(str(locator.get("archiveSha256"))):
                        raise CourseFileStorageError("Course archive identity invalid")
                    remote = _RemoteObject(self.config, locator, locator.get("archiveByteSize"))
                    with zipfile.ZipFile(_RangeFile(remote)) as archive:
                        member = archive.getinfo(_key(locator.get("memberPath")))
                        if member.file_size != size or member.is_dir() or member.flag_bits & 1:
                            raise CourseFileStorageError("Course archive member invalid")
                        with archive.open(member) as stream:
                            raw = stream.read(size + 1)
                else:
                    raise CourseFileStorageError("Course file locator invalid")
            finally:
                _SLOTS.release()
            if len(raw) != size or hashlib.sha256(raw).hexdigest() != checksum:
                raise CourseFileStorageError("Course file integrity failed")
            _remember_version(self, source, checksum)
            return raw
        except CourseFileStorageError:
            raise
        except (HTTPError, URLError, HTTPException, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile):
            raise CourseFileStorageError("Course file storage unavailable") from None


def course_bytes(path, *, expected_sha256=None, max_bytes=MAX_FILE_BYTES):
    """Read remote originals first; local is only for unregistered new work."""
    path = Path(path)
    raw = CourseFileStore().read_bytes(path, expected_sha256=expected_sha256, max_bytes=max_bytes)
    if raw is None:
        raw = path.read_bytes()
        if len(raw) > max_bytes or (expected_sha256 and hashlib.sha256(raw).hexdigest() != expected_sha256):
            raise CourseFileStorageError("Course file integrity failed")
    return raw


def course_text(path):
    return course_bytes(path).decode("utf-8")


def course_write_bytes(path, raw, *, expected_sha256=None):
    """Update a registered working file remotely, or return False for new work.

    Callers retain their existing local atomic creation for an unregistered
    path. Registered writes never create a shadow file, and a missing read
    version cannot silently become a blind overwrite.
    """
    store = CourseFileStore()
    entry = store.resolve(path)
    if entry is None:
        return False
    expected = expected_sha256 or (_READ_VERSIONS.get() or {}).get(_version_key(store, path))
    if not _SHA.fullmatch(str(expected)):
        raise CourseFileStorageError("Course file must be read before it is updated")
    from services.course_file_writer import CourseFileWriter
    CourseFileWriter(config=store.config, repository=store.repository).write_bytes(
        path, raw, expected_sha256=expected)
    _remember_version(store, path, hashlib.sha256(raw).hexdigest())
    return True


def course_exists(path):
    return CourseFileStore().resolve(path) is not None or Path(path).is_file()


def course_glob(directory, pattern="*", *, recursive=False):
    """Discover original evidence from DB paths plus a new local workspace."""
    directory = Path(directory)
    found = set(directory.rglob(pattern) if recursive else directory.glob(pattern))
    store = CourseFileStore()
    if store.config.mode == "registry":
        try:
            prefix = directory.resolve().relative_to(store.project_root).as_posix()
        except ValueError:
            return iter(sorted(found))
        if any((prefix + "/").startswith(root) or root.startswith(prefix + "/") for root in _SOURCE_ROOTS):
            from repositories.course_storage_repository import storage_id_for
            storage = storage_id_for(store.config.endpoint, store.config.bucket, store.config.region)
            patterns = tuple(pattern.split("/"))
            if recursive:
                patterns = ("**", *patterns)

            def matches(parts, tokens):
                if not tokens:
                    return not parts
                if tokens[0] == "**":
                    return matches(parts, tokens[1:]) or bool(parts) and matches(parts[1:], tokens)
                return bool(parts) and fnmatchcase(parts[0], tokens[0]) and matches(parts[1:], tokens[1:])

            for source in store.repository.paths_under(prefix, storage):
                relative = Path(source).relative_to(prefix)
                candidates = [relative, *relative.parents]
                for candidate in candidates:
                    if candidate != Path(".") and matches(candidate.parts, patterns):
                        found.add(directory / candidate)
    return iter(sorted(found))


def course_is_dir(path):
    return Path(path).is_dir() or next(course_glob(path), None) is not None


def course_stat(path):
    entry = CourseFileStore().resolve(path)
    if entry is None:
        return Path(path).stat()
    # Immutable remote identity for existing source-stability checks. A new
    # activated version changes the inode token even without a local file.
    return SimpleNamespace(st_size=entry["byteSize"], st_dev=0,
        st_ino=int(entry["sha256"][:16], 16), st_mtime_ns=0, st_ctime_ns=0)
