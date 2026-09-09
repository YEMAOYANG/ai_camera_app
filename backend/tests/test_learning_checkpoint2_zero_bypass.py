from __future__ import annotations

import copy
from contextlib import contextmanager
import hashlib
import json
import os
import unittest
from unittest.mock import patch

from content.primary_skill_boundaries import PRIMARY_SKILL_BOUNDARIES
from integrations.openmaic_question_adapter import (
    OpenMaicQuestionPhaseAdapter,
    QuestionPhaseResult,
)
from services.dynamic_learning_course_generation_service import ContentPhaseAdvance
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
    PrimaryOneHostGateResult,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from tests.test_openmaic_question_phase_adapter import (
    _candidate_course,
    _compiled_candidate,
    _independent_solution,
    _lesson_text,
    _outline_checkpoint,
    _question_fingerprints,
    _reconciliation,
    _validation,
)
from tests.test_learning_generated_course_validator import formal_host_fixture


class LearningCheckpoint2ZeroBypassTest(unittest.TestCase):
    def test_release_service_exposes_only_the_restricted_content_advance_entrypoint(self):
        self.assertTrue(hasattr(LearningCatalogReleaseService, "advance_content"))

    def test_missing_restricted_dependencies_is_zero_dispatch_dependency_retry(self):
        class ForbiddenLegacyGeneration:
            def __getattr__(self, name):
                raise AssertionError(f"legacy generation was accessed: {name}")

        service = LearningCatalogReleaseService(
            "mysql://unused:unused@127.0.0.1:3306/unused",
            dynamic_generation_service=ForbiddenLegacyGeneration(),
            lesson_package_service=ForbiddenLegacyGeneration(),
        )

        result = service.advance_content(
            "catalog_build_1",
            heartbeat=lambda: True,
        )

        self.assertEqual(result.kind, "dependency_retry")
        self.assertEqual(result.build_id, "catalog_build_1")
        self.assertIsNone(result.item_id)
        self.assertEqual(result.content_summary["contentCandidateItemCount"], 0)
        self.assertEqual(result.content_summary["contentFailedItemCount"], 0)
        self.assertFalse(result.content_summary["canActivate"])

    def test_one_canary_crosses_provider_graph_then_host_with_zero_legacy_calls(self):
        now = 100_000
        legacy_generation = _ExplodingLegacyDependency()
        lesson_package = _ExplodingLegacyDependency()
        repository = _MemoryContentRepository(now=now)
        staged = _MemoryStagedGenerator(repository)
        host = _CountingRealHost()
        profiles = {
            role: {
                "name": "kimi",
                "model": "moonshot-v1-8k",
                "baseUrl": "https://api.moonshot.cn/v1",
                "apiKeyEnv": "KIMI_API_KEY",
                "timeoutMs": 60_000,
                "maxTokens": 8_000,
                "temperature": 0.2,
            }
            for role in ("generator", "verifier")
        }
        service = LearningCatalogReleaseService(
            "mysql+pymysql://unused:unused@127.0.0.1:3306/unused",
            dynamic_generation_service=legacy_generation,
            lesson_package_service=lesson_package,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=host,
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        service.repository = repository
        service._audit_locked_content_inventory = lambda **kwargs: {
            "summary": service._content_summary(kwargs["inventory"]["items"]),
            "passedItemIds": frozenset(
                str(row["id"])
                for row in kwargs["inventory"]["items"]
                if str(row.get("status") or "") == "course_ready"
            ),
            "repairableItemIds": frozenset(),
        }

        results = [
            service.advance_content("catalog-build-canary", heartbeat=lambda: True)
            for _ in range(7)
        ]

        self.assertEqual([result.kind for result in results], ["progressed"] * 7)
        self.assertEqual(
            staged.phases,
            [
                "outline",
                "raw_candidate",
                "candidate_repair",
                "lesson_text",
                "reconciliation",
                "independent_verification",
            ],
        )
        self.assertEqual(host.calls, 1)
        self.assertEqual(repository.item["status"], "course_ready")
        self.assertEqual(repository.item["content_gate_status"], "passed")
        self.assertEqual(results[-1].content_summary["contentCandidateItemCount"], 1)
        self.assertEqual(
            results[-1].content_summary["subjectContentProgress"]["math"][
                "candidateCount"
            ],
            1,
        )
        self.assertEqual(legacy_generation.calls, 0)
        self.assertEqual(lesson_package.calls, 0)

    def test_attempt_two_missing_predecessor_fences_before_claim_or_provider(self):
        now = 100_000
        repository = _IncompleteAttemptTwoRepository(now=now)
        staged = _ExplodingStagedGenerator()
        profiles = {
            role: {
                "name": "kimi",
                "model": "moonshot-v1-8k",
                "baseUrl": "https://api.moonshot.cn/v1",
                "apiKeyEnv": "APP_AI_API_KEY",
                "timeoutMs": 1_000,
                "maxTokens": 2_000,
                "temperature": 0.2,
            }
            for role in ("generator", "verifier")
        }
        service = LearningCatalogReleaseService(
            "mysql+pymysql://unused:unused@127.0.0.1:3306/unused",
            dynamic_generation_service=_ExplodingLegacyDependency(),
            lesson_package_service=_ExplodingLegacyDependency(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=_PassingMemoryHost(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        service.repository = repository

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(repository.claim_attempt_two_calls, 0)
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(staged.calls, 0)

    def test_dependency_after_dispatch_race_fences_instead_of_returning_stale(self):
        now = 100_000
        repository = _MemoryContentRepository(now=now)
        staged = _DependencyStagedGenerator()
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=_PassingMemoryHost(),
        )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(staged.calls, 1)
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(
            repository.last_error_code,
            "preparation_content_contract_drift",
        )

    def test_unexpected_provider_exception_is_terminal_and_never_escapes(self):
        now = 100_000
        repository = _MemoryContentRepository(now=now)
        staged = _RaisingStagedGenerator()
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=_PassingMemoryHost(),
        )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(staged.calls, 1)
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(
            repository.last_error_code,
            "preparation_content_provider_unavailable",
        )

    def test_terminal_question_schema_rejection_is_content_validation_not_provider_unavailable(self):
        now = 100_000
        repository = _MemoryContentRepository(now=now)
        staged = _FailedSafeQuestionOutputGenerator()
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=_PassingMemoryHost(),
        )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(staged.calls, 1)
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(
            repository.last_error_code,
            "preparation_content_validation_failed",
        )

    def test_unexpected_host_exception_is_terminal_and_never_escapes(self):
        now = 100_000
        repository = _MemoryContentRepository(now=now)
        staged = _MemoryStagedGenerator(repository)
        host = _RaisingHost()
        service = _memory_content_service(
            now=now,
            repository=repository,
            staged=staged,
            host=host,
        )
        for _ in range(6):
            self.assertEqual(
                service.advance_content(
                    "catalog-build-canary", heartbeat=lambda: True
                ).kind,
                "progressed",
            )

        result = service.advance_content(
            "catalog-build-canary", heartbeat=lambda: True
        )

        self.assertEqual(result.kind, "failed")
        self.assertEqual(host.calls, 1)
        self.assertEqual(repository.fence_calls, 1)
        self.assertEqual(
            repository.last_error_code,
            "preparation_content_contract_drift",
        )


class _ExplodingLegacyDependency:
    def __init__(self):
        self.calls = 0

    def __getattr__(self, name):
        self.calls += 1
        raise AssertionError(f"legacy dependency was accessed: {name}")


class _ExplodingStagedGenerator:
    def __init__(self):
        self.calls = 0

    def advance(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("Provider must not run for incomplete attempt-one proof")


class _DependencyStagedGenerator:
    def __init__(self):
        self.calls = 0

    def advance(self, *args, **kwargs):
        self.calls += 1
        return ContentPhaseAdvance(
            kind="dependency_retry",
            result=None,
            replayed=False,
            process_started=False,
        )


class _RaisingStagedGenerator:
    def __init__(self):
        self.calls = 0

    def advance(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("raw Provider secret")


class _FailedSafeQuestionOutputGenerator:
    def __init__(self):
        self.calls = 0

    def advance(self, work, *, heartbeat):
        self.calls += 1
        return ContentPhaseAdvance(
            kind="failed_safe",
            result=QuestionPhaseResult(
                request_id=work.command.generation_request_id,
                phase=work.command.phase,
                phase_ordinal=work.command.phase_ordinal,
                outcome="failed_safe",
                checkpoint=None,
                provider_request_id_hash="a" * 64,
                input_tokens=1,
                output_tokens=1,
                billing_evidence="reported",
                safe_error_code="question_phase_output_rejected",
                elapsed_ms=1.0,
            ),
            replayed=False,
            process_started=True,
        )


class _MemoryContentRepository:
    def __init__(self, *, now: int):
        boundary_ordinal, boundary = next(
            (index, value)
            for index, value in enumerate(
                (
                    value
                    for value in PRIMARY_SKILL_BOUNDARIES
                    if value.grade_code == "primary_1"
                    and value.subject == "math"
                ),
                start=1,
            )
            if value.skill_id == "addition_subtraction_20"
        )
        self.now = now
        self.dispatches: list[dict[str, object]] = []
        self.item: dict[str, object] = {
            "id": "catalog-item-canary",
            "build_job_id": "catalog-build-canary",
            "grade_code": "primary_1",
            "subject": "math",
            "subject_ordinal": 2,
            "skill_id": "addition_subtraction_20",
            "boundary_ordinal": boundary_ordinal,
            "boundary_version": boundary.boundary_version,
            "curriculum_version": boundary.curriculum_version,
            "variant_ordinal": 1,
            "generation_request_id": "formal.addition_subtraction_20.v1",
            "active_generation_request_id": "formal.addition_subtraction_20.v1",
            "status": "processing",
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "content_phase": "outline",
            "content_gate_status": "not_started",
            "content_gate_attempt_count": 0,
            "content_lease_token": "lease-outline",
            "content_lease_expires_at": now + 120_000,
            "content_heartbeat_at": now,
            "content_attempt_started_at": now,
            "content_provider_attempt_hard_deadline_at": now + 1_800_000,
            "content_work_unit_deadline_at": now + 120_000,
            "content_receipt_hash": None,
            "course_id": None,
            "course_version": None,
        }
        self.items = [self.item] + [
            {
                "id": f"pending-{index}",
                "subject": "chinese" if index < 11 else "english",
                "skill_id": f"pending-skill-{index}",
                "variant_ordinal": 1,
                "status": "pending",
                "attempt_count": 0,
                "content_gate_status": "not_started",
                "content_receipt_hash": None,
            }
            for index in range(29)
        ]
        self.candidate: dict[str, object] | None = None
        self.fence_calls = 0
        self.last_error_code: str | None = None

    @contextmanager
    def transaction(self):
        yield object()

    def prepare_content_advance(self, conn, *, build_id, now, **kwargs):
        if self.item["content_phase"] == "host_gate_pending":
            self.item.update(
                content_phase="host_gate_running",
                content_gate_attempt_count=1,
                content_lease_token="host-lease-1",
                content_lease_expires_at=now + 120_000,
                content_work_unit_deadline_at=now + 120_000,
            )
            return {
                "action": "host",
                "item": copy.deepcopy(self.item),
                "items": copy.deepcopy(self.items),
                "candidate": copy.deepcopy(self.candidate),
                "job": {"id": "job-1"},
                "dispatches": copy.deepcopy(self.dispatches),
                "historicalQuestionFingerprints": [],
                "priorEvidence": [],
            }
        if self.item["content_phase"] == "course_ready":
            return {"action": "busy", "items": copy.deepcopy(self.items)}
        if self.item.get("content_lease_token") is None:
            self.item["content_lease_token"] = f"lease-{self.item['content_phase']}"
            self.item["content_lease_expires_at"] = self.item["content_work_unit_deadline_at"]
        return {
            "action": "provider",
            "item": copy.deepcopy(self.item),
            "items": copy.deepcopy(self.items),
            "dispatches": copy.deepcopy(self.dispatches),
            "historicalQuestionFingerprints": [],
            "priorEvidence": [],
            "attemptOneEvidence": None,
        }

    def load_content_provider_finalize_authority(self, conn, **kwargs):
        dispatch = next(
            (
                value
                for value in self.dispatches
                if value["phase"] == kwargs["phase"]
                and value["phase_ordinal"] == kwargs["phase_ordinal"]
            ),
            None,
        )
        return {
            "release": {"id": "release-1"},
            "build": {"id": kwargs["build_id"]},
            "items": copy.deepcopy(self.items),
            "item": copy.deepcopy(self.item),
            "dispatches": copy.deepcopy(self.dispatches),
            "persistedDispatch": copy.deepcopy(dispatch),
            "historicalQuestionFingerprints": [],
            "priorEvidence": [],
            "attemptOneEvidence": getattr(self, "attempt_one", None),
        }

    def _content_authority_is_exact(self, *args, **kwargs):
        return True

    def _provider_cas_matches(self, *args, **kwargs):
        return True

    def _complete_content_provider_phase_locked(self, conn, **kwargs):
        if kwargs["expected_next_phase"] is not None:
            self.item["content_phase"] = kwargs["expected_next_phase"]
            self.item["content_lease_token"] = None
            self.item["content_lease_expires_at"] = None
            self.item["content_work_unit_deadline_at"] = self.now + 120_000
        else:
            course = copy.deepcopy(kwargs["candidate_course"])
            self.item.update(
                content_phase="host_gate_pending",
                content_gate_status="pending",
                content_lease_token=None,
                content_lease_expires_at=None,
                content_provider_attempt_hard_deadline_at=None,
                content_work_unit_deadline_at=None,
                course_id=course["id"],
                course_version=course["version"],
            )
            self.candidate = {
                "id": "candidate-1",
                "course_id": course["id"],
                "course_version": course["version"],
                "content_json": json.dumps(
                    course["content"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        return copy.deepcopy(self.item)

    def complete_content_host_gate(self, conn, **kwargs):
        self.item.update(
            status="course_ready",
            content_phase="course_ready",
            content_gate_status="passed",
            content_receipt_hash=kwargs["receipt_hash"],
            content_lease_token=None,
            content_lease_expires_at=None,
            content_work_unit_deadline_at=None,
        )
        return copy.deepcopy(self.item)

    def load_content_summary_items(self, conn, *, build_id):
        rows = copy.deepcopy(self.items)
        for row in rows:
            row["_content_proof_verified"] = (
                row.get("status") == "course_ready"
                and row.get("content_gate_status") == "passed"
                and isinstance(row.get("content_receipt_hash"), str)
            )
        return rows

    def load_content_proof_inventory(self, conn, *, build_id):
        return {
            "build": {
                "id": build_id,
                "status": (
                    "failed" if self.item.get("status") == "failed" else "running"
                ),
            },
            "items": self.load_content_summary_items(conn, build_id=build_id),
        }

    def release_content_provider_dependency(self, *args, **kwargs):
        return False

    def release_content_host_dependency(self, *args, **kwargs):
        return False

    def fence_content_failure(
        self,
        conn,
        *,
        build_id,
        item_id,
        error_code,
        now,
    ):
        self.fence_calls += 1
        self.last_error_code = error_code
        self.item["status"] = "failed"


class _IncompleteAttemptTwoRepository(_MemoryContentRepository):
    def __init__(self, *, now: int):
        super().__init__(now=now)
        course = _candidate_course()
        self.item.update(
            status="failed",
            content_phase="failed",
            content_gate_status="failed_deterministic",
            course_id=course["id"],
            course_version=course["version"],
            content_lease_token=None,
            content_lease_expires_at=None,
            content_provider_attempt_hard_deadline_at=None,
            content_work_unit_deadline_at=None,
        )
        self.items[0] = self.item
        self.claim_attempt_two_calls = 0
        self.fence_calls = 0
        final_checkpoint = {
            "phaseStatus": "accepted",
            "candidateCourse": course,
            "questionFingerprints": _question_fingerprints(course),
            "validation": _validation(),
            "independentSolution": _independent_solution(course),
        }
        final_json = json.dumps(
            final_checkpoint,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.attempt_one = {
            "candidate": {
                "course_id": course["id"],
                "course_version": course["version"],
                "content_json": json.dumps(
                    course["content"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "validation_json": "{}",
            },
            "dispatches": [
                {
                    "build_item_id": self.item["id"],
                    "logical_attempt": 1,
                    "phase": "independent_verification",
                    "phase_ordinal": 11,
                    "generation_request_id": self.item["active_generation_request_id"],
                    "status": "succeeded",
                    "checkpoint_json": final_json,
                    "output_sha256": hashlib.sha256(final_json.encode()).hexdigest(),
                    "attempt_started_at": now,
                    "attempt_hard_deadline_at": now + 1_800_000,
                    "provider": "kimi",
                    "model": "moonshot-v1-8k",
                    "profile": "0" * 64,
                    "input_sha256": "0" * 64,
                }
            ],
        }

    def prepare_content_advance(self, conn, *, build_id, now):
        return {
            "action": "attempt2",
            "item": copy.deepcopy(self.item),
            "items": copy.deepcopy(self.items),
            "priorEvidence": [],
            "attemptOneEvidence": copy.deepcopy(self.attempt_one),
        }

    def _claim_content_attempt_two_locked(self, *args, **kwargs):
        self.claim_attempt_two_calls += 1
        return None

    def fence_content_failure(self, *args, **kwargs):
        self.fence_calls += 1


class _RaisingHost:
    def __init__(self):
        self.calls = 0

    def validate_primary_one_host_gate(self, *args, **kwargs):
        self.calls += 1
        raise RuntimeError("raw Host secret")

    def validate_primary_one_accepted_receipt(self, *args, **kwargs):
        raise AssertionError("variant-1 Host must not load prior receipts")


def _memory_content_service(*, now, repository, staged, host):
    profiles = {
        role: {
            "name": "kimi",
            "model": "moonshot-v1-8k",
            "baseUrl": "https://api.moonshot.cn/v1",
            "apiKeyEnv": "KIMI_API_KEY",
            "timeoutMs": 60_000,
            "maxTokens": 8_000,
            "temperature": 0.2,
        }
        for role in ("generator", "verifier")
    }
    service = LearningCatalogReleaseService(
        "mysql+pymysql://unused:unused@127.0.0.1:3306/unused",
        dynamic_generation_service=_ExplodingLegacyDependency(),
        lesson_package_service=_ExplodingLegacyDependency(),
        staged_content_candidate_generator=staged,
        primary_one_host_validator=host,
        question_phase_provider_profiles=profiles,
        clock_ms=lambda: now,
    )
    service.repository = repository
    if isinstance(repository, _MemoryContentRepository):
        service._audit_locked_content_inventory = lambda **kwargs: {
            "summary": service._content_summary(kwargs["inventory"]["items"]),
            "passedItemIds": frozenset(
                str(row["id"])
                for row in kwargs["inventory"]["items"]
                if str(row.get("status") or "") == "course_ready"
            ),
            "repairableItemIds": frozenset(),
        }
    return service


class _MemoryStagedGenerator:
    def __init__(self, repository):
        self.repository = repository
        self.phases: list[str] = []
        delegate = OpenMaicQuestionPhaseAdapter(
            provider_name="kimi",
            model_name="moonshot-v1-8k",
            base_url="https://api.moonshot.cn/v1",
            api_key_env="KIMI_API_KEY",
            provider_timeout_ms=60_000,
            max_tokens=8_000,
            temperature=0.2,
            process_timeout_seconds=1.0,
            process_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("memory preflight must not execute a process")
            ),
        )

        self._canonicalize_phase = delegate.canonicalize_phase

    def canonicalize_phase(self, command):
        return self._canonicalize_phase(command)

    def advance(self, work, *, heartbeat):
        self.phases.append(work.command.phase)
        prepared = self.canonicalize_phase(work.command)
        course, _target, _boundary, formal_evidence, _identity = (
            formal_host_fixture("addition_subtraction_20")
        )
        checkpoint_by_phase = {
            "outline": _outline_checkpoint(),
            "raw_candidate": {
                "phaseStatus": "accepted",
                "rawCandidate": _compiled_candidate(),
            },
            "candidate_repair": {
                "phaseStatus": "accepted",
                "candidate": _compiled_candidate(),
                "hostCompilation": {
                    "compiler": "host_compiler",
                    "source": "candidate_repair_output",
                    "version": "v1",
                },
            },
            "lesson_text": {
                "phaseStatus": "accepted",
                "lessonText": _lesson_text(),
            },
            "reconciliation": {
                "phaseStatus": "accepted",
                "reconciliation": _reconciliation(),
                "hostReconciliation": {
                    "reconciler": "host_reconciler",
                    "source": "reconciliation_output",
                    "version": "v1",
                },
            },
            "independent_verification": {
                "phaseStatus": "accepted",
                "candidateCourse": course,
                "questionFingerprints": formal_evidence.question_fingerprints,
                "validation": formal_evidence.validation,
                "independentSolution": formal_evidence.independent_solution,
            },
        }
        checkpoint = checkpoint_by_phase[work.command.phase]
        checkpoint_json = json.dumps(
            checkpoint,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.repository.dispatches.append(
            {
                "id": f"dispatch-{work.command.phase_ordinal}",
                "build_item_id": work.command.build_item_id,
                "logical_attempt": work.command.logical_attempt,
                "phase": work.command.phase,
                "phase_ordinal": work.command.phase_ordinal,
                "generation_request_id": work.command.generation_request_id,
                "item_lease_token": work.item_lease_token,
                "provider": "kimi",
                "model": "moonshot-v1-8k",
                "profile": prepared.profile_sha256,
                "input_sha256": prepared.input_sha256,
                "attempt_started_at": work.attempt_started_at,
                "attempt_hard_deadline_at": work.attempt_hard_deadline_at,
                "status": "succeeded",
                "checkpoint_json": checkpoint_json,
                "output_sha256": hashlib.sha256(checkpoint_json.encode()).hexdigest(),
            }
        )
        return ContentPhaseAdvance(
            kind="succeeded",
            result=QuestionPhaseResult(
                request_id=work.command.generation_request_id,
                phase=work.command.phase,
                phase_ordinal=work.command.phase_ordinal,
                outcome="succeeded",
                checkpoint=checkpoint,
                provider_request_id_hash="a" * 64,
                input_tokens=1,
                output_tokens=1,
                billing_evidence="reported",
                safe_error_code=None,
                elapsed_ms=1.0,
            ),
            replayed=False,
            process_started=True,
        )


class _PassingMemoryHost:
    def __init__(self):
        self.calls = 0

    def validate_primary_one_host_gate(self, evidence, **kwargs):
        self.calls += 1
        receipt = {
            "outcome": "passed",
            "contentValidationContractVersion": "mira.learning.primary-1-content-validation.v1",
            "hostContentFingerprint": "b" * 64,
        }
        canonical = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        course = copy.deepcopy(evidence.candidate_course)
        course["status"] = "published"
        return PrimaryOneHostGateResult(
            outcome="passed",
            course=course,
            receipt=receipt,
            receipt_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        )


class _CountingRealHost:
    def __init__(self):
        self.calls = 0
        self.validator = LearningGeneratedCourseValidator()

    def validate_primary_one_host_gate(self, *args, **kwargs):
        self.calls += 1
        return self.validator.validate_primary_one_host_gate(*args, **kwargs)

    def validate_primary_one_accepted_receipt(self, *args, **kwargs):
        return self.validator.validate_primary_one_accepted_receipt(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
