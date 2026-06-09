from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import hash_value, now_ms
from repositories.profile_repository import ProfileRepository
from schemas.auth import normalize_phone
from schemas.profile import (
    account_deletion_request_payload,
    account_profile_payload,
    account_security_payload,
    child_profile_payload,
    emergency_contact_payload,
    family_invitation_payload,
    family_member_payload,
    feedback_payload,
    guardian_identity_options_payload,
    pending_join_payload,
    role_capabilities_from_option,
    setting_payload,
)
from services.auth_service import AuthService


MEMBER_STATUSES = {"active", "invited", "disabled"}
INVITATION_TTL_MS = 7 * 24 * 60 * 60 * 1000
CONTENT_ROOT = Path(__file__).resolve().parents[1] / "content"
JOIN_CODE_DEFAULT_ROLE = "viewer"
INVITATION_DELIVERY_NOTICE = "邀请已保存。短信邀请暂未接入，请让对方使用该手机号登录后接受邀请。"
FALLBACK_ROLE_CAPABILITIES = {
    "admin": [
        "manage_family_members",
        "manage_family_code",
        "manage_devices",
        "manage_privacy",
        "manage_subscription",
        "manage_child_profile",
        "manage_child_settings",
        "manage_emergency_contacts",
        "manage_rewards",
        "manage_tasks",
        "confirm_tasks",
        "view_live_care",
        "view_reports",
        "view_points_rewards",
        "manage_account_security",
    ],
    "guardian": [
        "manage_child_profile",
        "manage_child_settings",
        "manage_emergency_contacts",
        "manage_rewards",
        "manage_tasks",
        "confirm_tasks",
        "view_live_care",
        "view_reports",
        "view_points_rewards",
        "manage_account_security",
    ],
    "viewer": ["view_basic_home", "view_alerts", "manage_account_security"],
}
SETTING_MANAGE_CAPABILITIES = {
    "ai-care-rules": "manage_child_settings",
    "notifications": "manage_child_settings",
    "conversation": "manage_child_settings",
    "education": "manage_child_settings",
    "privacy": "manage_privacy",
}
UNIQUE_GUARDIAN_IDENTITY_KEYS = {
    "mom",
    "dad",
    "maternal_grandpa",
    "maternal_grandma",
    "grandpa",
    "grandma",
}

LEGACY_GUARDIAN_IDENTITY_KEYS = {
    "母亲": "mom",
    "妈妈": "mom",
    "mother": "mom",
    "mom": "mom",
    "父亲": "dad",
    "爸爸": "dad",
    "father": "dad",
    "dad": "dad",
    "外公": "maternal_grandpa",
    "外婆": "maternal_grandma",
    "爷爷": "grandpa",
    "奶奶": "grandma",
    "guardian": "family_default",
    "caregiver": "family_default",
    "family": "family_default",
    "member": "family_default",
    "other": "family_default",
    "unknown": "family_default",
    "grandparent": "family_default",
}

SETTING_DEFAULTS = {
    "ai-care-rules": {
        "taskObservationEnabled": True,
        "voiceReminderEnabled": True,
        "delayReminderEnabled": True,
        "delayReminderIntervalMinutes": 3,
        "maxDelayReminderCount": 3,
        "cameraObservationStrategy": "balanced",
    },
    "notifications": {
        "taskReminder": True,
        "taskEndReminder": True,
        "deviceOfflineReminder": True,
        "pointsRewardReminder": True,
        "safetyAlert": True,
        "dailySummary": False,
        "quietHoursEnabled": False,
        "quietHoursStart": "21:30",
        "quietHoursEnd": "07:00",
    },
    "privacy": {
        "cameraCollectionAuthorized": False,
        "voiceBroadcastAuthorized": False,
        "childPrivacyAuthorized": False,
        "remoteViewingNoticeEnabled": True,
        "storeEventSnapshotsOnly": True,
        "detailedConversationLogEnabled": False,
        "dataRetentionDays": 30,
    },
    "conversation": {
        "wakeName": "看护助手",
        "voiceStyle": "温和女声",
        "boundaryLevel": "balanced",
        "freeChatEnabled": True,
        "homeworkModeRestricted": True,
        "bedtimeQuietEnabled": True,
        "detailedTranscriptEnabled": False,
    },
    "education": {
        "schoolbagEnabled": True,
        "schoolStage": "primary",
        "courseScheduleEnabled": False,
        "partnerContentEnabled": False,
        "learningDiagnosisEnabled": False,
        "notes": "",
    },
}


