from __future__ import annotations

import os
from typing import Any

from core.database import Database
from scripts.migrate import run_migrations


TEST_DATABASE_URL = os.getenv(
    "APP_TEST_DATABASE_URL",
    "mysql+pymysql://ai_camera_app:ai_camera_app_dev@127.0.0.1:3306/"
    "ai_camera_app_test?charset=utf8mb4",
)


def fresh_test_config(**overrides: Any) -> dict:
    reset_mysql_test_database()
    config = {
        "TESTING": True,
        "APP_ENV": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "AUTH_ACCESS_TOKEN_SECONDS": 900,
        "AUTH_REFRESH_TOKEN_SECONDS": 3600,
        "SMS_PROVIDER": "development",
        "DEV_ADAPTERS_ENABLED": True,
        "CAMERA_RUNTIME_PROVIDER": "disabled",
        "CAMERA_RUNTIME_ADAPTER": "disabled",
        "AI_CAMERA_TEST_BASE_URL": "",
        "CAMERA_BACKEND_URL": "",
        "TASK_WEBSOCKET_ENABLED": False,
    }
    config.update(overrides)
    return config


def reset_mysql_test_database() -> None:
    database = Database(TEST_DATABASE_URL)
    with database.transaction() as conn:
        conn.execute("SET FOREIGN_KEY_CHECKS = 0")
        rows = conn.execute("SHOW TABLES").fetchall()
        for row in rows:
            table_name = next(iter(row.values()))
            conn.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        conn.execute("SET FOREIGN_KEY_CHECKS = 1")
    run_migrations(TEST_DATABASE_URL, verbose=False)


def request_debug_code(client, phone: str) -> str:
    response = client.post("/api/auth/sms/request", json={"phone": phone})
    if response.status_code != 200:
        raise AssertionError(response.json)
    code = response.json.get("debugCode")
    if not code:
        raise AssertionError("development SMS provider did not return debugCode")
    return code
