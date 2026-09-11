from __future__ import annotations

import ipaddress
import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is a development convenience.
    load_dotenv = None


BACKEND_ROOT = Path(__file__).resolve().parents[1]

if load_dotenv is not None:
    load_dotenv(BACKEND_ROOT / ".env")


VALID_APP_ENVS = {"development", "test", "staging", "production"}
MEDIA_GATEWAY_REQUIRED_VERSION = "1.9.14"
DEVELOPMENT_STUDENT_AUTH_PEPPER = "mira-student-auth-development-only-pepper"
LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS = 360


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppConfig:
    APP_ENV: str
    SERVICE_NAME: str
    DATABASE_URL: str
    CORS_ORIGINS: list[str]
    AUTH_ACCESS_TOKEN_SECONDS: int
    AUTH_REFRESH_TOKEN_SECONDS: int
    STUDENT_AUTH_PEPPER: str
    STUDENT_ACCESS_TOKEN_SECONDS: int
    STUDENT_REFRESH_TOKEN_SECONDS: int
    STUDENT_DEVICE_TOKEN_SECONDS: int
    STUDENT_PAIRING_CODE_TTL_SECONDS: int
    STUDENT_QR_CHALLENGE_TTL_SECONDS: int
    STUDENT_QR_APPROVAL_EXCHANGE_SECONDS: int
    STUDENT_QR_POLLING_INTERVAL_MS: int
    STUDENT_QR_ACTIVE_CHALLENGE_LIMIT: int
    STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT: int
    STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS: int
    STUDENT_QR_RATE_LIMIT_MAX: int
    STUDENT_QR_IP_RATE_LIMIT_MAX: int
    STUDENT_QR_RETENTION_SECONDS: int
    STUDENT_PIN_PBKDF2_ITERATIONS: int
    STUDENT_PIN_MAX_ATTEMPTS: int
    STUDENT_PIN_LOCK_SECONDS: int
    SMS_PROVIDER: str
    SMS_TEMPLATE_ID: str
    SMS_CODE_TTL_SECONDS: int
    SMS_RESEND_COOLDOWN_SECONDS: int
    SMS_MAX_ATTEMPTS: int
    DEV_ADAPTERS_ENABLED: bool
    CAMERA_RUNTIME_PROVIDER: str
    CAMERA_RUNTIME_ADAPTER: str
    AI_CAMERA_TEST_BASE_URL: str
    AI_CAMERA_TEST_WORKSPACE: str
    CAMERA_BACKEND_URL: str
    CAMERA_COMMAND_TIMEOUT: float
    CAMERA_MONITOR_ENABLED: bool
    CAMERA_SPEAKER_ENABLED: bool
    CAMERA_STREAM_URL: str
    CAMERA_SNAPSHOT_URL: str
    MEDIA_GATEWAY_ENABLED: bool
    MEDIA_GATEWAY_API_BASE_URL: str
    MEDIA_GATEWAY_PUBLIC_BASE_URL: str
    MEDIA_GATEWAY_TIMEOUT_SECONDS: float
    MEDIA_GATEWAY_AUTO_START: bool
    MEDIA_GATEWAY_BINARY: str
    MEDIA_GATEWAY_CONFIG_FILE: str
    MEDIA_GATEWAY_VERSION: str
    CAMERA_SIGNALING_PUBLIC_BASE_URL: str
    ONVIF_DISCOVERY_TIMEOUT_SECONDS: float
    ONVIF_HTTP_TIMEOUT_SECONDS: float
    ONVIF_RTSP_TIMEOUT_SECONDS: float
    ONVIF_DISCOVERY_TOKEN_TTL_SECONDS: int
    ONVIF_SUPPORTED_MANUFACTURERS: list[str]
    ONVIF_SUPPORTED_MODELS: list[str]
    ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED: bool
    ONVIF_BOOTSTRAP_USERNAME: str
    ONVIF_BOOTSTRAP_PASSWORD: str
    DEVICE_SECRET_STORE_DIR: str
    DEVICE_SECRET_KEY: str
    DEVICE_SECRET_KEY_FILE: str
    TASK_REMINDER_LEAD_SECONDS: int
    TASK_SCHEDULER_ENABLED: bool
    TASK_SCHEDULER_INTERVAL_SECONDS: int
    LEARNING_DAILY_PREPARATION_ENABLED: bool
    LEARNING_DAILY_PREPARATION_HOUR: int
    LEARNING_DAILY_PREPARATION_MINUTE: int
    LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS: int
    LEARNING_DAILY_TIMEZONE: str
    LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED: bool
    LEARNING_COURSE_LIBRARY_ENABLED: bool
    LEARNING_COURSE_SUPPLY_SCOPE: str
    LEARNING_COURSE_SUPPLY_GRADE_SCOPES: dict[str, str]
    LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS: int
    LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS: int
    LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED: bool
    LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST: list[str]
    LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK: int
    LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD: int
    LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED: bool
    LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND: bool
    LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED: bool
    LEARNING_DYNAMIC_GENERATION_ENABLED: bool
    LEARNING_STATIC_CATALOG_ENABLED: bool
    LEARNING_DYNAMIC_POOL_TARGET: int
    OPENMAIC_QUESTION_TIMEOUT_SECONDS: float
    LEARNING_CLASSROOM_GENERATION_ENABLED: bool
    LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED: bool
    LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED: bool
    LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED: bool
    LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS: int
    LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED: bool
    LEARNING_MEDIA_WORKER_ENABLED: bool
    LEARNING_MEDIA_WORKER_INTERVAL_SECONDS: int
    LEARNING_TTS_PROVIDER: str
    LEARNING_MACOS_SAY_TIMEOUT_SECONDS: float
    LEARNING_VOXCPM_BASE_URL: str
    LEARNING_VOXCPM_BACKEND: str
    LEARNING_VOXCPM_MODEL: str
    LEARNING_VOXCPM_TIMEOUT_SECONDS: float
    LEARNING_MEDIA_STORAGE_ROOT: str
    OPENMAIC_FULL_RUNTIME_ENABLED: bool
    OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED: bool
    OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED: bool
    OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS: int
    OPENMAIC_FULL_RUNTIME_INTERNAL_URL: str
    OPENMAIC_FULL_RUNTIME_PUBLIC_URL: str
    OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS: float
    OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS: int
    OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS: int
    OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED: bool
    OPENMAIC_CONVERSATION_PROBE_ENABLED: bool
    OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS: int
    OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED: bool
    OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED: bool
    OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED: bool
    OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED: bool
    OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID: str
    CARE_ROUTINE_REMINDER_ENABLED: bool
    TASK_WEBSOCKET_ENABLED: bool
    TASK_WEBSOCKET_HOST: str
    TASK_WEBSOCKET_PORT: int
    TASK_WEBSOCKET_PATH: str
    TASK_DELAY_REMINDER_INTERVAL_SECONDS: int
    TASK_DELAY_REMINDER_MAX_COUNT: int
    HARDWARE_ADAPTER: str
    PROMPT_ROOT: str
    AI_PROVIDER: str
    AI_MODEL: str
    AI_API_KEY: str
    AI_BASE_URL: str
    AI_TIMEOUT_SECONDS: float
    AI_VISION_ENABLED: bool
    AI_VISION_MODEL: str
    AI_VISION_TIMEOUT_SECONDS: float
    AI_VISION_MAX_BYTES: int
    AI_VISION_MIN_INTERVAL_SECONDS: float
    AI_VISION_MAX_CALLS_PER_HOUR: int
    AI_VISION_BACKOFF_SECONDS: float
    AI_EVAL_ENABLED: bool
    INTERNAL_API_TOKEN: str
    INTERNAL_ALLOWED_SOURCES: list[str]
    HOST: str
    PORT: int
    DEBUG: bool

    @classmethod
    def from_env(cls) -> "AppConfig":
        app_env = _env("APP_ENV", "development").strip().lower()
        dev_adapters_enabled_default = "1" if app_env in {"development", "test"} else "0"
        database_url = _database_url_for_env(app_env)
        camera_runtime_provider = _env(
            "CAMERA_RUNTIME_PROVIDER",
            _env("APP_CAMERA_RUNTIME_ADAPTER", "disabled"),
        ).strip()
        ai_camera_test_base_url = _env(
            "AI_CAMERA_TEST_BASE_URL",
            _env("APP_CAMERA_BACKEND_URL", ""),
        ).strip()
        ai_provider = _env("APP_AI_PROVIDER", _default_ai_provider()).strip().lower()
        ai_model = _env("APP_AI_MODEL", _default_ai_model(ai_provider)).strip()
        learning_dynamic_generation_enabled = _bool(
            _env("LEARNING_DYNAMIC_GENERATION_ENABLED", "1")
        )
        return cls(
            APP_ENV=app_env,
            SERVICE_NAME=_env("APP_SERVICE_NAME", "ai-camera-app-backend"),
            DATABASE_URL=database_url,
            CORS_ORIGINS=_csv(_env("APP_CORS_ORIGINS", "*" if app_env == "development" else "http://127.0.0.1:8000,http://localhost:8000")),
            AUTH_ACCESS_TOKEN_SECONDS=int(_env("APP_AUTH_ACCESS_SECONDS", "900")),
            AUTH_REFRESH_TOKEN_SECONDS=int(
                _env("APP_AUTH_REFRESH_SECONDS", str(60 * 60 * 24 * 30))
            ),
            STUDENT_AUTH_PEPPER=_env(
                "APP_STUDENT_AUTH_PEPPER",
                DEVELOPMENT_STUDENT_AUTH_PEPPER
                if app_env in {"development", "test"}
                else "",
            ).strip(),
            STUDENT_ACCESS_TOKEN_SECONDS=int(
                _env("APP_STUDENT_ACCESS_SECONDS", "900")
            ),
            STUDENT_REFRESH_TOKEN_SECONDS=int(
                _env("APP_STUDENT_REFRESH_SECONDS", str(60 * 60 * 24 * 30))
            ),
            STUDENT_DEVICE_TOKEN_SECONDS=int(
                _env("APP_STUDENT_DEVICE_SECONDS", str(60 * 60 * 24 * 180))
            ),
            STUDENT_PAIRING_CODE_TTL_SECONDS=int(
                _env("APP_STUDENT_PAIRING_CODE_TTL_SECONDS", "600")
            ),
            STUDENT_QR_CHALLENGE_TTL_SECONDS=int(
                _env("APP_STUDENT_QR_CHALLENGE_TTL_SECONDS", "300")
            ),
            STUDENT_QR_APPROVAL_EXCHANGE_SECONDS=int(
                _env("APP_STUDENT_QR_APPROVAL_EXCHANGE_SECONDS", "60")
            ),
            STUDENT_QR_POLLING_INTERVAL_MS=int(
                _env("APP_STUDENT_QR_POLLING_INTERVAL_MS", "1500")
            ),
            STUDENT_QR_ACTIVE_CHALLENGE_LIMIT=int(
                _env("APP_STUDENT_QR_ACTIVE_CHALLENGE_LIMIT", "3")
            ),
            STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT=int(
                _env("APP_STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT", "100")
            ),
            STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS=int(
                _env("APP_STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS", "60")
            ),
            STUDENT_QR_RATE_LIMIT_MAX=int(
                _env("APP_STUDENT_QR_RATE_LIMIT_MAX", "8")
            ),
            STUDENT_QR_IP_RATE_LIMIT_MAX=int(
                _env("APP_STUDENT_QR_IP_RATE_LIMIT_MAX", "120")
            ),
            STUDENT_QR_RETENTION_SECONDS=int(
                _env("APP_STUDENT_QR_RETENTION_SECONDS", str(60 * 60 * 24 * 7))
            ),
            STUDENT_PIN_PBKDF2_ITERATIONS=int(
                _env("APP_STUDENT_PIN_PBKDF2_ITERATIONS", "210000")
            ),
            STUDENT_PIN_MAX_ATTEMPTS=int(
                _env("APP_STUDENT_PIN_MAX_ATTEMPTS", "5")
            ),
            STUDENT_PIN_LOCK_SECONDS=int(
                _env("APP_STUDENT_PIN_LOCK_SECONDS", "900")
            ),
            SMS_PROVIDER=_env("APP_SMS_PROVIDER", "development" if app_env in {"development", "test"} else "").strip(),
            SMS_TEMPLATE_ID=_env("APP_SMS_TEMPLATE_ID", "login-code"),
            SMS_CODE_TTL_SECONDS=int(_env("APP_SMS_CODE_TTL_SECONDS", "300")),
            SMS_RESEND_COOLDOWN_SECONDS=int(_env("APP_SMS_RESEND_COOLDOWN_SECONDS", "60")),
            SMS_MAX_ATTEMPTS=int(_env("APP_SMS_MAX_ATTEMPTS", "5")),
            DEV_ADAPTERS_ENABLED=_bool(_env("APP_ENABLE_DEV_ADAPTERS", dev_adapters_enabled_default)),
            CAMERA_RUNTIME_PROVIDER=camera_runtime_provider,
            CAMERA_RUNTIME_ADAPTER=camera_runtime_provider,
            AI_CAMERA_TEST_BASE_URL=ai_camera_test_base_url,
            AI_CAMERA_TEST_WORKSPACE=_env("AI_CAMERA_TEST_WORKSPACE", ""),
            CAMERA_BACKEND_URL=ai_camera_test_base_url,
            CAMERA_COMMAND_TIMEOUT=float(_env("CAMERA_COMMAND_TIMEOUT", "8")),
            CAMERA_MONITOR_ENABLED=_bool(_env("CAMERA_MONITOR_ENABLED", "1")),
            CAMERA_SPEAKER_ENABLED=_bool(_env("CAMERA_SPEAKER_ENABLED", "1")),
            CAMERA_STREAM_URL=_env("CAMERA_STREAM_URL", ""),
            CAMERA_SNAPSHOT_URL=_env("CAMERA_SNAPSHOT_URL", ""),
            MEDIA_GATEWAY_ENABLED=_bool(
                _env("APP_MEDIA_GATEWAY_ENABLED", "0")
            ),
            MEDIA_GATEWAY_API_BASE_URL=_env(
                "APP_MEDIA_GATEWAY_API_BASE_URL",
                "http://127.0.0.1:1984",
            ).strip(),
            MEDIA_GATEWAY_PUBLIC_BASE_URL=_env(
                "APP_MEDIA_GATEWAY_PUBLIC_BASE_URL",
                "",
            ).strip(),
            MEDIA_GATEWAY_TIMEOUT_SECONDS=float(
                _env("APP_MEDIA_GATEWAY_TIMEOUT_SECONDS", "5")
            ),
            MEDIA_GATEWAY_AUTO_START=_bool(
                _env("APP_MEDIA_GATEWAY_AUTO_START", "0")
            ),
            MEDIA_GATEWAY_BINARY=_env(
                "APP_MEDIA_GATEWAY_BINARY",
                "",
            ).strip(),
            MEDIA_GATEWAY_CONFIG_FILE=_env(
                "APP_MEDIA_GATEWAY_CONFIG_FILE",
                "",
            ).strip(),
            MEDIA_GATEWAY_VERSION=_env(
                "APP_MEDIA_GATEWAY_VERSION",
                MEDIA_GATEWAY_REQUIRED_VERSION,
            ).strip(),
            CAMERA_SIGNALING_PUBLIC_BASE_URL=_env(
                "CAMERA_SIGNALING_PUBLIC_BASE_URL",
                _env("APP_CAMERA_SIGNALING_PUBLIC_BASE_URL", ""),
            ).strip(),
            ONVIF_DISCOVERY_TIMEOUT_SECONDS=float(
                _env("ONVIF_DISCOVERY_TIMEOUT_SECONDS", "1.5")
            ),
            ONVIF_HTTP_TIMEOUT_SECONDS=float(_env("ONVIF_HTTP_TIMEOUT_SECONDS", "4")),
            ONVIF_RTSP_TIMEOUT_SECONDS=float(_env("ONVIF_RTSP_TIMEOUT_SECONDS", "4")),
            ONVIF_DISCOVERY_TOKEN_TTL_SECONDS=int(
                _env("ONVIF_DISCOVERY_TOKEN_TTL_SECONDS", "90")
            ),
            ONVIF_SUPPORTED_MANUFACTURERS=_csv(
                _env("ONVIF_SUPPORTED_MANUFACTURERS", "Vatilon")
            ),
            ONVIF_SUPPORTED_MODELS=_csv(_env("ONVIF_SUPPORTED_MODELS", "T62")),
            ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED=_bool(
                _env("ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED", "0")
            ),
            ONVIF_BOOTSTRAP_USERNAME=_env("ONVIF_BOOTSTRAP_USERNAME", "").strip(),
            ONVIF_BOOTSTRAP_PASSWORD=_env("ONVIF_BOOTSTRAP_PASSWORD", ""),
            DEVICE_SECRET_STORE_DIR=_env(
                "APP_DEVICE_SECRET_STORE_DIR",
                str(BACKEND_ROOT / "data" / "device-secrets"),
            ),
            DEVICE_SECRET_KEY=_env("APP_DEVICE_SECRET_KEY", "").strip(),
            DEVICE_SECRET_KEY_FILE=_env(
                "APP_DEVICE_SECRET_KEY_FILE",
                str(BACKEND_ROOT / "data" / ".device-secret.key"),
            ),
            TASK_REMINDER_LEAD_SECONDS=int(_env("TASK_REMINDER_LEAD_SECONDS", "300")),
            TASK_SCHEDULER_ENABLED=_bool(
                _env(
                    "TASK_SCHEDULER_ENABLED",
                    "1" if app_env == "development" else "0",
                )
            ),
            TASK_SCHEDULER_INTERVAL_SECONDS=int(_env("TASK_SCHEDULER_INTERVAL_SECONDS", "15")),
            LEARNING_DAILY_PREPARATION_ENABLED=_bool(
                _env("LEARNING_DAILY_PREPARATION_ENABLED", "1")
            ),
            LEARNING_DAILY_PREPARATION_HOUR=int(
                _env("LEARNING_DAILY_PREPARATION_HOUR", "5")
            ),
            LEARNING_DAILY_PREPARATION_MINUTE=int(
                _env("LEARNING_DAILY_PREPARATION_MINUTE", "0")
            ),
            LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS=int(
                _env("LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS", "60")
            ),
            LEARNING_DAILY_TIMEZONE=_env(
                "LEARNING_DAILY_TIMEZONE", "Asia/Shanghai"
            ).strip(),
            LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED=_bool(
                _env("LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED", "0")
            ),
            LEARNING_COURSE_LIBRARY_ENABLED=_bool(_env("LEARNING_COURSE_LIBRARY_ENABLED", "1")),
            LEARNING_COURSE_SUPPLY_SCOPE=_env("LEARNING_COURSE_SUPPLY_SCOPE", "canary"),
            LEARNING_COURSE_SUPPLY_GRADE_SCOPES=json.loads(_env("LEARNING_COURSE_SUPPLY_GRADE_SCOPES", "{}")),
            LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS=int(
                _env("LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS", "15")
            ),
            LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS=int(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS",
                    str(LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS),
                )
            ),
            LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED=_bool(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED",
                    "0",
                )
            ),
            LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST=_csv(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST",
                    "primary_1",
                )
            ),
            LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK=int(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK",
                    "1",
                )
            ),
            LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD=int(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD",
                    "1",
                )
            ),
            LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED=_bool(
                _env("LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED", "1")
            ),
            LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND=_bool(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND",
                    "1",
                )
            ),
            LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED=_bool(
                _env(
                    "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED",
                    "0",
                )
            ),
            LEARNING_DYNAMIC_GENERATION_ENABLED=learning_dynamic_generation_enabled,
            LEARNING_STATIC_CATALOG_ENABLED=_bool(
                _env(
                    "LEARNING_STATIC_CATALOG_ENABLED",
                    "0" if learning_dynamic_generation_enabled else "1",
                )
            ),
            LEARNING_DYNAMIC_POOL_TARGET=max(
                1,
                int(_env("LEARNING_DYNAMIC_POOL_TARGET", "1")),
            ),
            OPENMAIC_QUESTION_TIMEOUT_SECONDS=float(
                _env("OPENMAIC_QUESTION_TIMEOUT_SECONDS", "420")
            ),
            LEARNING_CLASSROOM_GENERATION_ENABLED=_bool(
                _env(
                    "LEARNING_CLASSROOM_GENERATION_ENABLED",
                    "1" if learning_dynamic_generation_enabled else "0",
                )
            ),
            LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED=_bool(
                _env("LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED", "0")
            ),
            LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED=_bool(
                _env("LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED", "0")
            ),
            LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED=_bool(
                _env("LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED", "0")
            ),
            LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS=int(
                _env("LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS", "15")
            ),
            LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED=_bool(
                _env("LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED", "0")
            ),
            LEARNING_MEDIA_WORKER_ENABLED=_bool(
                _env("LEARNING_MEDIA_WORKER_ENABLED", "0")
            ),
            LEARNING_MEDIA_WORKER_INTERVAL_SECONDS=int(
                _env("LEARNING_MEDIA_WORKER_INTERVAL_SECONDS", "15")
            ),
            LEARNING_TTS_PROVIDER=_env(
                "LEARNING_TTS_PROVIDER", "voxcpm2"
            ).strip().lower(),
            LEARNING_MACOS_SAY_TIMEOUT_SECONDS=float(
                _env("LEARNING_MACOS_SAY_TIMEOUT_SECONDS", "30")
            ),
            LEARNING_VOXCPM_BASE_URL=_env(
                "LEARNING_VOXCPM_BASE_URL", ""
            ).strip(),
            LEARNING_VOXCPM_BACKEND=_env(
                "LEARNING_VOXCPM_BACKEND", "vllm-omni"
            ).strip().lower(),
            LEARNING_VOXCPM_MODEL=_env(
                "LEARNING_VOXCPM_MODEL", "openbmb/VoxCPM2"
            ).strip(),
            LEARNING_VOXCPM_TIMEOUT_SECONDS=float(
                _env("LEARNING_VOXCPM_TIMEOUT_SECONDS", "30")
            ),
            LEARNING_MEDIA_STORAGE_ROOT=_env(
                "LEARNING_MEDIA_STORAGE_ROOT", "data/learning-media"
            ).strip(),
            OPENMAIC_FULL_RUNTIME_ENABLED=_bool(
                _env("OPENMAIC_FULL_RUNTIME_ENABLED", "0")
            ),
            OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED=_bool(
                _env("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", "0")
            ),
            OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED=_bool(
                _env("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED", "0")
            ),
            OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS=int(
                _env(
                    "OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS", "20"
                )
            ),
            OPENMAIC_FULL_RUNTIME_INTERNAL_URL=_env(
                "OPENMAIC_FULL_RUNTIME_INTERNAL_URL", ""
            ).strip(),
            OPENMAIC_FULL_RUNTIME_PUBLIC_URL=_env(
                "OPENMAIC_FULL_RUNTIME_PUBLIC_URL", ""
            ).strip(),
            OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS=float(
                _env("OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", "30")
            ),
            OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS=int(
                _env("OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS", "60")
            ),
            OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS=int(
                _env("OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS", "14400")
            ),
            OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED=_bool(
                _env("OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED", "0")
            ),
            OPENMAIC_CONVERSATION_PROBE_ENABLED=_bool(
                _env("OPENMAIC_CONVERSATION_PROBE_ENABLED", "0")
            ),
            OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS=int(
                _env("OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS", "90")
            ),
            OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED=_bool(
                _env("OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED", "0")
            ),
            OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED=_bool(
                _env(
                    "OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED",
                    "0",
                )
            ),
            OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED=_bool(
                _env("OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED", "0")
            ),
            OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED=_bool(
                _env("OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED", "0")
            ),
            OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID=_env(
                "OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID", ""
            ).strip(),
            CARE_ROUTINE_REMINDER_ENABLED=_bool(_env("CARE_ROUTINE_REMINDER_ENABLED", "1")),
            TASK_WEBSOCKET_ENABLED=_bool(
                _env(
                    "TASK_WEBSOCKET_ENABLED",
                    "1" if app_env in {"development", "staging", "production"} else "0",
                )
            ),
            TASK_WEBSOCKET_HOST=_env("TASK_WEBSOCKET_HOST", _env("APP_HOST", "0.0.0.0" if app_env == "development" else "127.0.0.1")),
            TASK_WEBSOCKET_PORT=int(_env("TASK_WEBSOCKET_PORT", "8001")),
            TASK_WEBSOCKET_PATH=_env("TASK_WEBSOCKET_PATH", "/api/tasks/stream"),
            TASK_DELAY_REMINDER_INTERVAL_SECONDS=int(
                _env("TASK_DELAY_REMINDER_INTERVAL_SECONDS", "180")
            ),
            TASK_DELAY_REMINDER_MAX_COUNT=int(_env("TASK_DELAY_REMINDER_MAX_COUNT", "3")),
            HARDWARE_ADAPTER=_env("APP_HARDWARE_ADAPTER", "disabled").strip(),
            PROMPT_ROOT=_env("APP_PROMPT_ROOT", str(BACKEND_ROOT / "prompts")),
            AI_PROVIDER=ai_provider,
            AI_MODEL=ai_model,
            AI_API_KEY=_env("APP_AI_API_KEY", _default_ai_api_key(ai_provider)).strip(),
            AI_BASE_URL=_env("APP_AI_BASE_URL", _default_ai_base_url(ai_provider)).strip(),
            AI_TIMEOUT_SECONDS=float(_env("APP_AI_TIMEOUT_SECONDS", "8")),
            AI_VISION_ENABLED=_bool(_env("APP_AI_VISION_ENABLED", "1")),
            AI_VISION_MODEL=_env(
                "APP_AI_VISION_MODEL",
                _env("KIMI_VISION_MODEL", ai_model),
            ).strip(),
            AI_VISION_TIMEOUT_SECONDS=float(_env("APP_AI_VISION_TIMEOUT_SECONDS", "20")),
            AI_VISION_MAX_BYTES=int(_env("APP_AI_VISION_MAX_BYTES", "524288")),
            AI_VISION_MIN_INTERVAL_SECONDS=float(_env("APP_AI_VISION_MIN_INTERVAL_SECONDS", "60")),
            AI_VISION_MAX_CALLS_PER_HOUR=int(
                _env(
                    "APP_AI_VISION_MAX_CALLS_PER_HOUR",
                    "72" if app_env == "development" else "20",
                )
            ),
            AI_VISION_BACKOFF_SECONDS=float(_env("APP_AI_VISION_BACKOFF_SECONDS", "300")),
            AI_EVAL_ENABLED=_bool(_env("APP_AI_EVAL_ENABLED", "0")),
            INTERNAL_API_TOKEN=_env("INTERNAL_API_TOKEN", _env("APP_INTERNAL_API_TOKEN", "")).strip(),
            INTERNAL_ALLOWED_SOURCES=_csv(_env("INTERNAL_ALLOWED_SOURCES", _env("APP_INTERNAL_ALLOWED_SOURCES", ""))),
            HOST=_env("APP_HOST", "0.0.0.0" if app_env == "development" else "127.0.0.1"),
            PORT=int(_env("APP_PORT", _env("PORT", "8000"))),
            DEBUG=_bool(_env("APP_DEBUG", _env("FLASK_DEBUG", "0"))),
        )

    def to_flask_config(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        if self.APP_ENV not in VALID_APP_ENVS:
            raise ConfigError(f"Unsupported APP_ENV: {self.APP_ENV}")

        if not 0 <= self.LEARNING_DAILY_PREPARATION_HOUR <= 23:
            raise ConfigError("LEARNING_DAILY_PREPARATION_HOUR must be between 0 and 23.")
        if not 0 <= self.LEARNING_DAILY_PREPARATION_MINUTE <= 59:
            raise ConfigError(
                "LEARNING_DAILY_PREPARATION_MINUTE must be between 0 and 59."
            )
        if self.LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS < 10:
            raise ConfigError(
                "LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS must be at least 10."
            )
        if not self.LEARNING_DAILY_TIMEZONE:
            raise ConfigError("LEARNING_DAILY_TIMEZONE must not be empty.")
        if self.LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS < 5:
            raise ConfigError(
                "LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS must be at least 5."
            )
        if (
            self.LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS
            < LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS
        ):
            raise ConfigError(
                "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS must be at least 360."
            )
        _validate_learning_curriculum_preparation_config(
            runner_enabled=self.LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED,
            content_generation_enabled=(
                self.LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED
            ),
            grade_allowlist=self.LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST,
            max_provider_subcalls_per_tick=(
                self.LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK
            ),
            max_inflight_per_build=(
                self.LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD
            ),
            canary_enabled=self.LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED,
            canary_auto_expand=(
                self.LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND
            ),
            reconciliation_enabled=(
                self.LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED
            ),
        )
        _validate_formal_production_gate_config(
            audio_validation_enabled=(
                self.LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED
            ),
            auto_publication_enabled=(
                self.LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED
            ),
        )
        if self.LEARNING_DYNAMIC_POOL_TARGET < 1:
            raise ConfigError("LEARNING_DYNAMIC_POOL_TARGET must be at least 1.")
        if not 30 <= self.OPENMAIC_QUESTION_TIMEOUT_SECONDS <= 900:
            raise ConfigError(
                "OPENMAIC_QUESTION_TIMEOUT_SECONDS must be between 30 and 900."
            )
        if self.LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS < 5:
            raise ConfigError(
                "LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS must be at least 5."
            )
        _validate_learning_media_config(
            app_env=self.APP_ENV,
            worker_enabled=self.LEARNING_MEDIA_WORKER_ENABLED,
            interval_seconds=self.LEARNING_MEDIA_WORKER_INTERVAL_SECONDS,
            provider=self.LEARNING_TTS_PROVIDER,
            macos_say_timeout_seconds=self.LEARNING_MACOS_SAY_TIMEOUT_SECONDS,
            base_url=self.LEARNING_VOXCPM_BASE_URL,
            backend=self.LEARNING_VOXCPM_BACKEND,
            model=self.LEARNING_VOXCPM_MODEL,
            timeout_seconds=self.LEARNING_VOXCPM_TIMEOUT_SECONDS,
            storage_root=self.LEARNING_MEDIA_STORAGE_ROOT,
        )
        _validate_openmaic_full_runtime_config(
            app_env=self.APP_ENV,
            enabled=self.OPENMAIC_FULL_RUNTIME_ENABLED,
            generation_enabled=self.OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED,
            autorun_enabled=self.OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED,
            generation_interval_seconds=(
                self.OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS
            ),
            internal_url=self.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
            public_url=self.OPENMAIC_FULL_RUNTIME_PUBLIC_URL,
            timeout_seconds=self.OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS,
            launch_ttl_seconds=self.OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS,
            session_ttl_seconds=self.OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS,
        )
        _validate_formal_runtime_candidate_config(
            enabled=self.LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED,
            classroom_runner_enabled=self.LEARNING_CLASSROOM_GENERATION_ENABLED,
            runtime_enabled=self.OPENMAIC_FULL_RUNTIME_ENABLED,
            generation_enabled=self.OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED,
            autorun_enabled=self.OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED,
        )
        _validate_openmaic_conversation_probe_config(
            runtime_enabled=self.OPENMAIC_FULL_RUNTIME_ENABLED,
            enabled=self.OPENMAIC_CONVERSATION_PROBE_ENABLED,
            ttl_seconds=self.OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS,
        )
        _validate_openmaic_deterministic_recovery_config(
            runtime_enabled=self.OPENMAIC_FULL_RUNTIME_ENABLED,
            probe_enabled=self.OPENMAIC_CONVERSATION_PROBE_ENABLED,
            generation_enabled=self.OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED,
            autorun_enabled=self.OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED,
            enabled=self.OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED,
            redispatch_enabled=(
                self.OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED
            ),
            internal_url=self.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
            internal_token=self.INTERNAL_API_TOKEN,
        )
        _validate_openmaic_tts_credential_recovery_config(
            runtime_enabled=self.OPENMAIC_FULL_RUNTIME_ENABLED,
            probe_enabled=self.OPENMAIC_CONVERSATION_PROBE_ENABLED,
            deterministic_recovery_enabled=(
                self.OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED
            ),
            redispatch_enabled=(
                self.OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED
            ),
            generation_enabled=self.OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED,
            autorun_enabled=self.OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED,
            enabled=self.OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED,
            internal_url=self.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
            internal_token=self.INTERNAL_API_TOKEN,
        )
        _validate_openmaic_formal_citation_recovery_config(
            runtime_enabled=self.OPENMAIC_FULL_RUNTIME_ENABLED,
            generation_enabled=self.OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED,
            enabled=self.OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED,
            source_job_id=(
                self.OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID
            ),
            internal_url=self.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
            internal_token=self.INTERNAL_API_TOKEN,
        )

        _validate_student_auth_config(
            app_env=self.APP_ENV,
            pepper=self.STUDENT_AUTH_PEPPER,
            access_token_seconds=self.STUDENT_ACCESS_TOKEN_SECONDS,
            refresh_token_seconds=self.STUDENT_REFRESH_TOKEN_SECONDS,
            device_token_seconds=self.STUDENT_DEVICE_TOKEN_SECONDS,
            pairing_code_ttl_seconds=self.STUDENT_PAIRING_CODE_TTL_SECONDS,
            qr_challenge_ttl_seconds=self.STUDENT_QR_CHALLENGE_TTL_SECONDS,
            qr_approval_exchange_seconds=self.STUDENT_QR_APPROVAL_EXCHANGE_SECONDS,
            qr_polling_interval_ms=self.STUDENT_QR_POLLING_INTERVAL_MS,
            qr_active_challenge_limit=self.STUDENT_QR_ACTIVE_CHALLENGE_LIMIT,
            qr_ip_active_challenge_limit=self.STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT,
            qr_rate_limit_window_seconds=self.STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS,
            qr_rate_limit_max=self.STUDENT_QR_RATE_LIMIT_MAX,
            qr_ip_rate_limit_max=self.STUDENT_QR_IP_RATE_LIMIT_MAX,
            qr_retention_seconds=self.STUDENT_QR_RETENTION_SECONDS,
            pin_pbkdf2_iterations=self.STUDENT_PIN_PBKDF2_ITERATIONS,
            pin_max_attempts=self.STUDENT_PIN_MAX_ATTEMPTS,
            pin_lock_seconds=self.STUDENT_PIN_LOCK_SECONDS,
        )

        _validate_media_gateway_config(
            app_env=self.APP_ENV,
            enabled=self.MEDIA_GATEWAY_ENABLED,
            api_base_url=self.MEDIA_GATEWAY_API_BASE_URL,
            public_base_url=self.MEDIA_GATEWAY_PUBLIC_BASE_URL,
            signaling_public_base_url=self.CAMERA_SIGNALING_PUBLIC_BASE_URL,
            timeout_seconds=self.MEDIA_GATEWAY_TIMEOUT_SECONDS,
            version=self.MEDIA_GATEWAY_VERSION,
        )

        _validate_onvif_bootstrap_credentials(
            app_env=self.APP_ENV,
            dev_adapters_enabled=self.DEV_ADAPTERS_ENABLED,
            enabled=self.ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED,
            username=self.ONVIF_BOOTSTRAP_USERNAME,
            password=self.ONVIF_BOOTSTRAP_PASSWORD,
        )

        if self.APP_ENV in {"staging", "production"} and not self.DATABASE_URL:
            raise ConfigError("APP_DATABASE_URL is required in staging/production.")

        dialect = _database_dialect(self.DATABASE_URL)
        if dialect != "mysql":
            raise ConfigError("Only MySQL databases are supported.")

        if self.APP_ENV == "production":
            if not self.CORS_ORIGINS or "*" in self.CORS_ORIGINS:
                raise ConfigError("APP_CORS_ORIGINS must be explicit in production.")
            if self.DEV_ADAPTERS_ENABLED:
                raise ConfigError("APP_ENABLE_DEV_ADAPTERS must be false in production.")
            if self.SMS_PROVIDER == "development":
                raise ConfigError("APP_SMS_PROVIDER=development is not allowed in production.")
            if self.CAMERA_RUNTIME_PROVIDER in {"ai_camera_test", "mock"}:
                raise ConfigError("CAMERA_RUNTIME_PROVIDER cannot use development adapters in production.")
            if not self.INTERNAL_API_TOKEN:
                raise ConfigError("INTERNAL_API_TOKEN is required in production.")


def apply_test_defaults(config: dict) -> dict:
    next_config = dict(config)
    next_config.setdefault("APP_ENV", "test")
    next_config.setdefault("DEV_ADAPTERS_ENABLED", True)
    next_config.setdefault("SMS_PROVIDER", "development")
    next_config.setdefault("TASK_SCHEDULER_ENABLED", False)
    next_config.setdefault("LEARNING_DAILY_PREPARATION_ENABLED", False)
    next_config.setdefault("LEARNING_DYNAMIC_GENERATION_ENABLED", False)
    next_config.setdefault("LEARNING_STATIC_CATALOG_ENABLED", True)
    next_config.setdefault("LEARNING_DYNAMIC_POOL_TARGET", 1)
    next_config.setdefault("OPENMAIC_QUESTION_TIMEOUT_SECONDS", 420.0)
    next_config.setdefault("LEARNING_CLASSROOM_GENERATION_ENABLED", False)
    next_config.setdefault("LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED", False)
    next_config.setdefault("LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED", False)
    next_config.setdefault("LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED", False)
    next_config.setdefault("LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED", False)
    next_config.setdefault("LEARNING_COURSE_LIBRARY_ENABLED", False)
    next_config.setdefault("LEARNING_COURSE_SUPPLY_SCOPE", "canary")
    next_config.setdefault("LEARNING_COURSE_SUPPLY_GRADE_SCOPES", {})
    next_config.setdefault("LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS", 15)
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS",
        LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS,
    )
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED", False
    )
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST", ["primary_1"]
    )
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK", 1
    )
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD", 1
    )
    next_config.setdefault("LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED", True)
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND", True
    )
    next_config.setdefault(
        "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED", False
    )
    next_config.setdefault("LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS", 15)
    next_config.setdefault("LEARNING_MEDIA_WORKER_ENABLED", False)
    next_config.setdefault("LEARNING_MEDIA_WORKER_INTERVAL_SECONDS", 15)
    next_config.setdefault("LEARNING_TTS_PROVIDER", "voxcpm2")
    next_config.setdefault("LEARNING_MACOS_SAY_TIMEOUT_SECONDS", 30.0)
    next_config.setdefault("LEARNING_VOXCPM_BASE_URL", "")
    next_config.setdefault("LEARNING_VOXCPM_BACKEND", "vllm-omni")
    next_config.setdefault("LEARNING_VOXCPM_MODEL", "openbmb/VoxCPM2")
    next_config.setdefault("LEARNING_VOXCPM_TIMEOUT_SECONDS", 30.0)
    next_config.setdefault("LEARNING_MEDIA_STORAGE_ROOT", "data/learning-media")
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_ENABLED", False)
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False)
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED", False)
    next_config.setdefault(
        "OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS", 20
    )
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_INTERNAL_URL", "")
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_PUBLIC_URL", "")
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30.0)
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS", 60)
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS", 14400)
    next_config.setdefault("OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED", False)
    next_config.setdefault("OPENMAIC_CONVERSATION_PROBE_ENABLED", False)
    next_config.setdefault("OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS", 90)
    next_config.setdefault("OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED", False)
    next_config.setdefault(
        "OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED", False
    )
    next_config.setdefault("OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED", False)
    next_config.setdefault("OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED", False)
    next_config.setdefault(
        "OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID", ""
    )
    next_config.setdefault("TASK_WEBSOCKET_ENABLED", False)
    next_config.setdefault("STUDENT_AUTH_PEPPER", DEVELOPMENT_STUDENT_AUTH_PEPPER)
    next_config.setdefault("STUDENT_ACCESS_TOKEN_SECONDS", 900)
    next_config.setdefault("STUDENT_REFRESH_TOKEN_SECONDS", 3600)
    next_config.setdefault("STUDENT_DEVICE_TOKEN_SECONDS", 86400)
    next_config.setdefault("STUDENT_PAIRING_CODE_TTL_SECONDS", 600)
    next_config.setdefault("STUDENT_QR_CHALLENGE_TTL_SECONDS", 300)
    next_config.setdefault("STUDENT_QR_APPROVAL_EXCHANGE_SECONDS", 60)
    next_config.setdefault("STUDENT_QR_POLLING_INTERVAL_MS", 1500)
    next_config.setdefault("STUDENT_QR_ACTIVE_CHALLENGE_LIMIT", 3)
    next_config.setdefault("STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT", 100)
    next_config.setdefault("STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS", 60)
    next_config.setdefault("STUDENT_QR_RATE_LIMIT_MAX", 8)
    next_config.setdefault("STUDENT_QR_IP_RATE_LIMIT_MAX", 120)
    next_config.setdefault("STUDENT_QR_RETENTION_SECONDS", 60 * 60 * 24 * 7)
    next_config.setdefault("STUDENT_PIN_PBKDF2_ITERATIONS", 1000)
    next_config.setdefault("STUDENT_PIN_MAX_ATTEMPTS", 5)
    next_config.setdefault("STUDENT_PIN_LOCK_SECONDS", 900)
    next_config.setdefault("LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED", False)
    return next_config


