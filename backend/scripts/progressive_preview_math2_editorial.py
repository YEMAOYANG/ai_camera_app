"""Prepare, independently review, then activate one unpublished math2 revision.

No command retries a Provider call. prepare/status are read-only except local
audit archives. review stages a separate candidate; activate never dispatches.
The old Native job may finish naturally, but cannot be published or rewritten.
"""
from __future__ import annotations
import argparse
from copy import copy, deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from content.learning_budget_policy import digest
from content.progressive_runtime_authoring_scope import CONTENT_FIELD, issue_runtime_authoring_scope
from core.config import AppConfig
from core.database import Database
from core.security import now_ms
from scripts.progressive_preview_editorial import _file, _save
from services.progressive_math2_revision import (
    ITEM, LESSON, SOURCE_COURSE, SOURCE_RUNTIME, SOURCE_NATIVE_JOB, BASE_REQUEST,
    EDITORIAL_REQUEST, AUDITS, SCHEMA, STARTED, REVIEWED, ACTIVATED,
    require, event, read_audit, reviewed_candidate, activated_revision,
)
from services.progressive_course_generation import (
    CONTRACT_VERSION, VALIDATION_SCHEMA, VERIFY_SCHEMA, generation_brief, _public_candidate,
    _assessment_generation_context, _reject_reused_independent_tasks, _validate_question,
    _provider_call, validate_progressive_course, validate_progressive_course_for_release,
)
NATIVE = ROOT / "openmaic-runtime/.runtime/OpenMAIC"
NATIVE_JOB = NATIVE / "data/classroom-jobs" / (SOURCE_NATIVE_JOB + ".json")
SOURCE_FILES = {
    "progressive_generation": "3bf7e4f3f2d33e9a8f403e58a274ed486c5197c2c737ac3be912b357c2058601/da5aa3da760a81b639b4de1c05a04ea01a2f2031e36e4dbac63a25bdd497032f.json",
    "progressive_verification": "126fcff4376ceb25d9654d5ad92eb0a250a5e9aaea222467c036b01676b0ac92/93ba2fe6060e058d3f5e5db673955f4f899391bea9dbff764fcbd51cbca3f01d.json",
}


def identity():
    from scripts.generate_progressive_preview import preview_identities
    all_ids = preview_identities("primary_6")
    selected = [x for x in all_ids if x["buildItemId"] == ITEM and x["slot"]["lessonId"] == LESSON and x["slot"]["variantOrdinal"] == 2]
    require(len(selected) == 1, "exact approved math2 scope changed")
    return selected[0], all_ids


def source_records():
    records, files = {}, []
    for phase, relative in SOURCE_FILES.items():
        value, file = _file(NATIVE / "data/formal-courseware-provider-responses" / relative)
        require(value["requestId"] == BASE_REQUEST + (":verify" if phase == "progressive_verification" else "")
            and value["phase"] == phase and value.get("responseId"), "source archive identity changed")
        records[phase] = json.loads(value["content"])
        files.append({**file, "requestId": value["requestId"], "phase": phase, "inputSha256": value["inputSha256"]})
    verification = records["progressive_verification"]
    verification = verification.get("verification", verification)
    require(verification.get("passed") is True, "preserve the real original passed review")
    return records["progressive_generation"]["candidateCourse"], verification, files


def edit(original, candidate):
    from scripts.progressive_preview_math_editorial import editorial_delta
    edits = editorial_delta(original, candidate)
    require(edits and CONTENT_FIELD not in candidate["content"], "explicit edits without Host metadata required")
    for change in edits:
        path = change["path"]
        allowed = re.fullmatch(r"/content/questions/(1|5)/(prompt|hint|explanation|answer|evidence/expression|choices/[0-3]/label)", path)
        match = re.fullmatch(r"/content/progressiveFlow/([0-9]+)/text", path)
        if match:
            allowed = candidate["content"]["progressiveFlow"][int(match[1])].get("questionId") in {"independent_1", "independent_5"}
        require(allowed, "revision changed an unapproved field: " + path)
    brief = generation_brief(LESSON)
    require(candidate["content"]["progressiveLesson"] == brief["binding"], "registry binding changed")
    questions = candidate["content"]["questions"]
    require([q["id"] for q in questions] == ["guided_1", *[f"independent_{i}" for i in range(1, 6)]], "frozen six-question identities changed")
    for q in questions:
        _validate_question(q, lesson=brief["lesson"], allowed=set(brief["allowedKnowledgeIds"]), introduced=set(brief["lesson"]["introducedKnowledgeIds"]))
    value = deepcopy(candidate)
    value["content"][CONTENT_FIELD] = issue_runtime_authoring_scope(lesson_id=LESSON,
        binding=brief["binding"], request_id=EDITORIAL_REQUEST, provider_content=candidate["content"])
    return value, edits, brief


