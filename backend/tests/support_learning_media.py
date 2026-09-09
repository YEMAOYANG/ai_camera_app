from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any, Mapping

from core.database import Database
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    LearningMediaMaterializationService,
)
from services.lesson_package_service import (
    LessonPackageGenerationResult,
    LessonPackageService,
)
from tests.test_learning_teacher_media_assets import ContractFakeVoxCpmProvider


class AutoPublishingLessonPackageService:
    """Test-only helper that runs the real staged media lifecycle locally."""

    def __init__(self, database_url: str, *, adapter: Any):
        self._temporary = tempfile.TemporaryDirectory(prefix="mira-catalog-media-")
        self.media_service = LearningMediaMaterializationService(
            LearningTeacherMediaRepository(Database(database_url)),
            tts_provider=ContractFakeVoxCpmProvider(),
            asset_store=FilesystemLearningMediaAssetStore(
                Path(self._temporary.name)
            ),
        )
        self.delegate = LessonPackageService(
            database_url,
            adapter=adapter,
            media_service=self.media_service,
        )

    def enqueue(self, **kwargs) -> dict[str, Any]:
        return self.delegate.enqueue(**kwargs)

    def generate(
        self,
        data: Mapping[str, Any],
    ) -> LessonPackageGenerationResult:
        generated = self.delegate.generate(data)
        if generated.payload.get("status") != "media_pending":
            return generated

        media = self.media_service.materialize_job(
            job_id=str(generated.payload["media"]["id"])
        )
        if media.get("requiresManualReview"):
            for segment in media["segments"]:
                self.media_service.review_pronunciation_asset(
                    asset_id=str(segment["assetId"]),
                    approved=True,
                    reviewer_type="content_reviewer",
                    reviewer_id="catalog-test-reviewer",
                    findings={"pronunciationAccurate": True},
                )
        finalized = self.delegate.finalize_media_package(
            package_id=generated.payload["package"]["id"],
            package_version=generated.payload["package"]["version"],
        )
        if finalized.get("status") != "published":
            raise AssertionError(finalized)
        return self.delegate.generate(data)

    def close(self) -> None:
        self._temporary.cleanup()