def validate_flask_config(config: dict) -> None:
    app_env = str(config.get("APP_ENV", "development")).strip().lower()
    if app_env not in VALID_APP_ENVS:
        raise ConfigError(f"Unsupported APP_ENV: {app_env}")
    learning_hour = int(config.get("LEARNING_DAILY_PREPARATION_HOUR", 5))
    learning_minute = int(config.get("LEARNING_DAILY_PREPARATION_MINUTE", 0))
    learning_interval = int(
        config.get("LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS", 60)
    )
    if not 0 <= learning_hour <= 23:
        raise ConfigError("LEARNING_DAILY_PREPARATION_HOUR must be between 0 and 23.")
    if not 0 <= learning_minute <= 59:
        raise ConfigError(
            "LEARNING_DAILY_PREPARATION_MINUTE must be between 0 and 59."
        )
    if learning_interval < 10:
        raise ConfigError(
            "LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS must be at least 10."
        )
    if not str(config.get("LEARNING_DAILY_TIMEZONE") or "Asia/Shanghai").strip():
        raise ConfigError("LEARNING_DAILY_TIMEZONE must not be empty.")
    if type(config.get("LEARNING_COURSE_LIBRARY_ENABLED", False)) is not bool:
        raise ConfigError("LEARNING_COURSE_LIBRARY_ENABLED must be boolean.")
    if config.get("LEARNING_COURSE_SUPPLY_SCOPE", "canary") not in {"canary", "first_unit", "catalog"}:
        raise ConfigError("LEARNING_COURSE_SUPPLY_SCOPE must be canary, first_unit or catalog.")
    grade_scopes = config.get("LEARNING_COURSE_SUPPLY_GRADE_SCOPES", {})
    if (type(grade_scopes) is not dict or any(
        grade not in {f"primary_{n}" for n in range(1, 7)} or scope not in {"canary", "first_unit", "catalog"}
        for grade, scope in grade_scopes.items()
    )):
        raise ConfigError("LEARNING_COURSE_SUPPLY_GRADE_SCOPES must map registered grades to explicit scopes.")
    if int(config.get("LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS", 15)) < 5:
        raise ConfigError(
            "LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS must be at least 5."
        )
    if int(
        config.get(
            "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS",
            LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS,
        )
    ) < LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS:
        raise ConfigError(
            "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS must be at least 360."
        )
    _validate_learning_curriculum_preparation_config(
        runner_enabled=config.get(
            "LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED", False
        ),
        content_generation_enabled=config.get(
            "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED", False
        ),
        grade_allowlist=config.get(
            "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST", ["primary_1"]
        ),
        max_provider_subcalls_per_tick=config.get(
            "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK",
            1,
        ),
        max_inflight_per_build=config.get(
            "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD", 1
        ),
        canary_enabled=config.get(
            "LEARNING_CURRICULUM_PREPARATION_CANARY_ENABLED", True
        ),
        canary_auto_expand=config.get(
            "LEARNING_CURRICULUM_PREPARATION_CANARY_AUTO_EXPAND", True
        ),
        reconciliation_enabled=config.get(
            "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED", False
        ),
    )
    _validate_formal_production_gate_config(
        audio_validation_enabled=config.get(
            "LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED", False
        ),
        auto_publication_enabled=config.get(
            "LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED", False
        ),
    )
    if int(config.get("LEARNING_DYNAMIC_POOL_TARGET", 1)) < 1:
        raise ConfigError("LEARNING_DYNAMIC_POOL_TARGET must be at least 1.")
    if not 30 <= float(config.get("OPENMAIC_QUESTION_TIMEOUT_SECONDS", 420)) <= 900:
        raise ConfigError(
            "OPENMAIC_QUESTION_TIMEOUT_SECONDS must be between 30 and 900."
        )
    if int(config.get("LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS", 15)) < 5:
        raise ConfigError(
            "LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS must be at least 5."
        )
    _validate_learning_media_config(
        app_env=app_env,
        worker_enabled=bool(config.get("LEARNING_MEDIA_WORKER_ENABLED", False)),
        interval_seconds=int(
            config.get("LEARNING_MEDIA_WORKER_INTERVAL_SECONDS", 15)
        ),
        provider=str(config.get("LEARNING_TTS_PROVIDER") or "voxcpm2"),
        macos_say_timeout_seconds=float(
            config.get("LEARNING_MACOS_SAY_TIMEOUT_SECONDS", 30)
        ),
        base_url=str(config.get("LEARNING_VOXCPM_BASE_URL") or ""),
        backend=str(config.get("LEARNING_VOXCPM_BACKEND") or "vllm-omni"),
        model=str(config.get("LEARNING_VOXCPM_MODEL") or "openbmb/VoxCPM2"),
        timeout_seconds=float(config.get("LEARNING_VOXCPM_TIMEOUT_SECONDS", 30)),
        storage_root=str(
            config.get("LEARNING_MEDIA_STORAGE_ROOT") or "data/learning-media"
        ),
    )
    _validate_openmaic_full_runtime_config(
        app_env=app_env,
        enabled=bool(config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False)),
        generation_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False)
        ),
        autorun_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED", False)
        ),
        generation_interval_seconds=int(
            config.get(
                "OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS", 20
            )
        ),
        internal_url=str(config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""),
        public_url=str(config.get("OPENMAIC_FULL_RUNTIME_PUBLIC_URL") or ""),
        timeout_seconds=float(
            config.get("OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30)
        ),
        launch_ttl_seconds=int(
            config.get("OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS", 60)
        ),
        session_ttl_seconds=int(
            config.get("OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS", 14400)
        ),
    )
    _validate_formal_runtime_candidate_config(
        enabled=bool(
            config.get("LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED", False)
        ),
        classroom_runner_enabled=bool(
            config.get("LEARNING_CLASSROOM_GENERATION_ENABLED", False)
        ),
        runtime_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False)
        ),
        generation_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False)
        ),
        autorun_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED", False)
        ),
    )
    _validate_openmaic_conversation_probe_config(
        runtime_enabled=bool(config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False)),
        enabled=bool(config.get("OPENMAIC_CONVERSATION_PROBE_ENABLED", False)),
        ttl_seconds=int(config.get("OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS", 90)),
    )
    _validate_openmaic_deterministic_recovery_config(
        runtime_enabled=bool(config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False)),
        probe_enabled=bool(config.get("OPENMAIC_CONVERSATION_PROBE_ENABLED", False)),
        generation_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False)
        ),
        autorun_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED", False)
        ),
        enabled=bool(config.get("OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED", False)),
        redispatch_enabled=bool(
            config.get(
                "OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED", False
            )
        ),
        internal_url=str(config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""),
        internal_token=str(config.get("INTERNAL_API_TOKEN") or ""),
    )
    _validate_openmaic_tts_credential_recovery_config(
        runtime_enabled=bool(config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False)),
        probe_enabled=bool(config.get("OPENMAIC_CONVERSATION_PROBE_ENABLED", False)),
        deterministic_recovery_enabled=bool(
            config.get("OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED", False)
        ),
        redispatch_enabled=bool(
            config.get(
                "OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED", False
            )
        ),
        generation_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False)
        ),
        autorun_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED", False)
        ),
        enabled=bool(
            config.get("OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED", False)
        ),
        internal_url=str(config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""),
        internal_token=str(config.get("INTERNAL_API_TOKEN") or ""),
    )
    _validate_openmaic_formal_citation_recovery_config(
        runtime_enabled=bool(config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False)),
        generation_enabled=bool(
            config.get("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False)
        ),
        enabled=bool(
            config.get("OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED", False)
        ),
        source_job_id=str(
            config.get("OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID") or ""
        ),
        internal_url=str(config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""),
        internal_token=str(config.get("INTERNAL_API_TOKEN") or ""),
    )
    _validate_student_auth_config(
        app_env=app_env,
        pepper=str(config.get("STUDENT_AUTH_PEPPER") or ""),
        access_token_seconds=int(config.get("STUDENT_ACCESS_TOKEN_SECONDS", 900)),
        refresh_token_seconds=int(config.get("STUDENT_REFRESH_TOKEN_SECONDS", 2592000)),
        device_token_seconds=int(config.get("STUDENT_DEVICE_TOKEN_SECONDS", 15552000)),
        pairing_code_ttl_seconds=int(
            config.get("STUDENT_PAIRING_CODE_TTL_SECONDS", 600)
        ),
        qr_challenge_ttl_seconds=int(
            config.get("STUDENT_QR_CHALLENGE_TTL_SECONDS", 300)
        ),
        qr_approval_exchange_seconds=int(
            config.get("STUDENT_QR_APPROVAL_EXCHANGE_SECONDS", 60)
        ),
        qr_polling_interval_ms=int(
            config.get("STUDENT_QR_POLLING_INTERVAL_MS", 1500)
        ),
        qr_active_challenge_limit=int(
            config.get("STUDENT_QR_ACTIVE_CHALLENGE_LIMIT", 3)
        ),
        qr_ip_active_challenge_limit=int(
            config.get("STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT", 100)
        ),
        qr_rate_limit_window_seconds=int(
            config.get("STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS", 60)
        ),
        qr_rate_limit_max=int(config.get("STUDENT_QR_RATE_LIMIT_MAX", 8)),
        qr_ip_rate_limit_max=int(
            config.get("STUDENT_QR_IP_RATE_LIMIT_MAX", 120)
        ),
        qr_retention_seconds=int(
            config.get("STUDENT_QR_RETENTION_SECONDS", 60 * 60 * 24 * 7)
        ),
        pin_pbkdf2_iterations=int(
            config.get("STUDENT_PIN_PBKDF2_ITERATIONS", 210000)
        ),
        pin_max_attempts=int(config.get("STUDENT_PIN_MAX_ATTEMPTS", 5)),
        pin_lock_seconds=int(config.get("STUDENT_PIN_LOCK_SECONDS", 900)),
    )
    _validate_media_gateway_config(
        app_env=app_env,
        enabled=bool(config.get("MEDIA_GATEWAY_ENABLED", False)),
        api_base_url=str(config.get("MEDIA_GATEWAY_API_BASE_URL") or ""),
        public_base_url=str(config.get("MEDIA_GATEWAY_PUBLIC_BASE_URL") or ""),
        signaling_public_base_url=str(
            config.get("CAMERA_SIGNALING_PUBLIC_BASE_URL") or ""
        ),
        timeout_seconds=float(config.get("MEDIA_GATEWAY_TIMEOUT_SECONDS", 5)),
        version=str(
            config.get("MEDIA_GATEWAY_VERSION") or MEDIA_GATEWAY_REQUIRED_VERSION
        ),
    )
    _validate_onvif_bootstrap_credentials(
        app_env=app_env,
        dev_adapters_enabled=bool(config.get("DEV_ADAPTERS_ENABLED")),
        enabled=bool(config.get("ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED")),
        username=str(config.get("ONVIF_BOOTSTRAP_USERNAME") or ""),
        password=str(config.get("ONVIF_BOOTSTRAP_PASSWORD") or ""),
    )
    database_url = str(config.get("DATABASE_URL", ""))
    if app_env in {"staging", "production"} and not database_url:
        raise ConfigError("APP_DATABASE_URL is required in staging/production.")
    if _database_dialect(database_url) != "mysql":
        raise ConfigError("Only MySQL databases are supported.")
    if app_env == "production":
        if config.get("DEV_ADAPTERS_ENABLED"):
            raise ConfigError("APP_ENABLE_DEV_ADAPTERS must be false in production.")
        if str(config.get("SMS_PROVIDER", "")).lower() == "development":
            raise ConfigError("APP_SMS_PROVIDER=development is not allowed in production.")
        if str(config.get("CAMERA_RUNTIME_PROVIDER", config.get("CAMERA_RUNTIME_ADAPTER", ""))).lower() in {
            "ai_camera_test",
            "mock",
        }:
            raise ConfigError("CAMERA_RUNTIME_PROVIDER cannot use development adapters in production.")
        if not str(config.get("INTERNAL_API_TOKEN", "")).strip():
            raise ConfigError("INTERNAL_API_TOKEN is required in production.")
        origins = config.get("CORS_ORIGINS") or []
        if not origins or "*" in origins:
            raise ConfigError("APP_CORS_ORIGINS must be explicit in production.")


