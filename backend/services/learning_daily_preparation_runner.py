from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass
class LearningDailyPreparationState:
    running: bool = False
    last_checked_at: int | None = None
    last_prepared_date: str | None = None
    last_result: dict[str, Any] = field(default_factory=dict)
    last_error: str = ""


class LearningDailyPreparationRunner:
    """Keeps missing daily subject tasks materialized after the local 05:00 gate."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._state = LearningDailyPreparationState()

    def start(self, app) -> None:
        if self._thread and self._thread.is_alive():
            return
        if not app.config.get("LEARNING_DAILY_PREPARATION_ENABLED"):
            return
        if app.config.get("TESTING"):
            return

        timezone_name = str(
            app.config.get("LEARNING_DAILY_TIMEZONE") or "Asia/Shanghai"
        )
        try:
            zone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise RuntimeError(
                f"Unknown learning daily timezone: {timezone_name}"
            ) from exc
        interval = max(
            10,
            int(app.config.get("LEARNING_DAILY_PREPARATION_INTERVAL_SECONDS", 60)),
        )
        hour = int(app.config.get("LEARNING_DAILY_PREPARATION_HOUR", 5))
        minute = int(app.config.get("LEARNING_DAILY_PREPARATION_MINUTE", 0))
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(app, zone, hour, minute, interval),
            name="learning-daily-preparation",
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
                "lastPreparedDate": self._state.last_prepared_date,
                "lastResult": dict(self._state.last_result),
                "lastError": self._state.last_error,
            }

    def run_due_once(
        self,
        *,
        now: datetime,
        hour: int,
        minute: int,
        prepare: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Runs one idempotent sweep after the gate; safe to unit-test without threads."""

        now_ms = int(now.timestamp() * 1000)
        local_date = now.date().isoformat()
        due = (now.hour, now.minute) >= (hour, minute)
        with self._lock:
            self._state.last_checked_at = now_ms
        if not due:
            return None

        try:
            result = prepare(local_date)
        except Exception as exc:
            with self._lock:
                self._state.last_error = str(exc)
            raise
        with self._lock:
            self._state.last_result = dict(result)
            if result.get("ok") is False:
                failure_count = len(result.get("failures") or [])
                self._state.last_error = (
                    f"daily preparation incomplete: {failure_count} child failure(s)"
                )
                return result
            self._state.last_prepared_date = local_date
            self._state.last_error = ""
        return result

    def _run(
        self,
        app,
        zone: ZoneInfo,
        hour: int,
        minute: int,
        interval: int,
    ) -> None:
        with self._lock:
            self._state.running = True
        try:
            while not self._stop.is_set():
                try:
                    with app.app_context():
                        from services.service_factory import learning_service

                        self.run_due_once(
                            now=datetime.now(zone),
                            hour=hour,
                            minute=minute,
                            prepare=lambda learning_date: learning_service().ensure_today_for_all_primary_children(
                                learning_date=learning_date
                            ),
                        )
                except Exception:
                    # The error is exposed through status and retried on the next interval.
                    pass
                self._stop.wait(interval)
        finally:
            with self._lock:
                self._state.running = False


learning_daily_preparation_runner = LearningDailyPreparationRunner()


def start_learning_daily_preparation(app) -> None:
    learning_daily_preparation_runner.start(app)


def learning_daily_preparation_status() -> dict[str, Any]:
    return learning_daily_preparation_runner.status()
