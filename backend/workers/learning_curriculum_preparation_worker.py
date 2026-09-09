from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
from urllib.parse import urlparse


# app.py creates its module-level Flask app during import. Set the role first
# so importing it cannot start a second, embedded curriculum runner.
os.environ["MIRA_PROCESS_ROLE"] = "curriculum-worker"

from app import app  # noqa: E402
from core.security import now_ms  # noqa: E402
from services.learning_curriculum_preparation_runner import (  # noqa: E402
    learning_curriculum_preparation_config_projection,
    learning_curriculum_preparation_runner,
)


LOGGER = logging.getLogger("mira.curriculum_worker")
ACTIVE_PROGRESS_WAIT_SECONDS = 2
SIDECAR_CLI = (
    Path(__file__).resolve().parents[1]
    / "openmaic-sidecar"
    / "src"
    / "cli.mjs"
)


def _wait_seconds_after_tick(result: object, interval: int) -> int:
    if (
        isinstance(result, dict)
        and result.get("claimed") == 1
        and result.get("resultCode") == "progressed"
    ):
        # Drain one shared build quickly while preserving the strict one-work-
        # unit/one-Provider-call concurrency contract.
        return ACTIVE_PROGRESS_WAIT_SECONDS
    return max(5, interval)


def _preflight() -> None:
    projection = learning_curriculum_preparation_config_projection(app)
    if projection is None:
        raise RuntimeError("curriculum worker configuration contract is invalid")
    if not projection.runner_enabled:
        raise RuntimeError(
            "LEARNING_CURRICULUM_PREPARATION_RUNNER_ENABLED must be enabled"
        )
    if not projection.content_generation_enabled:
        raise RuntimeError(
            "LEARNING_CURRICULUM_PREPARATION_CONTENT_GENERATION_ENABLED must be enabled"
        )
    if not app.config.get("OPENMAIC_FULL_RUNTIME_ENABLED"):
        raise RuntimeError("OPENMAIC_FULL_RUNTIME_ENABLED must be enabled")
    if not app.config.get("OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED"):
        raise RuntimeError(
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED must be enabled"
        )
    if not app.config.get("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED"):
        raise RuntimeError("OPENMAIC_FULL_RUNTIME_AUTORUN_ENABLED must be enabled")
    runtime_url = str(
        app.config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""
    ).strip()
    parsed_runtime_url = urlparse(runtime_url)
    if (
        parsed_runtime_url.scheme not in {"http", "https"}
        or not parsed_runtime_url.netloc
    ):
        raise RuntimeError(
            "OPENMAIC_FULL_RUNTIME_INTERNAL_URL is not configured"
        )
    # The learning worker never requires the backend camera Kimi profile. Its
    # only credential is the private OpenMAIC token; OpenMAIC owns the model
    # credential and the paid courseware invocation.
    if not str(os.getenv("INTERNAL_API_TOKEN") or "").strip():
        raise RuntimeError("INTERNAL_API_TOKEN is not configured")

    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is unavailable in the curriculum worker")
    if not SIDECAR_CLI.is_file():
        raise RuntimeError("OpenMAIC question sidecar is unavailable")
    completed = subprocess.run(
        [node, str(SIDECAR_CLI), "--availability"],
        cwd=str(SIDECAR_CLI.parents[1]),
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenMAIC sidecar readiness returned invalid JSON") from exc
    if (
        completed.returncode != 0
        or not isinstance(payload, dict)
        or payload.get("available") is not True
    ):
        raise RuntimeError("OpenMAIC sidecar readiness failed")


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _preflight()
    interval = int(
        app.config.get("LEARNING_CURRICULUM_PREPARATION_INTERVAL_SECONDS", 15)
    )
    stop = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("curriculum worker ready intervalSeconds=%s", interval)

    while not stop.is_set():
        wait_seconds = max(5, interval)
        try:
            # Formal-stage factories resolve services through ``current_app``.
            # Keep every background tick inside the same Flask application
            # context as an HTTP request would have.
            with app.app_context():
                result = learning_curriculum_preparation_runner.run_once(
                    app,
                    now_ms=now_ms(),
                )
            LOGGER.info(
                "curriculum tick result=%s",
                json.dumps(result, ensure_ascii=True, sort_keys=True),
            )
            wait_seconds = _wait_seconds_after_tick(result, interval)
        except Exception as exc:
            LOGGER.exception(
                "curriculum tick failed class=%s",
                type(exc).__name__,
            )
        stop.wait(wait_seconds)

    LOGGER.info("curriculum worker stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