def _validate_learning_curriculum_preparation_config(
    *,
    runner_enabled: object,
    content_generation_enabled: object,
    grade_allowlist: object,
    max_provider_subcalls_per_tick: object,
    max_inflight_per_build: object,
    canary_enabled: object,
    canary_auto_expand: object,
    reconciliation_enabled: object,
) -> None:
    if type(runner_enabled) is not bool or type(content_generation_enabled) is not bool:
        raise ConfigError(
            "Learning curriculum preparation enable flags must be booleans."
        )
    if (type(grade_allowlist) is not list or not grade_allowlist
        or any(type(grade) is not str or grade not in {f"primary_{n}" for n in range(1, 7)} for grade in grade_allowlist)
        or len(set(grade_allowlist)) != len(grade_allowlist)):
        raise ConfigError(
            "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST must contain unique registered primary grades."
        )
    if type(max_provider_subcalls_per_tick) is not int or max_provider_subcalls_per_tick != 1:
        raise ConfigError(
            "LEARNING_CURRICULUM_PREPARATION_MAX_PROVIDER_SUBCALLS_PER_TICK must be 1."
        )
    if type(max_inflight_per_build) is not int or max_inflight_per_build != 1:
        raise ConfigError(
            "LEARNING_CURRICULUM_PREPARATION_MAX_INFLIGHT_PER_BUILD must be 1."
        )
    if canary_enabled is not True or type(canary_auto_expand) is not bool:
        raise ConfigError(
            "Learning curriculum preparation canary must remain enabled and auto expansion must be an explicit boolean."
        )
    if reconciliation_enabled is not False:
        raise ConfigError(
            "LEARNING_CURRICULUM_PREPARATION_RECONCILIATION_ENABLED must remain disabled."
        )


