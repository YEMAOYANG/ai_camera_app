from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from core.database import Database, DatabaseRow
from core.errors import ApiError
from core.security import now_ms
from integrations.camera_runtime.ai_camera_test_adapter import AiCameraTestRuntimeAdapter
from integrations.camera_runtime.disabled_adapter import DisabledCameraRuntimeAdapter
from integrations.camera_runtime.guardian_local_adapter import GuardianLocalRuntimeAdapter
from integrations.camera_runtime.go2rtc_client import Go2RtcClient
from integrations.camera_runtime.mock_adapter import MockCameraRuntimeAdapter
from integrations.camera_runtime.onvif_rtsp_adapter import OnvifRtspRuntimeAdapter
from integrations.onvif.client import OnvifClient
from repositories.device_repository import DeviceRepository
from services.camera_bridge_service import CameraBridgeService
from services.device_credential_store import EncryptedFileCredentialStore
from services.onvif_runtime_recovery import OnvifRuntimeRecoveryService


@dataclass(frozen=True)
class ResolvedCameraRuntime:
    bridge: CameraBridgeService
    provider: str
    family_id: str | None
    device_id: str | None
    device: Mapping | None
    runtime_config: Mapping | None
    uses_global_provider: bool


class DeviceRuntimeResolver:
    def __init__(
        self,
        database_url: str | Path,
        *,
        provider: str,
        legacy_provider: str | None = None,
        ai_camera_test_base_url: str | None = None,
        camera_backend_url: str | None = None,
        dev_adapters_enabled: bool = False,
        app_env: str = "production",
        vision_service_factory: Callable[[], Any] | None = None,
        onvif_client: OnvifClient | None = None,
        credential_store: EncryptedFileCredentialStore | None = None,
        media_gateway: Go2RtcClient | None = None,
    ):
        self.repository = DeviceRepository(Database(database_url))
        self.provider = str(provider or "disabled").strip().lower()
        self.legacy_provider = str(legacy_provider or "").strip().lower()
        self.ai_camera_test_base_url = str(ai_camera_test_base_url or "").strip()
        self.camera_backend_url = str(camera_backend_url or "").strip()
        self.dev_adapters_enabled = bool(dev_adapters_enabled)
        self.app_env = str(app_env or "production").strip().lower()
        self.vision_service_factory = vision_service_factory
        self.onvif_client = onvif_client
        self.credential_store = credential_store
        self.media_gateway = media_gateway
        self.onvif_runtime_recovery = (
            OnvifRuntimeRecoveryService(
                repository=self.repository,
                client=onvif_client,
                credential_store=credential_store,
            )
            if onvif_client is not None and credential_store is not None
            else None
        )

    def global_bridge(self) -> CameraBridgeService:
        return self._bridge_for_provider(self._global_provider())

    def resolve(
        self,
        *,
        family_id: str | None,
        device_id: str | None = None,
        require_device: bool = False,
    ) -> ResolvedCameraRuntime:
        family_id = str(family_id or "").strip() or None
        requested_device_id = str(device_id or "").strip() or None
        device: DatabaseRow | None = None
        runtime_config: DatabaseRow | None = None

        if family_id:
            with self.repository.transaction() as conn:
                if requested_device_id:
                    device = self.repository.get_device(
                        conn,
                        family_id=family_id,
                        device_id=requested_device_id,
                    )
                    if device is None:
                        raise ApiError("device_not_found", "设备不存在", 404)
                    if str(device.get("status") or "") == "unbound":
                        raise ApiError("device_unbound", "设备已解绑", 409)
                else:
                    device = self.repository.ensure_default_device(
                        conn,
                        family_id=family_id,
                        now=now_ms(),
                    )
                if device:
                    runtime_config = self.repository.get_device_runtime_config(
                        conn,
                        family_id=family_id,
                        device_id=str(device["id"]),
                    )

        if require_device and device is None:
            raise ApiError("device_not_found", "设备不存在", 404)
        if family_id and device is None and not self._allow_device_less_fallback():
            raise ApiError("no_device", "还没有绑定摄像头，请先添加设备。", 404)
        if device and runtime_config is None and not self._allow_device_runtime_global_fallback():
            raise ApiError(
                "device_runtime_not_configured",
                "摄像头运行配置尚未完成。",
                409,
            )

        provider = self._provider_for_runtime_config(runtime_config) or self._provider_for_device(device)
        config = self._runtime_config_json(runtime_config)
        return ResolvedCameraRuntime(
            bridge=self._bridge_for_provider(
                provider,
                config=config,
                secret_ref=(
                    str(runtime_config.get("secret_ref") or "")
                    if runtime_config
                    else None
                ),
                family_id=family_id,
                device_id=str(device.get("id") or "") if device else requested_device_id,
            ),
            provider=provider,
            family_id=family_id,
            device_id=str(device.get("id") or "") if device else requested_device_id,
            device=device,
            runtime_config=runtime_config,
            uses_global_provider=runtime_config is None and not self._device_has_provider(device),
        )

    def _provider_for_runtime_config(self, runtime_config: Mapping | None) -> str | None:
        if not runtime_config:
            return None
        provider = str(runtime_config.get("provider") or "").strip().lower()
        return provider or None

    def _runtime_config_json(self, runtime_config: Mapping | None) -> dict[str, Any]:
        if not runtime_config:
            return {}
        raw = runtime_config.get("config_json")
        if raw is None or raw == "":
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError:
            raise ApiError("device_runtime_config_invalid", "摄像头运行配置格式不正确。", 503)
        if not isinstance(parsed, dict):
            raise ApiError("device_runtime_config_invalid", "摄像头运行配置格式不正确。", 503)
        return parsed

    def _provider_for_device(self, device: Mapping | None) -> str:
        if device:
            for key in ("runtime_provider", "camera_runtime_provider"):
                value = str(device.get(key) or "").strip().lower()
                if value:
                    return value
        return self._global_provider()

    def _device_has_provider(self, device: Mapping | None) -> bool:
        if not device:
            return False
        return any(str(device.get(key) or "").strip() for key in ("runtime_provider", "camera_runtime_provider"))

    def _global_provider(self) -> str:
        if self.provider == "disabled" and self.legacy_provider and self.legacy_provider != self.provider:
            return self.legacy_provider
        return self.provider or "disabled"

    def _bridge_for_provider(
        self,
        provider: str,
        *,
        config: Mapping[str, Any] | None = None,
        secret_ref: str | None = None,
        family_id: str | None = None,
        device_id: str | None = None,
    ) -> CameraBridgeService:
        adapter_name = str(provider or "disabled").strip().lower()
        config = config or {}
        if adapter_name == "ai_camera_test":
            self._require_dev_adapter("CAMERA_RUNTIME_PROVIDER=ai_camera_test")
            base_url = str(
                config.get("baseUrl")
                or config.get("base_url")
                or self.ai_camera_test_base_url
                or self.camera_backend_url
                or ""
            ).strip()
            if not base_url:
                raise ApiError(
                    "camera_runtime_not_configured",
                    "开发摄像头桥接已启用，但 AI_CAMERA_TEST_BASE_URL 未配置。",
                    503,
                )
            return CameraBridgeService(
                adapter=AiCameraTestRuntimeAdapter(
                    base_url,
                    vision_service=self._vision_service(),
                )
            )
        if adapter_name == "guardian_local":
            self._require_dev_adapter("CAMERA_RUNTIME_PROVIDER=guardian_local")
            media_base_url = str(
                config.get("baseUrl")
                or config.get("base_url")
                or self.ai_camera_test_base_url
                or self.camera_backend_url
                or ""
            ).strip()
            adapter = GuardianLocalRuntimeAdapter(
                family_id=family_id,
                device_id=device_id,
                vision_service=self._vision_service(),
                media_base_url=media_base_url or None,
            )
            profile = config.get("interactionProfile") if isinstance(config.get("interactionProfile"), dict) else {}
            if profile:
                adapter.sync_interaction_profile(profile)
            return CameraBridgeService(adapter=adapter)
        if adapter_name == "mock":
            self._require_dev_adapter("CAMERA_RUNTIME_PROVIDER=mock")
            return CameraBridgeService(
                adapter=MockCameraRuntimeAdapter(vision_service=self._vision_service()),
            )
        if adapter_name == "disabled":
            return CameraBridgeService(adapter=DisabledCameraRuntimeAdapter())
        if adapter_name == "onvif_rtsp":
            if self.onvif_client is None or self.credential_store is None:
                raise ApiError(
                    "camera_runtime_not_configured",
                    "ONVIF 摄像头运行时尚未配置。",
                    503,
                )
            if not secret_ref:
                raise ApiError(
                    "camera_runtime_not_configured",
                    "ONVIF 摄像头凭证尚未配置。",
                    503,
                )
            if not family_id or not device_id:
                raise ApiError(
                    "camera_runtime_not_configured",
                    "ONVIF 摄像头设备标识尚未配置。",
                    503,
                )
            return CameraBridgeService(
                adapter=OnvifRtspRuntimeAdapter(
                    config=config,
                    secret_ref=secret_ref,
                    client=self.onvif_client,
                    credential_store=self.credential_store,
                    media_gateway=self.media_gateway,
                    stream_name=onvif_preview_stream_name(
                        device_id,
                        secret_ref,
                    ),
                    recover_runtime=(
                        (
                            lambda current_config: self.onvif_runtime_recovery.recover(
                                family_id=family_id,
                                device_id=device_id,
                                secret_ref=secret_ref,
                                current_config=current_config,
                            )
                        )
                        if self.onvif_runtime_recovery is not None
                        else None
                    ),
                )
            )
        if adapter_name in {"future_hardware", "self_owned_camera"}:
            raise ApiError("camera_runtime_reserved_adapter", "自研摄像头运行时尚未接入。", 503)
        raise ApiError("camera_runtime_unknown_adapter", "未知摄像头运行时适配器。", 503)

    def _require_dev_adapter(self, label: str) -> None:
        if self.dev_adapters_enabled and self.app_env in {"development", "test"}:
            return
        raise ApiError(
            "development_adapter_not_allowed",
            f"{label} 只能在 development/test profile 下启用。",
            503,
        )

    def _allow_device_less_fallback(self) -> bool:
        if self.app_env not in {"development", "test"}:
            return False
        return self._global_provider() in {"disabled", "mock", "ai_camera_test", "guardian_local"}

    def _allow_device_runtime_global_fallback(self) -> bool:
        return self.app_env in {"development", "test"} and self._global_provider() in {
            "disabled",
            "mock",
            "ai_camera_test",
            "guardian_local",
        }

    def _vision_service(self):
        if self.vision_service_factory is None:
            return None
        try:
            return self.vision_service_factory()
        except Exception:
            return None


def onvif_preview_stream_name(
    device_id: str | None,
    secret_ref: str | None,
) -> str:
    value = str(device_id or "").strip()
    if not value:
        raise ApiError(
            "camera_runtime_not_configured",
            "摄像头设备标识尚未配置。",
            503,
        )
    secret_identity = str(secret_ref or "").strip()
    digest = hashlib.sha256(
        f"{value}:{secret_identity}".encode("utf-8")
    ).hexdigest()[:24]
    return f"mira_{digest}_preview"
