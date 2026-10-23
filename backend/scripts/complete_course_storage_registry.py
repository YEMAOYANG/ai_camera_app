#!/usr/bin/env python3
"""Supplement current frozen review dependencies; never change a course release.

inventory is read-only; prepare writes a private ZIP/index. Only the explicit
transfer-register command invokes the existing archive uploader and registers
verified source locators. Originals and existing public archives stay in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from content.textbook_catalog import digest
from content.textbook_interaction_policy import freeze_interaction_policy
from content.textbook_review_followup import (
    discover_complete_scene_review_followup, validate_complete_scene_review_followup,
)
from core.config import AppConfig
from core.course_storage_config import CourseStorageConfig
from core.database import Database
from repositories.course_storage_repository import (
    CourseStorageRepository, normalize_source_path, storage_id_for, storage_identity,
)
from scripts.course_storage_releases import _current_keys, parsed
from services.course_archive_exporter import (
    MAX_FILE_BYTES, MAX_FILES, _check_public, _check_source_text, _credential_file,
    _inspect_original, _original_suffix, _require_private_space, _safe_relative,
    _source_text_file, _supported_source_file,
)
from services.course_archive_queue import NodeArchiveClient
from services.course_file_store import CourseFileStore, _RangeFile, _RemoteObject

SCHEMA = "mira.course-review-dependency.supplement.v1"
SOURCE_KIND = "review_dependency_supplement"
REASON = "current-validator-enumerates-complete-stage-review-root"
REVIEW_ROOT = Path("openmaic-runtime/.runtime/OpenMAIC/data/textbook-current-review-revisions")
CLASSROOM_ROOT = Path("openmaic-runtime/.runtime/OpenMAIC/data/classrooms")
SHA = re.compile(r"[a-f0-9]{64}\Z")
STAGE = re.compile(r"[A-Za-z0-9_-]{1,255}\Z")
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".wav", ".mp3", ".ogg", ".mp4", ".webm"}


class SupplementError(ValueError):
    pass


def require(value, code):
    if not value:
        raise SupplementError(code)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def parse_json(raw):
    def members(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "supplement_duplicate_json_member")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=members)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stat_key(value):
    return tuple(getattr(value, field) for field in
                 ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns"))


def read_stable(path, expected=None):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= MAX_FILE_BYTES, "supplement_source_not_regular_or_oversized")
    require(expected is None or stat_key(before) == tuple(expected), "supplement_source_changed")
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        require(stat_key(os.fstat(handle.fileno())) == stat_key(before), "supplement_source_changed")
        raw = handle.read(MAX_FILE_BYTES + 1)
        require(stat_key(os.fstat(handle.fileno())) == stat_key(before), "supplement_source_changed")
    require(len(raw) == before.st_size and stat_key(path.lstat()) == stat_key(before), "supplement_source_changed")
    return raw, stat_key(before)


def no_links(path, boundary):
    path, boundary = Path(path), Path(boundary)
    require(path.is_relative_to(boundary), "supplement_source_outside_project")
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "supplement_source_symlink")
        if parent == boundary:
            break


def bound_roots(binding):
    session, stage = binding.get("sessionId"), binding.get("stageId")
    require(isinstance(session, str) and 0 < len(session) <= 255 and isinstance(stage, str)
            and STAGE.fullmatch(stage), "supplement_frozen_authoring_missing")
    expected = [(REVIEW_ROOT / sha(session.encode()) / stage).as_posix()]
    require(binding.get("sourceRoots") == expected and binding.get("selectionReason") == REASON,
            "supplement_unbound_source_roots")
    return expected


def binding_from_input(project_root, identity, original_input, storage_directory, *,
                       followup_reader=discover_complete_scene_review_followup, source_roots=None,
                       proof_validator=validate_complete_scene_review_followup):
    """Select the existing validator's exact frozen session/stage dependency."""
    project_root = Path(project_root).resolve()
    candidate = original_input.get("authoringCandidate")
    if candidate is None:
        return None
    require(isinstance(candidate, dict) and type(candidate.get("interactionPolicyVersion")) is int
            and candidate["interactionPolicyVersion"] >= 1, "supplement_candidate_policy_invalid")
    frozen = candidate.get("completeSceneReviewFollowup")
    if frozen is None and candidate["interactionPolicyVersion"] >= freeze_interaction_policy()["policy"]["version"]:
        return None
    authoring = original_input.get("authoring", {})
    session, stage = authoring.get("sessionId"), authoring.get("stageId")
    require(isinstance(session, str) and 0 < len(session) <= 255 and isinstance(stage, str)
            and STAGE.fullmatch(stage), "supplement_frozen_authoring_missing")
    stage_root = REVIEW_ROOT / sha(session.encode()) / stage
    path = project_root / stage_root
    no_links(path, project_root)
    # A historical policy with no revision archive has no review dependency.
    if not path.exists():
        require(frozen is None, "supplement_frozen_review_root_missing")
        return None
    require(path.is_dir(), "supplement_review_root_not_directory")
    proof = followup_reader(None, project_root / CLASSROOM_ROOT, session_id=session, stage_id=stage,
                            base_policy_version=candidate["interactionPolicyVersion"],
                            base_policy_sha256=candidate.get("interactionPolicySha256"),
                            candidate_source_sha256=original_input.get("sourceSha256"))
    mismatch = proof != frozen
    # A saved preview may retain an older sealed follow-up while the same
    # session/stage has since gained another valid revision. Preserve both
    # evidence identities; this does not approve that preview for publication.
    require(not mismatch or (identity.get("contentKey") is None and isinstance(frozen, dict)
                             and isinstance(proof, dict)), "supplement_current_review_differs_from_frozen")
    if mismatch:
        proof_validator(frozen, candidate_source_sha256=original_input.get("sourceSha256"),
                        candidate=candidate, current_policy=freeze_interaction_policy())
    if proof is None:
        return None
    require(isinstance(proof, dict) and isinstance(proof.get("revisionIds"), list)
            and proof["revisionIds"] and all(SHA.fullmatch(x) for x in proof["revisionIds"]),
            "supplement_review_proof_invalid")
    expected_roots = [stage_root.as_posix()]
    require(source_roots is None or sorted(source_roots) == expected_roots, "supplement_unbound_source_roots")
    _safe_relative(storage_directory)
    require(len(storage_directory.split("/")) == 5, "supplement_storage_directory_invalid")
    require(all(isinstance(identity.get(k), str) and identity[k] for k in
                ("courseId", "courseVersion", "previewKey", "classroomId", "originalInputSha256")),
            "supplement_course_binding_invalid")
    result = {**identity, "sessionId": session, "stageId": stage, "sourceRoots": expected_roots,
              "storageDirectory": storage_directory, "selectionReason": REASON,
              "reviewValidation": "frozen-proof-mismatch" if mismatch else "frozen-proof-match",
              "frozenReviewProofSha256": digest(frozen), "currentReviewProofSha256": digest(proof),
              "revisionIds": frozen["revisionIds"], "currentReviewRevisionIds": proof["revisionIds"],
              "frozenAuthoringCandidateSha256": candidate.get("sha256")}
    _check_public(result)
    bound_roots(result)
    return result


