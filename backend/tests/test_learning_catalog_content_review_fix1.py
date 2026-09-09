from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import inspect
import json
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import repositories.learning_catalog_repository as catalog_repository_module
from content.primary_skill_boundaries import CONTENT_VALIDATION_CONTRACT_VERSION
from integrations.openmaic_question_adapter import QUESTION_PHASE_IO
from core.database import Database
from repositories.learning_catalog_repository import (
    LearningCatalogBuildConflict,
    LearningCatalogRepository,
)
from services.dynamic_learning_course_generation_service import ContentPhaseAdvance
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
)
from services.learning_generated_course_validator import (
    AcceptedPrimaryOneHostReceipt,
    LearningGeneratedCourseValidator,
)
from services.learning_catalog_validator import PrimaryOneCourseTarget
from tests.test_learning_checkpoint2_zero_bypass import (
    _MemoryContentRepository,
    _MemoryStagedGenerator,
    _PassingMemoryHost,
    _memory_content_service,
)
from tests.test_learning_generated_course_validator import formal_host_fixture


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class LearningCatalogContentReviewFixOneRedTest(unittest.TestCase):
    def test_v71_attempt_claim_persists_a_240_second_provider_work_unit(self):
        class Connection:
            def __init__(self):
                self.executions = []

            def execute(self, statement, params=()):
                self.executions.append((statement, params))
                return _Cursor(rowcount=1)

        repository = object.__new__(LearningCatalogRepository)
        repository._mark_build_running = lambda *args, **kwargs: None
        repository.get_item = lambda *args, **kwargs: {"id": "item-1"}
        connection = Connection()

        claimed = repository._claim_content_attempt(
            connection,
            build={"id": "build-1"},
            row={"id": "item-1", "generation_request_id": "request-1"},
            attempt=1,
            now=1_000,
        )

        self.assertEqual(claimed, {"id": "item-1"})
        params = connection.executions[0][1]
        self.assertEqual(params[4], 241_000)
        self.assertEqual(params[8], 241_000)
        self.assertEqual(params[7], 1_801_000)

    def test_v71_public_initial_claim_uses_the_same_240_second_budget(self):
        class Connection:
            def __init__(self):
                self.executions = []

            def execute(self, statement, params=()):
                self.executions.append((statement, params))
                return _Cursor(rowcount=1)

        repository = object.__new__(LearningCatalogRepository)
        target = build_preparation_target("primary_1")
        build = {
            "id": "build-1",
            "release_id": "release-1",
            "execution_mode": "content_only",
            "stage_ceiling": "content_ready",
            "status": "queued",
            "curriculum_version": target["curriculumVersion"],
            "target_spec_json": _canonical_json(target),
            "content_manifest_version": target["schemaVersion"],
            "canary_manifest_json": _canonical_json(target["canaryManifest"]),
        }
        release = {
            "id": "release-1",
            "curriculum_version": target["curriculumVersion"],
        }
        immutables = repository._expected_content_item_immutables(
            build_id=build["id"],
            release_id=release["id"],
            curriculum_version=target["curriculumVersion"],
            content_manifest_version=target["schemaVersion"],
            course_targets=target["courseTargets"],
        )
        rows = [
            {
                **item,
                "status": "pending",
                "attempt_count": 0,
                "content_phase": "not_started",
                "content_gate_status": "not_started",
                "package_attempt_count": 0,
                "active_package_request_id": None,
                "package_id": None,
                "package_version": None,
            }
            for item in immutables
        ]
        repository.lock_build_authority = (
            lambda *args, **kwargs: (release, build)
        )
        repository.list_build_items = lambda *args, **kwargs: rows
        repository._release_has_catalog_items = lambda *args, **kwargs: False
        repository._mark_build_running = lambda *args, **kwargs: None
        repository.get_item = lambda *args, **kwargs: rows[0]
        connection = Connection()

        claimed = repository.claim_next_content_item(
            connection,
            build_id=build["id"],
            now=1_000,
            lease_ms=240_000,
        )

        self.assertIsNotNone(claimed)
        params = connection.executions[0][1]
        self.assertEqual(params[1], 241_000)
        self.assertEqual(params[4], 1_801_000)
        self.assertEqual(params[5], 241_000)

    def test_stale_item_contract_and_wrong_pointer_cannot_be_a_passed_proof(self):
        service = object.__new__(LearningCatalogReleaseService)
        course, target, boundary, evidence, identity = formal_host_fixture(
            "number_sense_20"
        )
        validator = LearningGeneratedCourseValidator()
        result = validator.validate_primary_one_host_gate(
            evidence,
            target=target,
            identity=identity,
            skill_boundary=boundary,
            accepted_host_receipts=(),
        )
        self.assertEqual(result.outcome, "passed")
        self.assertIsNotNone(result.course)

        envelope = {
            "schemaVersion": "mira.learning.primary-1-host-gate-evidence.v1",
            "contentFingerprint": result.receipt["hostContentFingerprint"],
            "hostGateReceipt": result.receipt,
            "hostGateReceiptHash": result.receipt_hash,
        }
        row = {
            "id": identity.catalog_item_id,
            "subject": target.subject,
            "subject_ordinal": target.subject_ordinal,
            "skill_id": target.skill_id,
            "boundary_ordinal": target.boundary_ordinal,
            "boundary_version": target.boundary_version,
            "variant_ordinal": target.variant_ordinal,
            "status": "course_ready",
            "content_phase": "course_ready",
            "content_gate_status": "passed",
            "content_gate_passed_at": 100_000,
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "active_generation_request_id": identity.generation_request_id,
            "content_validation_contract_version": "stale.contract.v0",
            "content_receipt_hash": result.receipt_hash,
            "course_id": "different-course-pointer",
            "course_version": result.course["version"],
            "content_lease_token": None,
            "content_lease_expires_at": None,
            "content_provider_attempt_hard_deadline_at": None,
            "content_work_unit_deadline_at": None,
        }
        job = {
            "id": "job-1",
            "request_id": identity.generation_request_id,
            "status": "validated",
        }
        candidate = {
            "id": "candidate-1",
            "job_id": job["id"],
            "ordinal": 1,
            "course_id": result.course["id"],
            "course_version": result.course["version"],
            "status": "course_validated",
            "content_json": _canonical_json(course["content"]),
            "validation_json": _canonical_json(envelope),
        }
        course_row = {
            "id": result.course["id"],
            "version": result.course["version"],
            "status": "validated",
            "published_at": None,
            "content_json": _canonical_json(result.course["content"]),
            "generation_content_hash": result.receipt[
                "hostContentFingerprint"
            ],
        }
        connection = _EvidenceConnection(
            job=job,
            candidate=candidate,
            course=course_row,
            dispatches=[],
        )

        with self.assertRaises(ValueError):
            service._validate_locked_passed_evidence(
                evidence={
                    "item": row,
                    "job": job,
                    "candidate": candidate,
                    "course": course_row,
                    "dispatches": [],
                },
                prior_evidence=(),
            )

    def test_second_fence_cannot_overwrite_first_terminal_reason(self):
        repository = object.__new__(LearningCatalogRepository)
        connection = _RecordingConnection()
        failed_build = {
            "id": "build-1",
            "status": "failed",
            "error_code": "preparation_provider_dispatch_outcome_unknown",
            "error_message_safe": "正式备课内容阶段已安全终止。",
            "completed_at": 100_000,
        }

        repository._fence_content_build_locked(
            connection,
            build=failed_build,
            rows=[],
            error_code="preparation_content_contract_drift",
            now=200_000,
        )

        self.assertEqual(connection.executions, [])

    def test_provider_completion_after_build_fence_writes_nothing(self):
        self.assertFalse(
            hasattr(LearningCatalogRepository, "complete_content_provider_phase")
        )
        self.assertTrue(
            hasattr(
                LearningCatalogRepository,
                "load_content_provider_finalize_authority",
            )
        )
        self.assertTrue(
            hasattr(
                LearningCatalogRepository,
                "_complete_content_provider_phase_locked",
            )
        )

    def test_crash_before_dispatch_reuses_same_live_provider_work_identity(self):
        repository = object.__new__(LearningCatalogRepository)
        now = 100_000
        row = {
            "id": "item-1",
            "build_job_id": "build-1",
            "status": "processing",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "outline",
            "content_lease_token": "original-live-lease",
            "content_lease_expires_at": now + 120_000,
            "content_provider_attempt_hard_deadline_at": now + 1_800_000,
            "content_work_unit_deadline_at": now + 120_000,
        }
        connection = _EvidenceConnection(dispatches=[])
        repository.get_item = lambda conn, *, item_id: copy.deepcopy(row)

        recovered = repository._claim_existing_provider_phase(
            connection,
            build={"id": "build-1", "status": "running"},
            row=row,
            now=now + 1,
            locked_dispatches=[],
        )

        self.assertEqual(recovered, row)
        self.assertEqual(recovered["content_lease_token"], "original-live-lease")
        self.assertEqual(
            recovered["content_lease_expires_at"],
            row["content_work_unit_deadline_at"],
        )
        self.assertEqual(connection.updates, [])

    def test_task5_stale_rereads_ambiguous_ledger_and_fences(self):
        now = 100_000
        repository = _StaleLedgerRepository(now=now)
        staged = _StaleAfterAmbiguousGenerator(repository)
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=_PassingMemoryHost(),
        )

        result = service.advance_content(
            "catalog-build-canary",
            heartbeat=lambda: True,
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(
            repository.last_error_code,
            "preparation_provider_dispatch_outcome_unknown",
        )
        self.assertEqual(staged.calls, 1)

    def test_stale_provider_reread_classifies_all_frozen_ledger_states(self):
        now = 100_000
        base_row = {
            "id": "item-1",
            "status": "processing",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "outline",
            "content_lease_token": "lease-1",
        }
        cases = (
            (None, True, "stale", None),
            ("dispatched", True, "busy", None),
            (
                "dispatched",
                False,
                "failed",
                "preparation_provider_dispatch_outcome_unknown",
            ),
            ("succeeded", False, "succeeded", None),
            (
                "ambiguous",
                False,
                "failed",
                "preparation_provider_dispatch_outcome_unknown",
            ),
            (
                "failed_safe",
                False,
                "failed",
                "preparation_content_provider_unavailable",
            ),
        )
        for status, live, expected, error_code in cases:
            with self.subTest(status=status, live=live):
                repository = object.__new__(LearningCatalogRepository)
                row = {
                    **base_row,
                    "content_lease_expires_at": now + 1 if live else now - 1,
                    "content_work_unit_deadline_at": now + 1 if live else now - 1,
                }
                repository.lock_build_authority = lambda conn, *, build_id: (
                    {"id": "release-1"},
                    {"id": build_id, "status": "running"},
                )
                repository.list_build_items = (
                    lambda conn, *, build_id, for_update: [row]
                )
                repository._content_authority_is_exact = (
                    lambda *args, **kwargs: True
                )
                dispatch = (
                    {
                        "build_item_id": row["id"],
                        "logical_attempt": 1,
                        "generation_request_id": "request-1",
                        "phase": "outline",
                        "phase_ordinal": 1,
                        "item_lease_token": "lease-1",
                        "status": status,
                    }
                    if status is not None
                    else None
                )
                repository.list_content_dispatches = (
                    lambda *args, **kwargs: [dispatch] if dispatch else []
                )
                fenced: list[str] = []
                repository._fence_content_build_locked = (
                    lambda conn, *, error_code, **kwargs: fenced.append(
                        error_code
                    )
                )

                result = repository.reconcile_content_provider_stale(
                    _RecordingConnection(),
                    build_id="build-1",
                    item_id="item-1",
                    logical_attempt=1,
                    generation_request_id="request-1",
                    phase="outline",
                    phase_ordinal=1,
                    lease_token="lease-1",
                    now=now,
                )

                self.assertEqual(result["action"], expected)
                self.assertEqual(fenced, [error_code] if error_code else [])

    def test_late_host_completion_after_build_fence_writes_nothing(self):
        repository = object.__new__(LearningCatalogRepository)
        now = 100_000
        row = {
            "id": "item-1",
            "build_job_id": "build-1",
            "status": "processing",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "host_gate_running",
            "content_gate_attempt_count": 1,
            "content_lease_token": "host-lease-1",
            "content_lease_expires_at": now + 120_000,
            "content_work_unit_deadline_at": now + 120_000,
        }
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1", "status": "draft"},
            {
                "id": build_id,
                "status": "failed",
                "error_code": "preparation_content_contract_drift",
            },
        )
        repository.list_build_items = lambda conn, *, build_id, for_update: [
            row
        ]
        connection = _RecordingConnection()

        rejected_receipt = {"outcome": "rejected"}
        persisted = repository.complete_content_host_gate(
            connection,
            build_id="build-1",
            item_id="item-1",
            logical_attempt=1,
            generation_request_id="request-1",
            course=None,
            receipt=rejected_receipt,
            receipt_hash=hashlib.sha256(
                _canonical_json(rejected_receipt).encode("utf-8")
            ).hexdigest(),
            outcome="rejected",
            lease_token="host-lease-1",
            gate_ordinal=1,
            now=now + 1,
        )

        self.assertIsNone(persisted)
        self.assertEqual(connection.executions, [])

    def test_host_completion_rejects_a_heartbeat_extended_item_lease(self):
        repository = object.__new__(LearningCatalogRepository)
        now = 100_000
        work_deadline = now + 120_000
        row = {
            "id": "item-1",
            "build_job_id": "build-1",
            "status": "processing",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "host_gate_running",
            "content_gate_attempt_count": 1,
            "content_lease_token": "host-lease-1",
            "content_lease_expires_at": work_deadline + 1,
            "content_work_unit_deadline_at": work_deadline,
        }
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1", "status": "draft"},
            {"id": build_id, "status": "running"},
        )
        repository.list_build_items = lambda conn, *, build_id, for_update: [
            row
        ]
        repository._content_authority_is_exact = lambda *args, **kwargs: True
        repository.list_content_dispatches = lambda *args, **kwargs: (
            _ for _ in ()
        ).throw(AssertionError("changed Host lease must fail before proof locks"))

        persisted = repository.complete_content_host_gate(
            _RecordingConnection(),
            build_id="build-1",
            item_id="item-1",
            logical_attempt=1,
            generation_request_id="request-1",
            course=None,
            receipt={},
            receipt_hash="a" * 64,
            outcome="rejected",
            lease_token="host-lease-1",
            gate_ordinal=1,
            now=now,
        )

        self.assertIsNone(persisted)

    def test_host_evidence_mutation_between_judgment_and_finalize_fences(self):
        repository = _MutatingHostFinalizeRepository()
        service = object.__new__(LearningCatalogReleaseService)
        service.repository = repository
        service.primary_one_host_validator = _DeterministicPassedHost()
        service.catalog_validator = object()
        service._content_clock_ms = lambda: 100_000
        calls = 0

        def host_evidence(*, plan, item):
            nonlocal calls
            calls += 1
            if plan.get("mutated") is True:
                raise ValueError("locked Host evidence changed")
            return object(), SimpleNamespace(variant_ordinal=1), object(), ()

        service._content_host_evidence = host_evidence
        item = {
            "id": "item-1",
            "skill_id": "number_sense_20",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_lease_token": "host-lease-1",
            "content_gate_attempt_count": 1,
            "content_work_unit_deadline_at": 200_000,
        }

        result = service._advance_content_host(
            build_id="build-1",
            plan={"candidate": {}, "dispatches": []},
            item=item,
            summary=service._empty_content_summary(),
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(calls, 2)
        self.assertEqual(repository.complete_calls, 0)
        self.assertEqual(repository.fence_calls, 1)

    def test_handoff_mutation_between_classification_and_return_fences(self):
        repository = _MutatingLockedAuditRepository(action="handoff")
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=_NeverCalledStagedGenerator(),
            host=_PassingMemoryHost(),
        )
        service._audit_locked_content_inventory = (
            lambda **kwargs: (_ for _ in ()).throw(
                ValueError("handoff proof changed under lock")
            )
        )

        result = service.advance_content("catalog-build-canary", heartbeat=lambda: True)

        self.assertEqual(result.kind, "failed")
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(repository.claim_attempt_two_calls, 0)

    def test_attempt_two_mutation_between_classification_and_claim_fences(self):
        repository = _MutatingLockedAuditRepository(action="attempt2")
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=_NeverCalledStagedGenerator(),
            host=_PassingMemoryHost(),
        )
        service._audit_locked_content_inventory = (
            lambda **kwargs: (_ for _ in ()).throw(
                ValueError("attempt-one proof changed under lock")
            )
        )

        result = service.advance_content("catalog-build-canary", heartbeat=lambda: True)

        self.assertEqual(result.kind, "failed")
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(repository.claim_attempt_two_calls, 0)

    def test_locked_attempt_two_success_claims_once_without_nested_transaction(self):
        receipt = {
            "outcome": "rejected",
            "hostContentFingerprint": "a" * 64,
            "issues": [
                {"code": "question_duplicate", "message": "题目重复。"}
            ],
        }
        receipt_hash = hashlib.sha256(
            _canonical_json(receipt).encode("utf-8")
        ).hexdigest()
        envelope = {
            "schemaVersion": "mira.learning.primary-1-host-gate-evidence.v1",
            "contentFingerprint": receipt["hostContentFingerprint"],
            "hostGateReceipt": receipt,
            "hostGateReceiptHash": receipt_hash,
        }
        repository = _LockedAttemptTwoRepository()
        service = object.__new__(LearningCatalogReleaseService)
        service.repository = repository
        service.primary_one_host_validator = _DeterministicRejectedHost(
            receipt=receipt,
            receipt_hash=receipt_hash,
        )
        service._content_clock_ms = lambda: 100_000
        service._content_host_evidence = lambda **kwargs: (
            object(),
            object(),
            object(),
            (),
        )
        summary = service._empty_content_summary()
        item = {
            "id": "item-1",
            "skill_id": "number_sense_20",
            "generation_request_id": "request-1",
            "course_id": "course-1",
            "course_version": "v1",
        }

        result = service._authorize_content_attempt_two(
            build_id="build-1",
            plan={
                "attemptOneEvidence": {
                    "candidate": {"validation_json": _canonical_json(envelope)},
                    "dispatches": [],
                }
            },
            item=item,
            summary=summary,
            conn=object(),
        )

        self.assertEqual(result.kind, "progressed")
        self.assertEqual(result.content_summary, summary)
        self.assertEqual(repository.claim_calls, 1)
        self.assertEqual(repository.transaction_calls, 0)

    def test_rejected_attempt_proof_binds_immutable_unverified_course(self):
        course, target, _boundary, _host_evidence, identity = formal_host_fixture(
            "pinyin_syllables"
        )
        service = object.__new__(LearningCatalogReleaseService)
        profile = {
            "name": "kimi",
            "model": "moonshot-v1-8k",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "APP_AI_API_KEY",
            "timeoutMs": 1_000,
            "maxTokens": 2_000,
            "temperature": 0.2,
        }
        service.question_phase_provider_profiles = {
            "generator": profile,
            "verifier": copy.deepcopy(profile),
        }
        curriculum = build_preparation_target("primary_1")[
            "curriculumVersion"
        ]
        item = {
            "grade_code": target.grade_code,
            "subject": target.subject,
            "skill_id": target.skill_id,
            "curriculum_version": curriculum,
            "boundary_version": target.boundary_version,
            "active_generation_request_id": identity.generation_request_id,
        }
        request_id = identity.generation_request_id
        job_id = "learning_course_job_" + hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest()[:32]
        fingerprint = hashlib.sha256(
            _canonical_json(
                {
                    "gradeCode": target.grade_code,
                    "subject": target.subject,
                    "nodeCode": target.skill_id,
                    "curriculumVersion": curriculum,
                    "boundaryVersion": target.boundary_version,
                    "generator": "openmaic_question_phase_v2",
                    "providerProfile": profile,
                    "requestedCandidateCount": 1,
                }
            ).encode("utf-8")
        ).hexdigest()
        candidate_id = "learning_course_candidate_" + hashlib.sha256(
            f"{job_id}:1".encode("utf-8")
        ).hexdigest()[:32]
        content_hash = hashlib.sha256(
            _canonical_json(
                {
                    "gradeCode": course["gradeCode"],
                    "subject": course["subject"],
                    "nodeCode": course["nodeCode"],
                    "title": course["title"],
                    "objective": course["objective"],
                    "content": course["content"],
                }
            ).encode("utf-8")
        ).hexdigest()
        evidence = {
            "job": {
                "id": job_id,
                "request_id": request_id,
                "request_fingerprint": fingerprint,
                "grade_code": target.grade_code,
                "subject": target.subject,
                "node_code": target.skill_id,
                "curriculum_version": curriculum,
                "boundary_version": target.boundary_version,
                "generator": "openmaic_question_phase_v2",
                "provider": profile["name"],
                "model": profile["model"],
                "prompt_version": "mira.learning.question-contract.v2",
                "requested_candidate_count": 1,
                "status": "failed",
                "error_code": "preparation_content_validation_failed",
                "error_message_safe": "内容未通过本地确定性门禁。",
            },
            "candidate": {
                "id": candidate_id,
                "job_id": job_id,
                "ordinal": 1,
                "course_id": course["id"],
                "course_version": course["version"],
                "grade_code": course["gradeCode"],
                "subject": course["subject"],
                "node_code": course["nodeCode"],
                "curriculum_version": curriculum,
                "boundary_version": target.boundary_version,
                "title": course["title"],
                "objective": course["objective"],
                "status": "rejected",
                "content_hash": content_hash,
                "content_json": _canonical_json(course["content"]),
                "validation_json": _canonical_json(
                    {
                        "schemaVersion": "mira.learning.primary-1-host-gate-evidence.v1",
                        "contentFingerprint": "",
                        "hostGateReceipt": {"outcome": "rejected"},
                        "hostGateReceiptHash": "a" * 64,
                    }
                ),
                "published_at": None,
                "error_code": "preparation_content_validation_failed",
                "error_message_safe": "内容未通过本地确定性门禁。",
            },
            "course": {
                "id": course["id"],
                "version": course["version"],
                "grade_code": course["gradeCode"],
                "subject": course["subject"],
                "node_code": course["nodeCode"],
                "curriculum_version": curriculum,
                "boundary_version": target.boundary_version,
                "title": course["title"],
                "objective": course["objective"],
                "status": "unverified",
                "quality_status": "legacy_unreviewed",
                "content_origin": "openmaic_generated",
                "generator": "openmaic_question_phase_v2",
                "generation_request_id": request_id,
                "generation_content_hash": content_hash,
                "content_json": _canonical_json(course["content"]),
                "published_at": None,
                "retired_at": None,
            },
        }
        service._validate_locked_generation_persistence(
            evidence=evidence,
            item=item,
            candidate_course=course,
            expected_job_status="failed",
            expected_candidate_status="rejected",
        )

        drifted = copy.deepcopy(evidence)
        drifted["course"]["content_json"] = "{}"
        with self.assertRaises(ValueError):
            service._validate_locked_generation_persistence(
                evidence=drifted,
                item=item,
                candidate_course=course,
                expected_job_status="failed",
                expected_candidate_status="rejected",
            )

    def test_provider_profiles_are_exact_strict_and_secret_free(self):
        service = object.__new__(LearningCatalogReleaseService)
        valid = {
            "name": "kimi",
            "model": "moonshot-v1-8k",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "APP_AI_API_KEY",
            "timeoutMs": 60_000,
            "maxTokens": 8_000,
            "temperature": 0.2,
        }
        service.question_phase_provider_profiles = {
            "generator": valid,
            "verifier": copy.deepcopy(valid),
        }
        self.assertEqual(service._content_profile_payload("generator"), valid)
        service.question_phase_provider_profiles["generator"] = {
            **valid,
            "timeoutMs": 180_000,
        }
        self.assertEqual(
            service._content_profile_payload("generator")["timeoutMs"],
            180_000,
        )
        service.question_phase_provider_profiles["generator"] = valid

        invalid_profiles = (
            {**valid, "apiKey": "secret-should-be-rejected"},
            {key: value for key, value in valid.items() if key != "baseUrl"}
            | {"base_url": valid["baseUrl"]},
            {**valid, "name": ""},
            {**valid, "name": "n" * 129},
            {**valid, "model": ""},
            {**valid, "model": "m" * 129},
            {**valid, "baseUrl": "https://example.com/" + "x" * 490},
            {**valid, "timeoutMs": True},
            {**valid, "timeoutMs": 999},
            {**valid, "timeoutMs": 180_001},
            {**valid, "maxTokens": True},
            {**valid, "maxTokens": 511},
            {**valid, "maxTokens": 32_001},
            {**valid, "temperature": True},
            {**valid, "temperature": math.nan},
            {**valid, "temperature": math.inf},
            {**valid, "temperature": -0.1},
            {**valid, "temperature": 1.1},
            {**valid, "apiKeyEnv": "K" * 81},
            {**valid, "apiKeyEnv": "not-an-env"},
            {**valid, "baseUrl": "https://example.com:bad"},
        )
        for value in invalid_profiles:
            with self.subTest(value=value):
                service.question_phase_provider_profiles = {
                    "generator": value,
                    "verifier": copy.deepcopy(valid),
                }
                with self.assertRaises(ValueError):
                    service._content_profile_payload("generator")

    def test_invalid_profile_is_dependency_before_any_new_catalog_claim(self):
        now = 100_000
        repository = _MemoryContentRepository(now=now)
        prepare_calls = 0
        original_prepare = repository.prepare_content_advance

        def prepare(*args, **kwargs):
            nonlocal prepare_calls
            prepare_calls += 1
            return original_prepare(*args, **kwargs)

        repository.prepare_content_advance = prepare
        staged = _NeverCalledStagedGenerator()
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=_PassingMemoryHost(),
        )
        service.question_phase_provider_profiles["generator"]["apiKey"] = (
            "secret-should-be-rejected"
        )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "dependency_retry")
        self.assertEqual(prepare_calls, 0)
        self.assertEqual(staged.calls, 0)
        self.assertNotIn("secret-should-be-rejected", repr(result))

    def test_invalid_profile_with_persisted_work_is_terminal_without_new_claim(self):
        repository = _InvalidPersistedProfileRepository()
        service = _memory_content_service(
            now=100_000,
            repository=repository,
            staged=_NeverCalledStagedGenerator(),
            host=_PassingMemoryHost(),
        )
        service.question_phase_provider_profiles["verifier"]["model"] = ""

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(repository.prepare_calls, 0)
        self.assertEqual(repository.fence_calls, 1)

    def test_repository_phase_cas_uses_task5_export_without_a_local_map(self):
        now = 100_000
        synthetic = {
            "phase": "synthetic_exported_phase",
            "phaseOrdinal": 15,
            "inputCheckpointKeys": (),
            "acceptedCheckpointKeys": ("phaseStatus",),
            "rejectedCheckpointKeys": None,
        }
        row = {
            "status": "processing",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "active_generation_request_id": "request-1",
            "content_phase": synthetic["phase"],
            "content_lease_token": "lease-1",
            "content_attempt_started_at": now,
            "content_provider_attempt_hard_deadline_at": now + 1_800_000,
            "content_work_unit_deadline_at": now + 120_000,
            "content_lease_expires_at": now + 120_000,
        }

        with patch.object(
            catalog_repository_module,
            "QUESTION_PHASE_IO",
            (*QUESTION_PHASE_IO, synthetic),
        ):
            self.assertTrue(
                LearningCatalogRepository._provider_cas_matches(
                    row,
                    logical_attempt=1,
                    generation_request_id="request-1",
                    phase=synthetic["phase"],
                    phase_ordinal=synthetic["phaseOrdinal"],
                    lease_token="lease-1",
                    attempt_started_at=now,
                    outer_deadline_at=now + 1_800_000,
                    work_deadline_at=now + 120_000,
                    now=now + 1,
                )
            )

    def test_phase_11_and_14_candidate_replay_is_exact_and_collision_safe(self):
        repository = object.__new__(LearningCatalogRepository)
        profile = {
            "name": "kimi",
            "model": "moonshot-v1-8k",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "APP_AI_API_KEY",
            "timeoutMs": 1_000,
            "maxTokens": 2_000,
            "temperature": 0.2,
        }
        curriculum = build_preparation_target("primary_1")[
            "curriculumVersion"
        ]
        for final_phase_ordinal in (11, 14):
            with self.subTest(final_phase_ordinal=final_phase_ordinal):
                course, target, _boundary, _evidence, identity = formal_host_fixture(
                    "pinyin_syllables",
                    final_phase_ordinal=final_phase_ordinal,
                )
                request_id = (
                    identity.generation_request_id
                    + f".phase{final_phase_ordinal}"
                )
                row = {
                    "active_generation_request_id": request_id,
                    "grade_code": target.grade_code,
                    "subject": target.subject,
                    "skill_id": target.skill_id,
                    "curriculum_version": curriculum,
                    "boundary_version": target.boundary_version,
                }
                job_id = "learning_course_job_" + hashlib.sha256(
                    request_id.encode("utf-8")
                ).hexdigest()[:32]
                request_fingerprint = hashlib.sha256(
                    _canonical_json(
                        {
                            "gradeCode": row["grade_code"],
                            "subject": row["subject"],
                            "nodeCode": row["skill_id"],
                            "curriculumVersion": curriculum,
                            "boundaryVersion": row["boundary_version"],
                            "generator": "openmaic_question_phase_v2",
                            "providerProfile": profile,
                            "requestedCandidateCount": 1,
                        }
                    ).encode("utf-8")
                ).hexdigest()
                content_json = _canonical_json(course["content"])
                content_hash = hashlib.sha256(
                    _canonical_json(
                        {
                            "gradeCode": course["gradeCode"],
                            "subject": course["subject"],
                            "nodeCode": course["nodeCode"],
                            "title": course["title"],
                            "objective": course["objective"],
                            "content": course["content"],
                        }
                    ).encode("utf-8")
                ).hexdigest()
                candidate_id = "learning_course_candidate_" + hashlib.sha256(
                    f"{job_id}:1".encode("utf-8")
                ).hexdigest()[:32]
                job = {
                    "id": job_id,
                    "request_fingerprint": request_fingerprint,
                    "grade_code": row["grade_code"],
                    "subject": row["subject"],
                    "node_code": row["skill_id"],
                    "curriculum_version": curriculum,
                    "boundary_version": row["boundary_version"],
                    "generator": "openmaic_question_phase_v2",
                    "provider": profile["name"],
                    "model": profile["model"],
                    "prompt_version": "mira.learning.question-contract.v2",
                    "requested_candidate_count": 1,
                }
                candidate = {
                    "id": candidate_id,
                    "job_id": job_id,
                    "ordinal": 1,
                    "course_id": course["id"],
                    "course_version": course["version"],
                    "grade_code": course["gradeCode"],
                    "subject": course["subject"],
                    "node_code": course["nodeCode"],
                    "curriculum_version": curriculum,
                    "boundary_version": target.boundary_version,
                    "title": course["title"],
                    "objective": course["objective"],
                    "status": "generated",
                    "content_hash": content_hash,
                    "content_json": content_json,
                    "validation_json": None,
                }
                exact = _CandidateReplayConnection(job=job, candidate=candidate)
                replayed_job, replayed_candidate = (
                    repository._create_or_replay_content_candidate(
                        exact,
                        row=row,
                        course=course,
                        generator_profile=profile,
                        now=100_000,
                    )
                )
                self.assertEqual(replayed_job["id"], job_id)
                self.assertEqual(replayed_candidate["id"], candidate_id)

                collision = copy.deepcopy(candidate)
                collision["content_hash"] = "0" * 64
                with self.assertRaises(LearningCatalogBuildConflict):
                    repository._create_or_replay_content_candidate(
                        _CandidateReplayConnection(
                            job=job,
                            candidate=collision,
                        ),
                        row=row,
                        course=course,
                        generator_profile=profile,
                        now=100_000,
                    )

    def test_only_locked_service_audit_authorizes_passed_and_attempt_two(self):
        repository_source = inspect.getsource(LearningCatalogRepository)
        service_source = inspect.getsource(LearningCatalogReleaseService)

        self.assertNotIn(
            "_content_passed_evidence_is_canonical", repository_source
        )
        self.assertNotIn("_content_row_has_passed_shape", repository_source)
        self.assertNotIn(
            "_attempt_one_rejection_is_replayable", repository_source
        )
        self.assertNotIn("_retired_partial_", repository_source)
        self.assertNotIn(
            "_content_passed_evidence_is_canonical", service_source
        )
        self.assertIn("passed_item_ids", repository_source)
        self.assertIn("repairable_item_ids", repository_source)

    def test_locked_passed_item_ids_come_from_locked_rows_not_receipt_objects(self):
        source = inspect.getsource(
            LearningCatalogReleaseService._audit_locked_content_inventory
        )

        self.assertNotIn("proof.catalog_item_id", source)
        self.assertIn('passed_ids.add(str(item["id"]))', source)

    def test_provider_completion_cas_rejects_every_changed_deadline_identity(self):
        now = 100_000
        row = {
            "status": "processing",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "outline",
            "content_lease_token": "lease-1",
            "content_attempt_started_at": now,
            "content_provider_attempt_hard_deadline_at": now + 1_800_000,
            "content_work_unit_deadline_at": now + 120_000,
            "content_lease_expires_at": now + 120_000,
        }
        base = {
            "logical_attempt": 1,
            "generation_request_id": "request-1",
            "phase": "outline",
            "phase_ordinal": 1,
            "lease_token": "lease-1",
            "attempt_started_at": now,
            "outer_deadline_at": now + 1_800_000,
            "work_deadline_at": now + 120_000,
            "now": now + 1,
        }
        mutations = (
            {"logical_attempt": 2},
            {"generation_request_id": "wrong-request"},
            {"phase": "raw_candidate", "phase_ordinal": 2},
            {"lease_token": "late-lease"},
            {"attempt_started_at": now + 1},
            {"outer_deadline_at": now + 1_800_001},
            {"work_deadline_at": now + 120_001},
            {"now": now + 120_001},
        )
        self.assertTrue(
            LearningCatalogRepository._provider_cas_matches(row, **base)
        )
        heartbeat_extended = {
            **row,
            "content_lease_expires_at": now + 120_001,
        }
        self.assertFalse(
            LearningCatalogRepository._provider_cas_matches(
                heartbeat_extended, **base
            )
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.assertFalse(
                    LearningCatalogRepository._provider_cas_matches(
                        row, **{**base, **mutation}
                    )
                )

    def test_next_phase_command_reauthenticates_predecessor_input_hash(self):
        now = 100_000
        repository = _MemoryContentRepository(now=now)
        staged = _MemoryStagedGenerator(repository)
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=_PassingMemoryHost(),
        )
        first = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )
        self.assertEqual(first.kind, "progressed")
        item = copy.deepcopy(repository.item)
        dispatches = copy.deepcopy(repository.dispatches)
        plan = {
            "priorEvidence": [],
            "attemptOneEvidence": None,
            "historicalQuestionFingerprints": [],
        }
        command, _ = service._content_phase_command(
            item=item,
            dispatches=dispatches,
            plan=plan,
        )
        self.assertEqual(command.phase, "raw_candidate")

        dispatches[0]["input_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            service._content_phase_command(
                item=item,
                dispatches=dispatches,
                plan=plan,
            )

    def test_locked_proof_inventory_uses_the_formal_global_lock_order(self):
        repository = object.__new__(LearningCatalogRepository)
        rows = [
            {
                "id": f"item-{index}",
                "status": "course_ready",
                "attempt_count": 1,
                "active_generation_request_id": f"request-{index}",
                "subject_ordinal": 1,
                "boundary_ordinal": index,
                "variant_ordinal": 1,
            }
            for index in (1, 2)
        ]
        order: list[str] = []
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1"},
            {"id": build_id},
        )
        repository.list_build_items = (
            lambda conn, *, build_id, for_update: copy.deepcopy(rows)
        )

        def dispatches(conn, *, item_id, logical_attempt):
            order.append(f"dispatch:{item_id}")
            return []

        repository.list_content_dispatches = dispatches
        connection = _ProofOrderConnection(order)

        repository.load_content_proof_inventory(
            connection,
            build_id="build-1",
        )

        stages = [value.split(":", 1)[0] for value in order]
        self.assertEqual(
            stages,
            [
                "dispatch",
                "job",
                "candidate",
                "course",
            ],
        )

    def test_service_has_no_second_hard_coded_phase_transition_graph(self):
        source = inspect.getsource(
            LearningCatalogReleaseService._next_content_phase
        )

        self.assertNotIn("if ordinal ==", source)
        self.assertIn("QUESTION_PHASE_TRANSITIONS", source)

        release_source = inspect.getsource(
            LearningCatalogRepository.release_content_provider_dependency
        )
        self.assertNotIn("'outline','raw_candidate'", release_source)
        self.assertIn("QUESTION_PHASE_IO", release_source)

    def test_build_authority_rejects_counter_curriculum_and_request_drift(self):
        repository = LearningCatalogRepository(
            Database("mysql+pymysql://unused:unused@127.0.0.1:3306/unused")
        )
        target = build_preparation_target("primary_1")
        request_id = "formal-build-request"
        digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:24]
        build = {
            "id": f"catalog_build_{digest}",
            "request_id": request_id,
            "release_id": f"catalog_release_{digest}",
            "curriculum_version": target["curriculumVersion"],
            "status": "queued",
            "execution_mode": "content_only",
            "stage_ceiling": "content_ready",
            "target_spec_json": repository.encode_json(target),
            "content_manifest_version": target["schemaVersion"],
            "canary_manifest_json": repository.encode_json(target["canaryManifest"]),
            "total_item_count": 30,
            "ready_item_count": 0,
            "failed_item_count": 0,
            "error_code": None,
            "error_message_safe": None,
            "completed_at": None,
        }
        release = {
            "id": build["release_id"],
            "status": "draft",
            "quality_status": "building",
            "curriculum_version": target["curriculumVersion"],
            "required_boundary_count": 10,
            "ready_item_count": 0,
            "activated_at": None,
            "retired_at": None,
        }
        rows = [
            {
                "package_attempt_count": 0,
                "active_package_request_id": None,
                "package_id": None,
                "package_version": None,
            }
            for _ in range(30)
        ]
        repository._release_has_catalog_items = lambda conn, *, release_id: False
        repository._expected_content_item_immutables = (
            lambda **kwargs: [{} for _ in range(30)]
        )
        repository._content_item_immutables_match = lambda row, expected: True
        self.assertTrue(
            repository._content_authority_is_exact(
                object(), release=release, build=build, rows=rows
            )
        )

        mutations = (
            ("build", "curriculum_version", "stale-curriculum"),
            ("build", "ready_item_count", 1),
            ("build", "failed_item_count", 1),
            ("build", "request_id", "other-request"),
            ("build", "id", "other-build"),
            ("release", "quality_status", "ready"),
            ("release", "ready_item_count", 1),
            ("release", "required_boundary_count", 9),
        )
        for owner, key, value in mutations:
            with self.subTest(owner=owner, key=key):
                changed_build = copy.deepcopy(build)
                changed_release = copy.deepcopy(release)
                (changed_build if owner == "build" else changed_release)[key] = value
                self.assertFalse(
                    repository._content_authority_is_exact(
                        object(),
                        release=changed_release,
                        build=changed_build,
                        rows=rows,
                    )
                )

    def test_attempt_two_feedback_comes_only_from_rejected_receipt_issue(self):
        service = object.__new__(LearningCatalogReleaseService)
        checkpoint = {
            "phaseStatus": "accepted",
            "questionFingerprints": [
                {"fingerprint": hashlib.sha256(f"q-{index}".encode()).hexdigest()}
                for index in range(5)
            ],
        }
        checkpoint_json = _canonical_json(checkpoint)
        receipt = {
            "outcome": "rejected",
            "issues": [
                {
                    "code": "host_exact_issue",
                    "message": "exact safe Host feedback",
                }
            ],
        }
        envelope = {
            "schemaVersion": "mira.learning.primary-1-host-gate-evidence.v1",
            "contentFingerprint": "",
            "hostGateReceipt": receipt,
            "hostGateReceiptHash": hashlib.sha256(
                _canonical_json(receipt).encode("utf-8")
            ).hexdigest(),
        }
        attempt_one = {
            "candidate": {
                "validation_json": _canonical_json(envelope),
                "error_code": "catalog-column-is-not-authority",
                "error_message_safe": "wrong catalog feedback",
            },
            "dispatches": [
                {
                    "phase": "independent_verification",
                    "phase_ordinal": 11,
                    "status": "succeeded",
                    "checkpoint_json": checkpoint_json,
                    "output_sha256": hashlib.sha256(
                        checkpoint_json.encode("utf-8")
                    ).hexdigest(),
                }
            ],
        }

        initial = service._attempt_initial_checkpoint(
            item={"variant_ordinal": 1, "attempt_count": 2},
            dispatches=[],
            plan={
                "priorEvidence": [],
                "attemptOneEvidence": attempt_one,
                "historicalQuestionFingerprints": [],
            },
        )

        self.assertEqual(
            initial["generationFeedback"],
            {"code": "host_exact_issue", "message": "exact safe Host feedback"},
        )

    def test_repairable_rejection_needs_exact_proof_to_stay_out_of_failed_count(self):
        service = object.__new__(LearningCatalogReleaseService)
        target = build_preparation_target("primary_1")
        rows = [
            {
                "id": f"summary-{index}",
                "subject": item["subject"],
                "skill_id": item["skillId"],
                "variant_ordinal": item["variantOrdinal"],
                "status": "pending",
                "attempt_count": 0,
                "content_gate_status": "not_started",
                "content_receipt_hash": None,
            }
            for index, item in enumerate(target["courseTargets"])
        ]
        rows[0].update(
            status="failed",
            attempt_count=1,
            content_gate_status="failed_deterministic",
            _content_repair_verified=False,
        )

        summary = service._content_summary(rows)

        self.assertEqual(summary["contentFailedItemCount"], 1)

    def test_locked_audit_summary_is_exact_at_all_review_boundaries(self):
        service = object.__new__(LearningCatalogReleaseService)
        manifest = build_preparation_target("primary_1")["courseTargets"]
        items = [
            {
                "id": f"item-{index}",
                "subject": target["subject"],
                "skill_id": target["skillId"],
                "variant_ordinal": target["variantOrdinal"],
                "status": "pending",
            }
            for index, target in enumerate(manifest)
        ]
        canary_keys = {
            ("chinese", "pinyin_syllables", 1),
            ("math", "number_sense_20", 1),
            ("english", "letters_sounds", 1),
        }
        canaries = [
            index
            for index, item in enumerate(items)
            if (
                item["subject"],
                item["skill_id"],
                item["variant_ordinal"],
            )
            in canary_keys
        ]
        self.assertEqual(len(canaries), 3)

        def proof(index):
            item = items[index]
            return SimpleNamespace(
                target=SimpleNamespace(
                    subject=item["subject"],
                    skill_id=item["skill_id"],
                    variant_ordinal=item["variant_ordinal"],
                )
            )

        selections = {
            0: [],
            1: canaries[:1],
            2: canaries[:2],
            3: canaries,
            29: list(range(29)),
            30: list(range(30)),
        }
        for expected_count, indexes in selections.items():
            with self.subTest(expected_count=expected_count):
                summary = service._content_summary_from_locked_audit(
                    items=items,
                    proofs=[proof(index) for index in indexes],
                    repairable_item_ids=set(),
                )
                self.assertEqual(
                    set(summary),
                    {
                        "contentCandidateItemCount",
                        "contentFailedItemCount",
                        "subjectContentProgress",
                        "canary",
                        "canActivate",
                    },
                )
                self.assertEqual(
                    summary["contentCandidateItemCount"], expected_count
                )
                self.assertIsInstance(
                    summary["contentCandidateItemCount"], int
                )
                self.assertIs(summary["canActivate"], False)
                self.assertEqual(
                    summary["canary"]["passed"],
                    all(index in indexes for index in canaries),
                )

    def test_handoff_requires_three_variant_set_for_each_of_ten_boundaries(self):
        service = object.__new__(LearningCatalogReleaseService)
        recorder = _RecordingVariantSetValidator()
        service.catalog_validator = recorder
        service.primary_one_host_validator = _AcceptingReceiptValidator()
        manifest = build_preparation_target("primary_1")
        proofs = tuple(
            AcceptedPrimaryOneHostReceipt(
                target=PrimaryOneCourseTarget(
                    grade_code="primary_1",
                    subject=str(item["subject"]),
                    subject_ordinal=int(item["subjectOrdinal"]),
                    skill_id=str(item["skillId"]),
                    boundary_ordinal=int(item["boundaryOrdinal"]),
                    boundary_version=str(item["boundaryVersion"]),
                    variant_ordinal=int(item["variantOrdinal"]),
                    instruction_language_code="zh-CN",
                    target_language_code=(
                        "en-US" if item["subject"] == "english" else "zh-CN"
                    ),
                ),
                immutable_course={
                    "id": f"course-{index}",
                    "version": "1.0.0",
                },
                receipt={"outcome": "passed"},
                receipt_hash=f"{index:064x}",
            )
            for index, item in enumerate(manifest["courseTargets"], start=1)
        )

        service._validate_content_handoff_proofs(proofs)
        self.assertEqual(len(recorder.calls), 10)
        self.assertTrue(
            all(
                sorted(variant.target.variant_ordinal for variant in group)
                == [1, 2, 3]
                for group in recorder.calls
            )
        )

        boundary_keys = sorted(
            {
                (
                    proof.target.subject,
                    proof.target.skill_id,
                    proof.target.boundary_version,
                )
                for proof in proofs
            }
        )
        self.assertEqual(len(boundary_keys), 10)
        for boundary_key in boundary_keys:
            with self.subTest(boundary_key=boundary_key):
                missing = tuple(
                    proof
                    for proof in proofs
                    if not (
                        (
                            proof.target.subject,
                            proof.target.skill_id,
                            proof.target.boundary_version,
                        )
                        == boundary_key
                        and proof.target.variant_ordinal == 2
                    )
                )
                with self.assertRaises(ValueError):
                    service._validate_content_handoff_proofs(missing)

    def test_expired_third_host_dependency_fences_without_a_fourth_claim(self):
        repository = object.__new__(LearningCatalogRepository)
        now = 300_001
        row = {
            "id": "item-1",
            "build_job_id": "build-1",
            "status": "processing",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "content_phase": "host_gate_running",
            "content_gate_status": "pending",
            "content_gate_attempt_count": 3,
            "content_lease_token": "host-lease-3",
            "content_lease_expires_at": 300_000,
            "content_work_unit_deadline_at": 300_000,
        }
        repository.lock_build_authority = lambda conn, *, build_id: (
            {"id": "release-1", "status": "draft"},
            {"id": build_id, "status": "running"},
        )
        repository.list_build_items = lambda conn, *, build_id, for_update: [
            row
        ]
        repository._content_authority_is_exact = lambda *args, **kwargs: True
        fenced: list[str] = []
        repository._fence_content_build_locked = (
            lambda conn, *, error_code, **kwargs: fenced.append(error_code)
        )

        outcome = repository.release_content_host_dependency(
            _RecordingConnection(),
            build_id="build-1",
            item_id="item-1",
            logical_attempt=1,
            generation_request_id="request-1",
            gate_ordinal=3,
            lease_token="host-lease-3",
            work_deadline_at=300_000,
            now=now,
        )

        self.assertEqual(outcome, "failed")
        self.assertEqual(
            fenced,
            ["preparation_content_gate_attempts_exhausted"],
        )

    def test_expired_host_ordinals_advance_only_one_then_two_to_three(self):
        for prior_ordinal, expected in ((1, 2), (2, 3)):
            with self.subTest(prior_ordinal=prior_ordinal):
                repository = object.__new__(LearningCatalogRepository)
                now = 300_001
                expired = {
                    "id": "item-1",
                    "attempt_count": 1,
                    "content_phase": "host_gate_running",
                    "content_gate_status": "pending",
                    "content_gate_attempt_count": prior_ordinal,
                    "content_work_unit_deadline_at": 300_000,
                    "content_lease_token": "expired-lease",
                    "content_lease_expires_at": 300_000,
                }
                pending = {
                    **expired,
                    "content_phase": "host_gate_pending",
                    "content_gate_status": "retry_wait",
                    "content_work_unit_deadline_at": None,
                    "content_lease_token": None,
                }
                claimed = {
                    **pending,
                    "content_phase": "host_gate_running",
                    "content_gate_attempt_count": expected,
                    "content_lease_token": "fresh-lease",
                    "content_lease_expires_at": now + 120_000,
                    "content_work_unit_deadline_at": now + 120_000,
                }
                get_calls = 0

                def get_item(conn, *, item_id):
                    nonlocal get_calls
                    get_calls += 1
                    return copy.deepcopy(
                        pending if get_calls == 1 else claimed
                    )

                connection = _RecordingConnection()
                repository.get_item = get_item
                repository.list_content_dispatches = lambda *args, **kwargs: []
                repository._lock_content_candidate_for_item = (
                    lambda conn, *, row: (
                        {"id": "job-1"},
                        {"id": "candidate-1"},
                    )
                )
                repository._load_content_attempt_histories_locked = (
                    lambda conn, *, rows: {
                        str(value["id"]): {
                            1: {
                                "dispatches": [],
                                "jobs": [{"id": "job-1"}],
                                "candidates": [{"id": "candidate-1"}],
                                "courses": [{"id": "course-1"}],
                            },
                            2: {
                                "dispatches": [],
                                "jobs": [],
                                "candidates": [],
                                "courses": [],
                            },
                        }
                        for value in rows
                    }
                )

                plan = repository._prepare_host_action(
                    connection,
                    build={"id": "build-1"},
                    row=expired,
                    rows=[expired],
                    now=now,
                    passed_item_ids=frozenset(),
                    locked_attempt_histories_by_item={
                        "item-1": {
                            1: {
                                "dispatches": [],
                                "jobs": [{"id": "job-1"}],
                                "candidates": [{"id": "candidate-1"}],
                                "courses": [{"id": "course-1"}],
                            },
                            2: {
                                "dispatches": [],
                                "jobs": [],
                                "candidates": [],
                                "courses": [],
                            },
                        }
                    },
                )

                self.assertEqual(plan["action"], "host")
                claim_params = connection.executions[1][1]
                self.assertEqual(claim_params[0], expected)
                self.assertEqual(
                    claim_params[2],
                    now + LearningCatalogRepository.FORMAL_CONTENT_WORK_UNIT_MS,
                )


