#!/usr/bin/env python3
"""Preserve course sources in a standard, content-deduplicated ZIP64 backup.

The ZIP contains this standalone program as restore.py. Verification and recovery
need only Python 3.9+ and the ZIP plus its existing-archives sidecar directory.
No command removes, relocates, or changes a source file.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import zipfile
import zlib
from dataclasses import dataclass


SCHEMA = "mira.courseware-backup.v1"
ARCHIVE_NAME = "courseware-sources.zip"
INDEX_NAME = "path-index.json"
RESERVE_BYTES = 2 * 1024 ** 3
CHUNK_BYTES = 1024 ** 2
DEFAULT_ROOTS = (
    "output", "openmaic-runtime/.runtime/OpenMAIC/data",
    "backend/data/learning-media", "backend/content/textbooks",
    "backend/data/course-storage",
)
EXCLUDED_DIRECTORY_NAMES = {".git", "node_modules", ".next", ".venv", "__pycache__"}
EXCLUDED_DATABASE_PATHS = {
    "output/textbook-first-course-20260924/database-backup/database.sql",
    "output/tiandiren-play-v2/sample-progress.sqlite3",
}
_OPERATOR_STAGING = ("output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard/"
                     "u4-l3/teaching-1/planning/native-operator-staging-0242/")
EXCLUDED_RUNTIME_LINK_TARGETS = {
    _OPERATOR_STAGING + name: "openmaic-runtime/.runtime/OpenMAIC/" + name
    for name in ("types", "public", "packages")
}
SHA_PATTERN = re.compile(r"[a-f0-9]{64}\Z")


class BackupError(RuntimeError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _safe_relative(value):
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise BackupError("unsafe_relative_path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) or re.match(r"^[A-Za-z]:", value):
        raise BackupError("unsafe_relative_path: " + value)
    if PurePosixPath(value).is_absolute():
        raise BackupError("absolute_path_forbidden")
    return value


def _under(path, root):
    return path == root or path.startswith(root + "/")


def _key(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _no_parent_links(path):
    path = Path(os.path.abspath(str(path)))
    for parent in reversed(path.parents):
        if parent.exists() and stat.S_ISLNK(parent.lstat().st_mode):
            raise BackupError("linked_parent_forbidden: " + str(parent))


def _scan_file(path, expected=None, sink=None):
    """Read a stable regular file without following a final-component link."""
    path = Path(path)
    before = path.lstat()
    snapshot = _key(before)
    if not stat.S_ISREG(before.st_mode):
        raise BackupError("regular_file_required: " + str(path))
    if expected is not None and snapshot != expected:
        raise BackupError("source_changed: " + str(path))
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    digest = hashlib.sha256()
    size = 0
    with os.fdopen(fd, "rb") as handle:
        if _key(os.fstat(handle.fileno())) != snapshot:
            raise BackupError("source_changed_during_open: " + str(path))
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            if sink is not None:
                sink(chunk)
        if _key(os.fstat(handle.fileno())) != snapshot:
            raise BackupError("source_changed_during_read: " + str(path))
    if _key(path.lstat()) != snapshot or size != before.st_size:
        raise BackupError("source_changed_during_read: " + str(path))
    return digest.hexdigest(), size, snapshot


def _measure_deflate(path, expected, sha256):
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    count = [0]

    def consume(chunk):
        count[0] += len(compressor.compress(chunk))

    actual, _, _ = _scan_file(path, expected, consume)
    count[0] += len(compressor.flush())
    if actual != sha256:
        raise BackupError("source_hash_changed: " + str(path))
    return count[0]


def _deflate_bytes(data):
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    return len(compressor.compress(data)) + len(compressor.flush())


def _exclusion(relative, st, *, link_target=None, project_root=None):
    name = PurePosixPath(relative).name
    parts = relative.split("/")
    if name in EXCLUDED_DIRECTORY_NAMES and stat.S_ISDIR(st.st_mode):
        return "non_course_dependency_or_build_directory"
    if name in EXCLUDED_DIRECTORY_NAMES and stat.S_ISLNK(st.st_mode):
        return "non_course_dependency_or_build_directory_link"
    if name == ".DS_Store" or name.endswith(".pyc"):
        return "finder_metadata_or_python_bytecode"
    if name == ".env" or name.startswith(".env."):
        return "secret_or_environment_configuration"
    expected_target = EXCLUDED_RUNTIME_LINK_TARGETS.get(relative)
    if (expected_target and stat.S_ISLNK(st.st_mode) and project_root is not None
            and link_target == str(Path(project_root) / expected_target)):
        return "verified_operator_staging_runtime_code_link"
    if relative in EXCLUDED_DATABASE_PATHS:
        return "confirmed_database_backup_or_progress_database"
    if name in {"worker.lock", "operator.lock"} and stat.S_ISREG(st.st_mode) and st.st_size == 0:
        return "confirmed_empty_runtime_lock"
    if parts[:4] == ["backend", "data", "course-storage", "archives"]:
        if len(parts) >= 6 and parts[5] == "课程资料":
            return "uploaded_course_archive_derived_staging"
        if len(parts) == 6 and name.endswith(".zip"):
            return "uploaded_course_archive_derived_zip"
    return None


def _is_sidecar(relative):
    parts = relative.split("/")
    return (len(parts) == 4 and parts[:2] == ["output", "course-data-snapshots"]
            and parts[-1].endswith(".tar.gz"))


@dataclass
class BackupPlan:
    project_root: Path
    index: dict
    source_stats: dict
    object_sources: dict
    restore_program: bytes
    zip_upper_bound: int

    def summary(self):
        files = self.index["files"]
        sidecars = self.index["sidecars"]
        return {
            "schemaVersion": SCHEMA, "roots": self.index["sourceRoots"],
            "fileCount": len(files), "sourceBytes": sum(x["byteSize"] for x in files),
            "uniqueObjects": len(self.index["objects"]),
            "uniqueBytes": sum(x["byteSize"] for x in self.index["objects"].values()),
            "zipSizeUpperBound": self.zip_upper_bound,
            "minimumFreeBytes": self.zip_upper_bound + RESERVE_BYTES,
            "reserveBytes": RESERVE_BYTES, "sidecarCount": len(sidecars),
            "sidecarLogicalBytes": sum(x["byteSize"] for x in sidecars),
            "recordedLinks": len(self.index["symlinks"]),
            "excludedCount": len(self.index["excluded"]),
        }


def build_plan(project_root, roots=None, progress=None):
    project_root = Path(project_root).resolve()
    roots = sorted({_safe_relative(x) for x in (roots or DEFAULT_ROOTS)})
    for number, root in enumerate(roots):
        if any(_under(root, earlier) for earlier in roots[:number]):
            raise BackupError("overlapping_source_roots: " + root)
    index = {
        "schemaVersion": SCHEMA, "createdAt": _now(), "sourceRoots": roots,
        "compression": {"method": "ZIP_DEFLATED", "level": 6, "zip64": True},
        "files": [], "directories": [], "symlinks": [], "sidecars": [],
        "objects": {}, "excluded": [],
    }
    snapshots, object_sources = {}, {}
    scanned = [0]

    def walk(relative):
        path = project_root / relative
        st = path.lstat()
        link_target = os.readlink(str(path)) if stat.S_ISLNK(st.st_mode) else None
        reason = _exclusion(relative, st, link_target=link_target, project_root=project_root)
        if reason:
            record = {"path": relative, "reason": reason}
            if stat.S_ISLNK(st.st_mode):
                record["linkTarget"] = link_target
                snapshots[relative] = _key(st)
            index["excluded"].append(record)
            return
        record = {"path": _safe_relative(relative), "mode": stat.S_IMODE(st.st_mode) & 0o777,
                  "mtimeNs": st.st_mtime_ns}
        snapshots[relative] = _key(st)
        if stat.S_ISLNK(st.st_mode):
            record["target"] = link_target
            index["symlinks"].append(record)
        elif stat.S_ISDIR(st.st_mode):
            index["directories"].append(record)
            for child in sorted(path.iterdir(), key=lambda x: x.name):
                walk(relative + "/" + child.name)
        elif stat.S_ISREG(st.st_mode):
            digest, size, _ = _scan_file(path, snapshots[relative])
            scanned[0] += 1
            if progress and scanned[0] % 10000 == 0:
                progress("Hashed %s source files." % scanned[0])
            record.update(sha256=digest, byteSize=size)
            if _is_sidecar(relative):
                record["backupPath"] = "existing-archives/" + relative
                index["sidecars"].append(record)
            else:
                index["files"].append(record)
                if digest not in index["objects"]:
                    index["objects"][digest] = {"entry": "objects/" + digest, "byteSize": size}
                    object_sources[digest] = relative
        else:
            raise BackupError("special_file_forbidden: " + relative)

    for root in roots:
        _no_parent_links(project_root / root)
        walk(root)
    if progress:
        progress("Hash inventory complete; measuring unique DEFLATE streams without output files.")
    for number, (digest, relative) in enumerate(object_sources.items(), 1):
        index["objects"][digest]["deflateBytes"] = _measure_deflate(
            project_root / relative, snapshots[relative], digest)
        if progress and number % 10000 == 0:
            progress("Measured %s / %s unique objects." % (number, len(object_sources)))
    program = Path(__file__).read_bytes()
    index["recoveryTool"] = {"entry": "restore.py", "byteSize": len(program),
                             "sha256": hashlib.sha256(program).hexdigest()}
    index_bytes = _json_bytes(index)
    # Seekable ZIP64 writer: 30-byte local + 46-byte central headers, names,
    # ZIP64 size/offset extras and end records. 320 bytes safely covers each
    # 72-byte ASCII object entry even when ZIP64 extras are present.
    upper = (sum(x["deflateBytes"] for x in index["objects"].values())
             + _deflate_bytes(program) + _deflate_bytes(index_bytes)
             + (len(object_sources) + 2) * 320 + 4096)
    return BackupPlan(project_root, index, snapshots, object_sources, program, upper)


def available_bytes(path):
    path = Path(path)
    while not path.exists():
        path = path.parent
    _no_parent_links(path)
    if stat.S_ISLNK(path.lstat().st_mode):
        raise BackupError("linked_destination_forbidden")
    return shutil.disk_usage(str(path)).free


def _fsync_file(path):
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_directory(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _clone_file(source, destination):
    if sys.platform != "darwin":
        raise BackupError("sidecar_clone_requires_macos; no ordinary-copy fallback")
    if source.stat().st_dev != destination.parent.stat().st_dev:
        raise BackupError("sidecar_clone_requires_same_filesystem; no ordinary-copy fallback")
    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    clone = library.clonefile
    clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clone.restype = ctypes.c_int
    if clone(os.fsencode(source), os.fsencode(destination), 0) != 0:
        error = ctypes.get_errno()
        raise BackupError("sidecar_clone_failed: " + os.strerror(error))


def _stable_sources(plan, hash_files):
    file_digests = {x["path"]: x["sha256"] for x in plan.index["files"] + plan.index["sidecars"]}
    for relative, expected in plan.source_stats.items():
        path = plan.project_root / relative
        if _key(path.lstat()) != expected:
            raise BackupError("source_changed: " + relative)
        if hash_files and relative in file_digests:
            digest, _, _ = _scan_file(path, expected)
            if digest != file_digests[relative]:
                raise BackupError("source_hash_changed: " + relative)


def _write_archive(plan, destination, progress=None):
    with zipfile.ZipFile(str(destination), "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        archive.writestr(INDEX_NAME, _json_bytes(plan.index))
        archive.writestr("restore.py", plan.restore_program)
        for number, (digest, relative) in enumerate(plan.object_sources.items(), 1):
            info = zipfile.ZipInfo("objects/" + digest)
            info.compress_type = zipfile.ZIP_DEFLATED
            info._compresslevel = 6
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            with archive.open(info, "w", force_zip64=True) as output:
                actual, _, _ = _scan_file(plan.project_root / relative,
                                          plan.source_stats[relative], output.write)
            if actual != digest:
                raise BackupError("source_hash_changed: " + relative)
            if progress and number % 10000 == 0:
                progress("Wrote %s / %s unique objects." % (number, len(plan.object_sources)))
    _fsync_file(destination)


def _write_json(path, value):
    temporary = path.with_name(path.name + ".part")
    with temporary.open("xb") as handle:
        handle.write(_json_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(str(temporary), str(path))


def create_backup(plan, destination, progress=None):
    destination = Path(os.path.abspath(str(destination)))
    _no_parent_links(destination)
    for root in plan.index["sourceRoots"]:
        source_root = plan.project_root / root
        if destination == source_root or source_root in destination.parents:
            raise BackupError("backup_destination_inside_source_root")
    if destination.exists() or destination.is_symlink():
        raise BackupError("backup_destination_already_exists")
    required = plan.zip_upper_bound + RESERVE_BYTES
    if available_bytes(destination) < required:
        raise BackupError("insufficient_space: require %s free bytes including 2 GiB reserve" % required)
    _stable_sources(plan, False)
    destination.mkdir(mode=0o700, parents=False)
    partial = destination / (ARCHIVE_NAME + ".part")
    try:
        for record in plan.index["sidecars"]:
            source = plan.project_root / record["path"]
            digest, size, _ = _scan_file(source, plan.source_stats[record["path"]])
            if (digest, size) != (record["sha256"], record["byteSize"]):
                raise BackupError("sidecar_source_changed")
            target = destination / record["backupPath"]
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _clone_file(source, target)
            _fsync_file(target)
            copied, copied_size, _ = _scan_file(target)
            if (copied, copied_size) != (digest, size):
                raise BackupError("sidecar_clone_verification_failed")
        if available_bytes(destination) < required:
            raise BackupError("insufficient_space_after_sidecar_clones")
        if progress:
            progress("Writing standard ZIP64 objects; source files remain in place.")
        _write_archive(plan, partial, progress)
        if partial.stat().st_size > plan.zip_upper_bound:
            raise BackupError("archive_exceeded_measured_space_bound")
        verify_backup(partial, sidecar_base=destination)
        _stable_sources(plan, True)
        digest, size, _ = _scan_file(partial)
        receipt = {"schemaVersion": "mira.courseware-backup.receipt.v1", "completedAt": _now(),
                   "archiveFile": ARCHIVE_NAME, "sha256": digest, "byteSize": size,
                   "pathIndexSha256": hashlib.sha256(_json_bytes(plan.index)).hexdigest(),
                   "summary": plan.summary()}
        _write_json(destination / "backup-receipt.json", receipt)
        final = destination / ARCHIVE_NAME
        os.replace(str(partial), str(final))
        _fsync_directory(destination)
        return receipt
    except Exception as error:
        # Keep owned diagnostic/partial output; never publish an unverified ZIP.
        if not (destination / ARCHIVE_NAME).exists():
            _write_json(destination / "backup-failure.json",
                        {"schemaVersion": "mira.courseware-backup.failure.v1", "failedAt": _now(),
                         "error": str(error), "finalArchiveCreated": False})
        raise


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError("duplicate_json_key")
        result[key] = value
    return result


def _integer(value, label):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BackupError("invalid_integer: " + label)
    return value


def _index_from_archive(archive):
    infos = archive.infolist()
    names = [x.filename for x in infos]
    if len(names) != len(set(names)) or INDEX_NAME not in names:
        raise BackupError("duplicate_members_or_missing_index")
    for info in infos:
        _safe_relative(info.filename)
        mode = (info.external_attr >> 16) & 0xffff
        if info.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or info.flag_bits & 1:
            raise BackupError("linked_special_or_encrypted_zip_member")
    info = archive.getinfo(INDEX_NAME)
    if info.file_size > 256 * 1024 ** 2:
        raise BackupError("index_too_large")
    raw = archive.read(INDEX_NAME)
    try:
        index = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json)
    except (ValueError, UnicodeError) as error:
        raise BackupError("invalid_path_index") from error
    if not isinstance(index, dict) or index.get("schemaVersion") != SCHEMA:
        raise BackupError("unsupported_path_index")
    roots = index.get("sourceRoots")
    if not isinstance(roots, list) or not roots:
        raise BackupError("invalid_source_roots")
    for root in roots:
        _safe_relative(root)
    paths = set()
    path_kinds = {}
    references = set()
    for category in ("files", "directories", "symlinks", "sidecars"):
        records = index.get(category)
        if not isinstance(records, list):
            raise BackupError("invalid_index_category: " + category)
        for record in records:
            if not isinstance(record, dict):
                raise BackupError("invalid_path_record")
            path = _safe_relative(record.get("path"))
            if path in paths or not any(_under(path, root) for root in roots):
                raise BackupError("duplicate_or_out_of_scope_path")
            paths.add(path)
            path_kinds[path] = category
            if _integer(record.get("mode"), "mode") > 0o777:
                raise BackupError("special_permissions_forbidden")
            _integer(record.get("mtimeNs"), "mtimeNs")
            if category == "symlinks":
                if not isinstance(record.get("target"), str) or "\x00" in record["target"]:
                    raise BackupError("invalid_recorded_link")
            if category in ("files", "sidecars"):
                if not isinstance(record.get("sha256"), str) or not SHA_PATTERN.fullmatch(record["sha256"]):
                    raise BackupError("invalid_sha256")
                _integer(record.get("byteSize"), "byteSize")
                if category == "files":
                    references.add(record["sha256"])
                else:
                    backup_path = _safe_relative(record.get("backupPath"))
                    if backup_path != "existing-archives/" + path:
                        raise BackupError("unsafe_sidecar_mapping")
    objects = index.get("objects")
    if not isinstance(objects, dict) or set(objects) != references:
        raise BackupError("missing_or_unreferenced_objects")
    expected_names = {INDEX_NAME, "restore.py"}
    for digest, record in objects.items():
        if not SHA_PATTERN.fullmatch(digest) or not isinstance(record, dict):
            raise BackupError("invalid_object")
        expected_entry = "objects/" + digest
        if record.get("entry") != expected_entry:
            raise BackupError("unsafe_object_mapping")
        _integer(record.get("byteSize"), "object size")
        _integer(record.get("deflateBytes"), "deflate size")
        expected_names.add(expected_entry)
    if set(names) != expected_names:
        raise BackupError("unexpected_or_missing_zip_members")
    for record in index["files"]:
        if objects[record["sha256"]]["byteSize"] != record["byteSize"]:
            raise BackupError("path_object_size_mismatch")
    for path in paths:
        for parent in PurePosixPath(path).parents:
            if str(parent) in path_kinds and path_kinds[str(parent)] != "directories":
                raise BackupError("non_directory_path_ancestor")
    return index, raw


def _sidecar_path(base, relative):
    path = Path(base) / _safe_relative(relative)
    _no_parent_links(path)
    if not stat.S_ISREG(path.lstat().st_mode):
        raise BackupError("regular_sidecar_required")
    return path


def verify_backup(archive_path, sidecar_base=None):
    archive_path = Path(archive_path)
    _no_parent_links(archive_path)
    if not stat.S_ISREG(archive_path.lstat().st_mode):
        raise BackupError("regular_archive_required")
    base = Path(sidecar_base) if sidecar_base is not None else archive_path.parent
    try:
        with zipfile.ZipFile(str(archive_path), "r") as archive:
            index, raw = _index_from_archive(archive)
            recovery = index.get("recoveryTool", {})
            if not isinstance(recovery, dict):
                raise BackupError("invalid_recovery_tool_record")
            program = archive.read("restore.py")
            if (recovery.get("entry") != "restore.py" or recovery.get("byteSize") != len(program)
                    or recovery.get("sha256") != hashlib.sha256(program).hexdigest()):
                raise BackupError("recovery_tool_hash_mismatch")
            for digest, record in index["objects"].items():
                info = archive.getinfo(record["entry"])
                if info.file_size != record["byteSize"] or info.compress_size != record["deflateBytes"]:
                    raise BackupError("object_zip_size_mismatch")
                actual = hashlib.sha256()
                size = 0
                with archive.open(info, "r") as handle:
                    while True:
                        chunk = handle.read(CHUNK_BYTES)
                        if not chunk:
                            break
                        actual.update(chunk)
                        size += len(chunk)
                if actual.hexdigest() != digest or size != record["byteSize"]:
                    raise BackupError("object_hash_mismatch")
            for record in index["sidecars"]:
                path = _sidecar_path(base, record["backupPath"])
                digest, size, _ = _scan_file(path)
                if (digest, size) != (record["sha256"], record["byteSize"]):
                    raise BackupError("sidecar_hash_mismatch")
    except (zipfile.BadZipFile, OSError, EOFError, zlib.error, NotImplementedError) as error:
        raise BackupError("backup_read_or_crc_error: " + str(error)) from error
    receipt_path = base / "backup-receipt.json"
    if archive_path.name == ARCHIVE_NAME and (receipt_path.exists() or receipt_path.is_symlink()):
        receipt_file = _sidecar_path(base, "backup-receipt.json")
        try:
            receipt = json.loads(receipt_file.read_text(encoding="utf-8"), object_pairs_hook=_unique_json)
        except (ValueError, UnicodeError) as error:
            raise BackupError("invalid_backup_receipt") from error
        if not isinstance(receipt, dict) or receipt.get("schemaVersion") != "mira.courseware-backup.receipt.v1":
            raise BackupError("invalid_backup_receipt")
        digest, size, _ = _scan_file(archive_path)
        if (receipt.get("archiveFile") != ARCHIVE_NAME or receipt.get("sha256") != digest
                or receipt.get("byteSize") != size
                or receipt.get("pathIndexSha256") != hashlib.sha256(raw).hexdigest()):
            raise BackupError("backup_receipt_mismatch")
    return index


def _restore_target(destination, relative):
    target = destination / _safe_relative(relative)
    _no_parent_links(target)
    if target.is_symlink():
        raise BackupError("linked_restore_destination_forbidden")
    return target


def restore_backup(archive_path, destination, roots=None, skip_links=False):
    archive_path = Path(archive_path)
    index = verify_backup(archive_path)
    roots = [_safe_relative(x) for x in roots] if roots else index["sourceRoots"]
    all_records = sum((index[x] for x in ("files", "directories", "sidecars", "symlinks")), [])
    for root in roots:
        if not any(_under(x["path"], root) for x in all_records):
            raise BackupError("selected_root_not_in_backup: " + root)

    def selected(record):
        return any(_under(record["path"], root) for root in roots)

    links = [x for x in index["symlinks"] if selected(x)]
    if links and not skip_links:
        raise BackupError("recorded_symlinks_refused; select other roots or explicitly use --skip-links")
    files = [x for x in index["files"] + index["sidecars"] if selected(x)]
    directories = [x for x in index["directories"] if selected(x)]
    destination = Path(os.path.abspath(str(destination)))
    _no_parent_links(destination)
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise BackupError("unsafe_restore_destination")
    for record in files:
        target = _restore_target(destination, record["path"])
        if target.exists():
            raise BackupError("restore_would_overwrite: " + record["path"])
    existing_directories = set()
    for record in directories:
        target = _restore_target(destination, record["path"])
        if target.exists() and not target.is_dir():
            raise BackupError("restore_directory_conflict")
        if target.exists():
            existing_directories.add(record["path"])
    required = sum(x["byteSize"] for x in files) + RESERVE_BYTES
    if available_bytes(destination) < required:
        raise BackupError("insufficient_restore_space: require %s free bytes" % required)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    for record in sorted(directories, key=lambda x: len(x["path"].split("/"))):
        _restore_target(destination, record["path"]).mkdir(mode=0o700, parents=True, exist_ok=True)
    with zipfile.ZipFile(str(archive_path), "r") as archive:
        for record in files:
            target = _restore_target(destination, record["path"])
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            digest = hashlib.sha256()
            size = 0
            if "backupPath" in record:
                source = _sidecar_path(archive_path.parent, record["backupPath"]).open("rb")
            else:
                source = archive.open(index["objects"][record["sha256"]]["entry"], "r")
            with os.fdopen(fd, "wb") as output, source:
                while True:
                    chunk = source.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if digest.hexdigest() != record["sha256"] or size != record["byteSize"]:
                raise BackupError("restore_hash_mismatch: " + record["path"])
            os.chmod(str(target), record["mode"])
            os.utime(str(target), ns=(record["mtimeNs"], record["mtimeNs"]))
    for record in sorted(directories, key=lambda x: len(x["path"].split("/")), reverse=True):
        if record["path"] in existing_directories:
            continue
        target = _restore_target(destination, record["path"])
        os.chmod(str(target), record["mode"])
        os.utime(str(target), ns=(record["mtimeNs"], record["mtimeNs"]))
    return {"restoredFiles": len(files), "restoredBytes": sum(x["byteSize"] for x in files),
            "skippedLinks": [x["path"] for x in links]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "create"):
        command = commands.add_parser(name)
        command.add_argument("--project-root", default=str(Path.cwd()))
        command.add_argument("--root", action="append", dest="roots",
                             help="Explicit project-relative source root; repeat to select several.")
        command.add_argument("--destination", required=(name == "create"))
    for name in ("verify", "restore"):
        command = commands.add_parser(name)
        command.add_argument("--archive", required=True)
        if name == "restore":
            command.add_argument("--destination")
            command.add_argument("--root", action="append", dest="roots")
            command.add_argument("--skip-links", action="store_true")
            command.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "restore" and not args.verify_only and not args.destination:
        parser.error("restore requires --destination unless --verify-only is used")
    progress = lambda message: print(message, file=sys.stderr, flush=True)
    try:
        if args.command in ("plan", "create"):
            plan = build_plan(args.project_root, args.roots, progress)
            if args.command == "plan":
                result = plan.summary()
                if args.destination:
                    result["availableBytes"] = available_bytes(args.destination)
                    result["spaceSufficient"] = result["availableBytes"] >= result["minimumFreeBytes"]
            else:
                result = create_backup(plan, args.destination, progress)
        elif args.command == "verify" or args.verify_only:
            index = verify_backup(args.archive)
            result = {"verified": True, "files": len(index["files"]),
                      "objects": len(index["objects"]), "sidecars": len(index["sidecars"]),
                      "recordedLinks": len(index["symlinks"])}
        else:
            result = restore_backup(args.archive, args.destination, args.roots, args.skip_links)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (BackupError, OSError, ValueError, KeyError, TypeError) as error:
        print("courseware-backup: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
