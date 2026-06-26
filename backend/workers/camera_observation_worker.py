from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from core.security import now_ms
from integrations.camera_runtime.ai_camera_test_observation_adapter import (
    AiCameraTestObservationAdapter,
    AiCameraTestObservationConfig,
)
from services.service_factory import build_vision_observation_service_from_config


log = logging.getLogger("camera_observation_worker")
RUNNING = True


class ObservationAdapter(Protocol):
    config: AiCameraTestObservationConfig

    def fetch_analysis(self) -> dict:
        ...

    def payloads_from_analysis(
        self,
        analysis: dict,
        *,
        window_start_ms: int,
        window_end_ms: int,
        observed_at: int | None = None,
    ) -> list[dict]:
        ...

    def post_observation(self, payload: dict) -> dict:
        ...


@dataclass(frozen=True)
class CameraObservationWorkerResult:
    observation_count: int
    posted_count: int
    responses: list[dict]


class CameraObservationWorker:
    def __init__(self, adapter: ObservationAdapter):
        self.adapter = adapter

    def run_once(self, *, window_start_ms: int | None = None, window_end_ms: int | None = None) -> CameraObservationWorkerResult:
        start = window_start_ms if window_start_ms is not None else now_ms()
        analysis = self.adapter.fetch_analysis()
        end = window_end_ms if window_end_ms is not None else now_ms()
        if end <= start:
            end = start + int(max(1.0, self.adapter.config.interval_seconds) * 1000)
        payloads = self.adapter.payloads_from_analysis(
            analysis,
            window_start_ms=start,
            window_end_ms=end,
            observed_at=end,
        )
        responses = [self.adapter.post_observation(payload) for payload in payloads]
        return CameraObservationWorkerResult(
            observation_count=len(payloads),
            posted_count=len(responses),
            responses=responses,
        )

    def run_forever(self) -> None:
        while RUNNING:
            tick_start = now_ms()
            try:
                result = self.run_once(window_start_ms=tick_start)
                log.info(
                    "camera observation tick posted=%s observations=%s",
                    result.posted_count,
                    result.observation_count,
                )
            except Exception as exc:  # pragma: no cover - exercised by runtime.
                log.exception("camera observation tick failed: %s", exc)
            deadline = time.monotonic() + self.adapter.config.interval_seconds
            while RUNNING and time.monotonic() < deadline:
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


def build_worker_from_env(environ: dict[str, str] | None = None) -> CameraObservationWorker:
    env = environ or os.environ
    config = AiCameraTestObservationConfig.from_env(env)
    config.validate()
    vision_service = build_vision_observation_service_from_config(_worker_config(env))
    return CameraObservationWorker(
        AiCameraTestObservationAdapter(config, vision_service=vision_service),
    )


def _worker_config(environ: Mapping[str, str]) -> dict:
    return {
        "PROMPT_ROOT": environ.get("APP_PROMPT_ROOT", str(Path(__file__).resolve().parents[1] / "prompts")),
        "AI_PROVIDER": environ.get("APP_AI_PROVIDER", environ.get("AI_PROVIDER", "")),
        "AI_MODEL": environ.get("APP_AI_MODEL", environ.get("AI_MODEL", "")),
        "AI_API_KEY": environ.get("APP_AI_API_KEY", environ.get("KIMI_API_KEY", environ.get("MOONSHOT_API_KEY", ""))),
        "AI_BASE_URL": environ.get("APP_AI_BASE_URL", environ.get("KIMI_BASE_URL", "")),
        "AI_VISION_ENABLED": environ.get("APP_AI_VISION_ENABLED", "1"),
        "AI_VISION_MODEL": environ.get("APP_AI_VISION_MODEL", environ.get("KIMI_VISION_MODEL", "")),
        "AI_VISION_TIMEOUT_SECONDS": environ.get("APP_AI_VISION_TIMEOUT_SECONDS", "20"),
        "AI_VISION_MAX_BYTES": environ.get("APP_AI_VISION_MAX_BYTES", "524288"),
        "AI_VISION_MIN_INTERVAL_SECONDS": environ.get("APP_AI_VISION_MIN_INTERVAL_SECONDS", "60"),
        "AI_VISION_MAX_CALLS_PER_HOUR": environ.get("APP_AI_VISION_MAX_CALLS_PER_HOUR", "20"),
        "AI_VISION_BACKOFF_SECONDS": environ.get("APP_AI_VISION_BACKOFF_SECONDS", "300"),
    }


def _shutdown(_signum=None, _frame=None):
    global RUNNING
    RUNNING = False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    worker = build_worker_from_env()
    if str(os.getenv("CAMERA_OBSERVATION_RUN_ONCE") or "").strip().lower() in {"1", "true", "yes", "on"}:
        result = worker.run_once()
        log.info("camera observation run-once posted=%s", result.posted_count)
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
