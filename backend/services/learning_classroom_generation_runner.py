from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class LearningClassroomGenerationState:
    running: bool = False
    last_checked_at: int | None = None
    last_request_id: str | None = None
    last_result: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""


class LearningClassroomGenerationRunner:
    """Drain classroom jobs outside student-facing request paths."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state = LearningClassroomGenerationState()

    def start(self, app) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not app.config.get("LEARNING_CLASSROOM_GENERATION_ENABLED"):
            return
        if app.config.get("TESTING"):
            return
        interval = max(
            5,
            int(app.config.get("LEARNING_CLASSROOM_GENERATION_INTERVAL_SECONDS", 15)),
        )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(app, interval),
            name="learning-classroom-generation",
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
                "lastRequestId": self._state.last_request_id,
                "lastResult": dict(self._state.last_result),
                "lastError": self._state.last_error,
            }

    def run_once(
        self,
        *,
        process_next: Callable[[], Any | None],
        checked_at_ms: int | None = None,
    ) -> dict[str, Any] | None:
        timestamp = int(checked_at_ms if checked_at_ms is not None else time.time() * 1000)
        with self._lock:
            self._state.last_checked_at = timestamp
        try:
            generated = process_next()
        except Exception as exc:
            with self._lock:
                self._state.last_error = str(exc)[:512]
            raise
        if generated is None:
            return None
        payload = dict(getattr(generated, "payload", generated) or {})
        job = payload.get("job") if isinstance(payload.get("job"), dict) else {}
        request_id = str(job.get("requestId") or payload.get("requestId") or "") or None
        with self._lock:
            self._state.last_request_id = request_id
            self._state.last_result = payload
            self._state.last_error = (
                str(payload.get("message") or payload.get("error") or "")[:512]
                if payload.get("ok") is False
                else ""
            )
        return payload

    def run_configured_once(
        self,
        *,
        app,
        lesson_packages,
        full_runtime,
        checked_at_ms: int | None = None,
    ) -> dict[str, Any] | None:
        if app.config.get("LEARNING_FORMAL_RUNTIME_CANDIDATE_ENABLED"):
            process_next = lambda: lesson_packages.process_next_formal_candidate(
                full_runtime
            )
        else:
            process_next = lesson_packages.process_next_pending
        return self.run_once(
            process_next=process_next, checked_at_ms=checked_at_ms
        )

    def _run(self, app, interval: int) -> None:
        with self._lock:
            self._state.running = True
        try:
            while not self._stop.is_set():
                try:
                    with app.app_context():
                        from services.service_factory import (
                            lesson_package_service,
                            openmaic_full_runtime_service,
                        )

                        self.run_configured_once(
                            app=app,
                            lesson_packages=lesson_package_service(),
                            full_runtime=openmaic_full_runtime_service(),
                        )
                except Exception:
                    # Status retains the safe error and the next interval retries another pass.
                    pass
                self._stop.wait(interval)
        finally:
            with self._lock:
                self._state.running = False


learning_classroom_generation_runner = LearningClassroomGenerationRunner()


def start_learning_classroom_generation(app) -> None:
    learning_classroom_generation_runner.start(app)


def learning_classroom_generation_status() -> dict[str, Any]:
    return learning_classroom_generation_runner.status()
