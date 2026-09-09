from __future__ import annotations

import copy
from contextlib import nullcontext
from dataclasses import fields
import hashlib
import inspect
import json
import os
import threading
import unittest
from unittest.mock import patch

from content.primary_skill_boundaries import (
    CONTENT_VALIDATION_CONTRACT_VERSION,
    PRIMARY_ONE_CONTENT_DATASET_SHA256,
    SUBJECT_LANGUAGE_POLICY_VERSION,
)
from core.database import Database
from integrations.openmaic_question_adapter import (
    OpenMaicQuestionPhaseAdapter,
    QuestionPhaseResult,
    _build_candidate_course,
    _build_question_fingerprints,
    _build_validation,
    _public_questions,
)
from repositories.dynamic_learning_course_repository import DynamicLearningCourseRepository
from repositories.learning_catalog_repository import LearningCatalogRepository
from services.dynamic_learning_course_generation_service import StagedContentCandidateGenerator
from services.learning_catalog_release_service import (
    ContentDispatchGraphAuditSnapshot,
    ContentParentRetryAuditSnapshot,
    ContentProofAuditSnapshot,
    ContentProviderDependencyAuditSnapshot,
    ContentWorkUnitClaim,
    LearningCatalogReleaseService,
)
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
    PrimaryOneHostGateIdentity,
    PrimaryOneHostGateControlError,
    PrimaryOneHostGateDependencyError,
    QuestionPhaseCourseEvidence,
)
from services.learning_curriculum_preparation_contract import (
    build_preparation_target,
    preparation_target_fingerprint,
)
from services.learning_catalog_release_service import ContentAdvanceResult
from tests.support import fresh_test_config, reset_mysql_test_database
from tests.test_learning_generated_course_validator import formal_host_fixture
from tests.test_openmaic_question_phase_adapter import _outline_checkpoint