def inspect_source(raw, path):
    require(not _credential_file(path), "supplement_credential_file_not_public")
    require(not any(re.search(r"(?:^|[._-])(?:claim|lease|ownership|session-control)(?:[._-]|$)", part, re.I)
                    or part.lower().endswith((".lock", ".pid")) for part in path.parts),
            "supplement_private_control_not_public")
    require(_supported_source_file(path), "supplement_original_format_unsupported")
    _inspect_original(raw, path)
    # Also scan literal JSON assignments; duplicate keys must not hide a secret
    # from a parser's final value. The sealed review reader independently rejects
    # duplicate members in review evidence.
    if _original_suffix(path) == ".json" or _source_text_file(path):
        _check_source_text(raw, _original_suffix(path), source_path=path)


def inventory_sources(binding, project_root, registry, storage_id, *, aliases=None, remote_reader=None):
    project_root = Path(project_root).resolve()
    records, snapshots, root_stats, blocked = [], {}, {}, []
    for relative in bound_roots(binding):
        root = project_root / relative
        no_links(root, project_root)
        root_stats[relative] = stat_key(root.lstat())
        require(stat.S_ISDIR(root.lstat().st_mode), "supplement_source_root_invalid")
        for parent, directories, names in os.walk(root, followlinks=False):
            directories.sort()
            for name in directories:
                directory = Path(parent) / name
                no_links(directory, root)
                require(stat.S_ISDIR(directory.lstat().st_mode), "supplement_special_directory")
                root_stats[directory.relative_to(project_root).as_posix()] = stat_key(directory.lstat())
            for name in sorted(names):
                path = Path(parent) / name
                relative_path = path.relative_to(project_root).as_posix()
                try:
                    no_links(path, root)
                    normalize_source_path(relative_path)
                    raw, snapshot = read_stable(path)
                    inspect_source(raw, path)
                except ValueError as error:
                    blocked.append({"sourcePath": relative_path, "reason": str(error)})
                    continue
                require(len(records) < MAX_FILES, "supplement_source_count_exceeded")
                checksum = sha(raw)
                snapshots[relative_path] = snapshot
                entry = registry.resolve(relative_path, storage_id=storage_id)
                require(entry is None or (entry["sha256"], entry["byteSize"]) == (checksum, len(raw)),
                        "supplement_registered_original_conflict")
                records.append({"sourcePath": relative_path, "sha256": checksum, "byteSize": len(raw),
                                "mimeType": mimetypes.guess_type(name)[0] or "application/octet-stream",
                                "archivePath": "原稿/" + relative_path,
                                "disposition": "already_registered" if entry else "zip",
                                **({"locator": entry["locator"]} if entry else {})})
    alias_map = aliases(records) if callable(aliases) else (aliases or {})
    for record in records:
        entry = alias_map.get(record["sha256"])
        if (record["disposition"] != "zip" or Path(record["sourcePath"]).suffix.lower() not in MEDIA_SUFFIXES
                or entry is None):
            continue
        require(remote_reader is not None, "supplement_alias_remote_verifier_required")
        require((entry["sha256"], entry["byteSize"], entry["mimeType"]) ==
                (record["sha256"], record["byteSize"], record["mimeType"]), "supplement_alias_identity_mismatch")
        raw = remote_reader.read_bytes(project_root / entry["sourcePath"],
                                       expected_sha256=record["sha256"], expected_bytes=record["byteSize"])
        require(raw is not None and len(raw) == record["byteSize"] and sha(raw) == record["sha256"],
                "supplement_alias_remote_hash_mismatch")
        record.update(disposition="reuse_registered", locator=entry["locator"],
                      verifiedAliasSourcePath=entry["sourcePath"])
    for relative, expected in root_stats.items():
        require(stat_key((project_root / relative).lstat()) == expected, "supplement_directory_changed")
    return {"binding": binding, "files": sorted(records, key=lambda x: x["sourcePath"]),
            "sourceStats": snapshots, "rootStats": root_stats, "blocked": blocked}


