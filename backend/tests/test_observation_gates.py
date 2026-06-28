from __future__ import annotations

import unittest

from services.observation_payload_builder import build_primary_payload
from services.observation_absence_mode import should_skip_vision_before_analyze, update_absence_after_analysis
from services.observation_session_state import session_snapshot_from_observation, should_post_observation
from services.vision_frame_gate import compute_dhash, frame_is_stable, hamming_distance
from services.vision_observation_enrich import enrich_observation, sanitize_absent_observation


class ObservationGateTest(unittest.TestCase):
    def test_dhash_stable_when_same_image(self):
        image = _tiny_png()
        first = compute_dhash(image)
        second = compute_dhash(image)
        self.assertEqual(first, second)
        self.assertEqual(hamming_distance(first, second), 0)
        self.assertTrue(
            frame_is_stable(
                previous={"hash": first, "last_changed_at": 1_000},
                current_hash=second,
                now_ms=120_000,
            )
        )

    def test_absence_mode_skips_before_interval(self):
        absence = {
            "mode": "absence",
            "consecutive_no_person": 3,
            "next_check_at": 999_999,
        }
        skip, reason = should_skip_vision_before_analyze(
            absence,
            now_ms=100_000,
            frame_stable=True,
            force_analyze=False,
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "absence_stable_skip")

    def test_absence_mode_analyzes_when_frame_changed(self):
        absence = {
            "mode": "absence",
            "consecutive_no_person": 3,
            "next_check_at": 999_999,
        }
        skip, reason = should_skip_vision_before_analyze(
            absence,
            now_ms=100_000,
            frame_stable=False,
            force_analyze=False,
        )
        self.assertFalse(skip)
        self.assertEqual(reason, "")

    def test_absence_resets_when_person_returns(self):
        absence = update_absence_after_analysis(
            {"mode": "absence", "consecutive_no_person": 5, "recorded_absent": True},
            has_person=True,
            now_ms=200_000,
            frame_stable=False,
        )
        self.assertEqual(absence["mode"], "active")
        self.assertEqual(absence["consecutive_no_person"], 0)

    def test_absent_description_sanitized(self):
        obs = sanitize_absent_observation(
            {
                "has_person": False,
                "description": "孩子在看屏幕，注意用眼距离。",
                "activity": "其他",
            }
        )
        self.assertNotIn("看屏幕", obs["description"])
        self.assertEqual(obs["activity"], "离开")

    def test_meal_standing_single_payload(self):
        payload = build_primary_payload(
            {
                "has_person": True,
                "activity": "玩玩具",
                "description": "孩子站在餐椅上，身体前倾拿食物。",
                "confidence": 0.86,
            },
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            source="test",
            window_start_ms=1_000,
            window_end_ms=4_000,
            observed_at=4_000,
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "meal_habit")
        self.assertEqual(payload["signals"][0]["signalType"], "meal_standing_on_chair")
        self.assertTrue(payload["recordCareEvent"])

    def test_toy_play_unsafe_payload(self):
        payload = build_primary_payload(
            {
                "has_person": True,
                "activity": "玩玩具",
                "description": "孩子正在爬茶几玩积木。",
                "confidence": 0.84,
            },
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            source="test",
            window_start_ms=1_000,
            window_end_ms=4_000,
            observed_at=4_000,
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["signals"][0]["signalType"], "toy_play_unsafe_climbing")

    def test_meal_eating_observed_payload(self):
        payload = build_primary_payload(
            {
                "has_person": True,
                "activity": "玩玩具",
                "description": "小爱坐在远处餐桌旁用餐，客厅中央有蹦床。",
                "confidence": 0.86,
            },
            family_id="fam_1",
            child_id="child_1",
            device_id="dev_1",
            source="test",
            window_start_ms=1_000,
            window_end_ms=4_000,
            observed_at=4_000,
        )
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["scenario"], "meal_habit")
        self.assertEqual(payload["signals"][0]["signalType"], "meal_eating_observed")
        self.assertTrue(payload["recordCareEvent"])

    def test_session_absent_only_records_once(self):
        should_post, reason = should_post_observation(
            previous_session={"bucket": "absent", "risk": "absent"},
            current_session={"bucket": "absent", "risk": "absent"},
            has_person=False,
            absence_mode="absence",
            recorded_absent=True,
        )
        self.assertFalse(should_post)
        self.assertEqual(reason, "absent_already_recorded")

    def test_enrich_meal_scene_normalizes_toy_activity(self):
        obs = enrich_observation(
            {
                "has_person": True,
                "activity": "玩玩具",
                "description": "孩子在餐桌前吃饭，站在餐椅上。",
                "confidence": 0.8,
            }
        )
        snapshot = session_snapshot_from_observation(obs)
        self.assertEqual(obs["activity"], "吃饭")
        self.assertEqual(snapshot["risk"], "meal_standing")


def _tiny_png() -> bytes:
    from PIL import Image
    import io

    image = Image.new("RGB", (32, 32), color=(120, 140, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
