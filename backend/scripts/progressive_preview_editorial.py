"""One audited editorial revision of the approved ZH6A01.01 preview slot.

prepare reads managed files and writes only an immutable local audit. apply
creates a separate job, performs one answer-blind verification, and stages its
accepted candidate. It never changes the source course, item, package or Native
job, and never represents the edit as another model-generation Provider call.
"""
from __future__ import annotations

import argparse
from copy import copy, deepcopy
from datetime import datetime
import fcntl
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from content.learning_budget_policy import digest
from core.security import now_ms
from services.progressive_course_generation import (
    CONTRACT_VERSION, VERIFY_SCHEMA, _provider_call, generation_brief,
    validate_progressive_course, validate_progressive_course_for_release,
)

AUDIT_ROOT = ROOT / "output/progressive-preview/editorial"
NATIVE_DATA = ROOT / "openmaic-runtime/.runtime/OpenMAIC/data"
NATIVE_JOB = NATIVE_DATA / "classroom-jobs/omformal_cd1c0dbf36d3c93d6a10c652.json"
SOURCE_REQUEST = "catalog_gen_7b6c5e725bb1003f70897ae29f2e4059a82100a6cf0e8129.correction3"
EDITORIAL_REQUEST = SOURCE_REQUEST.removesuffix(".correction3") + ".editorial1"
SOURCE_COURSE = "progressive_d78edf9c1e3c620a0ebeaf35"
SOURCE_FILES = {
    "progressive_generation": "bf7088179f6efd14a749c06d936ca2164ecbdcb3bed7e8f4e4a3f352911264b6/fdf107d5871468c62dd7db8a41ee70bf5c931dd65a97a5615b15a84c00423f4d.json",
    "progressive_verification": "7a0373de3fbd643466528f4641f497ea941da4c04e028721fd388eeea3b58f16/b04c608e663472b00533e7cbb67030af0e5f39fb17ae114cb8fd7c96b985b67b.json",
}
EDITS = (
    ("independent_1", "B", "桂花树的香味让人心情愉快。", "我觉得桂花的香味最好闻。"),
    ("independent_2", "A", "本周三下午学校将举行消防演习。", "学校通知写明，消防演习定于本周三下午举行。"),
    ("independent_2", "B", "消防演习能提高大家的安全意识。", "我认为学校应该每学期安排一次消防演习。"),
    ("independent_2", "C", "所有班级都要按路线撤离到操场。", "演习记录显示，所有班级都已按路线撤离到操场。"),
    ("independent_3", "A", "图书馆新购的绘本很受低年级同学欢迎。", "我认为新购的绘本很精彩。"),
)
FIELD_EDITS = (
    ("independent_2", "hint", "观点是个人判断，常用“能”“应该”等。",
     "观点表达个人评价或建议；结合句子内容和信息来源判断。"),
    ("independent_2", "explanation", "B句是个人对消防演习作用的判断，属于观点；A句是活动安排，C句是规定，都是可核实的事实性信息。",
     "B句表达个人提出的演习安排建议；A句转述学校通知中的时间，C句记录演习完成情况，后两句均可核实。"),
    ("independent_3", "explanation", "B句记录了借出绘本的具体数量，可以核实；A句含主观评价“很受欢迎”，C句是建议，都不是事实陈述。",
     "B句记录借出绘本的具体数量，可以核实；A句表达个人对绘本的评价，C句提出采购建议。"),
)
STARTED = "progressive_editorial_started"
SUCCEEDED = "progressive_editorial_succeeded"


def _file(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text()) != data:
            raise RuntimeError("immutable editorial audit differs")
        return
    with path.open("x", encoding="utf-8") as out:
        path.chmod(0o600)
        json.dump(data, out, ensure_ascii=False, sort_keys=True, indent=2)
        out.write("\n")


def _identity():
    from scripts.generate_progressive_preview import preview_identities
    identities = preview_identities("primary_6")
    selected = [i for i in identities if i["slot"]["lessonId"] == "ZH6A01.01"
                and i["slot"]["variantOrdinal"] == 1]
    if len(selected) != 1:
        raise RuntimeError("the exact approved Chinese first slot is unavailable")
    return selected[0], identities


