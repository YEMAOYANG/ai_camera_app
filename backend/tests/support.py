from __future__ import annotations

import os
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch
from urllib.parse import unquote, urlparse

from core.database import DEFAULT_SCHEMA, Database
from scripts.migrate import run_migrations

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT_ROOT = str(BACKEND_ROOT / "prompts")


TEST_DATABASE_URL = os.getenv(
    "APP_TEST_DATABASE_URL",
    "postgresql://mira@127.0.0.1:5433/mira_test",
)


def validated_test_database_url(database_url: str | None = None) -> str:
    resolved = str(
        database_url
        or os.getenv("APP_TEST_DATABASE_URL")
        or TEST_DATABASE_URL
    ).strip()
    parsed = urlparse(resolved)
    database_name = unquote(parsed.path.lstrip("/")).split("/", 1)[0]
    # mira_test, or mira_test_<suffix> for a parallel run; never the daily `mira`.
    if re.fullmatch(r"mira_test(_[a-z0-9]+)?", database_name) is None:
        raise RuntimeError(
            "APP_TEST_DATABASE_URL must name the mira_test database"
        )
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("APP_TEST_DATABASE_URL must be a postgresql:// URL")
    if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("APP_TEST_DATABASE_URL must use a safe local test boundary")
    return resolved


@contextmanager
def migration_fixture_through(version: str):
    """Run real migrations at one historical boundary, without editing their SQL."""
    migration = BACKEND_ROOT / "migrations" / version
    if Path(version).name != version or not migration.is_file():
        raise ValueError("historical migration fixture version must exist")
    with TemporaryDirectory(
        prefix="mira-migration-fixture-",
        dir=os.getenv("MIRA_TASK_TMPDIR") or os.getenv("TMPDIR"),
    ) as temporary:
        fixture_root = Path(temporary)
        fixture_migrations = fixture_root / "migrations"
        fixture_migrations.mkdir()
        for source in sorted((BACKEND_ROOT / "migrations").glob("*.sql")):
            if source.name <= version:
                shutil.copyfile(source, fixture_migrations / source.name)
        with patch("scripts.migrate.ROOT", fixture_root):
            yield


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
    reset_test_database(database_url)
    return config


def reset_test_database(database_url: str | None = None) -> None:
    safe_database_url = validated_test_database_url(database_url)
    database = Database(safe_database_url)
    with database.transaction() as conn:
        conn.executescript(f"DROP SCHEMA IF EXISTS {DEFAULT_SCHEMA} CASCADE; CREATE SCHEMA {DEFAULT_SCHEMA}")
    run_migrations(safe_database_url, verbose=False)


def request_debug_code(client, phone: str) -> str:
    response = client.post("/api/auth/sms/request", json={"phone": phone})
    if response.status_code != 200:
        raise AssertionError(response.json)
    code = response.json.get("debugCode")
    if not code:
        raise AssertionError("development SMS provider did not return debugCode")
    return code