class ProfileService:
    def __init__(self, database_url: str | Path, *, auth_service: AuthService):
        self.auth_service = auth_service
        self.repository = ProfileRepository(Database(database_url))

    def summary(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            profile = self.repository.get_parent_identity(conn, family_id=family["id"])
            member, relationship, relationship_key = self._current_member_identity(
                conn,
                family_id=family["id"],
                user=user,
                parent_identity=profile,
                now=now,
            )
            members = self.repository.list_family_members(conn, family_id=family["id"])
            child = self.repository.current_child(conn, family_id=family["id"])
            display_name = relationship or member["name"] or user["display_name"]
            return {
                "ok": True,
                "summary": {
                    "spaceTitle": "家庭看护空间",
                    "familyId": family["id"],
                    "familyName": family["name"],
                    "displayName": display_name,
                    "phone": user["phone"],
                    "role": member["role"],
                    "roleLabel": self._family_role_label(conn, member["role"]),
                    "capabilities": self._capabilities_for_role(conn, member["role"]),
                    "relationship": relationship,
                    "relationshipKey": relationship_key,
                    "memberCount": len(members),
                    "deviceCount": self.repository.count_devices(conn, family_id=family["id"]),
                    "pendingItemCount": self.repository.count_pending_items(
                        conn,
                        family_id=family["id"],
                    ),
                    "child": child_profile_payload(child),
                },
            }

    def guardian_identity_options(self, access_token: str) -> dict:
        self._auth_context(access_token)
        with self.repository.transaction() as conn:
            return {
                "ok": True,
                "options": guardian_identity_options_payload(
                    self.repository.list_app_option_items(
                        conn,
                        catalog_key="guardian_identity_group",
                    ),
                    self.repository.list_app_option_items(
                        conn,
                        catalog_key="guardian_identity_label",
                    ),
                    self.repository.list_app_option_items(
                        conn,
                        catalog_key="family_role",
                    ),
                ),
            }

    def list_family_members(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            parent_identity = self.repository.get_parent_identity(
                conn,
                family_id=context["family"]["id"],
            )
            self._current_member_identity(
                conn,
                family_id=context["family"]["id"],
                user=user,
                parent_identity=parent_identity,
                now=now,
            )
            rows = self.repository.list_family_members(conn, family_id=context["family"]["id"])
            return {"ok": True, "members": [family_member_payload(row) for row in rows]}

    def create_family_member(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        requested_name = self._required_text(data, "name", "请输入成员姓名")
        requested_relationship_key = self._optional_text(data, "relationshipKey")
        status = self._member_status(self._optional_text(data, "status") or "active")
        phone = self._optional_phone(data.get("phone"))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_members")
            name, relationship_key = self._guardian_identity_value(
                conn,
                relationship_key=requested_relationship_key,
                relationship=requested_name,
            )
            role = self._member_role(
                conn,
                self._optional_text(data, "role") or self._default_member_role(conn),
            )
            self._assert_member_role_available(
                conn,
                family_id=context["family"]["id"],
                role=role,
            )
            self._assert_guardian_identity_available(
                conn,
                family_id=context["family"]["id"],
                relationship_key=relationship_key,
            )
            member = self.repository.create_family_member(
                conn,
                family_id=context["family"]["id"],
                name=name,
                relationship_key=relationship_key,
                phone=phone,
                role=role,
                status=status,
                notify_enabled=bool(data.get("notifyEnabled", True)),
                now=now,
            )
            return {"ok": True, "member": family_member_payload(member)}

    def update_family_member(self, access_token: str, member_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        fields: dict = {}
        requested_relationship_key = self._optional_text(data, "relationshipKey")
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入成员姓名")
        if "phone" in data:
            fields["phone"] = self._optional_phone(data.get("phone"))
        raw_role = str(data["role"]) if "role" in data else None
        if "status" in data:
            fields["status"] = self._member_status(str(data["status"]))
        if "notifyEnabled" in data:
            fields["notify_enabled"] = int(bool(data["notifyEnabled"]))
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_members")
            if raw_role is not None:
                fields["role"] = self._member_role(conn, raw_role)
            member = self._member_or_error(conn, context["family"]["id"], member_id)
            if "name" in fields or requested_relationship_key is not None:
                relationship, relationship_key = self._guardian_identity_value(
                    conn,
                    relationship_key=requested_relationship_key,
                    relationship=fields.get("name") or member.get("name"),
                )
                fields["name"] = relationship
                fields["relationship_key"] = relationship_key
            if member["user_id"] == context["user"]["id"] and fields.get("role") not in {None, "admin"}:
                raise ApiError("cannot_downgrade_self", "不能降低当前管理员自己的权限")
            if fields.get("role"):
                self._assert_member_role_available(
                    conn,
                    family_id=context["family"]["id"],
                    role=fields["role"],
                    exclude_member_id=member_id,
                )
            if fields.get("relationship_key"):
                self._assert_guardian_identity_available(
                    conn,
                    family_id=context["family"]["id"],
                    relationship_key=fields["relationship_key"],
                    exclude_member_id=member_id,
                )
            member = self.repository.update_family_member(
                conn,
                family_id=context["family"]["id"],
                member_id=member_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "member": family_member_payload(member)}

    def delete_family_member(self, access_token: str, member_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_members")
            member = self._member_or_error(conn, context["family"]["id"], member_id)
            if member["user_id"] == context["user"]["id"]:
                raise ApiError("cannot_remove_self", "不能移除当前登录的管理员")
            self.repository.delete_family_member(
                conn,
                family_id=context["family"]["id"],
                member_id=member_id,
            )
            return {"ok": True}

    def transfer_family_admin(self, access_token: str, member_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            current_member = self._assert_current_admin(conn, context)
            target = self._member_or_error(conn, context["family"]["id"], member_id)
            if target["id"] == current_member["id"]:
                raise ApiError("cannot_transfer_to_self", "当前账号已经是管理员")
            if target["status"] != "active" or not target.get("user_id"):
                raise ApiError("member_not_joined", "只能转移给已加入家庭的成员")

            self.repository.update_family_member(
                conn,
                family_id=context["family"]["id"],
                member_id=current_member["id"],
                fields={"role": "guardian"},
                now=now,
            )
            self.repository.update_family_member(
                conn,
                family_id=context["family"]["id"],
                member_id=target["id"],
                fields={"role": "admin"},
                now=now,
            )
            rows = self.repository.list_family_members(conn, family_id=context["family"]["id"])
            return {
                "ok": True,
                "message": "管理员已转移",
                "members": [family_member_payload(row) for row in rows],
            }

    def list_family_invitations(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            rows = self.repository.list_family_invitations(
                conn,
                family_id=context["family"]["id"],
            )
            return {
                "ok": True,
                "invitations": [family_invitation_payload(row) for row in rows],
            }

    def create_family_invitation(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        requested_name = self._required_text(data, "name", "请输入成员称呼")
        requested_relationship_key = self._optional_text(data, "relationshipKey")
        phone = self._required_phone(data.get("phone"))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_members")
            name, relationship_key = self._guardian_identity_value(
                conn,
                relationship_key=requested_relationship_key,
                relationship=requested_name,
            )
            role = self._member_role(
                conn,
                self._optional_text(data, "role") or self._default_member_role(conn),
            )
            self._assert_member_role_available(
                conn,
                family_id=context["family"]["id"],
                role=role,
            )
            self._assert_guardian_identity_available(
                conn,
                family_id=context["family"]["id"],
                relationship_key=relationship_key,
            )
            invitation = self.repository.create_family_invitation(
                conn,
                family_id=context["family"]["id"],
                name=name,
                relationship_key=relationship_key,
                phone=phone,
                role=role,
                created_by=context["user"]["id"],
                now=now,
                expires_at=now + INVITATION_TTL_MS,
            )
            return {
                "ok": True,
                "invitation": family_invitation_payload(invitation),
                "deliveryStatus": invitation.get("delivery_status") or "not_configured",
                "deliveryNotice": invitation.get("delivery_message") or INVITATION_DELIVERY_NOTICE,
            }

    def resend_family_invitation(self, access_token: str, invitation_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_members")
            invitation = self._invitation_or_error(
                conn,
                context["family"]["id"],
                invitation_id,
            )
            if invitation["status"] != "pending":
                raise ApiError("invitation_not_pending", "这条邀请已经不可重发")
            invitation = self.repository.update_family_invitation(
                conn,
                family_id=context["family"]["id"],
                invitation_id=invitation_id,
                fields={
                    "created_at": now,
                    "expires_at": now + INVITATION_TTL_MS,
                    "delivery_status": "not_configured",
                    "delivery_message": INVITATION_DELIVERY_NOTICE,
                },
                now=now,
            )
            return {
                "ok": True,
                "invitation": family_invitation_payload(invitation),
                "deliveryStatus": invitation.get("delivery_status") or "not_configured",
                "deliveryNotice": invitation.get("delivery_message") or INVITATION_DELIVERY_NOTICE,
            }

    def cancel_family_invitation(self, access_token: str, invitation_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_members")
            self._invitation_or_error(conn, context["family"]["id"], invitation_id)
            invitation = self.repository.update_family_invitation(
                conn,
                family_id=context["family"]["id"],
                invitation_id=invitation_id,
                fields={"status": "cancelled"},
                now=now,
            )
            return {"ok": True, "invitation": family_invitation_payload(invitation)}

    def accept_family_invitation(self, access_token: str, invitation_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            invitation = self.repository.get_family_invitation_for_phone(
                conn,
                invitation_id=invitation_id,
                phone=user["phone"],
            )
            if invitation is None:
                raise ApiError("invitation_not_found", "没有找到可接受的家庭邀请", 404)
            if invitation["status"] != "pending":
                raise ApiError("invitation_not_pending", "这条邀请已经不可接受")
            if invitation.get("expires_at") and invitation["expires_at"] < now:
                self.repository.update_family_invitation_by_id(
                    conn,
                    invitation_id=invitation_id,
                    fields={"status": "expired"},
                    now=now,
                )
                raise ApiError("invitation_expired", "这条邀请已过期，请让管理员重新邀请")

            target_family = self._family_or_error(conn, invitation["family_id"])
            self._assert_join_target_available(
                conn,
                current_family_id=user["family_id"],
                target_family_id=target_family["id"],
                via="invitation",
            )
            self._assert_member_role_available(
                conn,
                family_id=target_family["id"],
                role=invitation["role"],
                exclude_invitation_id=invitation["id"],
            )
            relationship_key = invitation.get("relationship_key") or self._guardian_identity_key_for_value(
                conn,
                invitation["name"],
            )
            self._assert_guardian_identity_available(
                conn,
                family_id=target_family["id"],
                relationship_key=relationship_key,
                exclude_invitation_id=invitation["id"],
            )
            previous_family_id = user["family_id"]
            user = self.repository.update_user_family(
                conn,
                user_id=user["id"],
                family_id=target_family["id"],
            )
            member = self.repository.upsert_joined_family_member(
                conn,
                family_id=target_family["id"],
                user_id=user["id"],
                name=invitation["name"],
                relationship_key=relationship_key,
                phone=user["phone"],
                role=invitation["role"],
                now=now,
            )
            invitation = self.repository.update_family_invitation_by_id(
                conn,
                invitation_id=invitation_id,
                fields={
                    "status": "accepted",
                    "accepted_by": user["id"],
                    "accepted_at": now,
                },
                now=now,
            )
            if previous_family_id != target_family["id"]:
                self.repository.cleanup_orphan_family(conn, family_id=previous_family_id)
            return {
                "ok": True,
                "message": "已加入家庭空间",
                "family": {
                    "id": target_family["id"],
                    "name": target_family["name"],
                    "familyCode": target_family.get("family_code") or "",
                },
                "member": family_member_payload(member),
                "invitation": family_invitation_payload(invitation),
            }

    def decline_family_invitation(self, access_token: str, invitation_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            invitation = self.repository.get_family_invitation_for_phone(
                conn,
                invitation_id=invitation_id,
                phone=user["phone"],
            )
            if invitation is None:
                raise ApiError("invitation_not_found", "没有找到可处理的家庭邀请", 404)
            if invitation["status"] != "pending":
                raise ApiError("invitation_not_pending", "这条邀请已经不可处理")
            invitation = self.repository.update_family_invitation_by_id(
                conn,
                invitation_id=invitation_id,
                fields={"status": "declined", "declined_at": now},
                now=now,
            )
            return {"ok": True, "invitation": family_invitation_payload(invitation)}

    def family_code(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_code")
            family = self._family_or_error(conn, context["family"]["id"])
            return {
                "ok": True,
                "familyCode": {
                    "familyId": family["id"],
                    "familyName": family["name"],
                    "code": family.get("family_code") or "",
                    "updatedAt": family.get("family_code_updated_at"),
                },
            }

    def reset_family_code(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_family_code")
            family = self._family_or_error(conn, context["family"]["id"])
            family = self.repository.update_family_code(
                conn,
                family_id=family["id"],
                family_code=self._new_unique_family_code(conn),
                now=now,
            )
            return {
                "ok": True,
                "familyCode": {
                    "familyId": family["id"],
                    "familyName": family["name"],
                    "code": family.get("family_code") or "",
                    "updatedAt": family.get("family_code_updated_at"),
                },
            }

    def preview_join_code(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        code = self._family_code_text(data)
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self.repository.get_family_by_code(conn, code)
            if family is None:
                raise ApiError("family_code_invalid", "家庭号不正确，请核对后再试", 404)
            self._assert_join_target_available(
                conn,
                current_family_id=user["family_id"],
                target_family_id=family["id"],
                via="family_code",
            )
            return {
                "ok": True,
                "preview": {
                    "familyId": family["id"],
                    "familyName": family["name"],
                    "familyCode": family.get("family_code") or "",
                    "role": JOIN_CODE_DEFAULT_ROLE,
                    "roleLabel": self._family_role_label(conn, JOIN_CODE_DEFAULT_ROLE),
                    "message": "加入后可查看基础看护状态，管理员可在家庭成员中调整权限。",
                },
            }

    def accept_join_code(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        code = self._family_code_text(data)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self.repository.get_family_by_code(conn, code)
            if family is None:
                raise ApiError("family_code_invalid", "家庭号不正确，请核对后再试", 404)
            self._assert_join_target_available(
                conn,
                current_family_id=user["family_id"],
                target_family_id=family["id"],
                via="family_code",
            )
            previous_family_id = user["family_id"]
            user = self.repository.update_user_family(
                conn,
                user_id=user["id"],
                family_id=family["id"],
            )
            member = self.repository.upsert_joined_family_member(
                conn,
                family_id=family["id"],
                user_id=user["id"],
                name=user["display_name"] or "家庭成员",
                relationship_key=None,
                phone=user["phone"],
                role=JOIN_CODE_DEFAULT_ROLE,
                now=now,
            )
            if previous_family_id != family["id"]:
                self.repository.cleanup_orphan_family(conn, family_id=previous_family_id)
            return {
                "ok": True,
                "message": "已通过家庭号加入",
                "family": {
                    "id": family["id"],
                    "name": family["name"],
                    "familyCode": family.get("family_code") or "",
                },
                "member": family_member_payload(member),
            }

    def current_child(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            child = self.repository.current_child(conn, family_id=context["family"]["id"])
            return {"ok": True, "child": child_profile_payload(child)}

    def update_child(self, access_token: str, child_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        mapping = {
            "name": "name",
            "nickname": "nickname",
            "gender": "gender",
            "birthday": "birthday",
            "ageStage": "age_stage",
            "educationStage": "education_stage",
            "grade": "grade",
            "schoolName": "school_name",
        }
        for key, column in mapping.items():
            if key in data:
                if key == "name":
                    fields[column] = self._required_text(data, key, "请输入孩子姓名")
                elif key == "gender":
                    fields[column] = self._gender(self._optional_text(data, key))
                else:
                    fields[column] = self._optional_text(data, key)
        if "interests" in data:
            fields["interests"] = self._json_list(data["interests"])
        if "taskPreferences" in data:
            fields["task_preferences"] = self._json_dict(data["taskPreferences"])
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_child_profile")
            self._child_or_error(conn, context["family"]["id"], child_id)
            child = self.repository.update_child(
                conn,
                family_id=context["family"]["id"],
                child_id=child_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "child": child_profile_payload(child)}

    def list_contacts(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            rows = self.repository.list_contacts(conn, family_id=context["family"]["id"])
            return {
                "ok": True,
                "contacts": [
                    self._emergency_contact_payload(conn, row) for row in rows
                ],
            }

    def create_contact(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "name", "请输入联系人姓名")
        phone = normalize_phone(str(data.get("phone") or ""))
        relationship = self._optional_text(data, "relationship")
        relationship_key = self._optional_text(data, "relationshipKey")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_emergency_contacts")
            relationship, relationship_key = self._guardian_identity_value(
                conn,
                relationship_key=relationship_key,
                relationship=relationship,
                allow_legacy_fallback=True,
            )
            self._assert_contact_identity_available(
                conn,
                family_id=context["family"]["id"],
                relationship_key=relationship_key,
            )
            contact = self.repository.create_contact(
                conn,
                family_id=context["family"]["id"],
                name=name,
                phone=phone,
                relationship=relationship,
                relationship_key=relationship_key,
                default_notify=bool(data.get("defaultNotify", True)),
                now=now,
            )
            return {
                "ok": True,
                "contact": self._emergency_contact_payload(conn, contact),
            }

    def update_contact(self, access_token: str, contact_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入联系人姓名")
        if "phone" in data:
            fields["phone"] = normalize_phone(str(data.get("phone") or ""))
        if "defaultNotify" in data:
            fields["default_notify"] = int(bool(data["defaultNotify"]))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_emergency_contacts")
            self._contact_or_error(conn, context["family"]["id"], contact_id)
            if "relationship" in data or "relationshipKey" in data:
                relationship, relationship_key = self._guardian_identity_value(
                    conn,
                    relationship_key=self._optional_text(data, "relationshipKey"),
                    relationship=self._optional_text(data, "relationship"),
                    allow_legacy_fallback=True,
                )
                self._assert_contact_identity_available(
                    conn,
                    family_id=context["family"]["id"],
                    relationship_key=relationship_key,
                    exclude_contact_id=contact_id,
                )
                fields["relationship"] = relationship
                fields["relationship_key"] = relationship_key
            contact = self.repository.update_contact(
                conn,
                family_id=context["family"]["id"],
                contact_id=contact_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "contact": self._emergency_contact_payload(conn, contact)}

    def delete_contact(self, access_token: str, contact_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_emergency_contacts")
            self._contact_or_error(conn, context["family"]["id"], contact_id)
            self.repository.delete_contact(
                conn,
                family_id=context["family"]["id"],
                contact_id=contact_id,
            )
            return {"ok": True}

    def get_setting(self, access_token: str, key: str) -> dict:
        self._validate_setting_key(key)
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            row = self.repository.get_setting(conn, family_id=context["family"]["id"], key=key)
            value = _setting_value(row, key)
            return {"ok": True, "setting": setting_payload(key, value, row["updated_at"] if row else None)}

    def update_setting(self, access_token: str, key: str, data: dict) -> dict:
        self._validate_setting_key(key)
        context = self._auth_context(access_token)
        value = dict(SETTING_DEFAULTS[key])
        incoming = data.get("value") if isinstance(data.get("value"), dict) else data
        for item_key, item_value in incoming.items():
            if item_key in value:
                value[item_key] = item_value
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(
                conn,
                context,
                SETTING_MANAGE_CAPABILITIES[key],
            )
            row = self.repository.upsert_setting(
                conn,
                family_id=context["family"]["id"],
                key=key,
                value=value,
                now=now,
            )
            return {"ok": True, "setting": setting_payload(key, value, row["updated_at"])}

    def account_profile(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            parent_identity = self.repository.get_parent_identity(conn, family_id=family["id"])
            member, relationship, relationship_key = self._current_member_identity(
                conn,
                family_id=family["id"],
                user=user,
                parent_identity=parent_identity,
                now=now,
            )
            return {
                "ok": True,
                "profile": account_profile_payload(
                    user,
                    family,
                    parent_identity,
                    role=member["role"],
                    role_label=self._family_role_label(conn, member["role"]),
                    capabilities=self._capabilities_for_role(conn, member["role"]),
                    display_name=relationship or member["name"],
                    relationship=relationship,
                    relationship_key=relationship_key,
                ),
            }

    def update_account_profile(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        display_name = self._optional_text(data, "displayName")
        family_name = self._optional_text(data, "familyName")
        relationship = self._optional_text(data, "relationship")
        relationship_key = self._optional_text(data, "relationshipKey")
        now = now_ms()
        with self.repository.transaction() as conn:
            if family_name is not None or relationship is not None or relationship_key is not None:
                self._assert_capability(conn, context, "manage_family_members")
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            user = self.repository.update_user_profile(conn, user_id=user["id"], display_name=display_name)
            family = self.repository.update_family_name(conn, family_id=family["id"], name=family_name)
            parent_identity = self.repository.get_parent_identity(conn, family_id=family["id"])
            if relationship is not None or relationship_key is not None:
                relationship, relationship_key = self._guardian_identity_value(
                    conn,
                    relationship_key=relationship_key,
                    relationship=relationship or display_name,
                )
                self._assert_guardian_identity_available(
                    conn,
                    family_id=family["id"],
                    relationship_key=relationship_key,
                    exclude_parent_identity=True,
                    exclude_member_user_id=user["id"],
                )
                parent_identity = self.repository.upsert_parent_identity(
                    conn,
                    family_id=family["id"],
                    display_name=relationship,
                    relationship=relationship,
                    relationship_key=relationship_key,
                    now=now,
                )
                member = self.repository.get_family_member_by_user(
                    conn,
                    family_id=family["id"],
                    user_id=user["id"],
                )
                if member is not None:
                    member = self.repository.update_family_member(
                        conn,
                        family_id=family["id"],
                        member_id=member["id"],
                        fields={
                            "name": relationship,
                            "relationship_key": relationship_key,
                            "phone": user["phone"],
                        },
                        now=now,
                    )
            member, current_relationship, resolved_relationship_key = self._current_member_identity(
                conn,
                family_id=family["id"],
                user=user,
                parent_identity=parent_identity,
                now=now,
            )
            return {
                "ok": True,
                "profile": account_profile_payload(
                    user,
                    family,
                    parent_identity,
                    role=member["role"],
                    role_label=self._family_role_label(conn, member["role"]),
                    capabilities=self._capabilities_for_role(conn, member["role"]),
                    display_name=current_relationship or member["name"],
                    relationship=current_relationship,
                    relationship_key=resolved_relationship_key,
                ),
            }

    def account_security(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            sessions = self.repository.list_sessions(conn, user_id=user["id"])
            return {
                "ok": True,
                "security": account_security_payload(
                    user,
                    sessions,
                    current_access_hash=hash_value(access_token),
                ),
            }

    def revoke_account_session(self, access_token: str, session_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        current_access_hash = hash_value(access_token)
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            session = self.repository.get_session(conn, user_id=user["id"], session_id=session_id)
            if session is None:
                raise ApiError("session_not_found", "登录设备不存在", 404)
            if session.get("access_hash") == current_access_hash:
                raise ApiError("cannot_revoke_current_session", "当前设备不能在这里移除")
            self.repository.revoke_session(
                conn,
                user_id=user["id"],
                session_id=session_id,
                revoked_at=now,
            )
            sessions = self.repository.list_sessions(conn, user_id=user["id"])
            return {
                "ok": True,
                "message": "设备已移除",
                "security": account_security_payload(
                    user,
                    sessions,
                    current_access_hash=current_access_hash,
                ),
            }

    def request_account_deletion(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        reason = str(data.get("reason") or "").strip() or None
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            member = self._current_member_or_error(conn, context)
            if member["role"] == "admin":
                joined_members = [
                    row
                    for row in self.repository.list_family_members(
                        conn,
                        family_id=family["id"],
                    )
                    if row["id"] != member["id"]
                    and row["status"] == "active"
                    and row.get("user_id")
                ]
                if joined_members:
                    raise ApiError(
                        "admin_transfer_required",
                        "注销前请先把管理员转移给其他家庭成员",
                        409,
                    )
            deletion_request = self.repository.create_account_deletion_request(
                conn,
                user_id=user["id"],
                family_id=family["id"],
                reason=reason,
                requested_at=now,
            )
            user = self.repository.mark_user_deletion_requested(
                conn,
                user_id=user["id"],
                requested_at=now,
            )
            self.repository.revoke_user_sessions(
                conn,
                user_id=user["id"],
                revoked_at=now,
            )
            return {
                "ok": True,
                "message": "账号注销申请已提交",
                "accountStatus": user.get("account_status") or "deletion_requested",
                "deletionRequest": account_deletion_request_payload(deletion_request),
            }

    def request_account_phone_code(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        phone = normalize_phone(str(data.get("phone") or ""))
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            if user["phone"] == phone:
                raise ApiError("same_phone", "请填写一个新的手机号")
            existing = self.repository.get_user_by_phone(conn, phone)
            if existing is not None:
                raise ApiError("phone_in_use", "该手机号已被其他账号使用")

        result = self.auth_service.request_sms_code(phone)
        payload = {
            "ok": True,
            "codeSent": True,
            "expiresAt": result["expiresAt"],
            "provider": result["provider"],
            "templateId": result["templateId"],
            "deliveryStatus": result["deliveryStatus"],
            "message": "验证码已发送",
        }
        if result["debugCode"] is not None:
            payload["debugCode"] = result["debugCode"]
        return payload

    def change_account_phone(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        phone = normalize_phone(str(data.get("phone") or ""))
        code = self._required_text(data, "code", "请输入验证码")
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            if user["phone"] == phone:
                raise ApiError("same_phone", "请填写一个新的手机号")
            existing = self.repository.get_user_by_phone(conn, phone)
            if existing is not None and existing["id"] != user["id"]:
                raise ApiError("phone_in_use", "该手机号已被其他账号使用")

            sms = self.repository.find_sms_code(conn, phone)
            if not sms or sms["expires_at"] < now:
                raise ApiError("invalid_code", "验证码不正确，请重新输入")
            if sms["attempt_count"] >= self.auth_service.sms_max_attempts:
                raise ApiError("sms_attempts_exceeded", "验证码错误次数过多，请重新获取验证码", 429)
            if sms["code_hash"] != hash_value(code):
                self.repository.increment_sms_attempts(conn, phone)
                raise ApiError("invalid_code", "验证码不正确，请重新输入")

            self.repository.delete_sms_code(conn, phone)
            user = self.repository.update_user_phone(conn, user_id=user["id"], phone=phone)
            parent_identity = self.repository.get_parent_identity(conn, family_id=family["id"])
            member, relationship, relationship_key = self._current_member_identity(
                conn,
                family_id=family["id"],
                user=user,
                parent_identity=parent_identity,
                now=now,
            )
            sessions = self.repository.list_sessions(conn, user_id=user["id"])
            return {
                "ok": True,
                "message": "手机号已更新",
                "profile": account_profile_payload(
                    user,
                    family,
                    parent_identity,
                    role=member["role"],
                    role_label=self._family_role_label(conn, member["role"]),
                    capabilities=self._capabilities_for_role(conn, member["role"]),
                    display_name=relationship or member["name"],
                    relationship=relationship,
                    relationship_key=relationship_key,
                ),
                "security": account_security_payload(user, sessions),
            }

    def subscription_status(self, access_token: str) -> dict:
        self._auth_context(access_token)
        current = self._current_subscription_payload(_subscription_entitlements())
        return {
            "ok": True,
            "subscription": current,
        }

    def subscription_plans(self, access_token: str) -> dict:
        self._auth_context(access_token)
        return {"ok": True, "plans": _subscription_plans()}

    def subscription_current(self, access_token: str) -> dict:
        self._auth_context(access_token)
        return {"ok": True, "subscription": self._current_subscription_payload(_subscription_entitlements())}

    def subscription_entitlements(self, access_token: str) -> dict:
        self._auth_context(access_token)
        return {"ok": True, "entitlements": _subscription_entitlements()}

    def subscription_checkout_session(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        plan_id = self._optional_text(data, "planId")
        plan = next((item for item in _subscription_plans() if item["id"] == plan_id), None)
        if plan is None or plan["id"] == "basic":
            raise ApiError("invalid_subscription_plan", "套餐不可开通", 400)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_subscription")
        return {
            "ok": True,
            "checkout": {
                "planId": plan["id"],
                "planTitle": plan["title"],
                "status": "pending_payment",
                "provider": "app_store",
                "paymentRequired": True,
                "receiptVerificationRequired": True,
                "message": "在线付款入口即将开放，当前可先查看套餐权益。",
            },
        }

    def subscription_restore(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_subscription")
        return {
            "ok": True,
            "restore": {
                "status": "no_purchase_record",
                "message": "暂未找到可恢复的订阅记录。",
            },
        }

    def _current_subscription_payload(self, entitlements: list[dict]) -> dict:
        return {
            "plan": "basic",
            "planId": "basic",
            "planLabel": "基础版",
            "status": "active",
            "statusLabel": "已启用",
            "renewalText": "随设备提供基础看护能力",
            "storeProvider": "app_store",
            "entitlements": [
                {
                    "key": item["key"],
                    "name": item["name"],
                    "enabled": bool(item["basic"]),
                }
                for item in entitlements
            ],
        }

    def daily_report(self, access_token: str, query: dict) -> dict:
        context = self._auth_context(access_token)
        target_date = self._optional_text(query, "date") or date.today().isoformat()
        with self.repository.transaction() as conn:
            rows = conn.execute(
                """
                SELECT status, reward_points FROM tasks
                WHERE family_id = ? AND scheduled_date = ?
                """,
                (context["family"]["id"], target_date),
            ).fetchall()
            total = len(rows)
            completed = sum(1 for row in rows if row["status"] in {"completed", "confirmed"})
            pending = sum(
                1
                for row in rows
                if row["status"] in {"awaiting_parent_confirmation", "delayed", "missed"}
            )
            points = sum(int(row["reward_points"] or 0) for row in rows if row["status"] in {"completed", "confirmed"})
            return {
                "ok": True,
                "report": {
                    "date": target_date,
                    "title": "今日报告",
                    "summary": _daily_summary(total, completed, pending),
                    "taskTotal": total,
                    "taskCompleted": completed,
                    "pendingItems": pending,
                    "pointsEarned": points,
                    "suggestion": _daily_suggestion(total, completed, pending),
                },
            }

    def weekly_report(self, access_token: str, query: dict) -> dict:
        context = self._auth_context(access_token)
        end_date = date.fromisoformat(self._optional_text(query, "endDate") or date.today().isoformat())
        start_date = date.fromisoformat(self._optional_text(query, "startDate") or (end_date - timedelta(days=6)).isoformat())
        with self.repository.transaction() as conn:
            rows = conn.execute(
                """
                SELECT scheduled_date, status, reward_points FROM tasks
                WHERE family_id = ? AND scheduled_date >= ? AND scheduled_date <= ?
                ORDER BY scheduled_date
                """,
                (context["family"]["id"], start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
            total = len(rows)
            completed = sum(1 for row in rows if row["status"] in {"completed", "confirmed"})
            points = sum(int(row["reward_points"] or 0) for row in rows if row["status"] in {"completed", "confirmed"})
            return {
                "ok": True,
                "report": {
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "title": "周报",
                    "taskTotal": total,
                    "taskCompleted": completed,
                    "completionRate": round(completed / total, 2) if total else 0,
                    "pointsEarned": points,
                    "summary": _weekly_summary(total, completed),
                },
            }

    def growth_moments(self, access_token: str) -> dict:
        self._auth_context(access_token)
        return {
            "ok": True,
            "moments": [],
        }

    def legal_document(self, key: str) -> dict:
        document = _legal_document(key)
        if document is None:
            raise ApiError("legal_document_not_found", "文档不存在", 404)
        return {"ok": True, "document": document}

    def app_about(self) -> dict:
        return {
            "ok": True,
            "about": _app_about(),
        }

    def create_feedback(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        category = self._optional_text(data, "category") or "general"
        content = self._required_text(data, "content", "请输入反馈内容")
        now = now_ms()
        with self.repository.transaction() as conn:
            feedback = self.repository.create_feedback(
                conn,
                family_id=context["family"]["id"],
                user_id=context["user"]["id"],
                category=category,
                content=content,
                now=now,
            )
            return {"ok": True, "feedback": feedback_payload(feedback)}

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _user_or_error(self, conn, user_id: str):
        user = self.repository.get_user(conn, user_id)
        if user is None:
            raise ApiError("user_not_found", "账号不存在", 404)
        return user

    def _family_or_error(self, conn, family_id: str):
        family = self.repository.get_family(conn, family_id)
        if family is None:
            raise ApiError("family_not_found", "家庭空间不存在", 404)
        return family

    def _member_or_error(self, conn, family_id: str, member_id: str):
        member = self.repository.get_family_member(conn, family_id=family_id, member_id=member_id)
        if member is None:
            raise ApiError("member_not_found", "家庭成员不存在", 404)
        return member

    def _owner_member_identity(
        self,
        conn,
        *,
        family_id: str,
        user: dict,
        parent_identity=None,
    ) -> tuple[str, str]:
        parent_identity = parent_identity or self.repository.get_parent_identity(
            conn,
            family_id=family_id,
        )
        relationship_key = self._relationship_key_for_parent_identity(
            conn,
            parent_identity,
        )
        identity_label = (
            self._guardian_identity_label_for_key(conn, relationship_key)
            if relationship_key
            else ""
        )
        fallback_name = (
            parent_identity.get("relationship")
            if parent_identity and parent_identity.get("relationship")
            else parent_identity.get("display_name")
            if parent_identity and parent_identity.get("display_name")
            else user.get("display_name")
            or user.get("displayName")
            or "家长"
        )
        return identity_label or fallback_name, relationship_key

    def _current_member_identity(
        self,
        conn,
        *,
        family_id: str,
        user: dict,
        parent_identity=None,
        now: int,
    ):
        member = self.repository.get_family_member_by_user(
            conn,
            family_id=family_id,
            user_id=user["id"],
        )
        if member is None:
            owner_name, relationship_key = self._owner_member_identity(
                conn,
                family_id=family_id,
                user=user,
                parent_identity=parent_identity,
            )
            member = self.repository.ensure_owner_member(
                conn,
                family_id=family_id,
                user_id=user["id"],
                name=owner_name,
                relationship_key=relationship_key,
                phone=user.get("phone") or "",
                now=now,
            )
        else:
            member = self._repair_member_identity_from_accepted_invitation(
                conn,
                family_id=family_id,
                user=user,
                member=member,
                parent_identity=parent_identity,
                now=now,
            )
            if user.get("phone") and member.get("phone") != user.get("phone"):
                member = self.repository.update_family_member(
                    conn,
                    family_id=family_id,
                    member_id=member["id"],
                    fields={"phone": user["phone"]},
                    now=now,
                )

        relationship_key = member.get("relationship_key") or self._guardian_identity_key_for_value(
            conn,
            member.get("name"),
        )
        relationship = (
            self._guardian_identity_label_for_key(conn, relationship_key)
            if relationship_key
            else member.get("name") or user.get("display_name") or "家长"
        )
        return member, relationship, relationship_key

    def _repair_member_identity_from_accepted_invitation(
        self,
        conn,
        *,
        family_id: str,
        user: dict,
        member,
        parent_identity=None,
        now: int,
    ):
        invitation = self.repository.get_accepted_family_invitation_by_user(
            conn,
            family_id=family_id,
            user_id=user["id"],
        )
        if invitation is None:
            return member

        invitation_key = invitation.get("relationship_key") or self._guardian_identity_key_for_value(
            conn,
            invitation.get("name"),
        )
        invitation_name = (
            self._guardian_identity_label_for_key(conn, invitation_key)
            if invitation_key
            else invitation.get("name") or ""
        )
        if not invitation_name and not invitation_key:
            return member

        member_key = member.get("relationship_key") or ""
        parent_key = self._relationship_key_for_parent_identity(conn, parent_identity)
        parent_labels = {
            value
            for value in (
                parent_identity.get("display_name") if parent_identity else "",
                parent_identity.get("relationship") if parent_identity else "",
                self._guardian_identity_label_for_key(conn, parent_key)
                if parent_key
                else "",
            )
            if value
        }
        parent_identity_belongs_to_another_member = False
        if parent_key or parent_labels:
            for family_member in self.repository.list_family_members(conn, family_id=family_id):
                if family_member["id"] == member["id"]:
                    continue
                family_member_key = family_member.get(
                    "relationship_key"
                ) or self._guardian_identity_key_for_value(
                    conn,
                    family_member.get("name"),
                )
                if parent_key and family_member_key == parent_key:
                    parent_identity_belongs_to_another_member = True
                    break
                if family_member.get("name") in parent_labels:
                    parent_identity_belongs_to_another_member = True
                    break

        should_repair = (
            not member_key
            or member_key == invitation_key
            or (
                parent_identity_belongs_to_another_member
                and (
                    (parent_key and member_key == parent_key)
                    or member.get("name") in parent_labels
                )
            )
        )
        if not should_repair:
            return member

        fields = {}
        if invitation_name and member.get("name") != invitation_name:
            fields["name"] = invitation_name
        if invitation_key and member_key != invitation_key:
            fields["relationship_key"] = invitation_key
        if not fields:
            return member
        return self.repository.update_family_member(
            conn,
            family_id=family_id,
            member_id=member["id"],
            fields=fields,
            now=now,
        )

    def _current_member_or_error(self, conn, context: dict):
        member = self.repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            user = context["user"]
            owner_name, relationship_key = self._owner_member_identity(
                conn,
                family_id=context["family"]["id"],
                user=user,
            )
            member = self.repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=user["id"],
                name=owner_name,
                relationship_key=relationship_key,
                phone=user.get("phone") or "",
                now=now_ms(),
            )
        if member is None:
            raise ApiError("member_not_found", "家庭成员不存在", 404)
        return member

    def _assert_current_admin(self, conn, context: dict):
        member = self._current_member_or_error(conn, context)
        if member["role"] != "admin":
            raise ApiError("admin_required", "只有家庭管理员可以进行此操作", 403)
        return member

    def _capabilities_for_role(self, conn, role: str) -> list[str]:
        row = self.repository.get_app_option_item(
            conn,
            catalog_key="family_role",
            item_key=role,
        )
        capabilities = role_capabilities_from_option(row)
        return capabilities or FALLBACK_ROLE_CAPABILITIES.get(role, [])

    def _assert_capability(self, conn, context: dict, capability: str):
        member = self._current_member_or_error(conn, context)
        if capability not in self._capabilities_for_role(conn, member["role"]):
            raise ApiError("permission_denied", "当前身份不能进行此操作", 403)
        return member

    def _assert_join_target_available(
        self,
        conn,
        *,
        current_family_id: str,
        target_family_id: str,
        via: str,
    ) -> None:
        if current_family_id == target_family_id:
            raise ApiError("already_in_family", "你已经在这个家庭空间中")
        if via == "family_code" and not self.repository.setup_completed(
            conn,
            family_id=target_family_id,
        ):
            raise ApiError("family_not_ready", "这个家庭空间还没有完成首次设置")
        if self.repository.setup_completed(conn, family_id=current_family_id):
            raise ApiError("family_switch_not_supported", "当前账号已有家庭空间，暂不支持直接加入其他家庭")

    def _family_code_text(self, data: dict) -> str:
        raw = self._required_text(data, "familyCode", "请输入家庭号")
        code = "".join(ch for ch in raw.upper() if ch.isalnum())
        if len(code) < 6 or len(code) > 16:
            raise ApiError("invalid_family_code", "家庭号格式不正确")
        return code

    def _new_unique_family_code(self, conn) -> str:
        for _ in range(12):
            code = uuid.uuid4().hex[:8].upper()
            if self.repository.get_family_by_code(conn, code) is None:
                return code
        raise ApiError("family_code_generation_failed", "家庭号生成失败，请稍后再试", 503)

    def _invitation_or_error(self, conn, family_id: str, invitation_id: str):
        invitation = self.repository.get_family_invitation(
            conn,
            family_id=family_id,
            invitation_id=invitation_id,
        )
        if invitation is None:
            raise ApiError("invitation_not_found", "邀请不存在", 404)
        return invitation

    def _child_or_error(self, conn, family_id: str, child_id: str):
        child = self.repository.get_child(conn, family_id=family_id, child_id=child_id)
        if child is None:
            raise ApiError("child_not_found", "孩子资料不存在", 404)
        return child

    def _contact_or_error(self, conn, family_id: str, contact_id: str):
        contact = self.repository.get_contact(conn, family_id=family_id, contact_id=contact_id)
        if contact is None:
            raise ApiError("contact_not_found", "联系人不存在", 404)
        return contact

    def _required_text(self, data: dict, key: str, message: str) -> str:
        value = self._optional_text(data, key)
        if not value:
            raise ApiError(f"missing_{key}", message)
        return value

    def _optional_text(self, data: dict, key: str) -> str | None:
        value = data.get(key)
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    def _optional_phone(self, value: object) -> str | None:
        raw = str(value or "").strip()
        return normalize_phone(raw) if raw else None

    def _required_phone(self, value: object) -> str:
        phone = self._optional_phone(value)
        if not phone:
            raise ApiError("missing_phone", "请输入手机号")
        return phone

    def _member_role(self, conn, value: str) -> str:
        value = value.strip()
        role_keys = {
            row["item_key"]
            for row in self.repository.list_app_option_items(
                conn,
                catalog_key="family_role",
            )
        }
        if value not in role_keys:
            raise ApiError("invalid_member_role", "成员角色不支持")
        return value

    def _default_member_role(self, conn) -> str:
        roles = self.repository.list_app_option_items(conn, catalog_key="family_role")
        for row in roles:
            if row["item_key"] == "guardian":
                return row["item_key"]
        if roles:
            return roles[0]["item_key"]
        raise ApiError("family_role_options_missing", "家庭角色配置不可用", 503)

    def _family_role_label(self, conn, role: str) -> str:
        for row in self.repository.list_app_option_items(
            conn,
            catalog_key="family_role",
        ):
            if row["item_key"] == role:
                return row["label"]
        return role

    def _assert_member_role_available(
        self,
        conn,
        *,
        family_id: str,
        role: str,
        exclude_member_id: str | None = None,
        exclude_invitation_id: str | None = None,
    ) -> None:
        if role != "admin":
            return
        for member in self.repository.list_family_members(conn, family_id=family_id):
            if exclude_member_id and member["id"] == exclude_member_id:
                continue
            if member["role"] == "admin":
                raise ApiError("duplicate_family_admin", "一个家庭只能有一个管理员")
        for invitation in self.repository.list_family_invitations(conn, family_id=family_id):
            if exclude_invitation_id and invitation["id"] == exclude_invitation_id:
                continue
            if invitation["role"] == "admin":
                raise ApiError("duplicate_family_admin", "一个家庭只能有一个管理员")

    def _assert_guardian_identity_available(
        self,
        conn,
        *,
        family_id: str,
        relationship_key: str,
        exclude_member_id: str | None = None,
        exclude_member_user_id: str | None = None,
        exclude_invitation_id: str | None = None,
        exclude_parent_identity: bool = False,
    ) -> None:
        if relationship_key not in UNIQUE_GUARDIAN_IDENTITY_KEYS:
            return
        if not exclude_parent_identity:
            parent_identity = self.repository.get_parent_identity(
                conn,
                family_id=family_id,
            )
            if (
                parent_identity
                and self._relationship_key_for_parent_identity(conn, parent_identity)
                == relationship_key
            ):
                self._raise_duplicate_guardian_identity(conn, relationship_key)
        for member in self.repository.list_family_members(conn, family_id=family_id):
            if exclude_member_id and member["id"] == exclude_member_id:
                continue
            if exclude_member_user_id and member.get("user_id") == exclude_member_user_id:
                continue
            member_key = member.get("relationship_key") or self._guardian_identity_key_for_value(
                conn,
                member["name"],
            )
            if member_key == relationship_key:
                self._raise_duplicate_guardian_identity(conn, relationship_key)
        for invitation in self.repository.list_family_invitations(conn, family_id=family_id):
            if exclude_invitation_id and invitation["id"] == exclude_invitation_id:
                continue
            invitation_key = invitation.get("relationship_key") or self._guardian_identity_key_for_value(
                conn,
                invitation["name"],
            )
            if invitation_key == relationship_key:
                self._raise_duplicate_guardian_identity(conn, relationship_key)

    def _assert_contact_identity_available(
        self,
        conn,
        *,
        family_id: str,
        relationship_key: str,
        exclude_contact_id: str | None = None,
    ) -> None:
        if relationship_key not in UNIQUE_GUARDIAN_IDENTITY_KEYS:
            return
        for contact in self.repository.list_contacts(conn, family_id=family_id):
            if exclude_contact_id and contact["id"] == exclude_contact_id:
                continue
            contact_key = contact.get("relationship_key") or self._guardian_identity_key_for_value(
                conn,
                contact.get("relationship") or "",
            )
            if contact_key == relationship_key:
                self._raise_duplicate_guardian_identity(conn, relationship_key)

    def _raise_duplicate_guardian_identity(self, conn, relationship_key: str) -> None:
        label = self._guardian_identity_label_for_key(conn, relationship_key)
        raise ApiError(
            "duplicate_guardian_identity",
            f"家庭里已经有“{label}”这个称呼了，请选择其他称呼",
        )

    def _guardian_identity_label_for_key(self, conn, relationship_key: str) -> str:
        for row in self.repository.list_app_option_items(
            conn,
            catalog_key="guardian_identity_label",
        ):
            if row["item_key"] == relationship_key:
                return row["label"]
        return relationship_key

    def _guardian_identity_key_for_value(self, conn, value: str | None) -> str:
        normalized = (value or "").strip()
        if not normalized:
            return ""
        for row in self.repository.list_app_option_items(
            conn,
            catalog_key="guardian_identity_label",
        ):
            if row["item_key"] == normalized or row["label"] == normalized:
                return row["item_key"]
        return self._legacy_guardian_identity_key(normalized)

    def _guardian_identity_value(
        self,
        conn,
        *,
        relationship_key: str | None,
        relationship: str | None,
        allow_legacy_fallback: bool = False,
    ) -> tuple[str, str]:
        rows = self.repository.list_app_option_items(
            conn,
            catalog_key="guardian_identity_label",
        )
        if relationship_key:
            for row in rows:
                if row["item_key"] == relationship_key:
                    return row["label"], row["item_key"]
            legacy_key = self._legacy_guardian_identity_key(relationship_key)
            if legacy_key:
                for row in rows:
                    if row["item_key"] == legacy_key:
                        return row["label"], row["item_key"]
            raise ApiError("invalid_guardian_identity", "请选择有效的家庭称呼")
        if relationship:
            for row in rows:
                if row["item_key"] == relationship or row["label"] == relationship:
                    return row["label"], row["item_key"]
            legacy_key = self._legacy_guardian_identity_key(relationship)
            if legacy_key:
                for row in rows:
                    if row["item_key"] == legacy_key:
                        return row["label"], row["item_key"]
        if allow_legacy_fallback:
            for row in rows:
                if row["item_key"] == "family_default":
                    return row["label"], row["item_key"]
            if rows:
                return rows[-1]["label"], rows[-1]["item_key"]
        raise ApiError("invalid_guardian_identity", "请选择有效的家庭称呼")

    def _emergency_contact_payload(self, conn, row) -> dict:
        try:
            relationship, relationship_key = self._guardian_identity_value(
                conn,
                relationship_key=row.get("relationship_key") or None,
                relationship=row.get("relationship") or None,
                allow_legacy_fallback=True,
            )
        except ApiError:
            relationship = row.get("relationship") or ""
            relationship_key = row.get("relationship_key") or ""
        return emergency_contact_payload(
            row,
            relationship=relationship,
            relationship_key=relationship_key,
        )

    def _legacy_guardian_identity_key(self, value: str | None) -> str:
        if not value:
            return ""
        return LEGACY_GUARDIAN_IDENTITY_KEYS.get(value.strip().lower(), "")

    def _relationship_key_for_parent_identity(self, conn, parent_identity) -> str:
        if not parent_identity:
            return ""
        current = parent_identity.get("relationship_key") or ""
        if current:
            return current
        relationship = parent_identity.get("relationship") or ""
        if not relationship:
            return ""
        for row in self.repository.list_app_option_items(
            conn,
            catalog_key="guardian_identity_label",
        ):
            if row["item_key"] == relationship or row["label"] == relationship:
                return row["item_key"]
        return ""

    def _member_status(self, value: str) -> str:
        value = value.strip()
        if value not in MEMBER_STATUSES:
            raise ApiError("invalid_member_status", "成员状态不支持")
        return value

    def _gender(self, value: str | None) -> str:
        normalized = value or "unspecified"
        if normalized not in {"male", "female", "unspecified"}:
            raise ApiError("invalid_gender", "请选择有效的孩子资料选项")
        return normalized

    def _json_list(self, value: object) -> str:
        if not isinstance(value, list):
            raise ApiError("invalid_interests", "兴趣信息格式不正确")
        return json.dumps([str(item).strip() for item in value if str(item).strip()], ensure_ascii=False)

    def _json_dict(self, value: object) -> str:
        if not isinstance(value, dict):
            raise ApiError("invalid_task_preferences", "任务偏好格式不正确")
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _validate_setting_key(self, key: str) -> None:
        if key not in SETTING_DEFAULTS:
            raise ApiError("setting_not_found", "设置不存在", 404)


def _setting_value(row, key: str) -> dict:
    if row is None:
        return dict(SETTING_DEFAULTS[key])
    try:
        value = json.loads(row["value"])
    except (TypeError, ValueError, json.JSONDecodeError):
        value = {}
    merged = dict(SETTING_DEFAULTS[key])
    if isinstance(value, dict):
        merged.update(value)
    return merged


def _daily_summary(total: int, completed: int, pending: int) -> str:
    if total == 0:
        return "今天还没有安排任务。"
    if pending:
        return "今天还有需要家长处理的记录。"
    if completed == total:
        return "今天的任务已经全部完成。"
    return "今天的任务正在记录中。"


def _daily_suggestion(total: int, completed: int, pending: int) -> str:
    if total == 0:
        return "可以先为今天添加一两件最重要的小任务。"
    if pending:
        return "先看一眼需要确认的记录，再决定是否写入成长记录。"
    if completed == total:
        return "今天节奏很稳定，晚些时候可以补充奖励或备注。"
    return "等任务到点后，系统会继续记录完成情况。"


def _weekly_summary(total: int, completed: int) -> str:
    if total == 0:
        return "本周还没有任务记录。"
    if completed == total:
        return "本周任务都已完成。"
    return f"本周完成 {completed} / {total} 项任务。"


def _legal_document(key: str) -> dict | None:
    documents = _content_json("legal_documents.json", {})
    return documents.get(key)


def _subscription_plans() -> list[dict]:
    return _content_json("subscription_plans.json", [])


def _subscription_entitlements() -> list[dict]:
    return _content_json("subscription_entitlements.json", [])


def _app_about() -> dict:
    return _content_json(
        "app_about.json",
        {
            "appName": "",
            "displayName": "",
            "version": "",
            "build": "",
            "description": "",
            "principles": [],
        },
    )


def _content_json(filename: str, fallback):
    path = CONTENT_ROOT / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
