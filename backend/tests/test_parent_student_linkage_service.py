from __future__ import annotations

import copy
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from core.errors import ApiError
from services.student_auth_service import StudentAuthService


NOW = 1_777_000_000_000


class _ParentAuth:
    def authenticate(self, access_token: str) -> dict:
        if access_token != "parent_token":
            raise AssertionError("test passed an unexpected parent token")
        return {
            "family": {"id": "family_1"},
            "user": {
                "id": "user_1",
                "displayName": "妈妈",
                "phone": "13800000000",
            },
        }


class _ProfileRepository:
    def __init__(self):
        self.children = {
            ("family_1", "child_1"): {
                "id": "child_1",
                "family_id": "family_1",
            }
        }

    def get_child(self, conn, *, family_id: str, child_id: str):
        return self.children.get((family_id, child_id))

    def get_family_member_by_user(self, conn, *, family_id: str, user_id: str):
        return {"role": "admin"}

    def get_app_option_item(self, conn, *, catalog_key: str, item_key: str):
        return None


class _StudentRepository:
    def __init__(self):
        self.principal = {
            "id": "principal_1",
            "family_id": "family_1",
            "child_id": "child_1",
            "status": "active",
            "pin_hash": "old_hash",
            "pin_salt": "00" * 16,
            "pin_iterations": 2,
            "pin_updated_at": NOW - 20_000,
        }
        self.devices = {
            "device_1": {
                "id": "device_1",
                "principal_id": "principal_1",
                "family_id": "family_1",
                "child_id": "child_1",
                "device_label": "客厅学习平板",
                "device_type": "tablet",
                "platform": "android",
                "status": "trusted",
                "expires_at": NOW + 60_000,
                "last_active_at": NOW - 3_000,
                "created_at": NOW - 30_000,
                "updated_at": NOW - 3_000,
                "revoked_at": None,
                "device_token_hash": "must_not_leak",
            },
            "device_other_child": {
                "id": "device_other_child",
                "principal_id": "principal_2",
                "family_id": "family_1",
                "child_id": "child_2",
                "device_label": "不属于当前孩子",
                "device_type": "browser",
                "platform": "web",
                "status": "trusted",
                "expires_at": NOW + 60_000,
                "last_active_at": NOW,
                "created_at": NOW,
                "updated_at": NOW,
                "revoked_at": None,
            },
        }
        self.sessions = {
            "session_1": {
                "id": "session_1",
                "principal_id": "principal_1",
                "device_id": "device_1",
                "access_expires_at": NOW + 10_000,
                "refresh_expires_at": NOW + 50_000,
                "last_active_at": NOW - 3_000,
                "created_at": NOW - 10_000,
                "revoked_at": None,
                "access_hash": "must_not_leak",
                "refresh_hash": "must_not_leak",
            }
        }
        self.pairing_codes_revoked = False

    @contextmanager
    def transaction(self):
        yield object()

    def list_owned_authorizations(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
    ):
        rows = []
        for device in self.devices.values():
            if (
                device["family_id"] != family_id
                or device["child_id"] != child_id
                or device.get("revoked_at") is not None
            ):
                continue
            matching = [
                session
                for session in self.sessions.values()
                if session["device_id"] == device["id"]
                and session.get("revoked_at") is None
            ] or [None]
            for session in matching:
                row = copy.deepcopy(device)
                if session is not None:
                    row.update(
                        {
                            "session_id": session["id"],
                            "session_access_expires_at": session[
                                "access_expires_at"
                            ],
                            "session_refresh_expires_at": session[
                                "refresh_expires_at"
                            ],
                            "session_last_active_at": session[
                                "last_active_at"
                            ],
                            "session_created_at": session["created_at"],
                            "session_access_hash": session["access_hash"],
                            "session_refresh_hash": session["refresh_hash"],
                        }
                    )
                rows.append(row)
        return rows

    def get_owned_device_for_update(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
    ):
        device = self.devices.get(device_id)
        if (
            device is None
            or device["family_id"] != family_id
            or device["child_id"] != child_id
        ):
            return None
        return device

    def revoke_trusted_device(self, conn, *, device_id: str, revoked_at: int):
        device = self.devices[device_id]
        if device.get("revoked_at") is not None:
            return False
        device["status"] = "revoked"
        device["revoked_at"] = revoked_at
        device["updated_at"] = revoked_at
        return True

    def revoke_device_sessions(self, conn, *, device_id: str, revoked_at: int):
        count = 0
        for session in self.sessions.values():
            if session["device_id"] == device_id and session.get("revoked_at") is None:
                session["revoked_at"] = revoked_at
                count += 1
        return count

    def get_principal_for_child(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        for_update: bool = False,
    ):
        if (
            self.principal is not None
            and self.principal["family_id"] == family_id
            and self.principal["child_id"] == child_id
        ):
            return self.principal
        return None

    def update_principal_pin(
        self,
        conn,
        *,
        principal_id: str,
        pin_hash: str,
        pin_salt: str,
        pin_iterations: int,
        now: int,
    ):
        self.principal.update(
            {
                "pin_hash": pin_hash,
                "pin_salt": pin_salt,
                "pin_iterations": pin_iterations,
                "pin_updated_at": now,
                "updated_at": now,
                "status": "active",
            }
        )
        return self.principal

    def revoke_active_pairing_codes(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        revoked_at: int,
    ):
        self.pairing_codes_revoked = True

    def revoke_principal_sessions(
        self,
        conn,
        *,
        principal_id: str,
        revoked_at: int,
    ):
        count = 0
        for session in self.sessions.values():
            if (
                session["principal_id"] == principal_id
                and session.get("revoked_at") is None
            ):
                session["revoked_at"] = revoked_at
                count += 1
        return count

    def reset_principal_device_pin_failures(
        self,
        conn,
        *,
        principal_id: str,
        now: int,
    ):
        return sum(
            1
            for device in self.devices.values()
            if device["principal_id"] == principal_id
            and device.get("revoked_at") is None
        )


