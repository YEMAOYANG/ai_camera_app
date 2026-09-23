"""One audited repair of the unused ZH6A01.01 classroom input contract.

The rejected Native job and every replaced database row stay in the immutable
audit. A new request gets a new Native job while retaining one Backend Runtime.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

from content.learning_budget_policy import canonical, digest
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from services.lesson_package_validator import (
    formal_runtime_teaching_brief, LessonPackageValidator,
    FORMAL_RUNTIME_PACKAGE_SCHEMA, FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA,
)
from services.progressive_course_generation import validate_progressive_course_for_release, VALIDATION_SCHEMA

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "output/progressive-preview/contract-fixes"
NATIVE = ROOT / "openmaic-runtime/.runtime/OpenMAIC"
RUNTIME = "omfc_fwEg39lIxY5b2BzbFhDjNEqWB27bVSVTis177BSMiX4"
OLD_JOB = "omformal_cd1c0dbf36d3c93d6a10c652"
SESSION = "miraformal_fc6bcce7b0cb5594e7428bd6b37e3e158126446ccb0ef71b102863d17803217b"
PENDING = "progressive_contract_fix_pending"
DISPATCHED = "progressive_contract_fix_dispatched"
APPLIED = "progressive_contract_fix_applied"


def _editorial(conn, identity):
    try:
        from scripts.progressive_preview_editorial import accepted_editorial_candidate
    except ImportError:
        return None
    return accepted_editorial_candidate(conn, identity)


def _event(conn, runtime_id, kind):
    rows = conn.execute("SELECT payload_json FROM learning_curriculum_preparation_events "
        "WHERE event_type=? AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.runtimeId'))=? ORDER BY created_at,id",
        (kind, runtime_id)).fetchall()
    if len(rows) > 1:
        raise RuntimeError("conflicting contract repair events")
    return json.loads(rows[0]["payload_json"]) if rows else None


def _audit(sha):
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise RuntimeError("an exact contract repair audit SHA is required")
    data = json.loads((AUDITS / (sha + ".json")).read_text())
    if digest(data) != sha or data["originals"]["runtime"]["id"] != RUNTIME:
        raise RuntimeError("contract repair archive changed")
    return data


def audited_runtime_request_id(conn, *, runtime_id, canonical_request_id):
    event = _event(conn, runtime_id, PENDING)
    if event is None:
        return canonical_request_id
    audit = _audit(event["auditShaId"])
    if (audit["originals"]["runtime"]["request_id"] != canonical_request_id
            or event.get("runtimeRequestId") != canonical_request_id + ".contractfix1"
            or event.get("runtimeRequestId") != audit["replacement"]["requestId"]):
        raise RuntimeError("contract repair request is outside its immutable authority")
    return event["runtimeRequestId"]


def _native_absence():
    """Direct READ ONLY SQL; do not instantiate stores that run ensureSchema."""
    from dotenv import dotenv_values
    env = dotenv_values(os.environ.get("MIRA_OPENMAIC_PROVIDER_ENV_FILE") or os.environ.get("MIRA_BACKEND_ENV_FILE") or ROOT / "backend/.env")
    url = os.environ.get("MIRA_OPENMAIC_AGENT_DATABASE_URL") or env.get("MIRA_OPENMAIC_AGENT_DATABASE_URL")
    if not url or not url.startswith("postgres"):
        raise RuntimeError("Native readonly PostgreSQL configuration is missing")
    code = """const {Client}=require(process.argv[1]);let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',async()=>{let x=JSON.parse(s),c=new Client({connectionString:x.url});try{await c.connect();await c.query('BEGIN READ ONLY');let a=await c.query('SELECT COUNT(*)::int AS n FROM agent_sessions WHERE id=$1',[x.session]);let b=await c.query('SELECT COUNT(*)::int AS n FROM document_stages WHERE owner_id=$1',[x.owner]);await c.query('ROLLBACK');console.log(JSON.stringify({sessions:a.rows[0].n,stages:b.rows[0].n}));}catch(e){process.exitCode=1;}finally{await c.end();}});"""
    result = subprocess.run(["node", "-e", code, str(NATIVE / "node_modules/pg")],
        input=json.dumps({"url": url, "session": SESSION, "owner": "mira-formal-professional:" + SESSION[11:]}),
        capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Native readonly session/stage verification failed")
    absence = json.loads(result.stdout)
    if absence != {"sessions": 0, "stages": 0}:
        raise RuntimeError("the rejected Native input has an existing session or stage")
    return absence


def _native_files():
    files = {}
    for path in (NATIVE / "data/classroom-jobs" / (OLD_JOB + ".json"),
                 NATIVE / "data/classroom-jobs" / (OLD_JOB + ".formal-dispatch-started.json"),
                 NATIVE / "data/formal-paid-budget-bindings" / (SESSION + ".json")):
        raw = path.read_bytes()
        files[str(path)] = {"sha256": hashlib.sha256(raw).hexdigest(), "value": json.loads(raw)}
    return files


def _snapshot(library, identity):
    files = _native_files()
    native_job = files[str(NATIVE / "data/classroom-jobs" / (OLD_JOB + ".json"))]["value"]
    if (native_job.get("status") != "failed" or native_job.get("error") != "FORMAL_DIFFICULTY_AUTHORITY_MISSING"
            or native_job.get("scenesGenerated") != 0 or native_job.get("totalScenes") != 0
            or native_job.get("result") or native_job.get("classroomId")
            or OpenMaicFullRuntimeClient.formal_input_sha256(native_job["formalInput"]) != native_job["formalInputSha256"]):
        raise RuntimeError("the exact pre-session difficulty failure is no longer available")
    absence = _native_absence()
    created = int(datetime.fromisoformat(native_job["createdAt"].replace("Z", "+00:00")).timestamp() * 1000)
    with library.database.transaction() as conn:
        runtime = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?", (RUNTIME,)).fetchone()
        item = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?", (identity["buildItemId"],)).fetchone()
        owner = conn.execute("SELECT * FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint=?",
                             (identity["targetFingerprint"],)).fetchone()
        if (not runtime or runtime["candidate_build_item_id"] != item["id"] or runtime["upstream_job_id"] != OLD_JOB
                or runtime["status"] != "failed" or runtime["quality_status"] != "rejected"
                or runtime.get("error_code") != "openmaic_formal_generation_failed"
                or runtime.get("upstream_classroom_id") or runtime.get("retired_at") or runtime["attempt_ordinal"] != 1
                or runtime["request_id"] != native_job["runtimeRequestId"] or item["status"] != "course_ready"
                or (item["subject"], item["skill_id"], item["variant_ordinal"]) != ("chinese", "ZH6A01.01", 1)
                or owner["status"] != "running" or owner["stage"] != "generating_content"):
            raise RuntimeError("only the diagnosed original classroom may receive this repair")
        for sql, params in (
            ("SELECT COUNT(*) AS n FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?", (item["id"],)),
            ("SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?", (item["id"],)),
            ("SELECT COUNT(*) AS n FROM learning_sessions WHERE course_id=? AND course_version=?", (runtime["course_id"], runtime["course_version"])),
        ):
            expected = 1 if "learning_openmaic_runtime_classrooms" in sql else 0
            if conn.execute(sql, params).fetchone()["n"] != expected:
                raise RuntimeError("classroom instance, publication receipt or student use prevents predispatch repair")
        budget_key = digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]})
        ledger = list(conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id", (budget_key,)).fetchall())
        editorial = _editorial(conn, identity)
        if any(r["state"] in {"reserved", "dispatched", "unknown"} or int(r["created_at"]) >= created for r in ledger):
            # Editorial review is separately identifiable and can happen after
            # this failure. Its settled entries are allowed by the source audit.
            allowed_reservation = (editorial or {}).get("event", {}).get("verificationReservationId")
            for row in ledger:
                if row["state"] in {"reserved", "dispatched", "unknown"}:
                    raise RuntimeError("an unresolved paid request prevents contract repair")
                if int(row["created_at"]) >= created and row["id"] != allowed_reservation:
                    raise RuntimeError("paid work after the rejected classroom requires exact editorial dispatch evidence")
        package = conn.execute("SELECT * FROM learning_lesson_packages WHERE id=? AND version=?",
                               (runtime["package_id"], runtime["package_version"])).fetchone()
        private = conn.execute("SELECT * FROM learning_lesson_package_private WHERE package_id=? AND package_version=?",
                               (runtime["package_id"], runtime["package_version"])).fetchone()
        source = conn.execute("SELECT * FROM learning_classroom_source_artifacts WHERE id=?", (package["source_artifact_id"],)).fetchone()
        source_job = conn.execute("SELECT * FROM learning_classroom_generation_jobs WHERE id=?", (source["job_id"],)).fetchone()
        old_course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
                                  (item["course_id"], item["course_version"])).fetchone()
        if package["status"] != "candidate" or package.get("published_at") or package.get("retired_at") or int(package["version"]) != 1:
            raise RuntimeError("the source package is already used")
        original_receipt = validate_progressive_course_for_release(conn, course=old_course, expected_lesson_id="ZH6A01.01")
        course, receipt = (editorial["course"], editorial["receipt"]) if editorial else (old_course, original_receipt)
        if editorial and editorial["event"]["sourceCourseId"] != old_course["id"]:
            raise RuntimeError("editorial replacement is not derived from the frozen rejected classroom source")
    return {"originals": {k: dict(v) for k, v in {"runtime": runtime, "item": item, "owner": owner,
            "package": package, "private": private, "source": source, "sourceJob": source_job, "course": old_course}.items()},
        "nativeFiles": files, "nativeAbsence": absence, "paidReservations": [dict(r) for r in ledger],
        "editorialEvent": editorial["event"] if editorial else None, "newCourse": dict(course), "newContentReceipt": receipt}


