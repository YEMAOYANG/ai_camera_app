from __future__ import annotations

import unittest

from scripts.generate_one_formal_course import _citation_recovery_allowed


class FormalCitationRecoveryOperatorTest(unittest.TestCase):
    def test_exact_attempt_two_failure_uses_recovery_without_attempt_three(self) -> None:
        source_job_id = "omformal_e6b6986c631a548c9756037e"
        service = type(
            "RecoveryService",
            (),
            {
                "formal_citation_recovery_enabled": True,
                "formal_citation_recovery_client": object(),
                "formal_citation_recovery_source_job_id": source_job_id,
            },
        )()
        snapshot = {
            "runtimes": [
                {
                    "id": "attempt-1",
                    "attempt_ordinal": 1,
                    "provider_attempt_ordinal": 1,
                    "status": "failed",
                    "quality_status": "rejected",
                    "error_code": "openmaic_formal_generation_failed",
                    "upstream_job_id": "omformal_first",
                    "retired_at": None,
                },
                {
                    "id": "attempt-2",
                    "attempt_ordinal": 2,
                    "provider_attempt_ordinal": 2,
                    "status": "failed",
                    "quality_status": "rejected",
                    "error_code": "openmaic_formal_generation_failed",
                    "upstream_job_id": source_job_id,
                    "retired_at": None,
                },
            ],
            "citationRecovery": None,
        }

        self.assertTrue(_citation_recovery_allowed(snapshot, service))
        snapshot["runtimes"] = [
            *snapshot["runtimes"],
            {
                "id": "attempt-3",
                "attempt_ordinal": 3,
                "provider_attempt_ordinal": 3,
                "status": "pending",
                "quality_status": "pending_review",
                "error_code": None,
                "upstream_job_id": None,
                "retired_at": None,
            },
        ]
        self.assertFalse(_citation_recovery_allowed(snapshot, service))


if __name__ == "__main__":
    unittest.main()
