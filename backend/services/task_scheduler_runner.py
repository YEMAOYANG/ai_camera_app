from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskSchedulerState:
    running: bool = False
    last_tick_at: int | None = None
    next_tick_at: int | None = None
    tick_count: int = 0
    last_error: str = ""
    last_result: dict[str, Any] = field(default_factory=dict)


class TaskSchedulerRunner:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state = TaskSchedulerState()

    def start(self, app) -> None:
        if self._thread and self._thread.is_alive():
            return
        if app.config.get("DEBUG") and os.environ.get("WERKZEUG_RUN_MAIN") == "false":
            return
        interval = max(1, int(app.config.get("TASK_SCHEDULER_INTERVAL_SECONDS", 15)))
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(app, interval),
            name="mira-task-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._state.running,
                "lastTickAt": self._state.last_tick_at,
                "nextTickAt": self._state.next_tick_at,
                "tickCount": self._state.tick_count,
                "lastError": self._state.last_error,
                "lastResult": self._state.last_result,
            }

    def _run(self, app, interval: int) -> None:
        with self._lock:
            self._state.running = True
        try:
            while not self._stop.is_set():
                tick_start = int(time.time() * 1000)
                try:
                    with app.app_context():
                        from services.service_factory import task_runtime_service
                        from services.task_event_stream import publish_task_runtime_result

                        result = task_runtime_service().tick()
                        publish_task_runtime_result(result)
                    with self._lock:
                        self._state.tick_count += 1
                        self._state.last_tick_at = tick_start
                        self._state.last_error = ""
                        self._state.last_result = result
                except Exception as exc:  # pragma: no cover - covered by status path in integration.
                    with self._lock:
                        self._state.tick_count += 1
                        self._state.last_tick_at = tick_start
                        self._state.last_error = str(exc)
                next_tick = time.time() + interval
                with self._lock:
                    self._state.next_tick_at = int(next_tick * 1000)
                self._stop.wait(interval)
        finally:
            with self._lock:
                self._state.running = False


task_scheduler_runner = TaskSchedulerRunner()


def start_task_scheduler(app) -> None:
    if app.config.get("TASK_SCHEDULER_ENABLED") and not app.config.get("TESTING"):
        task_scheduler_runner.start(app)


def task_scheduler_status() -> dict:
    return task_scheduler_runner.status()
