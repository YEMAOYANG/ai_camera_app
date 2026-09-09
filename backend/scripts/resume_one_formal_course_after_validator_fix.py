from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from core.security import now_ms  # noqa: E402
from scripts.generate_one_formal_course import (  # noqa: E402
    EXPECTED_GRADE_CODE,
    LOCK_PATH,
    MAX_PUBLISHED_COURSES,
    SafetyStop,
    _eligible_child,
    _operator_app,
    _snapshot,
)
from services.learning_curriculum_preparation_contract import (  # noqa: E402
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import (  # noqa: E402
    learning_curriculum_preparation_runner,
)
from services.service_factory import (  # noqa: E402
    learning_curriculum_preparation_service,
    openmaic_full_runtime_service,
)


def _emit(event: str, **payload: object) -> None:
    print(
        json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True),
        flush=True,
    )


def _resume_failed_publication_plan(
    repository,
    *,
    plan_id: str,
    runtime_id: str,
    fingerprint: str,
) -> None:
    timestamp = now_ms()
    with repository.transaction() as conn:
        plan = conn.execute(
            "SELECT * FROM learning_curriculum_preparation_plans "
            "WHERE id = ? LIMIT 1 FOR UPDATE",
            (plan_id,),
        ).fetchone()
        if plan is None:
            raise SafetyStop("formal publication plan was not found")
        if str(plan.get("status") or "") == "running":
            return
        item_counts = conn.execute(
            """
            SELECT COUNT(*) AS total,
              SUM(status = 'course_ready') AS ready_count,
              SUM(status = 'pending') AS pending_count,
              SUM(status NOT IN ('course_ready', 'pending')) AS other_count
            FROM learning_catalog_build_items WHERE build_job_id = ?
            """,
            (plan["catalog_build_id"],),
        ).fetchone() or {}
        build = conn.execute(
            "SELECT status, error_code, completed_at FROM "
            "learning_catalog_build_jobs WHERE id = ? LIMIT 1 FOR UPDATE",
            (plan["catalog_build_id"],),
        ).fetchone()
        runtime = conn.execute(
            "SELECT status, upstream_classroom_id FROM "
            "learning_openmaic_runtime_classrooms WHERE id = ? "
            "LIMIT 1 FOR UPDATE",
            (runtime_id,),
        ).fetchone()
        evidence = conn.execute(
            """
            SELECT receipt.classroom_status, receipt.tts_status,
              receipt.asr_roundtrip_status, receipt.publication_status,
              audio.state AS audio_state
            FROM learning_curriculum_classroom_item_receipts AS receipt
            JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = receipt.build_item_id
             AND audio.runtime_classroom_id = receipt.runtime_classroom_id
            WHERE receipt.runtime_classroom_id = ? LIMIT 1 FOR UPDATE
            """,
            (runtime_id,),
        ).fetchone()
        provider_count = conn.execute(
            "SELECT COUNT(*) AS count FROM "
            "learning_openmaic_provider_readiness_jobs WHERE release_id = ?",
            (plan["catalog_release_id"],),
        ).fetchone() or {}
        probe_count = conn.execute(
            "SELECT COUNT(*) AS count FROM learning_openmaic_conversation_probes "
            "WHERE runtime_classroom_id = ?",
            (runtime_id,),
        ).fetchone() or {}
        if not (
            str(plan.get("status") or "") == "failed"
            and str(plan.get("stage") or "") == "completed"
            and str(plan.get("error_code") or "") == "preparation_validation_failed"
            and str(plan.get("target_fingerprint") or "") == fingerprint
            and plan.get("completed_at") is not None
            and all(
                plan.get(field) is None
                for field in (
                    "lease_token",
                    "lease_expires_at",
                    "heartbeat_at",
                    "next_run_at",
                    "hard_deadline_at",
                    "resume_stage",
                    "work_unit_kind",
                    "bound_catalog_item_id",
                    "bound_content_attempt_ordinal",
                    "bound_content_phase",
                )
            )
            and build is not None
            and str(build.get("status") or "") == "running"
            and build.get("error_code") is None
            and build.get("completed_at") is None
            and int(item_counts.get("total") or 0) == 30
            and int(item_counts.get("ready_count") or 0) == 1
            and int(item_counts.get("pending_count") or 0) == 29
            and int(item_counts.get("other_count") or 0) == 0
            and runtime is not None
            and str(runtime.get("status") or "") == "ready"
            and bool(str(runtime.get("upstream_classroom_id") or ""))
            and evidence is not None
            and all(
                str(evidence.get(field) or "") == "passed"
                for field in ("classroom_status", "tts_status", "asr_roundtrip_status")
            )
            and str(evidence.get("publication_status") or "") == "pending"
            and str(evidence.get("audio_state") or "") == "auto_validated"
            and int(provider_count.get("count") or 0) == 0
            and int(probe_count.get("count") or 0) == 0
        ):
            raise SafetyStop("formal publication plan no longer matches safe recovery")
        updated = conn.execute(
            """
            UPDATE learning_curriculum_preparation_plans
            SET status = 'running', stage = 'generating_content',
              next_run_at = ?, error_code = NULL, error_message_safe = NULL,
              completed_at = NULL, last_progress_at = ?, updated_at = ?
            WHERE id = ? AND status = 'failed' AND stage = 'completed'
              AND error_code = 'preparation_validation_failed'
              AND target_fingerprint = ? AND completed_at IS NOT NULL
              AND lease_token IS NULL AND lease_expires_at IS NULL
              AND heartbeat_at IS NULL AND next_run_at IS NULL
            """,
            (timestamp, timestamp, timestamp, plan_id, fingerprint),
        )
        if updated.rowcount != 1:
            raise SafetyStop("formal publication plan recovery conflicted")


