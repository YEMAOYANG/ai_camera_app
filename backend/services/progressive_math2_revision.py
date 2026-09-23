"""Authority for one audited, unpublished mathematics slot-two revision.

The original course, package, Native input and Provider history are immutable.
Only an activated editorial audit can select another package seed and admit its
retired predecessor. Ordinary builds retain their existing identities and gates.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from content.learning_budget_policy import digest

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "output/progressive-preview/math-slot2-editorial"
ITEM = "catalog_build_item_c38581679912c102b1d91061"
LESSON = "M6A01.01"
SOURCE_COURSE = "progressive_2d353a00432aaa47718ee42c"
SOURCE_RUNTIME = "omfc_L8kVrGObn8NzjOGExLwabTb2wnt3dWhVYHVYEaIhCvE"
SOURCE_NATIVE_JOB = "omformal_ae449edd4a7959bcbb62a17e"
BASE_REQUEST = "catalog_gen_c38581679912c102b1d91061605c753423663e67d6fb93c8"
EDITORIAL_REQUEST = BASE_REQUEST + ".editorial1"
SCHEMA = "mira.progressive-math2-editorial-audit.v1"
STARTED = "progressive_math2_revision_started"
REVIEWED = "progressive_math2_revision_reviewed"
ACTIVATED = "progressive_math2_revision_activated"


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def read_audit(sha):
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "exact revision audit SHA required")
    audit = json.loads((AUDITS / (sha + ".json")).read_text())
    require(digest(audit) == sha and audit.get("schemaVersion") == SCHEMA
        and audit.get("identity", {}).get("buildItemId") == ITEM
        and audit.get("editorialRequestId") == EDITORIAL_REQUEST
        and audit.get("sourceCourse", {}).get("id") == SOURCE_COURSE,
        "mathematics revision audit changed")
    for archive in audit["archives"]:
        require(hashlib.sha256(Path(archive["path"]).read_bytes()).hexdigest() == archive["sha256"],
            "original Provider archive changed")
    require(digest(audit["editedCandidate"]["content"]) == audit["editedContentSha256"], "edited candidate changed")
    return audit


def event(conn, kind):
    rows = conn.execute("SELECT e.payload_json,p.target_fingerprint FROM learning_curriculum_preparation_events e "
        "JOIN learning_curriculum_preparation_plans p ON p.id=e.plan_id WHERE e.event_type=? "
        "AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.buildItemId'))=? ORDER BY e.created_at,e.id",
        (kind, ITEM)).fetchall()
    require(len(rows) <= 1, "conflicting mathematics revision events")
    if not rows:
        return None
    value = json.loads(rows[0]["payload_json"])
    audit = read_audit(value.get("auditShaId"))
    require(rows[0]["target_fingerprint"] == audit["identity"]["targetFingerprint"], "revision owner changed")
    return value


def reviewed_candidate(conn, audit_sha=None):
    value = event(conn, REVIEWED)
    if not value:
        return None
    audit = read_audit(value["auditShaId"])
    require(audit_sha is None or value["auditShaId"] == audit_sha, "different editorial review exists")
    started = event(conn, STARTED)
    require(started and all(started.get(k) == value.get(k)
        for k in ("auditShaId", "generationJobId", "editorialRequestId")), "review start identity changed")
    job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=?", (value["generationJobId"],)).fetchone()
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?", (value["courseId"], value["courseVersionId"])).fetchone()
    paid = conn.execute("SELECT * FROM learning_budget_reservations WHERE id=?", (value["verificationReservationId"],)).fetchone()
    original = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=?", (audit["sourceJob"]["id"],)).fetchone()
    require(dict(original or {}) == audit["sourceJob"] and job and course
        and job["request_id"] == EDITORIAL_REQUEST and job["status"] == "validated"
        and course["generation_request_id"] == EDITORIAL_REQUEST
        and digest(json.loads(course["content_json"])) == audit["editedContentSha256"]
        and paid and paid["state"] == "settled" and paid["authorization_id"] == audit["authorizationId"],
        "reviewed revision provenance changed")
    from services.progressive_course_generation import validate_progressive_course_for_release
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=LESSON)
    require(digest(receipt) == value["contentReceiptShaId"], "reviewed content receipt changed")
    return {"course": dict(course), "job": dict(job), "receipt": receipt, "event": value, "audit": audit}


def activated_revision(conn):
    value = event(conn, ACTIVATED)
    if not value:
        return None
    reviewed = reviewed_candidate(conn, value["auditShaId"])
    require(reviewed and all(value.get(k) == reviewed["event"].get(k)
        for k in ("generationJobId", "courseId", "courseVersionId", "contentReceiptShaId")), "activation review changed")
    sha = value.get("activationShaId")
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "activation archive missing")
    archive = json.loads((AUDITS / ("activation-" + sha + ".json")).read_text())
    require(digest(archive) == sha and archive["auditShaId"] == value["auditShaId"]
        and archive["sourceRuntime"]["id"] == SOURCE_RUNTIME
        and archive["sourceNativeJob"]["id"] == SOURCE_NATIVE_JOB
        and archive["sourceNativeJob"]["status"] in {"succeeded", "failed"}, "activation archive changed")
    old = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?", (SOURCE_RUNTIME,)).fetchone()
    require(old and old.get("retired_at") == value.get("retiredAtMsCount"), "original runtime is not retired by this audit")
    retained = dict(old)
    retained["retired_at"] = archive["sourceRuntime"].get("retired_at")
    retained["updated_at"] = archive["sourceRuntime"]["updated_at"]
    require(retained == archive["sourceRuntime"], "original Runtime changed after retirement")
    native_path = ROOT / "openmaic-runtime/.runtime/OpenMAIC/data/classroom-jobs" / (SOURCE_NATIVE_JOB + ".json")
    require(hashlib.sha256(native_path.read_bytes()).hexdigest() == archive["sourceNativeJobSha256"], "original terminal Native job changed")
    item = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?", (ITEM,)).fetchone()
    require(item and item["course_id"] == value["courseId"] and item["course_version"] == value["courseVersionId"]
        and item["content_receipt_hash"] == value["contentReceiptShaId"] and item["content_gate_status"] == "passed"
        and item["content_phase"] == "course_ready" and item["generation_request_id"] == BASE_REQUEST,
        "current item is not bound to the audited revision")
    return {**reviewed, "activation": value, "archive": archive}


def formal_package_identity(conn, *, build_item_id, course_id, course_version):
    from services.progressive_preruntime_replacement import assert_preruntime_source_not_rejected
    assert_preruntime_source_not_rejected(conn, build_item_id=build_item_id, course_id=course_id)
    seed_value = build_item_id
    revision = activated_revision(conn) if build_item_id == ITEM else None
    if revision:
        require((course_id, course_version) == (revision["course"]["id"], revision["course"]["version"]),
            "package request does not select the active revision")
        seed_value += ":editorial:" + revision["activation"]["auditShaId"]
    seed = hashlib.sha256(seed_value.encode()).hexdigest()[:48]
    return {"seed": seed, "packageId": "formal_runtime_package_" + seed,
        "sourceJobId": "formal_runtime_job_" + seed, "sourceArtifactId": "formal_runtime_source_" + seed,
        "requestId": "formal-package-" + seed, "packageVersion": 1,
        "revisionSourceRuntimeId": SOURCE_RUNTIME if revision else None}


def is_audited_predecessor(conn, *, build_item_id, runtime):
    if build_item_id != ITEM or runtime.get("id") != SOURCE_RUNTIME:
        return False
    revision = activated_revision(conn)
    return bool(revision and runtime.get("retired_at") == revision["activation"]["retiredAtMsCount"])


def predecessor_selection_sql():
    """Narrow SQL prefilter; the Python reader verifies the full audit before use."""
    return (f"blocked.id='{SOURCE_RUNTIME}' AND item.id='{ITEM}' AND blocked.retired_at IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM learning_curriculum_preparation_events revision "
        f"WHERE revision.event_type='{ACTIVATED}' "
        f"AND JSON_UNQUOTE(JSON_EXTRACT(revision.payload_json,'$.buildItemId'))='{ITEM}' "
        "AND JSON_UNQUOTE(JSON_EXTRACT(revision.payload_json,'$.courseId'))=item.course_id "
        "AND JSON_UNQUOTE(JSON_EXTRACT(revision.payload_json,'$.courseVersionId'))=item.course_version)")


def accepted_math2_revision_job(conn, identity, item):
    if identity.get("buildItemId") != ITEM:
        return None
    revision = activated_revision(conn)
    if revision is None:
        return None
    require(identity == revision["audit"]["identity"] and item["course_id"] == revision["course"]["id"], "revision scope changed")
    return revision["job"]


def select_revision_runtimes(conn, identity, runtimes):
    if identity.get("buildItemId") != ITEM or not event(conn, ACTIVATED):
        return runtimes, []
    revision = activated_revision(conn)
    old = [r for r in runtimes if r["id"] == SOURCE_RUNTIME]
    current = [r for r in runtimes if r["id"] != SOURCE_RUNTIME]
    require(len(old) == 1 and len(current) <= 1, "unexpected mathematics Runtime history")
    if current:
        row = current[0]
        require(row["course_id"] == revision["course"]["id"] and row["course_version"] == revision["course"]["version"]
            and row["attempt_ordinal"] == 2 and row["provider_attempt_ordinal"] == 2
            and row["retry_of_runtime_id"] == SOURCE_RUNTIME and not row.get("retired_at"), "revision Runtime identity changed")
    return current, old


def assert_publishable_revision(course_id):
    require(course_id != SOURCE_COURSE, "Original mathematics slot two was rejected for repeated assessment material; publish only the independently reviewed revision")
    from services.progressive_preruntime_replacement import SOURCE_COURSE as ENGLISH2_REJECTED_COURSE
    require(course_id != ENGLISH2_REJECTED_COURSE, "Original English slot two was rejected for repeated assessment material; publish only the independently reviewed replacement")
