from __future__ import annotations

import re
import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "071_learning_deepseek_courseware_policy.sql"
)


class LearningDeepSeekCoursewarePolicyMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.normalized = re.sub(r"\s+", " ", cls.sql).lower()

    def test_preserves_v1_kimi_receipts_and_requires_v2_deepseek_pro(self) -> None:
        required = (
            "provider_contract_version in ( 'mira.openmaic.formal-provider-readiness.v1', 'mira.openmaic.formal-provider-readiness.v2' )",
            "provider_contract_version = 'mira.openmaic.formal-provider-readiness.v1'",
            "kind = 'kimi_text'",
            "provider_id = 'kimi'",
            "model_id = 'kimi-k2.6'",
            "provider_contract_version = 'mira.openmaic.formal-provider-readiness.v2'",
            "kind = 'deepseek_text'",
            "provider_id = 'deepseek'",
            "model_id = 'deepseek-v4-pro'",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.normalized)

    def test_call_receipts_are_bound_to_the_parent_contract_version(self) -> None:
        required = (
            "add column provider_contract_version varchar(128) null",
            "set call_receipt.provider_contract_version = readiness.provider_contract_version",
            "modify column provider_contract_version varchar(128) not null",
            "unique index uq_openmaic_provider_readiness_job_contract(id, provider_contract_version)",
            "foreign key (readiness_id, provider_contract_version) references learning_openmaic_provider_readiness_jobs(id, provider_contract_version)",
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.normalized)

    def test_replaces_both_identity_checks_without_persisting_secrets(self) -> None:
        self.assertIn(
            "drop check chk_openmaic_provider_readiness_identity",
            self.normalized,
        )
        self.assertIn(
            "drop check chk_openmaic_provider_readiness_call_identity",
            self.normalized,
        )
        self.assertIn(
            "add constraint chk_openmaic_provider_readiness_identity check",
            self.normalized,
        )
        self.assertIn(
            "add constraint chk_openmaic_provider_readiness_call_identity check",
            self.normalized,
        )
        ddl = re.sub(r"--.*", "", self.normalized)
        for forbidden in (
            "api_key",
            "provider_base_url",
            "raw_provider_body",
            "raw_chat_response",
            "raw_transcript",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotRegex(
                    ddl,
                    rf"(?:^|[,( ]){re.escape(forbidden)}\s+",
                )


if __name__ == "__main__":
    unittest.main()
