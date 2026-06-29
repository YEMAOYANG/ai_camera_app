from __future__ import annotations

from pathlib import Path
import re

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.setup import SETUP_DONE
from repositories.device_repository import DeviceRepository
from repositories.setup_repository import SetupRepository
from schemas.auth import normalize_phone
from schemas.setup import setup_payload
from services.auth_service import AuthService
from services.conversation_sync_service import ConversationSyncService
from services.wake_name_validator import validate_wake_name


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

UNIQUE_GUARDIAN_IDENTITY_KEYS = {
    "mom",
    "dad",
    "maternal_grandpa",
    "maternal_grandma",
    "grandpa",
    "grandma",
}


class SetupService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        camera_command_service_factory=None,
    ):
        self.auth_service = auth_service
        self.camera_command_service_factory = camera_command_service_factory
        database = Database(database_url)
        self.database_url = database.database_url
        self.repository = SetupRepository(database)
        self.device_repository = DeviceRepository(database)

    def status(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        family_id = context["family"]["id"]
        user_id = context["user"]["id"]
        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=family_id,
                now=now,
            )
            progress = self._complete_lightweight_setup_if_ready(
                conn,
                family_id=family_id,
                progress=progress,
                now=now,
            )
            return self._response(
                progress,
                self._saved_setup_details(conn, family_id, user_id=user_id),
            )

    def save_parent_identity(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        raw_display_name = self._optional_text(data, "displayName")
        raw_relationship = self._optional_text(data, "relationship")
        raw_relationship_key = self._optional_text(data, "relationshipKey")
        raw_role = self._optional_text(data, "role")
        now = now_ms()
        with self.repository.transaction() as conn:
            relationship, relationship_key = self._guardian_identity_value(
                conn,
                relationship_key=raw_relationship_key,
                relationship=raw_relationship or raw_display_name,
            )
            role, role_label = self._family_role_value(conn, raw_role)
            self._assert_guardian_identity_available(
                conn,
                family_id=context["family"]["id"],
                relationship_key=relationship_key,
                exclude_parent_identity=True,
            )
            display_name = relationship
            self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self.repository.save_parent_identity(
                conn,
                family_id=context["family"]["id"],
                display_name=display_name,
                relationship=relationship,
                relationship_key=relationship_key,
                now=now,
            )
            self.repository.upsert_family_member_role(
                conn,
                family_id=context["family"]["id"],
                user_id=context["user"]["id"],
                name=display_name,
                relationship_key=relationship_key,
                phone=context["user"].get("phone") or "",
                role=role,
                now=now,
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="parent_identity_status",
                now=now,
            )
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            return self._response(
                progress,
                {
                    "parentIdentity": {
                        "displayName": display_name,
                        "relationship": relationship,
                        "relationshipKey": relationship_key,
                        "role": role,
                        "roleLabel": role_label,
                    },
                },
            )

    def save_device(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        binding_code = self._optional_text(data, "bindingCode")
        location = self._optional_text(data, "location")
        name = self._device_name(self._optional_text(data, "deviceName"), location)
        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self._require_setup_steps(progress, "parent_identity")
            existing_default = self.device_repository.ensure_default_device(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            if binding_code:
                global_existing = self.device_repository.find_active_device_by_binding_code_global(
                    conn,
                    binding_code=binding_code,
                )
                if global_existing and global_existing["family_id"] != context["family"]["id"]:
                    raise ApiError("device_already_bound", "这台设备已绑定到其他家庭。", 409)
            if progress.device_binding == SETUP_DONE and existing_default:
                existing_code = str(existing_default.get("binding_code") or "").strip()
                if binding_code and binding_code == existing_code:
                    return self._response(
                        progress,
                        {
                            "device": {
                                "id": existing_default["id"],
                                "name": existing_default["name"],
                                "status": existing_default["status"],
                            }
                        },
                    )
                raise ApiError(
                    "setup_device_already_bound",
                    "已绑定摄像头，请在设备管理中添加新设备。",
                    409,
                )
            device_id = self.repository.save_device(
                conn,
                family_id=context["family"]["id"],
                binding_code=binding_code,
                name=name,
                location=location,
                now=now,
            )
            self._ensure_default_wake_name(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                now=now,
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="device_binding_status",
                now=now,
            )
            if existing_default is None:
                self.device_repository.set_default_device(
                    conn,
                    family_id=context["family"]["id"],
                    device_id=device_id,
                    now=now,
                )
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            return self._response(progress, {"device": {"id": device_id, "name": name, "status": "bound"}})

    def save_wifi(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        ssid = self._required_text(data, "ssid", "请输入 Wi-Fi 名称")
        auth_type = self._optional_text(data, "authType") or "wpa2"
        password_set = bool((data.get("password") or "").strip())
        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self._require_setup_steps(progress, "parent_identity")
            self.repository.save_wifi(
                conn,
                family_id=context["family"]["id"],
                ssid=ssid,
                auth_type=auth_type,
                password_set=password_set,
                now=now,
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="wifi_status",
                now=now,
            )
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            return self._response(progress, {"wifi": {"ssid": ssid, "authType": auth_type, "passwordSet": password_set}})

    def save_child(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "name", "请输入孩子姓名")
        nickname = self._optional_text(data, "nickname")
        gender = self._gender(self._optional_text(data, "gender"))
        age_stage = self._optional_text(data, "ageStage")
        education_stage = self._optional_text(data, "educationStage")
        grade = self._optional_text(data, "grade")
        birthday = self._optional_text(data, "birthday")
        sleep_time = self._time_of_day(self._optional_text(data, "sleepTime"))
        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self._require_setup_steps(progress, "parent_identity")
            child_id = self.repository.save_child(
                conn,
                family_id=context["family"]["id"],
                name=name,
                nickname=nickname,
                gender=gender,
                age_stage=age_stage,
                education_stage=education_stage,
                grade=grade,
                birthday=birthday,
                sleep_time=sleep_time,
                now=now,
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="child_profile_status",
                now=now,
            )
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            progress = self._complete_lightweight_setup_if_ready(
                conn,
                family_id=context["family"]["id"],
                progress=progress,
                now=now,
            )
            return self._response(
                progress,
                {
                    "child": {
                        "id": child_id,
                        "name": name,
                        "nickname": nickname,
                        "gender": gender,
                        "birthday": birthday,
                        "sleepTime": sleep_time,
                        "ageStage": age_stage,
                        "educationStage": education_stage,
                        "grade": grade,
                    }
                },
            )

    def save_camera_name(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            wake_name = self._wake_name(
                data.get("wakeName"),
                family_names=self._guardian_identity_labels(conn),
            )
            progress = self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self._require_setup_steps(
                progress,
                "parent_identity",
                "child_profile",
            )
            default_device = self.device_repository.ensure_default_device(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            if default_device is None:
                raise ApiError("device_not_found", "请先绑定摄像头。", 404)
            device_id = self.repository.save_camera_name(
                conn,
                family_id=context["family"]["id"],
                device_id=default_device["id"],
                wake_name=wake_name,
                now=now,
            )
            ConversationSyncService(self.database_url).sync_family_conversation(
                family_id=context["family"]["id"],
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="camera_name_status",
                now=now,
            )
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            return self._response(
                progress,
                {"cameraName": {"wakeName": wake_name, "deviceId": device_id}},
            )

    def camera_name_intro(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        family_id = context["family"]["id"]
        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(conn, family_id=family_id, now=now)
            self._require_setup_steps(
                progress,
                "parent_identity",
                "device_binding",
                "child_profile",
            )
            if progress.camera_name_intro == "done":
                return self._response(
                    progress,
                    {
                        "broadcast": {
                            "played": False,
                            "status": "alreadyPlayed",
                            "message": "已经介绍过摄像头命名。",
                        }
                    },
                )

        command = self._speak_for_setup(
            family_id=family_id,
            text="你好呀，我是家里的 AI 看护助手。你可以给我起一个名字，以后叫这个名字，我就知道你在找我。",
        )
        status = "played" if command.get("status") == "succeeded" else "offline"
        message = (
            "摄像头已开始介绍自己。"
            if status == "played"
            else "摄像头暂时不在线，稍后可以再试听。"
        )

        with self.repository.transaction() as conn:
            intro_at = now_ms()
            self.repository.mark_camera_name_intro_attempt(
                conn,
                family_id=family_id,
                now=intro_at,
            )
            progress = self.repository.get_or_create_progress(conn, family_id=family_id, now=intro_at)
            return self._response(
                progress,
                {
                    "broadcast": {
                        "played": status == "played",
                        "status": status,
                        "message": message,
                    }
                },
            )

    def camera_name_preview(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now_ms(),
            )
            self._require_setup_steps(
                progress,
                "parent_identity",
                "device_binding",
                "child_profile",
            )
            wake_name = self._wake_name(
                data.get("wakeName"),
                family_names=self._guardian_identity_labels(conn),
                allow_fallback=True,
            )
        command = self._speak_for_setup(
            family_id=context["family"]["id"],
            text=f"你可以叫我{wake_name}。我听到这个名字，就知道你在找我。",
        )
        played = command.get("status") == "succeeded"
        return {
            "ok": True,
            "broadcast": {
                "played": played,
                "status": "played" if played else "offline",
                "message": "已播放试听。" if played else "摄像头暂时不在线，稍后可以再试听。",
            },
        }

    def save_contacts(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        raw_contacts = data.get("contacts")
        if not isinstance(raw_contacts, list) or not raw_contacts:
            raise ApiError("missing_contacts", "请至少添加一个紧急联系人")

        contacts: list[dict] = []
        for item in raw_contacts:
            if not isinstance(item, dict):
                raise ApiError("invalid_contact", "联系人信息格式不正确")
            contacts.append(
                {
                    "name": self._required_text(item, "name", "请输入联系人姓名"),
                    "phone": normalize_phone(item.get("phone", "")),
                    "relationship": self._optional_text(item, "relationship"),
                    "relationship_key": self._optional_text(item, "relationshipKey"),
                }
            )

        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self._require_setup_steps(
                progress,
                "parent_identity",
                "child_profile",
            )
            resolved_contacts = []
            for contact in contacts:
                relationship_source = contact["relationship"]
                if self._legacy_guardian_identity_key(relationship_source) == "family_default":
                    relationship_source = contact["name"]
                relationship, relationship_key = self._guardian_identity_value(
                    conn,
                    relationship_key=contact["relationship_key"],
                    relationship=relationship_source or contact["name"],
                    allow_legacy_fallback=True,
                )
                resolved_contacts.append(
                    {
                        **contact,
                        "relationship": relationship,
                        "relationship_key": relationship_key,
                    }
                )
            self._assert_contacts_have_available_guardian_identities(
                conn,
                family_id=context["family"]["id"],
                contacts=resolved_contacts,
            )
            contact_ids = self.repository.replace_contacts(
                conn,
                family_id=context["family"]["id"],
                contacts=resolved_contacts,
                now=now,
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="contacts_status",
                now=now,
            )
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            return self._response(progress, {"contacts": {"count": len(contact_ids), "ids": contact_ids}})

    def complete(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            if any(
                step != "done"
                for step in (
                    progress.parent_identity,
                    progress.child_profile,
                )
            ):
                raise ApiError("setup_incomplete", "请先完成家长身份和孩子资料")

            self.repository.complete_setup(conn, family_id=context["family"]["id"], now=now)
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now,
            )
            return self._response(progress)

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _response(self, progress, extra: dict | None = None) -> dict:
        payload = {"ok": True, "setup": setup_payload(progress)}
        if extra:
            payload.update(extra)
        return payload

    def _complete_lightweight_setup_if_ready(self, conn, *, family_id: str, progress, now: int):
        """V1 kindergarten setup only blocks on parent identity and child basics.

        Camera connection, Wi-Fi details, camera wake name, emergency contacts,
        and family role fine-tuning remain available after entering the app, but
        they no longer block the first app session.
        """
        if progress.completed:
            return progress
        if (
            progress.parent_identity == SETUP_DONE
            and progress.child_profile == SETUP_DONE
        ):
            self.repository.complete_setup(conn, family_id=family_id, now=now)
            return self.repository.get_or_create_progress(conn, family_id=family_id, now=now)
        return progress

    def _device_name(self, value: str | None, location: str | None) -> str:
        if value:
            return value
        if location:
            return f"{location}暖瞳摄像头"
        return "暖瞳摄像头"

    def _ensure_default_wake_name(self, conn, *, family_id: str, device_id: str, now: int) -> None:
        device = self.device_repository.get_device(
            conn,
            family_id=family_id,
            device_id=device_id,
        )
        if device is not None and device.get("wake_name"):
            return
        self.repository.save_camera_name(
            conn,
            family_id=family_id,
            device_id=device_id,
            wake_name="小暖",
            now=now,
        )

    def _require_setup_steps(self, progress, *steps: str) -> None:
        for step in steps:
            if getattr(progress, step) != "done":
                raise ApiError(
                    "setup_step_out_of_order",
                    "请按当前设置步骤继续完成。",
                    409,
                )

    def _saved_setup_details(self, conn, family_id: str, *, user_id: str | None = None) -> dict:
        parent = self.repository.get_parent_identity(conn, family_id=family_id)
        member = (
            self.repository.get_family_member_by_user(
                conn,
                family_id=family_id,
                user_id=user_id,
            )
            if user_id
            else None
        )
        device = self.repository.current_device(conn, family_id=family_id)
        wifi = self.repository.current_wifi(conn, family_id=family_id)
        child = self.repository.current_child(conn, family_id=family_id)
        return {
            "parentIdentity": None
            if parent is None
            else {
                "displayName": parent["display_name"],
                "relationship": parent["relationship"],
                "relationshipKey": self._relationship_key_for_parent_identity(
                    conn,
                    parent,
                ),
                "role": member["role"] if member else "",
                "roleLabel": self._family_role_label(conn, member["role"]) if member else "",
            },
            "device": None
            if device is None
            else {
                "id": device["id"],
                "name": device["name"],
                "location": device["location"] or "",
                "status": device["status"],
                "wakeName": device.get("wake_name") or "",
            },
            "wifi": None
            if wifi is None
            else {
                "ssid": wifi["ssid"],
                "authType": wifi["auth_type"],
                "passwordSet": bool(wifi["password_set"]),
            },
            "child": None
            if child is None
            else {
                "id": child["id"],
                "name": child["name"],
                "nickname": child["nickname"] or "",
                "gender": child.get("gender") or "unspecified",
                "ageStage": child["age_stage"] or "",
                "educationStage": child.get("education_stage") or "",
                "grade": child.get("grade") or "",
                "birthday": child["birthday"] or "",
                "sleepTime": child.get("sleep_time") or "",
            },
            "cameraName": None
            if device is None
            else {"wakeName": device.get("wake_name") or ""},
        }

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

    def _gender(self, value: str | None) -> str:
        normalized = value or "unspecified"
        if normalized not in {"male", "female", "unspecified"}:
            raise ApiError("invalid_gender", "请选择有效的孩子资料选项")
        return normalized

    def _time_of_day(self, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split(":")
        if len(parts) != 2:
            raise ApiError("invalid_time", "请输入有效时间，例如 21:00")
        hour = int(parts[0]) if parts[0].isdigit() else None
        minute = int(parts[1]) if parts[1].isdigit() else None
        if hour is None or minute is None or hour > 23 or minute > 59:
            raise ApiError("invalid_time", "请输入有效时间，例如 21:00")
        return f"{hour:02d}:{minute:02d}"

    def _guardian_identity_labels(self, conn) -> set[str]:
        return {
            row["label"]
            for row in self.repository.list_app_option_items(
                conn,
                catalog_key="guardian_identity_label",
            )
            if row["label"]
        }

    def _family_role_value(self, conn, value: str | None) -> tuple[str, str]:
        rows = self.repository.list_app_option_items(
            conn,
            catalog_key="family_role",
        )
        requested = (value or "admin").strip() or "admin"
        for row in rows:
            if row["item_key"] == requested or row["label"] == requested:
                return row["item_key"], row["label"]
        raise ApiError("invalid_family_role", "请选择有效的家庭权限")

    def _family_role_label(self, conn, role: str) -> str:
        for row in self.repository.list_app_option_items(
            conn,
            catalog_key="family_role",
        ):
            if row["item_key"] == role:
                return row["label"]
        return role

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

    def _legacy_guardian_identity_key(self, value: str | None) -> str:
        if not value:
            return ""
        return LEGACY_GUARDIAN_IDENTITY_KEYS.get(value.strip().lower(), "")

    def _relationship_key_for_parent_identity(self, conn, parent) -> str:
        current = parent.get("relationship_key") or ""
        if current:
            return current
        relationship = parent.get("relationship") or ""
        if not relationship:
            return ""
        for row in self.repository.list_app_option_items(
            conn,
            catalog_key="guardian_identity_label",
        ):
            if row["item_key"] == relationship or row["label"] == relationship:
                return row["item_key"]
        return ""

    def _assert_contacts_have_available_guardian_identities(
        self,
        conn,
        *,
        family_id: str,
        contacts: list[dict],
    ) -> None:
        seen: set[str] = set()
        for contact in contacts:
            relationship_key = contact.get("relationship_key") or ""
            if relationship_key not in UNIQUE_GUARDIAN_IDENTITY_KEYS:
                continue
            if relationship_key in seen:
                self._raise_duplicate_guardian_identity(conn, relationship_key)
            seen.add(relationship_key)

    def _assert_guardian_identity_available(
        self,
        conn,
        *,
        family_id: str,
        relationship_key: str,
        exclude_parent_identity: bool = False,
    ) -> None:
        if relationship_key not in UNIQUE_GUARDIAN_IDENTITY_KEYS:
            return
        if not exclude_parent_identity:
            parent = self.repository.get_parent_identity(conn, family_id=family_id)
            if parent and self._relationship_key_for_parent_identity(conn, parent) == relationship_key:
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

    def _wake_name(
        self,
        value: object,
        *,
        family_names: set[str],
        allow_fallback: bool = False,
    ) -> str:
        return validate_wake_name(
            value,
            family_names=family_names,
            allow_fallback=allow_fallback,
        )

    def _speak_for_setup(self, *, family_id: str, text: str) -> dict:
        if self.camera_command_service_factory is None:
            return {"status": "failed", "message": "摄像头暂时不在线，稍后可以再试听。"}
        return self.camera_command_service_factory().internal_speak(
            family_id=family_id,
            text=text,
        )
