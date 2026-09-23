"""Restore only the audited slot-two coordinator failure; never dispatch work."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
SNAPSHOT_SHA = "0fc7a74c410b3605a585bd29458ee27849a9e31c38e479ca39ce106ee36ddd34"
SNAPSHOT = ROOT / "output/progressive-preview" / f"ZH6A01.01-2-owner-failure-{SNAPSHOT_SHA}.json"
EVENT = "progressive_content_owner_receipt_reconciled"

from core.config import AppConfig
from core.database import Database
from core.security import now_ms
from content.learning_budget_policy import digest
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from scripts.generate_one_library_course import LOCK_PATH
from scripts.generate_progressive_preview import preview_identities, preview_inventory, assert_preview_policy, assert_preview_scope
from services.course_library_service import CourseLibraryService
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.lesson_package_service import LessonPackageService


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def idle_processes():
    lines = subprocess.run(["ps", "-axo", "pid=,command="], check=True, capture_output=True, text=True).stdout.splitlines()
    tokens = ("workers.learning_curriculum_preparation_worker", "generate_progressive_preview.py",
              "generate_one_library_course.py", "generate_one_formal_course.py", "openmaic-sidecar/src/cli.mjs")
    active = []
    for line in lines:
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or int(parts[0]) == os.getpid():
            continue
        try:
            command = shlex.split(parts[1])
        except ValueError:
            continue
        # Match actual Python/Node workers, not an enclosing shell's audit text.
        if (command and Path(command[0]).name.startswith(("python", "node"))
                and any(token in argument for token in tokens for argument in command[1:])):
            active.append(int(parts[0]))
    require(not active, f"another production process is active: {active}")


class ReadonlyConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        require(sql.lstrip().upper().startswith("SELECT"), "preview must not mutate the database")
        return self.conn.execute(sql.replace(" FOR UPDATE", ""), params)


class ReservationGatePassed(Exception):
    pass


def check_actual_reservation_gate(conn, database_url, owner, item):
    """Run the real package service, stopping before its first INSERT."""
    class NoWrites:
        def execute(self, sql, params=()):
            if (sql.lstrip().upper().startswith("SELECT")
                    or sql.lstrip().startswith("WITH student_runtime_manifests AS (")):
                return conn.execute(sql, params)
            expected = "formal_runtime_job_" + hashlib.sha256(item["id"].encode()).hexdigest()[:48]
            if (sql.lstrip().startswith("INSERT INTO learning_classroom_generation_jobs(")
                    and params[0] == expected and params[2:4] == (item["course_id"], item["course_version"])):
                raise ReservationGatePassed()
            raise RuntimeError("unexpected write attempted by package preflight")

    @contextmanager
    def same_transaction():
        yield NoWrites()

    class NoRuntime:
        def issue_candidate_generation(self, **kwargs):
            raise RuntimeError("recovery cannot issue a Runtime")

    service = LessonPackageService(database_url)
    service.repository.transaction = same_transaction
    try:
        service.process_next_formal_candidate(NoRuntime(), preparation_plan=owner)
    except ReservationGatePassed:
        return
    raise RuntimeError("the exact accepted slot did not reach its normal package reservation gate")


def run(apply):
    raw = SNAPSHOT.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SNAPSHOT_SHA, "original failure snapshot changed")
    saved = json.loads(raw)
    identities = preview_identities("primary_6")
    identity = next(i for i in identities if i["slot"]["subject"] == "chinese" and i["slot"]["variantOrdinal"] == 2)
    require(saved["item"]["id"] == identity["buildItemId"], "snapshot slot changed")
    policy_path = BACKEND / "content/learning_classroom_policy.json"
    assert_preview_policy(str(policy_path), identities)
    idle_processes()
    database_url = AppConfig.from_env().DATABASE_URL
    database = Database(database_url)
    catalog = LearningCatalogReleaseService(database_url, dynamic_generation_service=None, lesson_package_service=None)
    preparations = LearningCurriculumPreparationRepository(database, content_proof_auditor=catalog.audit_locked_content_proofs)
    library = CourseLibraryService(database_url, grade_code="primary_6", preparation_repository=preparations)
    state = preview_inventory(library, identity)
    require(state["owner"] == saved["owner"] and state["item"] == saved["item"], "owner or accepted item changed since failure snapshot")
    require(state["owner"]["status"] == "failed" and state["owner"]["stage"] == "completed"
            and state["owner"]["error_code"] == "preparation_validation_failed", "not this diagnosed coordinator failure")
    require(state["generationJob"]["id"] == "learning_course_job_c860b1ffb60644cd85373c07f057f4a3"
            and state["generationJob"]["status"] == "validated" and not state["runtimes"]
            and state["receipt"] is None and state["budgetReservations"] == {"settled": 6}, "accepted content or settled scope changed")
    assert_preview_scope(library, identity, identities, {**state, "owner": {**state["owner"], "status": "running"}})
    conn = database.connect()
    try:
        if not apply:
            conn.execute("START TRANSACTION READ ONLY")
        checked = conn if apply else ReadonlyConnection(conn)
        owner = preparations.get_plan(checked, plan_id=state["owner"]["id"], for_update=True)
        require(dict(owner) == saved["owner"], "owner changed before recovery lock")
        item = checked.execute("SELECT * FROM learning_catalog_build_items WHERE id=? FOR UPDATE", (identity["buildItemId"],)).fetchone()
        require(dict(item) == saved["item"], "accepted item changed before recovery lock")
        authorization = digest({"schema": "mira.catalog-paid-budget.v1", "scope": identity["scope"]})
        reservations = checked.execute("SELECT id,state FROM learning_budget_reservations WHERE authorization_id=? FOR UPDATE",
                                       (authorization,)).fetchall()
        require(len(reservations) == 6 and all(row["state"] == "settled" for row in reservations),
                "the selected scope acquired an active or unresolved call")
        active = checked.execute("SELECT COUNT(*) AS count FROM learning_curriculum_preparation_plans WHERE lease_expires_at>?", (now_ms(),)).fetchone()
        require(active["count"] == 0, "a preparation worker owns an active lease")
        active = checked.execute("SELECT COUNT(*) AS count FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()
        require(active["count"] == 0, "a Provider call is active")
        active = checked.execute("SELECT COUNT(*) AS count FROM learning_openmaic_runtime_classrooms WHERE status IN ('pending','generating','recovering')").fetchone()
        require(active["count"] == 0, "a Runtime is active")
        require(not checked.execute("SELECT id FROM learning_lesson_packages WHERE course_id=? LIMIT 1", (item["course_id"],)).fetchone(), "slot already has a package")
        proof = catalog.audit_locked_content_proofs(checked, build_id=identity["buildId"])
        require(set(proof.passed_item_ids) == {identities[0]["buildItemId"], identity["buildItemId"]}
                and not proof.terminal_failed_item_ids and not proof.repairable_item_ids, "actual saved content receipts changed")
        expected = {"content_candidate_count": 2, "content_failed_count": 0, "content_canary_candidate_count": 1, "content_canary_failed_count": 0}
        result = {"status": "prepared", "ownerId": owner["id"], "buildItemId": item["id"],
                  "sourceSnapshotSha256": SNAPSHOT_SHA, "restoredStage": "generating_content", "expectedCounts": expected,
                  "providerCalls": 0, "newPackages": 0, "newOwners": 0}
        if apply:
            idle_processes()
            token, timestamp = uuid.uuid4().hex, now_ms()
            cursor = conn.execute("UPDATE learning_curriculum_preparation_plans SET status='running',stage='generating_content', "
                "error_code=NULL,error_message_safe=NULL,completed_at=NULL,lease_token=?,lease_expires_at=?,heartbeat_at=?, "
                "hard_deadline_at=?,work_unit_kind='coordinator',next_run_at=?,updated_at=? "
                "WHERE id=? AND status='failed' AND stage='completed' AND updated_at=? AND error_code='preparation_validation_failed'",
                (token,timestamp+60000,timestamp,timestamp+60000,timestamp,timestamp,owner["id"],owner["updated_at"]))
            require(cursor.rowcount == 1, "coordinator CAS lost")
            require(preparations.reconcile_shared_build(conn,build_id=identity["buildId"],target_fingerprint=identity["targetFingerprint"],
                    now=timestamp,owner_plan_id=owner["id"],owner_lease_token=token) == 1, "normal content audit did not refresh this owner")
            restored = preparations.get_plan(conn,plan_id=owner["id"])
            require(all(restored[k] == v for k,v in expected.items()), "normal audit produced unexpected content counts")
            check_actual_reservation_gate(conn,database_url,restored,item)
            conn.execute("UPDATE learning_curriculum_preparation_plans SET lease_token=NULL,lease_expires_at=NULL,heartbeat_at=NULL,hard_deadline_at=NULL, "
                         "work_unit_kind=NULL,next_run_at=?,updated_at=? WHERE id=? AND lease_token=?",
                         (now_ms(),now_ms(),owner["id"],token))
            result.update(status="restored", normalPackageReservationGatePassed=True,
                          contentReceiptSha256=item["content_receipt_hash"], sourceSnapshot=str(SNAPSHOT))
            preparations.append_event(conn,plan_id=owner["id"],event_type=EVENT,stage="generating_content",
                payload={"buildItemId": item["id"], "auditShaId": SNAPSHOT_SHA,
                         "generationJobId": state["generationJob"]["id"], "contentReceiptShaId": item["content_receipt_hash"],
                         "candidateCount": 2, "failedCount": 0, "code": "normal_package_gate_passed"},now=now_ms())
            conn.commit()
        else:
            conn.rollback()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-workers-stopped", action="store_true", required=True)
    args = parser.parse_args()
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(run(args.apply),ensure_ascii=False,sort_keys=True))
