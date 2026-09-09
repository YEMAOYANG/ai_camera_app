from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from core.database import Database
from core.errors import ApiError
from core.security import hash_value, new_token, now_ms
from integrations.hardware.base import HardwareDeviceAdapter
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from integrations.onvif.client import (
    OnvifAuthenticationError,
    OnvifClient,
    OnvifClientError,
    OnvifProtocolError,
    RtspAuthenticationError,
    RtspUnavailableError,
)
from integrations.onvif.identity import onvif_binding_code
from repositories.device_repository import DeviceRepository
from schemas.devices import device_payload, device_runtime_config_payload, runtime_config_json
from schemas.profile import role_capabilities_from_option
from services.auth_service import AuthService
from services.camera_bridge_service import CameraBridgeService
from services.conversation_sync_service import ConversationSyncService
from services.device_credential_store import EncryptedFileCredentialStore
from services.onvif_runtime_config import build_onvif_runtime_config
from services.device_runtime_resolver import (
    DeviceRuntimeResolver,
    onvif_preview_stream_name,
)

FALLBACK_ROLE_CAPABILITIES = {
    "admin": ["manage_devices"],
    "guardian": [],
    "viewer": [],
}

RUNTIME_PROVIDERS = {
    "disabled",
    "mock",
    "ai_camera_test",
    "guardian_local",
    "onvif_rtsp",
    "future_hardware",
    "self_owned_camera",
}
DEVELOPMENT_RUNTIME_PROVIDERS = {"mock", "ai_camera_test", "guardian_local"}
RESERVED_RUNTIME_PROVIDERS = {"future_hardware", "self_owned_camera"}
ONVIF_RUNTIME_PRIVATE_KEYS = {
    "deviceServiceUrl",
    "endpointReference",
    "hardwareId",
    "profileToken",
    "previewProfileToken",
    "previewStreamProfile",
    "previewVideoEncoding",
    "previewWidth",
    "previewHeight",
}
SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "apikey",
    "api_key",
    "accesskey",
    "access_key",
    "authorization",
    "cookie",
    "privatekey",
    "private_key",
    "certificate",
    "credential",
)
SENSITIVE_VALUE_MARKERS = (
    "-----begin",
    "bearer ",
    "password=",
    "passwd=",
    "token=",
    "api_key=",
    "apikey=",
    "secret=",
    "authorization:",
    "set-cookie:",
    "private key",
)
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

SPEAKER_CAPABILITIES_SCHEMA = {
    "enabled": "bool",
    "duplex": "bool",
    "volume": "number",
}
RUNTIME_CONFIG_SCHEMAS = {
    "disabled": {},
    "mock": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "interactionProfile": INTERACTION_PROFILE_SCHEMA,
    },
    "guardian_local": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "interactionProfile": INTERACTION_PROFILE_SCHEMA,
    },
    "ai_camera_test": {
        "baseUrl": "url",
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "interactionProfile": INTERACTION_PROFILE_SCHEMA,
    },
    "onvif_rtsp": {
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "deviceProfile": {
            "manufacturer": "text",
            "model": "text",
            "firmwareVersion": "text",
            "serialNumber": "text",
        },
    },
    "future_hardware": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "deviceProfile": {
            "model": "text",
            "region": "text",
            "firmwareChannel": "text",
        },
    },
    "self_owned_camera": {
        "adapterName": "text",
        "streamProfile": "text",
        "speakerCapabilities": SPEAKER_CAPABILITIES_SCHEMA,
        "deviceProfile": {
            "model": "text",
            "region": "text",
            "firmwareChannel": "text",
        },
    },
}


