from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from flask import Flask  # noqa: E402

from core.config import AppConfig, validate_flask_config  # noqa: E402
from core.security import now_ms  # noqa: E402
from services.learning_curriculum_preparation_contract import (  # noqa: E402
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import (  # noqa: E402
    learning_curriculum_preparation_config_projection,
    learning_curriculum_preparation_runner,
)
from services.openmaic_full_runtime_service import (  # noqa: E402
    OpenMaicRuntimeServiceError,
)
from services.service_factory import (  # noqa: E402
    learning_curriculum_preparation_service,
    openmaic_full_runtime_service,
)


EXPECTED_GRADE_CODE = "primary_1"
MAX_PUBLISHED_COURSES = 1
MAX_DISTINCT_PROVIDER_ITEMS = 1
MAX_PROVIDER_DISPATCHES = 14
MAX_DISTINCT_RUNTIME_ITEMS = 1
MAX_RUNTIME_ATTEMPTS = 3
MAX_DISTINCT_RECEIPT_ITEMS = 1
MAX_TICKS = 600
POLL_SECONDS = 1.25
RUNTIME_POLL_SECONDS = 5.0
LOCK_PATH = Path("/tmp/mira-generate-one-formal-course.lock")


class SafetyStop(RuntimeError):
    pass


def _operator_app() -> Flask:
    app = Flask("mira-one-course-operator")
    app.config.update(AppConfig.from_env().to_flask_config())
    # The adapter checks this immediately after publishing course one and
    # before it may claim a content phase for course two.
    app.config[
        "LEARNING_CURRICULUM_PREPARATION_PROGRESSIVE_PUBLICATION_LIMIT"
    ] = MAX_PUBLISHED_COURSES
    validate_flask_config(app.config)
    return app


def _emit(event: str, **payload: object) -> None:
    print(
        json.dumps(
            {"event": event, **payload},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


def _eligible_child(repository) -> dict[str, Any]:
    with repository.transaction() as conn:
        rows = list(
            conn.execute(
                """
                SELECT * FROM children
                WHERE grade_code = ? AND grade_selection_revision >= 1
                ORDER BY updated_at DESC, id
                """,
                (EXPECTED_GRADE_CODE,),
            ).fetchall()
        )
    if len(rows) != 1:
        raise SafetyStop(
            "one-course generation requires exactly one eligible primary_1 child"
        )
    return dict(rows[0])


def _snapshot(repository, *, child: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    with repository.transaction() as conn:
        plan = repository.get_current_for_child(
            conn,
            family_id=str(child["family_id"]),
            child_id=str(child["id"]),
            grade_selection_revision=int(child["grade_selection_revision"]),
            target_fingerprint=fingerprint,
        )
        if plan is None:
            return {
                "plan": None,
                "buildId": None,
                "releaseId": None,
                "providerDispatches": 0,
                "providerItems": 0,
                "runtimeItems": 0,
                "runtimeAttempts": 0,
                "runtime": None,
                "receiptItems": 0,
                "publishedCourses": 0,
                "course": None,
            }

        build_id = str(plan.get("catalog_build_id") or "")
        release_id = str(plan.get("catalog_release_id") or "")
        provider = {
            "dispatches": 0,
            "items": 0,
        }
        if build_id:
            row = conn.execute(
                """
                SELECT COUNT(*) AS dispatches,
                  COUNT(DISTINCT dispatch.build_item_id) AS items
                FROM learning_course_provider_dispatches AS dispatch
                INNER JOIN learning_catalog_build_items AS item
                  ON item.id = dispatch.build_item_id
                WHERE item.build_job_id = ?
                """,
                (build_id,),
            ).fetchone()
            provider = {
                "dispatches": int((row or {}).get("dispatches") or 0),
                "items": int((row or {}).get("items") or 0),
            }

        runtime_rows = list(conn.execute(
            """
            SELECT id, request_id, status, quality_status, upstream_job_id,
              upstream_classroom_id, provider_attempt_ordinal, error_code,
              error_message_safe, candidate_build_item_id, retired_at,
              created_at, updated_at
            FROM learning_openmaic_runtime_classrooms
            WHERE candidate_target_fingerprint = ?
              AND candidate_build_item_id IS NOT NULL
            ORDER BY created_at, id
            """,
            (fingerprint,),
        ).fetchall())
        receipt_row = conn.execute(
            """
            SELECT COUNT(DISTINCT build_item_id) AS items,
              SUM(CASE WHEN publication_status = 'published' THEN 1 ELSE 0 END)
                AS published
            FROM learning_curriculum_classroom_item_receipts
            WHERE target_fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()
        course = conn.execute(
            """
            SELECT receipt.course_id, receipt.course_version,
              receipt.runtime_classroom_id, runtime.upstream_classroom_id,
              course.title, course.subject
            FROM learning_curriculum_classroom_item_receipts AS receipt
            INNER JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = receipt.runtime_classroom_id
            INNER JOIN learning_courses AS course
              ON course.id = receipt.course_id
             AND course.version = receipt.course_version
            WHERE receipt.target_fingerprint = ?
              AND receipt.publication_status = 'published'
            ORDER BY receipt.published_at, receipt.build_item_id
            LIMIT 1
            """,
            (fingerprint,),
        ).fetchone()
        citation_recovery = None
        if runtime_rows:
            citation_recovery = conn.execute(
                """
                SELECT id, runtime_classroom_id, source_upstream_job_id,
                  upstream_recovery_id, status, response_receipt_sha256,
                  created_at, updated_at, terminal_at
                FROM learning_openmaic_formal_citation_recoveries
                WHERE runtime_classroom_id = ?
                LIMIT 1
                """,
                (runtime_rows[-1]["id"],),
            ).fetchone()

    return {
        "plan": dict(plan),
        "buildId": build_id or None,
        "releaseId": release_id or None,
        "providerDispatches": provider["dispatches"],
        "providerItems": provider["items"],
        "runtimeItems": len(
            {
                str(row["candidate_build_item_id"])
                for row in runtime_rows
            }
        ),
        "runtimeAttempts": len(runtime_rows),
        "runtimes": [dict(row) for row in runtime_rows],
        "runtime": dict(runtime_rows[-1]) if runtime_rows else None,
        "citationRecovery": (
            dict(citation_recovery) if citation_recovery is not None else None
        ),
        "receiptItems": int((receipt_row or {}).get("items") or 0),
        "publishedCourses": int((receipt_row or {}).get("published") or 0),
        "course": dict(course) if course is not None else None,
    }


def _assert_one_course_scope(snapshot: dict[str, Any]) -> None:
    limits = (
        ("published courses", int(snapshot["publishedCourses"]), MAX_PUBLISHED_COURSES),
        ("Provider build items", int(snapshot["providerItems"]), MAX_DISTINCT_PROVIDER_ITEMS),
        ("Provider dispatches", int(snapshot["providerDispatches"]), MAX_PROVIDER_DISPATCHES),
        ("Runtime build items", int(snapshot["runtimeItems"]), MAX_DISTINCT_RUNTIME_ITEMS),
        ("Runtime attempts", int(snapshot["runtimeAttempts"]), MAX_RUNTIME_ATTEMPTS),
        ("receipt build items", int(snapshot["receiptItems"]), MAX_DISTINCT_RECEIPT_ITEMS),
    )
    for label, observed, maximum in limits:
        if observed > maximum:
            raise SafetyStop(
                f"one-course safety limit exceeded for {label}: {observed}>{maximum}"
            )


def _assert_runtime_retry_scope(
    snapshot: Mapping[str, Any],
    *,
    allow_known_runtime_retry: bool,
    citation_recovery_allowed: bool = False,
) -> None:
    raw_runtimes = snapshot.get("runtimes") or []
    if not isinstance(raw_runtimes, list):
        raise SafetyStop("formal Runtime attempt inventory is invalid")
    runtimes = [row for row in raw_runtimes if isinstance(row, dict)]
    if len(runtimes) != len(raw_runtimes):
        raise SafetyStop("formal Runtime attempt inventory is invalid")
    for ordinal, runtime in enumerate(runtimes, start=1):
        if (
            int(runtime.get("provider_attempt_ordinal") or 0) != ordinal
            or runtime.get("retired_at") is not None
        ):
            raise SafetyStop("formal Runtime attempt history is not canonical")
    if len(runtimes) >= 2:
        predecessor = runtimes[0]
        if not (
            str(predecessor.get("status") or "") == "failed"
            and str(predecessor.get("quality_status") or "") == "rejected"
            and str(predecessor.get("error_code") or "")
            == "openmaic_formal_generation_failed"
            and bool(str(predecessor.get("upstream_job_id") or ""))
        ):
            raise SafetyStop("formal Runtime retry predecessor is not a known rejection")
    if not runtimes:
        return
    latest = runtimes[-1]
    latest_status = str(latest.get("status") or "")
    if latest_status in {"generating", "ready"}:
        return
    if latest_status == "recovering" and citation_recovery_allowed:
        return
    if latest_status != "failed":
        raise SafetyStop(
            "formal Runtime has a non-replayable status: "
            + (latest_status or "unknown")
        )
    if not (
        str(latest.get("quality_status") or "") == "rejected"
        and str(latest.get("error_code") or "")
        == "openmaic_formal_generation_failed"
        and bool(str(latest.get("upstream_job_id") or ""))
    ):
        raise SafetyStop("formal Runtime failure is not safely retryable")
    if len(runtimes) >= MAX_RUNTIME_ATTEMPTS:
        if citation_recovery_allowed:
            return
        raise SafetyStop("formal Runtime retry budget is exhausted")
    if not allow_known_runtime_retry:
        raise SafetyStop(
            "known formal Runtime rejection requires explicit retry confirmation"
        )


def _reserve_current_child(service, child: dict[str, Any]) -> None:
    with service.repository.transaction() as conn:
        service.reserve_for_saved_child(
            conn,
            family_id=str(child["family_id"]),
            child=child,
            now=now_ms(),
        )


def _ensure_formal_provider_ready(runtime_service) -> None:
    circuit = runtime_service.formal_provider_circuit_status()
    if circuit.get("dispatchAllowed") is True:
        return
    result = runtime_service.probe_formal_generation_provider()
    if result.get("ready") is not True:
        raise SafetyStop("DeepSeek formal generation readiness probe failed")
    _emit(
        "provider_probe_ready",
        providerId=result.get("providerId"),
        modelId=result.get("modelId"),
    )


def _citation_recovery_allowed(
    snapshot: Mapping[str, Any], runtime_service
) -> bool:
    if not (
        getattr(runtime_service, "formal_citation_recovery_enabled", False)
        and getattr(runtime_service, "formal_citation_recovery_client", None)
        is not None
    ):
        return False
    source_job_id = str(
        getattr(runtime_service, "formal_citation_recovery_source_job_id", "")
        or ""
    )
    raw_runtimes = snapshot.get("runtimes")
    if not isinstance(raw_runtimes, list) or len(raw_runtimes) != 2:
        return False
    runtimes = [row for row in raw_runtimes if isinstance(row, Mapping)]
    if len(runtimes) != 2:
        return False
    latest = runtimes[-1]
    recovery = snapshot.get("citationRecovery")
    status = str(latest.get("status") or "")
    if not (
        int(latest.get("attempt_ordinal") or 0) == 2
        and int(latest.get("provider_attempt_ordinal") or 0) == 2
        and str(latest.get("upstream_job_id") or "") == source_job_id
        and latest.get("retired_at") is None
    ):
        return False
    if status == "failed":
        return bool(
            recovery is None
            and str(latest.get("quality_status") or "") == "rejected"
            and str(latest.get("error_code") or "")
            == "openmaic_formal_generation_failed"
        )
    if status == "recovering":
        return bool(
            isinstance(recovery, Mapping)
            and str(recovery.get("source_upstream_job_id") or "")
            == source_job_id
            and str(recovery.get("status") or "")
            in {"reserving", "running", "succeeded"}
        )
    if status in {"generating", "ready"}:
        return bool(
            isinstance(recovery, Mapping)
            and str(recovery.get("source_upstream_job_id") or "")
            == source_job_id
            and str(recovery.get("status") or "") == "succeeded"
        )
    return False


def _reconcile_current_runtime(runtime_service, runtime: Mapping[str, Any]) -> str:
    status = str(runtime.get("status") or "")
    if status == "ready":
        return status
    if status != "generating":
        raise SafetyStop(
            "formal Runtime cannot be continued without a new dispatch: "
            + (status or "unknown")
        )
    upstream_job_id = str(runtime.get("upstream_job_id") or "")
    if not upstream_job_id:
        raise SafetyStop("formal Runtime is generating without an upstream job id")
    try:
        payload = runtime_service.generation_status(upstream_job_id)
    except OpenMaicRuntimeServiceError as exc:
        raise SafetyStop(
            "formal Runtime reconciliation failed: " + str(exc.code)
        ) from exc
    reconciled = payload.get("runtime") if isinstance(payload, dict) else None
    if not isinstance(reconciled, dict):
        raise SafetyStop("formal Runtime reconciliation returned no runtime")
    reconciled_status = str(reconciled.get("status") or "")
    if reconciled_status not in {"generating", "ready"}:
        raise SafetyStop(
            "formal Runtime reached a terminal non-ready status: "
            + (reconciled_status or "unknown")
        )
    return reconciled_status


def _run(timeout_seconds: int, *, allow_known_runtime_retry: bool) -> int:
    app = _operator_app()
    projection = learning_curriculum_preparation_config_projection(app)
    if projection is None:
        raise SafetyStop("formal curriculum runner configuration is invalid")
    if not projection.runner_enabled or not projection.content_generation_enabled:
        raise SafetyStop("formal curriculum generation is disabled")
    if projection.grade_code != EXPECTED_GRADE_CODE:
        raise SafetyStop("one-course generation is restricted to primary_1")

    expected_fingerprint = preparation_target_fingerprint(
        build_preparation_target(EXPECTED_GRADE_CODE)
    )
    if projection.target_fingerprint != expected_fingerprint:
        raise SafetyStop("runner target fingerprint is not the current contract")

    with app.app_context():
        service = learning_curriculum_preparation_service()
        repository = service.repository
        runtime_service = openmaic_full_runtime_service()
        child = _eligible_child(repository)
        before = _snapshot(
            repository,
            child=child,
            fingerprint=expected_fingerprint,
        )
        _assert_one_course_scope(before)
        citation_recovery_allowed = _citation_recovery_allowed(
            before, runtime_service
        )
        _assert_runtime_retry_scope(
            before,
            allow_known_runtime_retry=allow_known_runtime_retry,
            citation_recovery_allowed=citation_recovery_allowed,
        )
        if int(before["publishedCourses"]) == MAX_PUBLISHED_COURSES:
            _emit(
                "already_ready",
                gradeCode=EXPECTED_GRADE_CODE,
                publishedCourses=1,
                course=before["course"],
            )
            return 0
        if before["plan"] is not None:
            plan = dict(before["plan"])
            if str(plan.get("status") or "") in {"failed", "ready"}:
                raise SafetyStop(
                    "current professional target has a terminal non-published plan"
                )
        if not citation_recovery_allowed:
            _ensure_formal_provider_ready(runtime_service)

        _reserve_current_child(service, child)
        started_at = time.monotonic()
        last_observation: tuple[object, ...] | None = None

        for tick in range(1, MAX_TICKS + 1):
            if time.monotonic() - started_at >= timeout_seconds:
                raise SafetyStop("one-course generation timed out")

            current = _snapshot(
                repository,
                child=child,
                fingerprint=expected_fingerprint,
            )
            _assert_one_course_scope(current)
            citation_recovery_allowed = _citation_recovery_allowed(
                current, runtime_service
            )
            _assert_runtime_retry_scope(
                current,
                allow_known_runtime_retry=allow_known_runtime_retry,
                citation_recovery_allowed=citation_recovery_allowed,
            )
            if int(current["publishedCourses"]) == MAX_PUBLISHED_COURSES:
                _emit(
                    "completed",
                    gradeCode=EXPECTED_GRADE_CODE,
                    publishedCourses=1,
                    providerDispatches=int(current["providerDispatches"]),
                    course=current["course"],
                )
                return 0

            plan = current["plan"]
            if plan is not None and str(plan.get("status") or "") == "failed":
                raise SafetyStop(
                    "formal generation failed: "
                    + str(plan.get("error_code") or "unknown_error")
                )

            observation = (
                str((plan or {}).get("status") or ""),
                str((plan or {}).get("stage") or ""),
                str((plan or {}).get("bound_content_phase") or ""),
                int(current["providerDispatches"]),
                int(current["runtimeItems"]),
                str((current.get("runtime") or {}).get("status") or ""),
                int(current["receiptItems"]),
                int(current["publishedCourses"]),
                str((current.get("citationRecovery") or {}).get("status") or ""),
            )
            if observation != last_observation:
                _emit(
                    "progress",
                    tick=tick,
                    status=observation[0],
                    stage=observation[1],
                    contentPhase=observation[2] or None,
                    providerDispatches=observation[3],
                    runtimeItems=observation[4],
                    runtimeStatus=observation[5] or None,
                    receiptItems=observation[6],
                    publishedCourses=observation[7],
                    citationRecoveryStatus=observation[8] or None,
                )
                last_observation = observation

            runtime = current.get("runtime")
            if (
                isinstance(runtime, dict)
                and citation_recovery_allowed
                and str(runtime.get("status") or "") == "failed"
            ):
                runtime_service.start_formal_citation_recovery(
                    str(runtime["id"])
                )
                time.sleep(RUNTIME_POLL_SECONDS)
                continue
            if (
                isinstance(runtime, dict)
                and citation_recovery_allowed
                and str(runtime.get("status") or "") == "recovering"
            ):
                runtime_service.formal_citation_recovery_status(
                    str(runtime["id"])
                )
                time.sleep(RUNTIME_POLL_SECONDS)
                continue
            if isinstance(runtime, dict) and str(runtime.get("status") or "") == "generating":
                reconciled_status = _reconcile_current_runtime(
                    runtime_service,
                    runtime,
                )
                time.sleep(
                    POLL_SECONDS
                    if reconciled_status == "ready"
                    else RUNTIME_POLL_SECONDS
                )
                continue

            learning_curriculum_preparation_runner.run_once(
                app,
                now_ms=now_ms(),
            )
            time.sleep(POLL_SECONDS)

    raise SafetyStop("one-course generation exhausted its tick budget")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and publish at most one primary_1 formal course."
    )
    parser.add_argument(
        "--confirm-one-paid-course",
        action="store_true",
        help="Required acknowledgement that one course may use paid Providers.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=3600,
        choices=range(300, 7201),
        metavar="300..7200",
    )
    parser.add_argument(
        "--confirm-known-runtime-retry",
        action="store_true",
        help=(
            "Allow one Runtime retry only after an audited, definitive "
            "non-billing rejection."
        ),
    )
    args = parser.parse_args()
    if not args.confirm_one_paid_course:
        parser.error("--confirm-one-paid-course is required")

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyStop("another one-course operator is already running") from exc
        return _run(
            args.timeout_seconds,
            allow_known_runtime_retry=args.confirm_known_runtime_retry,
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyStop as exc:
        _emit("stopped", reason=str(exc))
        raise SystemExit(1)
