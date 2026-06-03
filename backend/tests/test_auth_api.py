from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import create_app


class AuthApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "AUTH_DB_PATH": str(Path(self.tmp.name) / "auth.db"),
                "AUTH_ACCESS_TOKEN_SECONDS": 1,
                "AUTH_REFRESH_TOKEN_SECONDS": 3600,
                "AUTH_DEV_SMS_CODE": "0426",
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_sms_login_creates_family_and_session(self):
        sms = self.client.post("/api/auth/sms/request", json={"phone": "13800002026"})
        self.assertEqual(sms.status_code, 200)
        self.assertTrue(sms.json["codeSent"])
        self.assertEqual(sms.json["provider"], "mock")
        self.assertEqual(sms.json["deliveryStatus"], "delivered")

        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": "0426"},
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
        self.client.post("/api/auth/sms/request", json={"phone": "13800002026"})
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": "0426"},
        )
        old_refresh = login.json["tokens"]["refreshToken"]

        refreshed = self.client.post("/api/auth/token/refresh", json={"refreshToken": old_refresh})
        self.assertEqual(refreshed.status_code, 200)
        self.assertNotEqual(old_refresh, refreshed.json["tokens"]["refreshToken"])

        stale = self.client.post("/api/auth/token/refresh", json={"refreshToken": old_refresh})
        self.assertEqual(stale.status_code, 401)

    def test_invalid_code_returns_clear_error(self):
        self.client.post("/api/auth/sms/request", json={"phone": "13800002026"})
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": "0000"},
        )
        self.assertEqual(login.status_code, 400)
        self.assertEqual(login.json["error"], "invalid_code")

    def test_logout_revokes_current_session(self):
        self.client.post("/api/auth/sms/request", json={"phone": "13800002026"})
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": "0426"},
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
