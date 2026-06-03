from __future__ import annotations

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
    CAMERA_RUNTIME_ADAPTER: str
    CAMERA_BACKEND_URL: str
    HARDWARE_ADAPTER: str
    PROMPT_ROOT: str
    AI_PROVIDER: str
    AI_MODEL: str
    AI_EVAL_ENABLED: bool
    HOST: str
    PORT: int
    DEBUG: bool

    @classmethod
    def from_env(cls) -> "AppConfig":
        app_env = _env("APP_ENV", "development").strip().lower()
        dev_adapters_enabled_default = "1" if app_env in {"development", "test"} else "0"
        database_url = _database_url_for_env(app_env)
        return cls(
            APP_ENV=app_env,
            SERVICE_NAME=_env("APP_SERVICE_NAME", "ai-camera-app-backend"),
            DATABASE_URL=database_url,
            CORS_ORIGINS=_csv(_env("APP_CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000")),
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
            CAMERA_RUNTIME_ADAPTER=_env("APP_CAMERA_RUNTIME_ADAPTER", "disabled").strip(),
            CAMERA_BACKEND_URL=_env("APP_CAMERA_BACKEND_URL", ""),
            HARDWARE_ADAPTER=_env("APP_HARDWARE_ADAPTER", "disabled").strip(),
            PROMPT_ROOT=_env("APP_PROMPT_ROOT", str(BACKEND_ROOT / "prompts")),
            AI_PROVIDER=_env("APP_AI_PROVIDER", "").strip(),
            AI_MODEL=_env("APP_AI_MODEL", "").strip(),
            AI_EVAL_ENABLED=_bool(_env("APP_AI_EVAL_ENABLED", "0")),
            HOST=_env("APP_HOST", "127.0.0.1"),
            PORT=int(_env("APP_PORT", _env("PORT", "8000"))),
            DEBUG=_bool(_env("APP_DEBUG", _env("FLASK_DEBUG", "0"))),
        )

    def to_flask_config(self) -> dict:
        return asdict(self)

    def validate(self) -> None:
        if self.APP_ENV not in VALID_APP_ENVS:
            raise ConfigError(f"Unsupported APP_ENV: {self.APP_ENV}")

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


def apply_test_defaults(config: dict) -> dict:
    next_config = dict(config)
    next_config.setdefault("APP_ENV", "test")
    next_config.setdefault("DEV_ADAPTERS_ENABLED", True)
    next_config.setdefault("SMS_PROVIDER", "development")
    return next_config


def validate_flask_config(config: dict) -> None:
    app_env = str(config.get("APP_ENV", "development")).strip().lower()
    if app_env not in VALID_APP_ENVS:
        raise ConfigError(f"Unsupported APP_ENV: {app_env}")
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
        origins = config.get("CORS_ORIGINS") or []
        if not origins or "*" in origins:
            raise ConfigError("APP_CORS_ORIGINS must be explicit in production.")


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
