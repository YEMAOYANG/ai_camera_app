"""One explicit editorial revision of the rejected M6A01.01 first slot.

Preserves all four failed model jobs and their eight paid calls. A new editorial
job performs one answer-blind review; normal Host/release gates precede any CAS
of the original item. No model generation or Runtime creation is performed.
"""
from __future__ import annotations

import argparse
from copy import copy, deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from content.learning_budget_policy import canonical, digest
from content.progressive_runtime_authoring_scope import CONTENT_FIELD, issue_runtime_authoring_scope
from core.config import AppConfig
from core.database import Database
from core.security import now_ms
from scripts.progressive_preview_editorial import _file, _save
from services.progressive_course_generation import (
    CONTRACT_VERSION, VALIDATION_SCHEMA, VERIFY_SCHEMA, _provider_call,
    _assessment_generation_context, _reject_reused_independent_tasks, _validate_question,
    generation_brief, validate_progressive_course, validate_progressive_course_for_release,
)

LESSON = "M6A01.01"
ITEM = "catalog_build_item_6b26bea50f1cdd7acaf2dfb2"
BASE_REQUEST = "catalog_gen_6b26bea50f1cdd7acaf2dfb226d09cd8f2c89841cff31b8f"
SOURCE_REQUEST = BASE_REQUEST + ".correction3"
EDITORIAL_REQUEST = BASE_REQUEST + ".editorial1"
AUDITS = ROOT / "output/progressive-preview/math-slot1-editorial"
NATIVE = ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/formal-courseware-provider-responses"
SOURCE_FILES = {
    "progressive_generation": "0631e14f4ff658bbda663d6aae694800b890f720e25c7a48eb65480b5238c10a/41889b6da3bdae0a9b55bd4a9faf05a5ff9a1cee87f4835e54ab75954172c209.json",
    "progressive_verification": "5d003ec0989efcc7f896b1260886d514450fe04535c7e34f22978802f01bd701/8f0ce34993584bf9b5b8cd42be57283a9aa5c242b7c20dc7bc94b8d685689089.json",
}
SCHEMA = "mira.progressive-math-editorial-audit.v1"
STARTED = "progressive_math_editorial_started"
SUCCEEDED = "progressive_math_editorial_succeeded"


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def identity():
    from scripts.generate_progressive_preview import preview_identities
    identities = preview_identities("primary_6")
    selected = [i for i in identities if i["buildItemId"] == ITEM
                and i["slot"]["lessonId"] == LESSON and i["slot"]["variantOrdinal"] == 1]
    require(len(selected) == 1, "exact approved mathematics first slot changed")
    return selected[0], identities


def source_records():
    records, archives = {}, []
    for phase, relative in SOURCE_FILES.items():
        row, file = _file(NATIVE / relative)
        request = SOURCE_REQUEST + (":verify" if phase == "progressive_verification" else "")
        require(row.get("requestId") == request and row.get("phase") == phase
            and row.get("responseId") and isinstance(row.get("usage"), dict), "original returned Provider identity changed")
        records[phase] = json.loads(row["content"])
        archives.append({**file, "phase": phase, "requestId": request, "inputSha256": row["inputSha256"]})
    verdict = records["progressive_verification"]
    verdict = verdict.get("verification", verdict)
    require(verdict.get("passed") is False and verdict.get("issues"), "source must remain explicitly rejected")
    return records["progressive_generation"]["candidateCourse"], verdict, archives


def editorial_delta(before, after, path=""):
    if type(before) is not type(after):
        raise RuntimeError("editorial cannot change the frozen JSON structure")
    if isinstance(before, dict):
        require(set(before) == set(after), "editorial cannot add/remove content fields")
        return [change for key in before for change in editorial_delta(before[key], after[key], path + "/" + key)]
    if isinstance(before, list):
        require(len(before) == len(after), "editorial cannot add/remove questions or teaching steps")
        return [change for i, (old, new) in enumerate(zip(before, after)) for change in editorial_delta(old, new, path + "/" + str(i))]
    if before == after:
        return []
    allowed = (path in {"/objective", "/content/intro"}
        or re.fullmatch(r"/content/progressiveFlow/[0-9]+/text", path)
        or re.fullmatch(r"/content/questions/[0-9]+/(prompt|hint|explanation|answer|evidence/expression|choices/[0-3]/label)", path))
    require(allowed and isinstance(after, str) and bool(after.strip()), "editorial changed a frozen field: " + path)
    return [{"path": path, "before": before, "after": after}]