def _validate_formal_production_gate_config(
    *,
    audio_validation_enabled: object,
    auto_publication_enabled: object,
) -> None:
    if (
        type(audio_validation_enabled) is not bool
        or type(auto_publication_enabled) is not bool
    ):
        raise ConfigError("formal production enable flags must be booleans.")


def _validate_learning_media_config(
    *,
    app_env: str,
    worker_enabled: bool,
    interval_seconds: int,
    provider: str,
    macos_say_timeout_seconds: float,
    base_url: str,
    backend: str,
    model: str,
    timeout_seconds: float,
    storage_root: str,
) -> None:
    provider_id = str(provider or "").strip().lower()
    if provider_id not in {"voxcpm2", "macos-say"}:
        raise ConfigError(
            "LEARNING_TTS_PROVIDER must be voxcpm2 or macos-say."
        )
    if provider_id == "macos-say":
        if str(app_env).strip().lower() != "development":
            raise ConfigError(
                "LEARNING_TTS_PROVIDER=macos-say is allowed only in development."
            )
        if platform.system() != "Darwin":
            raise ConfigError(
                "LEARNING_TTS_PROVIDER=macos-say requires macOS."
            )
    if macos_say_timeout_seconds < 1 or macos_say_timeout_seconds > 120:
        raise ConfigError(
            "LEARNING_MACOS_SAY_TIMEOUT_SECONDS must be between 1 and 120."
        )
    if interval_seconds < 5:
        raise ConfigError(
            "LEARNING_MEDIA_WORKER_INTERVAL_SECONDS must be at least 5."
        )
    if str(backend).strip().lower() not in {"vllm-omni", "python-api"}:
        raise ConfigError(
            "LEARNING_VOXCPM_BACKEND must be vllm-omni or python-api."
        )
    if not str(model).strip():
        raise ConfigError("LEARNING_VOXCPM_MODEL must not be empty.")
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ConfigError(
            "LEARNING_VOXCPM_TIMEOUT_SECONDS must be greater than 0 and at most 120."
        )
    if not str(storage_root).strip():
        raise ConfigError("LEARNING_MEDIA_STORAGE_ROOT must not be empty.")
    _validate_http_base_url(
        "LEARNING_VOXCPM_BASE_URL",
        str(base_url).strip(),
        required=worker_enabled and provider_id == "voxcpm2",
        allowed_schemes={"http", "https"},
    )


