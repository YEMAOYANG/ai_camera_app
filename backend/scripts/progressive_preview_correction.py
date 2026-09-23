"""One explicitly audited correction; preserve the original rejected jobs."""
from __future__ import annotations

from copy import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from content.learning_budget_policy import digest
from core.security import now_ms
from services.progressive_course_generation import (
    INPUT_SCHEMA, VERIFY_SCHEMA, VALIDATION_SCHEMA, validate_progressive_course_for_release,
)

ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = ROOT / "output" / "progressive-preview" / "corrections"
NATIVE_ROOT = ROOT / "openmaic-runtime" / ".runtime" / "OpenMAIC" / "data" / "formal-courseware-provider-responses"
STARTED = "progressive_correction_started"
SUCCEEDED = "progressive_correction_succeeded"


def _events(conn, identity, kind, *, correction_request_id=None):
    request_filter = " AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.correctionRequestId'))=?" if correction_request_id else ""
    rows = conn.execute("SELECT e.payload_json,p.target_fingerprint FROM learning_curriculum_preparation_events e "
        "JOIN learning_curriculum_preparation_plans p ON p.id=e.plan_id "
        "WHERE p.catalog_build_id=? AND e.event_type=? "
        "AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.buildItemId'))=?" + request_filter + " ORDER BY e.created_at,e.id",
        (identity["buildId"], kind, identity["buildItemId"], *((correction_request_id,) if correction_request_id else ()))).fetchall()
    if len(rows) > 1 or any(r["target_fingerprint"] != identity["targetFingerprint"] for r in rows):
        raise RuntimeError("conflicting progressive correction events")
    return json.loads(rows[0]["payload_json"]) if rows else None


def _read_audit(event, identity):
    sha = event.get("auditShaId", "")
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise RuntimeError("invalid correction audit identity")
    audit = json.loads((AUDIT_ROOT / (sha + ".json")).read_text())
    round_number = audit.get("correctionRound", 1)
    base_request = audit.get("originalJob", {}).get("request_id", "")
    source = audit.get("sourceRejectedJob", audit.get("originalJob", {}))
    expected_source = base_request + (f".correction{round_number - 1}" if round_number > 1 else "") if type(round_number) is int else None
    if (digest(audit) != sha or audit.get("identity") != identity
            or event.get("correctionRequestId") != audit.get("correctionRequestId")
            or type(round_number) is not int or round_number not in {1, 2, 3}
            or source.get("request_id") != expected_source or source.get("status") != "failed"
            or audit.get("correctionRequestId") != base_request + f".correction{round_number}"):
        raise RuntimeError("correction audit changed")
    return audit


def accepted_correction_job(conn, identity, item):
    from services.progressive_preruntime_replacement import accepted_preruntime_replacement_job
    replacement = accepted_preruntime_replacement_job(conn, identity, item)
    if replacement is not None:
        return replacement
    from services.progressive_math2_revision import accepted_math2_revision_job
    math2_revision = accepted_math2_revision_job(conn, identity, item)
    if math2_revision is not None:
        return math2_revision
    from scripts.progressive_preview_math_editorial import accepted_math_editorial_job
    math_editorial = accepted_math_editorial_job(conn, identity, item)
    if math_editorial is not None:
        return math_editorial
    try:
        from scripts.progressive_preview_editorial import accepted_editorial_candidate
    except ImportError:
        editorial = None
    else:
        editorial = accepted_editorial_candidate(conn, identity)
    if editorial and item.get("course_id") == editorial["course"]["id"]:
        if (item.get("course_version") != editorial["course"]["version"]
                or item.get("status") != "course_ready" or item.get("content_receipt_hash") != digest(editorial["receipt"])):
            raise RuntimeError("editorial candidate is not bound to the current exact item")
        return editorial["job"]
    event = _events(conn, identity, SUCCEEDED)
    if event is None:
        return None
    audit = _read_audit(event, identity)
    started = _events(conn, identity, STARTED, correction_request_id=event["correctionRequestId"])
    if (not started or started.get("auditShaId") != event["auditShaId"]
            or started.get("correctionRequestId") != event["correctionRequestId"]
            or item.get("status") != "course_ready"
            or item.get("generation_request_id") != audit["originalJob"]["request_id"]
            or item.get("course_id") != event.get("courseId")
            or item.get("course_version") != event.get("courseVersionId")
            or item.get("content_receipt_hash") != event.get("contentReceiptShaId")):
        raise RuntimeError("accepted correction is not bound to the current exact item")
    original = conn.execute("SELECT status,request_id FROM learning_course_generation_jobs WHERE id=?",
                            (audit["originalJob"]["id"],)).fetchone()
    source_snapshot = audit.get("sourceRejectedJob", audit["originalJob"])
    source = conn.execute("SELECT status,request_id FROM learning_course_generation_jobs WHERE id=?",
                          (source_snapshot["id"],)).fetchone()
    job = conn.execute("SELECT id,request_id,status,error_code,error_message_safe,updated_at "
                       "FROM learning_course_generation_jobs WHERE id=?", (event.get("generationJobId"),)).fetchone()
    if (not original or original["status"] != "failed" or original["request_id"] != audit["originalJob"]["request_id"]
            or not source or source["status"] != "failed" or source["request_id"] != source_snapshot["request_id"]
            or not job or job["request_id"] != event["correctionRequestId"]
            or job["status"] not in {"validated", "partially_validated"}):
        raise RuntimeError("accepted correction generation history changed")
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
                          (item["course_id"], item["course_version"])).fetchone()
    receipt = validate_progressive_course_for_release(conn, course=course,
                                                      expected_lesson_id=identity["slot"]["lessonId"])
    if (course["generation_request_id"] != event["correctionRequestId"]
            or digest(receipt) != event["contentReceiptShaId"]):
        raise RuntimeError("accepted correction no longer matches its actual candidate receipt")
    return job


