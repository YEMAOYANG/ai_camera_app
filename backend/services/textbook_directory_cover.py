"""Derive a directory cover from a published classroom's archived opening art."""
import hashlib
from pathlib import Path
import re

from core.errors import ApiError
from services.course_file_store import CourseFileStore
from services.courseware_asset_store import CoursewareAssetNotFound
from services.textbook_cover_guard import MEDIA_PATH, cover_bytes
from services.textbook_directory_access import published_release


ASSET_PATH = re.compile(r"textbooks/course-covers-v2/([a-f0-9]{64})\.webp\Z")
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


def read_directory_cover(repo, content_key, *, store=None):
    with repo.transaction() as conn:
        build = repo.get_build(conn, content_key)
        if not build or build["status"] != "published" or build["part_index"] != 1:
            raise CoursewareAssetNotFound("Published classroom cover is not available")
        revision = repo.get_revision(conn, build["edition_id"], build["revision_id"])
        if revision is None:
            raise CoursewareAssetNotFound("Published classroom cover is not available")
        try:
            _, release, _, _ = published_release(repo, conn, content_key, {"grade_code": revision["grade_code"]})
        except ApiError:
            raise CoursewareAssetNotFound("Published classroom cover is not available") from None

    opening = next((scene for scene in release["classroom"]["scenes"] if scene.get("type") == "slide"), {})
    images = {asset["path"]: asset for asset in release["media"] if asset.get("mimeType") in IMAGE_TYPES}
    for element in opening.get("content", {}).get("canvas", {}).get("elements", []):
        if element.get("type") != "image":
            continue
        url = element.get("src")
        match = MEDIA_PATH.fullmatch(url) if isinstance(url, str) else None
        if match is None or match[1] != release["classroomId"] or url not in images:
            continue
        asset = images[url]
        reader = store if store is not None else CourseFileStore()
        path = Path("openmaic-runtime/.runtime/OpenMAIC/data/classrooms") / match[1] / "media" / match[2]
        source = reader.read_bytes(reader.project_root / path, expected_sha256=asset["sha256"],
                                   expected_bytes=asset["byteSize"], max_bytes=8 * 1024 * 1024)
        if source is None:
            continue
        body = cover_bytes(source)
        checksum = hashlib.sha256(body).hexdigest()
        return {"mimeType": "image/webp", "sha256": checksum, "etag": f'"{checksum}"'}, body
    raise CoursewareAssetNotFound("Published classroom cover is not available")