def registered_media_aliases(registry, storage_id, binding, records):
    """Reuse bytes only from existing immutable scopes of this exact course."""
    wanted = {r["sha256"]: r for r in records if r["disposition"] == "zip"
              and Path(r["sourcePath"]).suffix.lower() in MEDIA_SUFFIXES}
    result = {}
    for scope in registry.find_scopes(storage_id=storage_id, course_id=binding["courseId"],
                                      course_version=binding["courseVersion"]):
        for item in scope["bindings"]:
            checksum = item["sha256"]
            if checksum not in wanted or checksum in result:
                continue
            entry = registry.resolve(item["sourcePath"], storage_id=storage_id, expected_sha=checksum)
            if (entry is not None and (entry["byteSize"], entry["mimeType"]) ==
                    (wanted[checksum]["byteSize"], wanted[checksum]["mimeType"])):
                result[checksum] = entry
    return result


def assert_sources(inventory, project_root):
    project_root = Path(project_root).resolve()
    roots = bound_roots(inventory["binding"])
    require(not inventory["blocked"], "supplement_public_ineligible_sources")
    records = inventory["files"]
    require(isinstance(records, list) and records and len(records) <= MAX_FILES,
            "supplement_source_count_invalid")
    by_path = {r["sourcePath"]: r for r in records}
    require(len(by_path) == len(records) and set(inventory["sourceStats"]) == set(by_path),
            "supplement_source_set_invalid")
    seen_files, seen_directories = set(), set()
    for root_path in roots:
        root = project_root / root_path
        no_links(root, project_root)
        for parent, directories, filenames in os.walk(root, followlinks=False):
            seen_directories.add(Path(parent).relative_to(project_root).as_posix())
            for name in directories:
                path = Path(parent) / name
                no_links(path, project_root)
                require(path.is_dir(), "supplement_special_directory")
            for name in filenames:
                seen_files.add((Path(parent) / name).relative_to(project_root).as_posix())
    require(seen_files == set(by_path) and seen_directories == set(inventory["rootStats"]),
            "supplement_source_set_changed")
    for relative, expected in inventory["rootStats"].items():
        require(stat_key((project_root / relative).lstat()) == tuple(expected), "supplement_directory_changed")
    for relative, expected in inventory["sourceStats"].items():
        normalize_source_path(relative)
        no_links(project_root / relative, project_root)
        raw, _ = read_stable(project_root / relative, expected)
        record = by_path[relative]
        require(sha(raw) == record["sha256"] and len(raw) == record["byteSize"], "supplement_source_hash_changed")
        require(record["archivePath"] == "原稿/" + relative
                and record["mimeType"] == (mimetypes.guess_type(relative)[0] or "application/octet-stream")
                and record["disposition"] in {"zip", "already_registered", "reuse_registered"},
                "supplement_source_record_invalid")
        inspect_source(raw, project_root / relative)


def manifest_for(binding, inventory):
    records = [r for r in inventory["files"] if r["disposition"] != "already_registered"]
    require(records, "supplement_no_missing_originals")
    return {"schemaVersion": SCHEMA, "sourceKind": SOURCE_KIND, "complete": True,
            "binding": binding, "files": records,
            "alreadyRegistered": [{k: r[k] for k in ("sourcePath", "sha256", "byteSize")}
                                  for r in inventory["files"] if r["disposition"] == "already_registered"]}