def edited_with_scope(original, edited):
    edits = editorial_delta(original, edited)
    require(edits and CONTENT_FIELD not in edited["content"], "editorial must change content, not supply Host metadata")
    brief = generation_brief(LESSON)
    require(edited["content"]["progressiveLesson"] == brief["binding"], "editorial registry binding changed")
    questions = edited["content"]["questions"]
    require([q["id"] for q in questions] == ["guided_1", *[f"independent_{i}" for i in range(1, 6)]], "exact six question identities changed")
    allowed = set(brief["allowedKnowledgeIds"])
    introduced = set(brief["lesson"]["introducedKnowledgeIds"])
    for question in questions:
        require(question.get("evidence", {}).get("kind") == "numeric_expression", "this editorial retains numeric evidence")
        # Deterministic numeric/choice validation only; never fabricate a review.
        _validate_question(question, lesson=brief["lesson"], allowed=allowed, introduced=introduced)
    result = deepcopy(edited)
    result["content"][CONTENT_FIELD] = issue_runtime_authoring_scope(lesson_id=LESSON, binding=brief["binding"],
        request_id=EDITORIAL_REQUEST, provider_content=edited["content"])
    return result, edits, brief


def snapshot(conn, selected):
    item = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?", (ITEM,)).fetchone()
    requests = [BASE_REQUEST, *[BASE_REQUEST + f".correction{i}" for i in range(1, 4)]]
    jobs = [conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=?", (r,)).fetchone() for r in requests]
    require(item and item["status"] == "failed" and item["content_phase"] == "failed"
        and item["generation_request_id"] == BASE_REQUEST and not item.get("course_id") and not item.get("course_version"),
        "source item is no longer the original rejected, unbound slot")
    require(all(j and j["status"] == "failed" and j["node_code"] == LESSON for j in jobs), "the four original failed jobs changed")
    for job in jobs:
        require(conn.execute("SELECT COUNT(*) AS n FROM learning_course_generation_candidates WHERE job_id=?", (job["id"],)).fetchone()["n"] == 0,
                "a rejected source job has staged candidates")
    require(conn.execute("SELECT COUNT(*) AS n FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?", (ITEM,)).fetchone()["n"] == 0,
            "editorial cannot replace an existing Runtime")
    owner = conn.execute("SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? AND library_target_fingerprint=?",
        (selected["buildId"], selected["targetFingerprint"])).fetchone()
    require(owner and owner["status"] == "running" and owner["stage"] == "generating_content"
        and owner.get("work_unit_kind") in {None, "coordinator"} and owner.get("bound_catalog_item_id") is None,
        "shared content coordinator is not idle and recoverable")
    auth_id = digest({"schema": "mira.catalog-paid-budget.v1", "scope": selected["scope"]})
    auth = conn.execute("SELECT * FROM learning_budget_authorizations WHERE id=?", (auth_id,)).fetchone()
    require(auth and json.loads(auth["scope_json"]) == selected["scope"] and auth["revoked_at"] is None
        and auth["expires_at"] > now_ms(), "exact production authorization is unavailable")
    ledger = [dict(r) for r in conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id", (auth_id,)).fetchall()]
    require(all(r["state"] == "settled" for r in ledger), "unresolved calls prevent editorial review")
    require(conn.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()["n"] == 0,
            "an active Provider call prevents editorial review")
    context = _assessment_generation_context(conn, lesson_id=LESSON,
        curriculum_version=generation_brief(LESSON)["binding"]["curriculumVersion"], request_id=EDITORIAL_REQUEST)
    return {"item": dict(item), "jobs": [dict(j) for j in jobs], "owner": dict(owner),
        "authorization": dict(auth), "ledger": ledger, "generationContext": context}


def prepare(path):
    selected, _ = identity()
    original, verdict, archives = source_records()
    candidate, input_file = _file(path)
    candidate = candidate.get("candidateCourse", candidate)
    edited, edits, brief = edited_with_scope(original, candidate)
    database = Database(AppConfig.from_env().DATABASE_URL)
    conn = database.connect()
    try:
        conn.execute("START TRANSACTION READ ONLY")
        saved = snapshot(conn, selected)
        require(len(saved["ledger"]) == 8, "source must have exactly eight settled content calls")
        require(not _event(conn, selected, STARTED) and not conn.execute("SELECT id FROM learning_course_generation_jobs WHERE request_id=?", (EDITORIAL_REQUEST,)).fetchone(),
                "this editorial was already dispatched; do not prepare another")
        _reject_reused_independent_tasks(edited["content"], saved["generationContext"])
    finally:
        conn.rollback()
        conn.close()
    audit = {"schemaVersion": SCHEMA, "identity": selected, "editorialRequestId": EDITORIAL_REQUEST,
        "sourceGenerationRequestId": SOURCE_REQUEST, "archives": archives, "originalCandidate": original,
        "sourceReview": verdict, "editedInput": input_file, "editedCandidate": edited, "edits": edits,
        "editedContentSha256": digest(edited["content"]), "brief": brief, "originals": saved,
        "provenance": {"kind": "model_generated_editorial_revision", "generationProviderCalls": 0,
            "requiredNewVerificationCalls": 1, "sourceModelRepliesPreserved": True},
        "coordinatorResume": "After real validation, restore only the same item and reconcile the idle owner from receipts; preserve all failed jobs and financial records."}
    sha = digest(audit)
    _save(AUDITS / (sha + ".json"), audit)
    _save(AUDITS / (sha + "-diff.json"), edits)
    return sha, audit


def read_audit(sha, selected):
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "invalid editorial audit SHA")
    audit = json.loads((AUDITS / (sha + ".json")).read_text())
    require(digest(audit) == sha and audit["schemaVersion"] == SCHEMA and audit["identity"] == selected
        and audit["editorialRequestId"] == EDITORIAL_REQUEST and audit["sourceGenerationRequestId"] == SOURCE_REQUEST,
        "editorial audit identity changed")
    original, verdict, archives = source_records()
    require((original, verdict, archives) == (audit["originalCandidate"], audit["sourceReview"], audit["archives"]), "original Provider archives changed")
    plain = deepcopy(audit["editedCandidate"])
    plain["content"].pop(CONTENT_FIELD)
    edited, edits, brief = edited_with_scope(original, plain)
    require(edited == audit["editedCandidate"] and edits == audit["edits"] and brief == audit["brief"]
        and digest(edited["content"]) == audit["editedContentSha256"], "editorial content or Host scope changed")
    return audit


def _event(conn, selected, kind):
    rows = conn.execute("SELECT e.payload_json,p.target_fingerprint FROM learning_curriculum_preparation_events e "
        "JOIN learning_curriculum_preparation_plans p ON p.id=e.plan_id WHERE p.catalog_build_id=? AND e.event_type=? "
        "AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.buildItemId'))=?",
        (selected["buildId"], kind, ITEM)).fetchall()
    require(len(rows) <= 1 and all(r["target_fingerprint"] == selected["targetFingerprint"] for r in rows), "conflicting editorial events")
    return json.loads(rows[0]["payload_json"]) if rows else None


def accepted_math_editorial_job(conn, selected, item):
    if selected.get("buildItemId") != ITEM:
        return None
    event = _event(conn, selected, SUCCEEDED)
    if not event:
        return None
    audit = read_audit(event["auditShaId"], selected)
    started = _event(conn, selected, STARTED)
    require(started and all(started.get(k) == event.get(k) for k in ("auditShaId", "editorialRequestId", "generationJobId")), "editorial start audit changed")
    for original in audit["originals"]["jobs"]:
        row = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=?", (original["id"],)).fetchone()
        require(dict(row or {}) == original, "original failed generation history changed")
    job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=?", (event["generationJobId"],)).fetchone()
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?", (event["courseId"], event["courseVersionId"])).fetchone()
    paid = conn.execute("SELECT * FROM learning_budget_reservations WHERE id=?", (event["verificationReservationId"],)).fetchone()
    require(job and course and job["request_id"] == EDITORIAL_REQUEST and job["status"] == "validated"
        and course["generation_request_id"] == EDITORIAL_REQUEST
        and digest(json.loads(course["content_json"])) == audit["editedContentSha256"]
        and paid and paid["authorization_id"] == audit["originals"]["authorization"]["id"] and paid["state"] == "settled",
        "accepted editorial provenance changed")
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=LESSON)
    require(digest(receipt) == event["contentReceiptShaId"] and item.get("course_id") == course["id"]
        and item.get("course_version") == course["version"] and item.get("content_receipt_hash") == digest(receipt)
        and item.get("content_gate_status") == "passed" and item.get("content_phase") == "course_ready"
        and item.get("generation_request_id") == BASE_REQUEST, "editorial is not bound to the original item")
    return job


