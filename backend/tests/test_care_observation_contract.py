from __future__ import annotations

from datetime import datetime
import json
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from core.database import Database
from core.security import now_ms
from models.care import (
    REMINDER_DECISION_ALLOWED,
    REMINDER_DECISION_PARENT_NOTIFY,
    REMINDER_DECISION_RECORD_ONLY,
    REMINDER_DECISION_SKIPPED_COOLDOWN,
    REMINDER_DECISION_SKIPPED_LOW_CONFIDENCE,
    REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
    REMINDER_EVENT_SOURCE_DRY_RUN,
    REMINDER_EVENT_SOURCE_INTERNAL,
    REMINDER_EVENT_SOURCE_TEST,
    REMINDER_STATUS_COMMAND_SENT,
    REMINDER_STATUS_FAILED,
    REMINDER_STATUS_GENERATED,
)
from repositories.care_repository import CareRepository
from services.ai_care_reminder_service import AiCareReminderService
from services.ai_text_provider import AiTextResponse
from services.prompt_registry import PromptRegistry
from services import task_event_stream
from services.routine_reminder_service import RoutineReminderService
from tests.support import fresh_test_config, request_debug_code


class CareObservationContractTest(unittest.TestCase):
    def setUp(self):
        self.internal_token = "test-internal-token"
        self.app = create_app(
            fresh_test_config(
                CAMERA_RUNTIME_PROVIDER="mock",
                INTERNAL_API_TOKEN=self.internal_token,
            )
        )
        self.client = self.app.test_client()
        self.access_token = self._login("13800004026")
        self.child_id = self._create_child("小雨")
        self._source_seq = 0

    def test_care_capabilities_defaults_and_patch(self):
        unauthenticated = self.client.get("/api/care/capabilities")
        self.assertEqual(unauthenticated.status_code, 401)

        response = self.client.get(
            "/api/care/capabilities",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        scenarios = {item["scenario"] for item in response.json["capabilities"]}
        self.assertEqual(
            scenarios,
            {
                "posture",
                "toy_cleanup",
                "meal_start",
                "meal_habit",
                "nap_time",
                "bedtime",
                "wake_up",
                "transition",
            },
        )
        self.assertTrue(all(item["enabled"] for item in response.json["capabilities"]))
        self.assertNotIn("promptId", response.json["capabilities"][0])

        patched = self.client.patch(
            "/api/care/capabilities",
            json={
                "childId": self.child_id,
                "capabilities": [{"scenario": "toy_cleanup", "enabled": False}],
            },
            headers=self._auth_headers(),
        )

        self.assertEqual(patched.status_code, 200)
        cleanup = next(item for item in patched.json["capabilities"] if item["scenario"] == "toy_cleanup")
        self.assertFalse(cleanup["enabled"])

    def test_routine_windows_can_be_replaced(self):
        defaults = self.client.get(
            "/api/care/routine-windows",
            query_string={"childId": self.child_id, "dayType": "school_day"},
            headers=self._auth_headers(),
        )
        self.assertEqual(defaults.status_code, 200)
        self.assertGreaterEqual(len(defaults.json["windows"]), 6)

        replacement = self.client.put(
            "/api/care/routine-windows",
            json={
                "childId": self.child_id,
                "windows": [
                    {
                        "dayType": "school_day",
                        "windowType": "wake_up",
                        "startTime": "07:15",
                        "endTime": "08:05",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                    {
                        "dayType": "weekend",
                        "windowType": "wake_up",
                        "startTime": "08:20",
                        "endTime": "09:20",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                ],
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(replacement.status_code, 200)
        self.assertEqual(len(replacement.json["windows"]), 2)
        self.assertEqual(replacement.json["windows"][0]["startTime"], "07:15")

    def test_visible_routine_replacement_does_not_gate_toy_cleanup(self):
        self._ensure_capabilities()
        replacement = self.client.put(
            "/api/care/routine-windows",
            query_string={"dayType": "school_day"},
            json={
                "childId": self.child_id,
                "windows": [
                    {
                        "dayType": "school_day",
                        "windowType": "wake_up",
                        "startTime": "07:00",
                        "endTime": "08:00",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                    {
                        "dayType": "school_day",
                        "windowType": "breakfast",
                        "startTime": "07:20",
                        "endTime": "08:20",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                    {
                        "dayType": "school_day",
                        "windowType": "lunch",
                        "startTime": "11:30",
                        "endTime": "12:30",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                    {
                        "dayType": "school_day",
                        "windowType": "nap",
                        "startTime": "12:40",
                        "endTime": "14:20",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                    {
                        "dayType": "school_day",
                        "windowType": "dinner",
                        "startTime": "17:30",
                        "endTime": "18:40",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                    {
                        "dayType": "school_day",
                        "windowType": "bedtime",
                        "startTime": "20:30",
                        "endTime": "21:20",
                        "enabled": True,
                        "timezone": "Asia/Shanghai",
                    },
                ],
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(replacement.status_code, 200)
        self.assertEqual(
            {row["windowType"] for row in replacement.json["windows"]},
            {"wake_up", "breakfast", "lunch", "nap", "dinner", "bedtime"},
        )

        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )
        allowed = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=5,
            signal_type="toys_scattered",
            observed_at=_ms("2026-06-17 10:30"),
        )

        self.assertEqual(allowed.json["decision"]["decision"], "allowed")
        self.assertTrue(allowed.json["decision"]["shouldSpeak"])

    def test_posture_risk_is_behavior_driven_not_blocked_by_routine_window(self):
        self._ensure_capabilities()
        self._patch_capability(
            "posture",
            minObservationSeconds=1,
            observationThreshold=0.74,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        response = self._post_observation(
            "posture",
            confidence=0.70,
            duration_seconds=5,
            signal_type="leaning_too_close",
            parent_summary="观察到坐姿需要留意。",
            observed_at=_ms("2026-06-17 10:30"),
            raw_detail={
                "has_person": True,
                "activity": "写作业/看书",
                "posture_status": "leaning_too_close",
                "description": "孩子头离纸面太近。",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["decision"]["decision"], "allowed")
        self.assertTrue(response.json["decision"]["shouldSpeak"])
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            decision = repository.get_reminder_decision(
                conn,
                decision_id=response.json["decision"]["id"],
            )
        snapshot = json.loads(decision["policy_snapshot_json"])
        self.assertEqual(snapshot["confidenceThreshold"], 0.68)
        self.assertEqual(snapshot["routineGate"]["reason"], "behavior_only_scenario")

    def test_posture_risk_uses_short_effective_observation_window(self):
        self._ensure_capabilities()
        self._patch_capability(
            "posture",
            minObservationSeconds=30,
            observationThreshold=0.74,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        response = self._post_observation(
            "posture",
            confidence=0.70,
            duration_seconds=3,
            signal_type="low_head",
            parent_summary="观察到坐姿需要留意。",
            observed_at=_ms("2026-06-17 10:30"),
            raw_detail={
                "has_person": True,
                "activity": "写作业/看书",
                "posture_status": "low_head",
                "description": "孩子头离纸面太近。",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["decision"]["decision"], "allowed")
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            decision = repository.get_reminder_decision(
                conn,
                decision_id=response.json["decision"]["id"],
            )
        snapshot = json.loads(decision["policy_snapshot_json"])
        self.assertEqual(snapshot["minObservationSeconds"], 3)

    def test_internal_observation_requires_token_and_low_score_records_only(self):
        self._ensure_capabilities()
        missing = self.client.post(
            "/internal/camera/observations",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": self.device_id,
                "scenario": "toy_cleanup",
                "confidence": 0.2,
            },
        )
        self.assertEqual(missing.status_code, 401)

        accepted = self.client.post(
            "/internal/camera/observations",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": self.device_id,
                "scenario": "toy_cleanup",
                "sourceEventId": "obs_contract_001",
                "confidence": 0.2,
                "evidenceType": "snapshot",
                "parentSummary": "玩具散落，观察分数较低。",
                "signals": [
                    {
                        "signalType": "toys_scattered",
                        "signalValue": "observed",
                        "confidence": 0.2,
                        "durationSeconds": 10,
                    }
                ],
            },
            headers={"X-Mira-Internal-Token": self.internal_token},
        )

        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json["decision"]["decision"], "skipped_low_confidence")
        self.assertFalse(accepted.json["decision"]["shouldSpeak"])
        self.assertEqual(accepted.json["observation"]["scenario"], "toy_cleanup")

        duplicate = self.client.post(
            "/internal/camera/observations",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": self.device_id,
                "scenario": "toy_cleanup",
                "sourceEventId": "obs_contract_001",
                "confidence": 0.9,
            },
            headers={"X-Mira-Internal-Token": self.internal_token},
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json["duplicate"])
        self.assertEqual(duplicate.json["observation"]["id"], accepted.json["observation"]["id"])

    def test_internal_observation_rejects_invalid_or_unbound_device(self):
        missing = self.client.post(
            "/internal/camera/observations",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": "dev_missing",
                "scenario": "toy_cleanup",
                "confidence": 0.9,
            },
            headers={"X-Mira-Internal-Token": self.internal_token},
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json["error"], "device_not_found")

        unbind = self.client.post(
            f"/api/devices/{self.device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbind.status_code, 200)
        unbound = self.client.post(
            "/internal/camera/observations",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": self.device_id,
                "scenario": "toy_cleanup",
                "confidence": 0.9,
            },
            headers={"X-Mira-Internal-Token": self.internal_token},
        )
        self.assertEqual(unbound.status_code, 409)
        self.assertEqual(unbound.json["error"], "device_unbound")

    def test_internal_observation_initializes_default_capabilities_and_routine_windows_without_flutter_setup(self):
        response = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=180,
            signal_type="toys_scattered",
            observed_at=_ms("2026-06-17 19:30"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["decision"]["decision"], "allowed")
        self.assertTrue(response.json["decision"]["shouldSpeak"])

    def test_continuous_observation_accumulates_until_policy_allows(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=15,
            cooldownSeconds=0,
            dailyLimit=4,
            parentNotifyThreshold=3,
        )
        start = _ms("2026-06-17 19:30")

        first = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=5,
            signal_type="toys_scattered",
            observed_at=_ms("2026-06-17 19:30"),
        )
        second = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=10,
            signal_type="toys_scattered",
            observed_at=_ms("2026-06-17 19:30") + 10_000,
        )

        self.assertEqual(first.json["decision"]["decision"], "skipped_continuity")
        self.assertEqual(second.json["decision"]["decision"], "allowed")
        self.assertTrue(second.json["decision"]["shouldSpeak"])

    def test_policy_decisions_cover_stage_2a_rules(self):
        self._ensure_capabilities()

        self._patch_capability("toy_cleanup", enabled=False)
        disabled = self._post_observation("toy_cleanup", confidence=0.9, duration_seconds=60)
        self.assertEqual(disabled.json["decision"]["decision"], "skipped_disabled")
        self.assertFalse(disabled.json["decision"]["shouldSpeak"])

        self._patch_capability("toy_cleanup", enabled=True, recordOnly=True)
        record_only = self._post_observation("toy_cleanup", confidence=0.9, duration_seconds=60)
        self.assertEqual(record_only.json["decision"]["decision"], "record_only")
        self.assertFalse(record_only.json["decision"]["shouldSpeak"])

        self._patch_capability("toy_cleanup", recordOnly=False, observationThreshold=0.8)
        low = self._post_observation("toy_cleanup", confidence=0.2, duration_seconds=60)
        self.assertEqual(low.json["decision"]["decision"], "skipped_low_confidence")

        self._patch_capability(
            "toy_cleanup",
            observationThreshold=0.72,
            cooldownSeconds=0,
            dailyLimit=4,
            parentNotifyThreshold=3,
            allowSpeaker=False,
        )
        toy_speaker_off = self._post_observation("toy_cleanup", confidence=0.9, duration_seconds=180)
        self.assertEqual(toy_speaker_off.json["decision"]["decision"], "record_only")
        self.assertFalse(toy_speaker_off.json["decision"]["shouldSpeak"])

        short = self._post_observation("posture", confidence=0.9, duration_seconds=1)
        self.assertEqual(short.json["decision"]["decision"], "skipped_continuity")

        self._patch_capability("toy_cleanup", allowSpeaker=True, cooldownSeconds=1200)
        self._create_real_reminder_event("toy_cleanup")
        cooldown = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=180,
        )
        self.assertEqual(cooldown.json["decision"]["decision"], "skipped_cooldown")

        self._patch_capability("meal_habit", cooldownSeconds=0, dailyLimit=1)
        self._create_real_reminder_event("meal_habit")
        limited = self._post_observation("meal_habit", confidence=0.9, duration_seconds=60)
        self.assertEqual(limited.json["decision"]["decision"], "skipped_daily_limit")

        self._patch_capability("bedtime", cooldownSeconds=0, dailyLimit=4, parentNotifyThreshold=1)
        self._create_real_reminder_event("bedtime")
        notify = self._post_observation("bedtime", confidence=0.9, duration_seconds=80)
        self.assertEqual(notify.json["decision"]["decision"], "parent_notify")
        self.assertTrue(notify.json["decision"]["shouldNotifyParent"])
        self.assertIsNotNone(notify.json["reviewItem"])
        self.assertEqual(notify.json["reviewItem"]["domain"], "care")
        self.assertNotIn("backend", notify.json["reviewItem"]["summary"])

        notify_again = self._post_observation("bedtime", confidence=0.9, duration_seconds=80)
        self.assertEqual(notify_again.json["reviewItem"]["id"], notify.json["reviewItem"]["id"])

        self._patch_capability("meal_start", cooldownSeconds=0, dailyLimit=2, parentNotifyThreshold=2)
        self._create_real_reminder_event("meal_start")
        self._create_real_reminder_event("meal_start")
        notify_at_limit = self._post_observation("meal_start", confidence=0.9, duration_seconds=60)
        self.assertEqual(notify_at_limit.json["decision"]["decision"], "parent_notify")
        self.assertTrue(notify_at_limit.json["decision"]["shouldNotifyParent"])

        self._patch_capability("wake_up", cooldownSeconds=0, dailyLimit=4, parentNotifyThreshold=3, allowSpeaker=False)
        speaker_off = self._post_observation("wake_up", confidence=0.9, duration_seconds=60)
        self.assertEqual(speaker_off.json["decision"]["decision"], "record_only")
        self.assertFalse(speaker_off.json["decision"]["shouldSpeak"])

        self._patch_capability("transition", cooldownSeconds=0, dailyLimit=4, parentNotifyThreshold=3, allowSpeaker=True)
        self._patch_capability("wake_up", cooldownSeconds=0, dailyLimit=4, parentNotifyThreshold=3, allowSpeaker=True)
        allowed = self._post_observation(
            "wake_up",
            confidence=0.9,
            duration_seconds=60,
            signal_type="wake_up_late",
            observed_at=_ms("2026-06-17 07:30"),
        )
        self.assertEqual(allowed.json["decision"]["decision"], "allowed")
        self.assertTrue(allowed.json["decision"]["shouldSpeak"])

    def test_test_and_dry_run_reminders_do_not_count_for_policy_limits(self):
        self._ensure_capabilities()
        self._patch_capability("nap_time", cooldownSeconds=1200, dailyLimit=1)
        self._create_real_reminder_event("nap_time", event_source=REMINDER_EVENT_SOURCE_TEST, is_test=True)
        self._create_real_reminder_event("nap_time", event_source=REMINDER_EVENT_SOURCE_DRY_RUN, is_test=False)

        allowed = self._post_observation(
            "nap_time",
            confidence=0.9,
            duration_seconds=80,
            signal_type="still_active",
            observed_at=_ms("2026-06-17 13:10"),
        )

        self.assertEqual(allowed.json["decision"]["decision"], "allowed")
        self.assertTrue(allowed.json["decision"]["shouldSpeak"])

    def test_recent_allowed_decision_prevents_repeated_allowed_decisions(self):
        self._ensure_capabilities()
        self._patch_capability("wake_up", cooldownSeconds=900, dailyLimit=4)

        first = self._post_observation(
            "wake_up",
            confidence=0.9,
            duration_seconds=60,
            signal_type="wake_up_late",
            observed_at=_ms("2026-06-17 07:30"),
        )
        second = self._post_observation(
            "wake_up",
            confidence=0.9,
            duration_seconds=60,
            signal_type="wake_up_late",
            observed_at=_ms("2026-06-17 07:31"),
        )

        self.assertEqual(first.json["decision"]["decision"], "allowed")
        self.assertEqual(second.json["decision"]["decision"], "skipped_cooldown")

    def test_routine_window_gate_controls_should_speak(self):
        self._ensure_capabilities()
        self._patch_capability(
            "meal_start",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )

        school_inside = self._post_observation(
            "meal_start",
            confidence=0.9,
            duration_seconds=5,
            signal_type="meal_ready",
            observed_at=_ms("2026-06-17 07:45"),
        )
        school_outside = self._post_observation(
            "meal_start",
            confidence=0.9,
            duration_seconds=5,
            signal_type="meal_ready",
            observed_at=_ms("2026-06-17 10:30"),
        )
        weekend_inside = self._post_observation(
            "meal_start",
            confidence=0.9,
            duration_seconds=5,
            signal_type="meal_ready",
            observed_at=_ms("2026-06-20 08:45"),
        )

        self.assertEqual(school_inside.json["decision"]["decision"], "allowed")
        self.assertTrue(school_inside.json["decision"]["shouldSpeak"])
        self.assertEqual(school_outside.json["decision"]["decision"], REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW)
        self.assertFalse(school_outside.json["decision"]["shouldSpeak"])
        self.assertEqual(weekend_inside.json["decision"]["decision"], "allowed")
        self.assertTrue(weekend_inside.json["decision"]["shouldSpeak"])

    def test_disabled_routine_window_blocks_should_speak(self):
        self._ensure_capabilities()
        self._patch_capability(
            "nap_time",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )
        response = self.client.put(
            "/api/care/routine-windows",
            query_string={"dayType": "school_day"},
            json={
                "childId": self.child_id,
                "windows": [
                    {
                        "dayType": "school_day",
                        "windowType": "nap",
                        "startTime": "12:40",
                        "endTime": "14:20",
                        "enabled": False,
                        "timezone": "Asia/Shanghai",
                    }
                ],
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)

        blocked = self._post_observation(
            "nap_time",
            confidence=0.9,
            duration_seconds=5,
            signal_type="still_active",
            observed_at=_ms("2026-06-17 13:10"),
        )

        self.assertEqual(blocked.json["decision"]["decision"], REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW)
        self.assertFalse(blocked.json["decision"]["shouldSpeak"])

    def test_positive_and_recovered_signals_do_not_speak(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )

        cleanup_started = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=5,
            signal_type="cleanup_started",
            observed_at=_ms("2026-06-17 19:30"),
        )
        recovered = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=5,
            signal_type="toys_scattered",
            signal_value="recovered",
            observed_at=_ms("2026-06-17 19:30") + 10_000,
        )

        self.assertEqual(cleanup_started.json["decision"]["decision"], REMINDER_DECISION_RECORD_ONLY)
        self.assertFalse(cleanup_started.json["decision"]["shouldSpeak"])
        self.assertEqual(recovered.json["decision"]["decision"], REMINDER_DECISION_RECORD_ONLY)
        self.assertFalse(recovered.json["decision"]["shouldSpeak"])

    def test_ai_description_is_recorded_as_parent_facing_camera_event(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )

        response = self._post_observation(
            "toy_cleanup",
            confidence=0.92,
            duration_seconds=8,
            signal_type="toy_playing_observed",
            observed_at=_ms("2026-06-17 19:30"),
            parent_summary="孩子正在玩玩具",
            raw_detail={
                "has_person": True,
                "activity": "玩玩具",
                "description": "孩子坐在沙发上玩玩具，周围有积木和小车。",
                "decision_reason": "孩子仍在玩玩具，暂不催收纳。",
                "toys_visible": True,
                "toys_scattered": True,
                "method": "vision-test",
            },
        )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["decision"]["decision"], REMINDER_DECISION_RECORD_ONLY)
        self.assertIsNone(response.json.get("reminder"))
        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        event = events.json["events"][0]
        self.assertEqual(event["displayTitle"], "孩子正在玩玩具")
        self.assertIn("孩子坐在沙发上玩玩具", event["displayMessage"])
        self.assertNotIn("可信度", event["evidenceSummary"])
        self.assertNotIn("已继续提醒", event["displayTitle"])

    def test_structured_ai_summary_never_leaks_to_camera_event_copy(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )

        response = self._post_observation(
            "toy_cleanup",
            confidence=0.92,
            duration_seconds=8,
            signal_type="toy_playing_observed",
            observed_at=_ms("2026-06-17 19:31"),
            parent_summary="",
            raw_detail={
                "has_person": True,
                "activity": "",
                "summary": {
                    "score": 80,
                    "skills": [
                        {"name": "专注", "score": 62},
                        {"name": "坐姿", "score": 92},
                    ],
                },
            },
        )

        self.assertEqual(response.status_code, 200, response.json)
        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        event = events.json["events"][0]
        visible = f"{event['displayTitle']} {event['displayMessage']} {event['evidenceSummary']}"
        self.assertNotIn("score", visible)
        self.assertNotIn("skills", visible)
        self.assertNotIn("{", visible)
        self.assertNotIn("[", visible)

    def test_toy_left_uncollected_triggers_internal_reminder_and_realtime_events(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        captured: list[tuple[str, dict]] = []
        original_broadcast = task_event_stream.task_event_stream_server.broadcast
        task_event_stream.task_event_stream_server.broadcast = (
            lambda family_id, payload: captured.append((family_id, payload))
        )
        try:
            response = self._post_observation(
                "toy_cleanup",
                confidence=0.9,
                duration_seconds=6,
                signal_type="child_left_toys_uncollected",
                observed_at=_ms("2026-06-17 19:30"),
                parent_summary="孩子离开后，玩具还没有收好。",
                raw_detail={
                    "has_person": False,
                    "activity": "玩具未收纳",
                    "description": "孩子离开了画面，地上还有散落玩具。",
                    "decision_reason": "玩具散落且孩子已离开，需要轻声提醒。",
                    "toys_scattered": True,
                    "method": "vision-test",
                },
            )
        finally:
            task_event_stream.task_event_stream_server.broadcast = original_broadcast

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["decision"]["decision"], REMINDER_DECISION_ALLOWED)
        self.assertTrue(response.json["decision"]["shouldSpeak"])
        self.assertIsNotNone(response.json.get("reminder"))
        self.assertEqual(response.json["reminder"]["reminder"]["scenario"], "toy_cleanup")
        self.assertEqual(response.json["reminder"]["reminder"]["eventSource"], "internal")
        pushed_types = [payload["type"] for _, payload in captured]
        self.assertIn("camera_observation.updated", pushed_types)
        self.assertIn("camera_event.created", pushed_types)
        self.assertIn("reminder_decision.created", pushed_types)
        self.assertIn("reminder_event.created", pushed_types)
        self.assertIn("camera_command.created", pushed_types)
        self.assertTrue(all(family_id == self.family_id for family_id, _ in captured))
        for _, payload in captured:
            self.assertNotIn("image", payload)
            self.assertNotIn("base64", payload)
        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        care_reminders = [
            event for event in events.json["events"] if event["category"] == "care_reminder"
        ]
        self.assertTrue(care_reminders, events.json["events"])
        self.assertEqual(care_reminders[0]["displayTitle"], "已提醒收纳玩具")

    def test_routine_reminder_tick_is_idempotent_and_uses_policy(self):
        self._ensure_capabilities()
        self._patch_capability(
            "wake_up",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        service = RoutineReminderService(self.app.config["DATABASE_URL"])
        now = _ms("2026-06-17 07:30")

        with self.app.app_context():
            first = service.tick(now=now)
            second = service.tick(now=now)

        self.assertGreaterEqual(first["triggeredCount"], 1)
        self.assertGreaterEqual(second["triggeredCount"], 1)
        wake_responses = [
            item for item in first["responses"] if item["observation"]["scenario"] == "wake_up"
        ]
        self.assertTrue(wake_responses)
        self.assertEqual(wake_responses[0]["decision"]["decision"], REMINDER_DECISION_ALLOWED)
        self.assertIsNotNone(wake_responses[0].get("reminder"))
        self.assertIsNotNone(wake_responses[0].get("careEvent"))
        duplicate_wake = [
            item for item in second["responses"] if item["observation"]["scenario"] == "wake_up"
        ]
        self.assertTrue(duplicate_wake)
        self.assertTrue(duplicate_wake[0]["duplicate"])

    def test_dev_routine_reminder_tick_endpoint_requires_auth_and_accepts_now(self):
        unauthenticated = self.client.post("/api/dev/care/routine-reminder/tick")
        self.assertEqual(unauthenticated.status_code, 401)

        invalid = self.client.post(
            "/api/dev/care/routine-reminder/tick",
            json={"now": "not-a-timestamp"},
            headers=self._auth_headers(),
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.json["error"], "invalid_now")

        response = self.client.post(
            "/api/dev/care/routine-reminder/tick",
            json={"now": _ms("2026-06-17 07:30")},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["ok"])
        self.assertGreaterEqual(response.json["triggeredCount"], 1)
        self.assertTrue(
            any(item["observation"]["scenario"] == "wake_up" for item in response.json["responses"])
        )

    def test_routine_reminder_day_type_filter_excludes_mismatched_windows(self):
        self._ensure_capabilities()
        self._patch_capability(
            "meal_start",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        service = RoutineReminderService(self.app.config["DATABASE_URL"])

        friday_breakfast = service.tick(now=_ms("2026-06-26 09:00"))
        weekend_breakfast = [
            item
            for item in friday_breakfast["responses"]
            if ":weekend:" in str(item["observation"].get("sourceEventId") or "")
            and "breakfast" in str(item["observation"].get("sourceEventId") or "")
        ]
        self.assertFalse(weekend_breakfast)

        friday_dinner = service.tick(now=_ms("2026-06-26 17:30"))
        school_dinners = [
            item
            for item in friday_dinner["responses"]
            if item["observation"]["scenario"] == "meal_start"
            and ":school_day:" in str(item["observation"].get("sourceEventId") or "")
            and "dinner" in str(item["observation"].get("sourceEventId") or "")
        ]
        self.assertTrue(school_dinners)
        self.assertEqual(school_dinners[0]["decision"]["decision"], REMINDER_DECISION_ALLOWED)

        saturday_wake = service.tick(now=_ms("2026-06-27 08:30"))
        weekend_wake = [
            item
            for item in saturday_wake["responses"]
            if item["observation"]["scenario"] == "wake_up"
            and ":weekend:" in str(item["observation"].get("sourceEventId") or "")
        ]
        school_wake = [
            item
            for item in saturday_wake["responses"]
            if item["observation"]["scenario"] == "wake_up"
            and ":school_day:" in str(item["observation"].get("sourceEventId") or "")
        ]
        self.assertTrue(weekend_wake)
        self.assertFalse(school_wake)

    def test_routine_window_exempt_from_parent_notify_threshold(self):
        self._ensure_capabilities()
        self._patch_capability(
            "meal_start",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=2,
            allowSpeaker=True,
        )
        self._create_real_reminder_event("meal_start")
        self._create_real_reminder_event("meal_start")

        service = RoutineReminderService(self.app.config["DATABASE_URL"])
        with self.app.app_context():
            result = service.tick(now=_ms("2026-06-26 17:30"))

        dinners = [
            item
            for item in result["responses"]
            if item["observation"]["scenario"] == "meal_start"
            and "dinner" in str(item["observation"].get("sourceEventId") or "")
        ]
        self.assertTrue(dinners)
        self.assertEqual(dinners[0]["decision"]["decision"], REMINDER_DECISION_ALLOWED)
        self.assertTrue(dinners[0]["decision"]["shouldSpeak"])

    def test_routine_window_exempt_from_daily_limit(self):
        self._ensure_capabilities()
        self._patch_capability(
            "meal_start",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=1,
            parentNotifyThreshold=10,
            allowSpeaker=True,
        )
        self._create_real_reminder_event("meal_start")

        service = RoutineReminderService(self.app.config["DATABASE_URL"])
        with self.app.app_context():
            result = service.tick(now=_ms("2026-06-26 17:30"))

        dinners = [
            item
            for item in result["responses"]
            if item["observation"]["scenario"] == "meal_start"
            and "dinner" in str(item["observation"].get("sourceEventId") or "")
        ]
        self.assertTrue(dinners)
        self.assertEqual(dinners[0]["decision"]["decision"], REMINDER_DECISION_ALLOWED)
        self.assertTrue(dinners[0]["decision"]["shouldSpeak"])

    def test_failed_reminder_does_not_count_toward_parent_notify_threshold(self):
        self._ensure_capabilities()
        self._patch_capability(
            "meal_start",
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=2,
            allowSpeaker=True,
            minObservationSeconds=1,
        )
        self._create_real_reminder_event("meal_start")
        self._create_real_reminder_event("meal_start", delivery_status=REMINDER_STATUS_FAILED)

        allowed = self._post_observation(
            "meal_start",
            confidence=0.9,
            duration_seconds=60,
            observed_at=_ms("2026-06-26 12:00"),
        )
        self.assertEqual(allowed.json["decision"]["decision"], REMINDER_DECISION_ALLOWED)
        self.assertTrue(allowed.json["decision"]["shouldSpeak"])

    def test_camera_events_include_record_kind_for_routine_observation(self):
        self._ensure_capabilities()
        self._patch_capability(
            "meal_start",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        service = RoutineReminderService(self.app.config["DATABASE_URL"])
        with self.app.app_context():
            service.tick(now=_ms("2026-06-26 17:30"))

        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        routine_events = [
            event for event in events.json["events"] if event.get("recordKind") == "routine"
        ]
        self.assertTrue(routine_events)
        self.assertIn("晚餐", routine_events[0]["displayTitle"])

    def test_routine_reminder_respects_disabled_speaker_off_and_window_gate(self):
        self._ensure_capabilities()
        service = RoutineReminderService(self.app.config["DATABASE_URL"])

        self._patch_capability("wake_up", enabled=False)
        disabled = service.tick(now=_ms("2026-06-18 07:30"))
        disabled_wake = [
            item for item in disabled["responses"] if item["observation"]["scenario"] == "wake_up"
        ]
        self.assertTrue(disabled_wake)
        self.assertEqual(disabled_wake[0]["decision"]["decision"], "skipped_disabled")
        self.assertIsNone(disabled_wake[0].get("reminder"))

        self._patch_capability(
            "wake_up",
            enabled=True,
            allowSpeaker=False,
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )
        speaker_off = service.tick(now=_ms("2026-06-19 07:30"))
        speaker_off_wake = [
            item for item in speaker_off["responses"] if item["observation"]["scenario"] == "wake_up"
        ]
        self.assertTrue(speaker_off_wake)
        self.assertEqual(speaker_off_wake[0]["decision"]["decision"], REMINDER_DECISION_RECORD_ONLY)
        self.assertFalse(speaker_off_wake[0]["decision"]["shouldSpeak"])
        self.assertIsNone(speaker_off_wake[0].get("reminder"))

        outside = service.tick(now=_ms("2026-06-19 10:30"))
        self.assertFalse(
            any(item["observation"]["scenario"] == "wake_up" for item in outside["responses"])
        )

    def test_duplicate_source_event_id_does_not_accumulate_duration_twice(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=20,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
        )
        source_event_id = "duplicate_duration_once"

        first = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=10,
            signal_type="toys_scattered",
            source_event_id=source_event_id,
            observed_at=_ms("2026-06-17 19:30"),
        )
        duplicate = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=10,
            signal_type="toys_scattered",
            source_event_id=source_event_id,
            observed_at=_ms("2026-06-17 19:30") + 5_000,
        )

        self.assertEqual(first.json["decision"]["decision"], "skipped_continuity")
        self.assertTrue(duplicate.json["duplicate"])
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            state = conn.execute(
                """
                SELECT *
                FROM current_behavior_states
                WHERE family_id = ? AND child_id = ? AND scenario = ? AND state = ?
                """,
                (self.family_id, self.child_id, "toy_cleanup", "toys_scattered"),
            ).fetchone()
        self.assertIsNotNone(state)
        self.assertEqual(int(state["consecutive_seconds"]), 10)

    def test_recent_duplicate_observation_does_not_create_second_care_event_or_reminder(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=1,
            cooldownSeconds=0,
            dailyLimit=10,
            parentNotifyThreshold=9,
            allowSpeaker=True,
        )
        captured: list[tuple[str, dict]] = []
        original_broadcast = task_event_stream.task_event_stream_server.broadcast
        task_event_stream.task_event_stream_server.broadcast = (
            lambda family_id, payload: captured.append((family_id, payload))
        )
        raw_detail = {
            "has_person": True,
            "activity": "看屏幕",
            "description": "孩子在看屏幕，注意用眼距离。",
        }
        try:
            first = self._post_observation(
                "posture",
                confidence=0.9,
                duration_seconds=3,
                signal_type="posture_risk",
                parent_summary="孩子低头靠近桌面，注意坐姿。",
                raw_detail=raw_detail,
                observed_at=_ms("2026-06-17 19:30"),
            )
            second = self._post_observation(
                "posture",
                confidence=0.9,
                duration_seconds=3,
                signal_type="posture_risk",
                parent_summary="孩子低头靠近桌面，注意坐姿。",
                raw_detail=raw_detail,
                observed_at=_ms("2026-06-17 19:30") + 5_000,
            )
        finally:
            task_event_stream.task_event_stream_server.broadcast = original_broadcast

        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(second.status_code, 200, second.json)
        self.assertTrue(second.json["duplicate"])
        self.assertTrue(second.json["duplicateCareEvent"])
        self.assertIsNone(second.json["careEvent"])
        self.assertIsNone(second.json["reminder"])
        camera_events = [
            payload
            for _, payload in captured
            if payload["type"] == "camera_event.created"
            and payload.get("source") == "camera_observation"
        ]
        self.assertEqual(len(camera_events), 1)

    def test_current_behavior_state_is_upserted(self):
        self._ensure_capabilities()
        self._patch_capability("toy_cleanup", cooldownSeconds=0)

        first = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=60,
            signal_type="toys_scattered",
            source_event_id="state_upsert_1",
        )
        second = self._post_observation(
            "toy_cleanup",
            confidence=0.95,
            duration_seconds=90,
            signal_type="toys_scattered",
            source_event_id="state_upsert_2",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM current_behavior_states
                WHERE family_id = ? AND child_id = ? AND scenario = ? AND state = ?
                """,
                (self.family_id, self.child_id, "toy_cleanup", "toys_scattered"),
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["consecutive_seconds"]), 150)

    def test_low_confidence_signal_does_not_reset_current_behavior_state(self):
        self._ensure_capabilities()
        self._patch_capability(
            "toy_cleanup",
            minObservationSeconds=20,
            observationThreshold=0.72,
            cooldownSeconds=0,
            dailyLimit=4,
            parentNotifyThreshold=3,
        )
        start = _ms("2026-06-17 19:30")

        first = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=15,
            signal_type="toys_scattered",
            source_event_id="low_conf_state_1",
            observed_at=start,
        )
        low = self._post_observation(
            "toy_cleanup",
            confidence=0.2,
            duration_seconds=10,
            signal_type="toys_scattered",
            source_event_id="low_conf_state_2",
            observed_at=start + 10_000,
        )
        third = self._post_observation(
            "toy_cleanup",
            confidence=0.9,
            duration_seconds=5,
            signal_type="toys_scattered",
            source_event_id="low_conf_state_3",
            observed_at=start + 20_000,
        )

        self.assertEqual(first.json["decision"]["decision"], "skipped_continuity")
        self.assertEqual(low.json["decision"]["decision"], "skipped_low_confidence")
        self.assertEqual(third.json["decision"]["decision"], "allowed")
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            state = conn.execute(
                """
                SELECT *
                FROM current_behavior_states
                WHERE family_id = ? AND child_id = ? AND scenario = ? AND state = ?
                """,
                (self.family_id, self.child_id, "toy_cleanup", "toys_scattered"),
            ).fetchone()
        self.assertIsNotNone(state)
        self.assertEqual(int(state["consecutive_seconds"]), 20)

    def test_internal_request_rejects_when_token_is_not_configured(self):
        app = create_app(fresh_test_config(INTERNAL_API_TOKEN=""))
        client = app.test_client()

        response = client.post(
            "/internal/camera/observations",
            json={
                "familyId": "fam_test",
                "childId": "child_test",
                "scenario": "toy_cleanup",
                "confidence": 0.8,
            },
            headers={"X-Mira-Internal-Token": "anything"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["error"], "internal_token_unconfigured")

    def test_reminder_test_is_hidden_by_default_and_internal_trigger_requires_allowed_decision(self):
        test_response = self.client.post(
            "/api/reminders/test",
            json={"childId": self.child_id, "scenario": "toy_cleanup"},
            headers=self._auth_headers(),
        )

        self.assertEqual(test_response.status_code, 200)
        self.assertEqual(test_response.json["reminder"]["scenario"], "toy_cleanup")
        self.assertTrue(test_response.json["reminder"]["isTest"])
        self.assertEqual(test_response.json["reminder"]["eventSource"], "test")
        self.assertEqual(test_response.json["reminder"]["deliveryStatus"], "test_generated")
        self.assertIn(test_response.json["reminder"]["textSource"], {"fallback", "ai"})

        hidden_events = self.client.get("/api/reminders/events", headers=self._auth_headers())
        self.assertEqual(hidden_events.status_code, 200)
        self.assertEqual(hidden_events.json["events"], [])

        test_events = self.client.get(
            "/api/reminders/events",
            query_string={"includeTest": "true"},
            headers=self._auth_headers(),
        )
        self.assertEqual(test_events.status_code, 200)
        self.assertEqual(len(test_events.json["events"]), 1)

        missing_decision = self.client.post(
            "/internal/reminders/trigger",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "scenario": "bedtime",
                "context": {"dayType": "school_day", "reminderLevel": "gentle"},
            },
            headers={"Authorization": f"Bearer {self.internal_token}"},
        )
        self.assertEqual(missing_decision.status_code, 400)
        self.assertEqual(missing_decision.json["error"], "reminder_decision_required")

        skipped_decision_id = self._create_decision(REMINDER_DECISION_SKIPPED_COOLDOWN, should_speak=True)
        skipped = self.client.post(
            "/internal/reminders/trigger",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "scenario": "bedtime",
                "reminderDecisionId": skipped_decision_id,
            },
            headers={"Authorization": f"Bearer {self.internal_token}"},
        )
        self.assertEqual(skipped.status_code, 409)
        self.assertEqual(skipped.json["error"], "reminder_decision_not_allowed")

        allowed_decision_id = self._create_decision(REMINDER_DECISION_ALLOWED, should_speak=True)
        internal = self.client.post(
            "/internal/reminders/trigger",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "scenario": "bedtime",
                "reminderDecisionId": allowed_decision_id,
                "context": {"dayType": "school_day", "reminderLevel": "gentle"},
            },
            headers={"Authorization": f"Bearer {self.internal_token}"},
        )
        self.assertEqual(internal.status_code, 200)
        self.assertEqual(internal.json["reminder"]["scenario"], "bedtime")
        self.assertFalse(internal.json["reminder"]["isTest"])
        self.assertEqual(internal.json["reminder"]["eventSource"], "internal")
        self.assertEqual(internal.json["reminder"]["deliveryStatus"], REMINDER_STATUS_COMMAND_SENT)
        self.assertTrue(internal.json["reminder"]["commandId"].startswith("cmd_"))
        self.assertEqual(internal.json["command"]["status"], REMINDER_STATUS_COMMAND_SENT)
        self.assertNotIn("我是 AI", internal.json["reminder"]["text"])

        events = self.client.get("/api/reminders/events", headers=self._auth_headers())
        self.assertEqual(events.status_code, 200)
        self.assertEqual(len(events.json["events"]), 1)
        event = events.json["events"][0]
        self.assertEqual(event["commandId"], internal.json["reminder"]["commandId"])
        self.assertEqual(event["delivery"]["commandStatus"], "succeeded")
        self.assertEqual(event["delivery"]["message"], "已执行")

    def test_internal_trigger_is_idempotent_for_same_decision(self):
        allowed_decision_id = self._create_decision(REMINDER_DECISION_ALLOWED, should_speak=True)
        provider = _CountingAiTextProvider()
        command_service = _FakeCameraCommandService()
        service = AiCareReminderService(
            self.app.config["DATABASE_URL"],
            auth_service=None,
            ai_text_provider=provider,
            prompt_registry=PromptRegistry(self.app.config["PROMPT_ROOT"]),
            camera_command_service=command_service,
        )

        with patch("routes.internal.reminders.ai_care_reminder_service", return_value=service):
            first = self.client.post(
                "/internal/reminders/trigger",
                json={
                    "familyId": self.family_id,
                    "childId": self.child_id,
                    "scenario": "bedtime",
                    "reminderDecisionId": allowed_decision_id,
                    "context": {"dayType": "school_day", "reminderLevel": "gentle"},
                },
                headers={"Authorization": f"Bearer {self.internal_token}"},
            )
            second = self.client.post(
                "/internal/reminders/trigger",
                json={
                    "familyId": self.family_id,
                    "childId": self.child_id,
                    "scenario": "bedtime",
                    "reminderDecisionId": allowed_decision_id,
                    "context": {"dayType": "school_day", "reminderLevel": "gentle"},
                },
                headers={"Authorization": f"Bearer {self.internal_token}"},
            )

        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(second.status_code, 200, second.json)
        self.assertEqual(first.json["reminder"]["id"], second.json["reminder"]["id"])
        self.assertTrue(second.json["idempotent"])
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(command_service.calls), 1)
        self.assertEqual(first.json["reminder"]["commandId"], second.json["reminder"]["commandId"])
        self.assertTrue(second.json["command"]["reusedExistingCommand"])
        self.assertEqual(self._count_internal_reminder_events_for_decision(allowed_decision_id), 1)

    def test_internal_trigger_uses_decision_device_for_speaker_command(self):
        allowed_decision_id = self._create_decision(
            REMINDER_DECISION_ALLOWED,
            should_speak=True,
            device_id=self.device_id,
        )
        provider = _CountingAiTextProvider()
        command_service = _FakeCameraCommandService()
        service = AiCareReminderService(
            self.app.config["DATABASE_URL"],
            auth_service=None,
            ai_text_provider=provider,
            prompt_registry=PromptRegistry(self.app.config["PROMPT_ROOT"]),
            camera_command_service=command_service,
        )

        with patch("routes.internal.reminders.ai_care_reminder_service", return_value=service):
            response = self.client.post(
                "/internal/reminders/trigger",
                json={
                    "familyId": self.family_id,
                    "childId": self.child_id,
                    "scenario": "bedtime",
                    "reminderDecisionId": allowed_decision_id,
                },
                headers={"Authorization": f"Bearer {self.internal_token}"},
            )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json["reminder"]["deviceId"], self.device_id)
        self.assertEqual(command_service.calls[0]["deviceId"], self.device_id)

    def test_internal_trigger_rejects_non_allowed_expired_and_device_mismatch(self):
        for decision in (
            REMINDER_DECISION_RECORD_ONLY,
            REMINDER_DECISION_PARENT_NOTIFY,
            REMINDER_DECISION_SKIPPED_OUT_OF_ROUTINE_WINDOW,
            REMINDER_DECISION_SKIPPED_LOW_CONFIDENCE,
        ):
            with self.subTest(decision=decision):
                decision_id = self._create_decision(decision, should_speak=False)
                response = self.client.post(
                    "/internal/reminders/trigger",
                    json={
                        "familyId": self.family_id,
                        "childId": self.child_id,
                        "scenario": "bedtime",
                        "reminderDecisionId": decision_id,
                    },
                    headers={"Authorization": f"Bearer {self.internal_token}"},
                )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json["error"], "reminder_decision_not_allowed")

        expired_decision_id = self._create_decision(
            REMINDER_DECISION_ALLOWED,
            should_speak=True,
            created_at=now_ms() - 3 * 60 * 1000,
        )
        expired = self.client.post(
            "/internal/reminders/trigger",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "scenario": "bedtime",
                "reminderDecisionId": expired_decision_id,
            },
            headers={"Authorization": f"Bearer {self.internal_token}"},
        )
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(expired.json["error"], "reminder_decision_expired")

        device_decision_id = self._create_decision(
            REMINDER_DECISION_ALLOWED,
            should_speak=True,
            device_id="dev_locked",
        )
        mismatch = self.client.post(
            "/internal/reminders/trigger",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": "dev_other",
                "scenario": "bedtime",
                "reminderDecisionId": device_decision_id,
            },
            headers={"Authorization": f"Bearer {self.internal_token}"},
        )
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json["error"], "reminder_decision_device_mismatch")

    def test_internal_trigger_marks_reminder_failed_when_speaker_command_fails(self):
        allowed_decision_id = self._create_decision(REMINDER_DECISION_ALLOWED, should_speak=True)
        provider = _CountingAiTextProvider()
        command_service = _FakeCameraCommandService(fail=True)
        service = AiCareReminderService(
            self.app.config["DATABASE_URL"],
            auth_service=None,
            ai_text_provider=provider,
            prompt_registry=PromptRegistry(self.app.config["PROMPT_ROOT"]),
            camera_command_service=command_service,
        )

        with patch("routes.internal.reminders.ai_care_reminder_service", return_value=service):
            response = self.client.post(
                "/internal/reminders/trigger",
                json={
                    "familyId": self.family_id,
                    "childId": self.child_id,
                    "scenario": "bedtime",
                    "reminderDecisionId": allowed_decision_id,
                },
                headers={"Authorization": f"Bearer {self.internal_token}"},
            )
            repeated = self.client.post(
                "/internal/reminders/trigger",
                json={
                    "familyId": self.family_id,
                    "childId": self.child_id,
                    "scenario": "bedtime",
                    "reminderDecisionId": allowed_decision_id,
                },
                headers={"Authorization": f"Bearer {self.internal_token}"},
            )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(repeated.status_code, 200, repeated.json)
        self.assertEqual(len(command_service.calls), 1)
        self.assertEqual(response.json["reminder"]["deliveryStatus"], REMINDER_STATUS_FAILED)
        self.assertEqual(response.json["command"]["status"], REMINDER_STATUS_FAILED)
        self.assertEqual(response.json["reminder"]["commandId"], "cmd_fake_1")
        self.assertIn("提醒没有播出", response.json["reminder"]["failureReason"])
        self.assertTrue(repeated.json["idempotent"])
        self.assertEqual(repeated.json["reminder"]["id"], response.json["reminder"]["id"])
        self.assertEqual(repeated.json["reminder"]["deliveryStatus"], REMINDER_STATUS_FAILED)
        self.assertEqual(repeated.json["command"]["status"], REMINDER_STATUS_FAILED)
        self.assertFalse(repeated.json["command"]["ok"])
        self.assertTrue(repeated.json["command"]["reusedExistingCommand"])
        self.assertEqual(len(command_service.calls), 1)

    def test_internal_trigger_dry_run_does_not_write_formal_reminder_event(self):
        expired_decision_id = self._create_decision(
            REMINDER_DECISION_ALLOWED,
            should_speak=True,
            created_at=now_ms() - 3 * 60 * 1000,
        )
        provider = _CountingAiTextProvider()
        command_service = _FakeCameraCommandService()
        service = AiCareReminderService(
            self.app.config["DATABASE_URL"],
            auth_service=None,
            ai_text_provider=provider,
            prompt_registry=PromptRegistry(self.app.config["PROMPT_ROOT"]),
            camera_command_service=command_service,
        )

        with patch("routes.internal.reminders.ai_care_reminder_service", return_value=service):
            response = self.client.post(
                "/internal/reminders/trigger",
                json={
                    "familyId": self.family_id,
                    "childId": self.child_id,
                    "scenario": "bedtime",
                    "reminderDecisionId": expired_decision_id,
                    "dryRun": True,
                },
                headers={"Authorization": f"Bearer {self.internal_token}"},
            )

        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json["dryRun"])
        self.assertEqual(response.json["reminder"]["eventSource"], "dry_run")
        self.assertEqual(len(command_service.calls), 0)
        self.assertEqual(self._count_internal_reminder_events_for_decision(expired_decision_id), 0)

    def test_care_summary_contract(self):
        response = self.client.get(
            "/api/care/summary",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        summary = response.json["summary"]
        self.assertEqual(summary["childId"], self.child_id)
        self.assertIn("currentStage", summary)
        self.assertIn("capabilities", summary)
        self.assertIn("needsParentReview", summary)

    def _login(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(login.status_code, 200)
        self.family_id = login.json["family"]["id"]
        return login.json["tokens"]["accessToken"]

    def _create_child(self, name: str) -> str:
        headers = self._auth_headers()
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200)
        device = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-CARE", "deviceName": "客厅设备", "location": "客厅"},
            headers=headers,
        )
        self.assertEqual(device.status_code, 200)
        self.device_id = device.json["device"]["id"]
        wifi = self.client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=headers,
        )
        self.assertEqual(wifi.status_code, 200)
        response = self.client.post(
            "/api/setup/child",
            json={"name": name, "nickname": name, "ageStage": "kindergarten_middle"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.json["child"]["id"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _ensure_capabilities(self):
        response = self.client.get(
            "/api/care/capabilities",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["capabilities"]

    def _patch_capability(self, scenario: str, **fields):
        response = self.client.patch(
            "/api/care/capabilities",
            json={
                "childId": self.child_id,
                "capabilities": [{"scenario": scenario, **fields}],
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return next(item for item in response.json["capabilities"] if item["scenario"] == scenario)

    def _post_observation(
        self,
        scenario: str,
        *,
        confidence: float,
        duration_seconds: int,
        signal_type: str | None = None,
        signal_value: str = "active",
        source_event_id: str | None = None,
        observed_at: int | None = None,
        parent_summary: str = "观察到一项日常看护情况。",
        raw_detail: dict | None = None,
    ):
        self._source_seq += 1
        source_event_id = source_event_id or f"{scenario}_{now_ms()}_{self._source_seq}"
        return self.client.post(
            "/internal/camera/observations",
            json={
                "familyId": self.family_id,
                "childId": self.child_id,
                "deviceId": self.device_id,
                "scenario": scenario,
                "sourceEventId": source_event_id,
                **({"observedAt": observed_at} if observed_at is not None else {}),
                "confidence": confidence,
                "evidenceType": "snapshot",
                "parentSummary": parent_summary,
                **({"rawDetail": raw_detail} if raw_detail is not None else {}),
                "signals": [
                    {
                        "signalType": signal_type or f"{scenario}_observed",
                        "signalValue": signal_value,
                        "confidence": confidence,
                        "durationSeconds": duration_seconds,
                    }
                ],
            },
            headers={"X-Mira-Internal-Token": self.internal_token},
        )

    def _create_real_reminder_event(
        self,
        scenario: str,
        *,
        event_source: str = REMINDER_EVENT_SOURCE_INTERNAL,
        is_test: bool = False,
        delivery_status: str = REMINDER_STATUS_COMMAND_SENT,
    ) -> str:
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        now = now_ms()
        with repository.transaction() as conn:
            row = repository.create_reminder_event(
                conn,
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=self.device_id,
                scenario=scenario,
                reminder_decision_id=None,
                event_source=event_source,
                is_test=is_test,
                source_type="test_contract",
                source_id=scenario,
                task_id=None,
                prompt_id=f"reminder.{scenario}",
                prompt_version="v1",
                text="轻声提醒一下。",
                tone="warm",
                text_source="fallback",
                delivery_status=delivery_status,
                command_id=None,
                fallback_used=True,
                generated_at=now,
                delivered_at=None,
                failure_reason=None,
                now=now,
            )
        return row["id"]

    def _create_decision(
        self,
        decision: str,
        *,
        should_speak: bool,
        scenario: str = "bedtime",
        device_id: str | None = None,
        created_at: int | None = None,
    ) -> str:
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        now = created_at or now_ms()
        with repository.transaction() as conn:
            row = repository.create_reminder_decision(
                conn,
                family_id=self.family_id,
                child_id=self.child_id,
                device_id=device_id,
                scenario=scenario,
                observation_event_id=None,
                behavior_state_id=None,
                source_type="test_contract",
                source_id=decision,
                task_id=None,
                decision=decision,
                reason=decision,
                reminder_level="gentle",
                cooldown_until=None,
                should_speak=should_speak,
                should_notify_parent=False,
                policy_snapshot_json=None,
                now=now,
            )
        return row["id"]

    def _count_internal_reminder_events_for_decision(self, decision_id: str) -> int:
        repository = CareRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM reminder_events
                WHERE family_id = ? AND child_id = ? AND scenario = ?
                  AND event_source = 'internal' AND is_test = 0
                  AND source_type = 'reminder_decision' AND source_id = ?
                """,
                (self.family_id, self.child_id, "bedtime", decision_id),
            ).fetchone()
        return int(row["total"] or 0)


def _ms(value: str) -> int:
    dt = datetime.strptime(value, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return int(dt.timestamp() * 1000)


class _CountingAiTextProvider:
    provider_name = "counting"
    model_name = "counting-test"

    def __init__(self):
        self.calls = 0

    def complete(self, *, system_prompt: str, user_prompt: str, max_tokens: int = 96, temperature: float = 0.4):
        self.calls += 1
        return AiTextResponse(
            text='{"text":"睡觉时间到，轻轻躺好。","tone":"warm","scenario":"bedtime","safety":"ok"}',
            provider=self.provider_name,
            model=self.model_name,
        )


class _FakeCameraCommandService:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[dict] = []

    def internal_speak(
        self,
        *,
        family_id: str,
        text: str,
        task_id: str | None = None,
        device_id: str | None = None,
        source: str | None = None,
        scenario: str | None = None,
    ) -> dict:
        self.calls.append(
            {
                "familyId": family_id,
                "text": text,
                "taskId": task_id,
                "deviceId": device_id,
                "source": source,
                "scenario": scenario,
            }
        )
        command_id = f"cmd_fake_{len(self.calls)}"
        if self.fail:
            return {
                "commandId": command_id,
                "status": "failed",
                "message": "摄像头暂时离线，提醒没有播出。",
            }
        return {
            "commandId": command_id,
            "status": "succeeded",
            "message": "已执行",
        }


if __name__ == "__main__":
    unittest.main()