def _validate_formal_runtime_candidate_config(
    *,
    enabled: bool,
    classroom_runner_enabled: bool,
    runtime_enabled: bool,
    generation_enabled: bool,
    autorun_enabled: bool,
) -> None:
    if enabled and not (
        classroom_runner_enabled
        and runtime_enabled
        and generation_enabled
        and autorun_enabled
    ):
        raise ConfigError(
            "LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED requires "
            "LEARNING_CLASSROOM_GENERATION_ENABLED, "
            "OPENMAIC_FULL_RUNTIME_ENABLED, and "
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED, and "
            "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED."
        )


def _validate_openmaic_full_runtime_config(
    *,
    app_env: str,
    enabled: bool,
    generation_enabled: bool,
    generation_interval_seconds: int,
    internal_url: str,
    public_url: str,
    timeout_seconds: float,
    launch_ttl_seconds: int,
    session_ttl_seconds: int,
    autorun_enabled: bool = False,
) -> None:
    if generation_enabled and not enabled:
        raise ConfigError(
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED requires "
            "OPENMAIC_FULL_RUNTIME_ENABLED."
        )
    if autorun_enabled and not generation_enabled:
        raise ConfigError(
            "OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED requires "
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED."
        )
    if generation_interval_seconds < 5 or generation_interval_seconds > 3600:
        raise ConfigError(
            "OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS must be "
            "between 5 and 3600."
        )
    if timeout_seconds <= 0 or timeout_seconds > 300:
        raise ConfigError(
            "OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS must be greater than 0 "
            "and at most 300."
        )
    if not 30 <= launch_ttl_seconds <= 300:
        raise ConfigError(
            "OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS must be between 30 and 300."
        )
    if not 300 <= session_ttl_seconds <= 86400:
        raise ConfigError(
            "OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS must be between 300 "
            "and 86400."
        )
    _validate_http_base_url(
        "OPENMAIC_FULL_RUNTIME_INTERNAL_URL",
        str(internal_url).strip(),
        required=enabled,
        allowed_schemes={"http", "https"},
    )
    _validate_http_base_url(
        "OPENMAIC_FULL_RUNTIME_PUBLIC_URL",
        str(public_url).strip(),
        required=enabled,
        allowed_schemes={"http", "https"},
    )
    if enabled and app_env in {"staging", "production"}:
        parsed = urlparse(str(public_url).strip())
        if parsed.scheme != "https":
            raise ConfigError(
                "OPENMAIC_FULL_RUNTIME_PUBLIC_URL must use HTTPS in "
                "staging/production."
            )


