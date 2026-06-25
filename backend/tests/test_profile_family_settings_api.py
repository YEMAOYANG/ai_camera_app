from __future__ import annotations

import unittest
from datetime import date

from app import create_app
from core.database import Database
from core.security import hash_value
from tests.support import fresh_test_config, request_debug_code


class ProfileFamilySettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="disabled"))
        self.client = self.app.test_client()
        self.access_token = self._login("13800002026")
        self._save_parent_identity()
        self.device_id = self._create_device()
        self._save_wifi()
        self.child_id = self._create_child("小宇")

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
                "displayName": "爸爸",
                "familyName": "我的家庭空间",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["profile"]["displayName"], "爸爸")
        self.assertEqual(profile.json["profile"]["familyName"], "我的家庭空间")
        self.assertEqual(profile.json["profile"]["relationship"], "爸爸")
        self.assertEqual(profile.json["profile"]["relationshipKey"], "dad")

        updated_summary = self.client.get("/api/profile/summary", headers=self._auth_headers())
        self.assertEqual(updated_summary.status_code, 200)
        self.assertEqual(updated_summary.json["summary"]["displayName"], "爸爸")
        self.assertEqual(updated_summary.json["summary"]["relationshipKey"], "dad")

        account = self.client.get("/api/account/profile", headers=self._auth_headers())
        self.assertEqual(account.status_code, 200)
        self.assertEqual(account.json["profile"]["displayName"], "爸爸")
        self.assertEqual(account.json["profile"]["relationship"], "爸爸")
        self.assertEqual(account.json["profile"]["relationshipKey"], "dad")

        security = self.client.get("/api/account/security", headers=self._auth_headers())
        self.assertEqual(security.status_code, 200)
        self.assertEqual(security.json["security"]["loginMethod"], "sms")
        self.assertEqual(
            security.json["security"]["loginDevices"][0]["label"],
            "其他登录设备",
        )
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET device_label = '已登录设备',
                    device_type = 'unknown',
                    device_model = '',
                    device_hardware = '',
                    platform = 'unknown'
                WHERE access_hash = ?
                """,
                (hash_value(self.access_token),),
            )
        legacy_security = self.client.get("/api/account/security", headers=self._auth_headers())
        self.assertEqual(legacy_security.status_code, 200)
        self.assertEqual(
            legacy_security.json["security"]["loginDevices"][0]["label"],
            "其他登录设备",
        )

        phone_code = self.client.post(
            "/api/account/phone/code",
            json={"phone": "13900002026"},
            headers=self._auth_headers(),
        )
        self.assertEqual(phone_code.status_code, 200)
        self.assertRegex(phone_code.json["debugCode"], r"^\d{6}$")

        changed_phone = self.client.patch(
            "/api/account/phone",
            json={"phone": "13900002026", "code": phone_code.json["debugCode"]},
            headers=self._auth_headers(),
        )
        self.assertEqual(changed_phone.status_code, 200)
        self.assertEqual(changed_phone.json["profile"]["phone"], "13900002026")
        self.assertEqual(changed_phone.json["security"]["phone"], "13900002026")

        members_after_phone = self.client.get(
            "/api/family/members",
            headers=self._auth_headers(),
        )
        self.assertEqual(members_after_phone.status_code, 200)
        self.assertEqual(members_after_phone.json["members"][0]["phone"], "13900002026")

    def test_guardian_identity_options_are_served_by_backend(self):
        response = self.client.get(
            "/api/profile/guardian-identity-options",
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        options = response.json["options"]

        groups = {item["key"]: item for item in options["identityGroups"]}
        self.assertEqual(groups["parent"]["label"], "父母")
        self.assertEqual(groups["parent"]["defaultLabel"], "妈妈")
        self.assertEqual(
            [item["label"] for item in groups["parent"]["labels"]],
            ["妈妈", "爸爸"],
        )
        self.assertEqual(groups["parent"]["labels"][0]["imageAsset"], "assets/images/guardian/guardian_mom.png")
        grandparent_assets = {
            item["label"]: item["imageAsset"]
            for item in groups["grandparent"]["labels"]
        }
        self.assertEqual(
            grandparent_assets["外公"],
            "assets/images/guardian/guardian_maternal_grandpa.png",
        )
        self.assertEqual(
            grandparent_assets["爷爷"],
            "assets/images/guardian/guardian_grandpa.png",
        )
        family_assets = {
            item["label"]: item["imageAsset"]
            for item in groups["family"]["labels"]
        }
        self.assertEqual(
            family_assets["叔叔"],
            "assets/images/guardian/guardian_uncle.png",
        )
        self.assertEqual(
            family_assets["舅舅"],
            "assets/images/guardian/guardian_maternal_uncle.png",
        )

        roles = {item["key"]: item["label"] for item in options["familyRoles"]}
        self.assertEqual(roles["admin"], "管理员")
        self.assertEqual(roles["guardian"], "监护人")
        self.assertEqual(roles["viewer"], "临时查看者")

    def test_account_security_devices_revoke_and_deletion_request(self):
        phone = "13800002126"
        code = request_debug_code(self.client, phone)
        mobile_login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
            headers={
                "X-Mira-Device-Label": "iPhone 17 Pro Max",
                "X-Mira-Device-Type": "phone",
                "X-Mira-Device-Platform": "ios",
                "X-Mira-Device-Model": "iPhone",
                "X-Mira-Device-Hardware": "iPhone18,2",
                "X-Mira-OS-Version": "iOS 26.1",
                "X-Mira-App-Version": "1.0.0+1",
            },
        )
        self.assertEqual(mobile_login.status_code, 200)
        first_mobile_access = mobile_login.json["tokens"]["accessToken"]

        code = request_debug_code(self.client, phone)
        repeated_mobile_login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
            headers={
                "X-Mira-Device-Label": "iPhone 17 Pro Max",
                "X-Mira-Device-Type": "phone",
                "X-Mira-Device-Platform": "ios",
                "X-Mira-Device-Model": "iPhone",
                "X-Mira-Device-Hardware": "iPhone18,2",
                "X-Mira-OS-Version": "iOS 26.1",
                "X-Mira-App-Version": "1.0.0+1",
            },
        )
        self.assertEqual(repeated_mobile_login.status_code, 200)
        mobile_access = repeated_mobile_login.json["tokens"]["accessToken"]

        old_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {first_mobile_access}"},
        )
        self.assertEqual(old_session.status_code, 401)

        code = request_debug_code(self.client, phone)
        browser_login = self.client.post(
            "/api/auth/sms/login",
            json={
                "phone": phone,
                "code": code,
                "clientDevice": {
                    "label": "MacBook Safari",
                    "type": "browser",
                    "platform": "macos",
                },
            },
        )
        self.assertEqual(browser_login.status_code, 200)
        browser_access = browser_login.json["tokens"]["accessToken"]

        security = self.client.get(
            "/api/account/security",
            headers={"Authorization": f"Bearer {mobile_access}"},
        )
        self.assertEqual(security.status_code, 200)
        devices = security.json["security"]["loginDevices"]
        self.assertEqual(len(devices), 2)
        current = next(item for item in devices if item["current"])
        removable = next(item for item in devices if not item["current"])
        self.assertEqual(current["label"], "iPhone 17 Pro Max")
        self.assertEqual(current["hardware"], "iPhone18,2")
        self.assertEqual(current["osVersion"], "iOS 26.1")
        self.assertEqual(current["appVersion"], "1.0.0+1")
        self.assertEqual(removable["label"], "MacBook Safari")

        current_revoke = self.client.post(
            f"/api/account/sessions/{current['id']}/revoke",
            headers={"Authorization": f"Bearer {mobile_access}"},
        )
        self.assertEqual(current_revoke.status_code, 400)
        self.assertEqual(current_revoke.json["error"], "cannot_revoke_current_session")

        published_revocations = []
        from services import task_event_stream

        original_publish_revocation = task_event_stream.publish_account_session_revoked
        task_event_stream.publish_account_session_revoked = (
            lambda *, session_id, **_: published_revocations.append(session_id)
        )
        try:
            removed = self.client.post(
                f"/api/account/sessions/{removable['id']}/revoke",
                headers={"Authorization": f"Bearer {mobile_access}"},
            )
        finally:
            task_event_stream.publish_account_session_revoked = original_publish_revocation
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(published_revocations, [removable["id"]])
        remaining_labels = [
            item["label"] for item in removed.json["security"]["loginDevices"]
        ]
        self.assertEqual(remaining_labels, ["iPhone 17 Pro Max"])

        revoked_session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {browser_access}"},
        )
        self.assertEqual(revoked_session.status_code, 401)

        deletion = self.client.post(
            "/api/account/deletion",
            json={"reason": "user_requested"},
            headers={"Authorization": f"Bearer {mobile_access}"},
        )
        self.assertEqual(deletion.status_code, 200)
        self.assertEqual(deletion.json["accountStatus"], "deletion_requested")
        self.assertEqual(deletion.json["deletionRequest"]["status"], "requested")

        session = self.client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {mobile_access}"},
        )
        self.assertEqual(session.status_code, 401)

        code = request_debug_code(self.client, phone)
        relogin = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(relogin.status_code, 403)
        self.assertEqual(relogin.json["error"], "account_inactive")

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
            json={"role": "viewer"},
            headers=self._auth_headers(),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["member"]["role"], "viewer")

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

    def test_family_admin_permissions_and_transfer(self):
        created = self.client.post(
            "/api/family/members",
            json={
                "name": "爸爸",
                "phone": "13600002126",
                "role": "guardian",
                "status": "active",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(created.status_code, 200)
        target = created.json["member"]
        target_access = self._attach_user_to_member("13600002126", target["id"])

        denied_create = self.client.post(
            "/api/family/members",
            json={"name": "外公", "phone": "13500002126", "role": "guardian"},
            headers={"Authorization": f"Bearer {target_access}"},
        )
        self.assertEqual(denied_create.status_code, 403)
        self.assertEqual(denied_create.json["error"], "permission_denied")

        denied_device = self.client.post(
            f"/api/devices/{self.device_id}/rename",
            json={"name": "非管理员改名"},
            headers={"Authorization": f"Bearer {target_access}"},
        )
        self.assertEqual(denied_device.status_code, 403)
        self.assertEqual(denied_device.json["error"], "permission_denied")

        deletion_blocked = self.client.post(
            "/api/account/deletion",
            json={"reason": "user_requested"},
            headers=self._auth_headers(),
        )
        self.assertEqual(deletion_blocked.status_code, 409)
        self.assertEqual(deletion_blocked.json["error"], "admin_transfer_required")

        transferred = self.client.post(
            f"/api/family/members/{target['id']}/transfer-admin",
            headers=self._auth_headers(),
        )
        self.assertEqual(transferred.status_code, 200)
        roles = {member["id"]: member["role"] for member in transferred.json["members"]}
        self.assertEqual(roles[target["id"]], "admin")

        old_profile = self.client.get("/api/account/profile", headers=self._auth_headers())
        self.assertEqual(old_profile.status_code, 200)
        self.assertEqual(old_profile.json["profile"]["role"], "guardian")

        old_admin_denied = self.client.post(
            "/api/family/members",
            json={"name": "外婆", "phone": "13500002127", "role": "guardian"},
            headers=self._auth_headers(),
        )
        self.assertEqual(old_admin_denied.status_code, 403)
        self.assertEqual(old_admin_denied.json["error"], "permission_denied")

        renamed = self.client.post(
            f"/api/devices/{self.device_id}/rename",
            json={"name": "管理员设备"},
            headers={"Authorization": f"Bearer {target_access}"},
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json["device"]["name"], "管理员设备")

    def test_family_invitations_create_resend_cancel_and_isolation(self):
        created = self.client.post(
            "/api/family/invitations",
            json={
                "name": "外婆",
                "relationshipKey": "maternal_grandma",
                "phone": "13600002026",
                "role": "viewer",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(created.status_code, 200)
        invitation = created.json["invitation"]
        self.assertEqual(invitation["name"], "外婆")
        self.assertEqual(invitation["relationshipKey"], "maternal_grandma")
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

    def test_pending_invitation_can_be_accepted_after_login(self):
        owner_profile = self.client.patch(
            "/api/account/profile",
            json={
                "displayName": "爸爸",
                "familyName": "我的家庭空间",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(owner_profile.status_code, 200)

        created = self.client.post(
            "/api/family/invitations",
            json={
                "name": "妈妈",
                "relationshipKey": "mom",
                "phone": "13600002226",
                "role": "guardian",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(created.status_code, 200)
        invitation = created.json["invitation"]
        self.assertEqual(invitation["name"], "妈妈")
        self.assertEqual(invitation["relationshipKey"], "mom")
        self.assertEqual(created.json["deliveryStatus"], "not_configured")
        self.assertIn("短信邀请暂未接入", created.json["deliveryNotice"])

        code = request_debug_code(self.client, "13600002226")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13600002226", "code": code},
        )
        self.assertEqual(login.status_code, 200)
        pending = login.json["pendingJoins"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], invitation["id"])
        self.assertEqual(pending[0]["name"], "妈妈")
        self.assertEqual(pending[0]["relationshipKey"], "mom")
        self.assertEqual(pending[0]["role"], "guardian")
        invited_user_id = login.json["user"]["id"]
        invited_access = login.json["tokens"]["accessToken"]

        accepted = self.client.post(
            f"/api/family/invitations/{invitation['id']}/accept",
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json["member"]["name"], "妈妈")
        self.assertEqual(accepted.json["member"]["relationshipKey"], "mom")
        self.assertEqual(accepted.json["member"]["role"], "guardian")
        self.assertEqual(accepted.json["invitation"]["status"], "accepted")

        profile = self.client.get(
            "/api/account/profile",
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json["profile"]["displayName"], "妈妈")
        self.assertEqual(profile.json["profile"]["relationship"], "妈妈")
        self.assertEqual(profile.json["profile"]["relationshipKey"], "mom")
        self.assertEqual(profile.json["profile"]["role"], "guardian")
        capabilities = profile.json["profile"]["capabilities"]
        self.assertIn("manage_child_profile", capabilities)
        self.assertIn("manage_child_settings", capabilities)
        self.assertIn("manage_emergency_contacts", capabilities)
        self.assertIn("manage_tasks", capabilities)
        self.assertIn("confirm_tasks", capabilities)
        self.assertIn("manage_rewards", capabilities)
        self.assertNotIn("manage_family_members", capabilities)
        self.assertNotIn("manage_devices", capabilities)
        self.assertNotIn("manage_subscription", capabilities)

        summary = self.client.get(
            "/api/profile/summary",
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["displayName"], "妈妈")
        self.assertEqual(summary.json["summary"]["relationship"], "妈妈")
        self.assertEqual(summary.json["summary"]["relationshipKey"], "mom")

        members = self.client.get(
            "/api/family/members",
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(members.status_code, 200)
        invited_member = next(
            member
            for member in members.json["members"]
            if member["userId"] == invited_user_id
        )
        self.assertEqual(invited_member["name"], "妈妈")
        self.assertEqual(invited_member["relationshipKey"], "mom")
        self.assertEqual(invited_member["phone"], "13600002226")
        self.assertEqual(invited_member["role"], "guardian")

        owner_invitations = self.client.get(
            "/api/family/invitations",
            headers=self._auth_headers(),
        )
        self.assertEqual(owner_invitations.status_code, 200)
        self.assertEqual(owner_invitations.json["invitations"], [])

        invited_invitations = self.client.get(
            "/api/family/invitations",
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(invited_invitations.status_code, 200)
        self.assertEqual(invited_invitations.json["invitations"], [])

        denied = self.client.post(
            "/api/family/members",
            json={"name": "奶奶", "phone": "13600002227", "role": "guardian"},
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json["error"], "permission_denied")

        denied_device = self.client.post(
            f"/api/devices/{self.device_id}/rename",
            json={"name": "监护人改设备名"},
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(denied_device.status_code, 403)
        self.assertEqual(denied_device.json["error"], "permission_denied")

        child = self.client.patch(
            f"/api/children/{self.child_id}",
            json={"name": "小宇", "educationStage": "幼儿园", "grade": "中班"},
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(child.status_code, 200)
        self.assertEqual(child.json["child"]["name"], "小宇")

        contact = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "李老师",
                "phone": "13600002228",
                "relationship": "其他家人",
                "relationshipKey": "family_default",
                "defaultNotify": True,
            },
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(contact.status_code, 200)
        self.assertEqual(contact.json["contact"]["name"], "李老师")

        task = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": "整理书包",
                "type": "learning",
                "rewardPoints": 2,
                "scheduledDate": "2026-06-05",
                "scheduledStart": "19:00",
                "scheduledEnd": "19:20",
            },
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(task.status_code, 200)
        self.assertEqual(task.json["task"]["title"], "整理书包")

        reward = self.client.post(
            "/api/rewards/items",
            json={
                "childId": self.child_id,
                "title": "贴纸奖励",
                "pointsCost": 8,
            },
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(reward.status_code, 200)
        self.assertEqual(reward.json["item"]["title"], "贴纸奖励")

        child_setting = self.client.patch(
            "/api/settings/ai-care-rules",
            json={"value": {"voiceReminderEnabled": False}},
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(child_setting.status_code, 200)
        self.assertFalse(
            child_setting.json["setting"]["value"]["voiceReminderEnabled"],
        )

        privacy_denied = self.client.patch(
            "/api/settings/privacy",
            json={"value": {"childPrivacyAuthorized": True}},
            headers={"Authorization": f"Bearer {invited_access}"},
        )
        self.assertEqual(privacy_denied.status_code, 403)
        self.assertEqual(privacy_denied.json["error"], "permission_denied")

    def test_family_code_preview_accept_and_viewer_permissions(self):
        self._mark_setup_completed()

        code_response = self.client.get("/api/family/code", headers=self._auth_headers())
        self.assertEqual(code_response.status_code, 200)
        family_code = code_response.json["familyCode"]["code"]
        self.assertRegex(family_code, r"^[A-Z0-9]{6,16}$")

        guest_access = self._login("13600002326")
        preview = self.client.post(
            "/api/family/join-code/preview",
            json={"familyCode": family_code.lower()},
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json["preview"]["role"], "viewer")
        self.assertEqual(preview.json["preview"]["roleLabel"], "临时查看者")

        accepted = self.client.post(
            "/api/family/join-code/accept",
            json={"familyCode": family_code},
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json["member"]["role"], "viewer")

        status = self.client.get(
            "/api/setup/status",
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json["setup"]["completed"])

        guest_code = self.client.get(
            "/api/family/code",
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(guest_code.status_code, 200)
        self.assertEqual(guest_code.json["familyCode"]["code"], family_code)

        guest_reset = self.client.post(
            "/api/family/code/reset",
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(guest_reset.status_code, 403)
        self.assertEqual(guest_reset.json["error"], "permission_denied")

        denied = self.client.post(
            f"/api/devices/{self.device_id}/rename",
            json={"name": "访客改名"},
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json["error"], "permission_denied")

        second_family_access = self._login("13600002327")
        self._mark_setup_completed(second_family_access)
        second_code = self.client.get(
            "/api/family/code",
            headers={"Authorization": f"Bearer {second_family_access}"},
        )
        self.assertEqual(second_code.status_code, 200)
        blocked_switch = self.client.post(
            "/api/family/join-code/preview",
            json={"familyCode": second_code.json["familyCode"]["code"]},
            headers={"Authorization": f"Bearer {guest_access}"},
        )
        self.assertEqual(blocked_switch.status_code, 400)
        self.assertEqual(blocked_switch.json["error"], "family_switch_not_supported")

    def test_unique_guardian_identity_and_admin_role_are_enforced(self):
        self.client.get("/api/family/members", headers=self._auth_headers())

        duplicate_admin_member = self.client.post(
            "/api/family/members",
            json={
                "name": "外公",
                "phone": "13500002026",
                "role": "admin",
                "status": "active",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(duplicate_admin_member.status_code, 400)
        self.assertEqual(duplicate_admin_member.json["error"], "duplicate_family_admin")

        duplicate_admin_invitation = self.client.post(
            "/api/family/invitations",
            json={"name": "外婆", "phone": "13600002026", "role": "admin"},
            headers=self._auth_headers(),
        )
        self.assertEqual(duplicate_admin_invitation.status_code, 400)
        self.assertEqual(
            duplicate_admin_invitation.json["error"],
            "duplicate_family_admin",
        )

        profile = self.client.patch(
            "/api/account/profile",
            json={
                "displayName": "爸爸",
                "familyName": "我的家庭空间",
                "relationship": "爸爸",
                "relationshipKey": "dad",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(profile.status_code, 200)

        parent_contact = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "爸爸",
                "phone": "13700002026",
                "relationship": "爸爸",
                "relationshipKey": "dad",
                "defaultNotify": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(parent_contact.status_code, 200)

        duplicate_parent_contact = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "爸爸",
                "phone": "13700002029",
                "relationship": "爸爸",
                "relationshipKey": "dad",
                "defaultNotify": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(duplicate_parent_contact.status_code, 400)
        self.assertEqual(duplicate_parent_contact.json["error"], "duplicate_guardian_identity")

        grandma_contact = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "外婆",
                "phone": "13800002027",
                "relationship": "外婆",
                "relationshipKey": "maternal_grandma",
                "defaultNotify": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(grandma_contact.status_code, 200)

        grandma_invitation = self.client.post(
            "/api/family/invitations",
            json={
                "name": "外婆",
                "phone": "13900002027",
                "role": "guardian",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(grandma_invitation.status_code, 200)

        duplicate_grandma_invitation = self.client.post(
            "/api/family/invitations",
            json={
                "name": "外婆",
                "phone": "13900002030",
                "role": "guardian",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(duplicate_grandma_invitation.status_code, 400)
        self.assertEqual(
            duplicate_grandma_invitation.json["error"],
            "duplicate_guardian_identity",
        )

        repeated_family_default = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "李老师",
                "phone": "13900002028",
                "relationship": "其他家人",
                "relationshipKey": "family_default",
                "defaultNotify": False,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(repeated_family_default.status_code, 200)

    def test_child_profile_and_emergency_contacts_crud(self):
        child = self.client.patch(
            f"/api/children/{self.child_id}",
            json={
                "name": "小宇",
                "nickname": "小宇",
                "educationStage": "小学",
                "grade": "一年级",
                "sleepTime": "20:45",
                "schoolName": "示例小学",
                "interests": ["阅读", "搭积木"],
                "taskPreferences": {"pace": "gentle"},
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(child.status_code, 200)
        self.assertEqual(child.json["child"]["grade"], "一年级")
        self.assertEqual(child.json["child"]["sleepTime"], "20:45")
        self.assertEqual(child.json["child"]["interests"], ["阅读", "搭积木"])

        current = self.client.get("/api/children/current", headers=self._auth_headers())
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json["child"]["schoolName"], "示例小学")
        self.assertEqual(current.json["child"]["sleepTime"], "20:45")

        contact = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "外婆",
                "phone": "13600002026",
                "relationship": "外婆",
                "relationshipKey": "maternal_grandma",
                "defaultNotify": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(contact.status_code, 200)
        contact_id = contact.json["contact"]["id"]
        self.assertEqual(contact.json["contact"]["relationship"], "外婆")
        self.assertEqual(
            contact.json["contact"]["relationshipKey"],
            "maternal_grandma",
        )

        listed = self.client.get(
            "/api/contacts/emergency",
            headers=self._auth_headers(),
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json["contacts"][0]["relationship"], "外婆")
        self.assertEqual(
            listed.json["contacts"][0]["relationshipKey"],
            "maternal_grandma",
        )

        updated = self.client.patch(
            f"/api/contacts/emergency/{contact_id}",
            json={
                "phone": "+86 136 0000 2026",
                "relationshipKey": "family_default",
                "defaultNotify": False,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json["contact"]["defaultNotify"])
        self.assertEqual(updated.json["contact"]["phone"], "13600002026")
        self.assertEqual(updated.json["contact"]["relationship"], "其他家人")
        self.assertEqual(updated.json["contact"]["relationshipKey"], "family_default")

        legacy = self.client.post(
            "/api/contacts/emergency",
            json={
                "name": "李老师",
                "phone": "13700002026",
                "relationship": "guardian",
                "defaultNotify": True,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.json["contact"]["relationship"], "其他家人")
        self.assertEqual(legacy.json["contact"]["relationshipKey"], "family_default")

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

        devices = self.client.get("/api/devices", headers=self._auth_headers())
        self.assertEqual(devices.status_code, 200)
        self.assertEqual(devices.json["devices"], [])

        summary = self.client.get("/api/profile/summary", headers=self._auth_headers())
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json["summary"]["deviceCount"], 0)

    def test_settings_legal_about_subscription_reports_and_feedback(self):
        setting = self.client.get("/api/settings/ai-care-rules", headers=self._auth_headers())
        self.assertEqual(setting.status_code, 200)
        self.assertTrue(setting.json["setting"]["value"]["voiceReminderEnabled"])
        self.assertNotIn(
            "safetyEventObservationEnabled",
            setting.json["setting"]["value"],
        )

        saved = self.client.patch(
            "/api/settings/ai-care-rules",
            json={"value": {"voiceReminderEnabled": False}},
            headers=self._auth_headers(),
        )
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json["setting"]["value"]["voiceReminderEnabled"])

        notifications = self.client.get(
            "/api/settings/notifications",
            headers=self._auth_headers(),
        )
        self.assertEqual(notifications.status_code, 200)
        self.assertNotIn("safetyAlert", notifications.json["setting"]["value"])

        conversation = self.client.patch(
            "/api/settings/conversation",
            json={
                "value": {
                    "boundaryLevel": "strict",
                    "wakeName": "豆豆",
                    "freeChatSingleMinutes": 6,
                    "freeChatDailyMinutes": 20,
                }
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(conversation.status_code, 200)
        self.assertEqual(
            conversation.json["setting"]["value"]["boundaryLevel"],
            "strict",
        )
        self.assertEqual(conversation.json["setting"]["value"]["wakeName"], "豆豆")
        self.assertEqual(
            conversation.json["setting"]["value"]["freeChatSingleMinutes"],
            6,
        )
        self.assertEqual(
            conversation.json["setting"]["value"]["freeChatDailyMinutes"],
            20,
        )
        device = self.client.get(
            f"/api/devices/{self.device_id}",
            headers=self._auth_headers(),
        )
        self.assertEqual(device.status_code, 200)
        self.assertEqual(device.json["device"]["wakeName"], "豆豆")

        for path in (
            "/api/settings/privacy",
            "/api/settings/education",
        ):
            response = self.client.get(path, headers=self._auth_headers())
            self.assertEqual(response.status_code, 200)

        legal = self.client.get("/api/legal/child-privacy-authorization")
        self.assertEqual(legal.status_code, 200)
        self.assertEqual(legal.json["document"]["title"], "儿童隐私授权说明")

        about = self.client.get("/api/app/about")
        self.assertEqual(about.status_code, 200)
        self.assertEqual(about.json["about"]["appName"], "家庭 AI 看护 App")
        self.assertEqual(about.json["about"]["displayName"], "家庭 AI 看护 App")

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

    def test_reports_include_growth_sections_and_camera_observations(self):
        today = date.today().isoformat()
        toy_task = self._create_task(
            title="玩具收纳",
            task_type="housework",
            scheduled_date=today,
            reward_points=3,
            requires_parent_confirmation=False,
        )
        water_task = self._create_task(
            title="喝水",
            task_type="life",
            scheduled_date=today,
            reward_points=1,
            requires_parent_confirmation=True,
        )

        completed = self.client.post(
            f"/api/tasks/{toy_task}/complete",
            json={
                "completionSource": "camera_ai",
                "evidenceSummary": "摄像头看到玩具已经放回收纳盒。",
                "aiObservationSummary": "小宇主动把积木放回盒子，收纳目标完成。",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(completed.status_code, 200)
        awaiting = self.client.post(
            f"/api/tasks/{water_task}/complete",
            json={
                "completionSource": "parent",
                "evidenceSummary": "孩子说已经喝水，等待家长确认。",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(awaiting.status_code, 200)
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            task_row = conn.execute(
                "SELECT family_id FROM tasks WHERE id = ?",
                (toy_task,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO task_events(
                  id, family_id, task_id, event_type, message, payload, created_at
                )
                VALUES (?, ?, ?, 'monitor_started', '摄像头已开始观察任务', '{}', 1)
                """,
                (f"event_{toy_task}", task_row["family_id"], toy_task),
            )

        daily = self.client.get(
            f"/api/reports/daily?date={today}",
            headers=self._auth_headers(),
        )
        self.assertEqual(daily.status_code, 200)
        report = daily.json["report"]
        self.assertEqual(report["taskTotal"], 2)
        self.assertEqual(report["taskCompleted"], 1)
        self.assertEqual(report["pendingItems"], 1)
        self.assertGreaterEqual(len(report["skills"]), 5)
        self.assertTrue(report["highlights"])
        self.assertTrue(report["improvements"])
        self.assertTrue(report["observations"])
        self.assertTrue(report["tasks"])
        self.assertTrue(report["nextActions"])
        combined_report_text = str(report["highlights"]) + str(report["observations"]) + str(report["tasks"])
        self.assertIn("玩具", combined_report_text)
        self.assertIn("收纳", combined_report_text)
        self.assertNotIn("monitor_started", combined_report_text)
        self.assertNotIn("开始观察任务", combined_report_text)

        weekly = self.client.get(
            f"/api/reports/weekly?startDate={today}&endDate={today}",
            headers=self._auth_headers(),
        )
        self.assertEqual(weekly.status_code, 200)
        self.assertGreaterEqual(len(weekly.json["report"]["skills"]), 5)

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

    def _attach_user_to_member(self, phone: str, member_id: str) -> str:
        access_token = self._login(phone)
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            owner = conn.execute(
                "SELECT * FROM users WHERE phone = ?",
                ("13800002026",),
            ).fetchone()
            target = conn.execute(
                "SELECT * FROM users WHERE phone = ?",
                (phone,),
            ).fetchone()
            self.assertIsNotNone(owner)
            self.assertIsNotNone(target)
            conn.execute(
                "UPDATE users SET family_id = ? WHERE id = ?",
                (owner["family_id"], target["id"]),
            )
            conn.execute(
                """
                UPDATE family_members
                SET user_id = ?, phone = ?, status = 'active'
                WHERE id = ?
                """,
                (target["id"], phone, member_id),
            )
        return access_token

    def _create_child(self, name: str) -> str:
        response = self.client.post(
            "/api/setup/child",
            json={"name": name, "nickname": name, "ageStage": "primary"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["child"]["id"]

    def _save_parent_identity(self) -> None:
        response = self.client.post(
            "/api/setup/parent-identity",
            json={
                "displayName": "其他家人",
                "relationship": "其他家人",
                "relationshipKey": "family_default",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)

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

    def _create_task(
        self,
        *,
        title: str,
        task_type: str,
        scheduled_date: str,
        reward_points: int,
        requires_parent_confirmation: bool,
    ) -> str:
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": self.child_id,
                "title": title,
                "taskType": task_type,
                "rewardPoints": reward_points,
                "scheduledDate": scheduled_date,
                "scheduledStart": "18:00",
                "scheduledEnd": "18:20",
                "requiresParentConfirmation": requires_parent_confirmation,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["task"]["id"]

    def _save_wifi(self) -> None:
        response = self.client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)

    def _mark_setup_completed(self, access_token: str | None = None) -> None:
        token = access_token or self.access_token
        summary = self.client.get(
            "/api/profile/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(summary.status_code, 200)
        family_id = summary.json["summary"]["familyId"]
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO setup_progress(
                  family_id, completed, parent_identity_status, device_binding_status,
                  wifi_status, child_profile_status, camera_name_status,
                  camera_name_intro_status, contacts_status, created_at, updated_at, completed_at
                )
                VALUES (?, 1, 'done', 'done', 'done', 'done', 'done', 'done', 'done', 1, 1, 1)
                ON DUPLICATE KEY UPDATE
                  completed = 1,
                  parent_identity_status = 'done',
                  device_binding_status = 'done',
                  wifi_status = 'done',
                  child_profile_status = 'done',
                  camera_name_status = 'done',
                  camera_name_intro_status = 'done',
                  contacts_status = 'done',
                  updated_at = 1,
                  completed_at = 1
                """,
                (family_id,),
            )

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
