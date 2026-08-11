from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Mapping

from repositories.device_repository import DeviceRepository
from repositories.profile_repository import ProfileRepository
from services.camera_observe_service import CameraObserveService
from services.camera_observation_authorization import (
    camera_image_analysis_authorized,
)
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.setting_policy import setting_value


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BoundCameraObservationConfig:
    interval_seconds: float = 60.0
    max_devices_per_tick: int = 8
    offline_backoff_seconds: float = 30.0
    offline_backoff_max_seconds: float = 300.0

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str],
    ) -> "BoundCameraObservationConfig":
        return cls(
            interval_seconds=max(
                1.0,
                float(environ.get("CAMERA_OBSERVATION_INTERVAL_SECONDS", "60")),
            ),
            max_devices_per_tick=max(
                1,
                min(
                    int(
                        environ.get(
                            "CAMERA_OBSERVATION_MAX_DEVICES_PER_TICK",
                            "8",
                        )
                    ),
                    100,
                ),
            ),
            offline_backoff_seconds=max(
                1.0,
                float(
                    environ.get(
                        "CAMERA_OBSERVATION_OFFLINE_BACKOFF_SECONDS",
                        "30",
                    )
                ),
            ),
            offline_backoff_max_seconds=max(
                1.0,
                float(
                    environ.get(
                        "CAMERA_OBSERVATION_OFFLINE_BACKOFF_MAX_SECONDS",
                        "300",
                    )
                ),
            ),
        )


