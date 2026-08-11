from __future__ import annotations

from pathlib import Path

from flask import current_app

from core.config import BACKEND_ROOT
from core.errors import ApiError
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from integrations.hardware.mock_adapter import MockHardwareDeviceAdapter
from services.auth_service import AuthService
from integrations.ai.kimi_vision_provider import OpenAICompatibleVisionProvider
from integrations.ai.unavailable_vision_provider import UnavailableVisionProvider
from services.ai_text_provider import OpenAICompatibleTextProvider, UnavailableAiTextProvider
from services.vision_observation_service import VisionObservationService
from services.camera_bridge_service import CameraBridgeService
from services.camera_ai_observation_service import CameraAiObservationService
from integrations.camera_runtime.python_open_cv_yolo_prefilter import default_local_vision_prefilter
from integrations.camera_runtime.go2rtc_client import Go2RtcClient
from integrations.onvif.client import OnvifClient
from services.camera_observe_service import CameraObserveService
from services.camera_command_service import CameraCommandService
from services.care_config_service import CareConfigService
from services.device_service import DeviceService
from services.device_credential_store import EncryptedFileCredentialStore
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.firmware_service import FirmwareService
from services.ai_care_reminder_service import AiCareReminderService
from services.internal_request_guard import InternalRequestGuard
from services.point_service import PointService
from services.profile_service import ProfileService
from services.reward_service import RewardService
from services.routine_reminder_service import RoutineReminderService
from services.setup_service import SetupService
from services.sms_provider import DevelopmentSmsProvider, SmsProvider, UnavailableSmsProvider
from services.prompt_registry import PromptRegistry
from services.task_service import TaskService
from services.task_template_service import TaskTemplateService
from services.task_runtime_service import TaskRuntimeService
from services.conversation_app_service import ConversationAppService
from services.conversation_sync_service import ConversationSyncService
from services.voice_conversation_service import VoiceConversationService
from services.voice_runtime_app_service import VoiceRuntimeAppService


def auth_service() -> AuthService:
    return AuthService(
        current_app.config["DATABASE_URL"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        sms_code_ttl_seconds=current_app.config["SMS_CODE_TTL_SECONDS"],
        sms_resend_cooldown_seconds=current_app.config["SMS_RESEND_COOLDOWN_SECONDS"],
        sms_max_attempts=current_app.config["SMS_MAX_ATTEMPTS"],
        sms_provider=sms_provider(),
    )


def setup_service() -> SetupService:
    return SetupService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        camera_command_service_factory=camera_command_service,
    )


def task_service() -> TaskService:
    return TaskService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        camera_command_service_factory=camera_command_service,
        ai_text_provider=ai_text_provider(),
        prompt_registry=prompt_registry(),
    )


def task_template_service() -> TaskTemplateService:
    return TaskTemplateService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
    )


def point_service() -> PointService:
    return PointService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def reward_service() -> RewardService:
    return RewardService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def profile_service() -> ProfileService:
    return ProfileService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def device_service() -> DeviceService:
    return DeviceService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        hardware_adapter=hardware_adapter(),
        runtime_resolver=device_runtime_resolver(),
        onvif_client=onvif_client(),
        credential_store=device_credential_store(),
        onvif_discovery_ttl_seconds=int(
            current_app.config.get("ONVIF_DISCOVERY_TOKEN_TTL_SECONDS", 90)
        ),
        onvif_supported_manufacturers=tuple(
            current_app.config.get("ONVIF_SUPPORTED_MANUFACTURERS") or ("Vatilon",)
        ),
        onvif_supported_models=tuple(
            current_app.config.get("ONVIF_SUPPORTED_MODELS") or ("T62",)
        ),
        onvif_bootstrap_credentials_enabled=bool(
            current_app.config.get("ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED")
        ),
        onvif_bootstrap_username=str(
            current_app.config.get("ONVIF_BOOTSTRAP_USERNAME") or ""
        ),
        onvif_bootstrap_password=str(
            current_app.config.get("ONVIF_BOOTSTRAP_PASSWORD") or ""
        ),
        app_env=str(current_app.config.get("APP_ENV", "production")),
        dev_adapters_enabled=bool(current_app.config.get("DEV_ADAPTERS_ENABLED")),
    )


def onvif_client() -> OnvifClient:
    return OnvifClient(
        discovery_timeout_seconds=float(
            current_app.config.get("ONVIF_DISCOVERY_TIMEOUT_SECONDS", 1.5)
        ),
        http_timeout_seconds=float(
            current_app.config.get("ONVIF_HTTP_TIMEOUT_SECONDS", 4)
        ),
        rtsp_timeout_seconds=float(
            current_app.config.get("ONVIF_RTSP_TIMEOUT_SECONDS", 4)
        ),
    )