def _validate_openmaic_conversation_probe_config(
    *, runtime_enabled: bool, enabled: bool, ttl_seconds: int
) -> None:
    if enabled and not runtime_enabled:
        raise ConfigError(
            "OPENMAIC_CONVERSATION_PROBE_ENABLED requires "
            "OPENMAIC_FULL_RUNTIME_ENABLED."
        )
    if not 30 <= ttl_seconds <= 300:
        raise ConfigError(
            "OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS must be between 30 and 300."
        )


def _validate_openmaic_deterministic_recovery_config(
    *,
    runtime_enabled: bool,
    probe_enabled: bool,
    generation_enabled: bool,
    autorun_enabled: bool,
    enabled: bool,
    redispatch_enabled: bool,
    internal_url: str,
    internal_token: str,
) -> None:
    if redispatch_enabled and not enabled:
        raise ConfigError(
            "OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED requires "
            "OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED."
        )
    if not enabled:
        return
    if not runtime_enabled or not probe_enabled:
        raise ConfigError(
            "OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED requires both "
            "OPENMAIC_FULL_RUNTIME_ENABLED and OPENMAIC_CONVERSATION_PROBE_ENABLED."
        )
    if generation_enabled or autorun_enabled:
        raise ConfigError(
            "OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED requires ordinary "
            "OpenMAIC generation and autorun to remain disabled."
        )
    parsed = urlparse(str(internal_url or "").strip())
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(
            "OPENMAIC deterministic recovery requires a credential-free loopback "
            "OPENMAIC_FULL_RUNTIME_INTERNAL_URL."
        )
    token = str(internal_token or "").strip()
    if len(token) < 32 or len(token) > 512 or any(char.isspace() for char in token):
        raise ConfigError(
            "OPENMAIC deterministic recovery requires a 32-512 character "
            "INTERNAL_API_TOKEN without whitespace."
        )


