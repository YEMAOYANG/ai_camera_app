"""Pure local preflight for original videos supplied to private authoring.

This validates immutable bytes and their declared scope, never pedagogy,
pronunciation, rights clearance, codec playback or publication. Recheck before
any dispatch so a stale receipt cannot silently buy replacement media.
"""
from pathlib import Path
import hashlib
import json
import re
from services.course_file_store import course_bytes, course_exists, course_stat

from content.textbook_release_media import media_mime_type, MAX_MEDIA_BYTES

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "output"
STORE_ROOT = ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/classrooms"
SHA = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[a-z][a-z0-9_-]{0,79}\Z")


def _require(ok, message):
    if not ok:
        raise ValueError("provided_media_" + message)


def _file(path, expected, allowed_root):
    _require(isinstance(path, str) and isinstance(expected, str) and SHA.fullmatch(expected), "file_identity_invalid")
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    resolved = candidate.resolve()
    _require(not candidate.is_symlink() and resolved.is_relative_to(allowed_root.resolve())
             and course_exists(resolved), "file_outside_owned_store")
    _require(course_stat(resolved).st_size <= MAX_MEDIA_BYTES, "file_too_large")
    raw = course_bytes(resolved, max_bytes=MAX_MEDIA_BYTES)
    _require(hashlib.sha256(raw).hexdigest() == expected, "file_hash_changed")
    return raw


def validate_provided_media(design, *, task_id, binding):
    if not isinstance(design, dict) or "providedMediaAssets" not in design:
        return []
    assets = design["providedMediaAssets"]
    _require(isinstance(assets, list) and 1 <= len(assets) <= 4, "asset_list_invalid")
    seen = set()
    for asset in assets:
        _require(isinstance(asset, dict) and asset.get("taskId") == task_id
                 and asset.get("binding") == binding, "scope_changed")
        asset_id = asset.get("assetId")
        _require(isinstance(asset_id, str) and ID.fullmatch(asset_id) and asset_id not in seen, "asset_identity_invalid")
        seen.add(asset_id)
        _require(asset.get("kind") == "video" and asset.get("mimeType") == "video/mp4"
                 and asset.get("originality") == "original_programmatic_animation", "asset_kind_invalid")
        owner = "tbmedia_" + task_id[:12]
        expected_src = f"/api/classroom-media/{owner}/media/{asset_id}-{str(asset.get('sha256'))[:16]}.mp4"
        _require(asset.get("src") == expected_src, "url_not_task_bound")
        raw = _file(asset.get("localPath"), asset.get("sha256"), OUTPUT_ROOT)
        _require(type(asset.get("bytes")) is int and asset["bytes"] == len(raw), "byte_size_changed")
        _require(media_mime_type(".mp4", raw) == "video/mp4", "container_invalid")
        installed = _file(str(STORE_ROOT / owner / "media" / expected_src.rsplit('/', 1)[1]),
                          asset["sha256"], STORE_ROOT)
        _require(installed == raw, "installed_copy_changed")
        receipt_raw = _file(asset.get("receiptPath"), asset.get("receiptSha256"), OUTPUT_ROOT)
        receipt = json.loads(receipt_raw)
        _require(receipt.get("schemaVersion") == "mira.textbook.provided-video-receipt.v1"
                 and receipt.get("taskId") == task_id and receipt.get("binding") == binding
                 and receipt.get("assetId") == asset_id and receipt.get("sha256") == asset["sha256"]
                 and receipt.get("bytes") == len(raw) and receipt.get("mimeType") == "video/mp4"
                 and receipt.get("src") == expected_src and receipt.get("httpReadbackVerified") is True,
                 "receipt_changed")
        _file(receipt.get("rendererPath"), receipt.get("rendererSha256"), OUTPUT_ROOT)
        probe = receipt.get("probe", {})
        _require(probe.get("codec") == "h264" and type(probe.get("durationMs")) is int
                 and 1000 <= probe["durationMs"] <= 60000
                 and type(probe.get("width")) is int and 320 <= probe["width"] <= 1920
                 and type(probe.get("height")) is int and 180 <= probe["height"] <= 1080,
                 "codec_receipt_invalid")
    return assets


def validate_frozen_provided_media(frozen):
    return validate_provided_media(frozen.get("activityDesign"), task_id=frozen["taskId"], binding=frozen["binding"])
