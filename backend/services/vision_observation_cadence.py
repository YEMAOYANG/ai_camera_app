from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VisionCadenceState:
    last_cloud_at: float = 0.0
    hour_bucket: int = 0
    hour_calls: int = 0
    backoff_until: float = 0.0
    last_result: dict[str, Any] | None = None


@dataclass
class VisionCadenceGate:
    min_interval_seconds: float = 60.0
    max_calls_per_hour: int = 20
    backoff_seconds: float = 300.0
    _devices: dict[str, VisionCadenceState] = field(default_factory=dict)

    def should_call_cloud(self, device_key: str, *, force: bool = False, now: float | None = None) -> bool:
        current = now if now is not None else time.time()
        state = self._devices.setdefault(device_key, VisionCadenceState())
        if force:
            return True
        if current < state.backoff_until:
            return False
        if state.last_cloud_at and (current - state.last_cloud_at) < self.min_interval_seconds:
            return False
        bucket = int(current // 3600)
        if state.hour_bucket != bucket:
            state.hour_bucket = bucket
            state.hour_calls = 0
        if state.hour_calls >= self.max_calls_per_hour:
            return False
        return True

    def record_cloud_call(self, device_key: str, result: dict[str, Any], *, now: float | None = None) -> None:
        current = now if now is not None else time.time()
        state = self._devices.setdefault(device_key, VisionCadenceState())
        state.last_cloud_at = current
        state.last_result = dict(result)
        bucket = int(current // 3600)
        if state.hour_bucket != bucket:
            state.hour_bucket = bucket
            state.hour_calls = 0
        state.hour_calls += 1

    def record_rate_limit(self, device_key: str, *, now: float | None = None) -> None:
        current = now if now is not None else time.time()
        state = self._devices.setdefault(device_key, VisionCadenceState())
        state.backoff_until = current + self.backoff_seconds

    def cached_result(self, device_key: str) -> dict[str, Any] | None:
        state = self._devices.get(device_key)
        if state is None or state.last_result is None:
            return None
        cached = dict(state.last_result)
        cached["method"] = "guardian_kimi_cached"
        cadence = dict(cached.get("vision_cadence") or {})
        cadence["called_cloud"] = False
        cached["vision_cadence"] = cadence
        return cached