def _replacement(snapshot, identity, runtime_service):
    original = snapshot["originals"]
    course = snapshot["newCourse"]
    brief, brief_sha, course_sha = formal_runtime_teaching_brief(course)
    if not isinstance(brief.get("difficultyPolicy"), dict):
        raise RuntimeError("the canonical progressive difficulty fix is not installed")
    public = {"schemaVersion": FORMAL_RUNTIME_PACKAGE_SCHEMA, "authority": "mira_backend_candidate_only",
        "buildItemId": identity["buildItemId"], "courseId": course["id"], "courseVersion": course["version"],
        "targetFingerprint": identity["targetFingerprint"], "sourceCourseContentSha256": course_sha,
        "teachingBriefSha256": brief_sha, "teachingBrief": brief, "studentLaunchEligible": False}
    report = LessonPackageValidator().validate_formal_runtime_package(payload=public, build_item_id=identity["buildItemId"],
        course_id=course["id"], course_version=course["version"], target_fingerprint=identity["targetFingerprint"],
        teaching_brief=brief, teaching_brief_sha256=brief_sha, source_course_content_sha256=course_sha)
    source = {"schemaVersion": FORMAL_RUNTIME_PACKAGE_SOURCE_SCHEMA, "buildItemId": identity["buildItemId"],
        "targetFingerprint": identity["targetFingerprint"], "sourceCourseContentSha256": course_sha,
        "teachingBriefSha256": brief_sha, "publicationEligible": False}
    old_manifest = json.loads(original["runtime"]["feature_manifest_json"])
    request_id = original["runtime"]["request_id"] + ".contractfix1"
    contract = deepcopy(old_manifest["generationContract"])
    contract.update(runtimeRequestId=request_id, teachingBrief=brief, teachingBriefSha256=brief_sha,
                    sourceCourseContentSha256=course_sha, difficultyPolicy=brief["difficultyPolicy"])
    contract["course"].update(id=course["id"], version=course["version"], difficultyCode=brief["course"]["difficultyCode"])
    manifest = runtime_service._requested_manifest(old_manifest["enabled"], old_manifest["required"], generation_contract=contract)
    manifest.update(formalRuntimeContract=old_manifest["formalRuntimeContract"], sourceCourseContentSha256=course_sha,
                    teachingBriefSha256=brief_sha, paidBudget=old_manifest["paidBudget"])
    if manifest["paidBudget"].get("authorizationId") != digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]}):
        raise RuntimeError("the repaired contract must retain the exact original budget")
    input_sha = runtime_service._formal_input_sha256(runtime_request_id=request_id, generation_contract=contract,
        formal_contract=manifest["formalRuntimeContract"], paid_budget=manifest["paidBudget"])
    return {"requestId": request_id, "nativeJobId": "omformal_" + hashlib.sha256(request_id.encode()).hexdigest()[:24],
        "formalInputSha256": input_sha, "publicPayload": public, "sourcePayload": source,
        "validationReport": report, "manifest": manifest}