class BoundCameraObservationService:
    """Observe bound cameras without exposing their address or credentials."""

    def __init__(
        self,
        config: BoundCameraObservationConfig,
        *,
        device_repository: DeviceRepository,
        profile_repository: ProfileRepository,
        runtime_resolver: DeviceRuntimeResolver,
        observe_service: CameraObserveService,
        monotonic=time.monotonic,
    ):
        self.config = config
        self.device_repository = device_repository
        self.profile_repository = profile_repository
        self.runtime_resolver = runtime_resolver
        self.observe_service = observe_service
        self.monotonic = monotonic
        self._cursor: tuple[str, str] | None = None
        self._failures: dict[tuple[str, str], tuple[int, float]] = {}

    def run_observe_tick(
        self,
        *,
        window_start_ms: int,
        window_end_ms: int,
    ) -> dict[str, Any]:
        devices = self._next_devices()
        if not devices:
            return _empty_tick("no_active_devices")

        observation_count = 0
        posted_count = 0
        responses: list[dict] = []
        skip_reasons: dict[str, int] = {}
        family_contexts: dict[str, tuple[str | None, str]] = {}
        now = self.monotonic()

        for row in devices:
            family_id = str(row.get("family_id") or "")
            device_id = str(row.get("device_id") or "")
            key = (family_id, device_id)
            if self._in_backoff(key, now=now):
                _increment(skip_reasons, "device_backoff")
                continue

            if family_id not in family_contexts:
                family_contexts[family_id] = self._family_context(family_id)
            child_id, policy_reason = family_contexts[family_id]
            if policy_reason:
                _increment(skip_reasons, policy_reason)
                continue

            try:
                resolved = self.runtime_resolver.resolve(
                    family_id=family_id,
                    device_id=device_id,
                    require_device=True,
                )
                snapshot = resolved.bridge.fetch_snapshot()
            except Exception:
                self._record_failure(key, now=now)
                _increment(skip_reasons, "device_unavailable")
                logger.warning(
                    "bound camera snapshot failed",
                    extra={"device_ref": _device_ref(family_id, device_id)},
                )
                continue

            self._failures.pop(key, None)
            try:
                result = self.observe_service.run_tick(
                    family_id=family_id,
                    child_id=str(child_id or ""),
                    device_id=device_id,
                    image_bytes=snapshot.body,
                    content_type=snapshot.content_type or "image/jpeg",
                    source="camera_observation_worker",
                    force_analyze=False,
                    force_post=False,
                    window_start_ms=window_start_ms,
                    window_end_ms=window_end_ms,
                )
            except Exception:
                _increment(skip_reasons, "observation_unavailable")
                logger.warning(
                    "bound camera analysis failed",
                    extra={"device_ref": _device_ref(family_id, device_id)},
                )
                continue

            observation_count += int(result.observation_count or 0)
            posted_count += 1 if result.posted else 0
            if result.response:
                responses.append(result.response)
            if result.skipped:
                _increment(
                    skip_reasons,
                    str(result.skip_reason or "observation_skipped"),
                )

        skipped = observation_count == 0 and posted_count == 0
        skip_reason = ""
        if skipped:
            skip_reason = _primary_skip_reason(skip_reasons)
        return {
            "observation_count": observation_count,
            "posted_count": posted_count,
            "responses": responses,
            "processed_count": len(devices),
            "skipped": skipped,
            "skip_reason": skip_reason,
            "skip_reasons": skip_reasons,
        }

    def _next_devices(self) -> list[Mapping[str, Any]]:
        after_family_id = self._cursor[0] if self._cursor else None
        after_device_id = self._cursor[1] if self._cursor else None
        with self.device_repository.transaction() as conn:
            rows = self.device_repository.list_active_observation_devices(
                conn,
                after_family_id=after_family_id,
                after_device_id=after_device_id,
                limit=self.config.max_devices_per_tick,
            )
            if not rows and self._cursor is not None:
                rows = self.device_repository.list_active_observation_devices(
                    conn,
                    limit=self.config.max_devices_per_tick,
                )
        if rows:
            last = rows[-1]
            self._cursor = (
                str(last.get("family_id") or ""),
                str(last.get("device_id") or ""),
            )
        else:
            self._cursor = None
        return rows

    def _family_context(self, family_id: str) -> tuple[str | None, str]:
        try:
            with self.profile_repository.transaction() as conn:
                privacy = setting_value(
                    self.profile_repository.get_setting(
                        conn,
                        family_id=family_id,
                        key="privacy",
                    ),
                    "privacy",
                )
                rules = setting_value(
                    self.profile_repository.get_setting(
                        conn,
                        family_id=family_id,
                        key="ai-care-rules",
                    ),
                    "ai-care-rules",
                )
                children = self.profile_repository.list_children(
                    conn,
                    family_id=family_id,
                )
        except Exception:
            return None, "policy_unavailable"

        if not camera_image_analysis_authorized(privacy):
            return None, "privacy_not_authorized"
        if rules.get("taskObservationEnabled") is not True:
            return None, "observation_disabled"
        if not children:
            return None, "no_child"
        if len(children) != 1:
            return None, "child_scope_ambiguous"
        return str(children[0].get("id") or ""), ""

    def _in_backoff(
        self,
        key: tuple[str, str],
        *,
        now: float,
    ) -> bool:
        failure = self._failures.get(key)
        return bool(failure and now < failure[1])

    def _record_failure(
        self,
        key: tuple[str, str],
        *,
        now: float,
    ) -> None:
        attempts = min(
            int((self._failures.get(key) or (0, 0.0))[0]) + 1,
            16,
        )
        delay = min(
            self.config.offline_backoff_seconds * (2 ** (attempts - 1)),
            self.config.offline_backoff_max_seconds,
        )
        self._failures[key] = (attempts, now + delay)


def _empty_tick(reason: str) -> dict[str, Any]:
    return {
        "observation_count": 0,
        "posted_count": 0,
        "responses": [],
        "processed_count": 0,
        "skipped": True,
        "skip_reason": reason,
        "skip_reasons": {reason: 1},
    }


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _primary_skip_reason(counts: Mapping[str, int]) -> str:
    if not counts:
        return "no_eligible_devices"
    return max(counts, key=lambda key: (counts[key], key))


def _device_ref(family_id: str, device_id: str) -> str:
    return hashlib.sha256(
        f"{family_id}:{device_id}".encode("utf-8")
    ).hexdigest()[:12]
