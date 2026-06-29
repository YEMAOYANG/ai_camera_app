from __future__ import annotations

import unittest

from services.observation_runtime_state import (
    default_runtime_payload,
    display_freshness_from_runtime,
)


class ObservationRuntimeDisplayFreshnessTest(unittest.TestCase):
    def test_prefilter_only_when_no_kimi_or_display(self):
        self.assertEqual(
            display_freshness_from_runtime(now_ms=1_000, display={}, last_kimi_at_ms=0),
            "prefilter_only",
        )

    def test_fresh_within_window(self):
        self.assertEqual(
            display_freshness_from_runtime(
                now_ms=200_000,
                display={"observed_at": 100_000},
                last_kimi_at_ms=100_000,
            ),
            "fresh",
        )

    def test_stale_after_window(self):
        self.assertEqual(
            display_freshness_from_runtime(
                now_ms=700_000,
                display={"observed_at": 100_000},
                last_kimi_at_ms=100_000,
            ),
            "stale",
        )

    def test_runtime_payload_includes_gate_sections(self):
        payload = default_runtime_payload()
        self.assertIn("cloud_gate", payload)
        self.assertIn("care_behavior", payload)
        self.assertIn("gate_state", payload["cloud_gate"])


if __name__ == "__main__":
    unittest.main()
