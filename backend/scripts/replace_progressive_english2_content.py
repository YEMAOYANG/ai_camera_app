"""Prepare, generate and activate one unexposed English2 replacement.

The original accepted course/verdict remains immutable. A distinct human review
rejects its use, and a new full model candidate receives normal blind review.
Each command is explicit; generation cannot be replayed after a start event.
"""
from __future__ import annotations
import argparse
from copy import copy
import fcntl
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from content.learning_budget_policy import digest
from core.config import AppConfig
from core.database import Database
from core.security import now_ms
from scripts.generate_one_library_course import LOCK_PATH, operator_app, assert_search_budget_ready
from scripts.generate_progressive_preview import preview_identities, preview_inventory, assert_preview_scope, assert_preview_policy
from scripts.progressive_preview_editorial import _save
from scripts.resume_progressive_content_owner import idle_processes
from services.progressive_preruntime_replacement import (
    ITEM, LESSON, SOURCE_COURSE, SOURCE_REQUEST, REQUEST, SCHEMA, AUDITS,
    STARTED, REVIEWED, ACTIVATED, OPERATOR_REJECTED, require, read_audit, event,
    reviewed_candidate, request_for_round, assert_unexposed_course,
)
from services.progressive_course_generation import (
    INPUT_SCHEMA, VERIFY_SCHEMA, VALIDATION_SCHEMA, validate_progressive_course_for_release,
)

ARCHIVES = (
    "f870db2c1e17e9193639248f92230169704a94546bb35ac596818ef44ae149f5/1680775e1fc8dcb1a6427475b1fccff61c2b73846a4edfa9e27a4083e4872fb7.json",
    "5b70b080674241da0c186addd7d630193edacea236f1c8fb48fa82d492b9eae7/52e3a874fdb9c8083551d89785b5e821edc30875bb8fc41a6e922e904c1bb4e7.json",
)
EXPOSURE = ROOT / "output/progressive-preview/saved-stage-english-slot1-revision2/repair-proposal.json"
EXPOSURE_SHA = "b922ba34f62abba2a65ce9fdd655baa69034b7f950024bcdd14bfa62f1bbaafc"
EXAMPLES = ["I like the cat.", "The cat likes me.", "She helps me.", "We see them.",
    "I see the dog.", "The dog sees me.", "Ben watches him.", "She draws a bird.",
    "The cat follows us.", "I drink water.", "They open the door.", "He is my friend.", "I thank him."]
ISSUES = [
    "人工复核否决当前已accepted版本的交付用途，原模型passed凭证必须保留而不是改成false。guided_1 My friend likes ____. 与English1 My brother likes ____.仅brother→friend且I/me/he选项完全相同；independent_3 The teacher helps ____ with the project. 与English1 He helps ____ with homework.仅换参与者/物件，she/her/he与核心作答信息相同。这是具体材料复用，不是禁止共享主宾形式知识。",
    "本套仍只考常见主宾形式和简单现在时，但须通过新的自足短语境同时练主语形式与动词宾语形式；六道题中至少两道主格与两道宾格，五道独立题中两种作用均出现。先教每个配对及必要词义。正确选项位置应自然分布，不能六道固定同一字母；不得靠猜人名性别、复杂从句或新时态增加难度。",
    "previousQuestions是负面避重材料。不得沿旧题逐句替换人物/地点/物品/频率；从新的明确交际或动作关系组织题面，代词所指应明确，读语境再识别主语或宾语。允许相同概念、常用动词和代词配对；禁止复用具体旧材料。",
    "English1课堂已公开演练以下13句，不能照搬、只换人名物品或改代词后当新验收题：" + " | ".join(EXAMPLES),
    "教学示例须另编且不能提前补全本套六题。讲主语/宾语作用，不把句首/动词后当无条件语法定义。只生成本课六题完整新candidate，不修改身份/课次，不扩教学目标。",
]


