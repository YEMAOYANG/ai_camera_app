from __future__ import annotations

import ipaddress
import os
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
        return cls(
            APP_ENV=app_env,
            SERVICE_NAME=_env("APP_SERVICE_NAME", "ai-camera-app-backend"),
            DATABASE_URL=database_url,
            CORS_ORIGINS=_csv(_env("APP_CORS_ORIGINS", "*" if app_env == "development" else "http://127.0.0.1:8000,http://localhost:8000")),
            AUTH_ACCESS_TOKEN_SECONDS=int(_env("APP_AUTH_ACCESS_SECONDS", "900")),
            AUTH_REFRESH_TOKEN_SECONDS=int(
                _env("APP_AUTH_REFRESH_SECONDS", str(60 * 60 * 24 * 30))
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
    next_config.setdefault("TASK_WEBSOCKET_ENABLED", False)
    return next_config


def validate_flask_config(config: dict) -> None:
    app_env = str(config.get("APP_ENV", "development")).strip().lower()
    if app_env not in VALID_APP_ENVS:
        raise ConfigError(f"Unsupported APP_ENV: {app_env}")
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
