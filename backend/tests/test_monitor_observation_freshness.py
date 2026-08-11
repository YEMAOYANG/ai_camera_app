from __future__ import annotations

import unittest
from unittest import mock

from routes.api.v1.camera_bridge import (
    _merge_runtime_display_into_response,
    _merge_stored_observation_into_response,
    _normalize_monitor_observation,
    _runtime_display_freshness,
)
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

    def test_prefilter_runtime_does_not_replace_stored_kimi_result(self):
        response = {
            "monitor": {
                "lastObservation": {
                    "summary": "暂未看到孩子",
                    "description": "客厅暂时没有看到孩子。",
                    "observedAt": 100_000,
                    "isReliable": False,
                    "freshness": "stale",
                }
            }
        }
        prefilter = {
            "summary": "",
            "description": "",
            "observedAt": 200_000,
            "isReliable": False,
            "freshness": "prefilter_only",
        }

        with mock.patch(
            "routes.api.v1.camera_bridge._latest_runtime_display_observation",
            return_value=prefilter,
        ):
            _merge_runtime_display_into_response(
                response,
                family_id="fam",
                child_id="child",
                device_id="dev",
            )

        self.assertEqual(
            response["monitor"]["lastObservation"]["summary"],
            "暂未看到孩子",
        )
        self.assertEqual(
            response["monitor"]["lastObservation"]["freshness"],
            "stale",
        )

    def test_unreliable_fresh_runtime_does_not_replace_stored_kimi_result(self):
        response = {
            "monitor": {
                "lastObservation": {
                    "summary": "暂未看到孩子",
                    "description": "客厅暂时没有看到孩子。",
                    "observedAt": 100_000,
                    "isReliable": False,
                    "freshness": "stale",
                }
            }
        }
        unreliable = {
            "summary": "",
            "description": "画面已更新，仍待确认",
            "observedAt": 200_000,
            "isReliable": False,
            "freshness": "fresh",
        }

        with mock.patch(
            "routes.api.v1.camera_bridge._latest_runtime_display_observation",
            return_value=unreliable,
        ):
            _merge_runtime_display_into_response(
                response,
                family_id="fam",
                child_id="child",
                device_id="dev",
            )

        self.assertEqual(
            response["monitor"]["lastObservation"]["summary"],
            "暂未看到孩子",
        )
        self.assertEqual(
            response["monitor"]["lastObservation"]["freshness"],
            "stale",
        )

    def test_refresh_response_restores_stored_result_over_unreliable_current(self):
        response = {
            "monitor": {
                "status": "refreshed",
                "lastObservation": {
                    "summary": "画面已更新，仍待确认",
                    "description": "画面已更新，仍待确认",
                    "observedAt": 200_000,
                    "isReliable": False,
                    "freshness": "fresh",
                },
            }
        }
        stored = {
            "summary": "暂未看到孩子",
            "description": "客厅暂时没有看到孩子。",
            "observedAt": 100_000,
            "isReliable": False,
            "freshness": "stale",
        }

        with mock.patch(
            "routes.api.v1.camera_bridge._latest_stored_observation",
            return_value=stored,
        ):
            _merge_stored_observation_into_response(
                response,
                family_id="fam",
                device_id="dev",
                trust_current=True,
            )

        self.assertEqual(
            response["monitor"]["lastObservation"]["summary"],
            "暂未看到孩子",
        )
        self.assertEqual(response["monitor"]["message"], "观察已刷新")

    def test_prefilter_runtime_is_visible_before_first_kimi_result(self):
        response = {"monitor": {"lastObservation": None}}
        prefilter = {
            "summary": "",
            "description": "",
            "observedAt": 200_000,
            "isReliable": False,
            "freshness": "prefilter_only",
        }

        with mock.patch(
            "routes.api.v1.camera_bridge._latest_runtime_display_observation",
            return_value=prefilter,
        ):
            _merge_runtime_display_into_response(
                response,
                family_id="fam",
                child_id="child",
                device_id="dev",
            )

        self.assertEqual(response["monitor"]["lastObservation"], prefilter)

    def test_preserved_runtime_result_becomes_stale_by_age(self):
        now_ms = 900_000
        observed_at = now_ms - 400_000
        with mock.patch("routes.api.v1.camera_bridge.now_ms", return_value=now_ms):
            freshness = _runtime_display_freshness(
                {
                    "observed_at": observed_at,
                    "freshness": "fresh",
                    "isReliable": True,
                },
                last_kimi_at_ms=observed_at,
            )

        self.assertEqual(freshness, "stale")

    def test_runtime_prefilter_freshness_remains_explicit(self):
        with mock.patch(
            "routes.api.v1.camera_bridge.now_ms",
            return_value=900_000,
        ):
            freshness = _runtime_display_freshness(
                {
                    "observed_at": 100_000,
                    "freshness": "prefilter_only",
                    "isReliable": False,
                },
                last_kimi_at_ms=0,
            )

        self.assertEqual(freshness, "prefilter_only")


if __name__ == "__main__":
    unittest.main()