def edit_candidate(original):
    edited = deepcopy(original)
    questions = edited["content"]["questions"]
    if len(questions) != 6 or len({q["id"] for q in questions}) != 6:
        raise RuntimeError("source question set changed")
    changes = []
    for question_id, choice_id, before, after in EDITS:
        question = next((q for q in questions if q["id"] == question_id), None)
        matches = [c for c in (question or {}).get("choices", []) if c["id"] == choice_id]
        if len(matches) != 1 or matches[0]["label"] != before:
            raise RuntimeError("editorial source does not match the exact old/new allowlist")
        matches[0]["label"] = after
        changes.append({"questionId": question_id, "choiceId": choice_id, "before": before, "after": after})
    for question_id, field, before, after in FIELD_EDITS:
        question = next((q for q in questions if q["id"] == question_id), None)
        if not question or question.get(field) != before:
            raise RuntimeError("editorial private explanation differs from the exact allowlist")
        question[field] = after
        changes.append({"questionId": question_id, "field": field, "before": before, "after": after})
    return edited, changes


def prepare_audit():
    identity, _ = _identity()
    native, native_file = _file(NATIVE_JOB)
    contract = json.loads(native["formalInput"]["requirement"])
    if (native.get("status") != "failed" or native.get("error") != "FORMAL_DIFFICULTY_AUTHORITY_MISSING"
            or native.get("scenesGenerated") != 0 or native.get("totalScenes") != 0
            or native.get("stageId") or native.get("classroomId")
            or contract.get("buildItemId") != identity["buildItemId"]
            or contract.get("targetFingerprint") != identity["targetFingerprint"]
            or contract["course"]["id"] != SOURCE_COURSE):
        raise RuntimeError("source Native job is not the exact zero-scene preflight failure")
    records, archives = {}, []
    for phase, relative in SOURCE_FILES.items():
        row, file = _file(NATIVE_DATA / "formal-courseware-provider-responses" / relative)
        expected = SOURCE_REQUEST + (":verify" if phase == "progressive_verification" else "")
        if row.get("phase") != phase or row.get("requestId") != expected or not row.get("responseId"):
            raise RuntimeError("original model reply identity changed")
        records[phase] = json.loads(row["content"])
        archives.append({**file, "phase": phase, "requestId": expected,
            "inputSha256": row["inputSha256"], "responseId": row["responseId"],
            "providerId": row.get("providerId"), "responseModelId": row.get("responseModelId")})
    original = records["progressive_generation"]["candidateCourse"]
    review = records["progressive_verification"]
    review = review.get("verification", review)
    validated, receipt = validate_progressive_course(original, brief=generation_brief("ZH6A01.01"),
        verification=review, request_id=SOURCE_REQUEST)
    if validated["id"] != SOURCE_COURSE or validated["version"] != contract["course"]["version"]:
        raise RuntimeError("saved model candidate is not the accepted source course")
    edited, changes = edit_candidate(original)
    return {"schemaVersion": "mira.progressive-editorial-audit.v1", "identity": identity,
        "editorialRequestId": EDITORIAL_REQUEST, "sourceGenerationRequestId": SOURCE_REQUEST,
        "sourceCourseId": SOURCE_COURSE, "sourceCourseVersionId": validated["version"],
        "sourceContentReceiptShaId": digest(receipt), "archives": archives,
        "nativePreflight": {**native_file, "jobId": native["id"], "error": native["error"],
            "sourcePackageId": contract["course"]["packageId"]},
        "originalCandidate": original, "editedCandidate": edited, "edits": changes,
        "editedContentSha256": digest(edited["content"]),
        "provenance": {"kind": "model_generated_editorial_revision", "generationProviderCalls": 0,
            "requiredNewVerificationCalls": 1, "sourceModelRepliesPreserved": True}}