def device_credential_store() -> EncryptedFileCredentialStore:
    app_env = str(current_app.config.get("APP_ENV", "production")).strip().lower()
    root = _backend_relative_path(
        str(current_app.config.get("DEVICE_SECRET_STORE_DIR") or "")
    )
    key_file_value = str(current_app.config.get("DEVICE_SECRET_KEY_FILE") or "")
    return EncryptedFileCredentialStore(
        root=root,
        key=str(current_app.config.get("DEVICE_SECRET_KEY") or ""),
        key_file=_backend_relative_path(key_file_value) if key_file_value else None,
        allow_key_generation=app_env in {"development", "test"},
    )


def _backend_relative_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_ROOT / path


def firmware_service() -> FirmwareService:
    return FirmwareService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def camera_bridge_service() -> CameraBridgeService:
    return device_runtime_resolver().global_bridge()


def device_runtime_resolver() -> DeviceRuntimeResolver:
    provider = str(current_app.config.get("CAMERA_RUNTIME_PROVIDER", "disabled"))
    return DeviceRuntimeResolver(
        current_app.config["DATABASE_URL"],
        provider=provider,
        legacy_provider=str(current_app.config.get("CAMERA_RUNTIME_ADAPTER", provider)),
        ai_camera_test_base_url=current_app.config.get("AI_CAMERA_TEST_BASE_URL"),
        camera_backend_url=current_app.config.get("CAMERA_BACKEND_URL"),
        dev_adapters_enabled=bool(current_app.config.get("DEV_ADAPTERS_ENABLED")),
        app_env=str(current_app.config.get("APP_ENV", "production")),
        vision_service_factory=lambda: build_vision_observation_service_from_config(current_app.config),
        onvif_client=onvif_client(),
        credential_store=device_credential_store(),
        media_gateway=media_gateway_client(),
    )


def media_gateway_client() -> Go2RtcClient | None:
    if not bool(current_app.config.get("MEDIA_GATEWAY_ENABLED")) or not bool(
        current_app.config.get("TASK_WEBSOCKET_ENABLED")
    ):
        return None
    return Go2RtcClient(
        str(
            current_app.config.get("MEDIA_GATEWAY_API_BASE_URL")
            or "http://127.0.0.1:1984"
        ),
        public_base_url=(
            str(current_app.config.get("MEDIA_GATEWAY_PUBLIC_BASE_URL") or "")
            or None
        ),
        timeout_seconds=float(
            current_app.config.get("MEDIA_GATEWAY_TIMEOUT_SECONDS", 5)
        ),
    )


def camera_command_service() -> CameraCommandService:
    return CameraCommandService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        runtime_resolver=device_runtime_resolver(),
    )


def care_config_service() -> CareConfigService:
    return CareConfigService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
    )


def ai_care_reminder_service() -> AiCareReminderService:
    return AiCareReminderService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        ai_text_provider=ai_text_provider(),
        prompt_registry=prompt_registry(),
        camera_command_service=camera_command_service(),
    )


def camera_ai_observation_service() -> CameraAiObservationService:
    return CameraAiObservationService(current_app.config["DATABASE_URL"])


def camera_observe_service() -> CameraObserveService:
    return CameraObserveService(
        current_app.config["DATABASE_URL"],
        vision_service=vision_observation_service(),
        vision_prefilter=default_local_vision_prefilter(),
    )


def routine_reminder_service() -> RoutineReminderService:
    return RoutineReminderService(current_app.config["DATABASE_URL"])


def internal_request_guard() -> InternalRequestGuard:
    return InternalRequestGuard(
        current_app.config["DATABASE_URL"],
        token=current_app.config.get("INTERNAL_API_TOKEN", ""),
        allowed_sources=current_app.config.get("INTERNAL_ALLOWED_SOURCES", []),
    )


def task_runtime_service() -> TaskRuntimeService:
    return TaskRuntimeService(
        current_app.config["DATABASE_URL"],
        camera_command_service=camera_command_service(),
        ai_text_provider=ai_text_provider(),
        prompt_registry=prompt_registry(),
        reminder_lead_seconds=int(current_app.config.get("TASK_REMINDER_LEAD_SECONDS", 300)),
        delay_reminder_interval_seconds=int(
            current_app.config.get("TASK_DELAY_REMINDER_INTERVAL_SECONDS", 180)
        ),
        max_delay_reminders=int(current_app.config.get("TASK_DELAY_REMINDER_MAX_COUNT", 3)),
        monitor_enabled=bool(current_app.config.get("CAMERA_MONITOR_ENABLED", True)),
        speaker_enabled=bool(current_app.config.get("CAMERA_SPEAKER_ENABLED", True)),
    )


def sms_provider() -> SmsProvider:
    provider = str(current_app.config.get("SMS_PROVIDER", "")).strip().lower()
    if provider == "development":
        _require_dev_adapter("APP_SMS_PROVIDER=development")
        return DevelopmentSmsProvider(
            template_id=current_app.config.get("SMS_TEMPLATE_ID", "login-code"),
        )
    if provider in {"aliyun", "tencent", "twilio"}:
        return UnavailableSmsProvider(provider)
    return UnavailableSmsProvider(provider or "unconfigured")


