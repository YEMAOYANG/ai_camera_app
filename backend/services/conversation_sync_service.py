from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path


log = logging.getLogger(__name__)

from core.database import Database
from core.security import now_ms
from repositories.device_repository import DeviceRepository
from services.conversation_policy_service import ConversationPolicyService
from services.voice_runtime_store import VoiceRuntimeStore


INTERACTION_PROFILE_SCHEMA = {
    "wakeName": "text",
    "fallbackWakeName": "text",
    "voiceStyle": "text",
    "boundaryLevel": "text",
    "freeChatEnabled": "bool",
    "freeChatSingleMinutes": "number",
    "freeChatDailyMinutes": "number",
    "homeworkModeRestricted": "bool",
    "bedtimeQuietEnabled": "bool",
    "bedtimeQuietAfter": "text",
    "childNickname": "text",
}


class ConversationSyncService:
    def __init__(self, database_url: str | Path):
        database = Database(database_url)
        self.device_repository = DeviceRepository(database)
        self.policy_service = ConversationPolicyService(database_url)

    def sync_family_conversation(self, *, family_id: str) -> dict | None:
        now = now_ms()
        with self.device_repository.transaction() as conn:
            device = self.device_repository.ensure_default_device(
                conn,
                family_id=family_id,
                now=now,
            )
            if device is None:
                return None
            rules = self.policy_service.get_rules(conn, family_id=family_id)
            profile = self.policy_service.build_interaction_profile(rules)
            wake_name = str(profile.get("wakeName") or "").strip()
            if wake_name:
                conn.execute(
                    "UPDATE devices SET wake_name = ?, updated_at = ? WHERE family_id = ? AND id = ?",
                    (wake_name, now, family_id, device["id"]),
                )
            runtime_row = self.device_repository.get_device_runtime_config(
                conn,
                family_id=family_id,
                device_id=device["id"],
            )
            config = self._runtime_config_json(runtime_row)
            config["interactionProfile"] = profile
            base_url = str(config.get("baseUrl") or os.getenv("AI_CAMERA_TEST_BASE_URL") or "").strip()
            if base_url:
                config["baseUrl"] = base_url
            provider = str(runtime_row["provider"] if runtime_row else "guardian_local").strip().lower()
            if provider in {"", "disabled"}:
                provider = "guardian_local"
            self.device_repository.upsert_device_runtime_config(
                conn,
                family_id=family_id,
                device_id=device["id"],
                provider=provider,
                config_json=json.dumps(config, ensure_ascii=False),
                secret_ref=str(runtime_row["secret_ref"] if runtime_row and runtime_row.get("secret_ref") else "") or None,
                status="active",
                now=now,
            )
            VoiceRuntimeStore.set_profile(
                family_id=family_id,
                device_id=device["id"],
                profile=profile,
            )
            base_url = str(config.get("baseUrl") or os.getenv("AI_CAMERA_TEST_BASE_URL") or "").strip()
            push_result = self._push_profile_to_ai_camera_test(profile, base_url=base_url)
            payload = {
                "deviceId": device["id"],
                "wakeName": wake_name,
                "interactionProfile": profile,
            }
            if push_result is not None:
                payload["aiCameraTestPush"] = push_result
            return payload

    def load_profile_for_device(self, *, family_id: str, device_id: str) -> dict:
        cached = VoiceRuntimeStore.get_profile(family_id=family_id, device_id=device_id)
        if cached:
            return cached
        with self.device_repository.transaction() as conn:
            rules = self.policy_service.get_rules(conn, family_id=family_id)
            profile = self.policy_service.build_interaction_profile(rules)
            runtime_row = self.device_repository.get_device_runtime_config(
                conn,
                family_id=family_id,
                device_id=device_id,
            )
            if runtime_row:
                config = self._runtime_config_json(runtime_row)
                stored = config.get("interactionProfile")
                if isinstance(stored, dict) and stored:
                    profile = {**stored, **profile}
            VoiceRuntimeStore.set_profile(
                family_id=family_id,
                device_id=device_id,
                profile=profile,
            )
            return profile

    def _runtime_config_json(self, runtime_row) -> dict:
        if not runtime_row:
            return {}
        raw = runtime_row.get("config_json")
        if isinstance(raw, dict):
            return dict(raw)
        try:
            parsed = json.loads(raw or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    def _push_profile_to_ai_camera_test(self, profile: dict, *, base_url: str) -> dict | None:
        enabled = str(os.getenv("VOICE_BRIDGE_PUSH_TO_AI_CAMERA_TEST", "1")).strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return None
        url_base = str(base_url or os.getenv("AI_CAMERA_TEST_BASE_URL") or "").strip().rstrip("/")
        if not url_base:
            return None
        payload = {
            "wakeName": profile.get("wakeName"),
            "fallbackWakeName": profile.get("fallbackWakeName"),
            "childNickname": profile.get("childNickname"),
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{url_base}/api/device/voice_profile",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5.0) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw or "{}")
                return {"ok": True, "baseUrl": url_base, "profile": parsed}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")[:240]
            log.warning("ai_camera_test voice profile push failed: %s %s", exc.code, detail)
            return {"ok": False, "baseUrl": url_base, "error": f"http_{exc.code}"}
        except Exception as exc:
            log.warning("ai_camera_test voice profile push failed: %s", exc)
            return {"ok": False, "baseUrl": url_base, "error": str(exc)[:240]}

