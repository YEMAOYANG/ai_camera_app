from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class OpenMaicRuntimeGenerationState:
    running: bool = False
    last_checked_at: int | None = None
    last_runtime_id: str | None = None
    last_result: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""


class OpenMaicRuntimeGenerationRunner:
    """Resume persisted sample/formal classrooms outside student requests."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state = OpenMaicRuntimeGenerationState()

    def start(self, app) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not app.config.get("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED"):
            return
        if app.config.get("TESTING"):
            return
        interval = max(
            5,
            int(
                app.config.get(
                    "OPENMAIC_FULL_RUNTIME_GENERATION_INTERVAL_SECONDS", 20
                )
            ),
        )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(app, interval),
            name="openmaic-full-runtime-generation",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._state.running,
                "lastCheckedAt": self._state.last_checked_at,
                "lastRuntimeId": self._state.last_runtime_id,
                "lastResult": dict(self._state.last_result),
                "lastError": self._state.last_error,
            }

    def run_once(
        self,
        *,
        process_next: Callable[[], dict[str, Any] | None],
        checked_at_ms: int | None = None,
    ) -> dict[str, Any] | None:
        timestamp = int(
            checked_at_ms if checked_at_ms is not None else time.time() * 1000
        )
        with self._lock:
            self._state.last_checked_at = timestamp
        try:
            payload = process_next()
        except Exception as exc:
            with self._lock:
                self._state.last_error = str(exc)[:512]
            raise
        if payload is None:
            return None
        runtime = payload.get("runtime") if isinstance(payload, dict) else {}
        with self._lock:
            self._state.last_runtime_id = (
                str(runtime.get("id") or "") or None
                if isinstance(runtime, dict)
                else None
            )
            self._state.last_result = dict(payload)
            self._state.last_error = ""
        return payload

    def _run(self, app, interval: int) -> None:
        with self._lock:
            self._state.running = True
        try:
            while not self._stop.is_set():
                try:
                    with app.app_context():
                        from services.service_factory import (
                            openmaic_full_runtime_service,
                        )

                        self.run_once(
                            process_next=(
                                openmaic_full_runtime_service().process_pending_batch
                            )
                        )
                except Exception:
                    # The safe status records the failure; a later interval retries.
                    pass
                self._stop.wait(interval)
        finally:
            with self._lock:
                self._state.running = False


openmaic_runtime_generation_runner = OpenMaicRuntimeGenerationRunner()


def start_openmaic_runtime_generation(app) -> None:
    openmaic_runtime_generation_runner.start(app)


def openmaic_runtime_generation_status() -> dict[str, Any]:
    return openmaic_runtime_generation_runner.status()
