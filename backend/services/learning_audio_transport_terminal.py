"""One exact completed local TTS transport; its unknown financial hold is immutable.

This is evidence of a returned local promise, not evidence of the vendor outcome.
No reservation, authorization, Native job, audio record or settlement is updated.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

from content.learning_budget_policy import canonical, digest
from core.security import now_ms
from repositories.learning_budget_repository import LearningBudgetRepository

ROOT = Path(__file__).resolve().parents[2]
NATIVE = ROOT / "openmaic-runtime/.runtime/OpenMAIC"
ARCHIVES = ROOT / "output/progressive-preview/audio-terminal"
EVENT = "audio_transport_terminal"
SCHEMA = "mira.learning.exact-audio-transport-terminal.v1"
RESERVATION = "5f40e482a9527db43dd49c841b46cbe1cbf0ba1c22c3838e7a4cf72b74593b47"
AUTHORIZATION = "278b0a430b952da40501b054c3eb91c9f2c92f092570cc16af9b1d6271194f5e"
RUNTIME = "omfc_PZVWPeoFgDxk4NJihaoTaCBUhJCc9Crw4sehbWBABAI"
REQUEST = "mira-formal-runtime-catalog_build_item_8c465a74b18ef347a19f52b7-attempt-1"
ITEM = "catalog_build_item_8c465a74b18ef347a19f52b7"
JOB = "omformal_d961effd180ea347e6b1b0bf"
JOB_SHA = "1736671f9f79ad50472814c523f7ea971d658f2ec69a6dfd2ca8945b3fa29eff"
INPUT_SHA = "8b47d84758d45e60c369b11bf4ff5d092edea1ff49e46c2adadc3f609b213f5b"
SESSION = "miraformal_b70ae221b3382f39cd1ff5bde07bef6dcba3f59bd205cb6c4e8278706ea7a0f3"
OWNER = "mira-formal-professional:" + SESSION[11:]
PROMPT_SHA = "67d0a9b423c123fb273bf04543e94ba65cd13df59c3923fba5dd00c2a209f56f"
STAGE = "stage-ZlKdLz74QS"
TTS = "formal_tts_002ae01cc48475d2c4b525d751847862d87d4c9d7360d4ab"
TTS_SHA = "bef98a161c52f283cc9aa3f69cf78c88791f356bdf239e552b30d677325c72b4"
TEXT = "所以第三步，证据是可核实的事实，用来支持一个观点。先分清楚，后面我们还要自己来辨一辨。"
SCOPE = {"purpose": "production", "gradeCode": "primary_6", "subject": "chinese",
         "courseId": "catalog-item:" + ITEM,
         "courseVersion": "6871f5fd296bbe0293055ee9d9af80e740b9c66a1d23e5266d80d0c2d4496e67",
         "productionJobId": ITEM, "userId": None, "sessionId": None,
         "approvalReference": "grade-build:c3adfddc5fa5884ff594667f3cb56e131d6ce19a15e41d2d7fe7ce27961e98dd"}
JOB_PATH = NATIVE / "data/classroom-jobs" / (JOB + ".json")
TTS_PATH = NATIVE / "data/formal-audio/jobs/tts/ddb33429572573190c53920e7f0ba57b5a8309bcee912e9f0d615f7af33ab5d7.json"


def _require(condition, message="exact audio transport evidence changed"):
    if not condition:
        raise RuntimeError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _js_sha(value):
    return _sha(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _at(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _native_proof(job):
    """Direct readonly SQL; never instantiate an Agent store with schema writes."""
    from dotenv import dotenv_values
    env = dotenv_values(os.environ.get("MIRA_OPENMAIC_PROVIDER_ENV_FILE")
        or os.environ.get("MIRA_BACKEND_ENV_FILE") or ROOT / "backend/.env")
    url = os.environ.get("MIRA_OPENMAIC_AGENT_DATABASE_URL") or env.get("MIRA_OPENMAIC_AGENT_DATABASE_URL")
    _require(url and url.startswith("postgres"), "Native readonly configuration missing")
    code = r"""const {Client}=require(process.argv[1]),crypto=require('node:crypto');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+':'+canonical(v)).join(',')+'}';