def _validate_openmaic_tts_credential_recovery_config(
    *,
    runtime_enabled: bool,
    probe_enabled: bool,
    deterministic_recovery_enabled: bool,
    redispatch_enabled: bool,
    generation_enabled: bool,
    autorun_enabled: bool,
    enabled: bool,
    internal_url: str,
    internal_token: str,
) -> None:
    if not enabled:
        return
    if not runtime_enabled or not probe_enabled:
        raise ConfigError(
            "OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED requires both "
            "OPENMAIC_FULL_RUNTIME_ENABLED and OPENMAIC_CONVERSATION_PROBE_ENABLED."
        )
    if not deterministic_recovery_enabled or redispatch_enabled:
        raise ConfigError(
            "OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED requires the parent "
            "deterministic recovery gate enabled and redispatch disabled."
        )
    if generation_enabled or autorun_enabled:
        raise ConfigError(
            "OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED requires ordinary "
            "OpenMAIC generation and autorun to remain disabled."
        )
    parsed = urlparse(str(internal_url or "").strip())
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(
            "OPENMAIC TTS credential recovery requires a credential-free "
            "loopback OPENMAIC_FULL_RUNTIME_INTERNAL_URL."
        )
    token = str(internal_token or "").strip()
    if (
        len(token) < 32
        or len(token) > 512
        or any(char.isspace() for char in token)
    ):
        raise ConfigError(
            "OPENMAIC TTS credential recovery requires a 32-512 character "
            "INTERNAL_API_TOKEN without whitespace."
        )


