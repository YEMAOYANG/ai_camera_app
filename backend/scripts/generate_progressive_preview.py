"""Operate only the six approved grade-six introductory courseware slots.

Plan/status are read-only. Every mutation uses one explicit library request and
the existing scoped preparation, budget, audio, review and publication gates.
This operator never starts ordinary workers or retries a failed candidate.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from content.learning_budget_policy import LearningBudgetPolicy, digest
from core.security import now_ms
from scripts.generate_one_library_course import (
    LOCK_PATH, assert_search_budget_ready, emit, inventory, operator_app,
    review_identity, review_ready, write_review_request,
)
from services.course_library_service import CourseLibraryService
from services.learning_curriculum_preparation_contract import (
    build_progressive_preparation_target, preparation_target_fingerprint,
)
from services.learning_curriculum_preparation_runner import learning_curriculum_preparation_runner
from services.service_factory import (
    learning_curriculum_preparation_service, openmaic_full_runtime_service,
)


def preview_identities(grade):
    """Pure identities from the complete grade target, never a subset build."""
    target = build_progressive_preparation_target(grade)
    fingerprint = preparation_target_fingerprint(target)
    request = "grade-build:" + fingerprint
    build_id = "catalog_build_" + hashlib.sha256(request.encode()).hexdigest()[:24]
    result = []
    for subject in ("chinese", "math", "english"):
        subject_slots = [slot for slot in target["courseTargets"] if slot["subject"] == subject]
        first_lesson = subject_slots[0]["lessonId"]
        for ordinal in (1, 2):
            matches = [slot for slot in subject_slots
                       if slot["lessonId"] == first_lesson and slot["variantOrdinal"] == ordinal]
            if len(matches) != 1:
                raise ValueError("introductory assessment slot is not unique")
            slot = matches[0]
            item_id = "catalog_build_item_" + hashlib.sha256(
                f"{build_id}:{grade}:{subject}:{slot['skillId']}:{ordinal}".encode()).hexdigest()[:24]
            scope = {"purpose": "production", "gradeCode": grade, "subject": subject,
                     "courseId": "catalog-item:" + item_id,
                     "courseVersion": digest({"curriculumVersion": target["curriculumVersion"],
                         "boundaryVersion": slot["boundaryVersion"], "targetSpec": target}),
                     "productionJobId": item_id, "userId": None, "sessionId": None,
                     "approvalReference": request}
            result.append({"targetFingerprint": fingerprint, "buildId": build_id,
                           "buildItemId": item_id, "scope": scope, "slot": deepcopy(slot)})
    return result


def assert_preview_policy(path, identities):
    if not path:
        raise RuntimeError("an existing --budget-policy with the six exact production scopes is required")
    policy = LearningBudgetPolicy.load(path)
    window = policy.raw.get("productionAuthorizationWindow") or {}
    scopes = window.get("scopes") or []
    expected = {digest(identity["scope"]) for identity in identities}
    if (policy.raw.get("enabled") is not True or policy.aggregate_limits_enabled
            or policy.raw.get("authorizationWindow") is not None
            or policy.renew_teaching_authorizations is not True
            or len(scopes) != 6 or len(expected) != 6
            or {digest(scope) for scope in scopes} != expected):
        raise RuntimeError("policy must preserve durable teaching and authorize precisely these six production slots")
    if not window.get("startsAt", now_ms() + 1) <= now_ms() < window.get("expiresAt", 0):
        raise RuntimeError("the six-slot production authorization is not active")
    return policy


def preview_inventory(library, identity):
    state = inventory(library, identity)
    key = digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]})
    with library.database.transaction() as conn:
        item = state.get("item") or {}
        job = conn.execute(
            "SELECT id,request_id,status,error_code,error_message_safe,updated_at "
            "FROM learning_course_generation_jobs WHERE request_id=?",
            (item.get("generation_request_id") or "",)).fetchone()
        from scripts.progressive_preview_correction import accepted_correction_job
        correction_job = accepted_correction_job(conn, identity, item)
        if correction_job is not None:
            job = correction_job
        from services.progressive_math2_revision import select_revision_runtimes
        state["runtimes"], state["historicalRuntimes"] = select_revision_runtimes(conn, identity, state["runtimes"])
        counts = conn.execute("SELECT state,COUNT(*) AS count FROM learning_budget_reservations "
                              "WHERE authorization_id=? GROUP BY state", (key,)).fetchall()
        touched = conn.execute(
            "SELECT item.id FROM learning_catalog_build_items item WHERE item.build_job_id=? "
            "AND item.id<>? AND (item.attempt_count>0 OR item.status<>'pending' OR EXISTS "
            "(SELECT 1 FROM learning_course_generation_jobs j WHERE j.request_id=item.generation_request_id) "
            "OR EXISTS (SELECT 1 FROM learning_course_provider_dispatches d WHERE d.build_item_id=item.id) "
            "OR EXISTS (SELECT 1 FROM learning_openmaic_runtime_classrooms r WHERE r.candidate_build_item_id=item.id))",
            (identity["buildId"], identity["buildItemId"])).fetchall()
    state.update(generationJob=dict(job) if job else None,
                 budgetReservations={row["state"]: int(row["count"]) for row in counts},
                 touchedSiblingIds=[row["id"] for row in touched])
    return state


def exact_review_ready(state):
    runtimes = state.get("runtimes") or []
    return len(runtimes) == 1 and review_ready(state, selected_runtime=runtimes[0])


def assert_preview_scope(library, identity, identities, state, *, require_request=True, allow_failed_content=False,
                         terminal_audio_runtime_id=None):
    if library.fingerprint != identity["targetFingerprint"]:
        raise RuntimeError("library target differs from the frozen complete grade target")
    slot = identity["slot"]
    expected = [{"subject": slot["subject"], "skill_id": slot["skillId"],
                 "variant_ordinal": slot["variantOrdinal"]}]
    approved = {(i["slot"]["subject"], i["slot"]["skillId"], i["slot"]["variantOrdinal"])
                for i in identities}
    if require_request and state["requests"] != expected:
        raise RuntimeError("enabled supply request is not the exact selected single slot; prepare it first")
    if len(state["requests"]) > 1 or any(
            (r["subject"], r["skill_id"], r["variant_ordinal"]) not in approved for r in state["requests"]):
        raise RuntimeError("another supply scope is enabled; no generation allowed")
    if (state.get("owner") or {}).get("status") in {"failed", "superseded"}:
        raise RuntimeError("the existing owner requires diagnosis; no automatic retry")
    item, job = state.get("item") or {}, state.get("generationJob") or {}
    if not allow_failed_content and (item.get("status") == "failed" or item.get("content_phase") == "failed" or job.get("status") == "failed"):
        raise RuntimeError("saved content generation failed: " + str(item.get("error_code") or job.get("error_code")))
    if len(state["runtimes"]) > 1 or any(
            r["status"] in {"failed", "recovering"} or r.get("retired_at") for r in state["runtimes"]):
        raise RuntimeError("Runtime failure or duplicate history requires diagnosis; no replacement allowed")
    if terminal_audio_runtime_id is not None:
        # Only saved-stage reconciliation/publication supply this argument.
        # Ordinary run-to-review never retries a failed/ambiguous Native job.
        key = digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]})
        with library.database.transaction() as conn:
            pending = conn.execute("SELECT state FROM learning_budget_reservations WHERE authorization_id=? "
                "AND state IN ('reserved','dispatched','unknown')", (key,)).fetchall()
            if any(row["state"] in {"reserved", "dispatched"} for row in pending):
                raise RuntimeError("an active Provider call prevents saved-stage continuation")
            if pending:
                from services.learning_http402_transport_terminal import ITEM as HTTP402_ITEM, assert_selected_http402_terminal
                if identity['buildItemId'] == HTTP402_ITEM:
                    assert_selected_http402_terminal(conn, identity=identity, runtime_id=terminal_audio_runtime_id)
                else:
                    from services.learning_audio_transport_terminal import assert_selected_audio_terminal
                    assert_selected_audio_terminal(conn, identity=identity, runtime_id=terminal_audio_runtime_id)
    elif state.get("budgetReservations", {}).get("unknown", 0):
        raise RuntimeError("an unresolved Provider outcome requires diagnosis before continuation")
    by_id = {i["buildItemId"]: i for i in identities}
    for sibling_id in state["touchedSiblingIds"]:
        if sibling_id not in by_id:
            raise RuntimeError("a course outside the six approved slots has already been touched")
        sibling = preview_inventory(library, by_id[sibling_id])
        if (not exact_review_ready(sibling)
                or (sibling["receipt"] or {}).get("publication_status") != "published"
                or any(r.get("retired_at") for r in sibling["runtimes"])):
            raise RuntimeError("finish the previously touched slot before starting another: " + sibling_id)
        review_identity(sibling, by_id[sibling_id], selected_runtime=sibling["runtimes"][0])


def status_payload(state, identity):
    item = state.get("item") or {}
    return {"buildItemId": identity["buildItemId"], "lessonId": identity["slot"]["lessonId"],
            "slot": identity["slot"]["variantOrdinal"], "contentStatus": item.get("status"),
            "contentPhase": item.get("content_phase"), "generationJob": state.get("generationJob"),
            "budgetReservations": state.get("budgetReservations"), "reviewReady": exact_review_ready(state),
            "runtimes": [{k: r.get(k) for k in ("id", "status", "quality_status", "upstream_job_id",
                "upstream_classroom_id", "error_code")} for r in state.get("runtimes", [])],
            "receipt": state.get("receipt")}


def save_failure(args, identity, state, error):
    path = Path(args.failure_output or ROOT.parent / "output" / "progressive-preview" /
                f"{args.lesson_id}-{args.slot}-stopped-{now_ms()}.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"event": "stopped", "at": now_ms(), "reason": str(error), "identity": identity,
            "state": status_payload(state, identity) if state else None}
    with path.open("x", encoding="utf-8") as output:
        path.chmod(0o600)
        json.dump(data, output, ensure_ascii=False, indent=2, default=str)
        output.write("\n")
    return str(path)


def run(args):
    identities = preview_identities(args.grade)
    if args.command == "plan":
        emit("plan", gradeCode=args.grade, identities=identities, providerCalls=0)
        return 0
    selected = [i for i in identities if i["slot"]["subject"] == args.subject
                and i["slot"]["lessonId"] == args.lesson_id and i["slot"]["variantOrdinal"] == args.slot]
    if len(selected) != 1:
        raise RuntimeError("only each grade-six subject's first lesson and slots 1/2 are approved")
    identity, state = selected[0], None
    app = operator_app(args, publishing=args.command == "publish")
    # This limit counts the entire build. Single active request still permits
    # only this slot; previously published siblings must not block slot two.
    app.config["LEARNING_CURRICULUM_PREPARATION_PROGRESSIVE_PUBLICATION_LIMIT"] = 6
    with app.app_context():
        preparation = learning_curriculum_preparation_service()
        library = CourseLibraryService(app.config["DATABASE_URL"], grade_code=args.grade,
                                       preparation_repository=preparation.repository)
        try:
            state = preview_inventory(library, identity)
            if args.command == "status":
                emit("status", **status_payload(state, identity))
                return 0
            if not args.confirm_workers_stopped:
                raise RuntimeError("--confirm-workers-stopped is required; this operator never starts ordinary workers")
            assert_preview_policy(args.budget_policy, identities)
            if args.command == "reconcile-saved-stage":
                from services.learning_saved_stage_reconciliation import reconcile_saved_stage
                # The ordinary scope check rejects a failed Runtime. Recovery
                # validates that same Runtime against its formal completion below.
                assert_preview_scope(library, identity, identities, {**state, "runtimes": []},
                                     terminal_audio_runtime_id=args.runtime_id)
                if (len(state["runtimes"]) != 1 or state["runtimes"][0]["id"] != args.runtime_id
                        or any(state.get("budgetReservations", {}).get(kind, 0)
                               for kind in ("reserved", "dispatched"))):
                    raise RuntimeError("saved-stage recovery requires the exact single Runtime and no active calls")
                # assert_preview_scope verified each touched sibling's exact
                # publication receipt; the existing helper otherwise assumes a
                # one-course build. No unfinished/out-of-scope sibling is ignored.
                scoped_state = {**state, "otherTouchedItems": 0}
                result = reconcile_saved_stage(runtime_service=openmaic_full_runtime_service(),
                    preparation_repository=preparation.repository, identity=identity, state=scoped_state,
                    runtime_id=args.runtime_id, completion_path=args.completion, now=now_ms())
                if (result.get("result") or {}).get("runtime", {}).get("status") != "ready":
                    raise RuntimeError("same saved classroom did not pass normal Runtime validation; saved outcome retained")
                state = preview_inventory(library, identity)
                assert_preview_scope(library, identity, identities, state,
                                     terminal_audio_runtime_id=args.runtime_id)
                if (len(state["runtimes"]) != 1 or state["runtimes"][0]["id"] != args.runtime_id
                        or state["runtimes"][0]["status"] != "ready"):
                    raise RuntimeError("the reconciled Runtime changed before visual review export")
                output = args.review_output or ROOT.parent / "output" / "progressive-preview" / f"{args.lesson_id}-{args.slot}-review.json"
                path = write_review_request(output, state, identity, selected_runtime=state["runtimes"][0])
                emit("saved_stage_reconciled", reviewRequest=path,
                     reviewRequestSha256=hashlib.sha256(Path(path).read_bytes()).hexdigest())
                return 0
            if args.command in {"plan-contract-fix", "apply-contract-fix"}:
                from services.progressive_contract_fix import plan_contract_fix, apply_contract_fix
                assert_preview_scope(library, identity, identities, {**state, "runtimes": []})
                runtime_service = openmaic_full_runtime_service()
                if args.command == "plan-contract-fix":
                    result = plan_contract_fix(library, identity, runtime_service)
                else:
                    result = apply_contract_fix(args, library, identity, runtime_service, preparation.repository)
                emit("contract_fix_plan" if args.command == "plan-contract-fix" else "contract_fix_applied", **result)
                return 0
            if args.command == "correct-rejected":
                from scripts.progressive_preview_correction import correct_rejected
                from services.service_factory import learning_curriculum_preparation_checkpoint_adapter
                audited_preparations = learning_curriculum_preparation_checkpoint_adapter().repository
                result = correct_rejected(args, library, identity, identities, state, audited_preparations)
                state = preview_inventory(library, identity)
                emit("correction_completed", correction=result, **status_payload(state, identity))
                return 0
            terminal_runtime_id = (state["runtimes"][0]["id"]
                if args.command == "publish" and len(state["runtimes"]) == 1 else None)
            assert_preview_scope(library, identity, identities, state, require_request=args.command != "prepare",
                                 terminal_audio_runtime_id=terminal_runtime_id)
            if args.command == "prepare":
                result = library.request_slot(subject=args.subject, skill_id=args.lesson_id, variant_ordinal=args.slot)
                state = preview_inventory(library, identity)
                assert_preview_scope(library, identity, identities, state, terminal_audio_runtime_id=terminal_runtime_id)
                emit("prepared", **result, buildItemId=identity["buildItemId"])
                return 0
            if args.command == "publish":
                from services.progressive_math2_revision import assert_publishable_revision
                assert_publishable_revision((state.get("item") or {}).get("course_id"))
                if not exact_review_ready(state):
                    raise RuntimeError("the exact classroom, TTS and ASR receipts have not passed")
                confirmation = json.loads(Path(args.visual_confirmation).read_text())
                if confirmation != {**review_identity(state, identity, selected_runtime=state["runtimes"][0]),
                                    "status": "approved"}:
                    raise RuntimeError("visual confirmation does not match this exact final artifact")
            else:
                from services.service_factory import _checkpoint_question_phase_profile
                profile = _checkpoint_question_phase_profile()
                if (not profile or profile.get("name") != "openmaic_runtime" or profile.get("model") != "courseware-v2"
                        or str(profile.get("baseUrl") or "").rstrip("/")
                        != str(app.config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or "").rstrip("/")):
                    raise RuntimeError("configured private OpenMAIC courseware authority is required")
            runtime_service = openmaic_full_runtime_service()
            if args.command != "publish" and not runtime_service.formal_provider_circuit_status()["dispatchAllowed"]:
                raise RuntimeError("existing Provider circuit is not ready; no probe was dispatched")
            deadline = time.monotonic() + args.timeout_seconds
            last_state, last_progress_at, last_runner = None, 0.0, None
            while time.monotonic() < deadline:
                assert_preview_policy(args.budget_policy, identities)
                state = preview_inventory(library, identity)
                assert_preview_scope(library, identity, identities, state, terminal_audio_runtime_id=terminal_runtime_id)
                if (state["receipt"] or {}).get("publication_status") == "published":
                    if not exact_review_ready(state):
                        raise RuntimeError("published receipt no longer matches a fully reviewed classroom")
                    emit("published", **status_payload(state, identity))
                    return 0
                if args.command == "run-to-review" and exact_review_ready(state):
                    output = args.review_output or ROOT.parent / "output" / "progressive-preview" / f"{args.lesson_id}-{args.slot}-review.json"
                    path = write_review_request(output, state, identity, selected_runtime=state["runtimes"][0])
                    emit("awaiting_visual_observation", reviewRequest=path, **status_payload(state, identity))
                    return 0
                if args.command != "publish":
                    assert_search_budget_ready(args, library, identity, runtime_service, state)
                    for runtime in state["runtimes"]:
                        if runtime["status"] == "generating" and runtime.get("upstream_job_id"):
                            runtime_service.generation_status(runtime["upstream_job_id"])
                            state = preview_inventory(library, identity)
                            assert_preview_scope(library, identity, identities, state)
                public_state = status_payload(state, identity)
                state_key = digest(public_state)
                if state_key != last_state or time.monotonic() - last_progress_at >= 30:
                    emit("progress", **public_state)
                    last_state, last_progress_at = state_key, time.monotonic()
                result = learning_curriculum_preparation_runner.run_scoped_once(app, now_ms=now_ms(), target=library.target)
                state = preview_inventory(library, identity)
                assert_preview_scope(library, identity, identities, state, terminal_audio_runtime_id=terminal_runtime_id)
                runner_key = (result.get("status"), result.get("stage")) if isinstance(result, dict) else str(result)
                if args.once or isinstance(result, dict) and result.get("claimed") or runner_key != last_runner:
                    emit("step_completed", runner=result, **status_payload(state, identity))
                    last_runner = runner_key
                if args.once:
                    return 0
                time.sleep(1.25)
            raise RuntimeError("operator timeout; existing outputs retained, no automatic retry")
        except Exception as exc:
            try:
                state = preview_inventory(library, identity)
                saved = save_failure(args, identity, state, exc)
                emit("diagnostic_saved", path=saved)
            except Exception as diagnostic_error:
                emit("diagnostic_save_failed", reason=str(diagnostic_error))
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "prepare", "status", "run-to-review", "publish", "correct-rejected", "plan-contract-fix", "apply-contract-fix", "reconcile-saved-stage"))
    parser.add_argument("--grade", choices=("primary_6",), default="primary_6")
    parser.add_argument("--subject", choices=("chinese", "math", "english"))
    parser.add_argument("--lesson-id")
    parser.add_argument("--slot", type=int, choices=(1, 2))
    parser.add_argument("--budget-policy")
    parser.add_argument("--review-output")
    parser.add_argument("--failure-output")
    parser.add_argument("--visual-confirmation")
    parser.add_argument("--rejection-audit")
    parser.add_argument("--correction-round", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--expected-contract-fix-sha")
    parser.add_argument("--runtime-id")
    parser.add_argument("--completion")
    parser.add_argument("--confirm-workers-stopped", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    args = parser.parse_args()
    if args.command != "plan" and (not args.subject or not args.lesson_id or args.slot is None):
        parser.error("--subject, --lesson-id and --slot are required")
    if args.command == "publish" and not args.visual_confirmation:
        parser.error("publish requires --visual-confirmation")
    if args.command == "correct-rejected" and not args.rejection_audit:
        parser.error("correct-rejected requires --rejection-audit")
    if args.command == "apply-contract-fix" and not args.expected_contract_fix_sha:
        parser.error("apply-contract-fix requires --expected-contract-fix-sha")
    if args.command == "reconcile-saved-stage" and (not args.runtime_id or not args.completion):
        parser.error("reconcile-saved-stage requires --runtime-id and --completion")
    if args.once and args.command != "run-to-review":
        parser.error("--once is only valid with run-to-review")
    if not 60 <= args.timeout_seconds <= 21600:
        parser.error("timeout must be 60..21600 seconds")
    try:
        if args.command in {"plan", "status"}:
            return run(args)
        with LOCK_PATH.open("a+") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError("another formal-course operator owns the lock") from exc
            return run(args)
    except Exception as exc:
        emit("stopped", reason=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
