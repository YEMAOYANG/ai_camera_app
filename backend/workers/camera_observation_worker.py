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
from services.camera_observe_service import build_observe_service_from_env
from services.vision_prefilter_service import validate_prefilter_runtime
from services.vision_worker_config import vision_worker_config


log = logging.getLogger("camera_observation_worker")
RUNNING = True


class ObservationAdapter(Protocol):
    config: AiCameraTestObservationConfig

    def run_observe_tick(self, *, window_start_ms: int, window_end_ms: int) -> dict:
        ...


@dataclass(frozen=True)
class CameraObservationWorkerResult:
    observation_count: int
    posted_count: int
    responses: list[dict]
    skipped: bool = False
    skip_reason: str = ""


class CameraObservationWorker:
    def __init__(self, adapter: ObservationAdapter):
        self.adapter = adapter

    def run_once(self, *, window_start_ms: int | None = None, window_end_ms: int | None = None) -> CameraObservationWorkerResult:
        start = window_start_ms if window_start_ms is not None else now_ms()
        end = window_end_ms if window_end_ms is not None else now_ms()
        if end <= start:
            end = start + int(max(1.0, self.adapter.config.interval_seconds) * 1000)
        result = self.adapter.run_observe_tick(window_start_ms=start, window_end_ms=end)
        posted = bool(result.get("posted"))
        return CameraObservationWorkerResult(
            observation_count=int(result.get("observation_count") or 0),
            posted_count=1 if posted else 0,
            responses=[result.get("response")] if result.get("response") else [],
            skipped=bool(result.get("skipped")),
            skip_reason=str(result.get("skip_reason") or ""),
        )

    def run_forever(self) -> None:
        while RUNNING:
            tick_start = now_ms()
            try:
                result = self.run_once(window_start_ms=tick_start)
                if result.skipped:
                    if result.skip_reason == "snapshot_unavailable":
                        log.warning("camera observation tick skipped: snapshot unavailable")
                    else:
                        log.info(
                            "camera observation tick skipped: %s",
                            result.skip_reason or "unknown",
                        )
                else:
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
    validate_prefilter_runtime()
    observe_service = build_observe_service_from_env(env)
    return CameraObservationWorker(
        AiCameraTestObservationAdapter(
            config,
            vision_service=observe_service.vision_service,
            observe_service=observe_service,
        ),
    )


def _worker_config(environ: Mapping[str, str]) -> dict:
    return vision_worker_config(environ)


def _load_worker_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


def _shutdown(_signum=None, _frame=None):
    global RUNNING
    RUNNING = False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_worker_env()
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    worker = build_worker_from_env()
    if str(os.getenv("CAMERA_OBSERVATION_RUN_ONCE") or "").strip().lower() in {"1", "true", "yes", "on"}:
        result = worker.run_once()
        if result.skipped:
            log.warning(
                "camera observation run-once skipped: %s",
                result.skip_reason or "unknown",
            )
        else:
            log.info("camera observation run-once posted=%s", result.posted_count)
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
