from __future__ import annotations

from pathlib import Path
from typing import Mapping


def vision_worker_config(environ: Mapping[str, str]) -> dict:
    backend_root = Path(__file__).resolve().parents[1]
    return {
        "PROMPT_ROOT": environ.get("APP_PROMPT_ROOT", str(backend_root / "prompts")),
        "AI_PROVIDER": environ.get("APP_AI_PROVIDER", environ.get("AI_PROVIDER", "")),
        "AI_MODEL": environ.get("APP_AI_MODEL", environ.get("AI_MODEL", "")),
        "AI_API_KEY": environ.get(
            "APP_AI_API_KEY",
            environ.get("KIMI_API_KEY", environ.get("MOONSHOT_API_KEY", "")),
        ),
        "AI_BASE_URL": environ.get("APP_AI_BASE_URL", environ.get("KIMI_BASE_URL", "")),
        "AI_VISION_ENABLED": environ.get("APP_AI_VISION_ENABLED", "1"),
        "AI_VISION_MODEL": environ.get("APP_AI_VISION_MODEL", environ.get("KIMI_VISION_MODEL", "")),
        "AI_VISION_TIMEOUT_SECONDS": environ.get("APP_AI_VISION_TIMEOUT_SECONDS", "20"),
        "AI_VISION_MAX_BYTES": environ.get("APP_AI_VISION_MAX_BYTES", "524288"),
        "AI_VISION_MIN_INTERVAL_SECONDS": environ.get("APP_AI_VISION_MIN_INTERVAL_SECONDS", "60"),
        "AI_VISION_MAX_CALLS_PER_HOUR": environ.get("APP_AI_VISION_MAX_CALLS_PER_HOUR", "20"),
        "AI_VISION_BACKOFF_SECONDS": environ.get("APP_AI_VISION_BACKOFF_SECONDS", "300"),
    }
