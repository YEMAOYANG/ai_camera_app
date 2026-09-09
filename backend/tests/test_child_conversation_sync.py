from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app import create_app
from core.database import Database
from core.security import now_ms
from repositories.device_repository import DeviceRepository
from services.conversation_sync_service import ConversationSyncService
from services.voice_runtime_store import VoiceRuntimeStore
from tests.support import fresh_test_config, request_debug_code


class ChildConversationSyncTest(unittest.TestCase):
    def setUp(self):
        push_patcher = patch.object(
            ConversationSyncService,
            "_push_profile_to_ai_camera_test",
            return_value=None,
        )
        self.push_profile = push_patcher.start()
        self.addCleanup(push_patcher.stop)
        self.app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="disabled"))
        self.client = self.app.test_client()

    def test_setup_child_without_device_keeps_conversation_sync_as_no_op(self):
        access_token, family_id = self._login("13800002201")
        self._save_parent_identity(access_token)

        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "陈小宇",
                "nickname": "豆豆",
                "ageStage": "kindergarten_middle",
            },
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(child.status_code, 200, child.json)
        self.assertEqual(child.json["child"]["nickname"], "豆豆")
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            runtime_count = conn.execute(
                "SELECT COUNT(*) AS count FROM device_runtime_configs WHERE family_id = ?",
                (family_id,),
            ).fetchone()
        self.assertEqual(runtime_count["count"], 0)
        self.push_profile.assert_not_called()

    def test_binding_device_without_runtime_keeps_mode_unconfigured_and_caches_nickname(self):
        access_token, family_id = self._login("13800002203")
        self._save_parent_identity(access_token)
        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "陈小宇",
                "nickname": "豆豆",
                "gradeCode": "primary_3",
                "schoolYearStartYear": 2026,
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200, child.json)
        self.push_profile.assert_not_called()

        device = self.client.post(
            "/api/devices",
            json={
                "bindingCode": "BIND-AFTER-LIGHTWEIGHT-SETUP",
                "name": "书房设备",
                "location": "书房",
            },
            headers=self._auth_headers(access_token),
        )

        self.assertEqual(device.status_code, 200, device.json)
        device_id = device.json["device"]["id"]
        self.assertIsNone(self._stored_runtime(family_id, device_id))
        self.assertEqual(
            VoiceRuntimeStore.get_profile(
                family_id=family_id,
                device_id=device_id,
            )["childNickname"],
            "豆豆",
        )
        self.push_profile.assert_not_called()

    def test_setup_and_profile_name_changes_refresh_camera_nickname_first(self):
        access_token, family_id = self._login("13800002202")
        self._save_parent_identity(access_token)
        device = self.client.post(
            "/api/setup/device",
            json={
                "bindingCode": "BIND-CHILD-CONVERSATION",
                "deviceName": "客厅设备",
                "location": "客厅",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(device.status_code, 200, device.json)
        device_id = device.json["device"]["id"]
        self._set_runtime_provider(family_id, device_id, "guardian_local")

        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "陈小宇",
                "nickname": "豆豆",
                "ageStage": "kindergarten_middle",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200, child.json)
        child_id = child.json["child"]["id"]
        self.assertEqual(
            self._stored_interaction_profile(family_id, device_id)["childNickname"],
            "豆豆",
        )
        self.assertEqual(self.push_profile.call_count, 1)
        self.assertEqual(
            self._stored_runtime(family_id, device_id)["provider"],
            "guardian_local",
        )

        self._set_runtime_provider(family_id, device_id, "ai_camera_test")

        renamed = self.client.patch(
            f"/api/children/{child_id}",
            json={"name": "陈小满"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(renamed.status_code, 200, renamed.json)
        self.assertEqual(
            self._stored_interaction_profile(family_id, device_id)["childNickname"],
            "豆豆",
        )
        self.assertEqual(self.push_profile.call_count, 2)
        self.assertEqual(
            self._stored_runtime(family_id, device_id)["provider"],
            "ai_camera_test",
        )

        nicknamed = self.client.patch(
            f"/api/children/{child_id}",
            json={"nickname": "果果"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(nicknamed.status_code, 200, nicknamed.json)
        self.assertEqual(
            self._stored_interaction_profile(family_id, device_id)["childNickname"],
            "果果",
        )
        self.assertEqual(self.push_profile.call_count, 3)

        unrelated = self.client.patch(
            f"/api/children/{child_id}",
            json={"sleepTime": "20:30"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(unrelated.status_code, 200, unrelated.json)
        self.assertEqual(self.push_profile.call_count, 3)

    def test_mock_and_disabled_runtime_providers_are_preserved_without_remote_push(self):
        access_token, family_id = self._login("13800002204")
        self._save_parent_identity(access_token)
        device = self.client.post(
            "/api/setup/device",
            json={
                "bindingCode": "BIND-PRESERVE-RUNTIME",
                "deviceName": "测试设备",
                "location": "书房",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(device.status_code, 200, device.json)
        device_id = device.json["device"]["id"]

        self._set_runtime_provider(family_id, device_id, "mock")
        child = self.client.post(
            "/api/setup/child",
            json={
                "name": "陈小宇",
                "nickname": "豆豆",
                "ageStage": "kindergarten_middle",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(child.status_code, 200, child.json)
        child_id = child.json["child"]["id"]
        self.assertEqual(self._stored_runtime(family_id, device_id)["provider"], "mock")
        self.assertEqual(
            self._stored_interaction_profile(family_id, device_id)["childNickname"],
            "豆豆",
        )

        self._set_runtime_provider(family_id, device_id, "disabled")
        renamed = self.client.patch(
            f"/api/children/{child_id}",
            json={"nickname": "果果"},
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(renamed.status_code, 200, renamed.json)
        self.assertEqual(
            self._stored_runtime(family_id, device_id)["provider"],
            "disabled",
        )
        self.assertEqual(
            self._stored_interaction_profile(family_id, device_id)["childNickname"],
            "果果",
        )
        self.push_profile.assert_not_called()

    def _login(self, phone: str) -> tuple[str, str]:
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        return login.json["tokens"]["accessToken"], login.json["family"]["id"]

    def _save_parent_identity(self, access_token: str) -> None:
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "爸爸",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(access_token),
        )
        self.assertEqual(parent.status_code, 200, parent.json)

    def _stored_interaction_profile(self, family_id: str, device_id: str) -> dict:
        runtime = self._stored_runtime(family_id, device_id)
        self.assertIsNotNone(runtime)
        config = json.loads(runtime["config_json"] or "{}")
        return config["interactionProfile"]

    def _stored_runtime(self, family_id: str, device_id: str):
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            runtime = conn.execute(
                """
                SELECT provider, config_json
                FROM device_runtime_configs
                WHERE family_id = ? AND device_id = ?
                """,
                (family_id, device_id),
            ).fetchone()
        return runtime

    def _set_runtime_provider(self, family_id: str, device_id: str, provider: str) -> None:
        repository = DeviceRepository(Database(self.app.config["DATABASE_URL"]))
        with repository.transaction() as conn:
            repository.upsert_device_runtime_config(
                conn,
                family_id=family_id,
                device_id=device_id,
                provider=provider,
                config_json=json.dumps(
                    {"baseUrl": "http://127.0.0.1:8767"},
                    ensure_ascii=False,
                ),
                secret_ref=None,
                status="active",
                now=now_ms(),
            )

    @staticmethod
    def _auth_headers(access_token: str) -> dict:
        return {"Authorization": f"Bearer {access_token}"}


if __name__ == "__main__":
    unittest.main()