def _returned_rejection(path, item, job):
    diagnostic = json.loads(Path(path).read_text())
    if (diagnostic.get("buildItemId") != item["id"] or diagnostic.get("requestId") != job["request_id"]
            or len(diagnostic.get("archives", [])) != 2):
        raise RuntimeError("rejection audit does not identify the original two returned calls")
    records = {}
    evidence = []
    for archive in diagnostic["archives"]:
        file = Path(archive["path"]).resolve()
        if not file.is_relative_to(NATIVE_ROOT.resolve()):
            raise RuntimeError("original reply is outside the managed Native archive")
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != archive["sha256"]:
            raise RuntimeError("original Native reply changed")
        data = json.loads(raw)
        phase = data.get("phase")
        expected_request = job["request_id"] + (":verify" if phase == "progressive_verification" else "")
        if (phase not in {"progressive_generation", "progressive_verification"} or phase in records
                or data.get("requestId") != expected_request or not data.get("responseId")
                or not isinstance(data.get("usage"), dict)):
            raise RuntimeError("Native reply has no exact returned-call identity")
        records[phase] = json.loads(data["content"])
        evidence.append({"path": str(file), "sha256": archive["sha256"],
                         "inputSha256": data["inputSha256"], "requestId": data["requestId"], "phase": phase})
    verdict = records["progressive_verification"]
    verdict = verdict.get("verification", verdict)
    if (verdict.get("passed") is not False
            or not isinstance(verdict.get("issues"), list) or not verdict["issues"]
            or any(not isinstance(issue, str) for issue in verdict["issues"])):
        raise RuntimeError("correction requires an explicit independent rejection, never an unknown outcome")
    return evidence, verdict