def prompt_registry() -> PromptRegistry:
    return PromptRegistry(current_app.config["PROMPT_ROOT"])


def ai_text_provider():
    provider = str(current_app.config.get("AI_PROVIDER", "")).strip().lower()
    api_key = str(current_app.config.get("AI_API_KEY", "")).strip()
    model = str(current_app.config.get("AI_MODEL", "")).strip()
    base_url = str(current_app.config.get("AI_BASE_URL", "")).strip()
    timeout = float(current_app.config.get("AI_TIMEOUT_SECONDS", 8))
    if provider in {"moonshot", "kimi", "openai", "openai_compatible"}:
        return OpenAICompatibleTextProvider(
            provider_name="moonshot" if provider == "kimi" else provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            timeout_seconds=timeout,
            disable_thinking=provider in {"moonshot", "kimi"},
        )
    return UnavailableAiTextProvider()


def ai_vision_provider():
    return build_ai_vision_provider_from_config(current_app.config)


def vision_observation_service() -> VisionObservationService:
    return build_vision_observation_service_from_config(current_app.config)


def build_ai_vision_provider_from_config(config: dict):
    if not bool(config.get("AI_VISION_ENABLED", True)):
        return UnavailableVisionProvider()
    provider = str(config.get("AI_PROVIDER", "")).strip().lower()
    api_key = str(config.get("AI_API_KEY", "")).strip()
    model = str(config.get("AI_VISION_MODEL") or config.get("AI_MODEL") or "").strip()
    base_url = str(config.get("AI_BASE_URL", "")).strip()
    timeout = float(config.get("AI_VISION_TIMEOUT_SECONDS", 20))
    max_bytes = int(config.get("AI_VISION_MAX_BYTES", 524288))
    max_dimension = int(config.get("AI_VISION_MAX_DIMENSION", 1280))
    jpeg_quality = int(config.get("AI_VISION_JPEG_QUALITY", 85))
    if provider in {"moonshot", "kimi", "openai", "openai_compatible"} and api_key and base_url and model:
        # kimi-k2.6 thinking 会吃掉 max_tokens，导致 content 为空；视觉观察只需 JSON 输出。
        disable_thinking = provider in {"moonshot", "kimi"} or str(model).startswith("kimi-k")
        return OpenAICompatibleVisionProvider(
            provider_name="moonshot" if provider == "kimi" else provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            timeout_seconds=timeout,
            max_bytes=max_bytes,
            max_image_dimension=max_dimension,
            jpeg_quality=jpeg_quality,
            disable_thinking=disable_thinking,
        )
    return UnavailableVisionProvider()


def build_vision_observation_service_from_config(config: dict) -> VisionObservationService:
    prompt_root = str(config.get("PROMPT_ROOT") or "")
    return VisionObservationService(
        vision_provider=build_ai_vision_provider_from_config(config),
        prompt_registry=PromptRegistry(prompt_root),
        enabled=bool(config.get("AI_VISION_ENABLED", True)),
        min_interval_seconds=float(config.get("AI_VISION_MIN_INTERVAL_SECONDS", 60)),
        max_calls_per_hour=int(config.get("AI_VISION_MAX_CALLS_PER_HOUR", 20)),
        backoff_seconds=float(config.get("AI_VISION_BACKOFF_SECONDS", 300)),
    )


def hardware_adapter():
    adapter = str(current_app.config.get("HARDWARE_ADAPTER", "disabled")).lower()
    if adapter == "mock":
        _require_dev_adapter("APP_HARDWARE_ADAPTER=mock")
        return MockHardwareDeviceAdapter()
    if adapter == "disabled":
        return DisabledHardwareDeviceAdapter()
    raise ApiError("hardware_unknown_adapter", "未知硬件设备适配器。", 503)


def _require_dev_adapter(label: str) -> None:
    if current_app.config.get("DEV_ADAPTERS_ENABLED") and current_app.config.get("APP_ENV") in {
        "development",
        "test",
    }:
        return
    raise ApiError(
        "development_adapter_not_allowed",
        f"{label} 只能在 development/test profile 下启用。",
        503,
    )

def conversation_service() -> ConversationAppService:
    database_url = current_app.config["DATABASE_URL"]
    return ConversationAppService(
        database_url,
        auth_service=auth_service(),
        conversation_service=VoiceConversationService(
            database_url,
            ai_text_provider=ai_text_provider(),
            prompt_registry=prompt_registry(),
        ),
    )


def conversation_sync_service() -> ConversationSyncService:
    return ConversationSyncService(current_app.config["DATABASE_URL"])


def voice_runtime_service() -> VoiceRuntimeAppService:
    return VoiceRuntimeAppService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        sync_service=conversation_sync_service(),
    )