def plan_contract_fix(library, identity, runtime_service):
    snapshot = _snapshot(library, identity)
    audit = {"schemaVersion": "mira.progressive-contract-fix.v1", "identity": identity, **snapshot,
             "replacement": _replacement(snapshot, identity, runtime_service)}
    sha = digest(audit)
    AUDITS.mkdir(parents=True, exist_ok=True)
    path = AUDITS / (sha + ".json")
    if path.exists():
        if json.loads(path.read_text()) != audit:
            raise RuntimeError("contract repair archive path conflicts")
    else:
        with path.open("x") as output:
            path.chmod(0o600)
            json.dump(audit, output, ensure_ascii=False, indent=2)
            output.write("\n")
    return {"auditSha256": sha, "auditPath": str(path), "runtimeId": RUNTIME, "oldNativeJobId": OLD_JOB,
        "newNativeJobId": audit["replacement"]["nativeJobId"], "newRequestId": audit["replacement"]["requestId"],
        "oldCourseId": snapshot["originals"]["course"]["id"], "newCourseId": snapshot["newCourse"]["id"],
        "readyToApply": snapshot["editorialEvent"] is not None,
        "blockers": [] if snapshot["editorialEvent"] else ["independently_accepted_editorial_course_required"],
        "nativeSessions": 0, "nativeStages": 0, "newRuntimeCount": 0, "businessWrites": 0, "providerCalls": 0}