def native_proof(*, terminal):
    raw = NATIVE_JOB.read_bytes(); job = json.loads(raw)
    require(job["id"] == SOURCE_NATIVE_JOB and job["runtimeRequestId"] == "mira-formal-runtime-" + ITEM + "-attempt-1"
        and digest(job["formalInput"]) == job["formalInputSha256"], "original Native input identity changed")
    if terminal:
        require(job["status"] in {"succeeded", "failed"} and job.get("completedAt") and not job.get("dispatchAmbiguous"), "original Native must be a confirmed terminal job")
    from dotenv import dotenv_values
    env = dotenv_values(os.environ.get("MIRA_OPENMAIC_PROVIDER_ENV_FILE") or ROOT / "backend/.env")
    url = os.environ.get("MIRA_OPENMAIC_AGENT_DATABASE_URL") or env.get("MIRA_OPENMAIC_AGENT_DATABASE_URL")
    code = r"""const {Client}=require(process.argv[1]),crypto=require('crypto');let s='';
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,x])=>JSON.stringify(k)+':'+canonical(x)).join(',')+'}':JSON.stringify(v);
process.stdin.on('data',x=>s+=x);process.stdin.on('end',async()=>{const x=JSON.parse(s),c=new Client({connectionString:x.url});try{await c.connect();await c.query('BEGIN READ ONLY');
const id='miraformal_'+sha(x.job.runtimeRequestId+'\n'+canonical(x.job.formalInput));
const r=(await c.query('SELECT id,owner_id,prompt,status,attempt,stage_id,active_stage_id,lease_worker_id,deleted_at,cancel_requested_at FROM agent_sessions WHERE id=$1',[id])).rows;
if(r.length!==1)throw Error('source session missing');const session=r[0];session.promptSha256=sha(session.prompt);delete session.prompt;
const events=(await c.query("SELECT seq,type,attempt,encode(sha256(convert_to(data::text,'UTF8')),'hex') AS data_sha256 FROM agent_session_events WHERE session_id=$1 ORDER BY seq",[id])).rows;
await c.query('ROLLBACK');console.log(JSON.stringify({session,events}));}catch(e){process.exitCode=1;}finally{await c.end();}});"""
    result = subprocess.run(["node", "-e", code, str(NATIVE / "node_modules/pg")], input=json.dumps({"url": url, "job": job}), text=True, capture_output=True, timeout=25)
    require(result.returncode == 0, "Native read-only session proof unavailable")
    proof = json.loads(result.stdout); session = proof["session"]
    require(session["owner_id"] == "mira-formal-professional:" + session["id"][11:] and not session["deleted_at"], "source session owner changed")
    if terminal:
        require(session["status"] in {"succeeded", "failed", "cancelled"} and not session["lease_worker_id"] and not session["active_stage_id"], "source Agent is not terminal")
    return {"job": job, "jobRaw": raw.decode(), "jobSha256": hashlib.sha256(raw).hexdigest(), "agent": proof}


