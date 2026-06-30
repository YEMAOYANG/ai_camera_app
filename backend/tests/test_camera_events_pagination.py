from __future__ import annotations

import json
import unittest

from app import create_app
from core.database import Database
from core.security import now_ms
from tests.support import fresh_test_config, request_debug_code


class CameraEventsPaginationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config(HARDWARE_ADAPTER="mock"))
        self.client = self.app.test_client()
        code = request_debug_code(self.client, "13800004101")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800004101", "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        self.access_token = login.json["tokens"]["accessToken"]
        self.family_id = login.json["family"]["id"]
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=self._auth_headers(),
        )
        self.assertEqual(parent.status_code, 200, parent.json)
        device = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-PAGE-01", "deviceName": "客厅摄像头", "location": "客厅"},
            headers=self._auth_headers(),
        )
        self.assertEqual(device.status_code, 200, device.json)
        self.device_id = device.json["device"]["id"]

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def test_has_more_when_recent_rows_include_non_care_commands(self):
        database = Database(self.app.config["DATABASE_URL"])
        now = now_ms()
        with database.transaction() as conn:
            for index in range(30):
                created_at = now - (index + 1) * 1000
                conn.execute(
                    """
                    INSERT INTO camera_commands(
                      id, family_id, device_id, task_id, command_type, status, message,
                      request_payload, response_payload, created_at, updated_at, completed_at
                    )
                    VALUES (?, ?, ?, NULL, 'ptz_move', 'succeeded', '调整方向', '{}', '{}', ?, ?, ?)
                    """,
                    (
                        f"cmd_ptz_{index}",
                        self.family_id,
                        self.device_id,
                        created_at,
                        created_at,
                        created_at,
                    ),
                )
            for index in range(12):
                created_at = now - (index + 40) * 3_600_000
                payload = json.dumps(
                    {
                        "displayTitle": f"画面观察 {index}",
                        "displayMessage": f"测试分页记录 {index}",
                        "category": "camera_observation",
                        "observation": {
                            "hasPerson": True,
                            "isReliable": True,
                            "description": f"测试分页记录 {index}",
                        },
                    },
                    ensure_ascii=False,
                )
                conn.execute(
                    """
                    INSERT INTO camera_commands(
                      id, family_id, device_id, task_id, command_type, status, message,
                      request_payload, response_payload, created_at, updated_at, completed_at
                    )
                    VALUES (?, ?, ?, NULL, 'camera_observation', 'succeeded', ?, '{}', ?, ?, ?, ?)
                    """,
                    (
                        f"cmd_obs_{index}",
                        self.family_id,
                        self.device_id,
                        f"观察记录 {index}",
                        payload,
                        created_at,
                        created_at,
                        created_at,
                    ),
                )

        first = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id, "limit": 10, "offset": 0},
            headers=self._auth_headers(),
        )
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(len(first.json["events"]), 10, first.json)
        self.assertTrue(first.json["hasMore"], first.json)

        second = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id, "limit": 10, "offset": 10},
            headers=self._auth_headers(),
        )
        self.assertEqual(second.status_code, 200, second.json)
        self.assertEqual(len(second.json["events"]), 2, second.json)
        self.assertFalse(second.json["hasMore"], second.json)


if __name__ == "__main__":
    unittest.main()