class DeviceService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        hardware_adapter: HardwareDeviceAdapter | None = None,
        camera_service: CameraBridgeService | None = None,
        runtime_resolver: DeviceRuntimeResolver | None = None,
        onvif_client: OnvifClient | None = None,
        credential_store: EncryptedFileCredentialStore | None = None,
        onvif_discovery_ttl_seconds: int = 90,
        onvif_supported_manufacturers: tuple[str, ...] = ("vatilon",),
        onvif_supported_models: tuple[str, ...] = ("t62",),
        onvif_bootstrap_credentials_enabled: bool = False,
        onvif_bootstrap_username: str = "",
        onvif_bootstrap_password: str = "",
        app_env: str = "production",
        dev_adapters_enabled: bool = False,
    ):
        self.auth_service = auth_service
        database = Database(database_url)
        self.database_url = database.database_url
        self.repository = DeviceRepository(database)
        self.hardware_adapter = hardware_adapter or DisabledHardwareDeviceAdapter()
        self.camera_service = camera_service
        self.runtime_resolver = runtime_resolver
        self.onvif_client = onvif_client
        self.credential_store = credential_store
        self.onvif_discovery_ttl_seconds = max(15, min(int(onvif_discovery_ttl_seconds), 300))
        self.onvif_supported_manufacturers = tuple(
            str(value or "").strip().lower()
            for value in onvif_supported_manufacturers
            if str(value or "").strip()
        )
        self.onvif_supported_models = tuple(
            str(value or "").strip().lower()
            for value in onvif_supported_models
            if str(value or "").strip()
        )
        self.onvif_bootstrap_credentials_enabled = bool(
            onvif_bootstrap_credentials_enabled
        )
        self.onvif_bootstrap_username = str(
            onvif_bootstrap_username or ""
        ).strip()
        self.onvif_bootstrap_password = str(onvif_bootstrap_password or "")
        self.app_env = str(app_env or "production").strip().lower()
        self.dev_adapters_enabled = bool(dev_adapters_enabled)

    def list_devices(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self.repository.ensure_default_device(
                conn,
                family_id=context["family"]["id"],
                now=now_ms(),
            )
            rows = self.repository.list_devices(conn, family_id=context["family"]["id"])
            return {"ok": True, "devices": [device_payload(row) for row in rows]}

    def bind_device(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        binding_code = self._required_text(data, "bindingCode", "请输入设备绑定码")
        name = (
            self._optional_text(data, "name")
            or self._optional_text(data, "deviceName")
            or "小守"
        )
        location = self._optional_text(data, "location")
        set_as_default = bool(data.get("setAsDefault"))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            family_id = context["family"]["id"]
            global_existing = self.repository.find_active_device_by_binding_code_global(
                conn,
                binding_code=binding_code,
            )
            if global_existing and global_existing["family_id"] != family_id:
                raise ApiError("device_already_bound", "这台设备已绑定到其他家庭。", 409)
            existing = self.repository.find_active_device_by_binding_code(
                conn,
                family_id=family_id,
                binding_code=binding_code,
            )
            duplicate = existing is not None
            if existing:
                device = self.repository.get_device(
                    conn,
                    family_id=family_id,
                    device_id=existing["id"],
                )
            else:
                unbound = self.repository.find_unbound_device_by_binding_code(
                    conn,
                    family_id=family_id,
                    binding_code=binding_code,
                )
                if unbound:
                    device = self.repository.rebind_device(
                        conn,
                        family_id=family_id,
                        device_id=unbound["id"],
                        name=name,
                        location=location,
                        now=now,
                    )
                else:
                    device = self.repository.create_device(
                        conn,
                        family_id=family_id,
                        binding_code=binding_code,
                        name=name,
                        location=location,
                        now=now,
                    )
            default_device = self.repository.get_default_device(conn, family_id=family_id)
            if device and (set_as_default or default_device is None):
                default_device = self.repository.set_default_device(
                    conn,
                    family_id=family_id,
                    device_id=device["id"],
                    now=now,
                )
                device = self.repository.get_device(
                    conn,
                    family_id=family_id,
                    device_id=device["id"],
                )
            response = {
                "ok": True,
                "duplicate": duplicate,
                "device": device_payload(device),
                "defaultDevice": device_payload(default_device) if default_device else None,
            }
        ConversationSyncService(self.database_url).sync_family_conversation(
            family_id=family_id,
        )
        return response

    def get_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            return {"ok": True, "device": device_payload(device)}

    def default_device(self, access_token: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self.repository.ensure_default_device(
                conn,
                family_id=context["family"]["id"],
                now=now_ms(),
            )
            return {"ok": True, "device": device_payload(device) if device else None}

    def discovery_status(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        raw_candidates = data.get("candidates")
        if raw_candidates is None and isinstance(data.get("bindingCodes"), list):
            raw_candidates = [
                {"id": str(code), "bindingCode": code}
                for code in data.get("bindingCodes", [])
            ]
        if not isinstance(raw_candidates, list):
            raise ApiError("invalid_discovery_candidates", "请选择要检查的摄像头", 400)
        candidates = raw_candidates[:20]
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            family_id = context["family"]["id"]
            results = [
                self._discovery_candidate_status(conn, family_id, item)
                for item in candidates
                if isinstance(item, Mapping)
            ]
            return {"ok": True, "candidates": results}

    def discover_onvif(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        client = self._onvif_client_or_error()
        target_ip = self._optional_text(data, "targetIp")
        timeout_ms = _onvif_discovery_timeout_ms(data.get("timeoutMs"))
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
        try:
            discovered = client.discover(
                target_ip=target_ip,
                timeout_ms=timeout_ms,
            )
        except OnvifProtocolError as exc:
            raise ApiError("invalid_onvif_target", str(exc), 400) from exc
        except OnvifClientError as exc:
            raise ApiError(
                "onvif_discovery_unavailable",
                "暂时无法搜索附近摄像头，请确认手机与设备连接同一网络。",
                503,
            ) from exc
        now = now_ms()
        expires_at = now + self.onvif_discovery_ttl_seconds * 1000
        family_id = context["family"]["id"]
        user_id = context["user"]["id"]
        response_candidates: list[dict] = []
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self.repository.delete_expired_onvif_discovery_sessions(
                conn,
                before=now - 86_400_000,
            )
            for candidate in discovered:
                if not self._onvif_candidate_supported(
                    candidate,
                    allow_unknown=bool(target_ip),
                ):
                    continue
                identity = candidate.endpoint_reference or candidate.device_service_url
                binding_code = onvif_binding_code(identity)
                existing = self.repository.find_active_device_by_binding_code_global(
                    conn,
                    binding_code=binding_code,
                )
                if existing is not None:
                    continue
                token = new_token("onvif_discovery")
                metadata = {
                    "deviceServiceUrl": candidate.device_service_url,
                    "endpointReference": candidate.endpoint_reference,
                    "displayName": candidate.display_name,
                    "manufacturerHint": candidate.manufacturer_hint,
                    "modelHint": candidate.model_hint,
                }
                self.repository.create_onvif_discovery_session(
                    conn,
                    token_hash=hash_value(token),
                    family_id=family_id,
                    user_id=user_id,
                    binding_code=binding_code,
                    metadata_json=json.dumps(
                        metadata,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    expires_at=expires_at,
                    now=now,
                )
                response_candidates.append(
                    {
                        "id": binding_code,
                        "discoveryToken": token,
                        "deviceUniqueId": binding_code,
                        "serialNumber": None,
                        "manufacturer": candidate.manufacturer_hint,
                        "model": candidate.model_hint,
                        "displayName": candidate.display_name or "AI 看护摄像头",
                        "requiresCredentials": (
                            not self._onvif_bootstrap_credentials_available()
                        ),
                        "supported": True,
                        "bindingState": "available",
                        "capabilities": {
                            "onvif": True,
                            "rtsp": True,
                            "ptz": False,
                            "audio": any(
                                "audio_encoder" in scope.lower()
                                for scope in candidate.scopes
                            ),
                        },
                        "expiresAt": expires_at,
                    }
                )
        return {"ok": True, "candidates": response_candidates}

    def pair_onvif(self, access_token: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        client = self._onvif_client_or_error()
        credential_store = self._credential_store_or_error()
        discovery_token = self._required_text(
            data,
            "discoveryToken",
            "设备发现信息已失效，请重新搜索。",
        )
        if len(discovery_token) > 512:
            raise ApiError(
                "onvif_discovery_token_invalid",
                "设备发现信息无效，请重新搜索。",
                400,
            )
        username, password = self._onvif_pairing_credentials(data)
        if len(username) > 128 or len(password) > 512:
            raise ApiError("invalid_onvif_credentials", "摄像头账号或密码格式不正确。", 400)
        family_id = context["family"]["id"]
        user_id = context["user"]["id"]
        now = now_ms()
        token_hash = hash_value(discovery_token)

        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            session = self._onvif_session_or_error(
                conn,
                token_hash=token_hash,
                family_id=family_id,
                user_id=user_id,
                now=now,
            )
            existing = self.repository.find_active_device_by_binding_code_global(
                conn,
                binding_code=session["binding_code"],
            )
            if existing is not None:
                raise ApiError("device_already_bound", "这台设备已经添加。", 409)
            metadata = _onvif_session_metadata(session)

        try:
            verified = client.inspect_and_verify(
                device_service_url=str(metadata["deviceServiceUrl"]),
                username=username,
                password=password,
            )
        except (OnvifAuthenticationError, RtspAuthenticationError) as exc:
            raise ApiError(
                "onvif_auth_failed",
                "摄像头账号或密码不正确。",
                422,
            ) from exc
        except RtspUnavailableError as exc:
            raise ApiError(
                "onvif_rtsp_unavailable",
                "摄像头视频流暂时不可用。",
                422,
            ) from exc
        except OnvifProtocolError as exc:
            raise ApiError(
                "onvif_capability_unsupported",
                "这台摄像头缺少所需的 ONVIF 视频能力。",
                422,
            ) from exc
        except OnvifClientError as exc:
            raise ApiError(
                "onvif_connection_unavailable",
                "暂时无法连接摄像头，请确认设备在线。",
                503,
            ) from exc
        if not self._onvif_identity_supported(
            manufacturer=verified.manufacturer,
            model=verified.model,
        ):
            raise ApiError(
                "onvif_device_unsupported",
                "这台摄像头型号暂未通过兼容验证。",
                422,
            )

        secret_ref = credential_store.store_onvif_credentials(
            username=username,
            password=password,
        )
        committed = False
        try:
            result = self._persist_onvif_pairing(
                context=context,
                token_hash=token_hash,
                metadata=metadata,
                verified=verified,
                secret_ref=secret_ref,
                name=(
                    self._optional_text(data, "name")
                    or verified.model
                    or str(metadata.get("displayName") or "")
                    or "AI 看护摄像头"
                ),
                location=self._optional_text(data, "location"),
                set_as_default=bool(data.get("setAsDefault")),
                live_ready=self._media_gateway_available(),
            )
            committed = True
            return result
        finally:
            if not committed:
                credential_store.delete(secret_ref)

    def get_runtime_config(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self._active_device_or_error(conn, context["family"]["id"], device_id)
            row = self.repository.get_device_runtime_config(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
            )
            return {
                "ok": True,
                "runtimeConfig": self._runtime_config_payload(row) if row else None,
            }

    def _discovery_candidate_status(self, conn, family_id: str, item: Mapping[str, Any]) -> dict:
        candidate_id = str(item.get("id") or "").strip()
        binding_code = str(item.get("bindingCode") or "").strip()
        if not binding_code:
            return {
                "id": candidate_id,
                "bindingCode": binding_code,
                "bindingState": "unknown",
                "isConnectable": True,
            }
        existing = self.repository.find_active_device_by_binding_code_global(
            conn,
            binding_code=binding_code,
        )
        if existing is None:
            return {
                "id": candidate_id,
                "bindingCode": binding_code,
                "bindingState": "available",
                "isConnectable": True,
            }
        if existing["family_id"] == family_id:
            return {
                "id": candidate_id,
                "bindingCode": binding_code,
                "bindingState": "boundToCurrentFamily",
                "isConnectable": False,
                "disabledReason": "已添加到当前家庭",
            }
        return {
            "id": candidate_id,
            "bindingCode": binding_code,
            "bindingState": "boundToAnotherFamily",
            "isConnectable": False,
            "disabledReason": "已被其他家庭绑定",
            "ownerHint": "another_family",
        }

    def _persist_onvif_pairing(
        self,
        *,
        context: dict,
        token_hash: str,
        metadata: dict,
        verified,
        secret_ref: str,
        name: str,
        location: str | None,
        set_as_default: bool,
        live_ready: bool,
    ) -> dict:
        now = now_ms()
        family_id = context["family"]["id"]
        user_id = context["user"]["id"]
        normalized_name = str(name or "AI 看护摄像头").strip()[:255] or "AI 看护摄像头"
        normalized_location = str(location).strip()[:255] if location else None
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            session = self._onvif_session_or_error(
                conn,
                token_hash=token_hash,
                family_id=family_id,
                user_id=user_id,
                now=now,
            )
            binding_code = str(session["binding_code"])
            global_existing = self.repository.find_active_device_by_binding_code_global(
                conn,
                binding_code=binding_code,
            )
            if global_existing is not None:
                raise ApiError("device_already_bound", "这台设备已经添加。", 409)
            unbound = self.repository.find_unbound_device_by_binding_code(
                conn,
                family_id=family_id,
                binding_code=binding_code,
            )
            if unbound:
                device = self.repository.rebind_device(
                    conn,
                    family_id=family_id,
                    device_id=unbound["id"],
                    name=normalized_name,
                    location=normalized_location,
                    now=now,
                )
            else:
                device = self.repository.create_device(
                    conn,
                    family_id=family_id,
                    binding_code=binding_code,
                    name=normalized_name,
                    location=normalized_location,
                    now=now,
                )
            if device is None:
                raise ApiError("device_pair_failed", "摄像头添加失败，请重试。", 500)

            runtime_config = build_onvif_runtime_config(
                device_service_url=str(metadata["deviceServiceUrl"]),
                endpoint_reference=str(metadata.get("endpointReference") or ""),
                verified=verified,
            )
            self.repository.upsert_device_runtime_config(
                conn,
                family_id=family_id,
                device_id=device["id"],
                provider="onvif_rtsp",
                config_json=json.dumps(
                    runtime_config,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                secret_ref=secret_ref,
                status="active",
                now=now,
            )
            default_device = self.repository.get_default_device(conn, family_id=family_id)
            if set_as_default or default_device is None:
                default_device = self.repository.set_default_device(
                    conn,
                    family_id=family_id,
                    device_id=device["id"],
                    now=now,
                )
                device = self.repository.get_device(
                    conn,
                    family_id=family_id,
                    device_id=device["id"],
                )
            if not self.repository.consume_onvif_discovery_session(
                conn,
                session_id=session["id"],
                consumed_at=now,
            ):
                raise ApiError(
                    "onvif_discovery_token_expired",
                    "设备发现信息已失效，请重新搜索。",
                    410,
                )
            return {
                "ok": True,
                "device": device_payload(device),
                "defaultDevice": (
                    device_payload(default_device)
                    if default_device is not None
                    else None
                ),
                "connection": {
                    "verified": True,
                    "liveReady": live_ready,
                    "liveReadiness": (
                        "ready"
                        if live_ready
                        else "media_gateway_unavailable"
                    ),
                    "capabilities": {
                        "onvif": True,
                        "rtsp": True,
                        "ptz": False,
                        "audio": bool(verified.has_audio),
                    },
                },
            }

    def _media_gateway_available(self) -> bool:
        if self.runtime_resolver is None:
            return False
        gateway = self.runtime_resolver.media_gateway
        if gateway is None:
            return False
        try:
            return gateway.is_healthy()
        except Exception:
            return False

    def _onvif_session_or_error(
        self,
        conn,
        *,
        token_hash: str,
        family_id: str,
        user_id: str,
        now: int,
    ):
        session = self.repository.get_onvif_discovery_session(
            conn,
            token_hash=token_hash,
            family_id=family_id,
            user_id=user_id,
        )
        if session is None:
            raise ApiError(
                "onvif_discovery_token_invalid",
                "设备发现信息无效，请重新搜索。",
                400,
            )
        if session.get("consumed_at") is not None:
            raise ApiError(
                "onvif_discovery_token_invalid",
                "设备已经添加，请重新搜索。",
                409,
            )
        if int(session["expires_at"]) < now:
            raise ApiError(
                "onvif_discovery_token_expired",
                "设备发现信息已过期，请重新搜索。",
                410,
            )
        return session

    def _onvif_candidate_supported(
        self,
        candidate,
        *,
        allow_unknown: bool,
    ) -> bool:
        return self._onvif_identity_supported(
            manufacturer=candidate.manufacturer_hint,
            model=candidate.model_hint,
            allow_unknown=allow_unknown,
        )

    def _onvif_identity_supported(
        self,
        *,
        manufacturer,
        model,
        allow_unknown: bool = False,
    ) -> bool:
        manufacturer = str(manufacturer or "").strip().lower()
        model = str(model or "").strip().lower()
        if not manufacturer and not model:
            return allow_unknown
        manufacturer_supported = not self.onvif_supported_manufacturers or any(
            allowed in manufacturer
            for allowed in self.onvif_supported_manufacturers
        )
        model_supported = not self.onvif_supported_models or any(
            allowed in model
            for allowed in self.onvif_supported_models
        )
        return manufacturer_supported and model_supported

    def _onvif_client_or_error(self) -> OnvifClient:
        if self.onvif_client is None:
            raise ApiError(
                "onvif_discovery_unavailable",
                "摄像头发现服务尚未配置。",
                503,
            )
        return self.onvif_client

    def _credential_store_or_error(self) -> EncryptedFileCredentialStore:
        if self.credential_store is None:
            raise ApiError(
                "device_credential_store_not_configured",
                "摄像头凭证存储尚未配置。",
                503,
            )
        return self.credential_store

    def update_runtime_config(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        provider = self._runtime_provider(data.get("provider"))
        config = data.get("config") if "config" in data else {}
        sanitized_config = self._runtime_config(provider, config)
        secret_ref = self._secret_ref(data.get("secretRef"))
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self._active_device_or_error(conn, context["family"]["id"], device_id)
            row = self.repository.upsert_device_runtime_config(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                provider=provider,
                config_json=json.dumps(sanitized_config, ensure_ascii=False, separators=(",", ":")),
                secret_ref=secret_ref,
                status="active",
                now=now,
            )
            return {
                "ok": True,
                "runtimeConfig": self._runtime_config_payload(row),
            }

    def set_default_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            device = self._active_device_or_error(conn, context["family"]["id"], device_id)
            default_device = self.repository.set_default_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device["id"],
                now=now,
            )
            return {"ok": True, "device": device_payload(default_device)}

    def update_device(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        fields: dict = {}
        if "name" in data:
            fields["name"] = self._required_text(data, "name", "请输入设备名称")
        if "location" in data:
            fields["location"] = self._optional_text(data, "location")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self._device_or_error(conn, context["family"]["id"], device_id)
            device = self.repository.update_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                fields=fields,
                now=now,
            )
            return {"ok": True, "device": device_payload(device)}

    def rename_device(self, access_token: str, device_id: str, data: dict) -> dict:
        context = self._auth_context(access_token)
        name = self._required_text(data, "name", "请输入设备名称")
        now = now_ms()
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            self._device_or_error(conn, context["family"]["id"], device_id)
            device = self.repository.update_device(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
                fields={"name": name},
                now=now,
            )
            return {"ok": True, "device": device_payload(device)}

    def unbind_device(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        now = now_ms()
        secret_ref_to_delete: str | None = None
        with self.repository.transaction() as conn:
            self._assert_capability(conn, context, "manage_devices")
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            runtime_config = self.repository.get_device_runtime_config(
                conn,
                family_id=context["family"]["id"],
                device_id=device_id,
            )
            if (
                runtime_config
                and str(runtime_config.get("provider") or "") == "onvif_rtsp"
                and runtime_config.get("secret_ref")
            ):
                secret_ref_to_delete = str(runtime_config["secret_ref"])
            if device["status"] == "unbound":
                default_device = self.repository.get_default_device(conn, family_id=context["family"]["id"])
                result = {
                    "ok": True,
                    "device": device_payload(device),
                    "defaultDevice": device_payload(default_device) if default_device else None,
                }
            else:
                was_default = bool(device.get("is_default"))
                device = self.repository.unbind_device(
                    conn,
                    family_id=context["family"]["id"],
                    device_id=device_id,
                    now=now,
                )
                default_device = self.repository.get_default_device(conn, family_id=context["family"]["id"])
                if was_default:
                    replacement = self.repository.find_replacement_default_device(
                        conn,
                        family_id=context["family"]["id"],
                        exclude_device_id=device_id,
                    )
                    if replacement:
                        default_device = self.repository.set_default_device(
                            conn,
                            family_id=context["family"]["id"],
                            device_id=replacement["id"],
                            now=now,
                        )
                    else:
                        self.repository.clear_default_device(conn, family_id=context["family"]["id"])
                        default_device = None
                result = {
                    "ok": True,
                    "device": device_payload(device),
                    "defaultDevice": device_payload(default_device) if default_device else None,
                }
        if secret_ref_to_delete:
            media_gateway = (
                self.runtime_resolver.media_gateway
                if self.runtime_resolver is not None
                else None
            )
            if media_gateway is not None:
                try:
                    media_gateway.delete_stream(
                        onvif_preview_stream_name(
                            device_id,
                            secret_ref_to_delete,
                        )
                    )
                except Exception:
                    pass
            if self.credential_store is not None:
                try:
                    self.credential_store.delete(secret_ref_to_delete)
                except Exception:
                    pass
        return result

    def device_status(self, access_token: str, device_id: str) -> dict:
        context = self._auth_context(access_token)
        with self.repository.transaction() as conn:
            device = self._device_or_error(conn, context["family"]["id"], device_id)
            hardware_status = self.hardware_adapter.status_for_device(device_payload(device))
            camera_status = self._camera_status_for_device(context["family"]["id"], device_id)
            return {
                "ok": True,
                "device": device_payload(device),
                "status": self._merge_status(hardware_status, camera_status),
            }

    def _camera_status_for_device(self, family_id: str, device_id: str) -> dict:
        if self.runtime_resolver is not None:
            return self.runtime_resolver.resolve(
                family_id=family_id,
                device_id=device_id,
                require_device=True,
            ).bridge.status()["status"]
        if self.camera_service is not None:
            return self.camera_service.status()["status"]
        return {}

    def _auth_context(self, access_token: str) -> dict:
        return self.auth_service.authenticate(access_token)

    def _device_or_error(self, conn, family_id: str, device_id: str):
        device = self.repository.get_device(conn, family_id=family_id, device_id=device_id)
        if device is None:
            raise ApiError("device_not_found", "设备不存在", 404)
        return device

    def _active_device_or_error(self, conn, family_id: str, device_id: str):
        device = self._device_or_error(conn, family_id, device_id)
        if device["status"] == "unbound":
            raise ApiError("device_unbound", "设备已解绑", 409)
        return device

    def _assert_current_admin(self, conn, context: dict):
        member = self.repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            user = context["user"]
            member = self.repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=user["id"],
                name=user.get("displayName") or "家长",
                phone=user.get("phone") or "",
                now=now_ms(),
            )
        if member is None:
            raise ApiError("member_not_found", "家庭成员不存在", 404)
        if member["role"] != "admin":
            raise ApiError("admin_required", "只有家庭管理员可以进行此操作", 403)
        return member

    def _assert_capability(self, conn, context: dict, capability: str):
        member = self.repository.get_family_member_by_user(
            conn,
            family_id=context["family"]["id"],
            user_id=context["user"]["id"],
        )
        if member is None:
            user = context["user"]
            member = self.repository.ensure_owner_member(
                conn,
                family_id=context["family"]["id"],
                user_id=user["id"],
                name=user.get("displayName") or "家长",
                phone=user.get("phone") or "",
                now=now_ms(),
            )
        if member is None:
            raise ApiError("member_not_found", "家庭成员不存在", 404)
        row = self.repository.get_app_option_item(
            conn,
            catalog_key="family_role",
            item_key=member["role"],
        )
        capabilities = role_capabilities_from_option(row) or FALLBACK_ROLE_CAPABILITIES.get(
            member["role"],
            [],
        )
        if capability not in capabilities:
            raise ApiError("permission_denied", "当前身份不能进行此操作", 403)
        return member

    def _merge_status(self, hardware_status: dict, camera_status: dict) -> dict:
        if not camera_status:
            return hardware_status
        capabilities = dict(hardware_status.get("capabilities") or {})
        capabilities.update(
            {
                "snapshot": bool(camera_status.get("snapshotAvailable")),
                "stream": bool(camera_status.get("streamAvailable")),
                "twoWayAudio": bool(camera_status.get("speakerAvailable")),
                "monitor": bool(camera_status.get("monitorAvailable")),
            }
        )
        connection = camera_status.get("connectionStatus") or hardware_status.get("connectionStatus")
        return {
            **hardware_status,
            "connectionStatus": connection,
            "lastSeenAt": camera_status.get("lastSeenAt"),
            "message": camera_status.get("message") or hardware_status.get("message") or "",
            "capabilities": capabilities,
            "camera": camera_status,
        }

    def _runtime_config_payload(self, row) -> dict:
        provider = str(row["provider"] or "").strip().lower()
        config = runtime_config_json(row)
        if provider == "onvif_rtsp":
            config = {
                key: value
                for key, value in config.items()
                if key not in ONVIF_RUNTIME_PRIVATE_KEYS
            }
            device_profile = config.get("deviceProfile")
            if isinstance(device_profile, dict):
                config["deviceProfile"] = {
                    key: value
                    for key, value in device_profile.items()
                    if key in {"manufacturer", "model", "firmwareVersion"}
                }
        return device_runtime_config_payload(
            row,
            config=config,
            adapter_implemented=provider not in RESERVED_RUNTIME_PROVIDERS,
        )

    def _runtime_provider(self, value) -> str:
        provider = str(value or "").strip().lower()
        if not provider:
            raise ApiError("missing_provider", "请选择摄像头运行方式。")
        if provider not in RUNTIME_PROVIDERS:
            raise ApiError("unsupported_runtime_provider", "暂不支持这个摄像头运行方式。")
        if provider == "onvif_rtsp":
            raise ApiError(
                "onvif_pairing_required",
                "请通过附近设备发现添加 ONVIF 摄像头。",
                409,
            )
        if provider in DEVELOPMENT_RUNTIME_PROVIDERS and not self._dev_runtime_allowed():
            raise ApiError(
                "development_adapter_not_allowed",
                "开发摄像头运行方式只能在测试环境中启用。",
                403,
            )
        return provider

    def _dev_runtime_allowed(self) -> bool:
        return self.dev_adapters_enabled and self.app_env in {"development", "test"}

    def _onvif_bootstrap_credentials_available(self) -> bool:
        return (
            self._dev_runtime_allowed()
            and self.onvif_bootstrap_credentials_enabled
            and bool(self.onvif_bootstrap_username)
            and bool(self.onvif_bootstrap_password)
        )

    def _onvif_pairing_credentials(self, data: dict) -> tuple[str, str]:
        if "username" in data or "password" in data:
            username = self._required_text(
                data,
                "username",
                "请输入摄像头管理账号。",
            )
            password = self._required_secret(
                data,
                "password",
                "请输入摄像头管理密码。",
            )
            return username, password
        if self._onvif_bootstrap_credentials_available():
            return self.onvif_bootstrap_username, self.onvif_bootstrap_password
        raise ApiError(
            "onvif_credentials_unavailable",
            "当前摄像头接入凭据尚未配置。",
            503,
        )

    def _runtime_config(self, provider: str, value) -> dict:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ApiError("invalid_runtime_config", "摄像头运行配置格式不正确。")
        self._assert_no_sensitive_config(value, path="config")
        return self._sanitize_config_object(
            value,
            RUNTIME_CONFIG_SCHEMAS[provider],
            path="config",
        )

    def _assert_no_sensitive_config(self, value, *, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key or "")
                compact_key = key_text.replace("-", "_").replace(" ", "").lower()
                if any(part in compact_key for part in SENSITIVE_KEY_PARTS):
                    raise ApiError("sensitive_runtime_config", f"{path}.{key_text} 不能包含敏感配置。")
                self._assert_no_sensitive_config(child, path=f"{path}.{key_text}")
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                self._assert_no_sensitive_config(child, path=f"{path}[{index}]")
            return
        if isinstance(value, str):
            lower_value = value.lower()
            if any(marker in lower_value for marker in SENSITIVE_VALUE_MARKERS):
                raise ApiError("sensitive_runtime_config", f"{path} 不能包含敏感配置。")

    def _sanitize_config_object(self, value: Mapping[str, Any], schema: Mapping[str, Any], *, path: str) -> dict:
        allowed = {key.lower(): (key, spec) for key, spec in schema.items()}
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key or "")
            lookup = key_text.lower()
            if lookup not in allowed:
                raise ApiError("runtime_config_key_not_allowed", f"{path}.{key_text} 暂不支持。")
            canonical_key, spec = allowed[lookup]
            if canonical_key in sanitized:
                raise ApiError("duplicate_runtime_config_key", f"{path}.{key_text} 重复。")
            sanitized[canonical_key] = self._sanitize_config_value(
                child,
                spec,
                path=f"{path}.{canonical_key}",
            )
        return sanitized

    def _sanitize_config_value(self, value, spec, *, path: str):
        if isinstance(spec, dict):
            if not isinstance(value, dict):
                raise ApiError("invalid_runtime_config", f"{path} 格式不正确。")
            return self._sanitize_config_object(value, spec, path=path)
        if spec == "url":
            return self._sanitize_url(value, path=path)
        if spec == "text":
            if not isinstance(value, str):
                raise ApiError("invalid_runtime_config", f"{path} 必须是文本。")
            text = value.strip()
            if not text:
                raise ApiError("invalid_runtime_config", f"{path} 不能为空。")
            if len(text) > 255:
                raise ApiError("invalid_runtime_config", f"{path} 过长。")
            return text
        if spec == "bool":
            if not isinstance(value, bool):
                raise ApiError("invalid_runtime_config", f"{path} 必须是开关值。")
            return value
        if spec == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ApiError("invalid_runtime_config", f"{path} 必须是数字。")
            return value
        raise ApiError("invalid_runtime_config", f"{path} 格式不正确。")

    def _sanitize_url(self, value, *, path: str) -> str:
        if not isinstance(value, str):
            raise ApiError("invalid_runtime_config", f"{path} 必须是链接。")
        url = value.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiError("invalid_runtime_config_url", f"{path} 只支持 http/https 链接。")
        if parsed.username or parsed.password:
            raise ApiError("invalid_runtime_config_url", f"{path} 不能包含账号或密码。")
        if len(url) > 512:
            raise ApiError("invalid_runtime_config_url", f"{path} 过长。")
        return url

    def _secret_ref(self, value) -> str | None:
        if value is None:
            return None
        secret_ref = str(value or "").strip()
        if not secret_ref:
            return None
        if len(secret_ref) > 255 or any(char.isspace() for char in secret_ref):
            raise ApiError("invalid_secret_ref", "凭证引用格式不正确。")
        lower_value = secret_ref.lower()
        if any(marker in lower_value for marker in SENSITIVE_VALUE_MARKERS):
            raise ApiError("invalid_secret_ref", "请保存凭证引用，不要填写真实密钥。")
        allowed_prefixes = ("vault://", "kms://", "secret://", "ref://", "arn:")
        if not secret_ref.startswith(allowed_prefixes):
            raise ApiError("invalid_secret_ref", "请使用凭证引用，不要填写真实密钥。")
        return secret_ref

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

    def _required_secret(self, data: dict, key: str, message: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise ApiError(f"missing_{key}", message)
        return value


def _onvif_session_metadata(session) -> dict:
    try:
        metadata = json.loads(str(session.get("metadata_json") or ""))
    except json.JSONDecodeError as exc:
        raise ApiError(
            "onvif_discovery_token_invalid",
            "设备发现信息无效，请重新搜索。",
            400,
        ) from exc
    if not isinstance(metadata, dict) or not str(metadata.get("deviceServiceUrl") or "").strip():
        raise ApiError(
            "onvif_discovery_token_invalid",
            "设备发现信息无效，请重新搜索。",
            400,
        )
    return metadata


def _onvif_discovery_timeout_ms(value) -> int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise ApiError(
            "invalid_onvif_timeout",
            "设备搜索时长格式不正确。",
            400,
        )
    return max(500, min(int(value), 5000))