def correct_rejected(args, library, identity, identities, state, preparations):
    from scripts.generate_progressive_preview import assert_preview_scope, assert_preview_policy, emit
    from scripts.generate_one_library_course import assert_search_budget_ready
    from services.service_factory import (
        _catalog_paid_budget_environment, dynamic_learning_course_generation_service, openmaic_full_runtime_service,
    )
    assert_preview_scope(library, identity, identities, state, allow_failed_content=True)
    if preparations.content_proof_auditor is None:
        raise RuntimeError("correction requires the normal content proof auditor before any dispatch")
    round_number = args.correction_round
    if any(state.get("budgetReservations", {}).get(key, 0) for key in ("unknown", "reserved", "dispatched")):
        raise RuntimeError("the original scope has unresolved Provider reservations")
    if state.get("budgetReservations", {}).get("settled", 0) < 2 * round_number:
        raise RuntimeError("the two original returned calls have not settled")
    if state["runtimes"]:
        raise RuntimeError("content correction cannot replace an existing Runtime")
    with library.database.transaction() as conn:
        if accepted_correction_job(conn, identity, state["item"]) is not None:
            return {"status": "already_applied"}
        item = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE",
                            (identity["buildItemId"],)).fetchone()
        job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=? FOR UPDATE",
                           (item["generation_request_id"],)).fetchone()
        correction_request_id = job["request_id"] + f".correction{round_number}"
        source_request_id = job["request_id"] + (f".correction{round_number - 1}" if round_number > 1 else "")
        source_job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=? FOR UPDATE",
                                  (source_request_id,)).fetchone()
        if not source_job or source_job["status"] != "failed":
            raise RuntimeError("this round requires the preceding round's explicitly rejected job")
        if round_number > 1:
            previous = _events(conn, identity, STARTED, correction_request_id=source_request_id)
            if not previous or _read_audit(previous, identity)["originalJob"] != dict(job):
                raise RuntimeError("the preceding correction has no matching immutable authorization audit")
        candidates = conn.execute("SELECT COUNT(*) AS count FROM learning_course_generation_candidates WHERE job_id=?",
                                  (job["id"],)).fetchone()
        source_candidates = conn.execute("SELECT COUNT(*) AS count FROM learning_course_generation_candidates WHERE job_id=?",
                                         (source_job["id"],)).fetchone()
        if (item["status"] != "failed" or item["content_phase"] != "failed" or job["status"] != "failed"
                or candidates["count"] or source_candidates["count"] or item.get("course_id") or item.get("course_version")):
            raise RuntimeError("only an original rejected content item without candidates may be corrected")
        archives, verdict = _returned_rejection(args.rejection_audit, item, source_job)
        started = _events(conn, identity, STARTED, correction_request_id=correction_request_id)
        if started:
            audit = _read_audit(started, identity)
            if (audit["originalItem"] != dict(item) or audit["originalJob"] != dict(job) or audit["archives"] != archives
                    or audit.get("sourceRejectedJob", audit["originalJob"]) != dict(source_job)):
                raise RuntimeError("the original rejection history changed after correction authorization")
        else:
            audit = {"schemaVersion": "mira.progressive-correction-audit.v1", "identity": identity,
                     "originalItem": dict(item), "originalJob": dict(job), "archives": archives,
                     "independentReview": verdict, "sourceRejectedJob": dict(source_job),
                     "correctionRound": round_number, "correctionRequestId": correction_request_id,
                     "originalCoordinator": state["owner"],
                     "coordinatorResume": "After validated correction and no unresolved calls, release only this idle content coordinator for a fresh normal stage deadline. Preserve original paid jobs and ledger."}
            sha = digest(audit)
            AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
            path = AUDIT_ROOT / (sha + ".json")
            if path.exists():
                if json.loads(path.read_text()) != audit:
                    raise RuntimeError("correction audit path already contains different evidence")
            else:
                with path.open("x") as output:
                    path.chmod(0o600)
                    json.dump(audit, output, ensure_ascii=False, sort_keys=True, indent=2)
                    output.write("\n")
            started = {"buildItemId": item["id"], "auditShaId": sha,
                       "originalGenerationJobId": job["id"], "sourceRejectedJobId": source_job["id"],
                       "correctionRoundCount": round_number, "correctionRequestId": audit["correctionRequestId"]}
            preparations.append_event(conn, plan_id=state["owner"]["id"], event_type=STARTED,
                                      stage="generating_content", payload=started, now=now_ms())
        existing = conn.execute("SELECT status FROM learning_course_generation_jobs WHERE request_id=?",
                                (audit["correctionRequestId"],)).fetchone()
        if existing and existing["status"] not in {"validated", "partially_validated"}:
            raise RuntimeError("the correction was already dispatched; inspect its saved result, never resend")
    emit("correction_authorized", auditSha256=started["auditShaId"], requestId=audit["correctionRequestId"])
    runtime_service = openmaic_full_runtime_service()
    assert_search_budget_ready(args, library, identity, runtime_service, state)
    if not runtime_service.formal_provider_circuit_status()["dispatchAllowed"]:
        raise RuntimeError("existing Provider circuit is not ready")
    generator = copy(dynamic_learning_course_generation_service())
    adapter = copy(generator.progressive_adapter)
    command = SimpleNamespace(build_item_id=identity["buildItemId"], grade_code=args.grade,
                              subject=args.subject, boundary={"skillId": args.lesson_id})

    def exact_environment(payload):
        assert_preview_policy(args.budget_policy, identities)
        expected = audit["correctionRequestId"] + (":verify" if payload.get("schemaVersion") == VERIFY_SCHEMA else "")
        if (payload.get("schemaVersion") not in {INPUT_SCHEMA, VERIFY_SCHEMA} or payload.get("requestId") != expected
                or payload.get("brief", {}).get("binding", {}).get("lessonId") != args.lesson_id):
            raise RuntimeError("the correction adapter cannot dispatch a different request or lesson")
        return _catalog_paid_budget_environment(command)

    adapter.execution_environment = exact_environment
    original_call = adapter._call

    def with_correction_context(payload):
        if payload.get("schemaVersion") == INPUT_SCHEMA:
            payload = {**payload, "correctionRequirements": {"auditShaId": started["auditShaId"],
                "issues": [*audit["independentReview"]["issues"],
                    "Host validation also rejected the original candidate: "
                    + str(audit.get("sourceRejectedJob", audit["originalJob"]).get("error_code") or "")
                    + ": " + str(audit.get("sourceRejectedJob", audit["originalJob"]).get("error_message_safe") or ""),
                    "content.progressiveLesson must equal the complete brief.binding object, never a lessonId string.",
                    "Copy all request identifiers exactly from the current request and expected output skeleton; never reuse or change a previous identifier."]}}
        return original_call(payload)

    adapter._call = with_correction_context
    generator.progressive_adapter = adapter
    result = generator.generate({"requestId": audit["correctionRequestId"],
        "curriculumVersion": library.target["curriculumVersion"], "lessonId": args.lesson_id,
        "gradeCode": args.grade, "subject": args.subject, "difficultyCode": "basic"}, enqueue_classroom=False)
    if result.payload.get("ok") is not True:
        emit("correction_rejected", result=result.payload, auditSha256=started["auditShaId"])
        raise RuntimeError("the correction did not pass; its separate job and paid replies are preserved")
    course_identity = result.payload["course"]
    with library.database.transaction() as conn:
        current = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE", (identity["buildItemId"],)).fetchone()
        original = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=? FOR UPDATE", (audit["originalJob"]["id"],)).fetchone()
        source_snapshot = audit.get("sourceRejectedJob", audit["originalJob"])
        source = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=? FOR UPDATE", (source_snapshot["id"],)).fetchone()
        if dict(current) != audit["originalItem"] or dict(original) != audit["originalJob"] or dict(source) != source_snapshot:
            raise RuntimeError("the original failure changed; saved correction retained without changing the item")
        course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=? FOR UPDATE",
                              (course_identity["id"], course_identity["version"])).fetchone()
        receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=args.lesson_id)
        if course["generation_request_id"] != audit["correctionRequestId"]:
            raise RuntimeError("the accepted course is not this correction")
        updated = conn.execute("UPDATE learning_catalog_build_items SET status='course_ready', content_phase='course_ready', "
            "course_id=?,course_version=?,content_gate_status='passed',content_gate_passed_at=?, "
            "content_validation_contract_version=?,content_receipt_hash=?,error_code=NULL,error_message_safe=NULL,updated_at=? "
            "WHERE id=? AND status='failed' AND content_phase='failed' AND generation_request_id=? AND updated_at=?",
            (course["id"], course["version"], now_ms(), VALIDATION_SCHEMA, digest(receipt), now_ms(),
             identity["buildItemId"], audit["originalJob"]["request_id"], current["updated_at"]))
        if updated.rowcount != 1:
            raise RuntimeError("failed item changed while accepting the correction")
        success = {**started, "generationJobId": result.payload["jobId"], "courseId": course["id"],
                   "courseVersionId": course["version"], "contentReceiptShaId": digest(receipt)}
        preparations.append_event(conn, plan_id=state["owner"]["id"], event_type=SUCCEEDED,
                                  stage="generating_content", payload=success, now=now_ms())
        # The original coordinator may have waited through operator diagnosis.
        # Release its idle content lease as the normal continuation does; its
        # next normal claim gets a new stage deadline without rewriting jobs.
        coordinator = preparations.get_plan(conn, plan_id=state["owner"]["id"], for_update=True)
        pending = conn.execute("SELECT COUNT(*) AS count FROM learning_budget_reservations WHERE authorization_id=? "
            "AND state IN ('reserved','dispatched','unknown')",
            (digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]}),)).fetchone()
        if (pending["count"] or coordinator["status"] != "running" or coordinator["stage"] != "generating_content"
                or coordinator.get("work_unit_kind") not in {None, "coordinator"}
                or coordinator.get("bound_catalog_item_id") is not None):
            raise RuntimeError("content coordinator is not idle; correction retained for diagnosis")
        conn.execute("UPDATE learning_curriculum_preparation_plans SET lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL, "
            "hard_deadline_at=NULL,work_unit_kind=NULL,next_run_at=?,updated_at=? WHERE id=? AND status='running' "
            "AND stage='generating_content' AND target_fingerprint=?",
            (now_ms(), now_ms(), coordinator["id"], identity["targetFingerprint"]))
        preparations.append_event(conn, plan_id=coordinator["id"], event_type="progressive_correction_coordinator_resumed",
            stage="generating_content", payload={"buildItemId": identity["buildItemId"], "auditShaId": started["auditShaId"],
                "previousDeadlineMsCount": int(coordinator.get("hard_deadline_at") or 0)}, now=now_ms())
        if preparations.reconcile_shared_build(conn, build_id=identity["buildId"],
                target_fingerprint=identity["targetFingerprint"], now=now_ms()) < 1:
            raise RuntimeError("accepted correction could not refresh its content coordinator from real receipts")
    return {"status": "accepted", **success}
