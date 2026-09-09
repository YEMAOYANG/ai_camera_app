from __future__ import annotations

import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "059_learning_openmaic_provider_readiness.sql"
)


class LearningOpenMaicProviderReadinessMigrationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.normalized = re.sub(r"\s+", " ", cls.sql).lower()

    def test_keeps_route_session_and_provider_proof_distinct(self) -> None:
        self.assertIn("route_session_receipt_hash char(64) not null", self.normalized)
        self.assertIn("route_session_provider_call tinyint not null default 0", self.normalized)
        self.assertIn("provider_receipt_hash char(64)", self.normalized)
        self.assertIn("route_session_provider_call = 0", self.normalized)
        self.assertIn("provider_call = 1", self.normalized)
        self.assertNotIn("provider_call = 0 and state = 'auto_validated'", self.normalized)

    def test_exactly_binds_057_runtime_and_058_audio_evidence(self) -> None:
        required = (
            "references learning_curriculum_classroom_item_receipts",
            "references learning_openmaic_runtime_classrooms",
            "references learning_formal_qwen_audio_jobs",
            "references learning_formal_qwen_audio_segment_receipts",
            "audio_job_state = 'auto_validated'",
            "validation_segment_state = 'auto_validated'",
            "validation_audio_sha256",
            "validation_audio_machine_receipt_hash",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.normalized)

    def test_provider_call_ledger_is_exact_and_attempt_first(self) -> None:
        required = (
            "expected_provider_call_count = 5",
            "provider_attempted_count <= expected_provider_call_count",
            "provider_passed_count <= provider_attempted_count",
            "kind = 'kimi_text'",
            "kind = 'qwen_asr'",
            "kind = 'qwen_tts'",
            "provider_id = 'kimi'",
            "model_id = 'kimi-k2.6'",
            "provider_id = 'qwen-asr'",
            "model_id = 'qwen3-asr-flash'",
            "provider_id = 'qwen-tts'",
            "model_id = 'qwen3-tts-flash'",
            "voice_id = 'serena'",
            "voice_id = 'ethan'",
            "voice_id = 'jennifer'",
            "attempted_at bigint not null",
            "completed_at >= attempted_at",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.normalized)

    def test_schema_forbids_raw_or_secret_persistence(self) -> None:
        forbidden_columns = (
            "api_key",
            "provider_base_url",
            "raw_provider_body",
            "raw_chat_response",
            "raw_transcript",
            "audio_body",
            "audio_url",
            "audio_base64",
            "secret",
        )
        ddl = re.sub(r"--.*", "", self.normalized)
        for name in forbidden_columns:
            with self.subTest(name=name):
                self.assertNotRegex(ddl, rf"(?:^|[,( ]){re.escape(name)}\s+")

    def test_has_claim_publication_and_receipt_indexes(self) -> None:
        for index in (
            "idx_openmaic_provider_readiness_claim",
            "idx_openmaic_provider_readiness_release",
            "idx_openmaic_provider_readiness_calls",
        ):
            self.assertIn(index, self.normalized)

    def test_line_comments_cannot_split_the_migration_runner(self) -> None:
        comments = [
            line for line in self.sql.splitlines() if line.lstrip().startswith("--")
        ]
        self.assertTrue(comments)
        self.assertTrue(all(";" not in line for line in comments))


if __name__ == "__main__":
    unittest.main()
