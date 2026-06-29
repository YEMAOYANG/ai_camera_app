from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.device_repository import DeviceRepository
from services.auth_service import AuthService
from services.conversation_policy_service import ConversationPolicyService
from services.conversation_sync_service import ConversationSyncService
from services.voice_conversation_service import VoiceConversationService
from services.voice_wake_service import match_wake_names, wake_ack_text


class ConversationAppService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        conversation_service: VoiceConversationService | None = None,
        policy_service: ConversationPolicyService | None = None,
        sync_service: ConversationSyncService | None = None,
    ):
        self.auth_service = auth_service
        self.database = Database(database_url)
        self.device_repository = DeviceRepository(self.database)
        self.policy_service = policy_service or ConversationPolicyService(database_url)
        self.conversation_service = conversation_service or VoiceConversationService(database_url)
        self.sync_service = sync_service or ConversationSyncService(database_url)

    def policy_for_token(self, access_token: str, *, device_id: str | None = None) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
            payload = self.policy_service.policy_payload(
                conn,
                family_id=family_id,
                device_id=resolved_device_id,
            )
            sync = self.sync_service.load_profile_for_device(
                family_id=family_id,
                device_id=resolved_device_id,
            )
            payload["interactionProfile"] = sync
            payload["synced"] = bool(sync.get("wakeName"))
            return {"ok": True, "policy": payload}

    def chat_for_token(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        text = str(data.get("text") or "").strip()
        if not text:
            raise ApiError("missing_text", "请输入对话内容。")
        device_id = self._optional_text(data, "deviceId")
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
            profile = self.sync_service.load_profile_for_device(
                family_id=family_id,
                device_id=resolved_device_id,
            )
            evaluation = self.policy_service.evaluate_chat_turn(conn, family_id=family_id)
            if evaluation["allowed"]:
                active = self.policy_service.conversation_repository.active_session(
                    conn,
                    family_id=family_id,
                    session_type="free_chat",
                )
                if active is None:
                    self.policy_service.start_free_chat_session(
                        conn,
                        family_id=family_id,
                        device_id=resolved_device_id,
                        session_id=f"cs_{uuid4().hex}",
                    )
            result = self.conversation_service.reply(
                conn,
                family_id=family_id,
                device_id=resolved_device_id,
                text=text,
                profile=profile,
            )
            if not result.get("allowed"):
                self.policy_service.end_active_free_chat_session(conn, family_id=family_id)
            return result

    def sync_after_conversation_update(self, *, family_id: str) -> dict | None:
        return self.sync_service.sync_family_conversation(family_id=family_id)

    def internal_profile(self, *, family_id: str, device_id: str | None = None) -> dict:
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
        profile = self.sync_service.load_profile_for_device(
            family_id=family_id,
            device_id=resolved_device_id,
        )
        return {
            "ok": True,
            "familyId": family_id,
            "deviceId": resolved_device_id,
            "interactionProfile": profile,
        }

    def internal_wake_evaluate(
        self,
        *,
        family_id: str,
        device_id: str | None,
        text: str,
        require_confirmation: bool = True,
    ) -> dict:
        heard = str(text or "").strip()
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
            profile = self.sync_service.load_profile_for_device(
                family_id=family_id,
                device_id=resolved_device_id,
            )
        wake_match = match_wake_names(
            heard,
            str(profile.get("wakeName") or ""),
            str(profile.get("fallbackWakeName") or ""),
            require_confirmation=require_confirmation,
        )
        wake_name = str(wake_match.get("name") or profile.get("wakeName") or "")
        return {
            "ok": True,
            "familyId": family_id,
            "deviceId": resolved_device_id,
            "text": heard,
            "wakeMatch": wake_match,
            "matched": bool(wake_match.get("matched")),
            "ackText": wake_ack_text(wake_name) if wake_match.get("matched") else "",
            "interactionProfile": profile,
        }

    def internal_chat(
        self,
        *,
        family_id: str,
        device_id: str | None,
        text: str,
    ) -> dict:
        command = str(text or "").strip()
        if not command:
            raise ApiError("missing_text", "请输入对话内容。")
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
            profile = self.sync_service.load_profile_for_device(
                family_id=family_id,
                device_id=resolved_device_id,
            )
            evaluation = self.policy_service.evaluate_chat_turn(conn, family_id=family_id)
            if evaluation["allowed"]:
                active = self.policy_service.conversation_repository.active_session(
                    conn,
                    family_id=family_id,
                    session_type="free_chat",
                )
                if active is None:
                    self.policy_service.start_free_chat_session(
                        conn,
                        family_id=family_id,
                        device_id=resolved_device_id,
                        session_id=f"cs_{uuid4().hex}",
                    )
            result = self.conversation_service.reply(
                conn,
                family_id=family_id,
                device_id=resolved_device_id,
                text=command,
                profile=profile,
            )
            if not result.get("allowed"):
                self.policy_service.end_active_free_chat_session(conn, family_id=family_id)
            return {
                **result,
                "familyId": family_id,
                "deviceId": resolved_device_id,
            }

    def internal_end_session(self, *, family_id: str, device_id: str | None = None) -> dict:
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
            duration = self.policy_service.end_active_free_chat_session(conn, family_id=family_id)
            return {
                "ok": True,
                "familyId": family_id,
                "deviceId": resolved_device_id,
                "ended": duration >= 0,
                "durationSeconds": duration,
            }

    def _resolve_device_id(self, conn, *, family_id: str, device_id: str | None) -> str:
        if device_id:
            device = self.device_repository.get_device(
                conn,
                family_id=family_id,
                device_id=device_id,
            )
            if device is None:
                raise ApiError("device_not_found", "设备不存在", 404)
            return device_id
        device = self.device_repository.ensure_default_device(
            conn,
            family_id=family_id,
            now=now_ms(),
        )
        if device is None:
            raise ApiError("device_not_found", "请先绑定摄像头。", 404)
        return device["id"]

    def _optional_text(self, data: dict, key: str) -> str | None:
        value = str(data.get(key) or "").strip()
        return value or None
