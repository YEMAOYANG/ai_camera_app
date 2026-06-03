from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import create_app


class TasksPointsRewardsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "AUTH_DB_PATH": str(Path(self.tmp.name) / "auth.db"),
                "AUTH_ACCESS_TOKEN_SECONDS": 900,
                "AUTH_REFRESH_TOKEN_SECONDS": 3600,
                "AUTH_DEV_SMS_CODE": "0426",
            }
        )
        self.client = self.app.test_client()
        self.access_token = self._login("13800002026")
        self.child_id = self._create_child("小宇")

    def tearDown(self):
        self.tmp.cleanup()

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
        self.client.post("/api/auth/sms/request", json={"phone": phone})
        login = self.client.post("/api/auth/sms/login", json={"phone": phone, "code": "0426"})
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
