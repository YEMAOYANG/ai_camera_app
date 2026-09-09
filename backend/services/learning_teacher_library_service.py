from __future__ import annotations

from typing import Any, Protocol

from content.teacher_profiles import (
    SUPPORTED_TEACHER_SUBJECTS,
    TEACHER_PROFILES,
    TEACHER_REGISTRY_VERSION,
    get_teacher_profile,
    list_teacher_profiles,
)
from core.security import now_ms
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_materialization_service import (
    LearningMediaMaterializationError,
)


class LearningAssetDeliveryResolver(Protocol):
    def resolve(
        self,
        *,
        asset_id: str,
        storage_key: str,
        content_hash: str,
        mime_type: str,
    ) -> str:
        """Return a short-lived delivery URL for an already authorized student."""


class LearningTeacherLibraryService:
    """Student-facing read boundary for teachers and approved lesson media.

    Storage keys, voice prompts, provider configuration and review details are
    intentionally withheld.  A route may inject a signed URL resolver after it
    has authorized the student's lesson session.
    """

    def __init__(
        self,
        repository: LearningTeacherMediaRepository,
        *,
        delivery_resolver: LearningAssetDeliveryResolver | None = None,
    ):
        self.repository = repository
        self.delivery_resolver = delivery_resolver

    def sync_teacher_registry(self) -> None:
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            for profile in TEACHER_PROFILES:
                self.repository.sync_teacher_profile(conn, profile=profile, now=timestamp)

    def list_teachers(
        self,
        *,
        subject: str | None = None,
        family_id: str | None = None,
        child_id: str | None = None,
    ) -> dict[str, Any]:
        subject_code = str(subject or "").strip().lower()
        if subject_code and subject_code not in SUPPORTED_TEACHER_SUBJECTS:
            self._fail("invalid_subject", "subject must be chinese, math, or english")
        self.sync_teacher_registry()
        selected: dict[str, Any] | None = None
        if child_id or family_id:
            if not family_id or not child_id or not subject_code:
                self._fail(
                    "invalid_teacher_preference_scope",
                    "family, child and subject are required for a selected teacher",
                )
            with self.repository.transaction() as conn:
                if not self.repository.child_belongs_to_family(
                    conn,
                    family_id=str(family_id),
                    child_id=str(child_id),
                ):
                    self._fail("child_not_found", "Child profile was not found")
                preference = self.repository.get_teacher_preference(
                    conn,
                    family_id=str(family_id),
                    child_id=str(child_id),
                    subject=subject_code,
                )
            if preference:
                selected = {
                    "id": str(preference["teacher_profile_id"]),
                    "version": int(preference["teacher_profile_version"]),
                }
        profiles = list_teacher_profiles(subject=subject_code or None)
        return {
            "registryVersion": TEACHER_REGISTRY_VERSION,
            "items": [profile.to_public_payload() for profile in profiles],
            "selected": selected,
        }

    def set_teacher_preference(
        self,
        *,
        family_id: str,
        child_id: str,
        subject: str,
        teacher_profile_id: str,
        teacher_profile_version: int | None = None,
        updated_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        subject_code = str(subject or "").strip().lower()
        try:
            profile = get_teacher_profile(teacher_profile_id, teacher_profile_version)
        except KeyError as exc:
            raise LearningMediaMaterializationError(
                "teacher_profile_not_found",
                "The selected teacher is unavailable",
            ) from exc
        if profile.subject != subject_code:
            self._fail(
                "teacher_subject_mismatch",
                "The selected teacher does not teach this subject",
            )
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            if not self.repository.child_belongs_to_family(
                conn,
                family_id=str(family_id),
                child_id=str(child_id),
            ):
                self._fail("child_not_found", "Child profile was not found")
            self.repository.sync_teacher_profile(conn, profile=profile, now=timestamp)
            preference = self.repository.set_teacher_preference(
                conn,
                family_id=str(family_id),
                child_id=str(child_id),
                subject=subject_code,
                profile_id=profile.profile_id,
                profile_version=profile.version,
                updated_by_user_id=(
                    str(updated_by_user_id).strip() if updated_by_user_id else None
                ),
                now=timestamp,
            )
        return {
            "childId": str(preference["child_id"]),
            "subject": str(preference["subject"]),
            "teacher": profile.to_public_payload(),
            "updatedAt": int(preference["updated_at"]),
        }

    def list_ready_assets(
        self,
        *,
        package_id: str,
        package_version: int,
        scene_id: str | None = None,
    ) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            rows = self.repository.list_ready_assets(
                conn,
                package_id=str(package_id),
                package_version=int(package_version),
                scene_id=str(scene_id) if scene_id else None,
            )
        return {
            "package": {"id": str(package_id), "version": int(package_version)},
            "sceneId": str(scene_id) if scene_id else None,
            "items": [self._public_asset(row) for row in rows],
        }

    def _public_asset(self, row: dict[str, Any]) -> dict[str, Any]:
        variants: list[dict[str, Any]] = []
        for variant in row.get("variants") or []:
            delivery_url = None
            if self.delivery_resolver is not None:
                delivery_url = self.delivery_resolver.resolve(
                    asset_id=str(row["id"]),
                    storage_key=str(variant["storage_key"]),
                    content_hash=str(variant["content_hash"]),
                    mime_type=str(variant["mime_type"]),
                )
            variants.append(
                {
                    "key": str(variant["variant_key"]),
                    "mimeType": str(variant["mime_type"]),
                    "byteSize": int(variant["byte_size"]),
                    "durationMs": variant.get("duration_ms"),
                    "checksum": str(variant["content_hash"]),
                    "deliveryUrl": delivery_url,
                }
            )
        return {
            "assetId": str(row["id"]),
            "kind": str(row["kind"]),
            "sceneId": row.get("scene_id"),
            "actionId": row.get("action_id"),
            "segmentIndex": int(row["segment_index"]),
            "subtitle": str(row["subtitle_text"]),
            "languageCode": str(row["language_code"]),
            "pronunciationKind": str(row["pronunciation_kind"]),
            "teacherProfile": {
                "id": str(row["teacher_profile_id"]),
                "version": int(row["teacher_profile_version"]),
            },
            "checksum": str(row["content_hash"]),
            "mimeType": str(row["mime_type"]),
            "durationMs": row.get("duration_ms"),
            "variants": variants,
        }

    @staticmethod
    def _fail(code: str, safe_message: str) -> None:
        raise LearningMediaMaterializationError(code, safe_message)
