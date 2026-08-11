from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from core.config import BACKEND_ROOT
from core.database import Database
from core.security import now_ms
from integrations.onvif.client import OnvifClient
from repositories.device_repository import DeviceRepository
from repositories.profile_repository import ProfileRepository
from services.bound_camera_observation_service import (
    BoundCameraObservationConfig,
    BoundCameraObservationService,
)
from services.camera_observe_service import (
    _database_url_from_env,
    build_observe_service_from_env,
)
from services.device_credential_store import EncryptedFileCredentialStore
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.vision_prefilter_service import validate_prefilter_runtime
from services.vision_worker_config import vision_worker_config


log = logging.getLogger("camera_observation_worker")
RUNNING = True


class ObservationAdapter(Protocol):
    config: BoundCameraObservationConfig

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
        posted_count = int(
            result.get("posted_count")
            if result.get("posted_count") is not None
            else (1 if result.get("posted") else 0)
        )
        responses = result.get("responses")
        if not isinstance(responses, list):
            responses = [result.get("response")] if result.get("response") else []
        return CameraObservationWorkerResult(
            observation_count=int(result.get("observation_count") or 0),
            posted_count=posted_count,
            responses=[item for item in responses if isinstance(item, dict)],
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
    config = BoundCameraObservationConfig.from_env(env)
    validate_prefilter_runtime()
    database_url = _database_url_from_env(env)
    database = Database(database_url)
    observe_service = build_observe_service_from_env(env)
    client = OnvifClient(
        discovery_timeout_seconds=float(
            env.get("ONVIF_DISCOVERY_TIMEOUT_SECONDS", "1.5")
        ),
        http_timeout_seconds=float(
            env.get("ONVIF_HTTP_TIMEOUT_SECONDS", "4")
        ),
        rtsp_timeout_seconds=float(
            env.get("ONVIF_RTSP_TIMEOUT_SECONDS", "4")
        ),
    )
    app_env = str(env.get("APP_ENV") or "development").strip().lower()
    secret_root_value = str(
        env.get("APP_DEVICE_SECRET_STORE_DIR") or ""
    ).strip() or str(BACKEND_ROOT / "data" / "device-secrets")
    key_file_value = str(
        env.get("APP_DEVICE_SECRET_KEY_FILE") or ""
    ).strip() or str(BACKEND_ROOT / "data" / ".device-secret.key")
    credential_store = EncryptedFileCredentialStore(
        root=_backend_path(secret_root_value),
        key=str(env.get("APP_DEVICE_SECRET_KEY") or ""),
        key_file=_backend_path(key_file_value),
        allow_key_generation=app_env in {"development", "test"},
    )
    resolver = DeviceRuntimeResolver(
        database_url,
        provider=str(
            env.get("CAMERA_RUNTIME_PROVIDER")
            or env.get("APP_CAMERA_RUNTIME_ADAPTER")
            or "disabled"
        ),
        legacy_provider=str(
            env.get("APP_CAMERA_RUNTIME_ADAPTER")
            or env.get("CAMERA_RUNTIME_PROVIDER")
            or "disabled"
        ),
        ai_camera_test_base_url=str(env.get("AI_CAMERA_TEST_BASE_URL") or ""),
        camera_backend_url=str(env.get("APP_CAMERA_BACKEND_URL") or ""),
        dev_adapters_enabled=_enabled(
            env.get(
                "APP_ENABLE_DEV_ADAPTERS",
                "1" if app_env in {"development", "test"} else "0",
            )
        ),
        app_env=app_env,
        onvif_client=client,
        credential_store=credential_store,
    )
    return CameraObservationWorker(
        BoundCameraObservationService(
            config,
            device_repository=DeviceRepository(database),
            profile_repository=ProfileRepository(database),
            runtime_resolver=resolver,
            observe_service=observe_service,
        ),
    )


def _backend_path(value: object) -> Path:
    path = Path(str(value or ""))
    return path if path.is_absolute() else BACKEND_ROOT / path


def _enabled(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