def snapshot(conn, selected, *, idle=False):
    item = dict(conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?", (ITEM,)).fetchone() or {})
    require(item.get("course_id") == SOURCE_COURSE and item.get("status") == "course_ready"
        and item.get("content_phase") == "course_ready" and item.get("content_gate_status") == "passed"
        and item.get("generation_request_id") == BASE_REQUEST, "original item has changed")
    course = dict(conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?", (SOURCE_COURSE, item["course_version"])).fetchone())
    require(course["status"] == "validated" and course.get("retired_at") is None, "source is published or retired")
    job = dict(conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=?", (BASE_REQUEST,)).fetchone())
    require(job["status"] == "validated", "original accepted job changed")
    runtimes = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?", (ITEM,)).fetchall()
    require(len(runtimes) == 1 and runtimes[0]["id"] == SOURCE_RUNTIME and runtimes[0]["course_id"] == SOURCE_COURSE
        and runtimes[0]["upstream_job_id"] == SOURCE_NATIVE_JOB and not runtimes[0].get("retired_at"), "original Runtime history changed")
    runtime = dict(runtimes[0])
    for sql, params in (
        ("SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?", (ITEM,)),
        ("SELECT COUNT(*) AS n FROM learning_formal_qwen_audio_jobs WHERE build_item_id=?", (ITEM,)),
        ("SELECT COUNT(*) AS n FROM learning_sessions WHERE course_id=? AND course_version=?", (SOURCE_COURSE, course["version"])),
        ("SELECT COUNT(*) AS n FROM learning_placement_questions WHERE course_id=? AND course_version=?", (SOURCE_COURSE, course["version"])),
        ("SELECT COUNT(*) AS n FROM learning_practice_exposures e JOIN learning_practice_questions q ON q.id=e.question_id WHERE q.course_id=? AND q.course_version=?", (SOURCE_COURSE, course["version"])),
    ):
        require(conn.execute(sql, params).fetchone()["n"] == 0, "original publication/audio/student evidence prevents revision")
    package = dict(conn.execute("SELECT * FROM learning_lesson_packages WHERE id=? AND version=?", (runtime["package_id"], runtime["package_version"])).fetchone())
    require(package["status"] == "candidate" and not package.get("published_at") and not package.get("retired_at"), "original package is already used")
    owner = dict(conn.execute("SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? AND library_target_fingerprint=?",
        (selected["buildId"], selected["targetFingerprint"])).fetchone())
    require(owner["status"] == "running" and not owner.get("completed_at") and not owner.get("superseded_at"), "same coordinator is not recoverable")
    auth_id = digest({"schema": "mira.catalog-paid-budget.v1", "scope": selected["scope"]})
    auth = dict(conn.execute("SELECT * FROM learning_budget_authorizations WHERE id=?", (auth_id,)).fetchone())
    require(json.loads(auth["scope_json"]) == selected["scope"] and auth["revoked_at"] is None and auth["expires_at"] > now_ms(), "exact production authorization unavailable")
    ledger = [dict(r) for r in conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id", (auth_id,)).fetchall()]
    if idle:
        require(int(owner.get("lease_expires_at") or 0) <= now_ms(), "coordinator lease is still live; wait for expiry")
        require(all(r["state"] == "settled" for r in ledger), "source paid outcome is unresolved")
        require(conn.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()["n"] == 0, "another paid call is active")
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=LESSON)
    require(digest(receipt) == item["content_receipt_hash"], "original content receipt changed")
    context = _assessment_generation_context(conn, lesson_id=LESSON, curriculum_version=course["curriculum_version"], request_id=EDITORIAL_REQUEST)
    # This precise unpublished/unexposed source is being replaced. All other
    # validated/published courses, including math1 editorial, remain in context.
    context["previousQuestions"] = [q for q in context["previousQuestions"] if not (q["courseId"] == SOURCE_COURSE and q["courseVersion"] == course["version"])]
    return {"item": item, "course": course, "job": job, "runtime": runtime, "package": package,
        "owner": owner, "authorization": auth, "ledger": ledger, "generationContext": context}


def prepared(candidate_path):
    selected, _ = identity(); original, review, archives = source_records()
    candidate, file = _file(candidate_path); candidate = candidate.get("candidateCourse", candidate)
    revised, delta, brief = edit(original, candidate)
    conn = Database(AppConfig.from_env().DATABASE_URL).connect()
    try:
        conn.execute("START TRANSACTION READ ONLY")
        saved = snapshot(conn, selected)
        require(not event(conn, STARTED), "review already attempted; never replay")
        _reject_reused_independent_tasks(revised["content"], saved["generationContext"])
    finally:
        conn.rollback(); conn.close()
    native = native_proof(terminal=True)
    audit = {"schemaVersion": SCHEMA, "identity": selected, "editorialRequestId": EDITORIAL_REQUEST,
        "archives": archives, "originalCandidate": original, "originalReview": review, "editedInput": file,
        "sourceCourse": saved["course"], "sourceJob": saved["job"], "sourceItem": saved["item"],
        "sourcePackage": saved["package"], "originalNativeAtPrepare": native,
        "authorizationId": saved["authorization"]["id"], "generationContext": saved["generationContext"],
        "editedCandidate": revised, "edits": delta, "brief": brief, "editedContentSha256": digest(revised["content"]),
        "provenance": {"kind": "model_generated_editorial_revision", "generationProviderCalls": 0,
            "requiredNewVerificationCalls": 1, "originalValidatedHistoryRetained": True},
        "reason": "independent_1 reuses math1 guided arithmetic; independent_5 receives new material in the same explicit revision"}
    sha = digest(audit); _save(AUDITS / (sha + ".json"), audit); _save(AUDITS / (sha + "-diff.json"), delta)
    return sha, audit


def assert_source(saved, audit, native):
    require(saved["course"] == audit["sourceCourse"] and saved["job"] == audit["sourceJob"]
        and saved["item"] == audit["sourceItem"] and saved["package"] == audit["sourcePackage"]
        and saved["generationContext"] == audit["generationContext"], "prepared original authority changed")
    old = audit["originalNativeAtPrepare"]
    require(native["jobSha256"] == old["jobSha256"] and native["agent"] == old["agent"]
        and native["job"]["formalInput"] == old["job"]["formalInput"] and native["job"]["formalInputSha256"] == old["job"]["formalInputSha256"]
        and native["agent"]["session"]["id"] == old["agent"]["session"]["id"]
        and native["agent"]["session"]["promptSha256"] == old["agent"]["session"]["promptSha256"]
        and native["agent"]["session"]["attempt"] == old["agent"]["session"]["attempt"], "original Native input or Agent generation changed")


def review(args, sha, audit):
    from scripts.generate_one_library_course import operator_app
    from scripts.generate_progressive_preview import assert_preview_policy
    from scripts.resume_progressive_content_owner import idle_processes
    from services.service_factory import (_catalog_paid_budget_environment, dynamic_learning_course_generation_service,
        learning_curriculum_preparation_checkpoint_adapter, openmaic_full_runtime_service)
    selected, all_ids = identity(); assert_preview_policy(args.budget_policy, all_ids); idle_processes()
    native = native_proof(terminal=True)
    with operator_app(args).app_context():
        generator = copy(dynamic_learning_course_generation_service()); adapter = copy(generator.progressive_adapter); generator.adapter = adapter
        repo = learning_curriculum_preparation_checkpoint_adapter().repository
        require(not adapter.fake_mode and adapter.provider_name == "openmaic_runtime", "real normal verifier required")
        require(openmaic_full_runtime_service().formal_provider_circuit_status()["dispatchAllowed"], "Provider circuit is not ready")
        with generator.repository.transaction() as conn:
            prior = reviewed_candidate(conn, sha)
            if prior:
                return {"status": "already_reviewed", **prior["event"]}
            saved = snapshot(conn, selected, idle=True); assert_source(saved, audit, native)
            require(not event(conn, STARTED) and not conn.execute("SELECT id FROM learning_course_generation_jobs WHERE request_id=?", (EDITORIAL_REQUEST,)).fetchone(), "review already attempted; inspect its saved outcome")
            start_archive = {"auditShaId": sha, "source": saved, "native": native}
            start_sha = digest(start_archive); _save(AUDITS / ("review-start-" + start_sha + ".json"), start_archive)
            job, created = generator.repository.create_or_get_job(conn, request_id=EDITORIAL_REQUEST, grade_code="primary_6", subject="math", node_code=LESSON,
                curriculum_version=audit["brief"]["binding"]["curriculumVersion"], boundary_version=saved["job"]["boundary_version"], generator="openmaic",
                provider=adapter.provider_name, model=adapter.model_name, prompt_version=CONTRACT_VERSION, requested_candidate_count=1,
                generation_spec={"brief": audit["brief"], "editorialAuditShaId": sha, "provenance": audit["provenance"], "editedContentSha256": audit["editedContentSha256"]}, now=now_ms())
            require(created, "review job already exists")
            payload = {"buildItemId": ITEM, "auditShaId": sha, "editorialRequestId": EDITORIAL_REQUEST, "generationJobId": job["id"], "reviewStartShaId": start_sha}
            repo.append_event(conn, plan_id=saved["owner"]["id"], event_type=STARTED, stage=saved["owner"]["stage"], payload=payload, now=now_ms())
            generator.repository.mark_job_generating(conn, job_id=job["id"], now=now_ms())
        used = False
        def environment(value):
            nonlocal used
            require(not used and value.get("schemaVersion") == VERIFY_SCHEMA and value.get("requestId") == EDITORIAL_REQUEST + ":verify"
                and value.get("brief") == audit["brief"] and value.get("publicCandidate") == _public_candidate(audit["editedCandidate"])
                and value.get("generationContext") == audit["generationContext"], "only the exact answer-blind editorial review is authorized")
            assert_preview_policy(args.budget_policy, all_ids); require(read_audit(sha) == audit, "audit changed")
            used = True
            return _catalog_paid_budget_environment(SimpleNamespace(build_item_id=ITEM, grade_code="primary_6", subject="math", boundary={"skillId": LESSON}))
        adapter.execution_environment = environment
        try:
            verdict = _provider_call(generator, request_id=EDITORIAL_REQUEST + ":verify", schema=VERIFY_SCHEMA,
                brief=audit["brief"], candidate=audit["editedCandidate"], generation_context=audit["generationContext"])
            _save(AUDITS / (sha + "-verification.json"), verdict)
            course, report = validate_progressive_course(audit["editedCandidate"], brief=audit["brief"], verification=verdict, request_id=EDITORIAL_REQUEST)
            with generator.repository.transaction() as conn:
                current = snapshot(conn, selected, idle=True); assert_source(current, audit, native_proof(terminal=True))
                _reject_reused_independent_tasks(course["content"], current["generationContext"])
                candidate, created = generator.repository.create_or_get_candidate(conn, job_id=job["id"], ordinal=1, course=course, now=now_ms())
                require(created, "candidate already staged")
                generator.repository.mark_candidate_validated(conn, candidate_id=candidate["id"], validation=report, now=now_ms())
            staged, _ = generator.repository.stage_candidate(candidate_id=candidate["id"], now=now_ms())
            with generator.repository.transaction() as conn:
                current = snapshot(conn, selected, idle=True); assert_source(current, audit, native_proof(terminal=True))
                old_ids = {r["id"] for r in saved["ledger"]}; new = [r for r in current["ledger"] if r["id"] not in old_ids]
                require([r for r in current["ledger"] if r["id"] in old_ids] == saved["ledger"] and len(new) == 1 and new[0]["state"] == "settled", "exactly one settled review required")
                receipt = validate_progressive_course_for_release(conn, course=staged, expected_lesson_id=LESSON)
                payload.update(courseId=staged["id"], courseVersionId=staged["version"], contentReceiptShaId=digest(receipt), verificationReservationId=new[0]["id"])
                repo.append_event(conn, plan_id=saved["owner"]["id"], event_type=REVIEWED, stage=saved["owner"]["stage"], payload=payload, now=now_ms())
            return {"status": "reviewed_not_activated", **payload}
        except Exception as exc:
            generator._persist_failure(job_id=job["id"], code=str(getattr(exc, "code", "math2_editorial_review_failed")), message=str(getattr(exc, "message", str(exc))))
            raise


def activate(args, sha, audit):
    from scripts.generate_one_library_course import operator_app
    from scripts.generate_progressive_preview import assert_preview_policy
    from scripts.resume_progressive_content_owner import idle_processes
    from services.service_factory import learning_curriculum_preparation_checkpoint_adapter
    selected, all_ids = identity(); assert_preview_policy(args.budget_policy, all_ids); idle_processes()
    native = native_proof(terminal=True)
    with operator_app(args).app_context():
        repo = learning_curriculum_preparation_checkpoint_adapter().repository
        with repo.transaction() as conn:
            prior = activated_revision(conn)
            if prior:
                require(prior["activation"]["auditShaId"] == sha, "another revision exists")
                return {"status": "already_activated", **prior["activation"]}
            # Stable owner/item/runtime rows fence every competing local writer.
            conn.execute("SELECT id FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint=? FOR UPDATE", (selected["targetFingerprint"],)).fetchall()
            conn.execute("SELECT id FROM learning_catalog_build_items WHERE id=? FOR UPDATE", (ITEM,)).fetchone()
            conn.execute("SELECT id FROM learning_openmaic_runtime_classrooms WHERE id=? FOR UPDATE", (SOURCE_RUNTIME,)).fetchone()
            saved = snapshot(conn, selected, idle=True); assert_source(saved, audit, native)
            revised = reviewed_candidate(conn, sha); require(revised, "real successful editorial review is required")
            archive = {"auditShaId": sha, "sourceRuntime": saved["runtime"], "sourceItem": saved["item"], "sourceOwner": saved["owner"],
                "sourcePackage": saved["package"], "sourceNativeJob": native["job"], "sourceNativeJobRaw": native["jobRaw"],
                "sourceNativeJobSha256": native["jobSha256"], "sourceAgent": native["agent"], "ledger": saved["ledger"], "review": revised["event"]}
            activation_sha = digest(archive); _save(AUDITS / ("activation-" + activation_sha + ".json"), archive)
            stamp = now_ms()
            changed = conn.execute("UPDATE learning_openmaic_runtime_classrooms SET retired_at=?,updated_at=? WHERE id=? AND retired_at IS NULL AND updated_at=?",
                (stamp, stamp, SOURCE_RUNTIME, saved["runtime"]["updated_at"]))
            require(changed.rowcount == 1, "source runtime retirement CAS failed")
            course = revised["course"]
            changed = conn.execute("UPDATE learning_catalog_build_items SET course_id=?,course_version=?,content_receipt_hash=?,content_validation_contract_version=?,content_gate_passed_at=?,updated_at=? "
                "WHERE id=? AND course_id=? AND course_version=? AND content_receipt_hash=? AND updated_at=?",
                (course["id"], course["version"], digest(revised["receipt"]), VALIDATION_SCHEMA, stamp, stamp, ITEM, SOURCE_COURSE,
                 saved["item"]["course_version"], saved["item"]["content_receipt_hash"], saved["item"]["updated_at"]))
            require(changed.rowcount == 1, "item revision CAS failed")
            payload = {**revised["event"], "activationShaId": activation_sha, "sourceRuntimeId": SOURCE_RUNTIME, "sourceNativeJobId": SOURCE_NATIVE_JOB,
                "sourceCourseId": SOURCE_COURSE, "retiredAtMsCount": stamp, "nextAttemptOrdinalCount": 2}
            repo.append_event(conn, plan_id=saved["owner"]["id"], event_type=ACTIVATED, stage=saved["owner"]["stage"], payload=payload, now=stamp)
            changed = conn.execute("UPDATE learning_curriculum_preparation_plans SET lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,hard_deadline_at=NULL,work_unit_kind=NULL,next_run_at=?,updated_at=? "
                "WHERE id=? AND status='running' AND updated_at=? AND (lease_expires_at IS NULL OR lease_expires_at<=?)",
                (stamp, stamp, saved["owner"]["id"], saved["owner"]["updated_at"], stamp))
            require(changed.rowcount == 1, "idle coordinator CAS failed")
            require(activated_revision(conn) is not None, "activated revision did not pass its own authority reader")
            require(repo.reconcile_shared_build(conn, build_id=selected["buildId"], target_fingerprint=selected["targetFingerprint"], now=stamp) >= 1, "normal content reconciliation failed")
            return {"status": "activated_no_runtime_dispatched", **payload}


def main():
    from scripts.generate_one_library_course import LOCK_PATH, emit
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "review", "activate", "status"))
    parser.add_argument("--candidate", default=str(AUDITS / "edited-candidate.json"))
    parser.add_argument("--audit")
    parser.add_argument("--budget-policy")
    parser.add_argument("--confirm-workers-stopped", action="store_true")
    args = parser.parse_args(); args.grade = "primary_6"
    require(args.command == "prepare" or args.audit, "--audit required")
    if args.command in {"review", "activate"}:
        require(args.budget_policy and args.confirm_workers_stopped, "explicit policy and --confirm-workers-stopped required")
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "prepare":
            sha, audit = prepared(args.candidate)
            result = {"status": "prepared_only", "auditShaId": sha, "auditPath": str(AUDITS / (sha + ".json")), "editedFieldCount": len(audit["edits"]), "providerCalls": 0}
        else:
            audit = read_audit(args.audit)
            if args.command == "status":
                conn = Database(AppConfig.from_env().DATABASE_URL).connect()
                try:
                    conn.execute("START TRANSACTION READ ONLY")
                    result = {"started": event(conn, STARTED), "reviewed": event(conn, REVIEWED), "activated": event(conn, ACTIVATED)}
                finally:
                    conn.rollback(); conn.close()
            else:
                result = (review if args.command == "review" else activate)(args, args.audit, audit)
        emit("math2_revision", **result)


if __name__ == "__main__":
    main()
