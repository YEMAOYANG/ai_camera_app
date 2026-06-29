from __future__ import annotations

import unittest

from app import create_app
from core.database import Database
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

    def test_lightweight_setup_steps_save_and_complete_persists(self):
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
        self.assertEqual(parent.json["setup"]["nextStep"], "child")

        parent_status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent_status.status_code, 200)
        self.assertEqual(parent_status.json["parentIdentity"]["displayName"], "爸爸")
        self.assertEqual(parent_status.json["parentIdentity"]["relationship"], "爸爸")
        self.assertEqual(parent_status.json["parentIdentity"]["relationshipKey"], "dad")
        summary = self.client.get(
            "/api/profile/summary",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["role"], "admin")

        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "小宇",
                "nickname": "小宇",
                "gender": "unspecified",
                "ageStage": "幼儿园 中班",
                "educationStage": "幼儿园",
                "grade": "中班",
                "birthday": "2019-05-20",
                "sleepTime": "21:15",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)
        self.assertTrue(child.json["setup"]["completed"])
        self.assertEqual(child.json["setup"]["childProfile"], "done")
        self.assertEqual(child.json["child"]["name"], "小宇")
        self.assertEqual(child.json["child"]["gender"], "unspecified")
        self.assertEqual(child.json["child"]["birthday"], "2019-05-20")
        self.assertEqual(child.json["child"]["sleepTime"], "21:15")
        self.assertEqual(child.json["setup"]["nextStep"], "home")

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
        self.assertEqual(status.json["child"]["sleepTime"], "21:15")
        self.assertIsNone(status.json["device"])
        self.assertIsNone(status.json["cameraName"])
        self.assertEqual(status.json["setup"]["deviceBinding"], "pending")
        self.assertEqual(status.json["setup"]["contacts"], "pending")

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
        self.assertEqual(contacts.json["contacts"]["count"], 2)

    def test_parent_identity_can_save_family_role(self):
        access_token = self._login("13800002029")

        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
                "role": "guardian",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        self.assertEqual(parent.json["parentIdentity"]["role"], "guardian")
        self.assertEqual(parent.json["parentIdentity"]["roleLabel"], "监护人")

        status = self.client.get(
            "/api/setup/status",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["parentIdentity"]["role"], "guardian")

        summary = self.client.get(
            "/api/profile/summary",
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["role"], "guardian")

    def test_setup_device_endpoint_remains_available_after_setup(self):
        access_token = self._login("13800002027")
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "妈妈",
                "relationship": "妈妈",
                "relationshipKey": "mom",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200)
        child = self.client.post(
            "/api/setup/child",
            json={"name": "小星", "nickname": "小星", "ageStage": "幼儿园 小班"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)
        self.assertTrue(child.json["setup"]["completed"])

        device = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2027", "location": "儿童房"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(device.status_code, 200, device.json)
        self.assertEqual(device.json["device"]["status"], "bound")
        self.assertEqual(device.json["device"]["name"], "儿童房暖瞳摄像头")
        self.assertEqual(device.json["setup"]["nextStep"], "home")

        fallback = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2027-NO-ROOM"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(fallback.status_code, 409)

        other_token = self._login("13800002028")
        other_parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(other_token),
        )
        self.assertEqual(other_parent.status_code, 200)
        default_name = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-2028"},
            headers=self._auth_headers(other_token),
        )
        self.assertEqual(default_name.status_code, 200, default_name.json)
        self.assertEqual(default_name.json["device"]["name"], "暖瞳摄像头")

    def test_setup_contacts_allow_parent_identity_and_reject_contact_duplicates(self):
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

        early_contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "妈妈", "phone": "13900003025", "relationship": "mother"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(early_contacts.status_code, 409)
        self.assertEqual(early_contacts.json["error"], "setup_step_out_of_order")

        self._complete_setup_before_contacts(access_token)

        contacts = self.client.post(
            "/api/setup/contacts",
            json={
                "contacts": [
                    {"name": "妈妈", "phone": "13900003026", "relationship": "mother"},
                ]
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(contacts.status_code, 200)

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

    def test_camera_name_updates_default_device_in_multi_device_family(self):
        access_token = self._login("13800003029")
        headers = self._auth_headers(access_token)
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=headers,
        )
        self.assertEqual(parent.status_code, 200)
        first = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-CAMERA-NAME-1", "deviceName": "客厅设备", "location": "客厅"},
            headers=headers,
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/devices",
            json={
                "bindingCode": "BIND-CAMERA-NAME-2",
                "name": "儿童房设备",
                "location": "儿童房",
                "setAsDefault": True,
            },
            headers=headers,
        )
        self.assertEqual(second.status_code, 200, second.json)
        second_id = second.json["device"]["id"]
        wifi = self.client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=headers,
        )
        self.assertEqual(wifi.status_code, 200)
        child = self.client.post(
            "/api/setup/child",
            json={"name": "小宇", "nickname": "小宇", "ageStage": "kindergarten_middle"},
            headers=headers,
        )
        self.assertEqual(child.status_code, 200)

        camera_name = self.client.post(
            "/api/setup/camera-name",
            json={"wakeName": "小守"},
            headers=headers,
        )
        self.assertEqual(camera_name.status_code, 200, camera_name.json)
        self.assertEqual(camera_name.json["cameraName"]["deviceId"], second_id)

        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            rows = conn.execute(
                "SELECT id, wake_name FROM devices WHERE family_id = ? ORDER BY created_at",
                (self.family_id,),
            ).fetchall()
        wake_names = {row["id"]: row.get("wake_name") for row in rows}
        self.assertEqual(wake_names[first.json["device"]["id"]], "小暖")
        self.assertEqual(wake_names[second_id], "小守")

    def _login(self, phone: str = "13800002026") -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200)
        self.family_id = login.json["family"]["id"]
        return login.json["tokens"]["accessToken"]

    def _complete_setup_before_contacts(self, access_token: str) -> None:
        child = self.client.post(
            "/api/setup/child",
            json={"name": "小宇", "nickname": "小宇", "ageStage": "kindergarten_middle"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200)

    def _auth_headers(self, access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}


if __name__ == "__main__":
    unittest.main()
