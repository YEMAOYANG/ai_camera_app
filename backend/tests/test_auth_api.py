from __future__ import annotations

import unittest

from app import create_app
from tests.support import fresh_test_config, request_debug_code


class AuthApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config(AUTH_ACCESS_TOKEN_SECONDS=1))
        self.client = self.app.test_client()

    def test_sms_login_creates_family_and_session(self):
        sms = self.client.post("/api/auth/sms/request", json={"phone": "13800002026"})
        self.assertEqual(sms.status_code, 200)
        self.assertTrue(sms.json["codeSent"])
        self.assertEqual(sms.json["provider"], "development")
        self.assertEqual(sms.json["deliveryStatus"], "delivered")
        self.assertRegex(sms.json["debugCode"], r"^\d{6}$")

        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": sms.json["debugCode"]},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json["user"]["phone"], "13800002026")
        self.assertIn("accessToken", login.json["tokens"])
        self.assertIn("refreshToken", login.json["tokens"])

        session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {login.json['tokens']['accessToken']}"},
        )
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.json["family"]["id"], login.json["family"]["id"])

    def test_refresh_rotates_refresh_token(self):
        code = request_debug_code(self.client, "13800002026")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": code},
        )
        old_refresh = login.json["tokens"]["refreshToken"]

        refreshed = self.client.post("/api/auth/token/refresh", json={"refreshToken": old_refresh})
        self.assertEqual(refreshed.status_code, 200)
        self.assertNotEqual(old_refresh, refreshed.json["tokens"]["refreshToken"])

        stale = self.client.post("/api/auth/token/refresh", json={"refreshToken": old_refresh})
        self.assertEqual(stale.status_code, 401)

    def test_invalid_code_returns_clear_error(self):
        request_debug_code(self.client, "13800002026")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": "0000"},
        )
        self.assertEqual(login.status_code, 400)
        self.assertEqual(login.json["error"], "invalid_code")

    def test_logout_revokes_current_session(self):
        code = request_debug_code(self.client, "13800002026")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": code},
        )
        tokens = login.json["tokens"]

        logout = self.client.post(
            "/api/auth/logout",
            json={"refreshToken": tokens["refreshToken"]},
            headers={"Authorization": f"Bearer {tokens['accessToken']}"},
        )
        self.assertEqual(logout.status_code, 200)

        session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {tokens['accessToken']}"},
        )
        self.assertEqual(session.status_code, 401)


if __name__ == "__main__":
    unittest.main()
