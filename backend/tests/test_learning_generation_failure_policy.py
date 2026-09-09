from __future__ import annotations

import unittest

from services.learning_generation_failure_policy import (
    is_transient_generation_failure,
)


class LearningGenerationFailurePolicyTest(unittest.TestCase):
    def test_provider_and_transport_failures_are_recoverable(self):
        cases = (
            ("generation_failed", "provider returned HTTP 429 Too Many Requests"),
            ("generation_failed", "You exceeded your current token quota"),
            ("dynamic_generation_failed", "connection reset by peer"),
            ("dynamic_generation_failed", "request timed out"),
            ("openmaic_unavailable", "HTTP 503 service unavailable"),
            ("generation_failed", "DNS name resolution failed"),
        )
        for code, message in cases:
            with self.subTest(code=code, message=message):
                self.assertTrue(is_transient_generation_failure(code, message))

    def test_content_and_client_failures_stay_terminal_for_the_attempt(self):
        cases = (
            ("invalid_generation", "candidate JSON was invalid"),
            ("invalid_verification", "q5 used an unsupported operand"),
            ("generation_failed", "provider returned HTTP 400 Bad Request"),
            ("generation_failed", "candidate choices were duplicated"),
            ("catalog_item_build_failed", "HTTP 429"),
        )
        for code, message in cases:
            with self.subTest(code=code, message=message):
                self.assertFalse(is_transient_generation_failure(code, message))


if __name__ == "__main__":
    unittest.main()
