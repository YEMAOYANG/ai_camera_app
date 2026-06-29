from __future__ import annotations

import unittest

from app import create_app
from tests.support import fresh_test_config


class InternalVoiceBridgeApiTest(unittest.TestCase):
    def setUp(self):
        self.internal_token = "voice-bridge-token"
        self.app = create_app(
            fresh_test_config(
                CAMERA_RUNTIME_PROVIDER="ai_camera_test",
                AI_CAMERA_TEST_BASE_URL="http://127.0.0.1:8767",
                INTERNAL_API_TOKEN=self.internal_token,
            )
        )
        self.client = self.app.test_client()
        self.headers = {
            "Content-Type": "application/json",
            "X-Mira-Internal-Token": self.internal_token,
            "X-Mira-Internal-Source": "ai_camera_test",
        }
        self.family_id = self._bootstrap_family()

    def _bootstrap_family(self) -> str:
        from tests.support import request_debug_code

        phone = "13800002188"
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        token = login.json["tokens"]["accessToken"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        for step, payload in (
            ("/api/setup/parent-identity", {"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"}),
            ("/api/setup/device", {"bindingCode": "BIND-VOICE-BRIDGE", "deviceName": "测试摄像头", "location": "客厅"}),
            ("/api/setup/wifi", {"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"}),
            ("/api/setup/child", {"name": "小宇", "nickname": "小宇", "ageStage": "kindergarten_middle"}),
        ):
            response = self.client.post(step, json=payload, headers=auth_headers)
            self.assertEqual(response.status_code, 200, response.json)
        setup = self.client.post(
            "/api/setup/camera-name",
            json={"wakeName": "小暖"},
            headers=auth_headers,
        )
        self.assertEqual(setup.status_code, 200, setup.json)
        self.device_id = setup.json["cameraName"]["deviceId"]
        summary = self.client.get("/api/profile/summary", headers=auth_headers)
        return summary.json["summary"]["familyId"]

    def test_internal_profile_wake_and_chat(self):
        profile = self.client.get(
            f"/internal/voice/profile?familyId={self.family_id}&deviceId={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["interactionProfile"]["wakeName"], "小暖")

        wake = self.client.post(
            "/internal/voice/wake-evaluate",
            json={
                "familyId": self.family_id,
                "deviceId": self.device_id,
                "text": "小暖小暖",
                "requireConfirmation": True,
            },
            headers=self.headers,
        )
        self.assertEqual(wake.status_code, 200)
        self.assertTrue(wake.json["matched"])
        self.assertEqual(wake.json["ackText"], "小暖在听，你说吧。")

        rejected = self.client.post(
            "/internal/voice/wake-evaluate",
            json={
                "familyId": self.family_id,
                "deviceId": self.device_id,
                "text": "你好小暖",
                "requireConfirmation": True,
            },
            headers=self.headers,
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(rejected.json["matched"])

        chat = self.client.post(
            "/internal/voice/chat",
            json={
                "familyId": self.family_id,
                "deviceId": self.device_id,
                "text": "小暖你好，讲个故事",
            },
            headers=self.headers,
        )
        self.assertEqual(chat.status_code, 200)
        self.assertIn("reply", chat.json)


if __name__ == "__main__":
    unittest.main()
