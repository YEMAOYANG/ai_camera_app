from __future__ import annotations

import unittest

from app import create_app
from tests.support import fresh_test_config, request_debug_code


class TasksPointsRewardsApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
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
        self.assertEqual(ledger.json["ledger"][0]["type"], "task_completed")
        self.assertEqual(ledger.json["ledger"][0]["delta"], 20)

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

    def _create_task(self, *, reward_points: int) -> dict:
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": "数学作业",
                "type": "learning",
                "rewardPoints": reward_points,
                "scheduledStart": "19:00",
                "scheduledEnd": "19:30",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["task"]

    def _login(self, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": code})
        self.assertEqual(login.status_code, 200)
        return login.json["tokens"]["accessToken"]

    def _create_child(self, name: str) -> str:
        response = self.client.post(
            "/api/setup/child",
            json={"name": name, "nickname": name, "ageStage": "primary"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["child"]["id"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
