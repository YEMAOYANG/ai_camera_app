from __future__ import annotations

import unittest

from app import create_app
from tests.support import fresh_test_config, request_debug_code


class ProfileFamilySettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="disabled"))
        self.client = self.app.test_client()
        self.access_token = self._login("13800002026")
        self.child_id = self._create_child("小宇")
        self.device_id = self._create_device()

    def test_profile_summary_and_account_contract(self):
        summary = self.client.get("/api/profile/summary", headers=self._auth_headers())
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["spaceTitle"], "家庭看护空间")
        self.assertEqual(summary.json["summary"]["memberCount"], 1)
        self.assertEqual(summary.json["summary"]["deviceCount"], 1)
        self.assertNotIn("妈妈", summary.json["summary"]["familyName"])

        profile = self.client.patch(
            "/api/account/profile",
            json={
                "displayName": "家长甲",
                "familyName": "我的家庭空间",
                "relationship": "监护人",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["profile"]["displayName"], "家长甲")
        self.assertEqual(profile.json["profile"]["familyName"], "我的家庭空间")

        security = self.client.get("/api/account/security", headers=self._auth_headers())
        self.assertEqual(security.status_code, 200)
        self.assertEqual(security.json["security"]["loginMethod"], "sms")

    def test_family_members_crud_and_family_isolation(self):
        created = self.client.post(
            "/api/family/members",
            json={
                "name": "爸爸",
                "phone": "13900002026",
                "role": "guardian",
                "status": "active",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(created.status_code, 200)
        member = created.json["member"]
        self.assertEqual(member["name"], "爸爸")

        updated = self.client.patch(
            f"/api/family/members/{member['id']}",
            json={"role": "caregiver"},
            headers=self._auth_headers(),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["member"]["role"], "caregiver")

        other_token = self._login("13700002026")
        isolated = self.client.patch(
            f"/api/family/members/{member['id']}",
            json={"name": "越权修改"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(isolated.status_code, 404)

        deleted = self.client.delete(
            f"/api/family/members/{member['id']}",
            headers=self._auth_headers(),
        )
        self.assertEqual(deleted.status_code, 200)

    def test_family_invitations_create_resend_cancel_and_isolation(self):
        created = self.client.post(
            "/api/family/invitations",
            json={"name": "外婆", "phone": "13600002026", "role": "viewer"},
            headers=self._auth_headers(),
        )
        self.assertEqual(created.status_code, 200)
        invitation = created.json["invitation"]
        self.assertEqual(invitation["name"], "外婆")
        self.assertEqual(invitation["status"], "pending")
        self.assertEqual(invitation["role"], "viewer")

        listed = self.client.get("/api/family/invitations", headers=self._auth_headers())
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json["invitations"]), 1)

        resent = self.client.post(
            f"/api/family/invitations/{invitation['id']}/resend",
            headers=self._auth_headers(),
        )
        self.assertEqual(resent.status_code, 200)
        self.assertEqual(resent.json["invitation"]["status"], "pending")

        other_token = self._login("13700002026")
        isolated = self.client.post(
            f"/api/family/invitations/{invitation['id']}/cancel",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(isolated.status_code, 404)

        cancelled = self.client.post(
            f"/api/family/invitations/{invitation['id']}/cancel",
            headers=self._auth_headers(),
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json["invitation"]["status"], "cancelled")

        listed_after_cancel = self.client.get(
            "/api/family/invitations",
            headers=self._auth_headers(),
        )
        self.assertEqual(listed_after_cancel.status_code, 200)
        self.assertEqual(listed_after_cancel.json["invitations"], [])

    def test_child_profile_and_emergency_contacts_crud(self):
        child = self.client.patch(
            f"/api/children/{self.child_id}",
            json={
                "name": "小宇",
                "nickname": "小宇",
                "educationStage": "小学",
                "grade": "一年级",
                "schoolName": "示例小学",
                "interests": ["阅读", "搭积木"],
                "taskPreferences": {"pace": "gentle"},
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(child.status_code, 200)
        self.assertEqual(child.json["child"]["grade"], "一年级")
        self.assertEqual(child.json["child"]["interests"], ["阅读", "搭积木"])

        current = self.client.get("/api/children/current", headers=self._auth_headers())
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json["child"]["schoolName"], "示例小学")

        contact = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "外婆",
                "phone": "13600002026",
                "relationship": "家人",
                "defaultNotify": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(contact.status_code, 200)
        contact_id = contact.json["contact"]["id"]

        updated = self.client.patch(
            f"/api/contacts/emergency/{contact_id}",
            json={"defaultNotify": False},
            headers=self._auth_headers(),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json["contact"]["defaultNotify"])

        deleted = self.client.delete(
            f"/api/contacts/emergency/{contact_id}",
            headers=self._auth_headers(),
        )
        self.assertEqual(deleted.status_code, 200)

    def test_device_management_and_status(self):
        renamed = self.client.post(
            f"/api/devices/{self.device_id}/rename",
            json={"name": "书房设备"},
            headers=self._auth_headers(),
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json["device"]["name"], "书房设备")

        patched = self.client.patch(
            f"/api/devices/{self.device_id}",
            json={"location": "书房"},
            headers=self._auth_headers(),
        )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json["device"]["location"], "书房")

        status = self.client.get(
            f"/api/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertIn("connectionStatus", status.json["status"])

        unbound = self.client.post(
            f"/api/devices/{self.device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbound.status_code, 200)
        self.assertEqual(unbound.json["device"]["status"], "unbound")
        self.assertIsNotNone(unbound.json["device"]["unboundAt"])

    def test_settings_legal_about_subscription_reports_and_feedback(self):
        setting = self.client.get("/api/settings/ai-care-rules", headers=self._auth_headers())
        self.assertEqual(setting.status_code, 200)
        self.assertTrue(setting.json["setting"]["value"]["voiceReminderEnabled"])

        saved = self.client.patch(
            "/api/settings/ai-care-rules",
            json={"value": {"voiceReminderEnabled": False}},
            headers=self._auth_headers(),
        )
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json["setting"]["value"]["voiceReminderEnabled"])

        for path in (
            "/api/settings/notifications",
            "/api/settings/privacy",
            "/api/settings/conversation",
            "/api/settings/education",
        ):
            response = self.client.get(path, headers=self._auth_headers())
            self.assertEqual(response.status_code, 200)

        legal = self.client.get("/api/legal/child-privacy-authorization")
        self.assertEqual(legal.status_code, 200)
        self.assertEqual(legal.json["document"]["title"], "儿童隐私授权说明")

        about = self.client.get("/api/app/about")
        self.assertEqual(about.status_code, 200)
        self.assertEqual(about.json["about"]["appName"], "Mira Guardian")
        self.assertEqual(about.json["about"]["displayName"], "家庭看护")

        subscription = self.client.get("/api/subscription/status", headers=self._auth_headers())
        self.assertEqual(subscription.status_code, 200)
        self.assertEqual(subscription.json["subscription"]["status"], "active")

        plans = self.client.get("/api/subscriptions/plans", headers=self._auth_headers())
        self.assertEqual(plans.status_code, 200)
        self.assertEqual([plan["id"] for plan in plans.json["plans"]], ["basic", "member", "family_plus"])
        self.assertEqual(plans.json["plans"][1]["price"], "¥29")

        current = self.client.get("/api/subscriptions/current", headers=self._auth_headers())
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json["subscription"]["planId"], "basic")

        entitlements = self.client.get(
            "/api/subscriptions/entitlements",
            headers=self._auth_headers(),
        )
        self.assertEqual(entitlements.status_code, 200)
        self.assertTrue(entitlements.json["entitlements"][0]["basic"])

        checkout = self.client.post(
            "/api/subscriptions/checkout-session",
            json={"planId": "member"},
            headers=self._auth_headers(),
        )
        self.assertEqual(checkout.status_code, 200)
        self.assertEqual(checkout.json["checkout"]["status"], "pending_payment")
        self.assertTrue(checkout.json["checkout"]["receiptVerificationRequired"])

        restore = self.client.post("/api/subscriptions/restore", headers=self._auth_headers())
        self.assertEqual(restore.status_code, 200)
        self.assertEqual(restore.json["restore"]["status"], "no_purchase_record")

        daily = self.client.get("/api/reports/daily", headers=self._auth_headers())
        weekly = self.client.get("/api/reports/weekly", headers=self._auth_headers())
        self.assertEqual(daily.status_code, 200)
        self.assertEqual(weekly.status_code, 200)

        feedback = self.client.post(
            "/api/feedback",
            json={"category": "general", "content": "页面提示很清楚"},
            headers=self._auth_headers(),
        )
        self.assertEqual(feedback.status_code, 200)
        self.assertEqual(feedback.json["feedback"]["status"], "received")

    def test_reward_item_delete_archives_item(self):
        item = self.client.post(
            "/api/rewards/items",
            json={"childId": self.child_id, "title": "亲子阅读", "pointsCost": 10},
            headers=self._auth_headers(),
        )
        self.assertEqual(item.status_code, 200)
        item_id = item.json["item"]["id"]

        deleted = self.client.delete(
            f"/api/rewards/items/{item_id}",
            headers=self._auth_headers(),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json["item"]["status"], "archived")

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

    def _create_device(self) -> str:
        response = self.client.post(
            "/api/setup/device",
            json={
                "deviceName": "客厅设备",
                "location": "客厅书桌区",
                "bindingCode": "BIND-2026",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["device"]["id"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
