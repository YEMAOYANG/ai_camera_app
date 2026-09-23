"""Explicit progressive-version content work within the formal preparation graph.

The legacy question phase graph is never replayed for these jobs. Accepted
content carries the progressive host receipt, then uses the existing formal
Runtime, audio/ASR, media and publication gates.
"""
from __future__ import annotations

import json
import uuid

from core.errors import ApiError
from services.learning_curriculum_preparation_contract import (
    canonical_preparation_target_for,
)
from services.progressive_course_generation import (
    VALIDATION_SCHEMA, digest, validate_progressive_course_for_release,
)


def audit_progressive_content(catalog, conn, *, build):
    from services.learning_catalog_release_service import ContentProofAuditSnapshot
    target = json.loads(build["target_spec_json"])
    if target != canonical_preparation_target_for(target):
        raise ValueError("progressive build target drift")
    items = catalog.repository.list_build_items(conn, build_id=build["id"], for_update=True)
    expected = {(item["subject"], item["skillId"], item["variantOrdinal"]): item for item in target["courseTargets"]}
    if len(items) != len(expected): raise ValueError("progressive build item count drift")
    passed, failed, seen = [], [], set()
    for item in items:
        identity = (item["subject"], item["skill_id"], item["variant_ordinal"])
        if identity in seen or identity not in expected: raise ValueError("progressive build item identity drift")
        seen.add(identity)
        if (item["boundary_version"] != expected[identity]["boundaryVersion"]
                or item["curriculum_version"] != target["curriculumVersion"]
                or item["release_id"] != build["release_id"]):
            raise ValueError("progressive build item scope drift")
        if item["status"] == "failed":
            failed.append(item["id"])
        elif item["status"] == "course_ready":
            course = conn.execute("SELECT * FROM learning_courses WHERE id = ? AND version = ? FOR UPDATE",
                                  (item["course_id"], item["course_version"])).fetchone()
            if course is None: raise ValueError("progressive course missing")
            receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=item["skill_id"])
            if (item.get("content_validation_contract_version") != VALIDATION_SCHEMA
                    or item.get("content_receipt_hash") != digest(receipt)
                    or item.get("content_phase") != "course_ready"
                    or item.get("content_gate_status") != "passed"):
                raise ValueError("progressive item receipt drift")
            passed.append(item["id"])
        elif item["status"] not in {"pending", "processing"}:
            raise ValueError("progressive content lifecycle invalid")
    return ContentProofAuditSnapshot(build_id=build["id"], release_id=build["release_id"],
        passed_item_ids=tuple(passed), repairable_item_ids=(), terminal_failed_item_ids=tuple(failed))


