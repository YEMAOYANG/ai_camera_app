from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import re
from typing import Any, Iterator, Mapping, Sequence
import uuid

from content.teacher_profiles import FormalSubjectQwenVoiceIdentity, TeacherProfile
from core.database import Database, DatabaseConnection, DatabaseRow
from services.learning_curriculum_preparation_contract import (
    preparation_target_fingerprint,
)


class LearningTeacherMediaRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def sync_teacher_profile(
        self,
        conn: DatabaseConnection,
        *,
        profile: TeacherProfile,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_teacher_profiles(
              id, version, display_name, avatar_path, subject, language_code,
              teaching_style, provider_id, provider_model, voice_mode,
              voice_prompt, capabilities_json, clone_allowed, status,
              content_hash, published_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                profile.profile_id,
                profile.version,
                profile.display_name,
                profile.avatar_path,
                profile.subject,
                profile.language_code,
                profile.teaching_style,
                profile.provider_id,
                profile.provider_model,
                profile.voice_mode,
                profile.voice_prompt,
                self.encode_json(profile.capabilities),
                profile.content_hash,
                now,
                now,
                now,
            ),
        )
        row = self.get_teacher_profile(
            conn,
            profile_id=profile.profile_id,
            version=profile.version,
        )
        if row is None or str(row["content_hash"]) != profile.content_hash:
            raise ValueError(
                "teacher profile versions are immutable; increment the registry version"
            )
        if bool(row.get("clone_allowed")) or str(row.get("voice_mode")) != "prompt":
            raise ValueError("persisted teacher profile violates the no-clone policy")
        return row

    def get_teacher_profile(
        self,
        conn: DatabaseConnection,
        *,
        profile_id: str,
        version: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_teacher_profiles
            WHERE id = ? AND version = ? LIMIT 1
            """,
            (profile_id, version),
        ).fetchone()

    def list_active_teacher_profiles(
        self,
        conn: DatabaseConnection,
        *,
        subject: str | None = None,
    ) -> list[DatabaseRow]:
        if subject:
            return list(
                conn.execute(
                    """
                    SELECT * FROM learning_teacher_profiles
                    WHERE status = 'active' AND subject = ?
                    ORDER BY display_name ASC, version DESC
                    """,
                    (subject,),
                ).fetchall()
            )
        return list(
            conn.execute(
                """
                SELECT * FROM learning_teacher_profiles
                WHERE status = 'active'
                ORDER BY subject ASC, display_name ASC, version DESC
                """
            ).fetchall()
        )

    def child_belongs_to_family(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
    ) -> bool:
        return (
            conn.execute(
                """
                SELECT id FROM children
                WHERE id = ? AND family_id = ? LIMIT 1
                """,
                (child_id, family_id),
            ).fetchone()
            is not None
        )

    def get_teacher_preference(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        subject: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT preference.*, profile.display_name, profile.language_code,
              profile.teaching_style, profile.capabilities_json,
              profile.status AS teacher_status
            FROM learning_student_teacher_preferences AS preference
            JOIN learning_teacher_profiles AS profile
              ON profile.id = preference.teacher_profile_id
             AND profile.version = preference.teacher_profile_version
            WHERE preference.family_id = ? AND preference.child_id = ?
              AND preference.subject = ?
            LIMIT 1
            """,
            (family_id, child_id, subject),
        ).fetchone()

    def set_teacher_preference(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        subject: str,
        profile_id: str,
        profile_version: int,
        updated_by_user_id: str | None,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            INSERT INTO learning_student_teacher_preferences(
              family_id, child_id, subject, teacher_profile_id,
              teacher_profile_version, updated_by_user_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE
              teacher_profile_id = VALUES(teacher_profile_id),
              teacher_profile_version = VALUES(teacher_profile_version),
              updated_by_user_id = VALUES(updated_by_user_id),
              updated_at = VALUES(updated_at)
            """,
            (
                family_id,
                child_id,
                subject,
                profile_id,
                profile_version,
                updated_by_user_id,
                now,
                now,
            ),
        )
        return self.get_teacher_preference(
            conn,
            family_id=family_id,
            child_id=child_id,
            subject=subject,
        )

    def create_or_get_media_job(
        self,
        conn: DatabaseConnection,
        *,
        idempotency_key: str,
        request_hash: str,
        package_id: str | None,
        package_version: int | None,
        course_id: str | None,
        course_version: str | None,
        subject: str,
        language_code: str,
        pronunciation_kind: str,
        profile: TeacherProfile,
        provider_id: str,
        provider_model: str,
        segment_count: int,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        job_id = f"media_job_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO learning_media_generation_jobs(
              id, idempotency_key, request_hash, package_id, package_version,
              course_id, course_version, subject, language_code,
              pronunciation_kind, teacher_profile_id,
              teacher_profile_version, provider_id, provider_model, status,
              segment_count, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                job_id,
                idempotency_key,
                request_hash,
                package_id,
                package_version,
                course_id,
                course_version,
                subject,
                language_code,
                pronunciation_kind,
                profile.profile_id,
                profile.version,
                provider_id,
                provider_model,
                segment_count,
                now,
                now,
            ),
        )
        row = self.get_job_by_idempotency_key(
            conn,
            idempotency_key=idempotency_key,
            for_update=True,
        )
        if row is None:
            raise RuntimeError("media job could not be created")
        return row, str(row["id"]) == job_id

    def create_narration_segments(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        segments: Sequence[Mapping[str, Any]],
        language_code: str,
        pronunciation_kind: str,
        review_policy: str,
        now: int,
    ) -> None:
        for index, segment in enumerate(segments):
            conn.execute(
                """
                INSERT INTO learning_narration_segments(
                  id, job_id, segment_index, scene_id, action_id, source_text,
                  subtitle_text, text_hash, language_code,
                  pronunciation_kind, review_policy, status, created_at,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    f"narration_{uuid.uuid4().hex}",
                    job_id,
                    index,
                    segment.get("sceneId"),
                    segment.get("actionId"),
                    segment["text"],
                    segment["subtitle"],
                    segment["textHash"],
                    language_code,
                    pronunciation_kind,
                    review_policy,
                    now,
                    now,
                ),
            )

    def get_job_by_idempotency_key(
        self,
        conn: DatabaseConnection,
        *,
        idempotency_key: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            """
            SELECT * FROM learning_media_generation_jobs
            WHERE idempotency_key = ? LIMIT 1
            """
            + lock,
            (idempotency_key,),
        ).fetchone()

    def get_media_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            "SELECT * FROM learning_media_generation_jobs WHERE id = ? LIMIT 1" + lock,
            (job_id,),
        ).fetchone()

    def get_media_job_by_asset(
        self,
        conn: DatabaseConnection,
        *,
        asset_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT job.*
            FROM learning_narration_segments AS segment
            JOIN learning_media_generation_jobs AS job ON job.id = segment.job_id
            WHERE segment.asset_id = ?
            LIMIT 1
            """,
            (asset_id,),
        ).fetchone()

    def list_package_media_jobs(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM learning_media_generation_jobs
                WHERE package_id = ? AND package_version = ?
                ORDER BY created_at ASC, id ASC
                """,
                (package_id, package_version),
            ).fetchall()
        )

    def get_next_pending_job(self, conn: DatabaseConnection) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM learning_media_generation_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC LIMIT 1
            """
        ).fetchone()

    def list_narration_segments(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT * FROM learning_narration_segments
                WHERE job_id = ? ORDER BY segment_index ASC
                """,
                (job_id,),
            ).fetchall()
        )

    def claim_media_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        now: int,
    ) -> bool:
        cursor = conn.execute(
            """
            UPDATE learning_media_generation_jobs
            SET status = 'generating', started_at = COALESCE(started_at, ?),
              error_code = NULL, error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, now, job_id),
        )
        return cursor.rowcount == 1

    def mark_segment_generating(
        self,
        conn: DatabaseConnection,
        *,
        segment_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_narration_segments
            SET status = 'generating', error_code = NULL,
              error_message_safe = NULL, updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, segment_id),
        )

    def register_segment_asset(
        self,
        conn: DatabaseConnection,
        *,
        job: Mapping[str, Any],
        segment: Mapping[str, Any],
        storage_key: str,
        content_hash: str,
        mime_type: str,
        byte_size: int,
        duration_ms: int | None,
        requires_manual_review: bool,
        now: int,
    ) -> DatabaseRow:
        package_id = job.get("package_id")
        package_version = job.get("package_version")
        scene_id = segment.get("scene_id")
        if package_id is not None and (package_version is None or not scene_id):
            raise ValueError(
                "package narration assets require package version and scene id"
            )
        asset_id = f"media_asset_{uuid.uuid4().hex}"
        asset_status = "review_pending" if requires_manual_review else "ready"
        metadata = {
            "schemaVersion": "mira.learning.narration-asset.v1",
            "jobId": str(job["id"]),
            "segmentId": str(segment["id"]),
            "teacherProfile": {
                "id": str(job["teacher_profile_id"]),
                "version": int(job["teacher_profile_version"]),
            },
            "languageCode": str(segment["language_code"]),
            "pronunciationKind": str(segment["pronunciation_kind"]),
            "subtitle": str(segment["subtitle_text"]),
        }
        conn.execute(
            """
            INSERT INTO learning_media_assets(
              id, kind, storage_key, content_hash, mime_type, byte_size,
              duration_ms, scan_status, moderation_status, transcode_status,
              status, source_type, source_ref, metadata_json, created_at,
              updated_at
            )
            VALUES (?, 'audio', ?, ?, ?, ?, ?, 'passed', 'passed',
              'not_required', ?, 'server_tts', ?, ?, ?, ?)
            """,
            (
                asset_id,
                storage_key,
                content_hash,
                mime_type,
                byte_size,
                duration_ms,
                asset_status,
                f"{job['id']}:{segment['id']}",
                self.encode_json(metadata),
                now,
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO learning_media_asset_variants(
              asset_id, variant_key, storage_key, content_hash, mime_type,
              byte_size, duration_ms, status, created_at, updated_at
            )
            VALUES (?, 'original', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                storage_key,
                content_hash,
                mime_type,
                byte_size,
                duration_ms,
                asset_status,
                now,
                now,
            ),
        )
        review_kind = (
            "manual_pronunciation" if requires_manual_review else "automated_integrity"
        )
        review_status = "pending" if requires_manual_review else "approved"
        reviewer_type = None if requires_manual_review else "system"
        reviewed_at = None if requires_manual_review else now
        conn.execute(
            """
            INSERT INTO learning_media_quality_reviews(
              id, asset_id, review_kind, required_review, status,
              reviewer_type, findings_json, reviewed_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"media_review_{uuid.uuid4().hex}",
                asset_id,
                review_kind,
                review_status,
                reviewer_type,
                self.encode_json(
                    {
                        "checksumVerified": True,
                        "mimeTypeVerified": True,
                        "manualPronunciationRequired": requires_manual_review,
                    }
                ),
                reviewed_at,
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE learning_narration_segments
            SET status = ?, asset_id = ?, audio_checksum = ?, duration_ms = ?,
              updated_at = ?
            WHERE id = ?
            """,
            (
                "awaiting_review" if requires_manual_review else "ready",
                asset_id,
                content_hash,
                duration_ms,
                now,
                segment["id"],
            ),
        )
        conn.execute(
            """
            UPDATE learning_media_generation_jobs
            SET asset_count = asset_count + 1, updated_at = ? WHERE id = ?
            """,
            (now, job["id"]),
        )
        package_exists = (
            conn.execute(
                """
                SELECT 1 FROM learning_lesson_packages
                WHERE id = ? AND version = ? LIMIT 1
                """,
                (package_id, int(package_version)),
            ).fetchone()
            if package_id is not None
            else None
        )
        if package_exists is not None:
            conn.execute(
                """
                INSERT INTO learning_lesson_package_assets(
                  package_id, package_version, asset_id, scene_id,
                  usage_kind, required_asset
                )
                VALUES (?, ?, ?, ?, 'narration', 1)
                """,
                (
                    package_id,
                    int(package_version),
                    asset_id,
                    scene_id,
                ),
            )
        return conn.execute(
            "SELECT * FROM learning_media_assets WHERE id = ? LIMIT 1",
            (asset_id,),
        ).fetchone()

    def finish_media_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        requires_manual_review: bool,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE learning_media_generation_jobs
            SET status = ?, completed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'generating'
            """,
            ("awaiting_review" if requires_manual_review else "ready", now, now, job_id),
        )

    def fail_media_job(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        segment_id: str | None,
        error_code: str,
        error_message_safe: str,
        now: int,
    ) -> None:
        if segment_id:
            conn.execute(
                """
                UPDATE learning_narration_segments
                SET status = 'failed', error_code = ?, error_message_safe = ?,
                  updated_at = ? WHERE id = ?
                """,
                (error_code, error_message_safe[:512], now, segment_id),
            )
        conn.execute(
            """
            UPDATE learning_media_generation_jobs
            SET status = 'failed', error_code = ?, error_message_safe = ?,
              completed_at = ?, updated_at = ? WHERE id = ?
            """,
            (error_code, error_message_safe[:512], now, now, job_id),
        )

    def review_asset(
        self,
        conn: DatabaseConnection,
        *,
        asset_id: str,
        approved: bool,
        reviewer_type: str,
        reviewer_id: str,
        notes: str,
        findings: Mapping[str, Any],
        now: int,
    ) -> DatabaseRow | None:
        review = conn.execute(
            """
            SELECT * FROM learning_media_quality_reviews
            WHERE asset_id = ? AND review_kind = 'manual_pronunciation'
            LIMIT 1 FOR UPDATE
            """,
            (asset_id,),
        ).fetchone()
        if review is None:
            return None
        status = "approved" if approved else "rejected"
        merged_findings = self.decode_json(review.get("findings_json"), {})
        if not isinstance(merged_findings, dict):
            merged_findings = {}
        merged_findings.update(dict(findings))
        merged_findings["manualPronunciationApproved"] = bool(approved)
        conn.execute(
            """
            UPDATE learning_media_quality_reviews
            SET status = ?, reviewer_type = ?, reviewer_id = ?,
              findings_json = ?, notes = ?, reviewed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                reviewer_type,
                reviewer_id,
                self.encode_json(merged_findings),
                notes or None,
                now,
                now,
                review["id"],
            ),
        )
        if approved:
            pending = conn.execute(
                """
                SELECT COUNT(*) AS total FROM learning_media_quality_reviews
                WHERE asset_id = ? AND required_review = 1
                  AND status <> 'approved'
                """,
                (asset_id,),
            ).fetchone()
            if int((pending or {}).get("total") or 0) == 0:
                conn.execute(
                    """
                    UPDATE learning_media_assets
                    SET status = 'ready', updated_at = ? WHERE id = ?
                    """,
                    (now, asset_id),
                )
                conn.execute(
                    """
                    UPDATE learning_media_asset_variants
                    SET status = 'ready', updated_at = ? WHERE asset_id = ?
                    """,
                    (now, asset_id),
                )
                conn.execute(
                    """
                    UPDATE learning_narration_segments
                    SET status = 'ready', updated_at = ? WHERE asset_id = ?
                    """,
                    (now, asset_id),
                )
        else:
            conn.execute(
                """
                UPDATE learning_media_assets
                SET status = 'rejected', updated_at = ? WHERE id = ?
                """,
                (now, asset_id),
            )
            conn.execute(
                """
                UPDATE learning_media_asset_variants
                SET status = 'rejected', updated_at = ? WHERE asset_id = ?
                """,
                (now, asset_id),
            )
            conn.execute(
                """
                UPDATE learning_narration_segments
                SET status = 'rejected', updated_at = ? WHERE asset_id = ?
                """,
                (now, asset_id),
            )
        job_row = conn.execute(
            """
            SELECT job.id
            FROM learning_narration_segments AS segment
            JOIN learning_media_generation_jobs AS job ON job.id = segment.job_id
            WHERE segment.asset_id = ? LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if job_row:
            self._refresh_job_review_status(conn, job_id=str(job_row["id"]), now=now)
        return conn.execute(
            "SELECT * FROM learning_media_assets WHERE id = ? LIMIT 1",
            (asset_id,),
        ).fetchone()

    def _refresh_job_review_status(
        self,
        conn: DatabaseConnection,
        *,
        job_id: str,
        now: int,
    ) -> None:
        counts = conn.execute(
            """
            SELECT
              SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
              SUM(CASE WHEN status <> 'ready' THEN 1 ELSE 0 END) AS unfinished
            FROM learning_narration_segments WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        rejected = int((counts or {}).get("rejected") or 0)
        unfinished = int((counts or {}).get("unfinished") or 0)
        if rejected:
            status = "rejected"
        elif unfinished:
            status = "awaiting_review"
        else:
            status = "ready"
        conn.execute(
            """
            UPDATE learning_media_generation_jobs
            SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?
            """,
            (status, now, now, job_id),
        )

    def list_ready_assets(
        self,
        conn: DatabaseConnection,
        *,
        package_id: str,
        package_version: int,
        scene_id: str | None = None,
    ) -> list[dict[str, Any]]:
        scene_filter = " AND segment.scene_id = ?" if scene_id else ""
        params: list[Any] = [package_id, package_version]
        if scene_id:
            params.append(scene_id)
        rows = conn.execute(
            """
            SELECT asset.*, segment.id AS segment_id,
              segment.segment_index, segment.scene_id, segment.action_id,
              segment.subtitle_text, segment.language_code,
              segment.pronunciation_kind, job.teacher_profile_id,
              job.teacher_profile_version
            FROM learning_media_generation_jobs AS job
            JOIN learning_narration_segments AS segment ON segment.job_id = job.id
            JOIN learning_media_assets AS asset ON asset.id = segment.asset_id
            WHERE job.package_id = ? AND job.package_version = ?
              AND job.status = 'ready' AND segment.status = 'ready'
              AND asset.status = 'ready' AND asset.scan_status = 'passed'
              AND asset.moderation_status = 'passed'
              AND asset.transcode_status IN ('passed', 'not_required')
              AND NOT EXISTS (
                SELECT 1 FROM learning_media_quality_reviews AS review
                WHERE review.asset_id = asset.id AND review.required_review = 1
                  AND review.status <> 'approved'
              )
            """
            + scene_filter
            + " ORDER BY segment.segment_index ASC",
            params,
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            variants = conn.execute(
                """
                SELECT variant_key, storage_key, content_hash, mime_type,
                  byte_size, duration_ms, status
                FROM learning_media_asset_variants
                WHERE asset_id = ? AND status = 'ready'
                ORDER BY variant_key ASC
                """,
                (row["id"],),
            ).fetchall()
            item["variants"] = [dict(variant) for variant in variants]
            results.append(item)
        return results

    def get_formal_audio_job(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            "SELECT * FROM learning_formal_qwen_audio_jobs "
            "WHERE build_item_id = ? LIMIT 1" + lock,
            (build_item_id,),
        ).fetchone()

    def get_formal_audio_segment(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            "SELECT * FROM learning_formal_qwen_audio_segment_receipts "
            "WHERE build_item_id = ? AND scene_order = ? LIMIT 1" + lock,
            (build_item_id, int(scene_order)),
        ).fetchone()

    def list_formal_audio_segments(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        for_update: bool = False,
    ) -> list[DatabaseRow]:
        lock = " FOR UPDATE" if for_update else ""
        return list(
            conn.execute(
                "SELECT * FROM learning_formal_qwen_audio_segment_receipts "
                "WHERE build_item_id = ? ORDER BY scene_order" + lock,
                (build_item_id,),
            ).fetchall()
        )

    def get_next_unreserved_formal_audio_authority(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str | None = None,
        release_id: str | None = None,
        target_fingerprint: str | None = None,
    ) -> DatabaseRow | None:
        """Return one current Task-13 classroom that still needs its sidecar."""

        scoped = any(
            value is not None
            for value in (build_id, release_id, target_fingerprint)
        )
        if scoped and not all(
            isinstance(value, str) and bool(value)
            for value in (build_id, release_id, target_fingerprint)
        ):
            raise ValueError("formal audio queue scope is incomplete")
        scope_sql = (
            " AND item.build_job_id = ? AND item.release_id = ?"
            " AND receipt.target_fingerprint = ?"
            if scoped else ""
        )
        params = (
            (build_id, release_id, target_fingerprint) if scoped else ()
        )
        return conn.execute(
            """
            SELECT item.id AS build_item_id, item.subject,
              runtime.id AS runtime_classroom_id,
              runtime.upstream_classroom_id, runtime.feature_manifest_json
            FROM learning_catalog_build_items AS item
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = receipt.runtime_classroom_id
            LEFT JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = item.id
            WHERE audio.build_item_id IS NULL
              AND item.execution_mode_snapshot = 'content_only'
              AND item.content_phase = 'course_ready'
              AND item.content_gate_status = 'passed'
              AND runtime.status = 'ready'
              AND runtime.candidate_build_item_id = item.id
              AND receipt.classroom_status = 'passed'
              AND receipt.tts_status = 'pending'
              AND receipt.asr_roundtrip_status = 'pending'
              AND receipt.auto_validated = 0 AND receipt.approved = 0
            """ + scope_sql + """
            ORDER BY item.release_id, item.subject_ordinal,
              item.boundary_ordinal, item.variant_ordinal, item.id
            LIMIT 1
            """,
            params,
        ).fetchone()

    def get_next_pending_formal_audio_job(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str | None = None,
        release_id: str | None = None,
        target_fingerprint: str | None = None,
    ) -> DatabaseRow | None:
        scoped = any(
            value is not None
            for value in (build_id, release_id, target_fingerprint)
        )
        if scoped and not all(
            isinstance(value, str) and bool(value)
            for value in (build_id, release_id, target_fingerprint)
        ):
            raise ValueError("formal audio queue scope is incomplete")
        scope_sql = (
            " AND item.build_job_id = ? AND audio.release_id = ?"
            " AND audio.target_fingerprint = ?"
            if scoped else ""
        )
        params = (
            (build_id, release_id, target_fingerprint) if scoped else ()
        )
        return conn.execute(
            """
            SELECT audio.* FROM learning_formal_qwen_audio_jobs AS audio
            JOIN learning_catalog_build_items AS item
              ON item.id = audio.build_item_id
            WHERE audio.state = 'pending'
            """ + scope_sql + """
            ORDER BY audio.created_at, audio.build_item_id LIMIT 1
            """,
            params,
        ).fetchone()

    def formal_audio_release_counts(
        self, conn: DatabaseConnection, *, release_id: str
    ) -> dict[str, int]:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
              SUM(CASE WHEN state = 'auto_validated' THEN 1 ELSE 0 END) AS ready,
              SUM(CASE WHEN state IN ('failed', 'ambiguous') THEN 1 ELSE 0 END)
                AS failed
            FROM learning_formal_qwen_audio_jobs WHERE release_id = ?
            """,
            (release_id,),
        ).fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "ready": int(row.get("ready") or 0),
            "failed": int(row.get("failed") or 0),
        }

    def formal_pipeline_counts(
        self,
        conn: DatabaseConnection,
        *,
        build_id: str,
        release_id: str,
        target_fingerprint: str,
    ) -> dict[str, int]:
        if re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is None:
            raise ValueError("formal pipeline target fingerprint is invalid")
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
              SUM(CASE WHEN item.status = 'course_ready'
                AND item.content_phase = 'course_ready'
                AND item.content_gate_status = 'passed'
                THEN 1 ELSE 0 END) AS content_ready,
              SUM(CASE WHEN receipt.classroom_status = 'passed'
                AND runtime.status = 'ready'
                AND runtime.candidate_build_item_id = item.id
                AND runtime.candidate_release_id = item.release_id
                AND runtime.candidate_grade_code = item.grade_code
                AND runtime.candidate_target_fingerprint = ?
                AND receipt.target_fingerprint = ?
                AND receipt.runtime_classroom_id = runtime.id
                THEN 1 ELSE 0 END) AS classroom_ready,
              SUM(CASE WHEN receipt.classroom_status = 'failed'
                OR runtime.status = 'failed' THEN 1 ELSE 0 END)
                AS classroom_failed,
              SUM(CASE WHEN audio.build_item_id IS NOT NULL THEN 1 ELSE 0 END)
                AS audio_total,
              SUM(CASE WHEN audio.state = 'auto_validated' THEN 1 ELSE 0 END)
                AS speech_ready,
              SUM(CASE WHEN audio.state IN ('failed', 'ambiguous')
                THEN 1 ELSE 0 END) AS speech_failed
            FROM learning_catalog_build_items AS item
            LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id
            LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = receipt.runtime_classroom_id
            LEFT JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = item.id
              AND audio.release_id = item.release_id
              AND audio.target_fingerprint = ?
            WHERE item.build_job_id = ? AND item.release_id = ?
              AND item.execution_mode_snapshot = 'content_only'
            """,
            (
                target_fingerprint,
                target_fingerprint,
                target_fingerprint,
                build_id,
                release_id,
            ),
        ).fetchone() or {}
        return {
            "total": int(row.get("total") or 0),
            "contentReady": int(row.get("content_ready") or 0),
            "classroomReady": int(row.get("classroom_ready") or 0),
            "classroomFailed": int(row.get("classroom_failed") or 0),
            "audioTotal": int(row.get("audio_total") or 0),
            "speechReady": int(row.get("speech_ready") or 0),
            "speechFailed": int(row.get("speech_failed") or 0),
        }

    def _lock_formal_audio_processing_context(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        claim_token: str,
        now: int,
        lock_segments: bool = False,
    ) -> tuple[DatabaseRow, DatabaseRow, DatabaseRow, list[DatabaseRow]]:
        snapshot = self.get_formal_audio_job(
            conn, build_item_id=build_item_id
        )
        if snapshot is None:
            raise ValueError("formal audio job was not found")

        # Runtime -> 057 receipt -> 058 job -> ordered segments is the shared
        # mutable tail of the formal-publication lock order.
        runtime = conn.execute(
            "SELECT * FROM learning_openmaic_runtime_classrooms "
            "WHERE id = ? LIMIT 1 FOR UPDATE",
            (snapshot["runtime_classroom_id"],),
        ).fetchone()
        receipt = conn.execute(
            "SELECT * FROM learning_curriculum_classroom_item_receipts "
            "WHERE build_item_id = ? LIMIT 1 FOR UPDATE",
            (build_item_id,),
        ).fetchone()
        job = self.get_formal_audio_job(
            conn, build_item_id=build_item_id, for_update=True
        )
        segments = (
            self.list_formal_audio_segments(
                conn, build_item_id=build_item_id, for_update=True
            )
            if lock_segments
            else []
        )
        manifest = self.decode_json(
            runtime.get("feature_manifest_json") if runtime else None, {}
        )
        exact = bool(
            runtime is not None
            and receipt is not None
            and job is not None
            and str(job.get("state") or "") == "processing"
            and str(job.get("claim_token") or "") == str(claim_token or "")
            and int(job.get("claim_deadline_at") or 0) > int(now)
            and str(runtime.get("status") or "") == "ready"
            and str(runtime.get("id") or "")
            == str(job.get("runtime_classroom_id") or "")
            and str(runtime.get("request_id") or "")
            == str(job.get("runtime_request_id") or "")
            and str(runtime.get("upstream_classroom_id") or "")
            == str(job.get("upstream_classroom_id") or "")
            and str(runtime.get("candidate_build_item_id") or "")
            == build_item_id
            and str(runtime.get("candidate_release_id") or "")
            == str(job.get("release_id") or "")
            and str(runtime.get("candidate_grade_code") or "")
            == str(job.get("grade_code") or "")
            and str(runtime.get("candidate_target_fingerprint") or "")
            == str(job.get("target_fingerprint") or "")
            and str(runtime.get("candidate_binding_contract_version") or "")
            == "mira.learning.candidate-runtime-binding.v1"
            and str(runtime.get("course_id") or "")
            == str(job.get("course_id") or "")
            and str(runtime.get("course_version") or "")
            == str(job.get("course_version") or "")
            and str(runtime.get("package_id") or "")
            == str(job.get("package_id") or "")
            and int(runtime.get("package_version") or 0)
            == int(job.get("package_version") or 0)
            and str(receipt.get("release_id") or "")
            == str(job.get("release_id") or "")
            and str(receipt.get("grade_code") or "")
            == str(job.get("grade_code") or "")
            and str(receipt.get("target_fingerprint") or "")
            == str(job.get("target_fingerprint") or "")
            and str(receipt.get("binding_contract_version") or "")
            == "mira.learning.candidate-runtime-binding.v1"
            and str(receipt.get("runtime_classroom_id") or "")
            == str(job.get("runtime_classroom_id") or "")
            and str(receipt.get("course_id") or "")
            == str(job.get("course_id") or "")
            and str(receipt.get("course_version") or "")
            == str(job.get("course_version") or "")
            and str(receipt.get("package_id") or "")
            == str(job.get("package_id") or "")
            and int(receipt.get("package_version") or 0)
            == int(job.get("package_version") or 0)
            and str(receipt.get("classroom_status") or "") == "passed"
            and int(receipt.get("auto_validated") or 0) == 0
            and int(receipt.get("approved") or 0) == 0
            and isinstance(manifest, Mapping)
            and str(manifest.get("classroomContentSha256") or "")
            == str(job.get("classroom_content_sha256") or "")
        )
        if not exact:
            raise ValueError("formal audio processing authority is stale")
        return runtime, receipt, job, segments

    def reserve_formal_audio_job(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        classroom_content_sha256: str,
        speech_manifest: Mapping[str, Any],
        voice: FormalSubjectQwenVoiceIdentity,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        """Bind a sidecar only to current immutable Task-13 evidence."""

        authority = conn.execute(
            """
            SELECT item.id AS build_item_id,
              item.release_id AS item_release_id,
              item.grade_code AS item_grade_code,
              item.course_id AS item_course_id,
              item.course_version AS item_course_version,
              item.package_id AS item_package_id,
              item.package_version AS item_package_version,
              item.subject AS item_subject,
              item.content_phase, item.content_gate_status,
              item.content_receipt_hash, build.id AS build_id,
              build.target_spec_json,
              build.execution_mode, build.stage_ceiling,
              release_row.status AS release_status,
              runtime.id AS runtime_classroom_id,
              runtime.request_id AS runtime_request_id,
              runtime.upstream_classroom_id,
              runtime.feature_manifest_json, runtime.status AS runtime_status,
              runtime.course_id AS runtime_course_id,
              runtime.course_version AS runtime_course_version,
              runtime.package_id AS runtime_package_id,
              runtime.package_version AS runtime_package_version,
              runtime.candidate_build_item_id,
              runtime.candidate_release_id,
              runtime.candidate_grade_code,
              runtime.candidate_target_fingerprint,
              runtime.candidate_binding_contract_version,
              receipt.release_id AS receipt_release_id,
              receipt.grade_code AS receipt_grade_code,
              receipt.target_fingerprint AS receipt_target_fingerprint,
              receipt.binding_contract_version AS receipt_binding_contract_version,
              receipt.runtime_classroom_id AS receipt_runtime_classroom_id,
              receipt.course_id AS receipt_course_id,
              receipt.course_version AS receipt_course_version,
              receipt.package_id AS receipt_package_id,
              receipt.package_version AS receipt_package_version,
              receipt.classroom_status, receipt.classroom_receipt_hash,
              receipt.tts_status, receipt.asr_roundtrip_status,
              receipt.auto_validated, receipt.approved
            FROM learning_catalog_build_items AS item
            JOIN learning_catalog_build_jobs AS build
              ON build.id = item.build_job_id AND build.release_id = item.release_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = item.release_id
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = item.id
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = receipt.runtime_classroom_id
            WHERE item.id = ? LIMIT 1 FOR UPDATE
            """,
            (build_item_id,),
        ).fetchone()
        if authority is None:
            raise ValueError("formal audio classroom authority was not found")
        feature_manifest = self.decode_json(
            authority.get("feature_manifest_json"), {}
        )
        target_spec = self.decode_json(authority.get("target_spec_json"), {})
        try:
            computed_target_fingerprint = preparation_target_fingerprint(
                target_spec
            )
        except (TypeError, ValueError):
            computed_target_fingerprint = ""
        target_voice = (
            target_spec.get("teacherTargets", {})
            .get(str(authority.get("item_subject") or ""), {})
            .get("formalVoiceSelection")
            if isinstance(target_spec, Mapping)
            else None
        )
        manifest = dict(speech_manifest)
        segments = manifest.get("segments")
        speech_manifest_sha256 = str(
            manifest.get("speechManifestSha256") or ""
        )
        expected_segment_count = manifest.get("expectedSegmentCount")
        formal_evidence = (
            feature_manifest.get("formalEvidence")
            if isinstance(feature_manifest, Mapping)
            else None
        )
        runtime_scene_count = (
            feature_manifest.get("sceneCount")
            if isinstance(feature_manifest, Mapping)
            else None
        )
        runtime_speech_action_count = (
            formal_evidence.get("speechActionCount")
            if isinstance(formal_evidence, Mapping)
            else None
        )
        exact_authority = bool(
            str(authority.get("candidate_build_item_id") or "") == build_item_id
            and str(authority.get("candidate_release_id") or "")
            == str(authority.get("item_release_id") or "")
            and str(authority.get("candidate_grade_code") or "")
            == str(authority.get("item_grade_code") or "")
            and computed_target_fingerprint
            == str(authority.get("candidate_target_fingerprint") or "")
            == str(authority.get("receipt_target_fingerprint") or "")
            and str(authority.get("candidate_binding_contract_version") or "")
            == "mira.learning.candidate-runtime-binding.v1"
            and str(authority.get("receipt_binding_contract_version") or "")
            == "mira.learning.candidate-runtime-binding.v1"
            and str(authority.get("receipt_release_id") or "")
            == str(authority.get("item_release_id") or "")
            and str(authority.get("receipt_grade_code") or "")
            == str(authority.get("item_grade_code") or "")
            and str(authority.get("receipt_runtime_classroom_id") or "")
            == str(authority.get("runtime_classroom_id") or "")
            and str(authority.get("item_course_id") or "")
            == str(authority.get("runtime_course_id") or "")
            == str(authority.get("receipt_course_id") or "")
            and str(authority.get("item_course_version") or "")
            == str(authority.get("runtime_course_version") or "")
            == str(authority.get("receipt_course_version") or "")
            and str(authority.get("runtime_package_id") or "")
            == str(authority.get("receipt_package_id") or "")
            and int(authority.get("runtime_package_version") or 0)
            == int(authority.get("receipt_package_version") or 0)
            and int(authority.get("runtime_package_version") or 0) > 0
            and authority.get("item_package_id") is None
            and authority.get("item_package_version") is None
            and str(authority.get("execution_mode") or "") == "content_only"
            and str(authority.get("stage_ceiling") or "") == "content_ready"
            and str(authority.get("content_phase") or "") == "course_ready"
            and str(authority.get("content_gate_status") or "") == "passed"
            and bool(str(authority.get("content_receipt_hash") or ""))
            and str(authority.get("release_status") or "") != "active"
            and str(authority.get("runtime_status") or "") == "ready"
            and bool(str(authority.get("runtime_request_id") or ""))
            and bool(str(authority.get("upstream_classroom_id") or ""))
            and str(authority.get("classroom_status") or "") == "passed"
            and str(authority.get("tts_status") or "") == "pending"
            and str(authority.get("asr_roundtrip_status") or "") == "pending"
            and int(authority.get("auto_validated") or 0) == 0
            and int(authority.get("approved") or 0) == 0
            and str(authority.get("item_subject") or "") == voice.subject
            and target_voice == voice.to_target_payload()
            and isinstance(feature_manifest, Mapping)
            and str(feature_manifest.get("classroomContentSha256") or "")
            == classroom_content_sha256
            and str(manifest.get("buildItemId") or "") == build_item_id
            and str(manifest.get("classroomContentSha256") or "")
            == classroom_content_sha256
            and manifest.get("voiceContract") == voice.to_target_payload()
            and type(expected_segment_count) is int
            and 1 <= expected_segment_count <= 240
            and type(runtime_scene_count) is int
            and 1 <= runtime_scene_count <= 60
            and type(runtime_speech_action_count) is int
            and runtime_scene_count
            <= runtime_speech_action_count
            <= min(240, runtime_scene_count * 20)
            and expected_segment_count == runtime_speech_action_count
            and isinstance(segments, list)
            and len(segments) == expected_segment_count
            and re.fullmatch(r"[0-9a-f]{64}", classroom_content_sha256)
            is not None
            and re.fullmatch(r"[0-9a-f]{64}", speech_manifest_sha256)
            is not None
            and int(now) > 0
        )
        if not exact_authority:
            raise ValueError("formal audio classroom authority is not exact")

        existing = self.get_formal_audio_job(
            conn, build_item_id=build_item_id, for_update=True
        )
        if existing is not None:
            immutable = (
                str(existing["runtime_classroom_id"]),
                str(existing["classroom_content_sha256"]),
                str(existing["speech_manifest_sha256"]),
                str(existing["teacher_profile_hash"]),
                str(existing["tts_voice_id"]),
                int(existing["expected_segment_count"]),
            )
            expected = (
                str(authority["runtime_classroom_id"]),
                classroom_content_sha256,
                speech_manifest_sha256,
                voice.teacher_profile_hash,
                voice.voice_id,
                expected_segment_count,
            )
            if immutable != expected:
                raise ValueError("formal audio job is already bound differently")
            return existing, False

        conn.execute(
            """
            INSERT INTO learning_formal_qwen_audio_jobs(
              build_item_id, release_id, grade_code, target_fingerprint,
              course_id, course_version, package_id, package_version,
              runtime_classroom_id, runtime_request_id, upstream_classroom_id,
              classroom_content_sha256, subject, language_code,
              teacher_profile_id, teacher_profile_version,
              teacher_profile_hash, teacher_name, teacher_gender, voice_gender,
              voice_contract_version, tts_provider_id, tts_model_id,
              tts_voice_id, tts_fallback_allowed, asr_provider_id,
              asr_model_id, asr_fallback_allowed, audio_contract_version,
              pcm_validation_contract_version, asr_roundtrip_contract_version,
              speech_manifest_sha256, expected_segment_count,
              created_at, updated_at
            ) VALUES (
              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
              ?, ?, ?, ?, 0, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                build_item_id,
                authority["item_release_id"],
                authority["item_grade_code"],
                computed_target_fingerprint,
                authority["item_course_id"],
                authority["item_course_version"],
                authority["runtime_package_id"],
                int(authority["runtime_package_version"]),
                authority["runtime_classroom_id"],
                authority["runtime_request_id"],
                authority["upstream_classroom_id"],
                classroom_content_sha256,
                voice.subject,
                voice.language_code,
                voice.teacher_profile_id,
                voice.teacher_profile_version,
                voice.teacher_profile_hash,
                voice.teacher_name,
                voice.teacher_gender,
                voice.voice_gender,
                "mira.openmaic.formal-subject-qwen3-voice.v1",
                voice.tts_provider_id,
                voice.tts_model_id,
                voice.voice_id,
                voice.asr_provider_id,
                voice.asr_model_id,
                "mira.learning.formal-qwen-audio.v1",
                "mira.learning.formal-pcm-validation.v1",
                "mira.learning.formal-qwen-asr-roundtrip.v1",
                speech_manifest_sha256,
                expected_segment_count,
                int(now),
                int(now),
            ),
        )
        for expected_order, segment in enumerate(segments):
            if not isinstance(segment, Mapping) or segment.get("sceneOrder") != expected_order:
                raise ValueError("formal audio speech manifest order is invalid")
            tts_payload = {
                "requestId": segment["ttsRequestId"],
                "classroomId": authority["upstream_classroom_id"],
                "classroomContentSha256": classroom_content_sha256,
                "subject": voice.subject,
                "teacherProfileId": voice.teacher_profile_id,
                "teacherProfileVersion": voice.teacher_profile_version,
                "teacherProfileSha256": voice.teacher_profile_hash,
                "teacherGender": voice.teacher_gender,
                "sceneId": segment["sceneId"],
                "sceneOrder": expected_order,
                "actionId": segment["actionId"],
                "narrationSegmentId": segment["narrationSegmentId"],
                "text": segment["text"],
                "textSha256": segment["textSha256"],
            }
            request_sha256 = hashlib.sha256(
                self.encode_json(tts_payload).encode("utf-8")
            ).hexdigest()
            conn.execute(
                """
                INSERT INTO learning_formal_qwen_audio_segment_receipts(
                  build_item_id, scene_order, scene_id, action_id,
                  narration_segment_id, source_text_sha256, tts_request_id,
                  tts_request_sha256, asr_request_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    build_item_id,
                    expected_order,
                    segment["sceneId"],
                    segment["actionId"],
                    segment["narrationSegmentId"],
                    segment["textSha256"],
                    segment["ttsRequestId"],
                    request_sha256,
                    segment["asrRequestId"],
                    int(now),
                    int(now),
                ),
            )
        created = self.get_formal_audio_job(
            conn, build_item_id=build_item_id, for_update=True
        )
        if created is None:
            raise RuntimeError("formal audio job disappeared after reservation")
        return created, True

    def claim_formal_audio_job(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        claim_token: str,
        claim_deadline_at: int,
        now: int,
    ) -> bool:
        if not claim_token or int(claim_deadline_at) <= int(now):
            raise ValueError("formal audio claim is invalid")
        cursor = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET state = 'processing', claim_token = ?, claim_deadline_at = ?,
              heartbeat_at = ?, started_at = COALESCE(started_at, ?),
              updated_at = ?
            WHERE build_item_id = ? AND state = 'pending'
            """,
            (
                claim_token,
                int(claim_deadline_at),
                int(now),
                int(now),
                int(now),
                build_item_id,
            ),
        )
        return cursor.rowcount == 1

    def begin_formal_tts_attempt(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        request_sha256: str,
        now: int,
    ) -> bool:
        _runtime, _receipt, job, segments = (
            self._lock_formal_audio_processing_context(
                conn,
                build_item_id=build_item_id,
                claim_token=claim_token,
                now=now,
                lock_segments=True,
            )
        )
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        if not (
            segment is not None
            and str(segment.get("tts_request_sha256") or "") == request_sha256
        ):
            raise ValueError("formal TTS attempt authority is stale")
        if str(segment.get("state") or "") == "tts_attempted":
            return False
        if str(segment.get("state") or "") != "pending":
            raise ValueError("formal TTS segment is not pending")
        updated = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET state = 'tts_attempted', tts_attempted_at = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ? AND state = 'pending'
              AND tts_request_sha256 = ?
            """,
            (
                int(now),
                int(now),
                build_item_id,
                int(scene_order),
                request_sha256,
            ),
        )
        if updated.rowcount != 1:
            return False
        incremented = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET tts_attempted_count = tts_attempted_count + 1,
              heartbeat_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ?
              AND tts_attempted_count < expected_segment_count
            """,
            (int(now), int(now), build_item_id, claim_token),
        )
        if incremented.rowcount != 1:
            raise RuntimeError("formal TTS attempt count was not persisted")
        return True

    def complete_formal_tts_attempt(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        request_sha256: str,
        runtime_audio_sha256: str,
        provider_media_url_sha256: str | None,
        now: int,
    ) -> bool:
        if re.fullmatch(r"[0-9a-f]{64}", runtime_audio_sha256) is None:
            raise ValueError("formal TTS audio hash is invalid")
        if provider_media_url_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", provider_media_url_sha256
        ) is None:
            raise ValueError("formal TTS media reference hash is invalid")
        _runtime, _receipt, _job, segments = (
            self._lock_formal_audio_processing_context(
                conn,
                build_item_id=build_item_id,
                claim_token=claim_token,
                now=now,
                lock_segments=True,
            )
        )
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        if segment is None or str(segment.get("tts_request_sha256") or "") != request_sha256:
            raise ValueError("formal TTS completion authority is stale")
        if str(segment.get("state") or "") in {
            "tts_completed", "audio_validated", "asr_attempted", "auto_validated"
        }:
            if str(segment.get("runtime_audio_sha256") or "") != runtime_audio_sha256:
                raise ValueError("formal TTS completion conflicts with its receipt")
            return False
        if str(segment.get("state") or "") != "tts_attempted":
            raise ValueError("formal TTS attempt is not completable")
        updated = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET state = 'tts_completed', tts_completed_at = ?,
              provider_audio_result_sha256 = ?, provider_media_url_sha256 = ?,
              runtime_audio_sha256 = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ?
              AND state = 'tts_attempted' AND tts_request_sha256 = ?
            """,
            (
                int(now), runtime_audio_sha256, provider_media_url_sha256,
                runtime_audio_sha256, int(now), build_item_id,
                int(scene_order), request_sha256,
            ),
        )
        if updated.rowcount != 1:
            return False
        counted = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET tts_completed_count = tts_completed_count + 1,
              heartbeat_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ? AND tts_completed_count < tts_attempted_count
            """,
            (int(now), int(now), build_item_id, claim_token),
        )
        if counted.rowcount != 1:
            raise RuntimeError("formal TTS completion count was not persisted")
        return True

    def record_formal_audio_write(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        storage_key: str,
        audio_sha256: str,
        byte_size: int,
        write_completed_at: int,
        readback_completed_at: int,
        now: int,
    ) -> str:
        if (
            re.fullmatch(r"[0-9a-f]{64}", audio_sha256) is None
            or not str(storage_key or "").strip()
            or len(str(storage_key)) > 512
            or not 44 <= int(byte_size) <= 16 * 1024 * 1024
            or not 0 < int(write_completed_at) <= int(readback_completed_at) <= int(now)
        ):
            raise ValueError("formal audio write evidence is invalid")
        _runtime, _receipt, job, segments = (
            self._lock_formal_audio_processing_context(
                conn,
                build_item_id=build_item_id,
                claim_token=claim_token,
                now=now,
                lock_segments=True,
            )
        )
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        if not (
            segment is not None
            and str(segment.get("state") or "") == "tts_completed"
            and str(segment.get("runtime_audio_sha256") or "") == audio_sha256
        ):
            raise ValueError("formal audio write authority is stale")
        source_ref = f"{build_item_id}:{int(scene_order)}"
        asset_id = "formal_audio_asset_" + hashlib.sha256(
            f"{source_ref}:{audio_sha256}".encode("utf-8")
        ).hexdigest()[:48]
        conn.execute(
            """
            INSERT INTO learning_media_assets(
              id, kind, storage_key, content_hash, mime_type, byte_size,
              duration_ms, scan_status, moderation_status, transcode_status,
              status, source_type, source_ref, metadata_json, created_at,
              updated_at
            ) VALUES (?, 'audio', ?, ?, 'audio/wav', ?, NULL, 'pending',
              'pending', 'not_required', 'quarantined', 'formal_qwen_tts',
              ?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE id = id
            """,
            (
                asset_id, storage_key, audio_sha256, int(byte_size), source_ref,
                self.encode_json({
                    "schemaVersion": "mira.learning.formal-qwen-audio-asset.v1",
                    "buildItemId": build_item_id,
                    "sceneOrder": int(scene_order),
                    "runtimeClassroomId": str(job["runtime_classroom_id"]),
                }),
                int(now), int(now),
            ),
        )
        persisted = conn.execute(
            "SELECT * FROM learning_media_assets WHERE id = ? LIMIT 1 FOR UPDATE",
            (asset_id,),
        ).fetchone()
        if not (
            persisted is not None
            and str(persisted.get("storage_key") or "") == storage_key
            and str(persisted.get("content_hash") or "") == audio_sha256
            and int(persisted.get("byte_size") or 0) == int(byte_size)
            and str(persisted.get("status") or "") == "quarantined"
            and str(persisted.get("source_type") or "") == "formal_qwen_tts"
            and str(persisted.get("source_ref") or "") == source_ref
        ):
            raise ValueError("formal audio asset conflicts with persisted bytes")
        conn.execute(
            """
            INSERT INTO learning_media_asset_variants(
              asset_id, variant_key, storage_key, content_hash, mime_type,
              byte_size, duration_ms, status, created_at, updated_at
            ) VALUES (?, 'original', ?, ?, 'audio/wav', ?, NULL,
              'quarantined', ?, ?)
            ON DUPLICATE KEY UPDATE asset_id = asset_id
            """,
            (
                asset_id, storage_key, audio_sha256, int(byte_size),
                int(now), int(now),
            ),
        )
        conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET download_sha256 = ?, streamed_sha256 = ?, storage_key = ?,
              write_completed_at = ?, readback_sha256 = ?,
              readback_completed_at = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ?
              AND state = 'tts_completed' AND runtime_audio_sha256 = ?
            """,
            (
                audio_sha256, audio_sha256, storage_key,
                int(write_completed_at), audio_sha256,
                int(readback_completed_at), int(now), build_item_id,
                int(scene_order), audio_sha256,
            ),
        )
        return asset_id

    def complete_formal_audio_validation(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        asset_id: str,
        evidence: Mapping[str, Any],
        now: int,
    ) -> bool:
        _runtime, _receipt, _job, segments = (
            self._lock_formal_audio_processing_context(
                conn,
                build_item_id=build_item_id,
                claim_token=claim_token,
                now=now,
                lock_segments=True,
            )
        )
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        digest = str(evidence.get("readback_sha256") or "")
        if not (
            segment is not None
            and str(segment.get("state") or "") == "tts_completed"
            and re.fullmatch(r"[0-9a-f]{64}", digest) is not None
            and digest == str(segment.get("runtime_audio_sha256") or "")
            == str(segment.get("download_sha256") or "")
            == str(segment.get("streamed_sha256") or "")
            == str(segment.get("readback_sha256") or "")
        ):
            raise ValueError("formal PCM validation authority is stale")
        asset = conn.execute(
            "SELECT * FROM learning_media_assets WHERE id = ? LIMIT 1 FOR UPDATE",
            (asset_id,),
        ).fetchone()
        if not (
            asset is not None
            and str(asset.get("status") or "") == "quarantined"
            and str(asset.get("content_hash") or "") == digest
            and str(asset.get("storage_key") or "")
            == str(segment.get("storage_key") or "")
            and int(asset.get("byte_size") or 0) == int(evidence.get("byte_size") or 0)
        ):
            raise ValueError("formal PCM asset is not the final stored object")
        fields = (
            "byte_size", "pcm_format", "channel_count", "bits_per_sample",
            "sample_rate_hz", "block_align", "byte_rate", "frame_count",
            "duration_ms", "normalized_peak_bps", "overall_rms_bps",
            "active_window_bps",
        )
        if any(type(evidence.get(field)) is not int for field in fields):
            raise ValueError("formal PCM evidence is incomplete")
        updated = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET state = 'audio_validated', asset_id = ?, mime_type = 'audio/wav',
              byte_size = ?, pcm_format = ?, channel_count = ?,
              bits_per_sample = ?, sample_rate_hz = ?, block_align = ?,
              byte_rate = ?, frame_count = ?, duration_ms = ?,
              normalized_peak_bps = ?, overall_rms_bps = ?,
              active_window_bps = ?, audio_validated_at = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ?
              AND state = 'tts_completed' AND readback_sha256 = ?
            """,
            (
                asset_id, *(int(evidence[field]) for field in fields),
                int(now), int(now), build_item_id, int(scene_order), digest,
            ),
        )
        if updated.rowcount != 1:
            return False
        conn.execute(
            """
            UPDATE learning_media_assets
            SET duration_ms = ?, scan_status = 'passed',
              moderation_status = 'passed', transcode_status = 'not_required',
              status = 'ready', updated_at = ? WHERE id = ?
            """,
            (int(evidence["duration_ms"]), int(now), asset_id),
        )
        conn.execute(
            """
            UPDATE learning_media_asset_variants
            SET duration_ms = ?, status = 'ready', updated_at = ?
            WHERE asset_id = ? AND variant_key = 'original'
            """,
            (int(evidence["duration_ms"]), int(now), asset_id),
        )
        counted = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET audio_validated_count = audio_validated_count + 1,
              heartbeat_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ?
              AND audio_validated_count < tts_completed_count
            """,
            (int(now), int(now), build_item_id, claim_token),
        )
        if counted.rowcount != 1:
            raise RuntimeError("formal PCM validation count was not persisted")
        return True

    def begin_formal_asr_attempt(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        request_sha256: str,
        now: int,
    ) -> bool:
        if re.fullmatch(r"[0-9a-f]{64}", request_sha256) is None:
            raise ValueError("formal ASR request hash is invalid")
        _runtime, _receipt, _job, segments = (
            self._lock_formal_audio_processing_context(
                conn,
                build_item_id=build_item_id,
                claim_token=claim_token,
                now=now,
                lock_segments=True,
            )
        )
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        if segment is None:
            raise ValueError("formal ASR segment was not found")
        if str(segment.get("state") or "") == "asr_attempted":
            if str(segment.get("asr_request_sha256") or "") != request_sha256:
                raise ValueError("formal ASR attempt conflicts with its receipt")
            return False
        if str(segment.get("state") or "") != "audio_validated":
            raise ValueError("formal ASR segment is not ready")
        updated = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET state = 'asr_attempted', asr_request_sha256 = ?,
              asr_attempted_at = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ?
              AND state = 'audio_validated'
            """,
            (
                request_sha256, int(now), int(now), build_item_id,
                int(scene_order),
            ),
        )
        if updated.rowcount != 1:
            return False
        counted = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET asr_attempted_count = asr_attempted_count + 1,
              heartbeat_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ?
              AND asr_attempted_count < audio_validated_count
            """,
            (int(now), int(now), build_item_id, claim_token),
        )
        if counted.rowcount != 1:
            raise RuntimeError("formal ASR attempt count was not persisted")
        return True

    def complete_formal_asr_pass(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        request_sha256: str,
        transcript_sha256: str,
        normalized_transcript_sha256: str,
        similarity_bps: int,
        now: int,
    ) -> tuple[DatabaseRow, bool]:
        if any(
            re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in (
                request_sha256,
                transcript_sha256,
                normalized_transcript_sha256,
            )
        ) or not 0 <= int(similarity_bps) <= 10_000:
            raise ValueError("formal ASR completion evidence is invalid")
        runtime, receipt, job, segments = self._lock_formal_audio_processing_context(
            conn,
            build_item_id=build_item_id,
            claim_token=claim_token,
            now=now,
            lock_segments=True,
        )
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        if not (
            segment is not None
            and str(segment.get("state") or "") == "asr_attempted"
            and str(segment.get("asr_request_sha256") or "") == request_sha256
        ):
            raise ValueError("formal ASR completion authority is stale")
        if int(similarity_bps) < 8_500:
            terminal = self._terminalize_formal_audio_locked(
                conn,
                runtime=runtime,
                receipt=receipt,
                job=job,
                segments=segments,
                scene_order=scene_order,
                outcome="failed",
                safe_error_code="formal_asr_similarity_below_threshold",
                now=now,
            )
            return terminal, True
        machine_receipt_hash = hashlib.sha256(
            self.encode_json({
                "schemaVersion": "mira.learning.formal-qwen-audio-segment.v1",
                "buildItemId": build_item_id,
                "sceneOrder": int(scene_order),
                "ttsRequestSha256": str(segment["tts_request_sha256"]),
                "runtimeAudioSha256": str(segment["runtime_audio_sha256"]),
                "readbackSha256": str(segment["readback_sha256"]),
                "asrRequestSha256": request_sha256,
                "transcriptSha256": transcript_sha256,
                "normalizedTranscriptSha256": normalized_transcript_sha256,
                "similarityBps": int(similarity_bps),
            }).encode("utf-8")
        ).hexdigest()
        updated = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET state = 'auto_validated', asr_completed_at = ?,
              asr_result_sha256 = ?, normalized_transcript_sha256 = ?,
              asr_similarity_bps = ?, machine_receipt_version = ?,
              machine_receipt_hash = ?, terminal_at = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ?
              AND state = 'asr_attempted' AND asr_request_sha256 = ?
            """,
            (
                int(now), transcript_sha256, normalized_transcript_sha256,
                int(similarity_bps),
                "mira.learning.formal-qwen-audio-segment.v1",
                machine_receipt_hash, int(now), int(now), build_item_id,
                int(scene_order), request_sha256,
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("formal ASR pass was not persisted")
        conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET asr_passed_count = asr_passed_count + 1,
              heartbeat_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ? AND asr_passed_count < asr_attempted_count
            """,
            (int(now), int(now), build_item_id, claim_token),
        )
        segments = self.list_formal_audio_segments(
            conn, build_item_id=build_item_id, for_update=True
        )
        expected_segment_count = int(job.get("expected_segment_count") or 0)
        if (
            not 1 <= expected_segment_count <= 240
            or len(segments) != expected_segment_count
            or any(
            str(row.get("state") or "") != "auto_validated" for row in segments
            )
        ):
            current = self.get_formal_audio_job(
                conn, build_item_id=build_item_id, for_update=True
            )
            if current is None:
                raise RuntimeError("formal audio job disappeared")
            return current, False

        tts_receipt_hash = hashlib.sha256(
            self.encode_json({
                "schemaVersion": "mira.learning.formal-qwen-tts-evidence.v1",
                "buildItemId": build_item_id,
                "classroomContentSha256": str(job["classroom_content_sha256"]),
                "segments": [
                    {
                        "sceneOrder": int(row["scene_order"]),
                        "ttsRequestSha256": str(row["tts_request_sha256"]),
                        "runtimeAudioSha256": str(row["runtime_audio_sha256"]),
                        "readbackSha256": str(row["readback_sha256"]),
                    }
                    for row in segments
                ],
            }).encode("utf-8")
        ).hexdigest()
        asr_receipt_hash = hashlib.sha256(
            self.encode_json({
                "schemaVersion": "mira.learning.formal-qwen-asr-evidence.v1",
                "buildItemId": build_item_id,
                "segments": [
                    {
                        "sceneOrder": int(row["scene_order"]),
                        "asrRequestSha256": str(row["asr_request_sha256"]),
                        "transcriptSha256": str(row["asr_result_sha256"]),
                        "normalizedTranscriptSha256": str(
                            row["normalized_transcript_sha256"]
                        ),
                        "similarityBps": int(row["asr_similarity_bps"]),
                    }
                    for row in segments
                ],
            }).encode("utf-8")
        ).hexdigest()
        terminal_receipt_hash = hashlib.sha256(
            self.encode_json({
                "schemaVersion": "mira.learning.formal-qwen-audio-job.v1",
                "buildItemId": build_item_id,
                "releaseId": str(job["release_id"]),
                "targetFingerprint": str(job["target_fingerprint"]),
                "runtimeClassroomId": str(job["runtime_classroom_id"]),
                "speechManifestSha256": str(job["speech_manifest_sha256"]),
                "ttsReceiptSha256": tts_receipt_hash,
                "asrReceiptSha256": asr_receipt_hash,
            }).encode("utf-8")
        ).hexdigest()
        receipt_update = conn.execute(
            """
            UPDATE learning_curriculum_classroom_item_receipts
            SET tts_status = 'passed', tts_receipt_hash = ?,
              tts_completed_at = ?, asr_roundtrip_status = 'passed',
              asr_roundtrip_receipt_hash = ?,
              asr_roundtrip_completed_at = ?, updated_at = ?
            WHERE build_item_id = ? AND classroom_status = 'passed'
              AND tts_status = 'pending' AND asr_roundtrip_status = 'pending'
              AND auto_validated = 0 AND approved = 0
            """,
            (
                tts_receipt_hash, int(now), asr_receipt_hash, int(now),
                int(now), build_item_id,
            ),
        )
        if receipt_update.rowcount != 1:
            raise RuntimeError("formal audio 057 evidence was not persisted")
        completed = conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET state = 'auto_validated',
              tts_attempted_count = expected_segment_count,
              tts_completed_count = expected_segment_count,
              audio_validated_count = expected_segment_count,
              asr_attempted_count = expected_segment_count,
              asr_passed_count = expected_segment_count,
              claim_token = NULL, claim_deadline_at = NULL,
              terminal_receipt_version = ?, terminal_receipt_hash = ?,
              terminal_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ?
            """,
            (
                "mira.learning.formal-qwen-audio-job.v1",
                terminal_receipt_hash, int(now), int(now), build_item_id,
                claim_token,
            ),
        )
        if completed.rowcount != 1:
            raise RuntimeError("formal audio aggregate was not persisted")
        final_receipt = conn.execute(
            "SELECT * FROM learning_curriculum_classroom_item_receipts "
            "WHERE build_item_id = ? LIMIT 1 FOR UPDATE",
            (build_item_id,),
        ).fetchone()
        if not (
            final_receipt is not None
            and str(final_receipt.get("tts_status") or "") == "passed"
            and str(final_receipt.get("asr_roundtrip_status") or "") == "passed"
            and int(final_receipt.get("auto_validated") or 0) == 0
            and int(final_receipt.get("approved") or 0) == 0
        ):
            raise RuntimeError("formal audio crossed the human approval boundary")
        final_job = self.get_formal_audio_job(
            conn, build_item_id=build_item_id, for_update=True
        )
        if final_job is None:
            raise RuntimeError("formal audio job disappeared after aggregate")
        return final_job, True

    def terminalize_formal_audio_job(
        self,
        conn: DatabaseConnection,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        outcome: str,
        safe_error_code: str,
        now: int,
    ) -> DatabaseRow:
        if outcome not in {"failed", "ambiguous"}:
            raise ValueError("formal audio terminal outcome is invalid")
        if not re.fullmatch(r"[a-z0-9_]{1,128}", str(safe_error_code or "")):
            raise ValueError("formal audio safe error code is invalid")
        runtime, receipt, job, segments = self._lock_formal_audio_processing_context(
            conn,
            build_item_id=build_item_id,
            claim_token=claim_token,
            now=now,
            lock_segments=True,
        )
        return self._terminalize_formal_audio_locked(
            conn,
            runtime=runtime,
            receipt=receipt,
            job=job,
            segments=segments,
            scene_order=scene_order,
            outcome=outcome,
            safe_error_code=safe_error_code,
            now=now,
        )

    def _terminalize_formal_audio_locked(
        self,
        conn: DatabaseConnection,
        *,
        runtime: Mapping[str, Any],
        receipt: Mapping[str, Any],
        job: Mapping[str, Any],
        segments: Sequence[Mapping[str, Any]],
        scene_order: int,
        outcome: str,
        safe_error_code: str,
        now: int,
    ) -> DatabaseRow:
        segment = next(
            (row for row in segments if int(row["scene_order"]) == int(scene_order)),
            None,
        )
        if segment is None:
            raise ValueError("formal audio terminal segment was not found")
        terminal_receipt_hash = hashlib.sha256(
            self.encode_json({
                "schemaVersion": "mira.learning.formal-qwen-audio-terminal.v1",
                "buildItemId": str(job["build_item_id"]),
                "runtimeClassroomId": str(runtime["id"]),
                "sceneOrder": int(scene_order),
                "previousState": str(segment["state"]),
                "outcome": outcome,
                "safeErrorCode": safe_error_code,
                "ttsRequestSha256": str(segment["tts_request_sha256"]),
                "asrRequestSha256": segment.get("asr_request_sha256"),
            }).encode("utf-8")
        ).hexdigest()
        conn.execute(
            """
            UPDATE learning_formal_qwen_audio_segment_receipts
            SET state = ?, safe_error_code = ?, terminal_at = ?, updated_at = ?
            WHERE build_item_id = ? AND scene_order = ?
              AND state NOT IN ('auto_validated', 'failed', 'ambiguous')
            """,
            (
                outcome, safe_error_code, int(now), int(now),
                job["build_item_id"], int(scene_order),
            ),
        )
        conn.execute(
            """
            UPDATE learning_media_assets
            SET status = 'quarantined', updated_at = ?
            WHERE source_type = 'formal_qwen_tts'
              AND source_ref LIKE ?
            """,
            (int(now), f"{job['build_item_id']}:%"),
        )
        conn.execute(
            """
            UPDATE learning_media_asset_variants AS variant
            JOIN learning_media_assets AS asset ON asset.id = variant.asset_id
            SET variant.status = 'quarantined', variant.updated_at = ?
            WHERE asset.source_type = 'formal_qwen_tts'
              AND asset.source_ref LIKE ?
            """,
            (int(now), f"{job['build_item_id']}:%"),
        )
        if outcome == "failed":
            tts_failure_hash = hashlib.sha256(
                f"{terminal_receipt_hash}:tts".encode("utf-8")
            ).hexdigest()
            asr_failure_hash = hashlib.sha256(
                f"{terminal_receipt_hash}:asr".encode("utf-8")
            ).hexdigest()
            conn.execute(
                """
                UPDATE learning_curriculum_classroom_item_receipts
                SET tts_status = 'failed', tts_receipt_hash = ?,
                  tts_completed_at = ?, asr_roundtrip_status = 'failed',
                  asr_roundtrip_receipt_hash = ?,
                  asr_roundtrip_completed_at = ?, updated_at = ?
                WHERE build_item_id = ? AND classroom_status = 'passed'
                  AND tts_status = 'pending'
                  AND asr_roundtrip_status = 'pending'
                  AND auto_validated = 0 AND approved = 0
                """,
                (
                    tts_failure_hash, int(now), asr_failure_hash, int(now),
                    int(now), job["build_item_id"],
                ),
            )
        conn.execute(
            """
            UPDATE learning_formal_qwen_audio_jobs
            SET state = ?, claim_token = NULL, claim_deadline_at = NULL,
              safe_error_code = ?, terminal_receipt_version = ?,
              terminal_receipt_hash = ?, terminal_at = ?, updated_at = ?
            WHERE build_item_id = ? AND state = 'processing'
              AND claim_token = ?
            """,
            (
                outcome, safe_error_code,
                "mira.learning.formal-qwen-audio-terminal.v1",
                terminal_receipt_hash, int(now), int(now),
                job["build_item_id"], job["claim_token"],
            ),
        )
        terminal = self.get_formal_audio_job(
            conn, build_item_id=str(job["build_item_id"]), for_update=True
        )
        if terminal is None or str(terminal.get("state") or "") != outcome:
            raise RuntimeError("formal audio terminal state was not persisted")
        return terminal

    def terminalize_stale_formal_audio_jobs(
        self,
        conn: DatabaseConnection,
        *,
        now: int,
        limit: int = 10,
    ) -> int:
        """Make an expired attempted job ambiguous; it is never claimable again."""

        if int(now) <= 0 or not 1 <= int(limit) <= 100:
            raise ValueError("formal audio stale sweep is invalid")
        candidates = conn.execute(
            """
            SELECT build_item_id FROM learning_formal_qwen_audio_jobs
            WHERE state = 'processing' AND claim_deadline_at <= ?
            ORDER BY claim_deadline_at, build_item_id LIMIT ?
            """,
            (int(now), int(limit)),
        ).fetchall()
        terminalized = 0
        for candidate in candidates:
            build_item_id = str(candidate["build_item_id"])
            snapshot = self.get_formal_audio_job(
                conn, build_item_id=build_item_id
            )
            if snapshot is None:
                continue
            runtime = conn.execute(
                "SELECT * FROM learning_openmaic_runtime_classrooms "
                "WHERE id = ? LIMIT 1 FOR UPDATE",
                (snapshot["runtime_classroom_id"],),
            ).fetchone()
            receipt = conn.execute(
                "SELECT * FROM learning_curriculum_classroom_item_receipts "
                "WHERE build_item_id = ? LIMIT 1 FOR UPDATE",
                (build_item_id,),
            ).fetchone()
            job = self.get_formal_audio_job(
                conn, build_item_id=build_item_id, for_update=True
            )
            segments = self.list_formal_audio_segments(
                conn, build_item_id=build_item_id, for_update=True
            )
            if not (
                runtime is not None
                and receipt is not None
                and job is not None
                and str(job.get("state") or "") == "processing"
                and int(job.get("claim_deadline_at") or 0) <= int(now)
            ):
                continue
            unfinished = next(
                (
                    row for row in segments
                    if str(row.get("state") or "")
                    not in {"auto_validated", "failed", "ambiguous"}
                ),
                None,
            )
            if unfinished is None:
                raise RuntimeError("expired formal audio job has no unfinished segment")
            self._terminalize_formal_audio_locked(
                conn,
                runtime=runtime,
                receipt=receipt,
                job=job,
                segments=segments,
                scene_order=int(unfinished["scene_order"]),
                outcome="ambiguous",
                safe_error_code="formal_audio_claim_expired_ambiguous",
                now=now,
            )
            terminalized += 1
        return terminalized

    @staticmethod
    def encode_json(value: Any) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def decode_json(value: str | None, fallback: Any = None) -> Any:
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
