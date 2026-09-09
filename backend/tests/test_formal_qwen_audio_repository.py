from __future__ import annotations

import hashlib
import json

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from repositories.learning_teacher_media_repository import LearningTeacherMediaRepository
from services.learning_media_materialization_service import build_formal_speech_manifest
from tests.test_learning_curriculum_classroom_repository import (
    LearningCurriculumClassroomRepositoryTest,
)


def _classroom() -> dict:
    return {
        "stage": {"id": "upstream-formal-audio-repository-1"},
        "scenes": [
            {
                "id": f"scene-{index}",
                "order": index,
                "actions": [{
                    "id": f"speech-{index}",
                    "type": "speech",
                    "text": f"第{index + 1}段正式讲解",
                }],
            }
            for index in range(10)
        ],
    }


class FormalQwenAudioRepositoryTest(LearningCurriculumClassroomRepositoryTest):
    def _prepare_audio_authority(
        self, suffix: str
    ) -> tuple[dict[str, object], LearningTeacherMediaRepository, object, dict]:
        fixture = self._seed_candidate(suffix)
        repository = LearningTeacherMediaRepository(self.database)
        voice = get_formal_subject_qwen_voice_identity("chinese")
        manifest = build_formal_speech_manifest(
            _classroom(), build_item_id=str(fixture["item_id"]), voice=voice
        )
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_openmaic_runtime_classrooms "
                "SET feature_manifest_json = ? WHERE id = ?",
                (json.dumps({
                    "classroomContentSha256": manifest["classroomContentSha256"],
                    "sceneCount": 10,
                    "formalEvidence": {
                        "speechActionCount": len(manifest["segments"])
                    },
                }), fixture["runtime_id"]),
            )
            self.catalog.record_classroom_item_evidence(
                conn,
                build_item_id=str(fixture["item_id"]),
                evidence_kind="classroom",
                outcome="passed",
                receipt_hash="8" * 64,
                completed_at=2_100,
                now=2_100,
            )
        return fixture, repository, voice, manifest

    def test_reservation_binds_authoritative_classroom_and_attempt_is_durable(self) -> None:
        fixture, repository, voice, manifest = self._prepare_audio_authority(
            "audio-repository"
        )
        with self.database.transaction() as conn:
            job, created = repository.reserve_formal_audio_job(
                conn,
                build_item_id=str(fixture["item_id"]),
                classroom_content_sha256=manifest["classroomContentSha256"],
                speech_manifest=manifest,
                voice=voice,
                now=2_200,
            )
        self.assertTrue(created)
        self.assertEqual(job["state"], "pending")
        self.assertEqual(job["expected_segment_count"], 10)
        self.assertEqual(job["tts_voice_id"], "Serena")

        with self.database.transaction() as conn:
            segments = repository.list_formal_audio_segments(
                conn, build_item_id=fixture["item_id"]
            )
            claimed = repository.claim_formal_audio_job(
                conn,
                build_item_id=fixture["item_id"],
                claim_token="claim-1",
                claim_deadline_at=10_000,
                now=2_300,
            )
        self.assertEqual(len(segments), 10)
        self.assertEqual([row["scene_order"] for row in segments], list(range(10)))
        self.assertTrue(claimed)
        request_sha256 = str(segments[0]["tts_request_sha256"])

        with self.database.transaction() as conn:
            attempted = repository.begin_formal_tts_attempt(
                conn,
                build_item_id=fixture["item_id"],
                scene_order=0,
                claim_token="claim-1",
                request_sha256=request_sha256,
                now=2_400,
            )
            replay = repository.begin_formal_tts_attempt(
                conn,
                build_item_id=fixture["item_id"],
                scene_order=0,
                claim_token="claim-1",
                request_sha256=request_sha256,
                now=2_401,
            )
        self.assertTrue(attempted)
        self.assertFalse(replay)
        with self.database.transaction() as conn:
            persisted = repository.get_formal_audio_job(
                conn, build_item_id=fixture["item_id"]
            )
            segment = repository.get_formal_audio_segment(
                conn, build_item_id=fixture["item_id"], scene_order=0
            )
        self.assertEqual(persisted["tts_attempted_count"], 1)
        self.assertEqual(segment["state"], "tts_attempted")
        self.assertEqual(segment["tts_request_sha256"], request_sha256)

    def test_reservation_rejects_receipt_target_fingerprint_mismatch(self) -> None:
        fixture, repository, voice, manifest = self._prepare_audio_authority(
            "audio-repository-receipt-target-mismatch"
        )
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_curriculum_classroom_item_receipts "
                "SET target_fingerprint = ? WHERE build_item_id = ?",
                ("f" * 64, fixture["item_id"]),
            )
        with self.assertRaisesRegex(
            ValueError, "formal audio classroom authority is not exact"
        ):
            with self.database.transaction() as conn:
                repository.reserve_formal_audio_job(
                    conn,
                    build_item_id=str(fixture["item_id"]),
                    classroom_content_sha256=manifest["classroomContentSha256"],
                    speech_manifest=manifest,
                    voice=voice,
                    now=2_200,
                )

    def test_reservation_rejects_recomputed_target_mismatch(self) -> None:
        fixture, repository, voice, manifest = self._prepare_audio_authority(
            "audio-repository-build-target-mismatch"
        )
        target = dict(fixture["target"])
        target["schemaVersion"] = "mira.learning.tampered-target.v1"
        with self.database.transaction() as conn:
            conn.execute(
                "UPDATE learning_catalog_build_jobs SET target_spec_json = ? "
                "WHERE id = ?",
                (repository.encode_json(target), fixture["build_id"]),
            )
        with self.assertRaisesRegex(
            ValueError, "formal audio classroom authority is not exact"
        ):
            with self.database.transaction() as conn:
                repository.reserve_formal_audio_job(
                    conn,
                    build_item_id=str(fixture["item_id"]),
                    classroom_content_sha256=manifest["classroomContentSha256"],
                    speech_manifest=manifest,
                    voice=voice,
                    now=2_200,
                )

    def test_ten_segments_aggregate_without_crossing_human_approval(self) -> None:
        fixture, repository, voice, manifest = self._prepare_audio_authority(
            "audio-repository-aggregate"
        )
        build_item_id = str(fixture["item_id"])
        with self.database.transaction() as conn:
            repository.reserve_formal_audio_job(
                conn,
                build_item_id=build_item_id,
                classroom_content_sha256=manifest["classroomContentSha256"],
                speech_manifest=manifest,
                voice=voice,
                now=2_200,
            )
            self.assertTrue(repository.claim_formal_audio_job(
                conn,
                build_item_id=build_item_id,
                claim_token="aggregate-claim",
                claim_deadline_at=100_000,
                now=2_300,
            ))

        final_completed = False
        for scene_order in range(10):
            timestamp = 3_000 + scene_order * 10
            audio_sha256 = hashlib.sha256(
                f"audio-{scene_order}".encode("utf-8")
            ).hexdigest()
            asr_request_sha256 = hashlib.sha256(
                f"asr-request-{scene_order}".encode("utf-8")
            ).hexdigest()
            transcript_sha256 = hashlib.sha256(
                f"transcript-{scene_order}".encode("utf-8")
            ).hexdigest()
            normalized_sha256 = hashlib.sha256(
                f"normalized-{scene_order}".encode("utf-8")
            ).hexdigest()
            with self.database.transaction() as conn:
                segment = repository.get_formal_audio_segment(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                )
                repository.begin_formal_tts_attempt(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                    claim_token="aggregate-claim",
                    request_sha256=str(segment["tts_request_sha256"]),
                    now=timestamp,
                )
            with self.database.transaction() as conn:
                repository.complete_formal_tts_attempt(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                    claim_token="aggregate-claim",
                    request_sha256=str(segment["tts_request_sha256"]),
                    runtime_audio_sha256=audio_sha256,
                    provider_media_url_sha256=None,
                    now=timestamp + 1,
                )
                asset_id = repository.record_formal_audio_write(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                    claim_token="aggregate-claim",
                    storage_key=f"formal/{scene_order}-{audio_sha256}.wav",
                    audio_sha256=audio_sha256,
                    byte_size=1_000,
                    write_completed_at=timestamp + 2,
                    readback_completed_at=timestamp + 3,
                    now=timestamp + 3,
                )
                repository.complete_formal_audio_validation(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                    claim_token="aggregate-claim",
                    asset_id=asset_id,
                    evidence={
                        "readback_sha256": audio_sha256,
                        "byte_size": 1_000,
                        "pcm_format": 1,
                        "channel_count": 1,
                        "bits_per_sample": 16,
                        "sample_rate_hz": 16_000,
                        "block_align": 2,
                        "byte_rate": 32_000,
                        "frame_count": 6_400,
                        "duration_ms": 400,
                        "normalized_peak_bps": 2_000,
                        "overall_rms_bps": 1_000,
                        "active_window_bps": 10_000,
                    },
                    now=timestamp + 4,
                )
                repository.begin_formal_asr_attempt(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                    claim_token="aggregate-claim",
                    request_sha256=asr_request_sha256,
                    now=timestamp + 5,
                )
            with self.database.transaction() as conn:
                _job, final_completed = repository.complete_formal_asr_pass(
                    conn,
                    build_item_id=build_item_id,
                    scene_order=scene_order,
                    claim_token="aggregate-claim",
                    request_sha256=asr_request_sha256,
                    transcript_sha256=transcript_sha256,
                    normalized_transcript_sha256=normalized_sha256,
                    similarity_bps=10_000,
                    now=timestamp + 6,
                )
            self.assertEqual(final_completed, scene_order == 9)

        with self.database.transaction() as conn:
            job = repository.get_formal_audio_job(
                conn, build_item_id=build_item_id
            )
            receipt = self.catalog.get_classroom_item_receipt(
                conn, build_item_id=build_item_id
            )
            segments = repository.list_formal_audio_segments(
                conn, build_item_id=build_item_id
            )
            system_reviews = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_media_quality_reviews "
                "WHERE reviewer_type = 'system'"
            ).fetchone()
        self.assertEqual(job["state"], "auto_validated")
        self.assertEqual(job["asr_passed_count"], 10)
        self.assertEqual({row["state"] for row in segments}, {"auto_validated"})
        self.assertEqual(receipt["tts_status"], "passed")
        self.assertEqual(receipt["asr_roundtrip_status"], "passed")
        self.assertEqual(receipt["auto_validated"], 0)
        self.assertEqual(receipt["approved"], 0)
        self.assertEqual(system_reviews["count"], 0)

    def test_speech_handoff_rejects_forged_count_without_thirty_058_receipts(self) -> None:
        fixture = self._seed_formal_ready_plan("audio-handoff-forgery")
        with self.database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_curriculum_preparation_plans
                SET status = 'running', stage = 'generating_speech',
                  progress_percent = 65, classroom_ready_count = 30,
                  speech_ready_count = 0, validation_ready_count = 0,
                  published_course_count = 0, next_run_at = 8100,
                  lease_token = 'audio-handoff-lease',
                  lease_expires_at = 9000, heartbeat_at = 8100,
                  hard_deadline_at = 9000, work_unit_kind = 'coordinator',
                  updated_at = 8100
                WHERE id = ?
                """,
                (fixture["plan_id"],),
            )
        with self.assertRaisesRegex(
            ValueError, "formal preparation progress is invalid"
        ):
            with self.database.transaction() as conn:
                self.preparations.persist_formal_stage_progress(
                    conn,
                    plan_id=str(fixture["plan_id"]),
                    lease_token="audio-handoff-lease",
                    target_fingerprint=str(fixture["fingerprint"]),
                    expected_stage="generating_speech",
                    classroom_ready_count=30,
                    speech_ready_count=30,
                    next_run_at=8101,
                    now=8100,
                )
        with self.database.transaction() as conn:
            plan = self.preparations.get_plan(conn, str(fixture["plan_id"]))
            audio_count = conn.execute(
                "SELECT COUNT(*) AS count FROM learning_formal_qwen_audio_jobs "
                "WHERE release_id = ?",
                (fixture["release_id"],),
            ).fetchone()
        self.assertEqual(audio_count["count"], 0)
        self.assertEqual(plan["stage"], "generating_speech")
        self.assertEqual(plan["speech_ready_count"], 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