def apply_contract_fix(args, library, identity, runtime_service, preparations):
    audit = _audit(args.expected_contract_fix_sha)
    if audit["identity"] != identity:
        raise RuntimeError("contract repair does not match this scope")
    if audit.get("editorialEvent") is None:
        raise RuntimeError("the original ambiguous question may not launch; wait for the accepted editorial source")
    with library.database.transaction() as conn:
        pending = _event(conn, RUNTIME, PENDING)
    if pending is None:
        preview = plan_contract_fix(library, identity, runtime_service)
        if preview["auditSha256"] != args.expected_contract_fix_sha:
            raise RuntimeError("contract repair source changed since the reviewed preview")
        old, new = audit["originals"], audit["replacement"]
        course = audit["newCourse"]
        with library.database.transaction() as conn:
            current = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=? FOR UPDATE", (RUNTIME,)).fetchone()
            if dict(current) != old["runtime"] or _event(conn, RUNTIME, PENDING):
                raise RuntimeError("the original Runtime changed before contract repair")
            for key, table, where, params in (
                ("item", "learning_catalog_build_items", "id=?", (identity["buildItemId"],)),
                ("owner", "learning_curriculum_preparation_plans", "id=?", (old["owner"]["id"],)),
                ("package", "learning_lesson_packages", "id=? AND version=1", (old["package"]["id"],)),
                ("private", "learning_lesson_package_private", "package_id=? AND package_version=1", (old["package"]["id"],)),
                ("source", "learning_classroom_source_artifacts", "id=?", (old["source"]["id"],)),
                ("sourceJob", "learning_classroom_generation_jobs", "id=?", (old["sourceJob"]["id"],)),
            ):
                locked = conn.execute(f"SELECT * FROM {table} WHERE {where} FOR UPDATE", params).fetchone()
                if not locked or dict(locked) != old[key]:
                    raise RuntimeError("contract repair source row changed: " + key)
            public_json, source_json, report_json = (canonical(new[k]) for k in ("publicPayload", "sourcePayload", "validationReport"))
            conn.execute("UPDATE learning_lesson_packages SET course_id=?,course_version=?,source_course_content_hash=?,public_payload_json=?,public_content_hash=?,validation_report_json=?,updated_at=? WHERE id=? AND version=1 AND status='candidate'",
                (course["id"], course["version"], new["publicPayload"]["sourceCourseContentSha256"], public_json,
                 hashlib.sha256(public_json.encode()).hexdigest(), report_json, now_ms(), old["package"]["id"]))
            conn.execute("UPDATE learning_classroom_source_artifacts SET payload_json=?,source_hash=?,validation_report_json=?,updated_at=? WHERE id=?",
                (source_json, hashlib.sha256(source_json.encode()).hexdigest(), report_json, now_ms(), old["source"]["id"]))
            conn.execute("UPDATE learning_classroom_generation_jobs SET course_id=?,course_version=?,updated_at=? WHERE id=?",
                         (course["id"], course["version"], now_ms(), old["sourceJob"]["id"]))
            conn.execute("UPDATE learning_catalog_build_items SET course_id=?,course_version=?,content_receipt_hash=?,content_validation_contract_version=?,content_gate_passed_at=?,updated_at=? WHERE id=? AND status='course_ready'",
                (course["id"], course["version"], digest(audit["newContentReceipt"]), VALIDATION_SCHEMA, now_ms(), now_ms(), identity["buildItemId"]))
            conn.execute("UPDATE learning_openmaic_runtime_classrooms SET course_id=?,course_version=?,request_id=?,upstream_job_id=NULL,status='pending',quality_status='pending_review',error_code=NULL,error_message_safe=NULL,feature_manifest_json=?,updated_at=? WHERE id=? AND status='failed'",
                (course["id"], course["version"], new["requestId"], canonical(new["manifest"]), now_ms(), RUNTIME))
            pending = {"runtimeId": RUNTIME, "buildItemId": identity["buildItemId"], "auditShaId": args.expected_contract_fix_sha,
                       "runtimeRequestId": new["requestId"], "oldNativeJobId": OLD_JOB, "newNativeJobId": new["nativeJobId"]}
            preparations.append_event(conn, plan_id=old["owner"]["id"], event_type=PENDING,
                                      stage="generating_content", payload=pending, now=now_ms())
            if old["owner"].get("work_unit_kind") not in {None, "coordinator"} or old["owner"].get("bound_catalog_item_id"):
                raise RuntimeError("contract repair cannot release another active content work unit")
            conn.execute("UPDATE learning_curriculum_preparation_plans SET hard_deadline_at=NULL,lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,work_unit_kind=NULL,next_run_at=?,updated_at=? WHERE id=? AND status='running' AND stage='generating_content'",
                         (now_ms(), now_ms(), old["owner"]["id"]))
    if pending.get("auditShaId") != args.expected_contract_fix_sha:
        raise RuntimeError("a different contract repair is already pending")
    new = audit["replacement"]
    from integrations.openmaic_formal_playful import playful_generation_kwargs
    contract = new["manifest"]["generationContract"]
    upstream = runtime_service.client.get_generation_job_by_request_id(new["requestId"], **playful_generation_kwargs(contract))
    if upstream is None:
        if not runtime_service.formal_provider_circuit_status()["dispatchAllowed"]:
            raise RuntimeError("existing Provider circuit is not ready; repaired job was not dispatched")
        with library.database.transaction() as conn:
            if _event(conn, RUNTIME, DISPATCHED):
                raise RuntimeError("the repaired dispatch outcome is unknown; never replay without diagnosis")
            preparations.append_event(conn, plan_id=audit["originals"]["owner"]["id"], event_type=DISPATCHED,
                                      stage="generating_content", payload=pending, now=now_ms())
        upstream = runtime_service.client.start_generation(requirement=canonical(contract),
            enable_web_search=True, enable_image_generation=contract["generation"]["enableImageGeneration"],
            enable_video_generation=contract["generation"]["enableVideoGeneration"], enable_tts=False, agent_mode="generate",
            runtime_request_id=new["requestId"], formal_runtime_contract=new["manifest"]["formalRuntimeContract"],
            professional_creation_policy=contract["professionalCreationPolicy"], paid_budget=new["manifest"]["paidBudget"],
            **playful_generation_kwargs(contract))
    if (upstream.job_id != new["nativeJobId"] or not runtime_service.client.formal_job_identity_matches(upstream,
            runtime_request_id=new["requestId"], formal_input_sha256=new["formalInputSha256"])):
        raise RuntimeError("repaired Native job identity differs from its immutable audit")
    with library.database.transaction() as conn:
        current = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=? FOR UPDATE", (RUNTIME,)).fetchone()
        if current["request_id"] != new["requestId"] or current["feature_manifest_json"] != canonical(new["manifest"]):
            raise RuntimeError("repaired Runtime changed before upstream binding")
        if current["status"] == "pending" and current.get("upstream_job_id") is None:
            runtime_service.repository.mark_generating(conn, runtime_id=RUNTIME, upstream_job_id=upstream.job_id, now=now_ms())
        elif current.get("upstream_job_id") != upstream.job_id:
            raise RuntimeError("repaired Runtime is attached to another Native job")
        if not _event(conn, RUNTIME, APPLIED):
            preparations.append_event(conn, plan_id=audit["originals"]["owner"]["id"], event_type=APPLIED,
                                      stage="generating_content", payload=pending, now=now_ms())
    return {"runtimeId": RUNTIME, "newNativeJobId": upstream.job_id, "auditSha256": args.expected_contract_fix_sha}
