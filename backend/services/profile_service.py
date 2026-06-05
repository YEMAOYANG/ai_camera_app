from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.profile_repository import ProfileRepository
from schemas.auth import normalize_phone
from schemas.profile import (
    account_profile_payload,
    account_security_payload,
    child_profile_payload,
    emergency_contact_payload,
    family_invitation_payload,
    family_member_payload,
    feedback_payload,
    setting_payload,
)
from services.auth_service import AuthService


MEMBER_ROLES = {"admin", "guardian", "caregiver", "viewer"}
MEMBER_STATUSES = {"active", "invited", "disabled"}
INVITATION_TTL_MS = 7 * 24 * 60 * 60 * 1000
CONTENT_ROOT = Path(__file__).resolve().parents[1] / "content"

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
            self.repository.ensure_owner_member(
                conn,
                family_id=family["id"],
                user_id=user["id"],
                name=user["display_name"],
                phone=user["phone"],
                now=now,
            )
            members = self.repository.list_family_members(conn, family_id=family["id"])
            child = self.repository.current_child(conn, family_id=family["id"])
            profile = self.repository.get_parent_identity(conn, family_id=family["id"])
            return {
                "ok": True,
                "summary": {
                    "spaceTitle": "家庭看护空间",
                    "familyId": family["id"],
                    "familyName": family["name"],
                    "displayName": user["display_name"],
                    "phone": user["phone"],
                    "role": "admin",
                    "roleLabel": "管理员",
                    "relationship": profile["relationship"] if profile else "",
                    "memberCount": len(members),
                    "deviceCount": self.repository.count_devices(conn, family_id=family["id"]),
                    "pendingItemCount": self.repository.count_pending_items(
                        conn,
                        family_id=family["id"],
                    ),
                    "child": child_profile_payload(child),
                },
            }

    def list_family_members(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            self.repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=user["id"],
                name=user["display_name"],
                phone=user["phone"],
                now=now,
            )
            rows = self.repository.list_family_members(conn, family_id=context["family"]["id"])
            return {"ok": True, "members": [family_member_payload(row) for row in rows]}

    def create_family_member(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "name", "请输入成员姓名")
        role = self._member_role(self._optional_text(data, "role") or "guardian")
        status = self._member_status(self._optional_text(data, "status") or "active")
        phone = self._optional_phone(data.get("phone"))
        now = now_ms()
        with self.repository.transaction() as conn:
            member = self.repository.create_family_member(
                conn,
                family_id=context["family"]["id"],
                name=name,
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
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入成员姓名")
        if "phone" in data:
            fields["phone"] = self._optional_phone(data.get("phone"))
        if "role" in data:
            fields["role"] = self._member_role(str(data["role"]))
        if "status" in data:
            fields["status"] = self._member_status(str(data["status"]))
        if "notifyEnabled" in data:
            fields["notify_enabled"] = int(bool(data["notifyEnabled"]))
        with self.repository.transaction() as conn:
            member = self._member_or_error(conn, context["family"]["id"], member_id)
            if member["user_id"] == context["user"]["id"] and fields.get("role") not in {None, "admin"}:
                raise ApiError("cannot_downgrade_self", "不能降低当前管理员自己的权限")
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
            member = self._member_or_error(conn, context["family"]["id"], member_id)
            if member["user_id"] == context["user"]["id"]:
                raise ApiError("cannot_remove_self", "不能移除当前登录的管理员")
            self.repository.delete_family_member(
                conn,
                family_id=context["family"]["id"],
                member_id=member_id,
            )
            return {"ok": True}

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
        name = self._required_text(data, "name", "请输入成员称呼")
        phone = self._required_phone(data.get("phone"))
        role = self._member_role(self._optional_text(data, "role") or "guardian")
        now = now_ms()
        with self.repository.transaction() as conn:
            invitation = self.repository.create_family_invitation(
                conn,
                family_id=context["family"]["id"],
                name=name,
                phone=phone,
                role=role,
                created_by=context["user"]["id"],
                now=now,
                expires_at=now + INVITATION_TTL_MS,
            )
            return {"ok": True, "invitation": family_invitation_payload(invitation)}

    def resend_family_invitation(self, access_token: str, invitation_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
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
                fields={"created_at": now, "expires_at": now + INVITATION_TTL_MS},
                now=now,
            )
            return {"ok": True, "invitation": family_invitation_payload(invitation)}

    def cancel_family_invitation(self, access_token: str, invitation_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._invitation_or_error(conn, context["family"]["id"], invitation_id)
            invitation = self.repository.update_family_invitation(
                conn,
                family_id=context["family"]["id"],
                invitation_id=invitation_id,
                fields={"status": "cancelled"},
                now=now,
            )
            return {"ok": True, "invitation": family_invitation_payload(invitation)}

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
            "birthday": "birthday",
            "ageStage": "age_stage",
            "educationStage": "education_stage",
            "grade": "grade",
            "schoolName": "school_name",
        }
        for key, column in mapping.items():
            if key in data:
                fields[column] = (
                    self._required_text(data, key, "请输入孩子姓名")
                    if key == "name"
                    else self._optional_text(data, key)
                )
        if "interests" in data:
            fields["interests"] = self._json_list(data["interests"])
        if "taskPreferences" in data:
            fields["task_preferences"] = self._json_dict(data["taskPreferences"])
        now = now_ms()
        with self.repository.transaction() as conn:
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
            return {"ok": True, "contacts": [emergency_contact_payload(row) for row in rows]}

    def create_contact(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "name", "请输入联系人姓名")
        phone = normalize_phone(str(data.get("phone") or ""))
        relationship = self._optional_text(data, "relationship")
        now = now_ms()
        with self.repository.transaction() as conn:
            contact = self.repository.create_contact(
                conn,
                family_id=context["family"]["id"],
                name=name,
                phone=phone,
                relationship=relationship,
                default_notify=bool(data.get("defaultNotify", True)),
                now=now,
            )
            return {"ok": True, "contact": emergency_contact_payload(contact)}

    def update_contact(self, access_token: str, contact_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入联系人姓名")
        if "phone" in data:
            fields["phone"] = normalize_phone(str(data.get("phone") or ""))
        if "relationship" in data:
            fields["relationship"] = self._optional_text(data, "relationship")
        if "defaultNotify" in data:
            fields["default_notify"] = int(bool(data["defaultNotify"]))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._contact_or_error(conn, context["family"]["id"], contact_id)
            contact = self.repository.update_contact(
                conn,
                family_id=context["family"]["id"],
                contact_id=contact_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "contact": emergency_contact_payload(contact)}

    def delete_contact(self, access_token: str, contact_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
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
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            parent_identity = self.repository.get_parent_identity(conn, family_id=family["id"])
            return {"ok": True, "profile": account_profile_payload(user, family, parent_identity)}

    def update_account_profile(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        display_name = self._optional_text(data, "displayName")
        family_name = self._optional_text(data, "familyName")
        relationship = self._optional_text(data, "relationship")
        now = now_ms()
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            family = self._family_or_error(conn, context["family"]["id"])
            user = self.repository.update_user_profile(conn, user_id=user["id"], display_name=display_name)
            family = self.repository.update_family_name(conn, family_id=family["id"], name=family_name)
            parent_identity = self.repository.get_parent_identity(conn, family_id=family["id"])
            if relationship is not None:
                parent_identity = self.repository.upsert_parent_identity(
                    conn,
                    family_id=family["id"],
                    display_name=display_name or user["display_name"],
                    relationship=relationship,
                    now=now,
                )
            self.repository.ensure_owner_member(
                conn,
                family_id=family["id"],
                user_id=user["id"],
                name=user["display_name"],
                phone=user["phone"],
                now=now,
            )
            return {"ok": True, "profile": account_profile_payload(user, family, parent_identity)}

    def account_security(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            user = self._user_or_error(conn, context["user"]["id"])
            sessions = self.repository.list_sessions(conn, user_id=user["id"])
            return {"ok": True, "security": account_security_payload(user, sessions)}

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
        self._auth_context(access_token)
        plan_id = self._optional_text(data, "planId")
        plan = next((item for item in _subscription_plans() if item["id"] == plan_id), None)
        if plan is None or plan["id"] == "basic":
            raise ApiError("invalid_subscription_plan", "套餐不可开通", 400)
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
        self._auth_context(access_token)
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

    def _member_role(self, value: str) -> str:
        value = value.strip()
        if value not in MEMBER_ROLES:
            raise ApiError("invalid_member_role", "成员角色不支持")
        return value

    def _member_status(self, value: str) -> str:
        value = value.strip()
        if value not in MEMBER_STATUSES:
            raise ApiError("invalid_member_status", "成员状态不支持")
        return value

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
