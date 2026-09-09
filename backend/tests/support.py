from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from core.database import Database
from scripts.migrate import run_migrations

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_ROOT = str(BACKEND_ROOT / "prompts")


TEST_DATABASE_URL = os.getenv(
    "APP_TEST_DATABASE_URL",
    "mysql+pymysql://ai_camera_app:ai_camera_app_dev@127.0.0.1:3306/"
    "ai_camera_app_test?charset=utf8mb4",
)


def validated_test_database_url(database_url: str | None = None) -> str:
    resolved = str(
        database_url
        or os.getenv("APP_TEST_DATABASE_URL")
        or TEST_DATABASE_URL
    ).strip()
    parsed = urlparse(resolved)
    database_name = unquote(parsed.path.lstrip("/")).split("/", 1)[0]
    if database_name != "ai_camera_app_test":
        raise RuntimeError(
            "APP_TEST_DATABASE_URL must name the exact ai_camera_app_test database"
        )
    if parsed.scheme != "mysql+pymysql":
        raise RuntimeError("APP_TEST_DATABASE_URL must use mysql+pymysql")
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("APP_TEST_DATABASE_URL must use a safe local test boundary")
    return resolved


def fresh_test_config(**overrides: Any) -> dict:
    config = {
        "TESTING": True,
        "APP_ENV": "test",
        "DATABASE_URL": os.getenv("APP_TEST_DATABASE_URL") or TEST_DATABASE_URL,
        "AUTH_ACCESS_TOKEN_SECONDS": 900,
        "AUTH_REFRESH_TOKEN_SECONDS": 3600,
        "SMS_PROVIDER": "development",
        "DEV_ADAPTERS_ENABLED": True,
        "CAMERA_RUNTIME_PROVIDER": "disabled",
        "CAMERA_RUNTIME_ADAPTER": "disabled",
        "AI_CAMERA_TEST_BASE_URL": "",
        "CAMERA_BACKEND_URL": "",
        "AI_PROVIDER": "",
        "AI_MODEL": "",
        "AI_API_KEY": "",
        "AI_BASE_URL": "",
        "TASK_WEBSOCKET_ENABLED": False,
        "PROMPT_ROOT": DEFAULT_PROMPT_ROOT,
    }
    config.update(overrides)
    database_url = validated_test_database_url(config["DATABASE_URL"])
    config["DATABASE_URL"] = database_url
    reset_mysql_test_database(database_url)
    return config


def reset_mysql_test_database(database_url: str | None = None) -> None:
    safe_database_url = validated_test_database_url(database_url)
    database = Database(safe_database_url)
    with database.transaction() as conn:
        conn.execute("SET FOREIGN_KEY_CHECKS = 0")
        rows = conn.execute("SHOW TABLES").fetchall()
        for row in rows:
            table_name = next(iter(row.values()))
            conn.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        conn.execute("SET FOREIGN_KEY_CHECKS = 1")
    run_migrations(safe_database_url, verbose=False)


def request_debug_code(client, phone: str) -> str:
    response = client.post("/api/auth/sms/request", json={"phone": phone})
    if response.status_code != 200:
        raise AssertionError(response.json)
    code = response.json.get("debugCode")
    if not code:
        raise AssertionError("development SMS provider did not return debugCode")
    return code
