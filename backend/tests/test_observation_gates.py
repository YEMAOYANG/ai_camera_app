from __future__ import annotations

import unittest

from services.observation_payload_builder import build_primary_payload
from services.observation_absence_mode import should_skip_vision_before_analyze, update_absence_after_analysis
from services.observation_session_state import risk_escalated, session_snapshot_from_observation, should_force_screen_use_resample, should_post_observation
from services.vision_frame_gate import compute_dhash, frame_is_stable, hamming_distance
from services.camera_command_service import lightweight_camera_event_from_observation
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
            "recorded_absent": True,
            "next_check_at": 999_999,
        }
        skip, reason = should_skip_vision_before_analyze(
            absence,
            now_ms=100_000,
            force_analyze=False,
        )
        self.assertTrue(skip)
        self.assertEqual(reason, "absence_prefilter_skip")

    def test_absence_mode_analyzes_when_prefilter_activity(self):
        absence = {
            "mode": "absence",
            "consecutive_no_person": 3,
            "recorded_absent": True,
            "next_check_at": 999_999,
        }
        skip, reason = should_skip_vision_before_analyze(
            absence,
            now_ms=100_000,
            force_analyze=False,
            prefilter_activity=True,
        )
        self.assertFalse(skip)
        self.assertEqual(reason, "")

    def test_absence_mode_analyzes_when_person_detected(self):
        absence = {
            "mode": "absence",
            "consecutive_no_person": 3,
            "recorded_absent": True,
            "next_check_at": 999_999,
        }
        skip, reason = should_skip_vision_before_analyze(
            absence,
            now_ms=100_000,
            force_analyze=False,
            prefilter_person=True,
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

    def test_toy_play_near_dining_table_not_meal(self):
        payload = build_primary_payload(
            {
                "has_person": True,
                "activity": "吃饭",
                "description": "小爱坐在餐桌旁玩玩具车，手中拿着玩具。",
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
        self.assertEqual(payload["scenario"], "toy_cleanup")
        self.assertEqual(payload["signals"][0]["signalType"], "toy_playing_observed")

    def test_cleanup_started_payload(self):
        payload = build_primary_payload(
            {
                "has_person": True,
                "activity": "收玩具",
                "description": "小爱正在把玩具车放进收纳盒。",
                "confidence": 0.9,
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
        self.assertEqual(payload["scenario"], "toy_cleanup")
        self.assertEqual(payload["signals"][0]["signalType"], "cleanup_started")
        self.assertFalse(payload["recordCareEvent"])

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

    def test_lightweight_event_absent_no_screen_message(self):
        obs = enrich_observation(
            {
                "has_person": False,
                "description": "孩子在看屏幕，注意用眼距离。",
                "activity": "其他",
            }
        )
        event = lightweight_camera_event_from_observation(
            event_id="evt_absent",
            device_id="dev_1",
            observation=obs,
            now=1_000,
        )
        self.assertNotIn("看屏幕", event["displayMessage"])
        self.assertNotIn("看屏幕", event.get("displayTitle", ""))

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

    def test_screen_use_resample_after_interval(self):
        previous = {
            "bucket": "screen_use",
            "risk": "screen_use_sustained",
            "last_record_at": 1_000,
        }
        current = {"bucket": "screen_use", "risk": "screen_use_sustained"}
        self.assertFalse(
            should_force_screen_use_resample(
                previous_session=previous,
                current_session=current,
                now_ms=90_000,
                interval_seconds=90,
            )
        )
        self.assertTrue(
            should_force_screen_use_resample(
                previous_session=previous,
                current_session=current,
                now_ms=91_000,
                interval_seconds=90,
            )
        )

    def test_screen_use_resample_not_for_other_buckets(self):
        self.assertFalse(
            should_force_screen_use_resample(
                previous_session={"bucket": "homework", "risk": "low_head", "last_record_at": 1_000},
                current_session={"bucket": "homework", "risk": "low_head"},
                now_ms=200_000,
            )
        )

    def _resolve_post_reason(
        self,
        *,
        force_post: bool,
        previous_session: dict,
        current_session: dict,
        should_post: bool,
        post_reason: str,
        now_ms: int,
    ) -> tuple[bool, str]:
        screen_use_resample = should_force_screen_use_resample(
            previous_session=previous_session,
            current_session=current_session,
            now_ms=now_ms,
        )
        post_force = (
            force_post
            or risk_escalated(previous_session, current_session)
            or screen_use_resample
        )
        if screen_use_resample and not should_post:
            post_reason = "screen_use_resample"
        return post_force, post_reason

    def test_force_post_does_not_mark_screen_use_resample(self):
        previous = {"bucket": "homework", "risk": "low_head", "last_record_at": 1_000}
        current = {"bucket": "homework", "risk": "low_head"}
        should_post, post_reason = should_post_observation(
            previous_session=previous,
            current_session=current,
            has_person=True,
            absence_mode="active",
            recorded_absent=False,
        )
        post_force, resolved_reason = self._resolve_post_reason(
            force_post=True,
            previous_session=previous,
            current_session=current,
            should_post=should_post,
            post_reason=post_reason,
            now_ms=200_000,
        )
        self.assertTrue(post_force)
        self.assertFalse(should_post)
        self.assertEqual(resolved_reason, "session_stable")

    def test_meal_risk_escalation_does_not_mark_screen_use_resample(self):
        previous = {"bucket": "meal", "risk": "meal_seated", "last_record_at": 1_000}
        current = {"bucket": "meal", "risk": "meal_standing"}
        should_post, post_reason = should_post_observation(
            previous_session=previous,
            current_session=current,
            has_person=True,
            absence_mode="active",
            recorded_absent=False,
        )
        post_force, resolved_reason = self._resolve_post_reason(
            force_post=False,
            previous_session=previous,
            current_session=current,
            should_post=should_post,
            post_reason=post_reason,
            now_ms=200_000,
        )
        self.assertTrue(post_force)
        self.assertTrue(should_post)
        self.assertEqual(resolved_reason, "session_changed")


def _tiny_png() -> bytes:
    from PIL import Image
    import io

    image = Image.new("RGB", (32, 32), color=(120, 140, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