class LearningCatalogContentOnlyContractTest(unittest.TestCase):
    def test_provider_dependency_projection_is_exact_and_rejects_artifact_residue(self):
        service = object.__new__(LearningCatalogReleaseService)
        item = {
            "id": "item-1",
            "build_job_id": "build-1",
            "release_id": "release-1",
            "status": "processing",
            "attempt_count": 1,
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1",
            "content_phase": "outline",
            "content_attempt_started_at": 1_000,
            "content_provider_attempt_hard_deadline_at": 1_801_000,
        }
        histories = {
            1: {
                "requestId": "request-1",
                "dispatches": [],
                "jobs": [],
                "candidates": [],
                "courses": [],
            },
            2: {
                "requestId": "request-1.attempt2",
                "dispatches": [],
                "jobs": [],
                "candidates": [],
                "courses": [],
            },
        }
        baseline = service.audit_content_provider_dependency_retry(
            evidence={"item": item, "attemptHistories": histories},
            content_phase="outline",
        )
        self.assertIsInstance(baseline, ContentProviderDependencyAuditSnapshot)
        self.assertEqual(baseline.item_id, "item-1")
        self.assertEqual(baseline.predecessor_dispatch_ids, ())

        for artifact in ("jobs", "candidates", "courses"):
            with self.subTest(artifact=artifact):
                drift = copy.deepcopy(histories)
                drift[1][artifact].append({"id": f"residue-{artifact}"})
                with self.assertRaisesRegex(ValueError, "persistence residue"):
                    service.audit_content_provider_dependency_retry(
                        evidence={"item": item, "attemptHistories": drift},
                        content_phase="outline",
                    )

    def test_provider_dependency_attempt_two_requires_structural_rejected_history(self):
        service = object.__new__(LearningCatalogReleaseService)
        service.primary_one_host_validator = LearningGeneratedCourseValidator()
        service.question_phase_provider_profiles = {
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
        math_target = next(
            target
            for target in build_preparation_target("primary_1")["courseTargets"]
            if target["subject"] == "math" and target["variantOrdinal"] == 1
        )
        item = {
            "id": "item-1",
            "build_job_id": "build-1",
            "release_id": "release-1",
            "status": "processing",
            "attempt_count": 2,
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1.attempt2",
            "content_phase": "outline",
            "content_attempt_started_at": 2_000,
            "content_provider_attempt_hard_deadline_at": 1_802_000,
            "curriculum_version": build_preparation_target("primary_1")[
                "curriculumVersion"
            ],
            "subject": math_target["subject"],
            "subject_ordinal": math_target["subjectOrdinal"],
            "skill_id": math_target["skillId"],
            "boundary_ordinal": math_target["boundaryOrdinal"],
            "boundary_version": math_target["boundaryVersion"],
            "variant_ordinal": math_target["variantOrdinal"],
        }
        generator = service._content_profile_evidence("generator")
        verifier = service._content_profile_evidence("verifier")
        candidate_course = {
            "id": "course-1",
            "version": "v1",
            "content": {"sealed": True},
        }
        final_checkpoint = {
            "candidateCourse": candidate_course,
            "questionFingerprints": [],
            "validation": {},
            "independentSolution": {},
        }
        host_evidence = QuestionPhaseCourseEvidence(
            final_phase="independent_verification",
            final_phase_ordinal=11,
            candidate_course=candidate_course,
            question_fingerprints=final_checkpoint["questionFingerprints"],
            validation=final_checkpoint["validation"],
            independent_solution=final_checkpoint["independentSolution"],
            generator_profile=generator,
            verifier_profile=verifier,
            existing_fingerprint_count=0,
        )
        identity = PrimaryOneHostGateIdentity(
            catalog_item_id="item-1",
            logical_attempt=1,
            generation_request_id="request-1",
            course_id="course-1",
            course_version="v1",
            curriculum_version=item["curriculum_version"],
            content_validation_contract_version=CONTENT_VALIDATION_CONTRACT_VERSION,
            content_validation_dataset_sha256=PRIMARY_ONE_CONTENT_DATASET_SHA256,
            subject_language_policy_version=SUBJECT_LANGUAGE_POLICY_VERSION,
            generator_profile_hash=generator.profile_hash,
            verifier_profile_hash=verifier.profile_hash,
        )
        receipt_base = service.primary_one_host_validator._primary_one_receipt_base(
            target=service._content_target(item),
            identity=identity,
            evidence=host_evidence,
            skill_boundary_sha256=hashlib.sha256(
                service._canonical_content_json(
                    service._content_boundary(str(item["skill_id"]))
                ).encode("utf-8")
            ).hexdigest(),
            candidate_course_sha256=hashlib.sha256(
                service._canonical_content_json(candidate_course).encode("utf-8")
            ).hexdigest(),
            sidecar_evidence_sha256=hashlib.sha256(
                service._canonical_content_json(
                    {
                        "questionFingerprints": final_checkpoint[
                            "questionFingerprints"
                        ],
                        "validation": final_checkpoint["validation"],
                        "independentSolution": final_checkpoint[
                            "independentSolution"
                        ],
                    }
                ).encode("utf-8")
            ).hexdigest(),
        )
        receipt = service.primary_one_host_validator._primary_one_rejected(
            receipt_base,
            [],
            issue="content",
            fingerprint="",
        ).receipt
        receipt_hash = hashlib.sha256(
            service._canonical_content_json(receipt).encode("utf-8")
        ).hexdigest()
        envelope = {
            "schemaVersion": "mira.learning.primary-1-host-gate-evidence.v1",
            "contentFingerprint": "",
            "hostGateReceipt": receipt,
            "hostGateReceiptHash": receipt_hash,
        }
        histories = {
            1: {
                "requestId": "request-1",
                "dispatches": [{"id": "attempt-one-dispatch"}],
                "jobs": [],
                "candidates": [],
                "courses": [],
            },
            2: {
                "requestId": "request-1.attempt2",
                "dispatches": [],
                "jobs": [],
                "candidates": [],
                "courses": [],
            },
        }
        attempt_one = {
            "dispatches": [
                {
                    "id": "attempt-one-dispatch",
                    "phase": "independent_verification",
                    "phase_ordinal": 11,
                    "attempt_started_at": 1_000,
                    "attempt_hard_deadline_at": 1_801_000,
                }
            ],
            "job": {
                "id": "job-1",
                "request_id": "request-1",
                "status": "failed",
            },
            "candidate": {
                "id": "candidate-1",
                "job_id": "job-1",
                "status": "rejected",
                "course_id": "course-1",
                "course_version": "v1",
                "validation_json": service._canonical_content_json(envelope),
                "published_at": None,
            },
            "course": {"id": "course-1", "version": "v1"},
        }
        graph = ContentDispatchGraphAuditSnapshot(
            item_id="item-1",
            logical_attempt=1,
            dispatch_ids=("attempt-one-dispatch",),
            final_phase="independent_verification",
            final_phase_ordinal=11,
        )
        service._validated_content_dispatch_graph = lambda **_kwargs: (
            graph,
            {
                ("independent_verification", 11): final_checkpoint
            },
        )
        service._validate_locked_generation_persistence = lambda **_kwargs: None
        attempt_one["dispatches"][0].update(
            provider=verifier.name,
            model=verifier.model,
            profile=verifier.profile_hash,
        )

        def invoke(history):
            service._locked_attempt_evidence = lambda **_kwargs: history
            return service.audit_content_provider_dependency_retry(
                evidence={"item": item, "attemptHistories": histories},
                content_phase="outline",
            )

        self.assertIsInstance(invoke(attempt_one), ContentProviderDependencyAuditSnapshot)
        mutations = {
            "job_status": lambda value: value["job"].update(status="validated"),
            "candidate_status": lambda value: value["candidate"].update(
                status="course_validated"
            ),
            "published": lambda value: value["candidate"].update(published_at=1),
            "receipt_hash": lambda value: value["candidate"].update(
                validation_json=service._canonical_content_json(
                    {**envelope, "hostGateReceiptHash": "b" * 64}
                )
            ),
            "passed_receipt": lambda value: value["candidate"].update(
                validation_json=service._canonical_content_json(
                    {
                        **envelope,
                        "hostGateReceipt": {
                            **receipt,
                            "outcome": "passed",
                        },
                        "hostGateReceiptHash": hashlib.sha256(
                            service._canonical_content_json(
                                {**receipt, "outcome": "passed"}
                            ).encode("utf-8")
                        ).hexdigest(),
                    }
                )
            ),
            "dispatch_profile": lambda value: value["dispatches"][0].update(
                profile="b" * 64
            ),
            "receipt_item_identity": lambda value: value["candidate"].update(
                validation_json=service._canonical_content_json(
                    {
                        **envelope,
                        "hostGateReceipt": {
                            **receipt,
                            "catalogItemId": "other-item",
                        },
                        "hostGateReceiptHash": hashlib.sha256(
                            service._canonical_content_json(
                                {**receipt, "catalogItemId": "other-item"}
                            ).encode("utf-8")
                        ).hexdigest(),
                    }
                )
            ),
            "fingerprint_non_string": lambda value: value["candidate"].update(
                validation_json=service._canonical_content_json(
                    {**envelope, "contentFingerprint": 0}
                )
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(drift=label):
                changed = copy.deepcopy(attempt_one)
                mutate(changed)
                with self.assertRaises(ValueError):
                    invoke(changed)

    def test_parent_retry_projection_has_exact_sealed_contract(self):
        self.assertEqual(
            [field.name for field in fields(ContentParentRetryAuditSnapshot)],
            [
                "build_id",
                "release_id",
                "authority_class",
                "provider_dispatch_ids",
                "open_or_ambiguous_dispatch_ids",
                "failed_safe_dispatch_ids",
                "provider_graph_complete",
                "next_work_kind",
                "build_error_code",
            ],
        )
        signature = inspect.signature(
            LearningCatalogReleaseService.audit_content_parent_retry_authority
        )
        self.assertEqual(set(signature.parameters), {"self", "inventory"})

    def test_parent_retry_projection_rejects_catalog_manifest_and_residue_drift(self):
        service = object.__new__(LearningCatalogReleaseService)
        service.repository = object.__new__(LearningCatalogRepository)
        target = build_preparation_target("primary_1")
        fingerprint = preparation_target_fingerprint(target)
        request_id = f"grade-build:{fingerprint}"
        request_digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[
            :24
        ]
        build_id = f"catalog_build_{request_digest}"
        release_id = f"catalog_release_{request_digest}"
        items = []
        for course_target in target["courseTargets"]:
            identity = (
                f"{build_id}:primary_1:{course_target['subject']}:"
                f"{course_target['skillId']}:"
                f"{course_target['variantOrdinal']}"
            )
            item_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            items.append(
                {
                    "id": f"catalog_build_item_{item_digest[:24]}",
                    "generation_request_id": f"catalog_gen_{item_digest[:48]}",
                    "build_job_id": build_id,
                    "release_id": release_id,
                    "grade_code": "primary_1",
                    "subject": course_target["subject"],
                    "skill_id": course_target["skillId"],
                    "curriculum_version": target["curriculumVersion"],
                    "boundary_version": course_target["boundaryVersion"],
                    "variant_ordinal": course_target["variantOrdinal"],
                    "subject_ordinal": course_target["subjectOrdinal"],
                    "boundary_ordinal": course_target["boundaryOrdinal"],
                    "execution_mode_snapshot": "content_only",
                    "content_manifest_version_snapshot": target[
                        "schemaVersion"
                    ],
                    "package_attempt_count": 0,
                    "active_package_request_id": None,
                    "package_id": None,
                    "package_version": None,
                    "status": "pending",
                    "attempt_count": 0,
                    "content_phase": "not_started",
                    "content_gate_status": "not_started",
                }
            )
        inventory = {
            "plan": {
                "catalog_build_id": build_id,
                "catalog_release_id": release_id,
                "shared_build_request_id": request_id,
                "target_fingerprint": fingerprint,
                "target_spec_json": service._canonical_content_json(target),
                "grade_code": "primary_1",
                "curriculum_version": target["curriculumVersion"],
            },
            "release": {
                "id": release_id,
                "status": "draft",
                "quality_status": "building",
                "curriculum_version": target["curriculumVersion"],
                "required_boundary_count": 10,
                "ready_item_count": 0,
                "activated_at": None,
                "retired_at": None,
            },
            "build": {
                "id": build_id,
                "release_id": release_id,
                "request_id": request_id,
                "execution_mode": "content_only",
                "stage_ceiling": "content_ready",
                "status": "queued",
                "curriculum_version": target["curriculumVersion"],
                "target_spec_json": service._canonical_content_json(target),
                "content_manifest_version": target["schemaVersion"],
                "canary_manifest_json": service._canonical_content_json(
                    target["canaryManifest"]
                ),
                "total_item_count": 30,
                "ready_item_count": 0,
                "failed_item_count": 0,
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
            },
            "items": items,
            "dispatches": [],
            "evidence": [],
            "attemptHistoriesByItem": {},
            "releaseHasCatalogItems": False,
        }

        baseline = service.audit_content_parent_retry_authority(
            inventory=inventory
        )

        self.assertEqual(baseline.authority_class, "pre_provider_dependency")
        self.assertEqual(baseline.provider_dispatch_ids, ())
        self.assertFalse(baseline.provider_graph_complete)

        def self_consistent_evil_request(value):
            evil_request = "evil-request"
            evil_digest = hashlib.sha256(
                evil_request.encode("utf-8")
            ).hexdigest()[:24]
            evil_build = f"catalog_build_{evil_digest}"
            evil_release = f"catalog_release_{evil_digest}"
            value["plan"].update(
                shared_build_request_id=evil_request,
                catalog_build_id=evil_build,
                catalog_release_id=evil_release,
            )
            value["build"].update(
                id=evil_build,
                release_id=evil_release,
                request_id=evil_request,
            )
            value["release"]["id"] = evil_release
            for row in value["items"]:
                identity = (
                    f"{evil_build}:primary_1:{row['subject']}:"
                    f"{row['skill_id']}:{row['variant_ordinal']}"
                )
                item_digest = hashlib.sha256(
                    identity.encode("utf-8")
                ).hexdigest()
                row.update(
                    id=f"catalog_build_item_{item_digest[:24]}",
                    generation_request_id=(
                        f"catalog_gen_{item_digest[:48]}"
                    ),
                    build_job_id=evil_build,
                    release_id=evil_release,
                )

        mutations = {
            "self_consistent_evil_request": self_consistent_evil_request,
            "release_status": lambda value: value["release"].update(
                status="active"
            ),
            "build_status": lambda value: value["build"].update(
                status="completed"
            ),
            "build_mode": lambda value: value["build"].update(
                execution_mode="full_pipeline"
            ),
            "target_manifest": lambda value: value["build"].update(
                target_spec_json="{}"
            ),
            "plan_fingerprint": lambda value: value["plan"].update(
                target_fingerprint="0" * 64
            ),
            "plan_target": lambda value: value["plan"].update(
                target_spec_json="{}"
            ),
            "item_snapshot": lambda value: value["items"][0].update(
                skill_id="drifted"
            ),
            "publication_residue": lambda value: value.update(
                releaseHasCatalogItems=True
            ),
            "future_dispatch_residue": lambda value: value["dispatches"].append(
                {
                    "id": "future-residue",
                    "build_item_id": value["items"][-1]["id"],
                    "logical_attempt": 1,
                    "status": "succeeded",
                }
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(drift=label):
                changed = copy.deepcopy(inventory)
                mutate(changed)
                snapshot = service.audit_content_parent_retry_authority(
                    inventory=changed
                )
                self.assertEqual(snapshot.authority_class, "not_replayable")
                self.assertFalse(snapshot.provider_graph_complete)

    def test_content_dispatch_graph_projection_has_exact_sealed_contract(self):
        self.assertEqual(
            [field.name for field in fields(ContentDispatchGraphAuditSnapshot)],
            [
                "item_id",
                "logical_attempt",
                "dispatch_ids",
                "final_phase",
                "final_phase_ordinal",
            ],
        )
        signature = inspect.signature(
            LearningCatalogReleaseService.audit_content_dispatch_graph
        )
        self.assertEqual(
            set(signature.parameters),
            {"self", "item", "dispatches"},
        )
        host_retry_signature = inspect.signature(
            LearningCatalogReleaseService.audit_content_host_retry_graph
        )
        self.assertEqual(
            set(host_retry_signature.parameters),
            {"self", "evidence", "prior_evidence"},
        )

    def test_host_retry_graph_projection_consumes_prior_and_attempt_one_evidence(self):
        service = object.__new__(LearningCatalogReleaseService)
        item = {
            "id": "item-1",
            "status": "processing",
            "content_phase": "host_gate_pending",
            "content_gate_status": "pending",
            "content_gate_attempt_count": 0,
            "content_gate_passed_at": None,
            "content_validation_contract_version": None,
            "content_receipt_hash": None,
            "attempt_count": 2,
            "content_claim_attempt_ordinal": 2,
            "content_attempt_started_at": 200,
            "content_provider_attempt_hard_deadline_at": None,
            "content_lease_token": None,
            "content_lease_expires_at": None,
            "content_heartbeat_at": None,
            "content_work_unit_deadline_at": None,
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1.attempt2",
            "course_id": "course-2",
            "course_version": "v2",
        }
        current = {
            "dispatches": [{"id": "dispatch-2"}],
            "job": {
                "id": "job-2",
                "request_id": "request-1.attempt2",
                "status": "generating",
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
            },
            "candidate": {
                "id": "candidate-2",
                "job_id": "job-2",
                "ordinal": 1,
                "status": "generated",
                "course_id": "course-2",
                "course_version": "v2",
                "validation_json": None,
                "error_code": None,
                "error_message_safe": None,
                "published_at": None,
            },
            "course": {"id": "course-2", "version": "v2"},
        }
        attempt_one = {
            "dispatches": [{"id": "dispatch-1"}],
            "job": {"id": "job-1"},
            "candidate": {"id": "candidate-1"},
            "course": {"id": "course-1"},
        }
        calls = []

        def locked_attempt(*, evidence, attempt):
            del evidence
            calls.append(("attempt", attempt))
            return attempt_one if attempt == 1 else current

        service._locked_attempt_evidence = locked_attempt
        service._locked_host_pending_attempt_evidence = locked_attempt
        service._validate_locked_rejected_history = lambda **kwargs: calls.append(
            ("attemptOne", kwargs["prior_evidence"])
        )
        service._content_host_evidence = lambda **kwargs: calls.append(
            ("hostEvidence", kwargs["plan"]["priorEvidence"])
        ) or (
            type("_HostEvidence", (), {"candidate_course": {}})(),
            object(),
            object(),
            (),
        )
        service._validate_locked_host_pending_persistence = (
            lambda **kwargs: calls.append(
                ("pendingPersistence", kwargs["attempt_one_evidence"])
            )
        )
        expected = ContentDispatchGraphAuditSnapshot(
            item_id="item-1",
            logical_attempt=2,
            dispatch_ids=("dispatch-2",),
            final_phase="independent_verification",
            final_phase_ordinal=11,
        )
        service.audit_content_dispatch_graph = lambda **kwargs: calls.append(
            ("dispatchGraph", kwargs["dispatches"])
        ) or expected
        prior = ({"item": {"id": "prior-1"}},)

        actual = service.audit_content_host_retry_graph(
            evidence={"item": item, "attemptHistories": {}},
            prior_evidence=prior,
        )

        self.assertEqual(actual, expected)
        self.assertIn(("attempt", 1), calls)
        self.assertIn(("attempt", 2), calls)
        self.assertIn(("attemptOne", prior), calls)
        self.assertIn(("hostEvidence", prior), calls)
        self.assertIn(("dispatchGraph", current["dispatches"]), calls)

    def test_attempt_one_host_retry_rejects_all_attempt_two_residue(self):
        service = object.__new__(LearningCatalogReleaseService)
        item = {
            "id": "item-1",
            "status": "processing",
            "content_phase": "host_gate_pending",
            "content_gate_status": "pending",
            "content_gate_attempt_count": 0,
            "content_gate_passed_at": None,
            "content_validation_contract_version": None,
            "content_receipt_hash": None,
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "content_attempt_started_at": 100,
            "content_provider_attempt_hard_deadline_at": None,
            "content_lease_token": None,
            "content_lease_expires_at": None,
            "content_heartbeat_at": None,
            "content_work_unit_deadline_at": None,
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1",
            "course_id": "course-1",
            "course_version": "v1",
        }
        current = {
            "candidate": {
                "id": "candidate-1",
                "job_id": "job-1",
                "ordinal": 1,
                "status": "generated",
                "course_id": "course-1",
                "course_version": "v1",
                "validation_json": None,
                "error_code": None,
                "error_message_safe": None,
                "published_at": None,
            },
            "job": {
                "id": "job-1",
                "request_id": "request-1",
                "status": "generating",
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
            },
            "dispatches": [{"id": "dispatch-1"}],
            "course": None,
        }
        service._locked_host_pending_attempt_evidence = (
            lambda **_kwargs: current
        )
        service._content_host_evidence = lambda **_kwargs: (
            type("_HostEvidence", (), {"candidate_course": {}})(),
            object(),
            object(),
            (),
        )
        service._validate_locked_host_pending_persistence = lambda **_kwargs: None
        service.audit_content_dispatch_graph = lambda **_kwargs: (
            ContentDispatchGraphAuditSnapshot(
                item_id="item-1",
                logical_attempt=1,
                dispatch_ids=("dispatch-1",),
                final_phase="independent_verification",
                final_phase_ordinal=11,
            )
        )
        empty = {
            "requestId": "request-1.attempt2",
            "dispatches": [],
            "jobs": [],
            "candidates": [],
            "courses": [],
        }
        for key in ("jobs", "candidates", "courses"):
            with self.subTest(residue=key):
                attempt_two = copy.deepcopy(empty)
                attempt_two[key].append({"id": f"residue-{key}"})
                with self.assertRaises(ValueError):
                    service.audit_content_host_retry_graph(
                        evidence={
                            "item": item,
                            "attemptHistories": {
                                1: {},
                                2: attempt_two,
                            },
                        },
                        prior_evidence=(),
                    )

    def test_host_retry_requires_exact_phase_lease_and_persistence_authority(self):
        service = object.__new__(LearningCatalogReleaseService)
        current = {
            "candidate": {
                "id": "candidate-1",
                "job_id": "job-1",
                "ordinal": 1,
                "status": "generated",
                "course_id": "course-1",
                "course_version": "v1",
                "validation_json": None,
                "error_code": None,
                "error_message_safe": None,
                "published_at": None,
            },
            "job": {
                "id": "job-1",
                "request_id": "request-1",
                "status": "generating",
                "error_code": None,
                "error_message_safe": None,
                "completed_at": None,
            },
            "dispatches": [{"id": "dispatch-1"}],
            "course": None,
        }
        service._locked_host_pending_attempt_evidence = (
            lambda **_kwargs: current
        )
        service._content_host_evidence = lambda **_kwargs: (
            type("_HostEvidence", (), {"candidate_course": {}})(),
            object(),
            object(),
            (),
        )
        service._validate_locked_host_pending_persistence = lambda **_kwargs: None
        service.audit_content_dispatch_graph = lambda **_kwargs: (
            ContentDispatchGraphAuditSnapshot(
                item_id="item-1",
                logical_attempt=1,
                dispatch_ids=("dispatch-1",),
                final_phase="independent_verification",
                final_phase_ordinal=11,
            )
        )
        base_item = {
            "id": "item-1",
            "status": "processing",
            "content_phase": "host_gate_pending",
            "content_gate_status": "pending",
            "content_gate_attempt_count": 0,
            "content_gate_passed_at": None,
            "content_validation_contract_version": None,
            "content_receipt_hash": None,
            "attempt_count": 1,
            "content_claim_attempt_ordinal": 1,
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1",
            "content_lease_token": None,
            "content_lease_expires_at": None,
            "content_heartbeat_at": None,
            "content_provider_attempt_hard_deadline_at": None,
            "content_work_unit_deadline_at": None,
            "content_attempt_started_at": 500,
            "course_id": "course-1",
            "course_version": "v1",
        }
        empty_attempt_two = {
            "requestId": "request-1.attempt2",
            "dispatches": [],
            "jobs": [],
            "candidates": [],
            "courses": [],
        }
        evidence = {
            "item": base_item,
            "attemptHistories": {1: {}, 2: empty_attempt_two},
        }
        self.assertEqual(
            service.audit_content_host_retry_graph(
                evidence=evidence,
                prior_evidence=(),
            ).item_id,
            "item-1",
        )
        item_mutations = {
            "pending_token": {"content_lease_token": "host-lease"},
            "pending_deadline": {"content_work_unit_deadline_at": 2_000},
            "pending_exhausted": {"content_gate_attempt_count": 3},
            "claim_ordinal": {"content_claim_attempt_ordinal": 2},
            "receipt": {"content_receipt_hash": "a" * 64},
            "running_deadline_mismatch": {
                "content_phase": "host_gate_running",
                "content_gate_attempt_count": 1,
                "content_lease_token": "host-lease",
                "content_lease_expires_at": 2_001,
                "content_heartbeat_at": 1_000,
                "content_work_unit_deadline_at": 2_000,
            },
        }
        for label, mutation in item_mutations.items():
            with self.subTest(item_drift=label), self.assertRaises(ValueError):
                service.audit_content_host_retry_graph(
                    evidence={
                        **evidence,
                        "item": {**base_item, **mutation},
                    },
                    prior_evidence=(),
                )

    def test_host_pending_persistence_reuses_exact_task7_generation_envelope(self):
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
            "verifier": profile,
        }
        item = {
            "grade_code": "primary_1",
            "subject": "math",
            "skill_id": "number_sense_20",
            "curriculum_version": "mira.primary.2026-fall.v1",
            "boundary_version": "boundary-v1",
            "active_generation_request_id": "request-1",
            "course_id": "course-1",
            "course_version": "v1",
        }
        candidate_course = {
            "id": "course-1",
            "version": "v1",
            "gradeCode": "primary_1",
            "subject": "math",
            "nodeCode": "number_sense_20",
            "title": "20以内数感",
            "objective": "建立20以内数感",
            "content": {"slides": [{"kind": "explain"}]},
        }
        normalized_profile = service._content_profile_payload("generator")
        request_id = item["active_generation_request_id"]
        job_id = "learning_course_job_" + hashlib.sha256(
            request_id.encode("utf-8")
        ).hexdigest()[:32]
        request_fingerprint = hashlib.sha256(
            service._canonical_content_json(
                {
                    "gradeCode": item["grade_code"],
                    "subject": item["subject"],
                    "nodeCode": item["skill_id"],
                    "curriculumVersion": item["curriculum_version"],
                    "boundaryVersion": item["boundary_version"],
                    "generator": "openmaic_question_phase_v2",
                    "providerProfile": normalized_profile,
                    "requestedCandidateCount": 1,
                }
            ).encode("utf-8")
        ).hexdigest()
        candidate_id = "learning_course_candidate_" + hashlib.sha256(
            f"{job_id}:1".encode("utf-8")
        ).hexdigest()[:32]
        content_hash = hashlib.sha256(
            service._canonical_content_json(
                {
                    "gradeCode": candidate_course["gradeCode"],
                    "subject": candidate_course["subject"],
                    "nodeCode": candidate_course["nodeCode"],
                    "title": candidate_course["title"],
                    "objective": candidate_course["objective"],
                    "content": candidate_course["content"],
                }
            ).encode("utf-8")
        ).hexdigest()
        job = {
            "id": job_id,
            "request_id": request_id,
            "request_fingerprint": request_fingerprint,
            "grade_code": item["grade_code"],
            "subject": item["subject"],
            "node_code": item["skill_id"],
            "curriculum_version": item["curriculum_version"],
            "boundary_version": item["boundary_version"],
            "generator": "openmaic_question_phase_v2",
            "provider": normalized_profile["name"],
            "model": normalized_profile["model"],
            "prompt_version": "mira.learning.question-contract.v2",
            "requested_candidate_count": 1,
            "status": "generating",
            "error_code": None,
            "error_message_safe": None,
            "completed_at": None,
        }
        candidate = {
            "id": candidate_id,
            "job_id": job_id,
            "ordinal": 1,
            "course_id": candidate_course["id"],
            "course_version": candidate_course["version"],
            "grade_code": candidate_course["gradeCode"],
            "subject": candidate_course["subject"],
            "node_code": candidate_course["nodeCode"],
            "curriculum_version": item["curriculum_version"],
            "boundary_version": item["boundary_version"],
            "title": candidate_course["title"],
            "objective": candidate_course["objective"],
            "status": "generated",
            "content_hash": content_hash,
            "content_json": service._canonical_content_json(
                candidate_course["content"]
            ),
            "validation_json": None,
            "error_code": None,
            "error_message_safe": None,
            "published_at": None,
        }
        evidence = {"job": job, "candidate": candidate, "course": None}
        service._validate_locked_host_pending_persistence(
            evidence=evidence,
            item=item,
            candidate_course=candidate_course,
            attempt_one_evidence=None,
        )
        for key, field, value in (
            ("job", "provider", "drifted-provider"),
            ("candidate", "subject", "english"),
            ("candidate", "title", "drifted-title"),
        ):
            with self.subTest(row=key, field=field), self.assertRaises(
                ValueError
            ):
                changed = copy.deepcopy(evidence)
                changed[key][field] = value
                service._validate_locked_host_pending_persistence(
                    evidence=changed,
                    item=item,
                    candidate_course=candidate_course,
                    attempt_one_evidence=None,
                )
        prior_course = {
            "id": "course-1",
            "version": "v1",
            "subject": "math",
            "content_json": "{}",
        }
        service._validate_locked_host_pending_persistence(
            evidence={**evidence, "course": prior_course},
            item=item,
            candidate_course=candidate_course,
            attempt_one_evidence={"course": prior_course},
        )
        with self.assertRaises(ValueError):
            service._validate_locked_host_pending_persistence(
                evidence={
                    **evidence,
                    "course": {**prior_course, "subject": "english"},
                },
                item=item,
                candidate_course=candidate_course,
                attempt_one_evidence={"course": prior_course},
            )

    def test_rejected_history_reconstructs_attempt_one_deadline_from_dispatches(self):
        service = object.__new__(LearningCatalogReleaseService)
        observed = []
        receipt = {
            "outcome": "rejected",
            "hostContentFingerprint": "f" * 64,
        }
        receipt_hash = hashlib.sha256(
            service._canonical_content_json(receipt).encode("utf-8")
        ).hexdigest()
        candidate = {
            "id": "candidate-1",
            "job_id": "job-1",
            "ordinal": 1,
            "status": "rejected",
            "course_id": "course-1",
            "course_version": "v1",
            "published_at": None,
            "validation_json": service._canonical_content_json(
                {
                    "schemaVersion": (
                        "mira.learning.primary-1-host-gate-evidence.v1"
                    ),
                    "contentFingerprint": "f" * 64,
                    "hostGateReceipt": receipt,
                    "hostGateReceiptHash": receipt_hash,
                }
            ),
        }
        item = {
            "id": "item-1",
            "generation_request_id": "request-1",
            "active_generation_request_id": "request-1.attempt2",
            "grade_code": "primary_1",
            "subject": "chinese",
            "skill_id": "pinyin_syllables",
            "curriculum_version": "primary-1-v1",
            "boundary_version": "boundary-v1",
            "attempt_count": 2,
            "content_attempt_started_at": 200_000,
        }
        history = {
            "candidate": candidate,
            "job": {
                "id": "job-1",
                "status": "failed",
                "request_id": "request-1",
                "grade_code": "primary_1",
                "subject": "chinese",
                "node_code": "pinyin_syllables",
                "curriculum_version": "primary-1-v1",
                "boundary_version": "boundary-v1",
                "generator": "openmaic_question_phase_v2",
                "requested_candidate_count": 1,
            },
            "course": {"id": "course-1", "version": "v1"},
            "dispatches": [
                {
                    "attempt_started_at": 100_000,
                    "attempt_hard_deadline_at": 1_900_000,
                }
            ],
        }

        def host_evidence(*, plan, item):
            del plan
            observed.append(dict(item))
            return (
                type("Evidence", (), {"candidate_course": {}})(),
                object(),
                object(),
                (),
            )

        service._content_host_evidence = host_evidence
        service._validate_locked_generation_persistence = lambda **_kwargs: None
        service._content_boundary = lambda _skill: {}
        service.primary_one_host_validator = type(
            "Validator",
            (),
            {
                "validate_primary_one_host_gate": lambda *_args, **_kwargs: (
                    type(
                        "Replay",
                        (),
                        {
                            "outcome": "rejected",
                            "course": None,
                            "receipt": receipt,
                            "receipt_hash": receipt_hash,
                        },
                    )()
                )
            },
        )()

        service._validate_locked_rejected_history(
            evidence={},
            item=item,
            history_evidence=history,
            prior_evidence=(),
        )

        self.assertEqual(observed[0]["content_attempt_started_at"], 100_000)
        self.assertIsNone(
            observed[0]["content_provider_attempt_hard_deadline_at"]
        )

    def test_locked_dispatch_input_replay_never_sees_future_checkpoints(self):
        service = object.__new__(LearningCatalogReleaseService)
        checkpoints = {
            ("outline", 1): {"phaseStatus": "accepted"},
            ("raw_candidate", 2): {"phaseStatus": "accepted"},
        }
        snapshot = ContentDispatchGraphAuditSnapshot(
            item_id="item-1",
            logical_attempt=1,
            dispatch_ids=("dispatch-1", "dispatch-2"),
            final_phase="raw_candidate",
            final_phase_ordinal=2,
        )
        service._validated_content_dispatch_graph = lambda **_kwargs: (
            snapshot,
            checkpoints,
        )
        service._attempt_initial_checkpoint = lambda **_kwargs: {}
        observed = []

        def assemble(*, phase, phase_ordinal, initial, succeeded):
            del phase, phase_ordinal, initial
            observed.append(tuple(succeeded))
            return {}

        service._assemble_content_checkpoint = assemble
        service._content_boundary = lambda _skill_id: {}
        service._content_provider_preflight = lambda _command: type(
            "Prepared", (), {"input_sha256": "a" * 64}
        )()
        item = {
            "id": "item-1",
            "attempt_count": 1,
            "active_generation_request_id": "request-1",
            "subject": "chinese",
            "skill_id": "primary_1_chinese_pinyin_initials",
        }
        dispatches = [
            {
                "phase": "outline",
                "phase_ordinal": 1,
                "input_sha256": "a" * 64,
            },
            {
                "phase": "raw_candidate",
                "phase_ordinal": 2,
                "input_sha256": "a" * 64,
            },
        ]

        service._validate_content_dispatch_chain(
            item=item,
            dispatches=dispatches,
            plan={
                "priorEvidence": [],
                "historicalQuestionFingerprints": [],
            },
        )

        self.assertEqual(observed, [(), (("outline", 1),)])

    def test_locked_content_proof_snapshot_has_exact_sealed_contract(self):
        self.assertEqual(
            [field.name for field in fields(ContentProofAuditSnapshot)],
            [
                "build_id",
                "release_id",
                "passed_item_ids",
                "repairable_item_ids",
                "terminal_failed_item_ids",
            ],
        )
        signature = inspect.signature(
            LearningCatalogReleaseService.audit_locked_content_proofs
        )
        self.assertEqual(set(signature.parameters), {"self", "conn", "build_id"})

    def test_locked_content_proof_projection_derives_only_audited_item_ids(self):
        service = object.__new__(LearningCatalogReleaseService)
        items = [
            {
                "id": f"item-{index:02d}",
                "status": (
                    "course_ready"
                    if index < 2
                    else "failed" if index in {2, 3} else "pending"
                ),
            }
            for index in range(30)
        ]

        class Repository:
            def load_content_proof_inventory(self, conn, *, build_id):
                self.call = (conn, build_id)
                return {
                    "release": {"id": "release-1"},
                    "build": {"id": build_id, "release_id": "release-1"},
                    "items": items,
                    "evidence": [],
                }

        repository = Repository()
        service.repository = repository
        service._audit_locked_content_inventory = lambda *, conn, inventory: {
            "passedItemIds": frozenset({"item-00", "item-01"}),
            "repairableItemIds": frozenset({"item-02"}),
            "proofs": (),
        }
        service._validate_content_handoff_proofs = lambda _proofs: (_ for _ in ()).throw(
            AssertionError("partial inventory validated as handoff")
        )
        conn = object()

        snapshot = service.audit_locked_content_proofs(
            conn, build_id="build-1"
        )

        self.assertEqual(repository.call, (conn, "build-1"))
        self.assertEqual(
            snapshot,
            ContentProofAuditSnapshot(
                build_id="build-1",
                release_id="release-1",
                passed_item_ids=("item-00", "item-01"),
                repairable_item_ids=("item-02",),
                terminal_failed_item_ids=("item-03",),
            ),
        )

    def test_content_work_unit_claim_and_optional_callbacks_are_backwards_compatible(self):
        self.assertEqual(
            [field.name for field in fields(ContentWorkUnitClaim)],
            [
                "build_id",
                "item_id",
                "item_lease_token",
                "logical_attempt",
                "content_phase",
                "work_unit_kind",
                "work_unit_deadline_at",
            ],
        )
        signature = inspect.signature(
            LearningCatalogReleaseService.advance_content
        )
        self.assertIsNone(signature.parameters["bind_work_unit"].default)
        self.assertIsNone(
            signature.parameters["authorize_control_work"].default
        )

    def test_content_advance_result_has_the_exact_public_contract(self):
        self.assertEqual(
            [field.name for field in fields(ContentAdvanceResult)],
            ["kind", "build_id", "item_id", "content_summary"],
        )
        summary = {
            "contentCandidateItemCount": 0,
            "contentFailedItemCount": 0,
            "subjectContentProgress": {},
            "canary": {},
            "canActivate": False,
        }
        for kind in (
            "progressed",
            "busy",
            "dependency_retry",
            "failed",
            "handoff",
            "stale",
        ):
            with self.subTest(kind=kind):
                result = ContentAdvanceResult(
                    kind=kind,
                    build_id="catalog-build-1",
                    item_id=None,
                    content_summary=summary,
                )
                self.assertEqual(result.kind, kind)
                self.assertEqual(result.build_id, "catalog-build-1")
                self.assertIsNone(result.item_id)
                self.assertEqual(result.content_summary, summary)

    def test_live_host_dependency_retry_reclaims_same_ordinal_and_deadline(self):
        repository = object.__new__(LearningCatalogRepository)
        now = 100_000
        deadline = now + 50_000
        row = {
            "id": "item-1",
            "attempt_count": 1,
            "content_phase": "host_gate_running",
            "content_gate_status": "retry_wait",
            "content_gate_attempt_count": 1,
            "content_work_unit_deadline_at": deadline,
            "content_lease_token": "host-lease",
            "content_lease_expires_at": deadline,
        }
        claimed = dict(row)
        connection = _RecordingUpdateConnection()
        repository.get_item = lambda conn, *, item_id: claimed
        repository._lock_content_candidate_for_item = (
            lambda conn, *, row: ({"id": "job-1"}, {"id": "candidate-1"})
        )
        repository.list_content_dispatches = lambda *args, **kwargs: []
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
            row=row,
            rows=[row],
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
        self.assertEqual(connection.executions, [])
        self.assertEqual(plan["item"]["content_gate_attempt_count"], 1)
        self.assertEqual(plan["item"]["content_lease_token"], "host-lease")
        self.assertEqual(
            plan["item"]["content_work_unit_deadline_at"], deadline
        )

    def test_content_authority_rejects_non_draft_release_before_work(self):
        repository = object.__new__(LearningCatalogRepository)
        target = build_preparation_target("primary_1")
        build = {
            "id": "build-1",
            "execution_mode": "content_only",
            "stage_ceiling": "content_ready",
            "target_spec_json": repository.encode_json(target),
            "content_manifest_version": target["schemaVersion"],
            "canary_manifest_json": repository.encode_json(
                target["canaryManifest"]
            ),
            "total_item_count": 30,
        }
        release = {
            "id": "release-1",
            "status": "building",
            "curriculum_version": target["curriculumVersion"],
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

        self.assertFalse(
            repository._content_authority_is_exact(
                object(), release=release, build=build, rows=rows
            )
        )

    def test_exact_canaries_then_fair_variant_order_reaches_all_thirty(self):
        target = build_preparation_target("primary_1")
        repository = LearningCatalogRepository(
            Database("mysql+pymysql://unused:unused@127.0.0.1:3306/unused")
        )
        rows = [
            {
                "id": f"item-{index}",
                "subject": item["subject"],
                "subject_ordinal": item["subjectOrdinal"],
                "skill_id": item["skillId"],
                "boundary_ordinal": item["boundaryOrdinal"],
                "boundary_version": item["boundaryVersion"],
                "variant_ordinal": item["variantOrdinal"],
                "status": "pending",
                "attempt_count": 0,
                "content_phase": "not_started",
                "content_gate_status": "not_started",
            }
            for index, item in enumerate(target["courseTargets"])
        ]
        build = {
            "canary_manifest_json": repository.encode_json(target["canaryManifest"])
        }
        selected: list[tuple[str, str, int]] = []
        canary_keys = {
            ("chinese", "pinyin_syllables", 1),
            ("math", "number_sense_20", 1),
            ("english", "letters_sounds", 1),
        }
        for _ in range(30):
            passed_keys = {
                (row["subject"], row["skill_id"], row["variant_ordinal"])
                for row in rows
                if row["status"] == "course_ready"
            }
            eligible = repository._eligible_content_rows(
                conn=object(),
                build=build,
                rows=rows,
                canaries_passed=canary_keys.issubset(passed_keys),
                passed_item_ids=frozenset(
                    str(row["id"])
                    for row in rows
                    if row["status"] == "course_ready"
                ),
            )
            passed_by_subject = {
                ordinal: sum(
                    1
                    for row in rows
                    if row["subject_ordinal"] == ordinal
                    and row["status"] == "course_ready"
                )
                for ordinal in (1, 2, 3)
            }
            row = repository._select_fair_content_row(
                eligible=eligible,
                passed_by_subject=passed_by_subject,
            )
            row["status"] = "course_ready"
            row["content_phase"] = "course_ready"
            row["content_gate_status"] = "passed"
            selected.append(
                (row["subject"], row["skill_id"], row["variant_ordinal"])
            )

        self.assertEqual(
            selected[:3],
            [
                ("chinese", "pinyin_syllables", 1),
                ("math", "number_sense_20", 1),
                ("english", "letters_sounds", 1),
            ],
        )
        self.assertEqual(
            {
                subject: sum(1 for row in rows if row["subject"] == subject and row["status"] == "course_ready")
                for subject in ("chinese", "math", "english")
            },
            {"chinese": 12, "math": 9, "english": 9},
        )
        for subject, skill_id in {
            (row["subject"], row["skill_id"]) for row in rows
        }:
            positions = [
                selected.index((subject, skill_id, ordinal))
                for ordinal in (1, 2, 3)
            ]
            self.assertEqual(positions, sorted(positions))

    def test_exported_provider_graph_uses_all_conditional_branches(self):
        service = object.__new__(LearningCatalogReleaseService)
        accepted = {"phaseStatus": "accepted"}
        rejected = {"phaseStatus": "rejected", "rejectionCode": "rejected"}
        self.assertEqual(service._next_content_phase("outline", 1, accepted), ("raw_candidate", 2))
        self.assertEqual(service._next_content_phase("raw_candidate", 2, accepted), ("candidate_repair", 3))
        self.assertEqual(service._next_content_phase("candidate_repair", 3, accepted), ("lesson_text", 5))
        self.assertEqual(service._next_content_phase("candidate_repair", 3, rejected), ("candidate_repair_retry", 4))
        self.assertEqual(service._next_content_phase("candidate_repair_retry", 4, accepted), ("lesson_text", 5))
        self.assertEqual(service._next_content_phase("lesson_text", 5, accepted), ("reconciliation", 6))
        self.assertEqual(service._next_content_phase("reconciliation", 6, rejected), ("reconciliation_retry", 7))

        clean = {"estimatedMinutes": 10, "questions": []}
        clean_checkpoint = {"phaseStatus": "accepted", "reconciliation": clean}
        self.assertEqual(
            service._next_content_phase(
                "reconciliation", 6, clean_checkpoint, succeeded={}
            ),
            ("independent_verification", 11),
        )
        leaking = {
            "estimatedMinutes": 10,
            "questions": [
                {},
                {
                    "type": "numeric",
                    "answer": "13",
                    "prompt": "计算 7+6。",
                    "verificationExpression": "7+6",
                },
            ],
        }
        lesson = {
            ("lesson_text", 5): {
                "phaseStatus": "accepted",
                "lessonText": {
                    "teachingFlow": {
                        "teach": {"sayText": "第二题答案是13", "keyPoints": []},
                        "recap": {"sayText": "检查"},
                    }
                },
            }
        }
        leak_checkpoint = {
            "phaseStatus": "accepted",
            "reconciliation": leaking,
        }
        self.assertEqual(
            service._next_content_phase(
                "reconciliation", 6, leak_checkpoint, succeeded=lesson
            ),
            ("practice_leak_repair_1", 8),
        )
        self.assertEqual(
            service._next_content_phase(
                "practice_leak_repair_1", 8, leak_checkpoint, succeeded=lesson
            ),
            ("practice_leak_repair_2", 9),
        )
        with self.assertRaises(ValueError):
            service._next_content_phase(
                "practice_leak_repair_2", 9, leak_checkpoint, succeeded=lesson
            )
        choice = {
            "estimatedMinutes": 10,
            "questions": [
                {
                    "type": "single_choice",
                    "prompt": "请选择十二、十三。",
                    "choices": [
                        {"id": "a", "label": "十二"},
                        {"id": "b", "label": "十三"},
                    ],
                }
            ],
        }
        self.assertEqual(
            service._next_content_phase(
                "reconciliation",
                6,
                {"phaseStatus": "accepted", "reconciliation": choice},
                succeeded={},
            ),
            ("choice_prompt_repair", 10),
        )
        ordinary_mentions = {
            "estimatedMinutes": 10,
            "questions": [
                {},
                {
                    "type": "accepted_text",
                    "answer": ["苹果"],
                    "prompt": "写出图中的水果。",
                },
            ],
        }
        ordinary_lesson = {
            ("lesson_text", 5): {
                "phaseStatus": "accepted",
                "lessonText": {
                    "teachingFlow": {
                        "teach": {
                            "title": "水果观察",
                            "sayText": "苹果可以是红色，也可以是绿色。",
                            "keyPoints": [],
                        },
                        "recap": {"sayText": "观察形状和颜色。"},
                    }
                },
            }
        }
        self.assertEqual(
            service._next_content_phase(
                "reconciliation",
                6,
                {"phaseStatus": "accepted", "reconciliation": ordinary_mentions},
                succeeded=ordinary_lesson,
            ),
            ("independent_verification", 11),
        )
        ordinary_choice_sentence = {
            "estimatedMinutes": 10,
            "questions": [
                {
                    "type": "single_choice",
                    "prompt": "十二比十三少几？",
                    "choices": [
                        {"id": "a", "label": "十二"},
                        {"id": "b", "label": "十三"},
                    ],
                }
            ],
        }
        self.assertEqual(
            service._next_content_phase(
                "reconciliation",
                6,
                {
                    "phaseStatus": "accepted",
                    "reconciliation": ordinary_choice_sentence,
                },
                succeeded={},
            ),
            ("independent_verification", 11),
        )
        self.assertEqual(service._next_content_phase("choice_prompt_repair", 10, accepted), ("independent_verification", 11))
        failed_review = {
            "phaseStatus": "accepted",
            "independentSolution": {"teachingReview": {"passed": False, "issues": ["x"]}},
        }
        passed_review = {
            "phaseStatus": "accepted",
            "independentSolution": {"teachingReview": {"passed": True, "issues": []}},
        }
        self.assertEqual(service._next_content_phase("independent_verification", 11, failed_review), ("consistency_repair", 12))
        self.assertIsNone(service._next_content_phase("independent_verification", 11, passed_review))
        self.assertEqual(service._next_content_phase("consistency_repair", 12, rejected), ("consistency_repair_retry", 13))
        review_checkpoint = {("independent_verification", 11): failed_review}
        repair_accepted = {"phaseStatus": "accepted", "repair": {"changes": []}}
        self.assertEqual(
            service._next_content_phase(
                "consistency_repair",
                12,
                repair_accepted,
                succeeded=review_checkpoint,
            ),
            ("verification_after_repair", 14),
        )
        self.assertEqual(
            service._next_content_phase(
                "consistency_repair_retry",
                13,
                repair_accepted,
                succeeded=review_checkpoint,
            ),
            ("verification_after_repair", 14),
        )
        self.assertIsNone(service._next_content_phase("verification_after_repair", 14, accepted))

    def test_content_summary_is_exact_at_zero_canary_partial_and_handoff(self):
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
        zero = service._content_summary(rows)
        self.assertEqual(zero, service._empty_content_summary())

        canary_keys = {
            ("chinese", "pinyin_syllables", 1),
            ("math", "number_sense_20", 1),
            ("english", "letters_sounds", 1),
        }
        for row in rows:
            if (row["subject"], row["skill_id"], row["variant_ordinal"]) in canary_keys:
                row.update(
                    status="course_ready",
                    attempt_count=1,
                    content_gate_status="passed",
                    content_receipt_hash=hashlib.sha256(row["id"].encode()).hexdigest(),
                    _content_proof_verified=True,
                )
        canary = service._content_summary(rows)
        self.assertEqual(canary["contentCandidateItemCount"], 3)
        self.assertEqual(canary["contentFailedItemCount"], 0)
        self.assertEqual(
            canary["subjectContentProgress"],
            {
                "chinese": {"candidateCount": 1, "failedCount": 0, "targetCount": 12},
                "math": {"candidateCount": 1, "failedCount": 0, "targetCount": 9},
                "english": {"candidateCount": 1, "failedCount": 0, "targetCount": 9},
            },
        )
        self.assertEqual(
            canary["canary"],
            {
                "targetCount": 3,
                "candidateCount": 3,
                "failedCount": 0,
                "passed": True,
            },
        )
        self.assertFalse(canary["canActivate"])

        for row in rows[:-1]:
            row.update(
                status="course_ready",
                attempt_count=1,
                content_gate_status="passed",
                content_receipt_hash=hashlib.sha256(row["id"].encode()).hexdigest(),
                _content_proof_verified=True,
            )
        self.assertEqual(service._content_summary(rows)["contentCandidateItemCount"], 29)
        rows[-1].update(
            status="failed",
            attempt_count=1,
            content_gate_status="failed_deterministic",
            _content_proof_verified=False,
            _content_repair_verified=True,
        )
        repairable = service._content_summary(rows)
        self.assertEqual(repairable["contentFailedItemCount"], 0)
        rows[-1].update(
            status="course_ready",
            attempt_count=2,
            content_gate_status="passed",
            content_receipt_hash=hashlib.sha256(rows[-1]["id"].encode()).hexdigest(),
            _content_proof_verified=True,
        )
        complete = service._content_summary(rows)
        self.assertEqual(complete["contentCandidateItemCount"], 30)
        self.assertEqual(complete["contentFailedItemCount"], 0)
        self.assertFalse(complete["canActivate"])

        forged = dict(rows[0])
        forged["_content_proof_verified"] = False
        forged_summary = service._content_summary(
            [forged]
            + [
                {
                    **dict(row),
                    "status": "pending",
                    "content_gate_status": "not_started",
                    "content_receipt_hash": None,
                    "_content_proof_verified": False,
                }
                for row in rows[1:]
            ]
        )
        self.assertEqual(forged_summary["contentCandidateItemCount"], 0)


class _RecordingUpdateConnection:
    def __init__(self):
        self.executions = []

    def execute(self, sql, params=()):
        self.executions.append((sql, params))

        class Cursor:
            rowcount = 1

        return Cursor()


class _NoopHostValidator:
    def validate_primary_one_host_gate(self, *args, **kwargs):
        raise AssertionError("one Provider phase must not enter the Host gate")


class _CountingHostValidator:
    def __init__(self):
        self.delegate = LearningGeneratedCourseValidator()
        self.host_calls = 0

    def validate_primary_one_host_gate(self, *args, **kwargs):
        self.host_calls += 1
        return self.delegate.validate_primary_one_host_gate(*args, **kwargs)

    def validate_primary_one_accepted_receipt(self, proof):
        return self.delegate.validate_primary_one_accepted_receipt(proof)


class _OutlineOnlyAdapter(OpenMaicQuestionPhaseAdapter):
    def __init__(self):
        super().__init__(
            provider_name="kimi",
            model_name="moonshot-v1-8k",
            base_url="https://api.moonshot.cn/v1",
            api_key_env="APP_AI_API_KEY",
            provider_timeout_ms=1_000,
            max_tokens=2_000,
            temperature=0.2,
            process_timeout_seconds=1.0,
            process_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("the test adapter must not spawn a process")
            ),
        )
        self.execute_calls = 0

    def execute_phase(self, prepared):
        self.execute_calls += 1
        command = prepared.command
        return QuestionPhaseResult(
            request_id=command.generation_request_id,
            phase=command.phase,
            phase_ordinal=command.phase_ordinal,
            outcome="succeeded",
            checkpoint=_outline_checkpoint(),
            provider_request_id_hash="a" * 64,
            input_tokens=10,
            output_tokens=20,
            billing_evidence="reported",
            safe_error_code=None,
            elapsed_ms=1.0,
        )


class _CompletePinyinCanaryAdapter(_OutlineOnlyAdapter):
    def __init__(self):
        super().__init__()
        course, _target, _boundary, evidence, _identity = formal_host_fixture(
            "pinyin_syllables"
        )
        content = course["content"]
        teaching_flow = content["teachingFlow"]
        questions = []
        for source in content["questions"]:
            question = {
                key: copy.deepcopy(source[key])
                for key in (
                    "type",
                    "prompt",
                    "skill",
                    "hint",
                    "explanation",
                    "answer",
                    "acceptedAnswers",
                    "verificationExpression",
                    "choices",
                )
                if key in source
            }
            questions.append(question)
        self._course = copy.deepcopy(course)
        self._compiled = {
            "title": course["title"],
            "intro": content["intro"],
            "estimatedMinutes": content["estimatedMinutes"],
            "teachingFlow": {
                "teach": copy.deepcopy(teaching_flow["teach"]),
                "recap": copy.deepcopy(teaching_flow["recap"]),
            },
            "questions": questions,
        }
        self._formal_evidence = evidence
        self.phases: list[str] = []

    def execute_phase(self, prepared):
        self.execute_calls += 1
        command = prepared.command
        self.phases.append(command.phase)
        checkpoint_by_phase = {
            "outline": {
                "phaseStatus": "accepted",
                "outlinePlan": {
                    "courseTitle": self._course["title"],
                    "languageDirective": "使用简体中文教学。",
                    "outlines": [
                        {
                            "order": 1,
                            "title": "观察口形",
                            "description": "观察口形并听辨单韵母。",
                            "keyPoints": ["观察口形", "听辨读音"],
                        }
                    ],
                },
            },
            "raw_candidate": {
                "phaseStatus": "accepted",
                "rawCandidate": copy.deepcopy(self._compiled),
            },
            "candidate_repair": {
                "phaseStatus": "accepted",
                "candidate": copy.deepcopy(self._compiled),
                "hostCompilation": {
                    "compiler": "host_compiler",
                    "source": "candidate_repair_output",
                    "version": "v1",
                },
            },
            "lesson_text": {
                "phaseStatus": "accepted",
                "lessonText": {
                    "title": self._compiled["title"],
                    "intro": self._compiled["intro"],
                    "teachingFlow": copy.deepcopy(
                        self._compiled["teachingFlow"]
                    ),
                },
            },
            "reconciliation": {
                "phaseStatus": "accepted",
                "reconciliation": {
                    "estimatedMinutes": self._compiled["estimatedMinutes"],
                    "questions": copy.deepcopy(self._compiled["questions"]),
                },
                "hostReconciliation": {
                    "reconciler": "host_reconciler",
                    "source": "reconciliation_output",
                    "version": "v1",
                },
            },
        }
        if command.phase == "independent_verification":
            course = _build_candidate_course(command, self._compiled)
            public_questions = _public_questions(course)
            solution = copy.deepcopy(self._formal_evidence.independent_solution)
            solution["verificationRequestId"] = command.generation_request_id
            solution["publicQuestionHash"] = hashlib.sha256(
                json.dumps(
                    public_questions,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            for answer, question in zip(
                solution["answers"], public_questions
            ):
                answer["questionId"] = question["id"]
            checkpoint = {
                "phaseStatus": "accepted",
                "candidateCourse": course,
                "questionFingerprints": _build_question_fingerprints(
                    command, course
                ),
                "validation": _build_validation(
                    course,
                    existing_count=len(
                        command.checkpoint["existingFingerprints"]
                    ),
                ),
                "independentSolution": solution,
            }
        else:
            checkpoint = checkpoint_by_phase[command.phase]
        return QuestionPhaseResult(
            request_id=command.generation_request_id,
            phase=command.phase,
            phase_ordinal=command.phase_ordinal,
            outcome="succeeded",
            checkpoint=checkpoint,
            provider_request_id_hash="b" * 64,
            input_tokens=10,
            output_tokens=20,
            billing_evidence="reported",
            safe_error_code=None,
            elapsed_ms=1.0,
        )


class _RejectingPinyinCanaryAdapter(_CompletePinyinCanaryAdapter):
    """Task-4-canonical output whose answer fails the pure Task-6 rule."""

    def __init__(self):
        super().__init__()
        question = self._compiled["questions"][0]
        wrong = next(
            choice["id"]
            for choice in question["choices"]
            if choice["id"] != question["answer"]
        )
        question["answer"] = wrong
        self._formal_evidence.independent_solution["answers"][0][
            "answer"
        ] = wrong


class _BlockingOutlineAdapter(_OutlineOnlyAdapter):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def execute_phase(self, prepared):
        self.entered.set()
        if not self.release.wait(timeout=10):
            raise AssertionError("overlap test did not release the Provider")
        return super().execute_phase(prepared)


class LearningCatalogContentProviderMysqlTest(unittest.TestCase):
    def setUp(self):
        config = fresh_test_config()
        self.database_url = config["DATABASE_URL"]

    def tearDown(self):
        reset_mysql_test_database(self.database_url)

    def test_canary_provider_phase_persists_then_authenticates_next_phase(self):
        now = 100_000
        database = Database(self.database_url)
        adapter = _OutlineOnlyAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
            self.database_url,
            dynamic_generation_service=object(),
            lesson_package_service=object(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=_NoopHostValidator(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id="task7-real-canary-provider-phase",
            title="Task 7 Provider 单阶段",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        build_id = str(created["build"]["id"])
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            result = service.advance_content(build_id, heartbeat=lambda: True)

        self.assertEqual(result.kind, "progressed")
        self.assertEqual(adapter.execute_calls, 1)
        with database.transaction() as conn:
            item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (result.item_id,),
            ).fetchone()
            dispatches = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? ORDER BY phase_ordinal
                """,
                (result.item_id,),
            ).fetchall()
        self.assertEqual(item["subject"], "chinese")
        self.assertEqual(item["skill_id"], "pinyin_syllables")
        self.assertEqual(item["content_phase"], "raw_candidate")
        self.assertIsNone(item["content_lease_token"])
        self.assertEqual(item["content_work_unit_deadline_at"], now + 120_000)
        self.assertEqual(len(dispatches), 1)
        self.assertEqual(dispatches[0]["phase"], "outline")
        self.assertEqual(dispatches[0]["status"], "succeeded")

    def test_real_host_finalizes_candidate_course_job_and_item_atomically(self):
        now = 200_000
        database = Database(self.database_url)
        adapter = _CompletePinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
            self.database_url,
            dynamic_generation_service=object(),
            lesson_package_service=object(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id="task7-real-host-finalize",
            title="Task 7 Host 原子完成",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        build_id = str(created["build"]["id"])
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            provider_results = [
                service.advance_content(build_id, heartbeat=lambda: True)
                for _ in range(6)
            ]
            host_result = service.advance_content(
                build_id, heartbeat=lambda: True
            )

        self.assertEqual([value.kind for value in provider_results], ["progressed"] * 6)
        self.assertEqual(host_result.kind, "progressed")
        self.assertEqual(
            adapter.phases,
            [
                "outline",
                "raw_candidate",
                "candidate_repair",
                "lesson_text",
                "reconciliation",
                "independent_verification",
            ],
        )
        self.assertEqual(host_result.content_summary["contentCandidateItemCount"], 1)
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (host_result.item_id,),
            ).fetchone()
            release = conn.execute(
                "SELECT * FROM learning_catalog_releases WHERE id = ? LIMIT 1",
                (item["release_id"],),
            ).fetchone()
            dispatches = conn.execute(
                """
                SELECT * FROM learning_course_provider_dispatches
                WHERE build_item_id = ? ORDER BY phase_ordinal
                """,
                (item["id"],),
            ).fetchall()
            job = conn.execute(
                """
                SELECT * FROM learning_course_generation_jobs
                WHERE request_id = ? LIMIT 1
                """,
                (item["active_generation_request_id"],),
            ).fetchone()
            candidate = conn.execute(
                """
                SELECT * FROM learning_course_generation_candidates
                WHERE job_id = ? AND ordinal = 1 LIMIT 1
                """,
                (job["id"],),
            ).fetchone()
            course = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE id = ? AND version = ? LIMIT 1
                """,
                (item["course_id"], item["course_version"]),
            ).fetchone()
            catalog_item_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_catalog_release_items
                WHERE release_id = ?
                """,
                (item["release_id"],),
            ).fetchone()["count"]
            package_pollution = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_catalog_build_items
                WHERE build_job_id = ? AND (
                  package_attempt_count <> 0 OR active_package_request_id IS NOT NULL
                  OR package_id IS NOT NULL OR package_version IS NOT NULL
                )
                """,
                (build_id,),
            ).fetchone()["count"]

        envelope = json.loads(candidate["validation_json"])
        self.assertEqual(item["status"], "course_ready")
        self.assertEqual(item["content_phase"], "course_ready")
        self.assertEqual(item["content_gate_status"], "passed")
        self.assertEqual(item["content_receipt_hash"], envelope["hostGateReceiptHash"])
        self.assertEqual(
            set(envelope),
            {
                "schemaVersion",
                "contentFingerprint",
                "hostGateReceipt",
                "hostGateReceiptHash",
            },
        )
        self.assertEqual(candidate["status"], "course_validated")
        self.assertEqual(job["status"], "validated")
        self.assertEqual(course["status"], "validated")
        self.assertEqual(course["quality_status"], "auto_validated")
        self.assertIsNone(course["published_at"])
        self.assertEqual(
            course["generation_content_hash"], envelope["contentFingerprint"]
        )
        self.assertEqual(release["status"], "draft")
        self.assertEqual(len(dispatches), 6)
        self.assertTrue(all(row["status"] == "succeeded" for row in dispatches))
        self.assertEqual(catalog_item_count, 0)
        self.assertEqual(package_pollution, 0)

        phases_before_drift = list(adapter.phases)
        with database.transaction() as conn:
            conn.execute(
                """
                UPDATE learning_course_generation_jobs
                SET model = 'drifted-model'
                WHERE id = ?
                """,
                (job["id"],),
            )
        drifted = service.advance_content(build_id, heartbeat=lambda: True)
        with database.transaction() as conn:
            fenced_build = conn.execute(
                """
                SELECT status, error_code FROM learning_catalog_build_jobs
                WHERE id = ? LIMIT 1
                """,
                (build_id,),
            ).fetchone()

        self.assertEqual(drifted.kind, "failed")
        self.assertEqual(
            drifted.content_summary["contentCandidateItemCount"], 0
        )
        self.assertEqual(adapter.phases, phases_before_drift)
        self.assertEqual(fenced_build["status"], "failed")
        self.assertEqual(
            fenced_build["error_code"],
            "preparation_content_contract_drift",
        )

    def test_real_rejection_persists_proof_then_authorizes_one_attempt_two(self):
        now = 250_000
        database = Database(self.database_url)
        adapter = _RejectingPinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
            self.database_url,
            dynamic_generation_service=object(),
            lesson_package_service=object(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id="task7-real-attempt-two-authority",
            title="Task 7 唯一内容修复授权",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        build_id = str(created["build"]["id"])
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            provider_results = [
                service.advance_content(build_id, heartbeat=lambda: True)
                for _ in range(6)
            ]
            rejected = service.advance_content(
                build_id, heartbeat=lambda: True
            )

        self.assertEqual(
            [result.kind for result in provider_results], ["progressed"] * 6
        )
        self.assertEqual(rejected.kind, "progressed")
        self.assertEqual(
            rejected.content_summary["contentCandidateItemCount"], 0
        )
        self.assertEqual(rejected.content_summary["contentFailedItemCount"], 0)
        phases_after_rejection = list(adapter.phases)
        with database.transaction() as conn:
            item = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (rejected.item_id,),
            ).fetchone()
            job = conn.execute(
                """
                SELECT * FROM learning_course_generation_jobs
                WHERE request_id = ? LIMIT 1
                """,
                (item["generation_request_id"],),
            ).fetchone()
            candidate = conn.execute(
                """
                SELECT * FROM learning_course_generation_candidates
                WHERE job_id = ? AND ordinal = 1 LIMIT 1
                """,
                (job["id"],),
            ).fetchone()
            course = conn.execute(
                """
                SELECT * FROM learning_courses
                WHERE id = ? AND version = ? LIMIT 1
                """,
                (item["course_id"], item["course_version"]),
            ).fetchone()
        attempt_one_envelope = str(candidate["validation_json"])
        envelope = json.loads(attempt_one_envelope)
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["attempt_count"], 1)
        self.assertEqual(item["content_gate_status"], "failed_deterministic")
        self.assertEqual(job["status"], "failed")
        self.assertEqual(candidate["status"], "rejected")
        self.assertEqual(envelope["hostGateReceipt"]["outcome"], "rejected")
        self.assertEqual(course["status"], "unverified")
        self.assertEqual(course["quality_status"], "legacy_unreviewed")
        self.assertIsNone(course["published_at"])

        with service.repository.transaction() as conn:
            canonical_inventory = service.repository.load_content_proof_inventory(
                conn, build_id=build_id
            )
            baseline = service._audit_locked_content_inventory(
                conn=conn,
                inventory=canonical_inventory,
            )
            self.assertEqual(
                baseline["repairableItemIds"], frozenset({str(item["id"])})
            )

            def mutate_missing_dispatch(value):
                value["evidence"][0]["attemptHistories"][1][
                    "dispatches"
                ].pop()

            def mutate_extra_dispatch(value):
                history = value["evidence"][0]["attemptHistories"][1]
                extra = copy.deepcopy(history["dispatches"][-1])
                extra["id"] = str(extra["id"]) + "-extra"
                history["dispatches"].append(extra)

            def mutate_open_dispatch(value):
                value["evidence"][0]["attemptHistories"][1][
                    "dispatches"
                ][0]["status"] = "dispatched"

            def mutate_attempt_two_residue(value):
                value["evidence"][0]["attemptHistories"][2][
                    "dispatches"
                ].append({"id": "forged-attempt-two-dispatch"})

            def mutate_envelope(value):
                value["evidence"][0]["attemptHistories"][1][
                    "candidates"
                ][0]["validation_json"] = "{}"

            def mutate_course(value):
                value["evidence"][0]["attemptHistories"][1]["courses"][0][
                    "content_json"
                ] = "{}"

            def mutate_job_profile(value):
                value["evidence"][0]["attemptHistories"][1]["jobs"][0][
                    "model"
                ] = "drifted-model"

            def mutate_pointer(value):
                value["evidence"][0]["item"]["course_id"] = "wrong-course"
                for row in value["items"]:
                    if str(row["id"]) == str(item["id"]):
                        row["course_id"] = "wrong-course"

            def mutate_control_residue(value):
                value["evidence"][0]["attemptHistories"][1][
                    "candidates"
                ][0]["error_code"] = "preparation_content_contract_drift"

            for label, mutation in (
                ("missing-dispatch", mutate_missing_dispatch),
                ("extra-dispatch", mutate_extra_dispatch),
                ("open-dispatch", mutate_open_dispatch),
                ("attempt-two-residue", mutate_attempt_two_residue),
                ("forged-envelope", mutate_envelope),
                ("changed-course", mutate_course),
                ("job-profile-drift", mutate_job_profile),
                ("wrong-item-pointer", mutate_pointer),
                ("control-error-residue", mutate_control_residue),
            ):
                with self.subTest(forbidden_attempt_two_source=label):
                    drifted_inventory = copy.deepcopy(canonical_inventory)
                    mutation(drifted_inventory)
                    with self.assertRaises(
                        (
                            ValueError,
                            PrimaryOneHostGateControlError,
                            PrimaryOneHostGateDependencyError,
                        )
                    ):
                        service._audit_locked_content_inventory(
                            conn=conn,
                            inventory=drifted_inventory,
                        )

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            authorized = service.advance_content(
                build_id, heartbeat=lambda: True
            )

        self.assertEqual(authorized.kind, "progressed")
        self.assertEqual(adapter.phases, phases_after_rejection)
        with database.transaction() as conn:
            claimed = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (item["id"],),
            ).fetchone()
            persisted_attempt_one = conn.execute(
                """
                SELECT * FROM learning_course_generation_candidates
                WHERE id = ? LIMIT 1
                """,
                (candidate["id"],),
            ).fetchone()
            attempt_two_dispatch_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 2
                """,
                (item["id"],),
            ).fetchone()["count"]
            attempt_two_job_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_course_generation_jobs
                WHERE request_id = ?
                """,
                (str(item["generation_request_id"]) + ".attempt2",),
            ).fetchone()["count"]
        self.assertEqual(claimed["attempt_count"], 2)
        self.assertEqual(claimed["content_claim_attempt_ordinal"], 2)
        self.assertEqual(claimed["content_phase"], "outline")
        self.assertEqual(
            claimed["active_generation_request_id"],
            str(item["generation_request_id"]) + ".attempt2",
        )
        self.assertEqual(claimed["course_id"], item["course_id"])
        self.assertEqual(claimed["course_version"], item["course_version"])
        self.assertEqual(
            persisted_attempt_one["validation_json"], attempt_one_envelope
        )
        self.assertEqual(attempt_two_dispatch_count, 0)
        self.assertEqual(attempt_two_job_count, 0)

    def test_two_real_attempt_two_claimers_have_one_cas_winner(self):
        now = 275_000
        database = Database(self.database_url)
        adapter = _RejectingPinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
            self.database_url,
            dynamic_generation_service=object(),
            lesson_package_service=object(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id="task7-real-attempt-two-overlap",
            title="Task 7 双修复授权",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        build_id = str(created["build"]["id"])
        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            results = [
                service.advance_content(build_id, heartbeat=lambda: True)
                for _ in range(7)
            ]
        self.assertEqual([result.kind for result in results], ["progressed"] * 7)
        with database.transaction() as conn:
            rejected_item = conn.execute(
                """
                SELECT * FROM learning_catalog_build_items
                WHERE id = ? LIMIT 1
                """,
                (results[-1].item_id,),
            ).fetchone()

        barrier = threading.Barrier(2)
        claims: list[object] = []
        errors: list[BaseException] = []
        phases_before_claim = list(adapter.phases)

        def claim_worker():
            try:
                barrier.wait(timeout=10)
                with patch.dict(
                    os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
                ):
                    claims.append(
                        service.advance_content(
                            build_id, heartbeat=lambda: True
                        )
                    )
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=claim_worker, name="task7-attempt2-1")
        second = threading.Thread(target=claim_worker, name="task7-attempt2-2")
        first.start()
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(claims), 2)
        with database.transaction() as conn:
            claimed = conn.execute(
                "SELECT * FROM learning_catalog_build_items WHERE id = ? LIMIT 1",
                (rejected_item["id"],),
            ).fetchone()
            attempt_two_dispatch_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_course_provider_dispatches
                WHERE build_item_id = ? AND logical_attempt = 2
                """,
                (rejected_item["id"],),
            ).fetchone()["count"]
            attempt_two_job_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_course_generation_jobs
                WHERE request_id = ?
                """,
                (str(rejected_item["generation_request_id"]) + ".attempt2",),
            ).fetchone()["count"]
        diagnostics = {
            "kinds": [claim.kind for claim in claims],
            "status": claimed["status"],
            "phase": claimed["content_phase"],
            "attempt": claimed["attempt_count"],
            "dispatchCount": attempt_two_dispatch_count,
            "jobCount": attempt_two_job_count,
            "processDelta": len(adapter.phases) - len(phases_before_claim),
        }
        self.assertTrue(
            all(claim.kind in {"progressed", "busy", "stale"} for claim in claims),
            diagnostics,
        )
        self.assertGreaterEqual(
            sum(claim.kind == "progressed" for claim in claims),
            1,
            diagnostics,
        )
        self.assertEqual(claimed["attempt_count"], 2)
        self.assertLessEqual(attempt_two_dispatch_count, 1)
        self.assertLessEqual(len(adapter.phases) - len(phases_before_claim), 1)

    def test_two_real_claimers_converge_on_one_item_dispatch_and_process(self):
        now = 300_000
        database = Database(self.database_url)
        adapter = _BlockingOutlineAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
            self.database_url,
            dynamic_generation_service=object(),
            lesson_package_service=object(),
            staged_content_candidate_generator=staged,
            primary_one_host_validator=_NoopHostValidator(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")
        created = service.create_preparation_content_build(
            request_id="task7-real-overlap",
            title="Task 7 双 claimer",
            preparation_target=target,
            target_fingerprint=preparation_target_fingerprint(target),
        )
        build_id = str(created["build"]["id"])
        results: list[object] = []
        errors: list[BaseException] = []
        connection_ids: list[int] = []

        def worker():
            try:
                with database.transaction() as marker_conn:
                    connection_ids.append(
                        int(
                            marker_conn.execute(
                                "SELECT CONNECTION_ID() AS id"
                            ).fetchone()["id"]
                        )
                    )
                    results.append(
                        service.advance_content(
                            build_id, heartbeat=lambda: True
                        )
                    )
            except BaseException as exc:
                errors.append(exc)

        with patch.dict(os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False):
            first = threading.Thread(target=worker, name="task7-claimer-1")
            first.start()
            self.assertTrue(adapter.entered.wait(timeout=10))
            second = threading.Thread(target=worker, name="task7-claimer-2")
            second.start()
            second.join(timeout=10)
            self.assertFalse(second.is_alive(), "second claimer did not converge")
            adapter.release.set()
            first.join(timeout=10)
            self.assertFalse(first.is_alive(), "first claimer did not finish")

        self.assertEqual(errors, [])
        self.assertEqual(len(connection_ids), 2)
        self.assertEqual(len(set(connection_ids)), 2)
        self.assertEqual(
            sorted(result.kind for result in results),
            ["busy", "progressed"],
        )
        self.assertEqual(adapter.execute_calls, 1)
        with database.transaction() as conn:
            dispatch_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_course_provider_dispatches
                WHERE build_item_id IN (
                  SELECT id FROM learning_catalog_build_items
                  WHERE build_job_id = ?
                )
                """,
                (build_id,),
            ).fetchone()["count"]
            claimed_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_catalog_build_items
                WHERE build_job_id = ? AND attempt_count <> 0
                """,
                (build_id,),
            ).fetchone()["count"]
            processing_count = conn.execute(
                """
                SELECT COUNT(*) AS count FROM learning_catalog_build_items
                WHERE build_job_id = ? AND status = 'processing'
                """,
                (build_id,),
            ).fetchone()["count"]
        self.assertEqual(dispatch_count, 1)
        self.assertEqual(claimed_count, 1)
        self.assertEqual(processing_count, 1)

    def test_provider_binder_false_or_raise_releases_exact_claim_before_process(self):
        now = 325_000
        database = Database(self.database_url)
        adapter = _OutlineOnlyAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=_NoopHostValidator(),
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")

        for label in ("false", "raise", "cleanup_cas_loss"):
            with self.subTest(binder=label):
                created = service.create_preparation_content_build(
                    request_id=f"task8-provider-binder-{label}",
                    title=f"Task 8 Provider binder {label}",
                    preparation_target=target,
                    target_fingerprint=preparation_target_fingerprint(target),
                )
                build_id = str(created["build"]["id"])
                claims = []

                def binder(claim):
                    claims.append(claim)
                    if label == "raise":
                        raise RuntimeError("private binder failure")
                    return False

                cleanup = (
                    patch.object(
                        service.repository,
                        "release_content_provider_dependency",
                        return_value=False,
                    )
                    if label == "cleanup_cas_loss"
                    else nullcontext()
                )
                with cleanup:
                    result = service.advance_content(
                        build_id,
                        heartbeat=lambda: (_ for _ in ()).throw(
                            AssertionError("rejected binder reached heartbeat")
                        ),
                        bind_work_unit=binder,
                    )

                self.assertEqual(result.kind, "stale")
                self.assertEqual(len(claims), 1)
                self.assertEqual(claims[0].work_unit_kind, "provider_phase")
                self.assertEqual(adapter.execute_calls, 0)
                with database.transaction() as conn:
                    item = conn.execute(
                        """
                        SELECT * FROM learning_catalog_build_items
                        WHERE id = ? LIMIT 1
                        """,
                        (claims[0].item_id,),
                    ).fetchone()
                    dispatch_count = conn.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM learning_course_provider_dispatches
                        WHERE build_item_id = ?
                        """,
                        (claims[0].item_id,),
                    ).fetchone()["count"]
                self.assertEqual(item["status"], "processing")
                self.assertEqual(item["attempt_count"], 1)
                self.assertEqual(item["content_phase"], "outline")
                if label == "cleanup_cas_loss":
                    self.assertEqual(
                        item["content_lease_token"], claims[0].item_lease_token
                    )
                    self.assertEqual(
                        item["content_lease_expires_at"],
                        claims[0].work_unit_deadline_at,
                    )
                else:
                    self.assertIsNone(item["content_lease_token"])
                    self.assertIsNone(item["content_lease_expires_at"])
                self.assertEqual(
                    item["content_work_unit_deadline_at"],
                    claims[0].work_unit_deadline_at,
                )
                self.assertEqual(
                    item["content_provider_attempt_hard_deadline_at"],
                    now + 30 * 60 * 1000,
                )
                self.assertEqual(dispatch_count, 0)

    def test_host_binder_false_or_raise_preserves_live_retry_claim_before_host(self):
        now = 350_000
        database = Database(self.database_url)
        adapter = _CompletePinyinCanaryAdapter()
        staged = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(database),
            adapter=adapter,
            clock_ms=lambda: now,
        )
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
        host = _CountingHostValidator()
        service = LearningCatalogReleaseService(
            self.database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            staged_content_candidate_generator=staged,
            primary_one_host_validator=host,
            question_phase_provider_profiles=profiles,
            clock_ms=lambda: now,
        )
        target = build_preparation_target("primary_1")

        for label in ("false", "raise", "cleanup_cas_loss"):
            with self.subTest(binder=label), patch.dict(
                os.environ, {"APP_AI_API_KEY": "test-only"}, clear=False
            ):
                created = service.create_preparation_content_build(
                    request_id=f"task8-host-binder-{label}",
                    title=f"Task 8 Host binder {label}",
                    preparation_target=target,
                    target_fingerprint=preparation_target_fingerprint(target),
                )
                build_id = str(created["build"]["id"])
                provider_results = [
                    service.advance_content(build_id, heartbeat=lambda: True)
                    for _ in range(6)
                ]
                self.assertEqual(
                    [result.kind for result in provider_results],
                    ["progressed"] * 6,
                )
                claims = []

                def binder(claim):
                    claims.append(claim)
                    if label == "raise":
                        raise RuntimeError("private binder failure")
                    return False

                host_calls_before = host.host_calls
                cleanup = (
                    patch.object(
                        service.repository,
                        "release_content_host_dependency",
                        return_value="stale",
                    )
                    if label == "cleanup_cas_loss"
                    else nullcontext()
                )
                with cleanup:
                    result = service.advance_content(
                        build_id,
                        heartbeat=lambda: (_ for _ in ()).throw(
                            AssertionError("Host binder reached Provider heartbeat")
                        ),
                        bind_work_unit=binder,
                    )

                self.assertEqual(result.kind, "stale")
                self.assertEqual(host.host_calls, host_calls_before)
                self.assertEqual(len(claims), 1)
                claim = claims[0]
                self.assertEqual(claim.work_unit_kind, "host_gate")
                self.assertEqual(claim.content_phase, "host_gate_running")
                with database.transaction() as conn:
                    item = conn.execute(
                        """
                        SELECT * FROM learning_catalog_build_items
                        WHERE id = ? LIMIT 1
                        """,
                        (claim.item_id,),
                    ).fetchone()
                self.assertEqual(item["status"], "processing")
                self.assertEqual(item["content_phase"], "host_gate_running")
                self.assertEqual(
                    item["content_gate_status"],
                    "pending" if label == "cleanup_cas_loss" else "retry_wait",
                )
                self.assertEqual(item["content_gate_attempt_count"], 1)
                self.assertEqual(item["content_lease_token"], claim.item_lease_token)
                self.assertEqual(
                    item["content_lease_expires_at"], claim.work_unit_deadline_at
                )
                self.assertEqual(
                    item["content_work_unit_deadline_at"],
                    claim.work_unit_deadline_at,
                )


if __name__ == "__main__":
    unittest.main()