def identity():
    identities = preview_identities("primary_6")
    selected = [i for i in identities if i["buildItemId"] == ITEM]
    require(len(selected) == 1 and selected[0]["slot"]["lessonId"] == LESSON, "approved scope changed")
    return selected[0], identities


def snapshot(conn, selected, *, locked=False):
    suffix = " FOR UPDATE" if locked else ""
    item = dict(conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?" + suffix, (ITEM,)).fetchone() or {})
    require(item.get("course_id") == SOURCE_COURSE and item.get("status") == "course_ready"
        and item.get("content_phase") == "course_ready" and item.get("content_gate_status") == "passed"
        and item.get("build_job_id") == selected["buildId"]
        and item.get("generation_request_id") == SOURCE_REQUEST.removesuffix(".correction1"), "source item changed")
    course = dict(conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?" + suffix, (SOURCE_COURSE, item["course_version"])).fetchone())
    job = dict(conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=?" + suffix, (SOURCE_REQUEST,)).fetchone())
    require(course["status"] == "validated" and not course.get("retired_at") and job["status"] == "validated"
        and course["generation_request_id"] == SOURCE_REQUEST, "source is no longer unpublished validated content")
    for sql, params in (
        ("SELECT COUNT(*) AS n FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=? OR course_id=?", (ITEM, SOURCE_COURSE)),
        ("SELECT COUNT(*) AS n FROM learning_lesson_packages WHERE course_id=? AND course_version=?", (SOURCE_COURSE, course["version"])),
        ("SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?", (ITEM,)),
        ("SELECT COUNT(*) AS n FROM learning_formal_qwen_audio_jobs WHERE build_item_id=?", (ITEM,)),
        ("SELECT COUNT(*) AS n FROM learning_sessions WHERE course_id=? AND course_version=?", (SOURCE_COURSE, course["version"])),
        ("SELECT COUNT(*) AS n FROM learning_placement_questions WHERE course_id=? AND course_version=?", (SOURCE_COURSE, course["version"])),
        ("SELECT COUNT(*) AS n FROM learning_practice_exposures e JOIN learning_practice_questions q ON q.id=e.question_id WHERE q.course_id=? AND q.course_version=?", (SOURCE_COURSE, course["version"])),
        ("SELECT COUNT(*) AS n FROM learning_student_formal_session_bindings WHERE build_item_id=?", (ITEM,)),
    ):
        if locked:
            # Current locking reads, including when a prior read established an
            # InnoDB RR snapshot before we waited for the item/course locks.
            exists = conn.execute(sql.replace("SELECT COUNT(*) AS n", "SELECT 1 AS n") + " LIMIT 1 FOR UPDATE", params).fetchone()
        else:
            exists = conn.execute(sql, params).fetchone()["n"]
        require(not exists, "Runtime/package/receipt/audio/student exposure prevents pre-runtime replacement")
    owner = dict(conn.execute("SELECT * FROM learning_curriculum_preparation_plans WHERE catalog_build_id=? AND library_target_fingerprint=?" + suffix,
        (selected["buildId"], selected["targetFingerprint"])).fetchone())
    require(owner["status"] == "running" and owner["stage"] == "generating_content"
        and int(owner.get("lease_expires_at") or 0) <= now_ms()
        and not owner.get("bound_catalog_item_id") and owner.get("work_unit_kind") in {None, "coordinator"}, "content coordinator is not idle")
    auth_id = digest({"schema": "mira.catalog-paid-budget.v1", "scope": selected["scope"]})
    auth = conn.execute("SELECT * FROM learning_budget_authorizations WHERE id=?" + suffix, (auth_id,)).fetchone()
    require(auth and json.loads(auth["scope_json"]) == selected["scope"] and not auth["revoked_at"]
        and auth["expires_at"] > now_ms(), "exact authorization unavailable")
    ledger = [dict(r) for r in conn.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id" + suffix, (auth_id,)).fetchall()]
    require(ledger and all(r["state"] == "settled" for r in ledger), "an unresolved scope reservation prevents replacement")
    require(not conn.execute("SELECT id FROM learning_budget_reservations WHERE state IN ('reserved','dispatched') LIMIT 1" + suffix).fetchone(), "another Provider call is active")
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=LESSON)
    require(digest(receipt) == item["content_receipt_hash"], "source content receipt changed")
    return {"item": item, "course": course, "job": job, "owner": owner, "ledger": ledger, "receipt": receipt}


def source_unchanged(saved, audit):
    require(all(saved[k] == audit["source"][k] for k in ("item", "course", "job", "receipt")), "source accepted history changed")
    old = {r["id"]: r for r in audit["source"]["ledger"]}
    current = {r["id"]: r for r in saved["ledger"]}
    require(all(current.get(k) == v for k, v in old.items()), "old settled ledger changed")


def prepare(args):
    selected, _ = identity()
    request_id = request_for_round(args.replacement_round)
    require(hashlib.sha256(EXPOSURE.read_bytes()).hexdigest() == EXPOSURE_SHA, "published English1 exposure source changed")
    archives, verdict = [], None
    for relative in ARCHIVES:
        path = ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/formal-courseware-provider-responses" / relative
        raw = path.read_bytes(); data = json.loads(raw)
        expected = SOURCE_REQUEST + (":verify" if data["phase"] == "progressive_verification" else "")
        require(data["requestId"] == expected and data.get("responseId"), "source Provider identity changed")
        archives.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "phase": data["phase"]})
        if data["phase"] == "progressive_verification":
            verdict = json.loads(data["content"])["verification"]
    require(verdict and verdict["passed"] is True, "original model verdict must remain passed")
    conn = Database(AppConfig.from_env().DATABASE_URL).connect()
    try:
        conn.execute("START TRANSACTION READ ONLY")
        saved = snapshot(conn, selected)
        require(not event(conn, STARTED, request_id) and not event(conn, REVIEWED, request_id) and not event(conn, ACTIVATED)
            and not conn.execute("SELECT id FROM learning_course_generation_jobs WHERE request_id=?", (request_id,)).fetchone(),
            "replacement already started/reviewed; inspect existing result")
        prior = None
        if args.replacement_round > 1:
            require(args.diagnosis, "a saved explicit rejection diagnosis is required for the next round")
            previous_request = request_for_round(args.replacement_round - 1)
            previous_event = event(conn, STARTED, previous_request)
            require(previous_event is not None, "preceding dispatch audit missing")
            rejected_job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE request_id=?", (previous_request,)).fetchone()
            diagnostic = json.loads(Path(args.diagnosis).read_text())
            require(rejected_job and diagnostic.get("requestId") == previous_request
                and diagnostic.get("buildItemId") == ITEM, "preceding outcome identity missing")
            reviewed = None
            if rejected_job["status"] == "validated":
                require(args.replacement_round == 3 and diagnostic.get("kind") == "operator_semantic_rejection",
                    "accepted model content requires a separate explicit operator rejection")
                reviewed = reviewed_candidate(conn, previous_request)
                require(reviewed and diagnostic.get("courseId") == reviewed["course"]["id"]
                    and diagnostic.get("contentSha256") == digest(json.loads(reviewed["course"]["content_json"])), "operator rejection source changed")
                assert_unexposed_course(conn, reviewed["course"])
                rejected_archives, rejected_review = [], None
                for entry in diagnostic["archives"]:
                    path = Path(entry["path"]).resolve()
                    native = (ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/formal-courseware-provider-responses").resolve()
                    require(path.is_relative_to(native) and hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], "accepted Provider archive changed")
                    raw = json.loads(path.read_text()); phase = raw["phase"]
                    require(phase in {"progressive_generation", "progressive_verification"}
                        and raw["requestId"] == previous_request + (":verify" if phase == "progressive_verification" else "")
                        and raw.get("responseId") and isinstance(raw.get("usage"), dict), "accepted reply identity changed")
                    rejected_archives.append({**entry, "phase": phase})
                    if phase == "progressive_verification": rejected_review = json.loads(raw["content"])["verification"]
                require(len(rejected_archives) == 2 and {e["phase"] for e in rejected_archives} == {"progressive_generation", "progressive_verification"}
                    and rejected_review and rejected_review["passed"] is True, "preserve the real passed model review")
                draft = diagnostic.get("generationDraft")
                require(draft and draft["content"]["questions"] == json.loads(reviewed["course"]["content_json"])["questions"], "six frozen draft questions changed")
            else:
                require(rejected_job["status"] == "failed", "preceding outcome is not terminal")
                require(not conn.execute("SELECT id FROM learning_course_generation_candidates WHERE job_id=?", (rejected_job["id"],)).fetchone(), "a staged candidate must not be regenerated")
                from scripts.progressive_preview_correction import _returned_rejection
                rejected_archives, rejected_review = _returned_rejection(args.diagnosis, saved["item"], rejected_job)
            require(isinstance(diagnostic.get("actionableIssues"), list) and diagnostic["actionableIssues"]
                and all(isinstance(x, str) and x.strip() for x in diagnostic["actionableIssues"]), "concrete actionable rejection issues required")
            old_audit = read_audit(previous_event["auditShaId"])
            require(len(saved["ledger"]) == len(old_audit["source"]["ledger"]) + 2, "preceding generation/review did not settle as exactly two calls")
            prior = {"auditShaId": previous_event["auditShaId"], "sourceRejectedJob": dict(rejected_job),
                "independentReview": rejected_review, "diagnosisSha256": hashlib.sha256(Path(args.diagnosis).read_bytes()).hexdigest(),
                "actionableIssues": diagnostic["actionableIssues"], "archives": rejected_archives,
                "kind": "operator_semantic_rejection" if reviewed else "model_or_host_rejection"}
            if reviewed:
                prior.update(reviewedCandidate={k: reviewed[k] for k in ("course", "job", "receipt", "event")}, generationDraft=diagnostic["generationDraft"])
            archives.extend(rejected_archives)
    finally:
        conn.rollback(); conn.close()
    audit = {"schemaVersion": SCHEMA, "identity": selected, "source": saved, "archives": archives,
        "replacementRequestId": request_id, "replacementRound": args.replacement_round,
        "authorizationId": digest({"schema": "mira.catalog-paid-budget.v1", "scope": selected["scope"]}),
        "originalModelReview": verdict, "humanReview": {"status": "rejected_for_delivery", "issues": ISSUES + (prior["actionableIssues"] if prior else [])},
        "precedingRejectedAttempt": prior,
        "previousTeachingExposure": {"path": str(EXPOSURE), "sha256": EXPOSURE_SHA, "sentences": EXAMPLES},
        "provenance": {"kind": "fresh_model_generation_after_human_review", "newGenerationCalls": 1, "newBlindReviewCalls": 1,
            "originalModelVerdictUnchanged": True, "sameDeliverySlot": True}}
    sha = digest(audit); _save(AUDITS / (sha + ".json"), audit)
    return {"auditShaId": sha, "auditPath": str(AUDITS / (sha + ".json"))}


def operate(args):
    from services.course_library_service import CourseLibraryService
    from services.service_factory import (_catalog_paid_budget_environment, dynamic_learning_course_generation_service,
        learning_curriculum_preparation_checkpoint_adapter, openmaic_full_runtime_service)
    selected, identities = identity(); assert_preview_policy(args.budget_policy, identities); idle_processes()
    audit = read_audit(args.audit_sha)
    request_id = audit["replacementRequestId"]
    require(audit["identity"] == selected, "replacement target changed")
    with operator_app(args).app_context():
        generator = copy(dynamic_learning_course_generation_service())
        preparations = learning_curriculum_preparation_checkpoint_adapter().repository
        library = CourseLibraryService(AppConfig.from_env().DATABASE_URL, grade_code="primary_6", preparation_repository=preparations)
        if args.command == "generate":
            # Prior STARTED intentionally blocks ordinary operators from the
            # rejected old course. This bounded correction proves the previous
            # terminal job below, then checks the same six-slot/sibling scope.
            if audit.get("replacementRound", 1) > 1:
                from scripts.generate_one_library_course import inventory
                state = inventory(library, selected)
                with library.database.transaction() as conn:
                    state["touchedSiblingIds"] = [r["id"] for r in conn.execute(
                        "SELECT item.id FROM learning_catalog_build_items item WHERE item.build_job_id=? AND item.id<>? "
                        "AND (item.attempt_count>0 OR item.status<>'pending' OR EXISTS "
                        "(SELECT 1 FROM learning_course_generation_jobs j WHERE j.request_id=item.generation_request_id) OR EXISTS "
                        "(SELECT 1 FROM learning_course_provider_dispatches d WHERE d.build_item_id=item.id) OR EXISTS "
                        "(SELECT 1 FROM learning_openmaic_runtime_classrooms r WHERE r.candidate_build_item_id=item.id))",
                        (selected["buildId"], ITEM)).fetchall()]
                    state["budgetReservations"] = {r["state"]: int(r["n"]) for r in conn.execute(
                        "SELECT state,COUNT(*) AS n FROM learning_budget_reservations WHERE authorization_id=? GROUP BY state",
                        (audit["authorizationId"],)).fetchall()}
                state["generationJob"] = audit["source"]["job"]
            else:
                state = preview_inventory(library, selected)
            assert_preview_scope(library, selected, identities, state)
            runtime = openmaic_full_runtime_service()
            assert_search_budget_ready(args, library, selected, runtime, state)
            require(runtime.formal_provider_circuit_status()["dispatchAllowed"], "Provider circuit not ready")
            with generator.repository.transaction() as conn:
                saved = snapshot(conn, selected, locked=True); source_unchanged(saved, audit)
                require(not event(conn, STARTED, request_id) and not event(conn, REVIEWED, request_id) and not event(conn, ACTIVATED)
                    and not conn.execute("SELECT id FROM learning_course_generation_jobs WHERE request_id=?", (request_id,)).fetchone(), "replacement dispatch already attempted; never replay")
                prior = audit.get("precedingRejectedAttempt")
                if prior:
                    failed = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=? FOR UPDATE", (prior["sourceRejectedJob"]["id"],)).fetchone()
                    require(dict(failed or {}) == prior["sourceRejectedJob"]
                        and failed["status"] == ("validated" if prior.get("kind") == "operator_semantic_rejection" else "failed")
                        and event(conn, STARTED, failed["request_id"])["auditShaId"] == prior["auditShaId"], "preceding failed outcome changed")
                    if prior.get("kind") == "operator_semantic_rejection":
                        reviewed = reviewed_candidate(conn, failed["request_id"])
                        require(reviewed and all(reviewed[k] == prior["reviewedCandidate"][k] for k in ("course", "job", "receipt", "event")), "operator rejected source changed")
                        assert_unexposed_course(conn, reviewed["course"], locked=True)
                        require(not event(conn, OPERATOR_REJECTED), "operator rejection already recorded")
                        preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type=OPERATOR_REJECTED, stage="generating_content",
                            payload={"buildItemId": ITEM, "auditShaId": args.audit_sha, "replacementRequestId": request_id,
                                "rejectedRequestId": failed["request_id"], "sourceCourseId": reviewed["course"]["id"],
                                "sourceContentShaId": digest(json.loads(reviewed["course"]["content_json"]))}, now=now_ms())
                preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type=STARTED, stage="generating_content",
                    payload={"buildItemId": ITEM, "auditShaId": args.audit_sha, "replacementRequestId": request_id, "sourceCourseId": SOURCE_COURSE}, now=now_ms())
            adapter = copy(generator.progressive_adapter)
            require(not adapter.fake_mode and adapter.provider_name == "openmaic_runtime", "real normal content generation required")
            command = SimpleNamespace(build_item_id=ITEM, grade_code="primary_6", subject="english", boundary={"skillId": LESSON})
            original_call = adapter._call
            called = set()
            def environment(payload):
                assert_preview_policy(args.budget_policy, identities)
                schema = payload.get("schemaVersion")
                require(schema in {INPUT_SCHEMA, VERIFY_SCHEMA} and schema not in called
                    and payload.get("requestId") == request_id + (":verify" if schema == VERIFY_SCHEMA else "")
                    and payload.get("brief", {}).get("binding", {}).get("lessonId") == LESSON, "replacement dispatch escaped its exact scope")
                called.add(schema)
                return _catalog_paid_budget_environment(command)
            def call(payload):
                if payload.get("schemaVersion") == INPUT_SCHEMA:
                    payload = {**payload, "correctionRequirements": {"auditShaId": args.audit_sha, "issues": audit["humanReview"]["issues"]}}
                prior = audit.get("precedingRejectedAttempt")
                if prior and prior.get("kind") == "operator_semantic_rejection":
                    require(all(q["courseId"] != prior["reviewedCandidate"]["course"]["id"] for q in payload["generationContext"]["previousQuestions"]), "precise unexposed source was not excluded")
                    _save(AUDITS / (args.audit_sha + "-" + ("verify" if payload["schemaVersion"] == VERIFY_SCHEMA else "generate") + "-public-context.json"), payload["generationContext"])
                return original_call(payload)
            adapter.execution_environment = environment; adapter._call = call; generator.progressive_adapter = adapter
            result = generator.generate({"requestId": request_id, "curriculumVersion": library.target["curriculumVersion"],
                "lessonId": LESSON, "gradeCode": "primary_6", "subject": "english", "difficultyCode": "basic"}, enqueue_classroom=False)
            _save(AUDITS / (args.audit_sha + "-generation-result.json"), result.payload)
            require(result.payload.get("ok") is True, "replacement failed; original and new outputs retained, no automatic retry")
            with generator.repository.transaction() as conn:
                saved = snapshot(conn, selected, locked=True); source_unchanged(saved, audit)
                new_ids = sorted(set(r["id"] for r in saved["ledger"]) - set(r["id"] for r in audit["source"]["ledger"]))
                require(len(new_ids) == 2 and called == {INPUT_SCHEMA, VERIFY_SCHEMA}, "unexpected paid replacement calls")
                course = dict(conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?", (result.payload["course"]["id"], result.payload["course"]["version"])).fetchone())
                require(course["generation_request_id"] == request_id and course["id"] != SOURCE_COURSE, "new candidate identity required")
                if (audit.get("precedingRejectedAttempt") or {}).get("kind") == "operator_semantic_rejection":
                    require(json.loads(course["content_json"])["questions"] == audit["precedingRejectedAttempt"]["generationDraft"]["content"]["questions"], "Provider changed the six approved draft questions; retain candidate for diagnosis, do not activate")
                receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=LESSON)
                dispatch = {"auditShaId": args.audit_sha, "newReservationIds": new_ids}; dispatch_sha = digest(dispatch)
                _save(AUDITS / (dispatch_sha + "-dispatch.json"), dispatch)
                value = {"buildItemId": ITEM, "auditShaId": args.audit_sha, "replacementRequestId": request_id,
                    "generationJobId": result.payload["jobId"], "courseId": course["id"], "courseVersionId": course["version"],
                    "contentReceiptShaId": digest(receipt), "dispatchAuditShaId": dispatch_sha}
                preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type=REVIEWED, stage="generating_content", payload=value, now=now_ms())
                _save(AUDITS / (args.audit_sha + "-candidate.json"), {"course": course, "content": json.loads(course["content_json"]), "receipt": receipt, "event": value})
            return {"status": "reviewed_not_activated", **value}
        with generator.repository.transaction() as conn:
            candidate = reviewed_candidate(conn, request_id)
            require(candidate and candidate["event"]["auditShaId"] == args.audit_sha and not event(conn, ACTIVATED), "candidate already activated or not reviewed")
            saved = snapshot(conn, selected, locked=True); source_unchanged(saved, audit)
            acceptance = json.loads(Path(args.acceptance).read_text())
            require(acceptance.get("schemaVersion") == "mira.progressive-replacement-human-review.v1"
                and acceptance.get("auditShaId") == args.audit_sha and acceptance.get("status") == "approved"
                and acceptance.get("courseId") == candidate["course"]["id"]
                and acceptance.get("contentSha256") == digest(json.loads(candidate["course"]["content_json"]))
                and acceptance.get("issues") == [] and isinstance(acceptance.get("observations"), list) and acceptance["observations"], "exact human content review is required")
            acceptance_sha = digest(acceptance); _save(AUDITS / (acceptance_sha + "-acceptance.json"), acceptance)
            value = {**candidate["event"], "acceptanceShaId": acceptance_sha}
            # Progressive migration 080 keeps both scheduling request fields
            # equal to the original item request. The immutable activation
            # event selects the replacement job; do not rewrite that lineage.
            updated = conn.execute("UPDATE learning_catalog_build_items SET course_id=?,course_version=?,content_gate_passed_at=?, "
                "content_validation_contract_version=?,content_receipt_hash=?,updated_at=? WHERE id=? AND course_id=? "
                "AND course_version=? AND status='course_ready' AND content_phase='course_ready' AND updated_at=?",
                (candidate["course"]["id"], candidate["course"]["version"], now_ms(), VALIDATION_SCHEMA, digest(candidate["receipt"]),
                    now_ms(), ITEM, SOURCE_COURSE, saved["course"]["version"], saved["item"]["updated_at"]))
            require(updated.rowcount == 1, "source item changed during activation")
            preparations.append_event(conn, plan_id=saved["owner"]["id"], event_type=ACTIVATED, stage="generating_content", payload=value, now=now_ms())
            conn.execute("UPDATE learning_curriculum_preparation_plans SET lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL, "
                "hard_deadline_at=NULL,work_unit_kind=NULL,next_run_at=?,updated_at=? WHERE id=? AND status='running' AND stage='generating_content'",
                (now_ms(), now_ms(), saved["owner"]["id"]))
            require(preparations.reconcile_shared_build(conn, build_id=selected["buildId"], target_fingerprint=selected["targetFingerprint"], now=now_ms()) >= 1, "coordinator receipt reconciliation failed")
        return {"status": "course_ready_no_runtime", **value}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "generate", "activate"))
    p.add_argument("--audit-sha"); p.add_argument("--acceptance")
    p.add_argument("--replacement-round", type=int, choices=(1, 2, 3), default=1)
    p.add_argument("--diagnosis")
    p.add_argument("--budget-policy", default="backend/content/learning_classroom_policy.json")
    p.add_argument("--confirm-workers-stopped", action="store_true")
    args = p.parse_args(); args.grade = "primary_6"; args.subject = "english"; args.lesson_id = LESSON; args.slot = 2
    require(args.command == "prepare" or (args.audit_sha and args.confirm_workers_stopped), "audit SHA and stopped-worker confirmation required")
    require(args.command != "activate" or args.acceptance, "activation requires the saved human content review")
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = prepare(args) if args.command == "prepare" else operate(args)
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
