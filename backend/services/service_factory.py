from __future__ import annotations

from flask import current_app

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
from services.camera_command_service import CameraCommandService
from services.care_config_service import CareConfigService
from services.device_service import DeviceService
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
        app_env=str(current_app.config.get("APP_ENV", "production")),
        dev_adapters_enabled=bool(current_app.config.get("DEV_ADAPTERS_ENABLED")),
    )


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
    if provider in {"moonshot", "kimi", "openai", "openai_compatible"} and api_key and base_url and model:
        return OpenAICompatibleVisionProvider(
            provider_name="moonshot" if provider == "kimi" else provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            timeout_seconds=timeout,
            max_bytes=max_bytes,
            disable_thinking=provider in {"moonshot", "kimi"},
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
