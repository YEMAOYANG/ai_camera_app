from __future__ import annotations

import unittest

from core.database import Database
from tests.support import fresh_test_config


# The PostgreSQL baseline carries the contract MySQL migration 058 added.
BASELINE_VERSION = "100_postgres_baseline_schema.sql"


class LearningFormalQwenAudioMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]
        self.assertIn("/mira_test", self.database_url)
        self.assertNotRegex(self.database_url, r"/mira(\?|$)")
        self.database = Database(self.database_url)

    def test_baseline_registers_exact_job_and_segment_receipt_contract(self) -> None:
        with self.database.transaction() as conn:
            marker = conn.execute(
                "SELECT COUNT(*) AS count FROM schema_migrations WHERE version = ?",
                (BASELINE_VERSION,),
            ).fetchone()
            tables = {
                row["table_name"]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema()"
                ).fetchall()
            }
            columns = {
                row["table_name"]: set()
                for row in conn.execute(
                    "SELECT DISTINCT table_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name IN ("
                    "'learning_formal_qwen_audio_jobs', "
                    "'learning_formal_qwen_audio_segment_receipts')"
                ).fetchall()
            }
            for row in conn.execute(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name IN ("
                "'learning_formal_qwen_audio_jobs', "
                "'learning_formal_qwen_audio_segment_receipts')"
            ).fetchall():
                columns[row["table_name"]].add(row["column_name"])
            constraints = {
                row["constraint_name"]
                for row in conn.execute(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_schema = current_schema()"
                ).fetchall()
            }
            indexes = {
                row["indexname"]
                for row in conn.execute(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
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