class _Cursor:
    def __init__(self, *, one=None, all_rows=None, rowcount=0):
        self._one = one
        self._all = [] if all_rows is None else all_rows
        self.rowcount = rowcount

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _NeverCalledStagedGenerator:
    def __init__(self):
        self.calls = 0

    def advance(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("invalid profile must stop before Task 5")


class _RecordingVariantSetValidator:
    def __init__(self):
        self.calls = []

    def validate_primary_one_variant_set(self, variants):
        self.calls.append(tuple(variants))


class _AcceptingReceiptValidator:
    def validate_primary_one_accepted_receipt(self, proof):
        return None


class _DeterministicPassedHost:
    def validate_primary_one_host_gate(self, *args, **kwargs):
        return SimpleNamespace(
            outcome="passed",
            course={"id": "course-1"},
            receipt={"outcome": "passed"},
            receipt_hash="a" * 64,
        )


class _DeterministicRejectedHost:
    def __init__(self, *, receipt, receipt_hash):
        self.receipt = receipt
        self.receipt_hash = receipt_hash

    def validate_primary_one_host_gate(self, *args, **kwargs):
        return SimpleNamespace(
            outcome="rejected",
            course=None,
            receipt=copy.deepcopy(self.receipt),
            receipt_hash=self.receipt_hash,
        )


class _LockedAttemptTwoRepository:
    def __init__(self):
        self.claim_calls = 0
        self.transaction_calls = 0

    @contextmanager
    def transaction(self):
        self.transaction_calls += 1
        raise AssertionError("locked attempt-2 must not open a nested transaction")
        yield object()

    def _claim_content_attempt_two_locked(self, conn, **kwargs):
        self.claim_calls += 1
        return {"id": kwargs["item_id"], "attempt_count": 2}


class _MutatingHostFinalizeRepository:
    def __init__(self):
        self.complete_calls = 0
        self.fence_calls = 0

    @contextmanager
    def transaction(self):
        yield object()

    def load_content_host_finalize_authority(self, conn, **kwargs):
        return {"mutated": True, "item": {"id": kwargs["item_id"]}}

    def complete_content_host_gate(self, conn, **kwargs):
        self.complete_calls += 1
        return {"id": kwargs["item_id"]}

    def fence_content_failure(self, conn, **kwargs):
        self.fence_calls += 1

    def load_content_summary_items(self, conn, *, build_id):
        return []

    def load_content_proof_inventory(self, conn, *, build_id):
        return {
            "build": {"id": build_id, "status": "failed"},
            "items": [],
        }


class _InvalidPersistedProfileRepository:
    def __init__(self):
        self.prepare_calls = 0
        self.fence_calls = 0

    @contextmanager
    def transaction(self):
        yield object()

    def inspect_content_profile_preflight(self, conn, *, build_id):
        return "persisted"

    def prepare_content_advance(self, conn, *, build_id, now):
        self.prepare_calls += 1
        raise AssertionError("invalid persisted profile cannot claim work")

    def fence_content_failure(self, conn, **kwargs):
        self.fence_calls += 1

    def load_content_summary_items(self, conn, *, build_id):
        return []


class _MutatingLockedAuditRepository:
    def __init__(self, *, action: str):
        self.action = action
        self.fence_calls = 0
        self.claim_attempt_two_calls = 0

    @contextmanager
    def transaction(self):
        yield object()

    def prepare_content_advance(self, conn, *, build_id, now):
        item = {"id": "item-1"}
        return {"action": self.action, "item": item, "items": [item]}

    def load_content_proof_inventory(self, conn, *, build_id):
        return {"items": [{"id": "mutated-item"}]}

    def claim_content_attempt_two(self, *args, **kwargs):
        self.claim_attempt_two_calls += 1
        return None

    def fence_content_failure(self, conn, **kwargs):
        self.fence_calls += 1


class _EvidenceConnection:
    def __init__(self, *, job=None, candidate=None, course=None, dispatches=None):
        self.job = job
        self.candidate = candidate
        self.course = course
        self.dispatches = [] if dispatches is None else dispatches
        self.updates: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql, params=()):
        if "FROM learning_course_generation_jobs" in sql:
            return _Cursor(one=self.job)
        if "FROM learning_course_generation_candidates" in sql:
            return _Cursor(one=self.candidate)
        if "FROM learning_courses" in sql:
            return _Cursor(one=self.course)
        if "FROM learning_course_provider_dispatches" in sql:
            return _Cursor(
                one=self.dispatches[0] if self.dispatches else None,
                all_rows=copy.deepcopy(self.dispatches),
            )
        self.updates.append((sql, params))
        return _Cursor(rowcount=1)


