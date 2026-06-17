from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from typing import Protocol

from core.security import now_ms
from integrations.camera_runtime.ai_camera_test_observation_adapter import (
    AiCameraTestObservationAdapter,
    AiCameraTestObservationConfig,
)


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
    config = AiCameraTestObservationConfig.from_env(environ or os.environ)
    config.validate()
    return CameraObservationWorker(AiCameraTestObservationAdapter(config))


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