def write_private(path, raw):
    require(not path.is_symlink(), "supplement_private_artifact_symlink")
    if path.exists():
        require(not path.is_symlink() and read_stable(path)[0] == raw, "supplement_private_artifact_conflict")
        return
    temporary = path.with_name(path.name + ".part")
    with temporary.open("xb") as handle:
        os.chmod(temporary, 0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def private_workspace(project_root, destination):
    project_root, destination = Path(project_root).resolve(), Path(destination).absolute()
    allowed = [project_root / "backend/data/course-storage/archives"]
    if os.environ.get("MIRA_TASK_TMPDIR"):
        task_alias = Path(os.environ["MIRA_TASK_TMPDIR"]).absolute()
        task_root = task_alias.resolve()
        # macOS exposes the task directory through /var and /private/var.
        # Canonicalize only that approved prefix, never arbitrary descendants.
        if destination.is_relative_to(task_alias):
            destination = task_root / destination.relative_to(task_alias)
        allowed.append(task_root)
    require(any(destination.is_relative_to(root) for root in allowed), "supplement_private_workspace_required")
    boundary = next(root for root in allowed if destination.is_relative_to(root))
    if boundary.is_relative_to(project_root):
        no_links(boundary, project_root)
    no_links(destination, boundary)
    return destination


def prepare_supplement(binding, inventory, project_root, destination, *, reserve_free_bytes=2 * 1024 ** 3):
    project_root = Path(project_root).resolve()
    destination = private_workspace(project_root, destination)
    require(not inventory["blocked"], "supplement_public_ineligible_sources")
    require(inventory["binding"] == binding, "supplement_inventory_binding_changed")
    assert_sources(inventory, project_root)
    manifest = manifest_for(binding, inventory)
    records = manifest["files"]
    _check_public(manifest)
    manifest_raw = json_bytes(manifest)
    manifest_sha = sha(manifest_raw)
    archive_id = "review-supplement-" + manifest_sha[:24]
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(not destination.stat().st_mode & 0o077, "supplement_workspace_not_private")
    zipped = [r for r in records if r["disposition"] == "zip"]
    require(type(reserve_free_bytes) is int and reserve_free_bytes >= 2 * 1024 ** 3,
            "supplement_disk_reserve_invalid")
    space = os.statvfs(destination)
    upper = (sum(r["byteSize"] for r in zipped) + len(manifest_raw) * 3
             + len(zipped) * 1024 + len(json_bytes(inventory)) + 2 * 1024 ** 2)
    require(space.f_bavail * space.f_frsize >= upper + reserve_free_bytes,
            "supplement_disk_reserve_insufficient")
    _require_private_space(destination, sum(r["byteSize"] for r in zipped) + len(manifest_raw) * 3,
                           phase="review_supplement")
    manifest_path = destination / "manifest.json"
    write_private(manifest_path, manifest_raw)
    zip_path = destination / "review-dependencies.zip"
    require(not zip_path.is_symlink(), "supplement_private_artifact_symlink")
    if not zip_path.exists():
        partial = destination / "review-dependencies.zip.part"
        with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for name, raw in [("manifest.json", manifest_raw)]:
                info = zipfile.ZipInfo(name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, raw)
            for record in zipped:
                raw, _ = read_stable(project_root / record["sourcePath"], inventory["sourceStats"][record["sourcePath"]])
                require(sha(raw) == record["sha256"], "supplement_source_hash_changed")
                info = zipfile.ZipInfo(record["archivePath"])
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, raw)
        os.chmod(partial, 0o600)
        with partial.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(partial, zip_path)
    raw_zip, _ = read_stable(zip_path)
    verify_zip(zip_path.open("rb"), manifest, manifest_raw)
    assert_sources(inventory, project_root)
    object_directory = binding["storageDirectory"]
    entries = []
    for local_path, filename, mime in (
            (manifest_path, "审核原稿补充-" + manifest_sha[:24] + ".json", "application/json"),
            (zip_path, "审核原稿补充-" + manifest_sha[:24] + ".zip", "application/zip")):
        raw, _ = read_stable(local_path)
        entries.append({"localPath": str(local_path), "relativePath": object_directory + "/" + filename,
                        "sha256": sha(raw), "byteSize": len(raw), "mimeType": mime})
    index = {"schemaVersion": "mira.course-archive.export.v1", "sourceKind": SOURCE_KIND,
             "archiveId": archive_id, "complete": True, "missingSources": [],
             "courseId": binding["courseId"], "courseVersion": binding["courseVersion"],
             "contentKey": binding.get("contentKey"), "classroomId": binding["classroomId"],
             "sourceDigest": manifest_sha, "objectDirectory": object_directory,
             "manifestPath": str(manifest_path), "indexPath": str(destination / "index.json"),
             "generatedPublicFiles": entries,
             "zip": {"path": str(zip_path), "sha256": sha(raw_zip), "byteSize": len(raw_zip)}}
    write_private(destination / "source-plan.json", json_bytes(inventory))
    write_private(destination / "index.json", json_bytes(index))
    return index