def advance_progressive_content(adapter, plan, *, now_ms):
    from services.learning_curriculum_preparation_runner import (
        LeaseHeartbeatGuard, PreparationStageResult,
    )
    target = json.loads(plan["target_spec_json"])
    if target != canonical_preparation_target_for(target): raise ValueError("progressive target drift")
    catalog = adapter.catalog_service
    generator = catalog.dynamic_generation_service
    if generator is None:
        raise ApiError("progressive_generator_unavailable", "新课次生成服务尚未配置", 409)
    token = uuid.uuid4().hex
    now = int(adapter.clock())
    selected = None
    with adapter.repository.transaction() as conn:
        locked = adapter.repository.get_plan(conn, plan_id=plan["id"], for_update=True)
        if not locked or locked.get("lease_token") != plan["lease_token"] or int(locked.get("lease_expires_at") or 0) <= now:
            raise ValueError("progressive preparation lease lost")
        build = catalog.repository.get_build(conn, build_id=plan["catalog_build_id"], for_update=True)
        if (not build or build.get("target_spec_json") != plan["target_spec_json"]
                or build.get("release_id") != plan["catalog_release_id"]):
            raise ValueError("progressive preparation build drift")
        items = catalog.repository.list_build_items(conn, build_id=build["id"], for_update=True)
        from repositories.course_supply_repository import requested_supply, filter_requested_supply
        requested = requested_supply(conn, build)
        if requested is None:
            raise ValueError("progressive production requires an explicit enabled supply scope")
        items = filter_requested_supply(items, requested)
        canaries = {(item["subject"], item["skillId"], item["variantOrdinal"]) for item in target["canaryManifest"]["targets"]}
        ordered = sorted(items, key=lambda item: ((item["subject"], item["skill_id"], item["variant_ordinal"]) not in canaries,
                                                 item["subject_ordinal"], item["boundary_ordinal"], item["variant_ordinal"]))
        for item in ordered:
            if item["status"] == "pending" or (item["status"] == "processing" and int(item.get("content_lease_expires_at") or 0) <= now):
                selected = item
                break
        if selected:
            # A recovered item reuses the same generation request. The generator
            # reads persisted success/failure and never blindly resends a call.
            conn.execute("UPDATE learning_catalog_build_items SET status='processing', content_phase='progressive_generation', "
                "attempt_count=1, active_generation_request_id=generation_request_id, content_lease_token=?, "
                "content_lease_expires_at=?, content_heartbeat_at=?, updated_at=? WHERE id=?",
                (token, now + adapter.plan_lease_ms, now, now, selected["id"]))
            conn.execute("UPDATE learning_catalog_build_jobs SET status='running', updated_at=? WHERE id=? AND status='queued'", (now, build["id"]))
    if selected:
        def heartbeat():
            current = int(adapter.clock())
            with adapter.repository.transaction() as conn:
                live = adapter.repository.heartbeat(conn, plan_id=plan["id"], lease_token=plan["lease_token"],
                    target_fingerprint=plan["target_fingerprint"], now=current, lease_ms=adapter.plan_lease_ms)
                result = conn.execute("UPDATE learning_catalog_build_items SET content_lease_expires_at=?, content_heartbeat_at=? "
                    "WHERE id=? AND content_lease_token=? AND status='processing'",
                    (current + adapter.plan_lease_ms, current, selected["id"], token))
                return bool(live and result.rowcount == 1)
        guard = LeaseHeartbeatGuard(heartbeat, interval_ms=adapter.heartbeat_interval_ms)
        guard.start()
        try:
            result = generator.generate({"requestId": selected["generation_request_id"],
                "curriculumVersion": target["curriculumVersion"], "lessonId": selected["skill_id"],
                "gradeCode": selected["grade_code"], "subject": selected["subject"], "difficultyCode": "basic"}, enqueue_classroom=False)
        finally:
            guard.stop()
        if guard.failed or not heartbeat(): raise ValueError("progressive content lease lost after generation")
        current = int(adapter.clock())
        with adapter.repository.transaction() as conn:
            if result.payload.get("ok") is True:
                identity = result.payload["course"]
                course = conn.execute("SELECT * FROM learning_courses WHERE id=? AND version=? FOR UPDATE",
                    (identity["id"], identity["version"])).fetchone()
                receipt = validate_progressive_course_for_release(conn, course=course, expected_lesson_id=selected["skill_id"])
                conn.execute("UPDATE learning_catalog_build_items SET status='course_ready', content_phase='course_ready', "
                    "course_id=?, course_version=?, content_gate_status='passed', content_gate_passed_at=?, "
                    "content_validation_contract_version=?, content_receipt_hash=?, content_lease_token=NULL, "
                    "content_lease_expires_at=NULL, content_heartbeat_at=NULL, updated_at=? WHERE id=? AND content_lease_token=?",
                    (course["id"], course["version"], current, VALIDATION_SCHEMA, digest(receipt), current, selected["id"], token))
            else:
                conn.execute("UPDATE learning_catalog_build_items SET status='failed', content_phase='failed', "
                    "content_gate_status='failed', error_code=?, error_message_safe=?, content_lease_token=NULL, "
                    "content_lease_expires_at=NULL, content_heartbeat_at=NULL, updated_at=? WHERE id=? AND content_lease_token=?",
                    (str(result.payload.get("error") or "progressive_generation_failed")[:128],
                     str(result.payload.get("message") or "课程生成未通过")[:512], current, selected["id"], token))
    current = int(adapter.clock())
    with adapter.repository.transaction() as conn:
        adapter.repository.reconcile_shared_build(conn, build_id=plan["catalog_build_id"],
            target_fingerprint=plan["target_fingerprint"], now=current,
            owner_plan_id=plan["id"], owner_lease_token=plan["lease_token"])
        refreshed = adapter.repository.get_plan(conn, plan_id=plan["id"])
        if refreshed["stage"] == "generating_content" and refreshed.get("lease_token") == plan["lease_token"]:
            if not adapter.repository.release_content_continuation(conn, plan_id=plan["id"],
                    plan_lease_token=plan["lease_token"], target_fingerprint=plan["target_fingerprint"],
                    catalog_build_id=plan["catalog_build_id"], next_run_at=current+5000, now=current, progressed=selected is not None):
                raise ValueError("progressive content continuation authority changed")
            refreshed = adapter.repository.get_plan(conn, plan_id=plan["id"])
    return PreparationStageResult(next_status=str(refreshed["status"]), next_stage=str(refreshed["stage"]),
        ready_course_count=int(refreshed["ready_course_count"]), failed_course_count=int(refreshed["failed_course_count"]),
        subject_progress=json.loads(refreshed["subject_progress_json"]), next_run_at=current + 1000,
        catalog_build_id=plan["catalog_build_id"], catalog_release_id=plan["catalog_release_id"],
        hard_deadline_at=None, already_persisted=True, result_kind="progressed")
