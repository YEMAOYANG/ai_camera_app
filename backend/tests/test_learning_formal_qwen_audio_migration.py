from __future__ import annotations

import unittest

from core.database import Database
from tests.support import fresh_test_config


MIGRATION_VERSION = "058_learning_formal_qwen_audio_receipts.sql"


class LearningFormalQwenAudioMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/ai_camera_app_test", self.database_url)
        self.assertNotIn("/ai_camera_app_dev", self.database_url)
        self.database = Database(self.database_url)

    def test_058_registers_exact_job_and_segment_receipt_contract(self) -> None:
        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (MIGRATION_VERSION,),
            ).fetchone()
            tables = {
                row["TABLE_NAME"]
                for row in conn.execute(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ).fetchall()
            }
            columns = {
                row["TABLE_NAME"]: set()
                for row in conn.execute(
                    "SELECT DISTINCT TABLE_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ("
                    "'learning_formal_qwen_audio_jobs', "
                    "'learning_formal_qwen_audio_segment_receipts')"
                ).fetchall()
            }
            for row in conn.execute(
                "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ("
                "'learning_formal_qwen_audio_jobs', "
                "'learning_formal_qwen_audio_segment_receipts')"
            ).fetchall():
                columns[row["TABLE_NAME"]].add(row["COLUMN_NAME"])
            constraints = {
                row["CONSTRAINT_NAME"]
                for row in conn.execute(
                    "SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ).fetchall()
            }
            indexes = {
                row["INDEX_NAME"]
                for row in conn.execute(
                    "SELECT DISTINCT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                ).fetchall()
            }

        self.assertEqual(marker["count"], 1)
        self.assertTrue(
            {
                "learning_formal_qwen_audio_jobs",
                "learning_formal_qwen_audio_segment_receipts",
            }.issubset(tables)
        )
        self.assertTrue(
            {
                "build_item_id", "classroom_content_sha256", "subject",
                "teacher_profile_hash", "teacher_gender", "voice_gender",
                "tts_voice_id", "speech_manifest_sha256",
                "expected_segment_count", "tts_attempted_count",
                "tts_completed_count", "audio_validated_count",
                "asr_attempted_count", "asr_passed_count", "state",
                "terminal_receipt_hash",
            }.issubset(columns["learning_formal_qwen_audio_jobs"])
        )
        self.assertTrue(
            {
                "build_item_id", "scene_order", "scene_id", "action_id",
                "narration_segment_id", "tts_request_id", "asr_request_id",
                "tts_request_sha256", "runtime_audio_sha256",
                "readback_sha256", "sample_rate_hz", "duration_ms",
                "normalized_peak_bps", "overall_rms_bps",
                "active_window_bps", "asr_similarity_bps", "state",
                "machine_receipt_hash",
            }.issubset(columns["learning_formal_qwen_audio_segment_receipts"])
        )
        forbidden = {
            "api_key", "provider_base_url", "raw_provider_body",
            "raw_asr_transcript", "approved", "approved_by", "approved_at",
        }
        self.assertTrue(forbidden.isdisjoint(columns["learning_formal_qwen_audio_jobs"] | columns["learning_formal_qwen_audio_segment_receipts"]))
        self.assertTrue(
            {
                "chk_formal_qwen_audio_job_counts",
                "chk_formal_qwen_audio_job_voice",
                "chk_formal_qwen_audio_job_terminal",
                "chk_formal_qwen_audio_segment_state",
                "chk_formal_qwen_audio_segment_pcm",
                "fk_formal_qwen_audio_segment_job",
            }.issubset(constraints)
        )
        self.assertIn("idx_formal_qwen_audio_jobs_claim", indexes)


if __name__ == "__main__":
    unittest.main()
