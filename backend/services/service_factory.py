from __future__ import annotations

from flask import current_app

from core.errors import ApiError
from integrations.camera_runtime.ai_camera_test_adapter import AiCameraTestRuntimeAdapter
from integrations.camera_runtime.disabled_adapter import DisabledCameraRuntimeAdapter
from integrations.camera_runtime.mock_adapter import MockCameraRuntimeAdapter
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from integrations.hardware.mock_adapter import MockHardwareDeviceAdapter
from services.auth_service import AuthService
from services.camera_bridge_service import CameraBridgeService
from services.camera_command_service import CameraCommandService
from services.device_service import DeviceService
from services.firmware_service import FirmwareService
from services.point_service import PointService
from services.profile_service import ProfileService
from services.reward_service import RewardService
from services.setup_service import SetupService
from services.sms_provider import DevelopmentSmsProvider, SmsProvider, UnavailableSmsProvider
from services.task_service import TaskService
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
        camera_service=camera_bridge_service(),
    )


def firmware_service() -> FirmwareService:
    return FirmwareService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def camera_bridge_service() -> CameraBridgeService:
    provider = str(current_app.config.get("CAMERA_RUNTIME_PROVIDER", "disabled"))
    legacy_provider = str(current_app.config.get("CAMERA_RUNTIME_ADAPTER", provider))
    if provider == "disabled" and legacy_provider != provider:
        provider = legacy_provider
    adapter_name = provider.lower()
    if adapter_name == "ai_camera_test":
        _require_dev_adapter("CAMERA_RUNTIME_PROVIDER=ai_camera_test")
        base_url = current_app.config.get("AI_CAMERA_TEST_BASE_URL") or current_app.config.get("CAMERA_BACKEND_URL")
        if not base_url:
            raise ApiError(
                "camera_runtime_not_configured",
                "开发摄像头桥接已启用，但 AI_CAMERA_TEST_BASE_URL 未配置。",
                503,
            )
        return CameraBridgeService(adapter=AiCameraTestRuntimeAdapter(base_url))
    if adapter_name == "mock":
        _require_dev_adapter("CAMERA_RUNTIME_PROVIDER=mock")
        return CameraBridgeService(adapter=MockCameraRuntimeAdapter())
    if adapter_name == "disabled":
        return CameraBridgeService(adapter=DisabledCameraRuntimeAdapter())
    raise ApiError("camera_runtime_unknown_adapter", "未知摄像头运行时适配器。", 503)


def camera_command_service() -> CameraCommandService:
    return CameraCommandService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        camera_service=camera_bridge_service(),
    )


def task_runtime_service() -> TaskRuntimeService:
    return TaskRuntimeService(
        current_app.config["DATABASE_URL"],
        camera_command_service=camera_command_service(),
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
