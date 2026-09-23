"""Import only the completed ZH6A01.01 slot-two Native audio receipts once.

No generation, TTS, ASR or publication is dispatched. The existing audio importer
performs its ordinary request, WAV, transcript and receipt validation unchanged.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from content.learning_budget_policy import canonical, digest
from core.database import Database
from repositories.learning_teacher_media_repository import LearningTeacherMediaRepository
from scripts.generate_one_library_course import LOCK_PATH, emit, operator_app
from scripts.generate_progressive_preview import assert_preview_policy, preview_identities
from services.learning_audio_transport_terminal import (
    ITEM, JOB, JOB_PATH, JOB_SHA, RUNTIME, REQUEST,
    INPUT_SHA, STAGE, SCOPE, assert_selected_audio_terminal,
)
from services.learning_media_materialization_service import FormalQwenAudioService
from services.service_factory import learning_curriculum_preparation_checkpoint_adapter

BUILD = "catalog_build_72d51e4443727df7b5480f1c"
RELEASE = "catalog_release_72d51e4443727df7b5480f1c"
COURSE = "progressive_b651e7b1bd7621f188e7b80f"
AUDITS = BACKEND.parent / "output/progressive-preview/slot2-audio-import"
SCHEMA = "mira.progressive-slot2-audio-import.v1"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class ExactSlotRepository(LearningTeacherMediaRepository):
    """Fail before any global cleanup or a different item's reservation/claim."""

    def terminalize_stale_formal_audio_jobs(self, conn, *, now, limit=10):
        count = conn.execute("SELECT COUNT(*) AS n FROM learning_formal_qwen_audio_jobs WHERE state='processing'").fetchone()["n"]
        require(count == 0, "another audio import exists; global stale cleanup must remain empty")
        return super().terminalize_stale_formal_audio_jobs(conn, now=now, limit=limit)

    def get_next_unreserved_formal_audio_authority(self, conn, **scope):
        row = super().get_next_unreserved_formal_audio_authority(conn, **scope)
        require(row is None or row["build_item_id"] == ITEM and row["runtime_classroom_id"] == RUNTIME,
                "another classroom would be reserved")
        return row

    def get_next_pending_formal_audio_job(self, conn, **scope):
        row = super().get_next_pending_formal_audio_job(conn, **scope)
        require(row is None or row["build_item_id"] == ITEM and row["runtime_classroom_id"] == RUNTIME,
                "another audio import would be claimed")
        return row


