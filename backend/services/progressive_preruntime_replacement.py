"""Read one explicit, unpublished English2 replacement without rewriting history."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from content.learning_budget_policy import digest

ROOT = Path(__file__).resolve().parents[2]
AUDITS = ROOT / "output/progressive-preview/english-slot2-replacement"
ITEM = "catalog_build_item_d5a6b286d326400b49241b5d"
LESSON = "EN6A01.01"
SOURCE_COURSE = "progressive_7b63a32638807c8bd46cc2d1"
SOURCE_REQUEST = "catalog_gen_d5a6b286d326400b49241b5d188129789412549dc2c3741e.correction1"
REQUEST = SOURCE_REQUEST.removesuffix(".correction1") + ".replacement1"
SCHEMA = "mira.progressive-preruntime-replacement.v1"
STARTED = "progressive_preruntime_replacement_started"
REVIEWED = "progressive_preruntime_replacement_reviewed"
ACTIVATED = "progressive_preruntime_replacement_activated"
OPERATOR_REJECTED = "progressive_preruntime_operator_rejected"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def request_for_round(number):
    require(type(number) is int and 1 <= number <= 3, "replacement round must be 1..3")
    return SOURCE_REQUEST.removesuffix(".correction1") + f".replacement{number}"


def read_audit(sha):
    require(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha), "exact replacement audit SHA required")
    audit = json.loads((AUDITS / (sha + ".json")).read_text())
    require(digest(audit) == sha and audit.get("schemaVersion") == SCHEMA
        and audit["identity"]["buildItemId"] == ITEM
        and audit["replacementRequestId"] == request_for_round(audit.get("replacementRound", 1))
        and audit["source"]["course"]["id"] == SOURCE_COURSE
        and audit["source"]["job"]["request_id"] == SOURCE_REQUEST,
        "replacement audit identity changed")
    for entry in audit["archives"]:
        require(hashlib.sha256(Path(entry["path"]).read_bytes()).hexdigest() == entry["sha256"],
            "original Provider bytes changed")
    return audit


def event(conn, kind, request_id=None):
    restriction = " AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.replacementRequestId'))=?" if request_id else ""
    rows = conn.execute("SELECT e.payload_json,p.target_fingerprint FROM learning_curriculum_preparation_events e "
        "JOIN learning_curriculum_preparation_plans p ON p.id=e.plan_id WHERE e.event_type=? "
        "AND JSON_UNQUOTE(JSON_EXTRACT(e.payload_json,'$.buildItemId'))=?" + restriction + " ORDER BY e.created_at,e.id",
        (kind, ITEM, *((request_id,) if request_id else ()))).fetchall()
    require(len(rows) <= (3 if kind in {STARTED, REVIEWED} and not request_id else 1), "conflicting replacement events")
    if not rows:
        return None
    row = rows[-1]
    value = json.loads(row["payload_json"])
    audit = read_audit(value.get("auditShaId"))
    require(row["target_fingerprint"] == audit["identity"]["targetFingerprint"]
        and value.get("replacementRequestId") == audit["replacementRequestId"], "replacement event scope changed")
    return value


def reviewed_candidate(conn, request_id=None, *, allow_operator_rejected=False):
    value = event(conn, REVIEWED, request_id)
    if not value:
        return None
    rejection = event(conn, OPERATOR_REJECTED)
    require(allow_operator_rejected or not rejection or rejection.get("rejectedRequestId") != value["replacementRequestId"],
        "human-rejected teaching content cannot be activated")
    started = event(conn, STARTED, value["replacementRequestId"])
    require(started and started["auditShaId"] == value["auditShaId"], "replacement start audit missing")
    audit = read_audit(value["auditShaId"])
    request_id = audit["replacementRequestId"]
    for key, table in (("course", "learning_courses"), ("job", "learning_course_generation_jobs")):
        original = conn.execute("SELECT * FROM " + table + " WHERE id=?", (audit["source"][key]["id"],)).fetchone()
        require(dict(original or {}) == audit["source"][key], "original accepted history changed")
    job = conn.execute("SELECT * FROM learning_course_generation_jobs WHERE id=?", (value["generationJobId"],)).fetchone()
    course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?", (value["courseId"], value["courseVersionId"])).fetchone()
    require(job and course and job["status"] == "validated" and job["request_id"] == request_id
        and course["generation_request_id"] == request_id and course["id"] != SOURCE_COURSE,
        "replacement candidate identity changed")
    paid = json.loads((AUDITS / (value["dispatchAuditShaId"] + "-dispatch.json")).read_text())
    require(digest(paid) == value["dispatchAuditShaId"] and paid["auditShaId"] == value["auditShaId"]
        and len(paid["newReservationIds"]) == 2, "replacement dispatch audit changed")
    for reservation_id in paid["newReservationIds"]:
        row = conn.execute("SELECT authorization_id,state FROM learning_budget_reservations WHERE id=?", (reservation_id,)).fetchone()
        require(row and row["authorization_id"] == audit["authorizationId"] and row["state"] == "settled",
            "replacement generation/review settlement changed")
    from services.progressive_course_generation import validate_progressive_course_for_release
    receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=LESSON)
    require(digest(receipt) == value["contentReceiptShaId"], "replacement receipt changed")
    return {"course": dict(course), "job": dict(job), "receipt": receipt, "event": value, "audit": audit}


def accepted_preruntime_replacement_job(conn, identity, item):
    if identity.get("buildItemId") != ITEM:
        return None
    started = event(conn, STARTED)
    if not started:
        return None
    active = event(conn, ACTIVATED)
    require(active is not None, "human-rejected unpublished content awaits its audited replacement; do not start the old Runtime")
    candidate = reviewed_candidate(conn, active["replacementRequestId"])
    require(candidate and identity == candidate["audit"]["identity"]
        and all(active.get(k) == candidate["event"].get(k) for k in
            ("auditShaId", "generationJobId", "courseId", "courseVersionId", "contentReceiptShaId")),
        "replacement activation changed")
    acceptance = json.loads((AUDITS / (active["acceptanceShaId"] + "-acceptance.json")).read_text())
    require(digest(acceptance) == active["acceptanceShaId"] and acceptance.get("status") == "approved"
        and acceptance.get("courseId") == candidate["course"]["id"]
        and acceptance.get("contentSha256") == digest(json.loads(candidate["course"]["content_json"]))
        and item.get("course_id") == active["courseId"] and item.get("course_version") == active["courseVersionId"]
        and item.get("content_receipt_hash") == active["contentReceiptShaId"]
        and item.get("active_generation_request_id") == candidate["audit"]["source"]["item"]["generation_request_id"]
        and item.get("generation_request_id") == candidate["audit"]["source"]["item"]["generation_request_id"]
        and item.get("content_phase") == "course_ready" and item.get("content_gate_status") == "passed",
        "current item is not the reviewed replacement")
    return candidate["job"]


def assert_preruntime_source_not_rejected(conn, *, build_item_id, course_id):
    if build_item_id == ITEM and course_id == SOURCE_COURSE:
        require(event(conn, STARTED) is None, "human-rejected source cannot start a formal package")
    if build_item_id == ITEM:
        rejection = event(conn, OPERATOR_REJECTED)
        require(not rejection or rejection.get("sourceCourseId") != course_id, "human-rejected teaching cannot start a formal package")


def assert_unexposed_course(conn, course, *, locked=False):
    suffix = " FOR UPDATE" if locked else ""
    require(course.get("status") == "validated" and not course.get("retired_at"), "replacement source must be unpublished")
    for sql, params in (
        ("SELECT id FROM learning_openmaic_runtime_classrooms WHERE course_id=?", (course["id"],)),
        ("SELECT id FROM learning_lesson_packages WHERE course_id=? AND course_version=?", (course["id"], course["version"])),
        ("SELECT id FROM learning_sessions WHERE course_id=? AND course_version=?", (course["id"], course["version"])),
        ("SELECT question_id FROM learning_placement_questions WHERE course_id=? AND course_version=?", (course["id"], course["version"])),
        ("SELECT e.question_id FROM learning_practice_exposures e JOIN learning_practice_questions q ON q.id=e.question_id WHERE q.course_id=? AND q.course_version=?", (course["id"], course["version"])),
    ):
        require(not conn.execute(sql + " LIMIT 1" + suffix, params).fetchone(), "reviewed replacement already has downstream artifacts or student exposure")


def excluded_unexposed_replacement_source(conn, *, request_id, lesson_id):
    if request_id != request_for_round(3) or lesson_id != LESSON:
        return None
    value = event(conn, OPERATOR_REJECTED)
    require(value and value["replacementRequestId"] == request_id, "round3 needs its explicit operator rejection")
    audit = read_audit(value["auditShaId"])
    prior = audit.get("precedingRejectedAttempt") or {}
    require(prior.get("kind") == "operator_semantic_rejection"
        and prior["reviewedCandidate"]["event"]["replacementRequestId"] == value["rejectedRequestId"], "operator rejection lineage changed")
    source = prior["reviewedCandidate"]["course"]
    row = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=?", (source["id"], source["version"])).fetchone()
    require(dict(row or {}) == source and digest(json.loads(source["content_json"])) == value["sourceContentShaId"], "rejected source bytes changed")
    assert_unexposed_course(conn, source)
    return source["id"], source["version"]