def verify_zip(handle, manifest, manifest_raw):
    with handle, zipfile.ZipFile(handle) as archive:
        expected = {"manifest.json"} | {r["archivePath"] for r in manifest["files"] if r["disposition"] == "zip"}
        infos = archive.infolist()
        require(len(infos) == len(expected) and {i.filename for i in infos} == expected,
                "supplement_zip_member_set_mismatch")
        for info in infos:
            _safe_relative(info.filename)
            require(not info.is_dir() and not info.flag_bits & 1
                    and stat.S_IFMT(info.external_attr >> 16) in {0, stat.S_IFREG},
                    "supplement_zip_member_invalid")
        require(archive.read("manifest.json") == manifest_raw, "supplement_zip_manifest_mismatch")
        for record in manifest["files"]:
            if record["disposition"] != "zip":
                continue
            _safe_relative(record["archivePath"])
            info = archive.getinfo(record["archivePath"])
            require(not info.is_dir() and not info.flag_bits & 1
                    and stat.S_IFMT(info.external_attr >> 16) in {0, stat.S_IFREG}
                    and info.file_size == record["byteSize"], "supplement_zip_member_invalid")
            require(sha(archive.read(info)) == record["sha256"], "supplement_zip_member_hash_mismatch")


def verify_and_register(index_path, *, binding_loader, registry, config, node_client,
                        remote_zip_factory=None, remote_object_read=None, alias_reader=None):
    project_root = Path(node_client.root).resolve()
    index_path = Path(index_path).absolute()
    index_path = private_workspace(project_root, index_path.parent) / index_path.name
    no_links(index_path, index_path.parent)
    require(index_path.name == "index.json" and not index_path.parent.stat().st_mode & 0o077,
            "supplement_workspace_not_private")
    require(callable(getattr(registry, "activate_heads_if_unchanged", None))
            and callable(getattr(registry, "head_scope", None)),
            "supplement_batch_head_cas_required")
    raw_index, _ = read_stable(index_path)
    index = parse_json(raw_index)
    require(index.get("sourceKind") == SOURCE_KIND and index.get("schemaVersion") == "mira.course-archive.export.v1"
            and index.get("complete") is True, "supplement_index_invalid")
    plan = parse_json(read_stable(index_path.parent / "source-plan.json")[0])
    binding = plan["binding"]
    require(binding_loader(binding) == binding, "supplement_current_binding_changed")
    assert_sources(plan, project_root)
    require(index.get("manifestPath") == str(index_path.parent / "manifest.json"),
            "supplement_index_artifact_invalid")
    manifest_raw, _ = read_stable(index_path.parent / "manifest.json")
    manifest = parse_json(manifest_raw)
    require(manifest.get("schemaVersion") == SCHEMA and manifest.get("sourceKind") == SOURCE_KIND
            and manifest.get("binding") == binding and index["sourceDigest"] == sha(manifest_raw)
            and manifest == manifest_for(binding, plan)
            and not plan["blocked"], "supplement_manifest_invalid")
    _check_public(manifest)
    entries = index["generatedPublicFiles"]
    require(len(entries) == 2 and {x["mimeType"] for x in entries} == {"application/zip", "application/json"},
            "supplement_two_public_objects_required")
    require(index.get("archiveId") == "review-supplement-" + sha(manifest_raw)[:24]
            and index.get("objectDirectory") == binding["storageDirectory"]
            and index.get("courseId") == binding["courseId"] and index.get("courseVersion") == binding["courseVersion"]
            and index.get("contentKey") == binding.get("contentKey") and index.get("classroomId") == binding["classroomId"]
            and index.get("indexPath") == str(index_path) and index.get("missingSources") == [],
            "supplement_index_binding_invalid")
    expected_paths = {"application/json": index_path.parent / "manifest.json",
                      "application/zip": index_path.parent / "review-dependencies.zip"}
    for entry in entries:
        local_path = expected_paths[entry["mimeType"]]
        no_links(local_path, index_path.parent)
        raw, _ = read_stable(local_path)
        extension = ".json" if entry["mimeType"] == "application/json" else ".zip"
        require(entry.get("localPath") == str(local_path)
                and entry.get("relativePath") == binding["storageDirectory"] + "/审核原稿补充-" + sha(manifest_raw)[:24] + extension
                and (entry.get("sha256"), entry.get("byteSize")) == (sha(raw), len(raw)),
                "supplement_public_artifact_changed")
    zip_entry = next(x for x in entries if x["mimeType"] == "application/zip")
    require(index.get("manifestPath") == str(expected_paths["application/json"])
            and index.get("zip") == {"path": zip_entry["localPath"], "sha256": zip_entry["sha256"],
                                     "byteSize": zip_entry["byteSize"]}, "supplement_index_artifact_invalid")
    verify_zip(Path(index["zip"]["path"]).open("rb"), manifest, manifest_raw)
    storage_id = storage_id_for(config.endpoint, config.bucket, config.region)
    remote_sources = alias_reader or CourseFileStore(config=config, project_root=project_root, repository=registry)
    expected_heads = {}
    for record in manifest["files"]:
        current = registry.resolve(record["sourcePath"], storage_id=storage_id)
        if current is None:
            expected_heads[record["sourcePath"]] = None
            continue
        require((current["sha256"], current["byteSize"], current["mimeType"]) ==
                (record["sha256"], record["byteSize"], record["mimeType"]), "supplement_source_head_changed")
        scope = registry.head_scope(record["sourcePath"], storage_id)
        require(scope is not None, "supplement_source_head_changed")
        raw = remote_sources.read_bytes(project_root / record["sourcePath"],
            expected_sha256=record["sha256"], expected_bytes=record["byteSize"])
        require(raw is not None and len(raw) == record["byteSize"] and sha(raw) == record["sha256"],
                "supplement_existing_head_remote_hash_mismatch")
        expected_heads[record["sourcePath"]] = {"sha256": current["sha256"], "scopeKey": scope["scopeKey"]}
    receipt = node_client.upload(str(index_path))
    identity = storage_identity(config.endpoint, config.bucket, config.region)
    require(receipt.get("schemaVersion") == "mira.course-archive.verification.v1"
            and receipt.get("complete") is True and receipt.get("archiveId") == index["archiveId"]
            and receipt.get("indexSha256") == sha(raw_index) and receipt.get("storage") == identity
            and receipt.get("courseId") == binding["courseId"]
            and receipt.get("courseVersion") == binding["courseVersion"]
            and receipt.get("sourceDigest") == index["sourceDigest"], "supplement_upload_receipt_mismatch")
    objects = receipt.get("objects", [])
    require(len(objects) == 2 and {x["objectKey"] for x in objects} == {x["relativePath"] for x in entries},
            "supplement_remote_object_set_mismatch")
    by_key = {x["objectKey"]: x for x in objects}
    for entry in entries:
        record = by_key[entry["relativePath"]]
        require(record.get("sha256") == entry["sha256"] and record.get("byteSize") == entry["byteSize"]
                and isinstance(record.get("etag"), str) and record["etag"], "supplement_remote_identity_mismatch")
    manifest_entry = next(x for x in entries if x["mimeType"] == "application/json")
    zip_entry = next(x for x in entries if x["mimeType"] == "application/zip")

    def locator(record):
        return {"kind": "object", "objectKey": record["objectKey"], "etag": record["etag"],
                **({"versionId": record["versionId"]} if record.get("versionId") else {})}

    manifest_remote = by_key[manifest_entry["relativePath"]]
    read_remote = remote_object_read or (lambda r: _RemoteObject(config, locator(r), r["byteSize"]).get(whole=True))
    require(read_remote(manifest_remote) == manifest_raw, "supplement_remote_manifest_hash_mismatch")
    zip_remote = by_key[zip_entry["relativePath"]]
    factory = remote_zip_factory or (lambda r: _RangeFile(_RemoteObject(config, locator(r), r["byteSize"])))
    verify_zip(factory(zip_remote), manifest, manifest_raw)
    files = []
    for record in manifest["files"]:
        if record["disposition"] == "zip":
            source_locator = {**locator(zip_remote), "kind": "zip_member", "archiveSha256": zip_remote["sha256"],
                              "archiveByteSize": zip_remote["byteSize"], "memberPath": record["archivePath"]}
        elif record["disposition"] == "reuse_registered":
            alias = registry.resolve(record["verifiedAliasSourcePath"],
                                     storage_id=storage_id_for(config.endpoint, config.bucket, config.region),
                                     expected_sha=record["sha256"])
            require(alias is not None and alias["locator"] == record["locator"], "supplement_alias_locator_changed")
            # Recheck reused bytes after ZIP upload and before activating heads.
            raw = remote_sources.read_bytes(project_root / alias["sourcePath"], expected_sha256=record["sha256"],
                                   expected_bytes=record["byteSize"])
            require(raw is not None and sha(raw) == record["sha256"], "supplement_alias_remote_hash_mismatch")
            source_locator = record["locator"]
        else:
            raise SupplementError("supplement_unknown_disposition")
        files.append({"sourcePath": record["sourcePath"], "sha256": record["sha256"],
                      "byteSize": record["byteSize"], "mimeType": record["mimeType"], "locator": source_locator})
    require(binding_loader(binding) == binding, "supplement_current_binding_changed")
    assert_sources(plan, project_root)
    metadata = {"registryVersion": 4, "sourceKind": SOURCE_KIND, "sourceDigest": sha(manifest_raw),
                "originalSourceDigest": binding.get("originalSourceDigest"),
                "courseId": binding["courseId"], "courseVersion": binding["courseVersion"],
                "contentKey": binding.get("contentKey"), "previewKey": binding["previewKey"],
                "classroomId": binding["classroomId"], "storageDirectory": binding["storageDirectory"],
                "selectionReason": REASON, "sourceRoots": binding["sourceRoots"],
                "frozenBindingSha256": digest(binding), "supplementManifestSha256": sha(manifest_raw),
                "reviewValidation": binding["reviewValidation"],
                "frozenReviewProofSha256": binding["frozenReviewProofSha256"],
                "currentReviewProofSha256": binding["currentReviewProofSha256"],
                "archiveSha256": zip_remote["sha256"]}
    metadata["scopeKey"] = digest(metadata)
    registered = registry.register_scope(metadata, files,
                                        storage_id_for(config.endpoint, config.bucket, config.region), activate=False)
    # Shared current stage roots can be registered by another course first.
    # Only byte-identical, remotely verified existing heads enter the baseline;
    # any head change during upload fails atomically instead of being replaced.
    activation = registry.activate_heads_if_unchanged(metadata["scopeKey"],
        storage_id, expected_heads)
    return {"scopeKey": metadata["scopeKey"], "sourceKind": SOURCE_KIND,
            "registeredFiles": len(files), "sourceDigest": metadata["sourceDigest"],
            "scope": registered, "activation": activation}