def _validate_openmaic_formal_citation_recovery_config(
    *,
    runtime_enabled: bool,
    generation_enabled: bool,
    enabled: bool,
    source_job_id: str,
    internal_url: str,
    internal_token: str,
) -> None:
    if not enabled:
        return
    if not runtime_enabled or not generation_enabled:
        raise ConfigError(
            "OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED requires both "
            "OPENMAIC_FULL_RUNTIME_ENABLED and "
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED."
        )
    job_id = str(source_job_id or "").strip()
    if (
        not job_id
        or len(job_id) > 128
        or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
            for char in job_id
        )
    ):
        raise ConfigError(
            "OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID must be one "
            "exact safe OpenMAIC job id."
        )
    parsed = urlparse(str(internal_url or "").strip())
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ConfigError(
            "OpenMAIC formal citation recovery requires a credential-free "
            "loopback OPENMAIC_FULL_RUNTIME_INTERNAL_URL."
        )
    token = str(internal_token or "").strip()
    if (
        len(token) < 32
        or len(token) > 512
        or any(char.isspace() for char in token)
    ):
        raise ConfigError(
            "OpenMAIC formal citation recovery requires a 32-512 character "
            "INTERNAL_API_TOKEN without whitespace."
        )


def _validate_media_gateway_config(
    *,
    app_env: str,
    enabled: bool,
    api_base_url: str,
    public_base_url: str,
    signaling_public_base_url: str,
    timeout_seconds: float,
    version: str,
) -> None:
    if timeout_seconds <= 0:
        raise ConfigError("APP_MEDIA_GATEWAY_TIMEOUT_SECONDS must be greater than zero.")
    if version != MEDIA_GATEWAY_REQUIRED_VERSION:
        raise ConfigError(
            "APP_MEDIA_GATEWAY_VERSION must be "
            f"{MEDIA_GATEWAY_REQUIRED_VERSION}."
        )
    if enabled and not api_base_url:
        raise ConfigError(
            "APP_MEDIA_GATEWAY_API_BASE_URL is required when the media gateway is enabled."
        )

    _validate_http_base_url(
        "APP_MEDIA_GATEWAY_API_BASE_URL",
        api_base_url,
        required=enabled,
        allowed_schemes={"http", "https"},
    )
    _validate_http_base_url(
        "APP_MEDIA_GATEWAY_PUBLIC_BASE_URL",
        public_base_url,
        required=False,
        allowed_schemes={"http", "https"},
    )
    _validate_http_base_url(
        "CAMERA_SIGNALING_PUBLIC_BASE_URL",
        signaling_public_base_url,
        required=False,
        allowed_schemes={"http", "https", "ws", "wss"},
    )

    if app_env == "production":
        for key, value in (
            ("APP_MEDIA_GATEWAY_PUBLIC_BASE_URL", public_base_url),
            ("CAMERA_SIGNALING_PUBLIC_BASE_URL", signaling_public_base_url),
        ):
            if value and _is_loopback_url(value):
                raise ConfigError(f"{key} cannot use a loopback host in production.")


def _validate_student_auth_config(
    *,
    app_env: str,
    pepper: str,
    access_token_seconds: int,
    refresh_token_seconds: int,
    device_token_seconds: int,
    pairing_code_ttl_seconds: int,
    qr_challenge_ttl_seconds: int,
    qr_approval_exchange_seconds: int,
    qr_polling_interval_ms: int,
    qr_active_challenge_limit: int,
    qr_ip_active_challenge_limit: int,
    qr_rate_limit_window_seconds: int,
    qr_rate_limit_max: int,
    qr_ip_rate_limit_max: int,
    qr_retention_seconds: int,
    pin_pbkdf2_iterations: int,
    pin_max_attempts: int,
    pin_lock_seconds: int,
) -> None:
    positive_values = {
        "APP_STUDENT_ACCESS_SECONDS": access_token_seconds,
        "APP_STUDENT_REFRESH_SECONDS": refresh_token_seconds,
        "APP_STUDENT_DEVICE_SECONDS": device_token_seconds,
        "APP_STUDENT_PAIRING_CODE_TTL_SECONDS": pairing_code_ttl_seconds,
        "APP_STUDENT_QR_CHALLENGE_TTL_SECONDS": qr_challenge_ttl_seconds,
        "APP_STUDENT_QR_APPROVAL_EXCHANGE_SECONDS": qr_approval_exchange_seconds,
        "APP_STUDENT_QR_POLLING_INTERVAL_MS": qr_polling_interval_ms,
        "APP_STUDENT_QR_ACTIVE_CHALLENGE_LIMIT": qr_active_challenge_limit,
        "APP_STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT": qr_ip_active_challenge_limit,
        "APP_STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS": qr_rate_limit_window_seconds,
        "APP_STUDENT_QR_RATE_LIMIT_MAX": qr_rate_limit_max,
        "APP_STUDENT_QR_IP_RATE_LIMIT_MAX": qr_ip_rate_limit_max,
        "APP_STUDENT_QR_RETENTION_SECONDS": qr_retention_seconds,
        "APP_STUDENT_PIN_MAX_ATTEMPTS": pin_max_attempts,
        "APP_STUDENT_PIN_LOCK_SECONDS": pin_lock_seconds,
    }
    for key, value in positive_values.items():
        if value <= 0:
            raise ConfigError(f"{key} must be greater than zero.")
    if qr_polling_interval_ms < 250:
        raise ConfigError("APP_STUDENT_QR_POLLING_INTERVAL_MS must be at least 250.")
    if qr_retention_seconds < qr_challenge_ttl_seconds:
        raise ConfigError(
            "APP_STUDENT_QR_RETENTION_SECONDS must not be shorter than the challenge TTL."
        )
    if pin_pbkdf2_iterations < 1000:
        raise ConfigError("APP_STUDENT_PIN_PBKDF2_ITERATIONS must be at least 1000.")
    if app_env == "production" and (
        not pepper.strip() or pepper == DEVELOPMENT_STUDENT_AUTH_PEPPER
    ):
        raise ConfigError(
            "APP_STUDENT_AUTH_PEPPER must be set to a private production secret."
        )


def _validate_http_base_url(
    key: str,
    value: str,
    *,
    required: bool,
    allowed_schemes: set[str],
) -> None:
    if not value:
        if required:
            raise ConfigError(f"{key} is required.")
        return
    parsed = urlparse(value)
    try:
        parsed_port = parsed.port
    except ValueError as exc:
        raise ConfigError(f"{key} has an invalid port.") from exc
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed_port == 0
    ):
        schemes = "/".join(sorted(allowed_schemes))
        raise ConfigError(
            f"{key} must be a {schemes} base URL without credentials, query, or fragment."
        )


def _is_loopback_url(value: str) -> bool:
    hostname = (urlparse(value).hostname or "").strip().lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _validate_onvif_bootstrap_credentials(
    *,
    app_env: str,
    dev_adapters_enabled: bool,
    enabled: bool,
    username: str,
    password: str,
) -> None:
    has_username = bool(username.strip())
    has_password = bool(password)
    if has_username != has_password:
        raise ConfigError(
            "ONVIF_BOOTSTRAP_USERNAME and ONVIF_BOOTSTRAP_PASSWORD must be set together."
        )
    if enabled and not has_username:
        raise ConfigError(
            "ONVIF bootstrap credentials must be set when the engineering fallback is enabled."
        )
    if has_username and not enabled:
        raise ConfigError(
            "ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED must be true when fixed credentials are configured."
        )
    if enabled and (
        app_env not in {"development", "test"} or not dev_adapters_enabled
    ):
        raise ConfigError(
            "Fixed ONVIF bootstrap credentials are development/test only."
        )


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_dialect(database_url: str) -> str:
    parsed = urlparse(database_url)
    return parsed.scheme.split("+", 1)[0] if parsed.scheme else ""


def _database_url_for_env(app_env: str) -> str:
    if app_env == "test":
        return os.getenv(
            "APP_TEST_DATABASE_URL",
            "mysql+pymysql://ai_camera_app:ai_camera_app_dev@127.0.0.1:3306/"
            "ai_camera_app_test?charset=utf8mb4",
        )
    if app_env in {"staging", "production"}:
        return os.getenv("APP_DATABASE_URL", "")
    return os.getenv(
        "APP_DATABASE_URL",
        "mysql+pymysql://ai_camera_app:ai_camera_app_dev@127.0.0.1:3306/"
        "ai_camera_app_dev?charset=utf8mb4",
    )


def _default_ai_provider() -> str:
    if _env("KIMI_API_KEY", "") or _env("MOONSHOT_API_KEY", ""):
        return "moonshot"
    if _env("OPENAI_API_KEY", ""):
        return "openai"
    return ""


def _default_ai_model(provider: str) -> str:
    if provider in {"moonshot", "kimi"}:
        return _env("KIMI_CHAT_MODEL", _env("MOONSHOT_CHAT_MODEL", "kimi-k2.6"))
    if provider == "openai":
        return _env("OPENAI_CHAT_MODEL", "gpt-4.1-mini")
    return ""


def _default_ai_api_key(provider: str) -> str:
    if provider in {"moonshot", "kimi"}:
        return _env("KIMI_API_KEY", _env("MOONSHOT_API_KEY", ""))
    if provider == "openai":
        return _env("OPENAI_API_KEY", "")
    return ""


def _default_ai_base_url(provider: str) -> str:
    if provider in {"moonshot", "kimi"}:
        return _env("KIMI_BASE_URL", _env("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"))
    if provider == "openai":
        return _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    return ""