class _CandidateReplayConnection:
    def __init__(self, *, job, candidate):
        self.job = copy.deepcopy(job)
        self.candidate = copy.deepcopy(candidate)

    def execute(self, sql, params=()):
        if "FROM learning_course_generation_jobs" in sql:
            return _Cursor(one=copy.deepcopy(self.job))
        if "FROM learning_course_generation_candidates" in sql:
            return _Cursor(one=copy.deepcopy(self.candidate))
        if sql.lstrip().startswith("INSERT INTO"):
            return _Cursor(rowcount=0)
        raise AssertionError(f"unexpected candidate replay SQL: {sql}")


class _ProofOrderConnection:
    def __init__(self, order):
        self.order = order

    def execute(self, sql, params=()):
        if "FROM learning_course_provider_dispatches" in sql:
            self.order.append("dispatch:all")
            return _Cursor(all_rows=[])
        if "FROM learning_course_generation_jobs" in sql:
            self.order.append("job:all")
            return _Cursor(
                all_rows=[
                    {"id": f"job-{value}", "request_id": value}
                    for value in params
                ]
            )
        if "FROM learning_course_generation_candidates" in sql:
            self.order.append("candidate:all")
            return _Cursor(
                all_rows=[
                    {
                        "id": f"candidate-{value}",
                        "job_id": value,
                        "ordinal": 1,
                        "course_id": f"course-{value}",
                        "course_version": "v1",
                    }
                    for value in params
                ]
            )
        if "FROM learning_courses" in sql:
            self.order.append("course:all")
            return _Cursor(all_rows=[])
        raise AssertionError(f"unexpected SQL: {sql}")


