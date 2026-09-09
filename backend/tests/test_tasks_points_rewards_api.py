from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from app import create_app
from core.database import Database
from integrations.camera_runtime.mock_adapter import MockCameraRuntimeAdapter
from services.ai_text_provider import AiTextResponse
from services.task_reminder_policy import build_task_reminder
from services.task_event_stream import task_runtime_messages_by_family
from services.service_factory import task_runtime_service
from tests.support import fresh_test_config, request_debug_code


class FakeReminderAiProvider:
    provider_name = "fake"
    model_name = "fake-task-reminder"

    def __init__(self, text: str):
        self.text = text
        self.last_system_prompt = ""
        self.last_user_prompt = ""

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 96,
        temperature: float = 0.4,
    ) -> AiTextResponse:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return AiTextResponse(text=self.text, provider=self.provider_name, model=self.model_name)


class TasksPointsRewardsApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="mock"))
        self.client = self.app.test_client()
        self.access_token = self._login("13800002026")
        self.child_id = self._create_child("小宇")

    def test_task_confirmation_grants_points_and_ledger(self):
        task = self._create_task(reward_points=20)

        today = self.client.get(
            "/api/tasks/today",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(today.status_code, 200)
        self.assertEqual(len(today.json["tasks"]), 1)
        self.assertEqual(today.json["tasks"][0]["id"], task["id"])

        complete = self.client.post(
            f"/api/tasks/{task['id']}/complete",
            json={"evidenceSummary": "AI 看到作业已完成"},
            headers=self._auth_headers(),
        )
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.json["task"]["status"], "awaiting_parent_confirmation")

        confirm = self.client.post(
            f"/api/tasks/{task['id']}/parent-confirm",
            headers=self._auth_headers(),
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json["task"]["status"], "confirmed")
        self.assertEqual(confirm.json["ledgerEntry"]["delta"], 20)

        confirm_again = self.client.post(
            f"/api/tasks/{task['id']}/parent-confirm",
            headers=self._auth_headers(),
        )
        self.assertEqual(confirm_again.status_code, 200)
        self.assertNotIn("ledgerEntry", confirm_again.json)

        account = self.client.get(
            "/api/points/account",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(account.status_code, 200)
        self.assertEqual(account.json["account"]["balance"], 20)

        ledger = self.client.get(
            "/api/points/ledger",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(ledger.status_code, 200)
        task_entries = [
            entry
            for entry in ledger.json["ledger"]
            if entry["sourceId"] == task["id"] and entry["type"] == "task_completed"
        ]
        self.assertEqual(len(task_entries), 1)
        self.assertEqual(task_entries[0]["delta"], 20)

    def test_today_tasks_respects_requested_date(self):
        self._create_task(reward_points=1)
        other_day = (datetime.now().date() + timedelta(days=1)).isoformat()

        response = self.client.get(
            "/api/tasks/today",
            query_string={"childId": self.child_id, "date": other_day},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["date"], other_day)
        self.assertEqual(response.json["tasks"], [])

    def test_parent_reject_is_terminal_and_skips_points(self):
        task = self._create_task(reward_points=12)

        complete = self.client.post(
            f"/api/tasks/{task['id']}/complete",
            json={"evidenceSummary": "观察结果不完整"},
            headers=self._auth_headers(),
        )
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.json["task"]["status"], "awaiting_parent_confirmation")

        reject = self.client.post(
            f"/api/tasks/{task['id']}/reject",
            json={"reason": "证据不足，未通过家长确认。"},
            headers=self._auth_headers(),
        )
        self.assertEqual(reject.status_code, 200)
        self.assertEqual(reject.json["task"]["status"], "rejected")
        self.assertEqual(reject.json["task"]["rejectionReason"], "证据不足，未通过家长确认。")
        self.assertIsNone(reject.json.get("ledgerEntry"))

        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200)
        event_types = [event["eventType"] for event in events.json["events"]]
        self.assertIn("parent_rejected", event_types)
        self.assertIn("points_award_skipped", event_types)

        ledger = self.client.get(
            "/api/points/ledger",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(ledger.status_code, 200)
        task_entries = [
            entry
            for entry in ledger.json["ledger"]
            if entry["sourceId"] == task["id"] and entry["type"] == "task_completed"
        ]
        self.assertEqual(task_entries, [])

        confirm_again = self.client.post(
            f"/api/tasks/{task['id']}/parent-confirm",
            headers=self._auth_headers(),
        )
        self.assertEqual(confirm_again.status_code, 400)

        start_again = self.client.post(
            f"/api/tasks/{task['id']}/start",
            headers=self._auth_headers(),
        )
        self.assertEqual(start_again.status_code, 400)

    def test_completed_task_cannot_be_rejected_without_reversal_flow(self):
        task = self._create_task_at(
            start_at=datetime.now().astimezone() - timedelta(minutes=10),
            due_at=datetime.now().astimezone() - timedelta(minutes=1),
            reward_points=5,
            requires_parent_confirmation=False,
        )
        complete = self.client.post(
            f"/api/tasks/{task['id']}/complete",
            json={"evidenceSummary": "家长手动确认已完成"},
            headers=self._auth_headers(),
        )
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.json["task"]["status"], "completed")
        self.assertIsNotNone(complete.json["ledgerEntry"])
        self.assertIsNotNone(complete.json["task"]["pointsGrantedAt"])

        reject = self.client.post(
            f"/api/tasks/{task['id']}/reject",
            json={"reason": "事后驳回"},
            headers=self._auth_headers(),
        )
        self.assertEqual(reject.status_code, 400)

    def test_parent_manual_completion_records_source_without_granting_points(self):
        task = self._create_task_at(
            start_at=datetime.now().astimezone() - timedelta(minutes=30),
            due_at=datetime.now().astimezone() - timedelta(minutes=5),
            reward_points=6,
            requires_parent_confirmation=True,
        )

        complete = self.client.post(
            f"/api/tasks/{task['id']}/complete",
            json={
                "completionSource": "parent_manual",
                "evidenceSummary": "家长手动补记完成。",
            },
            headers=self._auth_headers(),
        )

        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.json["task"]["status"], "completed")
        self.assertEqual(complete.json["task"]["completionSource"], "parent_manual")
        self.assertNotIn("ledgerEntry", complete.json)
        self.assertIsNone(complete.json["task"]["pointsGrantedAt"])

        ledger = self.client.get(
            "/api/points/ledger",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        task_entries = [
            entry
            for entry in ledger.json["ledger"]
            if entry["sourceId"] == task["id"] and entry["type"] == "task_completed"
        ]
        self.assertEqual(task_entries, [])

        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200)
        event_messages = [event["message"] for event in events.json["events"]]
        self.assertIn("家长手动记录完成，未发放积分", event_messages)

    def test_task_contract_supports_week_fields_and_updates(self):
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": "检查小书包",
                "description": "按明天课程准备材料",
                "taskType": "schoolbag",
                "scheduleType": "weekly",
                "startAt": "2026-06-03T20:10:00",
                "dueAt": "2026-06-03T20:30:00",
                "repeatRule": {"freq": "weekly", "days": [3]},
                "priority": 2,
                "rewardPoints": 4,
                "requiresParentConfirmation": True,
                "aiObservationSummary": "摄像头会在睡前观察桌面和书包区域。",
            },
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        task = response.json["task"]
        self.assertEqual(task["taskId"], task["id"])
        self.assertEqual(task["taskType"], "schoolbag")
        self.assertEqual(task["scheduleType"], "weekly")
        self.assertEqual(task["scheduledDate"], "2026-06-03")
        self.assertEqual(task["scheduledStart"], "20:10")
        self.assertEqual(task["priority"], 2)
        self.assertEqual(task["repeatRule"]["freq"], "weekly")

        week = self.client.get(
            "/api/tasks",
            query_string={
                "childId": self.child_id,
                "startDate": "2026-06-01",
                "endDate": "2026-06-07",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(week.status_code, 200)
        self.assertEqual([item["id"] for item in week.json["tasks"]], [task["id"]])

        patch = self.client.patch(
            f"/api/tasks/{task['id']}",
            json={
                "title": "检查小书包和美术材料",
                "rewardPoints": 5,
                "priority": 1,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json["task"]["title"], "检查小书包和美术材料")
        self.assertEqual(patch.json["task"]["rewardPoints"], 5)
        self.assertEqual(patch.json["task"]["priority"], 1)

        complete = self.client.post(
            f"/api/tasks/{task['id']}/complete",
            json={
                "completionSource": "camera",
                "evidenceSummary": "书包区截图显示材料已放入。",
                "evidence": {"confidence": 0.86, "clips": ["snapshot_1"]},
                "aiObservationSummary": "AI 判断材料已准备，建议家长确认。",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(complete.status_code, 200)
        self.assertEqual(complete.json["task"]["status"], "awaiting_parent_confirmation")
        self.assertEqual(complete.json["task"]["completionSource"], "camera")
        self.assertEqual(complete.json["task"]["evidence"]["confidence"], 0.86)
        self.assertEqual(
            complete.json["task"]["aiObservationSummary"],
            "AI 判断材料已准备，建议家长确认。",
        )

    def test_single_task_requires_explicit_date_or_time(self):
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": "没有日期的任务",
                "taskType": "learning",
                "rewardPoints": 1,
            },
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"], "missing_scheduled_date")

    def test_task_batch_creation_supports_day_schedule_rows(self):
        response = self.client.post(
            "/api/tasks/batch",
            json={
                "date": "2026-06-05",
                "tasks": [
                    {
                        "childId": self.child_id,
                        "title": "数学作业",
                        "taskType": "learning",
                        "startAt": "2026-06-05T19:00:00",
                        "dueAt": "2026-06-05T19:30:00",
                        "rewardPoints": 3,
                        "requiresParentConfirmation": True,
                    },
                    {
                        "childId": self.child_id,
                        "title": "阅读",
                        "taskType": "reading_interest",
                        "scheduledStart": "20:00",
                        "scheduledEnd": "20:20",
                        "rewardPoints": 2,
                        "requiresParentConfirmation": False,
                    },
                    {
                        "childId": self.child_id,
                        "title": "户外运动",
                        "taskType": "sports_outdoor",
                        "scheduledStart": "10:00",
                        "scheduledEnd": "10:30",
                        "rewardPoints": 4,
                    },
                ],
            },
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["tasks"]), 3)
        self.assertEqual(response.json["tasks"][1]["taskType"], "reading_interest")
        self.assertEqual(response.json["tasks"][1]["scheduledDate"], "2026-06-05")
        self.assertFalse(response.json["tasks"][1]["requiresParentConfirmation"])

        week = self.client.get(
            "/api/tasks",
            query_string={
                "childId": self.child_id,
                "startDate": "2026-06-05",
                "endDate": "2026-06-05",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(week.status_code, 200)
        self.assertEqual(len(week.json["tasks"]), 3)

    def test_task_batch_creation_reports_row_error_and_rolls_back(self):
        response = self.client.post(
            "/api/tasks/batch",
            json={
                "date": "2026-06-06",
                "tasks": [
                    {
                        "childId": self.child_id,
                        "title": "阅读",
                        "taskType": "reading_interest",
                        "scheduledStart": "20:00",
                        "scheduledEnd": "20:20",
                        "rewardPoints": 2,
                    },
                    {
                        "childId": self.child_id,
                        "title": "",
                        "taskType": "learning",
                        "scheduledStart": "20:30",
                        "scheduledEnd": "21:00",
                    },
                ],
            },
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("第 2 项", response.json["message"])

    def test_task_runtime_result_builds_family_scoped_websocket_update(self):
        messages = task_runtime_messages_by_family(
            {
                "checkedAt": 1780000000000,
                "changedTasks": [
                    {
                        "taskId": "task_1",
                        "familyId": "family_1",
                        "status": "in_progress",
                    }
                ],
                "events": [
                    {
                        "id": "event_1",
                        "familyId": "family_1",
                        "taskId": "task_1",
                        "eventType": "auto_started",
                    }
                ],
            }
        )

        self.assertIn("family_1", messages)
        message = messages["family_1"]
        self.assertEqual(message["type"], "task.updated")
        self.assertEqual(message["source"], "scheduler")
        self.assertEqual(message["taskIds"], ["task_1"])
        self.assertEqual(message["checkedAt"], 1780000000000)

    def test_task_runtime_result_keeps_families_separate(self):
        messages = task_runtime_messages_by_family(
            {
                "checkedAt": 1780000000000,
                "changedTasks": [
                    {
                        "taskId": "task_a",
                        "familyId": "family_a",
                        "status": "in_progress",
                    },
                    {
                        "taskId": "task_b",
                        "familyId": "family_b",
                        "status": "missed",
                    },
                ],
                "events": [
                    {
                        "id": "event_a",
                        "familyId": "family_a",
                        "taskId": "task_a",
                        "eventType": "auto_started",
                    },
                    {
                        "id": "event_b",
                        "familyId": "family_b",
                        "taskId": "task_b",
                        "eventType": "missed",
                    },
                ],
            }
        )

        self.assertEqual(set(messages), {"family_a", "family_b"})
        self.assertEqual(messages["family_a"]["taskIds"], ["task_a"])
        self.assertEqual(messages["family_b"]["taskIds"], ["task_b"])

        week = self.client.get(
            "/api/tasks",
            query_string={
                "childId": self.child_id,
                "startDate": "2026-06-06",
                "endDate": "2026-06-06",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(week.status_code, 200)
        self.assertEqual(week.json["tasks"], [])

    def test_reward_redemption_spends_cancels_and_fulfills_points(self):
        task = self._create_task(reward_points=30)
        self.client.post(f"/api/tasks/{task['id']}/complete", headers=self._auth_headers())
        self.client.post(f"/api/tasks/{task['id']}/parent-confirm", headers=self._auth_headers())

        reward = self.client.post(
            "/api/rewards/items",
            json={
                "childId": self.child_id,
                "title": "周末桌游 20 分钟",
                "pointsCost": 12,
                "category": "family_time",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(reward.status_code, 200)
        item = reward.json["item"]
        self.assertEqual(item["status"], "active")

        item_detail = self.client.get(
            f"/api/rewards/items/{item['id']}",
            headers=self._auth_headers(),
        )
        self.assertEqual(item_detail.status_code, 200)
        self.assertEqual(item_detail.json["item"]["title"], "周末桌游 20 分钟")

        list_items = self.client.get(
            "/api/rewards/items",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(list_items.status_code, 200)
        self.assertEqual(len(list_items.json["items"]), 1)

        redemption = self.client.post(
            "/api/rewards/redemptions",
            json={"rewardItemId": item["id"]},
            headers=self._auth_headers(),
        )
        self.assertEqual(redemption.status_code, 200)
        self.assertEqual(redemption.json["redemption"]["status"], "redeemed")
        self.assertEqual(redemption.json["account"]["balance"], 18)
        self.assertEqual(redemption.json["ledgerEntry"]["type"], "redemption_spent")

        cancelled = self.client.post(
            f"/api/rewards/redemptions/{redemption.json['redemption']['id']}/cancel",
            headers=self._auth_headers(),
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json["redemption"]["status"], "cancelled")
        self.assertEqual(cancelled.json["account"]["balance"], 30)
        self.assertEqual(cancelled.json["ledgerEntry"]["type"], "redemption_cancelled")

        cancelled_again = self.client.post(
            f"/api/rewards/redemptions/{redemption.json['redemption']['id']}/cancel",
            headers=self._auth_headers(),
        )
        self.assertEqual(cancelled_again.status_code, 200)
        self.assertEqual(cancelled_again.json["redemption"]["status"], "cancelled")
        self.assertEqual(cancelled_again.json["account"]["balance"], 30)
        self.assertNotIn("ledgerEntry", cancelled_again.json)

        second = self.client.post(
            "/api/rewards/redemptions",
            json={"rewardItemId": item["id"]},
            headers=self._auth_headers(),
        )
        self.assertEqual(second.status_code, 200)

        fulfilled = self.client.post(
            f"/api/rewards/redemptions/{second.json['redemption']['id']}/fulfill",
            headers=self._auth_headers(),
        )
        self.assertEqual(fulfilled.status_code, 200)
        self.assertEqual(fulfilled.json["redemption"]["status"], "fulfilled")

        redemptions = self.client.get(
            "/api/rewards/redemptions",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(redemptions.status_code, 200)
        self.assertEqual(len(redemptions.json["redemptions"]), 2)

        ledger = self.client.get(
            "/api/points/ledger",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        types = [entry["type"] for entry in ledger.json["ledger"]]
        self.assertIn("redemption_spent", types)
        self.assertIn("redemption_cancelled", types)

    def test_manual_point_adjustment_writes_ledger(self):
        adjust = self.client.post(
            "/api/points/adjust",
            json={"childId": self.child_id, "delta": 5, "note": "补记家务奖励"},
            headers=self._auth_headers(),
        )

        self.assertEqual(adjust.status_code, 200)
        self.assertEqual(adjust.json["account"]["balance"], 5)
        self.assertEqual(adjust.json["ledgerEntry"]["type"], "parent_adjustment")

    def test_stage_notice_acknowledge_stores_handled_balance(self):
        adjust = self.client.post(
            "/api/points/adjust",
            json={"childId": self.child_id, "delta": 10, "note": "阶段满额"},
            headers=self._auth_headers(),
        )
        self.assertEqual(adjust.status_code, 200)
        self.assertEqual(adjust.json["account"]["balance"], 10)
        self.assertEqual(adjust.json["account"]["stageNoticeHandledBalance"], 0)

        acknowledged = self.client.post(
            "/api/points/stage-notice/ack",
            json={"childId": self.child_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(acknowledged.status_code, 200)
        self.assertEqual(acknowledged.json["account"]["balance"], 10)
        self.assertEqual(acknowledged.json["account"]["stageNoticeHandledBalance"], 10)

        account = self.client.get(
            "/api/points/account",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(account.status_code, 200)
        self.assertEqual(account.json["account"]["stageNoticeHandledBalance"], 10)

    def test_point_reward_settings_are_backend_backed(self):
        settings = self.client.get("/api/points/settings", headers=self._auth_headers())

        self.assertEqual(settings.status_code, 200)
        self.assertEqual(settings.json["settings"]["stageThreshold"], 10)
        self.assertEqual(settings.json["settings"]["unit"], "flower")
        options = settings.json["settings"]["unitOptions"]
        self.assertEqual([item["key"] for item in options], ["points", "flower", "star"])
        self.assertEqual(options[1]["suffix"], "朵小红花")
        self.assertIn("assets/images/points/unit-flower.png", options[1]["imageAsset"])

        updated = self.client.patch(
            "/api/points/settings",
            json={"stageThreshold": 12, "unit": "star"},
            headers=self._auth_headers(),
        )

        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["settings"]["stageThreshold"], 12)
        self.assertEqual(updated.json["settings"]["unitOption"]["suffix"], "颗小星星")

        reloaded = self.client.get("/api/points/settings", headers=self._auth_headers())
        self.assertEqual(reloaded.json["settings"]["stageThreshold"], 12)
        self.assertEqual(reloaded.json["settings"]["unit"], "star")

        invalid_unit = self.client.patch(
            "/api/points/settings",
            json={"unit": "coin"},
            headers=self._auth_headers(),
        )
        self.assertEqual(invalid_unit.status_code, 400)

        invalid_threshold = self.client.patch(
            "/api/points/settings",
            json={"stageThreshold": 0},
            headers=self._auth_headers(),
        )
        self.assertEqual(invalid_threshold.status_code, 400)

    def test_point_account_lists_existing_child_before_any_ledger(self):
        response = self.client.get("/api/points/account", headers=self._auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["accounts"]), 1)
        self.assertEqual(response.json["accounts"][0]["childId"], self.child_id)
        self.assertEqual(response.json["accounts"][0]["balance"], 0)

    def test_task_isolation_by_family(self):
        task = self._create_task(reward_points=10)
        other_token = self._login("13900002026")

        response = self.client.get(
            f"/api/tasks/{task['id']}",
            headers={"Authorization": f"Bearer {other_token}"},
        )

        self.assertEqual(response.status_code, 404)

    def test_task_start_and_events_contract(self):
        task = self._create_task(reward_points=5)

        start = self.client.post(
            f"/api/tasks/{task['id']}/start",
            headers=self._auth_headers(),
        )
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.json["task"]["status"], "in_progress")

        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200)
        event_types = {event["eventType"] for event in events.json["events"]}
        self.assertIn("task_created", event_types)
        self.assertIn("manual_started", event_types)

    def test_scheduler_tick_auto_starts_task_and_records_camera_events(self):
        now = datetime.now().astimezone()
        start_at = now - timedelta(minutes=1)
        due_at = now + timedelta(minutes=2)
        task = self._create_task_at(start_at=start_at, due_at=due_at, reward_points=6)

        unauthenticated = self.client.post("/api/dev/tasks/scheduler/tick")
        self.assertEqual(unauthenticated.status_code, 401)

        tick = self._scheduler_tick()
        self.assertEqual(tick.status_code, 200)
        self.assertEqual(tick.json["changedTasks"][0]["id"], task["id"])
        self.assertEqual(tick.json["changedTasks"][0]["status"], "in_progress")
        tick_event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("auto_started", tick_event_types)
        self.assertIn("monitor_started", tick_event_types)

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["task"]["status"], "in_progress")

        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        event_types = {event["eventType"] for event in events.json["events"]}
        self.assertIn("auto_started", event_types)
        self.assertIn("monitor_started", event_types)

    def test_runtime_learning_waits_for_classroom_events_and_stops_camera_monitor(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="20以内加法互动课",
            task_type="learning",
            start_at=now - timedelta(minutes=1),
            due_at=now + timedelta(minutes=5),
            reward_points=0,
            requires_parent_confirmation=False,
        )
        with Database(self.app.config["DATABASE_URL"]).transaction() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET learning_course_id = 'course-runtime-test',
                  learning_course_version = '1'
                WHERE id = ?
                """,
                (task["id"],),
            )

        tick = self._scheduler_tick()

        self.assertEqual(tick.status_code, 200, tick.json)
        self.assertEqual(tick.json["changedTasks"][0]["status"], "delayed")
        event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("learning_classroom_waiting", event_types)
        self.assertIn("learning_start_reminder_sent", event_types)
        self.assertIn("monitor_started", event_types)
        self.assertNotIn("auto_started", event_types)

        started = self.client.post(
            f"/api/tasks/{task['id']}/start",
            headers=self._auth_headers(),
        )
        self.assertEqual(started.status_code, 200, started.json)
        with self.app.app_context():
            coordinated = task_runtime_service().learning_classroom_started(
                family_id=started.json["task"]["familyId"],
                task_id=task["id"],
            )
            completed = task_runtime_service().learning_classroom_completed(
                family_id=started.json["task"]["familyId"],
                task_id=task["id"],
            )
        self.assertTrue(coordinated["ok"])
        self.assertTrue(completed["ok"])

        detail = self.client.get(
            f"/api/tasks/{task['id']}",
            headers=self._auth_headers(),
        )
        # The camera coordinator cannot declare learning complete; only the
        # authoritative classroom/report transaction does that.
        self.assertEqual(detail.json["task"]["status"], "in_progress")
        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        persisted_types = {event["eventType"] for event in events.json["events"]}
        self.assertIn("learning_classroom_started", persisted_types)
        self.assertIn("learning_monitor_stopped", persisted_types)
        self.assertIn("learning_classroom_completed", persisted_types)
        self.assertIn("learning_finish_reminder_sent", persisted_types)

    def test_scheduler_tick_records_offline_camera_without_blocking_task(self):
        offline_app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="disabled"))
        offline_client = offline_app.test_client()
        offline_token = self._login_with_client(offline_client, "13700002026")
        offline_child = self._create_child_with_client(offline_client, offline_token, "小北")
        now = datetime.now().astimezone()
        response = offline_client.post(
            "/api/tasks",
            json={
                "childId": offline_child,
                "title": "整理书包",
                "taskType": "schoolbag",
                "startAt": (now - timedelta(minutes=1)).isoformat(),
                "dueAt": (now + timedelta(minutes=2)).isoformat(),
                "rewardPoints": 2,
            },
            headers={"Authorization": f"Bearer {offline_token}"},
        )
        self.assertEqual(response.status_code, 200)
        task = response.json["task"]

        tick = self._scheduler_tick(client=offline_client, access_token=offline_token)
        self.assertEqual(tick.status_code, 200)
        self.assertEqual(tick.json["changedTasks"][0]["status"], "in_progress")
        event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("auto_started", event_types)
        self.assertIn("monitor_failed", event_types)

        events = offline_client.get(
            f"/api/tasks/{task['id']}/events",
            headers={"Authorization": f"Bearer {offline_token}"},
        )
        self.assertEqual(events.status_code, 200)
        messages = [event["message"] for event in events.json["events"]]
        self.assertIn("摄像头暂时离线，任务仍会记录", messages)

    def test_scheduler_sends_reminder_once_before_start(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            start_at=now + timedelta(minutes=1),
            due_at=now + timedelta(minutes=5),
            reward_points=2,
            reminder_minutes_before=2,
        )

        first = self._scheduler_tick()
        second = self._scheduler_tick()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn("reminder_sent", {event["eventType"] for event in first.json["events"]})
        self.assertNotIn("reminder_sent", {event["eventType"] for event in second.json["events"]})

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "reminder_sent")
        self.assertEqual(detail.json["task"]["reminderStatus"], "sent")

    def test_task_reminder_uses_task_title_type_and_age_context(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="打篮球",
            task_type="sports_outdoor",
            start_at=now + timedelta(minutes=1),
            due_at=now + timedelta(minutes=20),
            reward_points=2,
            requires_parent_confirmation=False,
        )

        response = self.client.post(
            f"/api/tasks/{task['id']}/reminder",
            json={"phase": "start"},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        reminder = response.json["reminder"]
        self.assertEqual(reminder["phase"], "start")
        self.assertEqual(reminder["category"], "sports_ball")
        self.assertIn("打篮球", reminder["text"])
        self.assertIn("安全", reminder["text"])

        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        event_types = {event["eventType"] for event in events.json["events"]}
        self.assertIn("manual_start_reminder_sent", event_types)

    def test_drink_water_prepare_reminder_uses_child_name_without_generic_copy(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="喝水",
            task_type="life",
            start_at=now + timedelta(minutes=1),
            due_at=now + timedelta(minutes=5),
            reward_points=1,
            requires_parent_confirmation=False,
        )

        response = self.client.post(
            f"/api/tasks/{task['id']}/reminder",
            json={"phase": "prepare"},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        reminder = response.json["reminder"]
        self.assertEqual(reminder["phase"], "prepare")
        self.assertEqual(reminder["category"], "hydration")
        self.assertIn("小宇", reminder["text"])
        self.assertNotIn("小朋友", reminder["text"])
        self.assertIn("喝", reminder["text"])
        self.assertIn("水", reminder["text"])
        for bad_copy in ("准备东西", "准备物品", "准备材料", "要用的东西", "放到手边"):
            self.assertNotIn(bad_copy, reminder["text"])

    def test_task_reminder_can_use_ai_provider_with_task_context(self):
        provider = FakeReminderAiProvider("小宇，喝水时间到啦，慢慢喝几口水。")

        reminder = build_task_reminder(
            {
                "title": "喝水",
                "description": "午休后补水",
                "type": "life",
                "scheduled_start": "14:30",
                "scheduled_end": "14:35",
                "recentReminderTexts": ["小宇，先喝几口水吧。"],
                "evidence": {"hasPerson": False},
            },
            phase="start",
            child={"nickname": "小宇", "grade": "中班"},
            ai_text_provider=provider,
            prompt="按任务内容生成一句自然提醒。",
        )

        self.assertEqual(reminder["textSource"], "ai")
        self.assertEqual(reminder["text"], "小宇，喝水时间到啦，慢慢喝几口水。")
        self.assertIn("任务标题：喝水", provider.last_user_prompt)
        self.assertIn("任务说明：午休后补水", provider.last_user_prompt)
        self.assertIn("语义分类：hydration", provider.last_user_prompt)
        self.assertIn("孩子称呼：小宇", provider.last_user_prompt)
        self.assertIn("提醒阶段说明：到点开始", provider.last_user_prompt)
        self.assertIn("最近提醒：小宇，先喝几口水吧。", provider.last_user_prompt)
        self.assertIn("摄像头观察：no_person", provider.last_user_prompt)

    def test_hydration_ai_prepare_copy_with_generic_object_text_falls_back(self):
        provider = FakeReminderAiProvider("小朋友，喝水快到了，先把东西放到手边。")

        reminder = build_task_reminder(
            {
                "title": "喝水",
                "description": "午休后补水",
                "type": "life",
                "scheduled_start": "14:30",
                "scheduled_end": "14:35",
            },
            phase="prepare",
            child={"nickname": "小宇", "grade": "中班"},
            ai_text_provider=provider,
            prompt="按任务内容生成一句自然提醒。",
        )

        self.assertEqual(reminder["textSource"], "fallback")
        self.assertIn("小宇", reminder["text"])
        self.assertNotIn("小朋友", reminder["text"])
        self.assertNotIn("放到手边", reminder["text"])
        self.assertIn("喝", reminder["text"])

    def test_task_reminder_repeated_ai_text_falls_back(self):
        provider = FakeReminderAiProvider("小宇，喝水时间到啦，慢慢喝几口水。")

        reminder = build_task_reminder(
            {
                "title": "喝水",
                "description": "午休后补水",
                "type": "life",
                "scheduled_start": "14:30",
                "scheduled_end": "14:35",
                "recentReminderTexts": ["小宇，喝水时间到啦，慢慢喝几口水。"],
            },
            phase="start",
            child={"nickname": "小宇", "grade": "中班"},
            ai_text_provider=provider,
            prompt="按任务内容生成一句自然提醒。",
        )

        self.assertEqual(reminder["textSource"], "fallback")
        self.assertIn("喝", reminder["text"])
        self.assertNotEqual(reminder["text"], "小宇，喝水时间到啦，慢慢喝几口水。")

    def test_preschool_outdoor_walk_reminder_uses_child_friendly_copy(self):
        reminder = build_task_reminder(
            {
                "title": "遛娃",
                "description": "饭后到小区里走一走",
                "type": "sports_outdoor",
                "scheduled_start": "18:30",
                "scheduled_end": "19:00",
            },
            phase="start",
            child={"nickname": "小宇", "age_stage": "幼儿园"},
            prompt="",
        )

        self.assertEqual(reminder["textSource"], "fallback")
        self.assertEqual(reminder["category"], "outdoor_walk")
        self.assertIn("小宇", reminder["text"])
        self.assertIn("出门", reminder["text"])
        self.assertIn("走", reminder["text"])
        self.assertNotIn("遛娃", reminder["text"])
        self.assertNotIn("运动", reminder["text"])

    def test_api_prepare_reminder_for_preschool_outdoor_walk_avoids_generic_copy(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="遛娃",
            task_type="sports_outdoor",
            start_at=now + timedelta(minutes=1),
            due_at=now + timedelta(minutes=30),
            reward_points=1,
            requires_parent_confirmation=False,
        )

        response = self.client.post(
            f"/api/tasks/{task['id']}/reminder",
            json={"phase": "prepare"},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        reminder = response.json["reminder"]
        self.assertEqual(reminder["phase"], "prepare")
        self.assertEqual(reminder["category"], "outdoor_walk")
        self.assertIn("小宇", reminder["text"])
        self.assertIn("出门", reminder["text"])
        self.assertIn("鞋", reminder["text"])
        self.assertNotIn("遛娃", reminder["text"])
        self.assertNotIn("第一步", reminder["text"])
        self.assertNotIn("怎么做", reminder["text"])

    def test_custom_outdoor_walk_synonyms_avoid_generic_copy(self):
        reminder = build_task_reminder(
            {
                "title": "溜娃",
                "description": "楼下晒太阳",
                "type": "custom",
                "scheduled_start": "18:30",
                "scheduled_end": "19:00",
            },
            phase="prepare",
            child={"nickname": "小宇", "age_stage": "幼儿园"},
            prompt="",
        )

        self.assertEqual(reminder["category"], "outdoor_walk")
        self.assertIn("出门", reminder["text"])
        self.assertNotIn("溜娃", reminder["text"])
        self.assertNotIn("第一步", reminder["text"])

    def test_outdoor_walk_ai_copy_rewrites_parent_facing_title(self):
        provider = FakeReminderAiProvider("小朋友，遛娃开始啦，牵好大人的手。")

        reminder = build_task_reminder(
            {
                "title": "遛娃",
                "description": "饭后到小区里走一走",
                "type": "sports_outdoor",
                "scheduled_start": "18:30",
                "scheduled_end": "19:00",
            },
            phase="start",
            child={"nickname": "小宇", "age_stage": "幼儿园"},
            ai_text_provider=provider,
            prompt="按任务内容生成一句自然提醒。",
        )

        self.assertEqual(reminder["textSource"], "ai")
        self.assertEqual(reminder["category"], "outdoor_walk")
        self.assertIn("孩子可听懂说法：出门走走", provider.last_user_prompt)
        self.assertIn("孩子称呼：小宇", provider.last_user_prompt)
        self.assertIn("小宇", reminder["text"])
        self.assertIn("出门走走", reminder["text"])
        self.assertNotIn("小朋友", reminder["text"])
        self.assertNotIn("遛娃", reminder["text"])

    def test_outdoor_walk_ai_generic_prepare_copy_falls_back(self):
        provider = FakeReminderAiProvider("小朋友，遛娃快到了，先想一想第一步要怎么做。")

        reminder = build_task_reminder(
            {
                "title": "遛娃",
                "description": "饭后到小区里走一走",
                "type": "sports_outdoor",
                "scheduled_start": "18:30",
                "scheduled_end": "19:00",
            },
            phase="prepare",
            child={"nickname": "小爱", "age_stage": "幼儿园"},
            ai_text_provider=provider,
            prompt="按任务内容生成一句自然提醒。",
        )

        self.assertEqual(reminder["textSource"], "fallback")
        self.assertEqual(reminder["category"], "outdoor_walk")
        self.assertIn("小爱", reminder["text"])
        self.assertIn("出门", reminder["text"])
        self.assertNotIn("小朋友", reminder["text"])
        self.assertNotIn("遛娃", reminder["text"])
        self.assertNotIn("第一步", reminder["text"])
        self.assertNotIn("怎么做", reminder["text"])

    def test_voice_reminder_setting_disables_manual_camera_speak(self):
        setting = self.client.patch(
            "/api/settings/ai-care-rules",
            json={"value": {"voiceReminderEnabled": False}},
            headers=self._auth_headers(),
        )
        self.assertEqual(setting.status_code, 200)
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="阅读任务",
            task_type="reading_interest",
            start_at=now + timedelta(minutes=1),
            due_at=now + timedelta(minutes=20),
            reward_points=2,
        )

        response = self.client.post(
            f"/api/tasks/{task['id']}/reminder",
            json={"phase": "start"},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["command"]["status"], "skipped")
        self.assertEqual(
            response.json["command"]["reason"],
            "voice_reminder_disabled",
        )
        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        event_types = {event["eventType"] for event in events.json["events"]}
        self.assertIn("manual_start_reminder_skipped", event_types)

    def test_tasks_without_camera_create_and_skip_camera_reminders(self):
        app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="mock"))
        client = app.test_client()
        access_token = self._login_with_client(client, "13800006666")
        child_id = self._create_child_without_device_with_client(client, access_token, "小新")
        headers = {"Authorization": f"Bearer {access_token}"}
        setting = client.patch(
            "/api/settings/ai-care-rules",
            json={"value": {"voiceReminderEnabled": True}},
            headers=headers,
        )
        self.assertEqual(setting.status_code, 200)
        now = datetime.now().astimezone()

        single = client.post(
            "/api/tasks",
            json={
                "childId": child_id,
                "title": "喝水休息",
                "taskType": "life",
                "startAt": (now + timedelta(minutes=30)).isoformat(),
                "dueAt": (now + timedelta(minutes=40)).isoformat(),
                "rewardPoints": 1,
                "requiresParentConfirmation": False,
            },
            headers=headers,
        )
        self.assertEqual(single.status_code, 200)

        batch = client.post(
            "/api/tasks/batch",
            json={
                "date": now.date().isoformat(),
                "tasks": [
                    {
                        "childId": child_id,
                        "title": "绘本时间",
                        "taskType": "reading_interest",
                        "scheduledStart": "19:00",
                        "scheduledEnd": "19:20",
                    },
                    {
                        "childId": child_id,
                        "title": "玩具回位",
                        "taskType": "housework",
                        "scheduledStart": "19:30",
                        "scheduledEnd": "19:40",
                    },
                ],
            },
            headers=headers,
        )
        self.assertEqual(batch.status_code, 200)
        self.assertEqual(len(batch.json["tasks"]), 2)

        manual = client.post(
            f"/api/tasks/{single.json['task']['id']}/reminder",
            json={"phase": "start"},
            headers=headers,
        )
        self.assertEqual(manual.status_code, 200)
        self.assertEqual(manual.json["command"]["status"], "skipped")
        self.assertEqual(manual.json["command"]["reason"], "no_camera_device")
        manual_events = client.get(
            f"/api/tasks/{single.json['task']['id']}/events",
            headers=headers,
        )
        manual_types = {event["eventType"] for event in manual_events.json["events"]}
        self.assertIn("manual_start_reminder_skipped", manual_types)
        self.assertNotIn("manual_start_reminder_sent", manual_types)

        reminder_task = client.post(
            "/api/tasks",
            json={
                "childId": child_id,
                "title": "整理水杯",
                "taskType": "life",
                "startAt": (now + timedelta(minutes=1)).isoformat(),
                "dueAt": (now + timedelta(minutes=10)).isoformat(),
                "rewardPoints": 1,
                "reminderMinutesBefore": 2,
                "requiresParentConfirmation": False,
            },
            headers=headers,
        )
        self.assertEqual(reminder_task.status_code, 200)
        reminder_tick = self._scheduler_tick(client=client, access_token=access_token)
        self.assertEqual(reminder_tick.status_code, 200)
        reminder_event_types = {event["eventType"] for event in reminder_tick.json["events"]}
        self.assertIn("reminder_skipped", reminder_event_types)
        self.assertNotIn("reminder_sent", reminder_event_types)
        reminder_messages = " ".join(event["message"] for event in reminder_tick.json["events"])
        self.assertIn("未连接摄像头，本次只记录安排。", reminder_messages)

        active = client.post(
            "/api/tasks",
            json={
                "childId": child_id,
                "title": "自己阅读一本绘本",
                "taskType": "reading_interest",
                "startAt": (now - timedelta(minutes=2)).isoformat(),
                "dueAt": (now + timedelta(minutes=2)).isoformat(),
                "rewardPoints": 3,
                "requiresParentConfirmation": False,
            },
            headers=headers,
        )
        self.assertEqual(active.status_code, 200)
        start_tick = self._scheduler_tick(client=client, access_token=access_token)
        self.assertEqual(start_tick.status_code, 200)
        changed = {task["id"]: task for task in start_tick.json["changedTasks"]}
        self.assertEqual(changed[active.json["task"]["id"]]["status"], "in_progress")
        self.assertEqual(
            changed[active.json["task"]["id"]]["cameraObservationStatus"],
            "no_camera_device",
        )
        start_event_types = {event["eventType"] for event in start_tick.json["events"]}
        self.assertIn("auto_started", start_event_types)
        self.assertNotIn("start_reminder_sent", start_event_types)
        self.assertNotIn("monitor_started", start_event_types)

        client.patch(
            f"/api/tasks/{active.json['task']['id']}",
            json={"dueAt": (now - timedelta(seconds=5)).isoformat()},
            headers=headers,
        )
        finish_tick = self._scheduler_tick(client=client, access_token=access_token)
        self.assertEqual(finish_tick.status_code, 200)
        finish_changed = {task["id"]: task for task in finish_tick.json["changedTasks"]}
        self.assertEqual(finish_changed[active.json["task"]["id"]]["status"], "missed")
        finish_event_types = {event["eventType"] for event in finish_tick.json["events"]}
        self.assertIn("missed", finish_event_types)
        self.assertNotIn("completed", finish_event_types)
        self.assertNotIn("points_awarded", finish_event_types)

        ledger = client.get(
            "/api/points/ledger",
            query_string={"childId": child_id},
            headers=headers,
        )
        task_entries = [
            entry
            for entry in ledger.json["ledger"]
            if entry["sourceId"] == active.json["task"]["id"]
            and entry["type"] == "task_completed"
        ]
        self.assertEqual(task_entries, [])

    def test_scheduler_marks_child_not_ready_as_delayed_and_nudges(self):
        original = MockCameraRuntimeAdapter.task_observation
        MockCameraRuntimeAdapter.task_observation = lambda self, task: {
            "verdict": "not_started",
            "reason": "child_not_present",
            "confidence": 0.8,
            "evidence": {"hasPerson": False},
        }
        try:
            now = datetime.now().astimezone()
            task = self._create_task_at(
                start_at=now - timedelta(minutes=1),
                due_at=now + timedelta(minutes=10),
                reward_points=2,
            )
            tick = self._scheduler_tick()
        finally:
            MockCameraRuntimeAdapter.task_observation = original

        self.assertEqual(tick.status_code, 200)
        self.assertEqual(tick.json["changedTasks"][0]["status"], "delayed")
        event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("child_not_ready", event_types)
        self.assertIn("delayed", event_types)
        self.assertIn("delay_reminder_sent", event_types)

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "delayed")
        self.assertEqual(detail.json["task"]["delayReminderCount"], 1)

        events = self.client.get("/api/camera/events", headers=self._auth_headers())
        self.assertEqual(events.status_code, 200)
        visible_text = " ".join(
            f"{event.get('displayTitle', '')} {event.get('displayMessage', '')} {event.get('title', '')} {event.get('message', '')}"
            for event in events.json["events"]
        )
        event_types = {event["eventType"] for event in events.json["events"]}
        self.assertNotIn("还没看到孩子开始", visible_text)
        self.assertNotIn("已继续提醒", visible_text)
        self.assertFalse(
            any(event.get("category") == "task_observation" for event in events.json["events"])
        )
        self.assertFalse(any(event.get("category") == "care_reminder" for event in events.json["events"]))
        self.assertNotIn("任务事件", visible_text)
        self.assertNotIn("已执行", visible_text)
        self.assertNotIn("开始观察", visible_text)
        self.assertNotIn("reminder_due", event_types)
        self.assertNotIn("monitor_started", event_types)

    def test_scheduler_respects_ai_rule_settings(self):
        original = MockCameraRuntimeAdapter.task_observation
        MockCameraRuntimeAdapter.task_observation = lambda self, task: {
            "verdict": "not_started",
            "reason": "child_not_present",
            "confidence": 0.8,
            "evidence": {"hasPerson": False},
        }
        try:
            disabled_delay = self.client.patch(
                "/api/settings/ai-care-rules",
                json={"value": {"delayReminderEnabled": False}},
                headers=self._auth_headers(),
            )
            self.assertEqual(disabled_delay.status_code, 200)
            now = datetime.now().astimezone()
            delayed_task = self._create_task_at(
                start_at=now - timedelta(minutes=1),
                due_at=now + timedelta(minutes=10),
                reward_points=2,
            )
            delayed_tick = self._scheduler_tick()
            self.assertEqual(delayed_tick.status_code, 200)
            delayed_event_types = {
                event["eventType"] for event in delayed_tick.json["events"]
            }
            self.assertIn("delayed", delayed_event_types)
            self.assertNotIn("delay_reminder_sent", delayed_event_types)
            delayed_detail = self.client.get(
                f"/api/tasks/{delayed_task['id']}",
                headers=self._auth_headers(),
            )
            self.assertEqual(delayed_detail.json["task"]["delayReminderCount"], 0)

            disabled_observation = self.client.patch(
                "/api/settings/ai-care-rules",
                json={
                    "value": {
                        "taskObservationEnabled": False,
                        "delayReminderEnabled": True,
                    }
                },
                headers=self._auth_headers(),
            )
            self.assertEqual(disabled_observation.status_code, 200)
            auto_task = self._create_task_at(
                start_at=now - timedelta(minutes=2),
                due_at=now + timedelta(minutes=8),
                reward_points=2,
            )
            auto_tick = self._scheduler_tick()
            self.assertEqual(auto_tick.status_code, 200)
            auto_event_types = {event["eventType"] for event in auto_tick.json["events"]}
            self.assertIn("auto_started", auto_event_types)
            self.assertNotIn("child_not_ready", auto_event_types)
            auto_detail = self.client.get(
                f"/api/tasks/{auto_task['id']}",
                headers=self._auth_headers(),
            )
            self.assertEqual(auto_detail.json["task"]["status"], "in_progress")
            self.assertEqual(
                auto_detail.json["task"]["cameraObservationStatus"],
                "not_required",
            )
        finally:
            MockCameraRuntimeAdapter.task_observation = original

    def test_scheduler_does_not_mark_hydration_normal_without_matching_observation(self):
        original = MockCameraRuntimeAdapter.task_observation
        MockCameraRuntimeAdapter.task_observation = lambda self, task: {
            "verdict": "started",
            "reason": "mock_child_ready",
            "confidence": 0.8,
            "evidence": {"hasPerson": True, "activity": "其他"},
        }
        try:
            now = datetime.now().astimezone()
            task = self._create_task_at(
                title="喝水",
                task_type="life",
                start_at=now - timedelta(minutes=1),
                due_at=now + timedelta(minutes=5),
                reward_points=1,
                requires_parent_confirmation=False,
            )
            tick = self._scheduler_tick()
        finally:
            MockCameraRuntimeAdapter.task_observation = original

        self.assertEqual(tick.status_code, 200)
        self.assertEqual(tick.json["changedTasks"][0]["status"], "delayed")
        event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("child_not_ready", event_types)
        self.assertIn("delayed", event_types)
        self.assertNotIn("auto_started", event_types)
        self.assertNotIn("observation_unavailable", event_types)

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "delayed")
        self.assertEqual(detail.json["task"]["cameraObservationStatus"], "action_not_supported")

    def test_delayed_reading_task_marks_missed_at_end_without_finish_reminder(self):
        original = MockCameraRuntimeAdapter.task_observation
        MockCameraRuntimeAdapter.task_observation = lambda self, task: {
            "verdict": "not_started",
            "reason": "child_not_present",
            "confidence": 0.8,
            "evidence": {"hasPerson": False},
        }
        try:
            now = datetime.now().astimezone()
            task = self._create_task_at(
                title="自己阅读一本绘本",
                task_type="reading_interest",
                start_at=now - timedelta(minutes=10),
                due_at=now + timedelta(minutes=2),
                reward_points=3,
                requires_parent_confirmation=False,
            )
            delayed_tick = self._scheduler_tick()
            self.assertEqual(delayed_tick.status_code, 200)
            self.assertEqual(delayed_tick.json["changedTasks"][0]["status"], "delayed")

            self.client.patch(
                f"/api/tasks/{task['id']}",
                json={"dueAt": (now - timedelta(seconds=5)).isoformat()},
                headers=self._auth_headers(),
            )
            finish_tick = self._scheduler_tick()
        finally:
            MockCameraRuntimeAdapter.task_observation = original

        self.assertEqual(finish_tick.status_code, 200)
        self.assertEqual(finish_tick.json["changedTasks"][0]["status"], "missed")
        event_types = {event["eventType"] for event in finish_tick.json["events"]}
        self.assertIn("missed", event_types)
        self.assertNotIn("finish_reminder_sent", event_types)
        self.assertNotIn("completed", event_types)

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "missed")
        self.assertIsNone(detail.json["task"]["pointsGrantedAt"])

        events = self.client.get("/api/camera/events", headers=self._auth_headers())
        visible_text = " ".join(
            f"{event.get('displayTitle', '')} {event.get('displayMessage', '')}"
            for event in events.json["events"]
        )
        self.assertNotIn("本次未记录完成", visible_text)
        self.assertNotIn("任务已完成", visible_text)
        self.assertNotIn("已提醒结束", visible_text)

    def test_started_reading_without_completion_evidence_requires_parent_confirmation(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="自己阅读一本绘本",
            task_type="reading_interest",
            start_at=now - timedelta(minutes=8),
            due_at=now + timedelta(minutes=2),
            reward_points=4,
            requires_parent_confirmation=True,
        )
        start_tick = self._scheduler_tick()
        self.assertEqual(start_tick.status_code, 200)
        self.assertEqual(start_tick.json["changedTasks"][0]["status"], "in_progress")

        self.client.patch(
            f"/api/tasks/{task['id']}",
            json={"dueAt": (now - timedelta(seconds=5)).isoformat()},
            headers=self._auth_headers(),
        )
        finish_tick = self._scheduler_tick()

        self.assertEqual(finish_tick.status_code, 200)
        self.assertEqual(
            finish_tick.json["changedTasks"][0]["status"],
            "awaiting_parent_confirmation",
        )
        event_types = {event["eventType"] for event in finish_tick.json["events"]}
        self.assertIn("awaiting_parent_confirmation", event_types)
        self.assertNotIn("finish_reminder_sent", event_types)
        self.assertNotIn("completed", event_types)

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "awaiting_parent_confirmation")
        self.assertEqual(detail.json["task"]["evidenceSummary"], "只看到部分过程，请确认是否完成。")
        self.assertIsNone(detail.json["task"]["pointsGrantedAt"])

    def test_history_reading_task_without_observation_does_not_auto_finish(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="自己阅读一本绘本",
            task_type="reading_interest",
            start_at=now - timedelta(days=1, hours=1),
            due_at=now - timedelta(days=1, minutes=30),
            reward_points=5,
            requires_parent_confirmation=False,
        )
        start = self.client.post(f"/api/tasks/{task['id']}/start", headers=self._auth_headers())
        self.assertEqual(start.status_code, 200)

        tick = self._scheduler_tick()

        self.assertEqual(tick.status_code, 200)
        self.assertEqual(tick.json["changedTasks"][0]["status"], "missed")
        event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("missed", event_types)
        self.assertNotIn("finish_reminder_sent", event_types)
        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "missed")
        self.assertIsNone(detail.json["task"]["pointsGrantedAt"])

    def test_scheduler_announces_task_start_and_finish(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="打篮球",
            task_type="sports_outdoor",
            start_at=now - timedelta(minutes=1),
            due_at=now + timedelta(minutes=4),
            reward_points=2,
            requires_parent_confirmation=False,
        )

        start_tick = self._scheduler_tick()

        self.assertEqual(start_tick.status_code, 200)
        start_event_types = {event["eventType"] for event in start_tick.json["events"]}
        self.assertIn("auto_started", start_event_types)
        self.assertIn("monitor_not_required", start_event_types)
        self.assertNotIn("monitor_started", start_event_types)
        self.assertNotIn("monitor_failed", start_event_types)
        start_event = next(
            event for event in start_tick.json["events"] if event["eventType"] == "start_reminder_sent"
        )
        self.assertIn("打篮球", start_event["payload"]["text"])

        self.client.patch(
            f"/api/tasks/{task['id']}",
            json={"dueAt": (now - timedelta(seconds=5)).isoformat()},
            headers=self._auth_headers(),
        )
        finish_tick = self._scheduler_tick()

        self.assertEqual(finish_tick.status_code, 200)
        finish_event = next(
            event
            for event in finish_tick.json["events"]
            if event["eventType"] == "finish_reminder_sent"
        )
        self.assertIn("打篮球", finish_event["payload"]["text"])

    def test_scheduler_marks_past_unstarted_task_missed(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            start_at=now - timedelta(days=1, hours=1),
            due_at=now - timedelta(days=1, minutes=30),
            reward_points=2,
        )

        tick = self._scheduler_tick()

        self.assertEqual(tick.status_code, 200)
        self.assertEqual(tick.json["changedTasks"][0]["status"], "missed")
        event_types = {event["eventType"] for event in tick.json["events"]}
        self.assertIn("missed", event_types)

        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "missed")
        self.assertIsNotNone(detail.json["task"]["missedAt"])
        self.assertEqual(
            {action["value"] for action in detail.json["task"]["parentActions"]},
            {"reschedule", "manual_complete", "acknowledge_missed"},
        )

        acknowledged = self.client.post(
            f"/api/tasks/{task['id']}/acknowledge-missed",
            headers=self._auth_headers(),
        )
        self.assertEqual(acknowledged.status_code, 200)
        self.assertEqual(acknowledged.json["task"]["status"], "missed")
        self.assertEqual(acknowledged.json["task"]["parentActions"], [])

        events = self.client.get(
            f"/api/tasks/{task['id']}/events",
            headers=self._auth_headers(),
        )
        event_types = {event["eventType"] for event in events.json["events"]}
        self.assertIn("missed_acknowledged", event_types)

    def test_scheduler_finishes_unconfirmed_task_and_grants_points_once(self):
        now = datetime.now().astimezone()
        task = self._create_task_at(
            title="打篮球",
            task_type="sports_outdoor",
            start_at=now - timedelta(minutes=10),
            due_at=now - timedelta(minutes=1),
            reward_points=7,
            requires_parent_confirmation=False,
        )
        start = self.client.post(f"/api/tasks/{task['id']}/start", headers=self._auth_headers())
        self.assertEqual(start.status_code, 200)

        first = self._scheduler_tick()
        second = self._scheduler_tick()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        detail = self.client.get(f"/api/tasks/{task['id']}", headers=self._auth_headers())
        self.assertEqual(detail.json["task"]["status"], "completed")
        self.assertIsNotNone(detail.json["task"]["pointsGrantedAt"])

        ledger = self.client.get(
            "/api/points/ledger",
            query_string={"childId": self.child_id},
            headers=self._auth_headers(),
        )
        task_entries = [
            entry
            for entry in ledger.json["ledger"]
            if entry["sourceId"] == task["id"] and entry["type"] == "task_completed"
        ]
        self.assertEqual(len(task_entries), 1)
        self.assertEqual(task_entries[0]["delta"], 7)

    def _create_task(self, *, reward_points: int) -> dict:
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": "数学作业",
                "type": "learning",
                "rewardPoints": reward_points,
                "scheduledDate": datetime.now().date().isoformat(),
                "scheduledStart": "19:00",
                "scheduledEnd": "19:30",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["task"]

    def _create_task_at(
        self,
        *,
        start_at: datetime,
        due_at: datetime,
        reward_points: int,
        title: str = "阅读任务",
        task_type: str = "reading_interest",
        reminder_minutes_before: int | None = None,
        requires_parent_confirmation: bool = True,
    ) -> dict:
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": title,
                "taskType": task_type,
                "startAt": start_at.isoformat(),
                "dueAt": due_at.isoformat(),
                "rewardPoints": reward_points,
                "requiresParentConfirmation": requires_parent_confirmation,
                **(
                    {"reminderMinutesBefore": reminder_minutes_before}
                    if reminder_minutes_before is not None
                    else {}
                ),
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["task"]

    def _scheduler_tick(self, *, client=None, access_token: str | None = None):
        target_client = client or self.client
        token = access_token or self.access_token
        return target_client.post(
            "/api/dev/tasks/scheduler/tick",
            headers={"Authorization": f"Bearer {token}"},
        )

    def _login(self, phone: str) -> str:
        return self._login_with_client(self.client, phone)

    def _login_with_client(self, client, phone: str) -> str:
        code = request_debug_code(client, phone)
        login = client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(login.status_code, 200)
        return login.json["tokens"]["accessToken"]

    def _create_child(self, name: str) -> str:
        return self._create_child_with_client(self.client, self.access_token, name)

    def _create_child_with_client(self, client, access_token: str, name: str) -> str:
        self._prepare_setup_prerequisites(client, access_token)
        response = client.post(
            "/api/setup/child",
            json={"name": name, "nickname": name, "ageStage": "primary"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(response.status_code, 200)
        return response.json["child"]["id"]

    def _create_child_without_device_with_client(self, client, access_token: str, name: str) -> str:
        headers = {"Authorization": f"Bearer {access_token}"}
        parent = client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200)
        response = client.post(
            "/api/setup/child",
            json={"name": name, "nickname": name, "ageStage": "幼儿园", "grade": "中班"},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        return response.json["child"]["id"]

    def _prepare_setup_prerequisites(self, client, access_token: str) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        parent = client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200)
        device = client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-TASK", "deviceName": "客厅设备", "location": "客厅"},
            headers=headers,
        )
        self.assertEqual(device.status_code, 200)
        wifi = client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=headers,
        )
        self.assertEqual(wifi.status_code, 200)

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
