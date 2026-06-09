from __future__ import annotations

import unittest

from app import create_app
from tests.support import fresh_test_config, request_debug_code


class SetupApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config())
        self.client = self.app.test_client()

    def test_setup_status_initial_state(self):
        access_token = self._login()

        response = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["setup"]["completed"])
        self.assertEqual(response.json["setup"]["parentIdentity"], "pending")
        self.assertEqual(response.json["setup"]["deviceBinding"], "pending")
        self.assertEqual(response.json["setup"]["nextStep"], "parentIdentity")

    def test_setup_steps_save_and_complete_persists(self):
        access_token = self._login()

        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.json["setup"]["parentIdentity"], "done")
        self.assertEqual(parent.json["parentIdentity"]["displayName"], "爸爸")
        self.assertEqual(parent.json["parentIdentity"]["relationshipKey"], "dad")
        self.assertEqual(parent.json["setup"]["nextStep"], "device")

        parent_status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent_status.status_code, 200)
        self.assertEqual(parent_status.json["parentIdentity"]["displayName"], "爸爸")
        self.assertEqual(parent_status.json["parentIdentity"]["relationship"], "爸爸")
        self.assertEqual(parent_status.json["parentIdentity"]["relationshipKey"], "dad")

        device = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2026", "deviceName": "客厅设备", "location": "客厅"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(device.status_code, 200)
        self.assertEqual(device.json["setup"]["deviceBinding"], "done")
        self.assertEqual(device.json["device"]["status"], "bound")
        self.assertEqual(device.json["setup"]["nextStep"], "wifi")

        wifi = self.client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(wifi.status_code, 200)
        self.assertEqual(wifi.json["setup"]["wifi"], "done")
        self.assertTrue(wifi.json["wifi"]["passwordSet"])
        self.assertEqual(wifi.json["setup"]["nextStep"], "child")

        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "小宇",
                "nickname": "小宇",
                "gender": "unspecified",
                "ageStage": "primary",
                "educationStage": "小学",
                "grade": "一年级",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)
        self.assertEqual(child.json["setup"]["childProfile"], "done")
        self.assertEqual(child.json["child"]["name"], "小宇")
        self.assertEqual(child.json["child"]["gender"], "unspecified")
        self.assertEqual(child.json["setup"]["nextStep"], "cameraName")

        intro = self.client.post(
            "/api/setup/camera-name/intro",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(intro.status_code, 200)
        self.assertEqual(intro.json["setup"]["cameraNameIntro"], "done")
        self.assertEqual(intro.json["broadcast"]["status"], "offline")

        intro_again = self.client.post(
            "/api/setup/camera-name/intro",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(intro_again.status_code, 200)
        self.assertEqual(intro_again.json["broadcast"]["status"], "alreadyPlayed")

        preview = self.client.post(
            "/api/setup/camera-name/preview",
            json={"wakeName": "小豆"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json["broadcast"]["status"], "offline")

        camera_name = self.client.post(
            "/api/setup/camera-name",
            json={"wakeName": "小豆"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(camera_name.status_code, 200)
        self.assertEqual(camera_name.json["setup"]["cameraName"], "done")
        self.assertEqual(camera_name.json["cameraName"]["wakeName"], "小豆")
        self.assertEqual(camera_name.json["setup"]["nextStep"], "contacts")

        contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "妈妈", "phone": "13900002026", "relationship": "mother"},
                    {"name": "外婆", "phone": "13800002027", "relationship": "grandparent"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(contacts.status_code, 200)
        self.assertEqual(contacts.json["setup"]["contacts"], "done")
        self.assertEqual(contacts.json["contacts"]["count"], 2)
        self.assertEqual(contacts.json["setup"]["nextStep"], "complete")

        complete = self.client.post(
            "/api/setup/complete",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(complete.status_code, 200)
        self.assertTrue(complete.json["setup"]["completed"])
        self.assertEqual(complete.json["setup"]["nextStep"], "home")

        status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json["setup"]["completed"])
        self.assertEqual(status.json["setup"]["nextStep"], "home")

    def test_setup_contacts_reject_duplicate_unique_guardian_identity(self):
        access_token = self._login("13800003026")

        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)

        duplicate_parent = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "爸爸", "phone": "13900003026", "relationship": "father"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(duplicate_parent.status_code, 400)
        self.assertEqual(duplicate_parent.json["error"], "duplicate_guardian_identity")

        duplicate_contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "外婆", "phone": "13900003027", "relationshipKey": "maternal_grandma"},
                    {"name": "外婆", "phone": "13900003028", "relationship": "外婆"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(duplicate_contacts.status_code, 400)
        self.assertEqual(duplicate_contacts.json["error"], "duplicate_guardian_identity")

    def test_setup_complete_requires_all_steps(self):
        access_token = self._login()

        complete = self.client.post(
            "/api/setup/complete",
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(complete.status_code, 400)
        self.assertEqual(complete.json["error"], "setup_incomplete")

    def _login(self, phone: str = "13800002026") -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200)
        return login.json["tokens"]["accessToken"]

    def _auth_headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}


if __name__ == "__main__":
    unittest.main()
