from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class LearningMediaWorkerState:
    running: bool = False
    last_checked_at: int | None = None
    last_job_id: str | None = None
    last_result: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""


class LearningMediaWorkerRunner:
    """Materialize queued narration and finalize its staged lesson package."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state = LearningMediaWorkerState()

    def start(self, app) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not app.config.get("LEARNING_MEDIA_WORKER_ENABLED"):
            return
        if app.config.get("TESTING"):
            return
        interval = max(
            5,
            int(app.config.get("LEARNING_MEDIA_WORKER_INTERVAL_SECONDS", 15)),
        )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(app, interval),
            name="learning-media-materialization",
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
                "lastJobId": self._state.last_job_id,
                "lastResult": dict(self._state.last_result),
                "lastError": self._state.last_error,
            }

    def run_once(
        self,
        *,
        next_pending: Callable[[], dict[str, Any] | None],
        materialize: Callable[[str], dict[str, Any]],
        finalize: Callable[[str, int], dict[str, Any]],
        checked_at_ms: int | None = None,
    ) -> dict[str, Any] | None:
        timestamp = int(
            checked_at_ms if checked_at_ms is not None else time.time() * 1000
        )
        with self._lock:
            self._state.last_checked_at = timestamp
        candidate = next_pending()
        if candidate is None:
            return None
        job_id = str(candidate.get("id") or "")
        package = candidate.get("package")
        with self._lock:
            self._state.last_job_id = job_id or None
        try:
            job = materialize(job_id)
            result: dict[str, Any] = {"job": job, "package": None}
            if isinstance(package, dict) and package.get("id") is not None:
                result["package"] = finalize(
                    str(package["id"]),
                    int(package["version"]),
                )
        except Exception as exc:
            if isinstance(package, dict) and package.get("id") is not None:
                try:
                    finalize(str(package["id"]), int(package["version"]))
                except Exception:
                    pass
            with self._lock:
                self._state.last_error = str(exc)[:512]
            raise
        with self._lock:
            self._state.last_result = result
            self._state.last_error = ""
        return result

    def _run(self, app, interval: int) -> None:
        with self._lock:
            self._state.running = True
        try:
            while not self._stop.is_set():
                try:
                    with app.app_context():
                        from services.service_factory import (
                            learning_media_materialization_service,
                            lesson_package_service,
                        )

                        media_service = learning_media_materialization_service()
                        package_service = lesson_package_service()
                        self.run_once(
                            next_pending=media_service.next_pending_job,
                            materialize=lambda job_id: media_service.materialize_job(
                                job_id=job_id
                            ),
                            finalize=lambda package_id, package_version: (
                                package_service.finalize_media_package(
                                    package_id=package_id,
                                    package_version=package_version,
                                )
                            ),
                        )
                except Exception:
                    # State holds a safe error. Pending unconfigured jobs remain
                    # pending; failed upstream jobs remain explicit and never
                    # become fabricated ready assets.
                    pass
                self._stop.wait(interval)
        finally:
            with self._lock:
                self._state.running = False


learning_media_worker_runner = LearningMediaWorkerRunner()


def start_learning_media_worker(app) -> None:
    learning_media_worker_runner.start(app)


def learning_media_worker_status() -> dict[str, Any]:
    return learning_media_worker_runner.status()