class _RecordingConnection:
    def __init__(self):
        self.executions: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql, params=()):
        self.executions.append((sql, params))
        return _Cursor(rowcount=1)


class _StaleLedgerRepository(_MemoryContentRepository):
    @contextmanager
    def transaction(self):
        yield object()

    def reconcile_content_provider_stale(self, conn, **kwargs):
        dispatch = self.dispatches[-1] if self.dispatches else None
        if dispatch is not None and dispatch["status"] == "ambiguous":
            self.fence_content_failure(
                conn,
                build_id=kwargs["build_id"],
                item_id=kwargs["item_id"],
                error_code="preparation_provider_dispatch_outcome_unknown",
                now=kwargs["now"],
            )
            return "failed"
        return "stale"


class _StaleAfterAmbiguousGenerator:
    def __init__(self, repository):
        self.repository = repository
        self.calls = 0

    def advance(self, work, *, heartbeat):
        self.calls += 1
        self.repository.dispatches.append(
            {
                "id": "dispatch-outline",
                "build_item_id": work.command.build_item_id,
                "logical_attempt": work.command.logical_attempt,
                "phase": work.command.phase,
                "phase_ordinal": work.command.phase_ordinal,
                "generation_request_id": work.command.generation_request_id,
                "item_lease_token": work.item_lease_token,
                "attempt_started_at": work.attempt_started_at,
                "attempt_hard_deadline_at": work.attempt_hard_deadline_at,
                "status": "ambiguous",
            }
        )
        return ContentPhaseAdvance(
            kind="stale",
            result=None,
            replayed=False,
            process_started=False,
        )


if __name__ == "__main__":
    unittest.main()