let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',async()=>{let x=JSON.parse(s),c=new Client({connectionString:x.url});try{
await c.connect();await c.query('BEGIN READ ONLY');
let a=await c.query('SELECT id,owner_id,prompt,stage_id,active_stage_id,status,attempt,deleted_at,cancel_requested_at FROM agent_sessions WHERE id=$1',[x.session]);
let b=await c.query('SELECT id,owner_id FROM document_stages WHERE id=$1',[x.stage]);
let n=await c.query("SELECT COUNT(*)::int AS n FROM agent_sessions WHERE deleted_at IS NULL AND status IN ('queued','running')");
await c.query('ROLLBACK');let r=a.rows[0];if(!r||a.rows.length!==1)throw Error('session');
r.promptSha256=sha(r.prompt);delete r.prompt;
let input=canonical(x.job.formalInput); console.log(JSON.stringify({session:r,stage:b.rows,activeSessions:n.rows[0].n,
formalInputSha256:sha(input),derivedSessionId:'miraformal_'+sha(x.job.runtimeRequestId+'\n'+input)}));
}catch(e){process.exitCode=1;}finally{await c.end();}});"""
    result = subprocess.run(["node", "-e", code, str(NATIVE / "node_modules/pg")],
        input=json.dumps({"url": url, "session": SESSION, "stage": STAGE, "job": job}),
        capture_output=True, text=True, timeout=20)
    _require(result.returncode == 0, "Native readonly terminal-session verification failed")
    proof = json.loads(result.stdout)
    _validate_proof(proof)
    return proof


def _validate_proof(proof):
    row = proof["session"]
    _require(proof["activeSessions"] == 0 and proof["formalInputSha256"] == INPUT_SHA
        and proof["derivedSessionId"] == SESSION)
    _require(row["id"] == SESSION and row["owner_id"] == OWNER and row["status"] == "succeeded"
        and row["attempt"] == 0 and row["promptSha256"] == PROMPT_SHA
        and row["deleted_at"] is None and row["cancel_requested_at"] is None
        and row["stage_id"] == "stage-miraform" and row["active_stage_id"] is None)
    _require(proof["stage"] == [{"id": STAGE, "owner_id": OWNER}])


def _rows(conn):
    row = conn.execute("SELECT * FROM learning_budget_reservations WHERE id=?", (RESERVATION,)).fetchone()
    auth = conn.execute("SELECT * FROM learning_budget_authorizations WHERE id=?", (AUTHORIZATION,)).fetchone()
    _require(row is not None and auth is not None)
    return dict(row), dict(auth)


def _validate_plan(plan):
    _require(set(plan) == {"schemaVersion", "scope", "capturedAt", "localTransportEndedAt", "nativeJobRaw",
        "ttsRaw", "nativeProof", "reservation", "authorization", "sourceEvents", "runtime"})
    _require(plan["schemaVersion"] == SCHEMA and plan["scope"] == "local_transport_concurrency_only")
    _require(_sha(plan["nativeJobRaw"].encode()) == JOB_SHA and _sha(plan["ttsRaw"].encode()) == TTS_SHA)
    job, tts = json.loads(plan["nativeJobRaw"]), json.loads(plan["ttsRaw"])
    _require(job["id"] == JOB and job["runtimeRequestId"] == REQUEST and job["formalInputSha256"] == INPUT_SHA
        and job["status"] == "failed" and job["error"] == "FORMAL_AUDIO_TTS_INCOMPLETE:12:ambiguous")
    _require(job["formalInput"]["paidBudget"] == {"schemaVersion": "mira.learning.paid-budget-binding.v1",
        "required": True, "authorizationId": AUTHORIZATION})
    _require(tts["requestId"] == TTS and tts["state"] == "ambiguous"
        and tts["safeErrorCode"] == "provider_outcome_unknown" and tts["classroomId"] == STAGE
        and tts["textSha256"] == _sha(TEXT.encode()) and not tts.get("audioSha256"))
    _require(plan["localTransportEndedAt"] == _at(job["completedAt"])
        and _at(tts["providerAttemptedAt"]) < _at(tts["completedAt"]) <= plan["localTransportEndedAt"] <= plan["capturedAt"])
    _validate_proof(plan["nativeProof"])
    row, auth = plan["reservation"], plan["authorization"]
    _require(row["id"] == RESERVATION and row["authorization_id"] == AUTHORIZATION and row["state"] == "unknown"
        and all(row[k] is None for k in ("actual_units_json", "settlement_sha256", "provider_request_id", "settled_at")))
    _require(auth["id"] == AUTHORIZATION and json.loads(auth["scope_json"]) == SCOPE and auth["revoked_at"] is None)
    _require(digest({"schema": "mira.catalog-paid-budget.v1", "scope": SCOPE}) == AUTHORIZATION)
    identity = {k: tts[k] for k in ("classroomId", "classroomContentSha256", "subject", "teacherProfileId",
        "teacherProfileVersion", "teacherProfileSha256", "teacherGender", "sceneId", "sceneOrder", "actionId", "narrationSegmentId")}
    request = {"requestId": TTS, **identity, "text": TEXT, "textSha256": tts["textSha256"]}
    request_sha = _js_sha({"provider": "qwen-tts", "model": "qwen3-tts-flash", "request": request,
                           "maxUnits": {"calls": 1, "characters": len(TEXT)}})
    _require(request_sha == row["request_sha256"]
        and row["dispatch_id"] == "runtime:" + _js_sha([AUTHORIZATION, SESSION + ":completion", request_sha]))
    _require(row["request_identity_sha256"] == "623ff388c76e12322d66344014e0d1c3f36cb2183cfc4a13c95626414ae2b6d6")
    events = plan["sourceEvents"]
    _require([e["event_type"] for e in events] == ["reserved", "dispatched", "unknown"]
        and all(e["reservation_id"] == RESERVATION for e in events)
        and json.loads(events[-1]["evidence_json"]) == {"reasonCode": "provider_result_unknown"}
        and row["dispatched_at"] <= events[-1]["created_at"] <= plan["localTransportEndedAt"])
    runtime = plan["runtime"]
    _require(runtime["id"] == RUNTIME and runtime["request_id"] == REQUEST
        and runtime["candidate_build_item_id"] == ITEM and runtime["upstream_job_id"] == JOB
        and runtime["status"] == "generating" and runtime.get("retired_at") is None)
    return plan


def _validate_current(plan, row, auth):
    _require(row == plan["reservation"])
    # A later normal revocation cannot reopen a completed local transport.
    # No scope, budget, price, expiry, creation or policy field may change.
    expected = dict(plan["authorization"])
    revoked = auth.get("revoked_at")
    _require(revoked is None or type(revoked) is int and plan["capturedAt"] <= revoked <= now_ms())
    expected["revoked_at"] = revoked
    _require(auth == expected)


def _audit(sha):
    _require(isinstance(sha, str) and len(sha) == 64 and all(c in "0123456789abcdef" for c in sha))
    plan = json.loads((ARCHIVES / (sha + ".json")).read_text())
    _require(digest(plan) == sha)
    return _validate_plan(plan)


def _events(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM learning_budget_events WHERE reservation_id=? AND event_type=? ORDER BY id",
        (RESERVATION, EVENT)).fetchall()]


def verified_audio_terminal_ids(conn, *, pending_rows):
    if not any(r.get("id") == RESERVATION and r.get("state") == "unknown" for r in pending_rows):
        return set()
    try:
        events = _events(conn)
        _require(len(events) == 1)
        event = events[0]
        evidence = json.loads(event["evidence_json"])
        _require(set(evidence) == {"schemaVersion", "auditSha256", "reservationId"}
            and evidence["schemaVersion"] == SCHEMA and evidence["reservationId"] == RESERVATION)
        plan = _audit(evidence["auditSha256"])
        _require(event["created_at"] >= plan["capturedAt"])
        _validate_current(plan, *_rows(conn))
        return {RESERVATION}
    except (RuntimeError, ValueError, KeyError, TypeError, OSError):
        return set()


def assert_selected_audio_terminal(conn, *, identity, runtime_id):
    _require(identity["scope"] == SCOPE and identity["buildItemId"] == ITEM and runtime_id == RUNTIME,
             "audio terminal exception is restricted to its original course and Runtime")
    rows = [dict(r) for r in conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? AND state IN ('reserved','dispatched','unknown')",
        (AUTHORIZATION,)).fetchall()]
    _require(len(rows) == 1 and rows[0]["id"] == RESERVATION and rows[0]["state"] == "unknown"
        and verified_audio_terminal_ids(conn, pending_rows=rows) == {RESERVATION},
        "active or unverified Provider outcome prevents saved-stage continuation")


def _preflight(conn):
    _require(conn.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()["n"] == 0,
             "an active Provider call prevents terminal audit")
    rows = conn.execute("SELECT id FROM learning_budget_reservations WHERE authorization_id=? AND state='unknown'", (AUTHORIZATION,)).fetchall()
    _require([r["id"] for r in rows] == [RESERVATION], "this scope has another unresolved Provider result")
    raw_job, raw_tts = JOB_PATH.read_text(), TTS_PATH.read_text()
    _require(_sha(raw_job.encode()) == JOB_SHA and _sha(raw_tts.encode()) == TTS_SHA, "original Native/audio evidence changed; no blind replay")
    row, auth = _rows(conn)
    source_events = [dict(r) for r in conn.execute("SELECT * FROM learning_budget_events WHERE reservation_id=? AND event_type<>? ORDER BY id", (RESERVATION, EVENT)).fetchall()]
    runtime = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?", (RUNTIME,)).fetchone()
    _require(runtime is not None)
    plan = {"schemaVersion": SCHEMA, "scope": "local_transport_concurrency_only", "capturedAt": now_ms(),
        "localTransportEndedAt": _at(json.loads(raw_job)["completedAt"]), "nativeJobRaw": raw_job, "ttsRaw": raw_tts,
        "nativeProof": _native_proof(json.loads(raw_job)), "reservation": row, "authorization": auth,
        "sourceEvents": source_events, "runtime": dict(runtime)}
    return _validate_plan(plan)


def prepare(database):
    conn = database.connect()
    try:
        conn.execute("SET TRANSACTION READ ONLY")
        _require(not _events(conn), "an audit already exists; do not prepare another")
        plan = _preflight(conn)
    finally:
        conn.rollback()
        conn.close()
    sha = digest(plan)
    ARCHIVES.mkdir(parents=True, exist_ok=True)
    path = ARCHIVES / (sha + ".json")
    with path.open("x", encoding="utf-8") as output:
        path.chmod(0o600)
        output.write(canonical(plan) + "\n")
    return {"auditPath": str(path), "auditSha256": sha, "reservationId": RESERVATION,
        "databaseWrites": 0, "providerCalls": 0, "financialState": "unknown", "fundsReleased": False}


def apply(database, expected_sha):
    plan = _audit(expected_sha)
    with database.transaction() as conn:
        # Same InnoDB row lock as normal budget writers, without even changing revision.
        _require(conn.execute("SELECT id FROM learning_budget_control WHERE id=1 FOR UPDATE").fetchone() is not None)
        existing = _events(conn)
        if existing:
            _require(len(existing) == 1 and json.loads(existing[0]["evidence_json"]).get("auditSha256") == expected_sha
                and verified_audio_terminal_ids(conn, pending_rows=[plan["reservation"]]) == {RESERVATION})
            return {"status": "already_recorded", "auditSha256": expected_sha}
        current = _preflight(conn)
        _require({k: v for k, v in current.items() if k != "capturedAt"}
                 == {k: v for k, v in plan.items() if k != "capturedAt"}, "preflight state changed; new diagnosis required")
        LearningBudgetRepository(database).event(conn, RESERVATION, EVENT,
            {"schemaVersion": SCHEMA, "auditSha256": expected_sha, "reservationId": RESERVATION}, now_ms())
        _validate_current(plan, *_rows(conn))
        _require(verified_audio_terminal_ids(conn, pending_rows=[plan["reservation"]]) == {RESERVATION})
    return {"status": "recorded", "auditSha256": expected_sha, "financialState": "unknown", "fundsReleased": False,
        "providerCalls": 0, "reservationUpdates": 0, "authorizationUpdates": 0}
