"""Bind verified archives to file locators without uploading another byte."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from repositories.course_storage_repository import storage_id_for, normalize_source_path
from services.course_archive_queue import CourseArchiveProcessor, CourseArchiveQueue, _read


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _object_locator(obj):
    return {"kind": "object", **{k: obj[k] for k in ("objectKey", "etag", "versionId") if k in obj}}


def archive_registration(queue, job):
    processor = CourseArchiveProcessor(queue, None, None)
    index = processor._index(job)
    processor._receipt(job, index)
    receipt = json.loads(_read(Path(job["receiptPath"])))
    manifest_path = Path(job.get("retainedManifestPath") or index["manifestPath"])
    raw = _read(manifest_path)
    manifest = json.loads(raw)
    proof = next(e for e in index["generatedPublicFiles"] if e["localPath"] == index["manifestPath"])
    if (_sha(raw) != proof["sha256"] or len(raw) != proof["byteSize"]
            or manifest.get("archiveId") != index["archiveId"] or manifest.get("complete") is not True
            or manifest.get("missingSources")):
        raise ValueError("course_storage_manifest_not_verified")
    archive = next(e for e in index["generatedPublicFiles"] if e["localPath"] == index["zip"]["path"])
    if (not isinstance(index.get("objectDirectory"), str)
            or any(e["relativePath"].rsplit("/", 1)[0] != index["objectDirectory"] for e in index["generatedPublicFiles"])):
        raise ValueError("course_storage_directory_not_verified")
    verified = {o["objectKey"]: o for o in receipt["objects"]}
    zip_proof = verified[archive["relativePath"]]
    locator = {**_object_locator(zip_proof), "kind": "zip_member",
        "archiveSha256": archive["sha256"], "archiveByteSize": archive["byteSize"]}
    files = {}
    for entry in manifest["files"]:
        member = entry.get("archivePath", "")
        prefix = next((p for p in ("原稿/", "媒体/") if member.startswith(p)), None)
        if prefix is None or (prefix == "原稿/" and entry.get("original") is not True):
            continue  # DB snapshots remain in the DB; no fake filesystem path.
        path = normalize_source_path(member.removeprefix(prefix))
        item = {"sourcePath": path, **{k: entry[k] for k in ("sha256", "byteSize", "mimeType")},
                "locator": {**locator, "memberPath": member}}
        item["mimeType"] = {"audio/x-wav": "audio/wav", "audio/mp3": "audio/mpeg", "image/jpg": "image/jpeg"}.get(item["mimeType"], item["mimeType"])
        if path in files:
            if any(files[path][k] != item[k] for k in ("sha256", "byteSize", "mimeType")):
                raise ValueError("course_storage_duplicate_original")
        else:
            files[path] = item
    # Some formal courses store their original JSON in PostgreSQL. Expose the
    # exact archived classroom bytes at the Native legacy-compatible read path.
    cid = index.get("classroomId")
    if cid:
        path = "openmaic-runtime/.runtime/OpenMAIC/data/classrooms/" + cid + ".json"
        normalize_source_path(path)
        if path not in files:
            entry = next(e for e in manifest["files"] if e["archivePath"] == "classroom.json")
            files[path] = {"sourcePath": path, **{k: entry[k] for k in ("sha256", "byteSize", "mimeType")},
                "locator": {**locator, "memberPath": "classroom.json"}}
    metadata = {"scopeKey": _sha(("mira.course-storage.scope.v3:" + job["key"]).encode()),
        "queueJobKey": job["key"], "registryVersion": 3, "archiveId": index["archiveId"],
        "storageDirectory": index["objectDirectory"],
        "archiveSha256": archive["sha256"], "manifestSha256": proof["sha256"],
        "sourceDigest": index.get("sourceDigest") or index["releaseSha256"],
        **{k: index[k] for k in ("sourceKind", "courseId", "courseVersion", "contentKey", "classroomId", "status") if index.get(k) is not None}}
    if index.get("sourceKind") == "textbook_preview":
        key = index.get("courseId", "").removeprefix("textbook-preview:")
        if len(key) == 64:
            metadata["previewKey"] = key
    return metadata, list(files.values())


def register_archive(queue, job, repository, *, activate=True):
    metadata, files = archive_registration(queue, job)
    storage_id = storage_id_for(**queue.storage)
    registered = repository.register_scope(metadata, files, storage_id, activate=False)
    if activate:
        repository.activate_missing_heads(metadata['scopeKey'], storage_id)
    return registered


def media_registration(state_root, storage):
    root = Path(state_root)
    raw = _read(root / "active-manifest.json")
    active = json.loads(_read(root / "active-verification.json"))
    manifest_sha = _sha(raw)
    if active["manifestSha256"] != manifest_sha:
        raise ValueError("course_storage_media_manifest_changed")
    receipt_path = root / "transfers" / ("canonical-course-media-" + json.loads(raw)["uploadDate"]) / "verified-complete.json"
    receipt_raw = _read(receipt_path)
    receipt = json.loads(receipt_raw)
    if (_sha(receipt_raw) != active["verificationSha256"] or receipt["manifestSha256"] != manifest_sha
            or any(receipt["storage"].get(k) != v for k, v in storage.items())):
        raise ValueError("course_storage_media_not_verified")
    files = []
    for entry in json.loads(raw)["files"]:
        obj = receipt["blobs"][entry["objectKey"]]
        if any(obj[k] != entry[k] for k in ("sha256", "byteSize", "objectKey")):
            raise ValueError("course_storage_media_proof_changed")
        files.append({"sourcePath": entry["path"], **{k: entry[k] for k in ("sha256", "byteSize", "mimeType")},
            "locator": _object_locator(obj)})
    return {"scopeKey": _sha(("media:" + manifest_sha).encode()), "sourceKind": "published_media",
            "manifestSha256": manifest_sha, "sourceDigest": manifest_sha}, files
