from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppConfig:
    AUTH_DB_PATH: str
    AUTH_ACCESS_TOKEN_SECONDS: int
    AUTH_REFRESH_TOKEN_SECONDS: int
    AUTH_DEV_SMS_CODE: str
    CAMERA_BACKEND_URL: str
    PROMPT_ROOT: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            AUTH_DB_PATH=str(BACKEND_ROOT / "data" / "mira_guardian.db"),
            AUTH_ACCESS_TOKEN_SECONDS=int(os.getenv("MIRA_AUTH_ACCESS_SECONDS", "900")),
            AUTH_REFRESH_TOKEN_SECONDS=int(
                os.getenv("MIRA_AUTH_REFRESH_SECONDS", str(60 * 60 * 24 * 30))
            ),
            AUTH_DEV_SMS_CODE=os.getenv("MIRA_AUTH_DEV_SMS_CODE", "0426"),
            CAMERA_BACKEND_URL=os.getenv("MIRA_CAMERA_BACKEND_URL", "http://127.0.0.1:8767"),
            PROMPT_ROOT=os.getenv("MIRA_PROMPT_ROOT", str(BACKEND_ROOT / "prompts")),
        )

    def to_flask_config(self) -> dict:
        return asdict(self)