def read_editorial_audit(event, identity):
    sha = event.get("auditShaId", "")
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise RuntimeError("invalid editorial audit identity")
    audit = json.loads((AUDIT_ROOT / (sha + ".json")).read_text())
    if (digest(audit) != sha or audit["identity"] != identity or audit != prepare_audit()
            or event.get("editorialRequestId") != EDITORIAL_REQUEST):
        raise RuntimeError("editorial audit or original model evidence changed")
    return audit


def _event(conn, identity, kind):
    rows = conn.execute("SELECT e.payload_json,p.target_fingerprint FROM learning_curriculum_preparation_events e "
        "JOIN learning_curriculum_preparation_plans p ON p.id=e.plan_id WHERE p.catalog_build_id=? "
        "AND e.event_type=? AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.buildItemId'))=?",
        (identity["buildId"], kind, identity["buildItemId"])).fetchall()
    if len(rows) > 1 or any(r["target_fingerprint"] != identity["targetFingerprint"] for r in rows):
        raise RuntimeError("conflicting editorial events")
    return json.loads(rows[0]["payload_json"]) if rows else None


def accepted_editorial_candidate(conn, identity):
    event = _event(conn, identity, SUCCEEDED)
    if not event:
        return None
    audit = read_editorial_audit(event, identity)
    started = _event(conn, identity, STARTED)
    if not started or started.get("auditShaId") != event["auditShaId"]:
        raise RuntimeError("editorial source audit is missing")
    job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=?",
        (event["generationJobId"],)).fetchone()
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
        (event["courseId"], event["courseVersionId"])).fetchone()
    if (not job or not course or job["request_id"] != EDITORIAL_REQUEST
            or job["status"] not in {"validated", "partially_validated"}
            or course["generation_request_id"] != EDITORIAL_REQUEST
            or digest(json.loads(course["content_json"])) != audit["editedContentSha256"]):
        raise RuntimeError("editorial accepted candidate provenance changed")
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id="ZH6A01.01")
    if digest(receipt) != event["contentReceiptShaId"]:
        raise RuntimeError("editorial accepted receipt changed")
    return {"course": course, "job": job, "receipt": receipt, "event": event}


def _assert_source(conn, identity, audit):
    item = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE",
                        (identity["buildItemId"],)).fetchone()
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?",
        (SOURCE_COURSE, audit["sourceCourseVersionId"])).fetchone()
    job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=?", (SOURCE_REQUEST,)).fetchone()
    if (not item or not course or not job or item["course_id"] != SOURCE_COURSE
            or item["course_version"] != course["version"] or course["status"] != "validated"
            or course["generation_request_id"] != SOURCE_REQUEST or job["status"] != "validated"
            or digest(json.loads(course["content_json"])) != digest(audit["originalCandidate"]["content"])):
        raise RuntimeError("original accepted course or slot changed")
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id="ZH6A01.01")
    if digest(receipt) != audit["sourceContentReceiptShaId"]:
        raise RuntimeError("original course receipt changed")
    if conn.execute("SELECT COUNT(*) AS count FROM learning_sessions WHERE course_id=?", (SOURCE_COURSE,)).fetchone()["count"]:
        raise RuntimeError("source course has a learning session; editorial replacement forbidden")
    runtimes = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?",
                           (identity["buildItemId"],)).fetchall()
    if (len(runtimes) != 1 or runtimes[0]["upstream_job_id"] != audit["nativePreflight"]["jobId"]
            or runtimes[0].get("upstream_classroom_id") or runtimes[0].get("session_id")
            or runtimes[0]["status"] != "failed"):
        raise RuntimeError("only the original failed zero-stage Native runtime may be edited")
    auth_id = digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]})
    reservations = conn.execute("SELECT id,state,created_at FROM learning_budget_reservations WHERE authorization_id=?", (auth_id,)).fetchall()
    if any(r["state"] in {"reserved", "dispatched", "unknown"} for r in reservations):
        raise RuntimeError("unresolved paid reservation; no editorial review allowed")
    # Eight settled content calls preceded this editor: base + correction1/2/3,
    # each with one generation and one review. Native failed before its first call.
    native_started = json.loads(NATIVE_JOB.read_text())["createdAt"]
    native_started_ms = int(datetime.fromisoformat(native_started.replace("Z", "+00:00")).timestamp() * 1000)
    if (sum(r["state"] == "settled" for r in reservations) != 8
            or any(int(r["created_at"]) >= native_started_ms for r in reservations)):
        raise RuntimeError("paid history differs from the eight archived content calls")
    return item, course, job, {r["id"] for r in reservations}


