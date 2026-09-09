from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class StudentLearningMediaRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def get_owned_pinned_session(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        session_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT session.*, package.status AS package_status,
              package.public_content_hash AS current_package_content_hash
            FROM learning_sessions AS session
            JOIN learning_lesson_packages AS package
              ON package.id = session.lesson_package_id
             AND package.version = session.lesson_package_version
             AND package.public_content_hash = session.lesson_package_content_hash
            WHERE session.id = ? AND session.family_id = ? AND session.child_id = ?
              AND package.status = 'published'
            LIMIT 1
            """,
            (session_id, family_id, child_id),
        ).fetchone()

    def list_session_assets(
        self,
        conn: DatabaseConnection,
        *,
        session: DatabaseRow,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT asset.id AS asset_id, asset.kind, asset.content_hash,
                  asset.mime_type, asset.byte_size, asset.duration_ms,
                  package_asset.scene_id, package_asset.usage_kind,
                  segment.id AS segment_id, segment.segment_index,
                  segment.action_id, segment.subtitle_text,
                  segment.language_code, segment.pronunciation_kind,
                  job.teacher_profile_id, job.teacher_profile_version,
                  variant.variant_key, variant.content_hash AS variant_content_hash,
                  variant.mime_type AS variant_mime_type,
                  variant.byte_size AS variant_byte_size,
                  variant.duration_ms AS variant_duration_ms
                FROM learning_lesson_package_assets AS package_asset
                JOIN learning_media_assets AS asset
                  ON asset.id = package_asset.asset_id
                JOIN learning_narration_segments AS segment
                  ON segment.asset_id = asset.id
                 AND segment.scene_id = package_asset.scene_id
                JOIN learning_media_generation_jobs AS job
                  ON job.id = segment.job_id
                 AND job.package_id = package_asset.package_id
                 AND job.package_version = package_asset.package_version
                JOIN learning_media_asset_variants AS variant
                  ON variant.asset_id = asset.id
                 AND variant.status = 'ready'
                WHERE package_asset.package_id = ?
                  AND package_asset.package_version = ?
                  AND package_asset.required_asset = 1
                  AND package_asset.usage_kind = 'narration'
                  AND job.status = 'ready'
                  AND segment.status = 'ready'
                  AND asset.status = 'ready'
                  AND asset.scan_status = 'passed'
                  AND asset.moderation_status = 'passed'
                  AND asset.transcode_status IN ('passed', 'not_required')
                  AND NOT EXISTS (
                    SELECT 1 FROM learning_media_quality_reviews AS review
                    WHERE review.asset_id = asset.id
                      AND review.required_review = 1
                      AND review.status <> 'approved'
                  )
                ORDER BY segment.segment_index ASC, variant.variant_key ASC
                """,
                (
                    session["lesson_package_id"],
                    int(session["lesson_package_version"]),
                ),
            ).fetchall()
        )

    def authorize_asset_variant(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        asset_id: str,
        variant_key: str,
    ) -> DatabaseRow | None:
        """Resolve an asset only through an owned, pinned lesson session."""

        return conn.execute(
            """
            SELECT DISTINCT asset.id AS asset_id, asset.kind,
              asset.content_hash AS asset_content_hash,
              variant.variant_key, variant.storage_key,
              variant.content_hash, variant.mime_type, variant.byte_size,
              variant.duration_ms, segment.subtitle_text,
              segment.language_code, segment.pronunciation_kind,
              package_asset.scene_id, package_asset.usage_kind
            FROM learning_sessions AS session
            JOIN learning_lesson_packages AS package
              ON package.id = session.lesson_package_id
             AND package.version = session.lesson_package_version
             AND package.public_content_hash = session.lesson_package_content_hash
             AND package.status = 'published'
            JOIN learning_lesson_package_assets AS package_asset
              ON package_asset.package_id = package.id
             AND package_asset.package_version = package.version
             AND package_asset.asset_id = ?
             AND package_asset.required_asset = 1
             AND package_asset.usage_kind = 'narration'
            JOIN learning_media_assets AS asset
              ON asset.id = package_asset.asset_id
            JOIN learning_narration_segments AS segment
              ON segment.asset_id = asset.id
             AND segment.scene_id = package_asset.scene_id
            JOIN learning_media_generation_jobs AS job
              ON job.id = segment.job_id
             AND job.package_id = package.id
             AND job.package_version = package.version
             AND job.status = 'ready'
            JOIN learning_media_asset_variants AS variant
              ON variant.asset_id = asset.id
             AND variant.variant_key = ?
             AND variant.status = 'ready'
            WHERE session.family_id = ? AND session.child_id = ?
              AND segment.status = 'ready'
              AND asset.status = 'ready'
              AND asset.scan_status = 'passed'
              AND asset.moderation_status = 'passed'
              AND asset.transcode_status IN ('passed', 'not_required')
              AND NOT EXISTS (
                SELECT 1 FROM learning_media_quality_reviews AS review
                WHERE review.asset_id = asset.id
                  AND review.required_review = 1
                  AND review.status <> 'approved'
              )
            LIMIT 1
            """,
            (asset_id, variant_key, family_id, child_id),
        ).fetchone()
