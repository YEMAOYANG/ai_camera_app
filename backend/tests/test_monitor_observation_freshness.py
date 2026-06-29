from __future__ import annotations

import unittest
from unittest import mock

from routes.api.v1.camera_bridge import _normalize_monitor_observation
from services.observation_runtime_state import display_freshness_from_runtime


class MonitorObservationFreshnessTest(unittest.TestCase):
    def test_normalize_passes_through_explicit_freshness(self):
        observed_at = 1_000_000
        monitor = _normalize_monitor_observation(
            {
                "has_person": True,
                "activity": "写字",
                "confidence": 0.9,
                "observedAt": observed_at,
                "isReliable": True,
                "freshness": "stale",
            }
        )
        self.assertIsNotNone(monitor)
        assert monitor is not None
        self.assertEqual(monitor["freshness"], "stale")
        self.assertFalse(monitor["isReliable"])
        self.assertEqual(monitor["summary"], "孩子正在写字")

    def test_normalize_prefilter_only_clears_summary(self):
        monitor = _normalize_monitor_observation(
            {
                "has_person": True,
                "activity": "写字",
                "confidence": 0.9,
                "observedAt": 1_000_000,
                "isReliable": False,
                "freshness": "prefilter_only",
            }
        )
        self.assertIsNotNone(monitor)
        assert monitor is not None
        self.assertEqual(monitor["freshness"], "prefilter_only")
        self.assertFalse(monitor["isReliable"])
        self.assertEqual(monitor["summary"], "")

    def test_normalize_computes_freshness_when_missing(self):
        now_ms = 600_000
        observed_at = now_ms - 120_000
        with mock.patch("routes.api.v1.camera_bridge.now_ms", return_value=now_ms):
            monitor = _normalize_monitor_observation(
                {
                    "has_person": True,
                    "activity": "看书",
                    "confidence": 0.88,
                    "observedAt": observed_at,
                    "isReliable": True,
                }
            )
        self.assertIsNotNone(monitor)
        assert monitor is not None
        self.assertEqual(monitor["freshness"], "fresh")
        self.assertTrue(monitor["isReliable"])

    def test_display_freshness_matches_runtime_helper(self):
        now_ms = 900_000
        observed_at = now_ms - 400_000
        expected = display_freshness_from_runtime(
            now_ms=now_ms,
            display={"observed_at": observed_at},
            last_kimi_at_ms=observed_at,
        )
        with mock.patch("routes.api.v1.camera_bridge.now_ms", return_value=now_ms):
            monitor = _normalize_monitor_observation(
                {
                    "has_person": True,
                    "activity": "写字",
                    "confidence": 0.9,
                    "observedAt": observed_at,
                    "isReliable": True,
                    "last_kimi_at_ms": observed_at,
                }
            )
        self.assertIsNotNone(monitor)
        assert monitor is not None
        self.assertEqual(monitor["freshness"], expected)


if __name__ == "__main__":
    unittest.main()