def _run(
    *,
    runtime_id: str,
    request_id: str,
    upstream_job_id: str,
    expected_error_code: str,
) -> int:
    app = _operator_app()
    fingerprint = preparation_target_fingerprint(
        build_preparation_target(EXPECTED_GRADE_CODE)
    )
    with app.app_context():
        preparation_service = learning_curriculum_preparation_service()
        repository = preparation_service.repository
        runtime_service = openmaic_full_runtime_service()
        child = _eligible_child(repository)

        with runtime_service.repository.transaction() as conn:
            runtime = runtime_service.repository.get_runtime_classroom(
                conn, runtime_id=runtime_id, for_update=True
            )
            if runtime is None:
                raise SafetyStop("formal Runtime repair target was not found")
            if (
                str(runtime.get("request_id") or "") != request_id
                or str(runtime.get("upstream_job_id") or "") != upstream_job_id
                or int(runtime.get("provider_attempt_ordinal") or 0) != 3
                or runtime.get("retired_at") is not None
            ):
                raise SafetyStop("formal Runtime repair identity does not match")

            status = str(runtime.get("status") or "")
            if status == "failed":
                resumed = runtime_service.repository.resume_formal_candidate_after_validator_fix(
                        conn,
                        runtime_id=runtime_id,
                        expected_upstream_job_id=upstream_job_id,
                        expected_error_code=expected_error_code,
                    now=now_ms(),
                )
                if not resumed:
                    raise SafetyStop(
                        "formal Runtime no longer matches the validator rejection"
                    )
            elif status != "ready":
                raise SafetyStop(
                    "formal Runtime repair target is not failed or ready"
                )

        if status == "failed":
            payload = runtime_service.generation_status(upstream_job_id)
            reconciled = payload.get("runtime") if isinstance(payload, dict) else None
            if not isinstance(reconciled, dict) or str(
                reconciled.get("status") or ""
            ) != "ready":
                raise SafetyStop("same formal artifact did not become ready")
            _emit(
                "same_artifact_revalidated",
                runtimeId=runtime_id,
                upstreamJobId=upstream_job_id,
                upstreamClassroomId=reconciled.get("upstreamClassroomId"),
            )

        current = _snapshot(repository, child=child, fingerprint=fingerprint)
        current_plan = current.get("plan")
        if isinstance(current_plan, dict) and str(
            current_plan.get("status") or ""
        ) == "failed":
            _resume_failed_publication_plan(
                repository,
                plan_id=str(current_plan["id"]),
                runtime_id=runtime_id,
                fingerprint=fingerprint,
            )
            _emit("publication_plan_resumed", planId=current_plan["id"])

        for tick in range(1, 121):
            snapshot = _snapshot(repository, child=child, fingerprint=fingerprint)
            if int(snapshot["publishedCourses"]) == MAX_PUBLISHED_COURSES:
                _emit(
                    "completed",
                    gradeCode=EXPECTED_GRADE_CODE,
                    publishedCourses=1,
                    course=snapshot.get("course"),
                )
                return 0
            learning_curriculum_preparation_runner.run_once(app, now_ms=now_ms())
            time.sleep(0.25)

    raise SafetyStop("same-artifact publication did not complete")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Revalidate one exact OpenMAIC artifact after a local validator fix; "
            "this command never dispatches a Provider generation."
        )
    )
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--upstream-job-id", required=True)
    parser.add_argument("--expected-error-code", required=True)
    parser.add_argument("--confirm-zero-provider-revalidation", action="store_true")
    args = parser.parse_args()
    if not args.confirm_zero_provider_revalidation:
        parser.error("--confirm-zero-provider-revalidation is required")

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SafetyStop("another one-course operator is already running") from exc
        return _run(
            runtime_id=args.runtime_id,
            request_id=args.request_id,
            upstream_job_id=args.upstream_job_id,
            expected_error_code=args.expected_error_code,
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SafetyStop as exc:
        _emit("stopped", reason=str(exc))
        raise SystemExit(1)
