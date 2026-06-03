from __future__ import annotations

from pathlib import Path

from core.database import SQLiteDatabase
from core.errors import ApiError
from core.security import now_ms
from repositories.setup_repository import SetupRepository
from schemas.auth import normalize_phone
from schemas.setup import setup_payload
from services.auth_service import AuthService


class SetupService:
    def __init__(
        self,
        db_path: str | Path,
        *,
        auth_service: AuthService,
    ):
        self.auth_service = auth_service
        self.repository = SetupRepository(SQLiteDatabase(db_path))

    def status(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            progress = self.repository.get_or_create_progress(
                conn,
                family_id=context["family"]["id"],
                now=now_ms(),
            )
            return self._response(progress)

    def save_parent_identity(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        display_name = self._required_text(data, "displayName", "请输入家长称呼")
        relationship = self._required_text(data, "relationship", "请选择家长身份")
        now = now_ms()
        with self.repository.transaction() as conn:
            self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            self.repository.save_parent_identity(
                conn,
                family_id=context["family"]["id"],
                display_name=display_name,
                relationship=relationship,
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
            return self._response(progress, {"parentIdentity": {"displayName": display_name, "relationship": relationship}})

    def save_device(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "deviceName", "请输入设备名称")
        binding_code = self._optional_text(data, "bindingCode")
        location = self._optional_text(data, "location")
        now = now_ms()
        with self.repository.transaction() as conn:
            self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            device_id = self.repository.save_device(
                conn,
                family_id=context["family"]["id"],
                binding_code=binding_code,
                name=name,
                location=location,
                now=now,
            )
            self.repository.mark_step_done(
                conn,
                family_id=context["family"]["id"],
                column="device_binding_status",
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
            self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
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
        age_stage = self._optional_text(data, "ageStage")
        birthday = self._optional_text(data, "birthday")
        now = now_ms()
        with self.repository.transaction() as conn:
            self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            child_id = self.repository.save_child(
                conn,
                family_id=context["family"]["id"],
                name=name,
                nickname=nickname,
                age_stage=age_stage,
                birthday=birthday,
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
            return self._response(progress, {"child": {"id": child_id, "name": name, "nickname": nickname, "ageStage": age_stage}})

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
                }
            )

        now = now_ms()
        with self.repository.transaction() as conn:
            self.repository.get_or_create_progress(conn, family_id=context["family"]["id"], now=now)
            contact_ids = self.repository.replace_contacts(
                conn,
                family_id=context["family"]["id"],
                contacts=contacts,
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
                    progress.device_binding,
                    progress.wifi,
                    progress.child_profile,
                    progress.contacts,
                )
            ):
                raise ApiError("setup_incomplete", "请先完成所有首次设置步骤")

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