def apply_audit(args, sha, audit):
    from scripts.generate_one_library_course import operator_app, emit
    from scripts.generate_progressive_preview import assert_preview_policy
    from services.service_factory import (_catalog_paid_budget_environment, dynamic_learning_course_generation_service,
        learning_curriculum_preparation_checkpoint_adapter, openmaic_full_runtime_service)
    selected, identities = identity()
    assert_preview_policy(args.budget_policy, identities)
    app = operator_app(args)
    with app.app_context():
        preparations = learning_curriculum_preparation_checkpoint_adapter().repository
        require(preparations.content_proof_auditor is not None, "normal content proof auditor unavailable")
        generator = copy(dynamic_learning_course_generation_service())
        adapter = copy(generator.progressive_adapter)
        require(not adapter.fake_mode and adapter.provider_name == "openmaic_runtime", "normal real answer-blind verifier required")
        generator.adapter = adapter
        brief = audit["brief"]
        require(openmaic_full_runtime_service().formal_provider_circuit_status()["dispatchAllowed"], "normal Provider circuit is not ready")
        with generator.repository.transaction() as conn:
            accepted = accepted_math_editorial_job(conn, selected, dict(conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?", (ITEM,)).fetchone()))
            if accepted:
                emit("math_editorial_already_accepted", generationJobId=accepted["id"])
                return
            saved = snapshot(conn, selected)
            require(saved == audit["originals"] and len(saved["ledger"]) == 8, "source state changed after editorial preflight")
            require(not _event(conn, selected, STARTED) and not conn.execute("SELECT id FROM learning_course_generation_jobs WHERE request_id=?", (EDITORIAL_REQUEST,)).fetchone(),
                "editorial already dispatched; inspect its saved result, never resend")
            job, created = generator.repository.create_or_get_job(conn, request_id=EDITORIAL_REQUEST,
                grade_code="primary_6", subject="math", node_code=LESSON, curriculum_version=brief["binding"]["curriculumVersion"],
                boundary_version=saved["jobs"][-1]["boundary_version"], generator="openmaic",
                provider=adapter.provider_name, model=adapter.model_name, prompt_version=CONTRACT_VERSION,
                requested_candidate_count=1, generation_spec={"brief": brief, "editorialAuditShaId": sha,
                    "provenance": audit["provenance"], "editedContentSha256": audit["editedContentSha256"]}, now=now_ms())
            require(created, "editorial job already exists")
            event = {"buildItemId": ITEM, "auditShaId": sha, "editorialRequestId": EDITORIAL_REQUEST,
                "generationJobId": job["id"], "sourceGenerationJobId": saved["jobs"][-1]["id"], "generationProviderCallCount": 0}
            preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type=STARTED,
                stage="generating_content", payload=event, now=now_ms())
            generator.repository.mark_job_generating(conn, job_id=job["id"], now=now_ms())
        command = SimpleNamespace(build_item_id=ITEM, grade_code="primary_6", subject="math", boundary={"skillId": LESSON})
        used = False

        def exact_environment(payload):
            nonlocal used
            from services.progressive_course_generation import _public_candidate
            require(not used and payload.get("schemaVersion") == VERIFY_SCHEMA and payload.get("requestId") == EDITORIAL_REQUEST + ":verify"
                and payload.get("brief") == brief and payload.get("publicCandidate") == _public_candidate(audit["editedCandidate"])
                and payload.get("generationContext") == saved["generationContext"], "only one exact answer-blind editorial verification is allowed")
            assert_preview_policy(args.budget_policy, identities)
            require(read_audit(sha, selected) == audit, "editorial audit changed before dispatch")
            used = True
            return _catalog_paid_budget_environment(command)

        adapter.execution_environment = exact_environment
        try:
            verification = _provider_call(generator, request_id=EDITORIAL_REQUEST + ":verify", schema=VERIFY_SCHEMA,
                brief=brief, candidate=audit["editedCandidate"], generation_context=saved["generationContext"])
            _save(AUDITS / (sha + "-verification.json"), verification)
            course, report = validate_progressive_course(audit["editedCandidate"], brief=brief,
                verification=verification, request_id=EDITORIAL_REQUEST)
            _reject_reused_independent_tasks(course["content"], saved["generationContext"])
            with generator.repository.transaction() as conn:
                candidate, created = generator.repository.create_or_get_candidate(conn, job_id=job["id"], ordinal=1, course=course, now=now_ms())
                require(created, "editorial candidate already exists")
                generator.repository.mark_candidate_validated(conn, candidate_id=candidate["id"], validation=report, now=now_ms())
            staged, _ = generator.repository.stage_candidate(candidate_id=candidate["id"], now=now_ms())
            with generator.repository.transaction() as conn:
                conn.execute("SELECT id FROM learning_curriculum_preparation_plans WHERE id=? FOR UPDATE", (saved["owner"]["id"],)).fetchone()
                conn.execute("SELECT id FROM learning_catalog_build_items WHERE id=? FOR UPDATE", (ITEM,)).fetchone()
                current = snapshot(conn, selected)
                require(all(current[k] == saved[k] for k in saved if k != "ledger"), "original source changed during editorial review")
                old_ids = {r["id"] for r in saved["ledger"]}
                require([r for r in current["ledger"] if r["id"] in old_ids] == saved["ledger"], "old financial history changed")
                new_paid = [r for r in current["ledger"] if r["id"] not in old_ids]
                require(len(new_paid) == 1 and new_paid[0]["state"] == "settled", "one settled editorial review is required")
                receipt = validate_progressive_course_for_release(conn, course=staged, expected_lesson_id=LESSON)
                updated = conn.execute("UPDATE learning_catalog_build_items SET status='course_ready',content_phase='course_ready',"
                    "course_id=?,course_version=?,content_gate_status='passed',content_gate_passed_at=?,content_validation_contract_version=?,"
                    "content_receipt_hash=?,error_code=NULL,error_message_safe=NULL,updated_at=? "
                    "WHERE id=? AND status='failed' AND content_phase='failed' AND generation_request_id=? AND updated_at=?",
                    (staged["id"], staged["version"], now_ms(), VALIDATION_SCHEMA, digest(receipt), now_ms(), ITEM, BASE_REQUEST, saved["item"]["updated_at"]))
                require(updated.rowcount == 1, "source item changed before editorial CAS")
                success = {**event, "courseId": staged["id"], "courseVersionId": staged["version"],
                    "contentReceiptShaId": digest(receipt), "verificationReservationId": new_paid[0]["id"], "verificationProviderCallCount": 1}
                preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type=SUCCEEDED,
                    stage="generating_content", payload=success, now=now_ms())
                resumed = conn.execute("UPDATE learning_curriculum_preparation_plans SET lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,"
                    "hard_deadline_at=NULL,work_unit_kind=NULL,next_run_at=?,updated_at=? WHERE id=? AND status='running' "
                    "AND stage='generating_content' AND target_fingerprint=?",
                    (now_ms(), now_ms(), saved["owner"]["id"], selected["targetFingerprint"]))
                require(resumed.rowcount == 1, "same content coordinator changed before resume")
                preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type="progressive_math_editorial_coordinator_resumed",
                    stage="generating_content", payload={"buildItemId": ITEM, "auditShaId": sha,
                        "previousDeadlineMsCount": int(saved["owner"].get("hard_deadline_at") or 0)}, now=now_ms())
                require(preparations.reconcile_shared_build(conn, build_id=selected["buildId"],
                    target_fingerprint=selected["targetFingerprint"], now=now_ms()) >= 1, "normal content-proof reconciliation failed")
            emit("math_editorial_accepted", **success)
        except Exception as exc:
            generator._persist_failure(job_id=job["id"], code=str(getattr(exc, "code", "math_editorial_review_failed")),
                message=str(getattr(exc, "message", str(exc))))
            raise


def main():
    from scripts.generate_one_library_course import LOCK_PATH, emit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "apply"))
    parser.add_argument("--edited-candidate")
    parser.add_argument("--audit-sha")
    parser.add_argument("--budget-policy")
    parser.add_argument("--confirm-workers-stopped", action="store_true")
    args = parser.parse_args()
    args.grade = "primary_6"
    require(args.command != "prepare" or args.edited_candidate, "prepare requires --edited-candidate")
    require(args.command != "apply" or args.audit_sha and args.budget_policy and args.confirm_workers_stopped,
            "apply requires --audit-sha, --budget-policy and --confirm-workers-stopped")
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "prepare":
            sha, audit = prepare(args.edited_candidate)
            emit("math_editorial_prepared", auditPath=str(AUDITS / (sha + ".json")), auditShaId=sha,
                diffPath=str(AUDITS / (sha + "-diff.json")), editedFieldCount=len(audit["edits"]), databaseWrites=0, providerCalls=0)
        else:
            selected, _ = identity()
            apply_audit(args, args.audit_sha, read_audit(args.audit_sha, selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
