from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any

from core.database import Database
from core.errors import ApiError
from repositories.student_learning_media_repository import (
    StudentLearningMediaRepository,
)
from services.student_auth_service import StudentAuthService


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_AUDIO_MIME_TYPES = frozenset(
    {"audio/wav", "audio/mpeg", "audio/flac", "audio/ogg", "audio/webm"}
)
_MAX_DELIVERY_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class AuthorizedLearningAsset:
    path: Path
    mime_type: str
    content_hash: str
    byte_size: int
    download_name: str


class StudentLearningMediaService:
    """Authorize private lesson media through a student's pinned session."""

    def __init__(
        self,
        database_url: str | Path,
        *,
        student_auth_service: StudentAuthService,
        storage_root: str | Path,
    ):
        self.student_auth_service = student_auth_service
        self.repository = StudentLearningMediaRepository(Database(database_url))
        self.storage_root = Path(storage_root).expanduser().resolve()

    def session_manifest(self, access_token: str, session_id: object) -> dict[str, Any]:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        normalized_session_id = self._identifier(session_id, "session")
        with self.repository.transaction() as conn:
            session = self.repository.get_owned_pinned_session(
                conn,
                family_id=str(principal["family_id"]),
                child_id=str(principal["child_id"]),
                session_id=normalized_session_id,
            )
            if session is None:
                raise ApiError(
                    "learning_session_not_found",
                    "学习记录不存在",
                    404,
                )
            rows = self.repository.list_session_assets(conn, session=session)
        by_asset: dict[str, dict[str, Any]] = {}
        for row in rows:
            asset_id = str(row["asset_id"])
            item = by_asset.setdefault(
                asset_id,
                {
                    "id": asset_id,
                    "kind": str(row["kind"]),
                    "sceneId": str(row["scene_id"]),
                    "actionId": row.get("action_id"),
                    "usageKind": str(row["usage_kind"]),
                    "subtitle": str(row["subtitle_text"]),
                    "languageCode": str(row["language_code"]),
                    "pronunciationKind": str(row["pronunciation_kind"]),
                    "teacherProfile": {
                        "id": str(row["teacher_profile_id"]),
                        "version": int(row["teacher_profile_version"]),
                    },
                    "contentHash": str(row["content_hash"]),
                    "mimeType": str(row["mime_type"]),
                    "byteSize": int(row["byte_size"]),
                    "durationMs": row.get("duration_ms"),
                    "deliveryPath": f"/api/v2/student/learning/assets/{asset_id}",
                    "variants": [],
                },
            )
            item["variants"].append(
                {
                    "key": str(row["variant_key"]),
                    "contentHash": str(row["variant_content_hash"]),
                    "mimeType": str(row["variant_mime_type"]),
                    "byteSize": int(row["variant_byte_size"]),
                    "durationMs": row.get("variant_duration_ms"),
                    "deliveryPath": (
                        f"/api/v2/student/learning/assets/{asset_id}"
                        if str(row["variant_key"]) == "original"
                        else f"/api/v2/student/learning/assets/{asset_id}"
                        f"?variant={row['variant_key']}"
                    ),
                }
            )
        return {
            "ok": True,
            "sessionId": normalized_session_id,
            "package": {
                "id": str(session["lesson_package_id"]),
                "version": int(session["lesson_package_version"]),
                "contentHash": str(session["lesson_package_content_hash"]),
            },
            "assets": list(by_asset.values()),
        }

    def authorize_asset(
        self,
        access_token: str,
        asset_id: object,
        *,
        variant_key: object = "original",
    ) -> AuthorizedLearningAsset:
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        normalized_asset_id = self._identifier(asset_id, "asset")
        normalized_variant = self._identifier(variant_key or "original", "variant")
        with self.repository.transaction() as conn:
            row = self.repository.authorize_asset_variant(
                conn,
                family_id=str(principal["family_id"]),
                child_id=str(principal["child_id"]),
                asset_id=normalized_asset_id,
                variant_key=normalized_variant,
            )
        if row is None:
            raise ApiError(
                "learning_asset_not_found",
                "课程素材不存在或尚未通过审核",
                404,
            )
        mime_type = str(row["mime_type"]).split(";", 1)[0].strip().lower()
        if mime_type not in _AUDIO_MIME_TYPES or str(row["kind"]) != "audio":
            raise ApiError("learning_asset_unavailable", "课程素材不可用", 404)
        byte_size = int(row["byte_size"])
        if byte_size < 1 or byte_size > _MAX_DELIVERY_BYTES:
            raise ApiError("learning_asset_unavailable", "课程素材不可用", 404)
        content_hash = str(row["content_hash"] or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ApiError("learning_asset_unavailable", "课程素材不可用", 404)
        path = self._safe_storage_path(str(row["storage_key"] or ""))
        try:
            stat = path.stat()
        except OSError as exc:
            raise ApiError(
                "learning_asset_storage_missing",
                "课程素材暂时不可用",
                503,
            ) from exc
        if not path.is_file() or stat.st_size != byte_size:
            raise ApiError(
                "learning_asset_integrity_failed",
                "课程素材完整性校验失败",
                503,
            )
        digest = hashlib.sha256()
        try:
            with path.open("rb") as media_file:
                for chunk in iter(lambda: media_file.read(64 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ApiError(
                "learning_asset_storage_missing",
                "课程素材暂时不可用",
                503,
            ) from exc
        if digest.hexdigest() != content_hash:
            raise ApiError(
                "learning_asset_integrity_failed",
                "课程素材完整性校验失败",
                503,
            )
        return AuthorizedLearningAsset(
            path=path,
            mime_type=mime_type,
            content_hash=content_hash,
            byte_size=byte_size,
            download_name=f"{normalized_asset_id}{path.suffix.lower()}",
        )

    def _safe_storage_path(self, storage_key: str) -> Path:
        key = str(storage_key or "").strip()
        pure = PurePosixPath(key)
        if (
            not key
            or pure.is_absolute()
            or ".." in pure.parts
            or "." in pure.parts
            or "\\" in key
        ):
            raise ApiError("learning_asset_unavailable", "课程素材不可用", 404)
        try:
            candidate = self.storage_root.joinpath(*pure.parts).resolve(strict=True)
        except OSError as exc:
            raise ApiError(
                "learning_asset_storage_missing",
                "课程素材暂时不可用",
                503,
            ) from exc
        if candidate == self.storage_root or self.storage_root not in candidate.parents:
            raise ApiError("learning_asset_unavailable", "课程素材不可用", 404)
        return candidate

    @staticmethod
    def _identifier(value: object, label: str) -> str:
        normalized = str(value or "").strip()
        if not _ID_PATTERN.fullmatch(normalized):
            raise ApiError(f"invalid_{label}_id", f"{label} id 无效")
        return normalized