def _service(repository: _StudentRepository | None = None) -> StudentAuthService:
    service = object.__new__(StudentAuthService)
    service.parent_auth_service = _ParentAuth()
    service.profile_repository = _ProfileRepository()
    service.repository = repository or _StudentRepository()
    service.pepper = b"test-pepper"
    service.pin_pbkdf2_iterations = 2
    return service


def _contains_forbidden_key(value: object) -> bool:
    forbidden = {
        "pin",
        "pinhash",
        "pinsalt",
        "devicetokenhash",
        "accesshash",
        "refreshhash",
        "refreshtoken",
    }
    if isinstance(value, dict):
        return any(
            str(key).replace("_", "").lower() in forbidden
            or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


class ParentStudentLinkageServiceTest(unittest.TestCase):
    def test_list_authorizations_returns_only_owned_safe_device_and_session_metadata(self):
        repository = _StudentRepository()
        service = _service(repository)
        self.assertTrue(
            hasattr(service, "list_authorizations"),
            "parent authorization listing is not implemented",
        )

        with patch("services.student_auth_service.now_ms", return_value=NOW):
            payload = service.list_authorizations("parent_token", "child_1")

        self.assertEqual(payload["childId"], "child_1")
        self.assertEqual(len(payload["authorizations"]), 1)
        authorization = payload["authorizations"][0]
        self.assertEqual(authorization["id"], "device_1")
        self.assertEqual(authorization["displayName"], "客厅学习平板")
        self.assertEqual(authorization["status"], "active")
        self.assertEqual(authorization["lastUsedAt"], NOW - 3_000)
        self.assertEqual(authorization["createdAt"], NOW - 30_000)
        self.assertEqual(authorization["sessions"][0]["id"], "session_1")
        self.assertEqual(authorization["sessions"][0]["status"], "active")
        self.assertFalse(_contains_forbidden_key(payload))

    def test_revoke_authorization_is_owned_transactional_and_idempotent(self):
        repository = _StudentRepository()
        service = _service(repository)
        self.assertTrue(
            hasattr(service, "revoke_authorization"),
            "parent authorization revocation is not implemented",
        )

        with patch("services.student_auth_service.now_ms", return_value=NOW):
            first = service.revoke_authorization(
                "parent_token",
                "child_1",
                "device_1",
            )
            replay = service.revoke_authorization(
                "parent_token",
                "child_1",
                "device_1",
            )

        self.assertEqual(first["status"], "revoked")
        self.assertFalse(first["alreadyRevoked"])
        self.assertEqual(first["revokedSessionCount"], 1)
        self.assertTrue(replay["alreadyRevoked"])
        self.assertEqual(replay["revokedSessionCount"], 0)
        self.assertEqual(repository.sessions["session_1"]["revoked_at"], NOW)

        with self.assertRaises(ApiError) as caught:
            service.revoke_authorization(
                "parent_token",
                "child_1",
                "device_other_child",
            )
        self.assertEqual(caught.exception.code, "student_authorization_not_found")
        self.assertIsNone(repository.devices["device_other_child"]["revoked_at"])

    def test_reset_pin_invalidates_old_pin_and_sessions_but_preserves_devices(self):
        repository = _StudentRepository()
        service = _service(repository)
        self.assertTrue(
            hasattr(service, "reset_pin"),
            "parent PIN reset is not implemented",
        )
        old_pin = "1357"
        old_salt, old_hash = service._new_pin_hash(old_pin)
        repository.principal.update(
            {
                "pin_salt": old_salt,
                "pin_hash": old_hash,
                "pin_iterations": service.pin_pbkdf2_iterations,
            }
        )

        with patch("services.student_auth_service.now_ms", return_value=NOW):
            payload = service.reset_pin(
                "parent_token",
                "child_1",
                {"pin": "2468"},
            )

        self.assertFalse(service._verify_pin(old_pin, repository.principal))
        self.assertTrue(service._verify_pin("2468", repository.principal))
        self.assertEqual(repository.sessions["session_1"]["revoked_at"], NOW)
        self.assertEqual(repository.devices["device_1"]["status"], "trusted")
        self.assertTrue(repository.pairing_codes_revoked)
        self.assertEqual(payload["revokedSessionCount"], 1)
        self.assertEqual(payload["trustedDeviceCount"], 1)
        self.assertTrue(payload["existingDevicesRemainTrusted"])
        self.assertFalse(_contains_forbidden_key(payload))


if __name__ == "__main__":
    unittest.main()