def apply_audit(args, audit, sha):
    from scripts.generate_one_library_course import LOCK_PATH, emit, operator_app
    from scripts.generate_progressive_preview import assert_preview_policy
    from services.course_library_service import CourseLibraryService
    from services.service_factory import (_catalog_paid_budget_environment,
        dynamic_learning_course_generation_service, learning_curriculum_preparation_service)
    from services.progressive_contract_fix import _native_absence
    identity, identities = _identity()
    if not args.confirm_workers_stopped:
        raise RuntimeError("--confirm-workers-stopped is required")
    assert_preview_policy(args.budget_policy, identities)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        app = operator_app(args)
        with app.app_context():
            _native_absence()
            preparation = learning_curriculum_preparation_service()
            library = CourseLibraryService(app.config["DATABASE_URL"], grade_code="primary_6",
                preparation_repository=preparation.repository)
            generator = copy(dynamic_learning_course_generation_service())
            adapter = copy(generator.progressive_adapter)
            if adapter.fake_mode or adapter.provider_name != "openmaic_runtime":
                raise RuntimeError("editorial requires the real normal answer-blind verifier")
            generator.adapter = adapter
            brief = generation_brief("ZH6A01.01")
            with library.database.transaction() as conn:
                accepted = accepted_editorial_candidate(conn, identity)
                if accepted:
                    emit("editorial_already_staged", **accepted["event"])
                    return
                _item, _course, source_job, previous_reservation_ids = _assert_source(conn, identity, audit)
                if _event(conn, identity, STARTED) or conn.execute("SELECT id FROM learning_course_generation_jobs WHERE request_id=?", (EDITORIAL_REQUEST,)).fetchone():
                    raise RuntimeError("editorial already dispatched; inspect the retained result, never resend")
                owner = conn.execute("SELECT id FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? AND library_target_fingerprint=?",
                    (identity["buildId"], identity["targetFingerprint"])).fetchone()
                if not owner:
                    raise RuntimeError("exact library preparation owner missing")
                job, created = generator.repository.create_or_get_job(conn, request_id=EDITORIAL_REQUEST,
                    grade_code="primary_6", subject="chinese", node_code="ZH6A01.01",
                    curriculum_version=brief["binding"]["curriculumVersion"], boundary_version=source_job["boundary_version"],
                    generator="openmaic", provider=source_job["provider"], model=source_job["model"],
                    prompt_version=CONTRACT_VERSION, requested_candidate_count=1,
                    generation_spec={"brief": brief, "editorialAuditShaId": sha, "editorialProvenance": audit}, now=now_ms())
                if not created:
                    raise RuntimeError("editorial job already exists")
                event = {"buildItemId": identity["buildItemId"], "auditShaId": sha,
                    "editorialRequestId": EDITORIAL_REQUEST, "generationJobId": job["id"],
                    "sourceCourseId": SOURCE_COURSE, "sourceCourseVersionId": audit["sourceCourseVersionId"],
                    "sourceGenerationJobId": source_job["id"], "generationProviderCallCount": 0}
                preparation.repository.append_event(conn, plan_id=owner["id"], event_type=STARTED,
                    stage="generating_content", payload=event, now=now_ms())
                generator.repository.mark_job_generating(conn, job_id=job["id"], now=now_ms())
            command = SimpleNamespace(build_item_id=identity["buildItemId"], grade_code="primary_6",
                subject="chinese", boundary={"skillId": "ZH6A01.01"})

            def exact_environment(payload):
                assert_preview_policy(args.budget_policy, identities)
                if (payload.get("schemaVersion") != VERIFY_SCHEMA or payload.get("requestId") != EDITORIAL_REQUEST + ":verify"
                        or payload.get("brief") != brief or audit != prepare_audit()):
                    raise RuntimeError("editorial adapter only permits this one exact verification")
                return _catalog_paid_budget_environment(command)

            adapter.execution_environment = exact_environment
            try:
                verification = _provider_call(generator, request_id=EDITORIAL_REQUEST + ":verify", schema=VERIFY_SCHEMA,
                    brief=brief, candidate=audit["editedCandidate"])
                _save(AUDIT_ROOT / (sha + "-verification.json"), verification)
                course, report = validate_progressive_course(audit["editedCandidate"], brief=brief,
                    verification=verification, request_id=EDITORIAL_REQUEST)
                with generator.repository.transaction() as conn:
                    candidate, _ = generator.repository.create_or_get_candidate(conn, job_id=job["id"], ordinal=1,
                        course=course, now=now_ms())
                    generator.repository.mark_candidate_validated(conn, candidate_id=candidate["id"], validation=report, now=now_ms())
                staged, _ = generator.repository.stage_candidate(candidate_id=candidate["id"], now=now_ms())
                with library.database.transaction() as conn:
                    auth_id = digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]})
                    ledger = conn.execute("SELECT id,state FROM learning_budget_reservations WHERE authorization_id=?", (auth_id,)).fetchall()
                    new_reservations = [r for r in ledger if r["id"] not in previous_reservation_ids]
                    if (len(new_reservations) != 1 or new_reservations[0]["state"] != "settled"
                            or any(r["state"] in {"reserved", "dispatched", "unknown"} for r in ledger)
                            or not previous_reservation_ids.issubset({r["id"] for r in ledger})):
                        raise RuntimeError("the single editorial verification has no exact settled reservation")
                    receipt = validate_progressive_course_for_release(conn, course=staged, expected_lesson_id="ZH6A01.01")
                    event = {**event, "courseId": staged["id"], "courseVersionId": staged["version"],
                        "contentReceiptShaId": digest(receipt), "verificationProviderCallCount": 1,
                        "verificationReservationId": new_reservations[0]["id"]}
                    preparation.repository.append_event(conn, plan_id=owner["id"], event_type=SUCCEEDED,
                        stage="generating_content", payload=event, now=now_ms())
                emit("editorial_staged_no_rebinding", **event)
            except Exception as exc:
                generator._persist_failure(job_id=job["id"], code=str(getattr(exc, "code", "editorial_review_failed")),
                    message=str(getattr(exc, "message", str(exc))))
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "apply"))
    parser.add_argument("--audit", help="Exact immutable audit JSON emitted by prepare")
    parser.add_argument("--budget-policy", help="Existing approved six-slot production policy; required for apply")
    parser.add_argument("--confirm-workers-stopped", action="store_true")
    args = parser.parse_args()
    args.grade = "primary_6"
    try:
        audit = prepare_audit()
        sha = digest(audit)
        path = AUDIT_ROOT / (sha + ".json")
        if args.command == "prepare":
            _save(path, audit)
            print(json.dumps({"status": "prepared_read_only", "auditPath": str(path), "auditShaId": sha,
                "editorialRequestId": EDITORIAL_REQUEST, "edits": audit["edits"], "providerCalls": 0,
                "databaseWrites": 0, "applyRequiresLiveNoSessionNoClassroomPaidCheck": True}, ensure_ascii=False), flush=True)
            return 0
        if not args.audit or Path(args.audit).resolve() != path.resolve() or json.loads(path.read_text()) != audit:
            raise RuntimeError("apply requires the exact prepared immutable audit")
        apply_audit(args, audit, sha)
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "code": getattr(exc, "code", type(exc).__name__),
            "message": str(exc)}, ensure_ascii=False), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