def original_directory(registry, storage_id, identity):
    scopes = registry.find_scopes(storage_id=storage_id, course_id=identity["courseId"],
                                  course_version=identity["courseVersion"])
    directories = {s["metadata"]["storageDirectory"] for s in scopes
                   if s["metadata"].get("registryVersion") == 3
                   and s["metadata"].get("sourceKind") != SOURCE_KIND
                   and s["metadata"].get("sourceDigest") == identity.get("originalSourceDigest")
                   and s["metadata"].get("storageDirectory")}
    require(len(directories) == 1, "supplement_original_storage_directory_ambiguous")
    return directories.pop(), scopes


def load_bindings(database, registry, store, *, content_keys=(), preview_keys=(), all_current=False):
    storage_id = storage_id_for(store.config.endpoint, store.config.bucket, store.config.region)
    records, current_preview_keys = [], set()
    with database.transaction() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        keys = _current_keys(conn, None)
        require(all(k in keys for k in content_keys), "supplement_noncurrent_content_key")
        for key in keys:
            row = conn.execute("SELECT content_key,course_id,course_version,input_json,"
                "JSON_UNQUOTE(JSON_EXTRACT(review_json,'$.release.classroomId')) AS classroom_id,"
                "JSON_UNQUOTE(JSON_EXTRACT(review_json,'$.release.sha256')) AS release_sha256 "
                "FROM learning_textbook_course_builds WHERE content_key=?", (key,)).fetchone()
            frozen = parsed(row["input_json"])
            preview_key = frozen.get("previewKey")
            if preview_key:
                current_preview_keys.add(preview_key)
            if not all_current and key not in content_keys:
                continue
            identity = {"contentKey": key, "courseId": row["course_id"], "courseVersion": row["course_version"],
                        "classroomId": row["classroom_id"], "originalSourceDigest": row["release_sha256"],
                        "frozenInputSha256": sha(row["input_json"].encode())}
            if preview_key:
                preview = conn.execute("SELECT preview_key,classroom_id,input_json FROM learning_textbook_course_previews "
                                       "WHERE preview_key=?", (preview_key,)).fetchone()
                require(preview is not None, "supplement_bound_preview_missing")
                original = parsed(preview["input_json"])
                identity.update(previewKey=preview_key, originalInputSha256=sha(preview["input_json"].encode()))
            else:
                # Batch activities own an exact task input. Read only that
                # scope's frozen input; never glob historical output directories.
                directory, scopes = original_directory(registry, storage_id, identity)
                task_id = frozen.get("taskId")
                matches = []
                if isinstance(task_id, str) and SHA.fullmatch(task_id):
                    for scope in scopes:
                        for item in scope["bindings"]:
                            if item["sourcePath"].endswith("/" + task_id + "/input.json"):
                                raw = store.read_bytes(store.project_root / item["sourcePath"], expected_sha256=item["sha256"])
                                original_input = json.loads(raw)
                                if (original_input.get("taskId") == task_id
                                        and original_input.get("inputSha256") == frozen.get("sourceInputSha256")):
                                    matches.append((original_input, sha(raw)))
                require(matches and len({digest(x[0]) for x in matches}) == 1, "supplement_activity_input_binding_missing")
                original = matches[0][0]
                identity.update(previewKey=original.get("previewKey") or task_id, originalInputSha256=matches[0][1])
            directory, _ = original_directory(registry, storage_id, identity)
            records.append((identity, original, directory))
        saved_keys = [r["preview_key"] for r in conn.execute("SELECT preview_key FROM learning_textbook_course_previews "
            "WHERE classroom_json IS NOT NULL AND status IN ('preview_ready','review_required') ORDER BY preview_key").fetchall()
                      if r["preview_key"] not in current_preview_keys]
        require(all(k in saved_keys for k in preview_keys), "supplement_noncurrent_saved_preview")
        for key in saved_keys:
            if not all_current and key not in preview_keys:
                continue
            row = conn.execute("SELECT preview_key,classroom_id,classroom_sha256,input_json FROM learning_textbook_course_previews "
                               "WHERE preview_key=?", (key,)).fetchone()
            original = parsed(row["input_json"])
            identity = {"contentKey": None, "courseId": "textbook-preview:" + key,
                        "courseVersion": "saved-" + row["classroom_sha256"][:16], "previewKey": key,
                        "classroomId": row["classroom_id"], "originalSourceDigest": row["classroom_sha256"],
                        "originalInputSha256": sha(row["input_json"].encode()),
                        "frozenInputSha256": sha(row["input_json"].encode())}
            directory, _ = original_directory(registry, storage_id, identity)
            records.append((identity, original, directory))
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inventory", "prepare"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--content-key", action="append", default=[])
        sub.add_argument("--preview-key", action="append", default=[])
        sub.add_argument("--all-current", action="store_true")
        if command == "prepare":
            sub.add_argument("--output-root", type=Path, required=True)
            sub.add_argument("--reserve-free-bytes", type=int, default=2 * 1024 ** 3)
    transfer = subparsers.add_parser("transfer-register")
    transfer.add_argument("--index", "--plan", dest="index", type=Path, required=True)
    transfer.add_argument("--node", default=os.environ.get("COURSE_ARCHIVE_NODE", "node"))
    args = parser.parse_args(argv)
    try:
        database = Database(AppConfig.from_env().DATABASE_URL)
        config = CourseStorageConfig.from_env()
        require(config.mode == "registry", "supplement_registry_mode_required")
        registry = CourseStorageRepository(database)
        store = CourseFileStore(config=config, project_root=ROOT, repository=registry)
        storage_id = storage_id_for(config.endpoint, config.bucket, config.region)
        if args.command == "transfer-register":
            def reload_binding(binding):
                records = load_bindings(database, registry, store,
                    content_keys=[binding["contentKey"]] if binding.get("contentKey") else [],
                    preview_keys=[] if binding.get("contentKey") else [binding["previewKey"]])
                require(len(records) == 1, "supplement_current_binding_ambiguous")
                return binding_from_input(ROOT, *records[0])
            result = verify_and_register(args.index, binding_loader=reload_binding, registry=registry,
                config=config, node_client=NodeArchiveClient(project_root=ROOT, node=args.node))
            print(json.dumps(result, ensure_ascii=False))
            return 0
        require(args.all_current or args.content_key or args.preview_key, "supplement_explicit_current_selection_required")
        records = load_bindings(database, registry, store, content_keys=args.content_key,
                               preview_keys=args.preview_key, all_current=args.all_current)
        inapplicable = 0
        for identity, original, directory in records:
            binding = binding_from_input(ROOT, identity, original, directory)
            if binding is None:
                inapplicable += 1
                continue
            inventory = inventory_sources(binding, ROOT, registry, storage_id,
                aliases=lambda records: registered_media_aliases(registry, storage_id, binding, records),
                remote_reader=store)
            summary = {"binding": binding, "files": len(inventory["files"]),
                       "bytes": sum(r["byteSize"] for r in inventory["files"]),
                       "missing": sum(r["disposition"] == "zip" for r in inventory["files"]),
                       "blocked": inventory["blocked"]}
            if args.command == "prepare":
                target = args.output_root / digest(binding)[:24]
                summary["indexPath"] = prepare_supplement(binding, inventory, ROOT, target,
                    reserve_free_bytes=args.reserve_free_bytes)["indexPath"]
            print(json.dumps(summary, ensure_ascii=False), flush=True)
        print(json.dumps({"selectedCurrentRecords": len(records), "inapplicable": inapplicable}, ensure_ascii=False))
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, SupplementError) else "supplement_operation_failed"
        print(json.dumps({"ok": False, "errorType": type(error).__name__,
                          "errorCode": code if re.fullmatch(r"[a-z0-9_]+", code) else "supplement_operation_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