def preflight(database, repository, identity):
    native_raw = JOB_PATH.read_bytes()
    native = json.loads(native_raw)
    completion_path = JOB_PATH.parent.parent / "formal-saved-stage-recoveries" / JOB / "completion.json"
    completion = json.loads(completion_path.read_bytes())
    require(native.get("id") == JOB and native.get("status") == "succeeded" and not native.get("error")
        and native.get("runtimeRequestId") == REQUEST and native.get("formalInputSha256") == INPUT_SHA
        and (native.get("result") or {}).get("classroomId") == STAGE,
        "the original Native job has not completed normally")
    recovery = native.get("formalSavedStageRecovery") or {}
    require(recovery.get("sourceJobSha256") == JOB_SHA
        and completion.get("sourceJobSha256") == JOB_SHA
        and recovery.get("receiptSha256") == completion.get("receiptSha256")
        and completion.get("stageId") == STAGE,
        "the saved-stage completion differs from the exact original failed job")
    conn = database.connect()
    try:
        conn.execute("START TRANSACTION READ ONLY")
        require(conn.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()["n"] == 0,
                "a Provider call is still active")
        assert_selected_audio_terminal(conn, identity=identity, runtime_id=RUNTIME)
        require(conn.execute("SELECT COUNT(*) AS n FROM learning_formal_qwen_audio_jobs WHERE state='processing'").fetchone()["n"] == 0,
                "an active/stale audio import would be affected by the global sweep")
        item = conn.execute("SELECT * FROM learning_catalog_build_items WHERE id=?", (ITEM,)).fetchone()
        runtime = conn.execute("SELECT * FROM learning_openmaic_runtime_classrooms WHERE id=?", (RUNTIME,)).fetchone()
        receipt = conn.execute("SELECT * FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?", (ITEM,)).fetchone()
        require(item and runtime and receipt, "exact classroom authority is missing")
        require(item["build_job_id"] == BUILD and item["release_id"] == RELEASE and item["course_id"] == COURSE
            and item["subject"] == "chinese" and item["variant_ordinal"] == 2
            and item["content_phase"] == "course_ready" and item["content_gate_status"] == "passed",
            "exact source content/release changed")
        require(runtime["status"] == "ready" and runtime.get("retired_at") is None
            and runtime["candidate_build_item_id"] == ITEM and runtime["candidate_release_id"] == RELEASE
            and runtime["candidate_target_fingerprint"] == identity["targetFingerprint"]
            and runtime["course_id"] == COURSE and runtime["request_id"] == REQUEST
            and runtime["upstream_job_id"] == JOB and runtime["upstream_classroom_id"] == STAGE
            and receipt["runtime_classroom_id"] == RUNTIME and receipt["classroom_status"] == "passed",
            "exact Runtime has not passed Host reconciliation")
        scope = {"build_id": BUILD, "release_id": RELEASE, "target_fingerprint": identity["targetFingerprint"]}
        existing = repository.get_formal_audio_job(conn, build_item_id=ITEM)
        unreserved = repository.get_next_unreserved_formal_audio_authority(conn, **scope)
        pending = repository.get_next_pending_formal_audio_job(conn, **scope)
        done = bool(existing and existing["state"] == "auto_validated"
            and all(receipt.get(key) == "passed" for key in ("tts_status", "asr_roundtrip_status")))
        if not done:
            require(all(receipt.get(key) == "pending" for key in ("tts_status", "asr_roundtrip_status")),
                    "an existing partial/rejected import requires diagnosis")
            require((existing is None and unreserved is not None and pending is None)
                or (existing is not None and existing["state"] == "pending" and unreserved is None and pending is not None),
                "the importer cannot select exactly this untouched audio job")
            if existing:
                segments = repository.list_formal_audio_segments(conn, build_item_id=ITEM)
                require(segments and all(s["state"] == "pending" for s in segments), "partial audio import cannot be replayed")
        return {"schemaVersion": SCHEMA, "identity": identity, "scope": scope,
            "nativeJobSha256": hashlib.sha256(native_raw).hexdigest(),
            "completionReceiptSha256": completion["receiptSha256"], "item": dict(item), "runtime": dict(runtime),
            "receipt": dict(receipt), "audioJob": dict(existing) if existing else None, "alreadyValidated": done}
    finally:
        conn.rollback()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--budget-policy", required=True)
    parser.add_argument("--expected-preflight-sha")
    parser.add_argument("--confirm-workers-stopped", action="store_true")
    args = parser.parse_args()
    if args.mode == "apply" and not (args.expected_preflight_sha and args.confirm_workers_stopped):
        parser.error("apply requires --expected-preflight-sha and --confirm-workers-stopped")
    if args.mode == "plan" and args.expected_preflight_sha:
        parser.error("plan does not take an expected SHA")
    args.grade = "primary_6"
    identities = preview_identities(args.grade)
    identity = next(i for i in identities if i["buildItemId"] == ITEM)
    require(identity["scope"] == SCOPE, "frozen progressive scope changed")
    assert_preview_policy(args.budget_policy, identities)
    app = operator_app(args, publishing=False)
    database = Database(app.config["DATABASE_URL"])
    repository = ExactSlotRepository(database)
    with LOCK_PATH.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = preflight(database, repository, identity)
        if current["alreadyValidated"]:
            emit("audio_already_imported", buildItemId=ITEM, runtimeId=RUNTIME, providerCalls=0)
            return 0
        sha = digest(current)
        if args.mode == "plan":
            AUDITS.mkdir(parents=True, exist_ok=True)
            path = AUDITS / (sha + ".json")
            if path.exists():
                require(digest(json.loads(path.read_text())) == sha, "existing preflight archive changed")
            else:
                with path.open("x", encoding="utf-8") as output:
                    path.chmod(0o600)
                    output.write(canonical(current) + "\n")
            emit("audio_import_plan", preflightPath=str(path), preflightSha256=sha, databaseWrites=0, providerCalls=0)
            return 0
        require(args.expected_preflight_sha == sha, "audio import source changed after the reviewed preflight")
        require(digest(json.loads((AUDITS / (sha + ".json")).read_text())) == sha, "preflight archive changed")
        with app.app_context():
            existing_service = learning_curriculum_preparation_checkpoint_adapter().formal_audio_service
            require(existing_service is not None, "normal formal audio importer is unavailable")
            # Reuse precisely the normal importer/client/storage, with exact queue guards.
            service = FormalQwenAudioService(repository, runtime_client=existing_service.runtime_client,
                asset_store=existing_service.asset_store, clock=existing_service.clock)
            result = service.process_next(**current["scope"])
        # No loop/retry: a partial local failure stays recorded for diagnosis.
        emit("audio_import_result", buildItemId=ITEM, runtimeId=RUNTIME, result=result, providerCalls=0)
        require(preflight(database, repository, identity)["alreadyValidated"], "audio import did not validate every segment; no retry was attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
