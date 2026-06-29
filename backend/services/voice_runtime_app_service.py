from __future__ import annotations

from pathlib import Path

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.device_repository import DeviceRepository
from services.auth_service import AuthService
from services.conversation_sync_service import ConversationSyncService
from services.voice_runtime_store import VoiceRuntimeStore


class VoiceRuntimeAppService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        sync_service: ConversationSyncService | None = None,
    ):
        self.auth_service = auth_service
        self.database = Database(database_url)
        self.device_repository = DeviceRepository(self.database)
        self.sync_service = sync_service or ConversationSyncService(database_url)

    def runtime_for_token(self, access_token: str, *, device_id: str | None = None) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        with self.database.transaction() as conn:
            resolved_device_id = self._resolve_device_id(conn, family_id=family_id, device_id=device_id)
        profile = self.sync_service.load_profile_for_device(
            family_id=family_id,
            device_id=resolved_device_id,
        )
        payload = VoiceRuntimeStore.runtime_payload(
            family_id=family_id,
            device_id=resolved_device_id,
        )
        voice = payload.get("voice") if isinstance(payload.get("voice"), dict) else {}
        voice["interactionProfile"] = profile
        voice["wakeName"] = str(profile.get("wakeName") or voice.get("wakeName") or "")
        payload["voice"] = voice
        payload["deviceId"] = resolved_device_id
        return payload

    def record_heartbeat(
        self,
        *,
        family_id: str,
        device_id: str,
        snapshot: dict,
        profile: dict,
        running: bool,
    ) -> None:
        if profile:
            VoiceRuntimeStore.set_profile(
                family_id=family_id,
                device_id=device_id,
                profile=profile,
            )
        VoiceRuntimeStore.update_snapshot(
            family_id=family_id,
            device_id=device_id,
            snapshot=snapshot,
            running=running,
        )

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
